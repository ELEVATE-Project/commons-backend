"""Resolve AI Service deployment configuration."""

import os

from .exceptions import AIServiceConfigError


def resolve_config(tenant_id=None, provider=None, model=None):
    """Resolve caller values first, then environment values."""
    base_url = (os.getenv('AI_SERVICE_BASE_URL') or '').strip().rstrip('/')
    token = (os.getenv('AI_SERVICE_TOKEN') or '').strip()
    tenant = (tenant_id or os.getenv('AI_SERVICE_TENANT_ID') or '').strip()
    provider = (provider or os.getenv('AI_SERVICE_PROVIDER') or '').strip()
    model = (model or os.getenv('AI_SERVICE_MODEL') or '').strip()

    # AI Service requires all values; fail fast instead of guessing defaults.
    missing = [
        name for name, value in (
            ('AI_SERVICE_BASE_URL', base_url),
            ('AI_SERVICE_TOKEN', token),
            ('AI_SERVICE_TENANT_ID', tenant),
            ('AI_SERVICE_PROVIDER', provider),
            ('AI_SERVICE_MODEL', model),
        ) if not value
    ]

    if missing:
        raise AIServiceConfigError(
            f"AI-Service is not configured: missing {', '.join(missing)}.",
            code='missing_config',
        )

    return base_url, token, tenant, provider, model