# HUD gauge icons: Creak and Suspicion (2026-11-19)

Replaces the generic zigzag (Creak / Grincement) and magnifier (Suspicion / Soupçon) next to the two HUD gauges.
Original work, made for the game (listed in `docs/LICENSES.md`, section UI icons).

## Deliverables

| File | What |
|---|---|
| `Assets/Art/UI/Icons/creak.svg` | Creak icon, viewBox 0 0 64 64, one filled path, `#FFFFFF` |
| `Assets/Art/UI/Icons/suspicion.svg` | Suspicion icon, same format |
| `Assets/Art/UI/Icons/creak.png` | 256x256 RGBA render: RGB pure white everywhere, coverage in alpha, transparent background |
| `Assets/Art/UI/Icons/suspicion.png` | same |

Colours: the glyphs are pure white so the HUD tints them with `Image.color`. Tints checked on `sheet_final.png`:
cream `#FFF0D1` (Menu.TitleInk), the bar colours `#DB9E57` (Hud.CreakWood) and `#FFCC40` (Hud.SuspicionLow), and the
alarm red `#E64236` (Hud.PrimaryRedHover), on the gauge plate `#1A1A1F` (Hud.GaugeBack) and on a bare warm floor.

PNG import (`.png.meta`, written by hand from `Assets/Art/Icon/AppIcon_1024.png.meta`): Sprite (single, full rect),
mipmaps on with trilinear filtering (the HUD draws them at about 46 px, mips keep the 256 px source smooth when scaled
down), clamp, alpha is transparency, no compression, max size 256. The `.svg` files have no hand-written meta: Unity
imports them with its default importer (the built-in vector graphics module) or ignores them; the PNGs are what the HUD
should use. The SVGs carry no strokes, masks or CSS, so any SVG importer reads them.

## Candidates (sheets in this folder)

Shared rules: 64-unit grid, 5-unit strokes with round caps and joins, flat, no gradients, no text.

- `sheet_1_candidates_ABCD.png`
  - A: side-view chair + two sound arcs / heavy-lidded eye with a raised brow.
  - B: chair leg pressing a bending floor + jolt ticks / two narrowed side-glancing eyes.
  - C: chair + jagged creak zigzag / eye with alert ticks.
  - D: chair tilted on its back leg + vibration ticks / eye with a frowning and a raised brow.
  - Verdict: every side-view chair reads as the letter "h"; all the eyes are tiny at 32 px, and an eye clashes with the
    eye in the middle of the HUD (the seen / unseen indicator).
- `sheet_2_candidates_EF.png`: front-view chair with wobble arcs or shake ticks / skeptical face, big narrowed eyes.
  Verdict: the front-view chair reads as the letter "A". The face is the right idea: it says "a person is getting
  suspicious" and never looks like the visibility eye.
- `sheet_3_candidates_GHI.png`: 3/4 chair (solid backrest and seat, stroked legs) with sound arcs (G, I) or jags (H);
  outlined face (G), outlined head cap (H), solid head with knocked-out features (I).
  Verdict: the 3/4 chair is a chair at once, and arcs say "sound" better than jags. The outlined faces look light next
  to the solid chair; the solid head (I) matches it, but its half-disc eyes read as sunglasses.
- `sheet_4_refine_IJ_mono.png`: refinement J, lidded eyes with the pupils glancing sideways (the raised-eyebrow look).

## Choice: pair J, refined twice

- **Creak: a 3/4 chair sending two sound arcs.** It is the player (a chair) making a noise; nothing else in the HUD
  uses a chair, so it cannot be mistaken.
- **Suspicion: a solid head with a skeptical side-eye**: one low, flat brow, one raised arched brow, heavy lids with the
  pupils looking aside, a slanted mouth. It is the universal "suspicious" face and is a person, so it never competes
  with the visibility eye.
- Why it is a pair: same visual grammar (a solid shape built from the same 5-unit round strokes), the same weight and
  corner radius, both fill the 64 grid edge to edge.
- Refinement 1: pupils under the lids instead of half-disc eyes (no sunglasses read), bigger arcs.
- Refinement 2: chair moved 1.5 units left and arcs spread so the two arcs stay separate at 32 px; left brow lowered
  so it does not merge with the lid at 32 px.

## Rebuilding

`gen.py` (candidate sheets) and `final.py` (bakes pair J: strokes outlined and merged with Skia path ops into one
filled path per icon, then the SVG, the PNG and `sheet_final.png`). Run them in a throwaway venv outside the repo with
`pip install resvg-py skia-python pillow numpy` (cairosvg needs a Cairo DLL that this machine does not have).
`final.py` checks the baked path against the stroked source: the alpha matches within anti-aliasing.

# Options icons: Defaults, Back and the Language flags (2026-11-20)

Product owner request: icons on the Options page's "Par défaut" (Defaults) and "Retour" (Back) buttons, and the Language
row's globe replaced by the flag of the chosen language (French flag in French, US flag in English), switching live.
Original work, listed in `docs/LICENSES.md` (section UI icons).

| File | What |
|---|---|
| `Assets/Art/UI/Icons/reset.svg`, `reset.png` | Defaults: an anticlockwise open-circle arrow, its solid head at the top pointing into the gap |
| `Assets/Art/UI/Icons/back.svg`, `back.png` | Back: a left arrow, round-capped shaft and solid rounded head |
| `Assets/Art/UI/Icons/flag_fr.svg`, `flag_fr.png` | French flag: three vertical bands, blue `#1F5BC4`, white, red `#E8333A` |
| `Assets/Art/UI/Icons/flag_us.svg`, `flag_us.png` | US flag: 13 stripes (red `#C8283C` and white), a blue `#33417F` canton with a staggered 4-3-4-3-4 star grid |

- Same grammar as the HUD pair: 64-unit grid, round caps and joins, flat, no text. The two glyphs are one filled white
  path each (6-unit strokes, since they are line glyphs) and the PNG is pure white with the coverage in alpha, so the menu
  tints them with its cream label ink (`Menu.TitleInk`).
- The flags are drawn as is (not tinted): a 3:2 rounded rectangle (58 x 38.7 units, corner radius 5) on a thin
  semi-transparent dark rim, so the edge holds on the brown rest plate and on the red selected plate (the French red band
  next to the red selection). Layers are stacked (the white body first, the colours over it) so no two colours abut:
  abutting anti-aliased edges leave a see-through seam.
- 13 stripes were kept over a simplified 7-stripe variant: at the menu's 52 reference px both read, and 13 is the real
  flag. The stars are small enough to read as stars at 128 px and as a light speckle at 52 px.
- The PNG import settings are the HUD pair's (UiIconLibraryBuilder enforces them; the flags use them too, alpha is
  transparency so the colour is dilated under the transparent margin). `UiIconLibrary` holds `reset`, `back`,
  `flagFrench`, `flagEnglish`; a missing glyph leaves its button without an icon (label centred as before), a missing
  flag falls back to the procedural globe.
- In the menu (`Menu.OptionsPlainButton`), the Defaults and Back icons sit where the value rows' icons sit (inset 14,
  52 units) and their labels start where the value rows' labels start, so the column reads as one. The Language row's
  icon is swapped by `Menu.RefreshOptionsTexts`, which runs on every language change (`Strings.LanguageChanged`).
- Checked by `OptionsIconsTests` (EditMode: files, white glyphs, flag colours, library, licence rows) and
  `ProbeTestsOptionsIcons.Step79a_` (PlayMode: icons, live flag swap, navigation, fit on 1920 x 1080, 2400 x 1080 and
  1440 x 1080, screenshots to `TestResults/options` or the folder in `OOS_SHOTS_DIR`, never under docs).

Rebuilding: `options_icons.py` (this folder) writes the SVGs and PNGs and a review sheet (the icons on the Options plates
at 32 to 128 px) to the folder given as its first argument (`--candidates` renders the variants compared). Same throwaway
venv as above, outside the repo.
