# L13HARD progress (level13 too easy: the straight rush wins)

## The request (2026-11-23)
level13 (LEVELS6 variant L6_13c) is a bit too easy: `ProbeTestsRush.Rush02_NoRushWinsOnAnyListedLevel` fails with
"level13 (c): the rush WON at 6.6 s (path 14.4 m, 4 corners)". Make the level harder so that no rush wins and the
intended route needs real waits, keep LevelAudit at 0 DEFECTS at Normal and Difficile with routes written, and clear
any object standing in a doorway (DOORS rule, level13 was left pending by the DOORS agent).

## Diagnosis
- At the start Max (window desk (1.25, 3.0), 9 s) faces the west window (270) and Claire (direction (3.25, 8.75),
  3.5 s) faces the bookshelf (0): for the first ~9 s nobody looks at the office floor, the corridor or the accueil.
  Both straight lines to the exit (spawn, door 1, office diagonal, door 3, accueil: ~15 m; spawn, door 2, corridor,
  cafeteria, door 5, accueil: ~14.6 m) are unwatched at full speed (the vase falls, but a fall does not lose).
- DOORS offenders (LevelValidator.DoorwayIssues): decoy 3 (2.84, 4.75) in the approach of door 1 (2.25, 5.95) on the
  plateau side; prop Comptoir (12.0, 7.05), west end 0.8 m off door 7 (9.95, 6.75) on the cafeteria side.

## Tools (scratchpad lv6/)
- `gen13h.py <name> [knobs]`: variants of the Assets level13 (doorway fixes always applied unless nodoors=1), written to
  Build/levels_v2/variants/L13H_<name>.json.
- `rush.py <level.json> [N|D] [c|a]`: rough rush estimator on vis.py's static cone model with simulated schedules
  (rush c = string-pulled grid path at 2.18 m/s, the probe's 14.4 m / 6.6 s; POLY env = hand path; a = designerRoute
  with the waits removed, careful legs 1.25 m/s). Caught = seen while moving for 0.2 s.
- `l13run.ps1 <tag> <levels> [WRITE]`: detached-style audit launcher (agent l13), Build/L13H_<tag>.log / .out.txt.

## Runs

### r1 (Build/L13H_r1.log, 10 variants, 00:29-00:45)
- Max s0 turned to face the office (facing 90, 105, 75; with or without Claire changes, dwell 7/11, s1 dwell 2): every
  one has NO schedule at Normal and Difficile (node cap 40M, both via checks dead). Max watching the plateau 9 s out
  of every ~25 s closes the level. Abandoned.
- d0 (doorway fixes only, decoy 3 moved to x 3.05): Normal 3 pauses < 4 (DEFECT): the decoy move alone changes the route.

### r2 (Build/L13H_r2.log, 9 variants, 00:47-00:54)
- Second doorway fix "fix=z": decoy 3 pulled back toward its desk (z 4.75 -> 4.6) and Bureau3 0.05 m south
  (z 4.0 -> 3.95) so they do not overlap. x135 (old x 3.05 fix) keeps the 3-pause defect.
- Claire C0 turned toward the room exits (facing 135 or 150 instead of 0, the bookshelf): z135 / z135n / z135d / z0
  fail "les leurres ne sont pas necessaires"; z135m (+ Max dwell 7) has no schedule at Difficile.
- z150, z150g (facing 150, glance -45 instead of +45), z150d (z150g + dwell 4.5): 0 DEFECTS Normal AND Difficile.

### Shipped: L13H_z150d -> Assets level13.json, write run Build/l13.log (exact task command, exit 0)
- Claire station 0 (3.25, 8.75): facing 0 -> 150 (she faces the two ways out of the direction room: door 1 to the
  plateau and door 2 to the corridor), dwell 3.5 -> 4.5, glance (2.0, +45, 1.0) -> (2.0, -45, 1.0) (a look toward the
  corridor door). Max unchanged.
- Doorways: decoy 3 (2.84, 4.75) -> (2.84, 4.6); Bureau3 z 4.0 -> 3.95; Comptoir x 12.0 -> 12.3 (west end 11.1, clear
  of door 7's 1 m approach). DoorwayTests.Pending emptied (level13 is clear; the test fails while a clear level stays
  listed).
- Audit Normal: 0 DEFECTS, exit 38.6 s, wait 16.2 s (42 %), 4 pauses (3 en route), longest 5.7 s, spawn wait 6.2 s,
  longest loiter 7.1 s, 0 view-fidelity observations, decoys required, designerRoute 27 points written.
- Audit Difficile: 0 DEFECTS, exit 38.6 s, 41 %, 5 pauses (4 en route), longest 5.7 s, designerRouteHard 27 points.
- rush.py estimate: c (both straight lines) caught by Claire at ~0.3 s; a (waits removed) caught at ~0.8 s.

### PlayMode `--filter ProbeTestsRush|Step57b_` (TestResults/l13rush.xml, 00:55-01:00)
- Step57b_Level13VaseDropIsHeard: pass. Rush00 and Rush01: pass.
- Rush02, level13 row: a lost (caught 0.7 s, wp 1/27), b lost (caught 0.8 s), c lost (caught 0.6 s, wp 0/4). No
  level13 rush survives.
- Rush02 still FAILS on other levels: level11 (a) won 12.4 s, level11 (c) won 8.2 s (path 12.7 m), level25 (a) won
  15.5 s. Not level13; level11 had its sofa moved by DOORS today (probably the cause), level25 is not mine.

## A VERIFIER
- level11 (a and c) and level25 (a) rushes win in Rush02: owners to look (level11 likely the DOORS sofa move).
- The difficulty gain is at the start only: Claire now watches both exits of the direction room for her first 4.5 s,
  so the route waits 6.2 s at the spawn instead of rushing. The rest of the route (38.6 s, 4 pauses) is the L6_13c
  schedule. Facing Max toward the office (the stronger change) left no schedule at all.
- No PlayMode replay of the written designerRoute / designerRouteHard (Step45l_Level13Routes, Step64b_Level13Hard)
  was run here: only the -writeRoutes audit.
- DoorwayTests (EditMode) not run after emptying Pending; DOORS can now wire DoorwayIssues into
  LevelValidator.Validate (their A VERIFIER).
- Bureau3 moved 0.05 m south and decoy 3 0.15 m toward it: check the desk and chair look in play.
- Decoy tolerance warnings (decoys 1 to 4 off cell centres at Claire's 0.5 m) carried over from L6_13c, unchanged.
