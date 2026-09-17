@echo off
REM Start the complete local MVP on one port. Stop it with Ctrl+C.
setlocal
cd /d "%~dp0"
set "MVP_PORT=%~1"
if "%MVP_PORT%"=="" set "MVP_PORT=8175"
if not exist ".venv\Scripts\python.exe" goto :no_venv
if not exist "web\node_modules" goto :no_web
echo [data] Preparing and verifying the local research snapshot...
.venv\Scripts\python.exe -m pmx.data.prepare_mvp
if errorlevel 1 goto :failed
echo [web] Building the interface...
pushd web
call npm.cmd run build
if errorlevel 1 (
    popd
    goto :failed
)
popd
echo [start] Open http://127.0.0.1:%MVP_PORT% in your browser.
echo [start] Keep this window open. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m pmx.cli mvp serve --port "%MVP_PORT%"
if errorlevel 1 goto :failed
exit /b 0
:no_venv
echo [error] Create the Python environment first; see README.md.
goto :failed
:no_web
echo [error] Run npm.cmd ci from the web directory first; see README.md.
goto :failed
:failed
echo [error] Startup failed. The error above identifies the required action.
pause
exit /b 1
