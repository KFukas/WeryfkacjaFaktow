# Build produkcyjny panelu i serwowanie go na http://localhost:8080 BEZ Dockera (API na :8000 w osobnym oknie).
# Plik w ASCII (Windows PowerShell 5.1).
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location (Join-Path $root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { Write-Host "BLAD: build frontendu" -ForegroundColor Red; Pop-Location; exit $LASTEXITCODE }
Pop-Location
Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\uvicorn.exe backend.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -WorkingDirectory (Join-Path $root "frontend") -ArgumentList "-NoExit", "-Command", "npx vite preview --host 127.0.0.1 --port 8080 --strictPort"
Write-Host "Panel (build produkcyjny): http://localhost:8080"
Write-Host "API: http://127.0.0.1:8000/docs"
