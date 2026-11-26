# BEDROOM (2026-11-24): bedroom low-poly pack, floor decor mode

Nine procedural low-poly items in the game's style, one shared 512 px texture atlas, registered as one furniture look
("dress"), decor on host tops and a new host-less floor decor mode. No level JSON was edited (placement is for the coordinator).

## The pack

Generator: `tools/assets/bedroom_handoff.py` (venv `tools/assets/.venv`, reuses `room_dressing.Model` and its GLB writer);
software previews: `tools/assets/bedroom_preview.py`. Output: `ArtHandoff/Bedroom/` (GLBs, `bedroom_textiles.png`,
`inventory.json`), `Build/bedroom/Bedroom.zip`, `Build/bedroom/preview/` (`bedroom_set.png`, one PNG per item, and the
in-game renders `unity_*.png`). Copied for the game into `Assets/ThirdParty/Models/Bedroom/`.

All items: metres, Y up, front +Z, pivot at the bottom centre, identity node.

| Id | Item | Size (x, y, z m) | Tris | Use |
|---|---|---|---|---|
| bedside_table | bedside table, drawer, open shelf, oak | 0.45 x 0.55 x 0.41 | 144 | look on a nightstand |
| bedside_lamp | ball base, pleated shade, visible bulb | 0.23 x 0.30 x 0.23 | 228 | on nightstand, cabinet, table |
| alarm_clock | twin bell alarm clock | 0.11 x 0.13 x 0.05 | 300 | on nightstand, cabinet, bookshelf, table |
| clothes_heap | jeans and mustard sweater | 0.78 x 0.09 x 0.59 | 242 | floor |
| odd_socks | two odd socks | 0.30 x 0.02 x 0.29 | 144 | floor |
| slippers | pair of plush slippers | 0.24 x 0.08 x 0.28 | 180 | floor |
| laundry_basket | wicker basket, towel over the rim | 0.44 x 0.47 x 0.44 | 243 | floor |
| floor_book_stack | four stacked books | 0.24 x 0.13 x 0.18 | 192 | floor, nightstand, cabinet, table |
| teddy_bear | sitting teddy | 0.20 x 0.27 x 0.19 | 300 | floor, nightstand, cabinet, bookshelf |

Texture: one atlas `bedroom_textiles.png` (512 px, numpy): denim twill, near white V-stitch knit (the vertex colour is the yarn
colour: sweater, socks, slippers, teddy, towel), pale oak, wicker. UVs stay inside their quadrant (no repeat). Everything else
is COLOR_0. Materials: `Bedroom textiles` (atlas), `Bedroom matte`, `Bedroom glaze`, `Bedroom brass`, `Pleated shade` (two sided).

The rug from the brief was left out on purpose: a flat rug reads as the game's silent rug (PRD 4.5) and would mislead.

## In game

- `Core/DecorKindsBedroom.cs` (DecorKinds is now `partial`): the ids, footprints (Unity space, x negated), host kinds, look
  kinds, `FloorHost = "floor"`, `MaxFloorPerLevel = 4`, `FloorWallClearance = 0.06`, the look's size limit (0.7 x 0.75 m),
  the lamp's bulb (y 0.2, glow 0.05). `DecorKinds.cs` only gained the entries in Items, Looks, Meshes and the `default:` arms.
- `WallArray.DressingSlices` + `bedroom_textiles` (one slice), `DressingFolders` + `Assets/ThirdParty/Models/Bedroom/`.
- `DressingBuilder.Sources` + the nine meshes (the atlas is named by the GLB image), `TwoSided` + "Pleated shade", the bedside
  lamp's bulb glows like the linen lamp's. Everything draws with the wall material: no new material, nothing to strip.
- Floor mode (`LevelBuilderDressing.BuildFloorDecor`): `{"kind": "clothes_heap", "host": "floor", "x": 2.1, "z": -1.3,
  "yaw": 20}`, X, Z, Yaw absolute (level frame, like props). Stands on `FloorMap.OnFloor` (split levels), lifted by
  `Tuning.RugHeight` when on a rug. Merged into the floor renderer, Floor layer, no shadow, no collider: no sight, NavMesh,
  route, audit or doorway effect.
- `LevelValidator.CheckFloorDecor`: a floor kind, wholly in one room 6 cm off its bounds, not a bathroom, under no prop, wholly
  on or off each rug, no overlap with other floor items. Items on hosts keep `MaxPerLevel` 6, floor items their own cap of 4.
  The bedside table look: only on a nightstand at most 0.7 m wide and 0.75 m tall.
- `RoomLights.Bedside`: when a `bedside_lamp` item stands on the room's largest nightstand, the bedside glow moves into its
  bulb (0.05 m) instead of the 0.2 m globe at the stand's centre, and `CheckDecorLamps` skips that item.
- `Editor/BedroomShots.cs`: `-executeMethod OutOfSight.Editor.BedroomShots.Shoot` rebuilds the catalogs and renders the
  baked meshes with the wall material.

## Placement mapping (for the coordinator, from a scan of the level JSONs)

Nightstands are 0.45 x 0.55 x 0.40: dress them `"dress": "bedside_table"`; the lamp at about x -0.09 (bed side), the clock
at about x +0.15 (or the clock alone at x +-0.15 when RoomLights keeps its globe in the middle).

| Level | Bedroom props | Bedside prop | Suggested |
|---|---|---|---|
| level2 | Bed, Nightstand, Wardrobe (cabinet 2.0), Desk | yes: Nightstand | dress Nightstand, lamp + clock on it, slippers by the bed |
| level6 | Bed | no | clothes heap or socks on the floor |
| level8 | Lit, Armoire (cabinet 2.0) | no | laundry basket in a corner, clothes heap |
| level9 | Lit, TableDeChevet, Armoire | yes: TableDeChevet | dress it, lamp + clock, slippers |
| level10 | Lit, Commode (cabinet 1.2 x 1.0) | no (Commode) | clock or books on Commode, socks on the floor |
| level11 | Lit, Coiffeuse (cabinet 1.0 x 1.2) | no | clothes heap, slippers |
| level12 | Lit, Armoire | no | laundry basket, clothes heap |
| level14 | Commode, FauteuilMamie (no bed) | no | books on the floor by the armchair (Commode already has the linen lamp) |
| level16 | Lit | no | slippers, socks |
| level17 | Lit | no | clothes heap |
| level18 | Lit (0.75 x 1.6, child size) | no | teddy bear, books on the floor |
| level19 | Lit, Chevet | yes: Chevet | dress it, lamp + clock, slippers |
| level20 | Lit, Chevet | yes: Chevet | dress it, lamp + clock, clothes heap |
| level22 | chambre: Lit, ChevetChambre; boudoir: LitComtesse, ChevetBoudoir | yes: both | dress both, lamp on one, clock on the other, slippers |
| level23 | Lit (0.8 x 1.6), Chevet | yes: Chevet | dress it, clock, teddy bear (child bed) |
| level24 | Lit (0.8 x 1.6) | no (BahutA/B are 2.75 m nightstand-kind consoles: too big for the look) | teddy bear, books |

Not bedside tables: level22 Console5/Console6 and level23 Meuble (1.0 x 0.9 "nightstand" consoles), level24 BahutA/B: the
validator refuses the look on them; the lamp, clock and books may still stand on their tops.

## Verification

One Unity run (`BedroomShots.Shoot`, Build/bedroom.log): compiles clean, wall arrays 512 x 512 x 32 (22 surfaces, 6 dressing,
3 kitchen, 1 bedroom), the nine meshes baked with bounds equal to the footprints above (the lamp 276 triangles in game: its
open shade is doubled). Renders: `Build/bedroom/preview/unity_bedroom_set.png` (game-like angle), `unity_bedroom_top.png`,
`unity_<id>.png`.

## Tests

`ProbeTestsDressing` skips the host-frame check for floor items (they have no host group). Nothing else written or run (the user runs the tests). Existing tests that read `DecorKinds.Meshes` or the slice count
(`DressingTests`, `ProbeTestsDressing`, `ProbeTestsM42Look` via `WallArray.Depth`) now cover the new ids and the new slice.

## A VERIFIER

- In game, the bedside table on a nightstand: the look is turned 180 deg, so the drawer must face the stand's front (-z).
- The bedside lamp on the largest nightstand: the bedside glow should sit inside its bulb, seen through the shade's top.
- Floor items near doors: the validator does not check door leaves; keep floor items about 0.9 m clear of doorways and out of
  patrol paths (people walk through them visually).
- The clothes heap's sweater shows a radial knit pattern at its top (UV pole); judge it from the game camera.
- DressingTests compares the baked bounds with `TryFootprint`: the floor items' footprints are from the inventory.
