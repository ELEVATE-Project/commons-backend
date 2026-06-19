from django.contrib.auth.models import User
from django.db import models
from simple_history.models import HistoricalRecords


class Category(models.Model):
    name = models.CharField(max_length=1000, null=True, blank=True)
    category_id = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'shikshalokam"."category'

        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['category_id']),
            models.Index(fields=['created_at']),
        ]


class ProjectTemplate(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, related_name="project_template",
                                 null=True, blank=True)
    title = models.CharField(max_length=1000, null=True, blank=True)
    template_id = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'shikshalokam"."project_template'
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['template_id']),
            models.Index(fields=['created_at']),
            models.Index(fields=['category']),
        ]