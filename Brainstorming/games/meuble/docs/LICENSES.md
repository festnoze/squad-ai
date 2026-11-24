# Third party assets

Every file under `Assets/ThirdParty` is listed here with its title, author, source and licence.
This is the licence file required by the M3 gate (PRD 11). The EditMode test `LicenseTests`
fails when a file under `Assets/ThirdParty` has no line here.

All assets below are **CC0 1.0 Universal** (public domain dedication,
https://creativecommons.org/publicdomain/zero/1.0/), except the title font (section Fonts, SIL OFL 1.1) and the music
(section Music, CC BY 4.0, credited in the game). CC0 requires no attribution: the credits
are a courtesy, and they keep the provenance auditable. Each licence was read on the item's own
page on 2026-11-11. The full evidence is in [M3_ASSETS.md](M3_ASSETS.md) section 10 and
[M3_AUDIO.md](M3_AUDIO.md).

**In-game credits** (2026-11-19): the title page's "Crédits" / "Credits" button opens a scrollable Credits page built
from one list, `Assets/Scripts/Core/Credits.cs` (English and French): the creators, the tools, the engine, then every
third party asset of this file (each CC BY track with its title, author, source URL, licence link and changes; the SIL
OFL font with its authors and licence; every CC0 author and pack, credited anyway). This file stays the source of truth:
the EditMode test `CreditsTests` fails when a CC BY or SIL OFL row here, or a CC0 author or pack, is missing from that
list. Adding a third party asset means a row here and, when its licence or author is new, a line in `Credits.cs`.

## Models (`Assets/ThirdParty/Models`)

| File | Title | Author | Source | Licence |
|---|---|---|---|---|
| `Kenney/kenney_chair.glb` | Chair | Kenney (Furniture Kit) | https://poly.pizza/m/vHyrBYPBum | CC0 1.0 |
| `Kenney/kenney_bar_stool.glb` | Bar Stool | Kenney (Furniture Kit) | https://poly.pizza/m/2do92chR2k | CC0 1.0 |
| `Kenney/kenney_lounge_chair.glb` | Lounge Chair | Kenney (Furniture Kit) | https://poly.pizza/m/RY93lbAIFg | CC0 1.0 |
| `Kenney/kenney_lamp_round_floor.glb` | Lamp Round Floor | Kenney (Furniture Kit) | https://poly.pizza/m/8LiDIfXVLi | CC0 1.0 |
| `Kenney/kenney_lounge_sofa.glb` | Lounge Sofa | Kenney (Furniture Kit) | https://poly.pizza/m/jMu2iCmGxU | CC0 1.0 |
| `Kenney/kenney_table.glb` | Table | Kenney (Furniture Kit) | https://poly.pizza/m/41R2HTYj1O | CC0 1.0 |
| `Kenney/kenney_rug_rectangle.glb` | Rug Rectangle | Kenney (Furniture Kit) | https://poly.pizza/m/k5oJLb49gw | CC0 1.0 |
| `Kenney/kenney_rug_square.glb` | Rug Square (doormat) | Kenney (Furniture Kit) | https://poly.pizza/m/FiyXx0J6VB | CC0 1.0 |
| `Kenney/kenney_doorway.glb` | Doorway | Kenney (Furniture Kit) | https://poly.pizza/m/NjrIKzZLYv | CC0 1.0 |
| `Quaternius/quaternius_man.glb` | Man in Long Sleeves | Quaternius (Animated Men Pack) | https://poly.pizza/m/DLptRuewTn | CC0 1.0 |
| `Quaternius/quaternius_woman.glb` | Woman Casual | Quaternius (Animated Women Pack) | https://poly.pizza/m/jpKRgGDxhk | CC0 1.0 |
| `Quaternius/quaternius_man_shorts.glb` | Man (t-shirt and shorts) | Quaternius (Animated Men Pack) | https://poly.pizza/m/HMnuH5geEG | CC0 1.0 |
| `Quaternius/quaternius_man_suit.glb` | Man in Suit | Quaternius (Animated Men Pack) | https://poly.pizza/m/mQnGoME1ez | CC0 1.0 |
| `Quaternius/quaternius_man_tshirt.glb` | Man (t-shirt) | Quaternius (Animated Men Pack) | https://poly.pizza/m/fjHyMd5Wxw | CC0 1.0 |
| `Quaternius/quaternius_woman_jacket.glb` | Woman (jacket) | Quaternius (Animated Women Pack) | https://poly.pizza/m/AQsd9ngvKU | CC0 1.0 |
| `Quaternius/quaternius_woman_dress.glb` | Woman in Dress | Quaternius (Animated Women Pack) | https://poly.pizza/m/zMyPlQXBzq | CC0 1.0 |
| `Quaternius/quaternius_shiba.glb` | Shiba Inu | Quaternius (Animated Animal Pack) | https://poly.pizza/m/y4wdQpg767 | CC0 1.0 |
| `Quaternius/quaternius_husky.glb` | Husky | Quaternius (Animated Animal Pack) | https://poly.pizza/m/wcWiuEqwzq | CC0 1.0 |
| `Kenney/kenney_bed_double.glb` | Bed Double | Kenney (Furniture Kit) | https://poly.pizza/m/wcmbCZ63mg | CC0 1.0 |
| `Kenney/kenney_kitchen_fridge.glb` | Kitchen Fridge | Kenney (Furniture Kit) | https://poly.pizza/m/36ODvl4CIy | CC0 1.0 |
| `Kenney/kenney_coffee_table.glb` | Coffee Table | Kenney (Furniture Kit) | https://poly.pizza/m/y4ZU5S7RuD | CC0 1.0 |
| `Kenney/kenney_cabinet_bed_drawer_table.glb` | Cabinet Bed Drawer Table | Kenney (Furniture Kit) | https://poly.pizza/m/EcvXBrClPe | CC0 1.0 |
| `RoomDressing/*.glb`, `*.png` | 7 room accessories and 3 images | product owner delivery (Build/room-dressing/RoomDressing.zip, ArtHandoff/RoomDressing) | - | project owned |
| `LivingRoomFurniture/*.glb`, `*.png` | 5 living room models and 3 images | product owner delivery (Build/living-room-furniture/LivingRoomFurniture.zip, ArtHandoff/LivingRoomFurniture) | - | project owned |

Packs: Kenney "Furniture Kit" (https://poly.pizza/bundle/Furniture-Kit-NoG1sEUD1z, also
kenney.nl); Quaternius "Animated Men Pack" (https://poly.pizza/bundle/Animated-Men-Pack-DAC9SDgMQT),
"Animated Women Pack" (https://poly.pizza/bundle/Animated-Women-Pack-HHSKxnk1mY) and "Animated Animal
Pack" (https://poly.pizza/bundle/Animated-Animal-Pack-ILAPXeUYiS). M5: the five extra humans and the dog
were copied byte for byte from `ThirdParty_staging/poly.pizza` (sha256 checked against its
`manifest.json`); their licences were read on their own pages on 2026-11-11 (M3_ASSETS.md section 10:
the "Animated Men Pack", "Animated Women Pack" and "Animated Animal Pack" list every model as CC0 1.0).
The dog steps are synthesized at run time (`FootstepAudio`): no file.
M8 room objects (2026-11-19): the bed, fridge, coffee table and nightstand were downloaded from their own poly.pizza
pages with `tools/assets/polypizza.py`, each page reading "Public Domain (CC0)", licence CC0 1.0, and the "Furniture
Kit" bundle listing all its models as CC0 1.0 on the same day. The GLBs are the pages' files unchanged, except
`kenney_bed_double.glb`: the UVs of its cover (x 0.5) and pillows (x 0.6973) were rescaled in place to the kit's 39.37 UV
per native unit (Tuning.KenneyUvPerNativeUnit, the premise of probe step 22e), geometry untouched (CC0 allows it).
DOGBIG (2026-11-21): the house dog is now the Quaternius Husky (Animated Animal Pack), from
`ThirdParty_staging/poly.pizza/alternates/pets/pet_dog__quaternius_husky__wcWiuEqwzq.glb` (sha256 a1e107ec...77eb, checked
against its `manifest.json`, whose page record reads "Public Domain (CC0)", licence CC0 1.0). `quaternius_husky.glb` is
that file with its five materials renamed to the Shiba's names (Main, Main_Light, Black, Eyes_White, Eyes_Black), its mesh
named "Husky", a UV0 atlas added and, since DOGBIG v3 and v4, a "Jaw" joint, a subdivided and smoothed body and a rounder head
with a shorter muzzle (rig, weights and clips otherwise kept; CC0 allows it). The Shiba GLB stays in
the project but no catalog entry uses it any more.

## Textures (`Assets/ThirdParty/Textures`)

Retired on 2026-11-18: the ambientCG (CC0) derived details and normal maps of M4.2, M6 and M7 were replaced by the
product owner's environment images below and deleted from `Assets/ThirdParty/Textures` (they remain in the git
history; `tools/assets/derive_textures.py` documents how they were made). No file ships from this folder any more.

## Environment (`Assets/Art/Environment`)

The detail textures of every textured surface (`TextureLibrary`, `PrimitiveKit.Detail`), shipped through
`Assets/Resources/TextureLibrary.asset` (built by `ModelCatalogBuilder.BuildTextureLibrary`). Not third party: the 13
source images were provided by the product owner for this game on 2026-11-18. The shipped files under `Detail/` are
derived from them by `tools/assets/derive_env_textures.py`: the luminance of the source (grayscale: the palette colour
carries the meaning), its wrap edges cross-faded with a rolled copy where the source was not exactly seamless, wood,
parquet and lacquer rotated so the grain or the planks run vertically, resized to 512 x 512 with a wrap-around filter,
high-passed and softened (still seamless), then remapped to a calm contrast (no more fine detail than the detail it
replaced) with a mean of exactly 240/255 and the highlights capped at 1.0. The normal maps (the ten surfaces of
CONTRACT_M7 1.2; Plastic, Foliage and Soil stay bump-free) are a gentle periodic Sobel of the detail itself, OpenGL
convention, no stronger than the map they replaced. The 1254 x 1254 sources are not referenced by any shipped asset,
so they do not ship.

M7 real colours (CONTRACT_M7 5, product owner decision of 2026-11-18): the shipped colour maps under `Colour/` are
derived by `tools/assets/derive_env_colours.py` from the same sources and from `red_metal_source.png` (the player
furniture, provided on 2026-11-18 too): the same wrap-edge cross-fade (rolls found on the luminance, applied to every
channel), the same rotations and the same 512 x 512 wrap-around resize as the details, so the normal maps stay aligned;
the colours are kept as they are (sRGB, no high pass, no remap). Every surface shows its colour map; the details still
ship but are only shown on the inhabitants (CharacterLook keeps the palette rule).

M7 rug image (product owner decision of 2026-11-18): `rug_modern_inset_border.png` is used as is (not derived, not
seamless): every rug and the doormat show it exactly once, stretched over their own full size (UV 0 to 1,
`PrimitiveKit.RugDetail`), never tiled; their model or procedural skirt below it keeps the tiled Carpet detail above,
unchanged.

| Asset | Files | Author | Source | Licence |
|---|---|---|---|---|
| Wood (furniture wood grain) | `wood.png`; derived: `Colour/colour_wood.png`, `Detail/detail_wood.png`, `Detail/normal_wood.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Parquet (parquet of the hard floors) | `parquet.png`; derived: `Colour/colour_parquet.png`, `Detail/detail_parquet.png`, `Detail/normal_parquet.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Plaster (walls and caps) | `plaster.png` (from `crepi_cream_source.png`, 2026-11-18); derived: `Colour/colour_plaster.png`, `Detail/detail_plaster.png`, `Detail/normal_plaster.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Upholstery (upholstery weave) | `upholstery.png`; derived: `Colour/colour_upholstery.png`, `Detail/detail_upholstery.png`, `Detail/normal_upholstery.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Linen (linen: clothes, table cloths, lamp shade) | `linen.png`; derived: `Colour/colour_linen.png`, `Detail/detail_linen.png`, `Detail/normal_linen.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Carpet (rugs, doormat, soft floors: their tiled skirt or border, unchanged) | `carpet.png`; derived: `Colour/colour_carpet.png`, `Detail/detail_carpet.png`, `Detail/normal_carpet.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Rug picture (M7 rug image, 2026-11-18: the rug's and the doormat's own picture, stretched once per rug, never tiled, `PrimitiveKit.RugDetail`) | `rug_modern_inset_border.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Grass (the garden ground) | `grass.png`; derived: `Colour/colour_grass.png`, `Detail/detail_grass.png`, `Detail/normal_grass.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Lacquer (door leaves; until 2026-11-18 also the player furniture) | `lacquer.png`; derived: `Colour/colour_lacquer.png`, `Detail/detail_lacquer.png`, `Detail/normal_lacquer.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Metal (office chair frame, lamp pole and base, robot body) | `metal.png`; derived: `Colour/colour_metal.png`, `Detail/detail_metal.png`, `Detail/normal_metal.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Plastic (the robot's bumper) | `plastic.png`; derived: `Colour/colour_plastic.png`, `Detail/detail_plastic.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Foliage (leaves: the potted plants and the fallen load's foliage) | `foliage.png`; derived: `Colour/colour_foliage.png`, `Detail/detail_foliage.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Soil (the fallen load's spilled soil) | `soil.png`; derived: `Colour/colour_soil.png`, `Detail/detail_soil.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Tile (kitchen and bathroom floor tile) | `tile.png`; derived: `Colour/colour_tile.png`, `Detail/detail_tile.png`, `Detail/normal_tile.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Red painted metal (the player furniture, PRD 7.2) | `red_metal_source.png`; derived: `Colour/colour_player.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Sage painted plaster (wall finish "sage") | `wall_sage.png`; derived: `Colour/colour_wall_sage.png`, `Detail/detail_wall_sage.png`, `Detail/normal_wall_sage.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_wall_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| Clay limewash (wall finish "limewash") | `wall_limewash.png`; derived: `Colour/colour_wall_limewash.png`, `Detail/detail_wall_limewash.png`, `Detail/normal_wall_limewash.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_wall_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| Dusty blue grasscloth (wall finish "grasscloth") | `wall_grasscloth.png`; derived: `Colour/colour_wall_grasscloth.png`, `Detail/detail_wall_grasscloth.png`, `Detail/normal_wall_grasscloth.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_wall_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| Printed sprig wallpaper (wall finish "wallpaper") | `wall_wallpaper.png`; derived: `Colour/colour_wall_wallpaper.png`, `Detail/detail_wall_wallpaper.png`, `Detail/normal_wall_wallpaper.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_wall_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| White-grey veined marble (floor finish "marble") | `floor_marble.png`; derived: `Colour/colour_floor_marble.png`, `Detail/detail_floor_marble.png`, `Detail/normal_floor_marble.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_floor_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| Darker oak herringbone parquet (floor finish "herringbone") | `floor_herringbone.png`; derived: `Colour/colour_floor_herringbone.png`, `Detail/detail_floor_herringbone.png`, `Detail/normal_floor_herringbone.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_floor_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| Warm grey-beige loop pile carpet (floor finish "carpet") | `floor_carpet.png`; derived: `Colour/colour_floor_carpet.png`, `Detail/detail_floor_carpet.png`, `Detail/normal_floor_carpet.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_floor_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| Wide light oak planks (floor finish "lightoak", M9) | `floor_lightoak.png`; derived: `Colour/colour_floor_lightoak.png`, `Detail/detail_floor_lightoak.png`, `Detail/normal_floor_lightoak.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_floor_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| Dark green verde marble (floor finish "verde", M9) | `floor_verde.png`; derived: `Colour/colour_floor_verde.png`, `Detail/detail_floor_verde.png`, `Detail/normal_floor_verde.png` | Out of Sight team | Own creation, procedural (`tools/assets/make_floor_finishes.py`) | CC0 1.0 (own creation, dedicated to the public domain) |
| Small ivory bathroom tiles (floor finish "ivorytile", M9) | `tile_bathroom_small_ivory.png`; derived (`tools/assets/make_floor_finishes.py`): `Colour/colour_tile_bathroom_small_ivory.png`, `Detail/detail_tile_bathroom_small_ivory.png`, `Detail/normal_tile_bathroom_small_ivory.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Large teal bathroom tiles (floor finish "tealtile", M9) | `tile_bathroom_large_teal.png`; derived (`tools/assets/make_floor_finishes.py`): `Colour/colour_tile_bathroom_large_teal.png`, `Detail/detail_tile_bathroom_large_teal.png`, `Detail/normal_tile_bathroom_large_teal.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| White bathroom wall tiles over pastel blue paint (wall finish "whitetile", tiled walls) | `wall_bathroom_white_pastel_blue.png`; derived (`tools/assets/make_wall_finishes.py`): `Colour/colour_wall_bathroom_white_pastel_blue.png`, `Detail/detail_wall_bathroom_white_pastel_blue.png`, `Detail/normal_wall_bathroom_white_pastel_blue.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Ivory kitchen subway tiles over sage paint (wall finish "subwaytile", tiled walls) | `wall_kitchen_ivory_sage.png`; derived (`tools/assets/make_wall_finishes.py`): `Colour/colour_wall_kitchen_ivory_sage.png`, `Detail/detail_wall_kitchen_ivory_sage.png`, `Detail/normal_wall_kitchen_ivory_sage.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Greige honed travertine (wall finish "travertine", printed and stone walls) | `wall_travertine_greige.png`; derived (`tools/assets/make_wall_finishes.py`): `Colour/colour_wall_travertine_greige.png`, `Detail/detail_wall_travertine_greige.png`, `Detail/normal_wall_travertine_greige.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Slate blue Art Deco arches wallpaper (wall finish "arches", printed and stone walls) | `wall_deco_arches_blue.png`; derived (`tools/assets/make_wall_finishes.py`): `Colour/colour_wall_deco_arches_blue.png`, `Detail/detail_wall_deco_arches_blue.png`, `Detail/normal_wall_deco_arches_blue.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Olive pinstripe linen wallpaper (wall finish "pinstripe", printed and stone walls) | `wall_linen_pinstripe_olive.png`; derived (`tools/assets/make_wall_finishes.py`): `Colour/colour_wall_linen_pinstripe_olive.png`, `Detail/detail_wall_linen_pinstripe_olive.png`, `Detail/normal_wall_linen_pinstripe_olive.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Sage and terracotta quatrefoil wallpaper (wall finish "quatrefoil", walls 4) | `wall_quatrefoil.png`; derived (`tools/assets/make_wall_finishes.py`): `Colour/colour_wall_quatrefoil.png`, `Detail/detail_wall_quatrefoil.png`, `Detail/normal_wall_quatrefoil.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Sage fluted wall panel (wall finish "sageribbed", walls 4) | `wall_sage_ribbed.png`; derived (`tools/assets/make_wall_finishes.py`): `Colour/colour_wall_sage_ribbed.png`, `Detail/detail_wall_sage_ribbed.png`, `Detail/normal_wall_sage_ribbed.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Wall finish arrays (walls 4) | `Arrays/wall_colours.png`, `Arrays/wall_normals.png`: the colour and normal maps of the crepi and every wall finish above, stacked as they are by `ModelCatalogBuilder` (no new image) | As their sources | As their sources | As their sources |
| Window picture (every wall window: wood frame, four panes, blurred garden, 2026-11-19, `WindowImage`) | `window_wood_blurred_garden.png`; derived (`tools/assets/make_window_image.py`): `Assets/Resources/WindowImage.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Garden backdrop (the ring round every house and the title house, 2026-11-20, `GardenBackdrop`; the 2026-11-19 `garden_open_horizontal_tile.png` is retired, no longer shipped) | `garden_open_horizontal_tile_wide.png`; derived (`tools/assets/make_garden_backdrop.py`): `Assets/Resources/GardenBackdrop.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Sky ceiling (the round ceiling closing the garden ring, 2026-11-20, `GardenBackdrop`) | `sky_disc_sun_glow.png`; derived (`tools/assets/make_garden_backdrop.py`): `Assets/Resources/GardenSky.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |

Wall finishes (product owner request of 2026-11-19): the four `wall_*.png` sources above are our own procedural creation
(periodic filtered noise and a wrapped drawing, no source image, no third party asset), made and derived in one pass by
`tools/assets/make_wall_finishes.py`: the 1024 x 1024 sources (not shipped), their 512 x 512 colour maps (a 2 x 2 box
average, seamless), grayscale details (mean 240/255) and normal maps (a periodic Sobel of each finish's own height).
A room's `"wallFinish"` picks one; every other wall keeps the crepi.

Floor finishes (M8 ROOMS_PLAN.md 4, product owner request of 2026-11-19): the three `floor_*.png` sources above are
likewise our own procedural creation, made and derived in one pass by `tools/assets/make_floor_finishes.py`: marble's
veins are the near zero crossing of a few elongated noise fields and its joint sits centred on the wrap edge (a
continuous grout line once tiled); herringbone's chevron is built in a 45 degree rotated frame, independently periodic
on each axis so it tiles exactly. A room's `"floorFinish"` picks one; "marble" and "herringbone" need a hard floor
(join "tile"), "carpet" a soft one (LevelValidator); every other floor keeps the parquet, or on a soft floor its own
plain carpet look.

M9 floors (product owner request of 2026-11-19, docs/m9/FLOORS_WALLS.md): `floor_lightoak.png` (wide light oak
planks) and `floor_verde.png` (dark green verde marble) are own creation by the same script; the two
`tile_bathroom_*.png` bathroom tiles are the product owner's images, used as given (their grout is split over the wrap
edges, so they tile as is), the script only derives their colour, detail and normal maps. All four are hard floor only.

Tiled walls (product owner request of 2026-11-19, docs/m9/FLOORS_WALLS.md): `wall_bathroom_white_pastel_blue.png` and
`wall_kitchen_ivory_sage.png` are the product owner's images, each a whole wall (tiles above a trim above paint), used as
given; `tools/assets/make_wall_finishes.py` only derives their colour, detail and normal maps (wrapped along the wall,
clamped up it, the paint's wrap seam cross-faded in the derived maps). A room's `"wallFinish"` "whitetile" or
"subwaytile" picks one.

Printed and stone walls (product owner request of 2026-11-19, docs/m9/FLOORS_WALLS.md section 6):
`wall_travertine_greige.png`, `wall_deco_arches_blue.png` and `wall_linen_pinstripe_olive.png` are the product owner's
images, all-over patterns used as given; `tools/assets/make_wall_finishes.py` only derives their colour, detail and
normal maps (wrapped both ways, the travertine's and the linen's small wrap seams cross-faded in the derived maps). A
room's `"wallFinish"` "travertine", "arches" or "pinstripe" picks one.

Walls 4 (product owner request of 2026-11-19, docs/m9/FLOORS_WALLS.md section 7): `wall_quatrefoil.png` and
`wall_sage_ribbed.png` are the product owner's images, all-over patterns used as given (their maps derived the same way;
a room's `"wallFinish"` "quatrefoil" or "sageribbed" picks one). The bathroom tiles' derived maps now replace the source's
two cracked tiles and its chipped corner by clean tiles of the same image (the source stays as given): laid at their real
15 cm size, the defects came back every 1.5 m.

Window picture (product owner request of 2026-11-19): `window_wood_blurred_garden.png` is the product owner's image, used
as given apart from its framing: `tools/assets/make_window_image.py` crops it to the frame's own rectangle (the
transparent margin and the sill's small overhang go) into `Assets/Resources/WindowImage.png` (1024 x 1024, opaque). Every
wall window shows it in place of the former plain pane and trim strips, sliced so it is never stretched (`WindowImage`).

Garden backdrop (product owner requests of 2026-11-19 and 2026-11-20, docs/m9/backdrop/NOTES.md):
`garden_open_horizontal_tile_wide.png` (2026-11-20, replacing `garden_open_horizontal_tile.png` of 2026-11-19, which stays
in the folder but no longer ships) is the product owner's image, a wide garden panorama that repeats horizontally, used as
given apart from its preparation by `tools/assets/make_garden_backdrop.py` into `Assets/Resources/GardenBackdrop.png`
(4096 x 1024: its duplicate last column dropped, resampled with the wrap kept, the top of the sky made one uniform colour,
the lawn strip's mean matched to the grass plane, a light haze). It is shown on the inside of the ring round every house,
repeated round the circle at its own aspect (`GardenBackdrop`). `sky_disc_sun_glow.png` (2026-11-20) is the product
owner's image, a round overhead sky, prepared by the same script into `Assets/Resources/GardenSky.png` (1024 x 1024:
cropped to its disc, the sun moved off centre by a conformal map of the disc so it stands toward the scene's light, the rim
band made exactly the garden's top colour) and shown once on the round ceiling closing the ring (`GardenBackdrop`).

## Audio (`Assets/ThirdParty/Audio`)

Every clip is made from the original download by `tools/audio/audio_pipeline.py` (audio overhaul of 2026-11-18,
docs/audio/AUDIO_REPORT.md; until then `tools/assets/audio_derive.py`): mono 44.1 kHz, a 30 Hz high pass, silence
trimmed, short fades, loudness matched under a -1 dBTP true peak, 16-bit WAV. The original file names are given in
parentheses. The licences of the M3 picks were read on 2026-11-11 (docs/M3_AUDIO.md); the new picks of 2026-11-18 come
from the same item pages, whose licence facts are in `ThirdParty_staging/audio/sources.json`.

| File | Title | Author | Source | Licence |
|---|---|---|---|---|
| `wardrobe_close.wav` | 100 CC0 metal and wood SFX (wood_close_01) | rubberduck | https://opengameart.org/content/100-cc0-metal-and-wood-sfx | CC0 1.0 |
| `topple.wav` | 100 CC0 metal and wood SFX (wood_falling_02) | rubberduck | https://opengameart.org/content/100-cc0-metal-and-wood-sfx | CC0 1.0 |
| `wardrobe_open.wav` | 100 CC0 SFX (wooded_box_open) | rubberduck | https://opengameart.org/content/100-cc0-sfx | CC0 1.0 |
| `crash.wav` | 100 CC0 SFX (dishes_01) | rubberduck | https://opengameart.org/content/100-cc0-sfx | CC0 1.0 |
| `lamp_click.wav` | 100 CC0 SFX (switch_02) | rubberduck | https://opengameart.org/content/100-cc0-sfx | CC0 1.0 |
| `door_open.wav` | 50 RPG sound effects (doorOpen_1) | Kenney | https://opengameart.org/content/50-rpg-sound-effects | CC0 1.0 |
| `sting_win.wav` | 85 Short music jingles (jingles_PIZZA10) | Kenney | https://opengameart.org/content/85-short-music-jingles | CC0 1.0 |
| `ui_hover.wav` | Interface Sounds (tick_001) | Kenney | https://opengameart.org/content/interface-sounds | CC0 1.0 |
| `scrape_01.wav`, `scrape_02.wav`, `scrape_03.wav` | Saw or Wood Impact (three excerpts) | StarNinjas | https://opengameart.org/content/saw-or-wood-impact | CC0 1.0 |
| `creak_long.wav` | 100 CC0 SFX (door_02) | rubberduck | https://opengameart.org/content/100-cc0-sfx | CC0 1.0 |
| `creak_short.wav` | 50 RPG sound effects (creak3) | Kenney | https://opengameart.org/content/50-rpg-sound-effects | CC0 1.0 |
| `footstep_01.wav`, `footstep_02.wav`, `footstep_03.wav`, `footstep_04.wav`, `footstep_05.wav` | 50 RPG sound effects (footstep00, 01, 03, 07, 08) | Kenney | https://opengameart.org/content/50-rpg-sound-effects | CC0 1.0 |
| `roomtone_airvent_loop.wav` | Airvent Loop (crossfaded loop) | Longor | https://opengameart.org/content/airvent-loop | CC0 1.0 |
| `roomtone_clock_loop.wav` | Ticking clock. | bart | https://opengameart.org/content/ticking-clock | CC0 1.0 |
| `thump.wav` | Door open, door close (door-05) | qubodup | https://opengameart.org/content/door-open-door-close | CC0 1.0 |
| `vocal_huh.wav` | huh? | TinyWorlds | https://opengameart.org/content/huh | CC0 1.0 |
| `ui_click.wav` | Interface Sounds (click_001) | Kenney | https://opengameart.org/content/interface-sounds | CC0 1.0 |

**Made for the game** (SOUNDS, 2026-11-24): `hop_01.wav`, `hop_02.wav`, `hop_03.wav`, `hop_04.wav` (the furniture's
step: a muffled footstep on carpet, SOUNDS2), `hop_soft_01.wav`, `hop_soft_02.wav`, `hop_soft_03.wav`,
`hop_soft_04.wav` (the same step on a rug, muffled), `sting_caught.wav` and `sting_caught_long.wav` (the caught stings: soft
brass, marimba, pizzicato, a choked cymbal) are synthesized by `tools/audio/make_sounds.py` from code alone, no recording
and no third party material, so they need no licence row. They replace rubberduck's wood hits (75 CC0 breaking / falling
/ hit sfx, 100 CC0 metal and wood SFX), Kenney's jingles_SAX05 and 0new4y's "Game Over Trumpet SFX"; the replaced files are
kept for comparison in `Build/sounds/old/` (not shipped).

## Music (`Assets/ThirdParty/Audio/Music`)

Audio overhaul (2026-11-18, docs/audio/AUDIO_REPORT.md section 5). Not CC0: both tracks are by Kevin MacLeod under
**Creative Commons Attribution 4.0** (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/), which allows using them in a
game, sold or not, with credit. The licence and the credit format were read on https://incompetech.com/music/royalty-free/faq.html
on 2026-11-18 ("Title Kevin MacLeod (incompetech.com) Licensed under Creative Commons: By Attribution 4.0"). The credit is
shown in the game on the Credits page (`Credits.cs`, in full: title, author, source URL, licence and link, changes;
`CreditsTests` checks it) and in a short line at the bottom of the Options page (`Strings` key `options.musicCredits`,
English and French, moved there from the title page on 2026-11-19; `LicenseTests` checks it). Each shipped file is a seamless loop cut from the original MP3 (a stretch of the piece and a
120 ms crossfade, the "changes made" CC BY asks to indicate), loudness normalised, Ogg Vorbis, by `tools/audio/audio_pipeline.py`.

| File | Title | Author | Source | Licence |
|---|---|---|---|---|
| `Music/music_title.ogg` | "Sneaky Snitch" (the title page; a loop of 11.52 to 77.72 s) | Kevin MacLeod (incompetech.com) | https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3 (ISRC USUAN1100772) | CC BY 4.0 |
| `Music/music_level.ogg` | "Investigations" (the levels; a loop of 18.11 to 58.53 s) | Kevin MacLeod (incompetech.com) | https://incompetech.com/music/royalty-free/mp3-royaltyfree/Investigations.mp3 (ISRC USUAN1100646) | CC BY 4.0 |

## Fonts (`Assets/ThirdParty/Fonts`)

M7 title redesign. The game title's display face (title page, title page buttons, intro cards), loaded at run time
from `Assets/ThirdParty/Fonts/Resources` (`Hud.DisplayFont`). Not CC0: it is under the **SIL Open Font License 1.1**
(https://openfontlicense.org), which allows bundling it in a game, sold or not, as long as the font file is not sold on
its own and its licence travels with it (the licence text sits next to the font and ships in the build). Downloaded
from the Google Fonts repository on 2026-11-18; the licence was read in the file below.

| File | Title | Author | Source | Licence |
|---|---|---|---|---|
| `Resources/DMSerifDisplay-Regular.ttf` | DM Serif Display Regular | Colophon Foundry (DM fonts, from Adobe's Source Serif) | https://github.com/google/fonts/tree/main/ofl/dmserifdisplay | SIL OFL 1.1 |
| `Resources/DMSerifDisplay-OFL.txt` | DM Serif Display licence text (OFL.txt) | Adobe, Google LLC | https://github.com/google/fonts/blob/main/ofl/dmserifdisplay/OFL.txt | SIL OFL 1.1 |

## Characters (`Assets/Art/Characters`)

Rounded human GLBs in `Assets/Art/Characters/Models` are CC0 derivatives of the original Quaternius models listed above. Regenerate them with `tools/assets/round_characters.py`. The rig, clips and triangle indices are preserved.

M7 heads and clothes (`CharacterHead`, `CharacterLook`). Not third party: the sources were provided by the product owner
for this game on 2026-11-18. The heads use only `man_head_around.png` and `woman_head_around.png` (an all-around head
image wrapped once around each human head), copied unchanged to `Resources/CharacterManHeadWrap.png` and
`Resources/CharacterWomanHeadWrap.png` for the game. The clothes files are derived from their sources (the shirt and
trousers files: the garment cropped, in its real colours; `Resources/CharacterClothesAtlas.png` packs them). The earlier
face and head-back files (`man_face*.png`, `woman_face*.png`, `man_head_back*.png`, `woman_head_back*.png`) and the
fabric sources `cotton_source.png` and `twill_source.png` were not used by the game; moved out of `Assets` on
2026-11-19 (`docs/cleanup/unused_textures.md`) to `C:\Dev\outofsight_removed_assets`.

| Asset | Files | Author | Source | Licence |
|---|---|---|---|---|
| Characters | `man_head_around.png`, `woman_head_around.png`, `shirt_front_source.png`, `shirt_back_source.png`, `trousers_front_source.png`, `trousers_back_source.png`; derived: `shirt_front.png`, `shirt_back.png`, `trousers_front.png`, `trousers_back.png`, `Resources/CharacterManHeadWrap.png`, `Resources/CharacterWomanHeadWrap.png`, `Resources/CharacterClothesAtlas.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |
| Dog (black Labrador, DOGBIG 2026-11-21) | `labrador_black_face_front.png`, `labrador_black_fur_albedo.png`; derived (`tools/assets/dog/compose_dogfur.py`, sources unchanged): `Resources/DogFur.png` | Product owner | Provided by the product owner | Provided by the product owner for this game |

DOGBIG (2026-11-21): the dog's fur map `Resources/DogFur.png` is laid out on the UV0 atlas that
`tools/assets/dog/make_husky.py` adds to the Quaternius Husky (its layout, `dog_fur_uv_template.png`, is our own
drawing). It is made from the product owner's two images: the fur tiled (a rotated copy where the strands must run head
to tail) and the front face picture placed over the head, its edge feathered into the fur.

## UI icons (`Assets/Art/UI/Icons`)

Not third party: original work made for this game on 2026-11-19 (HUD gauge icons) and 2026-11-20 (Options icons), see
`docs/m9/icons/NOTES.md`. The two flags are drawn from scratch (flat bands, stripes and stars); national flags are not
copyrighted designs.

| Asset | Files | Author | Source | Licence |
|---|---|---|---|---|
| HUD gauge icons (Creak, Suspicion) | `creak.svg`, `suspicion.svg`, `creak.png`, `suspicion.png` | Out of Sight team (made with Claude Code) | Original, `docs/m9/icons/final.py` | Original work for this game |
| Options icons (Defaults, Back, French and US flags) | `reset.svg`, `back.svg`, `flag_fr.svg`, `flag_us.svg`, `reset.png`, `back.png`, `flag_fr.png`, `flag_us.png` | Out of Sight team (made with Claude Code) | Original, `docs/m9/icons/options_icons.py` | Original work for this game |
