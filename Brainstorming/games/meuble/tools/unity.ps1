# Runs the Unity CLI with an exclusive lock on this project: the PowerShell twin of tools/unity.sh, for when Git Bash
# hangs. Unity refuses to open a project another editor holds, so every agent goes through one lock directory.
#
# Usage (one string, arguments split on spaces, so no argument may contain a space):
#   pwsh -NoProfile -File tools/unity.ps1 -Agent <name> -UnityArgs "run . --timeout 1800 -- -executeMethod OutOfSight.Editor.Builder.SetupAndCompile -logFile Build/x.log"
#   pwsh -NoProfile -File tools/unity.ps1 -Agent <name> -UnityArgs "test . --mode PlayMode --filter Step65a_|Step26_ --report-format junit --output TestResults/x.xml --timeout 1800"
param(
    [Parameter(Mandatory = $true)][string]$UnityArgs,
    [string]$Agent = "shell"
)

$project = Split-Path -Parent $PSScriptRoot
$lock = Join-Path $project ".unity.lock"
$owner = Join-Path $lock "owner"

while ($true) {
    if (New-Item -ItemType Directory -Path $lock -ErrorAction SilentlyContinue) {
        break
    }
    # A lock whose owner process is gone (or that never got an owner within a minute) is stale.
    $ownerPid = $null
    if (Test-Path $owner) {
        $ownerPid = ((Get-Content $owner -ErrorAction SilentlyContinue | Select-Object -First 1) -split ' ')[0]
    }
    $age = (Get-Date) - (Get-Item $lock -ErrorAction SilentlyContinue).CreationTime
    if (($ownerPid -and -not (Get-Process -Id $ownerPid -ErrorAction SilentlyContinue)) -or (-not $ownerPid -and $age.TotalSeconds -gt 60)) {
        Remove-Item $lock -Recurse -Force -ErrorAction SilentlyContinue
        continue
    }
    Start-Sleep -Seconds 10
}

$code = 1
try {
    "$PID $Agent $UnityArgs" | Set-Content $owner
    $env:UNITY_NO_BANNER = 1
    $env:UNITY_NON_INTERACTIVE = 1
    Set-Location $project
    $argv = $UnityArgs -split '\s+' | Where-Object { $_ -ne '' }
    & "$env:LOCALAPPDATA\Unity\bin\unity.exe" @argv
    $code = $LASTEXITCODE
}
finally {
    Remove-Item $lock -Recurse -Force -ErrorAction SilentlyContinue
}
exit $code
