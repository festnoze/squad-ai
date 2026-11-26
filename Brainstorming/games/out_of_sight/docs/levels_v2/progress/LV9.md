# LV9 progress (level17, The Whole House, act 2 exam)

## State at resume (attempt 2, 2026-11-20 ~15:20)
- No progress file existed; level17.json untouched in git. Attempt 1 left variants l17_a..p (Build/levels_v2/variants),
  scratch scripts lv9_gen.py / lv9_ray.py / lv9_maps.py / lv9_run.ps1 (scratchpad) and two audit runs:
  r1 (l17_a..d, normal,difficile) and r2 (l17_e..h, normal). r3 (l17_m..p) never started (editor busy).
- Audit runs used so far: 2 of 6.
- C9 (loaded sit) passed: TestResults/C9_play.xml, 2/2 green -> Mamie's sit on the loaded chair (s1) stays.

## Diagnosis of r1/r2 (all 8 variants: no schedule)
- The strict search dies after 81 nodes: the chair spawns on Mamie's seat, is pinned 2.1-5.7 s, and Mamie
  (granny, hears a hop within 2.0 x 0.6 + 0.25 = 1.45 m) stays by the seat until about 8 s, then walks away slowly.
  The 8 s wait cap (anchor set at t = 0 on the spawn) expires before the chair can move 1 m away unheard.
- The relaxed diagnostics (no wait cap) found exits at 127-298 s only: the bridge crossing also needs Lea at s2
  (12.75, 5.25 facing 90) + Rex asleep + the robot's hum in its north half at the same time. With Lea s0 dwell 12,
  Lea reaches s2 at about 27.5 s, which makes the exit about 38 s and the waiting share about 0.5 (too high).
- BuffetBas ray check (lv9_ray.py): lane x 6.25 from z 6.75 to 4.25 is hidden from Rex (crossings 0.42-0.81 m);
  (6.75, 4.25) on the ramp foot is partly visible, so the chair waits at (6.25, 4.25).

## Plan (attempt 2)
- Mamie s0 dwell 2.0 -> 0.5 and s1 (sit) dwell 2.5 -> 1.5 (pin about 0.6-3.2 s) so the chair can leave the seat
  before the 8 s cap. Lea s0 dwell 12 -> 4 (glance offset 4 -> 1) so Lea reaches s2 at about 19.5 s; Rex start 1
  (nap first), awake 12.4-13.4 so his second nap starts about when Lea reaches s2; robot start 0.
- Generator: scratchpad lv9b_gen.py (source = Build/levels_v2/variants/l17v1_base.json, a copy of the v1 file).
- Cuisine floor ivorytile (base subwaytile/tile repeats level18's cuisine: palette rule 4.4).

## Runs
- r4 (Build/LV9_r4.log, levels_v2/LV9_r4.json; normal): the Mamie fix works (schedules found, all 5 requires
  bind, pet included; budgets 116 dc / 30 mat; no dead room). a (lea4, A12.4, r0): exit 33.0, share 18 %, 4 pauses,
  longest 3.7, slack 3. b (A12.9): 33.0 / 19 % / 4 / slack 4. c (A13.4): 33.0 / 21 % / slack 4 + loiter 8.5 s in the
  chambre (fail). d (A12.4, robot 1): 31.9 / 18 % / 4 / slack 5. e (lea5, A13.4): 33.0 / 21 % / slack 5 + loiter fail.
  f (s1 sit dwell kept 2.5): no schedule (confirms the spawn diagnosis; the sit must stay short).
  Defects common to all: "Mamie et Hugo ne se croisent jamais" (separation rule: every human pair must share a room
  once in 300 s; closest 2.25 m at 293.7 s) and the pace gate (share < 22 %, 4 pauses < 5).
- Findings: travel 24.8 s (20 careful legs absorb the timing slack, so few pauses); the chambre exit is gated by Hugo
  in the couloir until about 13 s; the crossing follows immediately (bridge about 20.6-24.2 s in a).
- Fix idea: shift Lea (s0 dwell) and Rex (awake) later by 2-5 s so the chair waits at the ramp foot and near Lea;
  Mamie s3/s4 dwells varied per variant for the separation rule (they do not touch the chair's first 37 s).
- r5 (Build/LV9_r5.log, LV9_r5.json; normal). Separation passes with Mamie s4 14 (g, l) or 8 (n); fails with s4 32 (i);
  s4 >= 32 also raises the granny habit warning (> 60 s without sitting). Robot start 1 with later shifts (h, j) and
  k, m: no schedule / node cap. g (lea7, A15.4, r0, s4 14): exit 34.9, 26 %, 6 pauses, slack 4, ONLY defect = chambre
  loiter 10.4 s (> 8). i (lea8): 36.2 / 28 % / slack 3, loiter 11.4. l (lea9, r1, s3 12, s4 14): 37.5 / 30 % /
  6 pauses / slack 6, loiter 12.4. n (lea6, A14.4, s4 8): 33.6 / 24 % / 5 pauses / slack 6, loiter 9.4.
- KEY FINDING: every extra second of slack goes to the chambre (the found schedule idles there before Hugo frees the
  couloir about 12 s), so the loiter rule (8 s motionless within 1.5 m, pinned time included) caps the chambre stay at
  about 11.5 s, i.e. the a-timing (lea4, A12.4). Pauses must be forced AFTER the chambre: the only downstream gate is
  the robot hum near Lea after the dog-timed bridge, so r6 sweeps the robot phase with a 3-point loop (same motion,
  same path: [(11.25, y0), 3.0, 1.5] or [(11.25, y0), 1.5, 3.0]; knob robotPhase in lv9b_gen.py).
- r6 (Build/LV9_r6.log, LV9_r6.json; normal,difficile): robot phase does NOT create pauses (careful legs absorb
  it). a-timing variants p1/p2/p5/p7: Normal 31.6-32.1 s, 18-20 %, 4 pauses, slack 5-8, loiter 7.4-7.9 (ok);
  Difficile: chambre loiter 8.5-8.6 s FAILS even at the a-timing (ranges +15 % push the couloir gate later).
  Phases 5.0, 6.25 (p3, p4, p6, p8): no schedule.
- CONCLUSION: the chambre loiter is structural (the pinned 2.6 s + Mamie's slow departure 3.7 s + the idle before
  the couloir gate all fall inside one 1.5 m disc, because the spawn is 2.3 m from the couloir door).
  Fix: move the spawn (and Mamie's sit) to the chambre's SW corner (0.75, 5.75), 4.3 m from the couloir door, so the
  spawn wait and the idle near the door are two separate stays. Knobs spawnX/spawnZ in lv9b_gen.py.
- r7 (Build/LV9_r7.log, 6th and last tuning run): l17w_w1..w8 (SW spawn): NO schedule in any variant. Diagnostic: a
  schedule exists without noise only. The bed blocks the north side, so the chair must hop east along z 6.25 within
  Mamie's 1.45 m hearing while she opens porte_bureau (6.5-7.2 s), and the 8 s cap expires first. SW spawn rejected.

## STATUS: BLOCKED after the 6-run cap (escalated in the LV9 report). Assets/Resources/Levels/level17.json NOT changed
(still v1). Best candidate: Build/levels_v2/variants/l17w_g.json (Mamie s0 0.5 / s1 1.5 / s4 14, Lea s0 7 glance
offset 1, Rex start 1 awake 15.4 nap 6, robot start 0, BuffetBas, palette, rev 1, requires, pace):
Normal exit 34.9, share 26 %, 6 pauses (5 mid), longest 3.7, slack 4, all 5 requires bind, 0 dead rooms,
116 dc / 30 mat; only defect = chambre loiter 10.4 s, of which 2.6 s are pinned under Mamie. Difficile not measured.

## Exact next step for a fresh agent
1. Ask the audit owner (C5) / PO: should samples pinned under a sitter count in the loiter rule (LevelAudit.cs
   LongestLoiter, around line 4418)? Section 1.3 already excludes pinned time from the waiting share. Without the
   pinned 2.6 s, l17w_g's loiter is 7.8 s (passes), n's 6.8 s.
2. If yes (after that code lands): audit l17w_g and l17w_n normal,difficile (one run); pick the passing one with slack
   4-5; copy to Assets level17.json; run -writeRoutes; run again to confirm replay; then PlayMode Step57b +
   ProbeTestsLoadedSit.
3. If no: the spec fallback is to drop Mamie's sit (s0/s1) so nothing pins the chair at the spawn, then retune
   (Lea s0 / Rex awake shifted together, robot start 0) in a new run budget.
