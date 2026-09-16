import os

from django.contrib.auth.models import User
from django.db import models
from django_s3_storage.storage import S3Storage
from simple_history.models import HistoricalRecords

from chatbot.models import Profile, Story
from shikshalokam.models.enums import ProjectStatus, TaskMandatoryStatus, ProjectCreatedBy

storage = S3Storage(aws_s3_bucket_name='mohini-static.shikshalokam.org')
S3_BASE_URL = os.getenv('S3_MEDIA_URL')


class Project(models.Model):
    story = models.ForeignKey(Story, related_name='project', on_delete=models.SET_NULL, null=True, blank=True)
    project_template = models.ForeignKey('shikshalokam.ProjectTemplate', on_delete=models.CASCADE, related_name="project",
                                         null=True, blank=True)
    author = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name="project")

    categories = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    title = models.CharField(max_length=1000, null=True, blank=True)
    expected_title = models.CharField(max_length=1000, null=True, blank=True)
    actual_title = models.CharField(max_length=1000, null=True, blank=True)

    problem_statement = models.TextField(null=True, blank=True)
    expected_problem_statement = models.TextField(null=True, blank=True)
    actual_problem_statement = models.TextField(null=True, blank=True)

    template_id = models.CharField(max_length=500, null=True, blank=True)
    project_id = models.CharField(max_length=500, unique=True)
    program_id = models.CharField(max_length=500, null=True, blank=True)
    program_name = models.CharField(max_length=1000, null=True, blank=True)

    recommended_for = models.TextField(null=True, blank=True)
    keywords = models.TextField(null=True, blank=True)

    objective = models.TextField(null=True, blank=True)
    expected_objective = models.TextField(null=True, blank=True)
    actual_objective = models.TextField(null=True, blank=True)

    duration = models.CharField(max_length=1000, null=True, blank=True)
    expected_duration = models.CharField(max_length=1000, null=True, blank=True)
    actual_duration = models.CharField(max_length=1000, null=True, blank=True)

    project_status = models.CharField(max_length=100, choices=ProjectStatus.choices, null=True, blank=True)
    generated_by = models.CharField(max_length=100, choices=ProjectCreatedBy.choices,
                                    default=ProjectCreatedBy.AI_GENERATED)

    other_params = models.JSONField(null=True, blank=True)
    project_language = models.CharField(max_length=100, null=True, blank=True)

    project_source = models.TextField(null=True, blank=True)
    program_source = models.TextField(null=True, blank=True)

    resource_name = models.CharField(max_length=1000, null=True, blank=True)
    resource_link = models.CharField(max_length=2000, null=True, blank=True)

    project_start_date = models.DateTimeField(null=True, blank=True)
    project_end_date = models.DateTimeField(null=True, blank=True)
    solution_download_count = models.PositiveBigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.title if self.title else "Unnamed Project"

    class Meta:
        db_table = 'shikshalokam"."project'
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['actual_title']),
            models.Index(fields=['project_id']),
            models.Index(fields=['recommended_for']),
            models.Index(fields=['keywords']),
            models.Index(fields=['objective']),
            models.Index(fields=['duration']),
            models.Index(fields=['project_status']),
            models.Index(fields=['resource_name']),
            models.Index(fields=['project_start_date']),
            models.Index(fields=['project_end_date']),
            models.Index(fields=['created_at']),
            models.Index(fields=['story']),
            models.Index(fields=['project_template']),
            models.Index(fields=['author']),
        ]


class Task(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='task')
    parent_task_id = models.CharField(max_length=255, null=True, blank=True)
    task_id = models.CharField(max_length=255, null=True, blank=True)
    task_name = models.CharField(max_length=1000, null=True, blank=True)
    mandatory_task = models.CharField(max_length=100, choices=TaskMandatoryStatus.choices, null=True, blank=True)
    observation_name = models.CharField(max_length=255, null=True, blank=True)
    number_of_submission_observation = models.IntegerField(null=True, blank=True)
    other_params = models.JSONField(null=True, blank=True)
    task_status = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    source = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'shikshalokam"."task'
        indexes = [
            models.Index(fields=['parent_task_id']),
            models.Index(fields=['task_id']),
            models.Index(fields=['task_name']),
            models.Index(fields=['mandatory_task']),
            models.Index(fields=['observation_name']),
            models.Index(fields=['number_of_submission_observation']),
            models.Index(fields=['created_at']),
            models.Index(fields=['project']),
        ]


class Evidence(models.Model):
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, related_name='evidence', null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='evidence', null=True, blank=True)

    remark = models.CharField(max_length=1000, null=True, blank=True)
    evidence_link = models.CharField(max_length=2000, null=True, blank=True)

    type = models.CharField(max_length=250, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'shikshalokam"."evidence'
        indexes = [
            models.Index(fields=['remark']),
            models.Index(fields=['evidence_link']),
            models.Index(fields=['created_at']),
            models.Index(fields=['task']),
            models.Index(fields=['project']),
        ]


class LearningResources(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='learning_resource',
                                null=True, blank=True)

    name = models.CharField(max_length=1000, null=True, blank=True)
    link = models.CharField(max_length=2000, null=True, blank=True)

    resource_id = models.CharField(max_length=500, null=True, blank=True)
    app = models.CharField(max_length=500, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'shikshalokam"."learning_resource'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['link']),
            models.Index(fields=['created_at']),
            models.Index(fields=['resource_id']),
            models.Index(fields=['project']),
        ]