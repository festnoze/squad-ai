# Install the voice bridge: TTS engines, the French voice, and (optionally)
# the agent hooks that read answers aloud.
#
#   .\install.ps1                 tools + voice only
#   .\install.ps1 -WireHooks      also wire Claude Code and Codex (backs up first)
#   .\install.ps1 -Unwire         remove the hooks again

[CmdletBinding()]
param(
    [switch]$WireHooks,
    [switch]$WithPocket,
    [switch]$Unwire
)

$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$stopHook = Join-Path $root 'hooks\stop_speak.ps1'
$promptHook = Join-Path $root 'hooks\prompt_context.ps1'
$claudeSettings = Join-Path $env:USERPROFILE '.claude\settings.json'
$codexHooks = Join-Path $env:USERPROFILE '.codex\hooks.json'
$marker = 'voice_bridge'

# ---------------------------------------------------------------- tools

function Install-Tools {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv est requis: https://docs.astral.sh/uv/"
    }
    foreach ($tool in 'piper-tts', 'edge-tts') {
        Write-Host "installation de $tool..."
        uv tool install $tool 2>&1 | Select-Object -Last 1
    }
    if (-not (Get-Command ffplay -ErrorAction SilentlyContinue)) {
        Write-Warning "ffplay introuvable (paquet ffmpeg). Le backend sapi marchera quand meme."
    }
}

function Install-Voice {
    param([string]$Name = 'fr_FR-siwis-medium')

    $dir = Join-Path $root 'voices'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $model = Join-Path $dir "$Name.onnx"
    if (Test-Path $model) { Write-Host "voix $Name deja presente"; return }

    # rhasspy/piper-voices lays voices out as <lang>/<locale>/<name>/<quality>/
    $parts = $Name -split '-'
    $locale = $parts[0]
    $lang = $locale.Split('_')[0]
    $base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/$lang/$locale/$($parts[1])/$($parts[2])/$Name"

    Write-Host "telechargement de $Name (~63 Mo)..."
    Invoke-WebRequest -Uri "$base.onnx" -OutFile $model
    Invoke-WebRequest -Uri "$base.onnx.json" -OutFile "$model.json"
}

function Install-Pocket {
    # Pocket TTS tire PyTorch, donc il vit dans son propre venv plutot que
    # dans l'outil uv de Piper. Le build CPU suffit et pese dix fois moins
    # que le build CUDA.
    $venv = Join-Path $root '.venv-pocket'
    if (Test-Path (Join-Path $venv 'Scripts\python.exe')) {
        Write-Host 'pocket-tts deja installe'
        return
    }
    Write-Host 'installation de pocket-tts (~1 Go, quelques minutes)...'
    uv venv --python 3.12 $venv 2>&1 | Select-Object -Last 1
    uv pip install --python (Join-Path $venv 'Scripts\python.exe') pocket-tts `
        --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | Select-Object -Last 1

    # Les poids se telechargent au premier chargement : autant payer maintenant.
    Write-Host 'telechargement des poids francais...'
    & (Join-Path $venv 'Scripts\python.exe') -c @'
from pocket_tts import TTSModel
m = TTSModel.load_model(language="french_24l")
m.get_state_for_audio_prompt("estelle")
print("poids prets")
'@
}

# ---------------------------------------------------------------- hooks

function Backup-File {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Copy-Item $Path "$Path.$stamp.bak"
    Write-Host "sauvegarde: $Path.$stamp.bak"
}

function New-HookEntry {
    param(
        [string]$Script,
        [ValidateSet('claude', 'codex')][string]$Style
    )
    # The two agents do NOT share a hook format. Claude Code takes exec form
    # (command + args array); Codex takes a single shell string and reports
    # "hook: Stop Failed" if handed the exec form.
    if ($Style -eq 'codex') {
        return [ordered]@{
            type    = 'command'
            command = "& `"powershell.exe`" -NoProfile -ExecutionPolicy Bypass -File `"$Script`""
            timeout = 15
        }
    }
    [ordered]@{
        type    = 'command'
        command = 'powershell.exe'
        args    = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Script)
        timeout = 15
    }
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @{} }
    $raw = Get-Content $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) { return @{} }
    return $raw | ConvertFrom-Json -AsHashtable
}

function Write-JsonFile {
    param([string]$Path, $Data)
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    $Data | ConvertTo-Json -Depth 20 | Set-Content -Path $Path -Encoding UTF8
}

function Remove-OurHooks {
    param($Config)
    if (-not $Config.hooks) { return $Config }
    foreach ($event in @($Config.hooks.Keys)) {
        $kept = @()
        foreach ($group in $Config.hooks[$event]) {
            # Match on both shapes: our path can sit in `args` or inside `command`.
            $inner = @($group.hooks | Where-Object {
                    "$($_.command) $($_.args -join ' ')" -notlike "*$marker*"
                })
            if ($inner.Count) { $group.hooks = $inner; $kept += $group }
        }
        if ($kept.Count) { $Config.hooks[$event] = $kept } else { $Config.hooks.Remove($event) }
    }
    return $Config
}

function Add-Hook {
    param($Config, [string]$Event, [string]$Script, [string]$Style)
    if (-not $Config.hooks) { $Config.hooks = @{} }
    if (-not $Config.hooks[$Event]) { $Config.hooks[$Event] = @() }
    $Config.hooks[$Event] = @($Config.hooks[$Event]) + @{
        matcher = ''
        hooks   = @(New-HookEntry -Script $Script -Style $Style)
    }
    return $Config
}

function Set-AgentHooks {
    param([switch]$Remove)

    $targets = @(
        @{ Path = $claudeSettings; Style = 'claude' },
        @{ Path = $codexHooks; Style = 'codex' }
    )

    foreach ($target in $targets) {
        Backup-File $target.Path
        $config = Read-JsonFile $target.Path
        $config = Remove-OurHooks $config
        if (-not $Remove) {
            $config = Add-Hook $config 'Stop' $stopHook $target.Style
            $config = Add-Hook $config 'UserPromptSubmit' $promptHook $target.Style
        }
        Write-JsonFile $target.Path $config
        Write-Host "$(if ($Remove) { 'retire de' } else { 'branche dans' }) $($target.Path)"
    }

    if (-not $Remove) {
        Write-Host ''
        Write-Host "Cote Codex, deux etapes de plus:" -ForegroundColor Yellow
        Write-Host "  1. lance 'codex' en interactif une fois et reponds 'Trust all and continue'" -ForegroundColor Yellow
        Write-Host "     (sans cette confiance, Codex ignore TOUS les hooks en silence)" -ForegroundColor Yellow
        Write-Host "  2. hooks.json est reecrit par le plugin GitKraken: si la voix se tait," -ForegroundColor Yellow
        Write-Host "     relance install.ps1 -WireHooks puis refais la confiance." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------- main

if ($Unwire) {
    Set-AgentHooks -Remove
    return
}

Install-Tools
Install-Voice
if ($WithPocket) { Install-Pocket }
if ($WireHooks) { Set-AgentHooks }

Write-Host ''
Write-Host "Pret. Active la voix avec:  .\voice.ps1 on" -ForegroundColor Green
