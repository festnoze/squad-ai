# Textures

Every file in this directory comes from **ambientCG** (https://ambientcg.com)
and is released under **CC0 1.0 Universal** (public domain dedication): no
attribution is required, and none of it restricts how this project ships.

They are here because the owner revised the asset policy of `docs/PRD_VISUAL.md`
section 3.2 on 2026-09-07, asking for real material detail rather than the
purely procedural surfaces the original policy allowed. Appendix C of that
document records the change and why. Before that date the project shipped no
binary asset at all except one UI font.

## What is here

Ten 1K PBR sets, as JPEG, with only the maps the game samples:

| set | used for |
|---|---|
| `Concrete034` | grey permanent ground and blocks (`platform`) |
| `Plaster001` | pale carvable ground (`platform_soft`) and lavender matter |
| `Rock030` | island skirts under the platforms |
| `Rock023` | decor islands on the horizon |
| `PavingStones092` | stone: stairs, socles, the teleporter pillar |
| `Wood067` | crates and bridge decks |
| `Metal032` | brushed steel: the sealed cage |
| `Metal030` | dull lead: the sealed battery |
| `MetalPlates006` | the teleporter machine |
| `Cardboard004` | paper: the polaroid frame |

## Map naming, which is a contract

`Assets/Editor/TextureImportRules.cs` reads the suffix to decide the import
settings, so the names are not cosmetic:

    <Set>_Color.jpg    albedo, the ONLY sRGB map
    <Set>_Normal.jpg   OpenGL convention normal map
    <Set>_Rough.jpg    roughness, linear data
    <Set>_Metal.jpg    metalness, linear data
    <Set>_Height.jpg   displacement, linear data
    <Set>_AO.jpg       ambient occlusion, linear data

Two traps are worth restating, because both produce a picture that looks
plausible instead of an error:

- ambientCG ships **NormalDX and NormalGL**. Unity wants **GL**. Importing the
  DX map inverts the green channel, so every bump becomes a dent and the light
  appears to come from the wrong side.
- roughness, metalness, height and AO are **data, not colour**. Imported with
  sRGB on (Unity's default) they are gamma decoded on sample, and a roughness of
  0.5 arrives as 0.21: the whole world turns glossy.

Both are handled by the import rules above, which is why the settings live in
code and not in `.meta` files edited by hand.

## Replacing a set

Download `<Set>_1K-JPG.zip` from ambientCG, extract only the maps listed above,
rename them to the pattern, and drop them here. The import rules do the rest.
Anything larger than 1K is capped to 1024 on import.
