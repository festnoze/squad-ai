# M9 heads: more realistic human heads

Request: bigger heads, more marked ears, nose, chin, jaw and brow; try several variants, keep the most realistic.

## How the heads are built and tested

- `Assets/Scripts/Runtime/CharacterHead.cs` sculpts the head grid that carries the wrap-around face image. M9 adds a
  per-gender `Sculpt` (head scale, nose height and width, nose wings, brow ridge, eye sockets, cheekbones and the hollow
  under them, lips, chin and the groove over it, jaw angle, jaw edge sharpness, ear stand-off and bowl, face front
  roundness). Every feature sits on the image's own landmarks (pupils, nose tip, mouth, chin, painted ears), so the
  painted face stays on its relief. The scale pivots low in the head, over the neck, so the chin barely moves.
- The head stays one grid in the skin's own slot: no material, no renderer, no collider change. Gameplay eyes come from
  `Tuning.EyeHeight` and the catalog's `eyeLocal`, never from the head mesh, so vision is unchanged.
- The grid changed: 2 fewer face columns (18 segments), side columns packed over the ears (|du| 0.23 to 0.30) and
  spread over the back of the head, and one more row under the nose tip (a round tip on two rows). The woman in a
  jacket, the heaviest model, goes from 2780 to 2940 triangles (budget 3000).
- Shots: `-executeMethod OutOfSight.Editor.HeadShots.Shoot -headShots docs/m9/heads -headVariants v7_refined`
  (editor scene, title_house: Hugo the man, Claire the woman). Per gender: `face`, `three_quarter`, `profile`, `back`
  close-ups, `game` (default orbit camera, 4 m at 40 degrees, 55 degree field), `game_zoom` (same eye, narrow field on
  the head), `game_body` (same eye on the whole body, round 2 on), as JPG. `heads.txt` lists the triangles per variant.
  `final/` is the shipped sculpt (identical to `v7_refined`).

## Variants

| Variant | Scale | Nose | Ears (rim) | Chin / jaw (man) | Other | Verdict |
|---|---|---|---|---|---|---|
| v0_current | 1.00 | M7 | 13 mm bump | none | the M7 head | soft blob: ears and jaw barely read, flat face |
| v1_subtle | 1.06 | x1.2 | 14 mm | 4 / 3 mm | light brow, sockets | better, but still reads as the M7 head |
| v2_defined | 1.10 | x1.45 | 18 mm | 7 / 6 mm | brow 8 mm, sockets, cheekbones, sharp jaw edge | features read, but the nose is a pointed beak in profile and three quarters |
| v3_strong | 1.15 | x1.8 | 24 mm | 10 / 9 mm | everything stronger | caricature: beak nose, ears flap out from the front, dark goatee under the woman's jaw |
| v4_big_subtle | 1.15 | x1.2 | 14 mm | 4 / 3 mm | v1 features | the size works against the body, the features stay too soft |
| v5_round | 1.10 | x1.25, round tip | 16 mm, softer outline | 7 / 6 mm | face front rounded 0.4, softer jaw edge | first natural one: a real nose tip, the cheeks turn away |
| v6_round_big | 1.14 | x1.35, round tip | 16 mm | 7 / 6 mm | face front rounded 0.6 | most natural three quarters; the back of the head shows facets |
| **v7_refined** | 1.14 | x1.35, raised bridge | 16 mm (woman 14) | 7 / 6 mm (woman 5 / 3) | v6 + deeper sockets, fuller lips, columns moved to the back | **kept** |

Round 1 (v1 to v4) used a nose table with a single-row tip; rounds 2 and 3 (v5 to v7) use the rounded tip, the softer
ear outline and the rebalanced grid, which is what ships. Older folders keep the shots of the grid they were made on.

## Kept: v7_refined

- The nose reads from every angle as a nose (straight bridge from between the eyes, round tip, wings, undercut to the
  lip), not a cone; in profile the eye now sits behind the bridge instead of on the silhouette.
- The rounded face front sets the outer eye corners and the mouth corners back from the nose, the main thing that took
  the "face painted on a flat plate" look away in three quarters.
- Ears stand off the head mostly at their back rim (14 to 16 mm), swept back, with a bowl: visible from the front and in
  the game view without sticking out.
- The man gets a firm brow, a square jaw angle and a chin; the woman a soft jaw, a small chin and a low brow, so the two
  stay distinct and neither turns uncanny. v3 showed where it turns into a caricature.
- 14 % larger heads read better at the game camera (`game_zoom`) while `game_body` keeps believable body proportions.
- Triangles per human (budget 3000): woman_jacket 2940, man_suit 2858, man 2840, woman_dress 2776, woman 2764,
  man_shorts 2728, man_tshirt 2692 (M7: 156 fewer each).
- Tests: PlayMode ProbeTestsM42Look, M3Look, M7Look, M3Models (Step25 budgets), M3Rig, M42Rig: 29 of 30 pass, the one
  failure being the known Step24f foot deformation (0.093 m against 0.08), unrelated to the head.
- Known limits: the original low-poly neck and the seam where the head grid meets the collar, both as in M7.

## 2026-11-21: woman head fix (product owner: "women faces look weird, men are ok")

- Diagnosis (her image against her sculpt): her painted eyes are larger and wider set than the man's (pupils at
  |du| 0.0705, the eyes with their eyeliner wings out to |du| 0.13), but her flat face front stopped at |du| 0.115 and
  her eye span (30 mm) squeezed the image to 0.90 of its own proportions. The outer half of each eye landed on the
  cheek ramp of a rounded front, 6.5 mm behind the pupil (man: 2 mm): in three quarters the eye sat at the side of the
  head. A 6 mm cheek bulge, a narrow 5 mm chin as far forward as the lower lip, a soft jaw edge (0.3) and the painted
  shadow under her chin (v 0.875 to 0.92) lying on the surface tucking into the neck made a heavy lower face with a
  goatee. The landmarks themselves (nose tip, mouth, chin, ears) matched the image; the lip bump sat 7 rows high.
- Changes, woman only (the man's shape, sculpt and wrap are untouched; his shots are identical): face front to
  |du| 0.135 and eye span 31 mm (image within 6 % of its proportions), front exponent 3.6 over the eyes and
  FrontRound 0.3 (flatter across the eyes), sections 3 mm wider over the cheeks and tapering to the chin, the skull back
  4 mm shorter (rounder), the lower face set back 2 to 3 mm behind the lips, cheek bulge 3 mm, chin 3.5 mm and wider
  (sigma 20 mm), jaw angle 1.5 mm, jaw edge 0.7, lips and their row on the painted mouth (v 0.69), the two lowest rows
  at 0.91 and 0.96, and her wrap's neck colour brought up to just under the painted chin line.
- Same grid size: triangles unchanged (woman_jacket 2940, man_tshirt 2692). No material, renderer or gameplay change.
- Shots (not versioned): Build/shots/heads_fix/run1 (final = before, w1_flat, w3_wide), run2 (final with the round 1
  choice, w5_edge05), run3 (shipped). `HeadShots` gained `WomanShapeTrials` (her landmarks, rows and sections by
  reflection) to try shape changes, not only sculpt values.
- Result: the face reads rounder and wider like her image, the eyes sit on the face front in three quarters and the
  game view, the cheeks and chin no longer bulge, the profile chin sits behind the lips. Still open: a darker band
  under the chin in the front view, barely lighter after the neck colour change, so mostly the shading of the
  surface turning under the jaw (the man has the same, hidden by his darker skin); and her painted eyes stay larger
  than the man's (that is the image itself).

## 2026-11-22: CHIN, the dark band under the women's chin

- Cause: shading, not the image. Under v 0.89 her wrap is already the flat neck colour (the same as the neck below the
  collar), yet the band rendered near black. The head grid's last rows tuck from the jaw line down to the collar: that
  surface faces down and back (measured on the posed mesh in game: mean normal y -0.76, z 0.32), away from every
  ceiling light and the sun, and the jaw line's own normal was a central difference with that tucked row, so it leaned
  down too. Shaded as is, chin to collar read as a dark band, then the neck (facing out) lit again at the seam. The man
  has the same surface, shorter (his chin sits lower) and hidden by his darker skin. Not a fold, not inverted normals
  (no sign flip anywhere), not the hair or skin palette, not the face UVs.
- Fix (woman only): `Sculpt.TuckNormal` (CharacterHead.cs), 1 for the woman, 0 for the man. On the rows under the jaw
  line the shading normal is the face's slope arriving from the row above (one-sided, so the jaw line keeps the chin's
  own front), turned toward the neck's outward normal as the vertex tucks (fully by tuck 0.5). The tucked rows then
  light like the neck they meet and the seam at the collar disappears. Positions, UVs, triangles, weights, material:
  unchanged. The man's branch is skipped (TuckNormal 0) and `GridNormal(fromAbove: false)` is the old code moved into
  a function, so his normals are bit for bit the same.
- Measured in game after the fix (posed mesh, face frame): plain woman lowest y -0.02 / mean z 0.86, jacket -0.01 / 0.86,
  dress 0.01 / 0.99.
- Test: PlayMode `ProbeTestsChinLook.ChinLook_WomenUnderChinOnTheRuntimePath` (Boot, then level11, level9, level10 for
  the three woman models and level13 for a man as reference, all humans pinned): asserts the under-chin normals of each
  woman face out (lowest y > -0.45, mean z > 0.75), and shoots front, three quarters and a far narrow-field game view at
  Haut, Moyen (the mobile default) and Bas, plus a "before" pass (TuckNormal 0 by reflection) on level11. Passed.
  Mutation `chin_tuck_normal` added to mutation.sh (marker MUTATION:CHIN_TUCK_NORMAL). HeadShots gained the trials
  `c0_before` (TuckNormal 0) and `c1_soft` (0.6).
- Shots (not versioned): Build/shots/chin/runtime_*.png, before_*.png, runtime_chin.txt. In the front views of the
  jacket and the dress the chin and the under chin now share the neck's tone, the painted chin line gives the outline;
  the game views (orbit pitch, far) read clean.

### A VERIFIER

1. HeadShots never ran in this task: two of the three allowed Unity runs died at compile (one on my test, one on
   LevelAudit.cs being edited by HUMANAUDIT at that moment). To do: `-executeMethod OutOfSight.Editor.HeadShots.Shoot
   -headShots Build/shots/chin/headshots -headVariants c0_before,c1_soft,final`, then compare woman_face and
   woman_three_quarter across the three, and check man_* are identical in all three.
2. Moyen and Bas (hard shadows on Mobile_RPAsset): a hard-edged shadow patch can sit on one side of the chin bottom
   (runtime_level9_woman_jacket_medium_face, runtime_level10_woman_dress_low_face). It is the head's own shadow on the
   under chin; it used to vanish in the dark band. If it bothers, try `c1_soft` (TuckNormal 0.6) or a receiver-side
   bias; Haut (soft shadows) looks right.
3. A faint vertical crease down the centre of the chin, from the lip to the chin bottom, on both genders (the man's
   front shot has it too): the centre column of the lips and chin bumps. Pre-existing, not touched here.
4. The level11 close-ups (front and three quarters, before and after) are blocked by furniture in front of the plain
   woman (the game's X-ray silhouette shows instead); her far game view is fine. Re-shoot her from HeadShots (item 1).
5. The jaw side under the ear is still darker in three quarters with the room light from the window behind: form
   shading of the side plane (the man shows it as well), not the under chin. Check against NIGHT's lighting.
