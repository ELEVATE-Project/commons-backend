from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from simple_history.models import HistoricalRecords
from chatbot.models import CompanyBot, ThemeType, ThemeStatus, SecondaryThemeMatchType


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


class ResourceTheme(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default='')
    is_primary = models.BooleanField(default=False, db_index=True)
    status = models.CharField(
        max_length=20, choices=ThemeStatus.choices, default=ThemeStatus.DRAFT, db_index=True
    )
    created_by = models.ForeignKey(
        'Profile', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_themes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'themes'
        ordering = ['-is_primary', 'name']
        verbose_name = "Resource Theme"
        verbose_name_plural = "Resource Themes"
        constraints = [
            models.UniqueConstraint(Lower('name'), name='themes_name_ci_uniq'),
        ]


class MediaSecondaryTheme(models.Model):
    media = models.ForeignKey('Media', on_delete=models.CASCADE, related_name='secondary_theme_links')
    theme = models.ForeignKey(ResourceTheme, on_delete=models.CASCADE, related_name='media_links')
    confidence = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    reasoning = models.TextField(blank=True, default='')
    match_type = models.CharField(
        max_length=20, choices=SecondaryThemeMatchType.choices, null=True, blank=True, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.media_id} - {self.theme}"

    class Meta:
        db_table = 'media_secondary_themes'
        ordering = ['-confidence']
        verbose_name = "Media Secondary Theme"
        verbose_name_plural = "Media Secondary Themes"
        constraints = [
            models.UniqueConstraint(fields=['media', 'theme'], name='media_secondary_theme_uniq'),
        ]
