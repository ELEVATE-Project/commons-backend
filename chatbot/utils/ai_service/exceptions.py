"""AI-Service gateway error types."""

class AIServiceError(Exception):
    """Base exception for AI-Service failures."""

    def __init__(self, message, code=None, http_status=None, request_id=None, retry_after=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.request_id = request_id
        self.retry_after = retry_after


class AIServiceConfigError(AIServiceError):
    """Missing or unusable configuration. Raised before any request is sent."""


class AIServiceTransportError(AIServiceError):
    """Connection failure or client-side timeout. Retryable."""


class AIServiceAuthError(AIServiceError):
    """401/403 — our service token is invalid, or it may not act for this tenant."""


class AIServiceTenantKeyError(AIServiceError):
    """422 — the tenant has no usable BYOK provider key."""


class AIServiceRateLimitError(AIServiceError):
    """429 or upstream_rate_limited. Retryable."""


class AIServiceUpstreamError(AIServiceError):
    """5xx from the gateway or the provider behind it. Retryable."""


class AIServiceResponseError(AIServiceError):
    """Well-formed HTTP response whose body we cannot use."""


RETRYABLE_ERRORS = (AIServiceTransportError, AIServiceRateLimitError, AIServiceUpstreamError)
