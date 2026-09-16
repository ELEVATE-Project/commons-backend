# Observability Admin

## Overview

This section documents the Django Admin customizations for the Observability app. It provides developer-level understanding of the administrative views that facilitate managing bot runs, test case mappings, and their statuses.

## Admin Classes

### CompanyBotRunTestCaseMapAdmin

Located in `admin/bot_run_test_case_map_admin.py`, this class manages the `BotRunTestCaseMap` model admin interface.

- **List Display:** Shows columns for bot run, metric name, test case, status, and creation timestamp.
- **Raw ID Fields:** Uses raw ID lookup for foreign keys to bot_run and test_case to optimize performance.
- **List Filters:** Enables filtering by status, metric name, related bot run and test case references, and includes a custom date filter (`CustomAdvanceDateFilter`).
- **Search Fields:** Allows searching by metric name, status, bot run ID, test case description, and response log.
- **Date Hierarchy:** Enables drill-down navigation by created_at field.
- **Ordering:** Default ordering is newest entries first by descending `created_at`.

These configurations improve admin usability for managing large datasets related to bot run tests and their evaluation metrics.

---

## CompanyBotTCRunAdmin

Located in `admin/company_bot_tc_run_admin.py`, this admin class manages the `CompanyBotTCRun` model.

- **Read-only Fields:** `status` and `metrics_result` fields are read-only to prevent manual editing.
- **Raw ID Fields:** Uses raw ID widget for the foreign key `company_bot` for efficient selection.
- **List Display:** Shows columns for company bot, run status, and creation timestamp.
- **List Filters:** Enables filtering by run status, related company bot, and creation date with a custom date filter.
- **Search Fields:** Allows searching by company bot name and status.
- **Date Hierarchy:** Provides date drill-down navigation based on `created_at`.
- **Ordering:** Displays newest runs first by ordering on `created_at` descending.

## CompanyBotTestCasesAdmin

Located in `admin/company_bot_test_cases_admin.py`, this admin class manages `CompanyBotTestCases` model.

- **List Display:** Displays columns for company bot, test case description, and creation date.
- **Raw ID Fields:** Uses raw ID for efficient selection of related company bot.
- **List Filters:** Filters by company bot and creation date using custom date filter.
- **Search Fields:** Enables searching by test case description, related company bot name, test case input, and expected output.
- **Date Hierarchy:** Enables drill down by creation date.
- **Ordering:** Orders by newest test cases first.
- **Inline Administration:** Displays `TCBotRunMetrics` inline only when editing an existing test case, allowing direct management of related metrics.

---
