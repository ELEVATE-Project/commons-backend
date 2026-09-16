# Django Models

`chatbot/models/`

This layer defines the complete database schema for the chatbot platform.

It manages persistence, relationships, constraints, indexing, and domain-level behavior across users, bots, conversations, content, media, and configuration.

---

Responsibilities of this Layer

- Define core domain entities (User, Bot, Story, Media, etc.)
- Maintain relational integrity using ForeignKeys and constraints
- Enforce validation rules and uniqueness constraints
- Store multilingual and vernacular content
- Manage conversation state and session tracking
- Support knowledge base document storage and vector indexing
- Enable tagging and categorization
- Maintain historical tracking using `simple_history`
- Provide model-level helper methods for business logic
- Use enums for consistent state definitions

---

## 1. BlacklistedToken

`chatbot/models/auth_models.py`

### Purpose

Stores authentication tokens that have been invalidated or revoked.
    Used to prevent blacklisted tokens from being reused.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| token | TextField (unique=True, required) |  |
| blacklisted_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_blacklisted_at()`
- `get_previous_by_blacklisted_at()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 2. BotVernacular

`chatbot/models/bot_vernacular_model.py`

### Purpose

Stores language-specific (vernacular) configurations for a company bot.
    Allows customized introductory and error messages per language.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| company_bot | ForeignKey (ForeignKey → CompanyBot) |  |
| language | CharField (required, max_length=250) | Language code, Example for English use en. |
| introductory_message | TextField () | Provide an introductory message that the bot will present when the conversation starts. |
| alt_introductory_message | TextField () | Provide an alternate introductory message that the bot will present when the conversation starts. |
| name | CharField (max_length=100) | Enter the name of the bot. |
| error_message | TextField () | Provide an error message that the bot will display. |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 3. ChatSession

`chatbot/models/chat_models.py`

### Purpose

Represents an active chat session between a user profile and a company bot.
    Stores session metadata, conversation state, and handles title generation using LLMs.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| session | CharField (unique=True, required, max_length=255) |  |
| profile | ForeignKey (ForeignKey → Profile) |  |
| company_bot | ForeignKey (ForeignKey → CompanyBot) |  |
| language | CharField (required, max_length=1000, choices) |  |
| title | CharField (max_length=255) |  |
| summary | TextField () |  |
| current_step | IntegerField () |  |
| session_context | JSONField () |  |
| session_status | CharField (max_length=20, choices) |  |
| project_id | CharField (max_length=400) |  |
| user_id | CharField (max_length=400) |  |
| session_type | CharField (max_length=100, choices) |  |
| other_params | JSONField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_language_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_session_status_display()`
- `get_session_type_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_title()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 4. Company

`chatbot/models/company_models.py`

### Purpose

Represents a company that owns and manages chatbot configurations.
    Stores company details like name, slug, status, and logo.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| name | CharField (required, max_length=100) |  |
| slug | CharField (unique=True, required, max_length=100) |  |
| status | CharField (required, max_length=20, choices) |  |
| url | URLField (max_length=200) |  |
| logo | ImageField (max_length=1000) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_file_upload_path()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_public_url()`
- `get_status_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 5. CompanyBot

`chatbot/models/company_models.py`

### Purpose

Defines a chatbot configuration for a specific company.
    Stores LLM settings, prompts, provider details, and behavior controls.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| name | CharField (required, max_length=100) | Enter the name of the bot. |
| company | ForeignKey (required, ForeignKey → Company) | Select the company this bot belongs to. |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| context | TextField (required) | Provide the bot's main prompt or description of its purpose. |
| max_token | IntegerField (required) |  |
| bot_temperature | FloatField (required) | Set the temperature for controlling response randomness (0-1). Lower values produce more deterministic responses. |
| top_k | IntegerField (required) | Set the top-k value for the bot's response selection. This defines how many top options to consider for each response. |
| provider | CharField (required, max_length=100, choices) | Select the LLM provider (BEDROCK, BEDROCK_CONVERSE, or OPENAI) |
| provider_keys | TextField (required, max_length=1000) | API keys or credentials for the selected LLM provider. |
| llm_model | CharField (required, max_length=100, choices) | Select the LLM model to be used by the bot (e.g., GPT-4o, GPT-4). |
| filter_score | FloatField (required) | Set the filter score for bot response selection (0-1). Responses below this score will be filtered out. |
| end_context | TextField () | Provide additional prompt or context to append at the end of the main prompt to guide the conversation |
| introductory_message | CharField (max_length=1000) | Provide an introductory message that the bot will present when the conversation starts. |
| tag_context | TextField () | Provide any information or context related to variables (like Python-bound variables) that will be inserted into the prompt. |
| route | CharField (required, max_length=100) | Specify the route or API endpoint for interacting with the bot. |
| bot_type | CharField (required, max_length=30, choices) |  |
| llm_key | CharField (max_length=255) |  |
| dynamic_context | TextField () | Provide dynamic context that can be adjusted during the bot's interactions, such as personalized data. |
| dynamic_context_type | CharField (max_length=20, choices) |  |
| pre_context | TextField () | Provide pre-context that will be set before the main prompt to shape the conversation. |
| tool_context | TextField () |  |
| other_params | JSONField () |  |
| connect_timeout | FloatField (required) | Timeout in seconds for establishing a LLM connection. |
| read_timeout | FloatField (required) | Timeout in seconds for reading a LLM response. |
| chat_history_limit | IntegerField (required) | Controls how many of the most recent chat messages are included as conversation history when making an LLM request. |
| stream | BooleanField (required) | Enable streaming mode for LLM responses. |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_bot_type_display()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_dynamic_context_type_display()`
- `get_file_upload_path()`
- `get_llm_model_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_provider_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 6. CompanyChat

`chatbot/models/company_models.py`

### Purpose

Represents a chat message exchanged between a user and a company bot.
    Stores message content, session data, metadata, and optional attachments.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| message | TextField (required) |  |
| translated_message | TextField () |  |
| chunks | TextField () |  |
| sender | ForeignKey (ForeignKey → Profile) |  |
| receiver | ForeignKey (ForeignKey → Profile) |  |
| session | CharField (required, max_length=255) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| status | CharField (max_length=20, choices) |  |
| feedback | CharField (max_length=20, choices) |  |
| source | CharField (required, max_length=20, choices) |  |
| source_msg_id | CharField (max_length=256) |  |
| whatsapp_message_id | CharField (max_length=255) |  |
| message_type | CharField (max_length=20) |  |
| stage | CharField (max_length=500) |  |
| other_params | JSONField () |  |
| audio_file | FileField (max_length=1000) |  |
| file_url | CharField (max_length=2000) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_feedback_display()`
- `get_file_upload_path()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_source_display()`
- `get_status_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 7. CompanyStateMachine

`chatbot/models/company_models.py`

### Purpose

Represents a step in a structured conversational workflow for a company bot.
    Defines stage logic, prompts, and optional pre/post processing rules.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| company_bot | ForeignKey (required, ForeignKey → CompanyBot) |  |
| name | CharField (required, max_length=100) | Enter the name of the state. |
| step | IntegerField (required) | Integer representing the order in which state function calling happens. Lower values are called first. |
| use_stage_chats | BooleanField (required) | If True, only chats from this stage will be included and passed to the LLM. |
| type | CharField (required, max_length=10, choices) | Specify whether the state is mandatory or optional. |
| text_conversion_type | CharField (required, max_length=15, choices) | Choose how to process this field's text: 'Translation' converts meaning into another language, 'Transliteration' preserves sound using another script. |
| bot_question | TextField () | Provide the first question that the bot will ask when the state is triggered. |
| completion_criteria | TextField () | Define the criteria required to move from this state to the next state. |
| context | TextField () | Provide the main prompt or description of the state, explaining its purpose. |
| tool_context | TextField () |  |
| preprocess_type | CharField (required, max_length=10, choices) | Choose how this stage should be preprocessed: 'Simple Prompt' lets you define a direct prompt, 'Use Preprocess Bot' lets you select a separate bot to handle complex logic. |
| preprocess_prompt | TextField () | Define the skip logic prompt if Preprocess Type is SIMPLE.  |
| preprocess_bot | ForeignKey (ForeignKey → CompanyBot) | Select which Bot to use for preprocessing for complex logic. |
| preprocess_output_mode | CharField (required, max_length=10, choices) | Define how to use the preprocess output: 'Skip' means use output to decide if stage should be skipped; 'Enrich' means use output in this stage's prompt; 'Custom' means run custom logic on the output. |
| postprocess_type | CharField (required, max_length=10, choices) | Choose how this stage should be postprocessed: 'Simple Prompt' lets you define a direct prompt, 'Use Postprocess Bot' lets you select a separate bot to handle complex logic. |
| postprocess_prompt | TextField () | Define the postprocess prompt if Postprocess Type is SIMPLE. |
| postprocess_bot | ForeignKey (ForeignKey → CompanyBot) | Select which Bot to use for postprocessing for complex logic. |
| postprocess_output_mode | CharField (required, max_length=10, choices) | Define how to use the postprocess output. |
| skip_to_step | IntegerField () | If set, the flow will skip directly to this step number when skip conditions are met. |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_postprocess_output_mode_display()`
- `get_postprocess_type_display()`
- `get_preprocess_output_mode_display()`
- `get_preprocess_type_display()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_text_conversion_type_display()`
- `get_type_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 8. KeyValue

`chatbot/models/media_models.py`

### Purpose

Stores structured key-value metadata associated with a Media document.
    Used for tagging or storing extracted attributes.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| media | ForeignKey (required, ForeignKey → Media) |  |
| key | CharField (required, max_length=1000) |  |
| value | TextField () |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 9. Media

`chatbot/models/media_models.py`

### Purpose

Represents knowledge/media files linked to a company bot.
    Handles storage, preview generation, vector indexing, and similarity search.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| name | CharField (required, max_length=1000) |  |
| organization | ForeignKey (ForeignKey → Company) |  |
| url | URLField (max_length=1000) |  |
| priority | CharField (required, max_length=50, choices) |  |
| media_type | CharField (required, max_length=100, choices) |  |
| company_bot | ForeignKey (required, ForeignKey → CompanyBot) |  |
| file | FileField (required, max_length=1000) |  |
| markdown_file | FileField (max_length=1000) |  |
| description | TextField () |  |
| extracted_text | TextField () |  |
| external_file_id | CharField (max_length=300) | External provider file identifier used for vector indexing (e.g. OpenAI Files API file_id) |
| parent | ForeignKey (ForeignKey → Media) |  |
| display_mode | CharField (required, max_length=20, choices) |  |
| view_count | PositiveBigIntegerField (required) |  |
| download_count | PositiveBigIntegerField (required) |  |
| thumbnail | ImageField (max_length=1000) | Auto-generated preview thumbnail |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| tags | ManyToManyField (required, ManyToMany → Tag) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `find_trigram_similar()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_display_mode_display()`
- `get_file_upload_path()`
- `get_media_type_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_priority_display()`
- `get_s3_url()`
- `get_thumbnail_s3_url()`
- `get_thumbnail_upload_path()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 10. MediaImage

`chatbot/models/media_models.py`

### Purpose

Stores images extracted or associated with a Media document.
    Maintains ordering and metadata like page number and dimensions.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| name | CharField (required, max_length=1000) |  |
| file | FileField (max_length=1000) |  |
| media | ForeignKey (required, ForeignKey → Media) |  |
| page | IntegerField () |  |
| index | IntegerField (required) |  |
| width | IntegerField () |  |
| height | IntegerField () |  |
| media_type | CharField (max_length=100, choices) |  |
| base64_str | TextField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_file_upload_path()`
- `get_media_type_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 11. MediaTemplate

`chatbot/models/media_models.py`

### Purpose

Defines reusable templates for processing or rendering Media content.
    Supports different template types and PDF handling strategies.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| name | CharField (unique=True, max_length=100) |  |
| template_content | TextField () |  |
| template_type | CharField (max_length=100, choices) |  |
| pdf_strategy | CharField (max_length=100, choices) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_pdf_strategy_display()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_template_type_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 12. MediaVector

`chatbot/models/media_models.py`

### Purpose

Stores vector database reference IDs for a Media document.
    Used for semantic search and embedding-based retrieval.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| media | ForeignKey (required, ForeignKey → Media) |  |
| vector_id | CharField (max_length=1000) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 13. Profile

`chatbot/models/profile_models.py`

### Purpose

Represents a user profile associated with a company.
    Stores personal details, authentication data, and metadata for chatbot interactions.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| first_name | CharField (max_length=100) |  |
| userid | CharField (max_length=200) |  |
| last_name | CharField (max_length=100) |  |
| email | EmailField (required, max_length=1000) |  |
| phone | CharField (max_length=20) |  |
| alternate_phone | CharField (max_length=20) |  |
| country | CharField (max_length=100) |  |
| status | CharField (required, max_length=20, choices) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| company | ForeignKey (required, ForeignKey → Company) |  |
| password | CharField (max_length=1000) |  |
| profile_type | CharField (required, max_length=20, choices) |  |
| profile_code | CharField (max_length=100) |  |
| location | CharField (max_length=1000) |  |
| caste | CharField (max_length=1000) |  |
| gender | CharField (max_length=1000, choices) |  |
| designation | TextField () |  |
| org_associated | CharField (max_length=1000) |  |
| product_interested | CharField (max_length=1000) |  |
| company_spoc | CharField (max_length=1000) |  |
| other_params | JSONField () |  |
| source | CharField (max_length=1000) |  |
| preferred_route | CharField (max_length=1000) |  |
| latest_flow_used | CharField (max_length=500, choices) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_file_upload_path()`
- `get_gender_display()`
- `get_latest_flow_used_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_profile_type_display()`
- `get_status_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 14. ProfileAddress

`chatbot/models/geo_models.py`

### Purpose

Stores address and geolocation details associated with a user profile.
    Includes full address fields along with optional latitude and longitude.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| profile | ForeignKey (required, ForeignKey → Profile) |  |
| address_line_1 | CharField (max_length=1000) |  |
| address_line_2 | CharField (max_length=1000) |  |
| block | CharField (max_length=1000) |  |
| city | CharField (max_length=1000) |  |
| district | CharField (max_length=1000) |  |
| state | CharField (max_length=1000) |  |
| country | CharField (max_length=1000) |  |
| pincode | CharField (max_length=10) |  |
| latitude | DecimalField () |  |
| longitude | DecimalField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 15. ProfileMedia

`chatbot/models/media_models.py`

### Purpose

Stores media files uploaded by a user profile.
    Encodes files to base64 and provides public S3 access.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| profile | ForeignKey (required, ForeignKey → Profile) |  |
| file | FileField (required, max_length=1000) |  |
| base64_str | TextField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_file_upload_path()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_public_url()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 16. Story

`chatbot/models/story_models.py`

### Purpose

Represents a story created by a user or AI within a chat session.
    Stores content, metadata, language, status, and translation support.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| title | CharField (required, max_length=1000) |  |
| author | ForeignKey (ForeignKey → Profile) |  |
| content | TextField () |  |
| blurb | TextField () |  |
| tweet | TextField () |  |
| session | CharField (unique=True, required, max_length=255) |  |
| objective | TextField () |  |
| action_steps | TextField () |  |
| impact | TextField () |  |
| micro_improvement | TextField () |  |
| location | CharField (max_length=1000) |  |
| district | CharField (max_length=1000) |  |
| state | CharField (max_length=1000) |  |
| block | CharField (max_length=1000) |  |
| formatted_content | TextField () |  |
| language | CharField (required, max_length=1000, choices) |  |
| source | CharField (required, max_length=1000, choices) |  |
| story_code | CharField (max_length=100) |  |
| stage | CharField (required, max_length=100, choices) |  |
| summary | TextField () |  |
| other_params | JSONField () |  |
| client_created_at | DateTimeField () |  |
| client_updated_at | DateTimeField () |  |
| validation_logs | TextField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_available_languages()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_language_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_source_display()`
- `get_stage_display()`
- `get_translation()`
- `get_translation_languages()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 17. StoryMedia

`chatbot/models/story_models.py`

### Purpose

Stores media files associated with a story.
    Handles file uploads, format conversion, and base64 encoding.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| name | CharField (required, max_length=1000) |  |
| file | FileField (max_length=1000) |  |
| story | ForeignKey (required, ForeignKey → Story) |  |
| include_in_story | BooleanField (required) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| base64_str | TextField () |  |
| source_path | TextField () |  |
| media_type | CharField (max_length=100, choices) |  |
| file_url | CharField (max_length=2000) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_file_upload_path()`
- `get_media_type_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_public_url()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 18. StoryTag

`chatbot/models/story_models.py`

### Purpose

Maps tags to stories with optional primary tag designation.
    Ensures a story cannot have duplicate tags.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| story | ForeignKey (required, ForeignKey → Story) |  |
| tag | ForeignKey (required, ForeignKey → Tag) |  |
| is_primary | BooleanField (required) |  |
| created_by | ForeignKey (ForeignKey → Profile) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 19. StoryTranslation

`chatbot/models/story_models.py`

### Purpose

Stores translated versions of a story in different languages.
    Maintains localized content while linking to the original story.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| story | ForeignKey (required, ForeignKey → Story) |  |
| language | CharField (required, max_length=10, choices) |  |
| title | CharField (required, max_length=1000) |  |
| content | TextField () |  |
| blurb | TextField () |  |
| tweet | TextField () |  |
| objective | TextField () |  |
| action_steps | TextField () |  |
| impact | TextField () |  |
| micro_improvement | TextField () |  |
| formatted_content | TextField () |  |
| location | CharField (max_length=1000) |  |
| district | CharField (max_length=1000) |  |
| state | CharField (max_length=1000) |  |
| block | CharField (max_length=1000) |  |
| other_params | JSONField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_language_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 20. StoryVernacular

`chatbot/models/story_vernacular_model.py`

### Purpose

Stores language-specific translations for story-related bot content.
    Links a company bot to translated JSON text for a given language.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| company_bot | ForeignKey (ForeignKey → CompanyBot) |  |
| translation_json | JSONField () | JSON object containing translated text in the specified language. |
| language | CharField (required, max_length=250) | Language code, Example for English use en. |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 21. Tag

`chatbot/models/story_models.py`

### Purpose

Represents a reusable tag used to categorize stories.
    Can be company-specific and linked to a creator profile.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| name | CharField (unique=True, required, max_length=1000) |  |
| status | CharField (required, max_length=100, choices) |  |
| company | ForeignKey (ForeignKey → Company) |  |
| source_type | CharField (max_length=50, choices) |  |
| description | TextField () |  |
| created_by | ForeignKey (ForeignKey → Profile) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_source_type_display()`
- `get_status_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 22. Theme

`chatbot/models/theme_models.py`

### Purpose

Stores theme configurations associated with a company bot.
    Supports custom story themes or inheritance from a master theme.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| bot | ForeignKey (required, ForeignKey → CompanyBot) | Select the bot this theme belongs to. |
| themes | JSONField (required) | Store a list of themes associated with this bot. |
| theme_type | CharField (required, max_length=10, choices) | Indicates if this theme is custom or uses a master theme. |
| master_theme | ForeignKey (ForeignKey → Theme) | If using a master theme, select the theme to inherit from. |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_theme_type_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 23. Voice

`chatbot/models/company_models.py`

### Purpose

Defines a text-to-speech voice configuration for a company bot.
    Stores provider details, language, gender, and playback settings.

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| company_bot | ForeignKey (ForeignKey → CompanyBot) |  |
| type | CharField (max_length=300, choices) |  |
| provider | CharField (max_length=300, choices) |  |
| name | CharField (max_length=100) |  |
| sample_link | URLField (max_length=200) |  |
| language | CharField (max_length=100) |  |
| provider_code | CharField (max_length=100) |  |
| gender | CharField (required, max_length=100, choices) |  |
| voice_speed | FloatField () |  |
| other_params | JSONField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |

### Methods

- `DoesNotExist()`
- `MultipleObjectsReturned()`
- `adelete()`
- `arefresh_from_db()`
- `asave()`
- `check()`
- `clean()`
- `clean_fields()`
- `date_error_message()`
- `from_db()`
- `full_clean()`
- `get_constraints()`
- `get_deferred_fields()`
- `get_gender_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_provider_display()`
- `get_type_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---
