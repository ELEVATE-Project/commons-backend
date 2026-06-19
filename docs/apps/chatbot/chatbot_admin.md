# Chatbot Admin Module

## Overview

The `admin` module contains Django admin customizations facilitating management of chatbot configurations and content through the Django Admin interface.

## Key Admin Modules

- `bot_vernacular_admin.py`: Admin configurations for bot vernacular settings allowing customization of bot messages per bot and locale.
- `company_admin.py`: Admin setup for managing Company entities.
- `generic_upload_admin.py`: Provides generic CSV bulk upload functionality for admin models enabling structured batch data ingestion.
- `media_admin.py`: Admin interface customizations for managing media entries related to chatbot content.
- `profile_admin.py`: Admin configurations for managing user profile data.
- `story_admin.py`: Admin setups for Story management including story content and media attachments.
- `theme_admin.py`: Admin customizations for theme management, likely affecting UI and style aspects.

## Purpose

These admin customizations provide a user-friendly and efficient UI overlay that simplifies managing core chatbot configurations, content, and metadata by directly manipulating the database through Django's ORM.

They support bulk uploading, content review, and entity configuration essential for daily operational management.