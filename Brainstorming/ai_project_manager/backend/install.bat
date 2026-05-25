@echo off
REM ---------------------------------------------------------------------------
REM install.bat — one-shot setup of the AI Project Manager backend.
REM
REM What it does (in order):
REM   1. Creates backend/venv if it doesn't already exist.
REM   2. Activates the venv for the current cmd session.
REM   3. Reads COMMONTOOLS_LOCAL_PATH from backend/.env (falls back to a
REM      sensible default if the file or the key is missing).
REM   4. pip install -e "<commontools path>"
REM   5. pip install -e ".[dev]"
REM
REM Usage:  double-click the file, or run `install.bat` from cmd/PowerShell in
REM         the backend folder.
REM
REM All commands are run from %~dp0 (the folder containing this script), so
REM it doesn't matter where you invoke it from.
REM ---------------------------------------------------------------------------

setlocal EnableDelayedExpansion

REM Always run relative to this script's folder.
pushd "%~dp0"

REM -- 1. Ensure venv exists --------------------------------------------------
if not exist "venv\Scripts\python.exe" (
    echo.
    echo [install] No venv found at backend\venv — creating one with the
    echo [install] default "python" on PATH...
    python -m venv venv
    if errorlevel 1 (
        echo [install] ERROR: failed to create venv. Is Python 3.12+ on PATH?
        popd
        exit /b 1
    )
) else (
    echo [install] Reusing existing venv at backend\venv
)

REM -- 2. Activate venv -------------------------------------------------------
call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [install] ERROR: failed to activate venv.
    popd
    exit /b 1
)

REM -- 3. Resolve COMMONTOOLS_LOCAL_PATH --------------------------------------
REM Prefer the value declared in .env; fall back to a hard-coded default
REM matching the one shipped in .env.example.
set "COMMONTOOLS_PATH="
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /I "%%A"=="COMMONTOOLS_LOCAL_PATH" set "COMMONTOOLS_PATH=%%B"
    )
)

if "!COMMONTOOLS_PATH!"=="" (
    set "COMMONTOOLS_PATH=C:/Dev/IA/AzureDevOps/ai-commun-tools"
    echo [install] COMMONTOOLS_LOCAL_PATH not set in .env — using default:
    echo [install]     !COMMONTOOLS_PATH!
) else (
    echo [install] COMMONTOOLS_LOCAL_PATH from .env: !COMMONTOOLS_PATH!
)

REM Basic sanity check — the folder must exist, otherwise pip install -e would
REM fail with a cryptic message.
if not exist "!COMMONTOOLS_PATH!" (
    echo [install] ERROR: the path "!COMMONTOOLS_PATH!" does not exist.
    echo [install] Update COMMONTOOLS_LOCAL_PATH in backend\.env and retry.
    popd
    exit /b 1
)

REM -- 4. pip install common-tools (editable) --------------------------------
echo.
echo [install] Step 1/2: installing common-tools in editable mode...
python -m pip install -e "!COMMONTOOLS_PATH!"
if errorlevel 1 (
    echo [install] ERROR: failed to install common-tools from "!COMMONTOOLS_PATH!".
    popd
    exit /b 1
)

REM -- 5. pip install project + dev deps -------------------------------------
echo.
echo [install] Step 2/2: installing ai-project-manager-backend ^(editable, [dev]^)...
python -m pip install -e ".[dev]"
if errorlevel 1 (
    echo [install] ERROR: failed to install the backend project.
    popd
    exit /b 1
)

echo.
echo [install] Done. The venv at backend\venv is ready.
echo [install] Next steps:
echo [install]     1. Copy .env.example to .env and set OPENAI_API_KEY (if not already done).
echo [install]     2. Run:  alembic upgrade head
echo [install]     3. Run:  uvicorn app.main:app --reload
echo.

popd
endlocal
