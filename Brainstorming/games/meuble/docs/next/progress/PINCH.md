# PINCH: pinch to zoom on touchscreens (2026-11-24)

User request: pinch to zoom in and out on mobile (Android and iPhone).

## Behaviour

- Two fingers spread apart zoom the orbit camera in; pinched together they zoom out. The rate scales with the zoom range,
  like a wheel notch, so big houses zoom alike.
- A pinch starts when a second finger lands:
  - within `Tuning.TouchPinchPairSeconds` (0.25 s) of the first one, the first not yet dragged (two fingers put down
    together, anywhere on the screen), or
  - on the right half while the orbit finger is held (a pinch on the camera side, any time).
- During a pinch the stick and the orbit drag steer nothing. When one finger lifts, the other is ignored until it lifts.
- Two thumbs playing normally (stick left, orbit right) never pinch unless they land almost together.

## Code

- `TouchControls.cs`: pinch pair detection (`Land`), per-frame distance change, `TryFind`.
- `InputReader.cs`: `SetTouchPinch` / `TouchPinchDelta` (pixels of a 1080 pixel high screen).
- `OrbitCamera.cs`: the pinch moves `Distance`, clamped like the wheel.
- `Tuning.cs`: `TouchPinchMetresPerPixel = 0.008` (440 px sweep 2.5 to 6 m), `TouchPinchPairSeconds = 0.25`.
- The spectator camera keeps its own pinch (height).

## Status

Compiled (SetupAndCompile, no error). Not tested, no build (user runs the tests). Test filter: `TouchControls`;
a PC player run with `-touch` shows the touch overlay.
