# FISHEYE progress (a barrel distortion and a peripheral blur on the title menu's moving 3D background)

## How to tune
File: `Build/Play/OutOfSight_Data/StreamingAssets/menu_camera.json` (a plain text file; the source copy is
`Assets/StreamingAssets/menu_camera.json`). Edit it with any text editor while the title menu is open and save: the
menu checks the file's write time every 2 s and reads it again when it changed, so the change shows within about 2 s,
no relaunch and no rebuild. The file is also read every time the title menu opens. A missing file, a missing key, a
value of the wrong type or broken JSON uses the built-in default (a `[MenuCamera]` warning in the player log);
out-of-range values are clamped. The `_help` key is only a reminder and is ignored.

| Key | Meaning | Range | Default |
|---|---|---|---|
| `fisheyeStrength` | barrel coefficient k: the centre of the picture shows 1 + k times larger than the farthest corner; 0 = no distortion | 0 to 1 | 0.3 |
| `fisheyeZoom` | 1 = auto-fit (the farthest corner lands exactly on its corner: no black, no stretched border); above 1 crops further in; below 1 zooms out and shows black borders | 0.5 to 2 | 1.0 |
| `fisheyeVignette` | darkening towards the corners, on top of the game's own post-processing vignette (0 = none) | 0 to 1 | 0.2 |
| `peripheralBlur` | blur of the periphery, the centre stays sharp (0 = off: no extra texture read at all) | 0 to 1 | 0.3 |
| `peripheralBlurRadius` | size of the sharp centre: where the blur starts, as a share of the way from the lens centre to the screen edge on each side (each corner is 1, the middle of each edge 0.71); the blur then ramps up smoothly over 0.45 more | 0 to 1 | 0.4 |
| `peripheralBlurMotion` | look of the blur: 0 = plain soft blur (peripheral vision), 1 = radial streak (zoom or motion blur), in between a mix | 0 to 1 | 0.6 |

With `fisheyeStrength` 0, `fisheyeVignette` 0, `peripheralBlur` 0 and `fisheyeZoom` 1 the pass is not even enqueued
(zero cost). With `peripheralBlur` 0 alone, the lens still runs but every pixel takes one texture read, no blur tap.
At full strength the streak is 0.05 screen heights long (54 px on a 1080 px screen) and the soft disc 0.012 heights in
radius (13 px), scaled by `peripheralBlur` and by the ramp.

Android: StreamingAssets is packed inside the APK, so the file is not read on a phone; the built-in defaults (the same
values as the shipped file) apply. To change the phone's look, copy the tuned values into `MenuCameraSettings`
(Assets/Scripts/Runtime/MenuFisheye.cs) and into the shipped file, then rebuild.

## Live slider panel (FISHEYEUI, 2026-11-24)
On Windows (standalone player and the editor; not Android), on the title's main page, press **I** to show or hide a
dark panel along the bottom of the screen, right of the button column: one slider per key above (name, current value,
range). A slider changes the background on the same frame.
- **Save** writes the six values to `StreamingAssets/menu_camera.json` (the player's copy in a build, the source copy
  `Assets/StreamingAssets/menu_camera.json` in the editor), keeping `_help` and any other key, 2-space indentation,
  3 decimals, then reads the file back.
- **Reset** puts the built-in defaults (`MenuCameraSettings` values) on the sliders and the effect, not saved.
- **Copy** puts the six values as JSON on the clipboard (to paste to the coordinator).
- While the panel is shown the 2 s file check is paused (`MenuFisheye.HoldFile`), so the file never snaps the sliders
  back. Unsaved values stay in use until the title next opens (the file is read again then).
- The panel hides itself when the main page goes away (Jouer, Niveaux, Options, Crédits). Hidden, its objects are
  inactive; shown, its widgets have no navigation links and a click on one hands the selection back to the menu button
  as soon as the mouse button is up, so the keyboard and the gamepad keep driving the menu. Nothing else reads I.
- Files: new `Assets/Scripts/Runtime/MenuFisheyeTuner.cs`; `MenuFisheye.cs` (Attach adds the tuner, `HoldFile`,
  `Override`, `MenuCameraSettings.From` and `ToJson`). The shipped defaults and file are unchanged.

## Request (2026-11-24)
A fish-eye on the moving 3D background of the main menu (the TitleCameraTour loop), never on the menu UI, the title
logo, the level-number card or gameplay; its intensity tunable on Windows without a rebuild, like card_number.json;
works in the built player on Windows and Android.
Addition (same day): a peripheral blur, sharp centre and blurred periphery (motion blur or peripheral vision feel), in
the same file and pass: `peripheralBlur`, `peripheralBlurRadius` and the optional `peripheralBlurMotion`; cheap on
mobile (a few taps, no extra target), nothing at strength 0.

## Design
- No renderer asset is touched. `MenuFisheye` (a component added to the tour camera by `TitleCameraTour.Attach`)
  subscribes to `RenderPipelineManager.beginCameraRendering` and, only for the tour's own camera and only while
  `TitleCameraTour.Active` (the title open over the title house), enqueues `MenuFisheyePass` on that camera's renderer
  (`UniversalAdditionalCameraData.scriptableRenderer.EnqueuePass`). In a level the tour is inactive and nothing is
  enqueued: PC_Renderer and Mobile_Renderer render gameplay exactly as before. Other cameras (the title logo's own
  camera, level miniatures, test cameras) are never touched.
- `MenuFisheyePass` (Render Graph, `RecordRenderGraph` only): at `AfterRenderingPostProcessing`, one full-screen
  `AddBlitPass` of the camera colour through `OutOfSight/Menu Fisheye` into one pooled texture of the same size (no MSAA,
  no depth), which then becomes the camera colour, so URP's final blit reads it (no copy back). A distortion cannot read
  and write the same pixels, so this one transient texture is the minimum. `requiresIntermediateTexture` makes URP keep
  an intermediate colour texture on a camera that would draw straight to the back buffer (a phone without
  post-processing); if the active target is the back buffer anyway, the pass skips itself with one warning.
- The menu canvas, the title logo (rendered by its own camera into a texture shown on an overlay canvas) and the HUD
  are Screen Space Overlay canvases drawn after the final blit: never distorted.
- Lens (`Assets/Settings/MenuFisheye.shader`, mirrored by `MenuFisheye.SourceUv` for the tests): for an output pixel
  at uv with offset d from the lens centre and r2 its squared radius in screen heights over the farthest corner's, the
  source is centre + d * (1 + k r2) / ((1 + k) zoom). The centre is the camera's optical axis (the tour's lens shift puts
  it at x 0.65, on the vanishing point right of the title column), so the bulge sits where the camera looks. Any point
  samples on the segment from the centre to itself (zoom 1), so nothing outside the picture is ever sampled whatever
  the centre and the aspect (16:9, 20:9). Out-of-picture samples (zoom below 1) are black, never a clamped smear.
- Peripheral blur, in the same fragment: weight = `peripheralBlur` * smoothstep(radius, radius + 0.45, rb), rb measured
  per side (the way from the lens centre to that side's edge), so the left and right edges blur alike although the lens
  centre sits at x 0.65. Where the weight is above 0.0005 the pixel takes 7 more taps (8 in all) around its lens
  sample, each offset by a mix (`peripheralBlurMotion`) of a soft disc (golden angle spiral) and a radial streak through
  the sample (alternately inward and outward, so nothing shifts), in a fixed pattern: a per-pixel jitter was tried
  first and read as grain (it raised the measured border detail instead of lowering it). The sharp centre and blur 0
  skip the taps (a branch); no extra render target. Mobile cost on the menu only: 8 bilinear reads per peripheral pixel.
- Stripping: the material is created from code, so `MenuFisheye.ShaderName` is in Always Included Shaders
  (`ProjectSetup.EnsureAlwaysIncludedShaders`, next to UiCardDim and UiNumberMask). One pass, no keyword.
- `MenuCameraSettings` follows `CardNumberSettings` (same `Number` reader, made internal for it): `Load()`,
  `Parse(json, problems)`, `PathOverride` for tests, `FilePath` null on Android.
- `--titletour <dir>` (TitleCameraTour, built player) now also writes a `fisheye:` line in titletour.txt (active, file,
  values, loads, the shader's parameters).

## Files
- New: `Assets/Scripts/Runtime/MenuFisheye.cs` (MenuFisheye, MenuFisheyePass, MenuCameraSettings),
  `Assets/Settings/MenuFisheye.shader`, `Assets/StreamingAssets/menu_camera.json`,
  `Assets/Tests/PlayMode/ProbeTestsFisheye.cs`.
- Changed: `TitleCameraTour.cs` (Attach adds MenuFisheye; the titletour report line), `CardNumber.cs`
  (`CardNumberSettings.Number` internal), `Assets/Editor/ProjectSetup.cs` (Always Included).

## Shots
- Built player (Build/PlayTest, 1920 x 1080 windowed, `--titletour`, the JSON swapped in
  `Build/PlayTest/OutOfSight_Data/StreamingAssets/` between runs, no rebuild): `Build/shots/fisheye/player_off/`,
  `player_default/`, `player_strong/` (strength 0.8, vignette 0.35), `title_tour_1..6.png` and `titletour.txt` each. The
  menu buttons, the "Out of Sight" title, the red chair logo and the credit line stay straight in all three; only the
  house behind bows (door jambs, the corridor's end wall, the kitchen counter's top). No black or smeared border. The
  titletour.txt `fisheye:` lines: off `active=False`, never enqueued; default `active=True`, params (0.30, 0.77, 0.20),
  lens (0.65, 0.50, 1.78, 0.63), enqueued and recorded on the same frame; strong params (0.80, 0.56, 0.35). No
  `[MenuCamera]` warning in the player logs (Build/fisheye_player_*.log).
  Note: `--titletour` needs an absolute directory in a player (ScreenCapture resolves a relative path under
  OutOfSight_Data and fails with "Failed to store screen shot"); the text report alone used the working directory.
- Final built player with the peripheral blur (Build/Play, same way, the shipped file put back afterwards):
  `Build/shots/fisheye/final_{off,default,strong,blur0,blurstrong}/title_tour_1..6.png` and `titletour.txt`. off = all
  zero; default = the shipped file; strong = fish-eye 0.8, vignette 0.35, blur 1, motion 1; blur0 and blurstrong = the
  default lens with blur 0 and 1. The default softens the periphery a little (the left wall's plaster against blur0),
  the centre stays crisp; strong shows long radial streaks at the edges; the menu, the title and the logo stay sharp
  and straight in all five. No `[MenuCamera]` warning (Build/fisheye_final_*.log). The `player_*` folders are the
  fish-eye-only round (Build/PlayTest).
- Editor (scene only, the tour camera through a render request):
  `Build/shots/fisheye/editor_{pc,phone}_{1,2}_{off,default,strong,blur0,blurstrong,blursoft}.png`, PC 1920 x 1080 and
  phone 2400 x 1080 (20:9), and `editor_fisheye.txt`. 20:9 fills the frame, corners included; blursoft is blur 1 with
  motion 0 (plain soft blur).

## Tests
`Assets/Tests/PlayMode/ProbeTestsFisheye.cs`:
- `Fisheye01_SettingsParseClampAndFallBack`: the shipped file has no problem and equals the defaults (0.3, 1, 0.2, blur 0.3, radius 0.4, motion 0.6);
  bad JSON, a text value, out-of-range values (clamped) and missing keys give one problem line each; all three off
  switches the pass off; the lens centre follows the tour's lens shift; at zoom 1, on 16:9 and 20:9, centred or shifted,
  k 0.3 and 1, every border pixel samples inside the picture and the farthest corner samples its corner; the centre is
  magnified 1 + k; zoom 0.8 reaches outside, 1.2 crops.
- `Fisheye02_OnTheTitleCameraOnly` (Boot scene): the file is read when the title opens; the pass is enqueued for the
  tour camera and recorded in its render graph on the same frame (aspect and centre checked), never for another
  camera; the default changes the picture (mean luma difference about 18 to 23) without darkening or blackening the
  border; the shader gets the blur values; on the default lens, the peripheral blur lowers the fine detail of the
  outer eighth of the picture (default below blur 0, strong under 0.75 of it) and leaves a box around the lens centre
  identical (difference 0.000); an edited file is read again within 2 s while the title stays open; in level1 nothing is enqueued or
  recorded; reopening the title reads the file again; no error logged.

## Runs
1. BuildWindows to Build/PlayTest/OutOfSight.exe (Build/fisheye_build.log): compiled, shader compiled, in Always
   Included Shaders (GraphicsSettings), menu_camera.json copied to StreamingAssets. Player shots above.
2. PlayMode `--filter Fisheye0|MenuCam_|LevelNum03` (TestResults/fisheye.xml): 4/4 green (Fisheye01, Fisheye02,
   LevelNum03, MenuCam_a).
3. BuildWindows to Build/Play/OutOfSight.exe (no OutOfSight process was running; Build/fisheye_play.log): built,
   menu_camera.json in `Build/Play/OutOfSight_Data/StreamingAssets/`.
4. BuildAndroid (fish-eye only, before the blur request): Build/Android/OutOfSight.apk 56.3 MB, the shader compiled
   for Android. Replaced by run 8.

Peripheral blur addition:

5. PlayMode, same filter (TestResults/fisheye2.xml): Fisheye02 failed, the strong blur raised the border detail
   (5.04 against 4.88 without blur): the per-pixel jittered taps read as grain. Changed to a fixed pattern with shorter
   sizes, and the radius measured per side (the right edge, near the off-centre lens, was not blurred at all).
6. PlayMode, same filter (TestResults/fisheye3.xml): 4/4 green. Border detail, blur 0 / default / strong: pc_1 4.88 /
   3.46 / 2.29, pc_2 3.14 / 2.05 / 1.56, phone_1 4.47 / 3.30 / 2.19, phone_2 2.54 / 1.59 / 1.24; centre difference
   0.000 everywhere.
7. BuildWindows to Build/Play/OutOfSight.exe (no OutOfSight process was running; Build/fisheye_play2.log): built; the
   final shots come from it.
8. BuildAndroid with the blur (Build/apk.log): Build/Android/OutOfSight.apk built, 56.3 MB (limit 150 MB), the shader
   compiled for Android.

Unity runs: 8 in all (about 6 asked, plus the couple the blur addition allowed).

## A VERIFIER
- On a phone (Mobile_Renderer, Vulkan or GLES3): the pass was built into the APK but not seen on a device. If the
  title shows no fish-eye there, look for the `[MenuCamera] ... back buffer` warning in logcat.
- The default (0.3, vignette 0.2) was judged on the six titletour points at 1920 x 1080; the user may want it
  softer (0.2) or stronger (0.4 to 0.5). 0.8 is clearly a "strong lens" look, the walls bend noticeably.
- The bulge is centred on the tour's optical axis (x 0.65, the vanishing point), not on the screen centre: the left
  side (under the title column) is compressed more than the right. Intended; say so if the user expects a centred lens.
- The game's own post-processing vignette is distorted with the picture (the pass runs after post-processing); not
  visible in the shots.
- Values tuned in menu_camera.json do not reach Android: copy them into MenuCameraSettings and rebuild the APK.
- The level select opened from the title also sits over the distorted background (the tour still runs under it).
- Peripheral blur: at strong values (1) the 8 fixed taps over a 54 px streak can show faint stepped copies of sharp
  edges on the far periphery; the default (0.3) keeps them under a few pixels. If the user wants a long, smooth streak,
  more taps (BLUR_TAPS in the shader) is the place, at a cost on phones.
- Peripheral blur on a phone: 8 reads per peripheral pixel on the menu only; not measured on a device.
