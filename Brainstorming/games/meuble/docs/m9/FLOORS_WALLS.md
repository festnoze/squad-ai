# M9 floors and walls (product owner request, 2026-11-19)

Nine floor looks, spread over the 24 levels with at most three per level, coherent with each room's type, plus varied
wall finishes. Visual only: every room's gameplay `"floor"` (hard or soft, the noise rules) is unchanged, and the rugs
(silent zones) are untouched.

## 1. The nine floor looks

| Family | Look | `floorFinish` | Image | Repeat | Floor |
|---|---|---|---|---|---|
| Parquet | honey oak planks (default) | none | `parquet.png` | 1.8 m | hard |
| Parquet | dark oak herringbone | `herringbone` | `floor_herringbone.png` | 0.7 m | hard |
| Parquet | wide light oak planks (new) | `lightoak` | `floor_lightoak.png` (own creation) | 2.0 m (8 boards of 25 cm) | hard |
| Carpet | plain soft carpet (default soft look) | none | `carpet.png` | 0.6 m | soft |
| Carpet | wall-to-wall loop pile | `carpet` | `floor_carpet.png` | 1.0 m | soft |
| Marble | white-grey veined marble | `marble` | `floor_marble.png` | 0.6 m slab | hard |
| Marble | dark green verde marble (new) | `verde` | `floor_verde.png` (own creation) | 1.6 m (four 0.8 m slabs) | hard |
| Bathroom tile | small ivory tiles (new, product owner) | `ivorytile` | `tile_bathroom_small_ivory.png` | 1.2 m (16 x 16, 7.5 cm tiles) | hard |
| Bathroom tile | large teal tiles (new, product owner) | `tealtile` | `tile_bathroom_large_teal.png` | 1.6 m (4 x 4, 40 cm tiles) | hard |

The generic kitchen `tile` (`tile.png`, 25 cm tiles, 1.5 m) stays for kitchens. Every value but `carpet` is hard floor
only (`RoomDef.HardFloorFinishes`, LevelValidator); a soft room shows one of the two carpets.

The new maps are made by `tools/assets/make_floor_finishes.py` (`--only lightoak verde tile_bathroom_small_ivory
tile_bathroom_large_teal`). The two bathroom images were checked: their grout is split over the two wrap edges (3 px in
total for the ivory, about 7 px for the teal against 5 to 6 px inside), so they tile as given; the script resizes them
to the 512 colour map through a 3 x 3 wrapped tiling (no clamped border) and builds the normal map from the grout grid.

## 2. Assignment rules

- Bathrooms and WC: a bathroom tile or a marble. Kitchens: tile or a marble. Bedrooms and living rooms: a carpet (soft
  rooms only) or a parquet. Halls: a marble or a parquet (a soft hall: a carpet). Corridors, offices and dining rooms: a
  parquet (a soft office or corridor: a carpet, since a hard look may never hide a quiet floor). One exception, for the
  material cap: level16's kitchen shares the herringbone of the rest of its flat (section 5).
- At most three distinct floor looks per level.
- Material caps (PRD 7.4: 24 on small levels, 32 on houses): until walls 4 each distinct floor or wall finish was one
  material. Since walls 4 (section 7) every wall finish and every floor look is a slice of one material: the number of
  looks a level shows no longer costs materials.

## 3. Level table

Walls 4 (section 7) reassigned every wall and moved every wall and floor look into one material: the Walls column and
the Materials column below are the state before it; section 7 holds the current walls per room and the current counts.

Floors and walls by look, with the rooms that use them. Materials: measured by PlayMode `Lights_e` after the change
(lights included), against the level's cap; updated for the tiled walls (section 5). The editor `LevelAudit` counts one
more on a level with a dog (12, 16, 17, 20, 23, 24): each vision cone counts the colour it shows in play, and the dog's
is its own.

| Level | Floor looks | Floors | Walls | Materials |
|---|---|---|---|---|
| 1 | 1 | parquet (room) | crepi (room) | 20 / 24 |
| 2 | 2 | parquet (couloir); light oak (chambre) | crepi (couloir); pinstripe (chambre) | 21 / 24 |
| 3 | 2 | herringbone (salle); tile (cuisine) | arches (salle); subway tile (cuisine) | 20 / 24 |
| 4 | 2 | verde (entree); herringbone (salon) | crepi (entree); grasscloth (salon) | 23 / 24 |
| 5 | 1 | light oak (salon) | arches (salon) | 22 / 24 |
| 6 | 2 | herringbone (salon); light oak (chambre) | crepi (salon, chambre) | 23 / 24 |
| 7 | 1 | herringbone (bureau) | pinstripe (bureau) | 20 / 24 |
| 8 | 2 | parquet (chambre, couloir, salon); verde (cuisine) | crepi (all) | 24 / 24 |
| 9 | 3 | light oak (chambre, salon); tile (cuisine); marble (entree) | wallpaper (chambre); limewash (cuisine); crepi (salon); travertine (entree) | 23 / 24 |
| 10 | 3 | parquet (chambre, couloir); herringbone (salon, veranda); marble (cuisine) | wallpaper (chambre); crepi (couloir); subway tile (cuisine); sage (salon); travertine (veranda) | 31 / 32 |
| 11 | 3 | light oak (chambre, couloir); herringbone (salon); tile (cuisine) | crepi (all) | 23 / 24 |
| 12 | 3 | parquet (chambre, couloir); marble (cuisine, entree); herringbone (salon) | grasscloth (chambre); crepi (couloir); subway tile (cuisine); travertine (entree); sage (salon) | 26 / 32 |
| 13 | 3 | plain carpet (direction); herringbone (plateau, couloir); marble (cafeteria, accueil) | grasscloth (direction, plateau); crepi (couloir, cafeteria); limewash (accueil) | 31 / 32 |
| 14 | 3 | parquet (sejour, chambre, couloir); ivory tile (salle, bathroom); marble (cuisine, entree) | sage (sejour); wallpaper (chambre); white tile (salle); crepi (cuisine, couloir, entree) | 31 / 32 |
| 15 | 3 | light oak (bureau, chambre, couloir, salon); tile (cuisine); verde (entree) | grasscloth (bureau); pinstripe (chambre); crepi (couloir); sage (salon); subway tile (cuisine); limewash (entree) | 30 / 32 |
| 16 | 1 | herringbone (salon, chambre, couloir, cuisine) | crepi (all) | 23 / 24 |
| 17 | 3 | parquet (chambre, couloir); herringbone (sejour, bureau); marble (cuisine, entree) | pinstripe (chambre); crepi (the others) | 31 / 32 |
| 18 | 3 | carpet (couloir, chambre); verde (entree); tile (cuisine) | wallpaper (couloir, chambre); limewash (entree); subway tile (cuisine) | 21 / 24 |
| 19 | 3 | carpet (chambre, salon, galerie); marble (entree, cuisine); teal tile (sdb) | grasscloth (chambre); sage (salon, entree); crepi (galerie); limewash (cuisine); travertine (sdb) | 32 / 32 |
| 20 | 3 | herringbone (salon, bureau); marble (cuisine, entree, sdb); plain carpet (couloir, chambre) | sage (salon, entree); subway tile (cuisine); white tile (sdb); crepi (couloir); arches (chambre); grasscloth (bureau) | 29 / 32 |
| 21 | 3 | plain carpet (bureau, archives); parquet (reunion, openspace, couloir, hall); tile (cafet) | grasscloth (bureau, reunion); crepi (the others) | 31 / 32 |
| 22 | 3 | plain carpet (chambre, boudoir, bibliotheque); herringbone (galerie, salon, galerie_est); verde (office, vestibule) | crepi (all) | 32 / 32 |
| 23 | 3 | plain carpet (chambre, couloir, entree); marble (bureau, a bathroom; cuisine); parquet (galerie, salon) | crepi (all) | 31 / 32 |
| 24 | 3 | plain carpet (chambre, chambre_enfants, couloir_est, entree); parquet (couloir, galerie, salle); marble (sdb, cuisine) | wallpaper (chambre, galerie); crepi (couloir, couloir_est, cuisine, entree); sage (chambre_enfants, sdb, salle) | 31 / 32 |

Coverage (levels using each look): parquet 1, 2, 8, 10, 12, 14, 17, 21, 23, 24; herringbone 3, 4, 6, 7, 10, 11, 12,
13, 16, 17, 20, 22; light oak 2, 5, 6, 9, 11, 15; plain carpet 13, 20, 21, 22, 23, 24; carpet 18, 19; marble 9, 10, 12,
13, 14, 17, 19, 20, 23, 24; verde 4, 8, 15, 18, 22; ivory tile 14; teal tile 19 (kitchen tile 3, 9, 11, 15, 18, 21).
Levels 12, 13, 14, 15, 17, 19, 20, 21 and 24 had four or five floor looks before and now have three; levels 13, 17 and
24 dropped from their material cap to one under it (8 and 22 stay at their cap: swaps only). Two levels were over their
cap by the audit, which counts the dog's cone colour (section 5): 23 (its new sage bedroom went back to the crepi) and
16 (its kitchen tile went to the flat's herringbone). `title_house.json` (the menu backdrop) is unchanged.

## 4. Shots

`docs/m9/floors/`: one steep view per room (`<level>_room_<room>.jpg`) and the start view (`<level>_start.jpg`) of
levels 4, 14, 15, 18, 19 and 24, rendered by `OutOfSight.Editor.WallShots.Shoot -wallShots docs/m9/floors
-wallLevels level14,level19,level15,level4,level18,level24 -wallLooks lowered -wallRooms` (the two flags are new). They
cover all nine looks: the ivory tiles (level14 salle), the teal tiles (level19 sdb), the light oak (level15 salon),
the verde (level15 and level4 entree), the herringbone (level4 salon), the marble (level24 cuisine and sdb), both
carpets (level18, level24) and the default parquet (level24 galerie). Every floor repeats at its metric size, no
stretching, no visible seam.

## 5. Tiled walls (product owner images, 2026-11-19)

Two more wall finishes from the product owner's own images, each a whole wall: tiles above a trim above paint.

| `wallFinish` | Image | For | Look | Scale |
|---|---|---|---|---|
| `whitetile` | `wall_bathroom_white_pastel_blue.png` | bathrooms | raised white square tiles, black grout (two cracked, one chipped corner), a thin white trim, pastel blue embossed paint | 27 cm tiles (ten per 2.7 m), trim at 0.99 to 1.03 m |
| `subwaytile` | `wall_kitchen_ivory_sage.png` | kitchens | ivory 3:1 subway tiles in a running bond, a rounded trim, sage paint | 67.5 x 22.5 cm tiles (four per course), trim at 1.09 to 1.13 m, just above a worktop |

Scale: the band must sit at one height and never repeat up the wall, and the image must not be stretched, so one
repeat is the wall's whole height, `Tuning.TiledWallHeight` = 2.7 m (every room's `wallHeight`), on both axes (square
images). A wall face's V is its height above the floor (`LevelBuilder.WallUvOffset`, the pieces over a door included),
so V runs 0 to 1 from the floor to the top; the maps are imported Repeat on U, Clamp on V (`ModelCatalogBuilder`,
`TextureLibrary.ClampsVertically`), so the wall top never samples the paint and the floor never samples the tiles.
`LevelValidator` rejects a tiled finish on walls taller than 2.7 m (the clamped top row would stretch).

Seams: both tile fields wrap as given (the grout line is split over the two side edges, its width the inner joints');
the paint and the trim did not (the bathroom's embossed paint jumped visibly at the wrap, the kitchen's trim and paint
faintly). `tools/assets/make_wall_finishes.py --only wall_bathroom_white_pastel_blue wall_kitchen_ivory_sage` keeps the
sources as given and, in the derived maps only, cross-fades those rows within 48 px (about 10 cm) of the wrap with a
copy rolled by half the width (variance preserving): the paint's horizontal edgeStep drops from 1.69 to 0.88
(bathroom) and from 1.81 to 1.07 (kitchen), 1 being invisible. The kitchen tiles' edgeStep (11.9) is a joint edge lying
on the wrap in every other course, as at every inner joint, not a seam. The 512 maps are resized wrapped across and
clamped up; the normal maps come from the grout (recessed, a soft bevel; the bathroom's cracks and chip too), the
trim's bead and the paint's grain. One material per finish, at smoothness 0.3 (`Tuning.TiledWallSmoothness`: glazed
tiles and matte paint share it).

Assignment (visual only: every room's hard or soft floor and every rug untouched, so gameplay is unchanged): `subwaytile` on 6 of the 18
kitchens (levels 3, 10, 12, 15, 18, 20), `whitetile` on 2 of the 5 bathrooms (level14 salle, level20 sdb). Kept for
variety: limewash kitchens 9 and 19, crepi kitchens elsewhere, the bathrooms of 19 (limewash, teal tiles), 23 (crepi) and
24 (sage). Budget: a swap where the room's finish was its level's last user (3, 14; 20's kitchen and bathroom both left
limewash, one material for two), else one material more on a level with room under its cap (10, 12, 15, 18). Levels
8, 16, 22 and 23 (at their cap) and 17 and 24 (at their cap by the audit) got no tiled wall.

Level 23 (found by the audit while this was done): it showed 33 materials against 32, normal and difficile. Not the
bookshelf contents nor the heads (its Lit and Emissive materials are the same as at 12:30); the cause is the M9 floors and
walls pass of its level JSON: the kitchen and the bathroom took the marble (Colour Tile out, Colour Marble in) and the
bedroom the sage (Colour Sage in), one material more, 32 by the probe and 33 by the audit, which also counts the dog's
cone colour. Fix by a swap: the bedroom's wall went back to the crepi; the audit now reads 32 / 32 in both difficulties.

Level 16 (found by the same audit run over every dog level): 25 materials against 24, both difficulties, already so
before the tiled walls and before the M9 floors (12:30: 24 by the probe with its kitchen's Colour Tile, plus the dog's
cone colour). Its walls are all crepi, so the only finish to swap was a floor: the kitchen's tile went to the herringbone
of the rest of the flat (a hard floor still, so the noise rules are unchanged): Colour Tile out, the audit reads 24 / 24.

Measured after the change: EditMode 506 / 506; PlayMode Step22c, 22d, 22e, 22f, Step39h, Step50a, Step61a, Lights_e,
Step72a pass (rerun after the level16 swap). `Lights_e` (lights included): level3 20 / 24, level10 31 / 32, level12
26 / 32, level14 31 / 32, level15 29 / 32, level16 23 / 24, level18 21 / 24, level20 29 / 32, level23 31 / 32; draw
calls at most 140 / 160 (level20) and 68 / 120 (level18). `LevelAudit -skipFixtures -difficulty normal,difficile`, no
defect in either difficulty: level3 20 / 24, level10 30 / 32, level12 26 / 32, level14 31 / 32, level15 29 / 32, level16
24 / 24, level17 32 / 32, level18 21 / 24, level20 30 / 32, level23 32 / 32, level24 31 / 32 (draw calls at most
155 / 160, level24, unchanged). Every dog level is audited. On every level without a dog audited today (3, 10, 14, 15,
18 here, 19, 21 and 22 in the 14:34 run) the audit counted no more than `Lights_e`, which keeps all 24 levels under
their caps.

Shots (`docs/m9/walls2/`): eye-level views from inside the rooms, one wall each, rendered with the new
`WallShots.Shoot -wallShots TestResults/walls2 -wallLevels level3,level14,level20,level18 -wallLooks none -wallInside
cuisine,salle,sdb` (the flag `-wallInside` is new, as `-wallRoomPitch`; `none` never cuts a wall), plus one gameplay view
(`level14_game_view_lowered.jpg`). Looked at: no stretching (square tiles stay square, the 3:1 subway tiles stay 3:1),
no visible seam on the 4.4 to 5.9 m walls (two wraps on the longest), the trim at one height on every wall of a room and
over the doors (bathroom: washbasin and bathtub rim height; kitchen: just above the worktop), the tiles reaching the wall
top in whole rows. One thing the image itself brings: its two cracked tiles and chipped corner repeat every 2.7 m along a
long bathroom wall (`level20_sdb_whitetile_north.jpg`).

## 6. Printed and stone walls (product owner images, 2026-11-19)

Three more wall finishes from the product owner's own images. None has a band (no dado, no trim): each is an all-over
pattern, so unlike the tiled walls it repeats both ways (Repeat on U and V, any wall height), at a metric scale, like the
four procedural finishes. A face's V is still its height above the floor, so a pattern row sits at the same height in
every room.

| `wallFinish` | Image | For | Look | Scale (one square repeat) |
|---|---|---|---|---|
| `travertine` | `wall_travertine_greige.png` | entrances, halls, living rooms, bathrooms | warm greige honed travertine, cloudy, pores in horizontal streaks, no joint | 1.2 m: pores of 1 to 4 cm, clouds of about 30 cm |
| `arches` | `wall_deco_arches_blue.png` | living and dining rooms, bedrooms | slate blue triple arches printed on a cream linen paper, a 4 x 4 lattice | 1.8 m: arches 26 cm tall, 45 cm apart both ways, six rows per 2.7 m wall exactly |
| `pinstripe` | `wall_linen_pinstripe_olive.png` | bedrooms, offices | beige linen wallpaper, eight olive and taupe pinstripe pairs | 1.2 m: a pair every 15 cm |

`Tuning.DetailTileTravertine`, `DetailTileArches`, `DetailTilePinstripe`. The papers are matte as the other wall finishes
(0.1); the travertine is honed stone, `Tuning.TravertineSmoothness` 0.2.

Seams (`tools/assets/make_wall_finishes.py --only wall_travertine_greige wall_deco_arches_blue
wall_linen_pinstripe_olive`, sources kept as given): the arches wrap on plain paper, as given (edgeStep 0.63 in the
source, 0.35 in the 512 map). The travertine (1.18) and the linen pinstripe (0.79, but a faint low-frequency jump of the
weave across the top and bottom wrap) are cross-faded in the derived maps only, rows and columns within 48 px (about 5 cm)
of each wrap, with a copy rolled by half the image along that axis, variance preserving around the mean taken along the
blend axis (a column's mean for the top and bottom wrap, so a vertical stripe keeps its colour); the 512 maps read 1.07
and 0.60. The maps are resized through a 3 x 3 wrapped tiling. Normal maps: the luminance high-pass (the stone's pores
and grain at xy rms 0.12; the linen weave at 0.08 and 0.05), the printed ink masked out so the stripes and the arches
lie flat on the paper.

Assignment (visual only: floors, rugs and gameplay unchanged), each finish used at least three times, on several
levels:

| Level | Room | Before | After | Materials |
|---|---|---|---|---|
| 2 | chambre | sage | pinstripe | swap (sage's last user) |
| 3 | salle (dining) | wallpaper | arches | swap |
| 5 | salon | sage | arches | swap |
| 7 | bureau | grasscloth | pinstripe | swap |
| 9 | entree | crepi | travertine | +1 (22 to 23 / 24) |
| 10 | veranda | limewash | travertine | swap |
| 12 | entree | limewash | travertine | swap |
| 15 | chambre | grasscloth | pinstripe | +1 (grasscloth stays in the bureau) |
| 17 | chambre | sage | pinstripe | swap (level at its cap) |
| 19 | sdb | limewash | travertine | +1 (limewash stays in the kitchen) |
| 20 | chambre | wallpaper | arches | swap |

Travertine on 4 levels (9, 10, 12, 19), arches on 3 (3, 5, 20), pinstripe on 4 (2, 7, 15, 17). The older finishes keep
variety: wallpaper 9, 10, 14, 18, 24; sage 10, 12, 14, 15, 19, 20, 24; grasscloth 4, 12, 13, 15, 19, 20, 21; limewash 9,
13, 15, 18, 19. Levels 8, 16, 22 and 23 (at their cap, all crepi walls: a swap there would have meant changing a floor)
and 24 (155 / 160 draw calls) are untouched; 17, at its cap, only swapped.

Audit (`LevelAudit -auditLevels level2,level3,level5,level7,level9,level10,level12,level15,level16,level17,level19,
level20,level23,level24 -skipFixtures -difficulty normal,difficile`): no defect in either difficulty, the same counts
in both. Materials and draw calls: level2 20 / 24 (60 / 120), level3 20 / 24 (66), level5 22 / 24 (48), level7 19 / 24
(50), level9 23 / 24 (91), level10 30 / 32 (82 / 160), level12 26 / 32 (97), level15 30 / 32 (101), level16 24 / 24
(81 / 120), level17 32 / 32 (116 / 160), level19 32 / 32 (138), level20 30 / 32 (141), level23 32 / 32 (133), level24
31 / 32 (155). The level table (section 3) shows these audit counts for 9, 15 and 19, the levels that gained a material
(no dog: the audit counts no more than the probe).

Tests: EditMode 506 / 506; PlayMode Step22c, 22d, 22e (every surface seen at its own repeat, the three new ones
included), 22f, Step39h, Step50a, Step61a (the three new normal maps) and Step72a (credits) pass. `Lights_e` failed in
four runs, each time on a different level and check (level23 draw calls +3, level2 then level7 "renderers added besides
the glows", level10 draw calls +3), level2 passing in the first run with its pinstripe and level23 untouched here: the
known flaky glow count (a transient renderer after the restart), not a material, which the audit above measures on
every changed level.

Shots (`docs/m9/walls3/`, rendered with `WallShots.Shoot -wallShots TestResults/walls3 -wallLevels
level3,level5,level7,level9,level10,level15,level19,level20 -wallLooks none -wallInside
salle,salon,bureau,chambre,entree,veranda,sdb`): arches (level3 salle, level5 salon, level20 chambre), pinstripe (level7
bureau, level15 chambre), travertine (level9 entree, level10 veranda, level19 sdb). Looked at: no stretching (the arches
keep their proportions, the stripes stay vertical and evenly spaced), no visible seam on walls of 4.4 to 10.4 m, the six
arch rows at the same heights on every wall of a room and from one room to the next (the top row just under the wall
top, the bottom one just above the skirting), the travertine reading as honed stone, a little cooler and smoother than
the crepi seen through its doors.

## 7. Walls 4: one material for every room surface, varied walls (product owner request, 2026-11-19)

The complaint: within a level the walls almost always showed the same texture. The blocker was the material budget
(PRD 7.4): every wall finish was its own URP Lit material, so several levels at their cap could take no new finish.

### 7.1 One material, the finishes in Texture2DArrays

- Every wall finish (the crepi included) and every floor look is a 512 x 512 slice of two Texture2DArrays,
  `Assets/Art/Environment/Arrays/wall_colours.png` (sRGB) and `wall_normals.png` (linear RGB): 22 slices in
  `WallArray.Slices` order (12 wall looks, then 10 floor looks), stacked by `ModelCatalogBuilder` from the same 512 maps
  as the library's entries (a slice that is not 512 would be resampled), imported as 2D arrays (mipmapped, Repeat both
  ways, compressed per platform: BC7 on PC, ASTC 6x6 on Android, never downscaled).
- One opaque material draws them, `Arrays/WallFinishes.mat` (shader `OutOfSight/Wall Finishes`,
  `Assets/Settings/WallFinishes.shader`): every wall face, fill, cap, closure, outside face and stub, every room floor,
  doorway threshold, floor under a wall, platform and ramp. Each vertex names its look (`WallArray.Tag`): UV1 = (slice + 1,
  repeats per metre, smoothness, normal strength), UV2 = the tiled walls' band layout (7.3). UV0 stays in metres, so the
  tiling is metric with the hardware wrap and every sample takes the gradients of that continuous UV (no seam). The
  combined meshes keep UV1 and UV2 (`PrimitiveKit.CombinedMesh`), so the two faces of a shared wall are one renderer even
  when their rooms differ, and every floor of a house is one renderer: draw calls went down too.
- Lighting is URP's own (`UniversalFragmentPBR`: main light and cascaded shadows, additional lights in Forward and
  Forward+, SSAO, reflection probes, fog), with URP's shadow caster, depth and depth normals passes; the tangent frame is
  rebuilt per pixel from screen derivatives (the combined meshes carry no tangent). Target 3.5 (`#pragma require
  2darray`): OpenGL ES 3.0, Vulkan, Metal, DirectX 11, the project's Android floor. The two materials are referenced by
  the library in Resources, so their shaders and variants ship.
- The see-through look: one material too, `Arrays/WallSeeThrough.mat` (`OutOfSight/Wall See-through`, alpha blended, no
  depth write, queue Transparent-1), now `WallFader.GhostMaterial`: a faded part of the room surface material shows its
  slices (`_ArrayFinish` 1 in its property block), any other faded part (door frames, baseboards, windows, leaves) its own
  2D maps, as the URP Lit see-through material did. The lowered look draws the sinking copy with the part's own material,
  unchanged. All four looks (lowered, see-through, both, none) and the opacity option work as before (7.5).
- Budget counting: nothing special-cased. `LevelAudit`, the probe and the tests count distinct materials as before; the
  room surface material and the see-through one are each counted once (comment in `LevelAudit.CountDraws`), so the number
  of wall finishes and floor looks a level shows no longer costs materials. The floors joined the arrays because the
  levels whose walls were all crepi (8, 16, 22, 23) gained the wall material while their crepi material stays (plaster
  furniture uses it): their floor materials pay for it. Without the library (or with `TextureLibrary.Disabled`) the walls
  and floors fall back to the URP Lit materials.
- The probe's "non URP shader" check accepts the two project shaders (`Probe.IsProjectWallShader`).

### 7.2 Two new finishes

| `wallFinish` | Image | Look | Scale |
|---|---|---|---|
| `quatrefoil` | `wall_quatrefoil.png` | sage quatrefoils, terracotta four-point stars, cream paper (an 8 x 8 lattice, wraps as given) | 1.35 m: a quatrefoil every 16.9 cm, sixteen rows per 2.7 m wall |
| `sageribbed` | `wall_sage_ribbed.png` | a sage painted fluted panel, 36 vertical ribs, real relief (wraps cross-faded, half the width is 18 ribs exactly) | 1.44 m: a rib every 4 cm, satin (0.2) |

Both are all-over patterns (no band): they repeat both ways on any wall height. Maps derived by
`tools/assets/make_wall_finishes.py --only wall_quatrefoil wall_sage_ribbed` (sources kept as given).

### 7.3 Room by room check: what was wrong and how it was fixed

Shots from the game camera (the player furniture moved to each room's centre, the four sides, lowered look) and at eye
level (four walls per room, look none) of every room of levels 3, 9, 14, 15 and 20 before (`docs/m9/walls4/verify/before/`)
and of levels 3, 9, 11, 14, 15, 20, 23 and 24 after (`verify/after/`), every room type and every finish at least twice,
level 20 and level 24 whole; compared with the source images.

1. Tiles far too big. Mapped once over the 2.7 m wall, the bathroom squares were 27 cm and the subway tiles 67.5 x
   22.5 cm, a kitchen that read as a breeze block wall. Fix: the tiled walls are laid as bands by the shader
   (`WallBandUv`): the paint from the floor to the trim, read back and forth inside the paint stretch of the image (never
   stretched), the trim once at its height (bathroom 0.99 m, kitchen 1.09 m: `Tuning.WhiteTileTrimHeight`,
   `SubwayTileTrimHeight`), then the image's tile field (six whole rows, seven whole courses, each wrapping on its grout
   line, measured by `make_wall_finishes.band_rows`, `TextureLibrary.BandOf`) repeated up to the wall top at real sizes:
   15 cm squares (1.5 m per image width) and 30 x 10 cm subway tiles (1.2 m), every other subway field shifted half a
   tile so the running bond never breaks across a repeat. Pieces over doors and fills keep V = height above the floor,
   so the trim sits at one height everywhere.
2. Repeating defects. At 15 cm the source's two cracked tiles and its chipped corner came back every 1.5 m along and
   0.93 m up the wall, a regular pattern of black marks. Fix: in the derived maps only (`heal_defects`), each tile cell far
   from the median cell is replaced by the cell half the image width away (five tiles, the grid stays aligned); the
   source stays as given.
3. Same texture everywhere (the complaint): every room reassigned (7.4).

Checked and found right (before and after): the all-over finishes upright, never stretched or rotated (arches open
downward, pinstripes and ribs vertical, quatrefoils square), seamless on walls up to 17.9 m, the pattern continued over
door pieces and fills, every outside face and wall end the crepi (no finish bleeds to the outside or the next room), the
finishes split exactly at the shared walls' centre lines. The colours read warmer than the source images (the pastel blue
paint turns teal, the sage olive) under the game's warm sun: lighting, not mapping; the colour maps' means match the
sources.

### 7.4 Assignment and level table

Rules: every bathroom white tile (one per level, so no travertine alternate), every kitchen subway tile; bedrooms
pinstripe, wallpaper, quatrefoil, sage; living and dining rooms arches, grasscloth, limewash, sage ribbed; entrances,
halls and corridors travertine, quatrefoil, limewash and the crepi; offices pinstripe, grasscloth, sage ribbed. Two rooms
that share a wall never show the same finish. Visual only: floors, rugs and gameplay unchanged. Materials and draw calls
by `LevelAudit -skipFixtures -difficulty normal,difficile` (all 24 levels, no defect in either difficulty).

| Level | Rooms: wall finish | Finishes | Materials (normal / difficile) | Draw calls |
|---|---|---|---|---|
| 1 | room (other): wallpaper | 1 | 19 / 19 of 24 | 38 of 120 |
| 2 | couloir (corridor): quatrefoil; chambre (bedroom): pinstripe | 2 | 18 / 18 of 24 | 57 of 120 |
| 3 | salle (dining): arches; cuisine (kitchen): subway tile | 2 | 17 / 17 of 24 | 63 of 120 |
| 4 | entree (hall): travertine; salon (living): grasscloth | 2 | 21 / 21 of 24 | 49 of 120 |
| 5 | salon (living): sage ribbed | 1 | 20 / 20 of 24 | 48 of 120 |
| 6 | salon (living): limewash; chambre (bedroom): wallpaper | 2 | 21 / 21 of 24 | 51 of 120 |
| 7 | bureau (study): pinstripe | 1 | 18 / 18 of 24 | 50 of 120 |
| 8 | chambre (bedroom): quatrefoil; couloir (corridor): travertine; cuisine (kitchen): subway tile; salon (living): arches | 4 | 23 / 23 of 24 | 68 of 120 |
| 9 | chambre (bedroom): wallpaper; cuisine (kitchen): subway tile; salon (living): sage ribbed; entree (hall): travertine | 4 | 18 / 18 of 24 | 82 of 120 |
| 10 | chambre (bedroom): pinstripe; couloir (corridor): quatrefoil; salon (living): grasscloth; cuisine (kitchen): subway tile; veranda (living): limewash | 5 | 24 / 24 of 32 | 69 of 160 |
| 11 | chambre (bedroom): sage; couloir (corridor): limewash; salon (living): arches; cuisine (kitchen): subway tile | 4 | 21 / 21 of 24 | 76 of 120 |
| 12 | chambre (bedroom): quatrefoil; couloir (corridor): crepi; cuisine (kitchen): subway tile; salon (living): sage ribbed; entree (hall): travertine | 5 | 20 / 20 of 32 | 84 of 160 |
| 13 | direction (study): pinstripe; plateau (study): grasscloth; couloir (corridor): quatrefoil; cafeteria (kitchen): subway tile; accueil (hall): travertine | 5 | 28 / 28 of 32 | 103 of 160 |
| 14 | sejour (living): arches; chambre (bedroom): wallpaper; salle (bathroom): white tile; cuisine (kitchen): subway tile; couloir (corridor): crepi; entree (hall): limewash | 6 | 26 / 26 of 32 | 94 of 160 |
| 15 | bureau (study): sage ribbed; chambre (bedroom): quatrefoil; couloir (corridor): crepi; salon (living): grasscloth; cuisine (kitchen): subway tile; entree (hall): travertine | 6 | 23 / 23 of 32 | 85 of 160 |
| 16 | salon (living): limewash; chambre (bedroom): pinstripe; couloir (corridor): quatrefoil; cuisine (kitchen): subway tile | 4 | 24 / 24 of 24 | 81 of 120 |
| 17 | chambre (bedroom): wallpaper; couloir (corridor): travertine; sejour (living): sage ribbed; bureau (study): pinstripe; cuisine (kitchen): subway tile; entree (hall): quatrefoil | 6 | 29 / 29 of 32 | 111 of 160 |
| 18 | couloir (corridor): quatrefoil; entree (hall): travertine; chambre (bedroom): sage; cuisine (kitchen): subway tile | 4 | 16 / 16 of 24 | 59 of 120 |
| 19 | chambre (bedroom): pinstripe; salon (living): arches; galerie (corridor): limewash; entree (hall): quatrefoil; cuisine (kitchen): subway tile; sdb (bathroom): white tile | 6 | 25 / 25 of 32 | 124 of 160 |
| 20 | salon (living): grasscloth; cuisine (kitchen): subway tile; entree (hall): travertine; couloir (corridor): crepi; chambre (bedroom): quatrefoil; bureau (study): pinstripe; sdb (bathroom): white tile | 7 | 24 / 24 of 32 | 125 of 160 |
| 21 | bureau (study): pinstripe; reunion (study): sage ribbed; openspace (study): grasscloth; couloir (corridor): crepi; archives (study): sage ribbed; cafet (kitchen): subway tile; hall (hall): travertine | 6 | 29 / 29 of 32 | 144 of 160 |
| 22 | chambre (bedroom): wallpaper; boudoir (bedroom): quatrefoil; galerie (corridor): travertine; salon (living): arches; bibliotheque (study): grasscloth; office (kitchen): subway tile; galerie_est (corridor): limewash; vestibule (hall): crepi | 8 | 31 / 31 of 32 | 144 of 160 |
| 23 | chambre (bedroom): sage; bureau (bathroom): white tile; galerie (living): sage ribbed; salon (living): arches; couloir (corridor): quatrefoil; cuisine (kitchen): subway tile; entree (hall): travertine | 7 | 31 / 31 of 32 | 131 of 160 |
| 24 | chambre (bedroom): pinstripe; couloir (corridor): limewash; chambre_enfants (bedroom): quatrefoil; sdb (bathroom): white tile; galerie (corridor): travertine; salle (dining): arches; couloir_est (corridor): crepi; cuisine (kitchen): subway tile; entree (hall): quatrefoil | 8 | 28 / 28 of 32 | 143 of 160 |

Finishes per level: 1 to 8, 4.4 on average; on the houses (4 rooms or more) 4 to 8, 5.6 on average. Every finish is used
on at least three levels: crepi 12, 14, 15, 20, 21, 22, 24; arches 3, 8, 11, 14, 19, 22, 23, 24; grasscloth 4, 10, 13,
15, 20, 21, 22; limewash 6, 10, 11, 14, 16, 19, 22, 24; pinstripe 2, 7, 10, 13, 16, 17, 19, 20, 21, 24; quatrefoil 2,
8, 10, 12, 13, 15, 16, 17, 18, 19, 20, 22, 23, 24 (entrances 17, 19, 24; corridors 2, 10, 13, 16, 18, 23; bedrooms and
the boudoir 8, 12, 15, 20, 22, 24); sage 11, 18, 23; sage ribbed 5, 9, 12, 15, 17, 21, 23; travertine 4, 8, 9, 12, 13,
15, 17, 18, 20, 21, 22, 23, 24; wallpaper 1, 6, 9, 14, 17, 22; subway tile in all 18 kitchens; white tile in all 5
bathrooms (14, 19, 20, 23, 24). `title_house.json`: bureau grasscloth, chambre quatrefoil, couloir crepi, salon arches,
cuisine subway tile, entree travertine.

Before walls 4 the levels at or near their cap were 8 (24 / 24), 16 (24 / 24), 17, 19, 22, 23 (32 / 32); now the highest
are 16 (24 / 24, all four rooms of different finishes), 22 and 23 (31 / 32), with fewer draw calls nearly everywhere
(level 19: 138 to 124, level 20: 141 to 125, level 24: 155 to 143).

### 7.5 Tests and shots

- `LevelAudit -skipFixtures -difficulty normal,difficile` (no `-writeRoutes`): all 24 levels, no defect in either
  difficulty (the counts above). The audit's material failure now lists the materials it counted.
- EditMode 506 / 506. PlayMode: ProbeTestsM7Walls (Step70a to 70h: the four looks, the opacity, the stubs, the x-ray
  silhouette through a standing wall), Step22c (every wall and floor renderer of the room surface material, no property
  block, every finish asked for shown), Step22d, Step22e (every wall and floor look at its own repeat, measured per
  vertex), Step22f (the two arrays: 22 slices of 512, mipmapped, Repeat, compressed, sRGB and linear; the two materials on
  them), Step39h, Step50a, Step61a (the kitchen tile floor's finish per vertex), Lights_e and Step72a (credits) pass.
- Lights_e had failed on a different level in each run for a while (+3 draw calls, or "renderers added besides the
  glows"). Its new diagnostic named the cause: a watcher's vision cone (level 16's dog, "VisionCone Rex") shown in one of
  the two snapshots and not the other, as the dog sleeps or wakes; not the lights and not a budget. The comparison now
  leaves the cones out (as Step39h does); the budgets are still asserted on everything drawn.
- Shots: `docs/m9/walls4/` (`WallShots.Shoot -wallShots docs/m9/walls4 -wallLevels level20,level24,level14,level8
  -wallLooks lowered,both,translucent -wallRooms -wallSize 1280x800 -wallJpg`): the four high views, the start view and a
  steep view of every room, in the lowered, both and see-through looks. `docs/m9/walls4/verify/before/` and `after/`
  (`-wallLooks lowered,none -wallGame -wallInside all -wallNoOverview -wallSize 960x600 -wallJpg`, the new flags: `-wallGame`
  the game camera on every room, `-wallInside all` every room, `-wallNoOverview`, `-wallSize`, `-wallJpg`).

### 7.6 The grasscloth looked stretched sideways (main menu, 2026-11-19)

The complaint: on the title house (bureau: grasscloth) the back wall and the near right wall looked heavily stretched
horizontally. What was checked, every finish against its source image (`docs/m9/stretch/finishes_source_vs_game.png`):

- Mapping: right. UV0 is in metres on every wall piece (U along the wall, V up), one repeats-per-metre value scales both
  axes, every source is square (the kitchen image 1252 x 1254, 0.16 %), so the 512 slices keep their aspect. In game the
  grasscloth's 0.9 m panel seams fall 0.9 m apart and the pinstripes, ribs, arches, quatrefoils and sprigs keep their
  proportions and spacing.
- Filtering: not the cause. The arrays are trilinear, aniso 2, and the PC "Haut" tier forces anisotropic filtering on.
- The source: the cause. The procedural grasscloth (`make_wall_finishes.grasscloth`) was gaussian noise filtered 70 to
  220 px along x and 1 to 2.5 px across, i.e. horizontally motion-blurred noise: its 1.1 px strands vanished in the 512
  map, leaving smooth streaks with no end, and its normal map was ridges only (xy rms 0.014 along, 0.16 up), which
  doubled the streaks in the sun. Measured on the eye-level shots, the sunlit wall was 14 times smoother along than up
  (mean luminance step 0.53 % along against 7.5 % up), exactly the source's own ratio at that scale: the game drew the
  image faithfully, and the image itself read as a texture stretched sideways.

Fix: the grasscloth is generated again (`--only grasscloth`, the product owner's images untouched) as real woven grass:
strands 3 to 8 px tall (1.5 to 4 texels of the 512 map, 5 to 14 mm), each a run of separate pieces of grass 21 to 91 cm
long with its own tone, a hard cut end and nodes, a 2 px cotton warp thread every 8 px, the two panels and their seams
as before; the normal map's rms 0.10 instead of 0.16, with relief both ways (rms 0.036 along, 0.093 up). Same repeat
(1.8 m), the arrays rebuilt by `ModelCatalogBuilder`. The sunlit wall is now 3.5 times smoother along than up (5 in the
shade), the strands show their ends at eye level and in the menu.

Shots in `docs/m9/stretch/`: `before/` and `after/` (`WallShots.Shoot -wallInside all -wallLooks none -wallNoOverview
-wallSize 960x600 -wallJpg`; before: title house, levels 22 to 24; after: title house, levels 21 and 22), `grasscloth_before_after.png`, `menu_before_report.png` and
`menu_title_*_after.png` (ProbeTestsTitleChair).

## 8. Near outer walls vanish (product owner request, 2026-11-19)

- In the see-through and both looks, an outer wall line between the camera and the house (the camera on its outer side,
  the outer rule) that covers more than `Tuning.NearWallEnterCoverage` (20 %) of the screen fades on to nothing instead of
  the opacity option: even at 10 to 50 %, a near outer wall veiled the whole view. It comes back to the opacity option only
  under `Tuning.NearWallExitCoverage` (14 %), so it never flickers while the camera orbits; both ways take
  `Tuning.NearWallVanishSeconds` (0.3 s). Interior (shared) lines keep the opacity option, whatever they cover.
- `WallFader` groups the outer parts by plane into wall lines once (cap and outside faces, door frames and the
  decorative outer leaf, which stand anyway, section 9), each with the quad of its centre plane. Each update clips that
  quad by the near plane and the four screen edges (fixed buffers, no allocation) and takes its area. A vanished part draws
  no copy at all. The wall fixtures follow `LevelOf`, which stays under 1 while a line is vanished or coming back.
- Both keeps the stubs: a vanished outer wall then reads exactly as a lowered one (its stub along the footprint). Lowered
  and off ignore the coverage.
- Tests: `ProbeTestsM9NearWalls` Step90a (every long outer wall of level1 and level12 vanishes from close, its door frames
  standing opaque (section 9), in both looks; keeps 35 % from far; lowered and off unchanged), Step90b (level12's interior walls keep the
  opacity from as close), Step90c (real frames, a camera backing away then coming back: transitions only across the
  hysteresis band, smooth, ending), Step90z (shots). `ProbeTestsM7Walls` and `WallsOptionM7Tests` still pass.
- Shots: `docs/m9/nearwalls/before_level1.png`, `before_level12.png` and `after_*.png` (see-through 35 %, the game camera
  at four yaws and two pitches), `after_level1_both.png`. Level12's views stand inside the house: its translucent walls
  there are interior ones and stay.

## 9. Doors never move (product owner rule, 2026-11-19)

- In every look (lowered, see-through, both, off) and for the near outer walls of section 8, the door parts are never
  lowered, faded or hidden: door frames (posts and head), the decorative outer leaf and the real leaves stay opaque, at
  full height. Only the wall changes, its lintel over the doorway included, so a doorway in a wall out of the way reads
  as a door standing in its frame, never under a floating piece of wall. The wall fixtures still go with their wall.
- `WallFader.KeepDoor` marks a door part (LevelBuilder by renderer name: `DoorFrame`, `DoorPostA`, `DoorPostB`,
  `DoorHead`, `DoorLeaf`; a real leaf marks itself in `WallFader.Add` with its box). The rule line is
  `hidden &= !e.Door; // MUTATION:DOORS_STAND`. The leaf box rule (wave 5A.1, `LEAF_FADE`) no longer applies to any part:
  an open leaf between the camera and the chair now stays drawn (Step36o). Lowered, only the shared walls' baseboards
  still stand by `KeepStandingWhenLowered`.
- Tests updated: ProbeTestsM5House Step36l (a leaf never moves in any look, its wall does) and Step36o (renamed
  `..._StaysDrawn`), ProbeTestsM7Walls Step70b (outer door frames in every look) and Step70f (frames opaque in see-through
  and both, baseboards stand lowered), ProbeTestsM9NearWalls Step90a (frames opaque in a vanished wall). `mutation.sh`:
  `leaf_fade` replaced by `doors_stand`.
- Shots: `docs/m9/doors/before_doors.png` and `after_doors.png` (ProbeTestsM9NearWalls.Step91z): columns lowered,
  see-through 35 %, both, off; rows level12's first shared doorway, its first outer doorway seen from outside (a near
  outer wall), level8's leaf door porte_cuisine.
