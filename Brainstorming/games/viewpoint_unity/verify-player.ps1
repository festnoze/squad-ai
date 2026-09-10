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
    #
    # LES DEUX NOMBRES SONT TESTES, et pas seulement le premier. Le compte de
    # systemes ne peut PAS tomber a zero dans un player : LevelBuilder.cs:340
    # appelle Atmosphere.Install pour chaque niveau sans condition, et
    # Atmosphere.cs:82-102 ajoute exactement un "Dust" sous la racine des que le
    # peripherique graphique n'est pas Null. Le nombre qui dit vraiment "rien ne
    # tourne" est donc "playing" : Atmosphere.cs:125 pose playOnAwake = false et
    # Atmosphere.cs:203 est le seul Play(true) du fichier. Perdez ce Play, ou
    # laissez l'objet Dust arriver desactive, et le jeu ne dessine plus un grain
    # d'air nulle part pendant que la sonde ecrit "systems=1 playing=0" - c'est
    # exactement la forme du recensement de marqueurs plus haut, un controle qui
    # imprimait OK sur precisement le build qu'il existe pour attraper.
    #
    # playing >= 1 est sans danger : la poussiere le garantit sur tout niveau
    # sain, tandis que les emetteurs par effet (etincelles d'une pile, colonne du
    # teleporteur) sont legitimement au repos et ne sont jamais comptes. "alive"
    # reste non teste, pour la raison que ShotProbe.cs:676-679 donne.
    $particleLines = @($text -split "`n" | Where-Object { $_ -match "^particles: systems=" })
    if ($particleLines.Count -eq 0) {
        Fail "la sonde ne dit rien des systemes de particules"
    }
    # Dedoublonne AVANT de tester, et cela ne perd rien : deux lignes identiques
    # echouent ou passent a l'identique, et la sonde en emet une par niveau plus
    # une par moment de feedback.
    foreach ($line in ($particleLines | ForEach-Object { $_.Trim() } | Select-Object -Unique)) {
        if ($line -match "systems=(\d+) playing=(\d+) emitting=(\d+) alive=(\d+)") {
            $psSystems = [int]$Matches[1]
            $psPlaying = [int]$Matches[2]
            $psAlive = [int]$Matches[4]
            if ($psSystems -eq 0) {
                Fail ("aucun ParticleSystem sous la racine de niveau : ni la poussiere" +
                      " ambiante ni aucun effet de ce palier ne tourne dans le player")
            } elseif ($psPlaying -eq 0) {
                Fail ("$psSystems systemes de particules mais aucun ne tourne : Atmosphere n'a" +
                      " jamais appele Play, donc le jeu ne dessine aucun air ambiant")
            } else {
                Write-Host ("  OK  particules : $psSystems systemes dont $psPlaying en" +
                            " marche, $psAlive particules vivantes")
            }
        } else {
            Fail "recensement des particules illisible : $($line.Trim())"
        }
    }

    # Le NOMBRE de volumes se rapporte sans jamais faire echouer : il depend de
    # l'etat (le studio photo pose le sien), donc aucun seuil n'a de sens ici.
    # Ce qui compte est de pouvoir LIRE les priorites le jour ou le
    # post-traitement ne ressemble pas a ce que les profils disent : l'annexe C.5
    # raconte une passe entiere perdue parce qu'un second profil par defaut
    # ecrasait le premier, sans une erreur et avec les bons nombres a l'ecran
    # dans l'inspecteur.
    #
    # Le listing complet reste imprime dessous : c'est la piece a conviction de
    # l'annexe C.5. Mais "aucun seuil n'a de sens" ne vaut QUE pour le compte.
    # Les trois choses ci-dessous sont booleennes, elles sont deja ecrites en
    # clair dans le fichier, et chacune veut dire "tout ce palier est inerte".
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

    # renderPostProcessing est le drapeau de l'annexe C.6, la decouverte la plus
    # chere du palier 0 : a false, TOUTE valeur de post-traitement de TOUT profil
    # est inerte et rien ne le dit. Il est pose une seule fois, a
    # PlayerController.cs:456, et rien ne leve d'exception s'il disparait.
    if ($postLines.Count -eq 0) {
        Fail "la sonde ne dit rien du post-traitement de la camera (annexe C.6)"
    }
    foreach ($line in $postLines) {
        if ($line -match "^post on camera: NO UniversalAdditionalCameraData") {
            Fail ("la camera du joueur n'a pas de UniversalAdditionalCameraData : rien ne" +
                  " post-traite, donc V-POST-04 et V-POST-05 sont inertes (annexe C.6)")
        } elseif ($line -match "^post on camera: renderPostProcessing=False") {
            Fail ("renderPostProcessing=False sur la camera du joueur : toute valeur de post" +
                  " de tout profil est inerte et rien d'autre ne le dit (annexe C.6)")
        } elseif ($line -match "^post component: NONE") {
            Fail ("aucun composant de post-traitement dans la scene : les bandes de PostFx" +
                  " n'existent pas, donc V-POST-04, V-POST-05 et V-POST-06 sont inertes")
        }
    }

    # ET LE POIDS DE LA BANDE, A L'INSTANT OU ELLE EST CENSEE ETRE LEVEE. Un
    # drapeau vert ne dit pas qu'une rampe monte : Main.Update peut cesser
    # d'atteindre DrivePostFx(true, ...) (la porte de Main.cs:235-253) sans une
    # exception, et les bandes restent alors a 0.00 pour tout le run.
    #
    # La sonde a deja mis la donnee au bon endroit du fichier : FeedbackRewind
    # tient R pendant 15 pas fixes (0.3 s de temps reel, contre 0.25 s de montee
    # pour la bande) PUIS appelle DumpFeedback PUIS photographie 07, donc le dump
    # coince entre "rewind mid-scrub:" et "shot 07_rewind_mid_scrub" porte le
    # poids de l'instant photographie. Idem pour la mise au point de l'image
    # levee entre "held picture:" et "shot 06_raised_photo", apres Settle(30)
    # contre 0.2 s de montee.
    #
    # Les noms sont ceux des OBJETS HOTES (PostFx.cs:351 et 393), pas les
    # libelles passes a Build() : "RewindTreatment" et "PhotoFocus".
    function BandWeightAt($lines, $startPattern, $endPattern, $hostName) {
        $start = -1
        $stop = -1
        for ($i = 0; $i -lt $lines.Count; $i++) {
            $probe = $lines[$i].Trim()
            if ($start -lt 0) {
                if ($probe -match $startPattern) { $start = $i }
            } elseif ($probe -match $endPattern) {
                $stop = $i
                break
            }
        }
        if ($start -lt 0 -or $stop -lt 0) { return $null }
        for ($i = $start; $i -lt $stop; $i++) {
            $probe = $lines[$i].Trim()
            if ($probe -match ("^volume\[" + [regex]::Escape($hostName) + "\].*weight=([\d,\.]+)")) {
                return [double]($Matches[1] -replace ",", ".")
            }
        }
        return $null
    }

    $diagLines = $text -split "`n"
    foreach ($band in @(
        @{ Host = "RewindTreatment"; Start = "^rewind mid-scrub:"; Stop = "^shot 07_rewind_mid_scrub";
           Item = "V-POST-04"; What = "le traitement de rembobinage" },
        @{ Host = "PhotoFocus"; Start = "^held picture:"; Stop = "^shot 06_raised_photo";
           Item = "V-POST-05"; What = "la mise au point de l'image levee" })) {
        $weight = BandWeightAt $diagLines $band.Start $band.Stop $band.Host
        if ($null -eq $weight) {
            Fail ("aucun volume[$($band.Host)] dans le dump qui precede la capture du moment :" +
                  " $($band.Item) ne peut pas etre verifie")
        } elseif ($weight -le 0.5) {
            Fail ("$($band.Item) inerte : $($band.What) est a un poids de $weight dans l'image" +
                  " meme qui existe pour le montrer, donc la rampe n'est jamais montee")
        } else {
            Write-Host "  OK  $($band.Item) : volume[$($band.Host)] a un poids de $weight"
        }
    }

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

    # LES TROIS MOMENTS DU PALIER 4, lus sur le VERDICT que la sonde ecrit et
    # jamais sur le nombre d'images.
    #
    # Compter les captures ne dit rien de ces moments : ShotProbe emet les trois
    # images SANS CONDITION. Elle photographie 07_rewind_mid_scrub meme sans
    # rembobinage du tout (ShotProbe.cs:224-234, avec le commentaire qui dit
    # pourquoi), elle photographie 05_viewfinder apres s'etre accorde une
    # pellicule si le pickup a disparu (166-179), et elle photographie
    # 06_raised_photo quel que soit le retour de CapturePhoto (195-209). Le
    # compte vaut donc 9 sur tout run qui atteint File.WriteAllText, et moins de
    # 9 veut dire que la coroutine est morte - ce qui emporte diagnostics.txt et
    # se fait deja attraper plus haut.
    #
    # La panne que cela laisse passer est reelle et propre au player : le studio
    # de PhotoSnaps se resout dans l'editeur mais son chemin de rendu est
    # supprime du build, PhotoSnaps.GetTexture rend null, le coin de l'ecran
    # porte une carte blanche, la moyenne RGB reste tres au-dessus du plancher de
    # 60, aucune exception n'est levee, et V-VFX-06 comme V-ANIM-04 ne montrent
    # rien. Les quatre lignes ci-dessous sont les seules qui le disent.
    $viewfinderLines = @($text -split "`n" | Where-Object { $_ -match "^viewfinder: " })
    if ($viewfinderLines.Count -eq 0) {
        Fail "la sonde ne dit rien du viseur"
    }
    foreach ($line in $viewfinderLines) {
        if ($line -match "^viewfinder: True") {
            Write-Host "  OK  le viseur se leve (V-VFX-06)"
        } else {
            Fail ("le viseur ne se leve pas : $($line.Trim()) - V-VFX-06 n'a rien a animer et" +
                  " l'image 05_viewfinder montre un niveau ordinaire")
        }
    }

    $captureLines = @($text -split "`n" | Where-Object { $_ -match "^capture: " })
    if ($captureLines.Count -eq 0) {
        Fail "la sonde ne dit rien de la prise de photo"
    }
    foreach ($line in $captureLines) {
        if ($line -match "^capture: True") {
            Write-Host "  OK  l'appareil prend une photo et la leve (V-ANIM-04)"
        } else {
            Fail ("l'appareil n'a pris aucune photo : $($line.Trim()) - il n'y a pas d'image" +
                  " levee, donc ni la glissade de V-VFX-06 ni l'ease de V-ANIM-04")
        }
    }

    # L'image levee doit AVOIR DES PIXELS. Une carte vide se dessine, s'anime et
    # ne se distingue d'une animation pas ecrite par aucune moyenne de couleur.
    # Une texture 1 x 1 se resout de la meme facon : d'ou le plancher, contre les
    # 768 de PhotoSnaps.SnapSize.
    $pictureLines = @($text -split "`n" | Where-Object { $_ -match "^held picture: " })
    if ($pictureLines.Count -eq 0) {
        Fail "la sonde ne dit rien de l'image tenue en main"
    }
    foreach ($line in $pictureLines) {
        if ($line -match "^held picture: NULL") {
            Fail ("l'image levee est nulle : le studio photo n'a rien rendu dans le player," +
                  " donc la carte du coin est vide et V-VFX-06 comme V-ANIM-04 n'animent rien")
        } elseif ($line -match "(\d+)x(\d+)\s*$" -and [int]$Matches[1] -ge 64 -and [int]$Matches[2] -ge 64) {
            Write-Host "  OK  l'image levee porte des pixels ($($Matches[1])x$($Matches[2]))"
        } else {
            Fail "image levee illisible ou degeneree : $($line.Trim())"
        }
    }

    # Le rembobinage doit ETRE EN COURS sur l'image 07, sinon c'est une image de
    # niveau ordinaire et la barre de V-HUD-06 comme la bande de V-POST-04
    # n'avaient rien a montrer.
    # Teste ligne a ligne et jamais sur $text : "-match" de PowerShell n'active
    # pas le mode multiligne, donc un "^" sur le texte entier n'ancre qu'au tout
    # premier caractere du fichier et ne trouverait jamais rien ici.
    $noRewindLines = @($text -split "`n" | Where-Object { $_ -match "^rewind: NO REWIND" })
    if ($noRewindLines.Count -gt 0) {
        Fail ("aucun systeme de rembobinage dans le player : Main l'a construit dans un try" +
              " qui a echoue, donc V-HUD-06 et V-POST-04 n'ont rien a animer")
    } else {
        $scrubLines = @($text -split "`n" | Where-Object { $_ -match "^rewind mid-scrub: " })
        if ($scrubLines.Count -eq 0) {
            Fail "la sonde ne dit rien de l'etat du rembobinage a l'instant photographie"
        }
        foreach ($line in $scrubLines) {
            if ($line -match "^rewind mid-scrub: rewinding=False") {
                Fail ("le rembobinage n'etait pas en cours a l'instant photographie :" +
                      " $($line.Trim()) - V-HUD-06 et V-POST-04 sont inertes")
            } else {
                Write-Host "  OK  le rembobinage est en cours sur l'image 07 (V-HUD-06)"
            }
        }
    }

    # --- Palier 5, "Interface" ------------------------------------------------
    #
    # V-HUD-01 remplace la police builtin du moteur par une OFL livree dans le
    # depot, et c'est l'echange le plus silencieux de tout le document. Si le
    # fichier n'atteint pas le player, Fonts.cs retombe sur la police du moteur :
    # le jeu demarre, dessine toutes les chaines figees de la PRD 12, ne leve
    # rien, se photographie, et ressemble EXACTEMENT a un palier jamais fait.
    # Le controle "Fonts.Default: NULL" plus haut ne voit que le cas ou il n'y a
    # plus aucune police.
    #
    # Les deux lignes de la sonde se lisent ENSEMBLE :
    #   - "font resource Fonts/Manrope:" dit si l'asset a atteint le player
    #     (Resources.Load est le seul chemin qui survive a un build, annexe C.8) ;
    #   - "font in use: <nom> builtin=<bool>" dit ce que l'interface dessine.
    # Manrope ABSENTE avec la police du moteur en service est la degradation que
    # le PRD_VISUAL 3.2 amende EXIGE (un checkout sans la police doit encore
    # demarrer et dessiner du texte) : c'est un avertissement, jamais un echec.
    # Manrope PRESENTE avec la police du moteur en service est un chemin de
    # chargement casse, et c'est le seul cas rouge.
    #
    # Le booleen vient de la sonde et n'est pas redecide ici : les noms de la
    # police builtin ("LegacyRuntime", "Arial") vivent dans
    # ShotProbe.IsBuiltinFont et nulle part ailleurs, pour qu'il y ait UN seul
    # endroit a corriger le jour ou Unity la renomme encore.
    $fontUseLines = @($text -split "`n" | Where-Object { $_ -match "^font in use: " })
    $fontResourceLines = @($text -split "`n" | Where-Object { $_ -match "^font resource Fonts/Manrope: " })
    if ($fontUseLines.Count -eq 0 -or $fontResourceLines.Count -eq 0) {
        Fail ("la sonde ne dit pas quelle police a ete resolue : V-HUD-01 ne peut pas etre" +
              " verifie (lignes 'font in use' et 'font resource Fonts/Manrope' attendues)")
    } elseif ($fontUseLines[0] -match "^font in use: (\S+) builtin=(\S+)") {
        # Les deux captures sont recopiees AVANT la comparaison suivante : tout
        # operateur -match ou -notmatch reecrit $Matches, et le nom de la police
        # serait alors celui de l'autre ligne.
        $fontName = $Matches[1]
        $fontBuiltin = $Matches[2] -eq "True"
        $manropePresent = $fontResourceLines[0] -notmatch "^font resource Fonts/Manrope: NULL"
        if ($fontName -eq "NONE") {
            # Deja rouge plus haut sur "Fonts.Default: NULL" : ne pas compter le
            # meme defaut deux fois.
            Write-Host "  --  aucune police en service, voir l'echec ci-dessus"
        } elseif ($manropePresent -and $fontBuiltin) {
            Fail ("Manrope est dans le player mais l'interface dessine avec la police builtin" +
                  " du moteur ($fontName) : le chemin de chargement de Fonts.cs est faux, et" +
                  " l'interface a exactement l'air qu'elle avait avant ce palier")
        } elseif (-not $manropePresent) {
            Write-Host ("  --  police OFL absente du player : l'interface retombe sur la police" +
                        " du moteur ($fontName). C'est permis (PRD_VISUAL 3.2 amende : un" +
                        " checkout sans la police doit tourner), mais V-HUD-01 ne se voit pas")
        } else {
            Write-Host "  OK  l'interface dessine avec la police du depot ($fontName)"
        }
    } else {
        Fail "police en service illisible : $($fontUseLines[0].Trim())"
    }

    # LES VIGNETTES DE LA GRILLE (V-MENU-02), rapportees et JAMAIS fatales.
    #
    # Une vignette est un niveau construit dans le studio photo, shoote puis
    # demonte : un run headless ou rendu en logiciel n'en produit legitimement
    # aucune, donc zero ici n'est pas une regression et ne peut pas faire
    # echouer. Ce qui compte est que le nombre soit LISIBLE, parce qu'une grille
    # sans vignette est exactement la grille d'avant ce palier - memes chaines,
    # memes vingt-cinq boutons, aucune exception - et qu'aucune capture ne les
    # distingue si personne ne compte.
    #
    # La sonde emet trois recensements : le titre froid au demarrage, puis les
    # deux qui encadrent le remplissage du cache a la fin du run. C'est la
    # PROGRESSION entre eux qui dit si le cache s'est rempli, ne s'est jamais
    # rempli, ou etait deja plein - d'ou l'absence de dedoublonnage ici.
    $gridLines = @($text -split "`n" | Where-Object { $_ -match "^level grid: " } |
        ForEach-Object { $_.Trim() })
    if ($gridLines.Count -eq 0) {
        Write-Host "  --  la sonde ne dit rien de la grille de niveaux"
    } else {
        foreach ($line in $gridLines) {
            if ($line -match "buttons=(\d+) unlocked=(\d+) thumbnails=(\d+) text-only=(\d+)") {
                $gridButtons = [int]$Matches[1]
                $gridUnlocked = [int]$Matches[2]
                $gridThumbs = [int]$Matches[3]
                $gridText = [int]$Matches[4]
                $plural = if ($gridUnlocked -gt 1) { "debloques" } else { "debloque" }
                Write-Host ("  --  grille : $gridButtons boutons dont $gridUnlocked $plural," +
                            " $gridThumbs avec vignette, $gridText en texte seul")
            } else {
                Write-Host "  --  recensement de grille illisible : $line"
            }
        }
        # L'inventaire d'une cellule, imprime tel quel : les comptes disent
        # combien de cellules portent une image, celui-ci dit DE QUOI une
        # cellule est faite, et c'est la seule chose qui montre une vignette
        # arrivee en 1 x 1 ou un glyphe compte comme une image.
        $cellLines = @($text -split "`n" | Where-Object { $_ -match "^level grid cell: " } |
            ForEach-Object { $_.Trim() } | Select-Object -Unique)
        $cellLines | ForEach-Object { "      $_" }
    }

    # A frame of nothing is dark or uniform; a frame of the game is not.
    #
    # Le plancher de 11 (6 images de la liste de 6.1, les trois moments du
    # palier 4, puis l'ecran titre et la grille de niveaux que la section 6.1
    # ajoute au palier 5) reste, mais comme simple garde de COMPLETUDE : il ne
    # dit rien de la reussite d'un moment, puisque la sonde emet ses onze images
    # sans condition. Ce sont les verdicts ci-dessus qui le disent.
    $shotLines = @($text -split "`n" | Where-Object { $_ -match "^shot .*mean rgb" })
    if ($shotLines.Count -lt 11) { Fail "seulement $($shotLines.Count) captures" }
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
