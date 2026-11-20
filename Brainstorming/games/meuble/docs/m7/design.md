# M7 design: difficulty and progression (CONTRACT_M7 section 4)

## 1. The difficulty option (4.1), done

`Core/DifficultyDef.cs`, values in `Tuning.cs` ("M7 design"). Applied in one place: `RoutineFactory.PersonalityOf`
(every routine of the game, the audit and the tests gets its personality there, and the audit's own watcher rows too),
plus `GameState.BuildLevel` for the grace and the creak and the audit's search for the creak.

| Knob | Facile | Normal | Difficile |
|---|---|---|---|
| View range factor (every watcher, lamp factor on top) | 0.85 | 1 | 1.15 |
| Cone half angle offset | -5 deg | 0 | +5 deg |
| Hearing factor | 0.75 | 1 | 1 (see below) |
| Suspicion gain factor | 0.75 | 1 | 1.5 (two discoveries lose) |
| Caught grace (and the dog's bark grace) | 0.30 s | 0.20 s | 0.14 s |
| Creak fill time | 25 s | 20 s | 16 s |

- Not knobs: the 0.6 s turn telegraph (the fairness rule of PRD 4.3 and 5.4) and the glance timings (a shorter dwell is
  not monotone: it can open windows as well as close them).
- Difficile hearing stays 1: at 1.25 the audit found no schedule on level 2 (rug lesson) and level 3 (decoy lesson),
  both with "a schedule exists without noise". 1.1 was never audited.
- The option: `SaveData.options.difficulty` ("facile", "normal", "difficile"; missing or unknown is Normal, version 1),
  a fifth row "Difficulté" on the Options page (cycle Facile, Normal, Difficile; "Par défaut" resets it to Normal).
- When it applies: at the next level build (load, next level or restart R). The level in play keeps the difficulty it
  was built with (`GameState.Difficulty`), so its rules and its record always agree and a switch before the exit cannot
  file a Facile run as a Difficile record.
- Records: `best["levelN"]` stays Normal (old saves keep theirs), `best["levelN@facile"]`, `best["levelN@difficile"]`;
  a win at any difficulty unlocks the next level; the level select shows the current difficulty's record.
- Audit: `-difficulty normal,difficile` (default: both, Normal first). A Difficile result is printed as
  `Niveau levelN@difficile`; `-writeRoutes` writes `designerRoute` (Normal) and `designerRouteHard` (Difficile, new
  field of LevelDef, checked by LevelValidator). Fixtures always run at Normal.

## 2. The measured curve (4.2): baseline, audit of 2026-11-17 (`-slack`, before any retune)

Margin = the largest margin with a schedule, in 0.1 s samples each side (15+ = at least 15). Exit = the audit's
earliest exit. Difficile ran with hearing x1.25 (since set back to 1).

| Level | Lesson | Normal margin | Normal exit (s) | Difficile |
|---|---|---|---|---|
| 1 | | 15+ | 10.7 | ok, 15+, 11.1 s |
| 2 | rug | 15+ | 13.3 | FAIL at hearing 1.25 (no schedule; one exists without noise) |
| 3 | decoy | 9 | 18.6 | FAIL at hearing 1.25 (no decoy schedule; one exists without noise) |
| 4 | careful | 8 | 14.9 | ok, 7 |
| 5 | sit | 10 | 16.1 | ok, 10 |
| 6 | dark | 15+ | 15.9 | ok, 15+ |
| 7 | glide | 10 | 20.3 | ok, 9 |
| 8 | door | 15+ | 18.2 | ok, 15+ |
| 9 | robot | 10 | 12.3 | ok, 10 |
| 10 | rock | 8 | 18.1 | ok, 8 |
| 11 | load | 15+ | 15.5 | ok, 15+ |
| 12 | pet | 15+ | 14.3 | ok, 15+ |
| 13 | load | 8 | 26.2 | FAIL: fidelity replay, Claire sees the chair at 6.1 s at (1.12, 5.25); fixed 2026-11-19 (see below): ok, 8, 36.6 s |
| 14 | split | 7 | 27.0 | ok, 7 |
| 15 | robot | 5 | 28.9 | ok, 5 |
| 16 | dark | 15+ | 27.6 | FAIL at both: 25 materials over the 24 budget (not a design defect: the M7 texture or lighting work) |
| 17 | final | 9 | 21.2 | not measured (the run ended before it) |
| 18 | wardrobe | 6 | 21.7 | not measured |

The curve is flat: margins 15+ on levels 6, 8, 11, 12 and 16, exits never above 29 s, level 17 easier than 15.
No level file was changed by the design agent (the product owner stopped the work before a retune could be audited at
both difficulties). The table "after" is therefore the table above.

Level 13 at Difficile, 2026-11-19: an audit defect, not a level one. The sighting at (1.12, 5.25) is the office chair
gliding into the hidden corner (0.75, 5.25): the replay releases early and the chair slides the last 0.37 m (the careful
stop distance plus the 0.1 m release), but the search checked a stop at the cell it stops at only, whose ring misses a
pose that far back. Six level variants (a shelf hiding the corner, Claire's dwell 3.5 and 4.5, Max's dwell 8, a narrower
door, Claire's station moved) each left the same sighting or moved it to another glide-in pose ((3.38, 6.75), (2.25, 6.12),
(1.85, 6.75)). The search now also checks the glide at the cell it comes from (LevelAudit.GlideCell, a moving node keeps
that cell in its state; fixture test_m7_audit_glide, mutation audit_glide). level13.json is unchanged but for its new
designerRouteHard: Normal margin 8, exit 26.2 s (same route); Difficile margin 8, exit 36.6 s, fidelity 0 sightings.
Levels 7 and 21 (the other office chairs) still pass at both difficulties with their file routes.

## 3. Retune plan per level (for later; each needs an audit at Normal and Difficile, then -writeRoutes)

Target: margin 15 on 1 and 2 down to 4 to 6 on 16 to 18; exit from about 10 s to 45 to 60 s on the last houses; never
easier than two levels before. Variants were written (scratch, not audited): designm7/round1.py. The method that saves
audits: variant files outside Assets audited in one batch by absolute path (`-auditLevels C:/.../level6_a`), Normal
and Difficile, `-slack -skipFixtures`.

| Level | Now | Target | Lever to try first |
|---|---|---|---|
| 2, 3 | Difficile fails at hearing 1.25 | pass at Difficile | re-audit with hearing 1 (current), else move the station 0 of level 2 off the rug edge |
| 5 | 10 / 16.1 | 9 / 19 | sit on the player 0.5 -> 2.5 s, station 2 dwell 8 -> 6.5 |
| 6 | 15+ / 15.9 | 8 / 17 | station 0 (4, -0.25) -> (2, -0.25): inside the 4 m dark range of the route |
| 7 | 10 / 20.3 | 8 / 21 | both dwells 2.5 -> 2.0 |
| 8 | 15+ / 18.2 | 8 / 20 | Paul station 1 faces south (180) over the salon crossing |
| 9 | 10 / 12.3 | 8 / 20 | start Claire at station 1 (facing the route), glances +-45 -> +-80 |
| 11 | 15+ / 15.5 | 8 / 22 | Lea starts at station 1 (couloir foot, facing up it) or her corner dwell 14 -> 5 |
| 12 | 15+ / 14.3 | 7 / 22 | Paul station 2 faces north (0) over the salon |
| 13 | 8 / 26.2 | 7 / 28 | Difficile passes since the glide fix (above); dwell retunes tried: Claire station 0 4 -> 5 (Normal regression), Max station 0 9 -> 7 (loitering) |
| 16 | 15+ / 27.6 | 5 / 35 | the dog awake 6 s of 12; Claire station 2 at (3.25, 1.75) facing 45 over the couloir door; fix the material budget first |
| 17 | 9 / 21.2 | 4 to 5 / 45+ | Lea station 0 faces north (0) over the sejour for her 25 s: the crossing waits for her canape and station 2 |
| 18 | 6 / 21.7 | 4 to 5 | Odile's looks away 5 s -> 4.7 s |
| 14, 15 | 7 / 27, 5 / 28.9 | exit 40+ | later, after 16 and 17 |
