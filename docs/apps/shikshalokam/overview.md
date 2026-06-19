# Shikshalokam Application

## Overview

The Shikshalokam application is an integral part of the overall platform, complementing the chatbot by providing additional domain-specific business functionalities, processing workflows, and integrations.

## Folder Structure

The application is organized into the following key components:

- `admin/`: Django admin customizations for Shikshalokam models.
- `apps.py`: App configuration.
- `migrations/`: Database schema changes.
- `models/`: Data models.
- `resource.py`: Core resource definitions and utilities.
- `scripts/`: Utility and maintenance scripts.
- `serializer/`: Serialization logic for API interactions.
- `tests.py`: Test cases.
- `urls.py`: URL routing for the app.
- `utils/`: Helper functions and utilities supporting various operations.
- `views/`: Web and API view implementations.

## Relationship to Chatbot

The Shikshalokam app structure has similarities to the chatbot application, primarily consisting of modular components like utils, serializers, admin, models, and views. 

Future maintenance could further modularize these components into subfolders (e.g., separating services, consumers, tasks) similar to the chatbot app, enhancing clarity and maintainability.

## Purpose

This app manages core business logic and integrations distinct from chatbot conversational logic, focusing on broader platform features and domain data.
