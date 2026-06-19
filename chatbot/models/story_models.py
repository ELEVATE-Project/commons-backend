import io
import os
import base64
from django.db import models
from django.core.validators import MinLengthValidator
from chatbot.models import Profile, TagChoices, StoryLanguageChoices, StorySourceChoices, MediaTypeChoices, \
    StoryStatusChoices, Company, TagSourceChoices
from pillow_heif import register_heif_opener
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError
import requests

from chatbot.services.storage import StorageFactory

S3_BASE_URL = os.getenv('S3_MEDIA_URL')
register_heif_opener()


class Story(models.Model):
    """
    Represents a story created by a user or AI within a chat session.
    Stores content, metadata, language, status, and translation support.
    """

    title = models.CharField(max_length=1000)
    author = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    blurb = models.TextField(null=True, blank=True)
    tweet = models.TextField(null=True, blank=True)
    session = models.CharField(max_length=255, unique=True)
    objective = models.TextField(null=True, blank=True)
    action_steps = models.TextField(null=True, blank=True)
    impact = models.TextField(null=True, blank=True)
    micro_improvement = models.TextField(null=True, blank=True)
    location = models.CharField(max_length=1000, null=True, blank=True)
    district = models.CharField(max_length=1000, null=True, blank=True)
    state = models.CharField(max_length=1000, null=True, blank=True)
    block = models.CharField(max_length=1000, null=True, blank=True)
    formatted_content = models.TextField(null=True, blank=True)
    language = models.CharField(max_length=1000, choices=StoryLanguageChoices.choices,
                                default=StoryLanguageChoices.ENGLISH)
    source = models.CharField(max_length=1000, choices=StorySourceChoices.choices,
                              default=StorySourceChoices.AI_GENERATED)
    story_code = models.CharField(max_length=100, null=True, blank=True)
    stage = models.CharField(max_length=100, choices=StoryStatusChoices.choices, default=StoryStatusChoices.PENDING)
    summary = models.TextField(null=True, blank=True)
    other_params = models.JSONField(null=True, blank=True)

    client_created_at = models.DateTimeField(null=True, blank=True)
    client_updated_at = models.DateTimeField(null=True, blank=True)
    validation_logs = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_translation(self, language):
        """Get story content in specified language"""
        if language == self.language:
            return self

        try:
            return self.translations.get(language=language)
        except StoryTranslation.DoesNotExist:
            return None

    def get_available_languages(self):
        """Get list of available languages for this story"""
        langs = [self.language]
        langs.extend(self.translations.values_list('language', flat=True))
        return langs

    def get_translation_languages(self):
        """Get only translation languages (excludes main story language)"""
        return list(self.translations.values_list('language', flat=True))

    class Meta:
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['session']),
            models.Index(fields=['author'])
        ]


class StoryMedia(models.Model):
    """
    Stores media files associated with a story.
    Handles file uploads, format conversion, and base64 encoding.
    """

    def get_file_upload_path(self, filename):
        folder_name = 'chatbot/storymedia/{}'.format(self.story.id)
        upload_path = f"{folder_name}/{filename}"
        return upload_path

    name = models.CharField(max_length=1000)
    file = models.FileField(upload_to=get_file_upload_path, max_length=1000, null=True, blank=True)
    story = models.ForeignKey(Story, related_name='story_media', on_delete=models.CASCADE)
    include_in_story = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    base64_str = models.TextField(null=True, blank=True)
    source_path = models.TextField(null=True, blank=True)
    media_type = models.CharField(max_length=100, choices=MediaTypeChoices.choices, null=True, blank=True)
    file_url = models.CharField(max_length=2000, null=True, blank=True)

    def get_public_url(self):
        if self.file:
            return f"{S3_BASE_URL}{self.file.name}"
        elif self.file_url:
            return self.file_url
        else:
            return ""

    def save(self, *args, **kwargs):
        try:
            if self.file_url:
                if self.file_url.startswith("s3://"):
                    storage_handler = StorageFactory.get_storage_handler()
                    response_content = storage_handler.get_file_from_store(self.file_url)
                    self.base64_str = base64.b64encode(response_content).decode('utf-8')
                    print("Encoded base64 from file_url")
                else:
                    response = requests.get(self.file_url)
                    response.raise_for_status()
                    self.base64_str = base64.b64encode(response.content).decode('utf-8')
                    print("Encoded base64 from file_url")

            if not self.file:
                super().save(*args, **kwargs)
                return
            self.file.seek(0)
            file_ext = os.path.splitext(self.file.name)[1].lower()
            print("file_ext:", file_ext)
            print("File name:", self.file.name)
            print("File size:", self.file.size)

            # Convert HEIC/HEIF to JPEG
            if file_ext in ['.heic', '.heif']:
                try:
                    image = Image.open(self.file)
                    converted_io = io.BytesIO()
                    image.save(converted_io, format='JPEG')

                    # Replace the file with JPEG
                    converted_io.seek(0)
                    new_filename = os.path.splitext(self.file.name)[0] + ".jpg"
                    self.file = ContentFile(converted_io.read(), name=new_filename)
                    self.media_type = MediaTypeChoices.JPEG

                    print("Converted HEIC/HEIF to JPEG:", new_filename)
                except UnidentifiedImageError:
                    print("Could not identify image file. Make sure it's valid.")
                except Exception as e:
                    print("Unexpected error during HEIF conversion:", str(e))

            # Reset pointer before base64 encoding
            self.file.seek(0)
            self.base64_str = base64.b64encode(self.file.read()).decode('utf-8')

        except Exception as e:
            print("Error during save():", str(e))

        super().save(*args, **kwargs)


class Tag(models.Model):
    """
    Represents a reusable tag used to categorize stories.
    Can be company-specific and linked to a creator profile.
    """

    name = models.CharField(max_length=1000, unique=True, null=False, blank=False,
                            validators=[MinLengthValidator(limit_value=3)])
    status = models.CharField(max_length=100, choices=TagChoices.choices, default=TagChoices.PENDING)
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)

    source_type = models.CharField(
        max_length=50, choices=TagSourceChoices.choices, null=True, blank=True
    )

    description = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Global Tag"
        verbose_name_plural = "Global Tags"

    def __str__(self):
        return self.name


class StoryTag(models.Model):
    """
    Maps tags to stories with optional primary tag designation.
    Ensures a story cannot have duplicate tags.
    """

    story = models.ForeignKey(Story, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.DO_NOTHING)
    is_primary = models.BooleanField(default=False)

    created_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.story.title} - {self.tag.name}"

    class Meta:
        unique_together = ('story', 'tag')


class StoryTranslation(models.Model):
    """
    Stores translated versions of a story in different languages.
    Maintains localized content while linking to the original story.
    """

    story = models.ForeignKey(Story, related_name='translations', on_delete=models.CASCADE)
    language = models.CharField(max_length=10, choices=StoryLanguageChoices.choices)

    title = models.CharField(max_length=1000)
    content = models.TextField(null=True, blank=True)
    blurb = models.TextField(null=True, blank=True)
    tweet = models.TextField(null=True, blank=True)
    objective = models.TextField(null=True, blank=True)
    action_steps = models.TextField(null=True, blank=True)
    impact = models.TextField(null=True, blank=True)
    micro_improvement = models.TextField(null=True, blank=True)
    formatted_content = models.TextField(null=True, blank=True)
    location = models.CharField(max_length=1000, null=True, blank=True)
    district = models.CharField(max_length=1000, null=True, blank=True)
    state = models.CharField(max_length=1000, null=True, blank=True)
    block = models.CharField(max_length=1000, null=True, blank=True)
    other_params = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('story', 'language')
        indexes = [
            models.Index(fields=['story', 'language']),
        ]

    def __str__(self):
        return f"{self.story.title} ({self.language})"
