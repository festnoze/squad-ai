# PARADOXE - contrats de modules

Signatures publiques. Un module peut ajouter des exports, jamais en changer un.
Regles globales: ES modules natifs, zero build, three.js r169 vendorise
(`import * as THREE from 'three'`), aucun addon `three/examples/jsm/*`, aucun
asset binaire, aucun `fetch`. Interface en francais, sans accent dans le 3D.
Commentaires en anglais. Zero allocation par image dans les chemins chauds.

---

## `src/config.js`

Constantes seulement. `GAME_ID`, `STORAGE`, `SIM`, `PLAYER`, `CRATE`, `WORLD`,
`CAMERA`, `BIT`, `KEYS`, `PALETTE`, `AUDIO`.

`SIM.version` versionne le format des sauvegardes: le changer invalide la
progression stockee (les reglages physiques ayant change, les bandes aussi).

---

## `src/levels.js`

```js
export const LEVEL_DEFS   // definitions brutes (deux grilles ASCII)
export function parseLevel(def, index) -> Level
export const LEVELS       // LEVEL_DEFS parses, dans l ordre de jeu
export const LEVEL_COUNT
```

`Level` = `{ index, name, hint, w, h, height:Int8Array, fragile:Uint8Array,
spawn:{x,z}, exit:{x,z}, buttons:[{x,z,group}], plates:[{x,z,group}],
doors:[{x,z,group}], crateSpawns:[{x,z}], teleports:[{x,z,tx,tz}],
require:Int8Array(8), seconds, ticks, maxClones, medalClones }`.

Grille `heights`: `' '` trou, `'0'` sol, `'1'` bloc de 1, `'2'` bloc de 2,
`'#'` mur. Grille `marks`: `'S'` depart, `'X'` sortie, `'K'` caisse, `'T'`/`'t'`
teleporteurs, `'1'..'6'` bouton du groupe n, `'a'..'f'` plaque du groupe 1..6,
`'A'..'F'` porte du groupe 1..6, `'~'` sol fragile. Une porte s ouvre quand
`require[groupe]` declencheurs du groupe sont actifs.

`parseLevel` leve une exception explicite sur toute grille mal formee.

---

## `src/sim.js`

Aucune dependance hors `./config.js`. Pas de three, pas de DOM.

```js
export function createSim(level) -> Sim
sim.reset(recordings)      // recordings: bandes des clones, du plus ancien au plus recent
sim.step(bits, yawByte)    // avance exactement un tick de 1/60 s
sim.traceAt(tick, bodyIndex, out) -> out
sim.heightAt(cx, cz) -> number     // hauteur courante de la cellule, -1 = trou
```

Etat lisible: `sim.tick`, `sim.actorCount`, `sim.status`
(`'run' | 'win' | 'fell' | 'timeout'`), `sim.actors`, `sim.crates`,
`sim.bodies` (table indexee: acteurs 0..maxActors-1 puis caisses),
`sim.doorOpen`, `sim.buttonOn`, `sim.plateOn`, `sim.groupOn`, `sim.heightNow`,
`sim.fragileTimer`, `sim.frameEvents` (vide au debut de chaque `step`).

Un evenement est `{ actor, key, tick }`. `actor` vaut 0 pour le joueur, i>=1
pour le clone i-1, -1 pour le monde. Cles: `jump`, `fall`, `refuse`,
`grab:<n>`, `drop:<n>`, `tp:<n>`, `b+<n>`, `b-<n>`, `exit`, `crack`, `collapse`.

Invariants non negociables:
- pas de `Math.random`, pas d horloge, `SIM.dt` est constant,
- acteurs mis a jour du plus ancien au plus recent, joueur en dernier,
- collisions iterees dans ce meme ordre d age (`iterBodies`),
- deux acteurs sont intangibles tant que leurs boites ne se sont pas separees
  une fois (ils demarrent tous empiles sur la case de depart).

---

## `src/recorder.js`

```js
export function createRecording(maxTicks) -> Recording
export function pushTick(rec, bits, yaw) -> boolean
export function markPos(rec, x, y, z)
export function pushEvent(rec, tick, key)
export function posAt(rec, tick, out) -> out
export function sealRecording(rec) -> Recording   // copie compactee
export function eventLabel(key) -> string
export function isMarkingEvent(key) -> boolean
```

`Recording` = `{ ticks, capacity, bits:Uint8Array, yaw:Uint8Array,
pos:Float32Array, events:[{tick,key}] }`.

---

## `src/paradox.js`

```js
export function createParadoxWatch() -> Watch
watch.reset(recordings)
watch.onEvent(actorIndex, key, tick)
watch.update(sim) -> null | { clone, text }
watch.stress(cloneIndex) -> 0..1
```

Strict sur les evenements marquants manquants (tolerance `SIM.eventTolerance`
ticks), indulgent sur les evenements en trop, et une derive de position de plus
de `SIM.driftRadius` pendant `SIM.driftTicks` ticks vaut blocage.

---

## `src/input.js`

```js
export function createInput(canvas) -> Input
input.bits                 // octet BIT, recalcule a chaque touche
input.pressed(name)        // front montant consomme: rewind, restart, undo, pause, mute
input.on(name, cb)
input.consumeMouse(out, dt) -> { dx, dy, wheel }
input.setEnabled(v)
input.releaseAll()
input.dispose()
```

`consumeMouse` fond trois sources d orbite dans un seul deplacement exprime en
pixels de souris: glisser au pointeur, glissement lateral du pave tactile
(`CAMERA.swipeToDrag`) et touches I J K L maintenues
(`CAMERA.keyRotate`, en pixels par seconde). `camera.js` n a donc qu une seule
sensibilite a connaitre. Les touches de camera ne sont jamais dans l octet
enregistre: seul le cap resultant l est, via `rig.yawByte()`.

---

## `src/camera.js`

```js
export function createCameraRig(width, height) -> Rig
rig.camera                 // THREE.PerspectiveCamera
rig.setSize(w, h)
rig.reset(level, x, y, z)
rig.handleMouse(dx, dy, wheel)
rig.yawByte() -> 0..255    // cap quantifie donne a la simulation et enregistre
rig.update(dt, sim, tx, ty, tz)
rig.punch(amount)
```

Le mouvement etant relatif a la camera, `yawByte()` fait partie de l entree
enregistree: c est ce qui rend le rejeu identique.

---

## `src/textures.js`

```js
export function createTextures(renderer) -> Textures
```

Champs: `floor`, `block`, `wall`, `crate`, `button`, `plate`, `fragile`, `exit`,
`tele`, `glow`, `sky`, plus `dispose()`. Tout est `THREE.CanvasTexture`, albedo
en `SRGBColorSpace`, PRNG `mulberry32` graine pour rester reproductible.

---

## `src/render/scene.js`

```js
export function createArena(level, textures, renderer) -> Arena
arena.scene                // THREE.Scene complete (fond, brouillard, lumieres)
arena.group
arena.sun                  // DirectionalLight, suivie sur le joueur par main.js
arena.update(sim, rpos, dt, elapsed)
arena.dispose()
```

`rpos` est un `Float32Array` de 3 flottants par index de corps (meme indexation
que `sim.bodies`), deja interpole par `main.js`.

---

## `src/render/clones.js`

```js
export function createActors(scene, textures) -> Actors
actors.sync(sim, rpos, elapsed, stressOf, sampleTrail)
actors.dispose()
```

`stressOf(cloneIndex) -> 0..1` alimente le grésillement du shader.

---

## `src/hud.js`

```js
export function createHUD() -> Hud
hud.els                    // tous les elements, resolus une fois
hud.showScreen(name|null)  // 'screen-menu', 'screen-pause', ...
hud.setHudVisible(v)
hud.setLoading(ratio, label)
hud.setLevel(index, total, name, hint)
hud.setTimer(remaining, ratio)
hud.setClones(used, max)
hud.banner(title, sub, ms) / hud.toast(text, kind)
hud.setRewind(t01) / hud.flash(kind)
hud.update(dt)
hud.setWin(name, clones, medal, best) / hud.setFail(title, detail, canUndo)
hud.setEnd(text) / hud.setMenuProgress(text)
hud.buildLevelGrid(levels, progress, best, onPick)
hud.showError(message)
```

Le constructeur leve une exception si un identifiant d `index.html` manque.

---

## `src/timeline.js`

```js
export function createTimeline(canvas) -> Timeline
timeline.resize()
timeline.draw(level, recordings, tick, rewind01)
```

---

## `src/audio.js`

```js
export function createAudio() -> Audio
audio.resume()             // premier geste utilisateur
audio.setVolume(v01) / audio.toggleMute() -> boolean
audio.startAmbient() / audio.stopAmbient()
audio.play(name)           // jump land step grab drop refuse buttonOn buttonOff
                           // plate doorOpen doorClose teleport crack collapse
                           // rewind clone paradox tick win fail ui medal
audio.dispose()
```

---

## `src/main.js`

Assemble tout. Phases: `menu`, `levels`, `playing`, `rewinding`, `paused`,
`win`, `fail`, `end`. Boucle: entrees -> commandes -> accumulateur de
simulation -> positions interpolees -> camera -> arene -> acteurs -> rendu ->
HUD. Expose `window.game` et `window.__ready`.
