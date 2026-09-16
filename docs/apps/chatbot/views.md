# View Layer

The View layer exposes HTTP endpoints and acts as the execution boundary between client requests and backend workflows.

Responsibilities of this layer:

- Parse and validate incoming requests
- Handle authentication (JWT where applicable)
- Resolve contextual entities (User, Company, CompanyBot)
- Trigger business workflows
- Initiate asynchronous tasks when required
- Return structured JSON responses

Views coordinate execution but do not contain heavy domain logic.

---

## 1. Chat APIs

### `chatbot/views/chat_view.py`

#### Purpose
Implements conversational session lifecycle and message persistence.

#### Responsibilities

- Create chat sessions
- Persist user messages
- Persist bot messages
- Associate chat sessions with CompanyBot
- Resolve authenticated user context
- Maintain chronological conversation ordering
- Structure response payload for frontend
- Ensure conversation continuity across requests

This is the primary entry point for conversational workflows.

---

## 2. Authentication, Profile & Session APIs

### `chatbot/views/api_views.py`

#### Purpose

Handles session generation, profile synchronization, authentication, and token management.

This module initializes and maintains authenticated user context before domain workflows begin.

---

#### Responsibilities

##### 1. Session Initialization

- Generate Django session ID using `SessionStore`
- Return session key to client
- Establish session-based tracking

---

##### 2. Profile Creation & Synchronization (`post_profile`)

- Validate required fields (email + company/subdomain)
- Resolve Company using slug
- Create or update Profile record
- Handle phone-based fallback lookup
- Serialize and persist profile data
- Perform first-name transliteration using AI4Bharat API (when preferred language is provided)
- Support demo / development company slugs

Ensures idempotent profile initialization aligned with company context.

---

##### 3. Login (`login`)

- Validate email and password
- Verify hashed password using `check_password`
- Fetch associated ProfileAddress
- Issue JWT access token via `RefreshToken`
- Store session authentication state
- Return authenticated profile metadata

---

##### 4. Logout (`logout`)

- Extract token from Authorization header
- Blacklist JWT token via `BlacklistedToken`
- Clear Django session
- Remove session cookie

---

#### Architectural Role

This module:

- Establishes authenticated user identity
- Resolves company context
- Issues JWT credentials
- Synchronizes profile state
- Manages session lifecycle 

It is the authentication boundary layer for the application.

---

## 3. Recommendation APIs

### `chatbot/views/recommendation.py`

#### Purpose
Provides structured domain-level recommendations (e.g., project recommendations).

#### Responsibilities

- Accept contextual filters or identifiers
- Execute recommendation logic
- Rank or filter recommendation results
- Format structured response output
- Return deterministic response schema

This endpoint is independent from conversational workflows.

---

## 4. Translation, Voice & Transliteration APIs

### `chatbot/views/bhashini_views.py`

#### Purpose

Provides multilingual processing and voice transformation endpoints.

This module dynamically selects language providers based on `CompanyBot` configuration and `VoiceType`.

---

#### Responsibilities

##### 1. Text-to-Speech (`text_speech_view`)

- Validate required route
- Resolve `CompanyBot` using route
- Select configured `Voice` provider (TextToSpeech)
- Generate audio from text via `text_speech_provider`
- Return encoded audio content

---

##### 2. Speech-to-Text (`speech_text`)

- Fetch audio from S3 URL
- Convert audio to WAV base64 format
- Resolve `CompanyBot` and fallback to `/common_bot` if needed
- Select SpeechToText voice provider
- Generate transcript via `speech_text_provider`
- Return transcription output

---

##### 3. Text Translation (`text_translation_view`)

- Resolve `CompanyBot` using route
- Select TextToText voice provider
- Translate message via `text_translate_provider`
- Return translated transcript

---

##### 4. Transliteration (`text_transliterate_view`)

- Resolve `CompanyBot` using route
- Select Transliterate voice provider
- Optionally detect source language using AI4Bharat API
- Perform script-level transliteration via `transliterate_text`
- Return transliterated output

---

#### Architectural Role

This module:

- Acts as multilingual abstraction layer
- Dynamically selects providers per bot configuration
- Integrates external language APIs
- Supports STT, TTS, Translation, and Transliteration
- Maintains consistent JSON response structure

It centralizes all language transformation workflows behind route-based configuration.

---

## 5. Media & Knowledge Ingestion APIs

### `chatbot/views/Media/document_upload_view.py`

#### Responsibilities

- Accept document upload requests
- Validate file inputs
- Create Media model entries
- Associate media with Company context
- Persist metadata fields
- Store initial structured data

---

### `chatbot/views/Media/upload_views.py`

#### Responsibilities

- Handle media upload workflows
- Normalize request payload
- Save structured media-related information
- Prepare media records for downstream processing

---

### `chatbot/views/Media/extract_views.py`

#### Responsibilities

- Trigger AI extraction workflows
- Initiate asynchronous Celery tasks
- Pass relevant media identifiers
- Manage extraction initiation state

---

### `chatbot/views/Media/save_views.py`

#### Purpose

Handles structured save operations related to Media entities.

#### Responsibilities

- Accept media-related update requests
- Persist structured metadata changes
- Update existing Media model fields
- Ensure data validation before persistence
- Return updated media state

This view complements upload and extraction workflows by handling structured persistence updates after initial creation.

---

### `chatbot/views/Media/status_views.py`

#### Responsibilities

- Accept Celery task IDs
- Query task readiness using AsyncResult
- Return structured task status
- Handle success and failure states
- Support frontend polling for async workflows

---

### `chatbot/views/Media/media_tracking_views.py`

#### Responsibilities

- Track ingestion state of media records
- Return structured tracking information
- Expose status metadata for frontend monitoring

---

### `chatbot/views/Media/media_views.py`

#### Responsibilities

- Retrieve media objects
- Return structured media details
- Support CRUD-like media interactions

---

### `chatbot/views/Media/media_api_views.py`

#### Responsibilities

- Implement PostgreSQL Full-Text Search (SearchVector)
- Apply SearchRank ordering
- Enable tag-based filtering
- Enable key-value metadata filtering
- Support query parameter-based search
- Implement pagination or limit-based slicing

Provides structured and ranked retrieval over ingested knowledge assets.

---

## 6. Story Management APIs

### `chatbot/views/story_views.py`

#### Purpose

Manages the full lifecycle of Story entities, including:

- Story creation from chat sessions
- Multilingual translation handling
- Story updates with synchronization
- Media attachment
- Story recreation
- Automatic PDF regeneration

---

#### Core Responsibilities

##### 1. Story Creation (`end_story`)

- Create structured Story from completed chat session
- Use `create_story_object` utility
- Support flow-based creation
- Return generated story ID and content

##### 2. Story CRUD (DRF-Based)

- List and create stories (`StoryListCreateView`)
- Retrieve, update, delete stories (`StoryRetrieveUpdateDestroyView`)
- Filter by session and author

##### 3. Multilingual Translation Handling

- Detect language using `LanguageDetectionMixin`
- If language ≠ English:
  - Get or create translation record
  - Update translated fields
  - Sync translated content back to main story
- Maintain translation integrity across updates

##### 4. Automatic PDF Regeneration

When story is updated:

- Trigger `update_story_pdf`
- Skip PDF update for Reflection flow
- Ensure story artifacts stay synchronized after edits

##### 5. Story Media Management

- Attach media to stories (`StoryMediaListCreateView`)
- Update/delete story media
- Trigger PDF regeneration on media changes
- Maintain story-media associations

##### 6. Profile Media Management

- CRUD operations for profile-level media
- Filter by profile

##### 7. Story Recreation (`story_recreate_view`)

- Reconstruct Story from profile + session
- Use `re_create_story_object`
- Useful for regenerating lost or inconsistent story content

##### 8. Story Retrieval by Session

- Fetch all stories associated with a session
- Return full serialized story representation

---

#### Architectural Role

This module:

- Bridges chat sessions and persistent Story records
- Handles multilingual story synchronization
- Manages story-level media attachments
- Keeps story PDFs consistent with content updates
- Provides deterministic CRUD APIs via DRF

It acts as the domain controller for narrative content lifecycle management.

---

## 7. Profile Management APIs

### `chatbot/views/profile_views.py`

#### Responsibilities

- Create profile records
- Update profile information
- Retrieve profile details
- Associate profile with Company
- Maintain profile integrity constraints

Separate from authentication/session initialization logic.

---

## 8. Location APIs

### `chatbot/views/location_views.py`

#### Responsibilities

- Fetch location data
- Return structured location responses
- Provide contextual location information

---

## 9. Infrastructure Integration APIs

### `chatbot/views/aws_views.py`

#### Responsibilities

- Generate S3 presigned URLs
- Validate upload-related parameters
- Return signed access credentials

---

### `chatbot/views/kafka_views.py`

#### Responsibilities

- Accept structured payloads
- Perform request validation
- Trigger Kafka-related operations
- Return status response

Documentation reflects only the request-level responsibilities of this view.

---

### `chatbot/views/gotenberg_view.py`

#### Responsibilities

- Accept document payload
- Trigger PDF rendering process
- Return rendered PDF response
- Handle response formatting

---

## 10. DRF-Based Generic APIs

### `chatbot/views/drf_views.py`

#### Purpose

Provides Django REST Framework–based generic CRUD endpoints for core models.

#### Responsibilities

- Implement ListCreateAPIView and RetrieveUpdateAPIView patterns
- Expose model-level CRUD operations
- Apply serializer-based validation
- Integrate Django Filter backend for query filtering
- Support pagination and query parameter filtering
- Return standardized DRF response formats

This module centralizes DRF-based CRUD patterns instead of writing custom views for each model.

---

## 11. Mitra Project Creation & Report API

### `chatbot/views/mitra_views.py`

#### Purpose

Handles Mitra project creation along with automated report generation (PDF & Excel).

---

#### Responsibilities

- Validate required project inputs
- Optionally create external project via `create_project_utils` (if access token is provided)
- Create internal Mitra project via `create_mitra_project_utils`
- Normalize source data and format project timeline
- Generate structured PDF report
- Generate structured Excel report
- Upload generated files to S3 using `upload_media`
- Attach media references to the created project
- Handle report-generation exceptions gracefully

---

#### Architectural Role

This endpoint combines:

- Project persistence
- External project synchronization
- Document generation
- Media storage integration

It is a domain workflow API focused on project lifecycle and artifact generation, not conversational processing.

---

## 12. Admin & Configuration Views

These views are accessible through Django Admin and are restricted to authenticated staff users.

They enable configuration management, bulk operations, and admin-triggered processing workflows that are not exposed to public APIs.

---

### `chatbot/views/admin/bot_admin_views.py`

#### Purpose

Implements import and export workflows for `CompanyBot` along with its related configuration models.

#### Detailed Responsibilities

- Export a CompanyBot configuration into structured JSON
- Include related inline models during export:
  - Voices
  - State Machines
  - Bot Vernacular
- Generate JSON templates to guide correct import format
- Import CompanyBot configuration from JSON payload
- Reconstruct related inline objects during import
- Detect whether to update an existing bot (route-based matching) or create a new one
- Execute the entire import inside a database transaction to ensure atomicity
- Enforce permission-based restrictions (e.g., superuser/moderator controls)

#### What This Enables

- Safe migration of bot configurations between environments
- Backup and restore of complex bot setups
- Replication of conversational configurations across tenants
- Structured configuration management without manual DB manipulation

This view effectively serializes and reconstructs bot-level conversational configuration.

---

### `chatbot/views/admin/generic_upload_views.py`

#### Purpose

Provides a reusable bulk upload engine for arbitrary Django models via CSV.

#### Detailed Responsibilities

- Dynamically inspect model fields using Django model metadata
- Generate downloadable CSV templates reflecting model structure
- Parse uploaded CSV files row-by-row
- Perform type conversion for fields (Integer, Boolean, Date, etc.)
- Resolve ForeignKey references using lookup logic
- Resolve ManyToMany relationships
- Validate required fields and field constraints
- Collect row-level validation errors
- Execute bulk inserts/updates within database transactions
- Return structured success/error summaries

#### What This Enables

- Admin-level batch data ingestion without writing custom import scripts
- Controlled mass updates for structured models
- Reduced risk of manual data-entry inconsistencies
- Transaction-safe bulk operations with validation feedback

This acts as a generic data ingestion utility within the admin layer.

---

### `chatbot/views/admin/post_processing_views.py`

#### Purpose

Triggers asynchronous post-processing workflows on Story entities.

These workflows refine, filter, or transform story-related data using background tasks.

#### Detailed Responsibilities

- Accept admin-triggered processing requests
- Dynamically determine processing type based on configuration
- Validate required input parameters
- Trigger Celery-based asynchronous post-processing tasks
- Return Celery task ID for tracking
- Provide task status polling endpoint
- Handle success and failure reporting
- Return structured iteration or transformation statistics

#### Processing Examples

Depending on configuration, post-processing may include:

- Unique challenge extraction
- Unique solution extraction
- Deduplication logic
- Content refinement
- Iterative filtering workflows

#### What This Enables

- Admin-triggered refinement pipelines
- Controlled execution of AI-based story processing
- Asynchronous transformation without blocking admin interface
- Transparent task monitoring via polling endpoints

This view provides structured control over background story refinement processes.

---

## Admin Layer Characteristics

- Restricted to authenticated staff users
- Transaction-safe configuration changes
- Async-aware processing for heavy workflows
- Structured validation and error reporting
- Designed for configuration management and controlled bulk operations

---

## View Layer Execution Characteristics

### 1. Thin Request Boundary
Views manage request lifecycle and workflow initiation.

### 2. Async-Aware Architecture
Heavy workflows (extraction, embedding) rely on Celery.

### 3. Structured Persistence Before Async Execution
Data is persisted before triggering asynchronous workflows.

### 4. Context Resolution
User, Company, and CompanyBot context are resolved early.

### 5. Deterministic Response Contracts
All endpoints return predictable JSON schemas.

### 6. Separation of Runtime & Admin Flows
Runtime APIs and admin workflows are clearly separated.
