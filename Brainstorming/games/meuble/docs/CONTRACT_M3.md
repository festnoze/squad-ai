# Contract M3 - "De vrais meubles" (v2, after the contract critique)

Build contract for milestone M3 of [PRD.md](PRD.md) (section 11, M3): the game looks like a game.
Same method as [CONTRACT_M2.md](CONTRACT_M2.md):
- this contract fixes rules, data, APIs, file ownership and the gate;
- the PRD wins when the two disagree;
- the integrator (the parent agent) decides any ambiguity.

Asset facts come from [M3_ASSETS.md](M3_ASSETS.md) and [M3_AUDIO.md](M3_AUDIO.md). v2 folds in
the critique of v1: 6 blockers and 7 should-fix items, all verified against the project's code
and the glTFast 6.20 sources in `Library/PackageCache`.

Everything M1 and M2 do must keep working: `./verify.sh` stays green with every test so far.

---

## 1. Ground rules

The ground rules of CONTRACT_M2 section 1 still apply:
- own your files;
- additive APIs;
- compile and test through `tools/unity.sh`;
- tests that can fail, with premise guards;
- no em-dash;
- constants in `Tuning.cs`;
- French strings in `Strings.cs`.

**The session scratchpad directory is shared by every agent.** Keep all your scratch files in
`scratchpad/<agent-name>/`. In M2, two agents used the same script name, and one ran the other's
mutation script five times against a file it did not own.

**A model is a visual only.** This is the structuring decision of M3.
- A prop, the player furniture, a decoy, a rug or the doormat keeps **exactly** its M2 colliders.
  So vision, the NavMesh, the audit and every test stay valid.
- When a model is used, the procedural parts are built as **collider-only GameObjects**: same
  transform and scale, a `BoxCollider` on the same layer, **no MeshFilter and no MeshRenderer**.
  The budget counters walk MeshFilters, so a disabled renderer would still count.
- A missing or broken model falls back to the procedural visual and logs one warning (never an
  error). Under `--probe`, the built player **fails** on any fallback.

## 2. Assets in the project (already landed by the integrator)

- **Package:** `com.unity.cloud.gltfast` 6.20.0. Burst, Collections and Mathematics come with it.
- **Models:** `Assets/ThirdParty/Models/Kenney/*.glb` (9 files) and
  `Assets/ThirdParty/Models/Quaternius/quaternius_{man,woman}.glb`, imported by glTFast's
  importer. The humans use **Legacy** animation (`animationMethod: 1` in their `.meta`).
- **Audio:** `Assets/ThirdParty/Audio/*.wav`, 21 clips.
- **Licences:** `docs/LICENSES.md` and `Tests/EditMode/LicenseTests.cs`, green.
- **Which props get a model in M3:**
  - chair (player and decoys), sofa, rug, doormat;
  - armchair, stool and floor lamp, ready for M4.
- **Stay procedural:**
  - the **tall bookshelf**, the only full cover; the Kenney one is 0.85 m;
  - the **dining tables**: the procedural one is a cloth down to the floor with a solid occluder
    up to 0.75 m, while the Kenney table has open legs and would make a solid occluder look
    see-through;
  - the **door**: the Kenney leaf is closed while the doorway is open. Doors are M5.
  - Props of the new kinds (cabinet, counter, plant, bed, desk, wardrobe) stay procedural unless
    the catalog has a fitting id.

## 3. Model catalog, fit, facing and colours

**Catalog.** `ModelCatalog` (Runtime, ScriptableObject) lives at
`Assets/Resources/ModelCatalog.asset`.
- **Entry fields:**
  - `string id`, `GameObject prefab`, `Vector3 nativeSize` (bounds size, unrotated);
  - `Vector3 boundsCenter`, used to recentre Kenney's corner pivot;
  - `float yawOffset`;
  - `bool rigged`;
  - `string headBone`, `Vector3 eyeLocal` (eye centroid in head bone space, rigged only);
  - `float eyeHeight` (native units, rigged only).
- **Ids in M3:**

  | Id | Fit | Facing (`yawOffset`) |
  |---|---|---|
  | `kenney.chair` | Box | 180 |
  | `kenney.sofa` | Box | 0 |
  | `kenney.rug` | Box | 0 |
  | `kenney.doormat` | Box | 0 |
  | `kenney.armchair` | Box | 180 |
  | `kenney.stool` | Box | 0 |
  | `kenney.floorlamp` | Box | 0 |
  | `quaternius.man` | Uniform (rigged) | the builder measures it |
  | `quaternius.woman` | Uniform (rigged) | the builder measures it |

  Facing cannot be measured from bounds. **Yaw offsets are multiples of 90**, set in
  `ModelCatalogBuilder`, and checked by a test.
- **Built by `OutOfSight.Editor.ModelCatalogBuilder.Build()`**, called from
  `Builder.SetupAndCompile` (integrator) and idempotent. Being referenced from Resources is what
  ships the GLBs in the player.

**Fit.** `ModelKit.Instantiate(string id, Transform parent, Vector3 boxSize, ModelFit fit)`
returns the visual root, or null so the caller falls back.
- `ModelFit.Box`: a per axis scale so the bounds fill the gameplay box exactly, bottom on
  y = 0, centred on x and z. **Never used for a rigged model**: a non-uniform scale shears the
  bones.
- `ModelFit.Uniform`: one scale from the height. For a rigged entry, the scale is
  `Tuning.EyeHeight / eyeHeight`, so the eyes of the model sit at the routine's eye.
- **Layers** are set recursively on every child (glTFast imports at layer 0). An inhabitant's
  model gets the Inhabitant layer, which the x-ray pass needs.
- `ModelKit.Disabled` (a static bool, false by default): when true, `Instantiate` returns null.
  Probe step 23 uses it to build every level without models.
- **The math is pure and lives in `Core/ModelMath.cs`** (fit scale, recentre, colour
  quantisation, red test, colour mapping), so EditMode tests stay Core-only.

**Facing test (EditMode or PlayMode).** For every seat id, the tallest part of the instantiated
model lies on the same local z side as the procedural backrest collider. The procedural chair's
backrest is on -z, the sofa's on +z.

**Colours.**
- Every imported material is replaced at instantiate time by `PrimitiveKit.Lit(c)`, where `c`
  is the glTFast base colour. glTFast stores `baseColorFactor` already gamma converted; its
  shader has no `_BaseColor`, so read the property glTFast writes.
- Quantise **in sRGB** to 1/64 so near-identical Kenney colours share one material. The
  near-blacks of the humans (below 0.08 in every sRGB channel) merge into one material.
- **The red test:** hue within 20 deg of 0, saturation above 0.5, value above 0.35.
- **Red is remapped** on every prop:
  - Kenney "carpet" on a rug becomes `rug.Color`;
  - on the doormat it becomes `exit.Color`;
  - on any other prop it becomes `prop.AccentColor`.
- **The player model** gets the player colour (red) on its main material.
- **Decoys** keep `decoy.Color`, with the existing guard that a decoy colour is never the player
  colour.
- glTFast materials are never used at run time. The models agent checks the BuildReport for the
  size of glTFast's shader graphs: if they bloat the build past budget, it bakes material-free
  prefabs.

## 4. Data

`LevelDef` additions are optional fields. The integrator lands them as stubs first.

```
props[].model, player.model, decoys[].model, rugs[].model, exit.model   (catalog id or null)
inhabitants[].model                                                      ("quaternius.man" | "quaternius.woman")
```

- Levels 1 to 3 name a model for the chair, sofa, rugs, doormat and decoys.
- **Every inhabitant of levels 1 to 3 uses `quaternius.man`**, for the material budget. The
  woman is kept for the second inhabitant of M5.

## 5. The rigged inhabitant

**Instantiation.** `LevelBuilder.BuildInhabitant` (models agent) calls
`ModelKit.Instantiate(def.Model, visual, size, Uniform)`. On success it calls
`InhabitantRig.Attach(inhabitant, modelRoot, entry)` (rig agent) and skips the procedural body.
On failure the M2 procedural body is built, unchanged.

**`InhabitantRig`** (Runtime, rig agent) drives the model from `InhabitantRoutine`.
- **Animation component.** glTFast puts it on the model root, with `playAutomatically` on and
  the first clip (Clapping) as default.
  - Set `playAutomatically = false`.
  - Set `cullingType = AlwaysAnimate`.
  - Find the clips by suffix: `_Idle`, `_Walk`, `_Jump`, matched with `EndsWith`. "Jump" alone
    also matches RunningJump.
  - glTFast sets every clip to Loop; Jump is set to `ClampForever`.
  - The 0.15 s cross fade is tested by clip **weight**, not by `IsPlaying`.

| Activity | Clip |
|---|---|
| Walking, Carrying | Walk |
| Idle, Waiting, Telegraph, Looking, Pinned | Idle |
| Startled | Jump, once, then held |
| PickingUp, PuttingDown | Idle, plus the procedural bend |

- **Head.** In `LateUpdate`, after the animation, the head bone's **world rotation is set
  absolutely**: `LookRotation(EyeForward of the interpolated pose) * calibration * tilt`. The
  calibration is measured once from the bind pose (Blender bones point along +Y). The telegraph
  tilt is a 12 deg roll. **The probe asserts the head bone forward stays within 5 deg of
  EyeForward.**
- **Arms (carry) and the bend** are set absolutely too, never added on top of the clip.
- **`FootstepCount`** increments from the fixed step walk phase, twice per cycle, never from
  render frame clip time.
- **The "?" and "!" markers** stay, placed above the head bone.
- **Budgets:** at most 3 000 triangles and 40 bones (Man 1 970 / 31). The probe reads
  `SkinnedMeshRenderer.sharedMesh` with `GetIndexCount` per submesh, and `bones.Length`.
- **While paused:** animation speed 0.

## 6. Look, menus and pause

**Lighting and post processing.**
- One shadowed directional light, from the URP asset (PRD 8.4).
- SSAO as a renderer feature on `PC_Renderer`. `ProjectSetup` adds it through `SerializedObject`
  (`m_Settings` is private), keeps `m_RendererFeatureMap` in sync, and is idempotent.
- Bloom with a threshold above 1, so only the window glows.
- Tonemapping Neutral.
- Light colour grading.
- **Baseboards and the window pane's emissive value are built by `LevelBuilder`** (the models
  agent owns it), with their constants in Tuning (integrator). Look only tunes the post
  processing and the lights.

**X-ray** (deferred from CONTRACT_M2 section 11).
- Inhabitants behind a wall are drawn as a flat silhouette: a URP `RenderObjects` feature on the
  Inhabitant layer, depth test Greater, with an override material.
- The vision cones draw over walls at reduced alpha.
- The "?" and "!" markers draw over walls.
- **A player must always know where every inhabitant is looking**, which pillar 2 demands.

**HUD vs markers.** World markers never overlap the HUD gauges. Clamp them below the HUD band in
screen space, or move the gauges to the bottom corners.

**Title screen** (`Menu`, look agent).
- It shows `title`, `title.play`, `title.quit` and the credits line, over the level 1 view with
  a slowly orbiting camera. The game is paused while it is up.
- **It shows only in a player** (`!Application.isEditor`) and not under `--probe`, or when a
  test calls `Menu.ShowTitle()`. Editor test runs, interactive or batch, never see it.
- While a menu is open, the cursor is unlocked and the HUD canvas is disabled.
- Buttons are uGUI `Button` with `InputSystemUIInputModule`. Keyboard (arrows plus Enter),
  gamepad and mouse all work.

**Pause.**
- Escape (keyboard) and the gamepad **Start** button pause and unpause. Restart moves to the
  gamepad **Y** button only; Start no longer restarts.
- `GameState.Paused` stops every fixed step rule.
- **`GameState.Update` does nothing while paused**, neither R nor Enter.
- **Interpolated visuals hold alpha 1** while paused: they read the static `GamePause.IsPaused`.
- `AudioListener.pause` is true while paused; the UI click source has `ignoreListenerPause`.
- The pause panel shows `pause.title`, `pause.resume`, `pause.restart` and `pause.menu`.

**End screen.** After winning the last level of `levels.json`, the win panel shows `end.title`
and `end.body`. Enter returns to the title (or restarts level 1 in the editor).

## 7. Recorded audio

- **`AudioLibrary`** (Runtime, ScriptableObject at `Assets/Resources/AudioLibrary.asset`), built
  by `OutOfSight.Editor.AudioLibraryBuilder.Build()`. The integrator calls it from `SetupAndCompile`.
- **`Sfx`** uses a recorded clip when the library has one, and its synthesis otherwise. Kept
  synthesized: "hm ?" and the tension loop. "hein ?" too, unless `vocal_huh` passes the product
  owner's listening pass.
- **New sounds:**
  - **footsteps:** one 3D `AudioSource` added **with `AddComponent` on the inhabitant root**,
    so no new Transform appears and probe step 09's count holds. It plays a step on every
    `FootstepCount` increment;
  - **room tone:** a 2D loop at a low level;
  - **hops:** a random variant, never the same twice in a row;
  - **UI click:** `Sfx.PlayUiClick()`, with `ignoreListenerPause`.
- **Volumes** come from each clip's measured RMS (M3_AUDIO) to a common target.
- **Tests** assert configuration and counters (as `CreaksPlayed` does), never `isPlaying`: there
  may be no audio device in batch mode.

## 8. File ownership

| Agent | Owns |
|---|---|
| **models** | `Core/ModelMath.cs`, `Core/LevelDef.cs`, `Core/LevelValidator.cs`, `Runtime/ModelCatalog.cs`, `Runtime/ModelKit.cs`, `Runtime/LevelBuilder.cs`, `Runtime/FurnitureKit.cs`, `Runtime/PrimitiveKit.cs`, `Runtime/FurnitureController.cs`, `Runtime/Probe.cs` (counters and the fallback failure), `Editor/ModelCatalogBuilder.cs`, `Editor/LevelAudit.cs` (budget counters only), `Resources/Levels/*.json`, `Resources/ModelCatalog.asset`, the import settings under `Assets/ThirdParty/Models`, `Tests/EditMode/ModelM3Tests.cs`, `Tests/PlayMode/ProbeTestsM3Models.cs` |
| **rig** | `Runtime/Inhabitant.cs`, `Runtime/InhabitantRig.cs`, `Tests/PlayMode/ProbeTestsM3Rig.cs` |
| **look** | `Runtime/Main.cs`, `Runtime/Menu.cs`, `Runtime/Hud.cs`, `Runtime/ProceduralArt.cs`, `Runtime/OrbitCamera.cs`, `Runtime/InputReader.cs`, `Runtime/GameState.cs` (pause and menu glue only: `Update`, `Paused`, the end screen flow), `Runtime/VisionConeView.cs` (x-ray alpha), `Editor/ProjectSetup.cs` (SSAO, RenderObjects), `Assets/Settings/*`, `Tests/PlayMode/ProbeTestsM3Look.cs` |
| **audio** | `Runtime/Sfx.cs`, `Runtime/AudioLibrary.cs`, `Editor/AudioLibraryBuilder.cs`, `Resources/AudioLibrary.asset`, the import settings under `Assets/ThirdParty/Audio`, `Tests/PlayMode/ProbeTestsM3Audio.cs` |
| **integrator** | `Core/Tuning.cs`, `Core/Strings.cs`, `Packages/manifest.json`, `docs/*`, `verify.sh`, `mutation.sh`, `tools/*`, `Editor/Builder.cs`, `Runtime/GamePause.cs`, the test asmdefs, the M1/M2 probe files, `Tests/EditMode/LicenseTests.cs`, `README.md` |

**Stubs the integrator lands before the builders start:**
- `LevelDef` model fields;
- `ModelCatalog` with its Entry fields, and `static ModelCatalog Load()`;
- `ModelKit.Disabled`;
- `ModelMath` (empty);
- `InhabitantRig.Attach(Inhabitant, GameObject, ModelCatalog.Entry)`;
- `Sfx.PlayUiClick()`;
- `AudioLibrary`;
- `Menu` with `ShowTitle()`, `SetPaused(bool)` and `IsOpen`;
- `InputReader.InjectPausePress()` and `PausePressed()`;
- `GamePause.IsPaused`;
- `ModelCatalogBuilder.Build()` and `AudioLibraryBuilder.Build()`, called from
  `Builder.SetupAndCompile`.

## 9. Gate

**Every M3 step first asserts its premise:** at least one model renderer, or one
SkinnedMeshRenderer, or one library clip exists. Otherwise a stub returning null would pass the
step. `verify.sh` requires `Step22_` to `Step27_`.

**EditMode (Core-only):**
- `ModelMath`: Box and Uniform fit on synthetic bounds, recentring, sRGB quantisation, the red
  test, colour mapping;
- every file under `Assets/ThirdParty` is in `docs/LICENSES.md` (already green).

**PlayMode:**

| Step | Assertion |
|---|---|
| 22 models | the catalog resolves every id; on levels 1 to 3, every prop, decoy, rug, doormat and the player whose data names a model has a model visual, and its procedural parts have no MeshFilter or MeshRenderer; an unknown id falls back with one warning and no error; the facing test passes for every seat |
| 23 colliders unchanged | per level, the set of collider bounds (layer, center, size) with models equals the set with `ModelKit.Disabled = true` |
| 24 rig | the Walk weight is above 0.9 while walking and the Idle weight while dwelling, after the cross fade; the head bone forward stays within 5 deg of EyeForward through a full loop; the model eye height is within 0.03 m of 1.6; FootstepCount increases while walking and not while dwelling; animation speed is 0 while paused |
| 25 budgets | per level: at most 3 000 triangles and 40 bones for the inhabitant (skinned triangles counted), each furniture at most 400 triangles, at most 24 materials (every material slot counted), at most 120 renderers |
| 26 menus | `Menu.ShowTitle()` pauses the game; Play starts level 1; an injected pause press stops every fixed step rule (Elapsed constant over 100 steps) and holds the visuals; R and Enter do nothing while paused; a second press resumes; winning level 3 shows the end screen |
| 27 audio | the library resolves every role; hop variants differ on consecutive hops (counter of the chosen index); footstep sources are 3D on each inhabitant root; the room tone source loops; `AudioListener.pause` follows the pause |

**Built player:**
- the M1 and M2 checks still hold;
- `report.json` gains, per level, the model visuals, the fallbacks (must be 0), the inhabitant
  triangles (skinned) and bones, and every material slot;
- any non-URP shader on a renderer fails;
- the screenshots show the models;
- the build stays at most 120 MB.

**Critic pass:** an adversarial agent reviews the screenshots and the code against this contract.
