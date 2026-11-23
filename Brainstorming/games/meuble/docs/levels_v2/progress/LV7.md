# LV7 progress (level15 rebuild, Let Sleeping Dogs Lie)

## State at resume (attempt 3, 2026-11-20 ~15:20)
- Owner file Assets/Resources/Levels/level15.json: still HEAD (untouched).
- Attempt 1 left Build/levels_v2/variants/level15_wip.json (spec base + overrides, rev 1, pace, Mamie granny loop
  3 stations, Rex sleep 3.5 / awake 1.8 at (11.75, 1.25) facing 270). Variants va..vd (Mamie/Rex dwell tweaks) never audited.
- Run a1 (Build/LV7_a1.log, 05:54) on level15_wip, Normal: 3 DEFECTS: 3 pauses (< 4); replayed route reaches (9.75,1.25)
  0.15 s late (rock plan); audit node cap 80M exceeded. Exit 26.5 s, share 36 %, longest pause 4.8 s, margin 0.3/0.3,
  longest wait 7.6 s, rock binds (without rock exit 22.2 s seen at 16.0 s). Audit took 374 s.
- Run a2 (10:38) failed to compile (LevelAudit.cs mid-edit by C6). Audit runs used on level15: 1.

## Analysis (attempt 3)
- Node cap: the 9 searches were main 9.5M, lesson 1.7M, then slack margins 4..10 (~9-13M each); the cap hit inside
  the margin-10 search. Slack 9 > target 5-8: lower slack = fewer slack searches = under the cap.
- Pauses: spawn hold + 2 hall holds (7.25 and 10.25). Rex's effective nap = sleep dwell + 0.6 s wake telegraph
  (Tuning.WakeTelegraph), so a 3.5 s dwell gives a ~4.1 s nap, enough for a 3 m hop (6 straight cells): that long
  straight hop is also what lags the kinematic replay (0.15 s at 9.75). Shorter naps -> shorter hops, one more hold,
  lower slack. Bureau loiter already 7.5 s (max 8): no room for a bureau pause.

## WARNING: DUPLICATE LV7 AGENT COLLISION (15:24-15:29)
- Two LV7 agents ran at once. The other one (Unity wrapper PID 56692) started run r2 at 15:18:28 on its own variants
  Build/levels_v2/variants/LV7_a..LV7_d (their ids were "LV7_a".., their content is NOT recorded here) with
  -logFile Build/LV7_r2.log. The duplicate agent (the one writing this note) did not know, and at 15:24:41 OVERWROTE
  LV7_a..d.json with its own content (id "level15", copy of level15_wip.json with only the Rex block changed:
  a = sleep 2.8 / awake 1.8 at x 11.75; b = sleep 3.0 / awake 1.6 at 11.75; c = sleep 3.5 / awake 1.8 at 11.25;
  d = sleep 3.0 / awake 1.8 at 11.25). The running r2 had already parsed a, b, c (and most likely d, which began
  right after c ended at 15:23:59), so r2's numbers belong to the ORIGINAL variants; the files on disk now do not.
  Regenerate LV7_a..d from your own script before building on them. The duplicate agent then stopped and touched
  nothing else (no Unity run of its own, no edit of level15.json). The analysis section above is its only addition.
- r2 numbers already in the log (original variants): a and c identical: exit 25.3, 33 %, 3 pauses (14.1-16.5 at 6.75,
  19.5-21.8 at 9.25), slack 7, replay lag 0.15 s at (11.75, 1.25), node cap 80M. b: exit 28.9, 45 %, 4 pauses
  (spawn 5.5, 6.25, 8.25, 10.25), slack 6, replay lag 0.15 s at (12.75, 1.25), per-search memory cap 40M (search 6 =
  30.6M nodes).
- Other agent's report (message): rows LV7_a/c = Rex sleep 3.0 at 11.75; LV7_b = sleep 2.8 at 11.75; 4th row (id level15)
  = sleep 3.0 / awake 1.8 at 11.25: exit 25.7, 42 %, 3 pauses, longest 6.1 (> 6.0), slack 7, lag at 11.25, node cap.
- The other agent is stopped (coordinator, 15:30). This agent is now the only LV7. Audit runs used: a1, r2 = 2 of 6.

## Findings after r2
- Replay lag: in every run the late cell is the 5th straight cell after a hold (a1 9.75 from 7.25; b 12.75 from 10.25;
  a/c 11.75 from 9.25; D 11.25). Short hops / a turn before the 5th cell should avoid it. The final hop (no stop
  needed once past Rex) is the long one.
- Node cap: under -slack the failing margin search (slack + 1) is not caught by the relaxation (sight-feasible, it fails
  on the 8 s loiter rule), so it explores to the 300 s horizon with ~145 rock states per cell. Without -slack the old
  level15 used 7M nodes. If it persists this is an audit limit to escalate (not a level-file fix).

## Run r3 (Build/LV7_r3.log, normal + difficile): variants LV7_e..h (from level15_wip.json, script inline)
- e: Rex sleep 2.8 / awake 1.8 at 11.75, exit x 12.75 -> 12.25 (final hop turns earlier)
- f: e + Mamie M0 dwell 3.5 -> 3.0 (shorter spawn hold, exit time)
- g: Rex sleep 2.6 / awake 2.0, exit 12.25
- h: Rex sleep 3.0 / awake 1.8, exit 12.25, Mamie M0 3.0
### r3 results (Build/LV7_r3.log, Build/levels_v2/LV7_r3.json). Runs used: 3 of 6.
- Normal e = f (Mamie M0 3.0 changes nothing): exit 28.4, share 46 % (DEFECT > 45), 4 pauses (5.5 spawn, 6.25, 8.25,
  10.25), slack 6, lag 0.14 at (4.25, 3.25) bureau (final hop now fine), node: failing margin-7 search > 40M created.
- Normal g (2.6/2.0): 28.4, 46 %, 4 pauses, slack 5, same lag. h (3.0/1.8): 24.9, 34 %, 3 pauses, lag hall 11.75.
- Difficile e/f/g: 28.9, 46 % (no pace gate at Difficile), 4 pauses, slack 6/6/5, lag 0.14 at (12.25, 1.25) (final
  hop 9.75 -> 12.25 straight). h: 25.3, 43 %, 3 pauses, longest 6.1.
- Lag hypothesis (fits all runs AND the old level15, whose holds were all entered by a turn or a reversal: lag 0.07,
  lead 0.27): after a stop the replayed chair rests a little short of the cell, so a hop leaving a hold IN THE SAME
  direction it arrived lags ~0.06 s beyond the plan model. Fix: make holds sit at turns (slalom).
- Budget: with -slack the failing margin search always exceeds 40M created (sight-feasible, dies on the 8 s loiter
  rule, so the relaxation does not catch it). Not fixable in the level file: ESCALATE (write/confirm runs will drop
  -slack; slack = last successful margin, 5-6).

## Run r4 (Build/LV7_r4.log, normal + difficile): slalom variants LV7_i..l (from LV7_e via ConvertFrom-Json)
- all: Console deleted; low boxes (0.3 high, under Rex's 0.35 eye) one cell wide: CartonsNord (7.25, 1.65) blocks
  hall row z 1.25 at x 7.25; Console (8.75, 0.3) blocks row 0.75 at 8.75; CartonsEst (10.25, 1.65) blocks row 1.25
  at 10.25; CartonBureau (2.75, 3.25) 0.25 x 0.25 x 0.5 breaks the bureau's straight row. All colour #8C5A36.
- i: sleep 2.8 / awake 1.8, exit 12.25; j: awake 1.5; k: exit 12.75; l: sleep 2.6 / awake 1.8.
### r4 results (Build/LV7_r4.log). Runs used: 4 of 6. SLALOM IS A DEAD END.
- Normal i/j/k/l: exit 32.7 / 30.9 / 33.1 / 31.5, share 43/39/42/41 %, 5 pauses, longest 3.7-4.3, slack 6/6/6/5;
  i, j, k LOITER defect (8.9-9.8 s near (9.25, 0.75)); every one lags 0.12-0.14 at the exit cells (final hop leaves
  the last hold eastward after arriving eastward); leads up to 0.25 s appear after turned holds. Bureau lag gone.
- Difficile i/j/k/l: 33.1 / 31.3 / 33.5 / 32.3, 39-43 %, 5 pauses, lag 0.11-0.15 (l mid-hall 9.75).

## Run r5 (Build/LV7_r5.log, last screening run; normal + difficile): LV7_m..p from LV7_e (no slalom)
- all: CartonBureau box (2.75, 3.25) 0.25 x 0.25 x 0.5 (r4 showed it removes the bureau lag); Console x 10.75 -> 10.65
  (row 0.75 blocked 9.75-11.25); exit moved to (11.75, 0.75) size 0.8 x 0.8, right beside Rex, so the final hop is
  <= 4 straight cells then one turn down into the doormat.
- m: Rex sleep 2.8 / awake 1.6 (share down) at 11.75; n: m with Rex at 11.25; o: awake 1.8; p: sleep 3.0 / awake 1.6.
- Plan: if one variant has no defect but the -slack budget one at both difficulties, copy it to level15.json and run
  r6 = -auditLevels level15 -writeRoutes WITHOUT -slack (the budget defect only comes from the slack report), then
  PlayMode Step64b_Level15Hard as the replay confirmation. Else: escalate, level15.json left unchanged.
### r5 results (Build/LV7_r5.log, Build/levels_v2/LV7_r5.json). Runs used: 5 of 6 (1 kept in reserve).
- m Normal: exit 27.0, share 40 %, 4 pauses (spawn 3.9, 6.25, 8.25, 10.25), longest 3.9, slack 6, margin 0.3/0.3,
  rock binds (rock-off 22.0 s seen rocking at 13.5 s), 4 rocks, no dead room, 66 dc / 23 mat, no habit / walk-line
  warning. Defects: lag 0.13 at (8.25, 1.25) (hop 6.25 -> 8.25, 4 cells, hold to hold eastward) + -slack budget.
- m Difficile: 27.4, 41 %, 4 pauses, longest 4.3, slack 6; same 2 defects (lag 0.14 at 7.75).
- n (Rex 11.25): N 27.4 / 41 % / 4 pauses, D same; o (awake 1.8): N 28.0 / 42 %, D 28.4 / 43 %; p (sleep 3.0):
  3 pauses (pace defect). All keep the lag (0.13-0.15) and the budget defect.

## AUDIT FIX LANDED (docs/levels_v2/progress/AUDFIX.md): restart cost after a stop + slack sweep stops on budget.
- LV7_m.json copied to Assets/Resources/Levels/level15.json (id level15).
- Run 6 (Build/LV7_write.log, Build/levels_v2/LV7_write.json, -writeRoutes, no -slack): 0 defects N and D.
  Normal: exit 27.1, 31 %, 4 pauses (spawn 1.8, 6.25, 8.25, 10.25), longest 2.3, lag 0.03 / lead 0.19, rock binds
  (rock-off 22.1 s seen at 13.5 s), 66 dc / 23 mat. Difficile: 27.5, 32 %, 4 pauses, longest 2.3, lag 0.04.
  designerRoute and designerRouteHard written (19 points each). Slack (AUDFIX run): 6, au moins.
- Audit run cap reached (6): the replay is confirmed by PlayMode (Step64b hard route, Step45m normal route).
- PlayMode (TestResults/LV7.xml): Step64b_Level15Hard PASS (hard route Won at offsets -0.2/0/+0.2 s, 27.0-27.4 s,
  0 discoveries, 0 barks). Step45m_Level15Routes FAILS on its T1 premise "level 15 has its robot" (expected); its
  normal route replay itself Won (26.6 s, 0 discoveries, 0 barks).
- T1 premises broken: LevelDataM2Tests WaveB row level15 (6 rooms, lesson robot -> 4 rooms, rock); ProbeTestsM5Levels
  WaveB row (2 humans + 1 robot -> 1 granny + 1 dog, 0 robot) and Step45m (drop the robot / MaskedNoises premise,
  require Rocks >= 3 and a win); Step45r order; ProbeTestsM9FloorDust shots (re-run only).
## DONE.

## (history) STATE before the fix: ESCALATED
- Best candidate: Build/levels_v2/variants/LV7_m.json (all level targets met except two audit defects).
- Lag: every hop that leaves a hold in the direction it arrived lags 0.11-0.15 s in RockTimingGuard, whatever the hop
  length (4 to 7 cells), nap length, Rex position or slalom. The level's verb IS hopping down a straight hall, so no
  level-file knob removes it. Proposed audit fix (LevelAudit.cs owner): RockPlan.For measures its start cost from an
  exact rest at the cell centre; also measure a restart after a stop (the replay's stop releases 0.1 m early and rests
  short of the centre), or start KinematicReplay's hops from the replayed rest pose.
- Budget: with -slack the failing margin search (slack + 1) creates > 40M nodes (rocking state x 300 s horizon; the
  relaxation does not catch a loiter-rule failure). Proposed: SlackReport stops on an exhausted budget and reports
  "slack >= last success" as a note, not a defect (or a per-search cap for the slack report).
- Next step once the audit is fixed: copy LV7_m.json to Assets/Resources/Levels/level15.json, run
  -auditLevels level15 -writeRoutes (no -slack) = run 6, then PlayMode Step64b_Level15Hard.
