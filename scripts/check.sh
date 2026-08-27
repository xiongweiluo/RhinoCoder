#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

python -m compileall -q agent data_pipeline eval plugin tools
python -m pytest -q
python eval/run_eval.py --dry-run
python tools/check_secrets.py
python tools/audit_trace_data.py
python tools/audit_release_data.py
npm run build --prefix agent/ui
