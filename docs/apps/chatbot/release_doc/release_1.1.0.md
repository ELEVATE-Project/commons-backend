# Release 1.1.0 — Deployment Guide

AI Search allows users to describe searches in natural language, for example:

> "List all PDFs from the Shikshalokam organization."

The system extracts organization and file-type filters and performs the search.

**Important:** Commons now depends on the **AI Service** microservice. Deploy and configure AI Service **before** deploying Commons.

---

## 1. Deployment Order

Follow this order:

| Step | Service    | Action                                            |
| ---- | ---------- | ------------------------------------------------- |
| 1    | AI Service | Deploy and run migrations                         |
| 2    | AI Service | Create `commons` tenant, service and provider key |
| 3    | AI Service | Start the service and note the URL/port           |
| 4    | Commons    | Configure `AI_SERVICE_*` variables                |
| 5    | Commons    | Run database migrations                           |
| 6    | Commons    | Seed the AI Search Filter Bot                     |
| 7    | Commons    | Restart application and Celery workers            |
| 8    | Both       | Run verification                                  |

**Important:** The AI Service bearer token is shown only once when the service is created. Save it immediately.

---

# 2. AI Service Setup

<details>
<summary><strong>Click to expand — AI Service deployment steps (sections 2–4)</strong></summary>

**Repository:** `https://github.com/priyanka-TL/AI-Service`
**Branch:** `release-1.2.0`

Refer to:

* `docs/local-setup.md`
* `docs/keys-cli.md`

### 2.1 Prerequisites

* [ ] Python 3.10
* [ ] `uv` installed
* [ ] `uv sync` completed
* [ ] PostgreSQL available
* [ ] Redis available
* [ ] spaCy model installed

```bash
uv run python -m spacy download en_core_web_lg
```

### 2.2 Configure `.env`

Create `.env` in the AI Service root:

```env
DB_URL=postgresql+asyncpg://<user>:<pass>@<host>:5432/llm_service
REDIS_URL=redis://<host>:6379

LOG_LEVEL=INFO
PRICING_STALENESS_DAYS=7
SECRET_BACKEND=postgres

GUARDRAILS_PRESIDIO_ENABLED=false
GUARDRAILS_LLAMA_GUARD_ENABLED=false
GUARDRAILS_LLAMA_GUARD_MODEL=none
GUARDRAILS_LLAMA_GUARD_API_KEY=
GUARDRAILS_LLAMA_GUARD_API_BASE=

GUARDRAILS_SIZE_CAP_INPUT_CHARS=100000
GUARDRAILS_SIZE_CAP_OUTPUT_CHARS=50000

CACHE_TTL_SECONDS=0

LLM_RETRY_MAX_ATTEMPTS=3
LLM_RETRY_BACKOFF_BASE_S=2.0
BATCH_MAX_SUBMIT_ATTEMPTS=3
```

* [ ] Production values configured
* [ ] Migrations completed

```bash
alembic upgrade head
```

---

### 3. Create Commons Tenant and Credentials

Run:

```bash
uv run python scripts/add_tenant_key.py
```

Use the following values:

```text
Tenant ID: commons
Tenant display name: Commons

Grant a calling service access to 'commons'? y
Service name: <press Enter>
New service name: commons

Add a provider key for 'commons'? y
Provider: bedrock
AWS Access Key ID: <aws-access-key-id>
AWS Secret Access Key: <aws-secret-access-key>
AWS Region: us-west-2
```

Save the generated service token.

### Verify

* [ ] Tenant `commons` exists
* [ ] Service `commons` exists
* [ ] Service has access to tenant `commons`
* [ ] Service bearer token saved securely
* [ ] Bedrock provider key configured

The provider configured here must match the provider Commons sends to AI Service.

If the tenant does not have a key for that provider, AI Service returns:

```text
422 missing_tenant_key
```

Commons will then fall back to non-LLM search.

---

### 4. Start AI Service

```bash
uv run uvicorn main:app --host 0.0.0.0 --port <port>
```

Record the service URL:

```text
http://<ai-service-host>:<port>
```

* [ ] AI Service is running
* [ ] Host and port recorded

**Note:** Do not use port `8000` if another service already uses it.

</details>

---

# 5. Configure Commons

**Note:** The first block (`AI_SERVICE_*` and `AI_SEARCH_LLM_MODE`/`AI_SEARCH_LLM_CONFIDENCE_THRESHOLD`) is **mandatory** — there are no code-level defaults for those. Everything below the second comment is **optional tuning** — each already has a code-level default (shown as the value here), so copy those lines only if the default behaviour needs to change.

Copy the full block below as-is into the Commons `.env`, then fill in the `<...>` placeholders:

```env
# --- Required ---
AI_SERVICE_BASE_URL=http://<ai-service-host>:<port>
AI_SERVICE_TOKEN=svc_<token-from-ai-service>
AI_SERVICE_TENANT_ID=commons
AI_SERVICE_PROVIDER=bedrock
AI_SERVICE_MODEL=us.meta.llama3-3-70b-instruct-v1:0

AI_SEARCH_LLM_MODE=fallback
AI_SEARCH_LLM_CONFIDENCE_THRESHOLD=0.5

# --- Optional tuning (values below are the code-level defaults) ---
AI_SEARCH_BOT_ROUTE=/ai_search_filters
AI_SERVICE_MAX_ATTEMPTS=2
AI_SERVICE_BACKOFF_BASE_S=0.4
AI_SERVICE_MAX_ELAPSED_S=35.0
AI_SERVICE_COOLDOWN_AFTER_FAILURES=3
AI_SERVICE_COOLDOWN_SECONDS=30.0
AI_SERVICE_CONFIG_COOLDOWN_SECONDS=300.0
AI_SEARCH_LLM_ORG_VOCAB_MODE=auto
AI_SEARCH_LLM_ORG_CANDIDATE_LIMIT=10
AI_SEARCH_LLM_ORG_FULL_MAX=50
AI_SEARCH_LLM_ORG_USE_FUZZY_CANDIDATES=false
```

### Required values

All five `AI_SERVICE_*` values are required:

| Variable               | Purpose               |
| ---------------------- | --------------------- |
| `AI_SERVICE_BASE_URL`  | AI Service URL        |
| `AI_SERVICE_TOKEN`     | Commons service token |
| `AI_SERVICE_TENANT_ID` | AI Service tenant     |
| `AI_SERVICE_PROVIDER`  | LLM vendor            |
| `AI_SERVICE_MODEL`     | LLM model             |

There are no code-level defaults for these values.

### Optional values (tuning)

<details>
<summary><strong>Click to expand — optional AI Search tuning variables</strong></summary>

All of these have code-level defaults, so none are required for a working deployment — they're already included in the copyable block above. Set them only if the default behaviour needs to change. Every setting can also be overridden per-bot via `other_params` (see Per-bot configuration below); `other_params` always wins over the environment.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_SEARCH_BOT_ROUTE` | `/ai_search_filters` | Overrides the AI Search Filter Bot route |
| `AI_SERVICE_MAX_ATTEMPTS` | `2` | Retry attempts for an AI Service call |
| `AI_SERVICE_BACKOFF_BASE_S` | `0.4` | Base backoff (seconds) between retries |
| `AI_SERVICE_MAX_ELAPSED_S` | `35.0` | Overall deadline (seconds) across all retry attempts. **Must exceed** `AI_SERVICE_MAX_ATTEMPTS × CompanyBot.read_timeout` plus backoff — otherwise the deadline expires before attempt one returns and no retry ever runs |
| `AI_SERVICE_COOLDOWN_AFTER_FAILURES` | `3` | Consecutive failures before a transient cooldown starts |
| `AI_SERVICE_COOLDOWN_SECONDS` | `30.0` | Cooldown duration after transient failures |
| `AI_SERVICE_CONFIG_COOLDOWN_SECONDS` | `300.0` | Cooldown duration after a config-level error (bad token, unregistered tenant/provider key). Longer on purpose — a config error is fixed by a person, not by retrying |
| `AI_SEARCH_LLM_ORG_VOCAB_MODE` | `auto` | How organization names are sent to the LLM: `candidates`, `full`, or `auto` |
| `AI_SEARCH_LLM_ORG_CANDIDATE_LIMIT` | `10` | Max organization candidates sent to the LLM in `candidates`/`auto` mode |
| `AI_SEARCH_LLM_ORG_FULL_MAX` | `50` | Max organizations sent to the LLM in `full` mode |
| `AI_SEARCH_LLM_ORG_USE_FUZZY_CANDIDATES` | `false` | Narrow organization candidates using the fuzzy matcher first before calling the LLM |

</details>

### Per-bot configuration

The provider and model can also be configured in the AI Search bot:

```text
other_params.ai_provider
other_params.ai_model
```

Resolution order:

```text
Bot configuration → Environment → Error
```

Every optional tuning value from the table above can also be set per-bot in `other_params`, using these keys:

| `other_params` key | Equivalent env var |
| --- | --- |
| `llm_mode` | `AI_SEARCH_LLM_MODE` |
| `llm_confidence_threshold` | `AI_SEARCH_LLM_CONFIDENCE_THRESHOLD` |
| `llm_max_attempts` | `AI_SERVICE_MAX_ATTEMPTS` |
| `llm_backoff_base_s` | `AI_SERVICE_BACKOFF_BASE_S` |
| `llm_max_elapsed_s` | `AI_SERVICE_MAX_ELAPSED_S` |
| `llm_cooldown_after_failures` | `AI_SERVICE_COOLDOWN_AFTER_FAILURES` |
| `llm_cooldown_seconds` | `AI_SERVICE_COOLDOWN_SECONDS` |
| `llm_config_cooldown_seconds` | `AI_SERVICE_CONFIG_COOLDOWN_SECONDS` |
| `llm_org_vocab_mode` | `AI_SEARCH_LLM_ORG_VOCAB_MODE` |
| `llm_org_candidate_limit` | `AI_SEARCH_LLM_ORG_CANDIDATE_LIMIT` |
| `llm_org_full_max` | `AI_SEARCH_LLM_ORG_FULL_MAX` |
| `llm_org_use_fuzzy_candidates` | `AI_SEARCH_LLM_ORG_USE_FUZZY_CANDIDATES` |

Resolution order for each key is the same: **bot `other_params` → environment variable → code default**. (`AI_SEARCH_BOT_ROUTE` is the one exception — it's environment-only and has no per-bot equivalent.)

The bot's `provider` column should remain:

```text
ai_service
```

It identifies **how Commons reaches the model**, not which vendor is used.

The `llm_model` column is not used by the AI Search Filter Bot.

---

# 6. Run Commons Deployment Steps

From the Commons project root:

### 6.1 Run migrations

```bash
.venv/bin/python manage.py migrate
```

### 6.2 Create/seed the AI Search Filter Bot

```bash
.venv/bin/python chatbot/scripts/ai_search/create_ai_search_bot.py
```

The bot route is:

```text
/ai_search_filters
```

This is the **new AI Search Filter Bot**.

The existing:

```text
/sg_search_bot
```

is the older search bot and must not be modified.

### 6.3 Restart Commons

Restart:

* Commons application
* Celery workers

This is required so the new environment variables are loaded.

---

# 7. Bot Seeding Rules

The seed script is safe to run multiple times.

### Code-managed values

These can be updated with `--force`:

```text
context
tool_context
provider
```

Run:

```bash
.venv/bin/python chatbot/scripts/ai_search/create_ai_search_bot.py --force
```

### Admin-managed values

Values in `other_params` are **never overwritten**.

The script only adds missing keys.

This means:

```text
Existing admin value → keep it
Missing value → add current effective default
```

The existing bot name is also never changed.

`AI_SEARCH_BOT_NAME` is used only when creating a new bot.

---

# 8. Verification

## 8.1 Verify AI Service

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  http://<ai-service-host>:<port>/v1/providers \
  -H "Authorization: Bearer $AI_SERVICE_TOKEN" \
  -H "X-Tenant-Id: commons"
```

Expected:

```text
200
```

Common failures:

| Status | Meaning                         |
| ------ | ------------------------------- |
| `200`  | Working                         |
| `401`  | Invalid/missing token           |
| `400`  | Missing tenant header           |
| `403`  | Service has no access to tenant |
| `000`  | Service unavailable/wrong URL   |

---

## 8.2 Verify AI Search Bot

```bash
.venv/bin/python manage.py shell -c "
from chatbot.services.search.prompts import get_search_bot
b = get_search_bot()
print(b.route, b.company.slug, len(b.context), bool(b.tool_context))
"
```

Verify:

* [ ] Route is `/ai_search_filters`
* [ ] `tool_context` is `True`
* [ ] Prompt length is reasonable
* [ ] Bot provider is `ai_service`

---

## 8.3 Test End-to-End Search

Run a natural-language search such as:

```text
List all PDFs from the <organization> organization
```

Verify:

* [ ] Search returns HTTP `200`
* [ ] `filter_resolution.llm_used` is `true`
* [ ] Organization filter contains the correct slug
* [ ] File type contains `application/pdf`
* [ ] Results are comparable with manually selected filters

Check:

```text
filter_resolution
```

Useful fields:

| Field                      | Purpose                            |
| -------------------------- | ---------------------------------- |
| `llm_used`                 | Whether LLM was called             |
| `llm_decision`             | Why LLM was or wasn't used         |
| `llm_confidence_threshold` | Active threshold                   |
| `fuzzy_confidence`         | Deterministic matcher confidence   |
| `llm_error`                | LLM failure                        |
| `llm_error_code`           | Error type                         |
| `organizations_source`     | `explicit`, `fuzzy`, `llm`, `none` |
| `media_types_source`       | `explicit`, `fuzzy`, `llm`, `none` |
| `llm_latency_ms`           | LLM request latency                |

---

## 8.4 Supported Search Filters

The vector service's `/documents/search` API (`PrioritizedSearchRequest`) supports more filters than AI Search's natural-language extraction currently uses. QA should only test the "already supported" filters through natural-language queries — the rest are only reachable via explicit UI filter selection, not by typing a sentence.

### Already supported by AI Search (natural-language extraction)

`exclude_organizations`, `exclude_file_type`, and `any_of` are **new in this release** — they did not exist in the previous (non-AI) search request payload.

| Filter | Maps to vector service field | New in 1.1.0? | Example query |
| --- | --- | --- | --- |
| Organization | `organizations` | No | "from Shikshalokam" |
| Exclude organization | `exclude_organizations` | **Yes** | "not from Shikshalokam" |
| File type | `file_type` | No | "PDFs" (Commons calls this `media_types` internally) |
| Exclude file type | `exclude_file_type` | **Yes** | "excluding videos" |
| OR combinations (`any_of`) | `any_of` blocks | **Yes** | "PDFs from Shikshalokam OR DOCX from CSF" |

**Example — `exclude_organizations` and `exclude_file_type`**

Query: *"Show everything except videos, not from Shikshalokam"*

```json
{
  "exclude_organizations": ["shikshalokam"],
  "exclude_file_type": ["video"]
}
```

**Example — `any_of`**

Query: *"PDFs from Shikshalokam OR DOCX files from CSF"*

```json
{
  "any_of": [
    { "organizations": ["shikshalokam"], "file_type": ["application/pdf"] },
    { "organizations": ["csf"], "file_type": ["application/docx"] }
  ]
}
```

Each block in `any_of` is AND'ed internally (organization AND file type within that block) and blocks are OR'd against each other. An empty block (no organizations/file types/excludes) is dropped rather than sent, since it would otherwise match every document.

### Not yet supported by AI Search (exists in vector service, explicit-filter only today)

| Filter | Vector service field | Current access path |
| --- | --- | --- |
| Tags | `categories` | Explicit `tags` query param only (UI filter, older `chat_query_handler.py` path) |
| Resource / document type (key entities) | `resource_type` | Explicit `resource_types` query param only |
| Search mode (hybrid vs. semantic) | `search_mode` | Not set by Commons; vector service defaults to `hybrid` |
| Tag/resource-type OR groups | `any_of` block-level `categories`/`resource_type` | Not populated — Commons' `any_of` blocks only carry organization/file type |

**Note:** These four are candidates for a future release if natural-language filtering needs to expand beyond organization and file type — they would need to be added to the LLM tool schema (`chatbot/services/search/prompts.py`) and the resolver in `chatbot/services/search/llm_extractor.py`.

---

# 9. Test Graceful Degradation

This test is required.

Stop AI Service and run the same search again.

Expected:

* [ ] Search still returns HTTP `200`
* [ ] Search still returns results
* [ ] `llm_used` is `false`
* [ ] `llm_error` is populated

**An AI Service failure must not make search fail.**

If search returns `5xx`, disable the feature immediately:

```env
AI_SEARCH_LLM_MODE=off
```

---

# 10. Rollback

No database rollback is required.

Disable AI Search LLM processing:

```env
AI_SEARCH_LLM_MODE=off
```

Restart Commons.

This restores the previous non-LLM search behaviour.

The `/ai_search_filters` bot can remain in the database. The existing `/sg_search_bot` remains unchanged.

---

# 11. Release Checklist

### AI Service

* [ ] AI Service deployed
* [ ] Migrations completed
* [ ] `commons` tenant created
* [ ] `commons` service created
* [ ] Service token saved
* [ ] Provider key configured
* [ ] AI Service running
* [ ] `/v1/providers` returns `200`

### Commons

* [ ] `AI_SERVICE_BASE_URL` configured
* [ ] `AI_SERVICE_TOKEN` configured
* [ ] `AI_SERVICE_TENANT_ID=commons`
* [ ] `AI_SERVICE_PROVIDER` matches AI Service provider key
* [ ] `AI_SERVICE_MODEL` configured
* [ ] Commons migrations completed
* [ ] AI Search Filter Bot seeded
* [ ] Application restarted
* [ ] Celery workers restarted

### Verification

* [ ] Natural-language search works
* [ ] Organization filter is correct
* [ ] PDF/file-type filter is correct
* [ ] LLM diagnostic fields are populated
* [ ] AI Service failure falls back gracefully
* [ ] `/sg_search_bot` remains unchanged

---

# 12. Important Release Notes

1. **AI Service must be available before Commons.**
2. **`/ai_search_filters` is the new AI Search Filter Bot.**
3. **`/sg_search_bot` is the existing legacy search bot and must not be modified.**
4. **Only the AI Search Filter Bot route is configurable.**
5. **Existing admin values in `other_params` are never overwritten by the seed script.**
6. **AI Service provider/model must be configured either at deployment level or per bot.**
7. **AI Search failures must degrade to normal search rather than fail the search request.**
8. **The kill switch is `AI_SEARCH_LLM_MODE=off`.**
