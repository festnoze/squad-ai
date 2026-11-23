# DOORS progress (nothing stands in front of a door)

## The request (product owner, 2026-11-23)
In level11 ("le vase") the sofa partly blocks a door. Clear that doorway, then find and fix the same fault in every
level: furniture, prop or decor whose footprint enters a door's opening or the swing and approach area right in front
of it. level13 and level17 were being reworked by other agents at the time: their offenders are only listed here.

## The rule
- `LevelValidator.DoorwayIssues(LevelDef)` (Assets/Scripts/Core/LevelValidator.cs, with `DoorApproachArea` and
  `DoorApproachDepth = 1.0`): for every door and every room it opens into (one room for an outer door, two for an
  inner one), the approach area is the rectangle of the opening's width running from the wall face 1.0 m into the
  room, clipped to the room interior. No prop and no decoy footprint may overlap it; touching edges do not count.
- 1.0 m is the square a 1 m leaf sweeps, kept on both sides whether the door has a leaf or not. It is fixed, not the
  door width: a 1.5 m opening does not need a deeper approach.
- Left to other rules: rugs and the exit mat (flat), platforms and ramps over a threshold (`CheckSplitLevel`), the
  leaf swing sector (`CheckSwingSector`), robots (`CheckRobots`).
- Not called from `Validate` yet: level13 still breaks it, and `LevelLoader.Load` throws on any `Validate` issue,
  so wiring it now would make level13 unloadable while another agent works on it. Instead the EditMode test
  `DoorwayTests.Every_level_file_keeps_its_doors_clear` holds every `level*.json` and `title_house.json` to it, with
  a `Pending` list (`level13`) that fails as soon as a pending level is clear, so the entry cannot rot.
- Test fixtures (`test_*.json`) are out of the test's scope. Three break the rule: `test_m5_audit_house` and
  `test_m5_audit_house2` (prop Sofa, door 6, room r10) and `test_v2_schema_odile` (prop Lit, door 2, room chambre,
  the level18 layout mirrored). Left alone: they serve audit fixture rules with their own premises.

## Moves (all levels but level13 and level17)
| Level | Door | Offender | Was | Now |
|---|---|---|---|---|
| level11 | 4 (salon / cuisine, x 10.25) | Canape, 0.3 m off the wall, over half the opening | x 9.25 | x 8.75 (TableBasse follows, x 9.25 to 8.75) |
| level4 | 1 (entree / salon) | Bench (counter along the south wall), 5 cm into the area | z -1.85, depth 0.3 | z -1.875, depth 0.25 (a longer move would reach door 2's area) |
| level10 (cut) | 2 (couloir / cuisine) | Evier, 5 cm in | z 7.2 | z 7.1 |
| level12 | 3 (salon / couloir) | CanapeOuest, 0.1 m in | z 6.6 | z 6.5 |
| level14 | 2 (chambre / salle) | Commode, 0.1 m in | x 0.6 | x 0.3 |
| level15 | 3 (salon / cuisine) | Canape, 0.1 m in | z 6.6 | z 6.7, Mamie's sit station z 5.85 to 5.95 (same seat front) |
| level18 | 2 (couloir / chambre) | Lit: the 2 m room leaves 0.75 m beside the door, the bed is 0.8 m wide | x -1.55, width 0.8 | x -1.625, width 0.75 (flush to the west wall, same yaw and z) |
| level22 | 2 (chambre / boudoir) | Paravent, 0.3 m in | x 1.6 | x 1.95 |

## level13 and level17 (not touched)
- level13 door 1 (2.25, 5.95), room plateau: decoy 3 (office_chair at (2.84, 4.75)), 0.875 m off the wall face.
- level13 door 7 (9.95, 6.75), room cafeteria: prop Comptoir ((12.0, 7.05), 2.4 m long), 0.8 m off the wall face.
- level17: no offender.

## Audit
`LevelAudit.RunBatch -auditLevels level11,level4,level10,level12,level14,level15,level18,level22 -skipFixtures
-difficulty normal,difficile -writeRoutes` (Build/doors.log, Build/doors18.log): every level "aucun defaut" at normal
and difficile.
- First try on level18 turned the bed 90 deg along the south wall: normal failed the pace gate (waiting share 52 %
  over 50 %). Replaced by the narrower bed above; level18 then passed at both difficulties.
- DoorwayTests (EditMode, targeted run, TestResults/doors.xml): 4 of 4 pass.
- Two runs were lost to other agents' half-written files (GameState.cs WorldSteps, ProbeTestsHeldStart.cs
  SequenceEqualTo); retried once each was whole.

## A VERIFIER
- Wire `DoorwayIssues` into `LevelValidator.Validate` once level13 is clear (remove `level13` from
  `DoorwayTests.Pending` at the same time). The three test fixtures above then need a move too, or `Validate` fails
  on them.
- level18: the bed is 5 cm narrower (0.75 m) and flush against the west wall; check the look in play.
- level4: the Bench is 5 cm thinner (0.25 m): check it still reads as a counter.
- level11: sofa and coffee table both moved 0.5 m west; check the salon still looks balanced.
