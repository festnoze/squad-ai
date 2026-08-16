# Liberty Horizon - Roadmap

GTA V-style open-world sandbox. Target: on-foot player, drivable cars, drivable boats,
a full island map, and a mission chain. Rendering is Three.js **WebGPU** (Chrome maps
WebGPU to **D3D12**, so it runs natively on the NVIDIA GPU) with automatic WebGL2 fallback.
Physics is **Rapier3D** (Rust compiled to WASM, SIMD).

Run: `npm run dev` -> http://localhost:8092

Legend: `[ ]` todo `[~]` in progress `[x]` done

---

## Iteration 1 - Engine foundation + city + player on foot  `[x]`
- [x] Project scaffold (Vite, three 0.185, rapier3d-compat 0.20)
- [x] `Engine`: WebGPURenderer w/ WebGL2 fallback, ACES tone mapping, HDR pipeline
- [x] Fixed-timestep game loop decoupled from render
- [x] Input system (keyboard + mouse look + pointer lock + gamepad)
- [x] Procedural PBR texture factory (albedo/normal/roughness/AO from FBM noise)
- [x] Material library: asphalt, concrete, glass curtain wall, brick, sand, grass, metal
- [x] Analytic `SkyDome` + time-of-day sun + PMREM environment
- [x] Post-processing: GTAO + bloom + SMAA (graceful degrade)
- [x] Rapier physics world wrapper w/ fixed step
- [x] Procedural city: road grid, sidewalks, city blocks, instanced buildings
- [x] Static colliders for buildings/ground
- [x] Player: capsule kinematic character controller, walk/sprint/jump
- [x] Third-person orbit camera with collision-aware boom
- [x] Verified booting in Chrome with no console errors

## Iteration 2 - Cars  `[~]`
- [x] `Vehicle`: Rapier `DynamicRayCastVehicleController` (4-wheel raycast)
- [x] Engine curve, gearbox, throttle/brake/handbrake, Ackermann steering
- [x] Procedural car mesh (body, glass, wheels, lights) - multiple classes
- [x] Enter/exit vehicle, camera mode switch, chase camera with speed FOV
- [x] Wheel visual sync (spin, steer, suspension travel)
- [x] Engine audio (WebAudio synth: revs, gearing, tyre squeal, horn, sirens)
- [x] Skid marks (lit ribbon decals) + tyre smoke + engine smoke
- [x] Traffic AI cars following the road network
- [x] Collision damage (contact-force driven, paint darkens, driver takes a hit)

## Iteration 3 - Boats + water  `[~]`
- [x] Ocean: analytic waves + scrolling normals (cross-backend; WaterMesh is WebGPU-only)
- [x] Buoyancy solver (multi-point volume sampling) + hydrodynamic drag
- [x] `Boat`: throttle, rudder, planing, run-aground  (wake/spray still todo)
- [x] Harbour, marina, docks, beach transition geometry
- [x] Swimming: buoyant surface swim, prone pose, splash on entry/exit

## Iteration 4 - Full map  `[~]`
- [x] Island terrain: coastline field, beaches, sea wall, heightfield collider
- [x] Districts: Downtown, Midtown, Suburbs, Industrial, Docks, Beachfront
- [x] Elevated ring highway: deck, barriers, piers, 4 ramps, overpasses, on map
- [x] AI traffic on the highway: 12/12 hold the deck across 130 s of simulation,
      7.8/12 flowing at 44 km/h with peaks to 126. Three defects, all in the shared
      stuck-recovery path: it teleported to ground height on an elevated network, it
      respawned cars inside the car they were wedged against, and a queue behind a jammed
      lead car tripped no timer at all. Behind `?hwtraffic=N`, still off by default
- [x] Traffic AI: lookahead rolls onto next edge, cross-track correction, scan ignores walls
- [x] Traffic flow fixed: lane offsets were off the carriageway
- [x] City traffic no longer decays: 23.8/28 flowing at 30 km/h and still rising at 130 s.
      The earlier "24.5/28 at 26 km/h" was an early-run sample that missed a slow bleed to
      15/28 - a dead-queue timer fixes it
- [x] Bridges over water: two cable-stayed spans, the 909 m Harbour Bridge (26 m
      clearance) and the 684 m Marina Bridge (16 m). Measured shortcuts - they replace
      1478 m and 1150 m road detours around the two inlets. Own map layer, not spliced
      into the ground road graph
- [ ] Tunnels - deliberately deferred. The island is flat, so there is no relief to bore
      through and a tunnel would only duplicate what the bridges already do. Worth
      revisiting only if the terrain grows hills or the city gets a grade-separated core
- [x] Street trees, hedges, planters, containers, rooftop plant
- [x] Lamp posts, traffic lights, hydrants, benches, bins, bus shelters
- [x] Rooftop billboards + wall signs (shared atlas, one draw call)
- [x] Minimap + world map (radar, streets, blips)
- [x] Vehicle LOD (draw calls 656 -> 292) + frustum culling

## Iteration 5 - Gameplay & missions  `[x]`
- [x] Pedestrian crowds (pavement routes, fleeing, knockdowns, LOD)
- [x] Wanted level (heat/stars, engagement gate) + police A* pursuit + busted
- [x] Weapons (4, hitscan, recoil, reload) + world pickups (health/armour/ammo/guns)
- [x] Mission framework (objectives, triggers, world markers, rewards)
- [x] 14 missions over nine objective types: steal, drive, goto, sail, collect, wait, and
      the three later templates - chase (2 jobs), defend (2) and race (2). The eight
      go-to/collect/wait jobs shipped first; `tools/probe-mtemplates.js` drives the three
      new templates through both endings, the one that pays and the one that puts the job
      back on the map
- [x] Save/load (localStorage, autosave, versioned), money, stats
- [x] Phone menu (`T`): jobs sorted by distance with one-click waypoints, a stats page
      and a layout-aware controls page. Does not pause the world

## Iteration 6 - Polish  `[ ]`
- [x] Dynamic weather: clear/cloudy/rain/storm, wet roads, lightning
- [x] Height fog: haze pools below a 155 m plane (deepens in rain) with a forward-
      scattering lobe that warms towards the sun. Replaces the uniform FogExp2 shading
      via `scene.fogNode`; `?fog=flat` restores the old one for comparison
- [~] Godrays: the TSL `godrays` pass runs on `?quality=ultra` and does contribute
      (A/B verified), but with `depthAwareBlend` it reads as a warm bleed around the sun
      rather than as distinct shafts - crank the density and the whole frame washes flat
      rather than streaking. Shipped conservatively and named honestly
- [x] Day/night cycle: street lights, lit windows, headlights, pooled real lights
- [x] Neon: 354 shopfronts, tubes + blade signs + graded pavement spill
- [x] Radio: 4 procedurally generated stations (scales, chords, drums), car-only
- [x] Ambient soundscape: three continuous noise beds (city hum / wind / surf) mixed from
      district density, altitude, speed, distance to shore and time of day
- [x] Pause menu with stats/settings/save tabs, quality + resolution + volume
- [x] Profiler + CPU pass: frame CPU 51.5ms -> 17.1ms (sleeping vehicles)
- [x] Highway traffic on by default (26 cars). Every car holds the deck across 130 s;
      median gap 139 m on the 4 km ring, +1.5 ms over 14 cars
- [x] Player can die. "Wasted" respawns at full health for a $750 hospital fee, drops
      armour, clears the wanted level and fails the active job. `damage()` had always
      returned true at zero health and the one call site discarded it, so the bar simply
      emptied and play continued
- [x] Police return fire (3 stars up, line-of-sight raycast, accuracy falling off with
      range). Before this, vehicle collisions were the *only* damage source in the game
- [x] Being busted now also fails the active mission, as dying does
- [x] Save/load replaces progress instead of merging into it. Loading used to keep
      weapons picked up after the save, keep missions completed after it (with the
      counter disagreeing, leaving them unplayable), and leave an in-progress mission
      running
- [x] Pickups and settings verified: health/armour/weapon pickups, the full-health guard
      that stops a health crate being wasted, volume reaching the audio graph, resolution
      scale resizing the framebuffer, and switching quality or toggling post FX without
      black-screening. No defects found - these were already correct
- [x] Ambient fill rig: a non-shadowing fill light opposite the sun, plus a much stronger
      hemisphere and ambient floor. The player's spawn view went from 90.6% of pixels
      below luminance 16 (median: pure black) to 49.6% with a median of 16.6. Tuned
      against `tools/luma.mjs`, not by eye
- [x] End-to-end smoke test (`npm run smoke`): 48 checks driven through real keyboard and
      mouse events - walk, enter/drive/exit car, enter/drive boat, a full mission from
      trigger through steal objective, drive-in and reward, weapon fire, wanted level,
      save/load round-trip, plus the failure paths - wasted, busted, mission timeout, and
      live police gunfire measured on the health bar. Found a per-frame exception in the
      boat HUD path that no screenshot could
- [x] Wrecked cars burn and then explode. Zero health lights a 3.4 to 5.5 s fuse (3.84 s on
      the recorded run, and the bang landed within 0.01 s of it) and turns the exit prompt
      into a "Bail out - 3.7s" clock, so leaving a burning car is a decision with a timer on
      it. The blast costs an unarmoured player 23.1 hp at 6 m against 51.3 hp at 2 m and
      nothing past 11 m, chars the hull and drops it out of the enterable set; on the
      recorded run it also floored 3 peds and set the car parked four metres away alight in
      turn. 28/28 on `tools/probe-wreck.js`
- [x] Fall damage and drowning. Landing damage is quadratic in impact speed above a 12 m/s
      floor: stepping off the 9.5 m highway deck costs 36.7 hp, 16 m costs 73.1, and a 2 m
      drop or a full-height jump cost nothing. Under water a 20 s breath meter appears on the
      HUD, goes red and pulses on its last quarter (measured: red 4.9 s before the first
      health tick, not after it) and then drains health at 2.8/s, which kills a full-health
      swimmer 53.9 s after going under. 17/17 on `tools/probe-falldmg.js`
- [x] AI traffic reads the traffic lights it drives past. `VehicleManager._driveAI` folds the
      signal phase for the car's approach axis into the same target-speed clamp the obstacle
      scan uses, with a hold cap so a red can never park a car for ever. Over 120 s of
      simulation the city flows 24.30 of 28 cars with the signals live, against the 23.8/28
      baseline with them detached, and 0 cars crossed a solid red across 26 signalled
      crossings. On the red band, 57% of 311 samples were stopped and the mean was 7.8 km/h
      while the crossing axis ran at 46.7; the lit lens agreed with the phase the cars obey
      on 40 of 40 samples. 12/12 on `tools/probe-lights.js`
- [x] Preferences persist. Quality, resolution scale, volume and the post toggle are written
      to their own `localStorage` key (not the save slot) and read synchronously at module
      load, because the preset decides which post stages exist and the scale decides how big
      the swap chain is - both are decided before the first frame, not applied over the top
      of a default. All four survive a real `page.reload()`: 28/28 on
      `tools/probe-settings-run.mjs`, 18 checks before the reload and 10 after, including a
      pipeline with no AO stage and a 1120 of 1600 px swap chain on the second boot
- [ ] Verify 60 fps at 1080p on real GPU hardware (headless numbers are not representative)
