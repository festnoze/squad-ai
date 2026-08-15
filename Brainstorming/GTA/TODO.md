# TODO - proposed improvements

The base game is feature-complete against ROADMAP.md (63 items done, 48-check smoke suite
green). These are the next tasks, ordered by how much play value they buy per unit of
effort. Each carries an acceptance test in the spirit of the rest of the build: a claim is
done when it is measured, not when it looks right. Every candidate below was checked
against the code first; none of them already exists.

Conventions: **S** under an hour, **M** one iteration, **L** several iterations.

---

## P1 - gameplay stakes (the game can now say no; make the world push back)

### 1. Vehicles explode at zero health  `M`
`applyDamage()` reaching 0 just cuts the engine (`Vehicle.js:450`); a wrecked car is a
parked car. Add a wreck state: fire VFX from the existing smoke pool, a delayed explosion
with a blast radius that damages the player, peds and nearby cars, a charred hull
material, and removal from the enterable set. Getting out of a burning car should be a
decision with a clock on it.
- *Accept:* smoke-test drives a car to 0 HP, exits, waits; car detonates, player standing
  6 m away loses health, hull is not enterable, no console errors.

### 2. Fall damage and drowning  `M`
`Player.damage()` has exactly one caller (vehicle impacts). Jumping off the highway deck
(9.5 m) or a tower roof is free, and the player can swim forever. Add impact damage from
vertical velocity on landing, and a breath meter that appears when submerged and drains
health when empty.
- *Accept:* scripted drop from the highway deck costs health, drop from 2 m costs none;
  60 s submerged kills; both in the smoke suite.

### 3. AI traffic obeys traffic lights  `L`
`StreetProps` builds and cycles signal heads (`signals[]`, per-approach, `litIndex`) but
`VehicleManager._driveAI` never reads them, so intersections are a free-for-all that the
player must obey visually while AI sails through. Feed the signal state for the car's
approach axis into the target-speed clamp the obstacle scan already uses.
- *Accept:* measured over 120 s of sim at a signalled junction, cars on the red axis queue
  behind the stop line and cross-traffic flows; city-wide flowing count stays at or above
  the current 23.8/28 baseline (lights must not deadlock the grid).

### 4. Police escalation tiers  `M`
Pursuit is one cruiser archetype at all star levels. Tie response to stars: 1-2 stars
pursue and bust only, 3-4 add gunfire (exists) and roadblocks on the road graph ahead of
the player's heading, 5 adds a faster interceptor spec and spike-strip props that blow
tyres (wheel friction already per-wheel in `Vehicle`).
- *Accept:* at 5 stars a roadblock spawns on the player's predicted edge within 30 s;
  driving over spikes visibly drops that wheel's grip; busted/wasted paths still pass.

## P2 - mission depth (8 missions, one template each; the systems can carry more)

### 5. Mission variety: chase, defend, boat race  `L`
All missions are variations of go-to / collect / wait. Three new templates using systems
that already exist: **chase** (kill or stop a fleeing AI car - traffic AI + vehicle
damage), **defend** (survive N waves at a point - wanted-system spawning without stars),
**race** (checkpoint ring against the clock on water - the sail objective plus a ghost
timer). Roughly 6 new missions on top of the 8.
- *Accept:* each template completable and failable in the smoke suite through real input,
  reward paid, state returns to the pool on failure.

### 6. Mission chains with a payphone hub  `M`
Missions are flat; nothing unlocks. Add `requires: [ids]` to the mission table, show
locked jobs greyed in the Phone's Jobs tab with their prerequisite, and gate the two
hardest existing missions behind chains. The Phone already has the UI surface.
- *Accept:* locked mission cannot be triggered at its marker, unlocks after prerequisite,
  chain state survives save/load (extends the fidelity checks).

### 7. GPS route to the waypoint  `M`
The Phone sets a waypoint blip but the player navigates by staring at the map. Dijkstra
over the road graph (already used for bridge-detour measurements) from the nearest node to
the waypoint's, drawn as a polyline on the minimap and world map, recomputed when the
player strays more than one edge off it.
- *Accept:* route renders on both maps, follows roads rather than crossing blocks,
  recomputes after a deliberate detour; frame cost of the recompute under 2 ms.

## P3 - world texture (alive between missions)

### 8. Highway ramps join the AI graph  `M`
Ring traffic circles forever; ramps carry no AI. Splice ramp foot nodes into the ground
graph and ramp tops into the ring's waypoint network with an elevation-aware
`lanePointOnEdge`, so cars actually enter and leave the expressway. The recovery-teleport
elevation bug that blocked this is already fixed.
- *Accept:* over 130 s of sim at least 3 cars transition ground-to-ring or ring-to-ground;
  ring occupancy stays within 20% of its spawn count (no drain-out); 12/12 on-deck
  invariant holds for cars that stay.

### 9. Parked-car variety and ownership reaction  `S`
Parked cars are silent props until stolen. Give a fraction of them alarms (the existing
horn on a timer plus a wanted bump), and have nearby peds flee on a break-in using the
existing `scatter()`.
- *Accept:* stealing an alarmed car raises heat and scatters peds within 20 m; starter car
  stays exempt.

### 10. Weather-reactive world  `S`
Rain already wets roads and thickens fog, but peds walk through storms untouched and AI
traffic drives at full speed on wet roads. Peds flee to building edges in rain (one new
state reusing FLEE pathing); AI target speed scales by `1 - wetness * 0.25`.
- *Accept:* in a scripted storm, pavement ped count drops and mean AI speed falls
  measurably; both recover on clear.

### 11. Ped variety and cops on foot  `M`
One ped archetype walks the pavements. Cheap wins with the existing `CharacterMesh` +
vertex tints: body-shape/palette variation per district, and at 1-2 stars a foot officer
who walks toward the player and busts on contact (reusing the bust timer), so low wanted
levels are not car-only.
- *Accept:* screenshot across two districts shows distinct silhouettes/palettes; a 1-star
  foot bust completes in the smoke suite.

## P4 - polish and QoL

### 12. Persist settings  `S`
Quality, resolution scale, volume and post toggle reset every reload; only the save slot
persists. Write them to `localStorage` beside the save, apply before first render (the
quality choice must precede pipeline build).
- *Accept:* set quality low + volume 0.2, reload, both hold; smoke check added.

### 13. Key rebinding UI  `M`
`Input.bindings` is data-driven and layout-aware but there is no UI over it. Add a
Controls tab in the pause menu: click an action, press a key, conflict detection,
persisted with the settings above.
- *Accept:* rebind interact to E, enter a car with E, F does nothing, survives reload.

### 14. Engine audio per vehicle class  `S`
Every car shares one oscillator stack; a bus sounds like a sports car. Scale the base
frequency and mix by `spec` (mass or a new `voice` field) so classes are audibly distinct.
- *Accept:* headless gain/frequency probe shows distinct values per class at the same rpm.

### 15. Photo mode  `S`
The free camera (`P`) is 90% of one. Hide the HUD while free-cam is active plus an
optional slow-time toggle, and a key that downloads a clean PNG capture.
- *Accept:* capture from free cam contains no HUD pixels (luma probe on the HUD regions).

## P5 - performance and platform (after a real-GPU baseline exists)

### 16. Real-GPU performance pass  `M` *(blocked on a human with the GPU)*
Every frame-time number so far is software-rendered headless; 60 fps at 1080p remains
unverified (the one open ROADMAP item). Once measured on hardware: if under 60, the known
candidates are shadow-map size (4096), GTAO resolution scale, and ped/vehicle LOD
distances - in that order of expected yield.
- *Accept:* F3 numbers from real hardware recorded in the README for high and ultra.

### 17. Instanced street props  `M`
Lamps, hydrants, bins and benches are merged geometry (fine) but trees carry unique
canopies; draw count at street level runs ~600-1000. Convert tree canopies/trunks to
`InstancedMesh` with per-instance tint to cut draws and memory.
- *Accept:* draw calls in the street shot drop by at least 15% with no visible change in
  a before/after screenshot pair.

### 18. Texture atlas for building faces  `L`
Each material is one 512/1024 procedural set; buildings already batch well, but a facade
atlas would allow more per-building variety (different window rhythms per face) without
new draw calls. Only worth it after 16 shows headroom.
- *Accept:* at least 4 new facade looks; draw count unchanged; luma/screenshot review.

---

# Batch 2 - second pass (2026-08-15)

Grounded the same way as batch 1: everything below was checked absent from the code before
being proposed (no PannerNode anywhere in `Audio.js`, one hardcoded save `KEY`, fixed
`radarSpan = 260`, no flying or two-wheeled vehicle class, no ambient-event system, no
i18n layer).

## P2+ - play value

### 19. Repeatable side hustles: taxi and vigilante  `M`
Missions are finite (8, soon ~14); once done, the world has no money loop. Enter a taxi
(new livery on an existing sedan spec) and press a key to start fares: pick a random road
node, deliver a ped within a soft timer, pay scales with distance. Same skeleton in a
police car gives vigilante (chase the marked AI car, task 5's chase logic). Infinite,
procedural, and reuses missions' objective markers without touching the mission table.
- *Accept:* three consecutive fares complete and pay through real input in the smoke
  suite; leaving the vehicle cancels the hustle and returns the world to idle.

### 20. Hidden packages  `S`
A classic collectible layer the pickup system already carries: 30 packages placed on
rooftops, pier ends, the bridge towers and park corners (spawn logic can reuse the
existing prop-collision checks), a running counter on the Phone stats page, money bonus
every 10, all persisted in the save.
- *Accept:* collecting increments a persisted counter; bonus paid at 10; counter and
  remaining package positions survive a save/load round-trip in the fidelity checks.

### 21. Ambient street events  `M`
Between missions the city never surprises: no fender-benders, no NPC police stops. A
lightweight director rolls every ~90 s within 150 m of the player: two AI cars collide
(drive them at a shared point), a cruiser pulls over a speeder (both already exist), or a
ped argument (two peds face off with the flee state inverted). Pure choreography over
existing systems; despawn when the player leaves.
- *Accept:* over 10 minutes of sim, at least 4 distinct events trigger within sight; none
  raises the player's wanted level or strands actors (event actors return to their pools).

### 22. Motorbike vehicle class  `L`
Every vehicle is a four-wheel box or a boat. A bike needs a two-wheel controller (lean
into `steer`, gyroscopic uprighting torque while moving, fall-over when stopped without
input) and exposes the player to task 2's fall damage on a crash - which is what makes it
a different way to drive rather than a thinner car.
- *Accept:* rides stably through the smoke-suite drive test at 60+ km/h, leans visibly in
  a screenshot, and a 60 km/h wall crash ejects the rider with health loss.

## P4+ - feel and QoL

### 23. Positional audio  `M`
Every sound plays at full volume in both ears regardless of where it happens; a gunshot
across the map sounds like one beside the player. Route per-source sounds (gunshots,
horns, sirens, impacts, splashes) through shared `PannerNode`s driven from the listener's
camera pose; keep beds (ambience, radio, engine) on the master bus as they are.
- *Accept:* headless probe places two gunshots 5 m left and 200 m right of the camera and
  reads back distinct pan/gain on the panner graph; siren audibly attenuates with distance.

### 24. Minimap zoom control  `S`
`radarSpan` is a hardcoded 260 m, tuned for on-foot play; at 120 km/h on the highway the
radar shows only road already behind the player. Scale span with player speed (260 m at a
walk to ~520 m at speed, smoothed), plus manual override with the mouse wheel while the
full map is open.
- *Accept:* probe reads `radarSpan` at rest and at highway speed and sees the spread;
  wheel zoom on the world map changes the drawn extent between fixed bounds.

### 25. Multiple save slots  `S`
One hardcoded `localStorage` key means one life; an experiment overwrites a good run. Three
slots with timestamps and a summary line (money, jobs done, clock) in the pause menu's
save tab, using `describe()` which already exists.
- *Accept:* save to slot 2, corrupt slot 1's raw JSON by hand, slot 2 still loads and slot
  1 reports unreadable instead of throwing; covered in the fidelity checks.

### 26. Kill cam / wasted cinematic  `S`
Death currently teleports instantly, which reads as a glitch rather than a consequence. On
wasted or busted: 2 s slow-motion orbit of the body or arrest (free camera rig already
orbits), desaturate via the post chain, then the existing respawn.
- *Accept:* scripted death shows the orbit frames (screenshot mid-cinematic), sim time
  scale returns to exactly 1.0 after, and the smoke-suite death checks still pass.

### 27. French localization  `M`
All UI strings are hardcoded English while the input layer already speaks AZERTY. Pull
HUD/Phone/pause/mission strings into a table keyed by id, ship `en` and `fr`, pick by
`navigator.language` with a pause-menu override persisted with task 12's settings.
- *Accept:* with `fr` forced, a screenshot sweep of HUD, Phone tabs, pause menu and a
  mission briefing shows no English; mission names stay as proper nouns by design.

### 28. Wet-road reflections (SSR)  `S` *(spike, timeboxed)*
three ships a TSL `SSRNode` alongside the GTAO/bloom already in use. Rain's wet-road look
is currently roughness/darkening only; real screen-space reflections of neon and
headlights on wet asphalt is the single biggest night-rain payoff available. Ultra-only,
behind the same graceful-degradation wrapper as the other passes - and abandoned honestly
if it washes out like the godrays did.
- *Accept:* same-camera A/B at night in rain shows lights mirrored on the carriageway, or
  the spike is closed with the measured reason in the README.

---

## Explicitly not proposed

- **Helicopters / planes** - flight trivialises the map (the island is 2.6 km across and
  every mission is ground- or water-based) and needs its own camera, controls and failure
  rules; a motorbike (22) adds a new way to drive for a tenth of the cost.
- **Multiplayer** - the fixed-step sim is not deterministic across machines and nothing
  is architected for rollback; this is a rewrite, not a task.
- **Tunnels** - still deferred for the reason in ROADMAP.md: the island is flat and
  bridges already serve the crossing role.
- **Interior spaces** - every system (traffic, wanted, missions, minimap) assumes the
  2D ground plan; interiors touch all of them at once for one building's worth of payoff.
