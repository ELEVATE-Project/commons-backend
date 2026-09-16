from rest_framework import serializers
from chatbot.models import Story, StoryMedia, StoryTranslation
from chatbot.serializer.profile_serializer import ProfileSerializer
from chatbot.utils.story_utils.base.translation_mixins import TranslationMixin


class StoryMediaCreateSerializer(serializers.ModelSerializer):
    public_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = StoryMedia
        exclude = ('base64_str', )

    def get_public_url(self, obj):
        return obj.get_public_url()


class StoryMediaRetrieveSerializer(serializers.ModelSerializer):
    public_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = StoryMedia
        fields = '__all__'

    def get_public_url(self, obj):
        return obj.get_public_url()


class StoryCreateSerializer(serializers.ModelSerializer):
    story_media = StoryMediaCreateSerializer(many=True, read_only=True)

    class Meta:
        model = Story
        exclude = ('formatted_content', )


class StoryRetrieveSerializer(TranslationMixin, serializers.ModelSerializer):
    story_media = StoryMediaRetrieveSerializer(many=True, read_only=True)

    def to_representation(self, instance):
        """Override to return translated content based on language"""
        data = super().to_representation(instance)
        return self.apply_translation(data, instance)

    class Meta:
        model = Story
        fields = '__all__'


class StoryFullSerializer(TranslationMixin, serializers.ModelSerializer):
    story_media = StoryMediaCreateSerializer(many=True, read_only=True)
    author = ProfileSerializer(read_only=True)

    def to_representation(self, instance):
        """Override to return translated content based on language"""
        data = super().to_representation(instance)
        return self.apply_translation(data, instance)

    class Meta:
        model = Story
        fields = '__all__'
