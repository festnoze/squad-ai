# CONTREPOIDS - contrats de modules

Court resume des signatures publiques. Voir les commentaires en tete de
chaque fichier pour le detail du raisonnement.

## `src/shaft.js` (pur, sans three.js)

```
KIND = { GROUND, PLATFORM }
OBJ = { PIERRE, ENCLUME, BALLON }
WEIGHT = { pierre: 1, enclume: 3, ballon: -1, player: 2 }
DIRS = [[1,0], [-1,0], [0,1], [0,-1]]   // est, ouest, sud, nord

createState(level) -> state
columnAt(state, gx, gz) -> column | null
weightOf(state, colId) -> number

canMove(state, dir) / moveTo(state, dir) -> { ok, events }
canJump(state, dir) / jumpTo(state, dir) -> { ok, events }
canTake(state) / takeItem(state) -> { ok, events }
canDrop(state) / dropItem(state) -> { ok, events }
canPush(state, dir) / pushAnvil(state, dir) -> { ok, events }

cloneState(state) -> state
copyInto(dst, src) -> dst
hashState(state) -> string
```

Chaque action mutante retourne `{ ok, events }`. `events` contient des entrees
`{type:'rope', a, b, ah, bh, amount}` (une par corde resolue) precedees d'une
entree decrivant l'action elle-meme (`move`, `jump`, `take`, `drop`, `push`).
Une action illegale ne mute jamais l'etat.

## `src/history.js`

```
createHistory() -> { depth, push(state), undo(state) -> bool, clear() }
```

## `src/levels.js`

```
LEVELS: Array<{ name, hint, par, grid, columns, ropes, items, start, exit }>
```

`grid[z]` est une ligne le long de +X. `columns[lettre] = {kind, h, min?, max?}`.
`ropes` est une liste de paires de lettres. `par` est valide hors ligne par
`tools/solve.mjs` (BFS exhaustif sur `hashState`).

## `src/camera.js`

```
createCameraRig(aspect) -> rig
rig.frame(center: Vector3, radius)
rig.setFocus(center: Vector3)
rig.orbit(dx, dy) / rig.zoom(delta)
rig.resolveDirection(action: 'forward'|'back'|'left'|'right') -> dirIndex (0..3)
rig.update(dt) / rig.resize(aspect)
```

## `src/input.js`

```
createInput(canvas) -> input
input.onMove(cb)      // cb('forward'|'back'|'left'|'right')
input.onCommand(cb)   // cb('pause'|'mute'|'undo'|'restart'|'jump'|'action')
input.onOrbit(cb) / input.onZoom(cb)
input.setEnabled(bool) / input.dispose()
```

## `src/hud.js` (DOM pur)

```
createHUD() -> hud
hud.show() / hide() / showScreen(id | null)
hud.setLoading(pct, line)
hud.setLevel(index, total, name, hint)
hud.setMoves(moves, par) / setUndo(n) / setHolding(item | null)
hud.banner(title, sub, good, ms) / clearBanner()
hud.toast(text)
hud.buildLevelGrid(entries, onPick)
hud.update(dt)
```

## `src/audio.js`

```
createAudio() -> audio
audio.resume() / setVolume(v01) / getVolume() / setMuted(bool) / toggleMute()
audio.step() / jump() / blocked() / take() / drop() / push() / pulley(amount)
audio.win(perfect) / undo() / click() / dispose()
```

## `src/render/layout.js`

```
SPACING, CRAN_UNIT, PLATFORM_SIZE, PLATFORM_THICK, RIG_MARGIN
worldX(gx) / worldZ(gz) / worldY(h)
```

## `src/render/textures.js`

```
createTextures(renderer) -> { rock, wood, iron, stone, balloon, rope, skin, exit, dispose() }
```

## `src/render/scene.js`

```
createRenderer(canvas) -> THREE.WebGLRenderer
createScene() -> { scene, ambient, hemi, key, torches, shaftGroup }
buildShaftWalls(shaftGroup, textures, bounds) -> rig info
```

## `src/render/platforms.js`

```
createPlatforms(textures) -> view
view.group / view.bounds
view.build(state)
view.syncItems(state)
view.setHeights(heightsByColId: number[])
view.surfacePoint(column, h, outVector3) -> outVector3
view.dispose()
```

## `src/render/ropes.js`

```
createRopes(textures) -> view
view.group
view.build(state)
view.setHeights(state, heightsByColId)
view.dispose()
```

## `src/render/player.js`

```
createPlayer(textures) -> view
view.group / view.handAnchor
view.setPosition(x, y, z) / setFacing(angleRad) / setCarrying(item | null)
view.update(dt, moving) / dispose()
```

## `src/main.js`

Assemble tout, machine a etats (`loading -> title -> play <-> paused`, plus
`won-pending -> won -> end`). Expose `window.game` et `window.__ready = true`
une fois le menu affiche.
