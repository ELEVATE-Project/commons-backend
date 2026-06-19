from rest_framework import serializers
from chatbot.models.media_models import ProfileMedia
from chatbot.models.profile_models import Profile
from chatbot.models.company_models import CompanyChat
from chatbot.models.geo_models import ProfileAddress
from chatbot.serializer.company_serializer import CompanySerializer


class ProfileAddressSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProfileAddress
        fields = '__all__'
        extra_kwargs = {'profile': {'required': False}}


class ProfileMediaSerializer(serializers.ModelSerializer):
    public_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ProfileMedia
        fields = '__all__'

    def get_public_url(self, obj):
        return obj.get_public_url()


class ProfileSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    profile_address = ProfileAddressSerializer(many=True, required=False)
    profile_media = ProfileMediaSerializer(many=True, required=False)

    class Meta:
        model = Profile
        exclude = ['password', ]

    def list(self, request, *args, **kwargs):
        print("GET request received")
        return super().list(request, *args, **kwargs)

    def create(self, validated_data):
        profile_address_data = validated_data.pop('profile_address', None)
        profile_media_data = validated_data.pop('profile_media', None)

        profile = Profile.objects.create(**validated_data)
        if profile_address_data:
            for address_data in profile_address_data:
                ProfileAddress.objects.create(profile=profile, **address_data)

        if profile_media_data:
            for profile_media in profile_media_data:
                ProfileMedia.objects.create(profile=profile, **profile_media)

        return profile

    def update(self, instance, validated_data):
        profile_address_data = validated_data.pop('profile_address', [])
        profile_media_data = validated_data.pop('profile_media', [])

        for field_name, value in validated_data.items():
            setattr(instance, field_name, value)

        # Update or create ProfileAddress instances
        for address_data in profile_address_data:
            profile_address = ProfileAddress.objects.filter(profile=instance)
            if len(profile_address) > 0:
                profile_address = profile_address[0]
                for field_name, value in address_data.items():
                    setattr(profile_address, field_name, value)
                profile_address.save()
            else:
                ProfileAddress.objects.create(profile=instance, **address_data)

        # Update or create ProfileMedia instances
        for media_data in profile_media_data:
            media_instance, _ = ProfileMedia.objects.update_or_create(
                profile=instance, id=media_data.get('id'), defaults=media_data
            )

        instance.save()
        return instance

class CompanyChatSerializer(serializers.ModelSerializer):
    sender = ProfileSerializer(read_only=True)
    receiver = ProfileSerializer(read_only=True)

    class Meta:
        model = CompanyChat
        fields = '__all__'
