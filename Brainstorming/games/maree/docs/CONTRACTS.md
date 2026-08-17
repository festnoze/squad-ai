# MAREE - contracts

Short reference of each module's public surface. Pure-logic modules
(`world.js`, `water.js`, `pathing.js`, `explorer.js`, `history.js`, `levels.js`)
have no three.js dependency and can be exercised from plain Node.

## src/config.js
Shared constants: `CELL`, `BODY_CELLS`, `FREEZE_HOLD_TIME`, `DROWN_TIME`,
`WATER_VISUAL_SPEED`, `WALK_STEP_TIME`, `SWIM_STEP_TIME`, `KEY_PROGRESS`,
`KEY_AUDIO`, `PALETTE`.

## src/world.js (pure)
- `createWorld(level) -> state` - builds the runtime model from a level (see
  `levels.js`). `state.floor` / `state.basinOf` are `Int8Array`s indexed by
  `z*w+x`; `state.basins[i]` is `{ id, level, visual, min, max, freeze,
  iceLevels, stableAt, stableTime }`; `state.gates[i]` is `{ a, b, x, z, open }`
  (`a`/`b` are basin indices); `state.wood[i]` is `{ x, z, homeFloor }`;
  `state.explorer` holds the autonomous walker's live state.
- `colIndex(state, x, z)`, `inBounds(state, x, z)`, `isVoid(state, x, z)`.
- `woodAt(state, x, z) -> {x,z,homeFloor} | null`.
- `classify(h, level) -> 'dry' | 'shallow' | 'swim' | 'drown'` - submersion of a
  standing surface at height `h` under a basin filled to `level`.
- `standableHeights(state, x, z) -> [{h, basin, kind}]` - every usable standing
  surface at a column right now (ground / floating wood / any formed ice).
- `groundNode(state, x, z)` - the plain dry-ground entry, used to place the
  explorer at level start.
- `rebuildGroups(state)` - recomputes `state.groupOf` / `state.groups` (union
  of basins joined by open gates). Called after any gate toggle.
- `cloneWorld(state)` / `copyInto(state, snapshot)` - used by `history.js`.

## src/water.js (pure)
- `requestLevelChange(state, basinId, delta) -> { changed, group? }` - moves a
  basin (and every basin currently merged with it) one cran up or down.
  `changed` is false only when the target equals the current level.
- `toggleGate(state, gateIndex) -> { changed: true }` - flips a gate; opening
  equalises its new group to the lowest level among its members.
- `updateVisualLevels(state, dt)` - advances `basin.visual` toward
  `basin.level` at `WATER_VISUAL_SPEED` crans/second, for rendering only.
- `updateFreeze(state, dt)` - accumulates `basin.stableTime` while a
  freeze-capable basin holds one level, and adds it to `iceLevels` after
  `FREEZE_HOLD_TIME` seconds.

## src/pathing.js (pure)
- `findPath(state, start, exit) -> [{x,z,h,swim}] | null` - BFS from `start`
  (always accepted even if currently unsafe) to any safe node on the exit
  column. Nodes classified `'drown'` are excluded except as the forced start.

## src/explorer.js (pure)
- `initExplorer(state)` - places the explorer on `state.start`, resting.
- `requestRepath(state)` - flags an immediate replan next time it's at rest
  (cosmetic responsiveness only: the explorer replans on every arrival anyway).
- `tickExplorer(state, dt)` - advances one simulation step: continues an
  in-flight move, otherwise replans on every arrival at a resting node and
  starts the next step of the freshest plan, or accumulates drowning time
  when stuck on a now-unsafe tile. Sets `state.explorer.status` to `'won'` /
  `'drowned'`.

## src/history.js (pure)
- `createHistory() -> { depth, push(state), pushSnapshot(snap), undo(state) -> bool, clear() }`.

## src/levels.js (pure data)
- `LEVELS: Level[]`, each `{ id, name, hint, w, d, h, floor, basin, wood?,
  stone?, gates?, basins, start, exit, par }`. `floor`/`basin` are `d` strings
  of length `w`; `floor` chars are a digit (rock height) or space (void, no
  column); `basin` chars are a lowercase basin id or `.` (dry land, never
  floods). See the top of the file for the full authoring notes.

## src/textures.js
- `createTextures() -> { rock, shore, wood, stone, ice, suit, dispose() }` -
  `THREE.CanvasTexture`s, no binary assets.

## src/camera.js
- `createCameraRig(aspect) -> rig` with `rig.camera`, `rig.frame(center,
  radius)`, `rig.orbit(dx, dy)`, `rig.zoom(delta)`, `rig.update(dt)`,
  `rig.resize(aspect)`.

## src/input.js
- `createInput(canvas) -> { onCommand, onLevel, onOrbit, onZoom, onClick,
  applyKeyOrbit(dt), setEnabled(bool), dispose() }`. Plain vertical wheel
  raises/lowers the selected basin (the game's primary action); Shift+wheel
  zooms; a dominant horizontal wheel delta (trackpad swipe) orbits.

## src/audio.js
- `createAudio() -> { resume, setVolume, getVolume, setMuted, toggleMute,
  raise, lower, gateOpen, gateClose, freeze, step(swimming), select, win,
  drown, undo, click, dispose() }`.

## src/hud.js
- `createHUD() -> { show, hide, showScreen(id|null), setLoading, setLevel,
  setMoves, setUndo, buildBasins(basins, selected, onPick),
  updateBasinValues(basins, selected), banner, clearBanner, toast,
  buildLevelGrid(entries, onPick), update(dt) }`.

## src/render/scene.js
- `createSceneObjects(textures) -> { group, build(state) -> {gateMeshes,
  exitBeacon}, setGateOpen(index, open), update(dt, elapsed), radius, center,
  gates, dispose() }`. Static per-level geometry: instanced rock/shore boxes,
  baked-in stone crates, gate props, the exit beacon.

## src/render/water.js
- `createWaterObjects(textures) -> { group, build(state) -> {basinMeshes},
  update(state, dt, elapsed), dispose() }`. One rippling ShaderMaterial plane
  per basin (sized to its column footprint, height follows `basin.visual`),
  ice planes created the moment they form, and the wood crate meshes (which
  track `max(homeFloor, basin.visual)` every frame).

## src/render/explorer.js
- `createExplorerObject(textures) -> { object, update(state, dt, elapsed),
  dispose() }`. A primitives-only low-poly figure with a hand-coded walk /
  swim / idle animation.

## src/main.js
Boots the renderer and every module above, owns the state machine (`loading
-> title -> play <-> paused`, `play -> won -> play|end`), and exposes a small
debug surface on `window.game` (state, mode, moves, raise/lower/selectBasin/
toggleGate/undo/start) mirroring the pattern used by the other games in this
repository.
