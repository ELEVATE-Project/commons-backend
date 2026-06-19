import os
from django.contrib.auth.models import User
from django.db import models
from django_s3_storage.storage import S3Storage
from simple_history.models import HistoricalRecords
from shikshalokam.models import Project, Task

storage = S3Storage(aws_s3_bucket_name='mohini-static.shikshalokam.org')
S3_BASE_URL = os.getenv('S3_MEDIA_URL')


class ProjectVernacular(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='project_vernacular',
                             null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, related_name='project_vernacular',
                             null=True, blank=True)

    language = models.CharField(max_length=250)
    details = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'shikshalokam"."project_vernacular'
        indexes = [
            models.Index(fields=['language']),
            models.Index(fields=['created_at']),
            models.Index(fields=['project']),
            models.Index(fields=['task']),
        ]
