import uuid6

from django.db import models


class Repository(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid6.uuid7, editable=False)
    repository_name = models.CharField(max_length=255)
    provider_type = models.CharField(max_length=50)
    root_link = models.TextField()
    status = models.CharField(max_length=50, default='ACTIVE')
    sync_enabled = models.BooleanField(default=True)
    last_sync_cursor = models.TextField(null=True, blank=True)
    last_sync_time = models.DateTimeField(null=True, blank=True)
    last_successful_sync = models.DateTimeField(null=True, blank=True)
    last_failed_sync = models.DateTimeField(null=True, blank=True)
    last_error_message = models.TextField(null=True, blank=True)
    total_resources = models.BigIntegerField(default=0)
    org_id = models.BigIntegerField()
    org_name = models.CharField(max_length=255)
    created_by = models.ForeignKey('Profile', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_repositories')
    updated_by = models.ForeignKey('Profile', on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_repositories')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'repositories'
        constraints = [
            models.UniqueConstraint(
                fields=['org_id', 'root_link'],
                name='repositories_org_id_root_link_uniq',
            ),
        ]
