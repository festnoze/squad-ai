# LEVELNUM progress (the level number on the start-of-level title card)

## How to tune
File: `Build/Play/OutOfSight_Data/StreamingAssets/card_number.json` (a plain text file; the source copy is
`Assets/StreamingAssets/card_number.json`). Edit it with any text editor while the game runs, save, then press R in game
(restart): the level's card shows again with the new values, no relaunch needed. A missing file, a missing key, a value
of the wrong type or broken JSON uses the built-in default (a warning in the player log); out-of-range values are
clamped. The `_help` key is only a reminder and is ignored.

| Key | Meaning | Range | Default |
|---|---|---|---|
| `dimOpacity` | opacity of the dark layer around the digits | 0 to 1 | 0.6 |
| `dimColor` | colour of that layer, `[r, g, b]` (also the inner shade's colour) | each 0 to 1 | `[0.07, 0.07, 0.08]` |
| `washOpacity` | wash inside the digits (0 = perfectly clear glass) | 0 to 1 | 0.04 |
| `washColor` | colour of that wash, `[r, g, b]` | each 0 to 1 | `[1.0, 1.0, 1.0]` |
| `startZoom` | size of the number when the card appears, in times its settled size | 1 to 30 | 12.4 |
| `zoomSeconds` | length of the zoom-out, in seconds (0 = no zoom) | 0 to 10 | 2.0 |
| `settledHeight` | height of the settled digits, as a share of the screen height | 0.1 to 1.2 | 0.5 |
| `fadeSeconds` | fade-out of the card, dim and number after the first input, in seconds | 0.05 to 5 | 0.4 |
| `font` | face of the digits: `inter` (Inter Display Bold), `montserrat` (Montserrat Bold), `bebas` (Bebas Neue), `dmserif` (DM Serif Display, the round 2 and 3 face) | one of the four | `"inter"` |
| `easing` | curve of the zoom-out (ease-out, no overshoot): `expo`, `quint`, `quart`, `cubic` (round 2 and 3), `sine`, `linear` | one of the six | `"expo"` |
| `fadeInSeconds` | fade-in of the dim and the digits when the card appears, in seconds (0 = none) | 0 to 2 | 0.2 |
| `edgeOpacity` | hairline light edge just inside the digits' outline (0 = none) | 0 to 1 | 0.25 |
| `edgeWidth` | width of that hairline, in pixels of a 1080 pixel tall screen | 0.5 to 8 | 1.5 |
| `edgeColor` | colour of the hairline, `[r, g, b]` | each 0 to 1 | `[1.0, 1.0, 1.0]` |
| `innerShadeOpacity` | soft shade (the dim's colour) inside the outline, fading inward (0 = none) | 0 to 1 | 0.2 |
| `innerShadeWidth` | how far inward that shade fades, in pixels of a 1080 pixel tall screen | 1 to 40 | 24 |

The start size is `startZoom` times `settledHeight` screen heights (12.4 x 0.5 = 6.2, as round 3's 10 x 0.62): change
both together to keep it.

Android: StreamingAssets is packed inside the APK, so the file is not read on a phone; the built-in defaults (the same
values as the shipped file) apply. To change the phone's look, copy the tuned values into `CardNumberSettings`
(Assets/Scripts/Runtime/CardNumber.cs) and into the shipped file, then rebuild.

## Request
- Round 1 (2026-11-23): the held intro card (it shows the level title until the first input; since AUTOSTART the world
  runs under it) gets a dim with the level number cut out of it, zooming in about 0.5 s to a modest size above the
  title. The number is the level select's number (card position in levels.json "levels"): level19 is 17.
- Round 2 (the user played the BUILT Windows player): on level13 they saw a small dark "13" with a white outline over
  "Roulettes et vase", the scene did not show through. What they want instead:
  1. a greyish-black layer over the whole screen at reduced opacity, on the scene, under the HUD text;
  2. the digits are see-through holes in it, the scene inside slightly whitened (15 to 25 %), no outline, no dark digits;
  3. settled size big: more than half the screen height, centred, behind the title (the title stays readable on top);
  4. start about 10 times the final size (only part of a digit shows at first);
  5. a slow zoom-out, 1.5 to 2 s, smooth ease-out, no bounce.
  Verified in a built player, then the final Windows build and the APK.
- Round 3 (the user: "exactly right", two changes): (1) the digits much less white, nearly clear (wash 0.2 to 0.05),
  the contrast from the dim (allowed up to about 0.55); (2) the values tunable on Windows without a rebuild, from a
  JSON file in StreamingAssets read at every card, safe fallbacks, clamped.

## Why round 1 failed in the player
Round 1 cut the digits with a uGUI stencil mask (clear, digits write 1, dim drawn where not 1, rim outside). Every
editor check rendered the HUD canvas in Screen Space Camera into the camera's own target, which has a depth-stencil
buffer. In the player the HUD is a Screen Space Overlay canvas that URP draws on the back buffer after the final blit,
and there the stencil did nothing: the digits wrote no hole, the dim covered them like the rest, and only the white rim
showed, hence "a dark 13 with a white outline". It was not shader stripping: the cut shader was in Always Included
Shaders. Lesson: an editor shot in camera space says nothing about an overlay canvas in the player.

## Round 2 design (no stencil, no depth, no destination colour)
- `Assets/Scripts/Runtime/CardNumber.cs` (new, a plain class owned by the Hud):
  - A `CardBackdrop` group (CanvasGroup, alpha = the card's) built right after the red pulse, so it is under the exit
    marker, the eye, the gauges, the card text and every other HUD element. It holds one full-screen RawImage `CardDim`.
  - The digits (level select number, display face DM Serif Display, generated at 480 by a TextGenerator, ink centred)
    are drawn by a CommandBuffer (`Graphics.ExecuteCommandBuffer`, outside any camera) into a mask RenderTexture at half
    the canvas's pixel size, with `OutOfSight/UI Number Mask` (glyph coverage, max blend, its own clip matrix, y flipped
    on top-row-first platforms like Unity's own projection).
  - `CardDim` uses `OutOfSight/UI Card Dim`: per pixel, lerp(dim, wash, mask) with plain alpha blending: dim
    (0.07, 0.07, 0.08) at `DimAlpha` 0.5 outside, white at `WashAlpha` 0.2 inside. It draws the same in an overlay
    canvas on the back buffer, a camera-space canvas or an offscreen UI pass.
  - Zoom: `StartFactor` 10 times the settled scale down to the settled scale (ink height `FinalHeightFraction` 0.62 of
    the canvas height, centred on the screen centre), over `ZoomSeconds` 1.75 s, a cubic ease-out applied in log space
    (steady to the eye, no overshoot). Fits the width: "19" settles at 825 of 1920 (16:9) and 738 of 2147 (20:9).
  - The mask is redrawn every frame while the card shows (a clear and a few quads at half resolution); nothing is drawn
    while the card is invisible. The glyph mesh is rebuilt on a new number and on `Font.textureRebuilt` (guarded against
    the rebuild its own request triggers). `Dispose` (Hud.OnDestroy) releases the texture and the hook.
  - If either shader is missing or unsupported, the layer is a plain dim (no holes) and a warning is logged.
- `Assets/Settings/UiCardDim.shader`, `Assets/Settings/UiNumberMask.shader` (new, no keywords). Round 1's
  `UiStencilCut.shader` and `InkCenter.cs` are deleted, and the stale Always Included entry was removed.
- `Assets/Editor/ProjectSetup.cs`: `CardNumber.DimShaderName`, `CardNumber.MaskShaderName` and `UI/Default` in
  `EnsureAlwaysIncludedShaders`. Both shaders appear in the player build report (Build/levelnum2_build.log).
- `Assets/Scripts/Runtime/Hud.cs`: builds `CardNumber`, sets its number in `ShowLevel` (every load and restart replays
  the zoom), advances its age on the HUD clock (frozen while paused or under a menu, each step capped at 1/30 s so the
  frame after a level build does not skip it) and poses it every frame with the card's alpha. The game title row is
  shown again (round 1 hid it). Kept from round 1: `ReducedMotion` (static hook, the game has no such option: final
  state at once), `HeldCardFadeSeconds` 0.4 s (the held card, dim and holes fade together from the first input; a card
  shown started keeps 4 s then 1 s). Test hooks: `LevelNumberShown`, `LevelNumberAge`, `CardBackdropAlpha`,
  `CardDimShown`, `LevelNumberHolesReady`, `LevelNumberScale`, `LevelNumberFinalScale`, `LevelNumberInkRect`,
  `LevelNumberCoveredShare`.
- `Assets/Scripts/Runtime/LevelSelect.cs`: `CardNumber(index)` and `DisplayNumber(order, levelId)` (round 1).
- `Assets/Scripts/Runtime/Menu.cs`: player hook `-autoShot <dir> [-autoLevel <id>]` (built player only, only with the
  argument): waits for the title, plays the level like a level select card (level13 by default), writes screen captures
  when the zoom reaches 0.1, 0.5, 1.0 s and settled (`<id>_t010.png`, `_t050`, `_t100`, `_settled`), logs a line per
  shot ([AutoShot], with age, scale, ink rect, card alpha), then quits. Example:
  `Build/PlayTest/OutOfSight.exe -screen-width 1920 -screen-height 1080 -screen-fullscreen 0 -autoShot Build/shots/levelnum2 -autoLevel level13 -logFile Build/levelnum2_player.log`
- `Assets/Tests/PlayMode/ProbeTestsLevelNum.cs` (adapted):
  - LevelNum01: holes ready (both shaders), the dim under the card text (sibling order), numbers (level1 1, level20 19,
    level19 17, a test level 0), dim 0.4 to 0.6; per screen (2400 x 1080, 1920 x 1080): at t = 0 the scale is 10 times
    the settled one and the ink over 5 screen heights; settled: final scale, ink over half the screen height, inside the
    width (16 px) and the top, centred; the mask read back has a solid hole (coverage 1) over 2 to 60 % of the screen.
  - LevelNum02: paused, the zoom stands still and finishes after the resume (1.75 s); a restart resets it and starts
    extremely zoomed; reduced motion gives the final scale at once; the first input fades card and dim together.
- `Assets/Tests/PlayMode/ProbeTestsHudV2.cs`: comments only (round 1, the fade length).

## Round 3 changes
- `CardNumberSettings` (in `CardNumber.cs`): the eight values, the built-in defaults (dim 0.55, wash 0.05, the rest as
  round 2), `Load()` from `Application.streamingAssetsPath/card_number.json` (not on Android: `FilePath` is null there),
  `Parse(json, problems)` with Newtonsoft JObject: per key type check, clamp, default and a problem line; bad JSON gives
  all defaults. `CardNumber.SetNumber` (every card: level start, restart, next level) loads it again and applies the
  colours. `Hud.CardDimAlpha`, `NumberZoomSeconds`, `HeldCardFadeSeconds` are now live values from it (`Hud.CardSettings`).
- `Assets/StreamingAssets/card_number.json` (new): the defaults plus a `_help` line. Unity copies it to
  `OutOfSight_Data/StreamingAssets/` in the Windows build (checked in Build/Play).
- `UiCardDim.shader`: dim and wash now mixed premultiplied. Mixing colour and alpha apart drew a pale rim at the glyph
  edges (half dim, half wash = mid-grey at mid alpha), very visible once the wash went down to 0.05. Seen on the first
  round 3 player shot of level13, fixed and checked in the final build.
- Tests: LevelNum01 uses the live `startZoom`; new LevelNum03: the shipped file parses with no problem and equals the
  built-in defaults, wash about 0.05 and dim about 0.55; bad JSON, a text value, out-of-range values (clamped), a
  two-channel colour and missing keys fall back with a problem line each; an edited file (`PathOverride`) shows at the
  next `Game.Restart()` (dim, wash, zoom length, fade, start zoom, settled height), a deleted one gives the defaults.

## Shots
- Built player (round 3, final Build/Play): Build/shots/levelnum3/{level13,level1}_{t010,t050,t100,settled}.png. The
  holes are nearly clear, with no rim, on the dim at 0.55; level1 (bright living room) reads too. No [CardNumber] warning
  in the player logs (the shipped file was read cleanly).
- Built player (round 2): Build/shots/levelnum2/level13_{t010,t050,t100,settled}.png, 1920 x 1080 windowed. The 13 is a
  see-through, slightly whitened hole in the dim, upright, behind "Out of Sight", "Roulettes et vase", the hint, the
  people block and the start line; at 0.1 s only a slab of the 3 shows; settled ink 670 of 1080 px. Player log lines:
  number 13, holes ready True; ages 0.103 / 0.502 / 1.001 / 2.753 s, scales 14.16 / 4.79 / 2.49 / 2.08 (final 2.08).
- Editor (camera-space HUD): Build/shots/levelnum/{level1,level20}_{2400x1080,1920x1080}_{t000,t015,t030,t060,t100,final}.png
  (the round 1 files of the same names were overwritten).

## Runs
- Round 1: compile clean twice; LevelNum01, LevelNum02, HudV2_01, HeldStart01 green twice (TestResults/levelnum.xml).
- Round 2:
  1. BuildWindows to Build/PlayTest/OutOfSight.exe: compile clean, built (Build/levelnum2_build.log); player run with
     -autoShot on level13, exit 0, shots above.
  2. PlayMode `--filter LevelNum0|HudV2_01_|HeldStart01_` (TestResults/levelnum2.xml): 4/4 green. Holes: level1 3.9 %
     (20:9) and 4.8 % (16:9) of the screen, level20 8.4 % and 10.5 %, highest coverage 1.00.
  3. BuildWindows to Build/Play/OutOfSight.exe (no OutOfSight process was running): built (Build/levelnum2_play.log).
  4. BuildAndroid: Build/Android/OutOfSight.apk built, 55.7 MB (limit 150 MB), Build/apk.log.
  One run of the five left unused.
- Round 3 (4 runs):
  1. BuildWindows to Build/PlayTest: built; player shots showed the pale rim at the glyph edges (fixed in the shader).
  2. BuildWindows to Build/Play/OutOfSight.exe (no OutOfSight process was running): built; player shots on level13 and
     level1 clean; card_number.json present in OutOfSight_Data/StreamingAssets.
  3. PlayMode `--filter LevelNum0|HudV2_01_|HeldStart01_` (TestResults/levelnum3.xml): 5/5 green (LevelNum01, 02, 03,
     HudV2_01, HeldStart01).
  4. BuildAndroid: Build/Android/OutOfSight.apk built, 55.7 MB (limit 150 MB), Build/apk.log.

## LEVELNUM2 (2026-11-24): a cleaner, more professional number
Request: nearly clear glass digits cut out of the dim (the scene shows, no white shapes), a clean modern face, crisp
edges at every zoom step, a subtle definition at the edge but no heavy outline, a refined ease-out, settled at about
half the screen height (start size kept), every new look value tunable.

Design choices:
- Face: Inter Display Bold (Inter, opsz 32, wght 700, OFL): a neutral grotesk with even strokes and open numerals,
  set against the DM Serif title. Montserrat Bold, Bebas Neue and DM Serif Display (the old face) are baked too and
  switchable with `font`.
- Edges: the digits are a signed distance field baked offline (tools/bake_level_digits.py: Pillow renders each digit
  4x supersampled, scipy measures the distance, 256 texels per figure height, spread 28 texels). The mask shader turns
  the field into a one-pixel anti-aliased edge with an exact field-to-pixel factor from the zoom's scale (no screen
  derivatives, so no dependency on filtering precision), and the mask is now drawn at full resolution (was half). No
  stair steps or halos at 0.1 s (about 6 screen heights) or settled.
- Glass: wash 0.04 (was 0.05), a 1.5 px hairline light edge at 0.25 just inside the outline (it carries the shape on a
  bright room as on a night one), and a soft inner shade (the dim's colour, 0.2, fading over 24 px) for a slight inset.
  Widths are pixels of a 1080 pixel tall screen and scale with the screen.
- Dim: 0.6 (round 3's last value was 0.7 in the code and 0.5 in the shipped file: the two disagreed, now both 0.6).
- Motion: expo ease-out in log scale (normalized to land exactly on 1, no jump, no overshoot) over 2 s (was cubic over
  1.75 s: expo is done to the eye by about 1.2 s, then glides), from 12.4 times the settled size (6.2 screen heights,
  as before) to `settledHeight` 0.5. The dim and the glass fade in over the first 0.2 s (smoothstep, on the real
  clock; reduced motion skips it).

Changes:
- `tools/bake_level_digits.py` (new) and `tools/fonts/` (the source TTFs and their OFL files, not shipped). Output in
  `Assets/ThirdParty/Fonts/Resources/LevelDigits/`: `<face>.json` (metrics, em/1000 units), `<face>_sdf.bytes` (raw R8,
  bottom row first: no texture import setting can compress or sRGB-convert the field on any platform) and
  `<face>-OFL.txt`. About 0.8 MB per face. Rebake: `python tools/bake_level_digits.py` (needs Pillow, numpy, scipy).
- `CardNumber.cs`: `LevelDigitFont` (loads a face once, R8 texture, RGBA32 fallback), the mesh from its glyphs (no
  TextGenerator, no `Font.textureRebuilt` hook any more), `Ease(kind, t)` (replaces `ZoomEase`), `FadeIn`, `FontName`;
  `CardNumberSettings` has the eight new keys (`font`, `easing`, `fadeInSeconds`, `edgeOpacity`, `edgeWidth`,
  `edgeColor`, `innerShadeOpacity`, `innerShadeWidth`; text keys checked against their lists) and the new defaults.
- `UiNumberMask.shader`: distance field to coverage (r), hairline (g) and inner shade (b). `UiCardDim.shader`: the glass
  is wash, then shade, then hairline, premultiplied, mixed with the dim by the coverage as before.
- `Hud.LevelNumberFont` (test hook); `Menu.AutoShot` logs the face and the easing.
- `card_number.json`: every key, the new defaults (identical to the code's).
- Tests (`ProbeTestsLevelNum.cs`): LevelNum01 dim 0.5 to 0.7, the face loaded, settled ink height = settledHeight
  (within 1 unit), holes 1 to 60 % of the screen; LevelNum03 compares the new keys, checks all four faces load with
  ten digits, the easings are monotonic, land on 1 and never overshoot, a bad `font` or `easing` falls back with a
  problem line, an edited file switches the face (bebas) and the easing at the next restart (its dim check was wrong,
  0.7 for a file saying 0.8: fixed).

Shots:
- Built player (Build/PlayTest, edge 0.3): Build/shots/levelnum4/{level13,level1,level20}_{t010,t050,t100,settled}.png,
  1920 x 1080 windowed. Settled ink 540 of 1080 px, centred; ages 0.10 / 0.50 / 1.00 / 3.0 s, scales (level13)
  4.09 / 1.11 / 0.77 / 0.72 (final 0.72). Edges crisp at every step; the glass reads on the bright living room
  (level1), level13 and the night level20; the hairline was a touch strong on the night level, hence 0.25.
- Final build (Build/Play, edge 0.25): Build/shots/levelnum4_final/, same names.
- Editor, 20:9 and 16:9: Build/shots/levelnum/{level1,level20}_{2400x1080,1920x1080}_{t000,...,final}.png: centred,
  inside the width.

Runs (4 Unity runs):
1. BuildWindows to Build/PlayTest (Build/levelnum4_build.log): built, both shaders compiled; player shots above, no
   [CardNumber] warning.
2. PlayMode `--filter LevelNum0|HudV2_01_|HeldStart01_` (TestResults/levelnum4.xml): 5/5 green. Holes: level1 2.7 %
   (20:9) and 3.4 % (16:9), level20 7.5 % and 9.3 %, highest coverage 1.00.
3. BuildWindows to Build/Play/OutOfSight.exe (no OutOfSight process was running at that moment; one was running at the
   start of the task and had closed): built (Build/levelnum4_play.log), card_number.json in StreamingAssets.
4. BuildAndroid: Build/Android/OutOfSight.apk built, 56.3 MB (limit 150 MB), Build/apk.log.
The final build was also shot (player runs, not Unity runs): Build/shots/levelnum4_final/, clean on all three levels.

## A VERIFIER
- LEVELNUM2: the digit atlas is an R8 texture loaded from raw bytes; on a phone without R8 sampling the RGBA32
  fallback is used. Not seen on a device yet.
- LEVELNUM2: the hairline (0.25) and the inner shade (0.2) were judged on three levels at 1920 x 1080; if the user
  still sees "an outline", lower `edgeOpacity` (0 removes it).
- Android (Vulkan or GLES3 on the phone): the mask's y flip relies on UNITY_UV_STARTS_AT_TOP and Unity's Vulkan
  conversion. If the number shows upside down on the phone only, the flip in UiNumberMask.shader is the place.
- Round 3 values (dim 0.55, wash 0.05) were judged on level13 and level1 in the built player; the night levels were not
  shot again in round 3 (round 2's level20 shot had wash 0.2).
- Values tuned in card_number.json do not reach Android: copy them into CardNumberSettings and rebuild the APK.
- The settled number (62 % of the height in round 3, 50 % since LEVELNUM2, centred) sits behind the title, the hint and the player's furniture at the
  screen centre while the card is held; the chair stays visible through the hole or the dim.
- The hold-off card (probe, look, tests) also shows the dim and the zoom for its 5 s: look shots taken in the first 5 s
  of a level are dimmed.
- No reduced-motion option exists in the game; `Hud.ReducedMotion` is only a hook.
- Speech bubbles and other canvases sorted under the HUD canvas are dimmed with the scene while the card shows.

- User tuning (2026-11-23): the digits more white than clear (wash 0.6) on a lighter dim (0.35); shipped file, built-in defaults and LevelNum01 bounds updated. A VERIFIER: LevelNum tests not rerun; the wash at 0.6 on very bright rooms.
- User tuning (2026-11-23): wash halved to 0.3 (0.6 read too white).
- User tuning (2026-11-23, final): dim 0.7, wash 0.05 (the user's values from the built file), copied into the shipped file, the defaults and LevelNum01's bounds.
- User choice (2026-11-24): the default face back to DM Serif Display (dmserif); every other LEVELNUM2 value kept.
