# STARTFIX progress (start a held level without moving)

## The bug (product owner, 2026-11-21)
In level2 (and level7), the red chair spawns inside the watcher's cone. The held start (C3a) was released only by a move
input or the action key (`InputReader.AnyStartInput`), so the only way to start was to move, and the chair was seen
moving on step 1. The rules allow being seen still: the player must be able to start the clock and wait.

Root cause: `AnyStartInput` had no "start without moving" input; the HUD line said "Bouge pour commencer".

## What changed (code)
- `Assets/Scripts/Runtime/InputReader.cs`: a start press. `LatchPresses` (every rendered frame, from
  FurnitureController.Update) latches Space, Enter, keypad Enter, gamepad A (south) and a touch tap
  (`PressTouchStart`). `AnyStartInput` now also returns true on a pending start press (`StartPressPending`,
  marker `// MUTATION:START_PRESS`). New: `InjectStartPress` (tests), `ConsumeStartPress`, `BlockStartPresses`,
  `PressTouchStart`. `DiscardGameplayPresses` (paused, menu closing frame) and `ResetInjections` clear it.
  `BlockStartPresses` also drops a device press of the current frame: the Enter or A that submitted Play, Resume,
  Next level or a level card never also starts the level, whatever the script order in that frame.
- Not start inputs (unchanged or by construction): Escape and gamepad Start (pause), R and gamepad Y (restart), gamepad
  B, the mouse (orbit, click, wheel), the right stick, the touch orbit drag, the careful key. There is no pinch gesture
  in TouchControls (the right half is a one finger orbit).
- `Assets/Scripts/Runtime/GameState.cs`: the held branch of `FixedUpdate` consumes the start press it read; a start
  press made while the level runs is consumed too (never kept for a later build). `BuildLevel` calls
  `BlockStartPresses` (first level, restart, next level). `// MUTATION:HOLD_START` kept.
- `Assets/Scripts/Runtime/TouchControls.cs`: a tap = a stick or orbit finger (so never a finger that landed on the action,
  careful or pause button) that lifts within 0.35 s having travelled at most 20 px of a 1080 px screen (under the stick
  dead zone, 0.2 x 120 px). It calls `InputReader.PressTouchStart`. A drag past that is never a tap. Marker
  `// MUTATION:TOUCH_TAP_START`.
- `Assets/Scripts/Core/Strings.cs` (hud.start keys reused):
  - keyboard: "Press Space to start (or move)" / "Appuie sur Espace pour commencer (ou bouge)"
  - gamepad: "Press A to start (or move)" / "Appuie sur A pour commencer (ou bouge)"
  - touch: "Tap the screen to start" / "Touche l'écran pour commencer"
- `Assets/Scripts/Runtime/Hud.cs`: `StartLineWidth` 980 -> 1120 (the French keyboard line is 43 characters at size 40).

### The press is never a game action
Space, Enter and A are no gameplay verb (the action is E / gamepad X): nothing but the start reads them in a level
(Tips.RawPress only reads after the start; NextLevelPressed only reads in the Won state). The start press is
consumed by the held step itself, so it never reaches a later step. E and X still start AND act on the same step, as
before (C3a behaviour, unchanged).

### The first steps after a start press are not movement (checked by reading)
The release step runs in full as step 1 (same schedule as RouteReplayer's ReleaseStart). With no wish,
`FurnitureController.Drive` sets `Velocity = 0` (PRD 3.2, no inertia; the office chair glide needs a speed above
`MovingSpeedThreshold`, it starts at 0), `Step` skips `controller.Move` when the velocity is zero (no depenetration
drift), so `EndStep` measures a zero planar speed and yaw rate: `IsMoving` false. `StepNoise` gets `FurnitureMoving`
false (no hop, no roll, no creak fill), `Rule.Step(seen, false)` never accumulates `SeenMoving`, the dog's bark rule
needs moving too. A stool cannot tip (it needs a speed above `StoolTipSpeed`).

## The audit (LevelAudit.cs, not changed): consistent with the new start
- The audit runs in batch mode, where `GameState.DefaultHoldStart` is false: its t = 0 is the build, with the chair at
  rest at the spawn and the routines running. A Space release gives exactly that: step 1 runs with the chair at rest.
  Before the fix, a human could only reach this timeline by moving on step 1, which the audit never does.
- The solver already models a spawn wait: `SpawnWaitEnd` / `SpawnWaitFailure` (RULEFIX, the samples before the first
  move, limited to `MaxSpawnWait` = 8 s, out of the loitering rule) and the start delay sweep (item 4 of its header).
  `KinematicReplay` and RouteReplayer drive a designerRoute "from spawn at rest", the first waypoint's "at" being the
  first departure (level2: 4.1 s, level7: 5.4 s).
- The static model below agrees: at the first departure of every designerRoute (and designerRouteHard), no human sees
  the spawn.

## Spawn against the watchers' cones (static, all 22 levels of levels.json)
Model: `scratchpad/startfix/spawncheck.py`, built on LEVELS6's `lv6/vis.py` (walls with door and window openings,
occluder props, platforms, ramps), with the game's own 5 spawn samples (VisionMath.SamplePoints, load +0.25 m), the
start station of each inhabitant (startStation, facing, eye 1.6 m, dog 0.35 m, seated 1.15 m, asleep sees nothing),
closed leaves blocking, ranges and half angles per personality and per difficulty (Facile x0.85 / -5 deg, Normal,
Difficile x1.15 / +5 deg), then each watcher's timeline (dwell with glances at 200 deg/s, walk along a grid path).

"t = 0" = the spawn is seen on the first step. "Seen still, first 12 s" = the windows (Normal; the other difficulties
differ by at most 0.2 s at the edges) when a human sees the spawn. "First move" = the audit route's first departure
(Normal / Difficile when it differs).

| Level | t = 0 Facile | t = 0 Normal | t = 0 Difficile | Seen still, first 12 s (N) | First move | Fair with the new start |
|---|---|---|---|---|---|---|
| level1 | no | no | no | 0.5-1.3 s Habitant (glance +80 deg at 0.3 s); again 7.1 and 11.1 s | 3.2 s | yes (see note 1) |
| level2 | **yes** Habitant | **yes** Habitant | **yes** Habitant | 0.0-0.7 s, 1.2-3.1 s Habitant (a 0.5 s glance away in between) | 4.1 s | yes: wait about 3 s |
| level3 | no | no | no | 7.8 s on | 3.5 s | yes |
| level4 | no | no | no | never | 3.2 s | yes |
| level5 | no | no | no | 5.1-6.3 s (walk to the armchair to sit) | 1.8 s | yes |
| level6 | no | no | no | never (in 12 s) | 3.4 / 5.2 s | yes |
| level7 | **yes** Habitant | **yes** Habitant | **yes** Habitant | 0.0-2.1 s Habitant (1.35 m, facing the chair); again 7.1 s | 5.4 s | yes: wait about 2 s |
| level8 | no | no | no | never | 6.0 s | yes |
| level9 | no | no | no | never | 3.4 s | yes |
| level12 | no | no | no | never (the dog Rex neither) | 4.7 s | yes |
| level11 | no | no | no | never | 0.3 s | yes |
| level15 | no | no | no | never (the dog Rex neither) | 1.8 / 2.2 s | yes |
| level13 | no | no | no | 4.1-4.4 s Claire | 6.4 / 0.3 s | yes |
| level14 | no | no | no | never | 6.8 s | yes |
| level18 | no | no | no | never | 5.6 s | yes |
| level17 | no | no | no | never (the dog Rex neither) | 0.3 s | yes |
| level19 | no | no | no | never | 2.1 / 1.6 s | yes |
| level21 | no | no | no | never | 0.3 s | yes |
| level20 | no | no | no | never (the dog Rex neither) | 0.3 / 0.6 s | yes |
| level22 | no | no | no | never | 3.2 s | yes |
| level25 | no | no | no | Facile never; N 11.0-11.6 s, D 10.2-11.6 s Marcel | 3.6 / 2.0 s | yes |
| level24 | no | no | no | never (the dog Rex neither) | 0.3 / 0.8 s | yes |

Count: the spawn is inside a cone at t = 0 in **2 levels out of 22** (level2, level7), at all three difficulties, a
human each time, never the dog. No watcher keeps the spawn in view for its whole cycle in any level, and no level
has a spawn seen at the audit's first departure.

### For the product owner (nothing looks unfair; levels not changed)
- level2 and level7: fair now. Press Space (A, a tap) and wait still: the watcher looks at the chair for about 3 s
  (level2) or 2 s (level7), then walks away; the audit's route leaves at 4.1 s and 5.4 s.
- Note 1, level1 (the first level): the spawn is NOT in the cone at t = 0, but the watcher's first glance (start
  station 2, +80 deg at 0.3 s) sweeps over it from about 0.5 s to 1.3 s. A player who starts by moving at once is in the
  open when the glance comes and is likely caught within the first 1.5 s; one who waits 1.5 s is fine (route: 3.2 s).
  Not a fairness defect, but a harsh first impression on the tutorial level; worth a look by the designer (a later
  glance offset, or a start prompt that says to wait), not changed here.
- level13 (being reworked by LEVELS6) and level25: the spawn is seen later (4.1 s, 10-11 s) while the routes have
  left already; not a start issue.

## Tests (static, NOT run; T1 owns the test files, minimal edits)
- `Assets/Tests/PlayMode/ProbeTestsHeldStart.cs` (edited, nothing removed): the class summary lists two new tests.
  - `HeldStart04_StartPressReleasesWithoutMovingUnderAWatcher` (level7, level2): a start press injected before the
    build is dropped by it (still held after 5 steps); then `InjectStartPress` starts the level on step 1, the press is
    consumed, and over 4 s: the watcher sees the chair (`Game.Seen` on at least one step, the premise), no step is
    moving, no action, no toggle, no drift or turn, no creak, `SeenMoving` 0, still Playing.
  - `HeldStart05_TouchTapStartsAndAnOrbitDragDoesNot` (level7, ForceTouchUI): a 200 px orbit drag on the right half
    leaves the level held; a tap in place starts it, the chair does not move.
- Existing tests left as they are: HeldStart01 (careful key and camera stick do not start, move and E do), ProbeTestsHudV2
  (compares the start line with `Strings.HudStart*`, so it follows the new text).
- Suggested run when the Unity lock is free: `test . --mode PlayMode --filter ProbeTestsHeldStart|ProbeTestsHudV2|ProbeTestsFocusPause`.

## Unity run
- 1 compile-only run asked (SetupAndCompile through tools/unity.ps1, Build/STARTFIX.log, 2026-11-21 01:14): NOT
  COMPILED. Unity aborted at startup, "It looks like another Unity instance is running with this project open"
  (exit 6 from the wrapper, 1 from Unity), before any script compilation. Not retried (one run allowed) and no Unity
  process killed. The edits were re-read by hand for compile errors (out variables and their scopes, local functions
  in the iterator tests, usings: System.Collections.Generic and UnityEngine are already imported), none found.
- To do when the project is free: `pwsh -NoProfile -File tools/unity.ps1 -Agent STARTFIX -UnityArgs "run . --timeout
  1800 -- -executeMethod OutOfSight.Editor.Builder.SetupAndCompile -logFile Build/STARTFIX.log"`, then the test filter
  above.

## A VERIFIER (manual)
- FIRST: the compile (not proven, see above), then ProbeTestsHeldStart (HeldStart04/05 new) and ProbeTestsHudV2.
- PC build, level2: on the intro card press Space. Expected: the card fades, the clock starts, the chair does not move,
  the watcher looks at it for about 3 s (eye icon open, no "VU !") then walks away; then move. Same with Enter, and
  with a gamepad A (the line must read "Appuie sur A pour commencer (ou bouge)" once the pad is used).
- PC: from the title, press Enter on "Jouer" (and on a level card, and on "Niveau suivant" after a win): the new level
  must stay held (the card and its start line stay up). Same with gamepad A. Pause on the card, Resume with Enter: still
  held.
- PC: on the held card, Escape opens the pause (no start), R restarts (still held), mouse orbit and wheel and the right
  stick do not start, Shift does not start; a move key and E still start.
- Lamp level (level6, floor lamp): Space on the card must not switch the lamp (only E does).
- Android: on the held card a quick tap anywhere outside the buttons starts with no move; a drag on the right half
  (orbit) does not; a tap on the pause button opens the pause, not the start; the action button starts and acts.
- The start line fits its plate in French at 16:9 and on a 20:9 phone (StartLineWidth 1120).
- level1 first glance (note 1): decide whether the tutorial's first glance should come later.
