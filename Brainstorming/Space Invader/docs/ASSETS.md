# TERRAFORM ODYSSEY - Inventaire des assets

Principe directeur : **zero asset binaire**. Aucun fichier .glb, .png, .mp3, .hdr.
Tout (maillages, textures, palettes, sons, cubemaps) est genere par code au
chargement, a partir d'une seed. Consequences :

- le repo reste a quelques centaines de Ko,
- 12 planetes uniques ne coutent rien en disque,
- une seed change tout le systeme solaire.

Les librairies portent le gros oeuvre : `three` (WebGL2, scenegraph, shaders,
composer, instancing), `simplex-noise` (bruit 2D/3D/4D seede), `lil-gui` +
`stats.js` (outillage debug). Le reste est du code metier.

---

## 1. Assets geometriques (maillages)

| Asset | Producteur | Technique | Budget |
|---|---|---|---|
| `A01` Patch de terrain spherique | `gen/terrainWorker.js` | grille 33x33 sur face de cube-sphere, deplacee par fBm ridged, normales analytiques, jupe (skirt) de 1 anneau pour masquer les fissures inter-LOD | 1089 vtx / patch, ~2.5k patchs vivants max |
| `A02` Sphere ocean | `render/ocean.js` | icosphere subdiv 6, rayon `R + seaLevel`, deplacement de vagues en vertex shader | 40k tris |
| `A03` Coque atmosphere | `render/atmosphere.js` | icosphere subdiv 4 rendue en `BackSide`, rayon `R * 1.055` | 1.2k tris |
| `A04` Coque nuages | `render/clouds.js` | 2 icospheres subdiv 5 (`R*1.012`, `R*1.022`) en rotation differentielle | 10k tris |
| `A05` Coque geante gazeuse | `render/gasGiant.js` | icosphere subdiv 6 + 3 coques internes translucides traversables | 40k tris |
| `A06` Anneau planetaire | `render/gasGiant.js` | `RingGeometry` 128 segments, alpha procedural par bandes | 256 tris |
| `A07` Vaisseau joueur | `game/ship.js` | fuselage extrude low-poly + ailes + tuyeres + verriere, merge en une geometry | ~900 tris |
| `A08` Arbre (4 especes) | `life/vegetation.js` | tronc `CylinderGeometry` tronque + 1 a 3 blobs de feuillage (icosphere deformee), fusionnes ; especes : conifere, feuillu, palmier, cycas | 120-260 tris, `InstancedMesh` |
| `A09` Rocher / caillou | `life/vegetation.js` | icosphere subdiv 1 deformee, aleatoire par seed | 40 tris, instancie |
| `A10` Creature volante (oiseau) | `life/fauna.js` | corps fuselé + 2 ailes animees par `morph`-like rotation d'instance | 60 tris, instancie |
| `A11` Creature terrestre (herbivore) | `life/fauna.js` | corps + 4 pattes + tete, low-poly | 110 tris, instancie |
| `A12` Soleil | `render/sun.js` | icosphere subdiv 4, shader emissif + couronne billboard | 1.3k tris |
| `A13` Champ d'etoiles | `render/starfield.js` | 12 000 `Points` sur sphere de rayon 3e7, tailles et couleurs par classe spectrale | 12k points |
| `A14` Nebuleuses de fond | `render/starfield.js` | 5 quads billboard geants, alpha fBm | 10 tris |
| `A15` Marqueur de nav (waypoint) | `game/hud.js` | `Sprite` + anneau `LineSegments` | negligeable |

## 2. Assets textures (generees, jamais chargees)

| Asset | Producteur | Format | Usage |
|---|---|---|---|
| `T01` Heightmap equirectangulaire | `gen/heightmapTexture.js` (worker) | `DataTexture` R16F 1024x512 | minimap HUD, teinte des eaux peu profondes, ombres de nuages, placement de vie |
| `T02` Biome-map equirectangulaire | idem | `DataTexture` RGBA8 1024x512 | minimap coloree, choix d'espece d'arbre, spawn faune |
| `T03` Rampe de palette biome | `gen/palettes.js` | `DataTexture` RGBA8 256x8 (8 lignes = 8 classes de temperature) | coloration terrain en shader |
| `T04` Normal map de detail | `gen/textures.js` | `DataTexture` RGB8 256x256 tileable, derivee de bruit | micro-relief du terrain au sol |
| `T05` Normal map d'eau (2 couches) | `render/ocean.js` | 2x `DataTexture` 256x256 defilantes | vagues, scintillement soleil |
| `T06` Sprite de nuage volumetrique | `render/clouds.js` | canvas 128x128 radial + bruit | particules d'entree atmosphere |
| `T07` Cubemap nebuleuse | `render/starfield.js` | 6 faces 512x512 sur canvas, fBm colore | fond de scene (`scene.background`) |
| `T08` Sprite de flare / glow | `render/sun.js` | canvas 256x256 radial additif | soleil, tuyeres, marqueurs |
| `T09` Bandes de geante gazeuse | `render/gasGiant.js` | `DataTexture` 64x512 (profil latitudinal) | teinte des bandes, echantillonnee en shader |
| `T10` Grille de vignette HUD | `styles.css` | gradient CSS pur | cadrage cockpit |

## 3. Assets shaders (GLSL, `ShaderMaterial`)

| Asset | Fichier | Contenu |
|---|---|---|
| `S01` Terrain | `render/materials/terrainMaterial.js` | couleur par vertex + rampe palette, triplanar detail normal, fog atmospherique, neige par pente/altitude/latitude, eclairage Lambert + wrap |
| `S02` Ocean | `render/ocean.js` | Gerstner 3 octaves, fresnel, specular Blinn-Phong soleil, profondeur via `T01`, ecume de rivage |
| `S03` Atmosphere | `render/atmosphere.js` | diffusion simple couche (Rayleigh approx), halo au limbe, transition sol->espace, terminateur jour/nuit |
| `S04` Nuages | `render/clouds.js` | fBm 3D anime domain-warped, eclairage par le soleil, ombre portee sur le sol |
| `S05` Geante gazeuse | `render/gasGiant.js` | bandes latitudinales + advection turbulente + vortex (grande tache), rendu interne "dans les nuages" |
| `S06` Soleil | `render/sun.js` | noyau emissif + granulation animee + couronne fresnel |
| `S07` Etoiles | `render/starfield.js` | `PointsMaterial` custom, scintillement, attenuation en atmosphere |
| `S08` Traînee de vitesse | `render/fx.js` | streaks additives en instancing, alignees sur le vecteur vitesse |
| `S09` Bouclier / rentree atmospherique | `render/fx.js` | fresnel additif, intensite = vitesse * densite atmo |

## 4. Assets audio (WebAudio procedural)

| Asset | Producteur | Synthese |
|---|---|---|
| `U01` Moteur (drone) | `core/audio.js` | 2 oscillateurs sawtooth desaccordes + lowpass, pitch/gain = poussee |
| `U02` Souffle atmospherique | idem | bruit blanc filtre bandpass, gain = densite * vitesse |
| `U03` Bip de scan | idem | sinus 880 Hz -> 1320 Hz, enveloppe 120 ms |
| `U04` Decouverte validee | idem | arpege majeur 3 notes |
| `U05` Victoire | idem | motif 6 notes + pad |
| `U06` Alarme de proximite | idem | carre 220 Hz pulse |
| `U07` Warp | idem | sweep 60 Hz -> 2 kHz + reverb par convolution de bruit |

## 5. Assets de donnees (contenu du jeu)

| Asset | Fichier | Contenu |
|---|---|---|
| `D01` Systeme solaire 12 corps | `gen/planetSpec.js` | table complete : nom, rayon orbital, rayon, type, classe de temperature, seed, flags de vie, palette |
| `D02` Profils de bruit par type | `gen/planetSpec.js` | 7 profils (continental, oceanique, desertique, volcanique, glace, aride, geante) : octaves, lacunarite, gain, ridged, warp |
| `D03` Palettes par temperature | `gen/palettes.js` | 8 classes (inferno -> frozen) x 12 biomes |
| `D04` Table des especes d'arbres | `life/vegetation.js` | 4 especes x (biomes valides, taille, couleurs) |
| `D05` Table des creatures | `life/fauna.js` | 2 archetypes x (comportement, taille, couleurs, biomes) |
| `D06` Textes FR du HUD | `game/strings.js` | tous les libelles, tooltips, journal de bord |
| `D07` Presets qualite | `core/settings.js` | low / medium / high / ultra : profondeur LOD, densite instances, resolution ocean, post-process |

## 6. Assets HUD / UI (DOM + CSS)

| Asset | Fichier | Contenu |
|---|---|---|
| `H01` Ecran titre | `index.html` + `styles.css` | logo texte, briefing de mission, bouton, choix de qualite |
| `H02` Reticule + horizon artificiel | `index.html` | SVG inline, roulis/tangage relatifs a la verticale locale |
| `H03` Panneau de nav | `game/hud.js` | liste des 12 corps, distance, type, statut de scan, cible active |
| `H04` Tracker des 3 elements | `game/hud.js` | 3 pastilles (ocean / arbres / faune) avec anneau de progression de scan |
| `H05` Bandeau telemetrie | `game/hud.js` | vitesse, altitude, poussee, densite atmo, temperature locale, heure locale (jour/nuit) |
| `H06` Minimap planetaire | `game/hud.js` | canvas 2D alimente par `T02` + position joueur + marqueurs de decouverte |
| `H07` Toasts de decouverte | `game/hud.js` | file de notifications animees |
| `H08` Ecran de victoire | `game/hud.js` | rapport de terraformation, temps, planetes visitees |
| `H09` Aide des commandes | `index.html` | overlay touche `H` |

## 7. Ce que fournissent les librairies (non reimplemente)

- `three` : WebGL2, scenegraph, `InstancedMesh`, `BufferGeometry`, `ShaderMaterial`,
  `EffectComposer` + `UnrealBloomPass` + `SMAAPass` (depuis `three/examples/jsm`),
  `logarithmicDepthBuffer`, frustum culling, raycasting, `DataTexture`, quaternions.
- `simplex-noise` : bruit 2D/3D/4D seede rapide (base de tout le fBm).
- `lil-gui` : panneau de reglages temps reel (touche `G`).
- `stats.js` : compteur FPS / ms / MB.
- `vite` : bundling, workers ES, HMR, build.

## 8. Budget de production

| Phase moteur | Assets couverts | Etat |
|---|---|---|
| P0 Fondations | `math`, `noise`, `heightField`, `planetSpec`, `palettes`, `settings`, `events` | contrats figes |
| P1 Terrain LOD | `A01`, `S01`, `T03`, `T04`, workers | fan-out |
| P2 Enveloppes | `A02`-`A04`, `S02`-`S04`, `T01`, `T02`, `T05`, `T06` | fan-out |
| P3 Espace | `A12`-`A14`, `S06`-`S07`, `T07`, `T08`, orbites, origine flottante | fan-out |
| P4 Geantes gazeuses | `A05`, `A06`, `S05`, `T09`, traversee | fan-out |
| P5 Vie | `A08`-`A11`, `D04`, `D05`, streaming par patch | fan-out |
| P6 Pilotage | `A07`, physique, camera, `S08`, `S09`, `U01`-`U02` | fan-out |
| P7 Jeu | decouverte, `H01`-`H09`, `D06`, `U03`-`U07` | fan-out |
| P8 Integration | `main.js`, boucle, transitions, verification navigateur | integration |
