# RESONANCE - contrats de modules

Signatures publiques uniquement. Les modules `wave`, `board`, `levels`,
`coords`, `history` sont purs (sans three, sans DOM) et importables sous Node.

## src/wave.js (pur)

- Constantes : `SIM_N` (96), `BANDS` (3), `PERIODS` (pas par oscillation),
  `STEP_DT` (1/60 s), `BASE_DAMP`, `FOAM_DAMP`, `WAVE_SPEED` (cellules/pas).
- `createWave()` renvoie :
  - `n`, `fields[b].cur/.prev` (Float32Array n*n), `wall` (Uint8Array), `damp`
  - `idx(x, y)` -> index de cellule
  - `setWall(x, y, on)`, `setFoam(x, y, on)`, `clearLayout()`
  - `setSources(list)` avec `{idx, band, amp, phase}` (phase en quarts de periode)
  - `addResonator(x, y, from, to, gain)`
  - `addProbe(x, y, band)` -> sonde ; `probeLevel(probe)` -> amplitude estimee
  - `step()` (un pas fixe, zero allocation), `reset()`, `t` (compteur de pas)

## src/board.js (pur)

- Constantes : `BOARD_N` (24), `SLOT` (4), `BAND_NAMES`, `CHARGE_TIME` (1.5 s),
  `DEFAULT_THRESHOLD`, codes d occupation `FREE/WALL/FOAM/CRYSTAL/RESON/FORK`.
- `slotToCell(s)` -> cellule centrale d une case.
- `createBoard(level, wave)` renvoie :
  - `forks`, `crystals`, `stock`, `poses`, `level`, `occ`
  - `occAt(x, y)`, `forkAt(x, y)`, `crystalAt(x, y)`, `inBounds(x, y)`
  - `place(x, y, band, phase)` / `remove(fork)` / `setBand(fork, band)` /
    `setPhase(fork, phase)` -> `{ok, reason?}` (refus uniquement physiques)
  - `tick()` -> cristal brise ce pas ou null (a appeler apres `wave.step()`)
  - `restoreShatteredSince(step)` -> cristaux restaures (support d annulation)
  - `status()` -> `{targetsLeft, failed, chargingForbidden, won}`
    (pas de victoire tant qu un interdit se charge)

## src/levels.js (pur)

- `LEVELS` : 12 niveaux `{id, name, hint, stock, crystals, walls?, foams?,
  resonators?, solution, par}`. `solution` est la reference validee par
  `tools/validate_levels.mjs` ; `par === solution.length` pilote les medailles.

## src/coords.js (pur)

- `cellToWorldX/Z(c)`, `slotToWorldX/Z(s)`, `worldToSlot(wx, wz, out)` -> bool.
  Seule source de verite du mapping cellule <-> monde (96 texels sur 95 segments).

## src/history.js (pur)

- `createHistory()` -> `{push(entry), undo() -> entry|null, clear(), length}`.

## src/camera.js

- `createOrbit(camera)` -> `{frame(), orbit(dx, dy), zoom(delta), update(dt),
  pick(ndcX, ndcY, outVec3) -> Vector3|null, target, state}`.

## src/input.js

- `createInput(canvas, handlers)` avec handlers `{gesture(), orbit(dx, dy),
  hover(nx, ny), click(nx, ny, button), wheel(nx, ny, dy), action(name)}` ;
  renvoie `{update(dt), dispose()}`.

## src/hud.js

- `createHud(handlers)` -> `{showScreen(name|null), setLevel(level, idx, total,
  best), setStock(stock, selectedBand), setPoses(n), setMuted(m), showFail(on),
  toast(msg, kind?), showComplete(info), bandName(b)}`.

## src/audio.js

- `createAudio()` -> `{unlock(), setMuted(m), muted, syncForks(forks),
  setDanger(frac), place(band), remove(), tweak(band), error(), shatter(band),
  fail(), win(), click(), dispose()}`.

## src/render/surface.js

- `BAND_COLORS` (3 THREE.Color).
- `createSurface(scene)` -> `{mesh, setLayout(wave), update(wave), dispose()}`.

## src/render/pieces.js

- `createPieces(scene, textures)` -> `{setBoard(board), sync(time,
  selectedFork, hoverSlot), shatter(crystal), update(dt, time), dispose()}`.

## src/render/cavern.js

- `createCavern(scene, textures)` -> `{setLayout(level), dispose()}`.

## src/textures.js

- `createTextures()` -> `{rock, halo, warn, frame, foam, dispose()}` (CanvasTexture).

## window.game (hooks de test)

- `mode`, `levelIndex`, `board`, `wave`, `levels`, `start()`, `loadLevel(i)`,
  `place(x, y, band, phase?)`, `removeAt(x, y)`, `undo()`, `restart()`,
  `status()`, `slotToWorld(x, y)`, `measureLuminance() -> Promise<0..255>`.
- `window.__ready === true` en fin de boot.
