# OVERCLOCK - contrats de modules

Signatures publiques. Un module peut ajouter des exports, jamais en changer un.
Zero build, ES modules natifs, three.js r169 vendorise dans `./vendor/`.
Aucun addon `three/examples/jsm/*`, aucun fetch, aucun asset binaire.

---

## Couche pure (aucune dependance a three ni au DOM)

### `src/levels.js`

```js
export const LEVELS: Level[]
export function levelIndexById(id) -> number
```

`Level` : `{ id, name, hint, h[], m[], start:{x,z,dir}, procs[], ops[], colors[],
optimal, solution }`.
`h` = hauteurs (`'0'..'9'`, `'.'` = vide), `m` = marqueurs
(`.` rien, `*` cible, `C` caisse, `r g b` peinture, `R G B` peinture + cible).
`solution` est le programme de reference : il sert au script de verification et
n est jamais montre au joueur.

### `src/warehouse.js`

```js
export const DIRS          // [{x,z}] indexe par dir, 0=+x 1=+z 2=-x 3=-z
export const COLOR_NONE
export function createWarehouse(level) -> Warehouse
```

```js
wh.cols, wh.rows, wh.tiles           // tile = {x,z,h,color,target,lit,crate}
wh.drone = { x, z, dir, level, carrying }
wh.targets, wh.lit
wh.at(x,z) / wh.topOf(tile) / wh.tileUnderDrone() / wh.aheadTile(n)
wh.colorUnder() -> 'n'|'r'|'g'|'b'
wh.reset() / wh.solved()
wh.forward() wh.jump() wh.turn(±1) wh.activate() wh.paint(c) wh.grab() wh.drop()
```

Toutes les actions retournent `{ ok, reason, moved, ... }`. Une action refusee
ne casse rien : elle rend `ok:false` et une raison affichable.

Regles figees :
- `topOf` = `h + (crate?1:0)`, `null` si `h < 0` et pas de caisse.
- `forward` exige la meme hauteur.
- `jump` monte de 1, descend de n importe quelle hauteur, ou franchit un vide
  d une case si la case d apres est a la meme hauteur.
- `grab` : caisse devant, `tile.h === drone.level`.
- `drop` : devant, pas de caisse, `tile.h` dans `[drone.level - 1, drone.level]`.

### `src/program.js`

```js
export const PROC_NAMES, OPS, CONDS, COND_LABEL
export function createProgram(level) -> Program
export function parseToken('RIGHT@r') -> { op, cond }
```

```js
program.procs                        // [{ name, slots:(null|{op,cond})[] }]
program.get(p,i) / set(p,i,op,cond) / clear(p,i) / cycleCond(p,i,allowed)
program.count() / isEmpty()
program.undo() / canUndo() / clearAll()   // undo illimite, snapshot avant mutation
program.serialize() / load(data)
```

### `src/vm.js`

```js
export const MAX_STEPS = 5000, MAX_DEPTH = 200, STATUS_LABEL
export function createVM(warehouse, program, opts) -> VM
vm.step() -> Event
vm.reset() / vm.peek() / vm.steps / vm.depth / vm.status
```

`status` : `running | win | halt | limit | overflow`.
`Event` : `{ kind, proc, slot, op, cond, ok, reason, detail, status }`,
`kind` dans `run | skip | empty | call | end`.

Un appel qui n a plus rien apres lui remplace sa frame (tail call) : sans cela
une procedure recursive utilisee comme boucle saturerait la pile en deux cents
iterations. "Plus rien apres lui" inclut les slots vides de fin, sinon laisser
un slot blanc changerait la semantique du programme.

### `src/storage.js`

```js
export function createStorage() -> Storage
storage.maxIndex / bestFor(id) / recordWin(id, index, used) -> bool
storage.programFor(id) / saveProgram(id, data) / wipe()
```

Cles prefixees `overclock.`, chaque acces sous `try/catch`.

---

## Couche rendu

### `src/textures.js`

```js
export function createTextures(renderer) -> { slab, crate, target, halo, spark,
                                              hull, ground, dispose() }
```

Tout est dessine dans un `<canvas>` 2D avec un PRNG graine.

### `src/render/scene.js`

```js
export const TILE = 1.0, STEP = 0.45
export function createScene(renderer, textures) -> SceneApi
api.scene / api.root / api.center / api.radius
api.build(warehouse) / api.sync() / api.update(dt) / api.updatePulse(dt)
api.cellX(x) / api.cellZ(z) / api.topY(top) / api.clearMeshes() / api.dispose()
```

Dalles, caisses et anneaux de cible sont trois `InstancedMesh`. `sync()` pousse
l etat du modele (peinture, caisses, cibles allumees) dans les instances,
`update(dt)` ne touche qu aux couleurs de pulsation.

### `src/render/drone.js`

```js
export function createDrone(textures) -> Drone
drone.group / drone.halo / drone.trail
drone.setPose(x,y,z,yaw,tiltX,tiltZ) / setCarrying(v) / setGroundY(y)
drone.refuse() / update(dt, moving) / bobOffset() / resetTrail() / dispose()
```

### `src/camera.js`

```js
export function createCameraRig(camera, domElement) -> Rig
rig.frame(radius, centerY) / rig.reset() / rig.update(dt) / rig.dispose()
```

Orbite au glisser, zoom molette, angles par defaut trois quarts.

---

## Couche interface

### `src/ui/panel.js`

```js
export function createPanel({ paletteEl, procsEl, onChange, onSound }) -> Panel
panel.setLevel(level, program) / refresh() / setEditable(v)
panel.highlight(proc, slot, 'exec'|'skip') / clearHighlight()
panel.handleKey(event) -> bool
panel.selection / panel.dispose()
```

### `src/hud.js`

```js
export function medalFor(used, optimal) -> { name, cls, over }
export function createHUD() -> HUD
hud.setLevel(i, total, level) / setTargets(lit, total) / setStack(n) / setSteps(n)
hud.setStatus(text, cls) / setBudget(used, optimal)
hud.toast(text, cls) / clearToasts()
hud.showScreen(name) / hideScreens()
hud.buildLevelGrid(levels, storage, onPick) / setWin(info) / setEndSummary(text)
```

### `src/audio.js`

```js
export function createAudio() -> Audio
audio.resume() / setVolume(v01) / getVolume() / toggleMute() / setRunning(bool)
audio.play(kind) / refuse() / win() / fail() / dispose()
```

`kind` : `ui place clear move turn jump act paint grab drop call start`.

### `src/main.js`

Assemble tout, tient la machine a etats
(`title | levels | play | pause | win | end`) et convertit les evenements du VM
en animations. Expose `window.game` et `window.__ready`.

---

## Verification

```bash
node --check src/<fichier>.js
```

et le script de non regression des niveaux : charger `levels.js`,
`warehouse.js`, `program.js`, `vm.js` dans node, rejouer `level.solution` et
verifier `vm.status === 'win'` et `program.count() === level.optimal` pour les
quatorze niveaux.
