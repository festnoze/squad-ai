# M8 room variety plan (product owner request, 2026-11-19)

Request (translated): vary the rooms (their function and their objects: a bathroom with a bathtub and a washbasin, a
kitchen with a table, a sink, an oven, etc.), give them fitting floors; vary the floors without changing their
property (besides parquet and tile: create a carpet, a marble and another parquet image) and apply them sensibly;
rework the existing levels to improve their game design with these rooms; add varied secondary lighting (bathroom
neon, warm living room light).

This file is the shared contract of the M8 agents. Field names, kinds and ids below are fixed: use them as written.

## 1. Survey (2026-11-19)

- 24 levels, 106 rooms: chambre 17, couloir 15, cuisine 15, salon 14, entree 11, bureau 7, galerie 4, salle 3,
  sejour 2, sdb 2, then one-offs (veranda, direction, plateau, cafeteria, accueil, reunion, openspace, archives,
  cafet, hall, boudoir, bibliotheque, office, galerie_est, vestibule, couloir_est). level1 has no room.
- Floors: `"floor"` is the gameplay property (`hard` 86, `soft` 20: it changes the noise rules). `"floorFinish"` is
  visual only: `tile` (16 rooms), otherwise the default look. Walls: `"wallFinish"` crepi (default), sage,
  limewash, grasscloth, wallpaper.
- Props are boxes with a `kind` (sofa, chair, table, counter, cabinet, bookshelf, wardrobe, stool, plant, box, ...)
  and an optional `model` (only a few Kenney GLBs: sofa, chair, stool, armchair, floor lamp, rugs, doormat). Beds are
  `sofa` boxes named "Lit" (14), the two bathtubs are `counter` boxes, kitchens are counters and a table.

## 2. Room types

New optional room field `"type"`; when missing it is inferred from the room id:

| type | ids inferred | key objects (new kinds in bold) | floor finish | light mood |
|---|---|---|---|---|
| bathroom | sdb, salle_de_bain, bain | **bathtub**, **washbasin** (with mirror), **toilet**, towel rack | marble or tile | cool neon |
| kitchen | cuisine, cafet, cafeteria, office | **kitchen_sink**, **stove** (oven + hob), **fridge**, table + chairs, counters | tile | neutral white |
| dining | salle, salle_a_manger | table + chairs, sideboard (cabinet) | herringbone | warm pendant |
| living | salon, sejour, veranda | sofa, armchair, **coffee_table**, **tv_unit**, bookshelf, fireplace | herringbone or parquet; carpet if soft | warm |
| bedroom | chambre, boudoir | **bed**, **nightstand**, wardrobe, dresser (cabinet) | carpet if soft, else parquet | dim warm |
| study | bureau, direction, bibliotheque, archives, reunion, openspace, plateau | desk (table), office chair, bookshelf, filing cabinet | herringbone | neutral |
| hall | entree, vestibule, accueil, hall | console, shoe cabinet, coat rack, doormat | marble | warm sconce |
| corridor | couloir*, galerie* | console, plant, runner rugs | parquet | warm sconce |
| other | anything else | | default | neutral |

Implemented (lights agent): `RoomDef.DeclaredType` is the JSON `"type"` (written only when set, validated against
`RoomTypes.All`); `RoomDef.Type` is what code reads: the declared type, else `RoomTypes.Infer(id)`. Inference ignores
case and French accents; a key matches the whole id or the id followed by a non-letter (`chambre2`, `sdb-haut`,
`salle_est`); `couloir`, `galerie` and `salle_de_bain` are stems (`couloir_est`, `galerie_est`, `salle_de_bains`); the
longest key wins (`salle_de_bain` over `salle`). Every room of the 24 levels infers a type other than `other`, so
phase 2 only needs `"type"` where the id says something else (an `atelier` used as a living room).

## 3. New objects (prop kinds)

`bathtub`, `washbasin`, `toilet`, `kitchen_sink`, `stove`, `fridge`, `coffee_table`, `tv_unit`, `bed`, `nightstand`.
Gameplay: static props like the existing ones: a collider that blocks the furniture and the inhabitants, `occluder`
set per prop in the level (tall ones such as the fridge block sight), never player furniture, never a hiding spot
(only wardrobes hide). A `bed` must behave exactly like today's `sofa` named "Lit" with the same size, so swapping
the kind changes the look only. Look: CC0 models (Kenney Furniture Kit, through the ModelCatalog) when available,
otherwise procedural (FurnitureKit). Every one fits the triangle budget and adds no more than one material.

Implemented (props agent): `PropKinds` (Core) lists every kind; the validator now rejects an unknown prop kind. Every
kind is built procedurally (`FurnitureKitRooms.cs`, one renderer per material); four of them also have an optional
Kenney model, used only when the prop names it in `"model"` (otherwise, and with ModelKit off, the procedural look).
Orientation: at yaw 0 the front (doors, oven, foot of the bed) faces -z and the back stands against a +z wall, as the
sofa and the cabinet: back on a -z wall is yaw 180, on a +x wall yaw 90, on a -x wall yaw 270. Every part stays inside
the box; colliders (only when `occluder`, the default) follow the solid body. The only new material is the plain white
ceramic (`FurnitureKit.CeramicMaterial`, shared by all of them and by the Kenney fridge); everything else reuses Wood,
Plaster, Linen, Upholstery, Metal or the household's near-black.

| kind | default size (x, y, z) | solid (colliders) | look | model id (optional) |
|---|---|---|---|---|
| `bathtub` | 1.7 x 0.6 x 0.75 | full footprint up to the rim (0.555) | ceramic tub, mixer on the back rim at +x | none (Kenney's is 1 204 tris) |
| `washbasin` | 0.6 x 1.8 x 0.45 | the vanity and basin, up to 0.85 | wood vanity, ceramic basin, tap; mirror against the wall above, standing on the back deck (only when y >= 1.3) | none (over budget) |
| `toilet` | 0.4 x 0.8 x 0.65 | footprint up to the lid (0.42) + the cistern to the top | ceramic, closed lid | none (over budget) |
| `kitchen_sink` | 1.2 x 1.08 x 0.6 | up to the worktop = y - 0.18 (0.9) | a counter with a metal basin; y includes the 0.18 m tap | none (over budget) |
| `stove` | 0.6 x 0.9 x 0.6 | full box | white enamel, black hob, oven door | none (over budget) |
| `fridge` | 0.7 x 1.8 x 0.7 | full box | white, two doors, handles on +x | `kenney.fridge` (9 draw calls vs 3) |
| `coffee_table` | 1.0 x 0.42 x 0.55 | full box | wood, shelf below | `kenney.coffee_table` (2 vs 1) |
| `tv_unit` | 1.4 x 1.1 x 0.45 | the cabinet (y x 0.45) + the screen | wood cabinet, 16:9 screen on top (none when y - cabinet < 0.25) | none |
| `bed` | 1.6 x 0.55 x 2.0 | exactly the `sofa` colliders of that size | headboard on +z, duvet over the foot | `kenney.bed` (10 vs 3) |
| `nightstand` | 0.45 x 0.55 x 0.4 | full box | wood, drawer and door, metal knobs | `kenney.nightstand` (6 vs 2) |

Gameplay mapping: nothing in the code switches on these kinds besides their builder (vision, the NavMesh, the audit
and the probes read the colliders; sitting works on any prop by name; decoys and hiding are not props), so each one
behaves as a static prop of its collider shape: `bed` as `sofa`; `bathtub`, `stove`, `fridge`, `coffee_table`,
`nightstand` as a solid `cabinet`/`counter` box; `kitchen_sink` and `washbasin` as a `counter` of their worktop or
basin height; `toilet` and `tv_unit` as a low block with a taller part on the back. Level 2's "Bed" must stay without a
model (ModelM3Tests: levels 1 to 3 keep their beds procedural). `Assets/Resources/Levels/test_rooms.json` shows all ten
(not in levels.json); `Assets/Editor/PropShots.cs` renders a level's rooms and room objects
(`-executeMethod OutOfSight.Editor.PropShots.Shoot -propShots <dir> -propLevel <id>`); shots in `docs/m8/props/`.

## 4. Floor finishes (visual only, the `floor` property never changes)

Existing: default parquet, `tile`. New `floorFinish` values: `carpet` (wall-to-wall carpet, warm grey-beige loop
pile; only on `soft` floors, so a carpet always means quiet), `marble` (white-grey marble slabs with fine veins; hard),
`herringbone` (darker oak herringbone parquet; hard). Seamless, real-colour images with normal maps, tiled at a
believable size in metres, one shared material each, no red or orange (the player furniture is the only red thing).

M9 (2026-11-19): four more hard-floor-only values, `lightoak`, `verde`, `ivorytile` and `tealtile`, and the assignment of
the nine looks over the 24 levels: docs/m9/FLOORS_WALLS.md.

## 5. Secondary lighting (visual only, never read by the rules)

One or two fixtures per room by type: bathroom: cool neon tube (about 6500 K, slightly blue); kitchen: neutral white
(4000 K); living and dining: warm pendant or wall light (2700 K); bedroom: dim warm bedside light (2400 K); study:
neutral desk light; hall and corridor: warm sconce. Unshadowed point or spot lights with a small emissive fixture
mesh. The floor lamp mechanic stays as it is (switching the lamp off dims every light of its room: LampLight.cs).
Quality tiers: fewer or no secondary lights on the low tier (Android), within the per-object light limit.

Implemented (lights agent, `Assets/Scripts/Runtime/RoomLights.cs`, built by `LevelBuilder.Build` under the level root as
`RoomLights`):

| type | first fixture | second fixture (large room) | light colour | pool |
|---|---|---|---|---|
| bathroom | cool neon tube on the wall over the `washbasin` (over its mirror), else on the best free wall (1.95 m) | none | (0.80, 0.89, 1.00), about 6500 K | 0.65 |
| kitchen | neutral strip on the wall over the longest `counter` / `kitchen_sink` / `stove` run against a wall (worktop + 0.5 m), else a wall strip | wall strip if area >= 18 m2 | (1.00, 0.94, 0.86), about 4000 K | 0.7 |
| dining | warm globe lamp in the middle of the largest `table`, else a wall sconce | wall sconce if area >= 18 m2 | (1.00, 0.80, 0.60), about 2700 K | 0.6 |
| living | warm wall sconce (1.85 m) | a pair on the longest free wall if area >= 18 m2 | (1.00, 0.80, 0.60), about 2700 K | 0.6 |
| bedroom | globe lamp on the largest `nightstand`, else a reading light beside the bed head (`bed`, or `sofa` named "Lit..."), else a wall light | none | (1.00, 0.76, 0.54), about 2400 K | 0.4 |
| study | globe desk lamp on the corner of the largest `table` nearest a wall, else a wall sconce | wall sconce if area >= 18 m2 | (1.00, 0.93, 0.82), neutral | 0.5 |
| hall | warm wall sconce | a pair if area >= 18 m2 | (1.00, 0.81, 0.62) | 0.6 |
| corridor | warm wall sconce | a pair if the corridor is 5 m long or more | (1.00, 0.81, 0.62) | 0.55 |
| other | none | none | | |

- Placement is automatic: a wall fixture keeps 0.35 m from the corners, 0.3 m from a doorway, 0.15 m from a window, and
  never hangs over a prop within 0.6 m of its wall that reaches 0.35 m below it (a wardrobe, a bookshelf, a fridge); the
  longest wall wins, as near its middle as it is free. Nothing hangs in mid-air (a pendant hid the player furniture from
  the high camera in the first shots): dining gets a table lamp. A wall fixture's glow goes with its wall line (M7
  Walls option): it shows only while that line stands, so a lowered wall never leaves it floating and a see-through wall
  never carries it opaque (its light stays). No collider, Default layer: no rule, ray or NavMesh ever meets a fixture.
- Every light is an unshadowed spot. There is no ceiling, so the source stands higher than its fixture (2.45 m and
  0.35 m off a wall fixture's wall; 1 m over a lamp), for wider, softer pools. A wall light aims at the floor half way
  across the room (at most a source height out), a lamp straight down (15 degrees away from a wall within 1.2 m); the
  cone stops short of the wall behind the source, so nothing leaks into the next room. The intensity gives the pool
  centre the "pool" above (added linear light; the sun gives a lit floor about 1), the range is 1.8 times that reach
  (2.4 to 4.5 m), and the intensity is capped so the surface under the light (a counter, a sofa back, the lamp's table)
  gets at most 1.2. Glow meshes: a wall sconce 0.16 x 0.24 x 0.10 m box, a tube 0.62 m, a strip as long as the counter
  run (0.4 to 1.2 m), globes 0.2 to 0.26 m.
- Optional room field `"lightWall"`: `"+x"`, `"-x"`, `"+z"` or `"-z"` puts the room's wall fixtures on that wall (the
  side of the room, as in `RoomSide`); `"none"` gives the room no fixture and no light. Absent: automatic.
- Quality tiers: Bas keeps the glowing fixtures and switches every secondary light off; Moyen keeps the first light of
  each room (Mobile_RPAsset is Forward, 4 additional lights per object); Haut keeps them all (PC_RPAsset is Forward+).
  The tier is applied at build and again whenever the Qualité option changes (a string compare per frame, no
  allocation). Only `Light.enabled` changes, so LampLight's room dimming (every enabled point or spot light standing in
  the lamp's room drops to `Tuning.LampOffLight`) dims these lights too and restores them exactly.
- Budgets: the glows of a level draw as at most two renderers (one per colour family, combined): the warm family uses
  the floor lamp's glow material (`Emissive FFCC75x1.9`), the cool one the window pane's (`Emissive BFE3F5x1.6`). A level
  gains at most 2 draw calls and 0 to 2 materials (PlayMode `Lights_e` asserts it on every manifest level and logs the
  table). Level8 is now at 24 of 24 materials and level21 at 156 of 160 draw calls: phase 2 re-dressing there must
  make room first (or give a room `"lightWall": "none"`).- Throwaway check level: `Assets/Resources/Levels/test_lights.json` (not in levels.json), one room of each type; shots
  in `docs/m8/lights/` (PlayMode `ProbeTestsM8Lights.Lights_z_Shots`, explicit).

## 6. Ownership (phase 1: code and art; phase 2: levels)

- Floors agent: the three floor images and normal maps, the `floorFinish` values, their materials and import settings.
- Props agent: the ten new kinds (LevelDef/LevelJson/LevelValidator kinds, LevelBuilder props, FurnitureKit or
  ModelCatalog models, licences).
- Lights agent: the room `type` field and its inference (LevelDef/LevelJson/LevelValidator), the light moods and
  fixtures, the quality tier rules.
- Phase 2 level agents (after phase 1): set room types, re-dress each room with fitting objects, floors and walls,
  and improve the game design, then prove each level: audit at Normal and Difficile, `-writeRoutes`, route replays,
  budgets (PRD 7.4: 24 materials and 120 draw calls on small levels, 32 and 160 on houses).
