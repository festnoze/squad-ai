# CONTRACT M7 - "Mobile", plus polish round 2

Build contract for milestone M7 of [PRD.md](PRD.md) (section 11, M7) and a second polish round the
product owner asked for on 2026-11-17 (textures and lighting). The PRD wins where this contract is
silent; this contract wins over the agent prompts. The product owner has few credits: each agent
does the smallest work that meets its items, with few Unity runs and a short report.

## 1. Decisions (binding)

### 1.1 Lighting (polish)
- Goal: a warmer, softer, more readable house: a warm key light (the sun through the windows) with
  soft shadows, a cool sky ambient (gradient or skybox ambient), tuned screen space ambient
  occlusion, a subtle bloom on bright windows and lit lamps, a neutral or ACES tonemapper with a
  light colour grade. The red player furniture stays the most visible thing in every frame (PRD 7.2).
- Limits: PC median frame time stays under 16.6 ms on every level (the player probe measures it);
  the probe's luminance checks and the HUD contrast stay as they are; nothing changes the rules.
- Before and after shots of three levels (one small, one house, the night level 16) in docs/m7/.

### 1.2 Textures (polish)
- Normal maps: derive a tangent-space normal map (512, from the ambientCG NormalGL map of the same
  material, licence rows unchanged) for each existing detail texture where it reads at play distance
  (wood, parquet, plaster, upholstery, linen, carpet, grass, lacquer, metal), applied through the URP
  Lit `_BumpMap` with a modest strength. The colour rule (grayscale detail times the palette colour)
  is unchanged.
- New surfaces where the house still looks flat: tiles for kitchen and bathroom floors (a room
  `"floorFinish": "tile"`, visual only: acoustically a hard floor), the door leaves (painted wood),
  and any obviously plain large surface the agent finds (say which). New textures follow the M4.2
  derivation and get a LICENSES row.
- The material caps of PRD 7.4 hold on every level (24 and 32).

### 1.3 Android build (M7)
- `OutOfSight.Editor.Builder.BuildAndroid` (`-output`, default `Build/Android/OutOfSight.apk`; the
  `-development` flag as for Windows): IL2CPP, ARM64, minimum API 26, the installed target API,
  landscape only, package id `com.outofsight.game`, Vulkan then OpenGL ES 3, ASTC textures, debug
  signing. The APK is at most 150 MB.
- On Android: `Screen.sleepTimeout = NeverSleep` while playing; the Android back button (Escape in
  the Input System) pauses or goes back, as Escape does on PC.

### 1.4 Quality tiers (M7)
- Three levels in QualitySettings, each with its URP asset: **Bas** (Mobile_RPAsset, render scale
  0.75, no soft shadows, no SSAO, no bloom), **Moyen** (Mobile_RPAsset, render scale 1, hard
  shadows), **Haut** (PC_RPAsset, everything of 1.1). Default: Android Moyen, PC Haut.
- A fourth option on the Options screen (CONTRACT_M6 2.1), **Qualité**: Bas, Moyen, Haut, saved in
  `SaveData.options.quality` (a missing field is the platform default; the version stays 1).
- Target frame rate: 30 on Bas and Moyen, 60 on Haut (Android); PC keeps its current setting.

### 1.5 Touch controls (M7)
- Shown when a touchscreen is the active input (`Touchscreen.current` with a recent touch) or with
  the `-touch` argument (and a test hook `InputReader.ForceTouchUI`); hidden otherwise.
- Left half of the screen: a floating virtual stick (it appears where the thumb lands) that moves
  the furniture like the left stick. Right half: drag to orbit the camera (the sensitivity option
  applies). Buttons at the bottom right, at least 9 mm (about 140 px at 1080p): the action (E),
  careful (a toggle on touch), and a pause button at the top right. Menus work by tap (uGUI with the
  InputSystemUIInputModule).
- The controls line shows the touch names when touch is active (a third string next to the keyboard
  and gamepad ones).

### 1.6 Android save (M7)
- Where `File.Replace` is not supported, the save writes the .tmp, copies the current file to the
  .bak (overwrite), deletes the target and moves the .tmp into place (CONTRACT_M5_v3 15.7, the open
  .bak rule). The load rule stays: main, then .tmp, then .bak. Tested in EditMode through the
  existing replace hook.

## 2. Agents and file ownership

| Agent | Files |
|---|---|
| **lighting** | `Runtime/Main.cs` (the lights, ambient and Volume setup only), `Runtime/LampLight.cs`, `Assets/Settings/PC_RPAsset.asset`, `PC_Renderer.asset`, `DefaultVolumeProfile.asset`, new `Tests/PlayMode/ProbeTestsM7Look.cs` (Step60x_), docs/m7/ shots |
| **textures** | `Runtime/TextureLibrary.cs`, `Editor/ModelCatalogBuilder.cs` (textures part), `Runtime/PrimitiveKit.cs`, `Runtime/FurnitureKit.cs`, `Runtime/DoorLeaf.cs` (material only), `Assets/ThirdParty/Textures/`, `docs/LICENSES.md`, `Tests/EditMode/LicenseTests.cs`, `Tests/PlayMode/ProbeTestsM6Textures.cs` (Step50, Step61x_); shared with small Edits: `Runtime/LevelBuilder.cs` (floor finish), `Core/LevelDef.cs` and `Core/LevelValidator.cs` (the floorFinish field), level JSON files (only the floorFinish field on kitchens and bathrooms) |
| **android** | `Editor/Builder.cs`, `Editor/ProjectSetup.cs` (Android player settings, quality levels), `Assets/Settings/Mobile_RPAsset.asset`, `Mobile_Renderer.asset`, `ProjectSettings/QualitySettings.asset`, `ProjectSettings/ProjectSettings.asset` (Android part), `Runtime/SaveStore.cs`, `Core/SaveData.cs`, `Runtime/Menu.cs` (the Qualité option), new `Runtime/QualityTier.cs`, new `Tests/EditMode/AndroidM7Tests.cs`, new `Tests/PlayMode/ProbeTestsM7Quality.cs` (Step62x_) |
| **touch** | `Runtime/InputReader.cs`, new `Runtime/TouchControls.cs`, `Runtime/OrbitCamera.cs`, `Runtime/GamePause.cs`, new `Tests/PlayMode/ProbeTestsM7Touch.cs` (Step63x_); shared with small Edits: `Runtime/Hud.cs` (the controls line) |
| **integrator** | `verify.sh`, `mutation.sh`, `tools/`, `Probe.cs`, docs (PRD, README, contracts) |

- `Core/Strings.cs` and `Core/Tuning.cs`: each agent adds only inside its own "M7 <agent>" block.
- Shared files: re-read before each Edit, small targeted Edits only.

## 3. Gate

`./verify.sh` green (every earlier stage included), the APK built and under 150 MB, the new tests
in the verify lists, the PC frame time under 16.6 ms. The 30 fps on a mid range Android phone is
measured by the product owner on a device (the gate notes record it as pending until then).

## 4. Difficulty and progression (product owner, 2026-11-17)

The product owner finished all 18 levels with best times of 8 to 34 s (level 13 in 8.4 s, level 17
in 15.6 s): every level is easy and the curve is flat. Owner: the **design** agent.

### 4.1 Difficulty
- A **Difficulté** option: Facile, Normal (default), Difficile, on the Options screen (CONTRACT_M6
  2.1) and saved in `SaveData.options.difficulty` (missing field: Normal; the version stays 1).
- One table in Core (`DifficultyDef`), applied in one place that both the game and the audit use
  (the routine and watcher construction, the vision, hearing and suspicion parameters), so the
  audit checks exactly what the player plays. Candidate knobs (the agent tunes the values): view
  range, cone half angle, turn telegraph time, caught grace, time between glances (dwell facing
  away), hearing range, suspicion gain, creak fill rate. Facile only ever helps the player and
  Difficile only ever hinders (an EditMode test asserts the monotonicity knob by knob).
- Records are kept per difficulty: `best["levelN"]` stays Normal (old saves keep their records),
  `best["levelN@facile"]` and `best["levelN@difficile"]` for the others; the level select shows the
  record of the current difficulty.
- **Always doable:** the audit runs every level at Normal and at Difficile and must pass both (Facile
  is easier by the monotonicity test); `-writeRoutes` writes the Normal route (`designerRoute`) and
  the Difficile route (`designerRouteHard`); the Step45 style replays win at both.

### 4.2 Progressive challenge
- At Normal, the curve rises from level 1 to level 18: the audit's timing margin (samples each
  side) goes from about 15 on levels 1 and 2 down to about 4 to 6 on levels 16 to 18, and the
  audit's exit time grows from about 10 s to about 45 to 60 s on the last houses. A level that
  introduces a mechanic may be a little easier than the one before it (a breather), never easier
  than two levels before it.
- Levers: more watchers or a watcher placed on the route, shorter glance gaps, longer routes and
  houses, fewer covers, tighter door and robot timings. Every level keeps its lesson and its hint
  true. The audit table (margin and exit per level, Normal and Difficile) goes in docs/m7/design.md.

## 5. Real-colour textures (product owner, 2026-11-18)

Replaces the colour rule of 1.2 and PRD 7.2 v1.7 (grayscale detail times the palette colour) for
the environment. Owner: the **envcolour** agent.

- Every image of `Assets/Art/Environment` is the base map of its surface in the image's own
  colours, tiled as a visible repeating pattern, on every surface of its kind: floors, walls, the
  garden, props, decoys, doors, the metal parts (`metal.png`) and the robot. The colour maps are
  seamless 512 sRGB textures in `Assets/Art/Environment/Colour` (`tools/assets/derive_env_colours.py`,
  same geometry as the Detail maps, so the gentle normal maps of 1.2 stay aligned).
- One URP Lit material per surface (`PrimitiveKit.SurfaceMaterial`): white base colour, the colour
  map, one finish per surface (`TextureLibrary.ColourFinishOf`); `PrimitiveKit.Detail` puts it in
  the slot and sets the tiling (metres per repeat: `Tuning.DetailTile*`) in the property block;
  LevelBuilder's combiner groups by that material. Repeats picked on the built player's shots:
  parquet 1.8, wood 0.8, plaster 2.0, upholstery 0.4, linen 0.35, carpet 0.6, grass 2.5,
  lacquer 1.0, metal 0.3, plastic 0.2, foliage 0.3, soil 0.25, tile 1.5 (25 cm tiles).
- It replaces one material per palette colour: the built player's probe (24 levels) measures 13 to
  23 materials below 5 rooms (cap 24) and 19 to 29 from 5 rooms (cap 32), at most 80 draw calls
  below 5 rooms (cap 120) and 156 from 5 rooms (cap 160); every level is at or under its count
  before the change.
- The one exception is the player furniture (PRD 7.2, found instantly in any frame): its red slots
  show the owner's red painted metal image (`red_metal_source.png`) through
  `PrimitiveKit.PlayerMaterial` (smoothness 0.8, metallic 0.35, no normal map). Decoys are the
  player's furniture kind and model in real colours, never its red.
- The inhabitants keep the M4.2 rule (palette material, grayscale detail): their clothes belong to
  `CharacterLook`.
- Tests: Step22c (every textured slot outside the inhabitants shows a colour map through its
  surface's white material, the player's red image only on the player), Step22d (the images add
  visible detail, at least 1.1 times the flat view's, under a raised noise cap of 5.0, measured
  4.2 on level1 and 2.5 on level5; at least 85 % of the red pixels of the start view lie on the
  player furniture, measured 99 % and 97 %), Step22f (colour maps ship sRGB, compressed,
  mipmapped), Step50a and Step61a (the player's finish, the garden, metal and tile colour
  materials), Step60a (the player furniture's built colour, base colour times its image's mean,
  stays the most saturated). Shots: docs/m7/env_colour_1.png (level 3) and env_colour_2.png
  (level 17).
