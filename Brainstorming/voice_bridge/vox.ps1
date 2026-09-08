# Filtre générique : tout ce qui passe dedans est réémis tel quel, puis lu.
# Pour les modèles qui n'ont aucun hook - Ollama, une API, un script maison.
#
#   ollama run ministral-3:8b "explique X" | vox
#   codex exec "resume le diff" | vox
#   curl -s ... | jq -r .answer | vox
#
# Ajoute ceci à ton $PROFILE pour avoir `vox` partout :
#   function vox { $input | & "C:\Dev\squad-ai\Brainstorming\voice_bridge\vox.ps1" @args }

[CmdletBinding()]
param(
    # Sous CmdletBinding, un script ne reçoit le pipeline que par un paramètre
    # qui le déclare : sans ça, PowerShell refuse l'entrée au lieu de l'ignorer.
    [Parameter(ValueFromPipeline = $true)]
    [string[]]$InputObject,

    [ValidateSet('piper', 'edge', 'sapi')]
    [string]$Backend
)

begin { $lines = [System.Collections.Generic.List[string]]::new() }

process { foreach ($line in $InputObject) { $lines.Add($line) } }

end {
    $text = $lines -join "`n"
    if ([string]::IsNullOrWhiteSpace($text)) { return }

    $speak = Join-Path $PSScriptRoot 'speak.py'
    $cliArgs = @($speak, '--tee')
    if ($Backend) { $cliArgs += @('--backend', $Backend) }

    $text | & python @cliArgs
}
