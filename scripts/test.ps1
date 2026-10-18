# Wszystkie testy offline: lint, pytest (backend, sandbox, orkiestrator, red-team), frontend. (ASCII - PowerShell 5.1)
Set-Location (Join-Path $PSScriptRoot "..")
function Step([string]$Name, [scriptblock]$Cmd) {
    Write-Host "==> $Name"
    & $Cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "BLAD: $Name" -ForegroundColor Red; exit $LASTEXITCODE }
}
Step "ruff" { .\.venv\Scripts\ruff.exe check . }
Step "pytest" { .\.venv\Scripts\pytest.exe }
Push-Location frontend
Step "typecheck" { npm run typecheck }
Step "vitest" { npm test }
Pop-Location
Write-Host "Wszystkie testy przeszly."
