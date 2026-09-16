from django.db import models
from simple_history.models import HistoricalRecords
from chatbot.models import CompanyBot


class StoryVernacular(models.Model):
    """
    Stores language-specific translations for story-related bot content.
    Links a company bot to translated JSON text for a given language.
    """

    company_bot = models.ForeignKey(CompanyBot, on_delete=models.SET_NULL, related_name='story_vernacular', null=True)

    translation_json = models.JSONField(
        null=True, blank=True,
        help_text="JSON object containing translated text in the specified language."
    )
    language = models.CharField(max_length=250, help_text="Language code, Example for English use en.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=['language']),
            models.Index(fields=['created_at']),
            models.Index(fields=['company_bot']),
        ]

    def __str__(self):
        return f"StoryVernacular ({self.language}) - {self.company_bot}"
