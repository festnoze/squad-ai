# Third party assets

Every file under `Assets/ThirdParty` is listed here with its title, author, source and licence.
This is the licence file required by the M3 gate (PRD 11). The EditMode test `LicenseTests`
fails when a file under `Assets/ThirdParty` has no line here.

All assets below are **CC0 1.0 Universal** (public domain dedication,
https://creativecommons.org/publicdomain/zero/1.0/). CC0 requires no attribution: the credits
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

M4.2. Each file is a 512 x 512 grayscale detail derived from the 1K-JPG download of an ambientCG material
(https://ambientcg.com/get?file=<id>_1K-JPG.zip): the luminance of its Color map (times its AmbientOcclusion
map for the parquet seams), rotated so the grain or the planks run vertically, high-passed and softened with
wrap-around filters (still seamless), then remapped to a low contrast with a mean of exactly 240/255 and the
highlights capped at 1.0. The licence was read on each item's own page (`https://ambientcg.com/a/<id>`) and on
https://docs.ambientcg.com/license/ on 2026-11-13: "All assets are released under the Creative Commons CC0
license".

| File | Title | Author | Source | Licence |
|---|---|---|---|---|
| `ambientCG/detail_wood_Wood049.png` | Wood 049 (furniture wood grain) | ambientCG | https://ambientcg.com/a/Wood049 | CC0 1.0 |
| `ambientCG/detail_parquet_WoodFloor051.png` | Wood Floor 051 (parquet of the hard floors) | ambientCG | https://ambientcg.com/a/WoodFloor051 | CC0 1.0 |
| `ambientCG/detail_plaster_Plaster001.png` | Plaster 001 (walls and caps) | ambientCG | https://ambientcg.com/a/Plaster001 | CC0 1.0 |
| `ambientCG/detail_upholstery_Fabric011.png` | Fabric 011 (upholstery weave) | ambientCG | https://ambientcg.com/a/Fabric011 | CC0 1.0 |
| `ambientCG/detail_linen_Fabric036.png` | Fabric 036 (linen: clothes, table cloths, lamp shade) | ambientCG | https://ambientcg.com/a/Fabric036 | CC0 1.0 |
| `ambientCG/detail_carpet_Carpet012.png` | Carpet 012 (rugs, doormat, soft floors) | ambientCG | https://ambientcg.com/a/Carpet012 | CC0 1.0 |

## Audio (`Assets/ThirdParty/Audio`)

Every clip was converted to mono 44.1 kHz 16-bit WAV, then trimmed and faded, by
`tools/assets/audio_derive.py`. The original file names are given in parentheses.

| File | Title | Author | Source | Licence |
|---|---|---|---|---|
| `hop_01.wav`, `hop_02.wav` | 75 CC0 breaking / falling / hit sfx (bfh1_wood_hit_01, 02) | rubberduck | https://opengameart.org/content/75-cc0-breaking-falling-hit-sfx | CC0 1.0 |
| `hop_03.wav`, `hop_04.wav` | 100 CC0 metal and wood SFX (wood_hit_05, 09) | rubberduck | https://opengameart.org/content/100-cc0-metal-and-wood-sfx | CC0 1.0 |
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
