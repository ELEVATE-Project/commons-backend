# Django Models

`shikshalokam/models/`

This layer defines the complete database schema for the `shikshalokam` application.

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

## 1. Category

`shikshalokam/models/template_models.py`

### Purpose

Category(id, name, category_id, created_at, updated_at, created_by)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| name | CharField (max_length=1000) |  |
| category_id | CharField (max_length=255) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| created_by | ForeignKey (ForeignKey → User) |  |

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

## 2. Evidence

`shikshalokam/models/project_models.py`

### Purpose

Evidence(id, task, project, remark, evidence_link, type, created_at, updated_at, created_by)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| task | ForeignKey (ForeignKey → Task) |  |
| project | ForeignKey (ForeignKey → Project) |  |
| remark | CharField (max_length=1000) |  |
| evidence_link | CharField (max_length=2000) |  |
| type | CharField (max_length=250) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| created_by | ForeignKey (ForeignKey → User) |  |

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

## 3. LearningResources

`shikshalokam/models/project_models.py`

### Purpose

LearningResources(id, project, name, link, resource_id, app, created_at, updated_at, created_by)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| project | ForeignKey (ForeignKey → Project) |  |
| name | CharField (max_length=1000) |  |
| link | CharField (max_length=2000) |  |
| resource_id | CharField (max_length=500) |  |
| app | CharField (max_length=500) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| created_by | ForeignKey (ForeignKey → User) |  |

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

## 4. Project

`shikshalokam/models/project_models.py`

### Purpose

Project(id, story, project_template, author, categories, description, title, expected_title, actual_title, problem_statement, expected_problem_statement, actual_problem_statement, template_id, project_id, program_id, program_name, recommended_for, keywords, objective, expected_objective, actual_objective, duration, expected_duration, actual_duration, project_status, generated_by, other_params, project_language, project_source, program_source, resource_name, resource_link, project_start_date, project_end_date, solution_download_count, created_at, updated_at, created_by)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| story | ForeignKey (ForeignKey → Story) |  |
| project_template | ForeignKey (ForeignKey → ProjectTemplate) |  |
| author | ForeignKey (ForeignKey → Profile) |  |
| categories | TextField () |  |
| description | TextField () |  |
| title | CharField (max_length=1000) |  |
| expected_title | CharField (max_length=1000) |  |
| actual_title | CharField (max_length=1000) |  |
| problem_statement | TextField () |  |
| expected_problem_statement | TextField () |  |
| actual_problem_statement | TextField () |  |
| template_id | CharField (max_length=500) |  |
| project_id | CharField (unique=True, required, max_length=500) |  |
| program_id | CharField (max_length=500) |  |
| program_name | CharField (max_length=1000) |  |
| recommended_for | TextField () |  |
| keywords | TextField () |  |
| objective | TextField () |  |
| expected_objective | TextField () |  |
| actual_objective | TextField () |  |
| duration | CharField (max_length=1000) |  |
| expected_duration | CharField (max_length=1000) |  |
| actual_duration | CharField (max_length=1000) |  |
| project_status | CharField (max_length=100, choices) |  |
| generated_by | CharField (required, max_length=100, choices) |  |
| other_params | JSONField () |  |
| project_language | CharField (max_length=100) |  |
| project_source | TextField () |  |
| program_source | TextField () |  |
| resource_name | CharField (max_length=1000) |  |
| resource_link | CharField (max_length=2000) |  |
| project_start_date | DateTimeField () |  |
| project_end_date | DateTimeField () |  |
| solution_download_count | PositiveBigIntegerField (required) |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| created_by | ForeignKey (ForeignKey → User) |  |

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
- `get_generated_by_display()`
- `get_next_by_created_at()`
- `get_next_by_updated_at()`
- `get_previous_by_created_at()`
- `get_previous_by_updated_at()`
- `get_project_status_display()`
- `prepare_database_save()`
- `refresh_from_db()`
- `save_base()`
- `save_without_historical_record()`
- `serializable_value()`
- `unique_error_message()`
- `validate_constraints()`
- `validate_unique()`

---

## 5. ProjectTemplate

`shikshalokam/models/template_models.py`

### Purpose

ProjectTemplate(id, category, title, template_id, description, created_at, updated_at, created_by)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| category | ForeignKey (ForeignKey → Category) |  |
| title | CharField (max_length=1000) |  |
| template_id | CharField (max_length=255) |  |
| description | TextField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| created_by | ForeignKey (ForeignKey → User) |  |

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

## 6. ProjectVernacular

`shikshalokam/models/project_vernacular_model.py`

### Purpose

ProjectVernacular(id, project, task, language, details, created_at, updated_at, created_by)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| project | ForeignKey (ForeignKey → Project) |  |
| task | ForeignKey (ForeignKey → Task) |  |
| language | CharField (required, max_length=250) |  |
| details | TextField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| created_by | ForeignKey (ForeignKey → User) |  |

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

## 7. ProjectWishlist

`shikshalokam/models/wishlist_model.py`

### Purpose

ProjectWishlist(id, author, project, created_at, updated_at)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| author | ForeignKey (required, ForeignKey → Profile) |  |
| project | ForeignKey (required, ForeignKey → Project) |  |
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

## 8. Task

`shikshalokam/models/project_models.py`

### Purpose

Task(id, project, parent_task_id, task_id, task_name, mandatory_task, observation_name, number_of_submission_observation, other_params, task_status, description, source, created_at, updated_at, created_by)

### Fields

| Field | Type & Constraints | Description |
|-------|-------------------|-------------|
| id | BigAutoField (unique=True, required) |  |
| project | ForeignKey (required, ForeignKey → Project) |  |
| parent_task_id | CharField (max_length=255) |  |
| task_id | CharField (max_length=255) |  |
| task_name | CharField (max_length=1000) |  |
| mandatory_task | CharField (max_length=100, choices) |  |
| observation_name | CharField (max_length=255) |  |
| number_of_submission_observation | IntegerField () |  |
| other_params | JSONField () |  |
| task_status | CharField (max_length=100) |  |
| description | TextField () |  |
| source | TextField () |  |
| created_at | DateTimeField (required) |  |
| updated_at | DateTimeField (required) |  |
| created_by | ForeignKey (ForeignKey → User) |  |

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
- `get_mandatory_task_display()`
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
