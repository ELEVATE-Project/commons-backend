# Large Language Model (LLM) Integration

## Overview

The LLM module integrates various large language models into the chatbot system, providing advanced conversational capabilities and story generation.

## Location

Located in the `chatbot/llm_models/` directory, the integration includes:

- `llm_script.py`: Implements core logic for interacting with different LLM providers and managing prompt orchestration.

## Supported LLM Providers and Features

The chatbot currently supports multiple LLM providers, each enabling different features:

### AWS Bedrock

The Bedrock LLM integration is mainly implemented via the `handle_bedrock_model` function in `llm_script.py`.

- **Purpose:** Sends conversation prompts to the AWS Bedrock Converse model endpoint and processes the response.
- **Parameters:**
  - `messages`: Chat messages and history.
  - `max_token`: Max tokens to generate.
  - `model_name`: Model identifier.
  - `is_json_format`: Whether to expect JSON response.
  - `temperature`, `top_p`, `seed`, `n`, `stream`: Controls sampling and streaming.
  - `url_to_use`: Optional override of endpoint URL.
- **Output:** Returns parsed JSON content when expecting JSON or raw string otherwise. Handles retries and exceptions internally.

### OpenAI GPT

The OpenAI integration is mainly implemented via the `handle_openai_response_api` function in `llm_script.py`.

- **Purpose:** Manages sending prompts and options to OpenAI API and processing the response.
- **Parameters:**
  - `messages`: List of chat messages starting with system prompt.
  - `max_token`: Limits max tokens in generated completion.
  - `temperature`: Sampling temperature controlling creativity.
  - `company_bot`: Optional company bot context.
  - `model_name`: Model to use, falls back to company bot's model or default.
  - `is_json_response`: If true, parses the completion as JSON.
  - `stream`: Enables streaming output.
  - `key_name`, `is_actual_key`, `client_choice`: Control API key and client instance.
  - `tools`, `tool_choice`: Controls tool integrations.
  - `top_p`: Controls nucleus sampling parameter.
  - `system_prompt`: Prepended system instructions.
- **Output:**
  - For non-stream, returns parsed JSON or string content of completion.
  - For stream, yields or returns streaming partial responses (depending on client implementation).
  - Raises exceptions on errors to be handled by caller.

This design enables flexible and powerful LLM interactions with detailed prompt and response control tailored to provider APIs.
