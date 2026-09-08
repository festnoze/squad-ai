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
                          "shader Surface    : Viewpoint/Surface",
                          "shader Backdrop   : Viewpoint/Backdrop",
                          "RenderSettings.skybox: Viewpoint/GradientSky")) {
        if ($text.Contains($needle)) { Write-Host "  OK  $needle" }
        else { Fail "shader ou ciel absent : $needle" }
    }

    # Les textures CC0 doivent avoir ATTEINT le player. Un materiau dont le
    # _BaseMap revient nul dessine quand meme : il dessine la couleur plate
    # d'avant ce palier, donc l'echec se lit "les textures n'ont rien donne"
    # alors que la cause est un asset absent du build. C'est exactement le
    # genre de panne silencieuse pour laquelle ce script existe.
    $surfaceLines = @($text -split "`n" | Where-Object { $_ -match "^platform surface:" })
    if ($surfaceLines.Count -eq 0) {
        Fail "la sonde ne dit rien du materiau de plateforme"
    }
    foreach ($line in $surfaceLines) {
        if ($line -match "_Style=ABSENT") {
            Fail "le materiau de plateforme n'est pas sur Viewpoint/Surface : $($line.Trim())"
        } else {
            Write-Host "  OK  le materiau de plateforme porte un style"
        }
        foreach ($map in @("_BaseMap", "_NormalMap")) {
            if ($line -match "$map=(ABSENT|NULL)") {
                Fail "$map absent du materiau de plateforme : la texture n'a pas atteint le player"
            } elseif ($line -match "$map=(\S+) (\d+)x(\d+)" -and [int]$Matches[2] -ge 256) {
                Write-Host "  OK  $map = $($Matches[1]) $($Matches[2])x$($Matches[3])"
            } else {
                # Une texture 1 x 1 se resout, s'echantillonne et rend exactement
                # la couleur plate qu'elle etait censee remplacer.
                Fail "$map illisible ou trop petit : $($line.Trim())"
            }
        }
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

    # V-PROP-06 cache la dalle physique du marqueur et dessine un decal a sa
    # place. La Decal Renderer Feature vit dans PC_Renderer.asset en YAML texte,
    # et une feature dont le m_Script ne se resout pas est LACHEE par Unity sans
    # un mot : pas d'exception, pas d'avertissement, tous les tests verts, et
    # l'audit trouve toujours ses marqueurs puisqu'il lit la donnee de niveau.
    # Il ne reste alors plus rien la ou le joueur doit se placer, et un niveau
    # qui ne dit plus ou aller n'est plus jouable. Les deux nombres cote a cote
    # sont la seule chose qui rende cette panne visible.
    $markerLines = @($text -split "`n" | Where-Object { $_ -match "^markers: " })
    if ($markerLines.Count -eq 0) {
        Fail "la sonde ne dit rien des marqueurs"
    }
    foreach ($line in $markerLines) {
        if ($line -match "slabs=(\d+) hidden=(\d+) decals=(\d+) halos=(\d+)") {
            $slabs = [int]$Matches[1]
            $hiddenSlabs = [int]$Matches[2]
            $decals = [int]$Matches[3]
            $halos = [int]$Matches[4]
            # The predicate is "this level has marker slabs and NOT ONE of them
            # is painted", and never "a slab is hidden with no decal". The
            # second one is dead code: LevelBuilder hides a slab only AFTER its
            # projector exists and has validated itself, so hidden > 0 already
            # implies decals > 0 and the test could never fire. Worse, the
            # failure it was written for does not hide anything at all - a
            # dropped Decal Renderer Feature (or "Shader Graphs/Decal" stripped
            # from the player) makes LevelBuilder KEEP every marker mesh, which
            # reads slabs>0 hidden=0 decals=0 and used to print OK.
            #
            # Halos are subtracted because the pickup contact shadows of
            # V-VFX-07 are decals too, so a level whose only projectors are
            # halos has no painted marker at all. Both counts stay in the OK
            # line: they are the detail that says WHICH of the two is missing.
            $painted = $decals - $halos
            if ($slabs -gt 0 -and $painted -le 0) {
                Fail ("$slabs dalles de marqueur et aucun decal peint ($decals decals dont" +
                      " $halos halos de pickup) : rien n'est dessine la ou le joueur doit se" +
                      " placer, le niveau est injouable")
            } else {
                Write-Host ("  OK  marqueurs : $slabs dalles dont $hiddenSlabs cachees," +
                            " $decals decals dont $halos halos")
            }
        } else {
            Fail "recensement des marqueurs illisible : $($line.Trim())"
        }
    }

    # The eye height is what every placement is anchored to.
    foreach ($line in ($text -split "`n" | Where-Object { $_ -match "eye above ground=" })) {
        if ($line -match "eye above ground=([\d,\.]+)") {
            $eye = [double]($Matches[1] -replace ",", ".")
            if ([math]::Abs($eye - 1.62) -gt 0.1) { Fail "oeil a $eye m du sol au lieu de 1.62" }
        }
    }
    Write-Host "  OK  l'oeil est a 1.62 m du sol"

    # --- Palier 4, "Feedback" -------------------------------------------------
    #
    # Tout ce palier n'est que des ANIMATIONS, et une animation qui ne tourne
    # jamais ressemble exactement a une animation pas encore ecrite : aucune
    # capture ne les distingue, et un test qui demande seulement si l'objet de
    # l'effet existe ne les distingue pas non plus. Ces controles portent donc
    # sur l'ETAT des systemes et jamais sur leur apparence.

    # V-VFX-08 pose la poussiere ambiante sous la racine de niveau, et les
    # effets de ce palier (motes du teleporteur, souffle d'une decoupe, etincelles
    # d'une pile) sont des ParticleSystem au meme endroit. Zero systeme = rien de
    # tout cela ne tourne, et le jeu reste exactement aussi silencieux qu'avant
    # ce palier tout en verifiant vert.
    $particleLines = @($text -split "`n" | Where-Object { $_ -match "^particles: systems=" })
    if ($particleLines.Count -eq 0) {
        Fail "la sonde ne dit rien des systemes de particules"
    }
    # Dedoublonne AVANT de tester, et cela ne perd rien : deux lignes identiques
    # echouent ou passent a l'identique, et la sonde en emet une par niveau plus
    # une par moment de feedback.
    foreach ($line in ($particleLines | ForEach-Object { $_.Trim() } | Select-Object -Unique)) {
        if ($line -match "systems=(\d+) playing=(\d+) emitting=(\d+) alive=(\d+)") {
            if ([int]$Matches[1] -eq 0) {
                Fail ("aucun ParticleSystem sous la racine de niveau : ni la poussiere" +
                      " ambiante ni aucun effet de ce palier ne tourne dans le player")
            } else {
                Write-Host ("  OK  particules : $($Matches[1]) systemes dont $($Matches[2]) en" +
                            " marche, $($Matches[4]) particules vivantes")
            }
        } else {
            Fail "recensement des particules illisible : $($line.Trim())"
        }
    }

    # Les volumes se RAPPORTENT sans jamais faire echouer : leur nombre depend de
    # l'etat (le studio photo pose le sien), donc aucun seuil n'a de sens ici.
    # Ce qui compte est de pouvoir LIRE les priorites le jour ou le
    # post-traitement ne ressemble pas a ce que les profils disent : l'annexe C.5
    # raconte une passe entiere perdue parce qu'un second profil par defaut
    # ecrasait le premier, sans une erreur et avec les bons nombres a l'ecran
    # dans l'inspecteur.
    $volumeLines = @($text -split "`n" |
        Where-Object { $_ -match "^volumes: \d+" -or $_ -match "^\s+volume\[" } |
        ForEach-Object { $_.Trim() } | Select-Object -Unique)
    if ($volumeLines.Count -eq 0) {
        Write-Host "  --  la sonde ne dit rien des volumes"
    } else {
        Write-Host "  --  volumes vus par la sonde :"
        $volumeLines | ForEach-Object { "      $_" }
    }
    $postLines = @($text -split "`n" | Where-Object { $_ -match "^post " } |
        ForEach-Object { $_.Trim() } | Select-Object -Unique)
    $postLines | ForEach-Object { "      $_" }

    # L'ANCRE DE POSE. Le placer est un enfant de la camera a transform local
    # identite, et c'est cela seul qui fait que la pose de la camera EST l'ancre
    # de placement (PRD 6.4). V-ANIM-01 ajoute du bob, un plongeon a
    # l'atterrissage et un FOV de course sur cette meme camera : c'est correct et
    # voulu, le bob entre dans l'ancre comme il entre deja dans le viseur. Mais
    # la premiere facon tentante d'ecrire n'importe laquelle de ces trois choses
    # est de decaler l'ENFANT, et cela casserait l'illusion centrale du jeu (ce
    # qu'on cadre n'est plus ce qu'on pose) sans lever une exception, sans
    # noircir une image et sans faire echouer un test qui ne regarde pas.
    #
    # Le roll n'est pas une derive : PhotoPlacer applique les quarts de tour de
    # la molette a cet objet meme, expres, pour que l'ancre tourne avec l'image
    # affichee. La sonde compare donc la rotation locale a
    # PhotoPlacer.RollRotation(RollSteps) et publie l'ecart sous "drift".
    $placerLines = @($text -split "`n" | Where-Object { $_ -match "^placer anchor:" })
    if ($placerLines.Count -eq 0) {
        Fail "la sonde ne dit rien de l'ancre de pose"
    }
    $placerOk = 0
    foreach ($line in $placerLines) {
        if ($line -match "offset ([\d\.]+) m roll=(\d+) local rot \([^)]*\) drift ([\d\.]+) deg") {
            $offset = [double]$Matches[1]
            $drift = [double]$Matches[3]
            if ($offset -gt 0.001) {
                Fail ("l'ancre de pose a derive : le placer est a $offset m de l'origine de la" +
                      " camera au lieu d'y etre pose, donc ce qu'on cadre n'est plus ce qu'on pose")
            } elseif ($drift -gt 0.05) {
                Fail ("l'ancre de pose a derive : la rotation locale du placer s'ecarte de $drift" +
                      " degres du roll demande, donc ce qu'on cadre n'est plus ce qu'on pose")
            } else {
                $placerOk++
            }
        } else {
            Fail "ancre de pose illisible : $($line.Trim())"
        }
    }
    if ($placerOk -gt 0) {
        Write-Host "  OK  l'ancre de pose est a l'identite sous la camera ($placerOk releves)"
    }

    # A frame of nothing is dark or uniform; a frame of the game is not.
    #
    # Le plancher est passe de 4 a 9 avec les trois moments que le palier 4 ajoute
    # a la liste de 6.1 (image levee, viseur, rembobinage en cours) : un moment
    # qu'on n'atteint plus est un moment qu'on ne photographie plus, et c'est la
    # seule chose qui le dise.
    $shotLines = @($text -split "`n" | Where-Object { $_ -match "^shot .*mean rgb" })
    if ($shotLines.Count -lt 9) { Fail "seulement $($shotLines.Count) captures" }
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
