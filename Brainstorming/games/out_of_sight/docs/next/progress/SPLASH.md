# SPLASH progress (the start poster on every launch, Windows and Android)

## Request (user, 2026-11-27)
At startup of the Windows and Android app, as soon as possible and for at least 3 seconds, show
`Assets/Art/UI/out-of-sight-affiche-fr.png` with its aspect ratio kept, on a black background.

## Approach chosen: Unity's splash stays off, the game's own first-frame splash, with the build deferred behind it

### Why not Unity's built-in splash (PlayerSettings.SplashScreen)
Checked against the Unity 6000.3.23f1 API docs (UnityEditor.CoreModule.xml) and this project's ProjectSettings:
- The "Made with Unity" logo can be off on this Personal license (Unity 6 made it optional): the project already ships
  with `show = false` and `showUnityLogo = false`, so that was never the obstacle.
- A background image is scaled to FILL the screen, aspect kept, so it is cropped (ProjectSettings stores
  `m_SplashScreenBackgroundLandscapeAspect` and `...LandscapeUvs`, the crop the editor computes). The poster is
  portrait 2:3: on a 16:9 screen only about 37 % of its height would show (the title or the tagline is cut). A
  pillarboxed copy on a 20:9 canvas would survive the crop from 4:3 to 21:9, but it is a second shipped image and its
  fit depends on undocumented scaling.
- A logo sprite is laid out as a centred logo (the DrawMode docs: "logos are shown in the centre", with the Unity logo
  below), not scaled to the screen's height (not measured here, no player was built): the full poster as a logo would
  be small and hard to read on a phone.
- It always fades in and out from its background colour, its logos last at least 2 s each, and it ends BEFORE the
  first scene's Awake. Main builds everything in Awake (subsystems, the first level, then the title house): that
  build would run after the splash on a black screen, and the poster could never fade into the title.
- The game's own splash appears at practically the same moment: Boot.unity is one GameObject, so before its first
  frame there is only the engine start, which also comes before Unity's splash.

### What the game does instead (Assets/Scripts/Runtime/StartSplash.cs)
1. `Main.Awake` (execution order -1000, the only object of Boot.unity) calls `StartSplash.Show()` before anything
   heavy. It loads `Resources/SplashArt.asset` (a ScriptableObject that points at the poster, so the PNG stays where it
   is), and builds:
   - a clear-only camera (black, culling mask 0, depth -100, no post processing, no shadows, no depth or colour
     texture), so the screen is black and the overlay draws even before the game camera exists. It is removed as soon
     as Main built the game camera;
   - a Screen Space Overlay canvas at sorting order 32000 (above everything: menus 50, simulated ad 200) with a
     CanvasGroup, a full screen black Image (raycast target) and the poster in a RawImage with an AspectRatioFitter in
     FitInParent mode (aspect 1024/1536). On any landscape screen the poster fills the height, centred, with black on
     both sides: 16:9 (1920 x 1080: poster 720 x 1080), 20:9 (2400 x 1080: 720 x 1080), 4:3 (1024 x 768: 512 x 768).
     No safe area: in landscape a phone's cutout and rounded corners are on the short sides, far from the poster.
2. Main then defers its whole build: `BuildBehindSplash` waits two frames (the first presents the poster, the second
   covers a render thread one frame behind on Android), then runs `BuildAll()` (every build step of the old Awake)
   and `BeginGame()` (the old Start: the first level, then `Menu.ShowTitle()`), then `StartSplash.BootDone()` (in a
   `finally`, so the splash is told even if something throws). The heavy frames (two level builds, then the title
   logo's bake over the next frames) all happen behind the poster.
3. The splash lifts when BOTH the poster has been on screen for 3 s of real time (`Time.realtimeSinceStartupAsDouble`,
   counted from the first frame after it was built, i.e. after it was presented) AND the boot reported, plus two frames.
   Safety: it lifts after 12 s whatever happens (a warning in the log).
4. Fade: 0.3 s (SmoothStep on the CanvasGroup alpha, real time) into the title, then the splash object is destroyed
   and the poster texture unloaded (`Resources.UnloadAsset`).

### Behind the poster
- Title music: `MusicPlayer.Evaluate` wants no track while `StartSplash.Holding`; the title loop starts at the fade and
  comes up over its usual 1.5 s crossfade.
- Title logo: `TitleLogo` bakes behind the poster (its 150 ms read back and composition hitches are hidden) but waits
  while `StartSplash.Holding` before it appears and starts its loop clock, so it fades in (0.45 s) as the poster fades
  out and its first act comes 2.5 s after the reveal, as designed. If the bake is not done after 3 s (a slow phone) the
  title shows first and the logo fades in when ready, as on any launch before.
- The title camera tour runs behind the poster (a slow loop, its phase at the reveal does not matter).

### Input during the splash
- The EventSystem's input module (InputSystemUIInputModule) is switched off from the moment Main creates it
  (`BootDone`, before the EventSystem's first update) until the splash is gone: no click, tap, key or gamepad press can
  submit or click a title button, even during the fade. The full screen black Image is also a raycast target on the
  top canvas.
- `TouchControls` treats the splash like a hidden overlay: every finger down on it is ignored until it lifts.
- `Main.Update` never captures the cursor from a click on the poster (the title behind it frees the cursor).
- Escape, Back and the pause key do nothing on the title page, as before. Start presses latched by a click on the
  poster are dropped by the next level build (`InputReader.BlockStartPresses`), as for a click on the title.
- Ctrl+F / F11 still toggle full screen (the poster refits).

## When it shows, when it does not (StartSplash.SkipReason)
- Shows: every launch of a built player, Windows (`Build/Play/OutOfSight.exe`, plain or with -touch, -mute, or
  Unity's -screen-* options) and Android. Once per process: nothing creates it again, so it never shows on a return to
  the title, a level load, a restart, or on resuming the Android app from the background.
- Skipped, the game building in Awake exactly as before:
  - in the editor (`Application.isEditor`): so every EditMode and PlayMode test, and Play in the editor;
  - in batch mode (`Application.isBatchMode`);
  - with ANY argument that starts with `--`: every option of the game's own test and screenshot tools does
    (`--level`, `--probe`, `--shot`, `--feet`, `--frameFailMs`, `--look`, `--titletour`, `--levelshot`,
    `--optionsshot`, `--charshots`, `--charlow`, `--charobj`, `--charlevels`), so `verify.sh player`
    (`--probe --shot ...`) and every `Build/Play/OutOfSight.exe --level levelN` start as fast as before;
  - with `-autoShot` (LEVELNUM's intro card shots, single dash);
  - with `-nosplash` (new, any case): a normal launch without the poster.
- `-touch` alone keeps the splash on purpose (it plays like a phone launch, which shows it); add `-nosplash` for a
  quick check of the touch layout.
- If `SplashArt.asset` or the poster is missing, a warning and the game starts as before.

## Settings (all in Assets/Editor/ProjectSetup.cs, applied by Builder.SetupAndCompile and every build)
- `EnsureSplashScreen` (was `EnsureSplashScreenDisabled`): `SplashScreen.show = false`, `showUnityLogo = false`,
  `backgroundColor = black` (was RGB 35, 31, 32), `background = null`, `backgroundPortrait = null`, no logos.
- `EnsureSplashArt`: the poster's importer, then `Assets/Resources/SplashArt.asset` pointing at it.
  - Poster: 1024 x 1536 (portrait 2:3), PNG RGB 24 bit, 1.79 MB on disk (not shipped as PNG).
  - Import: Default texture, 2D, sRGB, alpha source None, NO power-of-two rescale (1536 is not a power of two: the
    default "To Nearest" would have stretched it to 1024 x 2048), no mipmaps, not readable, clamp, bilinear, max size
    2048 (kept at full size), compression High Quality.
  - Platform overrides: Windows (Standalone) BC7, Android ASTC 5x5.

## Size impact
- APK: ASTC 5x5 of 1024 x 1536 = 205 x 308 blocks of 16 bytes = 1,010,240 bytes, about 1.0 MB (ASTC data barely
  compresses in the APK), plus a few hundred bytes for SplashArt.asset and the two scripts. ASTC 6x6 (the project's
  usual) would be 0.7 MB but smears the lettering's edges more; ASTC 4x4 would be 1.5 MB.
- Windows player: BC7 = 1,572,864 bytes (1.5 MB).
- Run time memory: the same, freed when the splash is gone.

## Android 12+ system splash
- Android 12 and later always show a system splash before the app draws. In Unity 6.3's Android template
  (`PlaybackEngines/AndroidPlayer/Apk/res/values-v31/styles.xml`) its icon is a TRANSPARENT colour
  (`windowSplashScreenAnimatedIcon = @color/windowSplashScreenAnimatedIconColor`, transparent; icon background
  transparent; animation 0), so no app icon shows: it is a flat colour. Its background is
  `@color/staticSplashScreenBackgroundColor`, which the build writes from `PlayerSettings.SplashScreen.backgroundColor`:
  the current APK (aapt2 dump of Build/Android/OutOfSight.apk, built 2026-11-26) carries #FF231F20, exactly the old
  RGB 35, 31, 32. With `backgroundColor = black` the next APK carries #FF000000, and the activity's windowBackground is
  already black, so the launch reads black, poster, title. That system splash itself cannot show the poster.
- Possible later (not done, not verifiable without a device): Unity's Android "Static Splash Image"
  (`androidSplashScreen`, `PlayerSettings.Android.splashScreenScale = ScaleToFit`) is drawn by the Java side before the
  engine starts, so it could show the poster even earlier; it would ship a second copy of the image and its scaling
  and its handover to the first Unity frame need a device to check.

## Files changed
- `Assets/Scripts/Runtime/StartSplash.cs` (new): the splash, its skip rule, input blocking, timing, fade.
- `Assets/Scripts/Runtime/SplashArt.cs` (new): the ScriptableObject that points at the poster.
- `Assets/Resources/SplashArt.asset` (new, written by ProjectSetup).
- `Assets/Scripts/Runtime/Main.cs`: Awake shows the splash and defers the build (`BuildBehindSplash`); the old Awake
  body is `BuildAll()`, the old Start body `BeginGame()`; no cursor capture under the splash.
- `Assets/Scripts/Runtime/MusicPlayer.cs`: no track while the poster holds.
- `Assets/Scripts/Runtime/TitleLogo.cs`: appears and starts its loop only as the poster lifts.
- `Assets/Scripts/Runtime/TouchControls.cs`: hidden (fingers ignored) under the splash.
- `Assets/Editor/ProjectSetup.cs`: `EnsureSplashScreen`, `EnsureSplashArt` and the poster's importer.
- `README.md`: the `-nosplash` option.

## Tests
- None run (not asked). No test changed: every test runs in the editor, where the splash is skipped and Main builds in
  Awake exactly as before; no test asserts the player's first frames or the built-in splash settings (searched
  Assets/Tests for Splash, TitleAtStart, the command line). `verify.sh player` runs `--probe`, which skips it.
- Filters for later, around the touched code: PlayMode `Music|TitleChair|Step74|Touch|Title`; EditMode none.
  `StartSplash.SkipReason(args, editor, batchMode)` is pure and can take an EditMode test.

## Run (2026-11-27)
- One Unity run through the lock: `tools/unity.ps1 -Agent SPLASH ... -executeMethod OutOfSight.Editor.Builder.SetupAndCompile
  -logFile Build/splash.log`, exit 0, "[Builder] Scripts compiled and project set up.", 0 `error CS`, no new warning
  (only the existing CS0618 icon API warnings of ProjectSetup.EnsureAppIcon).
- Log: "[ProjectSetup] Reimported Assets/Art/UI/out-of-sight-affiche-fr.png with the start poster settings.",
  "Created Assets/Resources/SplashArt.asset.", "Start poster 1024 x 1536, BC7, mipmaps 1." (1 = the base level only).
- ProjectSettings.asset after the run: `m_SplashScreenBackgroundColor: {r: 0, g: 0, b: 0, a: 1}`,
  `m_ShowUnitySplashScreen: 0`, `m_ShowUnitySplashLogo: 0`, `m_SplashScreenLogos: []`, no background sources.
- Poster .meta: textureType 0 (Default), enableMipMap 0, sRGB 1, isReadable 0, nPOTScale 0 (None), alphaUsage 0,
  filterMode 1 (bilinear), wrap 1 (clamp), max 2048; Standalone override format 25 (BC7), Android override 49 (ASTC 5x5).
- Side effect of the editor session, not of this change: `preloadedAssets` in ProjectSettings.asset lost its entry
  (Assets/InputSystem_Actions.inputactions, the Input System's project-wide actions, which the Input System adds during
  a player build and removes after it). Left as the editor wrote it.
- No player built, no test suite, no LevelAudit (not asked).

## How to check by hand (after a rebuild)
- PC: rebuild (`BuildWindows -output Build/Play/OutOfSight.exe`), launch `Build/Play/OutOfSight.exe`: the poster
  appears on black at once, whole and centred, for about 3 s (longer only if the boot is slower), no music under it,
  clicks and keys do nothing; then a short fade into the title, the music and the chair logo coming in. Try it in a
  window (`-screen-fullscreen 0 -screen-width 1280 -screen-height 960`, 4:3) and press F11 during it. Then
  `Build/Play/OutOfSight.exe --level level9` and `-nosplash`: no poster. Player.log has `[StartSplash]` lines with the
  frame and the real time it went up and how long it was shown.
- Android: rebuild the APK, install, launch: a black screen (no icon) then the poster centred on black for about 3 s,
  taps ignored, then the fade into the title. Back to the menu, into a level, home and back to the app: no poster.
  Kill the app and relaunch: the poster again.
