# HUMANAUDIT progress (optional "human" profile for LevelAudit)

## Verdict (short)
- The human profile unblocks NONE of the blocked levels (8, 13, 17, 20, 21, 22, 24). It makes the pause-count rule
  harder, not easier: the strict solver meets several pause minimums with 0.5-0.9 s micro-stops, and a human does not
  make those.
- Recommendation: do NOT judge the pace rules on the human profile instead of the strict one. Keep strict as the gate.
  Use `-profile human` as a design aid that shows which levels reach their pause count only through sub-second stops
  (level9, level17, level25 today). The blocked levels fail because their best route never needs to wait (2-14 %
  waiting, 1-2 pauses). That is a design problem, not a solver artefact.

## What was built
- `Assets/Scripts/Core/HumanProfile.cs` (new): constants (reaction 0.3 s, min freeze 1.0 s, min dash 2 cells), `TryParse`
  for the flag, `ReactionMask` (a door an inhabitant opened counts as open only 0.3 s later), `Breaches` (checks a
  schedule: freeze < 1 s, a one-cell dash that ends in a stop or a freeze, two toggles in a row).
- `Assets/Editor/LevelAudit.cs`: flag `-profile human` (`-profile strict` or no flag = the old audit). An unknown value is
  an error. Human + `-writeRoutes`: routes are NOT written (log line says so).
  - `SearchOptions.Human` (false by default) changes the search:
    - a freeze starts as one 10-sample block (`HumanFreeze`, every sample checked like a strict still sample);
    - a `Dash` node bit (in the state key only when human) stops the first cell of a run from stopping or freezing;
    - a move from rest needs both cells unseen (at the margin) for 0.3 s before it starts (`HumanReacts`), on top of the
      0.3 s margin. A doorway an inhabitant opened can be crossed 0.3 s after it opens;
    - no toggle right after a toggle.
  - The found path is unrolled back to one still node per sample (`UnrollFreezes`) and checked with
    `HumanProfile.Breaches`. A breach would be an "incoherence interne" defect. None was found in 44 results.
  - These searches use the profile: main search, sweep, slack, via checks, exit watch, diagnosis. The diagnosis also
    tries the strict search first ("un horaire existe au profil strict"). The lesson and requires counterfactuals stay
    strict (a superset: "no schedule even for a perfect player").
  - Output: a "profil humain" note per level, " (profil humain)" added to the no-schedule defect, a top-level
    `"profile": "human"` in the JSON. The strict path is unchanged: the same code paths behind `human == false`, the same
    key, the same notes, the same JSON. LEVELS6's runs A2 and my r3 ran the strict default on this code with no change.
- No speed margin: cell costs are whole samples tied to the replay (rock plan, load model), and the 0.3 s reaction
  already slows every start.
- `Assets/Tests/EditMode/HumanProfileTests.cs` (new, NOT run): constants, flag parsing, door reaction, each breach kind.
- New mutation markers (mutation script not edited, rows proposed):
  - `HUMAN_PAUSE` (LevelAudit HumanFreeze), `HUMAN_DASH` (LevelAudit move offer), `HUMAN_REACTION` (LevelAudit
    HumanReacts loop): kill target = this human run (e.g. level9 human must keep failing 3 < 4 pauses).
  - `HUMAN_FREEZE`, `HUMAN_REACTION_DOOR` (Core HumanProfile): kill target = HumanProfileTests.
  - Existing markers untouched.

## Runs (3 Unity runs used)
- r1 (Build/HUMANAUDIT_r1.log): died at compile in 16 s (CS0266, byte cast in UnrollFreezes). It also made LEVELS6's
  chain wait one retry (their note at 00:09).
- r2 (Build/HUMANAUDIT_r2.log, Build/next/HUMANAUDIT_human.json): human, 22 levels x normal,difficile, -skipFixtures.
  00:12-00:32. Sum 1142 s, 339 M nodes.
- r3 (Build/HUMANAUDIT_r3.log, Build/next/HUMANAUDIT_strict.json): strict, same set and flags. ~00:51-01:02 (queued behind
  LEVELS6_A2). Sum 677 s, 157 M nodes. Exit 0: every level passes strict at both difficulties.
- Level files between r2 and r3 (hashes in Build/next/HUMANAUDIT_hashes_r2.txt / _after.txt): only level17 (LEVELS6
  changed finishes, 00:41) and level25 (00:35, unknown edit) changed. level17 is still a fair comparison: LEVELS6_A1
  (strict, 00:03) on the exact file r2 saw gives the same numbers as r3 (34.9 s, 26 %, 6 pauses). level25 compares two
  different files.

## Comparison, Normal (strict | human). Pauses = all (mid-route); longest = longest mid pause
| level | strict | human |
|---|---|---|
| level1 | pass 12.0 s, 27 %, 1 (0) | pass 12.3 s, 29 %, 1 (0) |
| level2 | pass 13.3 s, 31 %, 1 (0) | pass 13.6 s, 32 %, 1 (0) |
| level3 | pass 20.2 s, 45 %, 2 (1), 5.2 | pass 20.2 s, 45 %, 2 (1), 5.5 |
| level4 | pass 14.9 s, 33 %, 2 (1) | pass 15.2 s, 34 %, 2 (1) |
| level5 | pass 16.6 s, 38 %, 3 (2) | pass 16.9 s, 39 %, 3 (2) |
| level6 | pass 19.0 s, 20 %, 1 (0) | pass 19.0 s, 20 %, 1 (0) |
| level7 | pass 19.3 s, 50 %, 2 (1) | pass 19.3 s, 52 %, 2 (1) |
| level8 | pass* 18.2 s, 36 %, 2 (1) | pass* 18.2 s, 36 %, 2 (1) |
| level9 | pass 19.3 s, 30 %, 4 (3), 0.7 | FAIL 19.3 s, 30 %, 3 (2): "3 pauses < 4" |
| level12 | pass 24.0 s, 42 %, 3 (2) | pass 24.3 s, 42 %, 3 (2) |
| level11 | pass* 15.5 s, 2 %, 0 | pass* 16.2 s, 6 %, 1 (0) |
| level15 | pass 27.1 s, 31 %, 4 (3) | FAIL 31.0 s, 34 %, 5 (4): loiter 10.5 s > 8 s near (7.75, 1.25) |
| level13 | pass* 26.2 s, 31 %, 2 (1) | FAIL no schedule: node cap 80 M reached (inconclusive) |
| level14 | pass 44.8 s, 24 %, 4 (2) | pass 44.8 s, 24 %, 4 (2) |
| level18 | pass 21.7 s, 47 %, 2 (1) | pass 21.7 s, 47 %, 2 (1) |
| level17 | pass 34.9 s, 26 %, 6 (4), 1.4 | FAIL 34.9 s, 26 %, 4 (2): "4 pauses < 5" |
| level19 | pass 72.0 s, 35 %, 6 (5), 6.0 | pass 72.0 s, 35 %, 7 (6), 6.0 |
| level21 | pass* 19.0 s, 5 %, 1 (1) | pass* 19.7 s, 8 %, 2 (1) |
| level20 | pass* 55.3 s, 14 %, 2 (1) | pass* 55.6 s, 14 %, 2 (1) |
| level22 | pass* 50.1 s, 31 %, 4 (3), 5.8 | pass* 50.1 s, 29 %, 4 (3), 5.8 |
| level25 | pass 29.9 s, 39 %, 5 (4) | FAIL 30.2 s, 39 %, 4 (3): "4 pauses < 5" (different file) |
| level24 | pass* 40.4 s, 2 %, 1 (1) | pass* 41.1 s, 4 %, 2 (1) |

`*` = the file on disk has no `pace` field (old designs: 8, 11, 13, 20, 21, 22, 24), so "pass" ignores the pace rules.

Difficile: the same picture. Human fails only level15 (loiter 10.8 s) and level13 (node cap). level17 passes there
(6 pauses vs 7 strict). Exits +0 to +0.3 s, except level15 (+4.9 s), level20 (+2.2 s), level21 (+0.7 s).

Rush times: the human profile barely slows the solver. Exits are +0.0 to +0.7 s on 20 of 21 comparable levels. Waiting
share moves 0 to +4 points. The only real change is level15 (+3.9 s Normal, +4.9 s Difficile).

## Blocked levels against the LEVELS_V2 10.1 pace targets (Normal)
| level | target share / pauses / max | strict | human | unblocked? |
|---|---|---|---|---|
| 8 | 22-45 % / 3 / 6.0 | 36 %, 2 pauses | 36 %, 2 pauses | no (pauses) |
| 13 | 22-45 % / 4 / 6.0 | 31 %, 2 pauses | no schedule (node cap) | no (inconclusive) |
| 17 | 22-45 % / 5 / 6.0 | 26 %, 6 pauses: passes | 26 %, 4 pauses | no: human breaks it |
| 20 | 22-45 % / 4 (3 mid) / 6.0 | 14 %, 2 pauses | 14 %, 2 pauses | no (share, pauses) |
| 21 | 22-45 % / 6 (5 mid) / 6.0 | 5 %, 1 pause | 8 %, 2 pauses | no (share, pauses) |
| 22 | 22-45 % / 5 (4 mid) / 6.0 | 31 %, 4 pauses | 29 %, 4 pauses | no (pauses) |
| 24 | 25-45 % / 8 / 6.0 | 2 %, 1 pause | 4 %, 2 pauses | no (share, pauses) |

Why: on 20, 21 and 24 the best route never needs to wait (14 %, 5-8 %, 2-4 %). The human rules remove micro-stops; they
cannot create waits the design does not force. On 8 and 22 the human route is the strict route. On 17 (and 9, 25) the
strict route reaches the minimum through 0.5-0.7 s stops (strict level17: 0.7 s at 12.9 s and 0.6 s at 29.6 s). A human
merges or drops those, so the count falls under the minimum.

## Other findings
- level15 (rocking chair): with 1 s freezes and no one-cell hops, the human route stays 10.5 s within 1.5 m of
  (7.75, 1.25), over the 8 s loiter limit. Strict avoids that with shorter stops (longest loiter 6.4 s). A real player
  on level15 likely hits that wait, worth a look by the level owner.
- level13: the human search ran out of the 80 M node budget (strict: 1-2 M). The dash bit doubles the states and level13
  carries a load. No conclusion for 13 without a larger cap.
- Cost: the human profile costs about 1.7x the strict one (1142 s vs 677 s, 339 M vs 157 M nodes).
- "longest 0.6 s" on human rows (8, 21, 24) is a door opening (0.6 s action), which the pace counts as a pause. It is
  not a freeze.

## Recommendation
- Keep the strict profile as the pace gate. The human profile does not relieve the blocked levels; they need decision
  points (forced waits), as LEVELS6 is doing.
- Optional PO decision: make the pause count read pauses of at least 1.0 s (the human freeze), or run `-profile human` as
  an advisory column in the final I1 audit. Either makes level9, level17 and level25 need real pauses. Do this only if
  the PO wants "pauses a human feels".

## A VERIFIER
- EditMode `HumanProfileTests` not run (no test suites). They only use Core.
- Fixtures not run (both runs used -skipFixtures). The strict path is unchanged by construction, and the strict r3 plus
  LEVELS6_A2 ran on this code with no internal-consistency defect, but the 35+ fixture self-test was not re-run.
- level13 human: inconclusive (node cap). A run with a bigger `Tuning.AuditNodeCap` would tell.
- level25 compared across two different files (changed at 00:35 between r2 and r3).
- The blocked levels were audited as they are on disk (old designs, no `pace` field). LEVELS6's variants (L6_8*, L6_20*,
  L6_21*, L6_22y) were not audited under the human profile.
- PostProcess (toggle folding, hide-flicker removal) may in theory put a sub-second wait back into a human path. The
  breach check runs before PostProcess. In r2 it folded spawn toggles on level6 D and level20 N/D, and one hide flicker
  on level22 D (at 24.7 s, inside the 20.2-25.3 s pause). All of them sit inside waits already over 1 s, so no short
  freeze came out of it. Not checked automatically after PostProcess.
- Human runs keep the spawn wait at 1.0 s minimum (the first freeze is a block). On level17 the pace shows a 0.5 s
  spawn pause because the pinned samples split the run. The freeze itself is 1 s or more.
- Mutation rows HUMAN_* proposed, not run.
- New files need their .meta committed (Unity generated them in r2): HumanProfile.cs.meta, HumanProfileTests.cs.meta.
