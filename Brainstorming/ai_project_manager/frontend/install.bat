@echo off
REM ---------------------------------------------------------------------------
REM install.bat — one-shot setup of the AI Project Manager frontend.
REM
REM What it does:
REM   1. Checks that Node.js is on PATH (fails fast with a friendly message).
REM   2. Runs `npm install` in the frontend folder.
REM
REM Usage: double-click the file, or run `install.bat` from cmd/PowerShell in
REM        the frontend folder.
REM ---------------------------------------------------------------------------

setlocal EnableDelayedExpansion

REM Always run relative to this script's folder.
pushd "%~dp0"

REM -- 1. Ensure Node is available -------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
    echo [install] ERROR: Node.js is not on PATH.
    echo [install] Install Node 18+ from https://nodejs.org and retry.
    popd
    exit /b 1
)

for /f "delims=" %%V in ('node --version') do set "NODE_VERSION=%%V"
echo [install] Using Node !NODE_VERSION!

REM -- 2. npm install --------------------------------------------------------
echo.
echo [install] Running `npm install`...
call npm install
if errorlevel 1 (
    echo [install] ERROR: npm install failed.
    popd
    exit /b 1
)

echo.
echo [install] Done. The frontend is ready.
echo [install] Next step:  npm run dev
echo.

popd
endlocal
