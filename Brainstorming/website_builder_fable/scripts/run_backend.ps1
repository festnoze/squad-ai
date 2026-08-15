# Runs the FastAPI backend on port 8300 (activates the venv first).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$activate = Join-Path $backend ".venv\Scripts\Activate.ps1"

if (-not (Test-Path $activate)) {
    Write-Error "Venv not found. Create it first: python -m venv `"$backend\.venv`" then pip install -r `"$backend\requirements.txt`""
}

Set-Location $backend
& $activate
uvicorn app.main:app --host 127.0.0.1 --port 8300 --reload
