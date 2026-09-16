import json

from rest_framework import serializers

from chatbot.serializer.profile_serializer import ProfileSerializer
from chatbot.serializer.story_serializer import StoryRetrieveSerializer
from shikshalokam.models.project_models import Project, Task, Evidence, LearningResources
from shikshalokam.models.template_models import ProjectTemplate


class ProjectTemplateSerializer(serializers.ModelSerializer):
    """Serializer for ProjectTemplate model"""
    class Meta:
        model = ProjectTemplate
        fields = '__all__'


class TaskSerializer(serializers.ModelSerializer):
    """Serializer for Task model"""
    class Meta:
        model = Task
        fields = '__all__'


class EvidenceSerializer(serializers.ModelSerializer):
    """Serializer for Evidence model"""
    class Meta:
        model = Evidence
        fields = '__all__'


class LearningResourceSerializer(serializers.ModelSerializer):
    """Serializer for LearningResources model"""
    class Meta:
        model = LearningResources
        fields = '__all__'


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model"""
    story = StoryRetrieveSerializer(read_only=True)
    project_template = ProjectTemplateSerializer(read_only=True)
    author = ProfileSerializer(read_only=True)
    task = TaskSerializer(many=True, read_only=True)
    evidence = EvidenceSerializer(many=True, read_only=True)
    learning_resource = LearningResourceSerializer(many=True, read_only=True)
    
    class Meta:
        model = Project
        fields = '__all__'

