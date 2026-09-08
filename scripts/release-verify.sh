#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

LOCAL_RHINO=0
if [[ "${1:-}" == "--local-rhino" ]]; then
  LOCAL_RHINO=1
elif [[ $# -gt 0 ]]; then
  echo "Usage: ./scripts/release-verify.sh [--local-rhino]" >&2
  exit 2
fi

git diff --check
./scripts/check.sh
python tools/check_demo_assets.py

if [[ $LOCAL_RHINO -eq 1 ]]; then
  python tools/verify_clean_install.py --local-rhino
else
  python tools/verify_clean_install.py
fi

echo "v0.3.0 local release verification passed. No commit, tag, push, or GitHub Release was created."
