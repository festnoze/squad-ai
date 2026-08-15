# Liberty Horizon

An open-world GTA-style sandbox that runs in the browser: an island city you can walk,
drive and sail around, with a mission chain.

Everything in the world is generated procedurally at load time - the coastline, the street
grid, every building, every texture, every vehicle body. There are no downloaded art
assets, which is why the whole thing is a few hundred KB of source and still fills a 3.4 km
island with several thousand buildings.

---

## Running it

```bash
npm install
npm run dev      # http://localhost:8092
```

Then click the canvas to capture the mouse.

## Controls

| Action | Key |
|---|---|
| Move | **ZQSD** (AZERTY) / **WASD** (QWERTY) |
| Look | Mouse |
| Sprint | Shift |
| Jump | Space |
| Enter / exit vehicle | F |
| Aim | Right mouse |
| Fire | Left mouse |
| Reload | R |
| Next weapon | `]` |
| Radio station (in a car) | `]` |
| Handbrake | Space |
| Headlights | L |
| World map | M |
| Free camera (photo mode) | P |
| Pause / settings / save | Esc |
| Toggle debug stats | F3 |
| Respawn | K |

Bindings are on physical key codes, so the movement cluster sits under the same fingers on
any layout - it is ZQSD on AZERTY and WASD on QWERTY, and the on-screen hints name whichever
keys are actually printed on your keyboard.

A gamepad works too: left stick moves, right stick looks, triggers are throttle and brake.

### URL flags

Useful for debugging and for lower-powered machines:

| Flag | Effect |
|---|---|
| `?webgl=1` | Force the WebGL2 backend instead of WebGPU |
| `?quality=low\|medium\|high\|ultra` | Post-processing preset (default `high`) |
| `?post=off` | Disable post-processing entirely |
| `?fog=off` | Disable atmospheric fog |
| `?exposure=0.6` | Override tone-mapping exposure |

---

## Technology

**Rendering** is [three.js](https://threejs.org) driving its `WebGPURenderer`. On
Windows, Chrome implements WebGPU on top of **D3D12**, so the scene runs natively on the
discrete GPU. If WebGPU is unavailable the same renderer falls back to a WebGL2 backend
through the identical code path.

The pipeline is HDR with ACES filmic tone mapping, a follow-the-player cascaded shadow
frustum, and a TSL post chain of GTAO -> bloom -> SMAA. Every post stage degrades
gracefully: if a node graph fails to compile the game renders directly rather than showing
a black screen.

**Physics** is [Rapier3D](https://rapier.rs) (Rust compiled to WASM). Cars use Rapier's
raycast vehicle controller with a drivetrain simulation on top; the player is a kinematic
capsule character controller; boats are driven by a buoyancy solver.

**Everything else is generated:**

- **Textures** - each material is synthesised from FBM and Worley noise into a full PBR
  set (albedo, normal from a Sobel of the height field, roughness, metalness, AO), tiling
  seamlessly. See `src/render/TextureFactory.js`.
- **The island** - one analytic signed field defines the coastline, and the road network,
  terrain mesh, beaches, sea wall and physics heightfield all derive from it, so they can
  never disagree.
- **The city** - a non-uniform road graph (dense downtown, sprawling suburbs) drives block
  subdivision, and each lot rolls an independent programme: tower, podium+tower, walk-up,
  stucco block, shophouse row, house, warehouse, car park, vacant plot, plaza, pocket park
  or construction site.
- **Vehicles** - car bodies are lofted from cross-sections rather than assembled from
  boxes, which is what gives them tapered noses and real rooflines.

## Design notes

A few decisions worth knowing about if you work on this:

**Vertex colours carry per-building tint.** The whole city is a handful of merged meshes -
one per material - so it draws in a handful of calls. Variety comes from writing a
per-surface tint into the vertex colour stream instead of creating a material per building.
Hex literals are decoded from sRGB to linear when written (`GeometryBuilder.setColor`);
skipping that decode is what makes hand-picked mid-tones render washed out.

**Rapier force accumulators persist.** `addForce`, `addForceAtPoint` and `addTorque` keep
applying every step until explicitly reset, unlike impulses. Both `Vehicle.fixedUpdate` and
`Boat.fixedUpdate` call `resetForces`/`resetTorques` first. Without it, buoyancy compounds
every frame and boats accelerate into orbit.

**Boats ignore terrain collision.** A hull resting on a broad collision surface fights the
buoyancy solver, which pins it at whatever depth it first touched. Vertical position is
owned entirely by buoyancy; `Boat._applyGrounding` provides an explicit run-aground rule.

**`GeometryBuilder.rotatedBox` uses the opposite yaw sense to the physics helpers.** Use
`colliderYaw()` when building a collider to match geometry, or the collider ends up
somewhere invisible and objects appear to rest on thin air.

**Rays are cast from the player, not the camera.** In third person the camera regularly
sits inside a wall or a tree, and a ray started there reports a hit at distance zero - so
every shot silently lands on whatever the camera is buried in. `WeaponSystem._fire` slides
the origin forward along the aim line until it is level with the player.

**Night lighting separates looking lit from casting light.** Every lamp head, signal lens
and tower window in the city is emissive geometry driven by one `nightFactor` - that is
what you see, and it costs nothing. A pool of ten real point lights is *re-targeted* each
frame onto the nearest lamp posts, and those are what actually light the road. Lights are
never created or destroyed at runtime, because adding one to a scene forces a shader
recompile. Note that three's punctual lights are physical: intensity is candela with
inverse-square falloff, so a 7 m lamp post needs a few hundred, not a few dozen.

**Wet surfaces darken.** Water fills the pores of asphalt, so less light scatters back
diffusely - a wet road loses albedo and gains a sharp specular. Dropping roughness alone,
without darkening the base colour, makes the road look like polished concrete instead of
wet tarmac.

**The world is never saved.** It regenerates from a fixed seed, so it is byte-identical
every run and storing it would be megabytes of redundancy. Saves hold only what the player
changed: progress, money, loadout, position, time of day.

**Skid marks are lit, not painted.** Asphalt is already almost black, so a flat black
decal is invisible on it. What makes a real skid stand out is that scrubbed rubber is
*glossier* than the road, so the marks use a low-roughness standard material and catch the
sun and the street lamps.

**Sleeping vehicles are the whole performance story.** `Vehicle.fixedUpdate` called
`body.resetForces(true)` - and that boolean is `wakeUp`. It woke every parked car in the
city on every fixed step, so all 148 of them ran a full four-raycast suspension update
forever. Passing `false` and early-returning on sleeping bodies took frame CPU from 51.5ms
to 17.1ms. Anything that touches a Rapier body should think about whether it means to wake it.

**Signs share one texture atlas.** Every billboard and wall sign picks a tile by offsetting
its UVs, so all 120 of them merge into a single mesh and a single draw call. A material per
design would have cost a draw call each.

**The highway is deliberately not in the road graph.** That graph is 2D - it has no
elevation - and every consumer of it (traffic routing, police pursuit, mission placement,
pedestrian spawns, parked cars) assumes any node is reachable from any other at ground
level. Splicing an elevated ring into it would have police pathing straight off a viaduct.
The highway carries its own waypoint ring instead, which is why it has no AI traffic yet.

**Traffic AI steers on two errors, not one.** Aiming at a lookahead point corrects
*heading* but says nothing about lateral drift, so cars slowly leave their lane and never
return. `VehicleManager._driveAI` adds a cross-track term (the Stanley correction) that
measures the signed distance to the lane centreline and steers back. Its lookahead also
rolls onto the *next* edge rather than clamping at the current one - clamping makes a
pure-pursuit controller cut every corner, which on a closed loop compounds into a spiral.
**Lane offsets are measured against the drivable width, not the road width.** The pavement
slab eats 3.2 m off each side, so a 13 m street has only 3.3 m of carriageway either side of
the centreline. Offsetting by half the *full* width put every car permanently half up on the
kerb, grinding along lamp posts and into corner buildings - which presented as traffic
mysteriously stalling at full throttle with nothing in front of it. `PAVEMENT_WIDTH` is
exported from `RoadNetwork` and imported by `City` so the two can never drift apart.

**An explicit cross-track correction made lane-keeping worse, and was removed.** Measured:
gain 1.6 gave 14 of 28 cars flowing with lane error growing past 2.5 m; gain 0 gives 24.5
flowing at 26 km/h and holds 1.6 m. Pure pursuit already aims at a point *on* the lane line,
so an added Stanley term double-counts and oscillates. `crossTrackGain` is left tunable as
a reminder to measure rather than reason about this one.

**The traffic obstacle scan ignores static geometry.** It looks only for cars, the player
and pedestrians. Including buildings deadlocks traffic: a car sitting slightly off its lane
heading points its ray at a wall, brakes, loses the speed its steering needs to correct,
and brakes forever.

**The radio is synthesised, not sampled.** Each station is a scale, a tempo, a chord
progression and a set of voices; `core/Radio.js` walks the progression and queues WebAudio
notes a beat *ahead* of time. Scheduling matters: triggering notes from
`requestAnimationFrame` puts every note wherever the frame landed and audibly stumbles,
because the audio clock is sample-accurate and the render loop is not.

**The sky is hand-rolled.** three's `SkyMesh` does not composite in this pipeline, so
`SkyDome` evaluates an analytic day/night model into vertex colours on the CPU. It also
feeds the PMREM environment bake, so reflections match the time of day.

## Verifying changes

`tools/shoot.mjs` boots the game in headless Chromium, waits for it to finish loading,
positions the camera at a named viewpoint, and reports console errors plus render stats
alongside a screenshot.

```bash
node tools/shoot.mjs --shot list
node tools/shoot.mjs --webgl --shot aerial --out shots/aerial.png --time 15
node tools/shoot.mjs --webgl --shot bay --js "window.game.boats.map(b => b.position.y)"
```

Use `--webgl` for screenshots: headless Chromium composites WebGL far more reliably than
WebGPU, and a WebGPU capture can silently return a stale frame - which is exactly how a
"the whole screen is red" bug once turned out to be a capture artifact rather than a
rendering one.

Exit code is non-zero if the page logged any console error, so it doubles as a smoke test.

The in-game overlay (F3) shows a per-subsystem CPU breakdown from `core/Profiler.js`.
Note that the headless harness renders in software, so its frame rate says nothing about
real performance - use the profiler's CPU numbers, which are meaningful, and measure GPU
cost on actual hardware.

## Layout

```
src/
  core/        Engine (renderer + fixed-step loop), Input, CameraRig, FreeCamera, Noise,
               Profiler,
               Audio (WebAudio synthesis)
  render/      TextureFactory, Materials, SkyDome, Atmosphere, PostFX, NightLights,
               VehicleFX (skid marks, smoke),
               Weather
  physics/     Rapier wrapper, collision groups, heightfields
  world/       GeometryBuilder, RoadNetwork, City, Island, Ocean, StreetProps,
               Signage, Highway
  entities/    Player, CharacterMesh, Vehicle, VehicleMesh, VehicleManager, Boat,
               PedestrianManager
  gameplay/    Missions, Wanted (police pursuit), Weapons, Pickups, SaveGame
  ui/          HUD, Minimap, PauseMenu, styles
tools/shoot.mjs  screenshot / smoke-test harness
ROADMAP.md       what is built and what is next
```

See `ROADMAP.md` for current status.

**Ambience is mixed, never triggered.** The three noise beds start on the first user
gesture and run for the whole session; only their gains and filter frequencies move. A bed
that fades up from silence is a bed the player *notices* - it reads as a cue. One that is
always present and merely changes level reads as the world. The mix is sampled at 6 Hz
because none of its inputs (district, altitude, distance to shore, clock) change faster
than that, and `landField` is a noise evaluation worth not doing 60 times a second.

**Headless can still measure WebAudio.** `AudioContext.currentTime` advances in headless
Chromium even with no output device, so `setTargetAtTime` ramps settle and
`gain.gain.value` reads back a real number. That makes the mix testable from
`tools/shoot.mjs`: wait ~2s, read the three gains, check they match the state the player
is standing in. Reading them in the same tick as the call gives 0 for everything, which
looks like a bug and is not one.

**The phone does not pause.** `PauseMenu` freezes the simulation; the phone deliberately
does not, so traffic keeps moving and missions keep running while it is open. It only
releases pointer lock so the list is clickable. Its list re-renders every 20 frames rather
than every frame - the distances tick visibly but the DOM work is negligible.

**Bridge decks are wound the same way the highway ring is, and that is load-bearing.**
The deck quads go (left0, left1, right1, right0), which only faces upward if the
along-deck and across-deck vectors form a right-handed frame with up. Taking the obvious
perpendicular `(-uz, ux)` gives the *left*-handed one, and the entire carriageway renders
unlit black. It looks exactly like a broken material and it is a sign error - two
characters.

**A pitched deck needs a pitched collider.** `addStaticBox` was yaw-only, which is fine
for a level viaduct and wrong for a bridge approach: yaw-only boxes under a 10% grade are
a staircase, and the wheel raycasts find the flat top of each step. `addStaticBoxQuat`
takes a full rotation, built from the segment direction as yaw = atan2(dx, dz) and
pitch = -asin(dy). Verified by driving: the car climbs 4 m -> 28 m across the approach at
up to 125 km/h, dead on the centreline, with its Y matching `deckHeightAt` to within a
metre the whole way.

**A tower leg that leans all the way from footing to apex stands in the road.** With a
single strut the leg is already most of the way inboard by the time it reaches deck
height, so two 3 m columns end up in the carriageway. Real A-frame towers are vertical to
deck level and only converge above it, which is also the only way the deck can pass
through them.
