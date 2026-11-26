# FOCUS progress (idea 6: pause on focus loss, nothing runs before the first input)

## State at start (2026-11-20)
- No `OnApplicationFocus` / `OnApplicationPause` anywhere in Assets/Scripts except MusicPlayer.cs:137-150, which only
  re-checks its loops on a regain (a stopped source is restarted). `runInBackground: 1` (ProjectSettings.asset:89): an
  alt-tab kept the level running (docs/IDEAS.md QW1 and section 22 item 6).
- IDEAS.md section 22 item 7 ("the record clock and the routines start at the build, during the 5 s intro card") was the
  pre-C3a state. It is already fixed by C3a, see below.

## What C3a (held start) already covers, verified by reading
- GameState.cs: `BuildLevel` sets `Started = !HoldStart` on every build (first level, restart, next level). `HoldStart`
  defaults to true in a player and in editor play mode, false under --probe, --look and batch mode; the PlayMode suite
  turns it off per test (HeldStartTestRun) and a test turns it on itself.
- `FixedUpdate` returns right after `InputReader.AnyStartInput()` while `!Started`, BEFORE step 1. Every gameplay system
  is driven from that one FixedUpdate in contract order (furniture, inhabitants and their routines, household doors,
  robots, vision, win/caught, barks (dog), sitting, memory and suspicion, carry, dog hold, noise and the creak gauge,
  suspicion decay, HUD, FixedStepped). So while the intro card is up: no timer (`Steps`/`Elapsed` stay 0), no routine, no
  dog, no robot (`RobotTime` 0), no creak, no suspicion. ProbeTestsHeldStart.HeldStart01 asserts exactly that for 3 s
  (steps, clock, creak, robot timeline and positions, every routine pose, the chair).
- Update/LateUpdate-driven scripts only interpolate or animate what the fixed step produced (Inhabitant, Robot, rigs,
  FurnitureController visuals) or read input (FurnitureController.Update latches presses, Hud, TouchControls). None of
  them advances a rule. The rigs keep their idle animation on purpose (cosmetic).
- Start inputs: a move vector past the dead zone (keys, stick, D-pad, touch stick), a move press or an action press (E,
  gamepad X, touch action). The careful key and camera input do not start. A move input while paused does not start
  (FixedUpdate returns on `Paused` first).
- The pause already works while held (`Paused` is checked before `Started`), the Hud holds the card while `!Started`
  (UpdateCardHold, MUTATION:CARD_HELD), and RouteReplayer.ReleaseStart / `GameState.ReleaseStart()` release it for tests.
- Conclusion for (b): nothing to re-implement. The sim gate is the `Started` flag on FixedUpdate, not Time.timeScale.
  Not touched.

## What FOCUS changed (part a)
- `Assets/Scripts/Runtime/GameState.cs`:
  - `OnApplicationFocus(false)` and `OnApplicationPause(true)` both call the new `PauseForBackground()`. The regain
    (`focused` true / `paused` false) does nothing: the player resumes from the pause menu.
  - `PauseForBackground()`: with `AutoPause` on, a level built and `State == Playing`, and no menu open
    (`Menu.IsOpen` false: never under the title and its pages, never twice), it calls `Menu.SetPaused(true)`, which is
    the same path as an Escape press (pause canvas, Resume selected, cursor freed, `Game.Paused = true`, so
    `GamePause.IsPaused` and `AudioListener.pause`; MusicPlayer ducks to `Tuning.MusicPauseDuck` because it reads
    `menu.PauseOpen`). Under the win or fail panel (`State` Won/Caught) it does nothing. Without a Menu (bare GameState)
    it sets `Paused` directly. A held level (intro card) pauses too. Counter `FocusPauses` for tests and the probe.
    Marker `// MUTATION:FOCUS_PAUSE_GATE` on the gate.
  - `AutoPause` static switch with the same shape as `HoldStart`: default `!(Probe.Requested || SaveStore.LookRequested
    || Application.isBatchMode)`, override for tests, `ResetAutoPause()`. The probe's timed captures and the CLI test
    runner are never paused by a focus event nobody can resume.
- "Resume must not inject the key that regained focus": by construction of the existing M3 pause. While paused,
  `GameState.Update` calls `InputReader.DiscardGameplayPresses()` every frame, `FurnitureController.Update` does not
  latch, and `FixedUpdate` returns before `AnyStartInput`. On the frame the menu closes, `Menu.ClosedThisFrame` makes
  `Update` discard again. A click that brings the window back does not capture the cursor while the pause menu is up
  (`Main.Update` checks `Menu.WantsCursor`). Nothing changed in Main.cs, InputReader.cs or Menu.cs.
- `runInBackground` left at 1 on purpose: the paused game keeps rendering the pause menu behind another window, which is
  harmless, and the music keeps playing ducked exactly as under a manual pause.
- Tests (static, NOT run): `Assets/Tests/PlayMode/ProbeTestsFocusPause.cs` (+ .meta). The existing `HeldStartTestRun`
  callback in ProbeTestsHeldStart.cs now also turns `AutoPause` off for the whole suite and resets it after the run
  (`TestRunCallback` allows a single assembly attribute, so one callback serves both switches). FocusPause01 (loss in play: menu
  open, listener paused, sim frozen under a move vector, second loss and Android path idempotent, regain does not
  resume, Resume resumes and the clock counts on), FocusPause02 (title: nothing; AutoPause off: ignored), FocusPause03
  (held level: pauses, stays held, Resume then the first move step is step 1), FocusPause04 (win panel and fail panel:
  nothing). The focus events are sent with `SendMessage("OnApplicationFocus"/"OnApplicationPause")` on the Game object,
  the way ProbeTestsMusicLoop does for the music.

## Unity runs
- 1 compile-only run (SetupAndCompile, Build/FOCUS.log, 2026-11-21 00:05, queued behind LV13's audit): FAILED on my own
  file, `CS0579 Duplicate 'TestRunCallback' attribute` (a second `[assembly: TestRunCallback]` for FocusPauseTestRun next
  to HeldStartTestRun's; the attribute is single-use per assembly). No other error in the log: GameState.cs and the test
  body compiled past that point only as far as the attribute check, so they are NOT yet proven by a compile.
- Fix: FocusPauseTestRun removed, HeldStartTestRun now sets and resets AutoPause too (the first log is kept as
  Build/FOCUS_run1_failed.log).
- Run 2 (the coordinator asked for it to confirm the fix, 2026-11-21 00:30, Build/FOCUS.log): Tundra build success,
  exit 0, no `error CS`. GameState.cs, ProbeTestsHeldStart.cs and ProbeTestsFocusPause.cs compile. Tests not run.
- Suggested run when the Unity lock is free: `test . --mode PlayMode --filter ProbeTestsFocusPause|ProbeTestsHeldStart`.

## A VERIFIER (manual)
- PC build: start a level, press a move key so the card goes, then alt-tab (or click another window). Expected: the pause
  menu is up when you come back, inhabitants and the clock frozen, the music ducked. Click Resume (or press Escape):
  the game resumes, the chair did not move from the alt-tab keys, the cursor is captured again. Repeat while the intro
  card is up: the pause menu opens over the card; after Resume the level is still held until the next move key.
- PC build, title screen and Options: alt-tab must change nothing (no pause menu). After a win or a catch: the end
  panel stays, no pause menu.
- Android build: in a level, press Home (or receive a call), come back. Expected: the pause menu is up, touch Resume to
  continue; the tap that brought the app back must not have moved the chair. Also with the intro card up (level still
  held after Resume) and on the title (nothing). Screen off / lock then unlock: same as Home.
- Editor play mode: clicking outside the editor pauses the level too (expected, `AutoPause` is on there). PlayMode tests
  are unaffected (FocusPauseTestRun turns it off; batch mode is off by default).
- Suggested run when the Unity lock is free: `test . --mode PlayMode --filter ProbeTestsFocusPause|ProbeTestsHeldStart`.
