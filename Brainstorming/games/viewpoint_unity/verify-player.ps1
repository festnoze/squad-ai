# VIEWPOINT - verify the game in a BUILT PLAYER, not in the editor.
#
# This step exists because its absence cost a working build. Every EditMode and
# PlayMode test runs inside the Unity editor, where Shader.Find resolves every
# shader in the project and TextMeshPro tolerates a missing settings asset. A
# player has neither luxury:
#
#   - shaders no ASSET references are STRIPPED from the build, and this game
#     creates every material at run time through Shader.Find, so URP/Lit,
#     URP/Unlit and the sky shader all came back null: the world rendered
#     invisible and the sky fell back to Unity's default, which looked like a
#     lone horizon line;
#   - TextMeshPro throws out of TMP_Settings the moment a label is added, which
#     killed Hud.Awake, then Main.Awake, so no player, no level root, no
#     rewind - and the symptom read as "the levels are empty".
#
# 130 green tests said nothing about any of it. So: build, run, and read what
# the game says about itself.
#
#   ./verify-player.ps1

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
$env:PATH = "$env:LOCALAPPDATA\Unity\bin;$env:PATH"
$env:UNITY_NO_BANNER = "1"
$env:UNITY_NO_PAGER = "1"
$env:UNITY_NON_INTERACTIVE = "1"

$results = Join-Path $project "TestResults"
New-Item -ItemType Directory -Force $results | Out-Null
$failed = 0

function Fail($message) {
    Write-Host "  ECHEC $message"
    $script:failed = 1
}

Write-Host ""
Write-Host "=== 1. Build du player ==="
& unity run $project -- -executeMethod Viewpoint.Editor.Builder.BuildWindows 2>&1 |
    Out-File (Join-Path $results "build.log") -Encoding utf8
$exe = Join-Path $project "Build\Windows\VIEWPOINT.exe"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $exe)) {
    Fail "le build a echoue (code $LASTEXITCODE)"
    Select-String -Path (Join-Path $results "build.log") -Pattern "error CS|Build failed" |
        Select-Object -First 20 | ForEach-Object { "    " + $_.Line }
    exit 1
}
Write-Host ("  player construit ({0:N1} MB)" -f ((Get-Item $exe).Length / 1MB))

Write-Host ""
Write-Host "=== 2. Le jeu tourne et se photographie ==="
$shots = Join-Path $project "Build\Windows\Shots"
if (Test-Path $shots) { Get-ChildItem $shots -File | ForEach-Object { $_.Delete() } }

$proc = Start-Process -FilePath $exe -PassThru -ArgumentList @(
    "--shot", "-screen-width", "1280", "-screen-height", "720", "-screen-fullscreen", "0")
$proc | Wait-Process -Timeout 300 -ErrorAction SilentlyContinue
if (-not $proc.HasExited) {
    $proc | Stop-Process -Force
    Fail "le jeu ne s'est jamais termine (300 s)"
} elseif ($proc.ExitCode -ne 0) {
    Fail "le jeu est sorti avec le code $($proc.ExitCode)"
} else {
    Write-Host "  le jeu a demarre, joue et quitte proprement"
}

Write-Host ""
Write-Host "=== 3. Aucune exception dans le player ==="
# Not a nicety: an exception in Awake aborts the rest of it, so one broken
# subsystem silently takes the whole game with it.
$log = Join-Path $env:USERPROFILE "AppData\LocalLow\DefaultCompany\VIEWPOINT\Player.log"
if (-not (Test-Path $log)) {
    Fail "aucun journal de player a $log"
} else {
    $exceptions = @(Get-Content $log | Select-String -Pattern "Exception|error CS")
    if ($exceptions.Count -gt 0) {
        Fail "$($exceptions.Count) exception(s) dans le journal du player :"
        $exceptions | Select-Object -First 8 | ForEach-Object { "    " + $_.Line.Trim() }
    } else {
        Write-Host "  zero exception"
    }
}

Write-Host ""
Write-Host "=== 4. Ce que le jeu dit de lui-meme ==="
$diag = Join-Path $shots "diagnostics.txt"
if (-not (Test-Path $diag)) {
    Fail "pas de diagnostics.txt : la sonde n'a pas conclu"
} else {
    $text = Get-Content $diag -Raw

    # Every one of these was NULL in the build that looked empty.
    foreach ($needle in @("shader URP/Lit    : Universal Render Pipeline/Lit",
                          "shader URP/Unlit  : Universal Render Pipeline/Unlit",
                          "shader GradientSky: Viewpoint/GradientSky",
                          "RenderSettings.skybox: Viewpoint/GradientSky")) {
        if ($text.Contains($needle)) { Write-Host "  OK  $needle" }
        else { Fail "shader ou ciel absent : $needle" }
    }

    if ($text -match "Fonts.Default: NULL") { Fail "aucune police : l'interface ne dessinera aucun texte" }
    else { Write-Host "  OK  police resolue" }

    # A label with no characters is an empty menu, which is how this was found.
    if ($text -match 'text="VIEWPOINT"') { Write-Host "  OK  le titre porte du texte" }
    else { Fail "le titre du menu est vide" }
    if ($text -match '1\. Premiers pas') { Write-Host "  OK  la grille porte les noms de niveaux" }
    else { Fail "la grille de niveaux est vide" }

    # A material-less or mesh-less renderer draws nothing.
    foreach ($line in ($text -split "`n" | Where-Object { $_ -match "nullMaterial=" })) {
        if ($line -match "nullMaterial=(\d+)" -and [int]$Matches[1] -gt 0) {
            Fail "des renderers sans materiau : $($line.Trim())"
        }
    }
    Write-Host "  OK  tous les renderers ont un materiau"

    # The eye height is what every placement is anchored to.
    foreach ($line in ($text -split "`n" | Where-Object { $_ -match "eye above ground=" })) {
        if ($line -match "eye above ground=([\d,\.]+)") {
            $eye = [double]($Matches[1] -replace ",", ".")
            if ([math]::Abs($eye - 1.62) -gt 0.1) { Fail "oeil a $eye m du sol au lieu de 1.62" }
        }
    }
    Write-Host "  OK  l'oeil est a 1.62 m du sol"

    # A frame of nothing is dark or uniform; a frame of the game is not.
    $shotLines = @($text -split "`n" | Where-Object { $_ -match "^shot .*mean rgb" })
    if ($shotLines.Count -lt 4) { Fail "seulement $($shotLines.Count) captures" }
    foreach ($line in $shotLines) {
        if ($line -match "mean rgb (\d+),(\d+),(\d+)") {
            $sum = [int]$Matches[1] + [int]$Matches[2] + [int]$Matches[3]
            if ($sum -lt 60) { Fail "image quasi noire : $($line.Trim())" }
        }
    }
    Write-Host "  OK  $($shotLines.Count) captures, aucune image noire"
}

Write-Host ""
Write-Host "  Les images sont dans $shots : REGARDEZ-LES."
Write-Host "  Aucun test ne remplace un oeil sur une capture, et c'est"
Write-Host "  precisement en ne regardant pas que ce harnais a laisse passer"
Write-Host "  un jeu qui ne montrait qu'une ligne d'horizon."
Write-Host ""
if ($failed -eq 0) { Write-Host "=== PLAYER VERT ===" } else { Write-Host "=== PLAYER ROUGE ===" }
exit $failed
