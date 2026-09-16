# Chatbot Form Module

## Overview

The chatbot `form` module contains Django form classes primarily used for input validation and processing within the chatbot admin and application UI.

## MediaAdminForm

Located in `form/media/media_form.py`, the `MediaAdminForm` class:

- A Django ModelForm for the `Media` model.
- Manages manual and auto tags with custom multiple choice fields.
- Supports filtered selection widgets for user-friendly tag selection.
- Handles saving and associating tags, preserving AI-generated tags while allowing manual tag updates.
- Includes logic for populating fields according to existing model instances or initializing new ones.

This form enables efficient tag management and validation in media-related chatbot admin workflows.
