# PINCH: pinch to zoom on touchscreens (2026-11-24, revised by TOUCHTUTO 2026-11-25)

User request: pinch to zoom in and out on mobile (Android and iPhone).

## Behaviour

- Two fingers spread apart zoom the orbit camera in; pinched together they zoom out. The rate scales with the zoom range,
  like a wheel notch, so big houses zoom alike.
- TOUCHTUTO: the touch screen is split in thirds (`Tuning.TouchStickZoneShare = 1/3`, decided where a finger lands):
  the left third is the floating stick, the right two thirds the camera (one-finger orbit and the pinch).
- A pinch starts only in the camera zone: when a second finger lands there while the orbit finger is held. Two fingers
  put down together in the camera zone work the same way (the first becomes the orbit finger, the second joins it).
- The stick finger never becomes part of a pinch (the old "fresh pair anywhere" rule, two fingers landing within
  `TouchPinchPairSeconds` anywhere, is removed, and so is that constant). A thumb on the stick keeps steering while the
  other hand pinches.
- During a pinch the orbit drag turns nothing; a third finger landing in the camera zone is ignored. When one pinching
  finger lifts, the other is ignored until it lifts.

## Code

- `TouchControls.cs`: pinch detection in `Land` (camera zone only, partner = the orbit finger), per-frame distance
  change, `TryFind`. The zone split is `TouchControls.StickZoneRight` (marker `MUTATION:TOUCH_ZONE_SPLIT`, formerly
  `TOUCH_HALF_SPLIT`; mutation.sh never had a row for it).
- `InputReader.cs`: `SetTouchPinch` / `TouchPinchDelta` (pixels of a 1080 pixel high screen).
- `OrbitCamera.cs`: the pinch moves `Distance`, clamped like the wheel.
- `Tuning.cs`: `TouchPinchMetresPerPixel = 0.008` (440 px sweep 2.5 to 6 m), `TouchStickZoneShare = 1/3`.
- The spectator camera keeps its own pinch (height).

## Status

Compiled (SetupAndCompile, no error). Not run (the user runs the tests). Test filter: `Step63` (Step63c covers the
thirds split and the camera-zone-only pinch); a PC player run with `-touch` shows the touch overlay.
