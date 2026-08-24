"""AI Service HTTP client."""

import json
import logging
import random
import time
import uuid

import requests
from json_repair import repair_json

from .config import resolve_config
from .constants import CHAT_PATH, PROVIDER_MAP, RETRYABLE_STATUSES, TENANT_KEY_CODES
from .exceptions import (
    AIServiceAuthError,
    AIServiceConfigError,
    AIServiceRateLimitError,
    AIServiceResponseError,
    AIServiceTenantKeyError,
    AIServiceTransportError,
    AIServiceUpstreamError,
    RETRYABLE_ERRORS,
)

logger = logging.getLogger('django')


def map_provider(provider):
    """
    Translate a configured provider name into the one the gateway expects.

    Raises AIServiceConfigError rather than returning None: an unmapped provider
    is a deployment mistake, and failing here keeps a misconfigured vendor from
    reaching the gateway as a confusing upstream error.
    """
    name = (provider or '').strip().lower()

    if name == 'ai_service':
        raise AIServiceConfigError(
            "'ai_service' is not a gateway provider. "
            "AI_SERVICE_PROVIDER must name the vendor.",
            code='unmapped_provider',
        )

    mapped = PROVIDER_MAP.get(name)
    if not mapped:
        raise AIServiceConfigError(
            f"No AI-Service provider mapping for {provider!r}. "
            f"Known values: {sorted(PROVIDER_MAP)}",
            code='unmapped_provider',
        )
    return mapped


def chat(
    *,
    messages,
    tools=None,
    tool_choice=None,
    temperature=None,
    max_tokens=None,
    connect_timeout=5.0,
    read_timeout=10.0,
    max_attempts=2,
    backoff_base_s=0.4,
    max_elapsed_s=8.0,
    tenant_id=None,
    provider=None,
    model=None,
    request_id=None,
    provider_options=None,
):
    """POST /v1/chat and return the parsed response."""
    base_url, token, tenant, provider, model = resolve_config(
        tenant_id, provider, model
    )

    provider = map_provider(provider)

    request_id = request_id or str(uuid.uuid4())

    payload = {
        'provider': provider,
        'model': model,
        'messages': messages,
        'params': {
            'connect_timeout': connect_timeout,
            'read_timeout': read_timeout,
        },
    }

    if tools:
        payload['tools'] = tools
    if tool_choice is not None:
        payload['tool_choice'] = tool_choice
    if temperature is not None:
        payload['params']['temperature'] = temperature
    if max_tokens is not None:
        payload['params']['max_tokens'] = max_tokens
    if provider_options:
        payload['provider_options'] = provider_options

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-Tenant-Id': tenant,
        'X-Request-Id': request_id,
    }

    url = f'{base_url}{CHAT_PATH}'
    deadline = time.monotonic() + max_elapsed_s
    last_error = None

    for attempt in range(max_attempts):
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=(connect_timeout, read_timeout),
            )

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise AIServiceResponseError(
                        f'AI-Service returned a non-JSON body: {exc}',
                        code='invalid_json',
                        http_status=200,
                        request_id=request_id,
                    )

            try:
                detail = response.json().get('detail')
            except Exception:
                detail = (response.text or '').strip()[:200]

            if isinstance(detail, str):
                code = detail
            elif detail is not None:
                code = json.dumps(detail)[:200]
            else:
                code = ''

            common = {
                'code': code,
                'http_status': response.status_code,
                'request_id': request_id,
            }

            if response.status_code in (401, 403):
                last_error = AIServiceAuthError(
                    f'AI-Service rejected credentials ({response.status_code}): {code}',
                    **common,
                )
            elif response.status_code == 429:
                last_error = AIServiceRateLimitError(
                    f'AI-Service rate limited: {code}',
                    retry_after=response.headers.get('Retry-After'),
                    **common,
                )
            elif code in TENANT_KEY_CODES:
                last_error = AIServiceTenantKeyError(
                    f'No usable provider key for this tenant: {code}',
                    **common,
                )
            elif response.status_code in RETRYABLE_STATUSES:
                last_error = AIServiceUpstreamError(
                    f'AI-Service upstream error ({response.status_code}): {code}',
                    retry_after=response.headers.get('Retry-After'),
                    **common,
                )
            else:
                last_error = AIServiceResponseError(
                    f'AI-Service returned {response.status_code}: {code}',
                    **common,
                )

        except requests.exceptions.Timeout as exc:
            last_error = AIServiceTransportError(
                f'AI-Service timed out: {exc}',
                code='timeout',
                request_id=request_id,
            )
        except requests.exceptions.RequestException as exc:
            last_error = AIServiceTransportError(
                f'Could not reach AI-Service: {exc}',
                code='transport',
                request_id=request_id,
            )

        if not isinstance(last_error, RETRYABLE_ERRORS):
            raise last_error

        if attempt + 1 >= max_attempts:
            break

        retry_after = getattr(last_error, 'retry_after', None)
        if retry_after:
            try:
                delay = max(0.0, float(retry_after))
            except (TypeError, ValueError):
                delay = 0.0
        else:
            delay = random.uniform(
                0, backoff_base_s * (2 ** (attempt + 1))
            )

        if time.monotonic() + delay >= deadline:
            logger.warning(
                'ai_service: deadline reached after %s attempt(s) [request_id=%s]',
                attempt + 1,
                request_id,
            )
            break

        time.sleep(delay)

    raise last_error


def extract_tool_arguments(response, tool_name):
    """Extract tool arguments from a chat response."""
    try:
        message = (response.get('choices') or [{}])[0].get('message') or {}
    except (AttributeError, IndexError, TypeError):
        return None

    for call in message.get('tool_calls') or []:
        function = call.get('function') or {}

        if tool_name and function.get('name') != tool_name:
            continue

        raw = function.get('arguments')
        if not raw or not isinstance(raw, str):
            continue

        try:
            parsed = json.loads(raw)
        except ValueError:
            try:
                parsed = repair_json(raw, return_objects=True)
            except Exception:
                parsed = None

        if isinstance(parsed, dict):
            return parsed

    # Some providers return the tool arguments as plain message content.
    content = message.get('content')
    if isinstance(content, str) and content:
        try:
            parsed = json.loads(content)
        except ValueError:
            try:
                parsed = repair_json(content, return_objects=True)
            except Exception:
                parsed = None

        if isinstance(parsed, dict):
            logger.info(
                'ai_service: recovered tool arguments from message content'
            )
            return parsed

    return None