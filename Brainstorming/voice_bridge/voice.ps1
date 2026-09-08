# Control the voice bridge: toggle spoken answers, run the Piper daemon,
# and read the last answer of a session on demand.
#
#   .\voice.ps1 on            spoken answers on (starts the daemon if needed)
#   .\voice.ps1 off           spoken answers off
#   .\voice.ps1 status        what is running
#   .\voice.ps1 start|stop    daemon only
#   .\voice.ps1 say "texte"   speak this now
#   .\voice.ps1 last          speak the last Claude Code answer of this folder
#   .\voice.ps1 shut          cut the current playback

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('on', 'off', 'status', 'start', 'stop', 'say', 'last', 'shut')]
    [string]$Action = 'status',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$stateDir = Join-Path $env:LOCALAPPDATA 'voice_bridge'
$toggle = Join-Path $stateDir 'enabled'
$daemonLog = Join-Path $stateDir 'piper_server.log'
$speak = Join-Path $root 'speak.py'
$server = Join-Path $root 'piper_server.py'
$piperPython = Join-Path $env:APPDATA 'uv\tools\piper-tts\Scripts\python.exe'
$port = 5111

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

function Test-Daemon {
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2 -UseBasicParsing
        return $true
    } catch { return $false }
}

function Get-DaemonProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*piper_server.py*' }
}

function Start-Daemon {
    if (Test-Daemon) { Write-Host "demon deja en route sur le port $port"; return }
    if (-not (Test-Path $piperPython)) {
        Write-Warning "piper-tts absent. Lance install.ps1 d'abord."
        return
    }
    Start-Process -FilePath $piperPython `
        -ArgumentList @($server, '--port', $port) `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput $daemonLog -RedirectStandardError "$daemonLog.err"

    # The model takes a few seconds to load; poll rather than guess.
    foreach ($i in 1..40) {
        Start-Sleep -Milliseconds 500
        if (Test-Daemon) { Write-Host "demon pret (port $port)"; return }
    }
    Write-Warning "le demon n'a pas repondu. Voir $daemonLog.err"
}

function Stop-Daemon {
    Get-DaemonProcesses | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host "demon arrete (pid $($_.ProcessId))"
    }
}

function Invoke-Speak {
    param([string]$Text, [switch]$Raw)
    $cliArgs = @($speak)
    if ($Raw) { $cliArgs += '--raw' }
    $Text | & python @cliArgs
}

function Get-LastClaudeAnswer {
    # Claude Code stores one JSONL transcript per session, in a folder named
    # after the project path with separators flattened to dashes.
    $slug = ($PWD.Path -replace '[:\\/]', '-').TrimStart('-')
    $dir = Join-Path $env:USERPROFILE ".claude\projects\$slug"
    if (-not (Test-Path $dir)) { Write-Warning "aucune session pour $PWD"; return $null }

    $session = Get-ChildItem $dir -Filter '*.jsonl' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $session) { Write-Warning "aucun transcript dans $dir"; return $null }

    $text = $null
    foreach ($line in [System.IO.File]::ReadLines($session.FullName)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { $entry = $line | ConvertFrom-Json } catch { continue }
        if ($entry.type -ne 'assistant') { continue }
        $chunks = @($entry.message.content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text })
        if ($chunks.Count) { $text = ($chunks -join "`n") }
    }
    return $text
}

switch ($Action) {
    'on' {
        Set-Content -Path $toggle -Value '1' -NoNewline
        Start-Daemon
        Write-Host "voix ACTIVEE - les reponses seront lues"
    }
    'off' {
        Remove-Item $toggle -ErrorAction SilentlyContinue
        Write-Host "voix DESACTIVEE (le demon reste chaud, .\voice.ps1 stop pour le tuer)"
    }
    'start' { Start-Daemon }
    'stop' { Stop-Daemon }
    'shut' { & python $speak --stop }
    'say' {
        $text = ($Rest -join ' ')
        if (-not $text) { Write-Warning 'rien a dire'; break }
        Invoke-Speak -Text $text -Raw
    }
    'last' {
        $text = Get-LastClaudeAnswer
        if ($text) { Invoke-Speak -Text $text }
    }
    'status' {
        $on = Test-Path $toggle
        $up = Test-Daemon
        Write-Host "voix        : $(if ($on) { 'ACTIVEE' } else { 'desactivee' })"
        Write-Host "demon piper : $(if ($up) { "en route (port $port)" } else { 'arrete' })"
        Get-DaemonProcesses | ForEach-Object { Write-Host "              pid $($_.ProcessId)" }
    }
}
