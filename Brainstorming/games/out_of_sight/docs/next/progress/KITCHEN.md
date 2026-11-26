# KITCHEN (2026-11-24): kitchen furniture and utensils

Ten new low poly kitchen assets, generated procedurally (no download, no licence) by `tools/assets/kitchen_handoff.py`
(tools/assets/.venv, numpy + Pillow, the shared `Model`/`GLB` writer of room_dressing.py). Same pipeline and format as the
RoomDressing and LivingRoomFurniture packs (docs/next/progress/DRESSING.md).

- Pack: `ArtHandoff/Kitchen/` (10 GLB, 3 PNG, inventory.json), ZIP `Build/kitchen/Kitchen.zip`.
- In the project: `Assets/ThirdParty/Models/Kitchen/` (the GLBs and PNGs of the pack).
- Previews: `Build/kitchen/preview/` (`kitchen_set.png`, `kitchen_set_top.png`, one PNG per item, `kitchen_ingame*.png`),
  rendered by `OutOfSight.Editor.KitchenShots.Shoot` (editor batch method, wall material, no PlayMode).

GLB convention: metres, Y up, front +Z, pivot at the bottom centre (contact point), identity node, plain colours in
COLOR_0. In Unity (x negated) the pan handles point to -x.

## The items

| Id | Role | Size W x H x D (m) | Triangles | Textures |
|---|---|---|---|---|
| kitchen_base_cabinet | look (counter) | 0.60 x 0.90 x 0.60 | 260 | worktop, steel |
| kitchen_drawer_cabinet | look (counter) | 0.60 x 0.90 x 0.60 | 332 | worktop, steel |
| kitchen_sink_cabinet | look (kitchen_sink) | 0.80 x 1.08 x 0.60 | 362 | worktop, steel |
| kitchen_range | look (stove) | 0.60 x 0.90 x 0.60 | 346 | steel |
| kitchen_tall_cabinet | look (cabinet, wardrobe) | 0.594 x 2.00 x 0.594 | 168 | steel |
| saucepan | decor | 0.359 x 0.150 x 0.218 | 240 | steel |
| frying_pan | decor | 0.437 x 0.045 x 0.267 | 268 | none (cast iron colour) |
| stock_pot | decor | 0.308 x 0.247 x 0.250 | 232 | steel (lid, handles) |
| kettle | decor | 0.268 x 0.253 x 0.200 | 222 | none (cream enamel) |
| cutting_board | decor | 0.397 x 0.034 x 0.250 | 252 | oak, steel (knife) |

Base modules share one build: a 10 cm toe kick recessed 5 cm, carcass to 0.86, 2 cm painted sage fronts, brushed steel bar
handles, a 4 cm worktop to 0.90 m over the full 0.60 depth. The sink unit's worktop is at 0.90 and its tap top at 1.08, the
game's kitchen_sink box (worktop 0.18 m under the box top). The range: black glass hob with four burners flush at 0.90, a
knob band, a steel oven door with its window and bar handle.

Why these five furniture: what the cutaway camera sees of a kitchen is its worktop line, so the five dress the props kitchens
already have (counter, kitchen_sink, stove, and the kitchen pantry wardrobe). A wall cabinet was left out: it would hide the
worktop and its utensils from above, and no prop stands for it. Why these five utensils: they read from above by silhouette
(round lids, a long pan handle, a board with orange carrot slices); single spoons and knives are too thin at that distance.

Textures (512 px, tileable, procedural, shared): `kitchen_brushed_steel.png` (streaks along u), `kitchen_worktop.png` (ivory
composite with speckles), `kitchen_oak.png` (blond oak, grain along u). UVs are box projected per face so the steel streaks
and the oak grain stay horizontal.

## How the game uses them

Exactly the DRESSING mechanism, no new material, shader or renderer kind (so nothing to strip in a player build):

- `WallArray.DressingSlices` gains the three images (three more slices in the wall arrays; a bedroom pack added its own after them) and `DressingFolders` the
  Kitchen folder. `ModelCatalogBuilder.Build` appends them to the arrays; `DressingBuilder` bakes the ten meshes into
  `Assets/Resources/DressingLibrary.asset` (now 22 entries).
- `DressingBuilder` now reads the slice of each textured material from its GLB image name (glTF `images[].name`, the PNG
  stem), since a kitchen GLB may carry two images (worktop and steel). The old packs resolve to the same slices as before.
  Textured vertices are drawn without metallic (the wall material's dressing path has no metallic slot): the steel reads
  by its albedo.
- `DecorKinds`: the five utensils are decor items (footprints from the inventory, Unity space) with host kinds: pans and
  pot on a `stove` or a `counter`, the kettle also on a `table`, the board on a `counter` or a `table`. Never on a
  `kitchen_sink` (its box top is the tap's). The five modules are looks: base and drawer cabinets on a `counter`, the sink
  unit on a `kitchen_sink`, the range on a `stove`, the pantry on a `cabinet` or a `wardrobe`.
- `LevelBuilder.DressKitchen`: a kitchen look is laid as a run of modules (`DecorKinds.KitchenRun`) along the prop's longer
  horizontal side, scaled together to its exact length, depth and height (one y scale from the tallest module, so the
  worktops stay level). A base or drawer look alternates door and drawer modules about every 0.6 m; a sink look centres the
  sink module and fills the rest with base modules when the prop is 0.3 m or more longer than 0.8 m. The fronts face local -z
  (run along x) or local -x (run along z: turn the prop by 180 degrees if its room side is +x; the collider box is the same).
  The prop keeps its colliders and occluder flag, as any look.
- `LevelValidator`: a kitchen look needs a prop height of 0.75 to 1.0 m (base, drawer, range), 0.85 to 1.15 m (sink) or
  1.5 to 2.3 m (pantry).

## Suggested placement (no level edited: COHERENCE and BANANA hold the level files)

From a scan of the level files (kind, name, size). Played levels first; level10, 16, 20, 21, 23 are not in the card list.

| Look | Props it would dress |
|---|---|
| kitchen_base_cabinet (or drawer) on `counter` | level11 Plan 2.4, level18 Plan 2.0, level19 Plan 0.7, level22 Comptoir 0.6, level24 Plan 0.6, level12 Plan 0.6x3.0 and level8 Plan 0.6x2.4 (runs along z: check the front side); also level10 Plan, level20 Plan and PlanEst, level23 Plan |
| kitchen_sink_cabinet on `kitchen_sink` | level3 Counter 2.4, level14 Plan 2.4, level15 Plan 2.4, level17 Plan 2.4, title_house Plan 2.4 (sink with cabinets each side), level19, level22, level24 Evier 1.2; also level10, level16, level20, level23 |
| kitchen_range on `stove` | level19, level22, level24 Cuisiniere; also level20, level23 |
| kitchen_tall_cabinet on `wardrobe` | level20 ArmoireCuisine (1.0 x 2.0 x 0.6) |

Not kitchen, never dress: the fireplaces (Cheminee counters), consoles, office reception and shop till counters (Accueil,
Caisse), the low Buffet and Bench counters.

Utensils: on the stoves (frying pan front, kettle or saucepan back, pot back), on dressed counters (board, pot, kettle),
board or kettle on a kitchen table (TableCuisine). They count in `DecorKinds.MaxPerLevel` (6) with the existing decor, and
must keep clear of RoomLights' lamps like any decor.

## Preview review (two KitchenShots runs)

Run 1 (Build/kitchen.log): every module baked within budget, the dressed test_rooms validated with no dressing issue and
built 8 placements (the 1.2 m sink as sink + base module), no dressing problem. Fixed after looking at it: the frying pan
vanished on the black hob from the game camera (iron and handle lightened), the worktop's cloudy blotches read as dirt
(calmed), the oak rings were too stripy (softened). Run 2 re-rendered the previews with these.

## Tests

None run (the user runs them). Existing ones that cover this without change: `DressingTests` (`Dressing_`: every
`DecorKinds.Meshes` id baked with the TryFootprint bounds, wall arrays at `WallArray.Depth` slices), `ProbeTestsDressing`.
The kitchen footprints in `DecorKinds.TryFootprint` are those of the inventory (Unity space).

## A VERIFIER

- In game, once placed: the long-z counters (level8, level12): the fronts face local -x; turn the prop by 180 if the room is
  on its +x side.
- The 2.4 m kitchen_sink props are 0.9 m tall (no room for the tap): the whole run is squashed to a 0.75 m worktop, as the
  procedural sink was (0.72). Raising those props to 1.08 would give a true 0.90 worktop.
- The brushed steel has no metallic on the wall material (textured dressing path): compare with the flat metallic handles
  of the procedural furniture.
- The pantry (0.594 wide) on level20's 1.0 m wardrobe is stretched 1.7 times in width: its doors read wide.
- The wall arrays grow by three 512 slices (ASTC on Android): check the texture memory line of the audit.
