import json
import os
import sys
from pathlib import Path

import django

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
    django.setup()

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from chatbot.models import Company, CompanyBot

REPO_ROOT = Path(__file__).resolve().parents[3]
BOT_FILES = ('setup/ThemeClassifierBot.json', 'setup/SecondaryThemeGeneratorBot.json')
INLINE_KEYS = ('voices', 'state_machines', 'bot_vernaculars')


class Command(BaseCommand):
    help = 'Create or update the Theme Classifier and Secondary Theme Generator bots from their setup/ JSON files.'

    def add_arguments(self, parser):
        parser.add_argument('--company-slug', type=str,
                            help="Import the bots under this company instead of the company_slug in the JSON files.")

    def handle(self, *args, **options):
        with transaction.atomic():
            for path in BOT_FILES:
                for data in json.loads((REPO_ROOT / path).read_text()):
                    self._import_bot(data, options['company_slug'])

    def _import_bot(self, data, company_slug):
        json_slug = data.pop('company_slug', None)
        slug = company_slug or json_slug
        company = Company.objects.filter(slug=slug).first()
        if not company:
            raise CommandError(f"Company {slug!r} not found. Pass --company-slug with an existing company slug.")
        for key in INLINE_KEYS:
            data.pop(key, None)

        bot, created = CompanyBot.objects.update_or_create(route=data['route'], company=company, defaults=data)
        self.stdout.write(f"{'created' if created else 'updated'} {bot.route} {company.slug}")


if __name__ == '__main__':
    Command().run_from_argv([sys.argv[0], ''] + sys.argv[1:])
