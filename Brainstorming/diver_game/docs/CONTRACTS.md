# ABYSSE - contrat de modules

Source de verite pour les interfaces entre modules. Tout module respecte
strictement les signatures decrites ici, sinon l'integration casse.

## Regles communes

- ES modules natifs, aucun build, aucun paquet npm.
- `import * as THREE from 'three'` uniquement (importmap vers `./vendor/three.module.js`, r169).
- Le seul autre import autorise est `./config.js`. Un module ne doit **jamais**
  importer un autre module de gameplay (pas de dependance croisee).
- Aucun asset binaire, aucune URL externe. Tout est procedural (canvas 2D,
  BufferGeometry, WebAudio).
- Le niveau de la mer est `y = 0`. Sous l'eau `y < 0`. La profondeur affichee
  vaut `-y`.
- Pas de tiret cadratin dans le code, les commentaires, l'UI ou la doc.
- Commentaires et identifiants en anglais, textes destines au joueur en francais
  sans accents problematiques (l'UI utilise une police standard, les accents
  passent, mais on reste sobre).
- Chaque module exporte une factory `createX(...)` qui renvoie un objet avec au
  minimum `update(dt, ctx)` et `dispose()`.

## Performances

- Cible: 60 fps sur un GPU integre. Instancier (`InstancedMesh`) tout ce qui se
  repete (rochers, coraux, kelp, poissons de banc).
- Pas de `new` par frame dans les boucles chaudes: utiliser des vecteurs
  temporaires alloues au niveau du module.
- Materiaux partages autant que possible.

---

## `textures.js`

```js
export function createTextures(): Textures
```

`Textures` est un objet plat. **Toutes** ces cles doivent exister et etre des
`THREE.Texture` valides (generees via canvas 2D), plus `dispose()`.

| cle | usage | notes |
|---|---|---|
| `sand` | fond sableux | tileable, `RepeatWrapping`, `SRGBColorSpace` |
| `sandNormal` | relief du sable | normal map, pas de colorSpace sRGB |
| `rock` | rochers et falaises | tileable |
| `rockNormal` | relief rocheux | normal map |
| `coral` | surfaces coralliennes | tileable, colore |
| `kelp` | lame de kelp | avec alpha, non tileable |
| `caustics` | motif de caustiques | tileable, niveaux de gris clairs |
| `noise` | bruit generique | tileable, gris |
| `bubble` | sprite bulle | alpha radial |
| `mote` | sprite neige marine | petit point doux |
| `glow` | halo radial | pour bioluminescence et lampes |
| `godray` | bande verticale douce | alpha degressif haut/bas |
| `flare` | halo de soleil | vu depuis sous la surface |
| `fishScale` | ecailles | tileable |
| `sharkSkin` | peau de requin | tileable, gris |
| `hullPanel` | coque du sous-marin | panneaux et rivets |
| `hullRust` | rouille de l epave | tileable brun |
| `beachSand` | sable de plage | tileable clair |
| `foliage` | feuillage d ile | avec alpha |
| `palmLeaf` | palme | avec alpha |
| `plank` | bois du ponton | tileable |
| `labWall` | mur du laboratoire | tileable clair |
| `seaFoam` | ecume de surface | tileable, alpha |
| `waterNormal` | normal map de surface | tileable, ondulations |

---

## `water.js`

```js
export function createWater(scene, textures, renderer): Water
```

Possede l'eau **et tout l'eclairage** de la scene.

```js
Water = {
  group,          // THREE.Group deja ajoute a la scene
  sun,            // THREE.DirectionalLight
  ambient,        // THREE.HemisphereLight
  update(dt, ctx),
  dispose(),

  // ctx = {
  //   camera,           THREE.PerspectiveCamera
  //   time,             secondes depuis le boot
  //   depth,            profondeur de la camera en metres (>= 0)
  //   aboveWater,       bool, la camera est hors de l eau
  //   biome,            id de biome (voir config.BIOMES)
  //   speed,            vitesse du joueur en m/s
  //   lampOn,           bool
  // }

  spawnBubbles(position, count, spread),  // gerbe de bulles ponctuelle
  spawnBlood(position, amount),           // nuage sombre a la mort d une creature
  fogColorAt(depth, biome) -> THREE.Color,
}
```

Doit fournir: plan de surface anime vu des deux cotes, caustiques projetees en
eau peu profonde, god rays, neige marine autour de la camera, bulles, halo de
soleil, brouillard exponentiel pilote par la profondeur et le biome
(`scene.fog`), extinction progressive de la lumiere avec la profondeur.

---

## `world.js`

```js
export function createWorld(scene, textures): World
```

```js
World = {
  group,
  update(dt, ctx),   // ctx = { time, camera, playerPos }
  dispose(),

  heightAt(x, z) -> number,    // altitude du terrain (negatif sous l eau,
                               // positif sur l ile). Doit etre rapide.
  biomeAt(x, z) -> string,     // une valeur de config.BIOMES
  isLand(x, z) -> bool,        // heightAt > 0.2

  // Correction de penetration contre les rochers, epave, ile.
  // Renvoie un vecteur de deplacement a ajouter, ou null si aucun contact.
  collide(position, radius) -> THREE.Vector3 | null,

  points: {
    subAnchor,    THREE.Vector3
    subDock,      THREE.Vector3
    dockLanding,  THREE.Vector3
    scientist,    THREE.Vector3
    lab,          THREE.Vector3
  },

  scientistMesh,     // THREE.Object3D, sur l ile, deja dans la scene
  labMesh,           // THREE.Object3D

  // Point de spawn libre pour la faune dans un biome donne.
  randomSpawn(biomeId, rng) -> THREE.Vector3,
}
```

Contenu attendu: fond marin en heightfield (lagon en pente vers une fosse),
rochers et arches instanciees, foret de kelp animee, jardins de corail,
anemones, epave de cargo, ile emergee avec plage, palmiers, ponton en bois,
laboratoire et scientifique (personnage low poly simple, anime doucement).

Le monde est genere avec `makeRandom(seed)` de `config.js` pour etre
reproductible.

---

## `fauna.js`

```js
export function createFauna(scene, world, textures): Fauna
```

Construit les maillages proceduraux par espece (`species.body`) et anime tout
le vivant.

```js
Creature = {
  uid,            number unique
  speciesId,      string
  species,        entree de SPECIES
  object,         THREE.Object3D (dans la scene)
  position,       THREE.Vector3 (= object.position)
  velocity,       THREE.Vector3
  health, maxHealth,
  alive,          bool
  state,          'idle' | 'flee' | 'hunt' | 'attack' | 'stunned' | 'dead'
  radius,         number, sphere de collision et de tir
  danger,         0 | 1 | 2
}

Specimen = {
  uid, speciesId, species,
  object,      THREE.Object3D
  position,    THREE.Vector3
  value,       number
  collected,   bool
}

Fauna = {
  group,
  creatures,   // Creature[]
  specimens,   // Specimen[]
  update(dt, ctx),
  dispose(),

  // ctx = {
  //   time, camera,
  //   playerPos      THREE.Vector3
  //   playerVel      THREE.Vector3
  //   playerVisible  bool (false quand le joueur est dans le sous-marin ou a terre)
  //   lampOn         bool
  //   noise          0..1, monte quand le joueur tire ou sprinte
  //   bleeding       0..1, attire les predateurs
  // }

  // Tir instantane. Renvoie le premier impact.
  raycast(origin, direction, maxDist) -> { creature, point, distance } | null,

  // Balayage spherique pour la melee.
  sphereHit(center, radius) -> Creature[],

  // Applique des degats. Gere la mort, le drop de specimen, le sang.
  // opts = { knockback: number, from: THREE.Vector3, stun: number }
  damage(creature, amount, opts) -> { killed: bool, specimen: Specimen | null },

  // Ce que le joueur vise, pour le scanner du HUD.
  scanTarget(camera, maxDist) -> Creature | null,

  // Menace la plus proche en mode chasse.
  nearestThreat(pos) -> { creature, distance } | null,

  collect(specimen) -> void,      // retire le specimen de la scene

  // Peuplement en flux autour du joueur. Appele par main de temps en temps.
  stream(playerPos) -> void,

  // Callbacks branches par main.js
  onDiverAttacked: (creature, damage) => void,
  onKill: (creature) => void,
  onSpecimenSpawn: (specimen) => void,
}
```

Comportements: `school` (boids serres, fuite a l approche), `drifter` (derive
lente, ondulation), `solo` (patrouille territoriale), `ambush` (cache dans le
decor, bondit de pres), `predator` (cercle puis charge, cooldown d attaque,
recule apres morsure). Les predateurs blesses par le baton electrique passent en
`stunned` puis `flee`. Le sang et le bruit augmentent le rayon d aggro.

---

## `hud.js`

```js
export function createHUD(callbacks): HUD
```

Possede tout le DOM de `index.html` et l ecriture de `styles.css`. Ne touche
jamais a la scene 3D.

```js
callbacks = {
  onPlay, onResume, onQuit, onRespawn,
  onSelectSkin(skinId),
  onScientistDone,
  onReset,
  onToggleMute,
}

HUD = {
  update(dt, state),
  dispose(),

  showScreen(id | null),     // 'loading'|'title'|'codex'|'scientist'|'skins'|'pause'|'help'|'dead'|null
  currentScreen -> string|null,
  isModalOpen() -> bool,     // true si un ecran bloque le jeu

  setLoading(progress01, label),
  setHudVisible(bool),
  toast(text, kind),         // kind: 'info'|'good'|'warn'|'bad'|'medal'
  setPrompt(text | null, key),
  flashDamage(strength01, directionAngleRad | null),
  flashPickup(),
  showTransit(title, subtitle | null),   // null pour masquer
  fade(alpha01, seconds),

  openCodex(save),                       // save = objet de progression
  openSkins(save, { forcePick: bool }),
  openScientist(report, save),
  openDead(reason, stats),
  refreshTitle(save),
}
```

`state` passe a `update()`:

```js
{
  mode,            'dive' | 'land' | 'transit' | 'menu'
  oxygen, maxOxygen,
  health, maxHealth,
  stamina, maxStamina,
  depth,           metres
  biomeLabel,      string
  yaw,             radians, pour la boussole
  weapon: { name, kind, mag, magSize, reserve, reloading, reloadProgress },
  net:   { count, capacity, items: [{ speciesId, name }] },
  cargoCount,
  medals, skinCount,
  discoveredCount, speciesTotal,
  scan: { creature, progress, known } | null,
  threat: 0..1,
  objective: string,
  prompt: { text, key } | null,
}
```

`report` passe a `openScientist()`:

```js
{
  handed: [{ speciesId, name, isNew, value }],
  newSpecies: number,
  medalsEarned: number,
  bonus: bool,             // palier des 10 especes atteint
  totalMedals: number,
  skinUnlocked: bool,
  credits: number,
  lines: [string],         // dialogue deja redige par main.js
}
```

---

## `audio.js`

```js
export function createAudio(): Audio
```

WebAudio pur, aucun fichier. Doit rester silencieux tant que `init()` n a pas
ete appele depuis un geste utilisateur.

```js
Audio = {
  init() -> Promise<void>,
  update(dt, ctx),
  dispose(),

  // ctx = { depth, biome, moving, threat 0..1, aboveWater, insideSub, oxygen01, health01 }

  play(name, opts),   // opts = { volume, rate, pan }
  setMuted(bool),
  muted -> bool,
}
```

Noms de sons requis: `harpoon`, `needle`, `shock`, `reload`, `dryfire`, `hit`,
`hitArmor`, `kill`, `pickup`, `deposit`, `medal`, `skin`, `ui`, `uiConfirm`,
`uiBack`, `bubble`, `splashIn`, `splashOut`, `sharkAlert`, `bite`, `sting`,
`lowOxygen`, `heartbeat`, `sonar`, `scanDone`, `engine`, `surface`, `footstep`,
`gull`.

Ambiance continue attendue: nappe sous-marine filtree par la profondeur, bulles
aleatoires, chant grave dans l abysse, vent et mouettes en surface.

---

## `save.js`, `input.js`, `diver.js`, `sub.js`, `main.js`

Ecrits par l integrateur, pas par les agents.
