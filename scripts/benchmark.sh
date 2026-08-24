#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

exec python eval/run_eval.py --mode both --runs "${RHINOCODER_EVAL_RUNS:-3}" "$@"
