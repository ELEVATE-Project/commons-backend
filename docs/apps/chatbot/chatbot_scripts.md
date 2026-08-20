# Chatbot Scripts

## Overview

This documents utility scripts located in the `chatbot/scripts/` directory that support various maintenance, data processing, and extraction workflows.

## Key Scripts

- `generate_models_docs.py`: Generates documentation for data models.
- `sync_media_to_vector_db.py`: Synchronizes media assets to a vector database for search capabilities.
- `qdrant_sanity_check.py`: Performs integrity checks on Qdrant vector database.
- `theme_extraction.py` and `theme_extraction_in_file.py`: Extract thematic data from input sources.
- `ai_search/create_ai_search_bot.py`: Seeds the `CompanyBot` row holding the AI search filter prompt and tool schema. Optional — only needed when AI Search is enabled. Idempotent; pass `--force` to overwrite an edited prompt.

## Usage

These scripts serve as development, migration, and data management tools complementing runtime chatbot functionalities.
They can be executed standalone to perform targeted operations required by the application lifecycle.
