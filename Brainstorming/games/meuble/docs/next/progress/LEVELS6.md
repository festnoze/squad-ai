# LEVELS6 progress (idea 4: structural rework of levels 17, 22, 20, 21, 8, 13)

## State at start (2026-11-20, late evening)
- No progress file existed. Owner files level8/13/17/20/21/22.json untouched (old designs still loaded).
- Inputs read: RULEFIX.md, LV5.md, LV8.md, LV9.md, LV10.md, LV11.md, LEVELS_V2.md 1.3 / 4 / 5 / 10.
- Cap per level: 3 Unity runs (exploration, refinement, write). Order: 17, 22, 20, 21, 8, 13.
- Runs used: none yet.

## Diagnoses carried over
- level17: Normal passes with Lea s0 >= 5.5 (l17w_g / rf17_x2) since RULEFIX; Difficile has no schedule once Lea s0 >= 5
  (view range x1.15 at Difficile). Structural suspect: a lane Lea sees at 1.15 x range but not at 1.0 x range.
- level22: fast schedules go gallery -> library -> pantry once the Comtesse opened porte_bibliotheque; wardrobe never binds;
  loiter 8.8 s waiting for Alfred in the open.
- level20: Normal 3 pauses (needs 4); Difficile loiters 19-29 s east of the lit zone at (12.25-13.75, 5.25-6.25).
- level21: slack 3-4 before pace work; waits land at spawn + a 6.2 s pause at (1.25, 7.25); needs 6 pauses.
- level8: player tails Paul down the east strip, beats every sofa look: 2 pauses (needs 3), slack 15.
- level13: spawn pause 6.4 s is a tie-break; 2-3 pauses (needs 4); Max desk glance variants explode to 57 s.

## Tool: scratchpad lv6/vis.py (static sight model: cone + walls/doors + occluder boxes + platform/ramps, 9 sample points)
- `python vis.py <level.json> diff [rooms]` lists cells seen at Difficile only, per station / glance / walk-leg pose;
  `cell x z` lists every pose seeing a cell; `custom x z yaw eyeH kind` prints an ASCII map (N / D-only).

## level17 diagnosis (vis.py on rf17_x2)
- Mamie's walk from the armchair through the bureau door (4.45, 1.25) to s3 (5.25, 0.75) faces ~120-125 deg at the door:
  at Normal she sees the bridge east end (9.75-10.75, 4.25); at Difficile (60 deg, 8.1 m) ALSO the bridge west cells
  (8.75, 4.25), (9.25, 4.25), the ramp E (11.25-12.25, 4.25) and the door cell (12.75, 2.25). Her passage (~21-23 s) falls
  exactly in the only crossing window (Rex nap + Lea at s2) once Lea's s0 is >= 5 s. That is the Difficile blocker.
- Other Difficile-only exposures (Lea sofa sees (8.75, 4.25); Lea's walk to the sofa sees (6.25, 4.25); Rex 75 deg sees
  (11.25, 4.25)) are off the schedule's timing.
- Structural fixes: (a) Mamie s3 -> (4.75, 0.75) facing 180 (she steps out of the door and turns south: her door leg faces
  ~150 deg, bridge outside the cone at both difficulties); (b) a 2.0 m "Bibliotheque" (bookshelf, occluder) at (5.8, 2.15)
  yaw 90, 1.3 x 0.4 footprint x 5.6-6.0 z 1.5-2.8, east of the bureau door: blocks every door->bridge ray; it does not
  touch Rex's rays to the lane (pet lesson keeps binding through the 1.0 m BuffetBas) nor Rex's view of the bridge.
- Variants (scratchpad lv6/gen17.py): L6_17a = rf17_x2 + (a); L6_17b = rf17_x2 + (b); L6_17c = both; L6_17d = l17w_g + both.

## Run 1 level17 (Build/LEVELS6_17r1.log, Build/levels_v2/LEVELS6_17r1.json): L6_17a..d, normal,difficile, no -slack
- First launch (00:10) died on Start-Process quoting; relaunched 00:29 via scratchpad lv6/run.ps1 (queued behind
  LV13 / TIPS / winbuild locks). Status file: Build/LEVELS6_17r1.out.txt ("exit N" line when done).
- Launcher: `pwsh -File <scratchpad>/lv6/run.ps1 <tag> <comma list of level paths> [extra flags]` (detached via Start-Process).
- Normal results (00:37): L6_17a 0 DEFECTS: exit 33.1, 23 %, 5 pauses (3 mid), longest mid 1.4, spawn 4.0 + pinned 2.6,
  loiter 2.3, 116 dc / 30 mat. L6_17b/c: same schedule but the bookshelf adds 3 materials (35 > 32: DEFECT, the
  "bookshelf" kind brings its own colours) -> the shelf is out. L6_17d (l17w_g timing + both): 34.9 s, 26 %, 6 pauses
  (4 mid), 35 mat. Difficile pending.

- Difficile L6_17a: NO SCHEDULE ("un horaire existe sans plafond d'attente: sortie a 260.1 s"): the Mamie move is not
  enough. New reading (vis.py ring samples): at Difficile Rex's 75 deg cone reaches (11.25, 4.25) and the ring of
  (11.75, 4.25), so the whole ramp W -> ramp E foot run must fit in one 6 s nap AND end inside the robot's hum window
  (the hops at (11.25-11.75, 4.25) are 1.4-1.8 m from Lea at s2): a 3-way coincidence (nap 19.9 s, robot 7.5 s, Lea
  ~31 s) that only aligns at 260 s under the wait cap. At Normal (70 deg) the chair pauses at (10.75, 4.25) and waits for
  the hum: decoupled.
- Fix: "BuffetEst", a 1.0 m cabinet (BuffetBas kind and colours, no new material) against the mezzanine's east face
  south of ramp E, (9.75, 2.8) yaw 90, 1.2 x 0.5: Rex's rays to (11.25-11.75, 4.25) cross it (vis.py: no Rex pose sees
  them any more; (10.75, 4.25) still seen through a ring point; the bridge stays visible to Rex: hint kept).

- Run 1 final (00:54, Difficile): a NO schedule (260 s without the cap); b (shelf only) no schedule + node cap; c (both)
  no schedule; d (l17w_g timing + Mamie move + bookshelf) SCHEDULE: exit 35.9 s, 28 %, 7 pauses (5 mid), longest mid 1.2,
  spawn 4.2 + pinned 2.6, closest robot 1.27 m, all requires bind; its ONLY defect (N and D) is 35 materials (bookshelf
  kind). d Normal: 34.9 s, 26 %, 6 pauses (4 mid), longest 1.4, loiter 3.6. => candidate = d with the occluder built as a
  "cabinet" kind (2.0 m tall "ArmoireHaute", BuffetBas colours: no new material; gen17.py shelfKind=cabinet).
- Runs used for level17: 1 (r1). Run 2 had already grabbed the lock with e..h (see below) before this reading.

## Run 2 level17 (Build/LEVELS6_17r2.log / .out.txt): L6_17e = a + BuffetEst; f = cabinet 1.4 x 1.3 m at z 2.7;
  g = e + Lea s0 6; h = rf17_x2 + cabinet only (no Mamie move). normal,difficile, queued 00:52 behind 22r1.
- Run 2 Normal: e/f/g/h all 0 defects (33.1 s, 23 %, 5 pauses, 3 mid; the cabinet kind adds NO material, 30 mat).
  Difficile e: no schedule (BuffetEst alone does not decouple the rf17_x2 timing). f/g/h pending.
- Run 2 final (01:14): Difficile e, f, g, h ALL no schedule (h also node cap). The rf17_x2 timing (Lea s0 5.5) never
  schedules at Difficile, with or without the Mamie move or BuffetEst; only the l17w_g timing (Lea s0 7, Rex awake 15.4)
  + Mamie s3 move + tall occluder east of the bureau door (L6_17d) does. Runs used: 2.
- DECISION: run 3 = write run of L6_17w copied to Assets/Resources/Levels/level17.json (backup of the old file in
  scratchpad lv6/orig/level17.json; restore it if the write run is not 0 defects in both difficulties).
  Queued 01:15 as Build/LEVELS6_17w.log ("-auditLevels level17 -writeRoutes").
- 01:15 incident: 20r1 and 17w waiters entered while my 22r1 editor ran (lock dir recreated within seconds keeps its old
  CreationTime on NTFS, so tools/unity.ps1 took it for a stale ownerless lock); Unity refused both (no run spent) and
  their wrappers deleted the lock; I recreated .unity.lock/owner for 22r1's wrapper (pid 19140). Now one waiter at a
  time via scratchpad lv6/chain.ps1 ("tag|levels|extra" jobs, retried when Unity refuses). Chain 01:16: 17w then 20r1.
- Write candidate prepared: Build/levels_v2/variants/L6_17w.json = L6_17d with the occluder as kind "cabinet"
  ("ArmoireHaute", 1.3 x 0.4 x 2.0 at (5.8, 2.15) yaw 90, same box as d's bookshelf).

## STOP 02:30 (PO priority: Windows build). STATE AND EXACT NEXT STEPS
- Run 17ww (02:18-02:25, Build/LEVELS6_17ww.log): level17 = L6_17w again 0 DEFECTS N and D (same numbers as 17w), but
  the WRITE token reached Unity verbatim (python wrote backspace characters into run.ps1's -replace pattern): routes NOT
  written. run.ps1 now fixed (plain 'WRITE' -> '-writeRoutes', checked). Without routes the file is not shippable, so
  Assets/Resources/Levels/level17.json was RESTORED to the old file (all six owner files == git). The audited design is
  kept at Build/levels_v2/variants/L6_17w_audited.json (identical to L6_17w.json).
- All queued wrappers cancelled; no LEVELS6 process left; no Unity run started after 17ww.
- level17 (READY, needs one write-only run): `cp Build/levels_v2/variants/L6_17w.json Assets/Resources/Levels/level17.json`
  then `pwsh -NoProfile -File tools/unity.ps1 -Agent LEVELS6 -UnityArgs "run . --timeout 3000 -- -executeMethod
  OutOfSight.Editor.LevelAudit.RunBatch -auditLevels level17 -skipFixtures -difficulty normal,difficile -writeRoutes
  -json Build/levels_v2/LEVELS6_17ww2.json -logFile Build/LEVELS6_17ww2.log"` (type it directly, not via run.ps1 args);
  check "designerRoute ecrite dans" and "designerRouteHard ecrite dans" in the log and `"at"` entries in the file.
- level20 (1 of 3 runs used): audit Build/levels_v2/variants/L6_20e, f, g, h (study door + lit zone moved next to
  porte_cuisine) in one normal,difficile run; if one is 0 defects at D and has >= 4 pauses at N, ship it with a write run;
  else refine (the 4th Normal pause: Papa P2 glance or P1 dwell) in run 3 and stop.
- level22 (3 of 3, NOT shipped): best = L6_22y. Next agent with a fresh budget: keep the office door removed and Alfred's
  south-only patrol, then fix the two separation defects (Alfred must share a room with the Comtesse and with Mamie once in
  300 s: e.g. a third station in the vestibule is not enough, a pass into the gallery is needed, which needs ArmoireEst
  >= 2.1 m off his line: move it into a library-wall niche) and the gallery-west wait (Comtesse C0 5 -> 3).
- level21 (0 runs used): audit L6_21a..d (cafet -> hall door (18.7, 7.2) + Sofia S1 facing 180 = hall gate) in one run.
- level8 (0 runs used): audit L6_8a..d (gen813.py 8) in one run.
- level13 (0 runs used): audit L6_13a..d (gen813.py 13) in one run.
- Use scratchpad lv6/chain.ps1 (one waiter at a time, retries on refusal / compile errors) with jobs "tag|levels|WRITE".

## Run 1 level22 (Build/LEVELS6_22r1.log / .out.txt): L6_22a..d normal,difficile, ran 01:15-01:27. Runs used: 1.
- All 4 (N and D): "aucun horaire" + both vias, BUT the structural goal is met: "lecon wardrobe : sans se cacher dans
  l'armoire, aucun horaire : l'armoire est requise", and the diagnostic says a schedule exists WITHOUT NOISE:
  a 57.7 s (hide in ArmoireEst 37-50 s), b 55.2 s (hide 44.4-47.4 s, 3.0 s: the designed hide), c 52.2 s, d 55.7 s.
- Reading: the no-noise routes wait at (18.25-19.25, 10.25-10.75), the gallery's east end on hard herringbone: within
  the Comtesse's 2.25 m hearing at C1 (17.75, 8.5) (hearing ignores walls) and Alfred's 1.25 m at A2 (19.25, 10.75).
- Fix for run 2: a runner rug on the gallery east end, x 16.0-19.85, z 10.15-11.05 (kenney.rug, colour #5B93D9 already
  used: no new material). Variants (gen22.py eastRug=1): L6_22e = a + rug; f = e + Alfred A2 5.0; g = b + rug; h = g + A2 5.0.
- 01:30 incident 2: the 22r2 chain I stopped had already started its Unity editor (pid 31772, log Build/LEVELS6_22r2.log):
  22r2 IS running (lock-less); my 17w attempt was refused (no run spent) and its wrapper deleted the lock. Lock restored
  with owner = editor pid 31772; after.ps1 cancelled. The 17w chain (pid 54248) retries 17w then runs 20r1.
- Run 2 level22 (Build/LEVELS6_22r2.log, 01:29-01:36): e..h N and D all "aucun horaire"; e's no-noise route is
  identical to a's: the runner rug changes nothing, so the noise is not in the gallery. Runs used: 2.
- ROOT CAUSE found by code reading (LevelAudit.MuffledSilent): while hidden, every listener must stay farther than
  CreakRadius 7 x WardrobeCreakFactor 0.5 x hearing factor + 0.25 from the wardrobe centre for the WHOLE hidden window.
  Alfred (x0.5) -> 2.0 m. His A1 <-> A2 walk passes 0.7 m from ArmoireEst (21.45, 7.0): a hide while he walks by is
  never silent, so "hide as he passes" can never be a schedule. Same rule for every hide-past design (note for 18/19/24).
- Run 3 design (blind, the last run): Alfred patrols the south half only, A0 (20.75, 1.25) facing 180 dwell 1.5 <->
  A1 (20.75, 4.75) facing 0 dwell 1.0 (gen22.py alfred=10): A1 is 2.36 m from the wardrobe centre (> 2.0). Cycle
  ~8.7 s with one back-turned window ~5 s; the corridor run gallery door -> vestibule is ~16 cells (~8 s careful):
  the hide is forced, wait in the gallery's east end (not visible from the corridor), hide, leave on the next window.
  Office door still removed, east runner kept. Assets level22.json = L6_22w (backup in lv6/orig); run "22w" =
  level22 -writeRoutes + info variants L6_22x (A0 dwell 1.0) and L6_22y (A0 2.5). Queued via after.ps1 (pid in log)
  behind chain 54248. If level22 is not 0 defects N and D: restore the backup.
- 01:36-01:39: 17w, 20r1 and 22w all aborted on "Scripts have compiler errors" (another agent mid-edit: tests use
  FurnitureController.ActionKeyClaimed, Strings.TouchAction, TouchControls.ActionButton, removed ~01:32-01:35 by an
  agent working on input/touch (not LEVELS6)). No audit happened: these do NOT count as runs.
- 01:41 relaunched one chain (pid in out files): 17w -> 22w -> 20r1; chain.ps1 now retries every 5 min while the
  project does not compile (16 tries) and writes "DONE <tag>" in Build/LEVELS6_<tag>.out.txt when audited.
- Run 17w (01:45-01:51, Build/LEVELS6_17w.log): level17 (Assets = L6_17w) 0 DEFECTS Normal AND Difficile.
  N: exit 34.9 s, 26 %, 6 pauses (4 mid), longest mid 1.4, spawn wait 4.2 (+2.6 pinned), loiter 3.6, closest robot 1.05 m,
  118 dc / 30 mat, all 5 requires bind. D: 35.9 s, 28 %, 7 pauses (5 mid), longest 1.2, spawn 4.2, robot 1.27 m.
  BUT "-writeRoutes" never reached Unity ("pwsh -File run.ps1 ... -writeRoutes" binds the dash argument as a parameter):
  no route written. run.ps1 fixed (pass WRITE / SLACK tokens). One more write-only run of level17 is needed (tooling
  bug, same precedent as RULEFIX w19); 22w (running now) has the same lost flag = audit-only.
- Run 22w = level22 run 3 (01:51-02:02, Build/LEVELS6_22w.log; -writeRoutes lost, audit only): the south-only patrol
  WORKS as a structure but no variant is clean. Assets level22 (= L6_22w, A0 1.5) and L6_22x (A0 1.0): no schedule N/D.
  L6_22y (A0 2.5) Normal: exit 53.2 s, 33 %, 5 pauses (5 mid), longest 5.4 (the hide 40.3-45.7 s in ArmoireEst), spawn
  0.3, wardrobe REQUIRED and binds, aile_nord passes, aile_sud 96.5 s (x1.81, warning). Defects: "Comtesse et Alfred" and
  "Alfred et Mamie ne se croisent jamais" (Alfred never leaves galerie_est any more), loiter 9.1 s at (5.25, 11.25)
  6.4-19.3 s (gallery west, waiting for the Comtesse to leave C0), view fidelity (Mamie at 11.3 s, (4.18, 11.18)).
  Difficile y: 64.1 s, 40 %, same two separation defects, loiter 10.3 s near the spawn, fidelity (Comtesse 42.5 s).
- level22 DECISION: cap reached (3 audit runs), NOT shipped; Assets/Resources/Levels/level22.json restored from the backup
  (git diff empty). Best variant: Build/levels_v2/variants/L6_22y.json. What remains: give Alfred one pass through
  another room (e.g. A2 back at the gallery door but reached by a path >= 2.1 m from ArmoireEst, impossible in the 1.9 m
  corridor: so instead a short A0 -> vestibule step, sharing the vestibule with nobody... or move ArmoireEst into a
  niche cut into the library's east wall, door-less alcove x 19.9-20.0), break the gallery-west wait (Comtesse C0 dwell
  5 -> 3, or Mamie's gallery station moved east), then re-check aile_sud (<= 1.5).
- Queue (02:08): 20r1 running (chain 54224) -> 17ww (level17 WRITE, after.ps1 51020) -> 21r1, 8r1, 13r1 (after.ps1
  on 51020). Check Build/LEVELS6_<tag>.out.txt for "DONE <tag>".
- Queue (01:35, superseded): chain pid 54248 = 17w then 20r1 (waiting behind winbuild / RULEFIX); after.ps1 pid 8644 starts the
  22r2 chain when 54248 exits (one LEVELS6 waiter at a time).

## Prepared variants (not audited)
- level21 (lv6/gen21.py on lv10_21m): hall gate = cafet -> hall door (18.7, 7.2) + Sofia S1 facing 180: her 4 s dwell sweeps
  the hall's east strip x 18.25-20.25 incl. the exit (vis.py checked, N and D), the pocket (16.75-17.25, 5.75-6.75) just
  inside porte_hall stays unseen: one more gate with a wait before it. L6_21a = hall gate; b = + Bertrand start 0; c = + Kevin
  K1 2.5; d = + Sofia S1 dwell 6.
- level8 (lv6/gen813.py 8 on LV5_l8e): L6_8a = Paul start 0 (cuisine first); b = s2 dwell 3 + sofa 110 glance 1.0/3.0 (longer
  block of the strip end and of the doormat); c = a + b; d = s1 north glance 5.0/2.0 (ends at his departure) + s2 3.
- level13 (lv6/gen813.py 13 on LV8_13f): L6_13a = Claire start 1 (C1 look at the accueil door lands on the chair's arrival);
  b = Claire start 2; c = Max M1 dwell 4; d = a + c.

## Run 1 level20 (Build/LEVELS6_20r1.log / .out.txt): L6_20a..d normal,difficile, queued 00:55 behind 17r2.

- Run 1 level20 result (02:08-02:19, Build/LEVELS6_20r1.log). Runs used: 1.
  a / d (Rex doors at z 1.25, d + P2 6): IDENTICAL to r8a: N 50.6 s, 25 %, 3 pauses (spawn 6.2, bureau 4.0, corridor
  2.6), only defect "3 pauses < 4"; D 86.9 s, loiter 28.1 s at (12.25, 5.25) 18-60 s. Rex is not the Difficile cause.
  b / c: validator "3 door leaves: at most 2 per level" (the extra cuisine door is illegal).
- New reading: at Difficile Maman at M1 (1.25, 5.25) facing east sees lit cells up to 11.5 m, i.e. the whole lit zone
  (x 10.5-12.0, 9.25-10.75 m away) that is out of her 10 m Normal range; the lamp then has to wait east of the zone.
- Run 2 design (gen20.py studyX): the study door and its lit zone slide west next to porte_cuisine (door (9.75, 6.95),
  zone centred x 9.75; or x 10.25): the lamp waits in the dark study and makes one 3-4 cell lit crossing straight into
  the kitchen; the lit cells are inside both difficulties' ranges, so N and D read alike. vis.py DARK=1: the crossing
  cells keep only brief walk-pose Difficile-only exposures. L6_20e = door x 9.75; f = x 10.25; g = e + Maman M2 x 5.25;
  h = f + Papa P2 6. Queued as 20r2 (after.ps1 behind 21r1/8r1/13r1).

## level20 diagnosis (vis.py with DARK=1: ranges x 0.4 outside the lit zone)
- Difficile-only exposures of the cuisine entry cells (9.25, 4.25) / (9.25, 3.25) come from Rex walking the cuisine's
  z 1.75 lane (dog dark range 2.76 m at Difficile vs 2.4 at Normal) and from Papa leaving s2 facing west. Reading of
  the r9 Difficile schedule (85.9 s): the Normal entry at 23-24 s falls in Rex's eastward pass (23-28 s), the earlier
  window collides with Rex leaving the salon (21-24 s) and the later one with Papa walking north out of the cuisine
  (30-33 s), so the lamp waits 40 s east of the lit zone for the next alignment.
- Variants (lv6/gen20.py on level20_r8a): L6_20a = Rex's two cuisine doors moved to z 1.25 (his lane 3.0 m from
  (9.25, 4.25): a still lamp there is never seen, the dog sees motion only); L6_20b = second cuisine door (11.75, 4.95)
  "porte_office" (closed, opened by Papa, playerLocked) so Papa's s2 -> s3 walk leaves the cuisine without facing the
  lamp's lane; L6_20c = both; L6_20d = a + Papa P2 dwell 6.

## level22 diagnosis (from LV11 r10b log + geometry)
- The wardrobe lesson is tested with UNLIMITED waiting: it binds only when the final exposed segment is longer than the
  sweeping watcher's unseen gap. r10b's route waits in the office east end (never seen) and hops 1.5 m from the office door
  (19.95, 4.75) to the vestibule door (21.95, 3.25) behind Alfred: no hide can ever be required there.
- Structural fix: remove the office -> galerie_est door. Every route then ends gallery door (19.95, 10.95) -> galerie_est
  -> vestibule: 9 cells (stool 0.5 s/cell) = 4.5 s on each side of ArmoireEst (hide cells (20.75, 6.75/7.25)). Alfred
  walking south from A2 (facing south) lets the player follow behind; his turn north at A1 (1.1 s) forces the hide; the
  leave + run to the vestibule (4.8 s) fits the gap "A1 -> A2 pass of z 7.5 (1.9 s) + A2 dwell + turn (1.1 s)" only with
  A2 dwell >= 2.5. No-hide schedules: the corridor north part is seen from A1/A0 facing north, the south part from the
  southbound walk; no gap covers the 9 s traverse.
- The south wing (porte_office) now continues office -> library -> porte_bibliotheque (Comtesse-opened) -> gallery ->
  same corridor; ratio to check (<= 1.5). Door memory: porte_office must not be seen open by the Comtesse (A2 next visit)
  nor by Mamie's walk boudoir -> salon.
- Variants (lv6/gen22.py, base level22_r10b): L6_22a = no office door, Alfred 3 stations (1.5/1.0/3.0); L6_22b = Alfred
  A1 <-> A2 only (A2 3.0: hide ~4 s instead of ~10 s); L6_22c = b with A2 2.0; L6_22d = a with A2 2.0.

## RESUME session 2 (2026-11-22 00:00)
- State found: all owner files == git except level17.json, which DOGBIG changed at 03:59 (sejour floorFinish removed: the
  dog's rooms must not use dark herringbone / verde / teal tile). L6_17w carried an older finish set (sejour herringbone,
  couloir verde) -> ship candidate L6_17s = L6_17w geometry and routines + the CURRENT Assets room finishes and colours
  (finishes only; room boxes are identical). Backup of the DOGBIG file: scratchpad lv6/orig/level17_dogbig.json.
- New launcher scratchpad lv6/run2.ps1 <tag> <levels> <timeout> [WRITE] [SLACK] (tools/unity.ps1 -Agent levels6).
- Run A1 (00:00, Build/LEVELS6_A1.log, timeout 5400): level17 (Assets = L6_17s, WRITE) + L6_20e..h + L6_21a..d.
  WRITE also writes routes into passing variant files (harmless).
- Run A1 result (00:00-00:03): level17 0 DEFECTS N and D, routes WRITTEN (designerRoute 37 pts, designerRouteHard 38 pts),
  30 materials. The variant paths were wrong (the audit wants absolute paths WITHOUT ".json"; relative paths resolve
  under Assets/Resources/Levels), so 20/21 were not audited (3 min run).
- level17 finishes corrected after A1: the spec palette (L6_17w: chambre lightoak, couloir verde/limewash, bureau
  lightoak, cuisine ivorytile, entree marble/grasscloth) with the sejour floorFinish REMOVED (DOGBIG rule: Rex's room
  is parquet). Routes kept. Re-verified in A2 (WRITE) for the material count.
- Run A2 (00:09, via scratchpad lv6/chain2.ps1, retries every 3 min on compile errors: HUMANAUDIT was mid-edit in
  LevelAudit.cs at 00:09): level17 + L6_20e..h + L6_21a..d + L6_8a..d, WRITE.
- level22 variants prepared (scratchpad lv6/gen22b.py on L6_22y): the Comtesse and Mamie each get a station in the
  galerie_est north stub (z 10-11.9, past the gallery door) so both cross Alfred; stub stations >= 3.8 m from ArmoireEst
  (muffled creak reach: Comtesse 3.75 m, Mamie 2.35 m); facings 290 (turn via north) or 0 (wall), never the corridor.
  z1 = C0 -> stub (21.25, 11.25) f290 d4, Mamie M2 -> (20.75, 10.25) f290 d4; z2 = z1 with Mamie f0 d5;
  z3 = Comtesse f0 d3, Mamie f290 d4; z4 = Comtesse keeps C0 (dwell 3) + stub inserted as C1 (f0 d2), Mamie f0 d5.
- Run A2 (00:13-, Build/LEVELS6_A2.log). level17 = SHIPPED: 0 DEFECTS Normal AND Difficile with the corrected finishes,
  designerRoute (37 pts) and designerRouteHard (38 pts) rewritten by the audit. N 34.9 s, 26 %, 6 pauses (4 mid), longest
  1.4, spawn 4.2 (+2.6 pinned), 30 materials; D 35.9 s, 28 %, 7 pauses (5 mid), longest 1.2. All 5 requires bind.
- A2 Normal, every variant fails:
  - L6_20e/g (study door x 9.75): exit 82-84 s, share 47-48 %, pauses of 6.2 s, loiter 19-20 s at (9.25, 8.25).
    L6_20f/h (x 10.25): exit 48.8 s, 34 %, 3 pauses (< 4), loiter 10.2 s at (10.25, 7.25) 8.0-24.7 s (waiting in
    the dark study for the crossing). Diagnosis: the study wait is one long block; it needs a second watcher beat that
    splits it (D18: Papa's P0 -> P1 walk past the study door).
  - L6_21a..d (hall gate): spawn-area loiter 12-14.6 s, share 48-49 %, a 6.2-6.6 s pause, plus a view-fidelity defect
    (Kevin or Bertrand). The hall gate does not fix the early wait at (1.25, 7.25-7.75).
  - L6_8a..d: ONLY defect "2 pauses < 3" (spawn 5.0-7.2 s + one 0.6 s door pause; slack-rich straight run).
- A2 Difficile: L6_20e..h loiter 18-27 s east of the lit zone (11.25, 5.25-5.75) or in the study, exit 82-84 s (20g also a
  Papa view-fidelity defect). L6_21a..d loiter 13-28 s + view fidelity (Kevin / Sofia), exits 50-93 s. L6_8a..d pass at
  Difficile (the 3-pause minimum is a Normal-only defect).
- level8 variants (scratchpad lv6/gen8b.py on L6_8a): a station just inside the salon facing back west through the
  kitchen doorway stops the tail behind Paul (chair must wait in the kitchen, then for the s1 glance). L6_8e = back
  station (5.25, 1.75) f270 d1.5; f = d2.5; g = (5.75, 2.25) f250 d2.0; h = e with d2.0 + s1 glance offset 2.5.
- Queue: A3 (L6_22z1..z4 + L6_13a..d, chain2) then A4 (L6_8e..h) via scratchpad lv6/after_A3.ps1.
- level20 variants (scratchpad lv6/gen20b.py on L6_20f): Papa visits the study between the bathroom and the kitchen
  (the light he left on), so the lamp must leave the door while he is in and follow him out (splits the one long study
  wait). L6_20i = study station (9.0, 9.95) f0 (desk) d3; j = d5; k = (7.25, 8.75) f270 d3; l = Maman M1 x 6.25 only.
  Queued as A5 after A4 (scratchpad lv6/after_A4.ps1). 00:52: HUMANAUDIT holds the lock (full audit), A3 waits.
- A3 level22 Normal (01:13-): z1/z2 FIX BOTH CROSSINGS (Comtesse-Alfred and Alfred-Mamie "se croisent"), no loiter, no
  fidelity defect, wardrobe still required, exit 42.4 s. Remaining: Comtesse and Mamie collide in the stub (0.04 m z1,
  0.37 m z2, ~238 s) and the pace is too easy (2 pauses < 5, share 16 % < 22 %; pauses (13.25, 10.75) 1.0 s + the hide
  5.4 s). z3: also node cap and vias. z4 (gallery C0 kept + stub): 128.9 s, start loiter 21 s, share 64 %.
- level22 round 2 (scratchpad lv6/gen22c.py on z2, Mamie M2 -> (21.25, 9.75) facing the east wall, 2.76 m from the
  wardrobe): m1 = that only; m2 = + Comtesse start 1; m3 = stub dwell 7 + glance (2, -40, 1.5); m4 = Comtesse start 2;
  m5 = gallery C0 restored (dwell 3) + stub d2 f290; m6 = same with C0 dwell 2.
- A3 level13 Normal: L6_13a only defect "3 pauses < 4" (26.2 s, 27 %, pauses 1.9 / 3.0 / 1.4 s, all mid-route).
- A3 level13: L6_13c (Max M1 dwell 4) = 0 DEFECTS Normal AND Difficile. N 38.6 s, 44 %, 4 pauses (3 mid), longest 5.7,
  spawn 6.4; D 38.6 s, 38 %, 3 pauses, longest 5.7. 13a passes D only (N 3 pauses); 13b loiter; 13d N 3 pauses.
  -> Assets level13.json = L6_13c (old file == git, restore with git if the write run fails). Write run queued as A6
  (level13 WRITE + L6_22m1..m6) via scratchpad lv6/after_A5.ps1.
- A3 level22 Difficile: z1/z2/z3/z4 all bad (start loiter 29-37 s, node cap 40M, vias "aucun horaire", z1 fidelity).

## RESUME session 3 (2026-11-22 09:46, after a watchdog kill)
- level13 = SHIPPED (A6, 09:45): Assets level13.json = L6_13c (Max M1 dwell 4), 0 DEFECTS Normal AND Difficile,
  designerRoute 27 pts and designerRouteHard 28 pts written. N 38.6 s, 44 %, 4 pauses (3 mid), longest 5.7, spawn 6.4.
- A4 level8 (finished 09:46): L6_8g (station (5.75, 2.25) facing 250 dwell 2.0 just inside the salon, looking back at the
  kitchen doorway) = 0 DEFECTS Normal AND Difficile. N 17.4 s, 24 %, 3 pauses (2 mid), longest 2.6; D 20.9 s, 44 %,
  3 pauses. e/f/h: 2 pauses < 3 and share 10 % (Paul's back station is too short to stop the tail).
  -> Assets level8.json = L6_8g (old file == git). Write run W8 started 09:5x (Build/LEVELS6_W8.log).
- A5 level20 (L6_20i..l, Papa study visit / Maman M1 x 6.25): all fail. N: loiter 10-29 s and 6.2 s pauses (the study
  visit adds waits instead of splitting them); D: loiter 28-35 s in the study or east of the lit zone. level20 BLOCKED.
- A6 level22 round 2 (m1..m6): best m1 Normal = exit 64.0 s, 37 %, 6 pauses, both crossings OK, separation 0.83 m OK,
  wardrobe required; defects: loiter 22 s around the wardrobe (20.25, 7.25) 27-57 s (two hides back to back) and a 7.0 s
  pause. Difficile (all m): loiter 22-40 s, view fidelity, node cap 40M, vias "aucun horaire". level22 BLOCKED.
- level8 = SHIPPED (W8, Build/LEVELS6_W8.log): Assets level8.json = L6_8g, 0 DEFECTS Normal AND Difficile, designerRoute
  22 pts and designerRouteHard 19 pts written.

## FINAL STATE (session 3)
- SHIPPED (0 defects N and D, routes written): level17 (L6_17w + spec finishes, sejour parquet), level13 (L6_13c),
  level8 (L6_8g).
- NOT SHIPPED (Assets file == git, except level20 which carries only NIGHT's "lighting": "night"):
  - level22: the south-only Alfred patrol plus the Comtesse and Mamie stub stations fix both crossings and keep the
    wardrobe required, but Alfred's back-turned window is rare (Normal waits 22 s at the wardrobe) and Difficile never
    finds a clean schedule (start loiter 22-40 s, 40M node cap, vias). Blocker: Alfred's cycle (A0 2.5 / A1 1.0) gives one
    ~5 s window; next idea: a longer A0 dwell with a turn glance, or a second hide spot before the corridor. Best: L6_22m1.
  - level20: every study/lit-zone layout leaves one long dark wait (10-35 s) east of the lit zone or in the study; Papa's
    study visit adds waits instead of splitting them. Blocker: the lit crossing aligns with Maman's back-turned window
    only once per ~40 s. Best Normal: L6_20f (48.8 s, 3 pauses).
  - level21: the hall gate does not fix the early wait at (1.25, 7.25-7.75) (loiter 12-28 s) and Kevin / Sofia
    view-fidelity defects appear. Blocker: Bertrand's B1 4 s station holds the start for two cycles.
  - level24: not attempted (LV13 escalation stands: Difficile has no schedule, 8-pause gate). Best: LV13_q2.
  - levels 3 and 6: not attempted (they pass; known compromises: level3 slack 3, level6 minimum pause only via spawn).

## A VERIFIER
- level17, level13, level8: no PlayMode replay of the written routes (only the -writeRoutes audit run, PO rule).
- level17 floors: spec palette with the sejour floorFinish removed (DOGBIG rule); docs/m9/FLOORS_WALLS.md row 17 still
  describes the old finishes (not mine to edit).
- level8 / level13 test premises (CoreM5Tests level8, ProbeTests) not checked against the new routines (Paul has a new
  station 1 in level8; level13 Max M1 dwell 4).
- level8 and level13 wall/floor finishes come from the v2 variant lineage (spec palette), not the old Assets finishes.
- level20 v2 variants carry floorFinish herringbone in salon and entree on Rex's route: if one ships, drop those finishes
  (DOGBIG rule) and keep "lighting": "night".
- A4/A5 timestamps: A5 ran 00:52-01:13 before A4 finished (A4 ran 01:40-09:46 incl. a long lock wait); results read from logs.
