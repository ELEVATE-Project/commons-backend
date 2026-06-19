# Observability Views

## Overview

This module contains REST API views exposed by the Observability app for developer interactions and testing bots.

## test_prompt_view

- Method: GET
- URL Parameter: `pk` (company bot primary key)

### Functionality

- Creates a new test run (`CompanyBotTCRun`) for the specified `company_bot` identified by the primary key.
- Saves the new test run record.
- Returns status `ok` if successful.
- Handles exceptions and returns error status and message on failure.

### Usage

This API endpoint can be invoked to trigger a new test run associated with a company bot.

---
