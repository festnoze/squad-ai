# TERRAFORM ODYSSEY

Jeu d'exploration spatiale 3D dans le navigateur. Terra Prime est morte : ses
oceans se sont retires, ses forets ont brule. Vous decollez avec un seul ordre de
mission - trouver, dans les 12 corps du systeme d'Helios Prime, une planete
terraformable.

Une planete est declaree viable lorsque trois elements y sont observes et
analyses : **des oceans**, **des arbres**, **de la vie animale**. Les trois sur
le meme monde, et la mission est un succes.

![stack](https://img.shields.io/badge/three.js-0.185-black)
![deps](https://img.shields.io/badge/deps-4-green)
![assets](https://img.shields.io/badge/assets%20binaires-0-green)

## Lancer

```powershell
cd "C:\Dev\squad-ai\Brainstorming\Space Invader"
npm install
npm run dev
```

Puis ouvrir <http://localhost:5310>. Navigateur WebGL2 requis (Chrome, Edge,
Firefox). `npm run build` produit un bundle statique dans `dist/`.

Une autre seed change tout le systeme, y compris la planete gagnante :
<http://localhost:5310/?seed=kepler>

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

## Le systeme d'Helios Prime

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

## Comment c'est fait

Tout est genere par code. Aucun `.glb`, aucun `.png`, aucun son en fichier :
voir `docs/ASSETS.md` pour l'inventaire complet (maillages, textures, shaders,
audio, donnees) et `docs/CONTRACTS.md` pour l'architecture et les signatures.

En bref :

- **Relief** : cube-sphere a 6 faces, quadtree de LOD jusqu'a 9 niveaux, patches
  maillés dans un pool de Web Workers. Le champ de hauteur (`src/gen/heightField.js`)
  est partage entre worker et thread principal : ce que vous voyez est
  exactement ce contre quoi vous entrez en collision.
- **Echelle** : les planetes font 2,6 a 6,8 km de rayon (42 km pour les geantes),
  soit 16 a 43 km de circonference. Il faut de l'ordre d'une minute pour en faire
  le tour, ce qui laisse le temps de chercher sans lasser.
- **Precision** : rendu relatif camera. Le vaisseau est l'origine du monde
  affiche, tout le reste est place a `position - viewOrigin`. Le systeme fait
  3,9 millions d'unites de large sans un seul tremblement de float32.
- **Vol interplanetaire** : dans le vide, l'acceleration n'est pas bridee. La
  vitesse est bornee par un seul mecanisme, le gouverneur de proximite : la
  vitesse maximale vaut la distance au corps le plus proche multipliee par un
  taux fixe. Loin de tout, on depasse le million d'unites par seconde ; en
  approche, la limite retombe toute seule et l'arrivee se fait en douceur.
  Un trajet de `D` a `d` prend `ln(D / d) / taux` secondes, soit environ 9 s
  entre Terra Prime et Aurelia. Effet de bord precieux : le deplacement par
  frame reste proportionnel a la distance au sol, donc traverser une planete
  entre deux images est geometriquement impossible.
  Sous pulse, la trajectoire se recale sur le nez : on va ou l'on pointe, sans
  deriver de cote. Avec `C` pour verrouiller le cap sur la cible, rejoindre un
  monde demande deux touches. `node scripts/probe-flight.mjs` rejoue tout cela
  hors navigateur et verifie les temps de trajet.
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
```
