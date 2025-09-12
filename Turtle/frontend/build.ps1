#!/usr/bin/env pwsh

Write-Host "===============================" -ForegroundColor Green
Write-Host "Turtle Trading Frontend Build" -ForegroundColor Green
Write-Host "===============================" -ForegroundColor Green

Write-Host ""
Write-Host "[1/2] Running type check..." -ForegroundColor Yellow
$env:NODE_OPTIONS = ""
& npx tsc --noEmit
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Type check failed" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "[2/2] Building production bundle..." -ForegroundColor Yellow
$env:VITE_API_URL = "http://localhost:8000"
$env:VITE_WS_URL = "ws://localhost:8000" 
$env:NODE_ENV = "production"
$env:NODE_OPTIONS = ""

& npx vite build
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Build failed" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "===============================" -ForegroundColor Green
Write-Host "Build completed successfully!" -ForegroundColor Green
Write-Host "Output: dist/ folder" -ForegroundColor Green
Write-Host "===============================" -ForegroundColor Green