# Stop hook for Claude Code and Codex: read the turn's final answer aloud.
#
# Both agents feed the hook a JSON payload on stdin. Claude Code puts the text
# in `last_assistant_message`; Codex exposes it under `payload.last_agent_message`
# depending on version, so we probe a few field names before giving up.
#
# The hook stays silent unless voice output is switched on, so it can live in
# settings permanently: `voice.ps1 on` / `voice.ps1 off` flips the toggle.

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $env:LOCALAPPDATA 'voice_bridge'
$toggle = Join-Path $stateDir 'enabled'

if (-not (Test-Path $toggle)) { exit 0 }

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }

try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }

$candidates = @(
    'last_assistant_message',
    'last_agent_message',
    'assistant_message',
    'message'
)

$text = $null
foreach ($field in $candidates) {
    foreach ($scope in @($payload, $payload.payload)) {
        if ($null -ne $scope -and $scope.PSObject.Properties.Name -contains $field) {
            $value = $scope.$field
            if (-not [string]::IsNullOrWhiteSpace($value)) { $text = $value; break }
        }
    }
    if ($text) { break }
}

if (-not $text) { exit 0 }

# Detached so the hook returns immediately: the agent must never wait on audio.
$speak = Join-Path $root 'speak.py'
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'python'
$psi.Arguments = "`"$speak`""
$psi.RedirectStandardInput = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)

# Write UTF-8 bytes straight to the stream. Setting StandardInputEncoding would
# be the obvious way, but that property only exists on .NET Core: under Windows
# PowerShell 5.1, which is what runs this hook, it throws and kills the hook.
$bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
$stream = $proc.StandardInput.BaseStream
$stream.Write($bytes, 0, $bytes.Length)
$stream.Flush()
$stream.Close()

exit 0
