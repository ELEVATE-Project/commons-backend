from django.db import models


class MediaOrgMapping(models.Model):
    id = models.BigAutoField(primary_key=True)
    media_id = models.ForeignKey('Media', on_delete=models.CASCADE, db_column='media_id', related_name='media_org_mappings')
    org_id = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
