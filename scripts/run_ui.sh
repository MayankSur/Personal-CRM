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

"$PYTHON_BIN" -m personal_crm_interface.webapp --db data/personal_crm.db --host 127.0.0.1 --port 5050
