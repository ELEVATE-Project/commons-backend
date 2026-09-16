from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.hashers import make_password
from simple_history.models import HistoricalRecords
from chatbot.models.enums import (
    EntityStatus, GenderChoices, ProfileType, SessionFlowName
)
from chatbot.models.company_models import Company, Flow


class Profile(models.Model):
    """
    Represents a user profile associated with a company.
    Stores personal details, authentication data, and metadata for chatbot interactions.
    """

    def get_file_upload_path(self, filename):
        folder_name = self.company.slug+'/'+'profile'+'/'+self.email
        upload_path = f"{folder_name}/{filename}"
        return upload_path

    first_name = models.CharField(max_length=100, null=True, blank=True)
    userid = models.CharField(max_length=200, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(max_length=1000, null=False, blank=False)
    phone = models.CharField(max_length=20, null=True, blank=True)
    alternate_phone = models.CharField(max_length=20, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=EntityStatus.choices, default=EntityStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company = models.ForeignKey(Company, on_delete=models.DO_NOTHING, null=False, blank=False)
    password = models.CharField(max_length=1000, null=True, blank=True)
    profile_type = models.CharField(max_length=20, choices=ProfileType.choices, default=ProfileType.USER)
    profile_code = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=1000, null=True, blank=True)
    caste = models.CharField(max_length=1000, null=True, blank=True)
    gender = models.CharField(max_length=1000, null=True, blank=True, choices=GenderChoices.choices)
    designation = models.TextField(null=True, blank=True)
    org_associated = models.CharField(max_length=1000, null=True, blank=True)
    product_interested = models.CharField(max_length=1000, null=True, blank=True)
    company_spoc = models.CharField(max_length=1000, null=True, blank=True)
    other_params = models.JSONField(null=True, blank=True)
    source = models.CharField(max_length=1000, null=True, blank=True)
    preferred_route = models.CharField(max_length=1000, null=True, blank=True)
    latest_flow_used = models.CharField(max_length=500, choices=SessionFlowName.choices, null=True, blank=True)
    latest_flow = models.ForeignKey(Flow, on_delete=models.DO_NOTHING, null=True, blank=True)
    history = HistoricalRecords()

    def __str__(self):
        return self.first_name if self.first_name else ""

    def clean(self):
        super().clean()

        if self.phone:
            if Profile.objects.filter(phone=self.phone, company=self.company).exists():
                raise ValidationError({
                        'phone': 'A profile with this phone number already exists for the specified company.'
                    })

    def save(self, *args, **kwargs):
        if self.password and 'pbkdf2_sha256' not in self.password:
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ('email', 'company')
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
        ]
