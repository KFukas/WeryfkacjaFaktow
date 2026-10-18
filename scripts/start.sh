#!/usr/bin/env bash
# Start API (:8000, w tle) i panelu redaktora (:5173). Ctrl+C zatrzymuje oba.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -x .venv/bin/uvicorn ]; then BIN=.venv/bin; else BIN=.venv/Scripts; fi
"$BIN/uvicorn" backend.main:app --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
echo "API: http://127.0.0.1:8000/docs   Panel: http://127.0.0.1:5173"
(cd frontend && npm run dev -- --host 127.0.0.1)
