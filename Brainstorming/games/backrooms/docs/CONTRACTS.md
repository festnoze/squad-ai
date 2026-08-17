# BACKROOMS - contrats de modules

Reference rapide des signatures publiques. Zero build, ES modules natifs,
three.js r169 vendorise dans `vendor/three.module.js`. Voir `README.md` pour
le pitch et les commandes.

Unites : metres, secondes, radians. `TILE_SIZE = 3` (1 tuile = 3 m).

---

## src/maze.js (pur, sans three)

```js
export const TILE_SIZE = 3;
export const TILE = { WALL, FLOOR, DOOR, EXIT };
export function mulberry32(seed) -> () => number        // PRNG deterministe [0,1)
export function generateMaze(cfg) -> Maze
export function bfsDistances(tiles, width, height, sx, sy) -> Int32Array   // -1 = injoignable
export function tileAt(maze, x, y) -> TILE
export function isWalkableAt(maze, x, y, openDoors) -> boolean
export function hasLineOfSight(maze, x0, y0, x1, y1, openDoors) -> boolean
export function worldToTile(wx, wz) -> {x, y}
export function tileToWorldCenter(x, y) -> {x, z}
export function circleFree(maze, openDoors, cx, cz, r) -> boolean
export function moveCircle(maze, openDoors, x, z, dx, dz, radius) -> {x, z}
```

`Maze = { width, height, tiles: Uint8Array, rooms, doors, startPos, exitPos, patrolPoints, items, seed }`.
`cfg = { seed, width, height, roomCount, minRoomSize, maxRoomSize, loopChance, patrolPoints, itemCount, itemType }`.

`moveCircle`/`circleFree` are the single shared collision primitive: both
`player.js` and `entity.js` call them, so a body sliding along a wall behaves
identically whether it is the player or the entity.

---

## src/levels.js (pur, sans three)

```js
export const THEMES;          // { [themeKey]: { wall, floor, ceiling, tube, fog, ambient,
                               //   ambientIntensity, ceilHeight, surface, fogDensity,
                               //   water?, gradientTo? } }, all colours are plain hex numbers
export const LEVELS;          // array of 12 level definitions, index = Niveau order
export function getLevelMaze(levelIndex) -> Maze     // cached, deterministic per seed
export function getLevelDef(levelIndex) -> LevelDef
export const LEVEL_COUNT;
```

`LevelDef = { id, name, theme, seed, width, height, roomCount, minRoomSize,
maxRoomSize, loopChance, entity: EntityDef|null, itemCount, itemType,
goldSeconds, encounterLimit, intro, flashlight?, finalLevel? }`.

`EntityDef = { count, speed, patrolSpeed, sightRange, hearRangeBase, loseTime, searchTime }`.

---

## src/entity.js (pur, sans three)

```js
export function createEntity(def, maze, index) -> Entity
export function updateEntity(entity, dt, ctx)   // ctx = { maze, openDoors, playerX, playerZ, noise01 }
export function breakTrail(entity)              // called after a contact teleports the player away
export const ENTITY_RADIUS;
```

`Entity` exposes `x, z, prevX, prevZ, facing, state ('patrol'|'chase'|'search'), detectedNow`.
State machine: patrol loop over `maze.patrolPoints` -> chase on sight/hearing ->
search (circles the last known position, never frozen more than `IDLE_MAX`
seconds) -> back to patrol. Detection combines `hasLineOfSight` (sight range)
with a hearing range scaled by the player's `noise01`; never omniscient.

---

## src/player.js (pur, sans three)

```js
export function createPlayer(startX, startZ) -> Player
export function respawnPlayer(player, x, z)
export function setCheckpoint(player, x, z)
export function eyeHeight(player) -> number
export function updatePlayer(player, dt, input, maze, openDoors, surface, canMove)
export function toggleFlashlight(player) -> boolean   // false only when physically impossible
export function addBattery(player, seconds)
export const PLAYER_RADIUS;
```

`Player` exposes `x, z, prevX, prevZ, yaw, crouching, sprinting, moving,
stamina, noise01, speed2D, stepEvent, checkpointX/Z, encounters,
flashlightOn, batteryLife, hasFlashlight`. `input` is any object exposing the
`src/input.js` `Input` API (`moveAxis()`, `any()`, `down()`).

---

## src/input.js

```js
export class Input {
  constructor(domElement)
  requestLock() / releaseLock()
  down(code) / pressed(code) / pressedAny(...codes) / any(...codes)
  moveAxis() -> {x, z}       // ZQSD/WASD + arrows
  lookAxis() -> {left, right, up, down}   // J/L/I/K keyboard look fallback
  endFrame()
  dispose()
  locked; fallbackLook; dragging; mouseDX/DY; dragDX/DY; sensitivity; invertY;
}
```

---

## src/camera.js

```js
export function createLook() -> { yaw, pitch }
export function updateLook(look, dt, input, settings)   // settings = { sensitivity, invertY }
export function applyLook(look, camera, eyeX, eyeY, eyeZ)
export function forwardVector(look, out?) -> THREE.Vector3
```

Runs once per rendered frame (not the fixed step): look is direct input, not
part of the deterministic simulation.

---

## src/textures.js

```js
export function createTextures(renderer) -> {
  themes: { [themeKey]: { wall, floor, ceiling } },   // THREE.CanvasTexture each
  tube, tubeRed, tubeBlue, door, exit, water,
  dispose(),
}
export function lerpColor(hexA, hexB, t) -> number
```

All canvas-drawn, deterministic per theme (seeded `mulberry32`). No binary
assets, no network fetch.

---

## src/render/scene.js

```js
export function createScene(canvas) -> { renderer, scene, camera, setSize(w, h) }
```

`renderer.outputColorSpace = SRGBColorSpace`, `toneMapping = ACESFilmicToneMapping`.
`scene.background` starts as a dark-but-not-pure-black colour.

---

## src/render/maze.js

```js
export function buildMazeScene(scene, maze, levelDef, theme, shared) -> MazeScene
```

`theme` is a `THEMES[key]` entry (numeric colours). `shared` is the object
returned by `createTextures`.

```js
mazeScene.group; mazeScene.openDoors;              // Set<"x,y">
mazeScene.exitWorld; mazeScene.startWorld;          // {x, z}
mazeScene.items;                                    // [{x, y, type, taken, mesh, ...}]
mazeScene.tryOpenDoor(px, pz, range?) -> boolean
mazeScene.tryPickup(px, pz, range?) -> item | null
mazeScene.update(dt, progress01?)                   // tubes flicker, doors swing, items bob,
                                                     // water scrolls, final-level colour gradient
mazeScene.dispose()
```

Walls/floor/ceiling are `InstancedMesh` (one draw call each). Fluorescent
tubes are plain emissive-look `MeshBasicMaterial` planes, never per-tube
lights (budget rule). Doors are individual pivoted meshes (few dozen per
level, well inside the draw-call budget).

---

## src/render/entity.js

```js
export function createEntityMesh() -> THREE.Group
export function updateEntityMesh(mesh, entity, alpha, dt)   // alpha = render interpolation factor
export function disposeEntityMesh(mesh)
```

Black primitives (torso/head/arms/legs) plus a cheap inflated-backface
outline per part, no custom shader.

---

## src/render/flashlight.js

```js
export function createFlashlight(camera) -> { spot, target, update(dt, on, baseIntensity?), dispose() }
```

The single dynamic light in the whole game (`THREE.SpotLight`), parented to
the camera. `camera` must be added to the scene (`scene.add(camera)`) once at
boot so the light is picked up by the renderer.

---

## src/audio.js

```js
export function createAudio() -> Audio
audio.resume()                          // call on first user gesture
audio.setMasterVolume(v01) / audio.toggleMute() -> boolean
audio.startAmbience(themeKey) / audio.stopAmbience()
audio.footstep(surfaceKey, sprinting)
audio.doorOpen() / audio.pickup() / audio.contact() / audio.flashlightClick() / audio.exitChime()
audio.update(dt, proximity01, detected)   // drives heartbeat + radio interference continuously
audio.dispose()
```

Everything synthesised with Web Audio oscillators/filtered noise. No sound
files. `proximity01` is *real* distance-based, independent of whether the
entity has actually detected the player (diegetic danger cue, not an AI
omniscience leak).

---

## src/hud.js (pur DOM)

```js
export function createHUD() -> HUD
```

See `src/hud.js` for the full method list (`showScreen`, `setStamina`,
`setBattery`, `toast`, `showLevelIntro`, `showLevelComplete`, `showFinale`,
`showPause`, `showError`, ...). Element ids are fixed by `index.html`.

---

## src/main.js

Boots the renderer, textures, input, audio, HUD; owns the state machine
(`menu -> intro -> playing -> paused/complete -> finale`) and the fixed-step
loop (`FIXED_DT = 1/60`, accumulator pattern, capped at 8 steps/frame, frozen
while `document.hidden`). Movement, entity AI and detection all run inside
`fixedUpdate`; look, particle/cosmetic animation and HUD/audio feedback run
once per rendered frame with render-interpolated positions (`alpha`).

Progress is persisted under `localStorage['backrooms.progress']` (last level
reached + best time/encounters/medal per level) and settings under
`localStorage['backrooms.settings']` (sensitivity, invertY, volume, muted).

---

## tools/validate_levels.mjs

Pure Node script (no three, no DOM): imports `src/levels.js` + `src/maze.js`
directly and, for every level, checks the exit is reachable from the start,
no room is isolated, every patrol point and item is reachable, and that
regenerating from the same seed reproduces byte-identical tiles. Run with:

```
node tools/validate_levels.mjs
```

---

## Non negociable

- Zero build, zero binary asset, zero external URL.
- `Escape` never calls `stopPropagation()` in capture phase: the arcade's own
  exit shortcuts must always fire.
- At most one dynamic light (the player's flashlight `SpotLight`); everything
  else is ambient/hemisphere light or emissive-look materials.
- Movement, AI and detection are fixed-step and pause with `document.hidden`.
