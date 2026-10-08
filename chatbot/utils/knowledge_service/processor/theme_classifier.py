import copy
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import json_repair
from jinja2 import Template

from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.models.enums import ThemeStatus

logger = logging.getLogger('django')

SECONDARY_THEME_MIN_WORDS = 2
SECONDARY_THEME_MAX_WORDS = 4
MAX_SECONDARY_THEME_COUNT = 10
MAX_SECONDARY_CANDIDATE_LIMIT = 500
SECONDARY_DESCRIPTION_MAX_CHARS = 300
CANDIDATE_DESCRIPTION_MAX_CHARS = 120
DEFAULT_MAX_VALIDATION_RETRIES = 2
DEFAULT_SUMMARY_MAX_CHARS = 3000
TYPED_VALUE_KEYS = frozenset({'type', 'value'})
PAYLOAD_LOG_PREVIEW_CHARS = 1000
STOP_WORDS = frozenset({'and', 'or', 'of', 'the', 'a', 'an', 'for', 'in', 'on', 'to'})
MATCHED_SECONDARY_FIELD = 'matched_secondary_themes'
NEW_SECONDARY_FIELD = 'new_secondary_themes'


class PartialMatchPolicy:
    EXISTING_PLUS_NEW = 'existing_plus_new'
    EXISTING_ONLY = 'existing_only'
    ALL = (EXISTING_PLUS_NEW, EXISTING_ONLY)


@dataclass(frozen=True)
class ThemeOption:
    code: str
    name: str
    description: str = ''


@dataclass(frozen=True)
class SecondaryCandidate:
    id: int
    name: str
    description: str = ''


@dataclass(frozen=True)
class DocumentMetadata:
    title: str = ''
    summary: str = ''
    tags: Tuple[str, ...] = ()
    document_type: str = ''
    key_entities: Tuple[str, ...] = ()

    @property
    def is_classifiable(self) -> bool:
        return bool(self.summary and self.summary.strip())


@dataclass(frozen=True)
class ClassifiedTheme:
    name: str
    confidence: Optional[float]
    reasoning: str
    code: Optional[str] = None
    theme_id: Optional[int] = None
    description: str = ''


@dataclass
class ThemeClassification:
    primary: ClassifiedTheme
    matched_secondary: List[ClassifiedTheme] = field(default_factory=list)
    needs_review: bool = False
    attempts: int = 0


@dataclass
class SectionResult:
    themes: List[ClassifiedTheme] = field(default_factory=list)
    rejected: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _bounded_float(value: Any, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


@dataclass(frozen=True)
class SecondaryThemeSettings:
    count: int = 2
    min_match_confidence: float = 0.7
    partial_match_policy: str = PartialMatchPolicy.EXISTING_PLUS_NEW
    candidate_statuses: Tuple[str, ...] = (ThemeStatus.DRAFT.value, ThemeStatus.PUBLISHED.value)
    candidate_limit: int = 200
    near_duplicate_threshold: float = 0.6
    match_retries: int = 1
    generation_retries: int = 1
    generator_route: str = '/secondary_theme_generator'

    @classmethod
    def from_params(cls, params: Optional[Dict[str, Any]]) -> 'SecondaryThemeSettings':
        params = params if isinstance(params, dict) else {}
        defaults = cls()
        policy = params.get('secondary_partial_match_policy', defaults.partial_match_policy)
        if policy not in PartialMatchPolicy.ALL:
            logger.warning(
                f"[ThemeClassifier] unknown secondary_partial_match_policy={policy!r}; "
                f"using {defaults.partial_match_policy}"
            )
            policy = defaults.partial_match_policy
        statuses = params.get('secondary_candidate_statuses')
        return cls(
            count=_bounded_int(params.get('secondary_theme_count'), defaults.count, 0, MAX_SECONDARY_THEME_COUNT),
            min_match_confidence=_bounded_float(
                params.get('secondary_min_match_confidence'), defaults.min_match_confidence
            ),
            partial_match_policy=policy,
            candidate_statuses=tuple(statuses) if isinstance(statuses, (list, tuple)) and statuses
            else defaults.candidate_statuses,
            candidate_limit=_bounded_int(
                params.get('secondary_candidate_limit'), defaults.candidate_limit, 1, MAX_SECONDARY_CANDIDATE_LIMIT
            ),
            near_duplicate_threshold=_bounded_float(
                params.get('secondary_near_duplicate_threshold'), defaults.near_duplicate_threshold
            ),
            match_retries=_bounded_int(params.get('secondary_match_retries'), defaults.match_retries, 0, 3),
            generation_retries=_bounded_int(
                params.get('secondary_generation_retries'), defaults.generation_retries, 0, 3
            ),
            generator_route=str(params.get('secondary_generator_route') or defaults.generator_route),
        )

    def slots_to_generate(self, matched_count: int) -> int:
        if self.count <= 0:
            return 0
        if self.partial_match_policy == PartialMatchPolicy.EXISTING_ONLY and matched_count > 0:
            return 0
        return max(self.count - matched_count, 0)


def normalize_theme_name(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _theme_key(value: str) -> str:
    return normalize_theme_name(value).casefold()


def _theme_tokens(value: str) -> frozenset:
    words = re.findall(r'[a-z0-9]+', _theme_key(value))
    return frozenset(word.rstrip('s') for word in words if word not in STOP_WORDS)


def is_token_variant(name: str, other: str) -> bool:
    tokens, other_tokens = _theme_tokens(name), _theme_tokens(other)
    return bool(tokens and other_tokens) and (tokens <= other_tokens or other_tokens <= tokens)


def _parse_confidence(value: Any) -> Optional[float]:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return confidence if 0.0 <= confidence <= 1.0 else None


def _parse_theme_id(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else None
    match = re.fullmatch(r'\s*\[?\s*(\d+)\s*\]?\s*', str(value or ''))
    return int(match.group(1)) if match else None


def _truncate(value: str, limit: int) -> str:
    value = normalize_theme_name(value)
    return value if len(value) <= limit else f"{value[:limit - 3].rstrip()}..."


def load_json_field(value: Any) -> Any:
    if isinstance(value, str):
        return json_repair.repair_json(value, return_objects=True) if value.strip() else None
    return value


def load_tool_config(tool_context: Any) -> Optional[Dict[str, Any]]:
    tools = load_json_field(tool_context)
    if isinstance(tools, list):
        tools = tools[0] if tools else None
    return tools if isinstance(tools, dict) else None


def set_array_limit(tools: Optional[Dict[str, Any]], property_name: str, limit: int) -> Optional[Dict[str, Any]]:
    if not isinstance(tools, dict):
        return tools
    tools = copy.deepcopy(tools)
    for tool in tools.get('toolConfig', {}).get('tools', []):
        properties = tool.get('toolSpec', {}).get('inputSchema', {}).get('json', {}).get('properties', {})
        schema = properties.get(property_name)
        if isinstance(schema, dict) and schema.get('type') == 'array':
            schema['maxItems'] = limit
    return tools


def preview_payload(payload: Any) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = repr(payload)
    return text if len(text) <= PAYLOAD_LOG_PREVIEW_CHARS else f"{text[:PAYLOAD_LOG_PREVIEW_CHARS]}...(truncated)"


def describe_theme(theme: ClassifiedTheme) -> str:
    confidence = f"{theme.confidence:.2f}" if theme.confidence is not None else '-'
    theme_id = f"#{theme.theme_id}" if theme.theme_id is not None else ''
    return f"{theme.name!r}{theme_id}@{confidence}"


def normalize_tool_arguments(value: Any) -> Any:
    if isinstance(value, str) and value.strip()[:1] in ('{', '['):
        value = load_json_field(value)
    if isinstance(value, dict):
        if 'value' in value and set(value) <= TYPED_VALUE_KEYS:
            return normalize_tool_arguments(value['value'])
        return {key: normalize_tool_arguments(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_tool_arguments(item) for item in value]
    return value


def extract_tool_payload(response: Any) -> Any:
    if not isinstance(response, dict):
        return response
    payload = response.get('input', response.get('parameters', response))
    return normalize_tool_arguments(load_json_field(payload))


class ThemeRules:

    def __init__(self, themes: Sequence[ThemeOption], fallback: ThemeOption):
        self.fallback = fallback
        self._primary_by_key = {_theme_key(theme.name): theme for theme in themes}
        self._primary_by_key[_theme_key(fallback.name)] = fallback
        reserved = [*themes, fallback]
        self._reserved_keys = {_theme_key(value) for theme in reserved for value in (theme.name, theme.code)}
        self._reserved_names = [theme.name for theme in reserved]

    def validate_primary(self, raw: Any) -> Tuple[Optional[ClassifiedTheme], List[str]]:
        if not isinstance(raw, dict):
            return None, ['primary_theme is missing or not an object.']

        name = normalize_theme_name(raw.get('name'))
        theme = self._primary_by_key.get(_theme_key(name))
        if not theme:
            return None, [f'primary_theme "{name}" is not a predefined theme or "{self.fallback.name}".']

        confidence = _parse_confidence(raw.get('confidence'))
        if confidence is None:
            return None, ['primary_theme.confidence must be a number between 0 and 1.']

        reasoning = normalize_theme_name(raw.get('reasoning'))
        return ClassifiedTheme(name=theme.name, code=theme.code, confidence=confidence, reasoning=reasoning), []

    def validate_new_secondary(self, raw: Any, needed: int, blocked_names: Sequence[str] = ()) -> SectionResult:
        if raw is None:
            return SectionResult(rejected=[f'{NEW_SECONDARY_FIELD} missing; treated as no new themes'])
        if not isinstance(raw, list):
            return SectionResult(errors=[f'{NEW_SECONDARY_FIELD} must be a list of objects.'])

        result = SectionResult()
        seen_keys = {_theme_key(name) for name in blocked_names}
        for item in raw:
            if len(result.themes) >= needed:
                result.rejected.append(f'extra item beyond the {needed} requested: {preview_payload(item)}')
                continue
            theme, reason = self._validate_new_secondary_item(item, seen_keys)
            if reason:
                result.rejected.append(reason)
                continue
            seen_keys.add(_theme_key(theme.name))
            result.themes.append(theme)
        return result

    def _validate_new_secondary_item(
            self, item: Any, seen_keys: set
    ) -> Tuple[Optional[ClassifiedTheme], Optional[str]]:
        if not isinstance(item, dict):
            return None, f'non-object item {preview_payload(item)}'

        name = normalize_theme_name(item.get('name'))
        word_count = len(name.split())
        if not SECONDARY_THEME_MIN_WORDS <= word_count <= SECONDARY_THEME_MAX_WORDS:
            return None, f'"{name}" must be {SECONDARY_THEME_MIN_WORDS}-{SECONDARY_THEME_MAX_WORDS} words'
        if _theme_key(name) in self._reserved_keys or self._paraphrases_primary(name):
            return None, f'"{name}" matches or paraphrases a primary theme'
        if _theme_key(name) in seen_keys:
            return None, f'"{name}" duplicates a theme already chosen for this file'

        confidence = _parse_confidence(item.get('confidence'))
        if confidence is None:
            return None, f'"{name}" has no confidence between 0 and 1'

        return ClassifiedTheme(
            name=name,
            confidence=confidence,
            reasoning=normalize_theme_name(item.get('reason') or item.get('reasoning')),
            description=_truncate(item.get('description') or '', SECONDARY_DESCRIPTION_MAX_CHARS),
        ), None

    def _paraphrases_primary(self, name: str) -> bool:
        return any(is_token_variant(name, reserved) for reserved in self._reserved_names)


class SecondaryMatchValidator:

    def __init__(self, candidates: Sequence[SecondaryCandidate], settings: SecondaryThemeSettings):
        self.candidates = {candidate.id: candidate for candidate in candidates}
        self.settings = settings

    def validate(self, raw: Any) -> SectionResult:
        if not self.candidates or self.settings.count <= 0:
            return SectionResult()
        if raw is None:
            return SectionResult(rejected=[f'{MATCHED_SECONDARY_FIELD} missing; treated as no match'])
        if not isinstance(raw, list):
            return SectionResult(errors=[
                f'{MATCHED_SECONDARY_FIELD} must be a list of objects with id, confidence and reason.'
            ])

        result = SectionResult()
        accepted: List[ClassifiedTheme] = []
        seen_ids = set()
        for item in raw:
            if not isinstance(item, dict):
                result.rejected.append(f'non-object item {preview_payload(item)}')
                continue
            theme_id = _parse_theme_id(item.get('id'))
            candidate = self.candidates.get(theme_id)
            if candidate is None:
                result.rejected.append(f'unknown id {item.get("id")!r}')
                continue
            if theme_id in seen_ids:
                result.rejected.append(f'duplicate id {theme_id}')
                continue
            confidence = _parse_confidence(item.get('confidence'))
            if confidence is None:
                result.rejected.append(f'id {theme_id} {candidate.name!r} has no confidence between 0 and 1')
                continue
            if confidence < self.settings.min_match_confidence:
                result.rejected.append(
                    f'id {theme_id} {candidate.name!r} confidence {confidence:.2f} '
                    f'below {self.settings.min_match_confidence:.2f}'
                )
                continue
            seen_ids.add(theme_id)
            accepted.append(ClassifiedTheme(
                name=candidate.name,
                confidence=confidence,
                reasoning=normalize_theme_name(item.get('reason') or item.get('reasoning')),
                theme_id=candidate.id,
            ))

        accepted.sort(key=lambda theme: theme.confidence, reverse=True)
        for extra in accepted[self.settings.count:]:
            result.rejected.append(f'id {extra.theme_id} {extra.name!r} beyond the limit of {self.settings.count}')
        result.themes = accepted[:self.settings.count]
        return result


class BedrockToolCaller:

    def __init__(self, company_bot, invoke: Callable[..., Any] = handle_bedrock_model):
        self.company_bot = company_bot
        self.invoke = invoke
        self.other_params = load_json_field(company_bot.other_params) or {}
        self.summary_max_chars = _bounded_int(
            self.other_params.get('summary_max_chars'), DEFAULT_SUMMARY_MAX_CHARS, 200, 50000
        )
        self.tools = load_tool_config(company_bot.tool_context)

    def document_context(self, document: DocumentMetadata) -> Dict[str, Any]:
        return {
            'title': document.title,
            'summary': document.summary[:self.summary_max_chars],
            'tags': list(document.tags),
            'document_type': document.document_type,
            'key_entities': list(document.key_entities),
        }

    def request(self, context: Dict[str, Any], log_prefix: str, attempt: int,
                tools: Optional[Dict[str, Any]] = None) -> Any:
        try:
            response = self.invoke(
                system_prompt=[{'text': self.company_bot.context}],
                messages=[{'role': 'user', 'content': [
                    {'text': Template(self.company_bot.end_context or '').render(**context)}
                ]}],
                model_name=self.company_bot.llm_model,
                temperature=self.company_bot.bot_temperature,
                max_token=self.company_bot.max_token,
                company_bot=self.company_bot,
                tools=tools if tools is not None else self.tools,
                aws_key=os.getenv('SG_REPO_AWS_ACCESS_KEY_ID'),
                aws_secret_key=os.getenv('SG_REPO_AWS_SECRET_ACCESS_KEY')
            )
        except Exception as e:
            logger.error(
                f"{log_prefix} attempt={attempt} bot_id={getattr(self.company_bot, 'id', None)} call failed: {e}"
            )
            return None
        return extract_tool_payload(response)


class ThemeClassifier(BedrockToolCaller):

    def __init__(self, company_bot, themes: Sequence[ThemeOption], fallback: ThemeOption,
                 invoke: Callable[..., Any] = handle_bedrock_model,
                 candidates: Sequence[SecondaryCandidate] = (),
                 settings: Optional[SecondaryThemeSettings] = None):
        super().__init__(company_bot, invoke)
        self.themes = list(themes)
        self.fallback = fallback
        self.settings = settings or SecondaryThemeSettings.from_params(self.other_params)
        self.candidates = list(candidates) if self.settings.count > 0 else []
        self.rules = ThemeRules(self.themes, fallback)
        self.match_validator = SecondaryMatchValidator(self.candidates, self.settings)
        self.max_retries = _bounded_int(
            self.other_params.get('max_validation_retries'), DEFAULT_MAX_VALIDATION_RETRIES, 0, 5
        )
        self.tools = set_array_limit(self.tools, MATCHED_SECONDARY_FIELD, self.settings.count)

    def classify(self, document: DocumentMetadata, log_prefix: str = '[ThemeClassifier]') -> ThemeClassification:
        best_primary: Optional[ClassifiedTheme] = None
        best_matches = SectionResult()
        feedback: List[str] = []
        match_retries_used = 0
        total_attempts = self.max_retries + 1

        for attempt in range(1, total_attempts + 1):
            started_at = time.monotonic()
            payload = self.request(self._prompt_context(document, feedback), log_prefix, attempt)
            if isinstance(payload, dict):
                primary, primary_errors = self.rules.validate_primary(payload.get('primary_theme'))
                matches = self.match_validator.validate(payload.get(MATCHED_SECONDARY_FIELD))
            else:
                primary, primary_errors = None, ['Response was not a theme_classification tool call.']
                matches = SectionResult()
            duration = time.monotonic() - started_at

            best_primary = primary or best_primary
            if matches.is_valid and len(matches.themes) >= len(best_matches.themes):
                best_matches = matches
            if matches.rejected:
                logger.info(f"{log_prefix} attempt={attempt} secondary matches rejected={matches.rejected}")

            match_retry_allowed = not matches.is_valid and match_retries_used < self.settings.match_retries
            if not primary_errors and (not match_retry_allowed or attempt == total_attempts):
                final_matches = matches if matches.is_valid else best_matches
                if not matches.is_valid:
                    logger.warning(
                        f"{log_prefix} attempt={attempt} secondary matching output invalid after retries "
                        f"errors={matches.errors}; continuing with matches={len(final_matches.themes)}"
                    )
                logger.info(
                    f"{log_prefix} attempt={attempt}/{total_attempts} valid duration={duration:.1f}s "
                    f"primary={describe_theme(primary)} "
                    f"matched_secondary={[describe_theme(theme) for theme in final_matches.themes]} "
                    f"candidates={len(self.candidates)} reasoning={primary.reasoning!r}"
                )
                return ThemeClassification(
                    primary=primary, matched_secondary=final_matches.themes, attempts=attempt
                )

            if not primary_errors:
                match_retries_used += 1
            feedback = primary_errors + matches.errors
            logger.warning(
                f"{log_prefix} attempt={attempt}/{total_attempts} invalid duration={duration:.1f}s errors={feedback} "
                f"payload={preview_payload(payload)}"
            )

        needs_review = best_primary is None
        primary = best_primary or ClassifiedTheme(
            name=self.fallback.name, code=self.fallback.code, confidence=None,
            reasoning='Assigned automatically after the classifier failed validation.'
        )
        logger.error(
            f"{log_prefix} retries exhausted; using primary={describe_theme(primary)} "
            f"matched_secondary={[describe_theme(theme) for theme in best_matches.themes]} "
            f"needs_review={needs_review} last_errors={feedback}"
        )
        return ThemeClassification(
            primary=primary, matched_secondary=best_matches.themes, needs_review=needs_review,
            attempts=total_attempts
        )

    def _prompt_context(self, document: DocumentMetadata, feedback: List[str]) -> Dict[str, Any]:
        return {
            'themes': self.themes,
            'fallback_theme': self.fallback,
            'secondary_theme_count': self.settings.count,
            'candidate_secondary_themes': [
                {
                    'id': candidate.id,
                    'name': candidate.name,
                    'description': _truncate(candidate.description, CANDIDATE_DESCRIPTION_MAX_CHARS),
                }
                for candidate in self.candidates
            ],
            'document': self.document_context(document),
            'feedback': feedback,
        }


class SecondaryThemeGenerator(BedrockToolCaller):

    def __init__(self, company_bot, themes: Sequence[ThemeOption], fallback: ThemeOption,
                 invoke: Callable[..., Any] = handle_bedrock_model, retries: int = 1):
        super().__init__(company_bot, invoke)
        self.themes = list(themes)
        self.fallback = fallback
        self.retries = max(retries, 0)
        self.rules = ThemeRules(self.themes, fallback)

    def generate(self, document: DocumentMetadata, primary: ClassifiedTheme, matched: Sequence[ClassifiedTheme],
                 existing_names: Sequence[str], needed: int,
                 log_prefix: str = '[ThemeClassifier]') -> List[ClassifiedTheme]:
        if needed <= 0:
            return []

        tools = set_array_limit(self.tools, NEW_SECONDARY_FIELD, needed)
        blocked_names = [theme.name for theme in matched]
        feedback: List[str] = []
        total_attempts = self.retries + 1

        for attempt in range(1, total_attempts + 1):
            started_at = time.monotonic()
            context = {
                'themes': self.themes,
                'fallback_theme': self.fallback,
                'primary_theme': primary.name,
                'matched_secondary_themes': blocked_names,
                'existing_secondary_themes': list(existing_names),
                'needed': needed,
                'document': self.document_context(document),
                'feedback': feedback,
            }
            payload = self.request(context, log_prefix, attempt, tools=tools)
            if isinstance(payload, dict):
                result = self.rules.validate_new_secondary(payload.get(NEW_SECONDARY_FIELD), needed, blocked_names)
            else:
                result = SectionResult(errors=['Response was not a secondary_theme_generation tool call.'])
            duration = time.monotonic() - started_at

            if result.is_valid:
                logger.info(
                    f"{log_prefix} generation attempt={attempt}/{total_attempts} valid duration={duration:.1f}s "
                    f"needed={needed} proposed={[describe_theme(theme) for theme in result.themes]} "
                    f"rejected={result.rejected}"
                )
                return result.themes

            feedback = result.errors
            logger.warning(
                f"{log_prefix} generation attempt={attempt}/{total_attempts} invalid duration={duration:.1f}s "
                f"errors={result.errors} payload={preview_payload(payload)}"
            )

        logger.error(f"{log_prefix} generation failed after {total_attempts} attempts; no new secondary themes")
        return []
