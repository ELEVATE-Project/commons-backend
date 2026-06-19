# Shikshalokam Views

## Overview

The views module in the Shikshalokam app contains the entry points for web and API requests, acting as the boundary between client calls and backend domain logic execution.

## Detailed Module Descriptions

### health_views.py
- Provides health check endpoint for service liveness verification.
- Implements lightweight JSON response to confirm service operational status.

### mitra_views.py
- Contains endpoints supporting Mitra project workflows.
- Functions include paraphrasing, objective generation and validation, title generation, action list generation, and project status update.
- Utilizes Shikshalokam and Chatbot utilities for content processing and response.
- Employs concurrency and robust error handling for API responses.

### profile_views.py
- Manages profile operations including elevated profile retrieval.
- Provides API endpoint to fetch user profile info by access token.
- Handles error cases for missing tokens or profile fetch failures.

### project_views.py
- Includes CRUD class-based API view for Project entity listing and creation.
- Provides endpoints for duplicating existing projects.
- Supports ingestion of external project and task data.
- Authenticates requests via JWT token verification.
- Utilizes serializers and utility functions for data handling.

### story_views.py
- Manages lifecycle of Story entities including creation, updating, media attachment, and deletion.
- Supports multilingual story translations and syncing.
- Handles PDF regeneration for stories.
- Provides standard Django REST Framework CRUD APIs.

### wishlist_views.py
- Handles user wishlist functionality.
- Provides endpoints to add/remove projects to/from wishlists and retrieve wishlist data.

Each view module orchestrates request parsing, domain logic execution, and response formatting within its feature domain.