#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

export PYTHONPATH="$ROOT_DIR/backend/src:$ROOT_DIR/interface/src"

"$PYTHON_BIN" -m personal_crm.cli daily-agent --db data/personal_crm.db --max 8 --output output/daily_digest.md

# Optional examples:
# - Add --llm-provider anthropic --llm-model claude-3-5-sonnet-latest
# - Add --notify-whatsapp-to "+15555550123" with WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID set

echo "Daily digest generated at output/daily_digest.md"
