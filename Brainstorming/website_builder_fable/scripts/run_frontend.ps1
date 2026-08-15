# Runs the Vite dev server on port 5300 (installs node_modules if missing).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"

Set-Location $frontend
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    npm install --no-audit --no-fund
}
npm run dev
