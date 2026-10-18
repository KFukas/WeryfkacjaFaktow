# Instalacja lokalna (Windows PowerShell): venv Python 3.12, zależności, .env, baza + dane przykładowe, frontend.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv")) {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3.12 -m venv .venv } else { python -m venv .venv }
}
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -e ".[dev]"
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Utworzono .env z .env.example (LLM_PROVIDER=mock)." }
& ".\.venv\Scripts\alembic.exe" upgrade head
& $py -m backend.seed
Push-Location frontend
npm install
Pop-Location
Write-Host "`nGotowe. Uruchom: .\scripts\start.ps1  (API :8000, panel :5173)"
