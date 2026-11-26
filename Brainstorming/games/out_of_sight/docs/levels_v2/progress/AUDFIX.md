# AUDFIX progress (LevelAudit targeted fix: rock replay lag after a stop, slack sweep node budget)

## Context
- From LV7 (docs/levels_v2/progress/LV7.md): (1) replay lag 0.11-0.15 s (limit 0.1) on hops that leave a hold in the
  direction they arrived; (2) with -slack the first failing margin search always overflows the 40M per-search cap.

## Diagnosis (code reading, before any run)
- Lag: RockPlan.For measures the start cost (Rock.Start) from an exact rest at the cell centre. The replay
  (KinematicReplay and RouteReplayer alike) releases a waypoint within 0.1 m and the rocking chair stops on the release
  step (no glide), so after a stop it rests up to ReleaseTolerance (0.1 m) short of the cell centre, along the arrival
  direction. Leaving in that same direction adds up to 0.1 m at top speed 1.2 m/s = 0.083 s (5 of 6 units) that the
  plan does not count; the search keeps its believed lag under one sample, so the real lag reaches up to ~0.18 s.
  A turned departure adds ~0.01 s, a reversal saves 0.08 s (the leads LV7 saw). Rock.Start = 5.17 samples today.
- Budget: SlackReport runs margins Margin+1.. until no schedule; the first failing margin search is not cut by the
  reachability relaxation (it fails on the wait rule) and overflows Tuning.AuditSearchNodeCap or AuditNodeCap; the
  Budget flags then make the level fail although its own searches stayed within budget.

## Plan
- Baseline run AUDFIX_r0 (current code, before any edit): level4, level8, level10, level12, level15, level18,
  test_rock, LV7_m; normal + difficile; -slack -strictRooms -skipFixtures; json Build/levels_v2/AUDFIX_r0.json.
- Fix, then run AUDFIX_r1 (same set + all fixtures), then EditMode tests.

## Fix prepared (scratch copy, applied to Assets/Editor/LevelAudit.cs only after r0 has compiled the old code)
- RockPlan.Restart: per turn sequence, the same replay started ReleaseTolerance behind the first centre along the
  first move; first-cell cost max over sequences. RockStep uses Restart when the node rests after a move
  (n.Moves > 0, arrived -1), Start only before any move (spawn). Note "bascule" prints the restart cost at its end
  (numbers.py regex kept). Marker // MUTATION:AUDIT_ROCK_RESTART (rest pose -> Vector3.zero restores the old model).
- SlackReport: a margin search that sets Budget.NodesExhausted stops the sweep; flags restored; note says
  "au moins" + which cap overflowed at which margin. Not a defect.
- r0 queued behind LV9's run (lock).

## Run r0 (Build/AUDFIX_r0.log, Build/levels_v2/AUDFIX_r0.json): baseline, OLD code. Unity runs used: 1.
- level4 N/D: ok, exit 14.9/14.9, slack 8/7. level8 N/D: 1 defect (dead room couloir, pre-existing), exit 18.2, slack 15+.
- level10 N/D: 2 dead-room defects (pre-existing), exit 18.1, rock replay lag 0.03 / lead 0.12, slack 8.
- level12 N/D: ok, exit 24.0, slack 5. level18 N/D: ok, exit 21.7, slack 6.
- level15 (old design) N/D: ok, exit 28.9, lag 0.07 / lead 0.27, slack 5.
- test_rock N/D: "aucun horaire" + dead room sortie (pre-existing, not touched by this fix).
- LV7_m N: exit 27.0, lag 0.13 at (8.25,1.25) DEFECT + 40M per-search cap DEFECT (slack search 6); D: 27.4, lag 0.14, cap.
- Fix applied to Assets/Editor/LevelAudit.cs right after r0 (LV8 took the lock next and compiles it).

## Run r1 (Build/AUDFIX_r1.log, Build/levels_v2/AUDFIX_r1.json): FIXED code, same set + all fixtures. Runs used: 2.
- Compiles (0 error CS). Rock plan: start 5.17, restart after a stop 6.00 samples (was implicitly 5.17).
- Self-test: 35/35 fixtures [ok] (test_m5_audit_fidelity, test_rock included).
- level4, level8, level12, level18 N/D: identical to r0 (exit, waits, slack, nodes, same pre-existing level8 dead room).
- level10 N/D: identical results (exit 18.1, lag 0.03 / lead 0.12, slack 8, same 2 pre-existing dead rooms);
  nodes 16.75M -> 16.42M.
- level15 (old design) N/D: still no defect, exit 28.9 unchanged, 40 -> 38 cell moves, lag 0.07, lead 0.27 -> 0.31.
- test_rock as a level: same 2 defects as r0 (it is a must-fail fixture).
- LV7_m N: NO DEFECT. exit 27.0 -> 27.1, lag 0.13 -> 0.03 (lead 0.19), 4 pauses, longest 3.9 -> 2.3, share 40 -> 31 %;
  slack note "6, au moins ; la recherche a 7 echantillons depasse le budget (plus de 40000000 noeuds crees)".
- LV7_m D: NO DEFECT. exit 27.4 -> 27.5, lag 0.14 -> 0.04, 4 pauses, share 41 -> 32 %, same slack note.
- Exit code 6 = the pre-existing defects above (level8, level10 dead rooms; test_rock).

## EditMode (TestResults/AUDFIX.xml, CoreM5BTests|LevelDataM2Tests|LevelDataM4Tests|LevelDefV2Tests). Runs used: 3.
- 137 run, 132 pass, 5 fail, all in LevelDataM2Tests on manifest/line-up premises (21 levels, level10 out of the play
  order, level1 station 3 dwell, level9 room count): level/manifest tasks (C6 saw 4 of them), not the audit. No
  EditMode test calls LevelAudit code.

## Mutation
- New marker // MUTATION:AUDIT_ROCK_RESTART (RockPlan.For, rest pose). mutation.sh NOT edited: its kill target is
  level15 once LV7 ships LV7_m (r0 is the mutated run: LV7_m fails the replay lag). Proposed row:
  "audit_rock_restart|Assets/Editor/LevelAudit.cs|Vector3 rest = -new Vector3(first.x, 0f, first.y) * ReleaseTolerance; // MUTATION:AUDIT_ROCK_RESTART|Vector3 rest = Vector3.zero; // MUTATION:AUDIT_ROCK_RESTART|Audit|level15"
- Existing markers untouched.

## DONE. Next for LV7: copy LV7_m to level15.json, -auditLevels level15 -writeRoutes, PlayMode Step64b_Level15Hard.
