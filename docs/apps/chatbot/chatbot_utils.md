# Chatbot Utilities

## Overview

The utilities module contains many helper functions and classes that support various chatbot operations ranging from audio processing, translation, data handling, to LLM integrations.

## Key Utility Files and Functions

- `chat_utils.py`: Utilities related to chatbot message processing and guided chat generation.
- `one_shot_utils.py`: Helpers for managing one-shot bot stages and interactions.
- `audio_provider_utils.py`: Functions for handling audio provider integrations including text-to-text translation.
- `transliterate_utils.py`: Supports text transliteration used in chat translations.
- `profile_utils.py`: Helpers to deal with user profile data extraction and formatting.
- `llm.py`: Instruments interactions with Large Language Model providers.

## Additional Utilities

- Tools for working with specific bot flows (e.g., `bedrock_tool_call.py`, `chaupal_tool_call.py`, `oneshot_guest_tool_call.py`).
- Converters for audio and image processing.
- Utilities for database access, environment parsing, Kafka messaging, and story recreation.

## Usage

- These utilities are imported and used strategically across services, consumers, and celery tasks for streamlined logic and code reuse.

---
