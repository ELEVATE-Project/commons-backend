#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'
NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC}  $1"; }

[[ -d ".venv" ]] || { echo "ERROR: .venv not found — run ./start.sh first"; exit 1; }
[[ -f ".env"  ]] || { echo "ERROR: .env not found"; exit 1; }

PYTHON=".venv/bin/python"

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

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Celery worker starting                          ${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

.venv/bin/celery -A shikshalokam_mohini worker --pool=threads
