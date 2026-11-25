# TOUCHTUTO: touch split in thirds and the level 1 touch tutorial (2026-11-25)

User request (validated mockup `Build/shots/tuto/tuto_mockup.png`), mobile and touch only.

## 1. Touch split in thirds

- `Tuning.TouchStickZoneShare = 1/3`: a finger landing on the left third is the floating move stick (it still appears
  where the thumb lands); a finger landing on the right two thirds orbits the camera. Decided where the finger lands.
  `TouchControls.StickZoneRight` is the split in pixels (marker `MUTATION:TOUCH_ZONE_SPLIT`, formerly
  `TOUCH_HALF_SPLIT`; mutation.sh never had a row for it, so nothing else changed).
- Pinch only in the camera zone: a second finger landing there while the orbit finger is held (two fingers put down
  together there too: the first becomes the orbit finger, the second joins it). The old "fresh pair anywhere" rule and
  `Tuning.TouchPinchPairSeconds` are gone: the stick finger never pinches and keeps steering through a pinch (the
  pinch's first frame no longer zeroes the stick). A third finger landing in the camera zone during a pinch is ignored.
  See `PINCH.md`.
- Unchanged: the buttons (checked first), the lamp tap, the start taps, ignored fingers, the hidden-overlay rules.

## 2. Level 1 touch tutorial

- `TouchTutorial` (new, plain class owned by `TouchControls`): its own root canvas, sorting 40 (over the HUD 10/20
  and the touch overlay 30, under the menus 50), CanvasScaler matched on the height (sizes are the mockup's, in a
  1080 high reference). Veil rgba(12,8,6,0.58); two sliced zone panels on the same split (outline 0.18, fill 0.05,
  48 px corners); left third: stick icon, "MOVE" / "SE DÉPLACER" and its caption; right two thirds: drag icon ("TURN")
  and pinch icon ("ZOOM") side by side, the row laid out like the mockup's flex row from the texts' widths; each
  column shrinks to fit its panel on narrow screens. Bottom centre: gold #F2C14E line on a dark pill (breathes like the
  start line). HUD font (LegacyRuntime), titles bold and in capitals, captions at 0.85. Built the first time it shows.
- Icons: `ProceduralArt.TutorialStick` (300 px), `TutorialDrag`, `TutorialPinch` (260 px) and the sliced
  `TutorialZone`, signed-distance drawings of the mockup's SVG (no texture file).
- Shown (`TouchTutorial.Wanted`, decided every frame in `TouchControls.Update` before the HUD reads it): level
  "level1" built and `GameState.AwaitingStart` (every build holds: a restart and a retry show it again), still
  playing, not spectator, `InputReader.TouchUIActive`, no pause or menu (`Hud.Visible`), no fail or win panel, and the
  touch overlay itself shown.
- Dismissed: while it shows, every finger that lands is the tutorial's (ignored for steering, no button); its lift is
  the start press (`InputReader.PressTouchStart`, the same as today's tap), however long it stayed or far it moved, so
  no move and no camera turn. Fingers already steering when it appears stop. It goes when the level starts (the next
  fixed step); a finger still down stays ignored until it lifts.
- HUD (`Hud.cs`): while it shows, the controls line is off and the intro card (title, level name, hint, people, start
  line, level number) is hidden; after a start from the tutorial the card stays hidden through its fade. If the
  tutorial goes while the level still waits (the device changed), the card shows again. `Hud.TutorialCovering`,
  `Hud.ControlsVisible` for tests.
- Strings (EN/FR): `tuto.move.title`, `tuto.move.caption`, `tuto.turn.title`, `tuto.turn.caption`,
  `tuto.zoom.title`, `tuto.zoom.caption`, `tuto.tap`.

## Files

- New: `Assets/Scripts/Runtime/TouchTutorial.cs`, `Assets/Tests/PlayMode/ProbeTestsTouchTuto.cs`.
- Changed: `TouchControls.cs`, `Hud.cs`, `ProceduralArt.cs`, `Core/Tuning.cs`, `Core/Strings.cs`,
  `Tests/PlayMode/ProbeTestsM7Touch.cs` (messages, new Step63c), comments in `OrbitCamera.cs` and `SpectatorCamera.cs`,
  `docs/next/progress/PINCH.md`.

## Tests (not run here; the user runs them)

- PlayMode filter: `TouchTuto|Step63` (TouchTuto01/02: shown on level1 with ForceTouchUI, not without touch, not on
  level2, hidden under the pause, texts EN/FR, HUD replaced, a lift starts with no move or turn, a restart shows it
  again; Step63c: thirds split, pinch only in the camera zone, the stick never pinches). Also worth a run:
  `HeldStart05` (touch start taps).
- New markers without mutation.sh rows (candidates): `TOUCH_TUTO_GATE` (TouchControls, replace with
  `tutorialShown = false;`, killer TouchTuto01_), `TOUCH_TUTO_TAP` (replace the condition with `false`, killer
  TouchTuto02_), `TOUCH_PINCH_ZONE` (killer Step63c_), `TUTO_COVERS_CARD` (Hud, killer TouchTuto01_).
- No editor-side UI screenshot tool exists (the shot tools render 3D only), so no preview image was made: check it on a
  phone or with a PC player run with `-touch` on level 1.

## Status

Compiled with `SetupAndCompile` (see `Build/TOUCHTUTO.log`). No test, LevelAudit or build run.
