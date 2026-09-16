from django.db import models
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords


class I18nTag(models.Model):
    """
    Model for storing internationalization tag names.
    Tags are used to group related translations together.
    """
    tag_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique tag name for grouping translations (e.g., 'welcome_message', 'button_labels')."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.tag_name

    class Meta:
        verbose_name = "I18n Tag"
        verbose_name_plural = "I18n Tags"
        indexes = [
            models.Index(fields=['tag_name']),
        ]
        ordering = ['tag_name']


class I18nTranslation(models.Model):
    """
    Model for storing internationalization translations.
    Each translation is associated with a tag and can have multiple variables in different languages.
    """
    tag_id = models.ForeignKey(
        I18nTag,
        on_delete=models.CASCADE,
        related_name='translations',
        help_text="The tag this translation belongs to."
    )
    variable_name = models.CharField(
        max_length=255,
        help_text="Variable name for this translation (e.g., 'title', 'description', 'button_text')."
    )
    language = models.CharField(
        max_length=10,
        help_text="Language code (e.g., 'en', 'hi', 'kn', 'te')."
    )
    value = models.TextField(
        help_text="Translated text value for this variable in the specified language."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.tag_id.tag_name} - {self.variable_name} ({self.language})"

    class Meta:
        verbose_name = "I18n Translation"
        verbose_name_plural = "I18n Translations"
        indexes = [
            models.Index(fields=['tag_id', 'variable_name', 'language']),
            models.Index(fields=['language']),
            models.Index(fields=['variable_name']),
        ]
        unique_together = [['tag_id', 'variable_name', 'language']]
        ordering = ['tag_id', 'variable_name', 'language']

    def clean(self):
        """Validate the translation data."""
        super().clean()
        
        # Validate language code format (should be lowercase)
        if self.language:
            self.language = self.language.lower().strip()
            
        # Validate that value is not empty
        if not self.value or not self.value.strip():
            raise ValidationError({
                'value': "Translation value cannot be empty."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
