#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -x .venv/bin/python ]; then BIN=.venv/bin; else BIN=.venv/Scripts; fi
"$BIN/ruff" check .
"$BIN/pytest"
(cd frontend && npm run typecheck && npm test)
