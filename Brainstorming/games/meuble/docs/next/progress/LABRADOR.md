# LABRADOR: the final Labrador replaces the dog (2026-11-25)

The house dog's catalog entry keeps its id `quaternius.husky` (every level naming it still works) and now draws the final
black Labrador of `ArtHandoff/LabradorFinal`, the model of the 3D tour. Gameplay is untouched: `Tuning.DogEyeHeight`
(0.35 m), the vision rules, the collider and the speeds do not change; only the model, its look and the grip pose do.

## Handoff used

The handoff changed while this pass ran (a review pass rewrote `ArtHandoff/LabradorFinal` at 01:05). The staged copy is
the LATEST one:

| File | First version (the brief) | Latest version (staged) |
|---|---|---|
| `labrador_profile_rigged.glb` | 9,095,280 bytes, 2,996 triangles | 9,223,564 bytes, 2,970 triangles (head primitive 2,424 to 2,346 vertices) |
| `LabradorHeadAtlas.png` | 4,065,236 bytes | 4,199,287 bytes |
| `inventory.json` | triangles 2996 | triangles 2970 |
| `DogFur.png` | unchanged, byte for byte the project's `Resources/DogFur.png` | unchanged |

Both versions: 50 joints, the 24 clips (Idle and Walk byte for byte the Husky's), the Jaw joint, the
`Head/LabradorEyeCenter` marker, materials "Main" and "Tete profil et face". What moved with the latest version: the eye
marker (head local y 0.000838 to 0.000896, z 0.001006 to 0.001209), the muzzle (front of the rest bounds 2.166 to 2.217
native units, as long as the Husky's 2.216), hence the values below.

If the handoff changes again: `python tools/assets/dog/stage_labrador.py`, then
`OutOfSight.Editor.Builder.SetupAndCompile` (it rebuilds the catalog), then re-derive `Tuning.DogSnoutDrop` and the GripTests
neck constants if the head moved.

## Files

- New `tools/assets/dog/stage_labrador.py`: checks the handoff against its `inventory.json` (triangles, joints, clips,
  marker, materials), checks each embedded image equal to its PNG, then writes
  `Assets/ThirdParty/Models/Quaternius/quaternius_labrador.glb` (1.65 MB) with the two embedded images dropped (geometry,
  UVs, skin, nodes, clips and material names byte for byte, checked by reading back every accessor) and copies
  `LabradorHeadAtlas.png` to `Assets/Art/Characters/Resources/`. Why drop them: glTFast imports an embedded image as an
  uncompressed RGBA32 texture with mips (about 22 MB each at 2048 px) that the catalog's prefab would load and ship (APK
  limit 150 MB); the game shows the same pixels from the PNGs, imported compressed.
- New `Assets/ThirdParty/Models/Quaternius/quaternius_labrador.glb` (+ .meta copied from the Husky's: glTFast, Legacy
  animation, new guid). Next to the old dog, as the existing convention. `quaternius_husky.glb` was NOT replaced:
  `tools/assets/labrador_full.py` builds the Labrador from it (its BODY); it no longer ships (nothing references it).
- New `Assets/Art/Characters/Resources/LabradorHeadAtlas.png` (+ .meta copied from DogFur's: sRGB, mips, 2048,
  compressed; Clamp like the GLB's sampler).
- `Assets/Editor/ModelCatalogBuilder.cs`: `Spec.EyeMarker`; the dog spec points at `quaternius_labrador.glb` with
  `LabradorEyeMarker` ("LabradorEyeCenter"). With a marker, MeasureRigged takes the eye centre from the marker under the
  head bone (eyeLocal, facing, rest and Idle eye height) and no longer needs Eyes_* submeshes (it falls back to them, with a
  warning, if the marker is missing). The log line of a pet adds the fitted values and its material names.
- `Assets/Scripts/Runtime/ModelKit.cs`: `PetHeadMaterial`, `PetHeadMap`, `PetSlotMap`, `IsPetHead`; `ApplyPetFurMap` gives
  each slot the map of its source material (fur map on "Main", head atlas on "Tete profil et face"; a head without its atlas
  falls back to the fur map with one warning; the old Husky's eye whites still keep their palette white); `PartOf` maps
  "tete profil et face" to the pet's coat (Clothes).
- `Assets/Scripts/Core/Tuning.cs`: `DogHeadAtlasResource = "LabradorHeadAtlas"`; `DogSnoutDrop` 0.010 to 0.015;
  `TitleLogoDogGrip` -0.808 to -0.797. `DogHeadScale` 1.45 and `DogJawOpenDegrees` 45 kept (the tour's values: the tour runs
  the game's PetPose and Tuning unchanged).
- Comments only: `TitleLogo.cs` (BuildDog), `PersonalityDef.cs` (dog row), `ModelCatalog.cs` (the id), `docs/LICENSES.md`.
- Tests updated (not run): `ModelM5Tests` (a pet may have 2 source materials; new
  `The_dog_is_the_final_Labrador_with_its_two_maps_and_its_eye_marker`), `GripTests` (neck chain rescaled to the new fit,
  snout 0.076 m), `ProbeTestsM5Watchers` (AssertWears: each dog slot shows its own map, untinted; Step37 counts the dog's
  two maps), `ProbeTestsDogLook` (the head atlas on a slot, both maps untinted; the log names the atlas).

## Catalog values measured (Build/LABRADOR.log)

| | Husky (before) | Final Labrador |
|---|---|---|
| eyes from | the Eyes_White and Eyes_Black vertices | marker `Head/LabradorEyeCenter` |
| eyeLocal (head bone space) | (0.0000232, 0.0012395, 0.0009168) | (0, 0.0008965, 0.0012091) |
| facing, yaw | +z, 0 | (-0.0094, 0, 0.1177), 0 |
| eye height Idle (native) | 2.6746 | 2.7140 (rest pose: 2.723) |
| fitted scale (Idle eyes at DogModelEyeHeight 0.525 m) | 0.1963 | 0.1934 (1.5 % smaller; the tour used 0.196) |
| eyes at rest, fitted | | 0.527 m (0.525 m in Idle) |
| native size | (0.990, 3.076, 3.690) | (0.990, 3.029, 3.691) |
| fitted height, length | 0.604 m, 0.724 m | 0.586 m, 0.714 m |
| snout reach (ForwardReach) | 0.435 m | 0.429 m |
| bones, triangles, slots | 50, 2978, 5 | 50 of 50, 2970 of 3000, 2 |
| clips | Idle, Walk | Idle, Walk (24 imported) |

Snout tip in the bind pose (the head orientation InhabitantRig holds), at the fitted scale: 0.079 m ahead of the head
bone and 0.0148 m below it (the Husky: 0.080 and 0.013), hence `DogSnoutDrop` 0.015.

## How the two textures are kept, and the tint

- Game: `ModelKit.Paint` (palette and tint), then `ApplyPetFurMap` replaces each slot with a URP Lit map material (white
  base colour, the map as base map, `DogFurSmoothness`, the fur map's mip bias and aniso 4 on both maps). `TintClothes`
  (Inhabitant.ApplyIdentity with the "#505458" tint) ends with `ApplyPetFurMap` too, so the tint never stays on a textured
  slot and never darkens a map. The dog's slots get no property block (their surfaces are Plain).
- Title logo: `BuildDog` instantiates through the same `ModelKit.Instantiate` (ModelPaint Main = DogTint, then the maps);
  each baked frame copies `skin.sharedMaterials`, so both maps reach the static copies; `CopyPrints` still copies any block
  (none for the dog).
- Tint decision: the tint does not apply to the textured dog at all (the paintings carry the look). It stays the dog's
  identity colour wherever it is read: the procedural fallback body, the floor contrast tests, and the model itself if the
  maps were missing (both slots then wear it, so the head never shows a white palette colour on a charcoal body).
- Materials: the dog draws 2 map materials (was the fur map and the palette white): at most one more material in a dog
  level (level 15 stood at 22 of its budget). Worth a LevelAudit run.

## What the user must check visually

- Walk: level 12 or 15, the dog walking (no sliding, ears hanging, tail low, the head atlas seam at the neck).
- The face: painted eyes readable at game distance (mip bias), no white or tinted head.
- Snout reach and grip on level 12: the pin, the grip (head rolled, jaw open 45 deg on the pink mouth), the drag (snout on
  the chair's edge, hold back), the release. `ProbeTestsDogLook` writes its frames to Build/shots/dog/runtime_level12_*.png.
- Logo: the dog trots in, bites the chair's left back leg low, drags, turns and leaves; both maps on every baked frame.
  The bake logs "[TitleLogo] the dog bites the chair's leg: ... m sideways from the chair's foot": aim for -0.274 m; tune
  `Tuning.TitleLogoDogGrip` by the difference if it is off.

## Tests to run (filters)

- EditMode: `ModelM5Tests|GripTests|CoreM5Tests`
- PlayMode: `ProbeTestsDogLook|ProbeTestsM5Watchers|ProbeTestsM3Models|ProbeTestsM3Rig|ProbeTestsGripLook`
- Then LevelAudit on the dog levels (12, 15, 16, 17, 20, 24) for the material budget.
