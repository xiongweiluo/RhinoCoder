#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="${RHINOCODER_PYTHON:-python3}"
VENV_DIR="${RHINOCODER_VENV_DIR:-$PROJECT_DIR/.venv}"

"$PYTHON_BIN" - <<'PY'
import sys
if not (sys.version_info >= (3, 11) and sys.version_info < (3, 14)):
    raise SystemExit("RhinoCoder 0.2.0 requires Python 3.11, 3.12, or 3.13")
PY

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

REQUIREMENTS_FILE="requirements-lock.txt"
if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  REQUIREMENTS_FILE="requirements.txt"
fi

"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$REQUIREMENTS_FILE"
npm ci --prefix agent/ui
npm run build --prefix agent/ui

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env. Fill in the local model key and evaluation token before running."
fi

echo "Bootstrap complete. Python: $VENV_DIR/bin/python"
echo "Activate with: source $VENV_DIR/bin/activate"
echo "Then run: ./scripts/start.sh"
