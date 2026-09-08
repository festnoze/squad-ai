# UserPromptSubmit hook: teach the agent the <voix> convention, but only while
# spoken answers are on.
#
# Without this, the Stop hook has to guess which sentences matter and falls back
# to reading the closing paragraph. With it, the agent writes its own one-line
# spoken summary and the written answer stays as detailed as usual.

$ErrorActionPreference = 'Stop'

$toggle = Join-Path (Join-Path $env:LOCALAPPDATA 'voice_bridge') 'enabled'
if (-not (Test-Path $toggle)) { exit 0 }

# Drain stdin: the agent sends the payload whether or not we read it, and
# leaving it unread can block the writer on a full pipe.
$null = [Console]::In.ReadToEnd()

$context = @'
Le mode vocal est actif : la fin de ta reponse sera lue a voix haute en francais.
Termine chaque reponse par une ligne <voix>...</voix> contenant UNE phrase parlee :
ce que tu as fait ou ce que tu attends, sans markdown, sans chemin de fichier,
sans nom de symbole. Le reste de ta reponse ne change pas.
'@

$payload = @{
    hookSpecificOutput = @{
        hookEventName     = 'UserPromptSubmit'
        additionalContext = $context
    }
}

$payload | ConvertTo-Json -Depth 5 -Compress
exit 0
