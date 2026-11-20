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
