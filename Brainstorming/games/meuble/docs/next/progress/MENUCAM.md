# MENUCAM progress (the title camera tour, 30 percent nearer the floor)

## Request
The moving camera behind the main menu (TitleCameraTour, the loop through Resources/Levels/title_house.json) runs 30
percent nearer the floor: its height times 0.7 along the whole path, still framing the same things, without clipping
through furniture, door frames, walls or the ceiling, and without showing the outside of the house.

## Change (2026-11-23)
- `Assets/Scripts/Core/Tuning.cs`:
  - `TitleTourHeight` 1.0 to 0.7 m. The tour has one constant height over its whole path (TitleCameraTour.Pose), so
    this lowers every point of the loop.
  - `TitleTourPitch` 7 to 5 degrees (looking down). The view axis still meets the floor about 8 m ahead
    (atan(0.7 * tan 7 / 1.0) = 4.9 degrees), so the same things stay framed; the horizontal lens shift is unchanged.
- No waypoint moved (TitleCameraTour.cs untouched): the path is planar, its clearances are horizontal and do not depend
  on the height, and the check below found nothing to fix.
- New PlayMode test `Assets/Tests/PlayMode/ProbeTestsMenuCam.cs`, `MenuCam_a_TheLowerTourClearsTheHouse`: along the
  whole loop every 5 cm, the new height and pitch; no solid collider within 0.25 m of the camera (found: 0.40 m at the
  closest, in the bureau-salon doorway, the same as at the old height); a 12 x 7 ray grid over the shifted lens every
  25 cm, each ray's first wall, prop, floor or ceiling hit inside the house's outline (found: 0 rays outside of
  10080, at the new and the old height). It writes before (1.0 m, 7 degrees) and after shots at six points of the
  loop, PC 1920 x 1080 and phone 2400 x 1080, to `Build/shots/menucam` (`pc_N_before/after.png`,
  `phone_N_before/after.png`, `sheet_pc.png`, `sheet_phone.png`, rows top to bottom the six points, left before,
  right after) and `menucam.txt`.

## Results
- Compile: OK (Build/menucam.log).
- `--filter MenuCam_|Lighting_a_`: 2 of 2 passed (the existing title ceiling check unchanged). No other test checks the
  tour's height or pitch.
- Shots: no clipping anywhere; at 0.7 m the counter tops (0.9), the console (0.8) and the sofa sit at or above eye
  level and show their sides, the window sills (0.9) are above the camera.

- 2026-11-23 (coordinator): the tour lowered again, `TitleTourHeight` 0.7 to 0.55 m and `TitleTourPitch` 5 to 4 degrees,
  ProbeTestsMenuCam updated to match; re-checked by the TITLEMOVE runs (`--filter Step74b|MenuCam_`,
  TestResults/titlemove.xml and titlemove2.xml): `MenuCam_a` PASSED, closest 0.40 m at (4.45, 0.55, 3.25) (the
  bureau-salon doorway, as at 0.7 and 1.0 m), 0 of 10080 rays outside; no waypoint changed. Shots: no clipping.

## A VERIFIER
- In the built game: the title page over the lowered tour, PC and phone (the shots render the scene only, without the
  menu canvas and the title logo).
- The kitchen stretch (shot 4): the sink counter now fills more of the left side, under the title column.
- The outside check counts 0 rays out at both heights: the window panes probably stop the rays (colliders), so it
  proves the lower camera sees no more outside through the doors, not through the windows (the shots show the windows
  with the garden, as before).

- CEILING (2026-11-24): TitleTourPitch 4 down to 4 up (-4), at the user's request, so the room ceilings read in the menu background.
