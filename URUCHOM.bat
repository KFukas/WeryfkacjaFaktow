@echo off
rem ============================================================================
rem  Kurier Faktow - uruchomienie calego projektu jednym kliknieciem (Windows).
rem
rem    URUCHOM.bat          instalacja przy pierwszym uruchomieniu, build panelu,
rem                         start API i panelu, otwarcie przegladarki
rem    URUCHOM.bat build    wymus ponowny build panelu (np. po aktualizacji kodu)
rem
rem  Porty: panel 8080, API 8010 (port 8000 zostawiamy innym projektom - API jest
rem  dostepne przez panel). Jesli port jest zajety przez INNA aplikacje, wybierany
rem  jest nastepny wolny (panel 8081..., API 8011...).
rem  Zatrzymanie: ZATRZYMAJ.bat (albo zamknij okna "Kurier Faktow - ...").
rem  Plik celowo w ASCII - konsola cmd nie zawsze dziala w UTF-8.
rem ============================================================================
setlocal EnableExtensions
cd /d "%~dp0"
title Kurier Faktow (start)
set "PYTHONIOENCODING=utf-8"

echo.
echo  === Kurier Faktow - weryfikacja faktow ===
echo.

rem --- 0. Wybor portow / czy juz dziala ----------------------------------------
set "PANEL_PORT="
set "PANEL_RUNNING="
for %%p in (8080 8081 8082 8083 8084 8085) do if not defined PANEL_PORT call :pickpanel %%p
if not defined PANEL_PORT (
    echo  BLAD: porty 8080-8085 sa zajete przez inne aplikacje.
    goto :fail
)
if defined PANEL_RUNNING (
    echo  Projekt juz dziala.
    goto :open
)
set "API_PORT="
set "API_RUNNING="
for %%p in (8010 8011 8012 8013 8014 8015 8016) do if not defined API_PORT call :pickapi %%p
if not defined API_PORT (
    echo  BLAD: porty 8010-8016 sa zajete przez inne aplikacje.
    goto :fail
)
if not "%PANEL_PORT%"=="8080" echo  Uwaga: port 8080 jest zajety przez inna aplikacje - panel bedzie na porcie %PANEL_PORT%.
if not "%API_PORT%"=="8010" echo  Uwaga: port 8010 jest zajety przez inna aplikacje - API bedzie na porcie %API_PORT%.

rem --- 1. Wymagania i instalacja ------------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
    echo  BLAD: brak Node.js w PATH. Zainstaluj Node.js 20+ ze strony https://nodejs.org
    goto :fail
)
if not exist ".venv\Scripts\python.exe" (
    echo  [1/4] Pierwsze uruchomienie - instalacja zaleznosci, to moze potrwac kilka minut...
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\setup.ps1"
    if errorlevel 1 goto :fail
) else (
    echo  [1/4] Srodowisko Python: OK
)
if not exist ".env" copy /y ".env.example" ".env" >nul
if not exist "frontend\node_modules" (
    echo        Instalacja zaleznosci panelu...
    pushd frontend
    call npm install --no-fund --no-audit
    if errorlevel 1 (
        popd
        goto :fail
    )
    popd
)
rem Dane przykladowe - idempotentne (dodaje tylko brakujace artykuly).
".venv\Scripts\python.exe" -m backend.seed >nul
if errorlevel 1 goto :fail

rem --- 2. Build panelu ----------------------------------------------------------
if /i "%~1"=="build" if exist "frontend\dist" rmdir /s /q "frontend\dist"
if not exist "frontend\dist\index.html" (
    echo  [2/4] Build panelu redaktora...
    pushd frontend
    call npm run build
    if errorlevel 1 (
        popd
        goto :fail
    )
    popd
) else (
    echo  [2/4] Build panelu: OK - ponowny build: URUCHOM.bat build
)

rem --- 3. Start serwerow --------------------------------------------------------
echo  [3/4] Start API (port %API_PORT%) i panelu (port %PANEL_PORT%)...
if defined API_RUNNING (
    echo        API juz dziala - pomijam.
) else (
    start "Kurier Faktow - API :%API_PORT%" /min cmd /k ".venv\Scripts\uvicorn.exe backend.main:app --host 127.0.0.1 --port %API_PORT%"
)
rem Panel przekazuje /api do naszego API (vite.config.ts czyta VITE_API_PROXY).
set "VITE_API_PROXY=http://127.0.0.1:%API_PORT%"
start "Kurier Faktow - panel :%PANEL_PORT%" /min cmd /k "cd /d frontend && node_modules\.bin\vite.cmd preview --host 127.0.0.1 --port %PANEL_PORT% --strictPort"

rem --- 4. Czekamy, az wszystko odpowie ----------------------------------------
echo  [4/4] Czekam na uruchomienie...
for /l %%i in (1,1,60) do (
    call :isours %PANEL_PORT%
    if not errorlevel 1 goto :ready
    ping -n 2 127.0.0.1 >nul
)
echo  BLAD: serwery nie odpowiedzialy w ciagu minuty.
echo        Sprawdz zminimalizowane okna "Kurier Faktow - API" i "Kurier Faktow - panel".
goto :fail

:ready
echo.
echo  Gotowe!
echo    Panel redaktora:  http://localhost:%PANEL_PORT%
echo    API (OpenAPI):    http://127.0.0.1:%API_PORT%/docs
echo    Zatrzymanie:      ZATRZYMAJ.bat
:open
if not defined KURIER_HEADLESS start "" "http://localhost:%PANEL_PORT%"
echo.
if not defined KURIER_HEADLESS pause
exit /b 0

:fail
echo.
echo  Uruchomienie nie powiodlo sie - szczegoly powyzej.
echo  Pomoc: docs\INSTRUKCJA_URUCHOMIENIA.md (sekcja "Rozwiazywanie problemow").
if not defined KURIER_HEADLESS pause
exit /b 1

rem --- Podprogramy --------------------------------------------------------------
rem :pickpanel PORT - port z naszym dzialajacym panelem albo wolny
:pickpanel
call :isours %1
if not errorlevel 1 (
    set "PANEL_PORT=%1"
    set "PANEL_RUNNING=1"
    exit /b 0
)
call :isfree %1
if not errorlevel 1 set "PANEL_PORT=%1"
exit /b 0

rem :pickapi PORT - port z naszym dzialajacym API albo wolny
:pickapi
call :isours %1
if not errorlevel 1 (
    set "API_PORT=%1"
    set "API_RUNNING=1"
    exit /b 0
)
call :isfree %1
if not errorlevel 1 set "API_PORT=%1"
exit /b 0

rem :isours PORT - 0, gdy pod portem odpowiada API tego projektu (bezposrednio albo przez panel)
:isours
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:%1/api/health'; if ($r.Content -match 'llm_provider') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
exit /b %errorlevel%

rem :isfree PORT - 0, gdy nic nie nasluchuje na porcie
:isfree
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %1 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }" >nul 2>nul
exit /b %errorlevel%
