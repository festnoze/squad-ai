# SPECTATOR progress (watch a level with a free camera, the furniture out of play)

## Request (product owner, 2026-11-24)
A "Mode spectateur" / "Spectator mode" checkbox on the level select. Ticked, a card loads its level as usual but the red
furniture is fully out of play and the camera is a free noclip camera; the inhabitants, pets and robots run their routines.
Normal play is unchanged when the box is unticked.

## UI
- `LevelSelect.cs`: `SpectatorButton`, a warm column button above Retour (y -262, 420 x 64, same StyleWarm colours) with a
  box on its left (ink frame, dark inside, chair red tick while ticked). Click, tap, Enter or gamepad A toggles it.
  Navigation: down past the grid's last row reaches the checkbox, then Retour; up from Retour reaches the checkbox, up
  from the checkbox the last card, right the first card. `SpectatorChecked` is a static: kept for the session, never saved.
- `Menu.PlayLevel` sets `GameState.Spectator` from the checkbox; Jouer and the title house clear it. In the pause menu the
  "Menu principal" button reads "Choix du niveau" / "Level select" in spectator mode and goes back to the level select
  (`ToTitleFromPause` then `OpenLevelSelect`). Reprendre and Recommencer are unchanged (a restart stays in spectator mode).
- `Hud.cs`: `SetSpectator(bool)` (called at every build) hides the play band (eye, gauges, controls line, careful, lamp,
  balance), the play hints (sat on, dog hold, tipped, door, locked) and the exit marker, and shows a "SPECTATEUR" tag at the
  top centre and the free camera's controls line (per device: keyboard, gamepad, touch). Both go with the whole HUD under a
  menu (pause). The card hold now reads `GameState.AwaitingStart`.
- `Strings.cs`: `select.spectator`, `hud.spectatorTag`, `hud.spectator`, `hud.spectatorGamepad`, `hud.spectatorTouch`,
  `pause.levels` (EN and FR).

## Rules (GameState.cs)
- `Spectator` (instance flag, read by every build): `Started = !HoldStart && !Spectator`, so the AUTOSTART rule (the
  furniture out of play before the first input: no input, `Vision.Unseen`, no shove, no clock, no exit, no catch, no
  creak, no tips, no hints) holds for the whole session. The first start input only sets `SpectatorCardDismissed` (the
  card goes); the free camera's first input does too (`DismissSpectatorCard`).
- `Win()` and `Lose()` return at once in spectator mode (belt and braces); `RecordLine` records nothing for a spectator
  game. No achievements system exists; records, stars and wins only go through `RecordLine` on a win.

## Free camera (SpectatorCamera.cs, new)
- Added to the game camera by the first spectator build; `Begin` disables the OrbitCamera and starts from its pose,
  `End` (any non-spectator build) re-enables and snaps it. Execution order 260 (after OrbitCamera and TitleCameraTour,
  before WallFader and RoomCeilings). Moves its transform only: no collider, no collision.
- PC: WASD/ZQSD/arrows fly along the view, Space or E up, Ctrl or Q (A on AZERTY, physical key) down, Shift x3, wheel
  scales the speed (x1.25 per notch, 0.5 to 15 m/s, 3 m/s at start), mouse look while the cursor is captured (like the
  game camera) or with the right button held.
- Gamepad: left stick flies, right stick looks, RT up, LT down, L3 faster.
- Touch: the overlay's left thumb stick flies, a drag on the right half looks, a two-finger pinch moves up or down (the
  view does not turn while two fingers are down).
- Bounds: the interior box plus 12 m, height -1 to 25 m. Holds still while paused.
- `InputReader.cs`: `SpectatorVertical`, `InjectSpectatorVertical`, `SpectatorFast`, `LookButtonHeld`.

## Walls and ceilings
- The level's WallFader gets the camera transform as its target and no furniture (the title tour's rule): no shared wall
  ever separates the camera from itself, so inside the house nothing is lowered and nothing flickers; the outer walls the
  camera stands outside of still get out of the way (unchanged rule). RoomCeilings already shows a ceiling only while the
  camera is below it.

## Tests (written, NOT run)
- `Assets/Tests/PlayMode/ProbeTestsSpectator.cs`: Spectator01 (level7: inputs do not start it, nobody sees the chair, no
  clock, no creak, no win on the exit, nothing saved, inhabitants move, card dropped, pause offers the level select,
  restart stays spectator), Spectator02 (level1: the free camera flies through a wall; a played build hands the camera
  back).
- Filter: `ProbeTestsSpectator`. Regression filters worth a run: `ProbeTestsHeldStart`, `ProbeTestsM5Ui`, `Tips_`.

## A VERIFIER
- Pinch on a real phone: speed of the up/down (`PinchMetresPerPixel` 0.012) and that a two-finger pinch on the left half
  does not also fly (the overlay's stick takes the first finger).
- Mouse look in a player: the cursor is captured by PlayLevel; after Escape and Resume it is recaptured.
- Ctrl+W/Ctrl+Q in the editor game view can hit editor shortcuts; in a player it is fine.
- Wall faders seen from outside the house: outer walls lower as in play; interior walls stay standing (by design).
- The near-wall vanish rule (see-through and both looks) with the camera just outside an outer wall.
- Gamepad A on the card: it dismisses the card only (no start).
