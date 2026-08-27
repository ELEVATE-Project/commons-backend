# Chatbot Scripts

## Overview

This documents utility scripts located in the `chatbot/scripts/` directory that support various maintenance, data processing, and extraction workflows.

## Key Scripts

- `generate_models_docs.py`: Generates documentation for data models.
- `sync_media_to_vector_db.py`: Synchronizes media assets to a vector database for search capabilities.
- `qdrant_sanity_check.py`: Performs integrity checks on Qdrant vector database.
- `theme_extraction.py` and `theme_extraction_in_file.py`: Extract thematic data from input sources.
- `ai_search/create_ai_search_bot.py`: Seeds the AI search filter prompt and tool schema onto the `CompanyBot` at `/ai_search_filters` (override with `AI_SEARCH_BOT_ROUTE`), creating the row if it does not exist. Optional — only needed when AI Search is enabled. Also seeds every AI-search knob into `other_params` at its currently effective value, so the settings are visible and editable in the admin instead of having to be typed from memory. Merges: a key already present is never overwritten, not even by `--force`, so admin tuning survives. Never writes `filter_score` or the name of a row that already exists. Idempotent; `--force` re-syncs the prompt and tool schema only. Refuses to run against `/sg_search_bot` — that is the separate, older search bot whose `filter_score` tunes the vector query.

## Usage

These scripts serve as development, migration, and data management tools complementing runtime chatbot functionalities.
They can be executed standalone to perform targeted operations required by the application lifecycle.
