# GARDENZOOM: the garden ring follows the zoom (2026-11-25)

User request: "upon strong dezoom, enlarge the garden background cylinder so that the camera remains inside it whatever
the de-zoom level is. Re-shrink upon re-zoom until the default garden cylinder size defined by config."

## Behaviour

- The garden ring (the cylinder showing the garden picture, closed by its round sky ceiling) keeps its default size from
  config: the house's farthest point times 1 + `Tuning.GardenRingHouseMargin` (GARDENFIT, unchanged).
- Every frame, once the cameras have moved, the ring is scaled to the smallest size, never below the default, that holds
  the game camera:
  - radius = max(default radius, camera's horizontal distance from the ring's axis + `Tuning.GardenRingCameraMargin`);
  - the ceiling stays `GardenBackdrop.HeadRoom` (1.5 m) above the camera, and the rounded rim (the 2.5 m fillet where the
    wall meets the ceiling) is taken into account, so a camera that is both high and near the wall is still inside.
  This holds for every zoom, orbit angle and view pitch. The camera never leaves the ring, so the inward-only faces
  never break the illusion.
- Zoomed in again, the ring shrinks back and lands on exactly the default size (transform scale exactly one).
- Smooth: the size eases toward its fit both ways (`Tuning.GardenRingFitTime`, 0.15 s time constant), so a wheel notch
  (which moves the camera in one jump) does not make the ring pop. The easing can never let the camera get closer than
  `GardenBackdropFit.MinClearance` (0.3 m) to the wall or the ceiling: if the zoom is faster than the easing, the ring is
  pushed out at once. When the camera zooms in, the ring settles in about half a second. The first fit after a level build
  is applied at once, so the ring never visibly grows at level start.
- Proportions: one uniform scale about the centre of the ring's foot. The foot stays on the ground (y = -Sink): the
  transform rises by Sink x (scale - 1). The garden picture keeps its aspect (its height grows with the circumference, and
  there are still three repeats). The sky picture still spans the ceiling's diameter. No mesh is rebuilt.
- Any camera: the fit follows Main's camera whoever drives it: the orbit camera, the spectator's free camera
  (SpectatorCamera: the interior plus 12 m, up to 25 m high, which can be far outside the default ring) and the title
  tour (always inside the title house, so the title ring stays at its default size). The title/menu house uses the same
  backdrop through LevelBuilder, so it gets the same fit.
- Coverage: the largest ring any camera of a level can ask for (`Ring.MaxScale`) covers the orbit camera's whole space
  (its farthest reach and its highest eye together, a bound) and the spectator's whole flight box. The far clip
  (`Ring.FarClip`, set by `OrbitCamera.SetTarget`) holds that largest ring across its diameter and its whole height. The
  lawn reaches under it (2 x `Ring.MaxRadius` + 20 m). If a camera ever goes beyond those bounds, the fit still encloses
  it and raises the far clip (it only ever raises it). The game has no fog (`RenderSettings.fog = false`), so there is
  nothing to adjust there.
- Gameplay: none. The ring has no collider and sits on the Default layer, so vision, raycasts and navigation never see it.

## Code

- `Assets/Scripts/Runtime/GardenBackdropFit.cs` (new MonoBehaviour, `[DefaultExecutionOrder(280)]`, after OrbitCamera
  200, TitleCameraTour 250 and SpectatorCamera 260). `GardenBackdrop.Build` adds it to the ring. API: `Ring` (the default
  ring), `Scale`, `Radius`, `Height`, `Top`, `FitFor(eye)`, and `Refresh(dt)` (`float.PositiveInfinity` applies the fit
  at once: tests use it). It only runs in play mode, so edit mode tools keep the default ring.
- `Assets/Scripts/Runtime/GardenBackdrop.cs`:
  - `ScaleToHold(ring, eye)` / `(ring, horizontal, height)` / `(ring, horizontal, height, side, above)`: the pure fit. It
    computes the gauge of the ring's convex profile (wall, rounded rim, flat ceiling) at the camera point grown by its
    margins: the square profile's answer, then the rim's quarter circle solved in closed form (smaller root). The result
    is continuous and monotonic, so a smooth camera gives a smooth ring.
  - `HorizontalSqr`.
  - `Ring.MaxScale`, `Ring.MaxRadius`, `Ring.MaxHeight`.
  - `Ring.InnerRadiusAt(y, scale)`.
  - `Ring.FarClip` now covers the largest ring.
  - `RingFor` computes `MaxScale` (orbit space and spectator box).
  - The class doc comment is updated.
- `Assets/Scripts/Runtime/LevelBuilder.cs`: lawn = max(size, 2 x max(Radius, CameraRadius, MaxRadius) + 20).
- `Assets/Scripts/Runtime/OrbitCamera.cs`: doc comment of `Fence` only (the zoom, its fence and its far clip line are
  unchanged).
- Mutation markers: `MUTATION:GARDENZOOM_RIM` (the rim root), `MUTATION:GARDENZOOM_FLOOR` (the MinClearance floor). No
  mutation.sh rows.

## Tuning (`Assets/Scripts/Core/Tuning.cs`)

- `GardenRingCameraMargin = 2` m: the room kept between the camera and the ring's wall. The ring starts to grow just
  before the camera would reach it.
- `GardenRingFitTime = 0.15` s: the time constant of the easing.
- `GardenRingHouseMargin = 0.50` (unchanged): the default size. Its doc comment now points at the zoom fit.
- Structural constants (in code, not Tuning): `GardenBackdropFit.MinClearance = 0.3` m and `LandEpsilon = 1e-4`.

Android cost: one LateUpdate of a few float operations (one `Mathf.Exp`, two square roots), the transform written only
when the scale changes, no allocation, no mesh rebuild, no new material or draw call (still two draw calls).

## Tests (`Assets/Tests/PlayMode/ProbeTestsM9Backdrop.cs`, edited)

- `Step95a`: at every pose (level, focus, yaw, pitch, longest zoom) the fitted ring holds the camera
  `GardenRingCameraMargin` from its wall and `HeadRoom` below its ceiling. Under the straight wall, the radius is exactly
  max(default, distance + margin). The fit is never beyond `MaxScale`, the far clip holds it, and the longest zoom does
  grow the ring. A camera at the house's centre keeps exactly the default ring. Every corner of the spectator's flight box
  fits in the largest ring.
- `Step95b`: the ring carries the fit. Zoomed in, it is exactly the default ring (scale one; the old structural
  checks run there). At every pose of the longest zoom the built ring has the fitted radius, its foot is on the ground,
  its ceiling is at the fitted top, the camera is inside it with the margin, the far clip holds it, and the lawn reaches
  under it. In real frames, a jump to the longest zoom never leaves the camera closer than `MinClearance`, the ring
  settles on its fit, and when zoomed in again it eases back to exactly the default (waits on conditions, with a 10 s
  real-time guard).
- `Step95z`: shots now use the `v6` prefix and each shot is taken after the fit is applied.

## Status

Compiled: SetupAndCompile through tools/unity.ps1 (Build/gardenzoom.log) finished with no `error CS`, and the Runtime
and PlayMode test assemblies were rebuilt after every edit. The first two attempts failed only on other agents' files
that were mid-edit (Menu.cs, MenuTouchLayout.cs). Tests not run, per instructions: no test suite, LevelAudit or player
build.

Test filter: `Step95a_|Step95b_|Step95z_` (or the class `ProbeTestsM9Backdrop`); `Step95` also covers the backdrop's
other checks (`Step95c`). Worth re-running nearby: `ProbeTestsNight` (the ring's tint, unchanged).

By hand:
- PC player: load any level, roll the mouse wheel all the way out (and orbit with the mouse at the lowest pitch). The
  garden picture stays all round the view and the sky ceiling stays closed. No grey/blue void and no cut edge of the
  cylinder should appear. Roll back in: within about half a second the garden comes back to its usual distance.
- Android: pinch in fully (fingers together) on the right two thirds of the screen, orbit with one finger, then spread to
  zoom back in. Same checks.
- Spectator mode: fly to a corner of the flight box and up to the ceiling. The ring stays around the camera.
