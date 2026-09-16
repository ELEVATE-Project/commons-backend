"""AI Service gateway contract and supported configuration."""

# AI Service endpoints used by this service.
ENDPOINTS = {
    'chat': '/v1/chat',
}

CHAT_PATH = ENDPOINTS['chat']

# Errors indicating a missing/rejected tenant provider key.
TENANT_KEY_CODES = {'missing_tenant_key', 'tenant_key_rejected'}

# Upstream status codes that are safe to retry.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Supported providers and their AI Service mapping.
PROVIDER_MAP = {
    'bedrock': 'bedrock',
    'bedrock/converse': 'bedrock',
    'openai': 'openai',
    'openrouter': 'openrouter',
}