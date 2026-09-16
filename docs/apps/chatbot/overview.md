# Chatbot Application

## Introduction

The Chatbot application is a key component of the Shikshalokam platform, designed to provide intelligent conversational capabilities to users. It supports various bot strategies to interact with users in different contexts, managing sessions, messages, and user profiles.

## Purpose and Features

- Handles multi-strategy chatbot interactions including guided, one-shot, and guest discussion bots.
- Supports real-time communication via websocket consumers.
- Integrates asynchronous message handling using Celery tasks for efficient background processing.
- Comprehensive authentication with JWT and token blacklisting.

## High-Level Architecture

The Chatbot app is organized into the following major components:

- **Authentication**: Manages user authentication and token validation.
- **Services**: Core business logic including chat orchestration, message preparation, and prompt building.
- **Strategies**: Defines behavior for different bot types.
- **Consumers**: WebSocket consumers for real-time interactions.
- **Celery Tasks**: Background processing tasks related to messaging.
- **Utilities**: Helper functions and utilities supporting various operations.
- **Management**: Django management commands (if any).
- **URLs and Routing**: Endpoint definitions and ASGI routing for websocket.
- **Templates**: Frontend components associated with the chatbot.

## Folder Structure

```plain
chatbot/
├── auth.py                   # Authentication logic
├── services/                 # Core chatbot services
│   ├── core/                 # Core service implementations
│   └── strategies/           # Bot behavior strategies
├── consumers/                # Websocket consumers
├── celery_tasks/             # Asynchronous task processing
├── utils/                    # Utility functions
├── management/               # Management commands
├── urls.py                   # Django URL routing
├── routing.py                # ASGI routing for websockets
└── templates/                # Frontend templates
```
