#!/bin/bash
set -e

# ──────────────────────────────────────────────────────────────────────────────
# Mitra Service - Start Script
# Works for fresh installation AND restarts (fully idempotent)
# ──────────────────────────────────────────────────────────────────────────────

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── 1. Homebrew ───────────────────────────────────────────────────────────────
info "Checking Homebrew..."
command -v brew &>/dev/null || error "Homebrew not found. Install it from https://brew.sh and re-run."

# ── 2. System dependencies ────────────────────────────────────────────────────
info "Checking system dependencies (ffmpeg, poppler)..."
brew install ffmpeg poppler 2>/dev/null || brew upgrade ffmpeg poppler 2>/dev/null || true

# ── 3. Python 3.10 ────────────────────────────────────────────────────────────
info "Checking Python 3.10..."
if ! command -v python3.10 &>/dev/null; then
  info "Installing Python 3.10..."
  brew install python@3.10
fi
python3.10 --version

# ── 4. uv ─────────────────────────────────────────────────────────────────────
info "Checking uv..."
command -v uv &>/dev/null || { info "Installing uv..."; pip install uv; }

# ── 5. PostgreSQL@14 ──────────────────────────────────────────────────────────
info "Checking PostgreSQL@14..."
brew list postgresql@14 &>/dev/null || { info "Installing PostgreSQL@14..."; brew install postgresql@14; }

if pg_isready -q 2>/dev/null; then
  info "PostgreSQL is already running"
else
  info "Starting PostgreSQL@14..."
  brew services start postgresql@14
  sleep 2
  pg_isready -q || { sleep 5; pg_isready || error "PostgreSQL failed to start. Run: brew services restart postgresql@14"; }
fi
info "PostgreSQL is ready"

# ── 6. Redis ──────────────────────────────────────────────────────────────────
info "Checking Redis..."
brew list redis &>/dev/null || { info "Installing Redis..."; brew install redis; }

if redis-cli ping &>/dev/null; then
  info "Redis is already running"
else
  info "Starting Redis..."
  brew services start redis
  sleep 1
  redis-cli ping &>/dev/null || { sleep 3; redis-cli ping | grep -q PONG || error "Redis failed to start."; }
fi
info "Redis is ready"

# ── 7. Validate .env ──────────────────────────────────────────────────────────
[[ -f ".env" ]] || error ".env not found — copy sample.env to .env and fill in values"

DB_NAME=$(grep "^DATABASE_NAME=" .env | cut -d= -f2 | tr -d '"'"'" )
DB_USER=$(grep "^DATABASE_USER=" .env | cut -d= -f2 | tr -d '"'"'" )
DB_PASS=$(grep "^DATABASE_PASSWORD=" .env | cut -d= -f2 | tr -d '"'"'" )
PG_SCHEMA=$(grep "^POSTGRES_SCHEMAS=" .env | cut -d= -f2 | tr -d '"'"'" )
PG_SCHEMA="${PG_SCHEMA:-shikshalokam}"

[[ -z "$DB_NAME" || -z "$DB_USER" || -z "$DB_PASS" ]] && \
  error ".env is missing DATABASE_NAME, DATABASE_USER, or DATABASE_PASSWORD"

# ── 8. PostgreSQL: DB user + database + schema ────────────────────────────────
info "Ensuring database '$DB_NAME' and schema '$PG_SCHEMA'..."

psql postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
  psql postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" >/dev/null

psql postgres -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
  psql postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" >/dev/null

psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" >/dev/null

PGPASSWORD="$DB_PASS" psql -U "$DB_USER" -d "$DB_NAME" \
  -c "CREATE SCHEMA IF NOT EXISTS $PG_SCHEMA;" \
  -c "GRANT ALL ON SCHEMA $PG_SCHEMA TO $DB_USER;" >/dev/null 2>&1 || true

info "Database '$DB_NAME' + schema '$PG_SCHEMA' ready"

# ── 9. Virtual environment ────────────────────────────────────────────────────
info "Checking virtual environment..."

# Detect stale venv (absolute paths break when project folder is moved)
if [[ -d ".venv" ]] && ! .venv/bin/python -c "import sys" &>/dev/null; then
  warn ".venv is broken (stale paths). Recreating..."
  rm -rf .venv
fi

if [[ ! -d ".venv" ]]; then
  info "Creating virtual environment..."
  uv venv --python python3.10
fi

PYTHON=".venv/bin/python"

# ── 10. Install / sync dependencies ──────────────────────────────────────────
info "Syncing dependencies..."
uv sync
uv pip install psycopg2-binary whitenoise

# ── 11. Load .env into shell ──────────────────────────────────────────────────
info "Loading .env..."
eval "$($PYTHON - <<'PYEOF'
from dotenv import dotenv_values
env = dotenv_values(".env")
for k, v in env.items():
    if v is None:
        v = ""
    v_escaped = v.replace("'", "'\\''")
    print(f"export {k}='{v_escaped}'")
PYEOF
)"

# ── 12. Directories ───────────────────────────────────────────────────────────
mkdir -p logs static

# ── 13. Django migrations ─────────────────────────────────────────────────────
info "Running Django migrations..."
$PYTHON manage.py migrate --run-syncdb
info "Migrations done"

# ── 14. Seed Company and CompanyBot rows from JSON files ─────────────────────
info "Seeding Company and CompanyBot records from JSON files..."
$PYTHON manage.py shell << 'PYEOF'
import json, os, sys
from django.db import transaction
from chatbot.models import Company, CompanyBot, Voice, CompanyStateMachine, BotVernacular

BOT_JSON_FILES = [
    'SGCommonsSearchBot.json',
    'DocTextExtractorBot.json',
]

created_count = 0
updated_count = 0

with transaction.atomic():
    # Pass 1: create/update all bots
    payloads = []
    for filename in BOT_JSON_FILES:
        if not os.path.exists(filename):
            print(f'WARNING: {filename} not found — skipping')
            continue

        with open(filename) as f:
            bots_data = json.load(f)

        for bot_data in bots_data:
            company_slug = bot_data.pop('company_slug', 'shikshalokamstaging')
            voices_data        = bot_data.pop('voices', [])
            state_machines_data = bot_data.pop('state_machines', [])
            bot_vernacular_data = bot_data.pop('bot_vernaculars', [])

            company, c_created = Company.objects.get_or_create(
                slug=company_slug,
                defaults={'name': company_slug, 'status': 'ACTIVE'},
            )
            if c_created:
                print(f'Company created  →  {company_slug}')

            existing = CompanyBot.objects.filter(route=bot_data['route'], company=company)
            if existing.exists():
                bot = existing.first()
                for key, value in bot_data.items():
                    setattr(bot, key, value)
                bot.save()
                updated_count += 1
                action = 'updated'
            else:
                bot = CompanyBot.objects.create(company=company, **bot_data)
                created_count += 1
                action = 'created'

            print(f'CompanyBot {action}  →  {bot.name}  (route: {bot.route})')

            # Clear existing inlines so re-running is idempotent
            Voice.objects.filter(company_bot=bot).delete()
            CompanyStateMachine.objects.filter(company_bot=bot).delete()
            BotVernacular.objects.filter(company_bot=bot).delete()

            payloads.append({
                'bot': bot,
                'company': company,
                'voices_data': voices_data,
                'state_machines_data': state_machines_data,
                'bot_vernacular_data': bot_vernacular_data,
            })

    # Pass 2: recreate inlines (matches import_bots_json two-pass logic)
    for p in payloads:
        bot, company = p['bot'], p['company']

        for v in p['voices_data']:
            Voice.objects.create(company_bot=bot, **v)
        if p['voices_data']:
            print(f'  → {len(p["voices_data"])} voice(s) created for {bot.name}')

        for sm in p['state_machines_data']:
            sm = sm.copy()
            pre_route  = sm.pop('preprocess_bot_route', None)
            post_route = sm.pop('postprocess_bot_route', None)
            pre_bot  = CompanyBot.objects.filter(route=pre_route,  company=company).first() if pre_route  else None
            post_bot = CompanyBot.objects.filter(route=post_route, company=company).first() if post_route else None
            CompanyStateMachine.objects.create(
                company_bot=bot, preprocess_bot=pre_bot, postprocess_bot=post_bot, **sm
            )

        for bv in p['bot_vernacular_data']:
            BotVernacular.objects.create(company_bot=bot, **bv)

print(f'Done — {created_count} created, {updated_count} updated.')
PYEOF

# ── 15. Create superuser (only if none exists) ───────────────────────────────
$PYTHON manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(username='admin', email='admin@shikshalokam.org', password='admin123')
    print('Superuser created  →  username: admin  /  password: admin123')
else:
    print('Superuser already exists')
" 2>/dev/null

# ── 16. Collect static files ──────────────────────────────────────────────────
# --clear is omitted: it calls exists("") on the storage backend which crashes
# when S3 is configured (S3 requires key length >= 1).
info "Collecting static files..."
$PYTHON manage.py collectstatic --noinput -v 0
info "Static files collected"

# ── 17. Launch Celery worker in a new Terminal window ─────────────────────────
info "Opening Celery worker in a new Terminal window..."
osascript -e "tell application \"Terminal\"
    do script \"cd '$PROJECT_DIR' && ./start_celery.sh\"
    activate
end tell"

# ── 18. Start server ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Mitra service is starting                       ${NC}"
echo -e "${GREEN}  Admin dashboard: http://localhost:9000/admin/   ${NC}"
echo -e "${GREEN}  Login: admin / admin123                         ${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

$PYTHON -m uvicorn shikshalokam_mohini.asgi:application \
  --host 0.0.0.0 \
  --port 9000 \
  --workers 1 \
  --reload
