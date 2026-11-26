# Out of Sight: current measured numbers, 24 levels

Source: one LevelAudit run, made through `tools/unity.ps1` (`-auditLevels level1..level24 -skipFixtures -difficulty normal,difficile`, no `-writeRoutes`). Log: `Build/numbers.log`, 20 Nov 2026, finished 02:03, exit 0, 25 min of audit time. 48 results (24 levels x 2 difficulties), **0 defects**. The level files are clean in git (HEAD 0edb14b20). The Normal results are identical to `Build/backdrop_audit.log` (19 Nov, 23:52). So the furniture rotations, wall finishes and garden backdrop changed no schedule, no exit time and no room on any route.

Raw data per level and difficulty: `numbers.json` (same folder). Scripts: `numbers.py` (measures) and `render_md.py` (tables).

## Key findings

1. **Every structural figure in the review is confirmed.** All 24 levels match on room count, area, number of watchers and floor off the route. Also confirmed:
   - 84 of the 108 rooms use `#B07A4E` floor on `#EDE6DA` wall.
   - The exit lies mostly east of the spawn in 22 of 24 levels (6 is mostly north, 19 is due south).
   - In levels 19 to 24, 40% of the floor is off the route and 12 of the 44 rooms are entered by nobody.
   - Levels 20 to 24 have 2 closed doors each, and an inhabitant opens one of them.
   - From 18 on, 6 of 7 levels have a wardrobe (21 has none) and the stool is the body in 5 of 7.
   - Levels 19, 21, 23 and 24 have a 0.6 m platform.
2. **Exit times match once the convention is aligned.** The review read the last `at` in the route, which is the departure of the last run. The audit's exit is the arrival on the doormat, 0.3 to 1.8 s later. With the review's convention, every exit except the rocking chair's is within 0.6 s of the review. Rocking chair levels: 10 exits at 18.1 s (review estimate 15) and 15 at 28.9 s (review 27).
3. **The review overstates waiting for the slow bodies.** The audit charges each body its own cost per 0.5 m cell:
   - chair 0.4 s, stool 0.5 s, armchair 0.6 s, lamp 0.9 s, office chair 0.3 s plus a 0.4 s glide at each stop.
   - **Lamp levels 6 and 16 are walked without a single stop** (0.3 s of waiting; the review says 6 s and 12 s). Level 20 waits 2.5 s (review: 7). In level 6, waypoints leave every 1.8 s for 2 cells (0.6, 2.4, 4.2, 5.1, 6.9 ...), which is exactly the lamp's travel time.
   - Other gaps: level 3 waits 9.0 s, not 14 (3.5 s at spawn, then 5.5 s at the table). Level 5 waits 7.1 s, not 11. Level 7: 10.7, not 13. Level 17: 0.9, not 5. Level 18: 10.0, not 15.
   - The "almost no pause" group is therefore 6, 9, 11, 12, 16, 17, 20, 21 and 24. Each spends 5% of the run waiting or less.
4. **Only one level meets the review's rule "wait often, never long" at Normal: 22.** The rule is 25 to 40% of the run spent waiting, 3 or more pauses, none above 6 s.
   - Level 13 does **not** meet it at Normal: 2 pauses, 6.4 s at spawn and 1.4 s mid-route. It meets it at Difficile (5 pauses, 30%, longest 5.7 s).
   - Level 19 meets it only at Difficile.
   - In 10 of 24 levels the longest pause is the wait at spawn (1, 2, 4, 7, 8, 10, 13, 15, 18, 23). Five levels have no pause of 0.5 s or more at all: 6, 9, 11, 12 and 16.
5. **Difficile changes the puzzle in only 4 levels:** 13 (+10.4 s), 19 (+7.5 s), 20 (+1.9 s) and 22 (+18.5 s, 6 pauses, 5 hides). Levels 1 (+0.4 s) and 24 (+0.5 s) barely change. The other 18 levels keep the same exit time at both difficulties, and the same schedule wherever both routes are current.
6. **The robot is not inert, which contradicts the review on 9 and 17.**
   - Level 9: the hum check binds (with the hum switched off, no schedule exists). The hum masks 27 samples (2.7 s) of the player's moves, nearest pass 1.0 m at 5.7 s.
   - Level 15: 38 samples masked.
   - Level 17: 7 samples masked and the hum check binds, so the robot is not "bypassed".
   - Level 24: the hum masks nothing, but the robot binds by contact (the schedule computed without it hits it at 31.2 s).
   - Level 21 also has a robot, which the review does not mention: nearest pass 2.0 m, 0 samples masked.
7. **Lesson checks that do not bind:**
   - Level 10: rock. The level carries the advisory waiver; the audit prints "the stops constrain nothing".
   - Level 17: pet. A schedule exists even with the dog's eye at 1.6 m, so the dog plays no role there.
   - Every other lesson check binds. In level 12 the pet check binds even though the dog's stations are 2.4 m from the route, so some low cover is needed (the review calls the sofa cover optional).
   - In 14 and 17 the platform check binds, but the route only crosses the platform's 1 m width: 2 cells on top and 8 ramp cells.
8. **Decoys matter little in 13.** The audit warns that all 4 decoys of level 13 explain nothing for the 0.5 m tolerance class: they sit at x = 2.84 and 5.84, off the cell centres. Only 8 samples (0.8 s) of its Normal schedule rely on a decoy, against 30 in level 3 and 24 in level 7.
9. **Budget headroom is thin late in the game.**
   - Level 16 uses 24 of 24 materials: the cap of its small tier, with nothing left.
   - Level 8: 23/24. Levels 22 and 23: 31/32. Levels 17 and 21: 29/32.
   - Draw calls peak at 150/160 (21) and 145/160 (22).
   - Any retune that adds props or colours to these levels needs a budget check.
10. **Stale routes:** in levels 15 and 18 the Normal `designerRoute` in the file differs from the current schedule (audit note). Their Normal pause figures come from the stale route. The Difficile routes are current and reach the same exit times:
    - 15: 10.1 s waiting, pauses 5.9 s and 4.2 s.
    - 18: 10.0 s waiting, hide at 13.6 s for 3.8 s.

## Smaller corrections to the review text

- Level 15: the mid-route park lasts 4.2 s (current Difficile route) to 5.8 s (stale Normal route), not about 8 s.
- Level 21 has 7 bookshelves, 6 of them tall (1.8 m or more), plus one low cabinet, rather than "seven tall cabinets".
- The margin of "15+" for level 16 comes from docs/m7/design.md and cannot be checked in this run: the audit computes the maximum margin only for levels 1 to 7 unless `-slack` is passed.
  - Level 16's schedule tolerates a shift of 0.4 s early / 1.0 s late at Normal and 0.4 s / 0.4 s at Difficile.
  - That is tighter than level 6 (0.4 s / 1.4 s, maximum margin 1.5 s or more).
- Level 6 really is the widest of levels 1 to 7 (maximum margin 1.5 s or more, like 1 and 2). Its station 0 is at (4.0, -0.25), 5.2 m from the route, outside the 4 m dark range, as the review says.
- The wall and floor look is wider than the colours say: 70 of the 108 rooms set a `floorFinish` and 101 set a `wallFinish` (11 wall finishes in use). The review counted `floorColor` and `wallColor` only. Whether the finishes read as different houses at play distance is a visual question that these numbers cannot answer.
- Warnings (not defects):
  - Start-delay sweep in 1, 2, 3, 5 and 7: some start moments of the loop force a wait over 8 s, for example level 5 at 2-3 s and 22-32 s of a 40.8 s loop.
  - Advisory waiver on 10.
  - Habit warnings in 13, 17, 21, 22 and 23. Examples: Kevin (hurried) dwells 11.3 s on average, Alfred 23.0 s; Mamie in 17 goes 120 s without sitting.

## How the numbers are computed

- **Exit**: the audit's `horaire : sortie a X s` (arrival on the exit cell).
- **Wait**: exit minus travel time.
  - Travel time = the audit's cell moves x the body's audit cell cost, plus 4 samples per office chair glide stop and 3 per lamp toggle. Vase levels count their careful legs at their own cost (7 samples for the chair, 4 for the office chair, from the log).
  - Opening a door, entering or leaving a wardrobe, and time hidden all count as waiting. Hidden time is also listed on its own.
  - This matches the replay of the file route to 0.1 s on every current route except 21 (0.4 s).
  - For the rocking chair (10, 15), wait comes from replaying the route with the audit's printed rock costs: start 5, straight 4, turn 5 samples, plus 9 samples of rocking per stop (counted as motion). These are estimates.
- **Pauses**: standing intervals of 0.5 s or more when the file route is replayed. A waypoint's `at` is the departure of the run of 2 straight cells or fewer that ends at it. "Mid-route" excludes the wait at spawn.
- **Audit longest wait**: the audit's own measure, which counts small moves inside its 1 m wait anchor. It is therefore always at least as long as the longest pure pause.
- **Margin early/late**: how far the whole found schedule can shift and stay valid. **Max margin**: the audit's `marge maximale` (levels 1 to 7 only; "+" means 15 samples or more).
- **Rooms on route**: rooms holding a `*`, `S` or `E` cell on the audit map of the current schedule. This agrees with the file route replay everywhere, and Normal and Difficile visit the same rooms in every level.
- **Nobody enters**: off-route rooms with no inhabitant station, no robot loop, and no crossing by an inhabitant's shortest doorway-to-doorway walk between consecutive stations.
  - Loop, pingpong and wander orders are respected.
  - A closed leaf blocks that walk unless `openedByInhabitants` is set.
  - The robot counts as a visitor (it only matters in 9, 15, 17, 21 and 24, and changes no "nobody" verdict).
- **Fixed watchers**: an inhabitant at a single position, or one station holding 85% or more of the cycle with a dwell of 60 s or more. Includes the dog in 12 (two stations at one spot) and in 24 (one station, 600 s).
- **Nearest station to route**: straight distance, walls ignored, from each station to the nearest cell of the file route.


## Table 1. Normal: measured now (LevelAudit run of 20 Nov 2026, designerRoute for the pauses)

| Lvl | Body | Rooms route/all | Nobody enters | Area m2 | Watchers | Closed doors (inhab. opens) | Wardrobes | Exit s | Wait s (share) | Pauses >=0.5 s | Longest pause s | Audit longest wait s | Margin early/late s | Max margin s | Off route % | Draw calls | Materials | Defects |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | chair | 1/1 | - | 48 | 1 | 0 (0) | 0 | 10.7 | 1.9 (18%) | 1 | 1.9 | 2.7 | 0.3/3.0 | 1.5+ | 0 | 39/120 | 19/24 | none |
| 2 | chair | 2/2 | - | 40 | 1 | 0 (0) | 0 | 13.3 | 4.1 (31%) | 1 | 4.1 | 4.9 | 0.3/2.9 | 1.5+ | 0 | 58/120 | 18/24 | none |
| 3 | chair | 2/2 | - | 48 | 1 | 0 (0) | 0 | 18.6 | 9.0 (48%) | 2 | 5.5 | 6.3 | 0.3/0.3 | 0.9 | 0 | 64/120 | 17/24 | none |
| 4 | stool | 2/2 | - | 36 | 1 | 0 (0) | 0 | 14.9 | 4.9 (33%) | 2 | 3.2 | 4.2 | 0.3/0.3 | 0.8 | 0 | 50/120 | 21/24 | none |
| 5 | armchair | 1/1 | - | 40 | 1 | 0 (0) | 0 | 16.1 | 7.1 (44%) | 2 | 5.3 | 6.5 | 0.3/0.3 | 1.0 | 0 | 49/120 | 20/24 | none |
| 6 | lamp | 2/2 | - | 52 | 1 | 0 (0) | 0 | 15.9 | 0.3 (2%) | 0 | 0.3 | 2.4 | 0.4/1.4 | 1.5+ | 0 | 52/120 | 21/24 | none |
| 7 | office chair | 1/1 | - | 50 | 1 | 0 (0) | 0 | 20.3 | 10.7 (53%) | 2 | 6.4 | 7.8 | 0.3/0.3 | 1.0 | 0 | 51/120 | 18/24 | none |
| 8 | chair | 3/4 | couloir | 76 | 1 | 2 (0) | 0 | 18.2 | 6.6 (36%) | 2 | 6.0 | 6.8 | 0.3/3.0 | - | 10 | 69/120 | 23/24 | none |
| 9 | chair | 3/4 | cuisine | 114 | 1 (1 fixed) | 0 (0) | 0 | 12.3 | 0.3 (2%) | 0 | 0.3 | 1.1 | 0.4/2.6 | - | 17 | 83/120 | 18/24 | none |
| 10 | rocker | 2/5 | chambre, couloir | 110 | 1 | 0 (0) | 0 | 18.1 | 6.6 (36%) | 1 | 6.6 | 7.6 | 0.3/3.0 | - | 49 | 70/160 | 24/32 | none |
| 11 | chair + vase | 3/4 | - | 84 | 1 | 0 (0) | 0 | 15.5 | 0.3 (2%) | 0 | 0.3 | 1.1 | 0.4/3.0 | - | 35 | 77/120 | 21/24 | none |
| 12 | stool | 4/5 | - | 102 | 1+dog (1 fixed) | 0 (0) | 0 | 14.3 | 0.3 (2%) | 0 | 0.3 | 1.3 | 0.4/3.0 | - | 23 | 84/160 | 20/32 | none |
| 13 | office chair + vase | 3/5 | - | 112 | 2 | 0 (0) | 0 | 26.2 | 8.2 (31%) | 2 | 6.4 | 7.2 | 0.3/0.3 | - | 22 | 104/160 | 28/32 | none |
| 14 | armchair | 3/6 | - | 127 | 2 | 0 (0) | 0 | 27.0 | 3.6 (13%) | 2 | 2.5 | 3.7 | 0.3/0.3 | - | 35 | 95/160 | 26/32 | none |
| 15 | rocker | 3/6 | - | 116 | 2 (1 fixed) | 0 (0) | 0 | 28.9 | 12.2 (42%) | 2 (stale) | 6.3 (stale) | 6.8 | 0.3/0.3 | - | 42 | 86/160 | 23/32 | none |
| 16 | lamp | 3/4 | - | 90 | 2+dog | 1 (0) | 0 | 27.6 | 0.3 (1%) | 0 | 0.3 | 2.4 | 0.4/1.0 | - | 22 | 82/120 | 24/24 | none |
| 17 | chair + vase | 4/6 | - | 156 | 3+dog | 2 (0) | 0 | 21.2 | 0.9 (4%) | 1 | 0.6 | 1.4 | 0.4/3.0 | - | 26 | 112/160 | 29/32 | none |
| 18 | stool | 3/4 | - | 32 | 1 (1 fixed) | 1 (1) | 1 | 21.5 | 10.0 (47%) | 2 (stale) | 5.4 (stale) | 6.6 | 0.3/0.3 | - | 28 | 60/120 | 16/24 | none |
| 19 | stool | 4/6 | cuisine, sdb | 208 | 2 (1 fixed) | 0 (0) | 4 | 57.7 | 10.2 (18%) | 4 | 3.5 | 4.5 | 0.3/0.3 | - | 31 | 125/160 | 25/32 | none |
| 20 | lamp | 4/7 | bureau, sdb | 199 | 2+dog (1 fixed) | 2 (1) | 3 | 55.3 | 2.5 (5%) | 1 | 2.2 | 7.2 | 0.3/0.3 | - | 39 | 126/160 | 24/32 | none |
| 21 | office chair | 3/7 | reunion, couloir, archives | 192 | 3 (2 fixed) | 2 (1) | 0 | 19.0 | 0.9 (5%) | 1 | 1.0 | 1.6 | 0.4/3.0 | - | 34 | 150/160 | 29/32 | none |
| 22 | stool | 4/8 | boudoir, office | 205 | 3 | 2 (1) | 4 | 50.1 | 15.6 (31%) | 4 | 5.8 | 6.8 | 0.3/0.3 | - | 62 | 145/160 | 31/32 | none |
| 23 | stool | 4/7 | bureau | 192 | 2+dog (1 fixed) | 2 (1) | 3 | 43.9 | 9.9 (23%) | 3 | 5.0 | 6.0 | 0.3/0.3 | - | 38 | 132/160 | 31/32 | none |
| 24 | stool | 5/9 | chambre_enfants, sdb | 234 | 3+dog (1 fixed) | 2 (1) | 3 | 40.4 | 0.9 (2%) | 1 | 0.6 | 1.6 | 0.4/1.1 | - | 37 | 144/160 | 28/32 | none |

## Table 2. Difficile: measured now (designerRouteHard for the pauses)

| Lvl | Exit s | Wait s (share) | Pauses >=0.5 s | Longest pause s | Audit longest wait s | Margin early/late s | Rooms on route | Off route % | Hides (s hidden) | Doors opened | Defects | vs Normal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 11.1 | 2.3 (21%) | 1 | 2.3 | 3.1 | 0.3/3.0 | 1/1 | 0 | 0 (0.0) | 0 | none / new warning: start-delay sweep: an 8 s+ wait is forced when starting at 29, 30, 31 s of a 38.8 s loop | +0.4 s |
| 2 | 13.3 | 4.1 (31%) | 1 | 4.1 | 4.9 | 0.3/2.9 | 2/2 | 0 | 0 (0.0) | 0 | none | same schedule |
| 3 | 18.6 | 9.0 (48%) | 2 | 5.5 | 6.3 | 0.3/0.3 | 2/2 | 0 | 0 (0.0) | 0 | none | same schedule |
| 4 | 14.9 | 4.9 (33%) | 2 | 3.2 | 4.2 | 0.3/0.3 | 2/2 | 0 | 0 (0.0) | 0 | none | same schedule |
| 5 | 16.1 | 7.1 (44%) | 2 | 5.3 | 6.5 | 0.3/0.3 | 1/1 | 0 | 0 (0.0) | 0 | none / new warning: start-delay sweep: an 8 s+ wait is forced when starting at 2, 3, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33 s of a 40.8 s loop | same schedule |
| 6 | 15.9 | 0.3 (2%) | 0 | 0.3 | 2.4 | 0.4/0.8 | 2/2 | 0 | 0 (0.0) | 0 | none | same schedule |
| 7 | 20.3 | 10.7 (53%) | 2 | 6.4 | 7.8 | 0.3/0.3 | 1/1 | 0 | 0 (0.0) | 0 | none | same schedule |
| 8 | 18.2 | 6.6 (36%) | 2 | 6.0 | 6.8 | 0.3/3.0 | 3/4 | 10 | 0 (0.0) | 1 | none | same schedule |
| 9 | 12.3 | 0.3 (2%) | 0 | 0.3 | 1.1 | 0.4/2.6 | 3/4 | 17 | 0 (0.0) | 0 | none | same schedule |
| 10 | 18.1 | 6.6 (36%) | 1 | 6.6 | 7.6 | 0.3/3.0 | 2/5 | 49 | 0 (0.0) | 0 | none | same schedule |
| 11 | 15.5 | 0.3 (2%) | 0 | 0.3 | 1.1 | 0.4/3.0 | 3/4 | 35 | 0 (0.0) | 0 | none | same schedule |
| 12 | 14.3 | 0.3 (2%) | 0 | 0.3 | 1.3 | 0.4/3.0 | 4/5 | 23 | 0 (0.0) | 0 | none | same schedule |
| 13 | 36.6 | 11.0 (30%) | 5 | 5.7 | 6.9 | 0.3/0.3 | 3/5 | 22 | 0 (0.0) | 0 | none | +10.4 s |
| 14 | 27.0 | 3.6 (13%) | 2 | 2.5 | 3.7 | 0.3/0.3 | 3/6 | 35 | 0 (0.0) | 0 | none | same schedule |
| 15 | 28.9 | 10.1 (35%) | 2 | 5.9 | 6.8 | 0.3/0.3 | 3/6 | 42 | 0 (0.0) | 0 | none | +0.0 s |
| 16 | 27.6 | 0.3 (1%) | 0 | 0.3 | 2.4 | 0.4/0.4 | 3/4 | 22 | 0 (0.0) | 0 | none | same schedule |
| 17 | 21.2 | 0.9 (4%) | 1 | 0.6 | 1.4 | 0.4/2.7 | 4/6 | 26 | 0 (0.0) | 1 | none | same schedule |
| 18 | 21.5 | 10.0 (47%) | 2 | 5.6 | 6.6 | 0.3/0.3 | 3/4 | 28 | 1 (3.8) | 0 | none | same schedule |
| 19 | 65.2 | 17.7 (27%) | 5 | 5.9 | 6.9 | 0.3/0.3 | 4/6 | 31 | 3 (9.2) | 0 | none | +7.5 s |
| 20 | 57.2 | 5.0 (9%) | 3 | 2.7 | 6.9 | 0.3/0.3 | 4/7 | 39 | 0 (0.0) | 0 | none | +1.9 s |
| 21 | 19.0 | 0.9 (5%) | 1 | 1.0 | 1.6 | 0.4/3.0 | 3/7 | 34 | 0 (0.0) | 1 | none | same schedule |
| 22 | 68.6 | 27.1 (40%) | 6 | 7.0 | 8.0 | 0.3/0.3 | 4/8 | 62 | 5 (13.8) | 0 | none | +18.5 s |
| 23 | 43.9 | 9.9 (23%) | 3 | 5.0 | 6.0 | 0.3/0.3 | 4/7 | 38 | 1 (3.7) | 1 | none | same schedule |
| 24 | 40.9 | 1.4 (3%) | 2 | 0.8 | 1.8 | 0.3/0.6 | 5/9 | 37 | 0 (0.0) | 1 | none | +0.5 s |

## Table 3. The review's table against the current numbers (Normal)

Review exit = the last departure written in the route (the review read the files); measured exit = the audit's arrival on the exit. Flags: E exit differs by more than 1.5 s from the review once the last-departure convention is applied, W waiting differs by more than 2 s, O off-route floor differs by more than 5 points, S rooms/area/watchers differ.

| Lvl | Review exit / wait / off % | Now: last departure / exit / wait / off % | Review rooms, area, watchers | Now | Flags |
|---|---|---|---|---|---|
| 1 | 10 / 2 / 0 | 10.3 / 10.7 / 1.9 / 0 | 1, 48, 1 | 1, 48, 1 | ok |
| 2 | 12 / 4 / 0 | 12.5 / 13.3 / 4.1 / 0 | 2, 40, 1 | 2, 40, 1 | ok |
| 3 | 18 / 14 / 0 | 18.2 / 18.6 / 9.0 / 0 | 2, 48, 1 | 2, 48, 1 | W |
| 4 | 14 / 5 / 0 | 14.4 / 14.9 / 4.9 / 0 | 2, 36, 1 | 2, 36, 1 | ok |
| 5 | 16 / 11 / 0 | 15.5 / 16.1 / 7.1 / 0 | 1, 40, 1 | 1, 40, 1 | W |
| 6 | 14 / 6 / 0 | 14.1 / 15.9 / 0.3 / 0 | 2, 52, 1 | 2, 52, 1 | W |
| 7 | 20 / 13 / 0 | 20.0 / 20.3 / 10.7 / 0 | 1, 50, 1 | 1, 50, 1 | W |
| 8 | 17 / 7 / 10 | 17.4 / 18.2 / 6.6 / 10 | 4, 76, 1 | 4, 76, 1 | ok |
| 9 | 12 / 1 / 17 | 11.9 / 12.3 / 0.3 / 17 | 4, 114, 1 | 4, 114, 1 | ok |
| 10 | 15* / 7 / 49 | n/a (rocker) / 18.1 / 6.6 / 49 | 5, 110, 1 | 5, 110, 1 | E |
| 11 | 15 / 2 / 35 | 14.8 / 15.5 / 0.3 / 35 | 4, 84, 1 | 4, 84, 1 | ok |
| 12 | 14 / 1 / 23 | 13.8 / 14.3 / 0.3 / 23 | 5, 102, 1+dog | 5, 102, 1+dog | ok |
| 13 | 25 / 10 / 22 | 25.4 / 26.2 / 8.2 / 22 | 5, 112, 2 | 5, 112, 2 | ok |
| 14 | 26 / 4 / 35 | 26.4 / 27.0 / 3.6 / 35 | 6, 127, 2 | 6, 127, 2 | ok |
| 15 | 27* / 16 / 42 | n/a (rocker) (stale) / 28.9 / 12.2 / 42 | 6, 116, 2 | 6, 116, 2 | W |
| 16 | 26 / 12 / 22 | 25.8 / 27.6 / 0.3 / 22 | 4, 90, 2+dog | 4, 90, 2+dog | W |
| 17 | 20 / 5 / 26 | 20.4 / 21.2 / 0.9 / 26 | 6, 156, 3+dog | 6, 156, 3+dog | W |
| 18 | 21 / 15 / 28 | 20.7 (stale) / 21.5 / 10.0 / 28 | 4, 32, 1 | 4, 32, 1 | W |
| 19 | 57 / 11 / 31 | 57.2 / 57.7 / 10.2 / 31 | 6, 208, 2 | 6, 208, 2 | ok |
| 20 | 54 / 7 / 39 | 54.4 / 55.3 / 2.5 / 39 | 7, 199, 2+dog | 7, 199, 2+dog | W |
| 21 | 19 / 2 / 34 | 18.7 / 19.0 / 0.9 / 34 | 7, 192, 3 | 7, 192, 3 | ok |
| 22 | 49 / 15 / 62 | 49.1 / 50.1 / 15.6 / 62 | 8, 205, 3 | 8, 205, 3 | ok |
| 23 | 43 / 10 / 38 | 43.4 / 43.9 / 9.9 / 38 | 7, 192, 2+dog | 7, 192, 2+dog | ok |
| 24 | 40 / 1 / 37 | 39.9 / 40.4 / 0.9 / 37 | 9, 234, 3+dog | 9, 234, 3+dog | ok |

## Table 4. Per level details (Normal)

| Lvl | Lesson checks (audit counterfactuals) | Route m (crow m) | Exit dir | Pause list [start s, length s] | Hides [at, s] | Nearest station to route, m (per watcher, per station) | Fixed watchers | Decoy samples | Robot nearest m | Default palette rooms | Audit warnings (not defects) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | - | 11.0 (8.1) | NE | [[0.0, 1.9]] | - | Habitant: [1.2, 0.4, 2.3, 2.5] | - | 0 | - | 1/1 | start-delay sweep: an 8 s+ wait is forced when starting at 29, 30 s of a 38.8 s loop |
| 2 | - | 11.5 (8.8) | NE | [[0.0, 4.1]] | - | Habitant: [0.6, 0.6, 0.1] | - | 0 | - | 2/2 | start-delay sweep: an 8 s+ wait is forced when starting at 26, 27 s of a 30.8 s loop |
| 3 | - | 12.1 (7.8) | E | [[0.0, 3.5], [7.9, 5.5]] | - | Habitant: [0.2, 1.2, 0.5, 1.4] | - | 30 | - | 1/2 | start-delay sweep: an 8 s+ wait is forced when starting at 7, 8, 9, 10, 11, 12 s of a 43.2 s loop |
| 4 | careful -> required | 10.1 (8.1) | E | [[0.0, 3.2], [11.7, 1.7]] | - | Habitant: [2.0, 1.5] | - | 0 | - | 2/2 | - |
| 5 | sit -> required | 7.5 (3.7) | NE | [[0.0, 1.8], [5.4, 5.3]] | - | Habitant: [1.0, 0.5, 4.4, 2.8] | - | 0 | - | 1/1 | start-delay sweep: an 8 s+ wait is forced when starting at 2, 3, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32 s of a 40.8 s loop |
| 6 | dark -> required; dark alone not enough, timing needed | 8.6 (6.7) | NE | [] | - | Habitant: [5.2, 5.2, 1.2] | - | 0 | - | 1/2 | - |
| 7 | glide -> required | 12.0 (8.9) | E | [[0.0, 6.4], [12.4, 4.3]] | - | Habitant: [0.2, 1.3] | - | 24 | - | 1/1 | start-delay sweep: an 8 s+ wait is forced when starting at 11, 12, 13, 14, 15 s of a 18.3 s loop |
| 8 | door -> required | 14.5 (7.5) | SE | [[0.0, 6.0], [8.4, 0.6]] | - | Paul: [0.5, 3.5, 0.8] | - | 0 | - | 3/4 | - |
| 9 | robot -> required (hum) | 15.0 (11.5) | E | [] | - | Claire: [1.5, 1.5]; Robot loop points: [1.0, 1.0] | Claire [2 glances] | 0 | 1.0 | 3/4 | - |
| 10 | rock (advisory waiver) | 13.5 (9.9) | SE | [[0.0, 6.6]] | - | Mamie: [2.8, 6.7, 0.1, 0.2] | - | 0 | - | 3/5 | lesson advisory waiver: rock stops constrain nothing |
| 11 | load -> required | 17.5 (10.1) | SE | [] | - | Lea: [3.5, 0.7, 0.0, 2.1] | - | 0 | - | 3/4 | - |
| 12 | pet -> required | 14.0 (8.0) | E | [] | - | Paul: [4.4, 1.0, 3.2, 4.7]; Rex: [2.4, 2.4] | Rex (dog) [0 glances] | 0 | - | 4/5 | - |
| 13 | load -> required | 20.0 (13.0) | SE | [[0.0, 6.4], [9.6, 1.4]] | - | Max: [0.2, 4.0]; Claire: [1.1, 3.6, 3.5] | - | 8 | - | 4/5 | decoy 1 explains nothing (off cell centres, 0.5 m tolerance); decoy 2 explains nothing (off cell centres, 0.5 m tolerance); decoy 3 explains nothing (off cell centres, 0.5 m tolerance); decoy 4 explains nothing (off cell centres, 0.5 m tolerance); habit Max (hurried): mean dwell 5.5 s (habit wants <= 2 s) |
| 14 | split -> required | 19.5 (12.5) | SE | [[0.0, 1.1], [4.7, 2.5]] | - | Mamie: [0.5, 0.5, 3.5, 3.5]; Lea: [3.5, 2.5, 2.0, 0.5] | - | 0 | - | 5/6 | - |
| 15 | robot -> required (hum) | 17.0 (11.8) | E | [[0.0, 6.3], [16.1, 5.8]] | - | Claire: [1.0, 1.0]; Hugo: [3.0, 2.8, 2.0, 6.7]; Robot loop points: [1.0, 0.7] | Claire [2 glances] | 0 | 1.0 | 5/6 | - |
| 16 | dark -> required; dark alone not enough, timing needed | 15.0 (8.1) | SE | [] | - | Claire: [3.5, 4.7, 3.6]; Max: [3.5, 4.2, 1.5]; Rex: [1.8, 0.7] | - | 0 | - | 3/4 | - |
| 17 | final -> door: required; pet: NOT required; split: required; robot: required (hum); load: required | 23.5 (16.0) | E | [[15.9, 0.6]] | - | Mamie: [1.7, 3.4, 3.6, 5.3]; Hugo: [4.6, 4.0, 1.2]; Lea: [1.9, 1.8, 1.0]; Rex: [2.0, 1.5]; Robot loop points: [1.7, 1.2] | - | 0 | 1.5 | 6/6 | habit Mamie (granny): 120 s without sitting (habit <= 60 s) |
| 18 | wardrobe -> required | 11.7 (6.5) | NE | [[0.0, 5.4], [13.4, 4.8]] | [[13.4, 4.0]] | Odile: [4.4, 2.5] | Odile [34 glances every 9.0 s, hold 5.0 s, yaw -80.0] | 0 | - | 3/4 | - |
| 19 | wardrobe -> required | 47.5 (9.5) | S | [[0.0, 0.8], [12.3, 2.5], [38.8, 3.5], [46.3, 3.4]] | [[38.8, 2.9], [46.3, 2.8]] | Maman: [0.5, 2.1]; Papa: [1.2, 1.2] | Maman [42 glances every 7.5 s, hold 4.5 s, yaw -80.0] | 0 | - | 4/6 | - |
| 20 | dark -> required; dark alone not enough, timing needed | 26.5 (11.0) | E | [[41.4, 2.2]] | - | Maman: [4.9, 5.4]; Papa: [4.5, 2.5]; Rex: [2.2, 1.0] | Maman [58 glances every 5.5 s, hold 1.5 s, yaw 80.0] | 0 | - | 5/7 | - |
| 21 | split -> required | 29.5 (20.1) | E | [[13.8, 1.0]] | - | Bertrand: [3.0]; Sofia: [3.5]; Kevin: [0.1, 5.3, 5.1]; Robot loop points: [2.0, 2.0] | Bertrand [65 glances every 4.5 s, hold 2.5 s, yaw 80.0], Sofia [64 glances every 4.5 s, hold 2.5 s, yaw -80.0] | 0 | 2.0 | 6/7 | habit Kevin (hurried): mean dwell 11.3 s (habit wants <= 2 s) |
| 22 | wardrobe -> required | 34.5 (24.3) | E | [[0.0, 3.2], [20.2, 5.5], [30.2, 1.1], [36.8, 5.8]] | [[20.2, 3.7], [24.5, 0.0], [25.1, 0.0], [36.8, 5.2]] | Comtesse: [0.2, 2.2]; Alfred: [0.6, 0.0]; Mamie: [4.9, 2.2, 4.8, 0.0] | - | 0 | - | 6/8 | habit Alfred (hurried): mean dwell 23.0 s (habit wants <= 2 s); habit Comtesse (watchful): station 1 waits 3,0 s without a glance; habit Comtesse (watchful): station 2 waits 5,0 s without a glance; habit Mamie (granny): 60 s without sitting (habit <= 60 s) |
| 23 | wardrobe -> required | 34.0 (19.3) | E | [[0.0, 5.0], [8.0, 0.6], [30.1, 4.3]] | [[30.1, 3.7]] | Odile: [1.6]; Hugo: [0.5, 3.4]; Rex: [3.7, 2.0] | Odile [40 glances every 10.0 s, hold 6.0 s, yaw -80.0] | 0 | - | 5/7 | habit Hugo (teen): a glance of 30 deg or more |
| 24 | final -> door: required; pet: required; split: required; robot: required (contact) | 39.5 (20.8) | SE | [[3.3, 0.6]] | - | Rex: [3.5]; Lea: [0.5, 4.8]; Theo: [5.0, 2.5]; Mamie: [4.9, 5.5]; Robot loop points: [0.5, 1.0] | Rex (dog) [0 glances] | 0 | 1.0 | 7/9 | - |

## Table 5. The review's rule "wait often, never long" (25 to 40 % waiting, 3+ pauses, none above 6 s), and the named obstacle on the route

| Lvl | Normal: share / pauses (mid-route) / longest / meets | Difficile: share / pauses (mid-route) / longest / meets | Route cells on the platform | Robot: nearest m, moves masked by its hum (samples) |
|---|---|---|---|---|
| 1 | 18% / 1 (0) / 1.9 / no | 21% / 1 (0) / 2.3 / no | - | - |
| 2 | 31% / 1 (0) / 4.1 / no | 31% / 1 (0) / 4.1 / no | - | - |
| 3 | 48% / 2 (1) / 5.5 / no | 48% / 2 (1) / 5.5 / no | - | - |
| 4 | 33% / 2 (1) / 3.2 / no | 33% / 2 (1) / 3.2 / no | - | - |
| 5 | 44% / 2 (1) / 5.3 / no | 44% / 2 (1) / 5.3 / no | - | - |
| 6 | 2% / 0 (0) / 0.3 / no | 2% / 0 (0) / 0.3 / no | - | - |
| 7 | 53% / 2 (1) / 6.4 / no | 53% / 2 (1) / 6.4 / no | - | - |
| 8 | 36% / 2 (1) / 6.0 / no | 36% / 2 (1) / 6.0 / no | - | - |
| 9 | 2% / 0 (0) / 0.3 / no | 2% / 0 (0) / 0.3 / no | - | 1.0, 27 |
| 10 | 36% / 1 (0) / 6.6 / no | 36% / 1 (0) / 6.6 / no | - | - |
| 11 | 2% / 0 (0) / 0.3 / no | 2% / 0 (0) / 0.3 / no | - | - |
| 12 | 2% / 0 (0) / 0.3 / no | 2% / 0 (0) / 0.3 / no | - | - |
| 13 | 31% / 2 (1) / 6.4 / no | 30% / 5 (5) / 5.7 / yes | - | - |
| 14 | 13% / 2 (1) / 2.5 / no | 13% / 2 (1) / 2.5 / no | Mezzanine: 2 | - |
| 15 | 42% / 2 (1) / 6.3 / no (stale route) | 35% / 2 (1) / 5.9 / no | - | 1.0, 38 |
| 16 | 1% / 0 (0) / 0.3 / no | 1% / 0 (0) / 0.3 / no | - | - |
| 17 | 4% / 1 (1) / 0.6 / no | 4% / 1 (1) / 0.6 / no | Mezzanine: 2 | 1.5, 7 |
| 18 | 47% / 2 (1) / 5.4 / no (stale route) | 47% / 2 (1) / 5.6 / no | - | - |
| 19 | 18% / 4 (3) / 3.5 / no | 27% / 5 (4) / 5.9 / yes | Mezzanine: 22 | - |
| 20 | 5% / 1 (1) / 2.2 / no | 9% / 3 (2) / 2.7 / no | - | - |
| 21 | 5% / 1 (1) / 1.0 / no | 5% / 1 (1) / 1.0 / no | Passerelle: 13 | 2.0, 0 |
| 22 | 31% / 4 (3) / 5.8 / yes | 40% / 6 (5) / 7.0 / no | - | - |
| 23 | 23% / 3 (2) / 5.0 / no | 23% / 3 (2) / 5.0 / no | Mezzanine: 9 | - |
| 24 | 2% / 1 (1) / 0.6 / no | 3% / 2 (1) / 0.8 / no | Mezzanine: 9 | 1.0, 0 |

