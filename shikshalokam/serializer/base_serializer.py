import json

from rest_framework import serializers

from chatbot.serializer.profile_serializer import ProfileSerializer
from shikshalokam.models.project_models import Project, Task, Evidence, LearningResources
from shikshalokam.models.template_models import Category, ProjectTemplate
from shikshalokam.models.wishlist_model import ProjectWishlist


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


class ProjectTemplateSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    class Meta:
        model = ProjectTemplate
        fields = '__all__'


class LearningResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningResources
        fields = '__all__'


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = '__all__'


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = '__all__'


class ProjectWishlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectWishlist
        fields = '__all__'


class ProjectSerializer(serializers.ModelSerializer):
    project_template = ProjectTemplateSerializer(read_only=True)
    task = TaskSerializer(many=True, read_only=True)
    author = ProfileSerializer(read_only=True)
    categories = serializers.ListField(child=serializers.JSONField(), required=False)
    recommended_for = serializers.ListField(child=serializers.JSONField(), required=False)
    evidence = EvidenceSerializer(many=True, read_only=True)
    learning_resource = LearningResourceSerializer(many=True, read_only=True)

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        user = self.context.get('author')
        print("author: ", user)
        print("project: ", instance)
        if user and instance:
            in_wishlist = ProjectWishlist.objects.filter(author=user, project=instance).exists()
            print("wishlist: ", in_wishlist)
            representation['wishlist'] = in_wishlist

        for field in ['categories', 'recommended_for', 'keywords']:
            try:
                representation[field] = json.loads(getattr(instance, field)) if getattr(instance, field) else []
            except json.JSONDecodeError:
                representation[field] = []
        return representation

    def to_internal_value(self, data):
        internal_value = super().to_internal_value(data)
        for field in ['categories', 'recommended_for', 'keywords']:
            if field in data:
                internal_value[field] = json.dumps(data[field])
        return internal_value

    class Meta:
        model = Project
        fields = '__all__'
