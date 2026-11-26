# LV2 progress (level3, level4)

## level4 - DONE except confirm replay run
- JSON: rev 1, pace {0.25, 0.45, 2, 6.0}, exact mirror applied, salon floorFinish removed. Routes written by -writeRoutes (run 10:41, Build/LV2_audit_w.log).
- Measured (Normal / Difficile): 0 defects; exit 14.9 / 14.9; waiting 4.9 s (33 %); 2 pauses 0.0-3.2 and 11.7-13.4 (mirror of the original exactly, numbers.md row 4: 14.9, 33 %, [[0.0,3.2],[11.7,1.7]]); slack 8 / 7 samples; careful required ("lecon careful ... le mode prudent est requis"); pace in target.
- Audit runs used on level4: 3 (04:53, ~05:57, 10:41).
- Next: confirm run without -writeRoutes (no "route perimee").

## level3 - IN PROGRESS
- JSON: rev 1, requires ["decoy"], pace {0.35, 0.52, 2, 6.0}, decoys[4] at (0.77, 0.25) yaw 0. Route not yet rewritten.
- Measured with (0.77, 0.25): 1 defect both difficulties: no decoy schedule; diagnostic "un horaire existe sans bruit" (stops (-0.25,0.25) 7.9 s, (0.25,0.25) 8.6 s). Cause (analysis): decoy box blocks cell (0.75,0.25); leaving (0.25,0.25) needs (0.25,0.75), 2.12 m from station 0 (-1.75,1.45) < 2.25 m hearing radius, on hard floor.
- Audit runs used on level3: 3 (04:53, ~05:57, 10:41).
- Spec fallback 2 (decoy (0.75, -0.30)) is invalid: decoy_cells.py reports 0 explained walkable cells, (0.75, 0.25) is a wall cell (capsule 0.28 crosses x 0.95). Fallback 1 (0.76) only applies to a validator rejection, which did not happen.
- Fix tried (deviation, owner file only): keep decoy (0.77, 0.25), move station 0 west so (0.25,0.75) and (0.25,1.25) are beyond 2.25 m. Variants in Build/levels_v2/variants: level3_s210 (x -2.1), level3_s225 (x -2.25), level3_s210f170 (x -2.1, facing 170).
- Note: the ~05:57 run never ran (project open elsewhere), so level3 audit runs before 14:20 = 2.
- Run 3 for level3 (Build/LV2_a4.log, 14:25): level4 confirm replay OK (same numbers, no "route perimee"): level4 DONE.
  s210: 2 defects (exit 63.9, loiter); s210f170: 2 defects; s225 (x -2.25): 0 defects both difficulties, exit 20.2, waiting 9.0 s (45 %), 2 pauses 0.0-3.5 and 8.6-13.8 (rest 5.2 s at (0.25,0.25)), explained 17 (N) / 18 (D), no walk-segment warning, BUT slack 3 / 3 (target 8-12).
- Run 4 for level3 (Build/LV2_a5.log): s225 dwell 5.0 / 5.5 / 6.0 and x -2.4 dwell 5.0: slack N 8/11/13/11, D 7/9/9/11, exit 20.2, BUT all 2 defects: decoys no longer needed ("requires decoy : ne contraint pas"). Longer window lets a decoy-free route exist.
- Assets level3.json now = s225 (station 0 x -2.25, dwell 4.0), the only 0-defect config so far (slack 3/3).
- Run 5 for level3 (Build/LV2_a6.log): Assets level3 with -writeRoutes + variants s225d45, s240d45, s250d45 (writeRoutes also writes into those variant files under Build, harmless). Pick the best 0-defect one; copy to Assets with its routes; run 6 = confirm replay.
  Result: Assets level3 (s225 d40) 0 defects N and D, routes WRITTEN (19 points each), slack 3/3, exit 20.2, 45 %, rest 5.2 s, explained 17/18, decoy required. Variants d45 (x -2.25/-2.4/-2.5): slack N 6/9/9, D 6/9/9, but decoys not needed (2 defects). Decoy necessity breaks as soon as station 0's window grows by 0.5 s: slack 8 and "decoy required" conflict in this geometry.
- Run 6 for level3 (Build/LV2_a7.log): confirm replay of Assets level3 (no -writeRoutes) + 2 exploratory variants for the escalation (rugA: s225 d40 + silent 1x1 m rug at (0.5, 1.0) on the doorway lane; rugB: same rug, station 0 back at x -1.75). After that: cap reached, escalate.
  Result: Assets level3 replays (no "differe"/"perimee" note), 0 defects N and D, same numbers as run 5. rugA: decoys not needed (slack 7/5). rugB: decoys not needed + pause 6.9 s. Both rejected.
- STATE: level3 shipped as s225 d40 with written routes. All targets met except slack 3 (N, target 8-12) and 3 (D, target >= 4). 6 audit runs used: ESCALATED in the task report. No further runs without a decision.
- Possible next steps for whoever continues: find what the decoy-free route is at dwell 4.5 (needs an audit that prints the decoys-off schedule), then block it (e.g. occluder/glance) and lengthen the station 0 window; or accept slack 3.
