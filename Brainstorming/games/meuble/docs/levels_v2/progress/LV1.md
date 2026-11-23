# LV1 progress (levels 1 and 2)

## State found at resume (2026-11-20 14:10, from Build/LV1_a1..a4 logs and git diff)
- level2 DONE in Assets: exact mirror + couloir marble + floorColor #D8D4CC + rev 1 + requires [rug] + pace {0.15,0.35,1,6.0};
  routes written by a4 (-writeRoutes, 10:58). Measured (a1/a4, normal = difficile): exit 13.3 s, travel 9.2, share 31 %,
  1 pause (spawn) 4.1 s, slack 15, 31 rug samples within earshot, requires rug binds ("contraint"); mirrored audit equals
  the original (a1: original level2 13.3 / 4.1 / slack 15); no-rug variant has no schedule. Missing: confirm run (a5 was killed).
- level1 in Assets: dwell 3.5 + rev 1, routes written by a4, but pace RELAXED to {maxShare 0.35, maxPause 6.0} by the
  previous attempt. Measured a4: normal exit 9.2, share 4 %, 0 pauses, slack 15; difficile 9.6, 1 pause 0.8 s, slack 15.
- Dwell sweep (a2, normal): 5.0 -> exit 10.7, spawn pause 1.9 s; 4.5 -> 10.2 / 1.4; 4.0 -> 9.7 / 0.9; 3.5 -> 9.2 / 0.
  So the >= 1.5 s pause target and the dwell change pull against each other (pause = dwell - 3.1 roughly).
- Rush probe (C7, PlayMode Rush02): level1 rush (c) NavMesh max speed WON at 5.2 s with dwell 5.0 (09:01) and 4.5 (09:48).
  Not yet measured at 3.5.

## Plan (this attempt)
1. Audit run A: level1, level2 (confirm replay), variants lv1_g35 (dwell 3.5 + over-the-shoulder glance at the window
   station, yaw 80 hold 1.0 offset 0.5) and lv1_g40 (dwell 4.0 + glance offset 0.7 hold 1.2) to get a >= 1.5 s pause.
2. Pick, copy to Assets, -writeRoutes, confirm.
3. PlayMode Rush02_NoRushWinsOnAnyListedLevel|Step20_DesignerRoutes on the final files.

## Log
- b1 (14:2x, audit level1,level2,lv1_g35,lv1_g40; normal = difficile unless noted):
  level2 Assets: 0 defects, exit 13.3, share 30.8 %, 1 spawn pause 4.1 s, slack 15, rug binds, 31 rug samples, NO "differe"
  note -> routes replay. LEVEL2 DONE.
  level1 Assets (3.5, no glance): 9.2 s, 0 pauses (difficile 9.6, 1 x 0.8 s).
  lv1_g35 (3.5 + glance 0.5/80/1.0): 0 defects, exit 12.4, share 29 %, 1 spawn pause 3.6 s, slack 15 (both difficulties).
  lv1_g40 (4.0 + glance 0.7/80/1.2): exit 12.8, share 31 %, pause 4.0 s, slack 15.
- Decision: level1 Assets = dwell 3.5 + window glance {offset 0.3, yaw 80, hold 0.8} (shorter than g35 to bring exit to
  about 12 s) + spec pace {0.12, 0.35, 1, 6.0}. Next: -writeRoutes level1 (b2), confirm (b3), PlayMode Rush02 + Step20.
- b2 (-writeRoutes level1, final data): 0 defects both difficulties, exit 12.0, travel 8.8, share 26.7 %, 1 spawn pause
  3.2 s (longest wait 4.0 s per the schedule line), slack 15, margin 0.3 / 3.0. Routes written (15 points each).
  Late-start sweep warning (info only): 7 failing starts 27-33 s of the 37.3 s loop (was 2, at 28-29 s, before the glance);
  moot with the held start. Next: b3 confirm audit + PlayMode Rush02|Step20 (launched together in one background job).
- b3 confirm audit level1: 0 defects both difficulties, exit 12.0, no "differe" note -> routes replay. LEVEL1 DONE.
- PlayMode (TestResults/LV1_play.xml): Step20_DesignerRoutes PASSED (level1 won 11.6/11.8/12.0 s at -0.2/0/+0.2 s,
  level2 won 13.0/13.2/13.4 s, rug near inhabitant True). Rush02 FAILED only on other levels (6, 9, 11, 15, 13, 17, 19);
  level1 rushes lose: (a) caught 1.3 s, (c) caught 2.0 s (was WON 5.2 s); level2 (a) and (c) caught 0.2 s.
- TASK COMPLETE. Nothing left to run for LV1.
