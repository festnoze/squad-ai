# GRAVITE NEUF - contrats de modules

Signatures publiques. Un module peut ajouter des exports, jamais en changer un.

## Regles globales

- Navigateur, **ES modules natifs, zero build**. Servi tel quel par la console arcade.
- three.js **r169** vendorise dans `./vendor/three.module.js`, importe par l'importmap
  de `index.html` : `import * as THREE from 'three';`.
  **Les addons `three/examples/jsm/*` n'existent pas ici.**
- **Zero asset binaire** : textures dessinees dans un `<canvas>` 2D, sons synthetises en
  Web Audio, geometrie generee en code. Aucun `fetch`, aucune URL externe.
- Le renderer **n'active pas** `logarithmicDepthBuffer` : les `ShaderMaterial` custom
  (`sky.js`) n'ont pas besoin des chunks `logdepthbuf_*`.
- Interface en francais. Dans les textures canvas et le 3D, **pas d'accents**.
- Jamais de tiret cadratin, nulle part.
- Commentaires en anglais, utiles seulement. Zero allocation par image dans `update`.
- Cles de stockage prefixees `gravite_neuf.` (`gravite_neuf.progress`, `gravite_neuf.audio`).

`src/world.js`, `src/gravity.js` et `src/levels.js` **ne doivent jamais importer three** :
ils sont charges tels quels par le solveur hors ligne qui valide les niveaux et calcule
leur par.

---

## `src/world.js`

Etat de la grille. Aucune dependance.

```js
export const S    // EMPTY WALL EXIT GLUE SPIKE SWITCH_A SWITCH_B GATE_A GATE_B
export const MV   // PLAYER CRATE KEY
export const DIRS // [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]]
export const DIR  // { PX:0, NX:1, PY:2, NY:3, PZ:4, NZ:5 }
export const DIR_LABEL // ['+X','-X','+Y','-Y','+Z','-Z']

export function staticBlocks(kind, gateAOpen, gateBOpen) -> boolean
export function createState(level) -> State      // leve si le niveau est mal forme
export function idx(state, x, y, z) -> number
export function inside(state, x, y, z) -> boolean
export function rebuildOcc(state)                // remplit state.occ
export function switchOn(state, plateKind) -> boolean
export function cloneState(state) -> State
export function copyInto(dst, src) -> dst        // recopie en place (undo)
export function hashState(state) -> string       // identite d'une position
export function snapshot(state) -> { pos, alive, stuck }
```

`State` : `{ level, W, H, D, statics: Uint8Array, movables: Movable[], playerIndex,
keysTotal, keysTaken, crateLost, status: 'play'|'won'|'lost', reason, gravity, occ, order }`.

`Movable` : `{ kind, x, y, z, stuck, alive, voided, killed, blockedBy }`.

Adressage : `idx = (y * D + z) * W + x`, `y` vers le haut.

---

## `src/gravity.js`

Resolution de chute. Depend de `./world.js` uniquement.

```js
export const REASON              // { VOID, SPIKE, GLUE }
export function applyGravity(state, dirIndex) -> { moved, steps, events }
export function settleInitial(state) -> { moved:false, steps:[snapshot], events }
```

Regles figees :

1. Une bascule est resolue par iterations d'une case. Dans une iteration les mobiles sont
   traites du plus proche du nouveau sol au plus loin (tri par projection decroissante sur
   la direction), ce qui interdit toute traversee.
2. Une case cible bloque si elle est un `WALL`, une `GLUE`, un `SPIKE`, une grille fermee,
   ou si elle contient deja un mobile. `EXIT` et les plaques ne bloquent jamais.
3. Un mobile bloque par de la `GLUE` devient `stuck` **definitivement**.
4. Un mobile bloque par un `SPIKE` est detruit.
5. Un mobile qui sort de la boite est detruit (`voided`).
6. Apres stabilisation, toute cle a distance de Manhattan 1 du joueur est ramassee ; si au
   moins une l'est, la resolution **reprend** (la case liberee peut relancer une chute).
7. Une grille de groupe A est ouverte tant qu'un mobile vivant occupe une plaque `a`.
8. Fin de partie : joueur detruit ou colle = perdu ; cle detruite = perdu ; joueur immobile
   sur la sortie avec toutes les cles = gagne.
9. Double borne d'arret : plus rien ne bouge, ou 512 iterations.

`steps[0]` est toujours l'etat d'avant la bascule, ce qui permet au rendu d'animer
directement depuis lui.

---

## `src/levels.js`

```js
export const LEGEND    // [[char, libelle], ...]
export const LEVELS    // [{ name, hint, par, layers }]
export const LEVEL_COUNT
```

`layers[y][z]` est une chaine ASCII le long de `+X`. Toutes les tranches d'un niveau ont
la meme taille. Legende : `.` vide, `#` mur, `X` sortie, `G` glu, `^` piques, `a`/`b`
plaques, `A`/`B` grilles, `@` joueur, `o` caisse, `*` cle.

`par` est la longueur de la solution la plus courte, obtenue par un parcours en largeur
hors ligne sur `applyGravity`. Toute modification d'un niveau ou d'une regle de
`gravity.js` invalide les `par` : il faut les recalculer.

---

## `src/history.js`

```js
export function createHistory() -> { depth, push(state), undo(state) -> bool, clear() }
```

Une entree = un clone complet du monde. Undo illimite.

---

## `src/textures.js`

```js
export const PALETTE                       // couleurs de reference, en chaines CSS
export function createTextures(renderer) -> Textures
```

`Textures` : `wall glue spike exit plateA plateB gateA gateB player crate key grid`
(toutes des `THREE.CanvasTexture` en `SRGBColorSpace`) et `dispose()`.
Chaque face de cube porte un liseré biseaute cuit dans la texture : c'est ce qui permet
de dessiner tout un mur en un seul `InstancedMesh` sans perdre la lecture des cubes.

---

## `src/voxels.js`

```js
export function createVoxels(textures) -> Voxels
voxels.group                   // THREE.Group, quaternion pilote par camera.js
voxels.radius                  // rayon englobant, pour le cadrage
voxels.busy                    // true pendant l'animation de chute
voxels.build(state)
voxels.applyState(state)       // pose instantanee (undo, reset)
voxels.syncStatics(state)      // grilles ouvertes/fermees, plaques allumees
voxels.setGravityFace(dirIndex)// deplace la grille de reperes sur la face du bas
voxels.play(steps)             // demarre l'animation
voxels.update(dt, elapsed)
voxels.dispose()
```

Un `InstancedMesh` par type de bloc statique, un `Mesh` par mobile. Les durees de chute
suivent une chute libre (`sqrt(k+1) - sqrt(k)`), bornees entre 34 et 170 ms par case.

---

## `src/sky.js`

```js
export function createSky(scene) -> { dome, setDirection(dirIndex, immediate), update(dt, elapsed), dispose() }
```

Dome `ShaderMaterial` `BackSide` fixe en espace ecran : son degrade est la reference
verticale permanente, sa teinte designe l'axe de gravite courant.

---

## `src/camera.js`

```js
export function createCameraRig(aspect) -> Rig
rig.camera
rig.worldQuat                       // a recopier dans voxels.group.quaternion
rig.tilting                         // true pendant les 400 ms de bascule
rig.frame(radius) / rig.resize(aspect)
rig.orbit(dx, dy) / rig.zoom(delta) / rig.resetOrbit() / rig.reset()
rig.resolveDirection(action) -> dirIndex   // action: forward back left right up down
rig.setGravity(dirIndex, immediate)
rig.update(dt)
```

`resolveDirection` projette la direction ecran demandee dans le repere du niveau puis la
colle sur l'axe monde le plus proche. C'est la seule facon d'eviter que les commandes
deviennent illisibles des que la camera a tourne.

---

## `src/input.js`

```js
export function createInput(canvas) -> Input
input.onTilt(cb)      // cb('forward'|'back'|'left'|'right'|'up'|'down')
input.onCommand(cb)   // cb('undo'|'restart'|'next'|'prev'|'pause'|'mute'|'help')
input.onOrbit(cb) / input.onZoom(cb)
input.setEnabled(v) / input.dispose()
```

Les lettres sont lues sur `event.key` (donc ZQSD et A / E sur un clavier francais).

---

## `src/hud.js`

```js
export function createHUD() -> HUD
hud.show() / hud.hide() / hud.showScreen(id | null)
hud.setLoading(pct, line)
hud.setLevel(index, total, name, hint, par)
hud.setMoves(moves, par) / hud.setKeys(taken, total) / hud.setUndo(n)
hud.setGravity(label, dirIndex)
hud.banner(title, sub, good, ms) / hud.clearBanner()
hud.toast(text)
hud.buildLevelGrid(entries, onPick)
hud.update(dt)
```

Les identifiants DOM sont figes par `index.html`.

---

## `src/audio.js`

```js
export function createAudio() -> Audio
audio.resume() / audio.setVolume(v01) / audio.getVolume() / audio.setMuted(v) / audio.toggleMute()
audio.tilt(dirIndex) audio.land(s) audio.blocked() audio.key() audio.glue()
audio.spike() audio.voidFall() audio.win(perfect) audio.fail() audio.undo() audio.click()
audio.dispose()
```

Contexte cree au premier geste utilisateur, une note par axe de gravite.

---

## `src/main.js`

Machine a etats `loading | title | play | paused | won | end`, boucle
`rig -> voxels -> sky -> hud -> render`. Expose `window.game`
(`state`, `levelIndex`, `moves`, `mode`, `tilt`, `undo`, `start`, ...) et `window.__ready`.

Regles d'entree, figees :

- Les six directions sont toujours acceptees. **Une bascule ou rien ne peut tomber reste un
  coup legal** : le monde pivote quand meme, elle compte dans le compteur et elle entre
  dans la pile d'annulation. La refuser bloquait le joueur des que la structure etait
  tassee contre toutes les faces atteignables.
- Seule exception : redemander la direction ou la gravite pointe deja ne fait rien et ne
  coute rien.
- Une touche de bascule pressee pendant l'animation est **memorisee** (`bufferedTilt`) et
  jouee des que `voxels.busy` et `rig.tilting` sont retombes. `setMode` et `doUndo` vident
  ce tampon.
- Le `par` d'un niveau ne compte que les bascules qui changent quelque chose, ce que le
  solveur hors ligne respecte : une bascule a vide ne raccourcit jamais une solution, elle
  ne fait que couter un coup.
