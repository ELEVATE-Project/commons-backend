# Release 1.2.0 — Deployment Guide

## 1. Add this key to .env

SECONDARY_THEME_COUNT = 2 // is the maximum number of secondary themes per document(up to 10).
## 2. Add the primary predefined themes into the DB:
.venv/bin/python manage.py migrate

## 3. Import the themes bots
  .venv/bin/python manage.py shell -c "
import json
from chatbot.models import Company, CompanyBot
for path in ['setup/ThemeClassifierBot.json', 'setup/SecondaryThemeGeneratorBot.json']:
    for data in json.load(open(path)):
        company = Company.objects.get(slug=data.pop('company_slug'))
        for key in ('voices', 'state_machines', 'bot_vernaculars'):
            data.pop(key, None)
        bot, created = CompanyBot.objects.update_or_create(route=data['route'], company=company, defaults=data)
        print('created' if created else 'updated', bot.route, bot.company.slug) "

## 4. Restart uvicorn and the Celery worker.
Restart the app and upload a file in the app. Themes are mapped to it automatically:
Classification runs as a Celery task a few seconds after the upload, so the worker must be running.
When you upload through admin, the page waits for the result and shows a message with the assigned theme.


## 5. Run these from the project root, after the migration and the bot import.

.venv/bin/python chatbot/scripts/themes/classify_media_themes.py --limit 5 --sync

You can change the n number of limit

**Important:** : If you run the command again with the same --limit, it continues from where the previous run stopped: it skips files that already have a theme and maps the next set of unmapped files.

## 6.Map all the remaining files :

.venv/bin/python chatbot/scripts/themes/classify_media_themes.py


