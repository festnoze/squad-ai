@echo off
REM ---------------------------------------------------------------------------
REM  AllAllowed - start the API and the replay dashboard together.
REM  Opens two windows: the ala API (8165) and the Vite web UI (5500), then
REM  opens the dashboard in your browser. Close either window to stop it.
REM
REM  Optional: run.bat 8166   to use a different API port (handy if 8165 is busy).
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "API_PORT=%~1"
if "%API_PORT%"=="" set "API_PORT=8165"
set "WEB_PORT=5500"
set "ALA_API=http://127.0.0.1:%API_PORT%"

if not exist ".venv\Scripts\python.exe" goto :no_venv

REM --- make sure at least one match exists so the picker is not empty ---------
if not exist "runs" mkdir runs
dir /b /a "runs" 2>nul | findstr /r /c:"." >nul
if not errorlevel 1 goto :have_runs
echo [setup] No matches found, generating a sample run...
.venv\Scripts\python.exe -m ala.cli match run --scenario concours --seed 42 --agents grinder,allier,raider,forger,parasite,mute --ticks 48 --cull-every 8 --out runs
:have_runs

REM --- install web dependencies once ------------------------------------------
if exist "web\node_modules" goto :have_web
echo [setup] Installing web dependencies (first run only)...
pushd web
call npm install
popd
:have_web

REM --- launch the two servers in their own windows ---------------------------
REM  Both windows inherit ALA_API from this script's environment, so the web
REM  proxy points at whatever API port was chosen above.
echo [start] API  =^> http://127.0.0.1:%API_PORT%
start "AllAllowed API %API_PORT%" /D "%~dp0" cmd /k ".venv\Scripts\python.exe -m ala.cli api serve --host 127.0.0.1 --port %API_PORT% --runs-dir runs"

echo [start] Web  =^> http://localhost:%WEB_PORT%
start "AllAllowed Web %WEB_PORT%" /D "%~dp0web" cmd /k "npm run dev"

REM --- give them a moment, then open the dashboard ---------------------------
timeout /t 5 /nobreak >nul
start "" "http://localhost:%WEB_PORT%"

echo.
echo Both servers are starting in separate windows.
echo    API : http://127.0.0.1:%API_PORT%
echo    Web : http://localhost:%WEB_PORT%
echo Close either window (or press Ctrl+C in it) to stop that server.
goto :eof

:no_venv
echo [error] Python venv not found at .venv
echo         Create it first, from this folder:
echo             py -3.12 -m venv .venv
echo             .venv\Scripts\python.exe -m pip install -e ".[dev]"
echo.
pause
