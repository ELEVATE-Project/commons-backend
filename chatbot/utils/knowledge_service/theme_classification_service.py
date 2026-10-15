import hashlib
import logging
import os
import re
import time
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from django.contrib.postgres.search import TrigramSimilarity
from django.db import IntegrityError, connection, transaction
from django.db.models import F, FloatField, Func, Q, Value
from simple_history.utils import bulk_update_with_history

from chatbot.llm_models.llm_script import handle_bedrock_model
from chatbot.models import (
    CompanyBot, KeyValue, Media, MediaSecondaryTheme, ResourceTheme, SecondaryThemeMatchType, ThemeStatus
)
from chatbot.utils.knowledge_service.processor.theme_classifier import (
    ClassifiedTheme, DocumentMetadata, SecondaryCandidate, SecondaryThemeGenerator, SecondaryThemeSettings,
    ThemeClassification, ThemeClassifier, ThemeOption, describe_theme, is_token_variant, load_json_field,
    normalize_theme_name
)

logger = logging.getLogger('django')

THEME_CLASSIFIER_ROUTE = '/theme_classifier'
DOC_TEXT_EXTRACTOR_ROUTE = '/tag_extractor'
MISCELLANEOUS_THEME_CODE = 'Miscellaneous'
EXTRACTION_PLACEHOLDER_PREFIX = 'Extracted from '
TITLE_KEY = 'TITLE'
DOCUMENT_TYPE_KEY = 'DOCUMENT_TYPE'
KEY_ENTITIES_KEY = 'KEY ENTITIES'
MEDIA_THEME_FIELDS = ['primary_theme', 'primary_theme_confidence', 'primary_theme_reasoning', 'needs_review']
SEARCH_TEXT_MAX_CHARS = 2000
THEME_CODE_HASH_LENGTH = 12
NEAR_DUPLICATE_NEIGHBOUR_FLOOR = 0.3
NEAR_DUPLICATE_NEIGHBOUR_LIMIT = 10
SECONDARY_THEME_LOCK_KEY = 7401202605
VECTOR_THEME_SYNC_DELAY_SECONDS = 10
ADMIN_THEME_WAIT_TIMEOUT_SECONDS = 30
THEME_WAIT_MAX_POLL_SECONDS = 3.0


class ThemeClassificationStatus:
    CLASSIFIED = 'classified'
    NEEDS_REVIEW = 'needs_review'
    SKIPPED_NO_SUMMARY = 'skipped_no_summary'
    SKIPPED_NO_BOT = 'skipped_no_bot'
    SKIPPED_NO_THEMES = 'skipped_no_themes'
    FAILED = 'failed'


class ThemeMessageLevel:
    SUCCESS = 'success'
    WARNING = 'warning'
    ERROR = 'error'
    INFO = 'info'


THEME_CODE_MAX_LENGTH = ResourceTheme._meta.get_field('code').max_length


class WordSimilarity(Func):
    function = 'word_similarity'
    output_field = FloatField()


@dataclass
class SecondaryThemeLink:
    theme: ResourceTheme
    match_type: str
    confidence: Optional[float]
    reasoning: str
    detail: str = ''


@dataclass
class ThemeClassificationOutcome:
    media_id: int
    status: str
    primary_theme: Optional[str] = None
    primary_theme_name: Optional[str] = None
    secondary_themes: Tuple[str, ...] = ()
    needs_review: bool = False
    matched: int = 0
    deduplicated: int = 0
    created: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            'media_id': self.media_id,
            'status': self.status,
            'primary_theme': self.primary_theme,
            'primary_theme_name': self.primary_theme_name,
            'secondary_themes': list(self.secondary_themes),
            'needs_review': self.needs_review,
            'secondary_reuse': {
                'matched': self.matched, 'deduplicated': self.deduplicated, 'created': self.created,
            },
        }


def get_company_bot(route: str, company) -> Optional[CompanyBot]:
    bots = CompanyBot.objects.filter(route=route)
    return (bots.filter(company=company).first() if company else None) or bots.order_by('id').first()


def get_theme_classifier_bot(company) -> Optional[CompanyBot]:
    return get_company_bot(THEME_CLASSIFIER_ROUTE, company)


def load_theme_options() -> Tuple[List[ThemeOption], Optional[ThemeOption]]:
    options = [
        ThemeOption(code=theme.code, name=theme.name, description=theme.description)
        for theme in ResourceTheme.objects.filter(is_primary=True, status=ThemeStatus.PUBLISHED).order_by('name')
    ]
    fallback = next((option for option in options if option.code == MISCELLANEOUS_THEME_CODE), None)
    return [option for option in options if option is not fallback], fallback


def build_search_text(document: DocumentMetadata) -> str:
    parts = [document.title, document.document_type, ' '.join(document.tags), document.summary]
    return ' '.join(part for part in parts if part)[:SEARCH_TEXT_MAX_CHARS]


def load_secondary_candidates(document: DocumentMetadata,
                              settings: SecondaryThemeSettings) -> Tuple[List[SecondaryCandidate], int]:
    if settings.count <= 0:
        return [], 0
    queryset = ResourceTheme.objects.filter(
        is_primary=False, status__in=settings.candidate_statuses
    ).only('id', 'name', 'description')
    total = queryset.count()
    if total <= settings.candidate_limit:
        rows = queryset.order_by('name')
    else:
        rows = queryset.annotate(
            relevance=WordSimilarity(F('name'), Value(build_search_text(document)))
        ).order_by('-relevance', 'name')[:settings.candidate_limit]
    candidates = [
        SecondaryCandidate(id=theme.id, name=theme.name, description=theme.description) for theme in rows
    ]
    return candidates, total


def build_theme_code(name: str) -> str:
    decomposed = unicodedata.normalize('NFKD', normalize_theme_name(name))
    ascii_name = decomposed.encode('ascii', 'ignore').decode()
    title_cased = ' '.join(word[:1].upper() + word[1:] for word in ascii_name.split())
    code = re.sub(r'[^0-9A-Za-z]+', '_', title_cased).strip('_')
    if not any(char.isalnum() and not char.isascii() for char in decomposed):
        return code[:THEME_CODE_MAX_LENGTH]

    digest = hashlib.sha1(decomposed.casefold().encode()).hexdigest()[:THEME_CODE_HASH_LENGTH]
    prefix = code[:THEME_CODE_MAX_LENGTH - THEME_CODE_HASH_LENGTH - 1] or 'Theme'
    return f"{prefix}_{digest}"


def acquire_secondary_theme_lock() -> None:
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [SECONDARY_THEME_LOCK_KEY])


def resolve_generated_theme(
        classified: ClassifiedTheme, threshold: float
) -> Tuple[Optional[ResourceTheme], str, str]:
    code = build_theme_code(classified.name)
    exact_lookup = Q(name__iexact=classified.name) | Q(code__iexact=code)
    exact = ResourceTheme.objects.filter(exact_lookup).first()
    if exact:
        return exact, SecondaryThemeMatchType.DEDUPLICATED, 'exact name or code match'

    neighbours = (
        ResourceTheme.objects.filter(is_primary=False)
        .annotate(similarity=TrigramSimilarity('name', classified.name))
        .filter(similarity__gte=min(threshold, NEAR_DUPLICATE_NEIGHBOUR_FLOOR))
        .order_by('-similarity')[:NEAR_DUPLICATE_NEIGHBOUR_LIMIT]
    )
    for neighbour in neighbours:
        if neighbour.similarity >= threshold:
            return neighbour, SecondaryThemeMatchType.DEDUPLICATED, (
                f'name similarity {neighbour.similarity:.2f} >= {threshold:.2f}'
            )
        if is_token_variant(classified.name, neighbour.name):
            return neighbour, SecondaryThemeMatchType.DEDUPLICATED, (
                f'word-set variant (similarity {neighbour.similarity:.2f})'
            )

    try:
        with transaction.atomic():
            theme = ResourceTheme.objects.create(
                name=classified.name, code=code, description=classified.description,
                is_primary=False, status=ThemeStatus.DRAFT,
            )
        return theme, SecondaryThemeMatchType.CREATED, 'new theme'
    except IntegrityError:
        return ResourceTheme.objects.filter(exact_lookup).first(), SecondaryThemeMatchType.DEDUPLICATED, (
            'created concurrently by another upload'
        )


def is_enabled(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ('false', '0', 'no', 'off', '')
    return bool(value)


def _queue_after_commit(task, media_id: int, label: str, **options) -> None:
    def _dispatch():
        try:
            task.apply_async(args=(media_id,), **options)
            logger.info(f"[ThemeClassifier] media_id={media_id} {label} queued {options}")
        except Exception as e:
            logger.error(f"[ThemeClassifier] media_id={media_id} failed to queue {label}: {e}")

    transaction.on_commit(_dispatch)


def queue_vector_theme_sync(media_id: int) -> None:
    from chatbot.celery_tasks.knowledge_service.media_tasks import sync_media_theme_to_vector_db

    _queue_after_commit(
        sync_media_theme_to_vector_db, media_id, 'vector theme sync', countdown=VECTOR_THEME_SYNC_DELAY_SECONDS
    )


def _clean_summary(summary: Optional[str]) -> str:
    summary = (summary or '').strip()
    return '' if summary.startswith(EXTRACTION_PLACEHOLDER_PREFIX) else summary


def extract_text_from_media_file(media: Media) -> str:
    from chatbot.utils.knowledge_service.base.extraction_config import parse_extractor_config
    from chatbot.utils.knowledge_service.extractor.document_extractor import DocumentExtractor

    if not media.file:
        return ''
    extension = os.path.splitext(media.file.name)[1].lstrip('.').lower()
    if not extension:
        return ''

    extractor_bot = get_company_bot(DOC_TEXT_EXTRACTOR_ROUTE, media.company_bot.company) or media.company_bot
    try:
        extractor = DocumentExtractor(**parse_extractor_config(extractor_bot))
        with media.file.open('rb') as file:
            extracted = extractor.extract_text_from_file(file, extension)
    except Exception as e:
        logger.warning(
            f"[ThemeClassifier] media_id={media.id} could not read text from file {media.file.name!r}: {e}"
        )
        return ''
    text = extracted[0] if extracted else ''
    return (text or '').strip()


def build_document_metadata(media: Media) -> DocumentMetadata:
    key_values = dict(
        KeyValue.objects.filter(media=media, key__in=[TITLE_KEY, DOCUMENT_TYPE_KEY, KEY_ENTITIES_KEY])
        .values_list('key', 'value')
    )
    key_entities = key_values.get(KEY_ENTITIES_KEY) or ''
    return DocumentMetadata(
        title=key_values.get(TITLE_KEY) or media.name or '',
        summary=_clean_summary(media.description) or _clean_summary(media.extracted_text),
        tags=tuple(media.tags.order_by('name').values_list('name', flat=True)),
        document_type=key_values.get(DOCUMENT_TYPE_KEY) or '',
        key_entities=tuple(entity.strip() for entity in key_entities.split(',') if entity.strip()),
    )


class MediaThemeClassificationService:

    def __init__(self, media: Media, invoke: Callable[..., Any] = handle_bedrock_model):
        self.media = media
        self.invoke = invoke
        self.log_prefix = f"[ThemeClassifier] media_id={media.id}"

    def run(self) -> ThemeClassificationOutcome:
        started_at = time.monotonic()
        logger.info(f"{self.log_prefix} classification started name={self.media.name!r}")

        company_bot = get_theme_classifier_bot(self.media.company_bot.company)
        if not company_bot:
            logger.error(f"{self.log_prefix} no CompanyBot with route {THEME_CLASSIFIER_ROUTE}; skipping")
            return self._flag_for_review(ThemeClassificationStatus.SKIPPED_NO_BOT)

        themes, fallback = load_theme_options()
        if not themes or not fallback:
            logger.error(
                f"{self.log_prefix} published primary themes missing (themes={len(themes)}, "
                f"fallback={'yes' if fallback else 'no'}); skipping"
            )
            return self._flag_for_review(ThemeClassificationStatus.SKIPPED_NO_THEMES)

        document = build_document_metadata(self.media)
        if not document.is_classifiable:
            file_text = extract_text_from_media_file(self.media)
            if file_text:
                document = replace(document, summary=file_text)
                logger.info(
                    f"{self.log_prefix} no description or extracted text; "
                    f"using {len(file_text)} chars read from the file"
                )
        logger.info(
            f"{self.log_prefix} input title={document.title!r} document_type={document.document_type!r} "
            f"tags={list(document.tags)} key_entities={list(document.key_entities)} "
            f"summary_chars={len(document.summary)} summary={document.summary[:300]!r}"
        )
        if not document.is_classifiable:
            logger.warning(
                f"{self.log_prefix} no description, extracted text or file text; skipping classification"
            )
            return self._flag_for_review(ThemeClassificationStatus.SKIPPED_NO_SUMMARY)

        other_params = load_json_field(company_bot.other_params) or {}
        settings = SecondaryThemeSettings.from_params(other_params)
        candidates, candidate_total = load_secondary_candidates(document, settings)
        logger.info(
            f"{self.log_prefix} using bot_id={company_bot.id} model={company_bot.llm_model} "
            f"primary_themes={len(themes)} fallback={fallback.code} secondary_theme_count={settings.count} "
            f"policy={settings.partial_match_policy} min_match_confidence={settings.min_match_confidence} "
            f"candidates_total={candidate_total} candidates_sent={len(candidates)} "
            f"prefiltered={candidate_total > len(candidates)}"
        )

        classification = ThemeClassifier(
            company_bot, themes, fallback, invoke=self.invoke, candidates=candidates, settings=settings
        ).classify(document, log_prefix=self.log_prefix)
        generated = self._generate_new_secondary(document, themes, fallback, classification, candidates, settings)
        links = self.save_classification(classification, generated, settings)
        if is_enabled(other_params.get('vector_theme_sync_enabled'), default=False):
            queue_vector_theme_sync(self.media.id)
        else:
            logger.info(f"{self.log_prefix} vector theme sync disabled by vector_theme_sync_enabled")

        counts = Counter(link.match_type for link in links)
        status = ThemeClassificationStatus.NEEDS_REVIEW if classification.needs_review \
            else ThemeClassificationStatus.CLASSIFIED
        logger.info(
            f"{self.log_prefix} classification saved status={status} primary={classification.primary.code} "
            f"confidence={classification.primary.confidence} secondary={[link.theme.name for link in links]} "
            f"attempts={classification.attempts} needs_review={classification.needs_review} "
            f"duration={time.monotonic() - started_at:.1f}s"
        )
        return ThemeClassificationOutcome(
            media_id=self.media.id,
            status=status,
            primary_theme=classification.primary.code,
            primary_theme_name=classification.primary.name,
            secondary_themes=tuple(link.theme.name for link in links),
            needs_review=classification.needs_review,
            matched=counts[SecondaryThemeMatchType.MATCHED],
            deduplicated=counts[SecondaryThemeMatchType.DEDUPLICATED],
            created=counts[SecondaryThemeMatchType.CREATED],
        )

    def _generate_new_secondary(self, document: DocumentMetadata, themes: Sequence[ThemeOption],
                                fallback: ThemeOption, classification: ThemeClassification,
                                candidates: Sequence[SecondaryCandidate],
                                settings: SecondaryThemeSettings) -> List[ClassifiedTheme]:
        matched_count = len(classification.matched_secondary)
        needed = settings.slots_to_generate(matched_count)
        if needed <= 0:
            logger.info(
                f"{self.log_prefix} secondary generation skipped matched={matched_count} "
                f"target={settings.count} policy={settings.partial_match_policy}"
            )
            return []

        generator_bot = get_company_bot(settings.generator_route, self.media.company_bot.company)
        if not generator_bot:
            logger.error(
                f"{self.log_prefix} no CompanyBot with route {settings.generator_route}; "
                f"cannot create new secondary themes (needed={needed})"
            )
            return []

        logger.info(
            f"{self.log_prefix} secondary generation requested needed={needed} matched={matched_count} "
            f"target={settings.count} bot_id={generator_bot.id} existing_names_sent={len(candidates)}"
        )
        generator = SecondaryThemeGenerator(
            generator_bot, themes, fallback, invoke=self.invoke, retries=settings.generation_retries
        )
        return generator.generate(
            document, classification.primary, classification.matched_secondary,
            [candidate.name for candidate in candidates], needed, log_prefix=self.log_prefix,
        )

    def save_classification(self, classification: ThemeClassification, generated: Sequence[ClassifiedTheme],
                            settings: SecondaryThemeSettings) -> List[SecondaryThemeLink]:
        with transaction.atomic():
            media = Media.objects.select_for_update().get(pk=self.media.pk)
            media.primary_theme_id = classification.primary.code
            media.primary_theme_confidence = classification.primary.confidence
            media.primary_theme_reasoning = classification.primary.reasoning
            media.needs_review = classification.needs_review
            bulk_update_with_history([media], Media, MEDIA_THEME_FIELDS)

            links = self._resolve_links(classification.matched_secondary, generated, settings)
            MediaSecondaryTheme.objects.filter(media=media).delete()
            MediaSecondaryTheme.objects.bulk_create([
                MediaSecondaryTheme(
                    media=media, theme=link.theme, confidence=link.confidence,
                    reasoning=link.reasoning, match_type=link.match_type,
                )
                for link in links
            ])
        self.media = media
        self._log_links(links)
        return links

    def _resolve_links(self, matched: Sequence[ClassifiedTheme], generated: Sequence[ClassifiedTheme],
                       settings: SecondaryThemeSettings) -> List[SecondaryThemeLink]:
        links: Dict[int, SecondaryThemeLink] = {}
        existing = ResourceTheme.objects.in_bulk([theme.theme_id for theme in matched])
        for classified in matched:
            theme = existing.get(classified.theme_id)
            if theme is None or theme.is_primary:
                logger.warning(
                    f"{self.log_prefix} matched secondary theme_id={classified.theme_id} "
                    f"is no longer available; skipped"
                )
                continue
            links.setdefault(theme.pk, SecondaryThemeLink(
                theme, SecondaryThemeMatchType.MATCHED, classified.confidence, classified.reasoning,
                'selected from existing secondary themes',
            ))

        if generated:
            acquire_secondary_theme_lock()
            for classified in generated:
                if len(links) >= settings.count:
                    logger.info(
                        f"{self.log_prefix} secondary limit {settings.count} reached; "
                        f"skipped {describe_theme(classified)}"
                    )
                    break
                theme, match_type, detail = resolve_generated_theme(classified, settings.near_duplicate_threshold)
                if theme is None or theme.is_primary:
                    logger.warning(
                        f"{self.log_prefix} generated {describe_theme(classified)} did not resolve to a "
                        f"secondary theme; skipped"
                    )
                    continue
                if theme.pk in links:
                    logger.info(
                        f"{self.log_prefix} generated {describe_theme(classified)} resolved to already linked "
                        f"theme_id={theme.pk} name={theme.name!r}; skipped"
                    )
                    continue
                links[theme.pk] = SecondaryThemeLink(
                    theme, match_type, classified.confidence, classified.reasoning,
                    f'generated {classified.name!r}: {detail}',
                )
        return list(links.values())

    def _log_links(self, links: Sequence[SecondaryThemeLink]) -> None:
        for link in links:
            confidence = f"{link.confidence:.2f}" if link.confidence is not None else '-'
            logger.info(
                f"{self.log_prefix} secondary theme match_type={link.match_type} theme_id={link.theme.pk} "
                f"name={link.theme.name!r} status={link.theme.status} confidence={confidence} "
                f"detail={link.detail!r} reason={link.reasoning!r}"
            )
        counts = Counter(link.match_type for link in links)
        reused = counts[SecondaryThemeMatchType.MATCHED] + counts[SecondaryThemeMatchType.DEDUPLICATED]
        reuse_rate = f"{reused / len(links):.2f}" if links else '-'
        logger.info(
            f"{self.log_prefix} secondary summary linked={len(links)} "
            f"matched={counts[SecondaryThemeMatchType.MATCHED]} "
            f"deduplicated={counts[SecondaryThemeMatchType.DEDUPLICATED]} "
            f"created={counts[SecondaryThemeMatchType.CREATED]} reuse_rate={reuse_rate}"
        )

    def _flag_for_review(self, status: str) -> ThemeClassificationOutcome:
        with transaction.atomic():
            media = Media.objects.select_for_update().get(pk=self.media.pk)
            media.needs_review = True
            bulk_update_with_history([media], Media, ['needs_review'])
        self.media = media
        logger.warning(f"{self.log_prefix} flagged for review status={status}")
        return ThemeClassificationOutcome(media_id=media.id, status=status, needs_review=True)


def enqueue_theme_classification(media_id: int) -> str:
    from chatbot.celery_tasks.knowledge_service.theme_tasks import classify_media_themes

    task_id = str(uuid.uuid4())
    _queue_after_commit(classify_media_themes, media_id, 'classification task', task_id=task_id)
    return task_id


def wait_for_theme_classification(task_id: str, timeout: float) -> Optional[Dict[str, Any]]:
    from celery.result import AsyncResult

    deadline = time.monotonic() + timeout
    delay = 0.5
    while time.monotonic() < deadline:
        result = AsyncResult(task_id)
        if result.ready():
            if result.successful() and isinstance(result.result, dict):
                return result.result
            return {'status': ThemeClassificationStatus.FAILED, 'error': str(result.result)}
        time.sleep(min(delay, max(deadline - time.monotonic(), 0)))
        delay = min(delay * 2, THEME_WAIT_MAX_POLL_SECONDS)
    logger.info(f"[ThemeClassifier] task_id={task_id} still running after {timeout}s; not waiting further")
    return None


def theme_outcome_message(media_name: str, outcome: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    label = f"'{media_name}'"
    if outcome is None:
        return ThemeMessageLevel.INFO, (
            f"Theme mapping for {label} is still running in the background. Refresh the list in a few seconds."
        )

    status = outcome.get('status')
    if status in (ThemeClassificationStatus.CLASSIFIED, ThemeClassificationStatus.NEEDS_REVIEW):
        primary = outcome.get('primary_theme_name') or outcome.get('primary_theme') or '-'
        secondary = ', '.join(outcome.get('secondary_themes') or []) or 'none'
        message = f"Themes mapped for {label}: primary {primary}; secondary {secondary}."
        if status == ThemeClassificationStatus.NEEDS_REVIEW:
            return ThemeMessageLevel.WARNING, (
                f"{message} It is flagged for review because the classifier was not confident."
            )
        return ThemeMessageLevel.SUCCESS, message
    if status == ThemeClassificationStatus.SKIPPED_NO_SUMMARY:
        return ThemeMessageLevel.WARNING, (
            f"Themes were not mapped for {label}: it has no description or extracted text, and no text "
            f"could be read from the file. Add a description and save again, or use Upload media to extract one "
            f"automatically."
        )
    if status == ThemeClassificationStatus.SKIPPED_NO_BOT:
        return ThemeMessageLevel.ERROR, (
            f"Themes were not mapped for {label}: the Theme Classifier bot is not configured."
        )
    if status == ThemeClassificationStatus.SKIPPED_NO_THEMES:
        return ThemeMessageLevel.ERROR, f"Themes were not mapped for {label}: no published primary themes exist."
    return ThemeMessageLevel.ERROR, f"Theme mapping failed for {label}. Check the Celery worker logs."
