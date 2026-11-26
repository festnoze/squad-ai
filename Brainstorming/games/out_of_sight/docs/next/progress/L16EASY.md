# L16EASY progress (2026-11-23/24): level select card 16 made more forgiving

## Which level
- levels.json "levels" order index 15 (card 16) = **level17.json**: the chair carrying the vase, Mamie sits on it at the
  start (LEVELS6 rebuild "La maison"). Checked against levels.json before any edit.

## Diagnosis (why a human finds it too hard)
- One crossing beat per Mamie cycle. The route must cross ramp W -> bridge -> ramp E inside Rex's 6 s nap (21.4-27.4 s),
  while Lea stands at her east-facing station s2 (9 s) and while the robot hums over the ramp E foot (the hops at
  (11.25-12.25, 4.25) are within Lea's hearing). Three periods (Rex 21.4 s, robot 7.5 s, Lea ~32 s) only line up once.
- Start-delay sweep (only measurable once Hugo is gone, see below): a player who starts later than ~12-15 s has NO
  schedule under the 8 s wait rule (18 of 23 start delays fail). Missing the first beat means a long, unguided wait.
- The vase forces careful legs (16-17 careful cell moves): the player cannot catch up after a late start.
- Mamie sits on the chair 0.6-3.2 s and the chair may only move ~6.8 s, once she walks south: moving early is caught
  (rush (a) is caught at 0.9 s). That part is readable (you see her leave) and was kept.
- Hugo (teen, wander seed 777: cuisine, couloir facing east, sejour NW) walks the couloir and the sejour lane. His
  wander never loops, so the level has no period at all (the audit cannot even run its start-delay sweep), and he makes
  the lane behind BuffetBas (the natural place to wait for the nap) unsafe for a late player. He is NOT on the optimal
  route: removing him alone leaves the found schedule and the slack unchanged (0.7 s Normal, 0.3 s Difficile).
- Difficile slack 0.3 s (the audit minimum): the binding constraint there is the end of Lea's s2 window (s2 11 s already
  lifts it to 0.7 s). At Normal the robot's hum window over the ramp E foot is part of the limit (robot loop moved north
  -> +0.1 to +0.2 s).

## Who to remove (human-profile audit, -slack; R1/R2)
| variant | Normal slack | Difficile slack | verdict |
|---|---|---|---|
| shipped | 0.7 s | 0.3 s | strict pass, human Normal fails pace (4 < 5 pauses) |
| no Hugo | 0.7 s | 0.3 s | same schedule; sweep becomes possible; identity intact |
| no Lea | 0.9 s | - | BREAKS requires pet AND requires hum (3 defects); Lea is the hum puzzle and is in the hint |
| no Mamie | 0.7 s | 0.7 s | no gain at Normal, 3 pauses; loses the "Mamie sits first" opening (hint) |
- Chosen: **Hugo**. He is not in the hint ("Mamie sits first. Rex sees the bridge. Lea hears everything the robot
  doesn't cover."), carries no lesson, and his removal makes the house periodic and readable. On his own he does not
  widen the solver's windows, so it is combined with wider windows.
- Knobs tried on top (no Hugo): Rex nap 7.5 s BREAKS the pet lesson (a schedule exists with the dog's eye at 1.6 m);
  Rex nap 6.5 s: no slack gain; Lea glance 1.0 s: no gain; Mamie sit 1.0 s: no gain; Lea s2 11-13 s: Difficile 0.3 -> 0.7;
  robot (11.25, 1.75)-(11.25, 3.25): Normal 0.8.

## Change (Assets/Resources/Levels/level17.json)
- Hugo removed (inhabitants: Mamie, Lea, Rex).
- Lea s2 (12.75, 5.25) facing east (away from the route): dwell 9 -> 20 s. Her loop is now about twice Rex's period, so
  a long "Lea looks away" window surrounds the nap (design intent: a second nap lines up later; not audited, see below).
- Robot loop (11.25, 1.5)-(11.25, 3.0) -> (11.25, 2.25)-(11.25, 3.25) (1.0 m, 5 s loop): it now hums over the ramp E
  foot for its whole loop. The hum is still REQUIRED (hum cut -> no schedule): Lea still hears the hops it covers.
- Unchanged: Mamie and her start on the chair, Rex (6 s nap, 15.4 s awake), the vase, props (no object moved: doorways
  untouched), rooms, doors, pace targets, hint text. No NIGHT key in this file. designerRoute (36 points) and
  designerRouteHard (39 points) rewritten by the strict -writeRoutes run.

## Numbers (before -> after)
Strict audit (gate; R3, Build/l16_r3.log; "before" = scratchpad copy of the shipped file audited in the same run):
| | Normal | Difficile |
|---|---|---|
| verdict | 0 defects -> 0 defects | 0 defects -> 0 defects |
| slack (max margin each side) | 0.7 s -> **0.9 s** | 0.3 s -> **0.7 s, at least** (0.8 s search hit the node budget) |
| route shift early / late | 0.3 / 1.2 s -> 0.3 / 1.9 s | 0.3 / 0.3 s -> 0.3 / 0.6 s |
| exit, waiting, pauses | 34.9 s, 26 %, 6 -> 34.6 s, 26 %, 6 | 35.9 s, 28 %, 7 -> 35.9 s, 26 %, 6 |
Human profile (-profile human; before = R1 Build/l16.log, after = R4 Build/l16_r4.log):
| | Normal | Difficile |
|---|---|---|
| verdict | FAIL pace 4 < 5 pauses -> FAIL pace 4 < 5 (unchanged, advisory only) | pass -> pass |
| slack | 0.7 s -> **0.9 s** | 0.3 s -> **0.9 s** |
| route shift early / late | 0.3 / 1.2 s -> 0.3 / 1.9 s | 0.3 / 0.3 s -> 0.3 / 0.6 s |
- The early side stays 0.3 s: it is the departure after Mamie stands up (move before she has left the room and she sees
  you). That is the one readable cue of the level and was kept on purpose.
- Lessons: door, pet, split, robot (hum), load all still bind; requires all bind.

## Tests
- Updated: LevelDataM2Tests Wave5B row (people without "teen:wander"), ProbeTestsM5Levels WaveB (level17: 2 humans).
- New: ProbeTestsRush.Rush03_Level17RushesLose (rush probe a/b/c on level17 alone, not Slow). Rush02 (Slow, every level)
  was not run. No Step58 test targets level17 (they cover levels 19-25), so none was selected.
- mutation.sh: no marker names Hugo or level17 (unchanged).
- PlayMode (TestResults/l16_play.xml, filter Rush03_Level17|Step45n_|Step64b_Level17|Step45r_|Step57a_): 5/5 passed.
  Rush03: (a) caught at 0.9 s (Mamie), (b) caught before the drop, (c) n/a (closed door): no rush wins. Step45n (Normal
  route replay) and Step64b (Difficile, offsets -0.2/0/+0.2 s) win with 0 discoveries, 0 alerts, vase held.
- EditMode (TestResults/l16_edit.xml, filter DoorwayTests|Wave5B_levels_follow_the_revised_level_table): 5/5 passed.

## Runs
- R1 Build/l16.log: human -slack, shipped + L16_a..d (normal, difficile).
- R2 Build/l16_r2.log: human -slack -sweep, L16_c, e..i, nL (no Lea), nM (no Mamie).
- R3 Build/l16_r3.log: strict -slack -sweep -writeRoutes: level17 (= L16_j), L16_orig, L16_k, L16_l, L16_n. Exit 0.
- R4 Build/l16_r4.log: human -slack -sweep, the new level17.
- Variants: Build/levels_v2/variants/L16_*.json, generator scratchpad l16/gen.py (backup of the shipped file:
  scratchpad l16/orig_level17.json, identical to git HEAD's level17.json).

## A VERIFIER
- Play it by hand: the user should now be able to wait behind BuffetBas in the sejour lane for Rex's nap; confirm it
  feels fair.
- Second chance: the 8 s wait rule still fails late starts (17-18 of 23 start delays in the sweep); whether a LATER nap
  lines up with Lea's long s2 window is design intent, not audited (it needs waits over 8 s).
- New audit WARNING "piece morte : cuisine" (no station there since Hugo left). Not a defect today; it would be one under
  -strictRooms.
- Human-profile pace at Normal still 4 < 5 pauses (same as before): advisory, the strict profile is the gate.
- Difficile slack is a lower bound (node budget at 0.8 s).

## Builds (2026-11-24)
- Windows: Build/Play/OutOfSight.exe, "Build Finished, Result: Success" (Build/pc.log). No OutOfSight process was
  running at build time (one was running at the start of the task, it had closed).
- Android: Build/Android/OutOfSight.apk, Success (Build/apk.log).
- Assets/StreamingAssets/card_number.json not touched by this task.
