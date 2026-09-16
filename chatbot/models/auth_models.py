from django.db import models


class BlacklistedToken(models.Model):
    """
    Stores authentication tokens that have been invalidated or revoked.
    Used to prevent blacklisted tokens from being reused.
    """
    token = models.TextField(unique=True)
    blacklisted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.token
