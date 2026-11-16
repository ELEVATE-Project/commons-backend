import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import django

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
    django.setup()

from django.core.management.base import BaseCommand, CommandError

from chatbot.celery_tasks.knowledge_service.theme_tasks import classify_media_themes
from chatbot.constants.constants import DOC_TEXT_EXTRACTOR_ROUTE
from chatbot.models import Media
from chatbot.utils.knowledge_service.metadata_backfill import find_missing_metadata
from chatbot.utils.themes.theme_classifier import SecondaryThemeSettings, load_json_field
from chatbot.utils.themes.theme_classification_service import (
    MediaThemeClassificationService, get_company_bot, get_theme_classifier_bot, load_theme_options
)
# Same order as the Media admin list, so a partial run (--limit) fills in the top of its first page.
NEWEST_FIRST = ('-created_at', '-id')


class Command(BaseCommand):
    help = ('Classify primary and secondary themes for existing top-level documents and subdocuments using the '
            'Theme Classifier bot, filling in any missing description, title, document type or tags first.')

    def add_arguments(self, parser):
        parser.add_argument('--media-ids', type=str, help='Comma-separated Media IDs to classify.')
        parser.add_argument('--company-slug', type=str, help='Only classify media owned by this company.')
        parser.add_argument('--all', action='store_true',
                            help='Reclassify every matching media, including already classified ones.')
        # Top-level documents and subdocuments are both classified unless one of these narrows it.
        documents = parser.add_mutually_exclusive_group()
        documents.add_argument('--top-level-only', action='store_true',
                               help='Classify only top-level documents (media without a parent).')
        documents.add_argument('--subdocuments-only', action='store_true',
                               help='Classify only subdocuments (media with a parent).')
        parser.add_argument('--fill-missing-metadata', action=argparse.BooleanOptionalAction, default=True,
                            help='Before classifying, run the upload extractor on media missing a description, title, '
                                 'document type or tags, and save only the missing fields. One extra LLM call each. '
                                 'Use --no-fill-missing-metadata to only map themes.')
        parser.add_argument('--limit', type=int, help='Maximum number of media to process, newest first.')
        # Each task can make up to three LLM calls (extraction, classification, new secondary themes).
        parser.add_argument('--interval', type=float, default=5.0,
                            help='Seconds between queued task start times, to avoid LLM throttling (default: 5.0).')
        parser.add_argument('--sync', action='store_true',
                            help='Run classification in this process instead of queueing Celery tasks.')
        parser.add_argument('--dry-run', action='store_true', help='List matching media without classifying.')

    def handle(self, *args, **options):
        fill_missing_metadata = options['fill_missing_metadata']
        self._check_prerequisites(fill_missing_metadata)
        queryset = self._build_queryset(options)
        media_ids = list(queryset.values_list('id', flat=True))
        self.stdout.write(f"Matched {len(media_ids)} media for theme classification.")

        if options['dry_run']:
            self.stdout.write(', '.join(map(str, media_ids)) or 'Nothing to classify.')
            if fill_missing_metadata:
                self._report_missing_metadata(media_ids)
            return

        if options['sync']:
            self._run_sync(media_ids, fill_missing_metadata)
        else:
            self._enqueue(media_ids, options['interval'], fill_missing_metadata)

    def _report_missing_metadata(self, media_ids):
        missing = {media.id: find_missing_metadata(media) for media in Media.objects.filter(id__in=media_ids)}
        incomplete = [media_id for media_id in media_ids if missing.get(media_id)]
        fields = Counter(field for media_id in incomplete for field in missing[media_id])
        self.stdout.write(
            f"{len(incomplete)} need extraction first (missing: {dict(fields) or 'none'}); "
            f"{len(media_ids) - len(incomplete)} have their metadata and get the theme only."
        )
        if incomplete:
            self.stdout.write(f"Need extraction: {', '.join(map(str, incomplete))}")

    def _check_prerequisites(self, fill_missing_metadata=False):
        if fill_missing_metadata and not get_company_bot(DOC_TEXT_EXTRACTOR_ROUTE, None):
            raise CommandError(f'Document extractor bot (route {DOC_TEXT_EXTRACTOR_ROUTE}) not found.')
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
        queryset = Media.objects.order_by(*NEWEST_FIRST)

        if options['media_ids'] is not None:
            try:
                ids = [int(value) for value in options['media_ids'].split(',') if value.strip()]
            except ValueError:
                raise CommandError('--media-ids must be a comma-separated list of integers.') from None
            if not ids:
                # An empty list would otherwise mean "no ID filter" and match every media.
                raise CommandError('--media-ids was given but contains no IDs.')
            queryset = queryset.filter(id__in=ids)
        if options['company_slug']:
            queryset = queryset.filter(company_bot__company__slug=options['company_slug'])
        if options['subdocuments_only']:
            queryset = queryset.filter(parent__isnull=False)
        elif options['top_level_only']:
            queryset = queryset.filter(parent__isnull=True)
        if not options['all']:
            queryset = queryset.filter(primary_theme__isnull=True, needs_review=False)
        if options['limit']:
            queryset = queryset[:options['limit']]
        return queryset

    def _enqueue(self, media_ids, interval, fill_missing_metadata):
        for index, media_id in enumerate(media_ids):
            classify_media_themes.apply_async(
                args=(media_id,), kwargs={'fill_missing_metadata': fill_missing_metadata}, countdown=index * interval
            )
        self.stdout.write(self.style.SUCCESS(
            f"Queued {len(media_ids)} classification tasks over ~{int(len(media_ids) * interval)}s."
        ))

    def _run_sync(self, media_ids, fill_missing_metadata):
        statuses = Counter()
        filled_count = 0
        for media in Media.objects.select_related('company_bot__company').filter(id__in=media_ids).order_by(*NEWEST_FIRST):
            try:
                outcome = MediaThemeClassificationService(media, fill_missing_metadata=fill_missing_metadata).run()
            except Exception as e:
                self.stderr.write(f"media_id={media.id} failed: {e}")
                statuses['failed'] += 1
                continue
            statuses[outcome.status] += 1
            filled_count += bool(outcome.metadata_filled)
            filled = f" filled={','.join(outcome.metadata_filled)}" if outcome.metadata_filled else ''
            self.stdout.write(f"media_id={media.id} status={outcome.status} primary={outcome.primary_theme}{filled}")
        summary = f"Done: {dict(statuses)}"
        if fill_missing_metadata:
            summary += f"; metadata filled for {filled_count}"
        self.stdout.write(self.style.SUCCESS(summary))


if __name__ == '__main__':
    Command().run_from_argv([sys.argv[0], ''] + sys.argv[1:])
