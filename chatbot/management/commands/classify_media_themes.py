from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from chatbot.celery_tasks.knowledge_service.theme_tasks import classify_media_themes
from chatbot.models import Media
from chatbot.utils.knowledge_service.processor.theme_classifier import SecondaryThemeSettings, load_json_field
from chatbot.utils.knowledge_service.theme_classification_service import (
    MediaThemeClassificationService, get_company_bot, get_theme_classifier_bot, load_theme_options
)


class Command(BaseCommand):
    help = 'Classify primary and secondary themes for existing media files using the Theme Classifier bot.'

    def add_arguments(self, parser):
        parser.add_argument('--media-ids', type=str, help='Comma-separated Media IDs to classify.')
        parser.add_argument('--company-slug', type=str, help='Only classify media owned by this company.')
        parser.add_argument('--all', action='store_true',
                            help='Reclassify every matching media, including already classified ones.')
        parser.add_argument('--include-subdocuments', action='store_true',
                            help='Also classify subdocuments (media with a parent).')
        parser.add_argument('--limit', type=int, help='Maximum number of media to process.')
        parser.add_argument('--interval', type=float, default=2.0,
                            help='Seconds between queued task start times, to avoid LLM throttling (default: 2.0).')
        parser.add_argument('--sync', action='store_true',
                            help='Run classification in this process instead of queueing Celery tasks.')
        parser.add_argument('--dry-run', action='store_true', help='List matching media without classifying.')

    def handle(self, *args, **options):
        self._check_prerequisites()
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
        queryset = Media.objects.order_by('id')

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
        if not options['all']:
            queryset = queryset.filter(primary_theme__isnull=True, needs_review=False)
        if options['limit']:
            queryset = queryset[:options['limit']]
        return queryset

    def _enqueue(self, media_ids, interval):
        for index, media_id in enumerate(media_ids):
            classify_media_themes.apply_async(args=(media_id,), countdown=index * interval)
        self.stdout.write(self.style.SUCCESS(
            f"Queued {len(media_ids)} classification tasks over ~{int(len(media_ids) * interval)}s."
        ))

    def _run_sync(self, media_ids):
        statuses = Counter()
        for media in Media.objects.select_related('company_bot__company').filter(id__in=media_ids).order_by('id'):
            try:
                outcome = MediaThemeClassificationService(media).run()
            except Exception as e:
                self.stderr.write(f"media_id={media.id} failed: {e}")
                statuses['failed'] += 1
                continue
            statuses[outcome.status] += 1
            self.stdout.write(f"media_id={media.id} status={outcome.status} primary={outcome.primary_theme}")
        self.stdout.write(self.style.SUCCESS(f"Done: {dict(statuses)}"))
