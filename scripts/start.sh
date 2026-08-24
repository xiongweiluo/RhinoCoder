#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f agent/ui/dist/index.html ]]; then
  echo "Building RhinoCoder UI..."
  npm run build --prefix agent/ui
fi

exec python -m agent.ui_server --port "${RHINOCODER_UI_PORT:-7860}"
