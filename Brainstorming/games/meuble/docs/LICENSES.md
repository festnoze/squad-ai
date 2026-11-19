# Third party assets

Every file under `Assets/ThirdParty` is listed here with its title, author, source and licence.
This is the licence file required by the M3 gate (PRD 11). The EditMode test `LicenseTests`
fails when a file under `Assets/ThirdParty` has no line here.

All assets below are **CC0 1.0 Universal** (public domain dedication,
https://creativecommons.org/publicdomain/zero/1.0/), except the title font (section Fonts, SIL OFL 1.1) and the music
(section Music, CC BY 4.0, credited in the game on the title page). CC0 requires no attribution: the credits
are a courtesy, and they keep the provenance auditable. Each licence was read on the item's own
page on 2026-11-11. The full evidence is in [M3_ASSETS.md](M3_ASSETS.md) section 10 and
[M3_AUDIO.md](M3_AUDIO.md).

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

Packs: Kenney "Furniture Kit" (https://poly.pizza/bundle/Furniture-Kit-NoG1sEUD1z, also
kenney.nl); Quaternius "Animated Men Pack" (https://poly.pizza/bundle/Animated-Men-Pack-DAC9SDgMQT),
"Animated Women Pack" (https://poly.pizza/bundle/Animated-Women-Pack-HHSKxnk1mY) and "Animated Animal
Pack" (https://poly.pizza/bundle/Animated-Animal-Pack-ILAPXeUYiS). M5: the five extra humans and the dog
were copied byte for byte from `ThirdParty_staging/poly.pizza` (sha256 checked against its
`manifest.json`); their licences were read on their own pages on 2026-11-11 (M3_ASSETS.md section 10:
the "Animated Men Pack", "Animated Women Pack" and "Animated Animal Pack" list every model as CC0 1.0).
The dog steps are synthesized at run time (`FootstepAudio`): no file.

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

Wall finishes (product owner request of 2026-11-19): the four `wall_*.png` sources above are our own procedural creation
(periodic filtered noise and a wrapped drawing, no source image, no third party asset), made and derived in one pass by
`tools/assets/make_wall_finishes.py`: the 1024 x 1024 sources (not shipped), their 512 x 512 colour maps (a 2 x 2 box
average, seamless), grayscale details (mean 240/255) and normal maps (a periodic Sobel of each finish's own height).
A room's `"wallFinish"` picks one; every other wall keeps the crepi.

## Audio (`Assets/ThirdParty/Audio`)

Every clip is made from the original download by `tools/audio/audio_pipeline.py` (audio overhaul of 2026-11-18,
docs/audio/AUDIO_REPORT.md; until then `tools/assets/audio_derive.py`): mono 44.1 kHz, a 30 Hz high pass, silence
trimmed, short fades, loudness matched under a -1 dBTP true peak, 16-bit WAV. The original file names are given in
parentheses. The licences of the M3 picks were read on 2026-11-11 (docs/M3_AUDIO.md); the new picks of 2026-11-18 come
from the same item pages, whose licence facts are in `ThirdParty_staging/audio/sources.json`.

| File | Title | Author | Source | Licence |
|---|---|---|---|---|
| `hop_01.wav`, `hop_02.wav` | 75 CC0 breaking / falling / hit sfx (bfh1_wood_hit_01, 02) | rubberduck | https://opengameart.org/content/75-cc0-breaking-falling-hit-sfx | CC0 1.0 |
| `hop_03.wav`, `hop_04.wav` | 100 CC0 metal and wood SFX (wood_hit_05, 09) | rubberduck | https://opengameart.org/content/100-cc0-metal-and-wood-sfx | CC0 1.0 |
| `hop_soft_01.wav`, `hop_soft_02.wav` | 75 CC0 breaking / falling / hit sfx (bfh1_wood_hit_01, 02, low passed at 700 Hz) | rubberduck | https://opengameart.org/content/75-cc0-breaking-falling-hit-sfx | CC0 1.0 |
| `hop_soft_03.wav`, `hop_soft_04.wav` | 100 CC0 metal and wood SFX (wood_hit_05, 09, low passed at 700 Hz) | rubberduck | https://opengameart.org/content/100-cc0-metal-and-wood-sfx | CC0 1.0 |
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
| `sting_caught.wav` | 85 Short music jingles (jingles_SAX05) | Kenney | https://opengameart.org/content/85-short-music-jingles | CC0 1.0 |
| `sting_caught_long.wav` | Game Over Trumpet SFX (losetrumpet) | 0new4y | https://opengameart.org/content/game-over-trumpet-sfx | CC0 1.0 |
| `vocal_huh.wav` | huh? | TinyWorlds | https://opengameart.org/content/huh | CC0 1.0 |
| `ui_click.wav` | Interface Sounds (click_001) | Kenney | https://opengameart.org/content/interface-sounds | CC0 1.0 |

## Music (`Assets/ThirdParty/Audio/Music`)

Audio overhaul (2026-11-18, docs/audio/AUDIO_REPORT.md section 5). Not CC0: both tracks are by Kevin MacLeod under
**Creative Commons Attribution 4.0** (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/), which allows using them in a
game, sold or not, with credit. The licence and the credit format were read on https://incompetech.com/music/royalty-free/faq.html
on 2026-11-18 ("Title Kevin MacLeod (incompetech.com) Licensed under Creative Commons: By Attribution 4.0"). The credit is
shown in the game on the title page, under the game's own credits (`Strings` key `title.musicCredits`, English and French);
`LicenseTests` checks it. Each shipped file is a seamless loop cut from the original MP3 (a stretch of the piece and a
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
