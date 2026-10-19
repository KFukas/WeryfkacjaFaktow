@echo off
rem Zatrzymuje API i panel uruchomione przez URUCHOM.bat - TYLKO procesy tego projektu
rem (inne aplikacje na portach 8000/8080 nie sa ruszane). Plik w ASCII.
setlocal
cd /d "%~dp0"
title Zatrzymywanie Kurier Faktow
echo  Zatrzymuje Kurier Faktow...
rem 1. Okna otwarte przez URUCHOM.bat (razem z procesami w srodku).
taskkill /f /t /fi "WINDOWTITLE eq Kurier Faktow - *" >nul 2>nul
rem 2. Na wszelki wypadek: uvicorn z .venv tego projektu i vite preview z jego folderu frontend.
set "ROOT=%~dp0"
powershell -NoProfile -Command "$root = $env:ROOT.TrimEnd('\'); Get-CimInstance Win32_Process | Where-Object { ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, 'OrdinalIgnoreCase') -and $_.CommandLine -match 'backend\.main:app') -or ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'vite' -and $_.CommandLine -match 'preview' -and $_.CommandLine -match [regex]::Escape($root)) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo  Zatrzymano.
if not defined KURIER_HEADLESS pause
