# DOGFACE: the black Labrador's open mouth and face readability

Follow-up of DOGBIG (`docs/next/progress/DOGBIG.md`, v4 A VERIFIER 1 and 2). Two problems left on the black dog:
1. the bite opened the Jaw joint 30 deg in the logs but no open mouth showed (the shortened muzzle left a tiny lower jaw,
   and the skin between the lips only stretched: a wall of black fur, no inside);
2. on the black face the eyes read, the brows and the mouth line barely.

Scope kept: jaw, face mesh, face texture, bite angles. Grip anchors, the snout target and carry logic (GRIP) untouched;
PetPose.cs untouched (only `Tuning.DogJawOpenDegrees` changed).

## 1. The open mouth (`tools/assets/dog/make_husky.py` v5, step 3b, on the final shape)

- The Jaw hinge moved back behind the mouth's corner: mesh (forward 0.0171, up 0.0242), was (0.0180, 0.0243). The lower
  jaw swings from further back, so its tip drops more for the same angle.
- The lower jaw is chosen on the final (v4 reshaped and smoothed) shape, per triangle: every body triangle of the muzzle
  ahead of the mouth's corner (forward 0.0182) and below the mouth line `MOUTH_LINE` (up 0.0239 at the corner to 0.0243
  under the nose, level with the face picture's own lips). 54 triangles; its inner vertices pushed down 45 % deeper
  (`DEEPEN`, the corner and the cut stay put).
- Skin weights: the inner jaw vertices go to the Jaw joint, eased in from the corner (`JAW_RAMP` forward 0.0178 to
  0.0190, so the throat stretches instead of folding); the back boundary vertices take half of it.
- The skin is CUT along the mouth line: each of its 13 vertices gets a second copy for the jaw side (snapped onto the
  line, at most 0.0004, so the lips meet on a clean curve). Each of the 14 cut edges gets a strip of two triangles
  between its upper and lower copies (26 triangles): zero area with the mouth shut, the mouth's inside when it opens.
  The corners stay closed (the strip tapers to them).
- The strips' UVs are in a new MOUTH atlas region (0.60, 0.62, 0.30 x 0.14): across = left corner, front, right corner;
  down = upper lip to lower lip.
- Triangles: 2952 to 2978 (budget 3000 unchanged), bones 50 (unchanged).
- `Tuning.DogJawOpenDegrees` 30 to 45.

## 2. Face texture (`tools/assets/dog/compose_dogfur.py` v5; sources untouched)

- Brows: a soft warm tan mark over each eye (`BROW_COLOUR` #8C705A at 0.5, feathered 9 px, inner end higher): L* 34
  against the forehead's 22 (dE 14.7). A hint, not a tan-pointed dog.
- Mouth line: drawn on the mesh's own cut (`husky_uv.json` 'mouth_line', the upper lip's face UVs): a muted rose core
  (#824850 at 0.95, 11 px) with a lighter grey lip edge just above it, so the shut mouth shows as a line on the black
  muzzle. Only the front's part: on the muzzle's sides the front projected face UVs fold over themselves (steep, zigzag
  segments), and a line painted there smeared into a pink spot at the mouth's corner (seen in run 2, removed).
- Mouth inside (MOUTH region): dark palate #3A121A at the upper lip to a deep red throat, the tongue's pink (#E87A8A,
  with a middle groove) rising from the lower lip at the front, the corners in shadow.
- Coat mean unchanged: #413F3F area weighted, atlas pixel mean #403B3C (was #3E3C3C), the floor contrast test bar
  still met.
- To rebuild: `tools/assets/.venv` activated, `python tools/assets/dog/make_husky.py` then
  `python tools/assets/dog/compose_dogfur.py`.

## Offline check (scratchpad software renderer, the texture on the GLB, jaw 0 / 30 / 45 deg)

Shut: a rose mouth line under the nose falling to the corners, tan brows over the eyes. Open 45: a big dark red mouth
with the pink tongue at the front, the lower jaw's fur under it, readable from the side, the front and three quarters.

## Tests (updated statically)

- `ModelM5Tests.The_dog_face_marks_and_mouth_inside_read_against_its_black_fur` (new, EditMode): brows lighter than
  the forehead by dE 10 or more; the tongue dE 30 or more from the coat and pink; the palate dark red.
- `ProbeTestsDogLook` (PlayMode): the lower jaw has 20 or more vertices on the Jaw alone; at the grip the jaw's skin
  (skinned as the renderer does, bone matrix times bind pose) swings more than half the opening and DOWN (about the
  dog's right, in the head's frame), not up into the muzzle; two new close shots of the open mouth at the grip
  (`runtime_level12_grip_mouth_left/right.png`). Every MUTATION marker kept.

## Unity runs (3 of 3)

1. `Builder.SetupAndCompile` (`Build/dogface.log`): compiled, no `error CS`; catalog `quaternius.husky` 50 bones of 50,
   2978 triangles of 3000, eyes found (86 vertices), size 0.99 x 3.08 x 3.69 (unchanged).
2. PlayMode `DogLook_|Step74b_` (`TestResults/dogface.xml`, shots `Build/shots/dogface`): DogLook_ passed. Logged: 97
   vertices on the Jaw alone; at the grip bite 1.00, jaw 45.0 deg, the lower jaw's skin swung 45.0 deg and DOWN (cross
   product about the dog's right +0.0050); the drag held the bite, the drop cleared it. Looked at: the open mouth reads
   in the profile (`runtime_level12_drag_profile_right.png`: a dark red mouth with the pink at the lower lip, the lower
   jaw dropped under it) and at the grip (`grip_mouth_right`); at rest (`start_close`) a pink spot showed at the mouth's
   corner (the mouth line smeared over the folded side UVs): fixed in compose_dogfur.py (front segments only), with a
   stronger rose line. Step74b_ failed at once with "the title logo was never baked": TitleLogo.cs and
   ProbeTestsTitleChair.cs were being rewritten by GRIP at the time (its alternating title loops), not a DOGFACE cause;
   the title dog shares the GLB and the fur map, so it shows the new face (no bite in the title by default).
3. PlayMode `DogLook_` again (`TestResults/dogface_b.xml`), with the fixed mouth line and a lower three quarter mouth
   camera at the grip: 1/1 passed (same logs: 97 jaw vertices, jaw 45.0 deg, skin swung 45.0 deg downward, bite held in the drag, released
   after the drop). Looked at: the dog now grips lower (GRIP's work in parallel), so the close cameras landed behind the
   hedge or under the occluded-inhabitant silhouette: no new readable mouth view in this run (run 2's profile stands).
   The rest shot (`start_close`) still showed the pink smear at the mouth's corner: traced offline (scratchpad renderer,
   three quarter views) to the mouth line's two corner segments on each side, whose face UVs are squeezed by the front
   projection (squeeze 0.84 and 0.44, recorded per segment in `husky_uv.json`); compose_dogfur.py now paints only the
   front segments (squeeze 0.9 or more). Checked offline only (no Unity run left): the smear is gone, the front line
   stays. The grip mouth camera went back to run 2's placement (0.6 m aside, 0.25 m ahead, 0.05 m up).

## A VERIFIER

1. In a Unity run: `start_close` (rest) without the pink smear at the mouth's corner, after the last compose_dogfur.py
   change (front segments only; not seen in Unity).
2. The open mouth at the grip with GRIP's low grip on the stool leg: frame it (the close cameras of ProbeTestsDogLook
   may need a placement that clears the hedge and the occlusion silhouette on level 12).
3. Run ModelM5Tests (new face test: brows dE 10, tongue dE 30, palate red), ProbeTestsM5Watchers Step37_/Step38_
   (triangle budget 2978 of 3000, AssertWears unchanged), ProbeTestsTitleChair Step74b_ once GRIP's title rewrite settles
   (it failed in run 2 with "the title logo was never baked", during GRIP's edits).
4. The jaw at 45 deg swings its back underside slightly into the throat (seen offline): check from below in play; ease
   with `JAW_RAMP` or `DogJawOpenDegrees` 40 if it shows.
5. Brows: a soft tan hint (#8C705A at 0.5); if it reads as a tan-pointed breed, lower `BROW_STRENGTH`.
6. Title logo: the new face shows there (same GLB and map); not looked at in this task.