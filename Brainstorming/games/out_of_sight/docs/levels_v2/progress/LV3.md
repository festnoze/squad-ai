# LV3 progress (levels 5 and 6)

## State at resume (attempt 3, 2026-11-20 ~11:40)
- Owner files level5.json / level6.json: still HEAD (untouched).
- Variants in Build/levels_v2/variants: level5_wip (spec: sit 1.5, TV 6.5, rev 1, pace), level6_wip (spec: st0 (2.0,0.6) f270
  dwell 10, glances +40@3/-40@7, chambre arches, no floorFinish, rev 1, pace), level6_k1 (dwell 9.5), level6_k2 (spawn -3.25,-3.85),
  level5_s10 (st0 5.5, sit 1.0), level5_s12n (st0 z 1.25 dwell 5.5, sit 1.2), level6_d16/d17 (wip with dwell 16/17), level5_c (wip, sit 1.0).
- Run r1 (Build/LV3_r1.log, levels_v2/LV3_r1.json), audit runs used: level5 1, level6 1:
  - level5_wip: DEFECT loiter 8.1 s > 8 (pinned 2.7 counts in the loiter rule); exit 17.1, share 38 %, 3 pauses, slack 5.
  - level6_wip/k1: share 4 % < 12 %, exit 15.9, 0 mid pauses (watcher leaves st0 at 10 s before the lamp reaches the
    boundary at ~12.6 s). k2: exit 13.2, same. Dark boundary = column x -2.25 (4.25 m from st0) vs x -1.75 (in range).
  - Reasoning: exit ~ max(12.6, D + 0.5) + 2.7 -> D 16-17 gives exit 19-20 and a 4-5 s boundary pause.

## Run r2 (Build/LV3_r2.log, LV3_r2.json) - audit runs used: level5 2, level6 2
- level5_c (spec but sit dwell 1.0): 0 defects N+D, exit 16.6/16.6, share 37.5 %, 3 pauses (1.8 spawn, 3.0, 0.6 home),
  pinned 2.2, loiter 7.6 s (<= 8), slack 8. level5_s12n: pass, exit 16.8, pinned 2.4, slack 9, loiter 7.9 (fragile).
  CHOSEN level5_c (sit 1.5 breaks the loiter rule, which counts pinned time).
- level6_d16: 0 defects N+D, exit 19.0 / 20.8 Dif, share 19.5 %, 1 pause 3.7 s AT THE SPAWN (0 mid), slack 15.
  level6_d17: exit 20.0 / 21.8, spawn pause 4.7 / 6.2 Dif. CHOSEN d16.
- Mid-route boundary pause NOT achievable by data knobs: the search's Pareto front (run near anchor) always moves waits
  to the earliest point (spawn); nothing threatens the bedroom path, so the wait never lands at the boundary.
- Copied level5_c -> level5.json, level6_d16 -> level6.json (14:4x). Next: -writeRoutes run on level5,level6, then confirm run.

## Run w (Build/LV3_w.log) - routes written (level5 11/11 pts, level6 12/11 pts, 1 toggle each), numbers identical to r2. Next: confirm run without -writeRoutes (Build/LV3_c.log).

## Run c (Build/LV3_c.log): 0 defects N+D, routes replay (no 'differe' note), same numbers as r2. Level files DONE. Next: PlayMode Step35b + Step35 + Step64b 05/06 (TestResults/LV3_play.xml).

## PlayMode (TestResults/LV3_play.xml, 14:38): 4/4 pass (Step35 levels 4-7 routes, Step35b rush, Step64b 05/06 hard). level5 sat on 1, 0 pratfalls; level6 1 toggle, 0 switch-ons. TASK COMPLETE except the mid-route boundary pause (escalated).
