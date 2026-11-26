# TVBIG progress (the TV and its stand twice as big)

## The request (product owner, 2026-11-24)
The TV is way too small: make the TV and the TV furniture 2x bigger.

## The TV
- `DecorKinds.TopTvScale` is now capped at `TopTvMaxScale = 2` (was 1, native), still within 90 % of the console's
  width: on a 2.4 m or 2.8 m console the TV is 2.11 m wide and 1.29 m tall (native 1.056 x 0.647), screen diagonal
  doubled. It stands on the console top, centred, 1 cm off the back, screen to the console's front, visual only.
- Its depth uses `DecorKinds.TopTvDepthScale`: the same scale, or less when the console is too shallow, so the foot
  stays on the top and leaves `TopTvFrontStrip = 0.12` m in front (the remote's strip, the validator's "stands in the
  TV" rule uses the same footprint). On a 0.4 m console the foot is 0.27 m deep (scale 1.22), on 0.45 m 0.32 m (1.45).
  A full 2x foot (0.44 m) would overhang a 0.4 m top or eat the remote's strip; the panel itself is thin either way.
- Top of the TV: 0.7 + 1.29 = 1.99 m, under the 2.7 m ceiling. Its back is 1 cm inside the console's back.
- `LevelBuilderDressing.DressProp` scales the TV (k, k, depth scale).
- The `tv_unit` branch (TV drawn inside the box) is unchanged but no level uses it any more (see below).

## The stands
Every stand is now a `counter` wearing `walnut_media_console`, 0.7 m tall, twice as wide, same depth:

| Level | Prop | Was | Now |
|---|---|---|---|
| level5 | TV | tv_unit (1.5, -2.3) 1.2 x 0.6 x 0.4, TV 0.54 m wide | counter (1.05, -2.3) 2.4 x 0.7 x 0.4 |
| level6 | MeubleTV | (2.0, 1.75) 1.2 x 0.55 x 0.4 | (1.05, 1.75) 2.4 x 0.7 x 0.4 |
| level8 | MeubleTV | (7.25, 0.75) 1.2 x 0.6 x 0.4 | (7.25, 0.75) 2.4 x 0.7 x 0.4 |
| level9 | Television | tv_unit (6.25, 0.3) 1.4 x 0.6 x 0.4, TV 0.54 m | counter (7.0, 0.3) 2.8 x 0.7 x 0.4 |
| level12 | Television | (7.25, 0.25) 1.4 x 0.6 x 0.4 | (7.25, 0.25) 2.8 x 0.7 x 0.4 |
| level15 | MeubleTV | (8.75, 2.25) 1.2 x 0.55 x 0.4 | (8.6, 2.25) 2.4 x 0.7 x 0.4 |
| level19 | MeubleTV | tv_unit (7.75, 11.675) 1.4 x 1.1 x 0.45, TV 0.99 m | counter (7.75, 11.675) 2.8 x 0.7 x 0.45 |
| title_house | MeubleTV | (8.3, 2.25) yaw 180, 1.2 x 0.55 x 0.4 | (9.65, 4.4) yaw 90, 2.4 x 0.7 x 0.4 |

Choices:
- Height: 2x would give 1.1 to 1.2 m, a sideboard under a 1.29 m TV (top at 2.4 m). Capped at 0.7 m, the validator's
  `ConsoleMaxHeight` for a console look on a counter.
- Depth kept (0.4, level19 0.45): 0.8 m is not a TV console, and the room in front is taken: coffee tables 0.18 to
  0.38 m away (level5, 9, 12, 19), Hugo's walk line 0.3 m off in level6, the designer route row 0.3 m off in level8.
- The three `tv_unit` stands became counters: a tv_unit's collider is its whole box, TV included, so a 2x TV inside
  it meant a 1.2 to 1.8 m wall. Now every TV is the same 2.11 m, visual only, above a 0.7 m collider. For level5 and
  level9 that is 4x their old TV (0.54 m, squeezed by the box), for level19 2.1x. level19's collider drops from 1.1 to
  0.7 m.
- Moves: level5 and level6 shift west so the TV clears the window behind (x 2.2 to 3.8); level9 shifts east past the
  plant (0.1 m gap); level15 shifts 0.15 m west to stay in the room.
- title_house: the old stand stood in the entree/salon doorway approach (door (8.25, 1.95), area x 7.75 to 8.75) and on
  the camera tour's path through it (waypoints (8.25, 1.95) then (8.22, 2.6)); the south wall west of it is the robot's
  loop (z 2.25, x 5.25 to 7.25), east of it the plant. It moved to the east wall, facing west into the salon (the sofa
  sees it from the side). Static tour check: the nearest waypoint (8.22, 2.6) is 1.37 m from the stand's corner
  (9.45, 3.2), the salon leg goes west from there: far over the 0.25 m of MenuCam_a. Materials 32/32, unchanged.
- level8's remote stays at (0.3, -0.155) on the stand: in front of the TV's foot (foot front at z -0.08).

## Code
- `Assets/Scripts/Core/DecorKinds.cs`: `TopTvMaxScale`, `TopTvFrontStrip`, `TopTvScale` (no depth term),
  `TopTvDepthScale`, `TopTvFootprint` (depth from the depth scale).
- `Assets/Scripts/Runtime/LevelBuilderDressing.cs`: the TV's scale vector.
- `Assets/Tests/EditMode/DressingTests.cs`: `Dressing_TopTv_SitsAgainstTheBackOfTheConsole` now expects 2x on a
  2.4 m console (not run).

## Audit (Build/tvbig_r2.log; r1 died on another agent's missing SpectatorCamera)
LevelAudit -writeRoutes, normal and difficile: 0 defect on level5, 6, 8, 9, 12, 15, 19 (routes rewritten).
title_house: 1 defect at each difficulty, "the schedule found loiters 9.6 s near (1.25, 3.25)" (bureau): a menu
house has no designed schedule (COHERENCE and ROOMS logged "no schedule" defects there before); the freed doorway now
lets the solver find a schedule, a poor one. Not written (no designerRoute in title_house).

## Build
Windows: Build/Play/OutOfSight.exe, "Build Finished, Result: Success" (Build/pc.log, data 2026-11-24 14:49). No APK.

## Tests for the user (written, not run)
- EditMode `--filter Dressing_|DoorwayTests`
- PlayMode `--filter Dressing_|MenuCam_` plus the route and rush tests of level5, 6, 8, 9, 12, 15, 19.

## A VERIFIER
- In game, each level: the 2.11 m TV reads right on its stand, faces the sofa, foot on the top, not into the wall.
- level19: the stand's collider is now 0.7 m (was 1.1): check the sight lines in the salon.
- title_house: the TV on the east wall is seen from the side by the sofa; judge it on the menu tour.
- The TV is visual only: an inhabitant sees through a 2 m screen. Judge whether that reads wrong.
- level9: the TV is centred 0.75 m east of the sofa (the plant blocks the west side).
