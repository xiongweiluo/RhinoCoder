#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

python -m pip install -r requirements.txt
npm ci --prefix agent/ui
npm run build --prefix agent/ui

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env. Fill in the local model key and evaluation token before running."
fi

echo "Bootstrap complete. Run: ./scripts/start.sh"
