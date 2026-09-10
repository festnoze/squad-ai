# Control the voice bridge: toggle spoken answers, run the local TTS daemons,
# pick a voice, and read the last answer of a session on demand.
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
    [ValidateSet('on', 'off', 'toggle', 'status', 'start', 'stop', 'say', 'last', 'shut', 'use', 'demo', 'voices')]
    [string]$Action = 'status',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$stateDir = Join-Path $env:LOCALAPPDATA 'voice_bridge'
$toggle = Join-Path $stateDir 'enabled'
$speak = Join-Path $root 'speak.py'
$configFile = Join-Path $root 'config.json'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

function Get-Config {
    if (Test-Path $configFile) { return Get-Content $configFile -Raw | ConvertFrom-Json }
    return [pscustomobject]@{}
}

# Les deux moteurs locaux gardent leur modele en memoire dans un demon, chacun
# sur son port et avec son propre interpreteur : piper vit dans un outil uv,
# pocket dans .venv-pocket parce qu'il tire PyTorch.
function Get-Engine {
    param([string]$Backend)

    $cfg = Get-Config
    if (-not $Backend) { $Backend = if ($cfg.backend) { $cfg.backend } else { 'piper' } }

    switch ($Backend) {
        'pocket' {
            $voice = if ($cfg.pocket_voice) { $cfg.pocket_voice } else { 'estelle' }
            return @{
                Name   = 'pocket'
                Port   = 5112
                Script = Join-Path $root 'pocket_server.py'
                Python = Join-Path $root '.venv-pocket\Scripts\python.exe'
                Voice  = $voice
                Args   = @('--voice', $voice)
                Missing = "pocket-tts absent. Lance install.ps1 -WithPocket."
            }
        }
        'piper' {
            $voice = if ($cfg.piper_voice) { $cfg.piper_voice } else { 'fr_FR-siwis-medium' }
            return @{
                Name   = 'piper'
                Port   = 5111
                Script = Join-Path $root 'piper_server.py'
                Python = Join-Path $env:APPDATA 'uv\tools\piper-tts\Scripts\python.exe'
                Voice  = $voice
                Args   = @('--model', (Join-Path $root "voices\$voice.onnx"))
                Missing = "piper-tts absent. Lance install.ps1 d'abord."
            }
        }
        default { return $null }  # edge et sapi n'ont pas de demon
    }
}

function Get-DaemonVoice {
    param($Engine)
    try {
        return (Invoke-WebRequest -Uri "http://127.0.0.1:$($Engine.Port)/health" `
                -TimeoutSec 2 -UseBasicParsing).Content
    } catch { return $null }
}

function Test-Daemon {
    param($Engine)
    return $null -ne (Get-DaemonVoice $Engine)
}

function Get-DaemonProcesses {
    param($Engine)
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*$($Engine.Name)_server.py*" }
}

function Stop-Daemon {
    param($Engine = $null)
    $engines = if ($Engine) { @($Engine) } else { @((Get-Engine 'piper'), (Get-Engine 'pocket')) }
    foreach ($e in $engines) {
        # uv lance le vrai interpreteur via un trampoline : tuer le parent
        # emporte l'enfant, donc le second pid a souvent deja disparu.
        Get-DaemonProcesses $e | ForEach-Object {
            if (Stop-Process -Id $_.ProcessId -Force -PassThru -ErrorAction SilentlyContinue) {
                Write-Host "demon $($e.Name) arrete (pid $($_.ProcessId))"
            }
        }
    }
}

function Start-Daemon {
    param($Engine = $null)

    if (-not $Engine) { $Engine = Get-Engine }
    if (-not $Engine) { return }   # backend sans demon

    $loaded = Get-DaemonVoice $Engine
    if ($loaded) {
        if ($loaded -eq $Engine.Voice) {
            Write-Host "demon $($Engine.Name) deja en route (voix $loaded)"
            return
        }
        # Un demon ne tient qu'une voix : pour en changer il faut le relancer.
        Write-Host "changement de voix ($loaded -> $($Engine.Voice)), redemarrage"
        Stop-Daemon $Engine
        Start-Sleep -Seconds 1
    }
    if (-not (Test-Path $Engine.Python)) { Write-Warning $Engine.Missing; return }

    $log = Join-Path $stateDir "$($Engine.Name)_server.log"
    Start-Process -FilePath $Engine.Python `
        -ArgumentList (@($Engine.Script, '--port', $Engine.Port) + $Engine.Args) `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err"

    # Le modele met quelques secondes a charger : on sonde plutot que de parier.
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 500
        if (Test-Daemon $Engine) {
            Write-Host "demon $($Engine.Name) pret (port $($Engine.Port), voix $($Engine.Voice))"
            return
        }
    }
    Write-Warning "le demon $($Engine.Name) n'a pas repondu. Voir $log.err"
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

# Phrase de test : des accents, des liaisons, des nombres et du jargon, parce
# qu'une voix qui passe sur "bonjour" peut s'effondrer sur "la dépréciation".
$demoLine = "J'ai corrigé la dépréciation et relancé la suite : les cent un tests passent, il reste un avertissement."

$demoVoices = @(
    @{ Backend = 'pocket'; Voice = 'estelle' },
    @{ Backend = 'piper'; Voice = 'fr_FR-siwis-medium' },
    @{ Backend = 'piper'; Voice = 'fr_FR-tom-medium' },
    @{ Backend = 'piper'; Voice = 'fr_FR-upmc-medium' },
    @{ Backend = 'edge'; Voice = 'fr-FR-DeniseNeural' },
    @{ Backend = 'edge'; Voice = 'fr-FR-HenriNeural' },
    @{ Backend = 'edge'; Voice = 'fr-FR-VivienneMultilingualNeural' },
    @{ Backend = 'sapi'; Voice = 'Microsoft Julie' }
)

# Les 26 embeddings livres avec le modele francais. L'origine du locuteur est
# ce qui predit l'accent en francais : seule estelle vient d'une source
# francaise, les VCTK sont des voix britanniques.
$pocketVoices = [ordered]@{
    'estelle'        = @{ G = 'F'; Origine = 'francaise (site Kyutai)' }
    'cosette'        = @{ G = 'F'; Origine = 'corpus Expresso' }
    'alba'           = @{ G = 'F'; Origine = 'Alba Mackenna' }
    'caro_davy'      = @{ G = 'F'; Origine = 'corpus voice-zero' }
    'anna'           = @{ G = 'F'; Origine = 'VCTK p228' }
    'vera'           = @{ G = 'F'; Origine = 'VCTK p229' }
    'fantine'        = @{ G = 'F'; Origine = 'VCTK p244' }
    'eponine'        = @{ G = 'F'; Origine = 'VCTK p262' }
    'azelma'         = @{ G = 'F'; Origine = 'VCTK p303' }
    'mary'           = @{ G = 'F'; Origine = 'VCTK p333' }
    'jane'           = @{ G = 'F'; Origine = 'VCTK p339' }
    'eve'            = @{ G = 'F'; Origine = 'VCTK p361' }
    'lola'           = @{ G = 'F'; Origine = 'Common Voice espagnol' }
    'jean'           = @{ G = 'H'; Origine = 'corpus EARS p010' }
    'marius'         = @{ G = 'H'; Origine = 'don de voix' }
    'javert'         = @{ G = 'H'; Origine = 'don de voix' }
    'charles'        = @{ G = 'H'; Origine = 'VCTK p254' }
    'paul'           = @{ G = 'H'; Origine = 'VCTK p259' }
    'george'         = @{ G = 'H'; Origine = 'VCTK p315' }
    'michael'        = @{ G = 'H'; Origine = 'VCTK p360' }
    'bill_boerst'    = @{ G = 'H'; Origine = 'corpus voice-zero' }
    'peter_yearsley' = @{ G = 'H'; Origine = 'corpus voice-zero' }
    'stuart_bell'    = @{ G = 'H'; Origine = 'corpus voice-zero' }
    'giovanni'       = @{ G = 'H'; Origine = 'Common Voice italien' }
    'juergen'        = @{ G = 'H'; Origine = 'source allemande' }
    'rafael'         = @{ G = 'H'; Origine = 'source portugaise' }
}

function Show-PocketVoices {
    $current = (Get-Config).pocket_voice
    Write-Host "26 voix livrees avec le modele francais. Choisir avec:  .\voice.ps1 use pocket <nom>"
    Write-Host ''
    foreach ($name in $pocketVoices.Keys) {
        $mark = if ($name -eq $current) { '*' } else { ' ' }
        Write-Host ("{0} {1,-16} {2}  {3}" -f $mark, $name, $pocketVoices[$name].G, $pocketVoices[$name].Origine)
    }
    Write-Host ''
    Write-Host "Au-dela de ces 26, le clonage depuis un .wav exige le depot HuggingFace"
    Write-Host "kyutai/pocket-tts, qui est sous acces controle : accepter les conditions"
    Write-Host "sur la page du modele puis definir HF_TOKEN."
}

function Set-Voice {
    param([string]$NewBackend, [string]$NewVoice)

    $config = @{}
    if (Test-Path $configFile) {
        $config = Get-Content $configFile -Raw | ConvertFrom-Json -AsHashtable
    }
    $config['backend'] = $NewBackend
    if ($NewVoice) { $config["${NewBackend}_voice"] = $NewVoice }

    $config | ConvertTo-Json -Depth 5 | Set-Content $configFile -Encoding UTF8
    Write-Host "moteur : $NewBackend$(if ($NewVoice) { " / $NewVoice" })"
    Write-Host "ecrit dans $configFile"

    # Un demon ne tient qu'une voix : sans redemarrage il refuserait chaque
    # requete et tout retomberait sur le chemin lent.
    Start-Daemon (Get-Engine $NewBackend)
}

function Invoke-Demo {
    Write-Host "Ecoute, puis fige ton choix avec:  .\voice.ps1 use <moteur> <voix>"
    Write-Host ''
    foreach ($candidate in $demoVoices) {
        $label = "$($candidate.Backend) / $($candidate.Voice)"
        Write-Host "  $label"
        # --raw: on veut entendre la phrase entiere, pas l'extrait d'une reponse.
        # speak.py ne rend la main qu'a la fin de la lecture (il tient le
        # verrou de voix), la pause ne sert plus qu'a separer les voix.
        & python $speak --raw --backend $candidate.Backend --voice $candidate.Voice --text "$($candidate.Backend). $demoLine"
        Start-Sleep -Seconds 1
    }
    & python $speak --stop
}

function Enable-Voice {
    Set-Content -Path $toggle -Value '1' -NoNewline
    Start-Daemon
    Write-Host "VOIX ACTIVEE - les reponses de Claude Code seront lues"
}

function Disable-Voice {
    Remove-Item $toggle -ErrorAction SilentlyContinue
    & python $speak --stop 2>$null | Out-Null
    Write-Host "VOIX COUPEE (le demon reste chaud, .\voice.ps1 stop pour le tuer)"
}

switch ($Action) {
    'on' { Enable-Voice }
    'off' { Disable-Voice }
    'toggle' {
        if (Test-Path $toggle) { Disable-Voice } else { Enable-Voice }
    }
    'start' { Start-Daemon }
    'stop' { Stop-Daemon }
    'shut' { & python $speak --stop }
    'demo' { Invoke-Demo }
    'voices' { Show-PocketVoices }
    'use' {
        if (-not $Rest) {
            Write-Warning 'usage: .\voice.ps1 use <piper|edge|sapi> [voix]'
            break
        }
        Set-Voice -NewBackend $Rest[0] -NewVoice ($Rest[1..($Rest.Count - 1)] -join ' ')
    }
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
        $cfg = Get-Config
        $backend = if ($cfg.backend) { $cfg.backend } else { 'piper' }
        Write-Host "voix    : $(if (Test-Path $toggle) { 'ACTIVEE' } else { 'desactivee' })"
        Write-Host "moteur  : $backend"
        foreach ($name in 'piper', 'pocket') {
            $e = Get-Engine $name
            $loaded = Get-DaemonVoice $e
            $mark = if ($name -eq $backend) { '*' } else { ' ' }
            $state = if ($loaded) { "en route, voix $loaded (port $($e.Port))" } else { 'arrete' }
            Write-Host "$mark demon $($e.Name.PadRight(6)) : $state"
        }
    }
}
