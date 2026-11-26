# LV8 progress (level13 Wheels and a Vase, level14 The Mezzanine)

## State at resume (attempt 3, 2026-11-20 ~15:30)
- No progress file existed. Owner files level13.json / level14.json untouched (no git diff).
- Earlier attempts left scratchpad lv8_variants.py (variants under Build/levels_v2/variants/level13_* / level14_*),
  lv8_maps.py (reads -debugSamples maps) and 4 audit runs (each on both levels): LV8_audit1, LV8_a2, LV8_a3, LV8_a4
  (LV8_a5 never ran). Runs used: 4 of 6 per level.
- level13 findings: spec design (Max to the front desk) = "Max et Claire ne se croisent jamais" defect, 10.5 s spawn
  loiter, decoys not necessary (a2, all 3 variants). Claire extra plateau stop (s2): 244 s mess. Max coffee kept with
  Max st0 dwell 8 (cof/cofb/cofc): 52.6 s, loiter 19 s, share 48 %: a 1 s shorter Max dwell misses the tail of Max.
  HEAD level13 (C5_spot.json, current audit): PASS 26.2 s, share 31 %, 2 pauses (1 mid), longest 6.4 s (spawn);
  Difficile 36.6 s, 30 %, 5 pauses, longest 5.7.
- level14 findings: every variant "aucun horaire" (wip, d6, A..E). Cause (a4 debugSamples, lv8_maps.py): Mamie pins
  the player 3.1-6.7 s and stands until ~10 s, second sit at 56.3 s (Mamie dwells 6/6; 68.3 s with 12/12); Lea's
  wander (5 stations, seed order checked with lv8_seeds.py = RoutinePatterns.WanderNext) leaves no window to descend
  ramp E and cross the couloir between ~25 s and the second sit. Without the sits the route takes ~30 s (B: 32.5 s).

## Plan (attempt 3)
- level14: Lea seed 30 = order 4 (sejour) -> 1 (kitchen door watch) -> 3 (couloir) -> 0 (cuisine, 24 s). Door watch
  dwell d1 holds the player on the top's south half, couloir dwell d3 holds him at the couloir door, then she leaves
  for the cuisine and he crosses. Model: exit ~ 4 + d1 + 3 + d3 + 13.6. Grid d1 16/18/20 x d3 9/11, Mamie 6/6
  (second sit 56.3 s), requires ["sit"] (binds by construction: no exit before 3.1 s).
- level13: start from HEAD inhabitants (cofe) + rev/pace/vias/tile floors; knobs to split the 6.4 s spawn pause and add
  pauses: Claire st0 dwell 3.5/3.0, Max st0 glance toward the door/decoy lane.

## Run 5 (launched, Build/LV8_r5.log, Build/levels_v2/LV8_r5.json): variants LV8_14a..f, LV8_13a..f
- Built by scratchpad lv8_variants.py (level13_r5 / level14_r5). 14a-c d1 16/18/20 d3 9; 14d-f same d1, d3 11.
  13a cofe (HEAD inhabitants + v2 head + tile floors), 13b Claire st0 3.5, 13c/13d Max st0 glance (5.0|6.5, +80, 1.5),
  13e Claire 3.5 + glance 6.0, 13f Claire 3.5 + Claire st1 facing 180 dwell 5.
- Next: summarize with scratchpad lv8_sum.py; pick per level; run 6 = last knob run.

## Run 5 results (Build/LV8_r5.log)
- level14 a..f: still "aucun horaire" N and D. Diagnostic of 14a: without the wait cap the exit is 45.4 s (my model
  T1 + d3 + 13.6 predicted 45.6 s); the blocker is the LOITER rule at the spawn: LongestLoiter counts samples "sat on"
  as idle, and Mamie's spec dwells (station 0 = 3 s, sit 2.5 s, then ~2 s standing beside the seat) keep the armchair
  still ~10 s within 1.5 m (> 8 s). Every earlier level14 variant had the same 3 / 2.5 dwells: that is why all failed.
  requires sit binds (as designed).
- level13 a = b (HEAD numbers: 26.2 s, 31 %, 2 pauses, spawn pause 0-6.4 s then 9.6-11.0 at decoy cell (2.25, 4.75),
  slack 8, vias cafeteria x1.18 / direct x1.00 pass, decoys necessary, 8 explained samples; Difficile 36.6 s 0 defects
  5 pauses longest 5.7 slack 8). Claire st0 dwell 3.5 changes nothing (spawn pause is a tie-break, not Claire).
  c/d/e (Max desk glance +80): 57 s, loiter defects: dead end. f (Claire 3.5 + st1 facing 180 dwell 5): 36.6 s, 40 %,
  3 pauses (6.4 / 1.6 / 5.7 at (5.25, 2.25)), 56 explained samples, slack 8; Difficile 0 defects.
- Run 6 (last knob run) plan: level14 Mamie st0 dwell 0.5, sit 2.0 (deviation from spec 3 / 2.5) with d1 13-15,
  d3 10-12; level13 Max st0 8.0-8.5 with Claire st0 3.0-3.5, Claire start station 2, 13f + Max 8.5.

## Run 6 results (Build/LV8_r6.log, Build/levels_v2/LV8_r6.json) - knob budget now spent (6 runs) on both levels
- level14 Normal (Mamie st0 0.5, sit 2.0): schedules exist. g (d1 13, d3 10): 43.4 s, 21 %, 4 pauses, longest 3.2,
  slack 5, sit at 0.6-3.7 / 50.8 s; only defects loiter 8.8 s (spawn stay: 0.5 still + 3.1 sat on + 3.2 Mamie stand-up
  + a FREE wait at (5.25, 5.25)) and share 21 %. h (13, 12): 45.4 s, 25 %, loiter 8.8 only. i (15, 10): free wait 4.0.
  j (15, 12, Mamie 7/7): 47.4 s, 28 %, second sit 52.8 s. Free early wait = d1 - 11.0 s exactly (g/i/k/l).
  Pinned 3.1 s, release at 6.8 s whatever the sit dwell.
- level14 Difficile: all "aucun horaire": the player cannot leave the seat until ~19 s (no-sit Difficile exits 43.4 s,
  having passed z 4.9 before Lea reached her door watch at 4.0 s). Cause (geometry): Difficile view range 11.5 m
  (Tuning.HardViewRangeFactor 1.15) lets Lea at (16.25, 6.75) see the rug lane (5.25-5.75, 4.9-5.5) through the
  kitchen door (10.5-11.1 m), below the Etagere's shadow (z 5.6-8.0).
- level13 r6 (Max st0 8.0/8.5, Claire start 2, combos): all worse (50-66 s, loiter or share > 45 %). ESCALATE level13:
  no candidate meets the pace gate (best = LV8_13a = HEAD + v2 head: only defect 2 pauses / 6.4 s spawn pause; or
  LV8_13f: 3 pauses). Assets level13.json left UNCHANGED (adding the pace field would turn a passing level into a
  failing one).
- level14 final candidate (extrapolated, written to Assets for the -writeRoutes run, which only writes passing levels):
  d1 11.9 (free wait 0.9 s: pause kept, loiter 7.7 s), d3 14 (share ~26 %, exit ~46.3), Mamie 0.5 / 2.0 / 8 / 8
  (second sit ~54.8 s), Etagere lengthened 2.4 -> 3.6 m (z 4.4-8.0, centre z 6.2) to shadow the rug lane from the door
  watch at Difficile range.

## Run W (Build/LV8_w.log, -writeRoutes on Assets level14 = d1 11.9, d3 14, Mamie 8/8, long Etagere)
- Difficile: 0 DEFECTS (Etagere fix confirmed): exit 46.3, 26 %, 4 pauses, slack 5; designerRouteHard written.
- Normal: exit 46.3, 26 %, 4 pauses (0.5 / 3.2 / 0.9 free wait / 6.8 top), slack 5, loiter 7.7 s (model exact), second
  sit 54.8 s; ONE defect: top pause 6.8 s > 6.0 (the extra couloir dwell moved onto the top: top pause = 2.8 + d3 - 10).
- Fix: d3 12.5, Mamie 7/7 (second sit ~52.8 s) -> predicted exit 44.8, top pause 5.3, share ~23.7 %.
  Generator now reads scratchpad level14_HEAD.json (git HEAD copy), not the Assets file.
- Run W2 launched (Build/LV8_w2.log, Build/levels_v2/LV8_w2.json, -writeRoutes). Next: confirm run without -writeRoutes.

## Run W2 (Build/LV8_w2.log): level14 0 DEFECTS Normal and Difficile; designerRoute + designerRouteHard written (37 pts)
## Run C (Build/LV8_c.log, Build/levels_v2/LV8_c.json): routes replay (no "differe" note), 0 defects N and D.
- level14 final (N = D): exit 44.8 s, share 24 %, 4 pauses (3 mid: 3.2 post-pin, 0.9, 5.3 on the mezzanine top),
  longest 5.3 (D 5.6), pinned 3.1, slack 5, margin 0.3/0.3, loiter 7.7 s (max 8), second sit 52.8 s (8.0 s after the
  exit), 9 route points on the top (x 8-10), split binds, requires sit binds, no dead room, 96 draw calls / 26 mat.
- Deviations: Mamie dwells 0.5 / 2.0 (sit) / 7 / 7 instead of 3 / 2.5 / 12 / 12 (8 s loiter limit counts the pin);
  Lea seed 30 + 5th station (sejour start (12.75, 6.75)), door watch at (16.25, 6.75) dwell 11.9, couloir dwell 12.5;
  Etagere 2.4 -> 3.6 m (z 4.4-8.0); cuisine limewash / tile (base). requires ["sit"] binds trivially (first sit 0.6 s).
- Test premises to recheck (T1): ProbeTestsM5Levels.Step45c_Level14Routes (first sit now 0.6 s, routes rewritten),
  Step45h start-view (Etagere lengthened), any test reading Mamie/Lea stations or the mezzanine/ramp coordinates.
## STATE: level14 DONE. level13 ESCALATED (Assets file unchanged; best variants LV8_13a / LV8_13f).
