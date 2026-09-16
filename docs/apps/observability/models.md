# Django Models

`observability/models/`

This layer defines the complete database schema for the `observability` application.

It manages persistence, relationships, constraints, indexing, and domain-level behavior across domain entities and system configuration.

---

## Responsibilities of this Layer

- Define core domain entities
- Maintain relational integrity using ForeignKeys and constraints
- Enforce validation rules and uniqueness constraints
- Manage state and lifecycle tracking
- Support indexing and optimized querying
- Provide model-level helper methods for business logic
- Use enums for consistent state definitions

---

## 1. BotRunTestCaseMap

`observability/models/base_models.py`

### Purpose

BotRunTestCaseMap(id, bot_run, test_case, metric_name, score, reason, status, response_log, created_at, updated_at)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| bot_run | ForeignKey (required, ForeignKey → CompanyBotTCRun) |  |
| test_case | ForeignKey (required, ForeignKey → CompanyBotTestCases) |  |
| metric_name | CharField (required, max_length=100, choices) |  |
| score | FloatField () |  |
| reason | TextField () |  |
| status | CharField (max_length=100, choices) |  |
| response_log | TextField () |  |
| created_at | DateTimeField () |  |
| updated_at | DateTimeField () |  |

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
- `get_metric_name_display()`
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

## 2. CompanyBotTCRun

`observability/models/base_models.py`

### Purpose

CompanyBotTCRun(id, created_at, updated_at, company_bot, llm_model, provider, status, metrics_result)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| company_bot | ForeignKey (required, ForeignKey → CompanyBot) |  |
| llm_model | CharField (required, max_length=100, choices) |  |
| provider | CharField (required, max_length=100, choices) |  |
| status | CharField (required, max_length=100, choices) |  |
| metrics_result | TextField () |  |

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
- `get_llm_model_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_provider_display()`
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

## 3. CompanyBotTestCases

`observability/models/base_models.py`

### Purpose

CompanyBotTestCases(id, about, company_bot, testcase_input, expected_output, chat_session, message, retrieval_context, input_format, json_output_schema, created_at, updated_at)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| about | TextField () | Optional description of the test case. For informational purposes only; it does not affect the test output. |
| company_bot | ForeignKey (ForeignKey → CompanyBot) |  |
| testcase_input | TextField () |  |
| expected_output | TextField (required) |  |
| chat_session | ForeignKey (ForeignKey → ChatSession) |  |
| message | TextField () |  |
| retrieval_context | TextField () |  |
| input_format | CharField (required, max_length=100, choices) |  |
| json_output_schema | TextField () |  |
| created_at | DateTimeField () |  |
| updated_at | DateTimeField () |  |

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
- `get_input_format_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 4. TCBotRunMetrics

`observability/models/base_models.py`

### Purpose

TCBotRunMetrics(id, bot_tc_run, metric_name, assessment_questions, metric_threshold_value, metric_score, reason)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| bot_tc_run | ForeignKey (required, ForeignKey → CompanyBotTestCases) |  |
| metric_name | CharField (required, max_length=100, choices) |  |
| assessment_questions | TextField () |  |
| metric_threshold_value | FloatField (required) |  |
| metric_score | FloatField () |  |
| reason | TextField () |  |

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
- `get_metric_name_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---
