# LEVELNUM progress (the level number on the start-of-level title card)

## How to tune
File: `Build/Play/OutOfSight_Data/StreamingAssets/card_number.json` (a plain text file; the source copy is
`Assets/StreamingAssets/card_number.json`). Edit it with any text editor while the game runs, save, then press R in game
(restart): the level's card shows again with the new values, no relaunch needed. A missing file, a missing key, a value
of the wrong type or broken JSON uses the built-in default (a warning in the player log); out-of-range values are
clamped. The `_help` key is only a reminder and is ignored.

| Key | Meaning | Range | Default |
|---|---|---|---|
| `dimOpacity` | opacity of the dark layer around the digits | 0 to 1 | 0.55 |
| `dimColor` | colour of that layer, `[r, g, b]` | each 0 to 1 | `[0.07, 0.07, 0.08]` |
| `washOpacity` | white wash inside the digits (0 = perfectly clear holes) | 0 to 1 | 0.05 |
| `washColor` | colour of that wash, `[r, g, b]` | each 0 to 1 | `[1.0, 1.0, 1.0]` |
| `startZoom` | size of the number when the card appears, in times its settled size | 1 to 30 | 10 |
| `zoomSeconds` | length of the zoom-out, in seconds (0 = no zoom) | 0 to 10 | 1.75 |
| `settledHeight` | height of the settled digits, as a share of the screen height | 0.1 to 1.2 | 0.62 |
| `fadeSeconds` | fade-out of the card, dim and number after the first input, in seconds | 0.05 to 5 | 0.4 |

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

## A VERIFIER
- Android (Vulkan or GLES3 on the phone): the mask's y flip relies on UNITY_UV_STARTS_AT_TOP and Unity's Vulkan
  conversion. If the number shows upside down on the phone only, the flip in UiNumberMask.shader is the place.
- Round 3 values (dim 0.55, wash 0.05) were judged on level13 and level1 in the built player; the night levels were not
  shot again in round 3 (round 2's level20 shot had wash 0.2).
- Values tuned in card_number.json do not reach Android: copy them into CardNumberSettings and rebuild the APK.
- The settled number (62 % of the height, centred) sits behind the title, the hint and the player's furniture at the
  screen centre while the card is held; the chair stays visible through the hole or the dim.
- The hold-off card (probe, look, tests) also shows the dim and the zoom for its 5 s: look shots taken in the first 5 s
  of a level are dimmed.
- No reduced-motion option exists in the game; `Hud.ReducedMotion` is only a hook.
- Speech bubbles and other canvases sorted under the HUD canvas are dimmed with the scene while the card shows.
