# Wszystkie testy offline: lint, pytest (backend, sandbox, orkiestrator, red-team), frontend.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe
Push-Location frontend; npm run typecheck; npm test; Pop-Location
