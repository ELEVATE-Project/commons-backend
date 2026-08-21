"""
Ask the LLM for search filters and a residual semantic query.

Returns Organization/File Type filters drawn from the vocabulary that actually
exists, plus what's left of the query once filter words are removed. Generic
over the caller — knows nothing about RapidFuzz, only that candidates may be
suggested.
"""

import logging
import time
from dataclasses import dataclass, field

from django.core.cache import cache
from json_repair import repair_json

from chatbot.services.search.config import bot_params, get_search_llm_setting
from chatbot.services.search.prompts import (
    SYSTEM_PROMPT,
    TOOL_NAME,
    build_user_message,
    get_search_bot,
)
from chatbot.services.search.vocabularies import (
    canonicalise_all,
    file_type_vocabulary,
    select_organization_vocabulary,
)
from chatbot.utils import ai_service

logger = logging.getLogger('django')

# ── Cooldown after failures ──────────────────────────────────────────────────
# Circuit breaker: without it, an unhealthy AI-Service makes every search pay
# the full retry/timeout budget before degrading. After enough consecutive
# failures, skip the LLM entirely until the cooldown expires.
#
# Cache-backed and approximate — workers converge on the same state, and being
# briefly wrong costs at most one skipped or one extra call.

FAILURE_STREAK_KEY = 'ai_search:llm_failure_streak'
COOLDOWN_KEY = 'ai_search:llm_cooldown'

# Configuration failures, not load — retrying won't fix them, so cool down on
# the first occurrence instead of waiting for a streak.
CONFIG_ERRORS = (
    ai_service.AIServiceConfigError,
    ai_service.AIServiceAuthError,
    ai_service.AIServiceTenantKeyError,
)

# Log hints keyed by the gateway's error code, or by exception type when there
# is no code (401/403 carry a free-text detail message instead).
REMEDIATION = {
    'missing_tenant_key': (
        'AI-Service has no provider key registered for this tenant. Add one: '
        'uv run llm-service keys set --tenant=<AI_SERVICE_TENANT_ID> '
        '--provider=<AI_SERVICE_PROVIDER> --format=api_key '
        '--data=\'{"api_key":"<key>"}\''
    ),
    'tenant_key_rejected': (
        'The provider key registered for this tenant was rejected upstream. '
        'Re-register it with a valid key for the vendor named in '
        'AI_SERVICE_PROVIDER.'
    ),
    'missing_config': (
        'Set AI_SERVICE_BASE_URL, AI_SERVICE_TOKEN, AI_SERVICE_TENANT_ID, '
        'AI_SERVICE_PROVIDER and AI_SERVICE_MODEL.'
    ),
    'unmapped_provider': (
        'AI_SERVICE_PROVIDER names a vendor this client cannot map. Use one of '
        'the keys in ai_service.PROVIDER_MAP.'
    ),
}

REMEDIATION_BY_TYPE = {
    ai_service.AIServiceTenantKeyError: (
        'This tenant has no usable provider key in AI-Service. Register one '
        'for the vendor named in AI_SERVICE_PROVIDER.'
    ),
    ai_service.AIServiceAuthError: (
        'AI-Service rejected our credentials. Check AI_SERVICE_TOKEN, and that '
        'it is allowed to act for AI_SERVICE_TENANT_ID.'
    ),
    ai_service.AIServiceConfigError: (
        'The AI-Service client is misconfigured. Check the AI_SERVICE_* '
        'environment variables.'
    ),
}


def remediation_for(exc):
    """The most specific fix-it hint available for a configuration failure."""
    hint = REMEDIATION.get(getattr(exc, 'code', None))
    if hint:
        return hint
    for error_type, hint in REMEDIATION_BY_TYPE.items():
        if isinstance(exc, error_type):
            return hint
    return str(exc)


def llm_in_cooldown(bot=None):
    """True when the LLM call should be skipped for now."""
    return bool(cache.get(COOLDOWN_KEY))


def cooldown_reason():
    """Why the LLM is in cooldown, for diagnostics. Empty when it is not."""
    value = cache.get(COOLDOWN_KEY)
    return value if isinstance(value, str) else ('cooling down' if value else '')


def _start_cooldown(seconds, reason):
    """
    Stop calling the LLM for ``seconds``, recording why for diagnostics.

    Also clears the failure streak — once the cooldown gates calls, a
    leftover streak underneath it would only shorten the next one.
    """
    try:
        cache.set(COOLDOWN_KEY, reason, seconds)
        cache.delete(FAILURE_STREAK_KEY)
    except Exception:
        # Cache errors must not break the search path — worst case is one
        # extra wasted call, same as not having a cooldown at all.
        logger.warning('ai_search: could not start the LLM cooldown', exc_info=True)


def record_success(bot=None):
    """Clear the failure streak."""
    cache.delete(FAILURE_STREAK_KEY)
    cache.delete(COOLDOWN_KEY)


def record_failure(bot=None):
    """Count a failure and start the cooldown once the threshold is reached."""
    threshold = get_search_llm_setting(bot, 'llm_cooldown_after_failures')
    seconds = get_search_llm_setting(bot, 'llm_cooldown_seconds')

    try:
        failures = int(cache.get(FAILURE_STREAK_KEY) or 0) + 1
        cache.set(FAILURE_STREAK_KEY, failures, max(seconds * 2, 60))
    except Exception:
        # Cache errors must not break the search path.
        logger.warning('ai_search: could not record LLM failure count', exc_info=True)
        return

    if failures >= threshold:
        logger.warning(
            'ai_search: LLM cooling down for %ss after %s consecutive failures',
            seconds, failures)
        _start_cooldown(seconds, f'{failures} consecutive failures')


def record_config_failure(bot, exc):
    """
    Start the cooldown immediately for a configuration failure.

    Unlike record_failure, this doesn't count a streak — one occurrence is
    proof the config is wrong, so this just avoids paying for the same doomed
    call on every query until someone fixes it.
    """
    seconds = get_search_llm_setting(bot, 'llm_config_cooldown_seconds')
    code = getattr(exc, 'code', None) or type(exc).__name__

    logger.error(
        'ai_search: AI-Service is misconfigured (%s) — LLM cooling down for %ss. %s',
        code, seconds, remediation_for(exc))
    _start_cooldown(seconds, f'config: {code}')


@dataclass
class LLMFilterResult:
    """
    What the model returned, after validation.

    ``organizations``/``media_types`` are None when the model gave no opinion
    (falls back to the fuzzy match) vs. an empty list when it explicitly
    answered none — the two are kept distinct through the merge.
    """
    organizations: list = None
    media_types: list = None
    semantic_query: str = ''
    rejected: dict = field(default_factory=dict)
    bot_route: str = ''
    latency_ms: int = 0


def _function_name(entry):
    """The function name out of one tool entry or a forcing tool_choice, or None."""
    if not isinstance(entry, dict):
        return None
    function = entry.get('function')
    if not isinstance(function, dict):
        return None
    name = function.get('name')
    return name if isinstance(name, str) and name.strip() else None


def _tool_name(tools, tool_choice):
    """
    Which function name to expect in the reply.

    Read from the bot's own tool_context (admin-editable) rather than assumed
    from a Python constant, so renaming the function there doesn't silently
    break extraction. A forcing tool_choice wins; a lone tool is unambiguous;
    several tools under 'auto' are genuinely ambiguous, so None is returned
    and extract_tool_arguments accepts whichever call comes back.
    """
    forced = _function_name(tool_choice)
    if forced:
        return forced

    if isinstance(tools, list) and tools:
        if len(tools) == 1:
            # A lone tool whose name is unreadable is malformed, not ambiguous.
            return _function_name(tools[0]) or TOOL_NAME
        return None

    return TOOL_NAME


def _tool_context(bot):
    """
    Parse the bot's stored tool schema, tolerating the usual JSON near-misses.

    Returns ``(tools, tool_choice, tool_name)``. Nothing here raises — the
    column is hand-edited, so anything unparseable degrades to the seed
    default rather than failing a search.
    """
    raw = getattr(bot, 'tool_context', None)
    if not raw:
        return None, None, TOOL_NAME
    parsed = repair_json(raw, return_objects=True) if isinstance(raw, str) else raw
    if not isinstance(parsed, dict):
        return None, None, TOOL_NAME

    tools = parsed.get('tool')
    tool_choice = parsed.get('tool_choice')
    name = _tool_name(tools, tool_choice)
    if name != TOOL_NAME:
        logger.info(
            'ai_search: bot %s calls its filter function %r, not %r',
            getattr(bot, 'route', '?'), name, TOOL_NAME)
    return tools, tool_choice, name


def _validated(values, vocabulary, name, rejected):
    """
    Canonicalise one field's values against its vocabulary.

    A field whose every value fails validation is treated as *absent*, not as
    an explicit "no filter" — a hallucination shouldn't clear a good fuzzy
    match.
    """
    if values is None:
        return None
    if not isinstance(values, list):
        logger.info('ai_search: ignoring non-list %s from the model: %r', name, values)
        return None

    accepted, dropped = canonicalise_all(values, vocabulary)
    if dropped:
        rejected[name] = dropped
        logger.info('ai_search: dropped out-of-vocabulary %s: %r', name, dropped)
    if values and not accepted:
        return None
    return accepted


def _drop_blanket_organizations(organizations, vocabulary):
    """
    "PDFs from all organizations" is not an organization filter.

    A model answering it by listing every value it was shown would filter on a
    subset, since the vocabulary sent is capped.
    """
    if not organizations or len(vocabulary) < 2:
        return organizations
    if set(organizations) >= set(vocabulary):
        logger.info('ai_search: model returned every organization; treating as no filter')
        return []
    return organizations


def _residual_query(returned, raw_query, has_filters):
    """
    Sanity-check the model's semantic_query against the original.

    Falls back to the raw query if the model returned nothing (and no filters
    were found either) or if it padded rather than reduced the text.
    """
    candidate = (returned or '').strip() if isinstance(returned, str) else ''
    if not candidate:
        return '' if has_filters else raw_query
    if len(candidate) > len(raw_query):
        logger.info('ai_search: semantic_query longer than the query, keeping the original')
        return raw_query
    return candidate


def extract_search_filters(*, raw_query, candidates=None, bot=None):
    """
    Return an LLMFilterResult, or None when the LLM could not be consulted
    (no search bot configured, or a cooldown is running).

    ``candidates`` is whatever the deterministic matcher proposed, as
    ``{field: [value, ...]}``. Errors from the gateway propagate; the pipeline
    above is what turns any failure into a degraded-but-successful search.
    """
    bot = bot or get_search_bot()
    if bot is None:
        return None

    if llm_in_cooldown(bot):
        logger.info(
            'ai_search: LLM in cooldown (%s), using deterministic filters',
            cooldown_reason())
        return None

    # Missing tool schema isn't fatal — the prompt (rule 5) also specifies a
    # plain JSON shape, so the bot still works, just without schema-constrained
    # decoding.
    tools, tool_choice, tool_name = _tool_context(bot)
    if not tools:
        logger.info(
            'ai_search: bot %s has no tool_context, asking for JSON in the reply instead',
            bot.route)

    candidates = candidates or {}
    org_vocabulary = select_organization_vocabulary(
        bot, candidates=candidates.get('organizations'))
    type_vocabulary = file_type_vocabulary()

    messages = [
        {'role': 'system', 'content': bot.context or SYSTEM_PROMPT},
        # Both halves of the prompt come from the bot row: context holds the
        # rules, pre_context the per-request layout.
        {'role': 'user', 'content': build_user_message(
            raw_query, org_vocabulary, type_vocabulary, candidates,
            template=bot.pre_context)},
    ]

    print(f"[extract_search_filters] raw_query: {raw_query!r}")
    print(f"[extract_search_filters] messages sent to LLM: {messages}")

    # Read once — bot_params repairs JSON per call, and three lookups would
    # repeat that per search.
    params = bot_params(bot)

    started = time.monotonic()
    try:
        response = ai_service.chat(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=bot.bot_temperature,
            max_tokens=bot.max_token,
            connect_timeout=bot.connect_timeout,
            read_timeout=bot.read_timeout,
            max_attempts=get_search_llm_setting(bot, 'llm_max_attempts'),
            backoff_base_s=get_search_llm_setting(bot, 'llm_backoff_base_s'),
            max_elapsed_s=get_search_llm_setting(bot, 'llm_max_elapsed_s'),
            # Gateway config: row-level values pin the vendor/model for this
            # bot, falling back to the AI_SERVICE_* env default.
            tenant_id=params.get('ai_tenant_id'),
            provider=params.get('ai_provider'),
            model=params.get('ai_model'),
        )
    except CONFIG_ERRORS as exc:
        record_config_failure(bot, exc)
        raise
    except Exception:
        record_failure(bot)
        raise
    record_success(bot)

    latency_ms = int((time.monotonic() - started) * 1000)

    print(f"[extract_search_filters] raw LLM response: {response}")

    arguments = ai_service.extract_tool_arguments(response, tool_name)
    print(f"[extract_search_filters] extracted tool arguments: {arguments}")
    if arguments is None:
        logger.warning('ai_search: no usable tool call in the AI-Service response')
        return None

    rejected = {}
    organizations = _validated(
        arguments.get('organizations'), org_vocabulary, 'organizations', rejected)
    organizations = _drop_blanket_organizations(organizations, org_vocabulary)
    media_types = _validated(
        arguments.get('file_types'), type_vocabulary, 'media_types', rejected)

    result = LLMFilterResult(
        organizations=organizations,
        media_types=media_types,
        semantic_query=_residual_query(
            arguments.get('semantic_query'), raw_query,
            bool(organizations or media_types)),
        rejected=rejected,
        bot_route=bot.route,
        latency_ms=latency_ms,
    )
    print(f"[extract_search_filters] final LLMFilterResult: {result}")
    return result
