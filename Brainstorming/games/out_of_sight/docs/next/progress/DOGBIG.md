# DOGBIG: a bigger, more readable dog (black Labrador)

Product owner requests (2026-11-21): "create a bigger 3D asset for the dog"; the bigger dog replaces the old one
everywhere (every level and the title logo); then "the dog becomes a BLACK LABRADOR" with two textures of their own
(`Assets/Art/Characters/labrador_black_face_front.png`, `labrador_black_fur_albedo.png`), floors made lighter wherever
the black dog fails the contrast bar on its own stations and paths.

## Model

- Looked in the project first: only the Quaternius Shiba is a dog in `Assets`; `ThirdParty_staging/poly.pizza` holds the
  Quaternius Husky (alternates/pets, `pet_dog__quaternius_husky__wcWiuEqwzq.glb`, sha256 checked against
  `manifest.json`: page https://poly.pizza/m/wcWiuEqwzq, "Public Domain (CC0)", CC0 1.0, Quaternius "Animated Animal
  Pack"). No Labrador exists in the Quaternius packs and no CC0 rigged Labrador was found in the project's sources.
- Parsed the GLB JSON before wiring: same AnimalArmature rig as the Shiba (49 joints: 3 more tail bones), 1920 triangles
  (budget 3000), the same 12 clips twice (plain and `AnimalArmature|`), Idle, Walk, Gallop, Eating, Idle_2... The Walk
  clip is the Shiba's key for key (IK foot tracks, 1.042 s), so the foot contact (0.83) is unchanged.
- Quaternius normalises its animals: native, the Husky is the Shiba's size (eyes 2.68 vs 2.71 units). The size comes
  from the fit: the model is now drawn 1.5 times the old dog (`Tuning.DogModelScale`, catalog target eye
  `Tuning.DogModelEyeHeight` 0.525 m instead of 0.35 m).
- `Assets/ThirdParty/Models/Quaternius/quaternius_husky.glb` (+ .meta copied from the Shiba's, Legacy animation, new guid),
  built by `tools/assets/dog/make_husky.py` from the staged file: the five materials renamed to the Shiba's names the
  pipeline reads (Main, Main_Light, Black, Eyes_White, Eyes_Black: eyes found by "Eyes_*", palette parts by name), the
  mesh named "Husky", and a UV0 atlas added (vertices split only where a vertex is shared by two regions: 3900 to 4000).
  Geometry, weights, rig and clips untouched. Catalog id `quaternius.husky` (`ModelCatalog.QuaterniusHusky`, replaces
  `QuaterniusShiba` in `Ids`); the Shiba GLB stays in the project, unused.

| | Shiba (before) | Husky (now) |
|---|---|---|
| eyes (fitted, Idle mean) | 0.35 m | 0.525 m (scale 0.1974) |
| height (ears pricked, rest pose; lower with the hanging ears) | 0.40 m | 0.629 m |
| length (snout to tail) | 0.51 m | 0.768 m |
| width | 0.14 m | 0.195 m |
| snout ahead of the root (ModelKit.ForwardReach) | 0.32 m | 0.476 m |
| bones / triangles | 46 / 1950 | 49 / 1920 |
| Walk stride (`DogWalkCycleMeters`) | 0.35 m | 0.525 m (2.7 cycles/s at 1.4 m/s) |

## Gameplay unchanged

Presentation only: the routine's eye (`Tuning.DogEyeHeight` 0.35 m: the vision cone's origin and the visual eye), the
capsule (0.2 x 0.5 m), hearing (none), the walk speed (1.4), run (2.6) and drag (0.8) speeds, the carry anchor
(`CarryForward`), the pin distance (InvestigateReach + CarryReachMargin) and the drag lift are all as before. The marker
and bubbles still float at the personality's eye + offset over the head bone (0.8 m and 1.1 m): above the bigger head.

Footprint vs doors (levels 12, 15, 17, 20, 24; `scratchpad dogroom.py`): every door is 1.0 m, the narrowest room 1.4 m;
the dog is 0.19 m wide and 0.76 m long, so it passes every door and turns in every corridor. Every dog station keeps
more than the new snout (0.47 m) ahead and the rump (0.29 m) behind before a wall (nearest: level 15 and 24 at 0.65 m
sideways).

## Drag attach point (re-measured)

The snout reach is measured, not typed: `ModelKit.ForwardReach(entry)` = the front of the catalog's rest pose bounds,
turned by the entry's yaw, times the rig scale: 0.476 m for the fitted Husky (logged by DogShots) (0.322 m for the old Shiba). The held
furniture's near edge is at `CarryForward - depth / 2` (the carried furniture takes the dog's yaw): 0.225 m for the
chair, armchair, lamp and rocking chair, 0.275 m stool, 0.375 m office chair. The Shiba's snout already reached 0.1 m into
the chair (DOGCARRY A VERIFIER 3); the Husky's would reach 0.25 m (chair: hold back 0.251 m). So while the dog drags (and wags after the drop) its
model steps back along its facing by `Inhabitant.DogHoldBack` = max(0, reach - near edge), eased at
`Tuning.DogHoldBackRate` (presentation only: the routine, its anchor and the furniture never move for it). GameState
gives every inhabitant the furniture's half depth (`Inhabitant.CarriedHalfDepth`, set with the routines' CarryForward).

## Black Labrador look

- Ears and tail: the Husky's pricked ears and curled tail are posed as a Labrador's after each clip pass by
  `PetPose` (new, `Assets/Scripts/Runtime/PetPose.cs`): each ear chain aimed down beside the head
  (`Tuning.DogEarOut` 0.35 out, `DogEarForward` 0.15 forward per unit down, in the head's frame), the tail chain back
  and down (`DogTailDroop` 0.6), straightened 85 % (`DogTailWeight`) so the clip's sway still shows. Applied by
  InhabitantRig (pets, after the head), by the title logo before it bakes each walk frame, and by DogShots.
- Fur map: `Assets/Art/Characters/Resources/DogFur.png` (2048, loaded as Resources `DogFur`,
  `Tuning.DogFurTextureResource`), composed by `tools/assets/dog/compose_dogfur.py` (the sources are never modified):
  - UV0 atlas (`make_husky.py`, layout drawn in `Assets/Art/Characters/dog_fur_uv_template.png`): body regions boxed by
    each triangle's normal (flank, mirrored; back; belly; chest and front legs; rump) at 0.46 UV per body length, and a
    FACE region (0.46 x 0.46 of the atlas) where every forward-facing head triangle (centroid ahead of the neck and above
    the jaw) is projected from the front: the model's eyes (x +-0.00216, up 0.02678 mesh units) land on the picture's
    eyes (x 355 and 685, y 390), its nose (up 0.0255) on the picture's nose (y 640), its jaw (0.0232) on the chin (y
    870), piecewise linear in height, uniform across.
  - Fur direction: the source strands run top to bottom. The flank region (snout to the right) takes a copy rotated
    90 deg (strands head to tail) above the belly line and the fur as given (downward) on the legs, blended over a
    band; the back and belly regions are laid out snout up, the chest and rump regions upright, so the fur as given runs
    head to tail or downward there. Tiled at 256 px per source (about 3 cm strands on the dog).
  - Seam: the fur's gain is matched to the picture's own fur in a ring inside its silhouette (x1.31 to 1.36), and the
    picture's edge is eroded 9 px and feathered 9 px into the fur, so the face triangles meet the neck's in the same fur.
  - `ModelKit.ApplyPetFurMap`: with the map present every slot of the dog's model takes one URP Lit material (white base
    colour, the map as base map: `PrimitiveKit.MapMaterial`, one per map), after the paint and after the tint, so the
    game and the title logo both show it. Without the map the dog shows its palette coat (tint `#505458` charcoal over the
    palette white): no new material.
- To replace the textures: put new sources in place (same names) and run `python tools/assets/dog/compose_dogfur.py`
  (re-run `make_husky.py` first only if the UV layout changes). To paint a whole map by hand instead, paint on
  `dog_fur_uv_template.png` and save it as `Assets/Art/Characters/Resources/DogFur.png`.

## Colour and contrast

- Dog's actual mean colour (the map sampled on every triangle at 7 points, weighted by its bind pose area, averaged in
  linear light): `#2A2929` (L* 16.7). The atlas' plain pixel mean is the same.
- Against `floorColor` (what `ModelM5Tests` reads) of the five shipped dog levels: nearest 42.4 (the `#B07A4E` carpet
  border at 0.82, levels 20 and 24), wood 53.0, light oak tint 59.3, marble tint 68.5, cream 75.1 to 79.6. New static
  test `ModelM5Tests.The_dog_fur_map_stands_out_from_every_floor_it_walks_on` (the map's pixel mean, same bar 30).
- Against the floor IMAGES actually drawn (colour map means): parquet `#CE8B46` 68.3, light oak 59.2, marble 68.0, ivory
  tile 69.9, plain carpet 56.8 (its 0.82 border 44.8), but herringbone `#513A28` only 19.1 (and verde 15.0, teal tile
  26.5: no dog level uses them).
- Floors changed (product owner decision; rooms on the dog's stations and paths only, `floorFinish` removed so the room
  shows the default parquet, `floorColor` `#B07A4E` kept: it already is the parquet rooms' tint, `floor` hard unchanged,
  nothing else touched):

| Level | Room | Dog use | Before | After | Floor looks |
|---|---|---|---|---|---|
| 17 | sejour | both stations (sleep 7.75, 2.25; watch 7.25, 2.75) | herringbone, 19.1 | parquet, 68.3 | 3 (parquet, herringbone in bureau, marble) |
| 16 (not shipped) | salon | both stations (5.5, 0.75; 6.75, 0.75) | herringbone, 19.1 | parquet, 68.3 | 2 (parquet, herringbone elsewhere) |

  Not changed: level20's salon and bureau (herringbone) are off the dog's route (entree to cuisine through their shared
  door); level17 bureau, level16 chambre, couloir, cuisine idem; levels 12, 15, 23, 24 have no herringbone. The
  `floorColor` contrast was never below 30 (53.0 for these rooms). `docs/m9/FLOORS_WALLS.md` table rows 16 and 17 and
  the dog note updated.
- The tint (`PersonalityDef` dog row) is `#505458` (was `#4F6670`): the coat without the map, a charcoal that is not a
  near-black (a tint may not be), 35.3 from the nearest dog floor. A pet's light parts (mask, belly, eye whites) take the
  palette white (`ModelKit.PetLightColours`).

## Title logo

`TitleLogo` now reads the dog row's model and tint (`PersonalityDef.For(Dog)`), so the bake picks up any future dog. The
bigger dog at full size would not fit: 0.72 m on screen between the frame's left edge and the chair's left edge (0.70 m)
with the rump inside. So the bake scales its copies by `Tuning.TitleLogoDogScale` 0.8 (1.2 times the old logo dog,
about the model's root), the grip moved from -0.62 to -0.67 so the snout (0.355 m ahead on screen) stays on the chair's
left edge, the walk stride from 0.24 to 0.29. The rescale guard of the bake now only fixes a gross scale error (> 25 %:
the hanging ears make the dog up to 15 % lower than the rest pose height) before the logo scale. The baked frames get
the PetPose and the fur map like the game.

## Files

- New: `Assets/ThirdParty/Models/Quaternius/quaternius_husky.glb` (+ .meta), `Assets/Art/Characters/Resources/DogFur.png`,
  `Assets/Art/Characters/dog_fur_uv_template.png`, `Assets/Scripts/Runtime/PetPose.cs`, `Assets/Editor/DogShots.cs` (look
  tool), `tools/assets/dog/` (make_husky.py, compose_dogfur.py, glbinfo_lib.py, husky_uv.json).
- Changed: Tuning (DogModelScale, DogModelEyeHeight, DogFurTextureResource, DogHoldBackRate, DogEar*, DogTail*,
  BudgetPetBones 49, DogWalkCycleMeters, TitleLogoDogGrip, TitleLogoDogScale, TitleLogoDogStride), PersonalityDef (dog
  model and tint), ModelCatalog (QuaterniusHusky), ModelCatalogBuilder (the Husky spec), ModelKit (PetLightColours,
  PetFurMap, ApplyPetFurMap, ForwardReach), PrimitiveKit (MapMaterial), Inhabitant (hold back), InhabitantRig (PetPose),
  GameState (CarriedHalfDepth), TitleLogo (dog row, logo scale, PetPose), Credits (dog line), docs/LICENSES.md (Husky row,
  the two dog images), docs/m9/FLOORS_WALLS.md, levels 16 and 17 (one room each, floorFinish only),
  `test_m5_watchers_dog.json` (model id).
- Tests updated statically (none run): ModelM5Tests (Husky id, model eye, big dog height/length/snout, fur map contrast),
  CoreM5Tests (dog row model and tint), ProbeTestsM5Watchers Step38 (Husky id, 49 bones, model eye at
  DogModelEyeHeight). Every `// MUTATION:` marker kept (PET_EYE_TARGET's line untouched).

## Unity runs (2 of 3)

1. `-executeMethod OutOfSight.Editor.DogShots.Shoot -dogShots Build/shots/dog -logFile Build/DOGBIG.log` (compiles every
   assembly, imports the Husky and DogFur.png, rebuilds the catalog, then shoots): exit 0, no `error CS` (only the old
   CS0628 warning of Inhabitant.FootstepCount). Catalog: `quaternius.husky` 49 bones of 49, 1920 triangles of 3000, eyes
   found (86 vertices), facing yaw 0, Idle eye 2.659 units. Shots in `Build/shots/dog` (lineup with the old Shiba, a man
   and the chair; door from above; fur flank, back, legs; face front and three quarters; drag side and front; levels
   12, 15, 17, 20, 24 at game distance and close). Looked at: a black Labrador twice the old dog's bulk, hanging ears,
   tail carried low, the face's eyes and nose on the model's, no seam visible between face and neck; the flank's strands
   run along the body (faint on black), down the legs; through a 1.0 m door with room to spare; in the drag the snout
   meets the chair's front edge; level17's sejour now shows the light parquet under the dog.
2. `test . --mode PlayMode --filter Step74b_` (the title logo look test, `TestResults/dogbig_logo.xml`): 1/1 passed.
   Logged: dog between y 357.0 and 412.4 (title glyphs top 346.7, 20:9 phone top 483), opaque between x -720.9 and
   -598.7 inside the frame (-722.4 to -468.4). Looked at `Build/shots/titlechair` (sheet and dog frames): the black
   Labrador trots in, its snout on the chair's left leg, drags it home, turns and fades out at the left edge; it never
   covers the letters.

## A VERIFIER

1. Run ModelM5Tests, CoreM5Tests, CreditsTests (EditMode) and ProbeTestsM5Watchers Step38_, ProbeTestsM5Game Step38h_
   and Step38i_, ProbeTestsTitleChair Step74b, ProbeTestsM3Models (PlayMode).
2. Feel at game distance: the 1.5x size, the slower trot (2.7 strides/s) and its paw patter; the hold back slide
   (0.25 m in 0.25 s) when the dog lets go and walks away.
3. Ears: the PetPose aim is computed, never seen in motion: check the hanging ears do not cut into the cheeks while the
   head turns, and the tail (85 % straightened) in Walk and Idle.
4. The face picture on the low poly muzzle: the long muzzle top is stretched (front projection); the pricked ear
   triangles carry forehead fur. A Labrador mesh (floppy ears, otter tail) would read better if one becomes available.
5. The visual (0.76 m) is longer than the capsule (0.4 m): it may poke into furniture props or walls where the dog turns
   close to them (no clearance problem found at its stations).
6. Herringbone rooms off the dog's route (level17 bureau, level20 salon and bureau) still give 19.1: a drag or a chase
   through them shows a dark dog on a dark floor. Product owner's call (rim light or floor).
7. The pet light palette (white mask) only shows without the fur map.
8. Title logo: the dog's rump comes within 1.5 UI units of the frame's left edge (test bar 2 below it); outside the pool of
   light the black dog is dark on the dark menu background. If wanted: TitleLogoDogScale 0.75 or a grip of -0.65.
9. ProbeTestsM5Watchers.AssertWears now expects the one fur map material on every dog slot (Step37_*), statically updated.

## v3: product owner feedback after playing (fur, head, bite)

Feedback: "a flat black low-poly silhouette": the fur is not visible, the head is too small for its face, and the dog
should bite the furniture's edge (head turned 60 deg, mouth open) from the grip to the drop.

### 1. Why the fur did not show, and the fix
- The material was right: `PrimitiveKit.MapMaterial` builds a URP Lit with a WHITE base colour and DogFur.png as base map
  (no tint multiplied in); every slot of the dog got it after the paint and the tint. The UVs were right on every part
  (checked on the atlas preview: face, flank, back, belly, chest, rump, nose, eyes all inside their regions).
- The causes: the source fur's strands sit within a few levels of its black (mean #1F1F1F, strands +5 to +15), the
  tile was 256 px (3 cm strands), so at game distance the mipmaps averaged it to flat black; smoothness 0.25 gave no sheen.
- Fix (`compose_dogfur.py` v3, sources untouched): the tile's fine detail (source minus its 5 px blur) boosted 2.3x, the
  fur and the face picture lifted by the same gamma 0.78 (darks up, blacks stay black), tile 512 px (strand clumps about
  6 cm). At run time (`ModelKit.PetFurMap`): mip bias -0.6 (`Tuning.DogFurMipBias`) and anisotropic level 4; the map
  material's smoothness 0.4 (`Tuning.DogFurSmoothness`, a coat's sheen; 0.5 put a pale stripe along the back). No normal
  map: the GLB has no tangents (adding them is not cheap to verify) and at game distance its detail mips away like the
  albedo's. No rim: URP Lit has none (a custom shader would be a new material); the sheen does the job.
- The eye whites keep the palette white (`ModelKit.IsPetEyeWhite`), so the eyes read; irises and pupils come from the
  face picture.
- Mean colour now `#413F3F` (area weighted; atlas pixel mean `#3E3C3C`, what the new EditMode test reads). Against the
  dog levels' `floorColor`: nearest 35.8 (36.5 for the pixel mean), the carpet borders of levels 20 and 24; wood 46+, cream
  60+. Against the floor images: parquet 61.5, light oak 49.6, marble 57.9, ivory tile 59.9, plain carpet 47.3 (its border
  35.4), herringbone 16.3 (only off the dog's stations and paths since the level16/17 changes). Test bar 30 kept.

### 2. Bigger head, face unrolled
- `Tuning.DogHeadScale` 1.35 on the head bone (`PetPose`, every frame, absolute): head, muzzle, eyes and ears grow, the
  neck blends through the skin weights (no visible tear in the shots). The snout now reaches 0.517 m (rest 0.476 + 0.35 x
  the 0.118 m it stands ahead of the head bone): `InhabitantRig.SnoutReach`, used by the hold back (chair: 0.292 m).
- Face UVs (`make_husky.py` v3): the front projection squeezed the whole muzzle top into the few rows between the eyes and
  the nose. Now the picture's height follows the model's height through the eyes (390), the nose top (560), middle (640),
  bottom (700) and chin (870), and on the muzzle top it slides from the eyes' row to the nose's top with the distance
  from the eyes to the tip: the muzzle top shows the picture's nose bridge at its length. The eyes still land on the
  model's eyes, the nose on the nose front, the mouth line and chin under it.

### 3. The bite
- The rig had no jaw: `make_husky.py` v3 adds a "Jaw" joint under Head (hinge behind the mouth: forward 0.0180, up 0.0243
  mesh units), its inverse bind matrix from the head's, and weights the 98 lower jaw vertices (head region, below the
  mouth line, ahead of the hinge) to it alone. 50 joints (`Tuning.BudgetPetBones` 50), still 1920 triangles.
- `GameState` sets `Inhabitant.Biting` every step: the hold dog, holding (from its pin and grip through the drag) and not
  waiting for a called human. `Inhabitant` eases `ShownBite` at `Tuning.DogBiteRate` (6/s) into `InhabitantRig.Bite`;
  `PetPose` rolls the head 60 deg (`DogBiteRollDegrees`) about its own forward axis and dips it 15 deg
  (`DogBitePitchDegrees`), and opens the jaw 30 deg (`DogJawOpenDegrees`) about the head's right axis. The drop (EndHold)
  clears Biting: the mouth closes and the head comes back in about 0.17 s. The MUTATION:HEAD line is untouched (the bite
  is applied after it, in PetPose).
- Title logo: the bigger head and the brighter fur, no bite (its two baked walk frames serve the trot in and out too).

### v3 Unity runs (3 of 3)
1. DogShots (levels 12 and 24): compiled, catalog 50 bones of 50, jaw found, head bone 0.358 m ahead of the root.
   Looked at: the strands show on the flank (along the body), back and legs, a soft sheen, the coat still black; bigger
   head; at game distance the dog reads as a dark furred dog, not a silhouette. The back's sheen at 0.5 made a pale
   stripe: lowered to 0.4.
2. DogShots again (bite views `bite_alone`, `bite_left`, `bite_left_rest`, `bite_close`, `drag_game`): the head rolls
   onto its side toward the chair; the jaw's opening is hard to see at 24 deg from these angles: raised to 30 (not shot).
3. `test . --mode PlayMode --filter Step74b_` (`TestResults/dogbig_logo_v3.xml`): 1/1 passed; dog between y 356.8 and
   412.5 (letters top 346.7, phone top 483), opaque x -720.9 to -595.2 inside the frame (-722.4 to -468.4). Looked at:
   the grey-black Labrador with its bigger head, readable on the dark menu, snout on the chair leg.

### v3 A VERIFIER
1. The bite in play (level 12, 24): the 60 deg roll direction (it rolls toward the dog's left), the 15 deg dip (it may
   read as a raise once rolled), and the jaw at 30 deg (unseen after the change from 24): a gap must show under the nose.
2. The stretched lip triangles between the jaw and the muzzle when the mouth opens (the fur stretched over them).
3. The sheen at 0.4 under the game's lights and the night levels (lamp off).
4. Face from the game camera: the white eye whites and the nose read; the brows and the mouth line stay subtle.
5. Run ModelM5Tests, ProbeTestsM5Watchers Step37_/Step38_ (AssertWears now expects the fur map and the palette eye whites
   on the dog), Step38h_/Step38i_, Step74b_.

## v4: verified on the real runtime path (product owner feedback on the 09:46 builds)

### Diagnosis (PlayMode look test on the Boot scene and the real level 12, `ProbeTestsDogLook`)
- New `Assets/Tests/PlayMode/ProbeTestsDogLook.cs`: `GameState.LoadLevel("level12")` with the game's own rules, every human
  frozen, the stool put in the dog's view and moved until the dog barks, runs, pins, grips and drags it home; game camera
  and close camera frames at the start, the grip, the drag (and both muzzle profiles) and after the drop
  (`Build/shots/dog/runtime_level12_*.png`), the dog's renderer, materials, texture, bite and bones logged.
- Logged in play: the skin shows `Map DogFur` (URP Lit, base colour white, base map DogFur, 2048 px, mip bias -0.6) on every
  slot but the eye whites (palette white), no property block, the mesh with UVs on all 5032 vertices: the texture is in
  the build's Resources and reaches the dog (nothing in CharacterLook, the tint or the paint replaces it). Grip: Biting
  true, bite weight 1.00, head scale 1.45, jaw 30.0 deg; drag: bite 1.00, hold back 0.195 m; after the drop: Biting false,
  bite 0. PetPose runs in InhabitantRig.Apply, from Inhabitant.LateUpdate, after the Legacy Animation pass; the Jaw joint
  is keyed by no clip.
- One harness trap: `WaitForEndOfFrame` never comes in the batch mode editor (the first look run hung until its timeout);
  the shots now render after a plain frame (the bones still hold the last LateUpdate pose).

### Geometry (`tools/assets/dog/make_husky.py` v4, in the bind pose, after the UVs, inverse bind matrices untouched)
- Torso, neck and haunches subdivided (red-green, no crack: 320 triangles into 4, their neighbours into 2 or 3), midpoints
  with their UV, normal and merged skin weights (top 4 renormalised): 1920 to 2952 triangles (budget 3000).
- Head: the muzzle 40 % shorter ahead of the eyes, skull and cheeks pulled 45 % toward a sphere, then the head bone grown
  1.45x at run time (`Tuning.DogHeadScale`): about 1.5x the original head overall, rounder, the muzzle shorter and fuller.
- Taubin smoothing (3 x 0.45 / -0.47) of the body and head (paws, ears, eye and nose pieces kept), then smooth normals
  welded over Main and Main_Light: no facets left.
- Snout re-measured: rest reach 0.435 m (catalog bounds, was 0.476), with the grown head 0.470 m
  (`InhabitantRig.SnoutReach`); hold back for the stool 0.195 m. Catalog: eyes idle 2.675 units, size 0.99 x 3.08 x 3.69,
  50 bones, 2952 triangles.

### v4 Unity runs (4 of 4)
1. SetupAndCompile (`Build/DOGBIG_v4.log`): compiled, catalog rebuilt (50 bones of 50, 2952 triangles of 3000).
2. PlayMode DogLook_ + Step74b_: hung on WaitForEndOfFrame (fixed in the test), ended by the CLI timeout.
3. PlayMode DogLook_ + Step74b_ (`TestResults/dogbig_v4.xml`): 2/2 passed. Looked at the runtime shots: the fur shows
   (strands along the body, a soft sheen, still black), the body round, the head big and round with hanging ears; at
   the grip and in the drag the head is rolled onto its side against the stool. Title (real menu bake,
   `Build/shots/dog/title_chair_*`): the round, furred dog with its big head, snout on the chair leg, inside the frame
   (opaque x -720.3 to -599.3, frame -722.4 to -468.4; dog y 357.0 to 412.3, letters top 346.7).
4. PlayMode DogLook_ with muzzle profiles (`TestResults/dogbig_v4b.xml`): 1/1 passed; the roll reads, but the 30 deg jaw
   does not show a visible gap in the shots (logged open, see A VERIFIER).

### v4 A VERIFIER
1. The open mouth: logged 30 deg on the Jaw joint at the grip and in the drag, but no gap readable in the runtime shots
   (the shortened muzzle leaves a small lower jaw, and the head faces the furniture). Next try: DogJawOpenDegrees 45 and a
   jaw region reaching higher (JAW_MOUTH_UP in make_husky.py), then a profile shot.
2. The face picture from the game camera is dark on a black dog: the eyes (white) read, the brows and mouth barely.
3. Run ModelM5Tests, ProbeTestsM5Watchers Step37_/Step38_, ProbeTestsM5Game Step38h_/Step38i_ (not run).
## Follow-up

The open mouth (v4 A VERIFIER 1) and the face's readability (2): see `docs/next/progress/DOGFACE.md`.

