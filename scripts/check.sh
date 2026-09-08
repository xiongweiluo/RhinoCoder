#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

python -m compileall -q agent data_pipeline eval plugin tools training
python -m pytest -q
python eval/run_eval.py --dry-run
python tools/check_collection_campaign.py
python tools/check_collection_campaign.py --manifest eval/collection/phase2_100.json
python tools/generate_phase3_tasks.py --check
python tools/check_collection_campaign.py --manifest eval/collection/phase3_300.json
python tools/check_secrets.py
python tools/audit_trace_data.py
python tools/audit_release_data.py
python tools/check_demo_assets.py
python tools/privacy_audit.py
if [[ -f data/golden_traces_v2.jsonl ]]; then
  if [[ -f data/training/a5/manifest.json ]]; then
    python tools/run_training.py audit
    if [[ -d data/training/tokenizer-cache ]]; then
      python tools/run_training.py tokenizer-audit --local-files-only
    fi
    if python -c "import torch" >/dev/null 2>&1; then
      python tools/run_training.py smoke
    fi
  fi
fi
python tools/run_training.py cluster-template-audit
python tools/check_release_consistency.py
if [[ -f data/audit/rhinocoder.sqlite3 ]]; then
  python tools/audit_db.py audit
fi
if [[ -f data/a6/run-manifest.json ]]; then
  python tools/run_a6_baseline.py audit
fi
npm run build --prefix agent/ui
