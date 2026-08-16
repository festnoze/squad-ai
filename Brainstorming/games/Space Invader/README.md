# TERRAFORM ODYSSEY

Jeu d'exploration spatiale 3D dans le navigateur. Votre monde est mort : ses
oceans se sont retires, ses forets ont brule. Vous decollez avec un seul ordre de
mission - trouver, quelque part dans le systeme, une planete terraformable.

L'ecran titre laisse choisir le systeme a explorer : l'Odyssee ecrite a la main
et ses 12 corps, notre propre systeme solaire (Sol-1, 8 planetes, depart de
Mars), ou un systeme tire au sort.

Une planete est declaree viable lorsque trois elements y sont observes et
analyses : **des oceans**, **des arbres**, **de la vie animale**. Les trois sur
le meme monde, et la mission est un succes.

![stack](https://img.shields.io/badge/three.js-0.185-black)
![deps](https://img.shields.io/badge/deps-4-green)
![assets](https://img.shields.io/badge/assets%20binaires-0-green)

## Lancer

```powershell
cd "C:\Dev\squad-ai\Brainstorming\games\Space Invader"
npm install
npm run dev
```

Puis ouvrir <http://localhost:5310>. Navigateur WebGL2 requis (Chrome, Edge,
Firefox). `npm run build` produit un bundle statique dans `dist/`.

Le systeme et la seed se forcent aussi par l'URL, ce qui evite de repasser par
le menu :

```
http://localhost:5310/?system=sol1
http://localhost:5310/?system=random&seed=kepler
http://localhost:5310/?seed=kepler          # Odyssee, mais gagnante redistribuee
```

## Commandes

Cinq touches suffisent : `Z` `S` pour descendre et monter, `Q` `D` pour tourner,
`Espace` pour pousser.

| Touche | Action |
|---|---|
| `Z` / `S` | Descendre / monter |
| `Q` / `D` | Tourner a gauche / a droite |
| Fleches | Idem, avec fleche haut = monter |
| `A` / `E` | Roulis, pour se remettre a plat (facultatif) |
| Souris | Visee libre (clic sur la fenetre pour capturer le pointeur) |
| `Espace` | Poussee |
| `Maj` | Post-combustion (et propulsion pulse dans le vide) |
| `Ctrl` / `X` | Frein |
| `F` | Analyser (accelere le scan en cours, sinon donne un indice) |
| `T` / `R` | Cible de navigation suivante / precedente |
| `C` | Maintenir pour aligner le nez sur la cible |
| `J` | Saut hyperspatial vers la cible |
| `M` | Afficher les orbites |
| `V` | Camera (poursuite / cockpit / orbite) |
| `L` | Train d'atterrissage |
| `H` | Aide |
| `G` | Panneau de reglages et compteur FPS |

## Le menu principal : trois systemes

L'ecran titre demande deux choses : un preset de qualite et un systeme. Le choix
est renvoye tel quel a `setSystem()` et le HUD est rebati derriere, car le
nombre de corps varie d'un systeme a l'autre.

| Choix | Corps | Echelle des orbites | Depart | Monde viable |
|---|---|---|---|---|
| **Odyssee** | 12, ecrits a la main | 1 UA = 420 000 u | Terra Prime | Aurelia (redistribue si autre seed) |
| **Sol-1** | 8 planetes reelles | 1 UA = 168 000 u (`SOL_AU_SCALE` = 0,4) | Mars | la Terre |
| **Genere aleatoirement** | 8 a 12, tires au sort | 1 UA = 420 000 u | le tellurique le plus habitable | un seul, tire au sort |

Dans les trois cas la regle est la meme : exactement une planete reunit les
trois elements, deux leurres en portent 1 et 2, et on ne demarre jamais sur la
gagnante.

### Odyssee - le systeme d'Helios Prime

| # | Corps | Orbite | Rayon | Type | Climat |
|---|---|---|---|---|---|
| 1 | Cindra | 0,38 UA | 2,6 km | Volcanique | Infernal |
| 2 | Vesk | 0,68 UA | 3,3 km | Desertique | Torride |
| 3 | **Terra Prime** | 1,00 UA | 6,4 km | Tellurique | Tempere (epuisee) |
| 4 | Ashkar | 1,34 UA | 3,7 km | Volcanique | Chaud |
| 5 | Nereidia | 1,80 UA | 4,9 km | Oceanique | Tempere chaud |
| 6 | Selvara | 2,25 UA | 5,6 km | Tellurique | Tempere |
| 7 | Bellatrix | 3,10 UA | 34 km | Geante gazeuse | Frais |
| 8 | Kaelune | 3,90 UA | 4,3 km | Tellurique | Froid |
| 9 | Aurelia | 4,70 UA | 6,8 km | Tellurique | Tempere |
| 10 | Ogthar | 5,90 UA | 42 km | Geante gazeuse (anneaux) | Froid |
| 11 | Hjalmar | 7,30 UA | 4,4 km | Glacee | Glacial |
| 12 | Nyx | 9,20 UA | 3,0 km | Sterile | Glacial |

Les deux geantes gazeuses n'ont pas de sol : on les traverse de part en part.
La visibilite tombe a quelques centaines de metres au coeur et les turbulences
secouent le vaisseau, mais rien ne vous arrete.

### Sol-1 - notre systeme solaire

Demi-grands axes reels, tous multiplies par le meme facteur `SOL_AU_SCALE = 0,4`
(l'UA du systeme vaut donc 168 000 u au lieu de 420 000) : les proportions sont
exactes, seule l'echelle absolue est raccourcie pour que Neptune reste
atteignable en une dizaine de secondes. Les rayons sont les rayons equatoriaux
reels, normalises pour que la Terre vaille 6 400 u, c'est-a-dire exactement le
rayon de Terra Prime et donc le meme ressenti au sol.

On decolle de **Mars** : la Terre est le monde viable, et commencer sur Terre
rendrait la mission gagnee d'avance.

| # | Corps | Orbite | Rayon | Type | Climat |
|---|---|---|---|---|---|
| 1 | Mercure | 0,387 UA | 2,5 km | Sterile | Torride |
| 2 | Venus | 0,723 UA | 6,1 km | Tellurique | Infernal |
| 3 | **Terre** | 1,00 UA | 6,4 km | Tellurique | Tempere (viable) |
| 4 | **Mars** | 1,524 UA | 3,4 km | Desertique | Froid (depart) |
| 5 | Jupiter | 5,203 UA | 70 km | Geante gazeuse | Frais |
| 6 | Saturne | 9,537 UA | 58 km | Geante gazeuse (anneaux) | Froid |
| 7 | Uranus | 19,191 UA | 25 km | Geante gazeuse (anneaux) | Glacial |
| 8 | Neptune | 30,07 UA | 25 km | Geante gazeuse | Glacial |

Les quatre geantes n'ont pas de sol, comme dans l'Odyssee. Uranus garde son
inclinaison de 97,8 degres (elle roule sur son orbite), Venus sa rotation
retrograde, Mars ses calottes polaires imposees - sans elles un monde aussi
froid et sec n'aurait pas un gramme de glace, puisque l'humidite y est nulle par
construction.

A cette echelle, Venus et la Terre ne sont separees que de 0,277 UA : leurs
spheres d'influence se frolent. C'est pourquoi le systeme n'active jamais que le
corps **le plus proche**. `node scripts/probe-systems.mjs` verifie que les
spheres de desactivation ne se recouvrent reellement pas, en mesurant la
distance 3D entre les corps et non la difference de rayons orbitaux (la marge la
plus serree est Venus / Jupiter, a x1,17).

### Genere aleatoirement

8 a 12 corps tires d'une seed : orbites facon Titius-Bode (chaque corps 1,35 a
1,9 fois plus loin que le precedent), climats deduits de la distance a l'etoile,
geantes gazeuses seulement au-dela de la ligne des glaces, anneaux une fois sur
trois. Le monde d'origine est reserve d'abord, parmi les mondes a eau liquide :
sans cette reserve on decollerait regulierement d'un caillou volcanique, ce qui
ne raconte rien.

## Comment c'est fait

Tout est genere par code. Aucun `.glb`, aucun `.png`, aucun son en fichier :
voir `docs/ASSETS.md` pour l'inventaire complet (maillages, textures, shaders,
audio, donnees) et `docs/CONTRACTS.md` pour l'architecture et les signatures.

En bref :

- **Relief** : cube-sphere a 6 faces, quadtree de LOD jusqu'a 9 niveaux, patches
  maillés dans un pool de Web Workers. Le champ de hauteur (`src/gen/heightField.js`)
  est partage entre worker et thread principal : ce que vous voyez est
  exactement ce contre quoi vous entrez en collision.
- **Echelle** : les planetes telluriques font 2,5 a 6,8 km de rayon, soit 15 a
  43 km de circonference (les geantes montent a 42 km de rayon dans l'Odyssee et
  70 km pour Jupiter dans Sol-1). Il faut de l'ordre d'une minute pour faire le
  tour d'un monde, ce qui laisse le temps de chercher sans lasser.
- **Precision** : rendu relatif camera. Le vaisseau est l'origine du monde
  affiche, tout le reste est place a `position - viewOrigin`. Le plus grand
  systeme fait plus de 5 millions d'unites de large sans un seul tremblement de
  float32.
- **Vol interplanetaire** : dans le vide, l'acceleration n'est pas bridee. La
  vitesse est bornee par un seul mecanisme, le gouverneur de proximite : la
  vitesse maximale vaut la distance a la surface du corps le plus proche
  multipliee par un taux fixe de **2,2**, plancher a 2 000 u/s et plafond a
  **600 000 u/s**. Concretement, a 56 km d'une surface on file deja a
  **124 000 u/s** ; en approche, la limite retombe toute seule et l'arrivee se
  fait en douceur sans toucher aux commandes.
  Un trajet de `D` a `d` prend `ln(D / d) / 2,2` secondes tant que le plafond
  n'est pas atteint : 4,7 s de Terra Prime a Aurelia, 2,8 s de Mars a la Terre,
  11,1 s de Mars a Neptune. Effet de bord precieux : le deplacement par frame
  reste proportionnel a la distance au sol (au pire 24 pour cent de celle-ci sur
  les trajets mesures), donc traverser une planete entre deux images est
  geometriquement impossible.
  Sous pulse, la trajectoire se recale sur le nez : on va ou l'on pointe, sans
  deriver de cote. Avec `C` pour verrouiller le cap sur la cible, rejoindre un
  monde demande deux touches. `node scripts/probe-flight.mjs` rejoue tout cela
  hors navigateur, pour l'Odyssee comme pour Sol-1, et echoue si un trajet sort
  du budget de temps ou si le pas par frame s'approche de la distance au sol.
- **Jour / nuit** : les planetes ne tournent pas, c'est la direction du soleil
  qui tourne dans leur repere local. Le terminateur balaie le sol, et un
  vaisseau en vol stationnaire reste au-dessus du meme rocher.
- **Biomes** : latitude, altitude, humidite et classe de temperature de l'orbite
  donnent 13 biomes, decoupes en 11 palettes. Une meme geographie donne une
  jungle sur Aurelia et un desert de cendre sur Ashkar.
- **Vie** : vegetation et faune instanciees, streamees par patch de terrain au
  fur et a mesure de la descente. Les oiseaux volent en nuees (boids), les
  herbivores paissent en troupeaux contraints au sol.

## Arborescence

```
src/
  core/     engine, entrees, audio, maths, reglages, evenements
  gen/      bruit, palettes, systeme solaire, champ de hauteur, workers, cartes
  render/   terrain LOD, ocean, atmosphere, nuages, geantes gazeuses, espace, effets
  life/     vegetation, faune
  world/    planete, systeme solaire, physique de vol
  game/     vaisseau, camera, decouverte, HUD, textes
  main.js   assemblage et boucle de jeu
docs/       ASSETS.md (inventaire), CONTRACTS.md (architecture)
scripts/    sondes hors navigateur (check-modules, list-exports, probe-*)
```

## Verifier sans navigateur

```powershell
npm run check                      # node --check sur chaque fichier de src/
node scripts/list-exports.mjs      # exports reels, a comparer a docs/CONTRACTS.md
node scripts/probe-systems.mjs     # les trois systemes du menu sont jouables
node scripts/probe-flight.mjs      # trajets Odyssee et Sol-1, budgets de temps
node scripts/probe-planets.mjs     # relief et biomes echantillonnes
```
