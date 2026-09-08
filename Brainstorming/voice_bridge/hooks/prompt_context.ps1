# UserPromptSubmit hook: teach the agent the <voix> convention, but only while
# spoken answers are on.
#
# Without this, the Stop hook has to guess which sentences matter and falls back
# to reading the closing paragraph. With it, the agent writes its own one-line
# spoken summary and the written answer stays as detailed as usual.
#
# The wording lives in consigne_vocale.md so it can be tuned without touching
# this script. Edit that file and the next prompt picks it up.

$ErrorActionPreference = 'Stop'

$toggle = Join-Path (Join-Path $env:LOCALAPPDATA 'voice_bridge') 'enabled'
if (-not (Test-Path $toggle)) { exit 0 }

$consigne = Join-Path (Split-Path -Parent $PSScriptRoot) 'consigne_vocale.md'

# Drain stdin: the agent sends the payload whether or not we read it, and
# leaving it unread can block the writer on a full pipe.
$null = [Console]::In.ReadToEnd()

if (Test-Path $consigne) {
    # ReadAllText plutot que Get-Content -Raw : ce dernier decore la chaine de
    # proprietes PowerShell (PSPath, PSProvider...) que ConvertTo-Json serialise
    # en objet, et le champ additionalContext doit etre une chaine.
    $context = [System.IO.File]::ReadAllText($consigne, [System.Text.Encoding]::UTF8)
} else {
    # Repli si le fichier a ete supprime : mieux vaut une consigne minimale
    # qu'un mode vocal qui lit le dernier paragraphe au hasard.
    $context = @'
Le mode vocal est actif : la fin de ta reponse sera lue a voix haute en francais.
Termine chaque reponse par une ligne <voix>...</voix> contenant UNE phrase parlee :
ce que tu as fait ou ce que tu attends, sans markdown, sans chemin de fichier,
sans nom de symbole. Le reste de ta reponse ne change pas.
'@
}

if ([string]::IsNullOrWhiteSpace($context)) { exit 0 }

$payload = @{
    hookSpecificOutput = @{
        hookEventName     = 'UserPromptSubmit'
        additionalContext = $context
    }
}

$payload | ConvertTo-Json -Depth 5 -Compress
exit 0
