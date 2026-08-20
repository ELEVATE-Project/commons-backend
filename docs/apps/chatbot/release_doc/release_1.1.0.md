# Release 1.0 — Deployment Checklist

AI-powered search: users describe what they want in plain language
("list all PDFs from the Shikshalokam organization") and the system resolves it
into Organization and File Type filters plus a clean search query.

This release adds a dependency on a **new external service** (AI Service), so it
must be deployed and provisioned *before* Commons is released.

---

## 0. Order of operations

Deploy strictly in this order — each step depends on the one before it.

| # | Where | What |
|---|-------|------|
| 1 | AI Service | Deploy, migrate, provision tenant + `commons` service + provider key |
| 2 | AI Service | Start the server, note the base URL and port |
| 3 | Commons | Set `AI_SERVICE_*` variables in `.env` |
| 4 | Commons | `manage.py migrate` |
| 5 | Commons | `chatbot/scripts/ai_search/create_ai_search_bot.py` |
| 6 | Commons | Restart the app + Celery workers |
| 7 | Both | Run the verification steps in §4 |

> The bearer token from step 1 is displayed **once and never again**. Capture it
> before closing the terminal, or you will have to re-register the service.

---

## 1. AI Service setup

**Repository:** <https://github.com/priyanka-TL/AI-Service>
**Release branch:** `release-1.2.0`
**Setup reference:** [`docs/local-setup.md`](https://github.com/priyanka-TL/AI-Service/blob/release-1.2.0/docs/local-setup.md) · [`docs/keys-cli.md`](https://github.com/priyanka-TL/AI-Service/blob/release-1.2.0/docs/keys-cli.md)

### 1.1 Prerequisites

- [ ] Python 3.10
- [ ] `uv` installed, `uv sync` run
- [ ] PostgreSQL reachable, database created
- [ ] Redis reachable
- [ ] spaCy model: `uv run python -m spacy download en_core_web_lg`

### 1.2 Environment

Create `.env` in the AI Service root. **Every variable must be present — the app
fails fast on any missing config.**

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

- [ ] `.env` created with production values
- [ ] Migrations applied: `alembic upgrade head`

### 1.3 Provision the tenant, the `commons` service, and the provider key

```bash
uv run python scripts/add_tenant_key.py
```

Answer the prompts as follows:

```
Tenant ID: commons
Tenant display name [commons]: Commons

Grant a calling service access to 'commons'? (y/n): y
  Service name (press Enter to create new): [press Enter]
  New service name: commons

  !! Save this token now — it will not be shown again:
     svc_<generated-token>          <-- this becomes AI_SERVICE_TOKEN

Add a provider key for 'commons'? (y/n): y
  Provider (...): bedrock
  AWS Access Key ID: <aws-access-key-id>
  AWS Secret Access Key: <aws-secret-access-key>
  AWS Region [us-east-1]: us-west-2
  (remaining prompts: press Enter to skip)
```

- [ ] Tenant `commons` created
- [ ] Calling service named **`commons`** created and granted access to the tenant
- [ ] Bearer token captured somewhere safe
- [ ] **Bedrock** provider key stored (`aws_credentials` format)

> The key must match the vendor commons asks the gateway for, which is
> `AI_SERVICE_PROVIDER` in commons' own `.env` (§2) — `bedrock` by default, with
> `AI_SERVICE_MODEL=us.meta.llama3-3-70b-instruct-v1:0`. If the tenant has no key
> for that vendor, `/v1/chat` returns **422 `missing_tenant_key`** and search
> quietly falls back to non-LLM behaviour.
>
> To use a different vendor, change those two variables (e.g.
> `AI_SERVICE_PROVIDER=anthropic`) to match the key you registered. This is
> deliberately *not* a per-bot setting: the model choice belongs to the AI
> Service deployment. The `/ai_search_filters` bot keeps `provider = ai_service`,
> which selects *how commons reaches the model*, not which vendor answers, and
> its `llm_model` column is ignored.

### 1.4 Start

```bash
uv run uvicorn main:app --port <port> --host 0.0.0.0
```

- [ ] Service running, port recorded for §2

> **Port:** do not reuse `8000` if the vectorization service already occupies it
> on the same host. On **macOS dev machines only**, avoid `7000` — the AirPlay
> Receiver also binds it and answers with a `403` that looks like an auth
> failure; use `127.0.0.1` rather than `localhost` there.

---

## 2. Commons configuration

**Repository:** <https://github.com/ELEVATE-Project/commons-backend>

Add to the Commons `.env` (see `sample.env` for the full annotated list):

```env
AI_SERVICE_BASE_URL=http://<ai-service-host>:<port>
AI_SERVICE_TOKEN=svc_<token-from-step-1.3>
AI_SERVICE_TENANT_ID=commons
AI_SERVICE_PROVIDER=bedrock
AI_SERVICE_MODEL=us.meta.llama3-3-70b-instruct-v1:0

AI_SEARCH_LLM_MODE=fallback
AI_SEARCH_LLM_CONFIDENCE_THRESHOLD=0.5
```

- [ ] All five `AI_SERVICE_*` values set — none has a fallback, and a missing one
      degrades search to non-LLM filters with a `missing_config` log
- [ ] `AI_SERVICE_TENANT_ID` matches the tenant ID from §1.3 exactly
- [ ] `AI_SERVICE_PROVIDER` matches the provider key registered in §1.3
- [ ] Remaining `AI_SEARCH_*` / retry variables left at defaults, or set deliberately

`AI_SERVICE_PROVIDER` and `AI_SERVICE_MODEL` are the only two with no per-bot
override, by design: which model answers belongs to the AI Service deployment,
not to a row in commons' database.

Optional tuning, all documented in `sample.env`, all overridable per bot via the
bot's `other_params` without a deploy:
`AI_SEARCH_LLM_ORG_VOCAB_MODE`, `AI_SEARCH_LLM_ORG_CANDIDATE_LIMIT`,
`AI_SEARCH_LLM_ORG_FULL_MAX`, `AI_SERVICE_MAX_ATTEMPTS`,
`AI_SERVICE_BACKOFF_BASE_S`, `AI_SERVICE_MAX_ELAPSED_S`,
`AI_SERVICE_COOLDOWN_AFTER_FAILURES`, `AI_SERVICE_COOLDOWN_SECONDS`,
`AI_SERVICE_CONFIG_COOLDOWN_SECONDS`.

---

## 3. Commands to run on Commons

```bash
# 1. schema
.venv/bin/python manage.py migrate

# 2. create the AI search prompt bot (idempotent; safe to re-run)
.venv/bin/python chatbot/scripts/ai_search/create_ai_search_bot.py

# 3. restart the app and Celery workers so the new .env is picked up
```

- [ ] `migrate` completed
- [ ] `create_ai_search_bot` reports **created** (or "already exists" on a re-run)
- [ ] App and workers restarted

**No new migrations ship with this release** — the prompt lives in an existing
`CompanyBot` row, so `migrate` is only a safety check.

Bot creation is a script rather than a management command, because AI Search is
optional — it is not part of the setup the chatbot needs to start. Run it from
the project root. Useful variants:

```bash
# per-company prompt override
.venv/bin/python chatbot/scripts/ai_search/create_ai_search_bot.py --company <slug>
# overwrite an edited prompt
.venv/bin/python chatbot/scripts/ai_search/create_ai_search_bot.py --force
```

Search resolves a company-specific prompt first and falls back to the global
one, so the single global bot is enough for this release.

---

## 4. Verification

### 4.1 AI Service reachable and the `commons` credentials work

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  http://<ai-service-host>:<port>/v1/providers \
  -H "Authorization: Bearer $AI_SERVICE_TOKEN" \
  -H "X-Tenant-Id: commons"
```

- [ ] Returns **200**

| Code | Meaning |
|------|---------|
| `200` | Working |
| `401` | Bearer token missing, malformed, or unknown |
| `400` | `X-Tenant-Id` header missing |
| `403` | Token is valid, but the `commons` service was not granted access to that tenant |
| `000` / refused | Service not running, or wrong host/port |

There is no unauthenticated health endpoint, so this doubles as a liveness and
an auth check.

### 4.2 The prompt bot exists

```bash
.venv/bin/python manage.py shell -c "
from chatbot.services.search.prompts import get_ai_search_bot
b = get_ai_search_bot(None)
print(b.route, b.company.slug, len(b.context), bool(b.tool_context))"
```

- [ ] Prints `/ai_search_filters`, a company slug, a non-zero prompt length, and `True`

### 4.3 End-to-end search

```bash
curl -s "http://<commons-host>/ai/documents/search?q=List+all+PDFs+from+the+<org>+organization" \
  | jq '.count, .search_metadata.filter_resolution'
```

- [ ] `filter_resolution.llm_used` is `true`
- [ ] `organizations` contains the organization **slug**, not its display name
- [ ] `media_types` contains `application/pdf`
- [ ] `count` is comparable to the same search with filters selected manually

`filter_resolution` is the diagnostic surface for this feature. Useful fields:

| Field | Meaning |
|---|---|
| `llm_used` | whether the LLM call actually happened |
| `llm_decision` | which branch was taken: `mode_off`, `mode_always`, `filters_explicit`, `confidence_met`, `low_confidence`, `no_answer` |
| `llm_mode` / `llm_confidence_threshold` | the resolved configuration |
| `fuzzy_confidence` | the deterministic matcher's score, compared against the threshold |
| `llm_error` / `llm_error_code` | set when the call was attempted and failed |
| `llm_rejected` | values the model returned that are not in the vocabulary |
| `organizations_source` / `media_types_source` | `explicit`, `fuzzy`, `llm` or `none` |
| `llm_latency_ms` | round-trip time for the call |

Read `llm_used` with `llm_decision`: a decision of `mode_always` with
`llm_used: false` and an `llm_error` means the call was made and failed, not
that it was skipped.

### 4.4 Graceful degradation (do not skip)

Stop the AI Service and repeat 4.3.

- [ ] Search still returns **HTTP 200** with results
- [ ] `llm_used` is `false` and `llm_error` is populated

An LLM failure must never fail a search. If this step returns a 5xx, stop the
release and set `AI_SEARCH_LLM_MODE=off`.

---

## 5. Rollback

No schema changes, so rollback is configuration only:

```env
AI_SEARCH_LLM_MODE=off
```

- [ ] Kill switch tested before release

This restores exactly the previous search behaviour without a redeploy or code
revert. The `/ai_search_filters` bot row can be left in place.

---

## 6. Known limitations for 1.0

- **Bots are not seeded automatically in production.** `deployment/ansible.yml`
  runs migrations only, so `create_ai_search_bot` is a deliberate manual step
  on every environment.
- **Tool-calling support is model-dependent.** AI Service passes
  `drop_params=True` to LiteLLM, so a model without tool support has the tool
  schema dropped silently and answers in prose. The client recovers JSON from
  the message body, but if extraction looks unreliable, change
  `AI_SERVICE_MODEL` first.
- **Organization matching is case-sensitive downstream.** Qdrant matches
  `metadata.company` exactly while Postgres uses `iexact`, so filter values are
  normalised to the stored slug. Verify 4.3 against a real organization slug.
- **One tenant for all organizations.** Every LLM call bills to the single
  `commons` tenant. Per-organization tenants are supported via the bot's
  `other_params.ai_tenant_id`, but nothing provisions them automatically.
- **Large organization lists inflate the prompt.** Above
  `AI_SEARCH_LLM_ORG_FULL_MAX` (default 50) the vocabulary automatically
  narrows to fuzzy-matcher candidates to stay under the guardrail input cap.
