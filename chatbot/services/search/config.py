"""
One resolution rule for every AI-search LLM setting.

Precedence is always ``CompanyBot.other_params`` -> environment -> default, the
same way ``filter_score`` and ``detail_filter_score`` already come off the bot
row. Keeping it in one helper means a new knob costs a table entry rather than
new plumbing, and no setting can drift onto its own precedence rule.

Nothing here raises. These values come from a DB column and a .env file, neither
of which is type-checked, and a typo in either must not be able to take search
down — a bad value is logged and the default is used.

What is deliberately absent: the vendor and the model. Those are not per-bot
settings — they belong to the AI Service deployment and are resolved from
AI_SERVICE_PROVIDER / AI_SERVICE_MODEL inside chatbot/utils/ai_service/.
Everything here is behavioural tuning: when to call the LLM, how hard to retry,
how much vocabulary to send.
"""

import logging
import os

from json_repair import repair_json

logger = logging.getLogger('django')

MODE_OFF = 'off'
MODE_FALLBACK = 'fallback'
MODE_ALWAYS = 'always'
VALID_MODES = (MODE_OFF, MODE_FALLBACK, MODE_ALWAYS)

VOCAB_CANDIDATES = 'candidates'
VOCAB_FULL = 'full'
VOCAB_AUTO = 'auto'
VALID_VOCAB_MODES = (VOCAB_CANDIDATES, VOCAB_FULL, VOCAB_AUTO)


def _mode(value):
    value = str(value).strip().lower()
    return value if value in VALID_MODES else None


def _vocab_mode(value):
    value = str(value).strip().lower()
    return value if value in VALID_VOCAB_MODES else None


def _ratio(value):
    """A float clamped to [0, 1]. Out-of-range is clamped, not rejected."""
    return min(1.0, max(0.0, float(value)))


def _positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise ValueError('must be >= 1')
    return parsed


def _positive_float(value):
    parsed = float(value)
    if parsed <= 0:
        raise ValueError('must be > 0')
    return parsed


# key -> (environment variable, default, parser)
SETTINGS = {
    'llm_mode': ('AI_SEARCH_LLM_MODE', MODE_FALLBACK, _mode),
    'llm_confidence_threshold': ('AI_SEARCH_LLM_CONFIDENCE_THRESHOLD', 0.5, _ratio),
    'llm_max_attempts': ('AI_SERVICE_MAX_ATTEMPTS', 2, _positive_int),
    'llm_backoff_base_s': ('AI_SERVICE_BACKOFF_BASE_S', 0.4, _positive_float),
    # Must exceed llm_max_attempts x CompanyBot.read_timeout plus the backoff,
    # or the deadline expires before attempt one returns and no retry ever runs.
    'llm_max_elapsed_s': ('AI_SERVICE_MAX_ELAPSED_S', 35.0, _positive_float),
    'llm_cooldown_after_failures': ('AI_SERVICE_COOLDOWN_AFTER_FAILURES', 3, _positive_int),
    'llm_cooldown_seconds': ('AI_SERVICE_COOLDOWN_SECONDS', 30.0, _positive_float),
    # Longer than the transient cooldown on purpose: a missing gateway config, a
    # rejected service token or an unregistered tenant key is fixed by a person,
    # not by waiting, so there is nothing to gain from probing every 30s.
    'llm_config_cooldown_seconds': ('AI_SERVICE_CONFIG_COOLDOWN_SECONDS', 300.0, _positive_float),
    'llm_org_vocab_mode': ('AI_SEARCH_LLM_ORG_VOCAB_MODE', VOCAB_AUTO, _vocab_mode),
    'llm_org_candidate_limit': ('AI_SEARCH_LLM_ORG_CANDIDATE_LIMIT', 10, _positive_int),
    'llm_org_full_max': ('AI_SEARCH_LLM_ORG_FULL_MAX', 50, _positive_int),
}


def bot_params(bot):
    """
    ``CompanyBot.other_params`` as a dict.

    It is a JSONField, but rows written by older code can hold a JSON *string* —
    media_api_views already runs json_repair over it for exactly this reason.
    """
    params = getattr(bot, 'other_params', None) if bot else None
    if isinstance(params, str):
        try:
            params = repair_json(params, return_objects=True)
        except Exception:
            return {}
    return params if isinstance(params, dict) else {}


def get_search_llm_setting(bot, key):
    """Resolve one setting: bot other_params -> environment -> default."""
    try:
        env_var, default, parse = SETTINGS[key]
    except KeyError:
        raise KeyError(f'Unknown AI-search setting {key!r}. Known: {sorted(SETTINGS)}')

    for source, raw in (('bot', bot_params(bot).get(key)), ('env', os.getenv(env_var))):
        if raw is None or raw == '':
            continue
        try:
            parsed = parse(raw)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None:
            return parsed
        logger.warning(
            'ai_search: ignoring invalid %s from %s (%r), falling back', key, source, raw)

    return default
