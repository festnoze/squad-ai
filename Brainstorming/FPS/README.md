# ASHFALL - Sector 7

A complete browser FPS set in a burnt-out post-apocalyptic downtown at sunset:
deep blue overhead, orange on the horizon, dust blowing through the ruins. One
map, one rifle, endless waves. No build step, no asset downloads, no network
calls at runtime: every texture, sound, model and animation is generated in code.

![stack](https://img.shields.io/badge/three.js-r169-black) ![deps](https://img.shields.io/badge/runtime%20deps-0-green)

## Run it

The game uses ES modules, so it must be served over HTTP (opening `index.html`
straight from disk will be blocked by the browser).

```powershell
# from this folder
python -m http.server 8090
```

Then open <http://localhost:8090/index.html> and click **DROP IN**.

Any static server works just as well (`npx serve`, `php -S`, IIS, nginx...).
Requires a WebGL2 browser: Chrome, Edge, Firefox or Safari 15+.

## Controls

| Input | Action |
| --- | --- |
| `W A S D` or `Z Q S D` | Move (QWERTY and AZERTY both work) |
| Arrow keys | Move (alternative) |
| `SHIFT` | Sprint |
| `CTRL` or `C` | Crouch |
| `SPACE` | Jump |
| Left mouse | Fire (full auto) |
| Right mouse | Aim down sight |
| `R` | Reload |
| `M` | Mute audio |
| `ESC` | Pause |

Mouse sensitivity is on the pause screen and is remembered between sessions.

If the browser refuses pointer lock (sandboxed iframes, some embedded views),
the game automatically falls back to free mouse look so it stays playable.

## The game

**Sector 7 - Ashfall** is a wave defence run. You drop into a plaza in a dead
city and hold it. Every wave adds more hostiles and a nastier mix:

| Enemy | Behaviour | Health |
| --- | --- | --- |
| Ghoul | Charges and swings in melee | 95 |
| Raider | Gas-masked, keeps its distance, fires 3-round bursts | 75 |
| Brute | Armoured, slow, hits for a third of your health | 300 |

Raiders join from wave 2, brutes from wave 4. Kills drop ammo crates and
medkits (medkits get more likely the more hurt you are), and each new wave
hands you a 30-round resupply. Health regenerates after six seconds without
taking a hit. Score, accuracy, time and your best wave are tracked, and the
best wave persists in `localStorage`.

The single weapon is the **AR-7 "Scavenger"**: 30-round magazine, 620 rpm,
hitscan, 27 damage a round with a 2.7x headshot multiplier and damage falloff
past 45 m. Spread grows while you fire, shrinks when you crouch or aim, and
blooms when you jump. Aiming down the sight roughly quarters it.

## How it is built

Plain ES modules and [three.js](https://threejs.org) r169 (vendored in
`vendor/`, the only third-party file). No bundler, no npm install.

```
FPS/
  index.html          markup, HUD elements, import map
  styles.css          HUD and menu styling
  vendor/
    three.module.js   three.js r169
  src/
    main.js           bootstrap, game loop, state machine, wave pacing
    world.js          procedural city, sky/lighting rig, ash field
    textures.js       canvas-generated textures (asphalt, facades, rust...)
    collision.js      AABB collision world, ray casts, swept movement
    player.js         movement, crouch, jump, health, recoil
    weapon.js         rifle viewmodel, ballistics, recoil, reload, ADS
    enemies.js        enemy types, AI state machine, hitboxes, wave manager
    pickups.js        ammo crates and medkits
    fx.js             pooled tracers, sparks, blood, smoke, bullet decals
    audio.js          Web Audio synthesis for every sound
    input.js          keyboard/mouse, pointer lock, layout-agnostic bindings
    hud.js            all DOM HUD state
```

A few decisions worth knowing about:

- **Everything is procedural.** Textures are painted onto canvases at boot,
  the city is generated from a fixed seed (so the map is the same every run),
  and all audio is synthesised from oscillators and filtered noise.
- **Collision is a hand-rolled AABB world**, not a physics engine. Solids
  register a box, movement resolves one axis at a time so bodies slide along
  walls, and a step-up pass lets you walk over kerbs and rubble. Bullets and
  line-of-sight checks reuse the same boxes with a slab test.
- **The viewmodel renders in a second scene** on a cleared depth buffer, which
  is why the rifle never clips into walls.
- **The sky is one shader**: an fbm dust layer, a real sun disc with a
  scattering halo, and haze on the horizon. It is drawn last with depth testing
  on, so pixels already covered by the city never run it. The dome is also
  baked into an environment map at boot with `PMREMGenerator`, otherwise metal
  surfaces render black.
- **Texel density is uniform.** Every world box scales its own UVs by its real
  size, so a 6 m wall and a 40 m tower show the same size windows. Buildings
  use a per-face material array to get a tar roof instead of windows on top.
- **Effects are pooled.** Tracers, decals, particles and impact lights are all
  pre-allocated, so firefights do not trigger garbage collection.

## Tuning

Most of the feel lives in a few constants:

- `src/weapon.js` - `RIFLE_STATS` (damage, rpm, reload, falloff), recoil and
  spread values in `fire()`.
- `src/player.js` - speeds, gravity, jump height, health regen at the top.
- `src/enemies.js` - `ENEMY_TYPES`, and `planWave()` for wave composition.
- `src/world.js` - `GRID` and `PITCH` for city size, `buildSky()` for the mood.

## Known limits

- Designed for mouse and keyboard; there is no touch or gamepad support.
- Enemies path by steering and wall-sliding rather than a navmesh, so a very
  determined player can occasionally kite them around a corner they will not
  cut properly.
- Shadows come from a single directional light with a frustum that follows the
  player, so distant geometry is unshadowed by design.
