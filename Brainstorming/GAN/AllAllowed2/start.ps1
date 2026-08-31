$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python environment missing. Follow the install steps in README.md first.'
}

$apiProcess = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList '-m', 'uvicorn', 'server.main:app', '--host', '127.0.0.1', '--port', '8500', '--reload' `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -PassThru

try {
    Set-Location (Join-Path $projectRoot 'web')
    npm run dev
}
finally {
    if (-not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id
    }
}
