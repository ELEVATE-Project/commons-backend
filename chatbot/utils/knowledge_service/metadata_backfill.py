"""Fill in an existing media's missing title, description, tags and key-values with the upload extractor."""

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from django.db import transaction
from simple_history.utils import bulk_update_with_history

from chatbot.constants.constants import DOCUMENT_TYPE_KEY, EXTRACTION_PLACEHOLDER_PREFIX, TITLE_KEY
from chatbot.models import CompanyBot, KeyValue, Media, Tag, TagChoices, TagSourceChoices
from chatbot.utils.knowledge_service.auto_tag_utils import TagProcessor
from chatbot.utils.knowledge_service.base.extraction_config import parse_extractor_config
from chatbot.utils.knowledge_service.extractor.document_extractor import DocumentExtractor
from chatbot.utils.knowledge_service.media_utils import build_key_values

logger = logging.getLogger('django')

MISSING_DESCRIPTION = 'description'
MISSING_TITLE = 'title'
MISSING_DOCUMENT_TYPE = 'document_type'
MISSING_TAGS = 'tags'
LEADING_NUMBERING = re.compile(r'^\d+\.?\s*')


@dataclass(frozen=True)
class MediaFileContent:
    text: str = ''
    images: Tuple[Dict[str, Any], ...] = ()


def has_real_description(description) -> bool:
    description = (description or '').strip()
    return bool(description) and not description.startswith(EXTRACTION_PLACEHOLDER_PREFIX)


def find_missing_metadata(media: Media) -> Tuple[str, ...]:
    keys = {
        key.upper() for key, value in KeyValue.objects.filter(media=media).values_list('key', 'value')
        if (value or '').strip()
    }
    missing = []
    if not has_real_description(media.description):
        missing.append(MISSING_DESCRIPTION)
    if TITLE_KEY not in keys:
        missing.append(MISSING_TITLE)
    if DOCUMENT_TYPE_KEY not in keys:
        missing.append(MISSING_DOCUMENT_TYPE)
    if not media.tags.exists():
        missing.append(MISSING_TAGS)
    return tuple(missing)


def build_extractor(extractor_bot: CompanyBot) -> DocumentExtractor:
    return DocumentExtractor(**parse_extractor_config(extractor_bot))


def read_media_file(media: Media, extractor: DocumentExtractor, log_prefix: str) -> MediaFileContent:
    if not media.file:
        return MediaFileContent()
    extension = os.path.splitext(media.file.name)[1].lstrip('.').lower()
    if not extension:
        return MediaFileContent()

    try:
        with media.file.open('rb') as file:
            extracted = extractor.extract_text_from_file(file, extension)
    except Exception as e:
        logger.warning(f"{log_prefix} could not read text from file {media.file.name!r}: {e}")
        return MediaFileContent()
    # Success returns (text, images, comprehensive_text, media_type); a failure returns ('', [], '').
    text = (extracted[0] if extracted else '') or ''
    images = extracted[1] if extracted and len(extracted) > 1 and isinstance(extracted[1], list) else []
    return MediaFileContent(text=text.strip(), images=tuple(images))


def fill_missing_metadata(media: Media, extractor_bot: CompanyBot, log_prefix: str) -> Tuple[str, ...]:
    """Runs the upload's extraction call when a field is missing and saves only the missing fields.

    Returns the names of the fields it filled. The caller syncs the vector DB afterwards.
    """
    missing = find_missing_metadata(media)
    if not missing:
        logger.info(f"{log_prefix} metadata complete; extraction skipped")
        return ()
    if not extractor_bot:
        logger.error(f"{log_prefix} metadata missing={list(missing)} but no extractor bot; extraction skipped")
        return ()

    extractor = build_extractor(extractor_bot)
    content = read_media_file(media, extractor, log_prefix)
    if not content.text:
        logger.warning(f"{log_prefix} metadata missing={list(missing)} but the file has no readable text")
        return ()

    company = media.organization or getattr(media.company_bot, 'company', None)
    other_data = {
        'master_tag': TagProcessor.get_master_tags(company=company, other_params=extractor_bot.other_params),
        'original_filename': os.path.splitext(os.path.basename(media.file.name))[0],
    }
    logger.info(f"{log_prefix} metadata missing={list(missing)}; extracting from {len(content.text)} chars")
    try:
        # The same single call upload makes for each linked subdocument; links in the file are not followed.
        extracted = extractor.ai_processor.extract_basic_content(
            content.text, extractor_bot, list(content.images), other_data, is_subdoc=True
        )
    except Exception as e:
        logger.exception(f"{log_prefix} metadata extraction failed: {e}")
        return ()
    if not extracted or extracted.get('error'):
        logger.error(f"{log_prefix} metadata extraction failed: {(extracted or {}).get('error') or 'no result'}")
        return ()

    filled = _save_extracted_metadata(media, extracted, missing)
    logger.info(f"{log_prefix} metadata filled={list(filled)}")
    return filled


def _save_extracted_metadata(media: Media, extracted: Dict[str, Any], missing: Tuple[str, ...]) -> Tuple[str, ...]:
    filled: List[str] = []
    with transaction.atomic():
        locked = Media.objects.select_for_update().get(pk=media.pk)
        update_fields = []
        summary = (extracted.get('summary') or '').strip()
        if MISSING_DESCRIPTION in missing and summary:
            locked.description = summary
            update_fields.append('description')
        title = (extracted.get('title') or '').strip()
        if title and _is_file_name(locked):
            locked.name = title[:Media._meta.get_field('name').max_length]
            update_fields.append('name')
        if update_fields:
            # Not save(): that re-indexes the vector DB on its own; the caller's theme sync sends everything once.
            bulk_update_with_history([locked], Media, update_fields)
            filled.extend(update_fields)

        filled.extend(_fill_key_values(locked, extracted))
        if MISSING_TAGS in missing and _add_tags(locked, extracted.get('tags') or []):
            filled.append(MISSING_TAGS)
    media.refresh_from_db()
    return tuple(filled)


def _is_file_name(media: Media) -> bool:
    # Source documents are saved under their file name; a name the user or the AI gave is kept.
    name = (media.name or '').strip()
    extension = os.path.splitext(media.file.name)[1].lower() if media.file else ''
    return not name or bool(extension and name.lower().endswith(extension))


def _fill_key_values(media: Media, extracted: Dict[str, Any]) -> List[str]:
    rows = {row.key.upper(): row for row in KeyValue.objects.filter(media=media)}
    key_values, _ = build_key_values(extracted)
    new_rows, emptied_rows = [], []
    for key_value in key_values:
        key = LEADING_NUMBERING.sub('', str(key_value.get('key') or '').strip())
        value = str(key_value.get('value') or '').strip()
        if not key or not value:
            continue
        row = rows.get(key.upper())
        if row is None:
            row = KeyValue(media=media, key=key, value=value)
            new_rows.append(row)
        elif not (row.value or '').strip():
            row.value = value
            emptied_rows.append(row)
        else:
            continue
        rows[key.upper()] = row
    KeyValue.objects.bulk_create(new_rows)
    KeyValue.objects.bulk_update(emptied_rows, ['value'])
    return [row.key for row in new_rows + emptied_rows]


def _add_tags(media: Media, extracted_tags) -> bool:
    # Upload keeps only extracted tags that already exist as approved tags; new names are dropped.
    names = set(TagProcessor.extract_tag_texts(extracted_tags))
    if not names:
        return False
    tags = list(
        Tag.objects.filter(
            name__in=names, source_type__in=[TagSourceChoices.MANUAL, TagSourceChoices.AI_EXTRACTED],
            status=TagChoices.APPROVED,
        ).order_by('name', 'id').distinct('name')
    )
    if tags:
        media.tags.add(*tags)
    return bool(tags)
