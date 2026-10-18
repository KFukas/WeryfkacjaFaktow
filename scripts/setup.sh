#!/usr/bin/env bash
# Instalacja lokalna (Linux/macOS/Git Bash): venv Python 3.12, zależności, .env, baza + dane, frontend.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -n "${PYTHON:-}" ]; then PYCMD=("$PYTHON")
elif command -v python3.12 >/dev/null; then PYCMD=(python3.12)
elif command -v py >/dev/null && py -3.12 --version >/dev/null 2>&1; then PYCMD=(py -3.12)   # Git Bash na Windows
else PYCMD=(python3); echo "UWAGA: nie znaleziono Pythona 3.12 — używam $(python3 --version)"; fi
[ -d .venv ] || "${PYCMD[@]}" -m venv .venv
if [ -x .venv/bin/python ]; then BIN=.venv/bin; else BIN=.venv/Scripts; fi
"$BIN/python" -m pip install --upgrade pip >/dev/null
"$BIN/python" -m pip install -e ".[dev]"
[ -f .env ] || { cp .env.example .env; echo "Utworzono .env z .env.example (LLM_PROVIDER=mock)."; }
"$BIN/alembic" upgrade head
"$BIN/python" -m backend.seed
(cd frontend && npm install)
echo; echo "Gotowe. Uruchom: scripts/start.sh  (API :8000, panel :5173)"
