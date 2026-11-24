# CEILING progress (a painted ceiling per room, shown from inside, gone from the overhead view)

## Request (2026-11-24)
"ajouter un plafond visible depuis l'interieur, qui s'efface par piece quand la camera surplombe la maison. Ca donnerait
au salon une vraie sensation d'interieur tout en gardant la lisibilite de la vue en coupe."

## Design
- New `Assets/Scripts/Runtime/RoomCeilings.cs`, built by `LevelBuilder.Build` for every level (right after the floor dust,
  so after the walls, the floors, the room lights and the lit zones), under the level root as `Ceilings`.
- Geometry: one mesh per room, a grid of quads 0.5 m apart, facing down, over the room's rectangle (its wall centre lines,
  so the edges hide inside the walls) at the room's `wallHeight` (2.7 m in every level). Its own renderer per room.
- No gameplay effect: no collider (vision raycasts on the Occluder mask, hearing, the NavMesh sources and LevelAudit
  never see it), Default layer (no occluder, no x-ray stencil), `ShadowCastingMode.Off` (the sun, the moon and the lamps
  light the rooms as before), and every renderer is built disabled: the draw call and material budgets the audit and
  the probe count are unchanged (they count enabled renderers only, and the overhead view never enables one).
- Material: the walls' one material (WallArray, `OutOfSight/Wall Finishes`), each vertex naming a flat colour (the
  `WallArray.Flat` encoding of the fixture housings: UV1.x = -1, UV2.rgb the linear colour). So no new material: a warm
  off-white paint (sRGB 0.93, 0.90, 0.85), matte (smoothness 0.08), lit by URP exactly like the walls: from below the
  ambient trilight gives it its ground colour by day (it reads close to the old title lid's hand-picked colour) and
  almost nothing at night, the player's floor lamp (a point light) lights it directly, SSAO darkens its corners on Haut.
  Without the wall material (textures off, tests) a URP Lit material of the same colour.
- Bounce (lamps lighting the ceiling, no new real-time light): every room light is a spot aimed down (RoomLights,
  LitZoneView) and never reaches a ceiling. Each one's floor pool is bounced onto its room's ceiling as a per-vertex glow:
  `BounceStrength` (0.08) x the pool's light (intensity / distance^2) x the form factor of a floor patch,
  (h^2 / (h^2 + r^2))^2 with h narrowed by `BounceSpread` (0.65, a soft patch over each lamp), in the light's colour
  (the paint tinted toward it where the glow is strong), capped at `BounceMax` (0.3 linear luminance) so no slab ever
  glows. The sun (or the moon) on the floors is bounced too: `SunBounce` (0.25) of its light on a level floor, darker
  toward the walls (0.4 at a wall face, none from 1 m in). The shader change is one line in the flat branch:
  emission = albedo x UV2.w (`WallFinishesForward.hlsl`; the housings carry 0 there). The glow follows the lights: a
  light switched off (tier Bas, a lamp's room dimming) rebakes its room's UV2 (a few hundred vertices, only on change), a
  new sun or moon (the night preset) every room's.
- Why a sun bounce: the first run had the lamp bounce only, and a ceiling by day read as a flat brown lid (the ambient
  trilight's ground colour is a dark brown, 0.28 / 0.23 / 0.19), much darker than the sunlit walls
  (`level1_inside_eye.png` of run 2 against run 3). With 0.25 it reads as a warm off-white ceiling a little darker than
  the walls; the variants 0, 0.15 and 0.38 are rendered next to it (`level1_inside_eye_sunX.png`).
- Night: the paint is lit by the night ambient (x0.24) and the weak moon bounce only, so the ceiling stays a dark grey,
  except over the lit pools of the room lights (stronger at night, NightPool 1.45) and near the player's lamp.
- The rule (`RoomCeilings.ShowsFrom`): a room's ceiling shows only while the camera is below it by 0.1 m. Why this is
  enough: a plane at height H never hides anything below H from an eye below H (the segment between two points below a
  plane never crosses it), and from above it is seen from behind and culled. So it can never hide the player's furniture,
  an inhabitant or a vision cone, whatever the room the camera hangs over or looks into. (The request's second clause,
  "inside the room's footprint and below it", is contained in the first.)
- The fade, per room, 0.3 s (unscaled time, smoothstepped): a fully shown ceiling is its opaque renderer (SRP batched,
  SSAO); while it fades its renderer is off and a copy is drawn each frame with the wall fader's see-through material
  (`WallFader.GhostMaterial`, already counted in every level) at its opacity, for the tracked camera only. A level start
  or a camera jump over 1.5 m (Tuning.WallFadeSnapDistance) snaps. `Apply(eye)` snaps for tests and tools.
- The title tour: the title house now shows its rooms' lit ceilings; `TitleCameraTour` builds its old unlit lid only
  when there are none (`RoomCeilings.Disabled`), as a fallback.

## Files
- New: `Assets/Scripts/Runtime/RoomCeilings.cs`, `Assets/Tests/PlayMode/ProbeTestsCeiling.cs`.
- Changed: `Assets/Scripts/Runtime/LevelBuilder.cs` (one call), `Assets/Settings/WallFinishesForward.hlsl` (the flat
  glow), `Assets/Scripts/Runtime/TitleCameraTour.cs` (no lid over room ceilings),
  `Assets/Tests/PlayMode/ProbeTestsLightingShots.cs` (Lighting_a_ checks the room ceilings when they exist).

## Tests (`Assets/Tests/PlayMode/ProbeTestsCeiling.cs`, run alone with `--filter Ceiling_`)
- `Ceiling_a_OnePerRoomNoGameplayFadesByCamera` (level20, night): one ceiling per room, at the wall top, over the room's
  rectangle, flat, facing down (normals and winding); no collider under the ceilings, shadows off, not Occluder nor
  Floor layer, no ray straight up from a room's middle meets it; from the default gameplay camera (y 3.97) every
  ceiling is at 0 and its renderer off (125 draw calls, 22 materials: the gameplay count); a test camera at 1.6 m shows
  every ceiling after a fade of 0.30 s (frames seen in between, the opaque renderer off while fading), back at 2.9 m it
  fades out in 0.30 s; switching the bureau's two room lights off drops its glow from 0.121 to 0.020 (the moon's share).
- `Ceiling_b_ShotsOverheadUnchangedInsideCeilinged`: before (`RoomCeilings.Disabled`) and after, the gameplay start view
  and the house view of level1 (day) and level20 (night): mean difference 0.009 to 0.28 out of 255, no ceiling shown.
  The few changed pixels are the striped vision cones' animation and a sub-pixel flicker at the frame's edge, not a
  ceiling (diff masks `*_diff.png` from run 2: the corridor's cone stripes in level20's house view). Then the inside
  shots and the variants.
- `Ceiling_c_TitleTourUnderTheCeilings`: the title house's ceilings all show on the tour, the tour builds no lid, three
  shots of the loop, and the same three over the old lid (the house rebuilt with `RoomCeilings.Disabled`).

## Shots (`Build/shots/ceiling`)
- Overhead, identical: `level1_{start,house}_{before,after}.png`, `level20_night_{start,house}_{before,after}.png`.
- Inside, ceiling visible: `level1_low_orbit.png` (the game camera, pitch 2 degrees, 4 m: eye at 1.31 m),
  `level1_inside_eye.png` (across the living room at 1.25 m) against `level1_inside_eye_before.png` (the sky and the
  garden's trees over the walls), `level1_inside_eye_sun{0.00,0.15,0.38}.png` (sun bounce variants).
- Night: `level20_bureau_inside_night.png` (the desk lamp's soft patch on a dark grey ceiling) with the variants
  `_bounce0`, `_bounce_half`, `_bounce_double` and `_before` (no ceiling); `level20_bureau_inside_day.png` by day.
- Menu tour: `title_tour_{1,2,3}.png` and `_before` (the old unlit lid). At the tour's 0.55 m eye height and 4 degree
  tilt the ceiling barely enters the frame (the top 40 to 80 px of stops 1 and 2, where it meets the wall tops; stop 3
  none), so the tour looks as before; it shows when the camera looks up or in the fish-eye's corners.

## Runs (5 Unity runs)
1. SetupAndCompile (Build/ceiling.log): compiled, no error.
2. PlayMode `--filter Ceiling_|MenuCam_|Fisheye0|NightLook|Lighting_a_` (TestResults/ceiling.xml): 11/11 passed. The day
   ceiling read as a brown lid: sun bounce added, lamp bounce narrowed (0.12 to 0.08, spread 0.65).
3. Same filter (TestResults/ceiling2.xml): 11/11 passed (Ceiling_a/b/c, Fisheye01/02, Lighting_a_, MenuCam_a,
   NightLook_a..d).
4. BuildWindows to Build/Play/OutOfSight.exe: SKIPPED, an OutOfSight process (Build/Play/OutOfSight.exe) was running when
   the build was due. Build/Play is still the previous build, without the ceilings.
5. BuildAndroid (Build/apk.log): Build/Android/OutOfSight.apk built, 56.3 MB (limit 150 MB).

## A VERIFIER
- Rebuild Build/Play (BuildWindows) once the game is closed, then look at the title tour and a low orbit in the player.
- The title tour at 0.55 m and 4 degrees barely frames the ceiling: if the user wants it to read on the title, tilt the
  tour up a little (Tuning.TitleTourPitch) or add waypoints that look up; nothing was changed there.
- The day look: SunBounce 0.25 (warm off-white, a little darker than the sunlit walls). Variants rendered at 0, 0.15 and
  0.38 (`level1_inside_eye_sun*.png`); the user may want it lighter or darker.
- The lamp bounce is a soft patch, subtle by day (BounceStrength 0.08); `_bounce_double` shows a stronger choice.
- In the Lowered and Both wall looks, a low orbit from outside the house shows the ceilings as a lid over the sunk wall
  (the cutaway with its ceiling): intended, not yet seen in a player.
- On a phone (Moyen, Bas): the ceilings use the wall material and its flat path; the glow (UV2.w) compiled for Android
  but was not seen on a device.
- Gameplay zoomed fully in at the default pitch puts the camera near 2.3 m, under the ceilings: they are enabled (a few
  extra draw calls, SRP batched) but out of the frustum, since the view looks down. Not measured on a phone.
