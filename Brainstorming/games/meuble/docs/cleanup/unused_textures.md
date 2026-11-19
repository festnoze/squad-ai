# Unused textures cleanup (2026-11-19)

Scope: every image (png, jpg, jpeg, tga, psd, exr, hdr, tif) under `Assets` of Out of Sight. The project has 79
such images, all PNG. Usage was checked against:
1. GUID references (from each image's `.meta`) in every `.asset`, `.mat`, `.unity`, `.prefab`, `.controller`,
   `.anim`, `.json` and non-texture `.meta` file under `Assets` and `ProjectSettings` (433 candidate files).
2. Path/file name/stem references in `Assets/Scripts`, `Assets/Editor`, `Assets/Tests` (`Resources.Load`,
   folder scans, name constants).
3. Inputs of a live pipeline script (`tools/assets/derive_env_textures.py`, `derive_env_colours.py`).
4. Product owner originals whose derived copy is used.
5. Third-party package requirements (not applicable here: no texture lives under `Assets/ThirdParty`).

## Result

69 of the 79 images are used (Environment originals and their `Colour/`/`Detail/` derivatives, the rug picture,
the 3 app icons referenced by GUID in `ProjectSettings.asset`, the head-around images and their
`Resources/CharacterManHeadWrap.png` / `CharacterWomanHeadWrap.png` copies loaded by `CharacterHead.cs`, the
clothes files packed into `Resources/CharacterClothesAtlas.png` loaded by `CharacterLook.cs`/`Tuning.cs`).

10 images are unused. All 10 live in `Assets/Art/Characters` and are confirmed dead by three independent checks:
zero GUID references anywhere, zero code references anywhere, and `docs/LICENSES.md` (lines 166-167, written for
the 2026-11-18 head rework) already states in prose that these exact files "are not used by the game". They are
the old face renders, the old head-back renders, their respective source photos, and two fabric swatches that
fed the old (pre-head-around) pipeline.

| Path | Size | Rule that makes it unused |
|---|---:|---|
| `Assets/Art/Characters/man_face.png` | 35 736 B | Superseded: heads now use only `man_head_around.png` (rule 2/4); no GUID or code reference; `docs/LICENSES.md` lists it as not used by the game. |
| `Assets/Art/Characters/man_face_source.png` | 1 735 474 B | Source of the dead `man_face.png` above; no reference anywhere; not a rule-3/4 pipeline input (no script reads it); listed as not used in `docs/LICENSES.md`. |
| `Assets/Art/Characters/woman_face.png` | 30 992 B | Same as `man_face.png`, woman variant. |
| `Assets/Art/Characters/woman_face_source.png` | 1 754 976 B | Same as `man_face_source.png`, woman variant. |
| `Assets/Art/Characters/man_head_back.png` | 50 147 B | Superseded: heads now use only `man_head_around.png` wrapped once around (rule 2/4), not a separate back image; no GUID or code reference; listed as not used in `docs/LICENSES.md`. |
| `Assets/Art/Characters/man_head_back_source.png` | 1 751 868 B | Source of the dead `man_head_back.png`; no reference anywhere; listed as not used in `docs/LICENSES.md`. |
| `Assets/Art/Characters/woman_head_back.png` | 48 847 B | Same as `man_head_back.png`, woman variant. |
| `Assets/Art/Characters/woman_head_back_source.png` | 1 775 233 B | Same as `man_head_back_source.png`, woman variant. |
| `Assets/Art/Characters/cotton_source.png` | 3 797 176 B | Fabric swatch for the retired `tools/assets/derive_textures.py` pipeline (ambientCG-era); not read by any current script or asset; listed as not used in `docs/LICENSES.md`. |
| `Assets/Art/Characters/twill_source.png` | 3 583 564 B | Same as `cotton_source.png`. |

Total moved: 10 images, 13 819 013 bytes of PNG payload (~13.18 MiB; ~13.92 MiB including the 10 `.meta`
siblings). None of the 10 live under a `Resources` folder, so none shipped in a build; all 10 were editor-only
disk weight.

## Kept, unsure

These were considered for removal but kept because the project's own documentation treats them as still live,
even though no GUID or C# reference was found for them (no automated atlas-packing script exists any more, so
the reference trail is documentation only):

- `Assets/Art/Characters/shirt_front.png`, `shirt_back.png`, `trousers_front.png`, `trousers_back.png`
- `Assets/Art/Characters/shirt_front_source.png`, `shirt_back_source.png`, `trousers_front_source.png`,
  `trousers_back_source.png`

`docs/LICENSES.md` (same 2026-11-18 paragraph) explicitly separates these from the confirmed-dead list above:
it says the clothes files are "derived from their sources" and that `Resources/CharacterClothesAtlas.png`
(loaded at run time by `CharacterLook.cs` via `Tuning.ClothesAtlasResource`) "packs them", and it does **not**
include any of these 8 files in the sentence naming what is unused. Treated as rule 4 originals/derivatives
behind a currently shipped asset (the atlas), the same way the Environment source PNGs are kept behind
`Detail/` and `Colour/`. Left in place; not moved.

## Everything else (69 images) stays

- `Assets/Art/Environment/{wood,parquet,plaster,upholstery,linen,carpet,grass,lacquer,metal,plastic,foliage,soil,tile}.png`
  (13 files): rule 3, read directly by `tools/assets/derive_env_textures.py` and `derive_env_colours.py`
  (`SRC = Assets/Art/Environment`, `luminance(os.path.join(SRC, name + ".png"))`).
- `Assets/Art/Environment/crepi_cream_source.png`: rule 4, the product owner's original photo behind
  `plaster.png` (`docs/LICENSES.md` line 81); explicitly called out as a keeper by the cleanup brief.
- `Assets/Art/Environment/red_metal_source.png`: rule 3, matched by `derive_env_colours.py`'s
  `PLAYER_SOURCES` glob (`"red*"`) and read to build `Colour/colour_player.png`.
- `Assets/Art/Environment/rug_modern_inset_border.png`: rule 1, GUID referenced in
  `Assets/Resources/TextureLibrary.asset` (`TextureLibrary.rugColour`).
- `Assets/Art/Environment/Colour/colour_*.png` (14 files) and `Assets/Art/Environment/Detail/detail_*.png` /
  `normal_*.png` (23 files): rule 1, all GUID referenced in `Assets/Resources/TextureLibrary.asset`.
- `Assets/Art/Icon/AppIcon_1024.png`, `AppIcon_Adaptive_Foreground_1024.png`,
  `AppIcon_Adaptive_Background_1024.png`: rule 1, GUID referenced in `ProjectSettings/ProjectSettings.asset`
  (player icon slots).
- `Assets/Art/Characters/man_head_around.png`, `woman_head_around.png`: rule 4, the product owner originals
  copied unchanged to the two Resources wraps below (`docs/LICENSES.md` lines 162-164).
- `Assets/Art/Characters/Resources/CharacterManHeadWrap.png`, `CharacterWomanHeadWrap.png`: rule 2,
  `Resources.Load<Texture2D>("CharacterManHeadWrap" / "CharacterWomanHeadWrap")` in
  `Assets/Scripts/Runtime/CharacterHead.cs`.
- `Assets/Art/Characters/Resources/CharacterClothesAtlas.png`: rule 2,
  `Resources.Load<Texture2D>(Tuning.ClothesAtlasResource)` in `Assets/Scripts/Runtime/CharacterLook.cs`
  (`Tuning.ClothesAtlasResource = "CharacterClothesAtlas"`).
- The 8 clothes files listed under "Kept, unsure" above.

## Moved to

`C:\Dev\outofsight_removed_assets\Assets\Art\Characters\<file>` and `<file>.meta` (same relative path as in the
project), one subfolder per moved file's original location. Nothing was deleted; the product owner can restore
any file by moving it back under `games/meuble/Assets/Art/Characters/`.
