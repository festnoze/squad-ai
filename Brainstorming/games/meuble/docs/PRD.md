# PRD - Out of Sight

Product requirements document. Version 1.10, 2026-11-15 (1.10 splits M6: the level work and the M6 gate move to M6b). Version 1.9, 2026-11-15 (1.9 splits milestone M6 at the product owner's request: M6 keeps the finishing work on PC and gains texture pass 2 and open question 28, the mobile port becomes M7). Version 1.8, 2026-11-13 (1.8 adds the M5 wave 5A notes in section 11). Version 1.7, 2026-11-13 (1.7 rewrites M5 after the product owner's M4 playtest: 10 new levels that combine mechanics, larger maze houses, several inhabitants with personalities, the robot vacuum, the rocking chair and the balanced load; adds 3.4, 4.8, 5.4 and the 7.4 house budgets). Version 1.6, 2026-11-12 (1.6 adds the M4 notes in section 11, the 3.3 and 4.7 amendments and open questions 11 to 15). Version 1.5, 2026-11-12 (1.5 adds the M3 notes in section 11 and the pause to hud.controls). Version 1.4, 2026-11-11 (1.4 writes back the
M2.1 fixes found by the critique of the M2 result: discovery grace,
position-only tolerance, decoys, level 1 start station, M2-aware audit; see
the M2 notes of sections 4.4 and 11). Version 1.3, 2026-11-11 (1.3 writes back the
M2 constants of docs/CONTRACT_M2.md: sections 4.4, 4.5, 9 and open question
9). Version 1.2, 2026-11-10 (1.1 adds the creak
gauge, section 4.6, to milestone M2; 1.2 writes back what building M1 taught:
sofa and table positions of level 1 moved after the level audit, dwell
extension rule, a still furniture is never displaced, see the M1 notes in
sections 3.2, 5.1 and 6.3).

This document is the contract for `games/OutOfSight`: a 3D stealth comedy game in
Unity where the player is a piece of furniture that may only move while nobody
is looking. It defines the rules, every constant, the asset strategy, the Unity
architecture, the verification harness and seven delivery milestones. Milestone 1
is deliberately tiny (one room, one inhabitant, one chair) and is specified to
the level of detail needed to build it without further questions. Later
milestones are specified at the level of rules and acceptance criteria; their
constants are tuned when they are reached and written back here.

Anything not covered here is an open question for the product owner, never
something to invent silently. Section 12 lists the open questions and the
default taken for each.

---

## 0. How to read this document

- Section 1 : what the game is and is not.
- Section 2 : conventions and units.
- Section 3 to 6 : the rules (player, observation, inhabitant, level), with
  every M1 constant.
- Section 7 : asset strategy and polygon budgets.
- Section 8 : Unity architecture and module contracts.
- Section 9 : strings shown to the player, in French, verbatim.
- Section 10 : verification harness.
- Section 11 : milestones M1 to M7 with acceptance criteria.
- Section 12 : risks and open questions.

Rules are tagged with the milestone that introduces them: `[M1]`, `[M2]`, etc.
A rule without a tag is `[M1]`.

---

## 1. Vision and scope

### 1.1 Pitch

You are a chair. You want out of this house. The people who live here must
never see you move. Shuffle across the living room while their back is turned,
freeze the instant a head starts to swing your way, and reach the front door
before anyone wonders why the chair is in the hallway.

It is the playground game "un, deux, trois, soleil" (red light, green light)
turned into a stealth game where the watcher does not know they are playing.

### 1.2 Design pillars

1. **Readable in ten seconds.** One rule: do not move while seen. Every system
   added later must be explainable as a consequence of that rule.
2. **Fair tension.** The player always knows whether they are seen, and every
   head turn is telegraphed. Getting caught must feel like the player's
   mistake, never a surprise.
3. **No dead time.** Waiting for a back to turn is the main risk of the
   concept. The player must always have a way to create their own window
   (noise, light, line of sight blockers) from M2 onward.
4. **Comedy.** The inhabitant does not sound an alarm when a chair is in the
   wrong place. They frown, and put it back.

### 1.3 Non-goals

- No combat, no health, no inventory.
- No multiplayer (prop hunt games cover that ground).
- No open world: levels are single houses, short (2 to 6 minutes).
- No narrative beyond a line of text per level.

### 1.4 Platforms

- PC Windows (keyboard and mouse, gamepad) from M1.
- Android from M7. Every budget in section 7.4 is a mobile budget from day
  one so M7 is a port, not a rewrite.

---

## 2. Conventions

- Units: meters, seconds, degrees. Unity axes: x right, y up, z forward.
- Yaw (body, head, furniture) is measured around +y: 0 faces +z, 90 faces +x,
  so a positive yaw turns clockwise seen from above. A glance of -70 deg
  turns the head 70 deg to the left of the body.
- "Seen" always means the result of the observation test in section 4.
- "Fixed step" is the Unity physics step, 0.02 s. All gameplay rules run in
  `FixedUpdate`; rendering only interpolates.
- All code, comments and documentation are in English. All strings shown to
  the player are in French (section 9).
- Async methods, if any, are prefixed with `a` (never suffixed `_async`).
- No em-dash character anywhere in code, docs or strings.

---

## 3. The player

### 3.1 Camera

Third person orbit camera around the furniture. Third person is mandatory: the
whole game is about seeing yourself and the watcher in the same frame.

| Constant | Value |
|---|---|
| Orbit distance | 4.0 m (mouse wheel 2.5 to 6.0) |
| Pitch range | -10 to 75 deg (the view; 2026-11-20 sky ceiling, was 15 to 75): the arm follows down to 5 deg above horizontal only, lower pitches tilt the view up toward the sky |
| Default pitch | 40 deg |
| Mouse sensitivity | 0.12 deg per pixel |
| Target point | furniture center + 0.5 m up |
| Follow smoothing | critically damped spring, 0.12 s |

**Dollhouse walls.** Walls and ceiling are single sided, facing inward. The
camera is allowed outside the room and sees through the back of the nearest
wall. This removes all camera collision code. M1 has no ceiling at all.

### 3.2 Movement `[M1]`

The furniture is a kinematic body driven by a `CharacterController`.

| Constant | Chair value |
|---|---|
| Max speed | 1.5 m/s |
| Acceleration | 10 m/s2 |
| Stop | velocity set to zero on the fixed step where input is released |
| Turn rate | 360 deg/s, toward the movement direction |
| Controller radius / height | 0.28 m / 0.90 m |

Input is camera relative (WASD or left stick). There is no inertia in M1:
releasing the input stops the chair on the next fixed step. Stopping is the
core verb and it must be exact.

M1 note (v1.2): a still furniture is never displaced by anything else. A
still chair does not call `CharacterController.Move`, because `Move`
depenetrates the controller from any overlap: an inhabitant walking through
a still chair shoved it, the shove counted as motion, and the player was
caught for being bumped (found by the probe bot, guarded by probe step 12).
In M1 the inhabitant walks through a still chair; reacting to furniture in
the way is M2 (Investigating).

A moving chair plays a hop animation purely on the visual child (vertical
offset `0.04 * abs(sin(t * 14))` m and a 4 deg rocking). The collider never
hops.

### 3.3 The "moving" predicate

The furniture is **moving** on a fixed step when either is true:

- planar speed over the step is greater than 0.05 m/s;
- yaw change over the step is greater than 3 deg/s.

The cosmetic hop does not count. This predicate is the single source of truth
for the caught rule and lives in pure logic (`MotionRule.IsMoving`).

M4 amendment (v1.6): an **action in progress** counts as moving whatever the
speed: a stool falling or righting itself, a lamp toggle
(`MotionRule.IsMoving(speed, yawRate, actionActive)`). Being sat on is not an
action: a pinned furniture does not move, so it is not moving.

---

### 3.4 Load and balance `[M5]`

A level may put a **load** on the player furniture (a vase, a stack of books, a plant):
`player.load`.
- The kinematic rule (v1.10, from CONTRACT_M5 16.5 and 18): the load **falls** when the change of the
  furniture's planar velocity over the last LoadWindow (0.5 s) reaches LoadFallDeltaV (1.8 m/s). A
  full speed start or stop, a full speed reversal and a 90 deg turn at full chair speed drop it; a
  careful start, stop, turn or reversal holds. There is no spring, no fall angle and no halved
  acceleration: the furniture moves as its body does.
- The load sways as a visual only (a damped spring fed by the same velocity), and the balance gauge
  (left of the creak gauge) shows the velocity change against the fall threshold; it turns red from
  BalanceWarning (0.9) of it.
- With a load, the furniture's sample box grows by LoadHeight (0.25 m): the top of the load is seen.
- When the load falls:
  - a crash noise of 6 m, which alerts like a creak;
  - the broken load stays on the floor as a clue: an inhabitant who sees it gets one discovery,
    walks to it and puts it away (a fall costs one discovery, never the level, q25).
- The load's triangles are budgeted on their own (7.4), not as part of the furniture.

## 4. Observation

### 4.1 Vision test `[M1]`

An inhabitant sees the furniture on a fixed step when at least one **sample
point** of the furniture passes all three checks:

1. distance from the eye is at most `ViewRange`;
2. the angle between the eye forward vector and the direction to the point is
   at most `ViewHalfAngle` (a true cone, not separate horizontal and vertical
   angles);
3. a raycast from the eye to the point hits nothing on the `Occluder` layer.

Sample points of a piece of furniture: its bounds center and the four top
corners of its bounds, each pulled 0.03 m inward. Five raycasts per
inhabitant per fixed step.

| Constant | Value |
|---|---|
| Eye height | 1.60 m |
| `ViewRange` | 10 m |
| `ViewHalfAngle` | 55 deg |
| Eye forward | head forward (head yaw is animated separately from body yaw) |

The geometric part (checks 1 and 2) is the pure function
`VisionMath.IsInCone(eye, forward, point, range, halfAngleDeg)`.

### 4.2 Caught rule `[M1]`

A timer `seenMoving` accumulates fixed step time while the furniture is both
seen and moving, and resets to zero on any step where either is false. The
player is **caught** when `seenMoving` reaches `CaughtGrace`.

| Constant | Value |
|---|---|
| `CaughtGrace` | 0.20 s |

In M1, caught means the level is lost: the inhabitant plays a startled pose,
the fail panel shows, and the level restarts on input. Being seen while
motionless has no consequence in M1, wherever the chair stands.

### 4.3 Fairness feedback `[M1]`

- **Eye indicator** (HUD, top center): closed eye when not seen, open eye when
  seen. It switches on the same fixed step as the vision test.
- **Vision cone on the floor**: a translucent fan mesh at floor level showing
  range and angle, clipped by occluders (fan of 40 raycasts). Always on in M1.
- **Telegraph**: before any head or body turn greater than 30 deg, the
  inhabitant stops and holds a 0.6 s "anticipation" beat (a small head tilt
  and a "hm ?" sound). No turn ever starts without it.
- **Seen and moving**: the screen edge pulses red while `seenMoving` is above
  zero.

### 4.4 Displacement memory `[M2]`

Each inhabitant keeps, for each piece of furniture they have seen, the last
pose at which they saw it. When they see it again at a pose that differs by
more than `DisplacementTolerance`, their **suspicion** rises and they walk
over and carry the furniture back to the remembered pose (the player is
carried and loses the ground gained). Suspicion decays slowly. At suspicion 1
the level is lost.

This is what makes "stand still in the middle of the room" a real decision,
and what turns failure into comedy rather than a restart. Constants are tuned
in M2 (starting point: tolerance 0.75 m or 30 deg, +0.34 suspicion per
discovery, decay 0.02 per second).

M2 values (v1.3, docs/CONTRACT_M2.md): tolerance 0.75 m and 45 deg (30 deg
made every sideways nudge a discovery, since the chair turns toward its
motion at 360 deg/s), +0.34 per discovery, decay 0.02 per second only while
the inhabitant is in Routine or Alerted (so three discoveries in a row lose).
One memory slot per piece of furniture and per inhabitant: the player slot
starts at the spawn pose (open question 9), decoy slots are fixed.

M2.1 values (v1.4), after the critique of the M2 result:

- **Discovery grace.** A discovery needs the chair to be seen out of place
  for 0.2 s in a row, the same grace as the caught rule. Before, a single
  20 ms glimpse was a discovery, which undid the fairness of the caught
  rule.
- **Tolerance.** It is position only (0.75 m). The chair turns toward its
  motion, so a yaw rule punished the act of moving, not the displacement.
- **Decoys.** Any decoy of the chair's kind explains the chair within
  0.75 m of it, whether the inhabitant sees that decoy or not ("une chaise
  parmi d'autres").
- **Shared memory.** After a carry back, every inhabitant remembers the
  chair at the put down pose.
- **Unreachable chair.** When an inhabitant cannot reach a displaced chair,
  it gives up and accepts the chair where it stands.

### 4.5 Hearing `[M2]`

Moving on a hard floor emits noise events with a radius; an inhabitant inside
the radius telegraphs, then turns to look at the source. Rugs are silent.
This gives the player a lure: make noise on purpose, then move the other way.

M2 values (v1.3): one hop event per hop landing on a hard floor, radius
2.0 m (3 m made level 1 a one-solution puzzle); rugs and "soft" rooms are
silent; walls do not block sound. An alerted inhabitant ignores further hop
events (only a creak retargets it), otherwise the head would follow a moving
chair through small turns without any telegraph.

### 4.6 Creak `[M2]`

Old wood cannot stay quiet. The player furniture owns a **creak gauge** from
0 to 1 that makes hiding forever impossible (the idea is borrowed from the
periodic whistle of prop hunt games).

- The gauge fills while the furniture is not moving (section 3.3) and drains
  while it is moving. A player who keeps making progress never creaks.
- At 1 the furniture **creaks**: a loud noise event (section 4.5) is emitted
  at its position and the gauge resets to 0.
- Every inhabitant inside the creak radius becomes Alerted: telegraph, then
  look at the source. The creak itself is not a fault. What matters is what
  the inhabitant then sees: a furniture in motion is caught (4.2), a
  furniture away from its remembered pose is a discovery (4.4), a furniture
  where it belongs is nothing.
- Warning: during the last `CreakWarning` seconds before a creak the
  furniture visibly trembles, a rising wood tension sound plays, and the HUD
  gauge flashes. The creak is never a surprise.
- The gauge is shown on the HUD next to the eye indicator.
- The gauge does not fill while the furniture is being carried back by an
  inhabitant, nor during the first `CreakStartDelay` seconds of a level.

Starting constants, tuned in M2:

| Constant | Value |
|---|---|
| `CreakFillTime` (0 to 1 while still) | 20 s |
| `CreakDrainTime` (1 to 0 while moving) | 10 s |
| `CreakWarning` | 3 s |
| `CreakRadius` | 7 m |
| `CreakStartDelay` | 5 s |
| Alerted look duration | 2 s |

Design consequences to check in playtest: a furniture far from its place has
at most 20 s before someone looks at it, so resting spots must be chosen
near the remembered pose or out of the creak radius; and a creak can be used
as a lure, since it pulls every head toward one known point.

### 4.7 Light `[M4]`

`ViewRange` is scaled by the light level at the furniture. A lamp furniture
can switch itself off.

M4 (v1.6): only the lamp's own light matters. While it is off, every
inhabitant's range for the lamp's sample points is 0.4 x 10 = 4 m, and the
floor cone shows that shorter range, dimmed. The room light is visual only.

---

### 4.8 The robot vacuum `[M5]`

A robot vacuum follows a fixed loop of waypoints at 0.4 m/s. It sees nothing and the household
ignores it.
- **It pushes the furniture it touches:** a 0.25 m shove along its heading over 0.5 s.
  - Being pushed is moving: seen during the shove, the furniture is caught.
  - The shove can also leave it out of place.
  - The robot then turns back along its loop.
- **Its hum masks small noises:** within 2.5 m of the robot, hops, rolls and clicks make no noise
  event. Topples, creaks and crashes are still heard. The robot is a useful cover as much as a
  moving threat.

## 5. The inhabitant

### 5.1 Routine `[M1]`

The inhabitant follows a looping list of **stations**. A station is a
position, a facing direction, a dwell time and a list of head glances.

Station cycle:

1. walk to the station position in a straight line (1.2 m/s);
2. telegraph, then turn the body to the station facing (180 deg/s);
3. dwell; during the dwell, play the glances in order. A glance is
   `(time offset, head yaw relative to body, hold duration)`; each one is
   telegraphed;
4. telegraph, turn toward the next station, go to 1.

In M1 paths are straight segments authored to be free of obstacles (checked
by the level audit, section 10.3). Navmesh pathfinding arrives in M2, when
the inhabitant needs to reach arbitrary points.

Head yaw relative to the body is limited to plus or minus 80 deg, at
200 deg/s.

M1 note (v1.2): when the glances of a station need more time than its dwell
(station 2 of level 1: a 0.8 s hold and two 0.6 s telegraphs in a 3.0 s
dwell), the dwell is extended until the head is back to center. A glance is
never cut short. Each routine action ends on a fixed step boundary. The
telegraph of steps 2 and 4 and of each glance applies to turns above 30 deg
(section 4.3); smaller turns start without it (in level 1: the 18 deg turns
leaving station 2 and arriving at station 3). An alternative for the product
owner: end the glance telegraph at its time offset instead of starting it
there, which makes station 2 fit in its 3.0 s.

### 5.2 States

| State | Milestone | Behavior |
|---|---|---|
| Routine | M1 | station cycle above |
| Startled | M1 | caught the player: stop, face the furniture, end of level |
| Alerted | M2 | heard a noise: telegraph, look at the source for 2 s |
| Investigating | M2 | displaced furniture seen: walk to it |
| Replacing | M2 | carry the furniture back to its remembered pose |
| Sitting | M4 | sits on a chair or sofa, the player included (pinned while sat on) |

### 5.3 Several inhabitants `[M5]`

Two or more inhabitants with crossed routines, plus a pet that sees low and
ignores displacement.

v1.7: up to 3 humans per level, plus at most one dog (eye at 0.35 m, sees moving furniture and
barks, a 6 m noise that turns the humans' heads, but never catches by itself).

### 5.4 Personalities and patterns `[M5]`

Every human has a **personality** (data, not code), shown on the level's intro card with one
line about its habit. The rules of fairness are the same for all: every turn of more than 30 deg
is telegraphed for 0.6 s, and the caught grace is 0.2 s.

| Personality | Shown as | Walk | Sight | Habit |
|---|---|---|---|---|
| default | (levels 1 to 7) | 1.2 m/s | 10 m, 55 deg | as M1 to M4 |
| dreamer | Le rêveur | 0.9 m/s | 8 m, 45 deg | long dwells, rare glances; suspicion grows slower |
| watchful | La méfiante | 1.2 m/s | 10 m, 60 deg | frequent glances behind; suspicion grows faster; notices 0.5 m |
| hurried | Le pressé | 1.7 m/s | 10 m, 50 deg | short dwells; hears little |
| granny | Mamie | 0.8 m/s | 7 m, 55 deg | sits often; hears little |
| teen | L'ado | 1.1 m/s | 6 m, 35 deg | eyes on the phone: a short, narrow cone; hears almost nothing |
| tidy | La maniaque | 1.2 m/s | 10 m, 55 deg | notices 0.4 m out of place; carries back faster |

A routine has a **pattern**: `loop` (the station cycle of M1), `pingpong` (there and back) or
`wander` (the next station drawn by a seeded generator: deterministic, so the audit sees it).

---

## 6. Levels

### 6.1 Level definition

A level is data (`LevelDef`), not a hand built scene: room rectangles, static
props, furniture spawn, exit zone, inhabitants and their stations. The scene
is built from it at load time by `LevelBuilder`. Levels live in
`Assets/Resources/Levels/*.json`, loaded with Newtonsoft.

### 6.2 Win and lose

- **Win**: the furniture center enters the exit zone. Being seen at that
  moment does not matter in M1 (from M2, the exit only counts while unseen).
- **Lose**: caught (section 4.2), or suspicion 1 from M2.
- Restart is instant (no loading screen): the level is torn down and rebuilt.

### 6.3 Level 1, "Le salon" `[M1]`

One rectangular room, 8 m along x by 6 m along z, floor at y = 0, origin at
the room center. Walls 2.7 m high, 0.1 m thick, no ceiling.

| Element | Position (x, z) | Size (x, y, z) | Notes |
|---|---|---|---|
| Chair (player) spawn | (-3.2, -2.2) | 0.45, 0.90, 0.45 | facing +z |
| Exit zone (doormat) | (3.5, 2.3) | 0.9, -, 0.9 | door gap in the +x wall |
| Sofa | (-0.75, -0.05) | 2.0, 0.85, 0.9 | occluder up to 0.85 m only (v1.2, was (0.0, 0.3)) |
| Bookshelf | (-1.5, 2.8) | 1.6, 2.0, 0.35 | against the +z wall, full occluder |
| Dining table | (2.45, -1.9) | 1.4, 0.75, 0.9 | occluder up to 0.75 m only (v1.2, was (2.2, -1.6)) |
| Window | (0.0, -3.0) | - | on the -z wall, decorative |

Note that the sofa and the table are lower than the chair (0.90 m): they hide
only part of it, so a top corner sample can still be seen from across the
room. That is intended. The first lesson of level 1 is that hiding behind
furniture is weaker than being behind a back.

Inhabitant stations (looping):

| # | Position (x, z) | Faces | Dwell | Glances (offset, yaw, hold) |
|---|---|---|---|---|
| 1 | (-1.5, 2.2) | +z (bookshelf) | 6.0 s | (3.0, -70, 1.0) |
| 2 | (1.2, 1.4) | -z (room) | 3.0 s | (1.0, +60, 0.8) |
| 3 | (0.0, -2.3) | -z (window) | 5.0 s | none |
| 4 | (2.2, -0.7) | -z (table) | 4.0 s | (2.0, -80, 1.0) |

M1 note (v1.2): with the sofa at (0.0, 0.3) and the table at (2.2, -1.6),
the level audit (10.3) found that three of the four straight walks cross a
prop: 2 to 3 and 4 to 1 go through the sofa, 3 to 4 clips a corner of the
table. The stations were kept (they carry the design intent and the timing
of the routine) and the two props were moved by the smallest amount that
keeps every walk line at least 0.3 m from the props (about 0.05 to 0.07 m
beyond the 0.25 m inhabitant capsule): sofa by 0.83 m, table by 0.39 m. To be
confirmed by the product owner (open question 7).

M1 note (v1.2): no prop lower than the chair can hide it. The top corner
samples sit at 0.87 m and a line from a 1.6 m eye down to them never drops
below 0.87 m, so the sofa (0.85 m) and the table (0.75 m) never block a top
corner. "Hiding only part of it" means hiding nothing in practice: only the
bookshelf and the walls are cover in level 1 (see open question 8).

Design intent: stations 1 and 3 are long, safe windows with one scare each;
station 2 sweeps the whole room and forces a full stop; the walks between
stations sweep diagonally. A first time player should finish in 60 to 120 s;
the designer route is under 40 s.

---

## 7. Assets

### 7.1 Decision

**No modelling tool is installed. Nothing binary is authored by hand.**

- **M1 and M2: procedural primitives built in C#.** Every object is a
  composition of boxes, cylinders and capsules generated at load time by
  `PrimitiveKit`. A chair is 6 boxes (72 triangles). The inhabitant is a
  capsule body, a sphere head, a box nose that shows where the head points,
  and two sphere eyes. This costs zero install, zero import pipeline, zero
  licence check, and lets M1 focus entirely on whether the game is fun.
- **M3: free CC0 low poly packs, imported as FBX.** Unity imports FBX
  natively, so no extra package and no converter.
  - Furniture and rooms: Kenney "Furniture Kit" (CC0, about 140 models, a few
    hundred triangles each).
  - Inhabitants: a Quaternius rigged humanoid with Idle and Walk clips at
    minimum (see the poly.pizza route already used for CALL OF WAR). The
    licence is checked per model, not per author: some Quaternius models are
    CC-BY.
  - If a wanted model only exists as GLB, add the UPM package
    `com.unity.cloud.gltfast` rather than converting by hand.
- **Fallback only if a pack cannot cover a need: Blender, driven headless.**
  Installed with `winget install BlenderFoundation.Blender`, used only as
  `blender --background --python script.py` to generate or convert a mesh, so
  the result stays reproducible from a script. It is not needed for M1 to M3
  and must not be installed before a concrete need is written in this PRD.

Rejected: MagicaVoxel (voxel look fights the furniture silhouettes and
produces heavy meshes without a cleanup pass), AI mesh generators (uneven
topology, unclear licences), ProBuilder (hand authoring inside the editor,
not scriptable by agents).

### 7.2 Art direction

Flat colors, no textures in M1 and M2. One URP Lit material per color, a warm
directional light through the window, soft shadows. v1.7 (M4.2, the product
owner's request): soft stylized textures, grayscale detail multiplied by the
palette color (wood grain, parquet, plaster, upholstery, linen, carpet; CC0,
ambientCG), set per renderer, so the materials stay one per color and every
palette color is kept within 1/255 on average. Palette: warm wood floor,
off white walls, saturated furniture; the player furniture has a color no
other object uses (M1: red chair) so it is found instantly in any frame.

### 7.3 Audio

M1: three generated sounds (hop tick, "hm ?" telegraph blip, caught sting),
synthesized at startup into `AudioClip` buffers, no audio file. M3 brings CC0
recordings (wood scrape, footsteps, room tone).

### 7.4 Budgets (mobile targets, enforced from M1)

| Item | Budget |
|---|---|
| Piece of furniture | at most 400 triangles |
| Inhabitant | at most 3 000 triangles, at most 40 bones |
| Whole level on screen | at most 60 000 triangles |
| Materials per level | at most 24, GPU instancing on |
| Draw calls | at most 120 |
| Real time lights | 1 directional with shadows, others unshadowed |
| Build size (Windows, M1) | at most 120 MB |

v1.7: a house of 5 rooms or more (levels 8 to 17) may use **160 draw calls and 32 materials**.
The built player must hold 60 fps on the development PC on every level. The Android
measurement stays in M7.

---

## 8. Unity architecture

### 8.1 Project

- Location: `Brainstorming/games/OutOfSight` (Unity project at the root, this PRD
  in `docs/`).
- Unity 6.3 LTS (`6000.3.23f1` as installed on 2026-09-03 in
  `C:\Dev\Unity\Editors`; confirm the installed version before bootstrapping).
- Template `com.unity.template.urp-blank`. It already ships URP, Input System
  and Test Framework: read `Packages/manifest.json` before adding anything.
- Extra packages: `com.unity.nuget.newtonsoft-json` (M1),
  `com.unity.ai.navigation` (M2).
- Driven by the `unity` CLI, as for `games/viewpoint_unity`.

### 8.2 Assemblies

| Assembly | Content | References |
|---|---|---|
| `OutOfSight.Core` | pure logic, no `UnityEngine` scene access: `VisionMath`, `MotionRule`, `CaughtRule`, `LevelDef`, `LevelValidator` | UnityEngine (math types only), Newtonsoft |
| `OutOfSight.Runtime` | MonoBehaviours | Core, Input System, URP |
| `OutOfSight.Editor` | `Builder` (player build entry point), menu tools | Runtime |
| `OutOfSight.Tests.EditMode` | unit tests of Core | Core |
| `OutOfSight.Tests.PlayMode` | probe (section 10.2) | Core, Runtime |

Any assembly that sets `overrideReferences` must list `Newtonsoft.Json.dll`
in `precompiledReferences`.

### 8.3 Runtime modules `[M1]`

| Class | Responsibility |
|---|---|
| `Main` | entry point on the single scene `Boot.unity`; builds every subsystem, each step in its own try/catch that logs |
| `LevelLoader` | reads a `LevelDef` from Resources, validates it |
| `LevelBuilder` | builds and tears down the level objects from a `LevelDef` |
| `PrimitiveKit` | boxes, cylinders, capsules, fan mesh; shared material cache by color |
| `FurnitureController` | input to movement, exposes `IsMoving` and sample points |
| `OrbitCamera` | section 3.1 |
| `Inhabitant` | station state machine, head and body yaw, telegraph |
| `Vision` | per inhabitant, per fixed step: sample raycasts, exposes `SeesPlayer` |
| `VisionConeView` | floor fan mesh |
| `GameState` | Playing, Caught, Won; owns `CaughtRule`; restart |
| `Hud` | eye indicator, red pulse, fail and win panels |
| `Sfx` | generated clips |
| `Probe` | runtime probe and screenshot mode (section 10.4), in the Runtime assembly so a built player can run it |

Layers: `Occluder` (walls and props that block sight), `Player`, `Inhabitant`,
`Floor`. Vision raycasts use the `Occluder` mask only.

### 8.4 Known Unity pitfalls to design around

These were paid for on `viewpoint_unity` and are requirements here:

- Materials created at runtime with `Shader.Find` are stripped from a build.
  The URP Lit and Unlit shaders are added to **Always Included Shaders**.
- No TextMeshPro. Text is uGUI `Text` with the built in `LegacyRuntime.ttf`.
- UI input uses `InputSystemUIInputModule`, never `StandaloneInputModule`.
- An exception in `Awake` cancels the rest of `Awake`: every build step in
  `Main` is isolated.
- Hide the HUD by disabling its `Canvas`, never its GameObject.
- Level teardown uses `DestroyImmediate` on level objects, then clears every
  registry, before the rebuild.
- Tonemapping Neutral, not ACES (ACES washes out a flat color palette).
- Shadow settings are read from the URP asset, not `QualitySettings`.

---

## 9. Strings (French, verbatim)

| Key | Text |
|---|---|
| title | Out of Sight |
| level1.name | Le salon |
| level1.hint | Ne bouge que lorsque personne ne regarde. |
| hud.controls | ZQSD : avancer    Souris : caméra    R : recommencer    Échap : pause (v1.5: pause added in M3) |
| fail.title | VU ! |
| fail.body | Un meuble ne bouge pas tout seul. (v1.6: body neutral since M4; was "Une chaise ne bouge pas toute seule.") |
| fail.action | Appuie sur R pour recommencer |
| win.title | DEHORS ! |
| win.body | Temps : {0} s |
| win.action | Appuie sur R pour rejouer |
| fail.suspicion.title | LOUCHE ! |
| fail.suspicion.body | Ce meuble se promène un peu trop. (v1.6: body neutral since M4) |
| win.next | Appuie sur Entrée pour le niveau suivant |
| level2.name | Le couloir |
| level2.hint | Sur un tapis, personne ne t'entend. |
| level3.name | La salle à manger |
| level3.hint | Une chaise parmi d'autres ne surprend personne. |

The last seven strings were added in v1.3 for M2.

Movement is bound by physical key position (the W, A, S, D positions), so the
French layout reads ZQSD without a separate binding.

---

## 10. Verification

A single script `verify.sh` runs all four stages and fails on the first red
one. It **refuses a run with zero tests** (an empty run exits 0 and looks
like a success) by reading the test count in the JUnit report.

### 10.1 EditMode unit tests (Core) `[M1]`

- `VisionMath.IsInCone`: point ahead in range; beyond range; exactly at the
  half angle (inside) and 1 deg past it (outside); behind; directly above.
- `MotionRule.IsMoving`: below and above each threshold; rotation only.
- `CaughtRule`: seen and moving for 0.18 s then hidden gives not caught and a
  reset timer; 0.20 s gives caught; seen and still for 10 s gives not caught;
  moving and unseen for 10 s gives not caught.
- `LevelValidator` on level 1: spawn, exit and stations inside the room; no
  station inside a prop; exit not overlapping a prop.
- Level JSON round trip.

### 10.2 PlayMode probe `[M1]`

Runs the real `Boot` scene. Every wait is a count of `WaitForFixedUpdate`,
never rendered frames.

| Step | Assertion |
|---|---|
| 01 boot | scene built, zero logged exception, player, inhabitant and HUD exist |
| 02 move unseen | inhabitant pinned facing away; chair driven 1 s; displacement between 1.3 and 1.6 m; state Playing |
| 03 still while seen | inhabitant pinned facing the chair; no input for 2 s; state Playing; eye indicator open |
| 04 caught | same pose; chair driven; state Caught within 0.20 to 0.30 s |
| 05 occluder | chair fully behind the bookshelf line; inhabitant facing it; chair driven; state Playing |
| 06 out of range or cone | inhabitant facing 90 deg away; chair driven; state Playing |
| 07 telegraph | over one full routine loop, every turn above 30 deg is preceded by at least 0.6 s of telegraph state |
| 08 win | chair teleported next to the exit, driven in; state Won |
| 09 restart | restart from Caught and from Won returns to spawn pose and Playing, and object counts equal those of step 01 |

**Mutation check, once, before trusting the probe:** invert the cone test and
confirm steps 03 to 06 turn red; remove the grace timer reset and confirm the
`CaughtRule` unit test turns red.

### 10.3 Level audit `[M1]`

For each level: every straight segment between consecutive stations is free
of props (capsule sweep); and a simulated full routine loop reports, for a
coarse grid of the room, the fraction of time each cell is unseen. The audit
fails if there is no path of cells from spawn to exit along which every cell
is unseen at least 25 % of the loop. This is the guard against an unwinnable
or all waiting level.

### 10.4 Built player check `[M1]`

A green editor test proves nothing about a build. The script builds a Windows
player, launches it with `--probe --shot <dir>`, and reads the JSON report
the player writes: shaders resolved, no renderer without material, font not
null, labels carry text, zero exception in `Player.log`, and two screenshots
whose mean luminance is neither near black nor near white. The screenshots
are then looked at by a person or an agent; no assertion replaces that.

---

## 11. Milestones

Each milestone ends with its gate green and a short playtest by the product
owner. The gate of a milestone includes every gate before it.

### M1 - "Une pièce, un perso, une chaise" (small)

Goal: answer one question, **is stopping in front of a turning head fun?**

Scope: sections 3, 4.1 to 4.3, 5.1, 6.3, 7.1 (primitives only), 8, 9, 10.

Acceptance:

- Level 1 playable from launch to win screen with keyboard and mouse.
- Caught rule, eye indicator, floor cone and telegraph behave as specified.
- `verify.sh` green: unit tests, 9 probe steps, level audit, built player
  check with screenshots reviewed.
- Mutation check done and noted in the README.
- Budgets of section 7.4 met (M1 should sit under 5 000 triangles).

Out of scope: menus, sound files, save, any second level, any suspicion.

### M2 - "Soupçon" (medium)

Goal: remove dead time and make failure funny.

- Displacement memory, suspicion meter, the inhabitant carries furniture back
  (4.4). Hearing and floor types (4.5). Navmesh pathfinding.
- Creak gauge (4.6): the furniture creaks after 20 s of stillness, with a
  3 s warning, and alerts every inhabitant in range.
- Exit only counts while unseen.
- Decoy furniture: other chairs that never move, so the player chair is one
  among several from the inhabitant's point of view.
- Levels 2 and 3 (two rooms, one doorway).
- Gate: probe steps for memory, carry back, noise lure; audit extended with
  "no cell requires waiting more than 8 s". Creak: unit tests of the gauge
  (fill, drain, reset, start delay, paused while carried) and three probe
  steps (still for 20 s creaks and alerts an inhabitant in range; an
  inhabitant out of range does not react; moving continuously for 60 s never
  creaks).

M2 notes (v1.4), as built (docs/CONTRACT_M2.md, amendment 11). The numbers of the latest green
run are in the README; the descriptions below are the design.

- **Level 1 under M2.**
  - The stations are unchanged.
  - Since M2.1 the inhabitant starts at station 3, looking out of the window, so the first move
    is possible at once. The PRD never fixed a start station. With station 1 as the start, the
    only clean schedule waited exactly 8 s at spawn, which is dead time (pillar 3).
  - The cost: the clean schedule now exits in about 11 s and never meets station 2, the full
    stop of the design intent. This is an A/B question for the playtest (open question 10).
- **Level 2, "Le couloir".** A 9 x 2 m corridor above a 5 x 4.4 m bedroom, where the chair
  starts. One doorway connects them.
  - The inhabitant starts at the bedroom door, then loops over the mirror (back turned, a glance
    toward the exit), the front door, and a check through the bedroom doorway.
  - A blue runner rug passes close behind the mirror station, so the chair can pass within
    earshot in silence.
- **Level 3, "La salle a manger".** A dining room and a kitchen.
  - Four decoy chairs stand around the dining table on a rug, a fifth beside the doorway and a
    sixth at the kitchen table. Each has a free spot within 0.75 m where the player chair is
    explained.
  - The chair starts at the head of the table, and the inhabitant at the kitchen sink.
  - The audit finds no schedule with decoys switched off: the decoys are required.
- **Designer routes.** Each level's `designerRoute` is the M2-aware audit's schedule, and probe
  step 20 replays it under the M2 rules. Each must win with 0 discoveries, 0 alerts and no creak,
  at time offsets of -0.2, 0 and +0.2 s. This proves the audit model matches the game, not that
  the timing suits a human: that is the playtest's job.
- **The audit** checks:
  - NavMesh paths for every station walk;
  - one grid per room, linked through the doorways;
  - a time-expanded search for a clean schedule from spawn to exit:
    - never seen while moving, never seen out of place for the grace;
    - with memory, decoys, the hop radius and the creak gauge;
    - **never waiting more than 8 s in one place, including at spawn**.

  It prints the schedule's time, longest wait and slack.
- **NavMesh:** runtime build with the voxel size at 0.05 m. The default size bends the level 1
  walks, which clear the props by only 0.05 m beyond the agent radius.

### M3 - "De vrais meubles" (medium)

Goal: the game looks like a game.

- Kenney furniture and a rigged, animated inhabitant replace the primitives
  (7.1), behind the same `LevelDef` (a prop gains a `model` field; primitives
  stay as fallback).
- Lighting and post processing pass, recorded audio, title screen, pause.
- Gate: budgets of 7.4 measured in the built player; licence file listing
  every imported model with its source and licence.

M3 notes (v1.5), as built (docs/CONTRACT_M3.md v2, then the M3.1 fixes):

- **Models are visuals only.**
  - Every element keeps its procedural colliders. Its procedural parts become collider-only, and
    probe step 23 proves the collider set is identical with and without models.
  - The tall bookshelf, the tables and the doors stay procedural.
  - A missing model or rig falls back to the procedural visual, and the built player fails on
    any fallback.
- **Every inhabitant of levels 1 to 3 is the Quaternius man.**
  - His eyes sit at 1.6 m, the vision eye, and his head bone follows the routine's eye yaw within
    5 deg.
  - The woman fits level 3's budget (21 materials) and is kept for M5.
- **Readability behind walls (pillar 2).**
  - A hidden inhabitant is drawn as a flat silhouette.
  - Its cone shows deep blue through occluders.
  - A gaze arrowhead (yellow when calm, red when it sees the chair) and the "?" and "!" markers
    draw over everything.
  - The HUD (eye and gauges) sits in a bottom band, so heads are never hidden.
  - Every wall cap fades with its wall plane.
- **Menus.**
  - The title shows only in a built player.
  - Escape and gamepad Start pause, and a pause stops every fixed step rule.
  - Restart is R or gamepad Y.
  - The end screen comes after the last level.
  - hud.controls gains "Échap : pause".
- **Audio.** 21 CC0 recordings, levelled to a common target with no clamped volume. "hm ?" and
  the tension stay synthesized, and "hein ?" too by default.
- **Open questions for the playtest:**
  - the x-ray cone tints low props strongly blue;
  - the recorded "hein ?";
  - the frozen man on the title screen.

### M4 - "Le mobilier" (medium)

Goal: depth through different bodies.

| Furniture | Rule |
|---|---|
| Chair | reference |
| Stool | fast, small, tips over and makes noise if it stops too hard |
| Armchair | slow; tall enough to block sight for anything behind it |
| Floor lamp | very slow; can switch off, cutting view range in its room (4.7) |
| Office chair | fastest; rolls with inertia, so stopping takes 0.4 s |
| Wardrobe | slowest; full occluder; a smaller furniture can hide inside |

- Inhabitants can sit on seats, the player included (5.2).
- Levels 4 to 7, each built around one furniture.
- Gate: one probe step per furniture rule.

M4 notes (v1.6), as built (docs/CONTRACT_M4.md v2 with its section 9 amendments and the M4.1
fix wave of its section 10):

- **Bodies** (`BodyDef`, the one size source):
  - **chair:** the reference, equal to the M1 constants field by field (a reflection test checks
    every field, and a mutation that speeds the chair up turns M1 probe step 02 red);
  - **stool:** 2.4 m/s in two stages, small enough to hide behind a sofa or a clothed table;
  - **armchair:** 0.9 m/s; its lesson is being sat on;
  - **floor lamp:** 0.6 m/s;
  - **office chair:** 2.8 m/s, with a procedural visual (the model is over the triangle budget).
- **The wardrobe body is dropped** (open question 12). Its hiding prop moves to a later
  milestone.
- **Careful mode** (every body, open question 11): holding Left Shift (gamepad left trigger)
  halves the max speed. It is not silent; rugs keep their M2 meaning.
- **The stool tips** when the input is released above 1.3 m/s, or when a wall stops a head-on
  hit above 1.3 m/s.
  - It falls for 0.3 s (15 steps), which counts as moving, and makes a topple noise of 3.5 m.
  - Only a head-on hit counts: within 30 deg of the wall normal. A graze along a wall at full
    speed does not tip it.
  - It lies on its side until a fresh move press, then rights itself in 0.4 s (20 steps), also
    moving. A key held through the fall does not right it. While it lies, the HUD says
    "Renversé : appuie sur une direction pour te relever.", the ghost and the decoy rings are
    hidden, and its sight samples use its lying box.
  - **The warning band (M4.1):** the fast stage ends at 1.0 m/s, and the stool climbs from 1.0 to
    1.3 m/s in 0.25 s. The tell (it leans back and rattles) starts at 1.0 and is full at 1.3, so
    the danger is always announced. A short tap never tips it. Careful mode caps it at 1.2 m/s,
    shows no tell, and never tips it.
  - Seen lying down, it is out of place wherever it stands (open question 15).
- **The office chair** glides to a stop in exactly 0.4 s after release. Opposite input brakes no
  faster. A ring shows the predicted stop point. Rolling makes a 1.2 m noise every 0.3 s, silent
  on rugs and soft floors.
- **The floor lamp:** E (gamepad X) toggles it, a 0.3 s action (15 steps, M4.1), with a click
  noise of 2.5 m. **During the toggle the rules use the lit range**, whatever the direction, so a
  toggle seen for its whole duration is always caught (the hint says to switch off unseen).
  - An inhabitant in Routine who sees it off comes and switches it on (open question 13).
  - It does so only if the lamp stands where it belongs. Otherwise the usual discovery and
    carry come first.
  - One inhabitant at a time. The switch-on makes a click sound but no noise event.
- **Noises on rugs (M4.1):** every furniture noise (hop, topple, click, roll) is silent on a rug
  or a soft floor, as the level 2 hint promises. The player still hears a muffled topple.
- **Input:** E and the move presses that right a stool are latched each frame and consumed in
  the fixed step. They are ignored while an action is in progress.
- **Sitting** (5.2):
  - A station may name a seat: a prop, or "player" with an authored seat home. The station spot
    is the seat front where the inhabitant stands, and its facing is the seated facing, so the
    arrival turn is the back turn (telegraphed).
  - The eye lowers from 1.6 to 1.15 m over 0.5 s. The dwell and the glances count from the end of
    the sit-down. Every stand-up is telegraphed, and Investigate, the switch-on and the carry
    stand up first.
  - **The sit-down slides (M4.1):** from the moment of sitting, the inhabitant's position and eye
    slide from the station spot to the seat home over 0.5 s (and back when standing). No step
    jumps, so the cone never moves without a visible motion.
  - **On the player:** the check happens at the moment of sitting, after the back turn. A seat
    body within 0.75 m of the seat home is sat on.
    - The furniture snaps to the seat home (its visual slides there over 0.3 s).
    - It is pinned: no input, not moving, not caught, the creak gauge paused.
    - Every inhabitant's remembered pose becomes the seat home.
    - On release, input needs a neutral step first.
    - The HUD shows "Quelqu'un est assis sur toi.", and an amber ghost and ring (not the cyan
      memory ghost) show the seat home from the start of the sitter's walk.
  - **On nothing** (the seat is not home): a pratfall (open question 14).
    - It counts as one discovery.
    - Then comes a telegraphed stand-up, and a 2 s Alerted look at the seat, before the routine
      resumes.
    - It plays its own sound, not the "hein ?".
  - Rules gating: `Bodies` gates the tip, the glide and careful mode; `Lamp` the light and the
    switch-on; `Sitting` the sit stations (a plain dwell when off). Body constants always apply.
  - **Sitting on a prop:** the seat home is the prop's center, facing the station's facing. The
    validator checks the seat-front geometry (the station 0.3 to 0.8 m in front of the seat
    along its yaw, facing the seat's yaw).
- **Levels 4 to 7**, one body each:

  | Level | Body | Audited exit | Longest wait | Lesson-required check | Slack (samples) |
  |---|---|---|---|---|---|
  | 4 "Le tabouret" | stool | 14.9 s | 4.2 s | at full speed every stop tips: no schedule | 8 |
  | 5 "Le fauteuil" | armchair | 16.1 s | 6.5 s (1.7 s sat on) | first sit at 8.5 s, earliest exit without sitting 13.7 s: the sit cannot be skipped | 10 |
  | 6 "La lampe" | floor lamp | 15.9 s | 2.4 s | the lamp always lit: no schedule; the inhabitant passes 1.3 m from the lamp's path | 15 or more |
  | 7 "Le bureau" | office chair | 20.3 s | 7.8 s | the schedule that ignores the glide is seen gliding at 12.8 s | 10 |

  Slack is the largest margin each way (in 0.1 s samples) for which a schedule still exists; the
  audit requires 3. Level 4's living room became a hard floor in M4.1: a silent topple on a rug
  would have let the full-speed stool through.

- **The audit is body aware:**
  - move samples, ring radius and noise radius per body;
  - a door clearance check per body;
  - the stool is searched at careful speed only;
  - every office chair stop costs 4 unseen samples;
  - the lamp is a state bit, and its toggle costs samples plus its click radius;
  - a sit on the player is forced presence at the seat home **from the moment of sitting** to the
    end of the pin (M4.1: the game's rule; the approach is free), which counts against the 8 s
    wait cap;
  - a dark or moving lamp must stay unseen; a lit, still lamp may be seen;
  - a toggle is checked at the lit range.
- **Lesson knob and fixtures.** Each level has a `lesson`: `careful`, `sit`, `dark` or `glide`.
  The fixtures `test_tip`, `test_dark` and `test_sit` (independent minimal levels since M4.1)
  must have no schedule when strict and get one when relaxed. A rush counter-route on level 5
  (straight to the exit) is caught at 1.4 s (probe step 35b).
- **Playtest data:**
  - The slack column above: every level has at least 0.8 s of margin each way for some
    schedule; the designer routes use the audit's 0.3 s.
  - Start-delay warnings remain on levels 5 and 7, as in M2: a player who starts late waits for
    the next loop, at home, harmlessly.

### M5 - "La maison" (large), rewritten in v1.7

Goal: a complete small game where mechanics combine. The product owner's M4 playtest replaced the
first M5 plan (3 levels: doors, dog, house); those mechanics are kept, as mechanics to combine
among others.

- **10 new levels, 8 to 17**, 17 in total. Each one combines two or three mechanics in a
  **larger, maze-like house**: 4 to 8 rooms, corridors, loops and dead ends.
- **Several inhabitants with personalities and patterns** (5.3, 5.4): up to 3 humans and a dog.
- **New mechanics:**
  - the **robot vacuum** (4.8);
  - the **rocking chair**, a new body that keeps rocking for 0.8 s after every stop (0.4 s in
    careful mode); the rocking counts as moving;
  - the **load and balance** (3.4).
- **Mechanics of the first M5 plan, kept:**
  - doors that the player opens only unseen: E, a 0.6 s action that counts as moving;
  - the dog;
  - one split level with a ramp per house where a level wants it.
- **Combinations**, for example:
  - wheels and balance: the office chair carrying a vase;
  - the stool and a load;
  - the robot and the stool;
  - the lamp, the dog and doors at night;
  - a final house with everything.
- **Level select, best times, save file.**
- Gate:
  - every level passes the audit, with a lesson-required check per mechanic;
  - a full playthrough of the 17 levels by the probe on the designer routes;
  - one probe step per new rule.

M5 wave 5A notes (v1.8), as built (docs/CONTRACT_M5.md v4 with its v5 and 5A.1 amendments,
sections 16 and 17):

- **Levels 8, 12, 14 and 16** ship in an 11-level play order (1 to 7, then 8, 12, 14, 16). The ids
  keep their final numbers; the order becomes 1 to 17 with wave 5B.

  | Level | Body | Rooms | People | Lesson |
  |---|---|---|---|---|
  | 8 "Les portes" | chair | 4 | the dreamer | door: two closed leaves |
  | 12 "Le chien" | stool | 5 | the dreamer and the dog | pet: two low sofas hide the stool from the dog |
  | 14 "La mezzanine" | armchair | 6 | Mamie (sits on the player) and the tidy one | split: a platform and a ramp |
  | 16 "La nuit" | floor lamp | 4 | the watchful and the hurried, the dog | dark: the lamp, one closed leaf |

- **Doors.**
  - E (gamepad X) opens the nearest closed leaf in reach: 0.85 m from the door centre, footprint
    outside the swing quarter disc. The furniture must be still, upright, not pinned or carried, and
    in no action.
  - The opening lasts 0.6 s (30 steps) and counts as moving.
  - The leaf is sampled on all 30 steps: a leaf seen swinging is a catch after the grace. PRD 4.1:
    9 rays during a swing.
  - The open leaf keeps its collider and occludes, against the wall. It fades when it stands
    between the camera and the furniture.
  - E near a closed leaf never switches the lamp, even when the opening is refused.
  - Inhabitants never open doors.
  - Station walks are planned once with the authored doors. Investigations plan with the doors
    open now, on one NavMesh where each doorway is its own area.
- **The dog.**
  - Eye at 0.35 m, sees 6 m wide (70 deg).
  - Seen moving by the awake dog for 0.2 s: a bark at the dog (6 m, turns the heads like a creak),
    then 3 s of cooldown. The bark is heard only through each human's hearing factor.
  - The dog never catches, has no memory, hears nothing and never opens doors.
  - **The hold** (2026-11-19, the product owner: "the dog does nothing when it detects you"; docs/CONTRACT_M5.md
    20): after its bark the dog runs to the furniture (2.6 m/s, a "!" over it), pins it next to itself as a
    sitter does (HUD line "Le chien te bloque : on vient te remettre en place."), and barks at it in a loop.
    The nearest free human is sent ("!") and, as always, finds it out of place (one discovery, then the carry
    back to its spot) or in place (nothing). On the put down the dog lets go and both return to their
    routines. A setback, never a catch: the dog costs the ground gained and one discovery, never the level
    by itself.
  - It sleeps at sleep stations (eye closed, a "z" mark, cone hidden). It wakes with a 0.6 s
    telegraph, eye still closed.
  - Its cone is cyan. The HUD eye has a dog shape when only the dog sees the furniture.
- **Personalities and patterns** as in 5.4, with:
  - six distinct Quaternius models and clothes tints;
  - a shared palette (8 colours plus one tint per personality);
  - the intro card naming the people with one line each.
  - Wander draws are indexed by visit; interruptions never draw again.
  - A taken seat is a standing dwell.
- **The split level.**
  - Platforms and ramps are solid; railings stand on every free edge.
  - The furniture visual follows the ramp slope, while the rules box stays upright.
  - Eyes, samples and cells add the floor height.
- **Save, level select, records.**
  - Save: `outofsight_save.json` in the persistent folder, written atomically with a .bak. A missing
    file is recovered from the .tmp, then the .bak. The editor, `--probe` and `--look` never touch
    it.
  - Level select: one card per level with its best time, levels unlocked in order. Play starts the
    first unwon level.
  - Records: "Record : x s" and "Nouveau record !".
- **Budgets** count draw calls as material slots: 120 (24 materials) below 5 rooms, 160 (32) from 5
  rooms.
- **Frame time.** The built player measures every level's start view: a median of 3.6 to 6.9 ms on
  the development PC (above 140 fps). The gate fails above 33 ms.
- **M4.2.**
  - Soft stylized textures: grayscale detail times the palette colour, six CC0 ambientCG textures,
    2 MB.
  - The feet fix: the idle clip did not animate the feet, so after a walk they stayed mid-stride;
    every clip now holds the bones it does not animate at rest.

### M6 - "Finition" (medium)

v1.9: M6 used to hold the mobile port too; the product owner moved that part to M7, so M6 is
PC only.

- Options (sensitivity, volume, cone display), gamepad pass, accessibility
  (the seen state is never conveyed by color alone).
- The gameplay items deferred to M6 by the open questions: the wardrobe hiding
  prop (12, 22), door memory (19), inhabitants opening doors (23).
- **Texture pass 2** (v1.9, the product owner's request after M5), same rule as
  M4.2 (grayscale CC0 detail times the palette colour, licence in
  docs/LICENSES.md):
  - The garden: a grass detail on the green ground around the house.
  - The player furniture: a reflective finish, glossy plastic or lacquered
    metal, with a detail clearly visible at play distance. It keeps its own
    colour (7.2: found instantly in any frame). See open question 28.
  - The surfaces still plain: metal parts (office chair frame, lamp pole and
    base, robot vacuum body), plastic (the robot's bumper), leaves and soil,
    the window pane (a light glass sheen), and any new surface M6 adds (the
    wardrobe).
  - Budgets: a finish may add materials (smoothness and metallic are per
    material); the 7.4 caps (24 and 32 materials) still hold, checked by the
    built player check.
- Gate: 60 fps on PC, built player check on PC.

### M6b - "Finition, niveaux" (small)

v1.10: the product owner split M6 on 2026-11-15, once texture pass 2 had landed: M6 keeps the
code above (options, gamepad, accessibility, texture pass 2, the wardrobe, door memory, inhabitants
opening doors, their audit support), and M6b takes the level work and the M6 gate.

- Level 18 "L'armoire": the wardrobe, a door opened by an inhabitant and door memory in one small
  house (docs/CONTRACT_M6.md 5).
- Levels 10, 13 and 17 pass the audit wait rule of M5 wave 5B.1 (and level 10 its rock lesson),
  with their routes rewritten and their replays winning.
- The RouteReplayer plays the hide and leave route actions.
- The M6 gate: verify.sh green, the M6 mutation rows, the PRD and README notes.

**M6 and M6b notes (2026-11-16).** Gate green: 448 EditMode, 214 PlayMode, 18 levels audited without
defect, built player 101 MB. Level 18 "L'armoire" (wardrobe lesson, a door its inhabitant opens,
door memory on). Level 13 and 17 retimed (17: out of the bedroom early, exit about 21 s). Level 10's
rock lesson is advisory (CONTRACT_M6 5, `lessonAdvisory`): no data change made it bind under the 5B.1
wait rule; the level stays winnable. The wardrobe fits the stool and the floor lamp only (0.40 m,
1.85 m). The full mutation run was skipped for credits; every new marker's kill was checked once by
its agent. Ctrl+F and F11 toggle full screen.

### M7 - "Mobile" (medium)

- Android build through a `Builder` class and `--execute-method`, touch
  controls (virtual stick, drag to orbit), quality tiers on the existing
  `Mobile_RPAsset` and `PC_RPAsset`.
- The Android save: the delete-then-move fallback of docs/CONTRACT_M5_v3.md
  15.7, with the .bak rule left open there.
- The 7.4 budgets measured on Android, the house budgets of open question 27
  included.
- Gate: 30 fps on a mid range Android phone, built player check on Android,
  and every M6 gate still green on PC.

---

## 12. Risks and open questions

### 12.1 Risks

| Risk | Mitigation |
|---|---|
| Waiting is boring | M1 measures it (audit of unseen time); M2 adds lures and the creak gauge, which punishes long stillness; the audit caps forced waits |
| The creak feels like a random punishment | it only fills while still, it is announced 3 s ahead, and it is harmless to a furniture standing where it belongs |
| Getting caught feels unfair | telegraph on every turn, eye indicator, floor cone, 0.2 s grace |
| "Stand still anywhere" is too safe | accepted in M1, fixed by displacement memory in M2 |
| Content cost of houses | levels are data; props are a kit; one audit validates all |
| Editor green, build broken | built player check in the gate from M1 |

### 12.2 Open questions (default taken until decided)

1. **Tone**: comedy, the inhabitant is puzzled rather than scared.
   Default: comedy.
2. **Camera**: third person orbit with dollhouse walls. Default: as written.
3. **Mobile priority**: PC first, Android at M7. Default: as written.
4. **Game name**: "Out of Sight". Default: as written.
5. **Vision cone always visible**: default yes in M1, becomes an option in M6.
6. **Voluntary creak**: a key that creaks on demand (and resets the gauge),
   to use the creak as a deliberate lure. Default: not in M2, decided after
   the first M2 playtest.
7. **Level 1 props** (v1.2): sofa and table moved so that the authored walks
   are free of obstacles (section 6.3). Alternative: keep the props and give
   the walks intermediate waypoints. Default: props moved.
8. **Level 1 difficulty** (v1.2): a bot that stops whenever the eye opens
   wins in 15 s; a bot with a 0.24 s reaction time that reads only the
   telegraph and the floor cone wins in 17.5 s but is once seen moving for
   0.18 s of the 0.20 s grace. The level may be easier and less tense than
   the 60 to 120 s first run of section 6.3. Default: unchanged until the M1
   playtest; M2 displacement memory is the planned answer (risk table).
9. **Initial displacement memory** (v1.3): PRD 4.4 says "for each piece of
   furniture they have seen". Taken literally, the first sighting is free
   anywhere, which undoes the M2 answer to question 8. Default: the
   inhabitant knows from the start where its chair belongs (memory seeded
   at the spawn pose). Alternative: memory unset until the first sighting.
10. **Level 1 start station** (v1.4): station 3 (window, default since M2.1, no
    dead time, about 11 s clean exit) or station 1 (bookshelf, the M1 start, an
    8 s wait at spawn, then the full routine with the station 2 sweep). Default:
    station 3. To be decided with an A/B in the first M2 playtest.
11. **Careful mode** (v1.6): a new control, not in the PRD: Shift (gamepad left
    trigger) halves the max speed of every body, which is how the stool stays
    under its tip speed. Default: in.
12. **The wardrobe** (v1.6): dropped as an M4 body (being the slowest and a full
    occluder gave it no lesson of its own). The hiding prop (a smaller
    furniture hides inside) is deferred, first to M5, then to M6. Default:
    deferred.
13. **Lamp switched back on** (v1.6): an inhabitant who sees the lamp off comes
    and switches it on; this is the lamp's carry back, a discovery only if the
    lamp is also out of place. Default: as written.
14. **Pulling the chair away during the back turn** (v1.6): the sit check happens
    at the moment of sitting, so the classic gag gives a pratfall (one
    discovery). Default: as written.
15. **A tipped stool is out of place anywhere** (v1.6): seen lying down, even on
    its own spot, it is a Suspect, then a Discovery after the grace. Default: as
    written.
16. **Pet bones** (v1.7): the dog model may use 46 bones; humans stay at 40.
    Default: accepted.
17. **Door key** (v1.7): E (gamepad X), as the lamp. Default: E.
18. **Seen opening a door** (v1.7): a normal catch after the grace, no mercy rule.
    Default: catch.
19. **Door memory** (v1.7): an inhabitant noticing a door it remembers closed.
    Default: deferred to M6.
20. **The bark** (v1.7): at the dog, 6 m, like a creak, 3 s cooldown. Default: as
    written. Decided 2026-11-19: the bark is followed by the dog's hold (M5 notes, The dog).
21. **Stacked floors** (v1.7): not in M5, one split level per house at most.
    Default: deferred.
22. **The wardrobe hiding prop** (v1.7): deferred to M6.
23. **Inhabitants opening doors** (v1.7): deferred to M6.
24. **Personalities** (v1.7): the six of 5.4 and their numbers. Default: as
    written, tuned after the M5 playtest.
25. **A fallen load** (v1.7): crash noise and a clue that costs one discovery,
    not a lost level. Default: as written.
26. **The robot's shove** (v1.7): 0.25 m, then it turns back. Default: as
    written.
27. **House budgets** (v1.7): 160 draw calls and 32 materials for houses of 5
    rooms or more. Default: as written, measured on PC; Android in M7.
28. **The player furniture's finish** (v1.9): glossy plastic or lacquered metal.
    Default: glossy lacquer (strong highlights, the wood grain still visible
    under it), compared with brushed metal in screenshots at the M6 playtest.
