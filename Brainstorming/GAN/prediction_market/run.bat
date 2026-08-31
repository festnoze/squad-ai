@echo off
REM ---------------------------------------------------------------------------
REM  pmx - start the API and the backtest dashboard together.
REM  Opens two windows: the API (8175) and the Vite web UI (5510), then opens
REM  the dashboard in your browser. Optional: run.bat 8176 to use another port.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "API_PORT=%~1"
if "%API_PORT%"=="" set "API_PORT=8175"
set "WEB_PORT=5510"
set "PMX_API=http://127.0.0.1:%API_PORT%"

if not exist ".venv\Scripts\python.exe" goto :no_venv

if not exist "data\markets" mkdir data\markets
dir /b /a "data\markets" 2>nul | findstr /r /c:"." >nul
if not errorlevel 1 goto :have_data
echo [setup] Seeding the bundled markets...
.venv\Scripts\python.exe -m pmx.cli data seed --out data\markets
:have_data

if exist "web\node_modules" goto :have_web
echo [setup] Installing web dependencies (first run only)...
pushd web
call npm install
popd
:have_web

echo [start] API =^> http://127.0.0.1:%API_PORT%
start "pmx API %API_PORT%" /D "%~dp0" cmd /k ".venv\Scripts\python.exe -m pmx.cli api serve --host 127.0.0.1 --port %API_PORT% --data data\markets"

echo [start] Web =^> http://localhost:%WEB_PORT%
start "pmx Web %WEB_PORT%" /D "%~dp0web" cmd /k "npm run dev"

timeout /t 5 /nobreak >nul
start "" "http://localhost:%WEB_PORT%"

echo.
echo Both servers are starting in separate windows.
echo    API : http://127.0.0.1:%API_PORT%
echo    Web : http://localhost:%WEB_PORT%
goto :eof

:no_venv
echo [error] Python venv not found at .venv
echo         Create it first:
echo             py -3.12 -m venv .venv
echo             .venv\Scripts\python.exe -m pip install -e ".[dev]"
pause
