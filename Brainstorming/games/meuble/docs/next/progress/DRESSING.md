# DRESSING (2026-11-24): room accessories and living room furniture

Two delivered packs, integrated in one pass:

- RoomDressing (Build/room-dressing/RoomDressing.zip, ArtHandoff/RoomDressing/inventory.json): open book, photo frame, sofa
  throw, ceramic mug, magazine stack, TV remote, key dish.
- LivingRoomFurniture (Build/living-room-furniture/LivingRoomFurniture.zip, ArtHandoff/LivingRoomFurniture/inventory.json):
  walnut coffee table, walnut media console, flat screen TV, tabletop pothos, linen table lamp.

Both ZIPs are extracted (GLB and texture PNGs only) into `Assets/ThirdParty/Models/RoomDressing/` and
`Assets/ThirdParty/Models/LivingRoomFurniture/`. The user's own Unity check of the models was a throwaway preview project
(Build/*/unity-preview.log), not an import in this project, so nothing was reused.

## How it is modelled

Data (`Assets/Scripts/Core`):

- `LevelDef.Decor` (JSON `"decor"`, optional, written only when not empty): a list of `DecorDef { kind, host, x, z, yaw }`.
  `host` is a prop name; `x`, `z`, `yaw` are in the host's frame; the item stands on the host's top (`sizeY`). A throw's `z`
  is measured from the backrest centre line, yaw 0 hangs its long side behind the back, 180 in front (used when the back is
  against a wall).
- `PropDef.Dress` (JSON `"dress"`): a furniture look drawn instead of the procedural visual (`walnut_coffee_table` on a
  `coffee_table`, `walnut_media_console` on a `tv_unit`, or a counter or cabinet at most 0.7 m tall). The prop keeps its
  colliders, occluder flag and position; `FurnitureKit.Build` runs with no visual, exactly as under a catalog model.
- `DecorKinds`: the kinds, their footprints (Unity space, from the inventories), the host kinds each may stand on, the looks
  and the kinds they may dress, the throw's backrest fit.
- `LevelValidator.CheckDressing`: unknown kind or look, unknown host, wrong host kind, off the host's top, two items of one
  host overlapping, an item in a bathroom, more than 6 items, a look on the wrong kind or too tall, a look with a model.

Rendering, zero material and zero draw call:

- `Editor/DressingBuilder` reads the GLBs directly (x negated, V flipped, winding turned) and bakes one mesh per model into
  `Assets/Resources/DressingLibrary.asset` (`Runtime/DressingLibrary`). Every vertex names how the wall material
  (`OutOfSight/Wall Finishes`) draws it: a flat colour (UV1.x = -1, UV2 = the GLB vertex colour, linear; the lamp bulb glows a
  little) or a dressing image of the wall arrays tinted by its vertex colour (UV1.x = slice + 1, UV2.x = -1, UV2.yzw = tint).
  Open sheets (pothos leaves, lamp shade, throw) are doubled back to back. The remote's red button is mapped off red as
  ModelKit maps model reds (PRD 7.2).
- `WallArray.DressingSlices`: the six images (book spread, photo, plaid, walnut, pothos leaf, linen) are appended to the two
  wall Texture2DArrays after the 22 surface slices (512 each, ASTC 6x6 on Android, the arrays' own import), with a flat normal
  each. `WallArray.Depth` = 28; `Ready` checks it. The shader tints dressing texels by UV2.yzw and never floor-dusts them
  (`FLOOR_DUST_LAST_FINISH`).
- `LevelBuilderDressing` (LevelBuilder is now partial): decor items join the level's floor renderer (wall material, Floor
  layer, no shadow), so they cost nothing; the looks and the TV form one "Dressing" renderer (wall material, the prop's
  layer, shadowed) which replaces the procedural renderers of the props it dresses. No collider anywhere. Without the wall
  material or with `DressingLibrary.Disabled`, nothing is dressed.
- `RoomLights.Lamps`: the globes of the table, desk and bedside lamps; the builder records any decor item standing in one in
  `LevelInstance.DressingProblems`, which the audit turns into failures. The audit also prints an "habillage" note per level.

## Placement

Planned by script against the inventory rules: hosts only where a matching prop exists, the front of a cabinet, counter,
shelf or nightstand is its local -z, a table's front faces away from its nearest wall, the book and the frame face the front,
the mug sits to the book's right, and nothing stands where RoomLights puts a lamp (the dining table centre, the study desk's
wall corner, the bedroom's largest nightstand). Never in a bathroom.

| Card | File | Decor (item@host) | Dressed props |
|---|---|---|---|
| 1 | level1 | throw@Sofa, book@Table, mug@Table, pothos@Table | - |
| 2 | level2 | key dish@Shoes, frame@Console, lamp@Console, book@Desk, mug@Desk | - |
| 3 | level3 | book@Table, mug@Table, frame@Sideboard, pothos@Sideboard | - |
| 4 | level4 | throw@Sofa, lamp@Table, frame@Buffet, pothos@Buffet | - |
| 5 | level5 | throw@Sofa, magazines@CoffeeTable, remote@CoffeeTable | TV (tv_unit) -> media_console + TV, CoffeeTable (coffee_table) -> coffee_table |
| 6 | level6 | throw@Sofa, magazines@CoffeeTable, remote@CoffeeTable, book@Table, mug@Table | CoffeeTable (coffee_table) -> coffee_table |
| 7 | level7 | book@DeskC, mug@DeskC, frame@DeskD, pothos@DeskB | - |
| 8 | level8 | throw@Canape, remote@MeubleTV, key dish@MeubleTV, book@TableCuisine, mug@TableCuisine | MeubleTV (counter) -> media_console |
| 9 | level9 | throw@Canape, magazines@TableBasse, remote@TableBasse, key dish@MeubleChaussures, book@Bureau | Television (tv_unit) -> media_console + TV, TableBasse (coffee_table) -> coffee_table |
| 10 | level12 | throw@Canape, key dish@MeubleChaussures, frame@MeubleHaut, book@TableCuisine, mug@TableCuisine | Television (counter) -> media_console |
| 11 | level11 | throw@Canape, magazines@TableBasse, remote@TableBasse, frame@Coiffeuse, pothos@Coiffeuse | TableBasse (coffee_table) -> coffee_table |
| 12 | level15 | throw@Canape, key dish@Console, frame@Cheminee, book@BureauTable, mug@BureauTable | - |
| 13 | level13 | book@BureauChef, mug@BureauChef, frame@BureauChef, key dish@Accueil, pothos@Accueil | - |
| 14 | level14 | throw@Canape, frame@Etagere, pothos@Etagere, key dish@Meuble, lamp@Commode | - |
| 15 | level18 | frame@Buffet, key dish@Buffet, pothos@Armoire, mug@Plan | - |
| 16 | level17 | throw@Canape, frame@BuffetBas, pothos@BuffetBas, key dish@Meuble, book@BureauTable | - |
| 17 | level25 | throw@CanapeExpo, book@TableOuest, magazines@TableEst, pothos@Caisse | - |
| 18 | level19 | throw@CanapeSalon, magazines@TableBasse, remote@TableBasse, book@TableSalle, key dish@EtagereMaman | MeubleTV (tv_unit) -> media_console + TV, TableBasse (coffee_table) -> coffee_table |
| 19 | level22 | key dish@Console5, lamp@Console6, book@TableSalon, mug@TableSalon, pothos@ArmoireGalerie1 | - |
| 20 | level24 | frame@BahutA, lamp@BahutB, book@TableSalle, mug@TableSalle | - |
| menu | title_house | throw@Canape, frame@Cheminee, book@BureauTable, mug@BureauTable, key dish@Console | - |

## Budgets

LevelAudit batch (Build/dressing.log, normal and difficile, -skipFixtures, no -writeRoutes): 0 defect on the 20 played
levels; every level builds all its decor items, none in a lamp. Draw calls and materials (before: plants2_r2 audit):

| Level | Draw calls | Materials |
|---|---|---|
| level1 | 46/120 (46) | 21/24 (21) |
| level2 | 66/120 (66) | 19/24 (19) |
| level3 | 74/120 (74) | 20/24 (20) |
| level4 | 60/120 (60) | 23/24 (23) |
| level5 | 53/120 (56) | 21/24 (22) |
| level6 | 62/120 (62) | 23/24 (23) |
| level7 | 56/120 | 19/24 |
| level8 | 76/120 (77) | 24/24 (24) |
| level9 | 74/120 (77) | 22/24 (22) |
| level12 | 95/160 (96) | 22/32 (22) |
| level11 | 79/120 (79) | 24/24 (24) |
| level15 | 65/120 | 22/24 |
| level13 | 109/160 (109) | 30/32 (30) |
| level14 | 100/160 | 26/32 |
| level18 | 61/120 | 21/24 |
| level17 | 111/160 | 28/32 |
| level25 | 120/120 (120) | 24/24 (24) |
| level19 | 118/160 | 28/32 |
| level22 | 150/160 | 32/32 |
| level24 | 134/160 (134) | 31/32 (31) |

The decor adds no material and no draw call (it rides the floor renderer); a dressed coffee table or TV unit replaces
its procedural renderers by the shared "Dressing" renderer, so the levels with looks went down (level5 -3 draw calls and
-1 material, level9 -3, level8 and level12 -1). No level had to drop items.

## Tests (written, not run)

- EditMode `DressingTests`: `--filter Dressing_` (levels validate with 2 to 5 items and the planned looks, every validator
  rule fails when it should, the library is baked for every kind with the DecorKinds bounds, the arrays hold 28 slices).
- PlayMode `ProbeTestsDressing`: `--filter Dressing_` (every item on its host's top, none in a lamp, merged into the floor
  renderer; colliders identical to the undressed level; no material added, at most one draw call added, within caps).
- `ProbeTestsM42Look` now expects `WallArray.Depth` slices in the wall arrays.

## A VERIFIER

- In game: the throw's long side behind the backrest (most sofas) and in front for the two sofas whose back touches a wall
  (level4, level6): there its fringe may touch the seat by about 2 cm.
- The vertex colours are read as linear (glTF COLOR_0): compare the mug, the remote and the TV frame with the delivery's
  preview renders.
- The media console on a 0.6 m TV unit is squashed to the procedural cabinet height (0.27 m) with a small TV above, as the
  procedural screen was; level19's 1.1 m unit is close to native.
- The dressed looks draw on the Occluder layer from one combined renderer under the level root: check that x-ray and any
  prop fade still read right around the dressed coffee tables and TV units.
- The decor casts no shadow (it is merged into the floor renderer); judge whether small items read as grounded.
