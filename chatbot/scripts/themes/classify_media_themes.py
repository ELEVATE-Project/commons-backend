import logging
import os
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import django

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
    django.setup()

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from simple_history.utils import bulk_update_with_history

from chatbot.celery_tasks.knowledge_service.media_tasks import (
    build_vector_db_metadata, delete_from_vector_db, save_in_vector_db
)
from chatbot.celery_tasks.knowledge_service.theme_tasks import classify_media_themes
from chatbot.constants.constants import DOCUMENT_TYPE_KEY, EXTRACTION_PLACEHOLDER_PREFIX, TITLE_KEY
from chatbot.models import FileTypeChoices, KeyValue, LLMProvider, Media
from chatbot.utils.database_util import build_document_fields, is_document_indexed
from chatbot.utils.knowledge_service.auto_tag_utils import TagProcessor
from chatbot.utils.knowledge_service.base.extraction_config import parse_extractor_config
from chatbot.utils.knowledge_service.base.main import get_doc_tags_from_ai
from chatbot.utils.themes.theme_classifier import SecondaryThemeSettings, load_json_field
from chatbot.utils.themes.theme_classification_service import (
    MediaThemeClassificationService, get_company_bot, get_theme_classifier_bot, load_theme_options
)
from chatbot.views.Media.save_views import BatchMediaSaveView
from chatbot.views.Media.status_views import BatchMediaTaskStatusView

logger = logging.getLogger('django')

# Same order as the Media admin list, so a partial run (--limit) fills in the top of its first page.
NEWEST_FIRST = ('-created_at', '-id')

# --fill-missing checks each media for these values in Postgres and never changes one that is already there
SUMMARY = 'summary'
TAGS = 'tags'
THEME = 'theme'
# The upload screen drops this key value before saving, since it is stored as Media.organization
ORGANIZATION_KEY = 'ORGANIZATION'
# Only the extraction LLM can fill these; TITLE falls back to Media.name
LLM_FIELDS = (SUMMARY, TAGS, DOCUMENT_TYPE_KEY)
CHANGE_REASON = 'Missing metadata filled by classify_media_themes --fill-missing'
# 404 means the document was never indexed, so indexing it fresh is still safe
DELETE_OK_STATUSES = (200, 404)
# Connection error or timeout: the vector DB did not answer at all, so the run stops
VECTOR_DB_UNREACHABLE_STATUSES = (503, 504)
# Top-level vector DB fields that are left out of the request when they are empty in Postgres
OPTIONAL_VECTOR_FIELDS = ('summary', 'theme', 'tags')
LOG_VALUE_MAX_CHARS = 200


def shorten(value):
    """Cuts long strings, inside dicts and lists too, so a log line stays readable"""
    if isinstance(value, dict):
        return {key: shorten(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shorten(item) for item in value]
    if isinstance(value, str) and len(value) > LOG_VALUE_MAX_CHARS:
        return f'{value[:LOG_VALUE_MAX_CHARS]}... ({len(value)} chars)'
    return value


class Command(BaseCommand):
    help = 'Classify primary and secondary themes for existing media files using the Theme Classifier bot.'

    def add_arguments(self, parser):
        parser.add_argument('--media-ids', type=str, help='Comma-separated Media IDs to classify.')
        parser.add_argument('--company-slug', type=str, help='Only classify media owned by this company.')
        parser.add_argument('--all', action='store_true',
                            help='Reclassify every matching media, including already classified ones.')
        parser.add_argument('--include-subdocuments', action='store_true',
                            help='Also classify subdocuments (media with a parent).')
        parser.add_argument('--limit', type=int, help='Maximum number of media to process, newest first.')
        parser.add_argument('--interval', type=float, default=2.0,
                            help='Seconds between queued task start times, to avoid LLM throttling (default: 2.0). '
                                 'With --fill-missing, seconds to wait after each media that needed an LLM call.')
        parser.add_argument('--sync', action='store_true',
                            help='Run classification in this process instead of queueing Celery tasks.')
        parser.add_argument('--fill-missing', action='store_true',
                            help='Also fill the missing summary, tags and key values (from Postgres or the extraction '
                                 'LLM), then re-index each changed media in the vector DB. Media listed in '
                                 '--media-ids are always re-indexed, even when nothing is missing. Stops when the '
                                 'vector DB does not answer. Always runs in this process.')
        parser.add_argument('--dry-run', action='store_true', help='List matching media without classifying.')

    def handle(self, *args, **options):
        self._check_prerequisites()
        if options['fill_missing']:
            if options['all']:
                raise CommandError('--all reclassifies existing themes and cannot be combined with --fill-missing.')
            self._fill_missing(options)
            return

        queryset = self._build_queryset(options)
        media_ids = list(queryset.values_list('id', flat=True))
        self.stdout.write(f"Matched {len(media_ids)} media for theme classification.")

        if options['dry_run']:
            self.stdout.write(', '.join(map(str, media_ids)) or 'Nothing to classify.')
            return

        if options['sync']:
            self._run_sync(media_ids)
        else:
            self._enqueue(media_ids, options['interval'])

    def _check_prerequisites(self):
        themes, fallback = load_theme_options()
        if not themes or not fallback:
            raise CommandError('Published primary themes (including Miscellaneous) are missing. Run migrations first.')
        classifier_bot = get_theme_classifier_bot(None)
        if not classifier_bot:
            raise CommandError('Theme Classifier bot (route /theme_classifier) not found. Import it first.')
        settings = SecondaryThemeSettings.from_params(load_json_field(classifier_bot.other_params))
        if settings.count and not get_company_bot(settings.generator_route, None):
            self.stderr.write(self.style.WARNING(
                f"Secondary Theme Generator bot (route {settings.generator_route}) not found: existing secondary "
                f"themes will still be matched, but no new ones will be created."
            ))

    def _build_queryset(self, options):
        queryset = self._base_queryset(options)
        if not options['all']:
            queryset = queryset.filter(primary_theme__isnull=True, needs_review=False)
        if options['limit']:
            queryset = queryset[:options['limit']]
        return queryset

    def _base_queryset(self, options):
        queryset = Media.objects.order_by(*NEWEST_FIRST)

        if options['media_ids']:
            try:
                ids = [int(value) for value in options['media_ids'].split(',') if value.strip()]
            except ValueError:
                raise CommandError('--media-ids must be a comma-separated list of integers.') from None
            queryset = queryset.filter(id__in=ids)
        if options['company_slug']:
            queryset = queryset.filter(company_bot__company__slug=options['company_slug'])
        if not options['include_subdocuments']:
            queryset = queryset.filter(parent__isnull=True)
        return queryset

    def _enqueue(self, media_ids, interval):
        for index, media_id in enumerate(media_ids):
            classify_media_themes.apply_async(args=(media_id,), countdown=index * interval)
        self.stdout.write(self.style.SUCCESS(
            f"Queued {len(media_ids)} classification tasks over ~{int(len(media_ids) * interval)}s."
        ))

    def _run_sync(self, media_ids):
        statuses = Counter()
        for media in Media.objects.select_related('company_bot__company').filter(id__in=media_ids).order_by(*NEWEST_FIRST):
            try:
                outcome = MediaThemeClassificationService(media).run()
            except Exception as e:
                self.stderr.write(f"media_id={media.id} failed: {e}")
                statuses['failed'] += 1
                continue
            statuses[outcome.status] += 1
            self.stdout.write(f"media_id={media.id} status={outcome.status} primary={outcome.primary_theme}")
        self.stdout.write(self.style.SUCCESS(f"Done: {dict(statuses)}"))

    def _fill_missing(self, options):
        """
        For each media: summary, tags and DOCUMENT_TYPE come from the upload's extraction LLM call, mapped and stored
        the way the upload screen does it (tags are limited to approved master tags), along with the other key values
        it returns that the media lacks (GEOGRAPHY, KEY ENTITIES, ...). TITLE comes from that call, otherwise from
        Media.name. Then the theme is classified, and a media that had anything filled, or that is missing from the
        vector DB, is deleted and indexed again there, the same way Media.save() does it. Media listed in --media-ids
        are always indexed again, so a vector sync that failed in an earlier run can be retried. When the vector DB
        does not answer, the run stops rather than filling Postgres for documents it cannot index. Every step is
        logged to the django logger (info.log, error.log) with a "[MediaBackfill] media_id=<id>" prefix, and printed:
        the Postgres values before and after, and the exact fields sent to the vector DB.
        """
        self.dry_run = options['dry_run']
        self.counts = Counter()
        self._master_tags_by_bot = {}
        self._can_ask_vector_db = True
        self._vector_db_down = False
        self._always_reindex = bool(options['media_ids'])
        media_ids = list(self._base_queryset(options).values_list('id', flat=True))
        self._log(logging.INFO, (
            f'fill-missing run started media_to_check={len(media_ids)} dry_run={self.dry_run} limit={options["limit"]}'
        ))

        failed = {}
        for media_id in media_ids:
            if options['limit'] and self.counts['with missing values'] >= options['limit']:
                self._log(logging.INFO, f'--limit {options["limit"]} reached, stopping')
                break

            # Fetched one at a time, so a long run sees edits made while it was running
            media = self._fetch(media_id)
            if not media:
                continue
            missing = self._find_missing(media)
            indexed = self._vector_db_indexed(media)
            if self._vector_db_down:
                break
            if not missing and indexed is not False:
                self.counts['complete'] += 1
                if not self._always_reindex:
                    self._log(logging.INFO, f'complete: nothing missing in Postgres, indexed_in_vector_db={indexed}', media)
                    continue
                self._log(logging.INFO, 'complete in Postgres; re-indexing in the vector DB, as it is listed in --media-ids', media)
            else:
                self.counts['with missing values'] += 1

            started_at = time.monotonic()
            self._used_llm = False
            try:
                errors = self._backfill(media, missing, indexed)
            except Exception as e:
                self._log(logging.ERROR, f'crashed: {e}', media, exc_info=True)
                errors = [f'crashed: {e}']
            if self.dry_run:
                if errors:
                    self._log(logging.WARNING, f'dry run: would fail: {errors}', media)
                continue

            duration = time.monotonic() - started_at
            if errors:
                failed[media.id] = errors
                self._log(logging.ERROR, f'finished with errors duration={duration:.1f}s errors={errors}', media)
            else:
                self._log(logging.INFO, f'finished duration={duration:.1f}s', media)
            if self._vector_db_down:
                break
            if self._used_llm and options['interval']:
                time.sleep(options['interval'])

        self._log(logging.INFO, f'fill-missing run finished {dict(self.counts)} failed_ids={sorted(failed)}')
        retry = f'--fill-missing --media-ids {",".join(map(str, sorted(failed)))}'
        if self._vector_db_down:
            first = f'run {retry} (their vector DB document was not updated), then ' if failed else ''
            raise CommandError(
                f'Stopped: the vector DB at {os.getenv("VECTOR_DB_BASE_URL")} did not answer. Start or restart it, '
                f'{first}run this command again.'
            )
        if failed:
            raise CommandError(f'{len(failed)} media finished with errors: {sorted(failed)}. Retry them with {retry}')

    @staticmethod
    def _fetch(media_id):
        return Media.objects.select_related('organization', 'company_bot__company').filter(id=media_id).first()

    def _find_missing(self, media):
        missing = []
        description = (media.description or '').strip()
        if not description or description.startswith(EXTRACTION_PLACEHOLDER_PREFIX):
            missing.append(SUMMARY)
        if not media.tags.exists():
            missing.append(TAGS)
        keys = self._keys_with_value(media)
        missing.extend(key for key in (DOCUMENT_TYPE_KEY, TITLE_KEY) if key not in keys)
        # Same rule as the default run: media flagged for review are left for a person to map
        if not media.primary_theme_id and not media.needs_review:
            missing.append(THEME)
        return missing

    @staticmethod
    def _keys_with_value(media):
        return {
            key.strip().upper()
            for key, value in media.key_values.values_list('key', 'value')
            if value and value.strip()
        }

    def _backfill(self, media, missing, indexed):
        """Fills what it can and returns the errors, empty when every step worked"""
        self._log(logging.INFO, (
            f'started name={media.name!r} missing_in_postgres={missing} indexed_in_vector_db={indexed}'
        ), media)
        self._log(logging.INFO, f'postgres before: {self._postgres_snapshot(media)}', media)
        llm_fields = [field for field in missing if field in LLM_FIELDS]
        if llm_fields and not media.file:
            self._log(logging.WARNING, f'has no file, so {llm_fields} cannot be extracted', media)
            llm_fields = []
        if self.dry_run:
            self._log(logging.INFO, f'dry run: {self._describe_plan(media, missing, llm_fields, indexed)}', media)
            if media.file and media.organization:
                self._log_vector_payload(media, 'vector DB payload with the current Postgres values')
            return []

        errors = []
        extracted = None
        if llm_fields:
            try:
                extracted = self._extract(media)
            except Exception as e:
                errors.append(f'extraction failed: {e}')
                self._log(logging.ERROR, f'extraction failed: {e}; filling from Postgres only', media)

        filled = self._fill_postgres(media.id, extracted)

        if THEME in missing:
            try:
                if self._classify_theme(media):
                    filled.append(THEME)
            except Exception as e:
                errors.append(f'theme classification failed: {e}')
                self._log(logging.ERROR, f'theme classification failed: {e}', media, exc_info=True)

        media = self._fetch(media.id)
        self._log(logging.INFO, f'postgres after: {self._postgres_snapshot(media)}', media)
        still_missing = self._find_missing(media)
        if still_missing:
            self._log(logging.WARNING, f'still missing in postgres after backfill: {still_missing}', media)
        if not filled and indexed is not False and not self._always_reindex:
            self._log(logging.INFO, 'nothing was filled and the document is not missing from the vector DB, '
                                    'so the vector DB is left as it is', media)
            return errors
        if not media.file:
            self._log(logging.WARNING, 'has no file, so it cannot be indexed in the vector DB', media)
            return errors

        # When it classified a theme, the theme classifier has also queued its own vector theme sync through
        # Celery (if vector_theme_sync_enabled); that sends this same data again, so the result is the same.
        if filled:
            reason = f'filled={filled}'
        elif indexed is False:
            reason = 'document missing from the vector DB'
        else:
            reason = 'listed in --media-ids'
        self._log(logging.INFO, f'vector sync started {reason}', media)
        if media.organization:
            self._log_vector_payload(media, 'vector DB payload')
        vector_error = self._sync_vector_db(media)
        if vector_error:
            errors.append(f'vector sync failed: {vector_error}')
            self._log(logging.ERROR, f'vector sync failed: {vector_error}', media)
        else:
            self.counts['vector synced'] += 1
            self._log(logging.INFO, 'vector sync done', media)
        return errors

    def _describe_plan(self, media, missing, llm_fields, indexed):
        plan = []
        if llm_fields:
            plan.append(f'would call the extraction LLM for {llm_fields}')
        if TITLE_KEY in missing:
            source = 'the LLM, falling back to Media.name' if llm_fields else 'Media.name'
            plan.append(f'would fill {TITLE_KEY} from {source}')
        if THEME in missing:
            plan.append('would classify the theme')
        if not media.file:
            plan.append('cannot be indexed in the vector DB (no file)')
        elif indexed is False:
            plan.append('would index it in the vector DB, where it is missing')
        elif self._always_reindex:
            plan.append('would re-index it in the vector DB, as it is listed in --media-ids')
        else:
            plan.append('would re-index in the vector DB if anything gets filled')
        return '; '.join(plan)

    def _vector_db_indexed(self, media):
        """True or False from the vector DB; None when it cannot be asked"""
        if not self._can_ask_vector_db:
            return None
        if media.company_bot.provider == LLMProvider.OPENAI:
            # These live in OpenAI's vector store, which verify-sources does not cover
            return None
        indexed = is_document_indexed(media.id)
        if indexed is None:
            self._can_ask_vector_db = False
            if self.dry_run:
                self._log(logging.WARNING, 'could not reach the vector DB to check which documents are indexed; '
                                           'not checking again in this dry run', media)
            else:
                self._vector_db_down = True
                self._log(logging.ERROR, 'could not reach the vector DB to check whether it is indexed; '
                                         'stopping before changing anything for this media', media)
        return indexed

    @staticmethod
    def _postgres_snapshot(media):
        return shorten({
            'description': media.description,
            'tags': list(media.tags.values_list('name', flat=True)),
            'primary_theme': media.primary_theme_id,
            'needs_review': media.needs_review,
            'key_values': dict(media.key_values.values_list('key', 'value')),
        })

    def _log_vector_payload(self, media, label):
        """Logs the fields save_in_vector_db sends, built by the same functions it uses"""
        try:
            metadata = build_vector_db_metadata(media)
            if media.company_bot.provider == LLMProvider.OPENAI:
                self._log(logging.INFO, f'{label} (OpenAI vector store attributes): metadata={shorten(metadata)}', media)
                return
            fields = build_document_fields(media)
        except Exception as e:
            self._log(logging.WARNING, f'could not build the vector DB payload to log it: {e}', media)
            return

        self._log(logging.INFO, (
            f'{label}: source_id={media.id} priority={media.priority!r} {shorten(fields)} metadata={shorten(metadata)}'
        ), media)
        not_sent = [field for field in OPTIONAL_VECTOR_FIELDS if field not in fields]
        if not_sent:
            self._log(logging.WARNING, f'vector DB will not get {not_sent}, as they are empty in Postgres', media)

    def _extract(self, media):
        """Runs the upload's extraction LLM call on the media file and maps the result like the upload screen"""
        company_bot = media.company_bot
        extension = os.path.splitext(media.file.name)[1].lstrip('.').lower()
        if not FileTypeChoices.is_valid_extension(extension):
            raise ValueError(f'unsupported file type {extension!r}')
        max_file_size_mb = parse_extractor_config(company_bot).get('max_file_size_mb', 50)
        file_size = media.file.size
        if file_size > max_file_size_mb * 1024 * 1024:
            raise ValueError(f'file is {file_size / (1024 * 1024):.1f} MB, over the {max_file_size_mb} MB limit')

        other_data = {'master_tag': self._master_tags(company_bot), 'original_filename': media.name}
        self._log(logging.INFO, (
            f'extraction started bot_id={company_bot.id} file={media.file.name!r} '
            f'size_bytes={file_size} master_tags={len(other_data["master_tag"])}'
        ), media)
        self._used_llm = True
        self.counts['llm extractions'] += 1
        started_at = time.monotonic()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}') as tmp:
                tmp_path = tmp.name
                with media.file.open('rb') as source:
                    for chunk in source.chunks():
                        tmp.write(chunk)
            ai_data = get_doc_tags_from_ai(
                file=tmp_path, company_bot=company_bot, file_extension=extension, other_data=other_data
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        duration = time.monotonic() - started_at

        if not ai_data or ai_data.get('error') or ai_data.get('error_type'):
            ai_data = ai_data or {}
            raise ValueError(
                f'{ai_data.get("error") or "no data returned"} '
                f'(error_type={ai_data.get("error_type")}, duration={duration:.1f}s)'
            )

        ai_data['original_filename'] = media.name
        processed = BatchMediaTaskStatusView().process_ai_extracted_data(ai_data)
        enhanced = processed['enhanced_data']
        extracted = {
            'summary': (enhanced.get('summary') or '').strip(),
            'auto_tags': processed['auto_tags'],
            'key_values': enhanced.get('enhanced_key_values') or [],
        }

        returned_tags = TagProcessor.extract_tag_texts(ai_data.get('tags') or [])
        kept_tags = TagProcessor.extract_tag_texts(extracted['auto_tags'])
        self._log(logging.INFO, (
            f'extraction done duration={duration:.1f}s summary_chars={len(extracted["summary"])} '
            f'tags_kept={kept_tags} tags_dropped_not_master={[tag for tag in returned_tags if tag not in kept_tags]} '
            f'key_values={[kv["key"] for kv in extracted["key_values"]]}'
        ), media)
        return extracted

    def _master_tags(self, company_bot):
        if company_bot.id not in self._master_tags_by_bot:
            self._master_tags_by_bot[company_bot.id] = TagProcessor.get_master_tags(
                company=company_bot.company, other_params=company_bot.other_params
            )
        return self._master_tags_by_bot[company_bot.id]

    def _fill_postgres(self, media_id, extracted):
        """Writes only the values that are missing and returns the names of the fields it filled"""
        filled = []
        history_fields = ['updated_at']
        with transaction.atomic():
            # Locked and checked again: the LLM call can take minutes, and someone may have filled a value meanwhile
            media = Media.objects.select_for_update().get(id=media_id)
            missing = self._find_missing(media)
            if SUMMARY in missing and extracted and extracted['summary']:
                previous = media.description
                media.description = extracted['summary']
                history_fields.append('description')
                filled.append(SUMMARY)
                self._log(logging.INFO, (
                    f'description filled from LLM chars={len(media.description)} previous={previous!r}'
                ), media)

            if TAGS in missing and extracted and extracted['auto_tags']:
                tags = TagProcessor.process_tags_for_media(
                    extracted['auto_tags'], 'extracted', None, media.organization, is_manual=False
                )
                media.tags.add(*tags)
                filled.append(TAGS)
                self._log(logging.INFO, f'tags filled from LLM tags={[tag.name for tag in tags]}', media)

            for key, value, source in self._missing_key_values(media, extracted):
                # Only rows with an empty value can exist for a missing key, so this never overwrites data
                if not KeyValue.objects.filter(media=media, key__iexact=key).update(value=value):
                    KeyValue.objects.create(media=media, key=key, value=value)
                filled.append(key)
                self._log(logging.INFO, f'key value {key} filled from {source} value={value[:200]!r}', media)

            if filled:
                # Not Media.save(): that would re-index in the vector DB through Celery before this step finishes
                media.updated_at = timezone.now()
                bulk_update_with_history([media], Media, history_fields, default_change_reason=CHANGE_REASON)

        for field in filled:
            self.counts[f'filled {field}' if field in (SUMMARY, TAGS) else 'key values added'] += 1
        return filled

    @staticmethod
    def _missing_key_values(media, extracted):
        """Yields (key, value, source) for each key value the media lacks, preferring the LLM's value"""
        have = Command._keys_with_value(media) | {ORGANIZATION_KEY}
        candidates = []
        if extracted:
            clean_key = BatchMediaSaveView().clean_key_for_ordered_list
            candidates += [
                (clean_key(kv['key']), Command._format_like_upload(kv), 'LLM') for kv in extracted['key_values']
            ]
        candidates.append((TITLE_KEY, media.name, 'Postgres Media.name'))

        for key, value, source in candidates:
            key, value = str(key or '').strip(), str(value or '').strip()
            if key and value and key.upper() not in have:
                have.add(key.upper())
                yield key, value, source

    @staticmethod
    def _format_like_upload(kv):
        """Formats a build_key_values value the way the upload screen stores it (processStructuredContentForSave)"""
        value = str(kv.get('value') or '')
        if kv.get('original_type') == 'array':
            # The screen turns the "• item" lines back into a list, which ends up saved as its Python repr
            return str([line.strip().lstrip('•').strip() for line in value.split('\n') if line.strip()])
        return re.sub(r'\n{3,}', '\n\n', '\n'.join(line.strip() for line in value.split('\n')))

    def _classify_theme(self, media):
        """Returns True when the media got a primary theme"""
        # Fetched again so the classifier sees the summary, tags and key values filled just before
        media = self._fetch(media.id)
        self._used_llm = True
        outcome = MediaThemeClassificationService(media).run()
        self._log(logging.INFO if outcome.primary_theme else logging.WARNING, (
            f'theme classification status={outcome.status} primary={outcome.primary_theme!r} '
            f'secondary={list(outcome.secondary_themes)} needs_review={outcome.needs_review}'
        ), media)
        if outcome.primary_theme:
            self.counts['theme classified'] += 1
        return bool(outcome.primary_theme)

    def _sync_vector_db(self, media):
        """Deletes and indexes the document again; returns an error message, or None when it was indexed"""
        # Checked before deleting, since indexing would fail and leave the document missing
        if not media.organization:
            return 'has no organization, cannot be indexed; left the existing document in place'

        try:
            delete_status = delete_from_vector_db(media.id)
        except Exception as e:
            return f'delete failed: {e}; left the existing document in place'
        if delete_status not in DELETE_OK_STATUSES:
            self._vector_db_down = delete_status in VECTOR_DB_UNREACHABLE_STATUSES
            # Indexing on top of a document that was not removed would duplicate it
            return f'delete failed with status {delete_status}; left the existing document in place'

        try:
            save_status = save_in_vector_db(media.id)
        except Exception as e:
            return f'deleted but indexing failed: {e}; the document is now missing from the vector DB'
        if not 200 <= save_status < 300:
            self._vector_db_down = save_status in VECTOR_DB_UNREACHABLE_STATUSES
            return f'deleted but indexing failed with status {save_status}; the document is now missing from the vector DB'
        return None

    def _log(self, level, message, media=None, exc_info=False):
        line = f'[MediaBackfill] media_id={media.id} {message}' if media else f'[MediaBackfill] {message}'
        logger.log(level, line, exc_info=exc_info)
        style = {logging.WARNING: self.style.WARNING, logging.ERROR: self.style.ERROR}.get(level)
        self.stdout.write(style(line) if style else line)


if __name__ == '__main__':
    Command().run_from_argv([sys.argv[0], ''] + sys.argv[1:])
