from django.db import models
from simple_history.models import HistoricalRecords
from chatbot.models import Profile
from shikshalokam.models import Project


class ProjectWishlist(models.Model):
    author = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="wishlist")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='wishlist')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        db_table = 'shikshalokam"."project_wishlist'

        indexes = [
            models.Index(fields=['author']),
            models.Index(fields=['project']),
            models.Index(fields=['created_at']),
        ]
