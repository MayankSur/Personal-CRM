#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  source .env
  set +a
fi

if [[ -f ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

export PYTHONPATH="$ROOT_DIR/backend:$ROOT_DIR/interface"

echo "Starting Personal CRM web UI with hot-reload enabled..."
echo "UI will reload automatically when backend or interface files change."

"$PYTHON_BIN" -m personal_crm_interface.webapp --db data/personal_crm.db --host 127.0.0.1 --port 5050 --debug
