#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

npm run build:public --prefix "$ROOT_DIR/agent/ui"
mkdir -p "$ROOT_DIR/dist"
rsync -a --delete "$ROOT_DIR/agent/ui/dist/" "$ROOT_DIR/dist/"
test -f "$ROOT_DIR/dist/index.html"
