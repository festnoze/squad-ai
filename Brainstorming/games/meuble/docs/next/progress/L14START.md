# L14START progress (2026-11-24): level 14 starts in the bedroom, the route crosses the whole house

## Which level
- Card 14 = Assets/Resources/Levels/level14.json ("La mezzanine", lesson split, requires sit), player = red armchair.
- User request: the spawn sat in the middle of the sejour, so the bedroom and the bathroom (the far side from the exit)
  were never visited. Start in place of the grey armchair, and move the bathroom door so the route crosses everything.

## Status: NOT VALIDATED (audit stopped on the user's order)
- The level file holds an UNAUDITED variant (Mamie bathroom dwell 2 s, living room dwell 20 s). The last audited state
  (12 s / 12 s, run R2) still had defects (see below). The user stopped the audits before R3 ran.
- designerRoute and designerRouteHard were NOT rewritten: -writeRoutes only writes a passing level. Both routes in the
  file are still the OLD ones (they start at the old spawn 5.75, 6.25 on the rug), so every route replay test of level14
  will fail until a passing audit rewrites them.

## Changes (level14.json, rev 1 -> 2: old best times are no longer read)
- Spawn: (5.75, 6.25) yaw 270 -> (2.25, 7.75) yaw 180, in the bedroom "chambre", where the grey armchair stood, facing
  the bathroom door.
- Grey armchair "FauteuilMamie" removed: it was not a decoy (the level has no decoys), only Mamie's seat; the player IS
  her armchair now. Her sit station on it became her "sit": "player" station (seat home = the new spawn).
- Doors (connectivity):
  - before: sejour <-> chambre (4.45, 7.25), chambre <-> salle (1.25, 4.95); the bathroom was a dead end off the bedroom.
  - after: chambre <-> salle (1.25, 4.95, unchanged), salle <-> sejour (4.45, 3.75, width 1.0, moved from 4.45, 7.25).
    Bedroom -> bathroom -> sejour is the only way out of the right side; the east side (mezzanine, couloir, entree,
    cuisine) is untouched.
  - New door approach strips (1 m each side, z 3.25-4.25): bathroom side x 3.45-4.4 clear of the washbasin
    (z 4.45-4.9) and the bathtub (x <= 0.75); sejour side x 4.5-5.5 clear of the plant (z <= 2.1) and the ramp (x >= 6).
    The chambre <-> salle strips are unchanged and stay clear of the commode. No plant moved (none in the bathroom, the
    bedroom plant stays in its corner). The floor book stack (1.55, 7.8) is beside the spawn, in no door approach.
- Mamie (loop): s0 (2.25, 7.25) f180 0.5 s; s1 same spot, sits on the player (seat 2.25, 7.75, yaw 180) 2 s; s2 the
  bathroom window (2.25, 2.25) f180, dwell 2 s; s3 the living room window (5.25, 7.75) f0, dwell 20 s.
  Lea unchanged.
- Hint (Strings.cs level14.hint), EN / FR "tu":
  "Mamie sits on you first, then walks through the bathroom to the living room window: let her go ahead, and cross the
  mezzanine while her back is turned." / "Mamie s'assoit d'abord sur toi, puis passe par la salle de bain jusqu'à la
  fenêtre du séjour : laisse-la prendre de l'avance, et traverse la mezzanine pendant qu'elle te tourne le dos."
- Test: ProbeTestsM5Levels.Step45h control. It raised the bookshelf to 2 m to hide the armchair at the start view; the
  shelf is now far from the spawn, so the control moves the shelf (3 m tall, 0.1 m deep) 0.65 m in front of the armchair
  on the camera side.

## Numbers (strict audit, -slack)
| | before (shipped copy, R1) | R1: 7 s / 6 s | R2: 12 s / 12 s | file now: 2 s / 20 s |
|---|---|---|---|---|
| Normal | 0 defects; exit 44.8 s, waiting 9.9 s (24 %), 4 pauses (2 on the way), longest 5.3 s, max slack 0.5 s | no schedule + Mamie and Lea never cross | 3 defects: never cross; 14.6 s loitering at (1.25, 5.75); longest pause 6.8 > 6.0. Exit 60.4 s, waiting 32 %, 5 pauses, max slack 1.4 s | not audited |
| Difficile | 0 defects; exit 44.8 s, 24 %, 4 pauses, longest 5.6 s, max slack 0.5 s | same 2 defects | 2 defects: never cross; same loitering | not audited |
- Lessons in R2: split binds (platform and ramps barred: no schedule); requires sit binds (first sit 0.6 s).
- R2 diagnosis: the schedule waits in the bedroom for the whole bathroom dwell and crosses the bathroom once Mamie has
  gone into the sejour; her sejour dwell is what lets the player reach the ramp. Hence the untested 2 s / 20 s: a short
  bathroom stop (the 14.6 s wait should fall under 8 s) and a long sejour stop (time to reach the mezzanine, and more
  chances to share the sejour with Lea).
- "Never cross" (new defect): in the shipped level Mamie and Lea only shared the sejour at t = 1 s (both start there).
  Mamie now starts in the bedroom; Lea only visits the sejour at her short s4 stop (12.75, 6.75, 1 s). The longer sejour
  dwell may or may not overlap one of her visits within 300 s.
  Fallbacks if it does not: a different Lea "seed", or a longer Lea s4 dwell (s4 stands beside the east part of the
  route, so audit it).

## Rush (not run, reasoning only)
- (c) straight path at t = 0: Mamie stands at the seat front facing -z, right on the way to the bathroom door: the rush
  drives into her cone, caught.
- (a) waits removed: the route can only be written by a passing audit; Mamie walks ahead through the bathroom, so a rush
  that catches up with her is seen when she turns at door B (facing +x) or on her walk north.

## A VERIFIER
- Run the audit: `-auditLevels level14 -skipFixtures -difficulty normal,difficile -writeRoutes -slack`. Expected
  remaining risks: "Mamie et Lea ne se croisent jamais", loitering or pause over 6 s at the bathroom door.
- Routes are stale until that audit passes: Step45c and Step64b replay the OLD route from the old spawn.
- Step45c checks the first sit by 10 s (it is at 0.6 s here) and that Mamie pins the armchair.
- Step45h: the rewritten control (shelf moved in front of the armchair) was never run.
- DoorwayTests and PlantPlacementTests were reasoned only; Dressing_ tests touch level14's bathroom (washbasin unmoved).
- Variants and the backup are in the scratchpad (l14start/orig_level14.json = the shipped file).
- Logs: Build/l14start_r1.log, Build/l14start_r2.log (R3 never started: stopped while waiting for the Unity lock).
