# BANANA: bigger, open banana plants

User request (2026-11-24): banana leaves 2x bigger, the banana reshaped into a wide open rosette of rounded blades, a
footprint that matches the canopy, every banana re-placed in a corner or at a corridor end, one banana at the end of
the title house corridor.

## Shape (Assets/Scripts/Runtime/FurnitureKit.cs, BananaMeshes / BananaBlade)

- Same topology as the user's plant, so the same budget: 7 blades of 6 rows x 3 ribs (AddLeafBlade, 32 triangles each,
  224), the pot (110), soil + pseudostem + 7 petioles (62): 396 of the 400 furniture triangles. Same colours, same
  BananaLeafDetail chart once per blade, same UVs.
- Every blade now leaves the crown outward, rises, arches over and droops toward its tip (lift = start + rise sin(pi t)
  - droop t^2). Outer blades reach 0.46 of the footprint and droop to the pot rim; inner ones start higher and reach
  0.34 to 0.38. No upright bunch any more.
- Fuller outline: LeafWidths { 0, 0.8, 1, 0.98, 0.8, 0 } (was { 0, 0.66, 1, 0.94, 0.64, 0 }), a blunt rounded tip.
- The blades are laid out in fractions of the prop footprint (disc of about 0.93 of its width), so the canopy always
  stays inside the Leaves collider box. Size comes from the box: a 1.0 x 1.0 m banana has blades about 0.65 m long and
  0.35 to 0.42 m wide, twice the old ones (the old banana stood in a 0.5 x 0.5 box).
- The pot uses the shared PotBuilder, its width capped at 0.6 m (BananaPotWidth), so a 1 m canopy keeps a 0.36 m pot.
  The collider boxes are unchanged (Pot 0.6 x size, Leaves full size), as ProbeTestsPlantLook asserts.

## Placements (all touched plants now carry "style": "banana")

Footprint 1.0 x 1.0 where it fits; smaller only where the room does not allow it. Ficus: none touched.

| Card | File | Plant | Before (x, z) size | After (x, z) sizeX x sizeZ | Note |
|---|---|---|---|---|---|
| 2 | level2 | Plant (couloir) | (4.2, 2.7) 0.5 | (3.95, 2.45) 1.0 x 1.0 | corridor end |
| 2 | level2 | PlanteChambre2 (chambre) | (-0.1, 0.4) 0.5 | (0.05, 0.45) 1.0 x 0.8 | wardrobe south of it |
| 5 | level5 | PlanteSalon | (3.6, 2.1) 0.5 | (3.45, 1.95) 1.0 x 1.0 | 0.49 m from Habitant station 4 |
| 5 | level5 | PlanteSud | (-3.6, -2.1) 0.5 | (-3.45, -2.0) 1.0 x 0.9 | route cell (-3.25, -1.25) 0.3 m away |
| 6 | level6 | PlanteChambre | (-4.6, -2.7) 0.5 | (-4.45, -2.65) 1.0 x 1.0 | |
| 6 | level6 | PlanteChambre2 | (-1.4, -2.7) 0.5 | (-1.55, -2.95) 1.0 x 1.0 | |
| 7 | level7 | Plant | (2.0, 4.5) 0.5 | (1.95, 4.45) 1.0 x 1.0 | yaw 90 kept |
| 7 | level7 | PlanteBureau | (2.1, -4.6) 0.5 | (1.95, -4.45) 1.0 x 1.0 | |
| 8 | level8 | PlanteChambre | (0.4, 5.1) 0.5 | (0.39, 4.99) 0.7 x 0.9 | no 1 m corner anywhere (door approaches, bed, routes) |
| 9 | level9 | PlanteSalon | (5.1, 0.4) 0.5 | (5.025, 0.55) 0.95 x 1.0 | television east of it |
| 9 | level9 | PlanteChambre | (0.4, 4.9) 0.5 | (0.55, 5.05) 1.0 x 1.0 | |
| 9 | level9 | PlanteSalon2 | (11.3, 0.4) 0.5 | (11.35, 0.55) 1.0 x 1.0 | |
| 11 | level11 | PlanteChambre | (3.8, 4.9) 0.5 | (3.85, 5.05) 1.0 x 1.0 | |
| 11 | level11 | PlanteCuisine | (11.5, 0.4) 0.5 | (11.35, 0.55) 1.0 x 1.0 | |
| 10 | level12 | Plante (couloir) | (9.5, 8.75) 0.5 | (9.35, 8.7) 1.0 x 1.0 | corridor end |
| 13 | level13 | PlanteDirection | (0.4, 9.5) direction 0.5 | (0.55, 5.35) plateau NW 1.0 x 1.0 | moved room: the direction corners hold the desk, bookshelf, door approaches |
| 13 | level13 | PlanteCafeteria | (13.5, 3.6) 0.5 | (13.35, 3.55) 1.0 x 1.0 | |
| 14 | level14 | PlanteCuisine | (17.5, 8.0) 0.5 | (17.4, 7.85) 0.9 x 1.0 | kitchen sink west of it |
| 19 | level22 | PlanteBoudoir | (3.3, 3.4) 0.5 | (3.35, 3.55) 1.0 x 1.0 | |
| 20 | level24 | PlanteCouloir | (13.0, 12.5) 0.5 | (12.85, 12.35) 1.0 x 1.0 | 0.6 m from Rex's stations |
| - | title_house | PlanteBureau | (4.0, 0.5) 0.5 | (3.85, 0.55) 1.0 x 1.0 | |
| - | title_house | PlanteEntree | (5.0, 0.5) 0.5 | (5.05, 0.55) 1.0 x 1.0 | corridor end |
| - | title_house | PlanteCouloir (new) | - | (12.95, 8.2) 0.8 x 1.0, height 1.3 | east end of the couloir, centred across it |

Checks (scratch script, same rules as PLANTS2): box 0.03 m or more inside the wall faces, corner or corridor end gap at
most 0.35 m, no overlap with a prop, decoy, door approach (1.1 m), spawn or exit; stations 0.45 m or more; designer
routes 0.3 m or more from the box; at most 2 plants per room, none in a bathroom; plant counts per level unchanged.

Title house couloir plant: sizeX 0.8 (not 1.0) so Hugo's station (12.25, 8.25) keeps 0.3 m (navmesh agent radius 0.25).
Camera clearance, from the waypoints, the centripetal Catmull-Rom (24 samples per segment) at 0.55 m: the tour turns
south into the kitchen at x 11.78 at most; nearest approach 0.82 m (at (11.74, 7.57)), over the 0.25 m of MenuCam_a.
PlanteBureau and PlanteEntree: 2.20 m. Waypoints unchanged.

## Audit

One Unity run (compile included), Build/banana_r1.log: LevelAudit.RunBatch on level2, 5, 6, 7, 8, 9, 11, 12, 13, 14,
22, 24, -skipFixtures, normal and difficile, -writeRoutes: "aucun defaut" for all 12 levels at both difficulties.
-writeRoutes rewrote the designer routes of those 12 files (the plant edits survived; level5's route now keeps clear of
PlanteSud). Budgets are unchanged in count, because no plant changed style: level22 is at 32 of 32 materials, level24 at
31 of 32, level12 and level8 at 24 of 24, all as before. Draw calls are at most 150 of 160 (level22). Slack (-slack) was
not measured.

Tests were not run (the user runs them).

## A VERIFIER

- Look at the new banana in game (PlantLook_ shots): blade droop, the pot under a 1 m canopy, blade overlap.
- level8 PlanteChambre is 0.7 x 0.9 (squeezed rosette); level2 PlanteChambre2 1.0 x 0.8, level5 PlanteSud 1.0 x 0.9,
  level9 PlanteSalon 0.95 x 1.0, level14 PlanteCuisine 0.9 x 1.0, title couloir 0.8 x 1.0.
- level13 PlanteDirection now stands in the plateau (name kept); the direction room has no plant.
- Title house: Hugo's station 4 (12.25, 8.25) is 0.3 m from the new couloir plant (he never walks there on the title,
  the game is paused).
- -writeRoutes changed the designer routes of the 12 audited files: the route and rush replays must pass on them.
- Window frames and sills were not a constraint: check blades near windows.
- The test fixtures (test_lights, test_m5_house_mock8) still hold position-picked bananas at 0.5 x 0.5: they draw the
  new shape at half size.
