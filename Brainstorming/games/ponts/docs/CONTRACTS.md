# PONTS DE FORTUNE - contrats de modules

Signatures publiques. Un module peut ajouter des exports, jamais en changer un.

## Regles globales

- ES modules natifs, zero build. `three` r169 vendorise, importe via l importmap de
  `index.html`. Aucun addon `three/examples/jsm/*`, aucun CDN, aucun `fetch`.
- Toutes les textures sont dessinees dans un `<canvas>`, tous les sons synthetises.
- Unites SI: metres, secondes, kilogrammes, newtons. 1 unite three = 1 metre.
- Interface en francais. Pas d accents dans le 3D ni dans les textures.
- Commentaires en anglais, utiles seulement. Pas de code mort.
- Zero allocation par frame dans `update` / `draw*`: vecteurs scratch au niveau module.
- `localStorage` prefixe `ponts.`.

## Repere

Le pont vit dans le plan `z = 0`, appele plan d edition. `x` court d une rive a l autre,
`y` est la verticale, `z` est l epaisseur du tablier. Les deux fermes sont a
`z = -HALF_WIDTH` et `z = +HALF_WIDTH`.

Coordonnees de grille: `col` croissant vers la droite, `row` 0 au niveau de la chaussee.
Conversion par `colToX(level, col)` et `rowToY(row)`.

---

## `src/config.js`

Constantes seulement. Exporte `GAME_ID`, `STORE`, `GRID`, `DECK_Y`, `HALF_WIDTH`,
`RAVINE_DEPTH`, `SIM`, `MATERIALS`, `MATERIAL_ORDER`, `BRACE`, `VEHICLES`, `CONVOY`,
`CAMERA`, `REPLAY`, `PALETTE`, `KEYS`. Toute valeur de reglage vient de la.

## `src/physics.js` (pur, sans three)

```js
createSim({ gravity?, iterations?, damping? }) -> Sim
sim.addNode({ x, y, z, mass, anchor, owner?, side? }) -> index
sim.addLink({ a, b, rest?, stiff, capT, capC, tensionOnly?, owner?, kind?, side? }) -> index
sim.addLoad(nodeIndex, kilos)   // efface a chaque step
sim.step(dt)                     // un sous pas fixe
sim.peakRatio() -> number        // pire |force| / capacite
sim.drainBreaks(out) -> out      // [{ link, owner, kind, reason, time, x, y, z }]
sim.nodes / sim.links / sim.time / sim.diverged
bucklingFactor(length) -> number // perte de capacite en compression
```

Un lien porte `force` (newtons lisses, positif = traction), `ratio` (|force| / capacite
dans le sens de travail) et `broken`. Un lien `tensionOnly` ne contraint rien tant que sa
longueur est inferieure au repos.

## `src/levels.js`

```js
LEVELS: Level[]                     // 14 chantiers
levelByKey(key) -> Level | null
colToX(level, col) / rowToY(row) / xToCol(level, x) / yToRow(y)
canPlaceNode(level, col, row) -> boolean
anchorPoints(level) -> Array<[col, row]>
```

## `src/bridge.js`

```js
createBridge(level) -> Bridge
bridge.elements / nodes / spent / budgetLeft / historyDepth / anchors / level
bridge.evaluate(ca, ra, cb, rb, type) -> { ok, reason, len, cost }
bridge.add(...) -> meme objet      // empile l historique
bridge.removeAt(index) -> element | null
bridge.findElement(ca, ra, cb, rb) -> index
bridge.undo() -> boolean           // illimite
bridge.clear() / bridge.load(data) / bridge.snapshot() -> data
bridge.nodeIndexOf(col, row) / bridge.isAnchor(col, row)
bridge.deckGaps() -> number[]      // colonnes de chaussee manquantes
bridge.buildSim() -> Plan
```

`Plan = { sim, pair, elemLinks, traverses, deck, nodeCount }`. `elemLinks[i]` donne les
deux liens (une ferme chacun) de l element `i`; `deck` est la liste triee des cases de
chaussee avec les noeuds physiques de leurs extremites.

`evaluate` retourne toujours une `reason` en francais, affichee telle quelle par le HUD.

## `src/convoy.js`

```js
createConvoy(level, plan, spec) -> Convoy
convoy.applyLoads()      // avant chaque sous pas du solveur
convoy.advance(dt)       // apres chaque sous pas
convoy.vehicles          // [{ def, key, mass, u, x, y, z, pitch, roll, state, onBridge, wheelSpin }]
convoy.allDone() / convoy.leader() / convoy.time / convoy.started
convoy.maxLoad / convoy.failed / convoy.failReason
```

## `src/replay.js`

```js
createState(plan) -> { pos: Float32Array, ratio: Float32Array, sign: Int8Array, broken: Uint8Array }
captureState(sim, state)
createRecorder(plan, vehicleCount) -> Recorder
recorder.record(sim, vehicles) / reset() / markBreak(x, y, z, kind)
recorder.read(frame, state, vehicles)
recorder.firstFrame() / recorder.total / recorder.capacity / recorder.breakPoint
```

Anneau de frames dimensionne selon la taille du pont. Le rendu ne lit jamais le solveur
directement: il lit un `state`, rempli soit par `captureState`, soit par `recorder.read`.

## `src/render/scene.js`

```js
createStage(canvas, textures) -> Stage
stage.renderer / scene / camera / sun / rig
stage.frameLevel(level, immediate)
stage.orbit(dYaw, dPitch) / stage.zoom(steps) / stage.pan(dx, dy)
stage.lookAtPoint(x, y, z, dist?, yaw?, pitch?)
stage.fitDistance(width, height) -> number
stage.update(dt) / stage.resize() / stage.render() / stage.dispose()
stage.planePoint(clientX, clientY, outVec3) -> Vector3 | null
```

Le PMREM cuit depuis la texture de ciel est indispensable: sans environnement, un
materiau metallique n a rien a reflechir et rend noir mat.

## `src/render/terrain.js`

```js
createTerrain(scene, textures, level) -> { group, update(dt), dispose() }
```

Falaises en rubans de bruit, plateaux, routes d acces, piliers, pylones, plafond de
tunnel, brume et oiseaux. Recree a chaque changement de chantier.

## `src/render/bridgeview.js`

```js
createBridgeView(scene, textures) -> View
view.setLevel(level) / setBridge(bridge) / setPlan(plan | null) / setHover(index) / showGrid(bool)
view.drawModel()                 // mode chantier, tout est sur la grille
view.drawState(state)            // mode test et rejeu
view.setPreview(a, b, type, ok)  // fantome de l element en cours de trace
view.burst(x, y, z, kind)        // debris et poussiere sur rupture
view.update(dt, timeScale) / view.clearEffects() / view.dispose()
```

Un `InstancedMesh` par materiau, recharge chaque frame. La couleur d instance porte la
teinte du materiau melangee a la contrainte.

## `src/render/vehicles.js`

```js
createVehicleView(scene) -> { setConvoy(vehicles), sync(vehicles), setVisible(v), dispose(), group }
```

## `src/editor.js`

```js
createEditor({ canvas, stage, view, audio, hud, getMode, onChange, onMaterial }) -> Editor
editor.setLevel(level, bridge) / editor.setMaterial(key) -> boolean
editor.material / editor.enabled / editor.drawing / editor.dispose()
```

## `src/hud.js`

```js
createHUD() -> HUD    // leve si un identifiant DOM manque
hud.dom / hud.buttons
hud.show() / hide() / setMode('build' | 'test' | 'replay') / showScreen(id | null)
hud.setLevel(level, index, total) / setBudget(spent, total, count)
hud.setPalette(allowed, current) / setCursor(cost, reason, ok) / onMaterial(cb)
hud.setTest(status, loadKg, ratio) / setReplayNote(text) / toast(text, kind)
hud.setLevelGrid(levels, progress, onPick) / setWin(level, rows, title, sub) / setLose(reason, detail)
hud.setProgressLine(done, total) / setLoading(pct, line) / setUndoEnabled(v)
```

## `src/audio.js`

```js
createAudio() -> Audio
audio.resume() / setVolume(v01) / toggleMute() -> boolean / muted
audio.click() / place(type) / remove() / deny() / undo()
audio.testStart() / crack(intensity) / collapse() / win() / lose()
audio.engine(on, load01) / creak(ratio01)
audio.dispose()
```

## `src/storage.js`

```js
loadProgress() -> Progress     // ne leve jamais
saveProgress(progress) -> boolean
recordFor(progress, key) -> record
countDone(progress) -> number
```

## `src/main.js`

Machine a etats `loading -> title -> build <-> test -> replay -> win | lose`, boucle
`requestAnimationFrame`, `dt` clampe a 0.05 s. Expose `window.game` (dont `step(seconds)`
pour avancer un test sans attendre les frames) et `window.__ready` une fois le titre
affiche.
