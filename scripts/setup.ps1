# Instalacja lokalna (Windows PowerShell): venv Python 3.12, zaleznosci, .env, baza + dane przykladowe, frontend.
# Plik celowo w ASCII: Windows PowerShell 5.1 czyta skrypty bez BOM w kodowaniu ANSI.
# Nie uzywamy $ErrorActionPreference="Stop" - komunikaty narzedzi na stderr (np. logi alembica) bylyby bledami;
# zamiast tego sprawdzamy kod wyjscia kazdego kroku.
Set-Location (Join-Path $PSScriptRoot "..")

function Step([string]$Name, [scriptblock]$Cmd) {
    Write-Host "==> $Name"
    & $Cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "BLAD w kroku: $Name (kod $LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }
}

if (-not (Test-Path ".venv")) {
    if (Get-Command py -ErrorAction SilentlyContinue) { Step "venv (py -3.12)" { py -3.12 -m venv .venv } }
    else { Step "venv (python)" { python -m venv .venv } }
}
$py = ".\.venv\Scripts\python.exe"
Step "pip" { & $py -m pip install --upgrade pip --quiet }
Step "zaleznosci Pythona" { & $py -m pip install -e ".[dev]" --quiet }
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Utworzono .env z .env.example (LLM_PROVIDER=mock)." }
Step "migracje bazy" { cmd /c ".venv\Scripts\alembic.exe upgrade head 2>&1" }
Step "dane przykladowe" { & $py -m backend.seed }
Push-Location frontend
Step "zaleznosci frontendu" { npm install --no-fund --no-audit }
Pop-Location
Write-Host ""
Write-Host "Gotowe. Uruchom: .\scripts\start.ps1  (API :8000, panel :5173)"
