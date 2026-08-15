# VELOCITRON - contrats de modules

Source de verite pour l'ecriture parallele des modules. Toute signature listee
ici est **figee** : un module peut ajouter des exports, jamais en changer un.

---

## 0. Regles globales (valables pour tous les fichiers)

- Cible : navigateur, **ES modules natifs, zero build**. Servi par `serve.py`.
- three.js **r169** vendorise dans `./vendor/three.module.js`, importe par
  l'importmap de `index.html` : `import * as THREE from 'three';`
  **Les addons `three/examples/jsm/*` n'existent pas ici.** Pas d'EffectComposer,
  pas d'UnrealBloomPass, pas de GLTFLoader, pas de lil-gui, pas de CDN.
- **Zero asset binaire.** Toutes les textures sont dessinees dans un
  `<canvas>` 2D, tous les sons sont synthetises en Web Audio, toute la geometrie
  est generee en code. Aucun `fetch`, aucune URL externe.
- Le renderer **n'active PAS** `logarithmicDepthBuffer` : les `ShaderMaterial`
  custom n'ont donc pas besoin des chunks `logdepthbuf_*`.
- Rendu HDR : la scene est rendue dans une `WebGLRenderTarget` `HalfFloatType`
  en espace **lineaire**, `renderer.toneMapping = THREE.NoToneMapping`. Le
  tonemapping ACES + la conversion sRGB sont faits **a la main** dans la passe
  finale de `post.js`. Consequence : les materiaux peuvent emettre des valeurs
  > 1 (c'est ce qui declenche le bloom), et toute texture d'albedo doit avoir
  `texture.colorSpace = THREE.SRGBColorSpace` (les normal/rough/AO restent en
  `THREE.NoColorSpace`).
- Unites : metres, secondes, radians. 1 unite three = 1 metre.
- Langue de l'interface : **francais**. Dans les textures canvas et le 3D,
  **pas d'accents** (rendu de police peu fiable) ; le DOM peut en avoir.
- **Ne jamais utiliser le caractere tiret cadratin** dans le code, les
  commentaires, l'UI ou la doc. Utiliser `-` ou des parentheses.
- Style : commentaires utiles seulement, en anglais dans le code (comme le reste
  du depot), noms explicites, pas de code mort.
- Perf cible : 60 fps en 1920x1080 sur un GPU integre recent. Budget indicatif :
  < 400 draw calls, < 1.2M triangles. Utiliser `InstancedMesh` pour tout ce qui
  est repete (batiments, pods lumineux, rambardes, etoiles).
- Chaque module exporte une fonction `createX(...)` et, si il alloue des
  ressources GPU, une methode `dispose()`.
- **Zero allocation par frame** dans les chemins chauds (`update`) : vecteurs
  scratch au niveau module, mais **jamais partages entre deux fonctions qui
  peuvent s'imbriquer** (piege deja rencontre dans ce depot).

### Verification avant de rendre la main

```bash
cp src/<mon-fichier>.js /tmp/check.mjs && node --check /tmp/check.mjs
```
(sous Windows, ecrire dans le dossier scratch). Le fichier doit passer le check
syntaxique. Le module ne doit importer que : `three`, `./config.js`, et les
modules explicitement autorises dans sa section.

---

## 1. Conventions geometriques

### Repere du monde
`Y` vers le haut. Le circuit est pose autour de l'origine.

### Espace piste (track space)
Un vaisseau n'est jamais represente par une position monde libre : son etat est
`(s, x, h, yaw)`.

| champ | sens |
|---|---|
| `s`   | abscisse curviligne le long de l'axe du circuit, dans `[0, track.length)` |
| `x`   | deport lateral en metres, positif vers `frame.right` |
| `h`   | hauteur au dessus de la surface de la route, le long de `frame.up` |
| `yaw` | cap du vaisseau **relatif a la tangente**, positif = nez vers la droite |

Position monde : `frame.pos + frame.right * x + frame.up * h`.

### Orientation d'un maillage de vaisseau
**Le nez du vaisseau pointe vers `-Z` local**, comme une camera three.js.
L'orientation se construit avec
`m.makeBasis(right, up, backward)` ou `backward = -forward`.

---

## 2. `src/config.js` (deja ecrit, ne pas modifier)

Exporte `GAME_TITLE`, `TRACK_NAME`, `PALETTE`, `TRACK`, `SHIP`, `RACE`,
`CAMERA`, `POST`, `KEYS`, `AUDIO`, `DEBUG`. Lire ce fichier avant de coder :
toute constante de reglage doit venir de la, pas etre re-ecrite en dur.

---

## 3. `src/textures.js`

Aucune dependance hors `three` et `./config.js`.

```js
export function createTextures(renderer) -> Textures
```

`renderer` sert uniquement a lire `renderer.capabilities.getMaxAnisotropy()`.
Toutes les textures sont des `THREE.CanvasTexture` (ou `DataTexture` pour le
bruit), `wrapS/wrapT = RepeatWrapping` sauf mention contraire, mipmaps actifs,
`anisotropy` au maximum pour les surfaces vues en biais (route, murs).

Champs obligatoires de `Textures` :

| champ | type | description |
|---|---|---|
| `road` | Texture | bitume sombre granuleux, marquages lateraux, tuile 8m x 32m, `repeat` gere par `track.js` |
| `roadNormal` | Texture | normal map correspondante (rainures, joints) |
| `roadRough` | Texture | roughness/metalness packee (canal G = rough) ou roughness seule |
| `roadDetail` | Texture | chevrons + numeros de secteur, alpha, utilisee en decals |
| `wall` | Texture | panneaux techniques, tuile 8m x 4m |
| `wallNormal` | Texture | normal map des panneaux |
| `wallEmissive` | Texture | bandes neon des murs, noir sauf les bandes |
| `edgeStrip` | Texture | degrade de bande lumineuse (1D vertical) |
| `boostPad` | Texture | chevrons d'acceleration, tres emissifs |
| `checker` | Texture | damier de ligne d'arrivee |
| `hull` | Texture | coque du vaisseau : plaques, lignes de panneaux, marquages |
| `hullNormal` | Texture | normal map de coque |
| `hullEmissive` | Texture | bandes lumineuses de coque (a teinter par livree) |
| `cockpit` | Texture | verriere fumee avec reflets |
| `windows` | Texture | facade de gratte-ciel, fenetres allumees aleatoires |
| `windowsEmissive` | Texture | idem, canal emissif |
| `billboard` | Texture | panneau publicitaire holographique (texte neon) |
| `sky` | Texture | equirectangulaire 2048x1024, degrade de nuit + nebuleuse + horizon urbain diffus |
| `grid` | Texture | grille luminescente pour le sol lointain |
| `spark` | Texture | particule ronde douce (alpha) |
| `smoke` | Texture | particule de fumee douce |
| `flare` | Texture | halo de reacteur |
| `ring` | Texture | anneau de choc |
| `noise` | Texture | bruit 256x256 RGBA, `NoColorSpace`, pour le grain et les shaders |
| `dispose()` | fn | libere tout |

`createTextures` doit s'executer en **moins de 400 ms**. Un helper interne
`makeCanvas(w, h)` et un generateur de bruit deterministe (pas de `Math.random`
non graine : utiliser un PRNG local `mulberry32` pour que le rendu soit
reproductible) sont attendus.

---

## 4. `src/track.js`

Depend de `three`, `./config.js`, `./textures.js` (via l'objet passe).

```js
export function createTrack(textures) -> Track
```

### Trace demande
Circuit ferme d'environ `TRACK.targetLength` metres, dessine a la main
(tableau de points de controle), avec dans l'ordre :

1. une ligne droite de depart/arrivee large et plate (~350 m),
2. une chicane rapide gauche/droite,
3. un long virage releve a 180 degres (devers jusqu'a 45 degres),
4. une montee vers un **tunnel** (~180 m) qui debouche en descente,
5. une bosse franche qui **fait decoller** l'appareil,
6. un grand courbe rapide en devers au dessus du vide,
7. une section technique lente (double apex, piste retrecie a `halfWidthMin`),
8. la remontee vers la ligne droite, avec 2 plaques de turbo.

Contraintes verifiables (a auto-verifier avec un script node avant livraison) :
- courbe **fermee** et C1 continue (`THREE.CatmullRomCurve3` avec `closed=true`),
- rayon de courbure horizontal minimum >= 55 m,
- pente absolue maximum <= 16 %,
- pas d'auto-intersection en XZ a moins de 35 m d'ecart lateral, **sauf** si la
  difference d'altitude est > 25 m (passage superieur autorise, et alors il faut
  un viaduc visible),
- longueur totale dans `[3800, 4800]`.

### Frames
Le repere est propage par **parallel transport** le long de la courbe (pas de
`computeFrenetFrames` : ca vrille sur les portions droites), puis le residu de
torsion sur la boucle fermee est reparti uniformement sur tous les echantillons.
Le devers (roll) est ajoute apres coup par rotation autour de la tangente.

```js
track.length            // number, longueur totale de l'axe (m)
track.sampleCount       // number
track.spacing           // number, metres entre deux echantillons
track.group             // THREE.Group, tout le decor de piste, a ajouter a la scene
track.startS            // number, abscisse de la ligne de depart/arrivee
track.checkpoints       // number[], abscisses croissantes des checkpoints (anti raccourci)

track.makeFrame()       // -> objet frame neuf (a allouer une fois par appelant)
track.at(s, frame)      // remplit et retourne frame, s est wrappe automatiquement
track.wrapS(s)          // -> number dans [0, length)
track.deltaS(a, b)      // -> plus court ecart signe de a vers b, dans [-L/2, L/2]
track.toWorld(s, x, h, outVec3)   // -> outVec3
track.halfWidthAt(s)    // -> number
track.padAt(s, x)       // -> boolean, true si (s,x) est sur une plaque de turbo
track.outlinePoints     // Array<{x, y}> normalise dans [-1,1], pour le minimap
track.dispose()
```

Structure d'une frame (tous les champs presents, objets reutilises) :

```js
{
  s: 0,
  pos: THREE.Vector3,        // point de l'axe, sur la surface de la route
  tangent: THREE.Vector3,    // unitaire, sens de la course
  up: THREE.Vector3,         // normale a la route, tient compte du devers
  right: THREE.Vector3,      // = tangent x up, unitaire
  halfWidth: 11,             // demi largeur de la route a cet endroit
  curvature: 0,              // courbure horizontale signee, 1/m, + = tourne a droite
  vertCurvature: 0,          // courbure verticale signee, 1/m, negatif = sommet de bosse
  roll: 0,                   // devers en radians
}
```

`track.at` est appele plusieurs fois par frame et par vaisseau : **interpolation
lineaire entre deux echantillons pre-calcules, zero allocation, pas de recherche
lineaire** (index direct `s / spacing`).

### Geometrie construite dans `track.group`
- surface de route (`MeshStandardMaterial`, `road` + `roadNormal` + roughness,
  `TRACK.roadColumns` colonnes, UV en metres),
- bandes lumineuses emissives sur les deux bords (couleur `PALETTE.cyan`, valeur
  emissive > 1 pour attraper le bloom), plus une ligne centrale discrete,
- murs des deux cotes (`TRACK.wallHeight`), face interieure texturee + emissive,
- pods lumineux instancies tous les `TRACK.lightStripSpacing` m,
- portiques instancies/repetes tous les `TRACK.gantrySpacing` m,
- plaques de turbo (au moins 4, aux abscisses exposees dans `track.boostPads`),
- ligne de depart/arrivee en damier + portique principal,
- tunnel ferme sur la section prevue (interieur texture, anneaux lumineux),
- viaduc / pylones sous la piste la ou elle survole le vide.

Le sol/decor lointain n'est **pas** ici : il appartient a `world.js`.

---

## 5. `src/post.js`

Depend de `three` et `./config.js` uniquement.

```js
export function createPost(renderer, scene, camera) -> Post
post.render(dt)          // rend la scene puis toutes les passes, jusqu'a l'ecran
post.setSize(w, h)       // en pixels physiques
post.params              // objet mutable, voir POST dans config.js
                         // + params.speed (0..1) et params.shake (0..1) pilotes par main.js
post.dispose()
```

Pipeline attendu, en `WebGLRenderTarget` `HalfFloatType`, sans addon :
1. rendu de la scene dans `sceneRT` (lineaire, sans tonemapping),
2. **bright pass** : seuil `POST.bloomThreshold` avec knee doux, demi resolution,
3. **blur separable gaussien** sur `POST.bloomLevels` niveaux de mipmap (down
   puis up avec accumulation, style "dual filter"), rayon `POST.bloomRadius`,
4. **passe finale** plein ecran : composite scene + bloom, flou radial vers le
   centre pilote par `params.speed`, aberration chromatique, vignettage, grain
   anime, tonemapping ACES, puis conversion lineaire -> sRGB **a la main**.

Les quads plein ecran utilisent un unique `THREE.BufferGeometry` triangle
couvrant l'ecran et des `RawShaderMaterial`/`ShaderMaterial` sans lumiere.
Attention : ne pas oublier `renderer.setRenderTarget(null)` avant la passe
finale, et re-appliquer `setSize` sur toutes les cibles.

---

## 6. `src/ship.js`

Depend de `three`, `./config.js`. Recoit `track`, `textures` en argument.

```js
export function createShipMesh(textures, color) -> THREE.Group
export function createShip(opts) -> Ship
export function updateShip(ship, controls, dt, track)
export function respawnShip(ship, track)
```

`opts = { track, textures, index, isPlayer, name, color }`.

`createShipMesh` : appareil anti-gravite construit en code (pas de primitive
brute visible), longueur `SHIP.length`, nez vers **-Z**, avec fuselage effile,
deux nacelles laterales, ailerons, verriere teintee, 2 tuyeres arriere
(reperees par `mesh.userData.thrusters = [Object3D, Object3D]`, positionnees a
la sortie des tuyeres, +Z local) et bandes emissives a la couleur `color`.
Le materiau emissif de la coque doit etre accessible via
`mesh.userData.glowMaterials = [Material, ...]` pour que `fx.js` puisse le
pulser. Origine du groupe au centre geometrique, au niveau du plancher.

`controls` (objet reutilise, jamais alloue par frame) :

```js
{ thrust: 0..1, brake: 0..1, steer: -1..1, airLeft: 0|1, airRight: 0|1, boost: bool }
```

### Etat `Ship`

```js
{
  index, name, isPlayer, color, mesh,
  s, x, h, yaw,          // etat piste
  speed,                 // m/s le long du cap
  vLat, vh,              // vitesses laterale et verticale
  roll, pitch,           // attitude cosmetique
  shield, boostEnergy,
  boostTimer, padBoostTimer,
  lap, lastCheckpoint, finished, finishTime,
  lapStartTime, lapTimes: [], bestLap,
  totalProgress,         // lap * track.length + s, sert au classement
  destroyed, respawnTimer,
  worldPos: Vector3, quat: Quaternion,
  events: { wallHit: 0, padHit: false, land: 0, shipHit: 0 }, // remis a zero par updateShip
}
```

### Modele physique (a implementer exactement)

```
frame = track.at(s)
// 1 - longitudinal
accel  = SHIP.thrust * controls.thrust
accel -= SHIP.brakeForce * controls.brake
if (boostTimer > 0)    accel += SHIP.boostAccel
if (padBoostTimer > 0) accel += SHIP.padBoostAccel
// la poussee s'efface sur les 10 derniers % avant le plafond, sinon un rappel
// doux ne gagne jamais contre une poussee constante et l'appareil se stabilise
// largement au dessus
cap = (boostTimer > 0 || padBoostTimer > 0) ? SHIP.boostMaxSpeed : SHIP.maxSpeed
nearCap = clamp01((|speed| - cap * 0.9) / (cap * 0.1))
accel *= (1 - nearCap)                                           // idem pour les turbos
speed += accel * dt
// la trainee s'oppose au mouvement : soustraite sans signe, un appareil a
// l'arret sur la grille recule tout seul pendant le decompte
dragAccel = (SHIP.drag * speed * speed + SHIP.rollingDrag) * dt
speed = speed > 0 ? max(0, speed - dragAccel) : min(0, speed + dragAccel)
speed -= SHIP.airbrakeDrag * speed * (airLeft + airRight) * 0.5 * dt
if (speed > cap) speed += (cap - speed) * min(1, 2.5 * dt)      // retour doux
speed = max(speed, SHIP.reverseSpeed)

// 2 - cap
authority = SHIP.steerRate * lerp(1, SHIP.steerSpeedFalloff, clamp01(|speed| / SHIP.maxSpeed))
yaw += controls.steer * authority * dt
yaw += (controls.airRight - controls.airLeft) * SHIP.airbrakeYaw * dt
yaw -= yaw * SHIP.yawDamping * dt          // realignement sur la tangente
yaw  = clamp(yaw, -1.0, 1.0)

// 3 - lateral
// LA charge en virage : sans elle l'amortissement de cap realigne l'appareil
// gratuitement et tout le circuit se fait a fond sans toucher une touche. Le
// devers en annule une partie, c'est ce qui rend le 180 releve beaucoup plus
// rapide que l'epingle a plat.
load  = speed * speed * frame.curvature * SHIP.corneringLoad
      - SHIP.gravity * sin(frame.roll)
vLat -= load * dt
vLat -= (controls.airRight - controls.airLeft) * SHIP.airbrakeSlide * dt   // vers l'exterieur du virage qu'il ouvre
vLat += speed * sin(yaw) * SHIP.slideFromYaw * dt
vLat -= vLat * SHIP.gripLateral * dt
x    += (speed * sin(yaw) + vLat) * dt

// 4 - abscisse, corrigee de la courbure (le bord exterieur est plus long)
denom = max(0.25, 1 - x * frame.curvature)
s = track.wrapS(s + speed * cos(yaw) * dt / denom)

// 5 - hauteur, avec effet de bosse
vh -= speed * speed * frame.vertCurvature * dt          // sommet de bosse = decollage
if (h < SHIP.hoverHeight * 2.2)
     vh += ((SHIP.hoverHeight - h) * SHIP.hoverStiffness - vh * SHIP.hoverDamping) * dt
else vh -= SHIP.gravity * dt
h += vh * dt
if (h < 0.05) { if (vh < -6) events.land = -vh; h = 0.05; vh = 0 }

// 6 - murs
limit = frame.halfWidth - SHIP.halfWidth
if (|x| > limit) {
  impact = |speed * sin(yaw) + vLat|
  x = sign(x) * limit
  vLat = -0.22 * vLat
  yaw *= 0.35
  if (impact > 6) { speed -= speed * SHIP.wallSpeedLoss * clamp01(impact / 30)
                    shield -= impact * SHIP.wallDamageScale
                    events.wallHit = impact }
  else { speed -= SHIP.wallScrapeDrag * dt
         shield -= impact * SHIP.wallDamageScale * 0.25 * dt * 10
         events.wallHit = max(events.wallHit, impact * 0.3) }
}
```

Puis : plaques de turbo (`track.padAt`), regen de `boostEnergy`
(`SHIP.boostRegen`), destruction quand `shield <= 0` (mise en `destroyed`,
`respawnTimer = SHIP.respawnTime`, le maillage devient invisible), attitude
cosmetique (`roll`, `pitch` lerpes vers leur cible), puis mise a jour de
`worldPos`, `quat`, `mesh.position`, `mesh.quaternion`, `totalProgress`.

Le declenchement du turbo (touche) consomme `SHIP.boostCost` d'energie et arme
`boostTimer = SHIP.boostDuration` ; il est ignore si l'energie est insuffisante.

**Collisions entre vaisseaux** : `export function resolveShipCollisions(ships, track, dt)`
appele une fois par frame par `race.js`. Un choc reel est une impulsion et le
reste ; deux coques qui frottent produisent une poussee et des degats **par
seconde** (sinon tout depend de la frequence d'images). Deux vaisseaux se touchent si
`|deltaS| < SHIP.length` et `|dx| < SHIP.width`. Reponse : separation laterale
symetrique, echange d'impulsion sur `vLat`, degats `SHIP.shipDamageScale`,
`events.shipHit`.

---

## 7. `src/ai.js`

Depend de `three`, `./config.js`, `./ship.js`.

```js
export function createAI(ship, track, skill) -> AI     // skill dans [0,1]
export function updateAI(ai, dt, context) -> controls  // l'objet controls du pilote
```

`context = { ships, playerProgress, raceTime, state }`.

Comportement attendu :
- **ligne de course** pre-calculee a la construction : pour chaque echantillon
  de piste, un deport lateral cible qui coupe a la corde (issu de la courbure
  lissee sur quelques dizaines de metres), plus un bruit propre a chaque pilote,
- **vitesse cible** issue de la courbure a venir (`sqrt(gripLat / |curvature|)`,
  regardee ~2.5 s devant), moderee par `skill`,
- freinage et aerofreins engages quand la vitesse depasse la cible,
- evitement lateral des autres appareils dans les 25 m devant,
- turbo utilise dans les lignes droites quand l'energie est pleine,
- `RACE.rubberBand` : leger bonus/malus de vitesse cible selon l'ecart au joueur,
  jamais plus de `RACE.rubberBand` de la vitesse max, et jamais actif dans les
  2 dernieres secondes d'une course serree (pas de triche visible).

L'IA ne doit **jamais** ecrire directement dans l'etat physique du vaisseau :
elle ne produit que des `controls`.

---

## 8. `src/world.js`

Depend de `three`, `./config.js`. Recoit `(scene, track, textures)`.

```js
export function createWorld(scene, track, textures) -> World
world.update(dt, cameraPos, playerSpeed01)
world.group
world.dispose()
```

Contenu :
- `scene.background` = la texture `sky` en `EquirectangularReflectionMapping`,
  `scene.environment` = un `PMREMGenerator` construit depuis cette meme texture
  (three r169 : `pmrem.fromEquirectangular(tex).texture`) pour que la coque
  metallique ait des reflets. Detruire le PMREM apres usage.
- Brouillard : `THREE.FogExp2(PALETTE.fog, 0.0016)`.
- Lumieres : une `HemisphereLight` faible (ciel violet / sol presque noir), une
  `DirectionalLight` rasante bleu froid **avec ombres** (`shadowMap` PCFSoft,
  cible suivant le joueur, `shadow.camera` orthographique serree sur ~140 m),
  et quelques `PointLight` de couleur le long des sections signature (maximum 6
  actives, activees/desactivees selon la distance a la camera dans `update`).
- Ville de fond : gratte-ciel instancies (>= 400 instances, 3 profils de
  batiment) places **hors** de l'emprise du circuit, avec facades emissives.
  Quelques tours signatures plus hautes avec antennes clignotantes.
- Sol : grand plan/grille luminescente sous le circuit, plus des reliefs bas
  (mesa) pour cacher l'horizon.
- Trafic aerien : 12 a 20 vehicules lumineux instancies qui suivent des
  trajectoires en boucle au dessus de la ville (simple, purement visuel).
- Panneaux publicitaires holographiques le long du circuit (utiliser
  `track.at` pour les placer sur les bords exterieurs, hors de la piste).
- Etoiles : `Points` avec la texture `spark`.
- `update` fait bouger le trafic, fait clignoter les antennes, recentre les
  elements infinis (grille, etoiles) sur la camera et recale l'ombre.

Aucun element de `world.js` ne doit intersecter la piste : verifier la distance
a l'axe via `track.at` avant de placer un objet.

---

## 9. `src/fx.js`

Depend de `three`, `./config.js`.

```js
export function createFX(scene, textures) -> FX
fx.attach(ship)                      // cree reacteurs + trainee pour un vaisseau
fx.update(dt, camera, ships)
fx.sparks(worldPos, normal, amount)  // gerbe d'etincelles sur choc de mur
fx.explode(worldPos)                 // destruction d'un appareil
fx.boostBurst(ship)                  // anneau de choc + flamme longue
fx.dust(worldPos, amount)            // impact au sol / atterrissage
fx.dispose()
```

Implementation : **un seul** systeme de particules `Points` avec un pool de
2000 particules maximum et un `BufferAttribute` mis a jour partiellement
(`needsUpdate` + `updateRanges`), `AdditiveBlending`, `depthWrite = false`.
Les reacteurs sont des cones/plans additifs attaches a
`ship.mesh.userData.thrusters`, dont la longueur et la couleur suivent
`ship.speed`, `controls.thrust` et l'etat de turbo (`PALETTE.thrustCore` ->
`PALETTE.boostCore` en turbo). Les trainees sont des rubans (`BufferGeometry`
en `TriangleStrip` maison ou `LineSegments` epaissis) sur les 24 dernieres
positions de chaque appareil, fondues en alpha.

Pas de `Sprite` par particule (trop de draw calls).

---

## 10. `src/hud.js` + `styles.css`

Depend de rien (DOM pur). **Le meme agent ecrit `styles.css`.**
Les identifiants DOM sont figes par `index.html` : les lire avant d'ecrire.

```js
export function createHUD(track) -> HUD
hud.show() / hud.hide()
hud.setSpeed(kph, ratio01)          // dessine aussi la jauge canvas #gauge
hud.setShield(ratio01)
hud.setBoost(ratio01, ready)
hud.setLap(lap, total)
hud.setPosition(pos, total)
hud.setTimes({ current, last, best })   // ms, null = "--:--.---"
hud.setDelta(ms | null)                 // ecart au meilleur tour, colore
hud.setStandings(rows)                  // [{pos, name, gap, isPlayer, color}]
hud.setMinimap(dots)                    // [{u, v, color, isPlayer}] en [-1,1]
hud.setCountdown(text | null)           // "3", "2", "1", "GO", null
hud.banner(title, sub, ms)
hud.toast(text)
hud.hit(intensity01)                    // flash rouge
hud.boostFlash()
hud.speedFx(ratio01)                    // vignette de vitesse
hud.results(rows, title, sub)           // remplit #results-body
hud.formatTime(ms) -> "1:23.456"
```

`hud.setMinimap` dessine sur `#minimap` le trace issu de `track.outlinePoints`
(trace une fois dans un canvas hors ecran, puis blit + points a chaque frame).
La jauge `#gauge` est un arc de 240 degres, gradue, avec une aiguille et un
secteur rouge au dela de 90 % de la vitesse max.

`styles.css` : esthetique Wipeout / cyberpunk. Fond noir, typo condensee
(`system-ui` / `Arial Narrow` / monospace, **aucune webfont distante**),
neon cyan et magenta, coins coupes (`clip-path`), fines lignes de scan, legere
animation de glitch sur les titres. Tout doit rester lisible en 1280x720 comme
en 2560x1440 (unites relatives, `clamp()`). Aucune image externe.

---

## 11. `src/audio.js`

Depend de `./config.js`. **Web Audio pur, zero fichier son.**

```js
export function createAudio() -> Audio
audio.resume()                     // a appeler sur le premier clic utilisateur
audio.setMasterVolume(v01)
audio.toggleMute() -> boolean
audio.startEngine() / audio.stopEngine()
audio.setEngine({ speed01, throttle01, boost, airborne })
audio.startMusic() / audio.stopMusic()
audio.countdownBeep(step)          // step 3,2,1 puis 0 pour le GO
audio.scrape(intensity01)
audio.impact(intensity01)
audio.boost()
audio.lapChime(isBest)
audio.explosion()
audio.finish(won)
audio.update(dt)
audio.dispose()
```

- Moteur : 3 oscillateurs (saw + square + sub) accordes sur une frequence
  pilotee par `speed01`, filtre passe bas resonnant qui s'ouvre avec le
  throttle, plus un bruit filtre pour le vent qui monte avec la vitesse.
  Aucune coupure audible : tout est module par rampes
  (`setTargetAtTime`), jamais par recreation de noeuds.
- Musique : sequenceur `AUDIO.bpm` avec un ordonnanceur a 25 ms d'avance
  (lookahead), kick synthetise, snare bruite, basse acide (filtre resonnant
  module), arpege 16e sur une gamme mineure, avec un delai ping-pong. La
  musique doit boucler indefiniment sans derive de tempo.
- Tout passe par un `GainNode` maitre, plus un `DynamicsCompressorNode` avant
  la destination pour eviter la saturation.

---

## 12. `src/race.js`

Depend de `./config.js`, `./ship.js`, `./ai.js`.

```js
export function createRace(opts) -> Race    // opts = { track, ships, ais, laps }
race.state          // 'countdown' | 'racing' | 'finished'
race.time           // secondes depuis le GO (negatif pendant le decompte)
race.update(dt, playerControls)
race.standings      // [{ ship, pos, gap }] trie, recalcule chaque frame
race.playerShip
race.results        // rempli quand state === 'finished'
race.events         // { countdown: n|null, lap: {ship, time, isBest}|null, finish: bool, ... }
                    // consomme et remis a zero par main.js chaque frame
race.placeOnGrid()
```

Regles : `RACE.laps` tours ; un tour n'est valide que si tous les
`track.checkpoints` ont ete franchis dans l'ordre ; le classement se fait sur
`totalProgress` ; l'IA continue de courir apres l'arrivee du joueur jusqu'a ce
que tout le monde ait fini ou 20 s de plus ; les temps sont en millisecondes.
`race.update` appelle `updateAI`, `updateShip` pour tous les vaisseaux et
`resolveShipCollisions`.

---

## 13. `src/input.js`

```js
export function createInput(target) -> Input
input.controls      // objet controls reutilise, cf. ship.js
input.update()      // recalcule controls depuis l'etat clavier
input.pressed(action)   // -> bool, front montant consomme (ex: 'boost', 'respawn')
input.isDown(action)
input.onAction(action, cb)   // 'pause', 'camera', 'mute', 'respawn'
input.enabled = true
input.dispose()
```

Mappings issus de `KEYS`. Les touches gerees doivent appeler
`preventDefault()` (surtout `Space` et les fleches) et le module doit relacher
toutes les touches sur `blur`.

---

## 14. `src/main.js`

Assemble tout. Depend de tous les modules ci-dessus.

Sequence de boot :
1. cree le renderer WebGL2 (`antialias: false`, on a du post-process ;
   `powerPreference: 'high-performance'`, `NoToneMapping`,
   `outputColorSpace = SRGBColorSpace` mais la passe finale ecrit en sRGB a la
   main donc **la passe finale doit desactiver toute conversion automatique**),
2. affiche `#screen-loading` et avance `#loading-fill` entre chaque etape
   (`await` d'une micro-pause pour laisser le DOM peindre),
3. `createTextures` -> `createTrack` -> `createWorld` -> `createFX` ->
   `createShip` x4 -> `createAI` x3 -> `createRace` -> `createPost` ->
   `createHUD` -> `createAudio` -> `createInput`,
4. bascule sur `#screen-menu`, le bouton `#btn-start` demarre la course
   (et `audio.resume()`).

Boucle : `requestAnimationFrame`, `dt` clampe a `1/30`, ordre =
input -> race.update -> fx.update -> world.update -> camera -> hud -> audio ->
post.render.

Camera : poursuite ressort (`CAMERA.chaseLag`) derriere le vaisseau du joueur,
FOV interpole de `CAMERA.fovBase` a `CAMERA.fovAtMaxSpeed` avec la vitesse,
secousse a l'impact, mode cockpit sur `C`. La camera doit rester **au dessus de
la surface de la route** (utiliser `track.at` pour la contraindre) et ne jamais
traverser un mur.

Etats : `loading`, `menu`, `countdown`, `racing`, `paused`, `results`.
`Echap` met en pause (et coupe le moteur audio). Le redimensionnement met a jour
renderer, camera et post.

Exposer `window.game = { track, ships, race, post, world, audio, hud, renderer, scene, camera }`
pour le debug depuis la console, et `window.__ready = true` une fois le menu
affiche (utilise par les tests automatises).

---

## 15. Non negociable

- Le jeu doit **demarrer sans une seule erreur console** et tourner a 60 fps.
- Aucun `TODO`, aucun placeholder, aucune fonction vide livree.
- Chaque module doit fonctionner meme si un autre est encore en cours
  d'ecriture : ne jamais importer un symbole non liste ici.
