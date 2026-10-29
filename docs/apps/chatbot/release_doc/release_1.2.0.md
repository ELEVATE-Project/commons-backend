# Release 1.2.0 — Deployment Guide

## 1. Add these keys to .env

SECONDARY_THEME_COUNT = 2 // is the maximum number of secondary themes per document(up to 10).

Switch the AI Search LLM to Luna. These replace the `AI_SERVICE_PROVIDER` and `AI_SERVICE_MODEL` values set in release 1.1.0:

AI_SERVICE_PROVIDER=openrouter
AI_SERVICE_MODEL=openai/gpt-6-luna

## 2. Add the primary predefined themes into the DB:
.venv/bin/python manage.py migrate

## 3. Import the themes bots
.venv/bin/python chatbot/scripts/themes/import_theme_bots.py

The bots are imported under the `shikshalokamstaging` company. If that company does not exist in this environment, pass an existing one:

.venv/bin/python chatbot/scripts/themes/import_theme_bots.py --company-slug <company-slug>

## 4. Re-seed the AI Search Filter bot
.venv/bin/python chatbot/scripts/ai_search/create_ai_search_bot.py --force

`--force` rewrites the stored prompt and tool schema, which now include the theme filter keys. Values set in admin under `other_params` are kept.

## 5. Restart uvicorn and the Celery worker.
Restart the app and upload a file in the app. Themes are mapped to it automatically:
Classification runs as a Celery task a few seconds after the upload, so the worker must be running.
When you upload through admin, the page waits for the result and shows a message with the assigned theme.


## 6. Run these from the project root, after the migration and the bot import.

.venv/bin/python chatbot/scripts/themes/classify_media_themes.py --limit 5 --sync

You can change the n number of limit

**Important:** : If you run the command again with the same --limit, it continues from where the previous run stopped: it skips files that already have a theme and maps the next set of unmapped files.

## 7.Map all the remaining files :

.venv/bin/python chatbot/scripts/themes/classify_media_themes.py


