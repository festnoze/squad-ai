# WINDOWS3D - real 3D windows instead of the flat window picture (2026-11-24)

## Request

Every window of every level was a flat textured quad on the wall (the 2026-11-19 window picture, `WindowImage`): fine from
afar, closed and depthless close up. Replace it everywhere (every `windows` entry of `Assets/Resources/Levels/*.json`, the
title house and the test fixtures included) with the art handoff's 3D wood casement window
(`ArtHandoff/WoodWindow/INTEGRATION.md`), the garden backdrop visible through its glass, collisions and vision unchanged.

## What changed

- **Model asset.** `Assets/ThirdParty/Models/WoodWindow/wood_casement_window.glb` (the handoff GLB, beside the other
  in-house dressing packs). `WindowModelBuilder` (Editor, called by `ModelCatalogBuilder.Build`, so by `SetupAndCompile` and
  every player build) bakes `Assets/Resources/WindowModel.asset` (`WindowModel`) from it, hash-guarded like the dressing:
  - `frame`: wood, gaskets and hardware (880 triangles) through `DressingBuilder.Bake` (now `internal`, with a material
    filter): the walnut samples the existing `walnut_veneer` dressing slice of the wall arrays (the handoff PNG is byte for
    byte `LivingRoomFurniture/walnut_veneer.png`, so it is not copied twice), the gaskets and the hardware are flat colours
    with their own metallic and smoothness. Drawn by the wall material: no new material for the frame.
  - `glass`: the "Clear glazing" slot alone (6 quads, 12 triangles), as glTFast imports it (x negated, V flipped), UV 0-1 per
    pane kept.
  - `glassMaterial`: `Assets/Settings/WindowGlass.mat` (created by the builder), shader `Out of Sight/Window Glass`
    (`Assets/Settings/WindowGlass.shader`, the handoff shader as delivered, header comment added), the handoff's reference
    values (`_Tint` 0.93/0.98/1, `_Veil` 0.006, `_ReflectionStrength` 0.88), queue Transparent.
  - Build safety: the shader ships because `Resources/WindowModel.asset` references the material (no Always Included entry
    needed). The built player probe now fails if that material's shader did not reach the build or is unsupported
    (`Probe.Audit`), and the glass shader is accepted as a project URP shader (`Probe.IsProjectWallShader`).
- **Level build (`LevelBuilder`).**
  - `WindowOpenings` + `Pieces`: every face of a wall line with windows (both sides, the fills of a shared line, an outer
    line's outside faces) is drawn around each window's JSON rectangle inset by `Tuning.WindowOpeningOverlap` (1 cm), the
    wall pattern continued across the pieces. The `Segment` box colliders are untouched: the wall stays solid for sight,
    the player and the NavMesh (vision cones, occlusion and LevelAudit see exactly the same colliders).
  - `Window3D`: pivot at the opening's bottom centre, scale `(Width / 1.32, (Top - Bottom) / 1.36, z)`, z fitted so the outer
    frame (model z -0.103 to 0.059) spans the wall thickness 3 mm proud of each face (`Tuning.WindowFrameProud`), the sill and
    the handle standing proud on the room side; +z toward the room (yaw 180 on the -1 face side, 0 on the +1 side). The frame
    overlaps the cut edges by 1 cm, so no reveal faces are needed (the frame lines the opening through the whole wall).
  - Frames of one wall line combine into one `WindowFrame` renderer (wall material, Default layer, casts shadows: the sun
    through the opening draws the sashes on the floor). One `WindowGlass` renderer per window (shared glass material, no
    shadow): the shader takes its angle from the window's own object space and every window sorts as its own transparent.
  - The flat M3 pane and trim strips (`WindowDecor`) remain only when there is no wall material (textures off) or no model
    (`WindowModel.Usable` null, or `WindowModel.Disabled` for tests). In that case nothing is cut.
- **Fading (`WallFader`).** Frame and glass are registered with their wall line's rule exactly like the door frames since
  DOORFADE: the outer rule on an outer line (gone whenever the camera is outside it, near-wall vanish included), the centre
  plane on a shared line. Lowered look: both sink with the wall. See-through look: the frame's copy uses the one
  see-through material (it reads the walnut slice and the flat colours from the arrays); the glass is marked (`MarkGlass`)
  and its copy is drawn with its own glass material, reflections and tint scaled by the copy's opacity (`DrawGlass`), so a
  faded wall never shows an opaque sheet in the panes. Ceilings (CEILING) are untouched.
- **Night.** The glass streaks are unlit: under the night preset each glass gets a block with `_ReflectionStrength` at
  `Tuning.WindowGlassNightReflection` (0.45) of the material's. The garden keeps its own day and night tint.
- **Retired.** `WindowImage.cs` and `Assets/Resources/WindowImage.png` (1 MB no longer shipped). The source picture stays in
  `Assets/Art/Environment` (README and `docs/LICENSES.md` updated). `LevelBuilder.PaneMaterial` names the cached unlit pane
  material the garden ring and the cool fixture glows still share.

## Files

- Added: `Assets/Scripts/Runtime/WindowModel.cs`, `Assets/Editor/WindowModelBuilder.cs`, `Assets/Settings/WindowGlass.shader`,
  `Assets/Settings/WindowGlass.mat` (generated), `Assets/Resources/WindowModel.asset` (generated),
  `Assets/ThirdParty/Models/WoodWindow/wood_casement_window.glb` (+ Unity metas).
- Modified: `LevelBuilder.cs`, `WallFader.cs`, `Probe.cs`, `Tuning.cs`, `GardenBackdrop.cs`, `RoomLights.cs` and `Main.cs`
  (comments only), `DressingBuilder.cs`, `ModelCatalogBuilder.cs`, `mutation.sh` (`window_model`, `night_glass`),
  `docs/LICENSES.md`, `Assets/Art/Environment/README.md`.
- Tests updated (not run): `ProbeTestsM5House.Step39h_` (one glass per window, frames per wall line, both registered with the
  fader, glass marked, a wall collider behind every window, no flat pane), `ProbeTestsM6Textures.Step50a_`
  (`AssertWindows3D`), `ProbeTestsM8Lights.Lights_a_` (the cool glow is `LevelBuilder.PaneMaterial`), `ProbeTestsNight.Night_b_`
  (glass reflections by day and at night instead of the picture's colour), `ProbeTestsM9Backdrop.Step95b_` (the ring is the
  cached pane material), `ProbeTestsM42Look.Step22e_` (window frames exempt from the tiled-finish check).
- Deleted: `Assets/Scripts/Runtime/WindowImage.cs`, `Assets/Resources/WindowImage.png` (+ metas).

## Budgets

- Materials: `Tuning.BudgetMaterials` 24 -> 25 and `Tuning.BudgetHouseMaterials` 32 -> 33. The glass material is the only new
  one (shared by every window of the game); the frame costs none. Nothing was freed: the unlit pane material the picture used
  is still the garden ring's. Last audit (rooms_r1, 2026-11-24 13:55) had level11 at 24/24 and title_house at 32/32, both
  with three windows: each would have been one over.
- Draw calls: per level, minus the old pane renderer(s), plus one glass per window, plus one frame renderer per wall line
  with windows (title_house about 101 -> 106 of 160, level11 about 77 -> 82 of 120).
- Triangles: 892 per window (880 frame + 12 glass), at most about 6.3k on test_lights (7 windows), far under 60k.

## Compile

`Builder.SetupAndCompile` (Build/WINDOWS3D.log): no `error CS`; the builder logged `created Assets/Settings/WindowGlass.mat`,
`frame: 1316 vertices, 880 triangles`, `glass: 24 vertices, 12 triangles`, `baked Assets/Resources/WindowModel.asset`.
No test, audit or player build was run.

## To check visually

- Close up on several levels (level1, level7, level12, title_house): the garden through all six panes, the parallax when the
  camera moves, the handle on the room side, the slow moving streaks, no gap between the frame and the cut wall (inside and
  from the title tour outside), the sill proud on the room side.
- The three Walls looks: lowered (frame and glass sink with their wall), see-through and both (frame ghosted at the
  opacity option, panes stay clear with faint streaks, nothing opaque in the panes), near outer wall vanishing.
- Night levels (level20, test_lights): dimmer streaks, the dark garden through the glass.
- The sun patch now entering through the openings (frames and sashes drawn on the floor): intended, visual only.
- Textures off (Options or tests): the old flat window on an uncut wall.

## Test filters to run

`Step39h_ Step50a_ Night_ Lights_a_ Lights_e_ Step95b_ Step22e_ Step22_ Step25_ Dressing_ Step70 Step90 Step36l_ Step36o_
Ceiling_ Spectator MenuCam_`, then LevelAudit (budgets with the new caps) and the built player probe (glass shader check).

## Risks

- `ProbeTestsM42Look.Step22e_` may already trip on the room dressing merged into the floor renderer (its vertices name no
  tiled finish either): pre-existing, not changed here beyond the window frame exemption.
- The sunlight through the openings changes pixel based checks slightly (night and wall renders compare views, not
  absolute values, so they should hold).
