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

**Height fog beats distance fog in a city, and the difference is visible in one A/B.**
`FogExp2` greys everything at a given depth equally, so downtown towers wash out at the
same rate as the low-rise behind them and the skyline flattens. Fogging by how far a
fragment sits *below* a height plane instead leaves the towers dark and solid while the
low-rise and the coastline dissolve - the skyline rises out of the haze. `?fog=flat`
keeps the old uniform shading so the two can be shot from the same camera.

The density does not carry over between the two. `exponentialHeightFogFactor` multiplies
by `(height - y)` as well as by depth before squaring, so it is roughly two orders of
magnitude more sensitive than `FogExp2.density`; the first attempt reused the number
directly and buried the entire city in white at 600 m. The ratio in `VolumetricFog` is
fitted, not converted, and it is commented as such.

**The godrays stage does not produce godrays.** The TSL `godrays` pass raymarches the
sun's shadow map and it genuinely contributes - the A/B at `?quality=ultra` shows a warm
bleed spreading from the sun aperture that is absent at `high`. But composited through
`depthAwareBlend`, which lerps the scene toward a flat colour by ray density, raising the
density does not sharpen the shafts, it washes the whole frame beige. Two things work
against shafts here: at street level in a canyon almost the entire marched volume is
either lit or shadowed rather than sliced, and the shadow frustum is a 150 m follow box.
It ships at a conservative density, faded out with sun elevation, described as a bleed.

**`depthAwareBlend` needs texture nodes, not passes.** It samples every input at offset
UVs, so a bare pass or an arithmetic node (which is what the AO stage leaves behind) has
no `.sample()` and the shader build dies with `blendNode.sample is not a function`.
`getTextureNode()` on the passes, `convertToTexture()` on everything else.

**`tools/shoot.mjs` now rejects unknown arguments.** It silently ignored them, so
`--quality ultra` against a build that had no such flag rendered at the default and
looked exactly like a feature that did nothing. Any harness that swallows a typo will
eventually cost an hour of debugging the wrong thing.

**Measure traffic in simulation time, over minutes, or do not believe the number.** Two
figures published earlier in this build were wrong the same way: "highway holds the deck
11/12" and "city traffic 24.5/28 flowing at 26 km/h". Both were sampled seconds after
spawn, during the phase where cars are still accelerating and no jam has had time to form.
Run either for two minutes and the highway drops to 1/12 on the deck and the city to
15/28. Sampling wall-clock makes it worse: the fixed-step loop caps at five steps a frame
and *discards* the remainder, so at 5 fps headless the simulation runs at a third of real
time and a "12 second" test is four seconds of game. Hook a fixed callback, accumulate
`dt`, and drive the test off that.

**One recovery path, three separate bugs, all invisible to a short test.** Stuck cars are
teleported forward along their lane. That code (a) hardcoded wheel height, which is right
for the 2D street graph whose `lanePointOnEdge` returns no `y` at all and catastrophic
for a deck 9.5 m up - highway cars were teleported off the viaduct one at a time, which is
why they ended up on the ground *at their correct ring radius*; (b) nudged the car
`along + 0.05`, about two metres, which is shorter than a car, so a vehicle wedged
nose-to-tail was rematerialised inside its neighbour and the pile-up fed itself; and (c)
only counted a car as stuck if it was *asking for throttle*, deliberately excluding cars
queued legitimately - but when the lead car is jammed against scenery, nobody in the queue
trips either test and the whole line parks permanently.

The third fix needed a second, slower timer rather than loosening the first. Loosening the
throttle test is what cost a third of the city's traffic once before (it is in the git
history); twelve seconds below walking pace is a different question from "wants to move
and cannot", and it deserves its own counter.

**A test that bypasses input cannot catch input bugs.** The first version of the smoke
test poked game state directly - `setLinvel` on the player, `traffic.enter()` for the
car - and reported four failures that were all defects in the test. The player is a
kinematic character controller and ignores rigid-body velocity; vehicle entry is gated on
`input.pressed('interact')`, an edge that never fires unless a key actually goes down.
Rewritten to dispatch real `KeyboardEvent`s and `MouseEvent`s at the window, it exercises
the same path a player does, and every one of those four "failures" passed.

**One exception per frame cost 36x the frame budget.** `Boat` has `speedKmh` and
`gearLabel` but no `rpm` - it has a throttle, not a gearbox. The HUD debug line read
`car.rpm.toFixed(0)` for any vehicle, so every frame the player spent in a boat threw and
took the rest of the render update with it. The smoke test ran 11 seconds of simulation in
420 seconds of wall clock; with the guard added, 22 seconds in 22. Nothing about this was
visible in a screenshot - the boat still floated, still steered, and the frame still drew.
It needed a test that got in the boat and kept playing.

Run it with `npm run smoke` against a dev server on 8092.

**Teleporting an entity in a physics world needs a destination that exists.** Completing a
mission in the smoke test means getting a car to the objective, and the obvious shortcut -
drop it forty metres short along the straight line from the mission start - puts it inside
a city block about as often as not. A car spawned inside a building sits at full throttle
reading zero, which looks exactly like a broken drivetrain. Placing it on an actual road
node adjacent to the goal fixed it in one go, and recording top speed during the run
separates "wedged" from "never accelerated" without another debugging round.

**While DRIVING, `player.position` is stale.** `Player.update` returns early in that
state and the body is not stepped; `Missions._playerPoint` reads the vehicle instead.
Anything measuring the player's progress has to do the same or it measures a parked
corpse - the smoke test reported a constant 620 m to a goal it was driving straight at.

**The player could not die, and nothing in the game could hurt them.** `Player.damage()`
has always returned `true` at zero health, and the single call site - vehicle collision
damage - discarded the result. Nothing anywhere read `player.health`. So the bar emptied
and play carried on. Worse, that collision was the *only* damage source in the entire
codebase: police could ram you and arrest you but never shoot you, which made a five-star
wanted level a chase with no stakes. Both are fixed, and the health check now lives in one
place in the fixed step rather than at each damage site, so a future damage source cannot
forget to handle killing the player.

**"It exists" is not a test.** The first version of the police-gunfire check asserted
`typeof wanted._shootAt === 'function'`, which would pass just as happily if the method
returned immediately every time. Replacing it with a live pursuit - stand a cruiser next
to the player at four stars, give it line of sight, watch the health bar - immediately
exposed a real bug in the feature I had just written: the muzzle sits above the cruiser's
roof and the ray was not excluding the shooter's own collider, so officers were taking
cover behind their own cars. One shot in twelve seconds became six, and the damage from a
single unit went from 9.6 to 37.3.

**A load that can only ever give you more is not a load.** `SaveGame.load` merged the
saved state into the live one instead of replacing it. It added the saved weapons to the
set the player already held, and marked the saved missions complete without clearing the
rest - so loading a save from before you found the rifle left you holding the rifle, and a
mission finished after the save stayed finished.

That last one was the worst of the three, because it left the game *self-contradictory*:
`completed` was assigned `done.size` from the save while the mission itself still carried
`state: 'complete'` and its start marker stayed hidden. The counter read 0 of 8, the
mission could never be triggered again, and nothing in the UI explained why. Missions now
go through `restoreProgress()`, which sets every mission's state and marker from the save
and cancels anything in progress; weapons rebuild their set from scratch.

None of this was reachable from the old test, which only checked that money survived a
round-trip. Money was the one field the merge happened to get right.

**An iteration that finds nothing is still worth running.** Pickups, the settings panel and
the effect pools were all checked on the assumption something would be wrong with them,
and nothing was: the full-health guard correctly refuses to consume a health crate, volume
reaches the audio graph, resolution scale really does resize the drawing buffer, and
churning quality through all four presets and toggling post FX off and on leaves the scene
rendering rather than black. Skid marks looked like a leak at 1032 of them, but the pool is
a fixed 2400-quad ring buffer drawn in one call with a draw range, so it is bounded by
construction. Those twelve checks are now in the suite, which is the actual return on the
iteration: the behaviour is pinned whether or not it was broken today.
