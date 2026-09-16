# Observability URLs

## Overview

This module defines the URL routing patterns for the Observability app.

## URL Patterns

- `test_bot_prompt/<int:pk>`
    - Routed to `test_prompt_view` in `views.py`.
    - Used to create a new test run for a specified company bot with primary key `pk`.

- Includes debug toolbar URLs via `debug_toolbar_urls()` for debugging and profiling during development.

---

This routing setup allows integration of observability testing endpoints with developer debugging tools.
