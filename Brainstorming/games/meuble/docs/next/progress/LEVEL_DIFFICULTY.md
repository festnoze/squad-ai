# LEVEL_DIFFICULTY: can every card be solved in Normal, and how hard is each one (2026-11-25)

Scope: the 20 cards of `Assets/Resources/Levels/levels.json` (rev 4), in card order (card N = `levels[N-1]`).
Measured with the strict LevelAudit at Normal (plus a `-slack` margin sweep), with a second advisory run under the
human profile (`-profile human`). No level JSON, runtime code or Tuning value was changed. No editor code was added:
the audit already selects the difficulty with `-difficulty normal`.

## 0. Correction (2026-11-25, after the user's playtest): read the rest of this file with care

The user plays level3 and level9 easily (level3: hide next to the other chair, let the human pass, go straight to the
exit; level9: enter the room staying near the robot, behind the human). The report below misreads the audit:

- **"Fails" does not mean "unsolvable".** The audit found a route on every card, level9 included (exit at 68.1 s).
  Its defects are design lint: the pacing rules (no more than `Tuning.AuditMaxWait` = 8 s within 1 m of one spot,
  wait share, longest pause), the material budget, and its own sampling self-check. None of them says a player
  cannot finish.
- **The scores measure the solver, not a player.** The solver plays under stricter rules than the game: it may never
  wait more than 8 s in one spot, and being seen still out of place is an instant failure (unless a decoy explains
  it), where the game fills a Suspicion gauge. When the natural strategy is a long wait (level3's decoy hide), the
  solver is not allowed to use it and must thread a tight timed route, which shows as a low slack and a high score.
- So the scores in section 2 are a "strict solver" metric only. They are not a difficulty ranking for humans; use
  playtest feedback for that. The curve analysis below inherits the same bias.

## 1. Verdict

- **18 of 20 cards pass the strict audit in Normal with 0 defects.**
- **Card 9 (level9, The Robot) FAILS** (4 defects). Its fastest route needs 68.1 s with about 47 s of waiting in the
  bedroom. The robot's lap, lengthened by L9LONG (2026-11-24, never audited), is a 44.4 s loop, so the hum only reaches
  the route once per lap. The strict route breaks the wait rule (31.4 s in one spot, limit 8 s). Claire also sees it in
  the fidelity replay at 43.9 s. On top of that the level has 27 materials (budget 25). The human-profile route at the
  same 68.1 s is not seen, so a very patient player can probably finish. Under the audit's rules, though, it is not a
  valid level.
- **Card 14 (level14, The Mezzanine) is solvable but fails the audit** (3 defects). This is the L14START variant that
  was left unvalidated. A route exists at 54.9 s and the fidelity replay sees nothing. But it has to wait 9.1 s in the
  bedroom (limit 8 s), its longest pause is 6.8 s (limit 6 s), and Mamie and Lea never meet in 300 s (separation rule).
- **Borderline for a human player** (they pass strict but not the human profile on solvability rules):
  - card 13 (level13): the human route needs 63.9 s instead of 38.6 s and a 14.1 s wait in one spot;
  - card 12 (level15): the human route has to wait 10.5 s in one spot.
- **Near-zero margin:** card 3 (level3) has slack 3, exactly the audit's own minimum (0.3 s), at both profiles. It is
  the tightest timing in the game, tighter than the finale (card 20, slack 4).

## 2. How it was run

Through the lock wrapper (PowerShell, in the background):

```
pwsh -NoProfile -File tools/unity.ps1 -Agent LEVELDIFF -UnityArgs "run . --timeout 3000 -- -executeMethod OutOfSight.Editor.LevelAudit.RunBatch -difficulty normal -skipFixtures -slack -json Build/leveldiff.json -logFile Build/leveldiff.log"
pwsh -NoProfile -File tools/unity.ps1 -Agent LEVELDIFF -UnityArgs "run . --timeout 3000 -- -executeMethod OutOfSight.Editor.LevelAudit.RunBatch -difficulty normal -skipFixtures -profile human -json Build/leveldiff_human.json -logFile Build/leveldiff_human.log"
```

- No `-writeRoutes` (designer routes untouched), no fixtures, no player build, no test suite.
- Unity exits 1 because level9 and level14 have defects. That is expected.
- Outputs:
  - `Build/leveldiff.log` and `Build/leveldiff.json` (strict);
  - `Build/leveldiff_human.log` and `Build/leveldiff_human.json` (human profile).
- What "Normal" means: `DifficultyDef.For("normal")`, the M6 game knob for knob. That is view range x1, cone +0 deg,
  hearing x1, suspicion x1, `Tuning.CaughtGrace`, and `Tuning.CreakFillTime`. The audit sets `DifficultyDef.Current`
  before each level.
- What the audit proves (strict): a schedule from spawn to exit that is:
  - never seen moving, never seen out of place without a decoy, never heard;
  - creak gauge under 0.85;
  - no wait over 8 s in one spot;
  - robust to a 0.3 s shift of every sight and hearing window.
  It is then replayed against the game's own sight test (the fidelity replay). Suspicion never rises on such a
  schedule (it is never seen), so there is no Suspicion peak to report.

## 3. Table (card order, Normal)

Legend:
- Exit = exit time of the fastest valid schedule, strict (human profile in brackets).
- Moves = cell moves (hops) on that schedule.
- Pauses = mid-route pauses of at least 0.5 s / waiting share.
- Slack = the largest sight and hearing margin, in 0.1 s samples, for which a schedule still exists (`-slack`). 3 is
  the audit's own minimum, 15 is the cap ("15+" = at least).
- Creak = peak creak gauge on the route (the cap is 0.85).
- Watchers: H = human (personality), D = dog, R = robot vacuum.
- Mechanics = what the audit proves is required (lesson and `requires` checks that bind, decoys switched off gives
  no schedule) plus the body's constant handling rule (stool careful, office chair glide, rocking chair rock, vase load).

| Card | Level | Solved (Normal) | Exit s | Moves | Pauses / wait | Slack | Creak | Watchers | Mechanics | Score | Comment |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | level1 The Living Room | Yes | 12.0 (12.3) | 22 | 0 / 27 % | 15+ | 0.00 | 1H default | none | **1.1** | Tutorial, very forgiving. |
| 2 | level2 The Hallway | Yes | 13.3 (13.6) | 23 | 0 / 31 % | 15+ | 0.00 | 1H default | rug | **1.4** | Rug binds; forgiving timing. |
| 3 | level3 The Dining Room | Yes, zero spare margin | 20.2 (20.2) | 28 | 1 / 45 % | **3** | 0.26 | 1H default | decoy | **4.6** | Act 1 spike: tightest timing in the game. |
| 4 | level11 The Vase | Yes | 15.0 (15.7) | 33 | 0 / 2 % | 15+ | 0.00 | 1H tidy | load | **1.4** | Run-through (no waiting at all); only vase handling. No `pace` field. |
| 5 | level5 The Armchair | Yes | 16.6 (16.9) | 15 | 2 / 38 % | 8 | 0.18 | 1H default | sit | **3.6** | Sit binds; 2.2 s sat on. |
| 6 | level6 The Lamp | Yes | 19.0 (19.0) | 17 | 0 / 20 % | 15+ | 0.00 | 1H default | dark | **1.5** | Dip: one switch, no mid-route pause. |
| 7 | level7 The Office | Yes | 19.3 (19.3) | 24 | 1 / 50 % | 8 | 0.21 | 1H default | glide, decoy | **3.7** | Solid act 1 closer. |
| 8 | level8 The Doors | Yes | 17.4 (17.4) | 33 | 2 / 24 % | 15+ | 0.13 | 1H dreamer | door | **2.1** | Lenient act 2 opener; both vias hold (corridor 17.4 s, kitchen 20.9 s). |
| 9 | level9 The Robot | **NO** (4 defects) | 68.1 (68.1) | 46 | 27 / 73 % | 8 | **0.85** | 1H watchful + R | hum | **fail** (6.6 on an invalid route) | Blocker: 47 s wait for the 44.4 s robot lap, seen at 43.9 s, 27/25 materials. |
| 10 | level12 The Dog | Yes | 23.3 (23.6) | 28 | 2 / 40 % | 5 | 0.13 | 1H dreamer + D | pet, careful | **5.0** | Plays the stool one card before the stool lesson. |
| 11 | level4 The Stool | Yes | 14.9 (15.2) | 20 | 1 / 33 % | 8 | 0.09 | 1H default | careful | **3.3** | Dip; tutorial placed after its mechanic was needed. |
| 12 | level15 Let Sleeping Dogs Lie | Yes (human: 10.5 s wait) | 27.1 (31.0) | 28 | 3 / 31 % | 6+ | 0.12 | 1H granny + D | rock | **6.0** | Borderline for humans. |
| 13 | level13 Wheels and a Vase | Yes (human: 14.1 s wait) | 38.6 (**63.9**) | 44 | 3 / 42 % | 13 | 0.28 | 2H hurried, watchful | load, glide, decoy | **5.9** | Easy for the solver, much harder for a human. |
| 14 | level14 The Mezzanine | Solvable, **audit fails** (3 defects) | 54.9 (54.9) | 65 | 2 / 25 % | 14 | 0.34 | 2H granny, tidy (wander) | split, sit | **4.0** | Unvalidated L14START variant; designer routes stale. |
| 15 | level18 The Wardrobe | Yes | 21.7 (21.7) | 23 | 1 / 47 % | 6 | 0.23 | 1H tidy | wardrobe, careful | **4.2** | Breather before the exam. |
| 16 | level17 The Whole House | Yes | 34.6 (34.6) | 47 | 4 / 26 % | 9 | 0.10 | 2H granny, tidy + D + R | door, pet, split, hum, load | **6.4** | Exam: all 5 mechanics bind. Dead room: cuisine. |
| 17 | level25 The Showroom | Yes | 29.7 (30.0) | 46 | 4 / 38 % | 8 | 0.25 | 2H hurried (1 wander) | decoy | **5.0** | Act 3 opener. "boulevard" via is 1.5x slower (warning). |
| 18 | level19 Hide and Seek, Family Size | Yes | 72.0 (72.0) | 93 | 5 / 35 % | 5 | 0.30 | 2H watchful, dreamer | wardrobe, careful | **7.4** | Longest level (72 s, 93 moves). |
| 19 | level22 Skeletons in the Closet | Yes | 50.1 (50.1) | 67 | 3 / 33 % | 5 | 0.29 | 3H watchful, hurried, granny | wardrobe, careful | **6.6** | Same premise as card 18. Dead rooms: boudoir, office. No `pace` field. |
| 20 | level24 The Great Escape | Yes | 47.0 (56.0) | 71 | 6 / 40 % | 4 | 0.23 | 3H + D + R | door, pet, decoy, hum, exitwatch | **9.3** | Clear peak; second tightest slack. |

Other exposure numbers from the log:
- Closest approach to the robot (contact zone 0.72 m): level9 1.00 m, level17 1.45 m, level24 0.97 m.
- Shift tolerance of the found route: 0.3 s early and 0.3 s late on 13 of 20 levels (normal for a fastest route).
  The late side is larger on level1, level6, level11 and level14 (3.0 s), level2 (2.9 s), level17 (1.9 s) and level9
  (0.5 s).
- Vase: level11 and level17 keep the vase 0.12 m/s under its fall threshold, and level13 0.20 m/s. A player who goes
  slower than the solver is safer.
- Late start sweep (levels 1 to 7 only): if the player starts acting at some phases of the loop, a schedule needs a
  wait over 8 s. This happens at 7 of 37 start times on level1, 2 of 31 on level2, 6 of 44 on level3, 14 of 40 on
  level5, 4 of 17 on level7, and none on level4 or level6.
- Warnings (not defects):
  - level13 and level24: 4 decoys explain nothing under the strictest watcher's tolerance (still required for the
    others);
  - level13 and level22: habit warnings;
  - level22: a pause 0.29 m from Comtesse's walk line;
  - dead rooms in level17 and level22.

## 4. Scoring formula

Each metric is scaled to 0..1 (clamped):

| Component | Weight | Scale | Why |
|---|---|---|---|
| Tightness | 3 | (15 - slack) / 12 | Slack 3 (no spare margin) = 1, slack 15 = 0. Precise timing is the core skill. |
| Length | 2 | (exit - 10 s) / 60 s | Longer exposure, more to execute and more to lose on a mistake. |
| Beats | 2 | mid-route pauses / 6 | Each mid-route pause is one timing decision. |
| Threats | 1.5 | (humans + 0.75 x dogs + 0.5 x robots - 1) / 4 | 1 human = 0; 3 humans + dog + robot is about 0.8. |
| Mechanics | 1.5 | required mechanics / 5 | As defined in the table legend. |

- Base score = 1 + 9 x (weighted sum / 10).
- Human adjustment, added on top (cap 10):
  - +1 when the human-profile route has to wait more than 8 s in one spot and the strict one does not (level13,
    level15);
  - +0.5 when the human route's exit is more than 15 % longer than the strict one (level13 +65 %, level24 +19 %).
- Level9 has no score: its numbers come from a route the audit rejects. The formula would give 6.6.
- The script is in the session scratchpad (`score.py`). Inputs: the two audit JSON files, the strict log (decoy
  checks) and the level JSON files (watchers, body, load).

Sanity check against the level JSON (judgement):
- Every score agrees within about 1 point with the layout, cast and mechanics in the file.
- Two levels are probably under-rated by the formula, which only sees timing:
  - level11 (card 4), formula 1.4, judgement 2 to 3: the vase handling (careful before every turn, tidy Lea with a
    0.4 m tolerance) is execution difficulty;
  - level8 (card 8), formula 2.1, judgement about 3: first door leaf, 4 rooms, route choice.

## 5. Difficulty curve in card order

```
Act 1   1 #                 1.1
        2 #                 1.4
        3 #####             4.6   <- spike, slack 3
        4 #                 1.4   <- dip, 2 % waiting
        5 ####              3.6
        6 ##                1.5   <- dip
        7 ####              3.7
Act 2   8 ##                2.1   (act opener)
        9 XXXXXXXXXX        FAIL  <- blocker
       10 #####             5.0   <- stool used before its lesson
       11 ###               3.3   <- dip, the stool lesson
       12 ######            6.0
       13 ######            5.9
       14 ####              4.0   (audit fails)
       15 ####              4.2
       16 ######            6.4   exam
Act 3  17 #####             5.0   (act opener)
       18 #######           7.4
       19 #######           6.6   <- same premise as 18
       20 #########         9.3   finale
```

Problems:
1. **Card 9 is a blocker.** The line breaks right after the act 2 opener.
2. **Card 3 is a spike inside act 1** (1.4, then 4.6, then 1.4). It is the only level with zero spare margin, and it
   teaches memory and decoys at once.
3. **Act 1 zigzags.** It has dips at card 4 (level11: 2 % waiting, no pause, a run-through) and card 6 (level6: one
   switch, no mid-route pause). The two easiest cards after the tutorial sit right after the spike and right before
   the act closer.
4. **Cards 10 and 11 are in the wrong order.** Card 10 (level12) plays the stool, then card 11 (level4, "Too fast and
   the stool topples") teaches it, with a 1.7 point dip. Rev 4 created this by swapping level4 and level11: rev 3 had
   level4 at card 4.
5. **The second half of act 2 sags before the exam.**
   - Cards 12 and 13 (6.0 and 5.9 with the human adjustment) are harder than cards 14 and 15 (4.0 and 4.2).
   - The exam (6.4) is only 0.4 above card 12.
   - The planned breather at card 15 is fine; card 14 makes it a two-card dip.
6. **Cards 18 and 19 are near-identical.**
   - Same furniture (stool), same lesson (wardrobe), long multi-room houses, slack 5 both.
   - Card 15 (level18) is also stool plus wardrobe, so 3 of the last 6 cards share that premise.
   - Card 19 is also 0.8 easier than card 18.
7. **The finale step is the largest late step** (+2.7, from 6.6 to 9.3). It is acceptable for a finale. Card 20 is
   also the second tightest level (slack 4), and the human route needs 56 s (via the north wing) instead of 47 s.

What works:
- Act 3 now has a shape: opener 5.0, then a climb to 9.3.
- The finale is clearly the hardest card.
- The exam is the hardest card of act 2.

## 6. Recommendations (priority order)

1. **Fix level9 (blocker).** The hum must reach the bedroom-to-salon crossing within a few seconds of the start.
   Options:
   - shorten the lap (it was a back and forth before L9LONG);
   - start the robot at the point of its loop next to the bedroom door;
   - give the first leg a quiet (rug) crossing so it does not need the hum.
   Also bring the materials back to 25: the L9LONG bookshelf or another prop added colours, so reuse existing ones.
   Then audit with `-writeRoutes`, because both designer routes are stale.
2. **Finish level14 (L14START).**
   - Trim about 1.5 s of the opening wait (Mamie's sit or bathroom timing) so the bedroom wait drops under 8 s and the
     longest pause under 6 s.
   - Give Mamie and Lea one moment in the same room.
   - Then audit with `-writeRoutes`. Its designer routes still start at the old spawn, so route replay tests fail
     until then.
3. **Swap cards 10 and 11 back** (level4 before level12). That needs a levels.json rev 5 with `previous` = the rev 4
   order. It gives 3.3, then 5.0, then 6.0, removes the dip, and teaches the stool before it is needed.
4. **Ease level3 (card 3).** Aim for slack 6 or more like its neighbours, for example a longer decoy-covered window or
   a slightly longer habitant dwell.
   - Alternative (reorder only): act 1 = level1, level2, level11, level6, level5, level3, level7. That gives 1.1, 1.4,
     1.4, 1.5, 3.6, 4.6, 3.7, and decoys are taught right before card 7 uses them. First check that no hint on cards
     3 to 5 relies on the memory rule that level3 introduces.
5. **Human-feasibility of cards 12 and 13.** Shorten the waits the human profile hits: level15 near (7.75, 1.25)
   (10.5 s) and level13 near (3.75, 4.75) (14.1 s). Without that, a real player's experience of card 13 is closer to
   a 64 s level than the 39 s the strict audit reports.
6. **Act 3 variety.**
   - Either reorder to level25, level22, level19, level24 (5.0, 6.6, 7.4, 9.3, monotonic), keeping two wardrobe
     levels side by side;
   - or, in a later pass, give level22 another furniture so that cards 15, 18 and 19 are not all stool plus wardrobe.
7. **Add `pace` fields to level11 and level22**, so the audit checks their pace rules too. Today their "0 defects"
   ignores pace.

## 7. Level files not in levels.json

- level10, level16, level23: cut in LEVELS_V2 (decision D2). The files stay on disk because tests load them by id.
- level20, level21: parked by ACT3A (2026-11-24). The files stay on disk.
- Not audited here (out of the line-up). The folder also holds `title_house.json` (the title screen house) and the
  `test_*.json` audit and test fixtures, which are not levels.

## 8. Files

- New: this report.
- Generated (ignored by git): `Build/leveldiff.log`, `Build/leveldiff.json`, `Build/leveldiff_human.log`,
  `Build/leveldiff_human.json`, `Build/LEVELDIFF_wrapper.out`, `Build/LEVELDIFF_human_wrapper.out`.
- Editor code added: none (`LevelAudit.RunBatch` already takes `-difficulty normal`, `-slack`, `-json` and `-profile`).
- Not changed: any level JSON, any runtime script, any Tuning value, any designer route.

## A VERIFIER

- Designer routes differ from today's audit schedule on level9, level14 and level22. Level22's stored route may still
  replay (the audit says it stays valid if the probe wins it). Level9 and level14 need a passing audit with
  `-writeRoutes` first.
- Difficile was not run. The scores are Normal only.
- The scores come from the solver's best schedule plus a human reaction profile, not from playtests. Vase handling
  (level11, level13, level17) and reading the cones are not in the formula.
