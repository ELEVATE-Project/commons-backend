# Chatbot URLs and Routing

## Overview

The chatbot application exposes several HTTP API endpoints and WebSocket routes to facilitate various chatbot functionalities.

## HTTP URL Routing

- Defined in `chatbot/urls.py`.
- Uses Django REST Framework views for API endpoints.
- Endpoints support profile management, chat sessions, media handling, transcription, translation, story management, and more.
- Includes both standard RESTful routes and specialized views for media batch operations, tracking, and document uploads.

### Example Endpoints

- `/api/profile/`: Create or update user profile.
- `/api/login/`: Login endpoint.
- `/api/save-company-chat/`: Save chat messages.
- `/api/chatsession/`: Manage chat sessions.
- `/api/text_translate/`: Text translation API.

## WebSocket Routing

- Defined in `chatbot/routing.py`.
- Maps WebSocket URL patterns to specialized consumer classes handling different chatbot conversational models.
- Examples:
  - `ws/common/` mapped to `AsyncSocketConsumer` for standard chats.
  - `ws/shikshalokam_chaupal/` for Chaupal-specific bots.
  - `ws/guided_guest/`, `ws/free_flow/`, and others.

## Summary

This routing setup provides comprehensive access to chatbot functionalities both synchronously over HTTP and asynchronously via WebSocket for real-time communication.

---
