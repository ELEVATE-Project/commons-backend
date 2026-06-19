from django.db import models
from simple_history.models import HistoricalRecords
from chatbot.models import CompanyBot


class BotVernacular(models.Model):
    """
    Stores language-specific (vernacular) configurations for a company bot.
    Allows customized introductory and error messages per language.
    """

    company_bot = models.ForeignKey(CompanyBot, on_delete=models.SET_NULL, related_name='bot_vernacular', null=True)

    language = models.CharField(max_length=250, help_text="Language code, Example for English use en.")
    introductory_message = models.TextField(
        null=True, blank=True, help_text="Provide an introductory message that the bot will present when the "
                                         "conversation starts."
    )
    alt_introductory_message = models.TextField(
        null=True, blank=True, help_text="Provide an alternate introductory message that the bot will present when the "
                                         "conversation starts."
    )
    name = models.CharField(max_length=100,null=True, blank=True, help_text="Enter the name of the bot.")
    error_message = models.TextField(
        null=True, blank=True, help_text="Provide an error message that the bot will display."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        db_table = 'shikshalokam"."bot_vernacular'
        indexes = [
            models.Index(fields=['language']),
            models.Index(fields=['created_at']),
            models.Index(fields=['company_bot']),
        ]
