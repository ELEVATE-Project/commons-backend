# Chatbot Templates

## Overview

The chatbot application includes several HTML templates primarily used within the Django admin interface to facilitate batch media upload and generic batch imports associated with chatbot data.

## Key Templates

### Batch Upload Templates

Stored under `templates/admin/batch_upload/`, these templates support a guided, multi-step workflow for batch uploading media:

- `batch_upload.html`: Main batch upload page extending the admin base template.
  - Includes steps for file upload, review, and saving.
  - Dynamically loads JavaScript and CSS required for upload functionality.
  - Uses included sub-templates:
    - Step indicators
    - Status messages
    - Upload, Review, and Save step content sections

- Supporting partial templates like:
  - `includes/step_indicator.html`
  - `includes/status_messages.html`
  - `steps/step1_upload.html`, `steps/step2_review.html`, `steps/step3_save.html`

### Generic Batch Upload Template

- `generic_batch_upload.html`
  - Supports batch importing for generic chatbot models.
  - Provides a step-based UI with progress indicators and field selections.
  - Includes embedded CSS for styling and JavaScript integration.

### Template Usage Context

These templates are primarily used in the Django admin UI for chatbot media and data management, enabling administrators to perform bulk imports and uploads with validation and review steps.

They provide a smooth UI experience to upload or import data sets, review them, and process saving actions, essential for managing chatbot content and configurations.

---

This complements backend chatbot functionalities with admin interface tools for effective management of media and model data.
