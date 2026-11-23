# AUTOSTART progress (the world runs from the level start, the first input only starts the clock)

## Request (product owner, 2026-11-23)
- The inhabitants' and animals' routines start moving as soon as the level begins, without waiting for any input.
- The player's first input (Space, Enter, gamepad A, a move key ZQSD/WASD/arrows, the action key, a touch tap) now ONLY
  hides the level title card and starts the level timer.

## State before (C3a held start, STARTFIX, FOCUS)
- `GameState.FixedUpdate` returned right after `InputReader.AnyStartInput()` while `!Started`: no furniture, routine,
  robot, vision, clock, creak or `FixedStepped` before the first input. The Hud holds the card while `!Started`
  (`Hud.UpdateCardHold`, MUTATION:CARD_HELD); Tips, the near-miss bubble and the locked hint already wait for `Started`.
- `HoldStart` is on in a player and in editor play mode, off under --probe, --look, batch mode and for every PlayMode
  test (HeldStartTestRun). With the hold off, `Started` is true from the build, so the change below is a no-op there.

## What changed
- `Assets/Scripts/Runtime/GameState.cs`
  - `FixedUpdate`: the `!Started` block only reads the start input (and releases on it, MUTATION:HOLD_START kept); it no
    longer returns. Every step then runs the whole schedule. New `WorldSteps` counter (fixed steps since the build, reset
    by every build, frozen by a pause); `Steps`/`Elapsed` still count from the first input (records exclude card time).
  - The detection-before-first-input rule (see below), all keyed on `Started`:
    - step 1: `furniture.Step(dt, playing && started)` (no input, so no motion, no action, careful off);
    - step 2: `StepRobots(furniture, playing && started, dt)`: a robot contact before the start reverses the robot and
      counts the contact, but never shoves (no `BeginPush`) and raises no `RobotBumped` (MUTATION:SHOVE_BEFORE_START);
    - step 3: `vision.Unseen()` in place of `vision.Step(...)` (new method in Vision.cs: `SeesPlayer` false, samples
      cleared, so the cone view never shows the alarm) (MUTATION:UNSEEN_BEFORE_START). Leaves are still seen swinging
      (a household door), which can neither catch nor bark while the furniture is still;
    - step 4: clock, exit, caught rule and barks run only once started;
    - step 5: a pratfall before the start (an inhabitant sits where the seat home is and the chair is not there) plays
      its sound and counts in `PratfallCount` but costs no discovery and no suspicion. A sit ON the player (the chair is
      on its seat home) still happens: it is a routine, not a detection, and only pins the chair;
    - step 7: the creak gauge steps only once started (its start delay counts from the first input as before);
    - step 9: the door and wardrobe hints wait for the start (as the locked hint already did), so the card stays clean.
  - Doc comments: class header, `HoldStart`, `Started`, `ReleaseStart`, `RobotTime`, `PauseForBackground`.
- `Assets/Scripts/Runtime/Vision.cs`: `Unseen()`.
- `Assets/Scripts/Runtime/Tips.cs`: header comment only (no tip before the first input: unchanged code).
- Hud.cs untouched (the card already follows `Started`; another agent may animate the card's level number).
- `Assets/Tests/PlayMode/RouteReplayer.cs`: comment only (a release at the first sample keeps t = 0 only right after the
  build).
- `mutation.sh`: rows `hold_start` (HeldStart01_ FocusPause03_ Tips_07_), `unseen_before_start` (HeldStart04_),
  `shove_before_start` (HeldStart06_). The HOLD_START marker existed without a row; START_PRESS, CARD_HELD,
  FOCUS_PAUSE_GATE, TOUCH_TAP_START keep their markers and still have no row (unchanged).

## The detection-before-first-input rule
Until the player's first input the player's furniture is out of play. It cannot move by itself (no input reaches it, no
robot shoves it), no watcher sees it (so no catch, no bark, no discovery, no suspicion, the eye stays closed, no cone
alarm), its creak gauge and the clock wait, and no hint or tip shows over the card. Inhabitants may still sit on it if it
stands on their seat home (that pins it, nothing else). Reason: being seen still is already harmless, so the only ways
to lose without touching anything were a robot shove (then seen moving, then caught) or a pratfall discovery; making the
chair simply undetectable is the rule a player expects while reading the title, and the world around it still moves.

## Designer routes and LevelAudit
- Designer routes are replayed by RouteReplayer, which runs with the hold off or releases the hold at its first sample,
  right after the build: the world and the player both start at t = 0, exactly the old alignment. HeldStart02 checks it
  on level1 and level8 (same exit step, time and counters with the hold on and off).
- LevelAudit runs in batch mode (hold off): unchanged. Its main schedule is the "press at once" case. Its start delay
  sweep (M2.2, levels 1 to 7 by default, `-sweep` for the others) already models a late start: the world runs from
  sample 0, the furniture stands at the spawn until delay d, the gauge is empty at d. The game is at least as lenient as
  that model: (1) the game's creak start delay counts from the first input, the audit's from world t = 0; (2) before the
  first input the game makes the chair unseen and unshoveable, while the audit demands the spawn stay out of the robot
  contact zone during the delay. So a schedule the sweep finds is still valid in the game.
- Limits (not new, they existed before C3a and C3a hid them): a player who starts late meets the routines at another
  phase. The sweep's failures are warnings (no schedule within the 8 s wait cap for some delays on some levels), a
  wandering routine has no sweep, and the sweep only covers delays within one loop. Since waiting under the card is free
  (no creak, unseen), a player can always wait for the phase he wants; the routines loop.

## Pause, focus loss, restart, tips
- Pause: `FixedUpdate` still returns on `Paused` first, so the world freezes under the card too (HeldStart01,
  FocusPause03 assert `WorldSteps`, `RobotTime` and routine poses frozen).
- Focus loss: `PauseForBackground` already paused a held level; it now matters (the world runs). Unchanged code.
- Restart and next level: `BuildLevel` sets `Started = !HoldStart` and `WorldSteps = 0`: the card comes back and the
  world restarts at t = 0.
- Tips: `Tips.Trigger` and `OnFixedStepped` already refuse while `!Started`; Tips_07 checks no tip under the card while
  the world runs, and that one may show after the start.

## Tests
- ProbeTestsHeldStart: HeldStart01 rewritten (world runs under the card, identical to the hold off after 3 s; clock,
  creak and chair wait; pause freezes the world; first input is clock step 1 and world step n+1; restart, action key,
  next level); HeldStart02 replays right after the build (no 50-step wait); HeldStart04 adds the unseen check against a
  hold-off reference and compares the post-start sightings step by step; new HeldStart06 (robot contact before the
  start: no shove, no discovery, no loss).
- ProbeTestsFocusPause.FocusPause03: the world runs under the card, the pause freezes it, Resume then the first move is
  clock step 1 and the world's next step.
- ProbeTestsHudV2.HudV2_01: also asserts the world runs under the held card.
- ProbeTestsTips: new Tips_07.

## Run (2026-11-23, PlayMode, filter HeldStart0|FocusPause0|HudV2_01_|Tips_0|LoadedSit, TestResults/autostart.xml)
- Compile clean (Build/autostart.log).
- Green (17): HeldStart01, 03, 04, 05, 06; FocusPause01 to 04; HudV2_01; LoadedSit x2; Tips_02, 04, 05, 06, 07.
- Red (3), all on the hold-off path, where every AUTOSTART change is a no-op (`Started` is true from the build):
  - HeldStart02: level8's designer route is caught (SeenMoving at 9.42 s) WITH THE HOLD OFF, the test's premise.
    level1 matched step for step with the hold on and off. level8.json is modified in the working tree by other work:
    its designerRoute needs `LevelAudit -writeRoutes` (or the level fix) before this check can pass.
  - Tips_01: `Hud.ScreenRectOf(Hud.EyeAnchor)` is an empty rect (the eye anchor), the pointer test cannot pass.
  - Tips_03: on level3 the decoy tip already fired by itself before the test's Trigger ("tips.decoy is on screen").
  The Tips tests were written without ever being run (their class comment says so); both failures are in the test or
  the HUD layout, not in the start logic.

## A VERIFIER
- HeldStart02 once level8's route wins again with the hold off; Tips_01 and Tips_03 (see above).
- Play level1 to level7 in the editor with the hold on: read the card for 5 to 10 s, then play. Check the late-start
  phases feel fair (the audit sweep warnings on levels 1, 2, 3, 5, 7 are the ones to watch; level1's window dwell 3.5 s
  was tuned for the C3a held start, CONTRACT_M2 11.8).
- A level whose "sit": "player" seat home is NOT the spawn: before the first input the pratfall is now free (no
  discovery). Check no level relies on that early pratfall as a lesson.
- Speech bubbles may show over the card (a household door opened, a sit on the player): judge if that is wanted.
- The start line still says "Press Space to start (or move)": still accurate (it starts the clock), wording left as is.
- A robot path through the spawn reverses on the out-of-play chair before the first input, which shifts its timeline
  against the audit's (the audit forbids that contact during the delay, so no audited level should have it).
- mutation.sh rows `hold_start`, `unseen_before_start`, `shove_before_start` not run (no full suite asked).
