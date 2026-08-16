# PRISON SCAPE

A browser stealth-action game. You stole the Coeur de Valmont, they gave you
twelve years, and you have one night to walk out of Blackridge penitentiary.

The game opens with a two-and-a-half minute low-poly cinematic - the heist, the
sirens, the arrest, the sentence, the cell door - then drops you in cell N1 with
nothing in your hands.

![stack](https://img.shields.io/badge/three.js-r169-black) ![deps](https://img.shields.io/badge/runtime%20deps-0-green) ![assets](https://img.shields.io/badge/external%20assets-0-green)

No build step, no asset downloads, no network calls at runtime: every texture,
sound, model, animation and shot of the cinematic is generated in code.

## Run it

The game uses ES modules, so it must be served over HTTP (opening `index.html`
straight from disk will be blocked by the browser).

```powershell
# from this folder
python -m http.server 8091
```

Then open <http://localhost:8091/index.html>.

Any static server works just as well (`npx serve`, `php -S`, IIS, nginx...).
Requires a WebGL2 browser: Chrome, Edge, Firefox or Safari 15+.

> If you edit a file and the change does not show up, the browser is holding the
> old ES module. Hard-reload with `Ctrl+Shift+R`, or serve with no-store headers.

## Controls

| Input | Action |
| --- | --- |
| `Z Q S D` or `W A S D` | Move (AZERTY and QWERTY both work) |
| Arrow keys | Move (alternative) |
| `SHIFT` | Sprint - fast, and loud enough to pull guards across a room |
| `CTRL` or `C` | Crouch - halves how fast you are spotted, near-silent |
| `SPACE` | Jump |
| Left click | Fire, or punch when your hands are empty |
| `F` | Punch, whatever you are holding |
| `R` | Reload |
| `1` `2` `3` | Pistol / shotgun / rifle |
| `E` | Take a downed officer's uniform, search a body, or work something loose |
| `M` | Expand the floor plan |
| `ESC` | Pause |

## How it plays

You lose the moment the prison knows you are loose. That happens two ways, and
both of them are on a clock you can see.

### One clock, not one per officer

Getting identified does not end the run: it starts **the lockdown clock**, and
the whole game is the eight seconds that follow.

Every guard on his radio and every camera with you on screen feeds that one
shared clock, and it always runs at the same speed - **being seen by four people
is no worse than being seen by one**. Silence every caller and the clock winds
back down; let it run out and the prison is sealed. The countdown is on screen
the whole time, with the number of sources still calling.

You silence a caller by killing him, punching him (which knocks two seconds
straight off the clock), or - for a camera - shooting it out or breaking its
line of sight long enough that it loses you.

**Cameras** sweep a blue cone. Step into one with a clear line of sight and a
meter starts filling. Once it passes about a tenth, the camera **stops sweeping
and turns to follow you** - the cone goes amber, and a little over a second later
it has you identified and starts calling you in, exactly like a guard on his
radio. Crouching slows it down, breaking line of sight drains the meter and sends
the camera back to its patrol sweep, and a couple of bullets kill it outright.

**Guards** patrol a fixed roster of fourteen officers. Nothing ever replaces one
you put down - the `POLICIERS EN SERVICE` counter on the HUD only ever falls.
What it does do is call the others over: a gunshot pulls every patrol within 48
metres toward the noise, and the HUD says so when it happens.

Ten of them work the cell block, the rotunda, the spine and the yard. The other
four cover the rest of the building, so no wing is a free walk: one round takes
the service corridor and the three rooms hanging off it, one does the laundry,
the plant room and the showers, one walks the workshop and the north corridor
with a look down the solitary slot, and one works the refectory and the kitchen.

They see roughly 105 degrees in front of them - drawn as a fan on the floor -
and hear you long before that if you sprint. When one identifies you he starts
shouting into his radio and the lockdown clock above starts running.

Guards navigate the building properly: when the way to you is blocked they take
a route through the corridors using a flow field over the walkable tiles, and
they treat a still-locked security door as a wall, the same as you do. They
cannot walk through walls, and a safety check puts any guard who somehow ends up
inside geometry back where he last legitimately stood.

### The three things that get you out

- **Guns.** A pistol sits on the desk in the guard post. A shotgun and a rifle
  are locked in the armoury. They make the problem solvable and very, very loud:
  a shot pulls every guard within 48 metres toward the noise.
- **A uniform.** Put an officer down and press `E`. While you are wearing his
  uniform the cameras ignore you completely and guards need to get within nine
  metres before they start to wonder. Fire a shot where a living guard can see
  you and the cover is gone.
- **Your fists.** Always available, gun or not. A punch in the back is a silent
  takedown. A punch in the face staggers the officer for a second and a half,
  stops him calling and knocks two seconds off the lockdown clock - which is how
  an unarmed prisoner survives being spotted.

### Cameras open doors

The security doors are wired to the camera network, so wrecking a camera is not
just a way to hide - it is the key.

| Destroy | Opens |
| --- | --- |
| CAM-2 (rotunda) | The armoury |
| CAM-3 (refectory) | The airlock to the yard |
| CAM-4 **and** CAM-5 (watchtowers) | The main gate |

The floor plan in the corner fills in as you explore, marking the cameras you
have found, their live cones, and whether each security door is still red.

## The rooms

Thirty-five named rooms, each furnished for what it is rather than being a box
with a texture on it:

| Wing | Rooms | On duty |
| --- | --- | --- |
| Cell block | Twelve cells (bunks, pan, sink), two coursives, the sally port | G1, plus CAM-1 down the coursive |
| Central | Rotunda with a raised control desk and pillars, north corridor | G2, G4, G13, plus CAM-2 and CAM-8 |
| Security | Guard post (desk, monitor wall, lockers), armoury (racks, crates), **solitary** (two bare isolation cells, slab bunk and a bucket each) | G3 on the guard post, plus CAM-7, and G13 looks into the solitary slot on his way past. The armoury stays empty: nobody walks through a door they cannot open |
| Service | Refectory, **kitchen** (ranges, extraction hoods, walk-in, knife rack), laundry, plant room, showers (heads, dividers, drains) | G6 and G14 on the refectory and the kitchen, G12 on the laundry, the plant room and the showers, plus CAM-3 |
| West wing | **Sanitary block** (stalls, urinals, trough sink, mirror strip), **infirmary** (three beds behind curtain rails, drug cabinets, trolley), **parloir** (four booths split by glass, stools, handsets) | G11, who walks the service corridor and steps into all three |
| North | **Workshop** (benches, vices, pillar drill, timber stack) | G13, down the bench aisle |
| Spine | The main corridor, from the cell wing to the refectory | G5 and G10, plus CAM-6 |
| Outside | Exercise yard, main gate | G7, G8, G9, plus CAM-4 and CAM-5 |
| Off-plan | The backrooms | Nobody. They do not path in there |

## Off-plan

There is one more level, and it is not on the plan.

The last stall in the sanitary block has a panel that does not sit quite flush,
with a hairline of yellow light around its edge. Pull it away and behind it is
mono-yellow damp wallpaper, soaked mustard carpet, a ceiling low enough to feel
wrong, and fluorescent tubes humming over a grid of identical corridors that
have no business being inside a prison.

No camera watches it and no guard will ever walk in - they do not path off-plan.
There is a rifle back there, a full ammo crate and a medkit, and at the far end
a rusted vent grille that shoves open behind the pallets at the bottom of the
yard. Which makes the whole thing a shortcut that skips the airlock the
refectory camera controls, for whoever bothers to find it.

Both ends are sealed until you work them loose, so the maze cannot simply be
walked into from the yard.

## Layout

```
  cell wing        rotunda      north corridor        armoury
  +--------+       +------+     +--------------+      +------+
  | N1..N6 |       |      |-----|              |------|      |
  | ------ |-------|      |     +-----+--------+      +------+
  | S1..S6 |       |      |           | guard  |
  +--------+       +--+---+           | post   |
       |              |               +--------+
  +----+--------------+------------------------------+
  |            main spine corridor                   |
  +--+------+-----+------+-----+--------+------------+
     |laundry|tech |showers|    refectory
     +-------+-----+-------+    +-----+
                                   |  airlock
                              +----+-------------+
                              |       yard       | -> main gate
                              +------------------+
```

## Code map

| File | What lives there |
| --- | --- |
| `src/main.js` | State machine (menu / film / run / win / loss), shot resolution, objectives |
| `src/cutscene.js` | The opening film: seven sets, fifteen shots, subtitles |
| `src/layout.js` | The level as plain data: rooms, doors, cameras, patrols, pickups. No three.js, so it can be checked from Node |
| `src/world.js` | Turns that data into geometry, colliders, props and lights |
| `src/guards.js` | Patrol, hearing, sight cones, the radio call, the punch |
| `src/cameras.js` | Sweeping cones, detection meters, destruction, the doors they unlock |
| `src/player.js` | Movement, stance, health, disguise, how much noise you make |
| `src/weapons.js` | Three guns and a pair of fists, plus the view models |
| `src/minimap.js` | Fog-of-war floor plan |
| `src/collision.js` | AABB world, swept movement, ray casts |
| `src/textures.js` | Every surface, painted into a canvas at boot |
| `src/audio.js` | Every sound, synthesised with the Web Audio API |
| `src/fx.js` | Pooled sparks, blood, glass, smoke, tracers, decals |
| `src/hud.js` | The DOM overlay |

## Checking your changes

```powershell
npm run check
```

Two checks, both in plain Node - no browser, no dependencies, no build.

**`tools/check-refs.mjs`** walks every module and reports identifiers it uses
but never declared or imported. Parsing alone proves nothing: a constant used
inside a method that was never imported is valid JavaScript right up until the
method runs, and for level-building code that means a black screen on load.

**`tools/check-level.mjs`** asserts the level holds together: no two rooms claim
the same tile, nothing is placed inside a wall, every texture exists, and - the
important part - the progression gating still works. Armoury sealed until CAM-2,
yard until CAM-3, gate until CAM-4 and CAM-5, backrooms sealed from both ends.

Run it after touching `src/layout.js`. Rooms are rectangles and two adjacent
rectangles merge, so a column of solid tiles between two rooms is load-bearing.
Adding a room one tile too wide once deleted the column that kept the armoury
locked - nothing looked broken until you walked straight in.

## Debugging

The running game is exposed as `window.game`. Useful pokes from the console:

```js
game.player.position.set(x, y, z)   // teleport
game.arsenal.give('rifle', 120)     // hand yourself a gun
game.cameras.cameras                // every camera, with its live meter
game.guards.list                    // every guard, with state and radio timer
game.minimap.toggle()               // expand the plan
game.cutscene.time = 90             // jump to a shot in the film
```
