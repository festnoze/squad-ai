<#
.SYNOPSIS
    Builds the Windows player of UN, DEUX, TROIS, MEUBLE and launches it.

.DESCRIPTION
    The build goes through tools/unity.sh, the same Unity lock and fair queue as verify.sh and the agents, so it
    waits its turn instead of colliding with another Unity run. It builds into Build/Play/ (never Build/Windows/,
    which verify.sh rebuilds and probes), then starts the game.

    The Unity Editor must not have this project open: Unity refuses a second editor on the same project.

.PARAMETER NoBuild
    Launches the last build without rebuilding.

.PARAMETER Run
    Runs the release (non debug) build in Build/Play/: launches it if it exists, builds it first otherwise.
    This is what run.cmd does.

.PARAMETER Dev
    Builds a Development Build with script debugging into Build/PlayDev/ (the release build in Build/Play/ is
    never replaced by it), so Visual Studio 2022 can attach to the running player (Debug > Attach Unity
    Debugger). The development console shows errors in the corner of the screen.

.PARAMETER WaitForDebugger
    With -Dev: the player waits at startup until Visual Studio attaches.

.PARAMETER Windowed
    Starts the game in a 1600 x 900 window instead of full screen.

.EXAMPLE
    .\play.cmd                      build, then play
    .\play.cmd -NoBuild             play the last build
    .\play.cmd -Dev -Windowed       debuggable build, in a window
    .
    .\run.cmd                       play the release build (built once if missing)
#>
param(
    [switch]$NoBuild,
    [switch]$Run,
    [switch]$Dev,
    [switch]$WaitForDebugger,
    [switch]$Windowed
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if ($Run -and $Dev) { throw "-Run plays the release build; use play.cmd -Dev for a debuggable one." }
$folder = if ($Dev) { 'PlayDev' } else { 'Play' }
$exe = Join-Path $project "Build\$folder\Meuble.exe"
$log = Join-Path $project "Build\$($folder.ToLower())_build.log"
if ($Run -and (Test-Path $exe)) { $NoBuild = $true }

if (-not $NoBuild) {
    $bash = @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $bash) {
        throw "Git Bash is required to build (tools/unity.sh). Install Git for Windows, or use -NoBuild."
    }
    New-Item -ItemType Directory -Force (Join-Path $project 'Build') | Out-Null

    $unityArgs = @('-executeMethod', 'Meuble.Editor.Builder.BuildWindows', '-output', "Build/$folder/Meuble.exe", '-logFile', (Split-Path $log -Leaf | ForEach-Object { "Build/$_" }))
    if ($Dev) { $unityArgs += '-development' }
    if ($Dev -and $WaitForDebugger) { $unityArgs += '-waitForDebugger' }

    Write-Host "Building the Windows player into Build\$folder (log: $log)..."
    Write-Host "If an agent or verify.sh holds Unity, the build waits in the queue."
    Push-Location $project
    try {
        $env:MEUBLE_AGENT = 'play'
        & $bash tools/unity.sh run . --timeout 1800 -- @unityArgs
        $code = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($code -ne 0 -or -not (Test-Path $exe)) {
        if (Test-Path $log) {
            Select-String -Path $log -Pattern 'error CS|\[Builder\]|Build failed' | Select-Object -Last 15 | ForEach-Object { Write-Host $_.Line }
        }
        throw "The build failed (Unity exit code $code). See $log."
    }
    Write-Host "Build ready: $exe"
}

if (-not (Test-Path $exe)) {
    throw "No build in Build\$folder yet: run play.cmd without -NoBuild first."
}

$gameArgs = @()
if ($Windowed) { $gameArgs += @('-screen-fullscreen', '0', '-screen-width', '1600', '-screen-height', '900') }
Write-Host "Launching the game..."
if ($gameArgs.Count -gt 0) {
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) -ArgumentList $gameArgs
}
else {
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe)
}
