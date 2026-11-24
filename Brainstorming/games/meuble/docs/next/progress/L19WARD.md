# L19WARD (2026-11-24): card 19 (level22), the bedroom "wardrobe" against the north wall

Mapping checked: levels.json rev 4, card 19 = "levels"[18] = level22 ("Skeletons in the Closet").

## What the screenshot shows
- The wooden box in the middle of the start bedroom ("chambre", x 0-3.9, z 8-11.9) is the prop **Paravent**,
  kind **cabinet** (1.2 x 1.6 x 0.3 m), not kind "wardrobe": it is NOT a hiding spot (WardrobeRule only takes kind
  "wardrobe"), so no designer route hides in it. The routes only walk around it (z 8.25 then x 3.25).
- Camera of the screenshot: the x = 0 wall is the bottom edge (grass outside), the z = 11.9 wall (bed headboard,
  nightstand) the left edge, the z = 8 partition (boudoir) the right edge, and the **x = 3.9 wall, with the door to the
  gallery (3.95, 10.75) and its door icon, the top edge**. Screen up is within about 25 degrees of world +x, so
  "north" = the x = 3.9 wall. (The headboard is on the z = 11.9 wall, on the upper left of the shot.)

## Change (level22.json only)
| Paravent | x | z | yaw | footprint |
|---|---|---|---|---|
| before | 1.95 | 9.2 | 270 | x 1.8-2.1, z 8.6-9.8 (mid-room) |
| after | 3.7 | 9.1 | 270 | x 3.55-3.85, z 8.5-9.7 (back 5 cm off the x = 3.9 wall) |

- Yaw 270 already faced -x, so the front faces into the room; size and yaw unchanged.
- Clear of the gallery doorway approach strip (z 10.25-11.25, 1 m deep: 0.55 m margin), of the boudoir door strip
  (x 0.75-1.75), of the bed (x 1.15-2.75, z 10.4-11.8), the nightstand and the slippers (0.85, 10.95).
- Nothing else moved. No plant touched (the chambre has none; level keeps its 3 plants). The hint does not mention
  this prop.

## Audit
- Run 1 (Build/l19ward_r1.log, shipped file, Normal, -slack): **0 defects**, exit 50.1 s, waiting 15.6 s (31 %),
  4 pauses (3 en route), longest 5.8 s, margin 0.3/0.3 s, slack 5 (0.5 s), 2 wardrobe hides (8.9 s hidden).
  Warnings: dead rooms boudoir and office.
- The run was stopped on the user's request before the Difficile baseline and before the two variants
  (Paravent at z 9.1 and z 8.65) were audited. **The moved file was never audited and the routes were not
  rewritten** (designerRoute / designerRouteHard are the shipped ones).

## A VERIFIER
- The moved Paravent used to stand between Mamie's gallery station s3 (4.75, 10.75, facing 270, looking through the
  bedroom door) and the start corner; against the x = 3.9 wall it no longer screens that line. Check the start
  (first 3.2 s wait at (0.75, 8.25)) and the walk along x = 3.25 at both difficulties.
- The designer route's column x = 3.25 passes 0.13 m from the Paravent's front face (stool half width 0.175): the
  route may now be blocked for the replay. If the level22 route tests fail, run the audit with -writeRoutes.
- DoorwayTests, PlantPlacementTests and Dressing_ were not run.
- The Paravent is a cabinet (not a hide): if the user wanted a real wardrobe hide in the bedroom, change its kind
  (and size 1.0 x 2.0 x 0.6) and re-audit: that changes the level's routes.
