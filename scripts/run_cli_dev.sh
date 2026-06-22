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

# Use watchdog to auto-restart on file changes
"$PYTHON_BIN" -m watchmedo auto-restart \
  --directory=backend,interface \
  --pattern='*.py' \
  --recursive \
  -- "$PYTHON_BIN" -m personal_crm.cli "$@"
