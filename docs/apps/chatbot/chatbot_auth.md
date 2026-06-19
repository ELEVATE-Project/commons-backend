# Chatbot Authentication

## Overview

The authentication layer in the Chatbot app is responsible for validating user identity, securing access, and managing JWT tokens.

## ProfileJWTAuthentication Class

Located in `chatbot/auth.py`, this class extends JWTAuthentication from rest_framework_simplejwt to:

- Authenticate users based on JWT tokens.
- Retrieve user profile information from the `Profile` model.
- Ensure blacklisted tokens cannot be used.

### Key Methods

- `authenticate(request)`: Verifies presence of Authorization header, validates token, checks blacklist.
- `get_user(validated_token)`: Extracts the user from the token, raises errors if token invalid or user not found.

### Token Blacklisting

- Utilizes `BlacklistedToken` model.
- Checks if token is blacklisted and denies authentication if so.

## Interaction

- Integrated directly with Django Rest Framework authentication flow.
- Used across chatbot endpoints for secure access.
