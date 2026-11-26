# Environment textures

Color images in this folder are material sources for the game's environments and props. Their suggested roles correspond to the surface categories in `TextureLibrary`. Actual usage is determined by the game's materials and texture library, not by the presence of a file here.

| Image | Intended role |
| --- | --- |
| `grass.png` | Garden and outdoor lawn. |
| `soil.png` | Exposed earth, such as soil in plant pots. |
| `foliage.png` | Leaves and greenery on decorative plants. |
| `plaster.png` | Painted plaster on walls and related interior surfaces. |
| `crepi_cream_source.png` | Cream stucco with pronounced grain, an alternative wall color source. |
| `parquet.png` | Wooden plank floors and raised wooden flooring. |
| `tile.png` | Ceramic floor tiles, especially kitchens and bathrooms. |
| `carpet.png` | Carpeted floors, rugs and mats. |
| `wood.png` | Furniture, doors, shelves, frames and wooden trim. |
| `window_wood_blurred_garden.png` | Front view of a four-pane wood window, with a blurred green garden and bright glass reflections. Transparent outside the frame. Shown by every wall window from 2026-11-19 to 2026-11-24 (cropped by `tools/assets/make_window_image.py` into `Assets/Resources/WindowImage.png`), then replaced by the 3D wood window of the art handoff (WINDOWS3D, `Assets/ThirdParty/Models/WoodWindow`): no longer shipped. |
| `garden_open_horizontal_tile.png` | Standalone garden backdrop with a narrow strip of lawn, freely growing trees and shrubs, pink and white flowers, a winding gravel path, and an open blue sky. Repeats horizontally (its last column repeats its first). Product owner image. Shown inside the garden backdrop ring around every house from 2026-11-19 to 2026-11-20, then replaced by `garden_open_horizontal_tile_wide.png`: no longer shipped. |
| `garden_open_horizontal_tile_wide.png` | 5016 × 1254 panoramic garden source with four varied stretches of freely growing trees, flower beds and glimpses of garden paths. Repeats horizontally (its last column repeats its first). Product owner image (2026-11-20). Shown inside the garden backdrop ring around every house, three times round (`GardenBackdrop`; derived by `tools/assets/make_garden_backdrop.py` into `Assets/Resources/GardenBackdrop.png`, 4096 x 1024: resampled with the wrap kept, the top sky made uniform, the lawn matched to the grass plane, the source unchanged). |
| `sky_disc_sun_glow.png` | Circular overhead sky source with a central sun and bloom. The blue rim matches the top of the wide garden panorama. Transparent outside the disc. Product owner image (2026-11-20). Shown once on the round ceiling closing the garden ring (`GardenBackdrop`; derived by `tools/assets/make_garden_backdrop.py` into `Assets/Resources/GardenSky.png`, 1024 x 1024: cropped to the disc, the sun moved toward the scene's light by a conformal map of the disc, the rim made exactly the garden's top colour, the source unchanged). |
| `window_oak_four_panes.png` | Light oak window with a 2 × 2 pane grid, a central brass latch and shaded edges around the glass. |
| `window_sage_six_panes.png` | Sage painted window with a tall 2 × 3 pane grid, central latch and recessed glazing. |
| `window_walnut_six_panes.png` | Dark walnut window with a wide 3 × 2 pane grid, a central metal latch and shaded bevels. |
| `lacquer.png` | Painted or lacquered furniture surfaces. |
| `upholstery.png` | Fabric on sofas, armchairs, cushions and other padded seats. |
| `linen.png` | Fine fabric for lampshades, textiles and clothing. |
| `metal.png` | Neutral metal parts such as lamp poles, bases and chair frames. |
| `plastic.png` | Matte plastic on small props and furniture details. |
| `red_metal_source.png` | Vivid red painted-metal color source for the movable chair or other player-controlled furniture. |
| `wall_sage.png` | Wall finish "sage": soft painted plaster in a muted sage (own creation, `tools/assets/make_wall_finishes.py`). |
| `wall_limewash.png` | Wall finish "limewash": warm clay limewash, cloudy and brushed (own creation). |
| `wall_grasscloth.png` | Wall finish "grasscloth": dusty blue woven grasscloth, two 0.9 m panels per repeat (own creation). |
| `wall_wallpaper.png` | Wall finish "wallpaper": printed sage stripes and botanical sprigs on off-white (own creation). |
| `wall_travertine_greige.png` | Wall finish "travertine" (entrances, halls, living rooms, bathrooms): a warm greige, honed travertine effect and fine mineral pores, no joint. Repeats in both directions, 1.2 m per repeat (pores of 1 to 4 cm). Product owner image. |
| `wall_deco_arches_blue.png` | Wall finish "arches" (living and dining rooms, bedrooms): muted slate blue Art Deco arches on ivory paper, a 4 x 4 lattice. Repeats in both directions, 1.8 m per repeat: 26 cm arches 45 cm apart, six rows per 2.7 m wall. Product owner image. |
| `wall_linen_pinstripe_olive.png` | Wall finish "pinstripe" (bedrooms, offices): natural linen grain and fine olive and taupe stripes, eight pairs per repeat. Repeats in both directions, 1.2 m per repeat (a pair every 15 cm). Product owner image. |
| `wall_bathroom_white_pastel_blue.png` | Wall finish "whitetile" (tiled walls, bathrooms): raised square white tiles and black grout. Two tiles are cracked and one has a broken corner near the lower right (healed in the derived maps only, walls 4). The lower band is textured pastel blue paint. Laid as bands (walls 4): 15 cm tiles (1.5 m per image width), the trim at 0.99 m, the paint mirrored under it, six-row tile fields repeated to the top. Product owner image. |
| `wall_kitchen_ivory_sage.png` | Wall finish "subwaytile" (tiled walls, kitchens): ivory subway tiles above soft sage paint. Laid as bands (walls 4): 30 x 10 cm tiles (1.2 m per image width), the trim at 1.09 m, seven-course tile fields repeated to the top, every other one shifted half a tile (running bond). Product owner image. |
| `wall_quatrefoil.png` | Wall finish "quatrefoil" (walls 4: bedrooms, entrances, corridors): sage quatrefoils with terracotta four-point stars on a cream paper, an 8 x 8 lattice. Repeats in both directions, 1.35 m per repeat: a quatrefoil every 16.9 cm, sixteen rows per 2.7 m wall. Product owner image. |
| `wall_sage_ribbed.png` | Wall finish "sageribbed" (walls 4: living and dining rooms, offices): a sage painted fluted panel, 36 vertical ribs per repeat. Repeats in both directions, 1.44 m per repeat (a rib every 4 cm), satin. Product owner image. |
| `floor_marble.png` | Floor finish "marble": white-grey slabs with fine veins and a thin joint, 0.6 m per slab (own creation, `tools/assets/make_floor_finishes.py`). |
| `floor_herringbone.png` | Floor finish "herringbone": darker oak herringbone parquet, a woven chevron (own creation). |
| `floor_carpet.png` | Floor finish "carpet": wall-to-wall carpet, a warm grey-beige loop pile (own creation). |
| `floor_lightoak.png` | Floor finish "lightoak" (M9): wide light oak planks, the third parquet, 25 cm boards, 2 m repeat (own creation, `tools/assets/make_floor_finishes.py`). |
| `floor_verde.png` | Floor finish "verde" (M9): dark green verde marble with pale veins, four 0.8 m slabs per 1.6 m repeat (own creation). |
| `tile_bathroom_small_ivory.png` | Floor finish "ivorytile" (M9): small ivory bathroom tiles, a 16 x 16 grid repeated every 1.2 m (7.5 cm tiles). Product owner image. |
| `tile_bathroom_large_teal.png` | Floor finish "tealtile" (M9): large teal bathroom tiles, a 4 x 4 grid repeated every 1.6 m (40 cm tiles). Product owner image. |

The four procedural wall finishes are seamless by construction; a room's `"wallFinish"` in its level JSON picks one for the
room-facing side of its walls (the default is the crepi, `plaster.png`). The three `floor_*.png` finishes (M8
ROOMS_PLAN.md 4) are seamless the same way; a room's `"floorFinish"` picks one: "marble" and "herringbone" need a hard
floor (join "tile"), "carpet" a soft one (a wall-to-wall look, distinct from the plain soft floor's own look and from
`carpet.png` above, which stays the rug's, the doormat's and the plain soft floor's own surface). Rerun the matching
script to regenerate a family and its `Colour/`, `Detail/` maps.

Tiled walls (2026-11-19, docs/m9/FLOORS_WALLS.md): a room's `"wallFinish"` "whitetile" or "subwaytile" shows them.
Walls 4 (docs/m9/FLOORS_WALLS.md section 7): no longer mapped once over the wall (27 cm and 67.5 cm tiles were far too
big); the wall material lays them as bands: the paint from the floor to the trim (mirrored, never stretched), the trim at
`Tuning.WhiteTileTrimHeight` or `SubwayTileTrimHeight`, then the image's tile field repeated in whole rows up to the wall
top, at real tile sizes (`Tuning.DetailTileWhiteTile` 1.5 m, `DetailTileSubwayTile` 1.2 m per image width). A room with
walls taller than `Tuning.TiledWallHeight` is still rejected (LevelValidator). Their tiles wrap as given (the grout is split over the two side edges); the paint and the trim do not,
so `make_wall_finishes.py --only wall_bathroom_white_pastel_blue wall_kitchen_ivory_sage` cross-fades those rows within
about 10 cm of the wrap in the derived maps (the sources stay as given), resizes them to 512 wrapped across and clamped
up, and builds their normal maps from the grout, the trim's bead and the paint's grain. `ModelCatalogBuilder` imports
their colour, detail and normal maps Repeat on U and Clamp on V.

Printed and stone walls (2026-11-19, docs/m9/FLOORS_WALLS.md section 6): a room's `"wallFinish"` "travertine", "arches"
or "pinstripe" shows the three all-over images above. They have no band, so they repeat both ways at their metric size
(`Tuning.DetailTileTravertine`, `DetailTileArches`, `DetailTilePinstripe`), Repeat on both axes, on any wall height.
`make_wall_finishes.py --only wall_travertine_greige wall_deco_arches_blue wall_linen_pinstripe_olive` keeps the sources
as given; in the derived maps it cross-fades the travertine's and the linen pinstripe's rows and columns within about
5 cm of each wrap (the arches wrap on plain paper as given), resizes them to 512 through a 3 x 3 wrapped tiling, and
builds their normal maps from their own fine relief (the stone's pores and grain; the linen's weave, the printed ink
lying flat).

Walls 4 (2026-11-19, docs/m9/FLOORS_WALLS.md section 7): `wall_quatrefoil.png` and `wall_sage_ribbed.png` are two more
all-over images of the product owner, derived the same way (`make_wall_finishes.py --only wall_quatrefoil
wall_sage_ribbed`; the quatrefoil wraps on plain paper as given, the fluted panel's wraps are cross-faded). Every wall
finish, the crepi included, is also stacked by `ModelCatalogBuilder` into `Arrays/wall_colours.png` and
`Arrays/wall_normals.png` (twelve 512 slices in `WallArray.Slices` order, imported as Texture2DArrays) that the one wall
material (`Arrays/WallFinishes.mat`) and the see-through one (`Arrays/WallSeeThrough.mat`) read.

M9 floors (2026-11-19, docs/m9/FLOORS_WALLS.md): the floor finishes are now nine looks. Parquets: the default
`parquet.png`, "herringbone", "lightoak". Carpets (soft floors only): the plain soft floor (`carpet.png`) and "carpet".
Marbles: "marble", "verde". Bathroom tiles: "ivorytile", "tealtile" (the generic "tile" stays for kitchens). Every value
but "carpet" needs a hard floor (`RoomDef.HardFloorFinishes`). The two bathroom tile images are used as given: their grout
is split over the wrap edges, so they tile as is (checked); `make_floor_finishes.py` derives their 512 maps through a
3 x 3 wrapped resize (no clamped border) and builds their normal maps from the grout grid. Run it with
`--only <name ...>` to remake just some finishes.

The source images were generated with repeatable surfaces in mind. Opposite edges are not guaranteed to match; inspect and correct seams before tiling, especially on `tile.png`. The red source also requires a tiling check. Color images are not substitutes for the linear grayscale detail maps currently expected by the game.

`Detail/` contains separate grayscale detail maps and, for selected surfaces, normal maps. A detail map modulates the material color; a normal map supplies apparent surface relief. These files can differ from the color sources above and should be checked in the texture library before use.

For shiny red painted metal, the red image supplies base color only. Set smoothness and metallic properties in the material and use appropriate lighting and reflection sources for moving highlights. Metallic red paint and glossy red lacquer are different finishes; the latter generally uses a low metallic value.
