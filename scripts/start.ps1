# Start API (:8000) i panelu redaktora (:5173) w osobnych oknach PowerShell. (ASCII - PowerShell 5.1)
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\uvicorn.exe backend.main:app --port 8000"
Start-Process powershell -WorkingDirectory (Join-Path $root "frontend") -ArgumentList "-NoExit", "-Command", "npm run dev -- --host 127.0.0.1"
Write-Host "API:   http://127.0.0.1:8000/docs"
Write-Host "Panel: http://127.0.0.1:5173"
