from django.db import models
from simple_history.models import HistoricalRecords
from chatbot.models import CompanyBot, ThemeType


class Theme(models.Model):
    """
    Stores theme configurations associated with a company bot.
    Supports custom story themes or inheritance from a master theme.
    """

    bot = models.ForeignKey(
        CompanyBot, on_delete=models.CASCADE, related_name='themes',
        help_text="Select the bot this theme belongs to."
    )
    themes = models.JSONField(
        default=list, blank=True,
        help_text="Store a list of themes associated with this bot."
    )

    theme_type = models.CharField(
        max_length=10, choices=ThemeType.choices, default=ThemeType.CUSTOM,
        help_text="Indicates if this theme is custom or uses a master theme."
    )

    master_theme = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='child_themes',
        help_text="If using a master theme, select the theme to inherit from."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"Themes for {self.bot.name}"

    class Meta:
        verbose_name = "Theme"
        verbose_name_plural = "Themes"
        indexes = [
            models.Index(fields=['bot']),
            models.Index(fields=['theme_type']),
        ]
