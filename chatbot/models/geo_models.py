from django.db import models
from django.db.models import DecimalField
from chatbot.models import Profile


class ProfileAddress(models.Model):
    """
    Stores address and geolocation details associated with a user profile.
    Includes full address fields along with optional latitude and longitude.
    """

    profile = models.ForeignKey(Profile, related_name='profile_address', on_delete=models.CASCADE)
    address_line_1 = models.CharField(max_length=1000, null=True, blank=True)
    address_line_2 = models.CharField(max_length=1000, null=True, blank=True)
    block = models.CharField(max_length=1000, null=True, blank=True)
    city = models.CharField(max_length=1000, null=True, blank=True)
    district = models.CharField(max_length=1000, null=True, blank=True)
    state = models.CharField(max_length=1000, null=True, blank=True)
    country = models.CharField(max_length=1000, null=True, blank=True)
    pincode = models.CharField(null=True, blank=True, max_length=10)

    latitude = DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.profile.first_name
