"""AI-Service LLM gateway integration.

The gateway handles the LLM call; this package handles timeouts, retries,
configuration, provider mapping, errors, and structured response parsing.

This package is independent of CompanyBot and search. Callers provide any
bot-specific timeout/retry/config overrides.

Modules:
    constants.py  Gateway contract and provider mapping
    exceptions.py Error types
    config.py     AI_SERVICE_* configuration
    client.py     HTTP client and response parsing
"""

from .client import chat, extract_tool_arguments, map_provider
from .config import resolve_config
from .constants import PROVIDER_MAP
from .exceptions import (
    AIServiceAuthError,
    AIServiceConfigError,
    AIServiceError,
    AIServiceRateLimitError,
    AIServiceResponseError,
    AIServiceTenantKeyError,
    AIServiceTransportError,
    AIServiceUpstreamError,
    RETRYABLE_ERRORS,
)

__all__ = [
    'chat',
    'extract_tool_arguments',
    'map_provider',
    'resolve_config',
    'PROVIDER_MAP',
    'AIServiceError',
    'AIServiceConfigError',
    'AIServiceTransportError',
    'AIServiceAuthError',
    'AIServiceTenantKeyError',
    'AIServiceRateLimitError',
    'AIServiceUpstreamError',
    'AIServiceResponseError',
    'RETRYABLE_ERRORS',
]