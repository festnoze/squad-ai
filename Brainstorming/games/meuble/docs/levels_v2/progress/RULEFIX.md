# RULEFIX progress (PO decision 2026-11-20: spawn wait and pinned time out of the pace / loitering rules)

## Rule change (Assets/Editor/LevelAudit.cs, docs LEVELS_V2.md 10.3)
- `MaxSpawnWait = 8f`; `SpawnWaitEnd(path)` = the sample the first move starts from (marker // MUTATION:PACE_SPAWN_WAIT).
- Spawn wait = samples before the first move, pinned ones left out. `SpawnWaitFailure`: > 8 s is a defect at every
  difficulty (note "attente au depart : ..."). The search's 8 s / 1 m anchor already bounds it.
- Pace: spawn runs out of `LongestPause` (max-pause rule); still in `Pauses` (minimum count, as 10.1 lists spawn
  pauses) and in the share; `MidPauses` = pauses starting after the first move. Note "minimum de pauses (N) atteint
  grace a l'attente au depart" when the minimum needs the spawn pause(s). JSON: `spawnWait`, `spawnPauses`.
- Loitering: spawn-wait samples and pinned samples are not idle (marker // MUTATION:LOITER_PINNED).
- The search (wait anchor) is NOT changed.

## Fixtures
- test_v2_audit_pace_fail reworked (room 8x4, shelf 2.5 m, spawn (-3.25,-1.25), watcher dwell 11): the long pause
  must now be mid-route (the 4.2 s spawn wait no longer breaks maxPause 2.0).
- New test_v2_audit_pace_spawn (old pace_fail house): strict = old rules fail, relaxed = new rules pass + the spawn
  limit bites on the schedule delayed 8.1 s.
- New test_v2_audit_loiter_pinned (test_sit house): synthetic schedule, hop off the seat and back, 7 s own + pin.
- test_m5_audit_fidget: watcher dwell 13 -> 21 (its 12.5 s loiter started at the spawn).

## Runs
- r1 (Build/RULEFIX_r1.log, levels_v2/RULEFIX_r1.json): all fixtures + level3, level3_s225d45, level6, l17w_g,
  l17w_n, test_v2_audit_pace_pass. Runs used: 1. NOTE: with -auditLevels the fixtures only run when listed in
  -fixtures (none ran in r1).
  - level3 (Assets, s225 d40) N/D: 0 defects, exit 20.2, 45 %, 2 pauses (1 mid), longest mid 5.2, spawn 3.5, slack 3/3.
    level3_s225d45 N/D: slack 6, still "requires decoy : ne contraint pas" (2 defects). The rule change does not touch
    level3: its open issue is slack 3 vs 8-12 (decoy necessity breaks as soon as station 0's window grows).
  - level6 (Assets) N/D: 0 defects, exit 19.0 / 20.8, 19.5 / 26 %, 1 pause = the spawn wait 3.7 / 5.5 s, 0 mid,
    slack 15. Minimum (1) met only by the spawn wait (spec wants 1 mid-route pause).
  - l17w_g N: 0 DEFECTS (34.9 s, 26 %, 6 pauses, 4 mid, longest mid 1.4, pinned 2.6, spawn 4.2, slack 4).
    l17w_n N: 0 defects (33.6 s, 24 %, 5 pauses, 3 mid, slack 6). BUT Difficile: g "aucun horaire" (no single rule
    relaxed gives one) + dead room entree; n: schedule only without the wait cap (223 s). Design issue at Difficile.
  - test_v2_audit_pace_pass as a level N/D: 0 defects (spawn 4.2 s, 0 mid).
- r2 (Build/RULEFIX_r2.log): fixtures (pace_fail, pace_spawn, loiter_pinned, fidget, wait, sit, deadroom, flicker)
  + LV5_l8e, level9, LV8_13a, LV8_13f, level17 round 1 rf17_x1..x4 (lv9b_gen.py: x1 leaS0 5 / rexAwake 13.4 / s4 14,
  x2 5.5 / 13.9 / 14, x3 6 / 14.4 / 14, x4 5 / 13.4 / 8): between the a-timing (Difficile ok, Normal 18 %) and n/g.
  Runs used: 2. Results:
  - FIXTURES 8/8 [ok]: pace_fail (mid pause 3.7 > 2.0), pace_spawn (old rules 4.2 > 2.0; new rules pass, limit bites),
    loiter_pinned (old 18.2 s; new 7 s), fidget (11.7 s after the spawn wait, > 8), wait, sit, deadroom, flicker.
  - LV5_l8e N/D: exit 17.7, 34.5 %, 2 pauses (1 mid), longest mid 0.6, spawn 5.5, slack 15; N defect "2 pauses < 3"
    (unchanged: the pause count is a design issue). D 0 defects.
  - level9 (Assets) N/D: 0 defects, unchanged (19.3 s, 29.5 %, 4 pauses, spawn 3.4, slack 8). No regression.
  - LV8_13a N: 26.2 s, 31 %, 2 pauses (1 mid), longest mid 1.4, spawn 6.4, slack 8, defect "2 < 4"; 13f N: 36.6 s,
    40 %, 3 pauses (2 mid), longest mid 5.7, defect "3 < 4". D both 0 defects (36.6 s, 5 pauses). Design issue.
  - level17 x2 / x3 N: 0 DEFECTS (33.1 / 33.6 s, 22.6 / 23.9 %, 5 pauses, 3 mid, spawn 4.0 / 4.2, slack 6);
    x1 / x4 N: 21 % and 4 pauses. ALL four Difficile: "aucun horaire" (+ requires load / dead room entree fallout).
    Difficile breaks between Lea s0 4 (a-timing, r6: schedules) and 5; Normal needs >= 5.5. Conflict = design issue
    (Difficile view range x1.15 makes the later Lea crossing window unreachable). No further round (credits).
- r3 (Build/RULEFIX_r3.log): lv10_19w, lv10_19ac..aj, lv10_21m, lv10_21l. Runs used: 3. Results:
  - lv10_19ag N: 0 DEFECTS (72.0 s, 35.4 %, 6 pauses, 5 mid, longest mid 6.0 = limit, spawn 2.1, slack 5);
    D: 0 defects (72.0 s, 6 pauses, longest 6.5 (a note at Difficile), spawn 1.6). SHIPPED (exit 72 s above the soft
    46-62 band; route length deviation already reported by LV10).
  - 19w N: 4 pauses < 5 (D passes). 19ac/ad/ah: a mid pause 6.4-7.0 s; ac/ad/ae/af: view-fidelity defect (Papa at
    17.4 s); ae/af/aj: mid-route loiter 8.9-10 s; Difficile loiter at (2.25, 8.25) from 8.4 s (mid-route). 19ai invalid
    (Maman glanceEvery past the dwell).
  - lv10_21m N: 4 pauses < 6, mid pause 6.2 s at (1.25, 7.75), loiter 11.4 s AFTER the spawn wait (6.6 s); D loiter
    13.3 s mid-route. 21l: share 51 %, same 6.2 s pause, view-fidelity defect at D. level21 still failing (design).
- PO instruction (mid-task): no EditMode/PlayMode runs, no separate confirm-replay run, -writeRoutes run with 0 defects
  is enough.
- w19 (Build/RULEFIX_w19.log): flags lost by Start-Process quoting (routes NOT written; audit identical). Runs used: 4.
- w19b (Build/RULEFIX_w19b.log): level19 -writeRoutes: 0 defects N and D, designerRoute + designerRouteHard written
  (58 points each), same numbers as r3. Runs used: 5. level19 DONE.

## Final state
- Shipped: level19 (= lv10_19ag). Unchanged and passing: level3 (slack 3), level6 (min pause only via spawn).
- Still failing (design): level8 (2 pauses < 3), level13 (2-3 pauses < 4), level17 (Difficile no schedule for every
  variant that meets the Normal pace), level21 (4 pauses < 6, 6.2 s mid pause, mid-route loiter).

## A VERIFIER
- EditMode / PlayMode suites not run after the rule change (PO instruction); no EditMode test calls LevelAudit pace/loiter code.
- Full fixture registry not rerun: only 8 fixtures ran (pace_fail, pace_spawn, loiter_pinned, fidget, wait, sit, deadroom, flicker).
- Mutation rows PACE_SPAWN_WAIT / LOITER_PINNED proposed, not run through mutation.sh (I1).
- level19 replay of the written routes not confirmed by a separate run (only the -writeRoutes run).
- level19 test premises (T1): tests reading Papa/Maman stations, the sofa (CanapeSalon z 9.5), TableBasse z 11.0 or the old route.
- Shipped levels with a sit or a long spawn wait (5, 14, 17 v1) not re-audited; the change only relaxes rules, the search is unchanged.
- JSON report gained spawnWait/spawnPauses and midPauses now excludes post-pin spawn pauses: numbers.py / STATUS readers may differ.
