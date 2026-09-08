#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

export RHINOCODER_RHINO_URL="http://127.0.0.1:1"
exec ./scripts/start.sh
