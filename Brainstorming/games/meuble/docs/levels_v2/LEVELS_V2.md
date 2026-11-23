# Out of Sight - Levels v2: overhaul specification (wave 2 brief)

Date: 2026-11-20. Author: wave 1 synthesis agent. Status: final for wave 2.

This document is the single source of truth for the level overhaul. Where it differs from a wave 1 design file, this
document wins. The wave 1 inputs are copied next to it in `docs/levels_v2/wave1/`:

- `design_act1.json` (levels 1-7), `design_act2a.json` (8, 9, 15, 11, 10 cut), `design_act2b.json` (12, 13, 14, 18, 17, 16 cut),
  `design_act3a.json` (19, 21), `design_act3b.json` (20, 22), `design_act3c.json` (25 new, 24, 23 cut)
- `code_features.json` (25 code features with file and line references), `feedback.md`, `mechanics.md`, `system_map.md`,
  `numbers.md`, `numbers.py` (the measuring script used by wave 1)
- `tools/decoy_cells.py` (new): lists the walkable audit cells each decoy explains. Run it on every level with decoys.

Each level section below says "base: <file> <level>" and then lists only the overrides. A wave 2 level agent reads its
section, then the base design for coordinates, and applies the base changes plus the overrides.

---

## 1. Goals and principles

### 1.1 The brief (product owner review, 19 Nov 2026)

"The houses got bigger. The puzzle did not." Cut three levels, retune the rest, give every late level its own body,
threat, shape and look. Four rules for every retune:

1. **No dead room.** Every room is on a viable route or holds a watcher's station (or a robot waypoint, a sleeping dog, a
   needed hide). Otherwise delete it.
2. **The obstacle in the title is on the route.** The audit's best schedule passes within reach of it, and its lesson
   check binds with no `lessonAdvisory` waiver.
3. **Wait often, never long.** About 25 to 40 % of the schedule spent waiting, in three or more pauses, none above 6 s.
4. **Change one axis per neighbour.** Body, main threat, plan shape, exit direction, palette: two neighbours share at most two.

### 1.2 What the field feedback adds (wave 1 feedback report)

- **The strict audit exit is an upper bound on a skilled run, not a floor** (owner cleared level 13 in 8.4 s against a
  26.2 s audit). Every level gets rush counter-routes that must lose (R2).
- **The level starts when the player does** (held start, QW4): the clock, routines and creak wait for the first input
  after the intro card. Without it the card eats the first window of half the levels.
- **Readable threats**: inhabitant names on the intro card, hint tokens per device, hum disc for the robot, an exit marker.
- **True hints**: a hint describes the threat, never the route, and never contradicts the data.
- **The look comes from finishes, not colours**: `floorColor`/`wallColor` only tint the level-select miniature. Walls and
  floors share one Texture2DArray material, so finish variety is free.
- **Progression must survive the reorder** (unlock rule + migration) and records of redesigned levels must reset (rev).

### 1.3 How the rules are measured in v2 (interpretations, decided)

- **Length.** PRD 1.3's "2 to 6 minutes" means a new player's first clear including retries, not a clean run. A clean
  run cannot be that long without breaking the 8 s wait cap. Length comes from decisions (pauses while a watcher is
  deciding), never from more floor.
- **Waiting share** = (exit - travel) / (exit - pinned time). Travel uses the audit's own cell cost per body; in-place
  actions (lamp toggles, door openings, wardrobe hide and leave and the time hidden) count as waiting; time pinned under a
  sitter is excluded from both sides; the office chair's glide and the rocking chair's rock count as travel.
- **Pause** = a run of 5 samples (0.5 s) or more at one cell. "Mid-route" pauses exclude the run that starts at t = 0
  (amended 2026-11-20, section 10.3: the spawn wait, everything before the first move, has its own 8 s limit).
- **Exit time is derived, not targeted.** Because routes keep roughly their length, exit = travel / (1 - share). With the
  25-40 % aim that is 1.33 to 1.67 x travel. The per-level exit bands in section 10 are soft (a warning), the pace gate is
  hard. This removes the contradiction between exit bands and waiting shares the critic found in 11 levels.
- **Pace gate** (hard, Normal): share 22 to 45 % in acts 2 and 3 (the PO's 25-40 % is the aim; the gate allows 3 to 5
  points of audit noise), the per-level minimum pause count, no pause above 6.0 s. Act 1 keeps per-level bands (a
  12 s tutorial with three pauses would feel fussy). Listed exceptions: level 3 (40-52 %, the wait is the joke), level 7
  (35-55 %, decoy rest + glide), level 18 (30-50 %, the hide is the lesson).
- **Margin** is always the audit `-slack` maximum, in samples (0.1 s). Curve: act 1 from 15 down to about 8, act 2 from
  about 9 down to 4-5 (the exam, level 17, lowest), act 3 from about 7 down to 4-5 (the finale, level 24, lowest). The
  audit's validity minimum (0.3 s early and late) still applies everywhere.
- **Difficulty of a slow body is not its clock.** The armchair (level 14) is long because the armchair is slow. The act
  curve is read on margin and pause count; the act closers have the lowest margin and the most pauses of their act.

---

## 2. Decisions log (every contested point, with the reason)

| # | Topic | Decision | Why |
|---|---|---|---|
| D1 | Line-up size | 22 levels: 7 + 9 + 6 | Review's 21 + the Showroom as a regular slot (the code has no optional-level concept; a regular slot costs nothing). |
| D2 | Cuts | level10, level16, level23 removed from `levels.json`; files stay on disk unchanged | Tests and fixtures load them by id; `CoreM4Tests`/`LevelDataM8Tests` validate every file in the folder. Never reuse their ids. |
| D3 | Showroom id | New id `level25`, new plan (not level23's) | Records and wins are keyed by id; level23's plan is level24's core, so it would repeat next door. |
| D4 | Dog before rocker | **Swap**: slot 10 = level12 (The Dog), slot 12 = level15 (Let Sleeping Dogs Lie) | The rebuilt level15 needs a dog (only a watcher without memory makes the rock bind). With the swap the dog is taught first and the rocker reuses a dog the player knows: one new thing per level. Both designs work unchanged in either slot (act2a says so). |
| D5 | Waiting share vs exit bands | Pace rule is the hard gate; exit bands are derived from travel (section 1.3) and soft | Fixed route lengths make "longer exit" and "25-40 % waiting" incompatible in 11 levels. The PO's rule is about rhythm, so rhythm wins. |
| D6 | Waiting gate width | Acts 2-3 gate 22-45 %, aim 25-40 %; act 1 per level | Audit granularity; act 1 teaches one rule per level. |
| D7 | Act 2 curve (14 vs 17) | Level 17 must have the lowest margin of act 2 (4-5 samples) and the most pauses (5+); level 14 stays the longest clock (armchair) with margin 5-8 | Length of a slow body is not difficulty. design.md's "45 s or more for the exam" is dropped: at a 45 % share it needs travel the chair level does not have. |
| D8 | Level 14 second sit | Described as a **soft deadline** (missing it costs a pratfall + discovery, not the level). `requires: ["sit"]` only if it binds | The audit forces seat presence at sit samples; a late schedule can be sat on again and continue. |
| D9 | Goal variety | Timed-return goal and two exits are **deferred to wave 3**. v2 variety is data-only: sit deadlines (5, 14, 17), door memory (20, 22), household doors (20, 22, 24), watched exits checked by `exitwatch` (24), route choices proved by `viaChecks` (8, 13, 21, 22, 24), a decoy grid (25), darkness by range (6, 20) | No v2 level design uses the return goal (effort L, 13 files, several owned by the visual-polish workflow). The PO marked the code goals "all optional". The effort goes to measurement (pace, vias, requires) that every level needs. |
| D10 | Lures (pillar 3, R9) | Not in v2. Open question for the PO (section 13) | No level can require a lure until the audit can model a deliberate alert. |
| D11 | Level 1 change | Window station dwell 5.0 -> 3.5 s, recorded as an amendment of CONTRACT_M2 11.8 and PRD 6.3 (integration task) | With the held start a full-speed rush would win level 1 without ever freezing. The station-2 A/B test (PRD open question 10) is closed: the dwell change gives the first mid-route freeze. |
| D12 | Act 1 mirrors/rotation | Keep: mirror 2 and 4 (x -> -x), rotate 7 by +90 deg | Verified exact: every room size along the mirrored axis is a multiple of 0.5 m, so the per-room audit grid maps onto itself. |
| D13 | Act 2 exit directions | Mirror level 18 (exact, all sizes multiples of 0.5) to exit NW. Mirror level 9 with the re-snap procedure (section 4.3), "should", revert after 3 failed audit iterations. No other act 2 mirror | **Correction to the critic**: act 2 houses use rooms 4.4/4.9 m wide with 0.1 m wall gaps, so a mirror shifts every point 0.1 m off the audit grid (checked on all act 2-3 files: only level 18 mirrors exactly). Level 9 is rebuilt anyway, so its re-snap costs little. |
| D14 | Decoy placement | Every decoy that must explain a rest is placed 0.51 to 0.6 m from one walkable cell centre along one axis (level 7/13 recipe), checked with `tools/decoy_cells.py` before the audit | The audit grid is per room on .25/.75 centres with a capsule of the body radius and no skin. Fixes the level 24 blocker, level 25's missing slots and level 3's 5 mm collision. Placements in this document were checked with the script. |
| D15 | Decoy necessity | Already checked by the audit (LevelAudit.cs 1935-1947: a schedule with decoys off fails the level). Treated as a hard constraint on 3, 7, 13, 21, 24, 25. The `decoy` id in `requires` only makes it explicit. The `rug` check (level 2) is new | Corrects the act 1 / act 3c code requests. |
| D16 | Level 24 mezzanine | Delete it (and both ramps) and use `requires: ["door", "pet", "decoy", "hum", "exitwatch"]`. Fallback if the `requires` feature (C6) slips: keep the mezzanine and lesson final as today | Keeps the platform to 14 (walked along), 17 (crossed) and 21 (catwalk). |
| D17 | Level 17 pet cover | Replace the 0.6 m CanapeBas by a 1.0 m low cabinet; Mamie's sit on the loaded chair only if the loaded-sit probe (C9) passes | A loaded chair's top samples are at 1.12 m; a ray from the dog's 0.35 m eye to the ramp foot crosses the cover near face at about 0.78 m, above a sofa. The sit-on-a-loaded-chair combination was never tested. |
| D18 | Level 20 lamp re-teach | Papa's first walk passes the bureau doorway inside his lit cone but beyond his dark range, so switching off is visibly what lets the lamp wait; the hint says sight ranges differ per person | The lamp is absent from slot 6 to slot 19. No new UX code required. |
| D19 | Level 21 floors | Open space stays **hard** with `floorFinish: tile` (grey office floor). Meeting room soft carpet | Keeps hearing in the late game (feedback C7) and the review's "grey office floor". Deviation from act3a. |
| D20 | Robot appearances | 9, 17, 24 only (21 loses its robot, 15 loses its robot) | Cross-group consistency (act3a still listed 10 and 21). |
| D21 | Level 20 exit | West (new garden door in the salon) | act3a's neighbour table was stale. |
| D22 | Names in hints | Hints use the inhabitant names exactly as in the data, in both languages ("Lea", "Theo", "Maman", "Papa", "Alfred", "la Comtesse"); the intro card shows the same names (C3b) | R7. No accents added to data names (tests find inhabitants by name). |
| D23 | Records | Every listed level changes in v2, so every listed level except the new level25 gets `"rev": 1` | A record made on an easier version must not stand (level 13's 8.4 s). Level 13 is "fix", not "keep". |
| D24 | Habit warnings | No new habit warning. Pre-existing accepted: Max (13, hurried, mean dwell 5.75 s) and Hugo (17, teen) | Max's long plateau dwell is the cafeteria choice; making it 2 s rewrites level 13. Recorded. |
| D25 | Night look | `"lighting": "night"` is a schema field (visual only). The preset (C10) lands only after the visual-polish workflow merges; level 20 ships with its blue finishes and `lightWall: none` either way | Main lighting, RoomLights and GardenBackdrop are being edited by that workflow. |
| D26 | Lit zone | Built (C4) for level 20; `requires: ["lit"]` only once C4 + C6 land | The PO's level 20 twist. Optional if it slips. |
| D27 | Player-locked door | Built (C3a runtime, C6 audit) for level 20's `porte_cuisine` | "A door only Dad opens" is otherwise breakable in play. |
| D28 | First-time tips (UX2), relaxed audit, two exits, return goal, walk-in closet, seeded wander per attempt, validator wall-backed rule | Wave 3 | Not needed by any v2 level design. |
| D29 | Hint text fixes | French accents fixed, tokens `{action}`/`{careful}` everywhere a key was hard-coded, "tu" register everywhere | Critic minor, feedback R8. |
| D30 | Margin units | `-slack` samples everywhere (section 10) | Critic minor. |

---

## 3. Final ordered line-up

Exit directions are world directions from spawn to exit. Look = the finish set (wall / floor) in the main rooms.

| Slot | Id | Title EN / FR | Body | Main threat | Plan shape | Exit | Look | Twist | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Act 1** | | **One piece, one rule / Un meuble, une regle** | | | | | | | |
| 1 | level1 | The Living Room / Le salon | chair | one default watcher, facing | 1 room | NE | wallpaper / parquet | first freeze mid-route as he looks at the door | fix (1 dwell) |
| 2 | level2 | The Hallway / Le couloir | chair | hearing, runner rug | L, 2 rooms | NW (mirrored) | quatrefoil / marble hall | tiptoe on the rug behind his back | fix (mirror + marble) |
| 3 | level3 | The Dining Room / La salle a manger | chair | memory + decoys | 2 rooms side by side | E then S | arches / herringbone | park beside the doorway decoy while he walks past | fix (decoy moved, hint) |
| 4 | level4 | The Stool / Le tabouret | stool | seated watcher, careful pace | 2 rooms, bench lane | W (mirrored) | travertine / verde | creep low along the bench | fix (mirror, finish) |
| 5 | level5 | The Armchair / Le fauteuil | armchair | sit deadline | 1 room | NE | sageribbed / lightoak | he sits on you, long enough to feel it | fix (2 dwells) |
| 6 | level6 | The Lamp / La lampe | floor lamp | dark range | L, 2 rooms | N | limewash / herringbone | in his cone, in the dark, nothing happens | fix (station moved) |
| 7 | level7 | The Office / Le bureau | office chair | pacing watcher, glide | long room (rotated) | S | sage / marble | glide to a stop beside a decoy | fix (rotation, dwells) |
| **Act 2** | | **The household / La maisonnee** | | | | | | | |
| 8 | level8 | The Doors / Les portes | chair | Paul at three posts | 4-room loop | SE | wallpaper, limewash, whitetile, arches | first real route choice (two doors) | fix |
| 9 | level9 | The Robot / Le robot | chair | Claire's hearing + robot hum | 3 rooms, one shared lane | W (re-snap mirror, should) else E | arches / parquet, grasscloth / herringbone | ride in the hum, dodge the bumper | fix (kitchen cut) |
| 10 | level12 | The Dog / Le chien | stool | Rex awake (low eye) + Paul | 5-room flat, salon strip | E | wallpaper / parquet, sageribbed / lightoak | sofas hide you from the dog, not from Paul | fix |
| 11 | level11 | The Vase / Le vase | chair + vase | Lea (tidy) on a loop | corridor spine | SE | sageribbed, travertine / herringbone | the last slow turn inside her head turn | fix |
| 12 | level15 | Let Sleeping Dogs Lie / Chien qui dort | rocking chair | napping Rex + Mamie | L with a long hall | E | pinstripe, quatrefoil / parquet, limewash / verde | every stop swings; Rex sees swings | rebuild |
| 13 | level13 | Wheels and a Vase / Roulettes et vase | office chair + vase | Max + Claire | open plan, two loops | SE | carpet / pinstripe, tile | detour behind the receptionist | fix |
| 14 | level14 | The Mezzanine / La mezzanine | armchair | Mamie's sits (soft deadline) + Lea | S over a 2 m mezzanine | SE | sage / lightoak, pinstripe / verde, limewash / ivorytile | the mezzanine is the crossing | fix |
| 15 | level18 | The Wardrobe / L'armoire | stool | Odile, metronome sentinel | tiny L | NW (mirrored) | unchanged | the only safe place is inside the furniture | fix (hold 4.8, mirror) |
| 16 | level17 | The Whole House / La maison | chair + vase | the whole household | 6 rooms, bridge | SE | one finish pair per room | every act 2 rule once | fix (exam) |
| **Act 3** | | **Far from home / Loin de chez soi** | | | | | | | |
| 17 | level19 | Hide and Seek, Family Size / Cache-cache en famille | stool | Maman's beat + Papa wandering | three bands, long gallery, no platform | S | pinstripe / carpet, sage / lightoak, limewash / herringbone | the same wardrobe against two threats | fix |
| 18 | level21 | The Catwalk / La passerelle | office chair | Kevin's back-and-forth + desk watchers | open plan, raised spine | E | grasscloth / tile, arches / carpet | park among decoy chairs at empty desks | fix |
| 19 | level20 | Midnight Munchies / Fringale de minuit | floor lamp | dark ranges of three watchers | ring of lanes off a corridor | W | arches / herringbone, grasscloth / carpet, night | a door only Papa opens; a lit zone | rebuild |
| 20 | level22 | Skeletons in the Closet / Des cadavres dans le placard | stool | Alfred's patrol + door memory | two wings and a gallery | E | sage, sageribbed / herringbone, verde | leave every door as you found it | fix |
| 21 | level25 | The Showroom / Le magasin de meubles | chair | Marcel, wandering night guard | one hall of aisles | W | limewash / ivorytile | nineteen display chairs: freeze only where a chair belongs | new |
| 22 | level24 | The Great Escape / La grande evasion | chair | everyone, Rex on patrol | trunk + two wings | SE | one finish pair per room | the exit stands in a watched room | fix |
| cut | level10 | The Rocking Chair | - | - | - | - | - | lesson moves to level15 | cut |
| cut | level16 | Night Shift | - | - | - | - | - | door beat moves to level20 | cut |
| cut | level23 | Upstairs, Downstairs | - | - | - | - | - | repeat of 18/19 | cut |

(Titles in this table drop French accents only for table width; the strings in section 8 are authoritative.)

`levels.json` order: level1, level2, level3, level4, level5, level6, level7, level8, level9, level12, level11, level15,
level13, level14, level18, level17, level19, level21, level20, level22, level25, level24. Acts start at indices 0, 7, 16.

**Neighbour check** (body / threat / shape / exit / look; at most 2 shared): 7-8 share nothing beyond a south-east lean;
8-9 body; 9-12 nothing (if 9 is not mirrored: exit); 12-11 exit lean; 11-15 exit lean; 15-13 exit lean; 13-14 exit;
14-18 nothing; 18-17 nothing; 17-19 look family; 19-21 nothing; 21-20 nothing; 20-22 nothing; 22-25 nothing; 25-24 body.

**Mechanic coverage after v2**: decoys 3, 7, 13, 21, 25, 24 (late return); sat on 5, 14, 17; vase 11, 13, 17; rocking
chair 15; dog 12, 15, 17, 20, 24; robot 9, 17, 24; wardrobe 18, 19, 22; platform 14, 17, 21; lamp 6, 20; metronome
sentinel 18, 19 only; household door 20, 22, 24 (17 via Mamie); door memory 20, 22.

---

## 4. Shared conventions for wave 2

### 4.1 Audit grid and decoys (D14)

- Audit cells are per room: centres at `room.MinX + (i + 0.5) * 0.5`, `room.MinZ + (j + 0.5) * 0.5`. In every house built
  with rooms starting on 0.5 m multiples, centres are on .25/.75.
- A cell is walkable when a capsule of the body radius (chair 0.28, stool 0.22, armchair 0.45, lamp 0.22, office chair
  0.30, rocking chair 0.36; no skin) clears every Furniture and Occluder collider, including decoy boxes (body footprint).
- A decoy explains a cell within 0.6 m (0.75-tolerance watchers only; watchful 0.4, tidy 0.32: chair and office-chair
  decoys never fool watchful or tidy watchers in the audit).
- **Recipe**: decoy centre = walkable cell centre + 0.55 m along one axis (0.59 m for the office chair), other axis
  equal. Run `python docs/levels_v2/tools/decoy_cells.py Assets/Resources/Levels/levelN.json` and keep at least one
  "ok" cell per decoy the route needs. The script ignores door gaps (a doorway cell may show "wall" wrongly).
- No designed rest cell within 0.6 m of an inhabitant walk segment (people walk through furniture, IDEAS bug 1). C5 adds
  an audit warning for it.

### 4.2 Exact mirror and rotation

- Mirror about x = 0: x -> -x, every yaw and facing f -> (360 - f) mod 360, every glance yaw g -> -g, door `hinge`
  start <-> end, door `swing` unchanged (it names a room). Rotation +90: (x, z) -> (z, -x), f -> f + 90, sizes swap.
- Exact only when every room size along the mirrored axis is a multiple of 0.5 m (true for levels 2, 4, 7, 18).
  Verify: the mirrored audit must reproduce the original exit time and pause pattern (mirrored). If not, revert.

### 4.3 Re-snap mirror (level 9 only)

For houses with x.4/x.9 room widths: let W = (house min x) + (house max x) over the room boxes. Room boxes, walls, doors
and windows set in vertical walls (constant x) and wall-backed props against vertical walls use x' = W - x. All other
points (stations, spawn, exit, robot waypoints, decoys, rug centres, doors/windows set in horizontal walls, free props)
use x' = W + 0.1 - x so they land back on cell centres. Then audit: this is a retune, not an exact symmetry.

### 4.4 Palette rule

A room's (wallFinish, floorFinish) pair must not repeat in either neighbouring level. Room types keep fiction (no
parquet in an office, tiles in kitchens) but kitchens are not all subway tile. `floorColor`/`wallColor` may be updated
for the miniature only. Carpet is allowed on soft floors only; changing `floor` soft/hard is a gameplay change and is
listed explicitly where it happens.

### 4.5 Working procedure for a level task

1. Copy the level file to `Build/levels_v2/variants/<id>_wip.json` (outside Assets). Edit there.
2. Validate and audit the variant by absolute path without `.json`:
   `pwsh -NoProfile -File tools/unity.ps1 -Agent <task> -UnityArgs "run . --timeout 3000 -- -executeMethod OutOfSight.Editor.LevelAudit.RunBatch -auditLevels C:/Dev/squad-ai/Brainstorming/games/meuble/Build/levels_v2/variants/<id>_wip -skipFixtures -difficulty normal,difficile -slack -strictRooms -json Build/levels_v2/<task>.json -logFile Build/<task>.log"`
   (`-strictRooms` and `-json` exist once C5 lands; before that, drop them and measure pace with `docs/levels_v2/wave1/numbers.py`.)
   Never `-writeRoutes` on a variant. Batch several variants in one call (comma list) to save Unity launches.
3. Apply the knobs listed in the level section, in order, one or two per run. At most 6 audit runs per level before
   escalating with a report (the Unity lock is shared by every agent).
4. When the targets hold: copy into `Assets/Resources/Levels/<id>.json`, run once with `-auditLevels <id> -writeRoutes`,
   then once more without it to confirm the written routes replay (no "route perimee" note).
5. Report: final numbers (exit, share, pauses, longest pause, slack, lessons, requires, vias, dead rooms, budgets) for
   both difficulties, plus the list of test premises your change breaks (file, test name, what changed). Do not edit
   tests: task T1 owns them.

General rules: PowerShell only (Git Bash hangs), only the lock wrapper for Unity, never kill another Unity process, no
git write commands, English, no em-dash character anywhere, edit on top of the visual-polish workflow's uncommitted
changes (never revert them).

---

## 5. Per-level specifications

Notation: "pace" = the JSON `pace` field to add (C1/C5): `{ "minShare", "maxShare", "minPauses", "maxPause" }`.
"slack" = the `-slack` maximum margin band in samples at Normal (Difficile at least 4 unless stated).

### Act 1

#### level1 - The Living Room (slot 1, fix)
- Base: design_act1 level1. Change only `inhabitants[0].stations[2].dwell` 5.0 -> 3.5. Fallback 4.0 if slack < 12.
- Add `"rev": 1`, `"pace": {"minShare": 0.12, "maxShare": 0.35, "minPauses": 1, "maxPause": 6.0}`.
- Targets: exit 9-12 s at both difficulties; at least one pause of 1.5 s or more; slack >= 15 (fallback >= 12); the
  full-speed straight rush from t = 0 loses (C7 probe); late-start sweep: no forced wait above 8 s (the warning on
  levels 1, 2, 3, 5, 7 should disappear once the held start makes t = 0 the first input; the sweep itself stays).
- Correction recorded: none of the three props hides the chair (top samples 0.87 m, sofa 0.85, table 0.75, bookshelf
  flush on the wall): level 1 is pure facing.
- Hint unchanged. Docs: amendment to CONTRACT_M2 11.8 and PRD 6.3 (task I1). Test LevelDataM2Tests
  `Level1_keeps_its_stations_start_and_props` expects 3.5 (task T1).

#### level2 - The Hallway (slot 2, fix)
- Base: design_act1 level2 (full mirror list). Couloir `floorFinish: "marble"`.
- `"rev": 1`, `"requires": ["rug"]`, pace `{0.15, 0.35, 1, 6.0}`.
- Targets: exit 12-15 s; spawn pause >= 2 s; >= 20 rug samples within earshot; slack >= 12; the waits-removed route loses.
  The mirrored audit must equal the original (mirrored); otherwise revert the mirror and keep only the marble.

#### level3 - The Dining Room (slot 3, fix)
- Base: design_act1 level3, **override the decoy**: `decoys[4]` -> `(0.77, 0.25)`, yaw 0 (critic fix; checked:
  explains exactly cell (0.25, 0.25) at 0.52 m with 0.295 m capsule clearance; it is 1.02 m from the watcher's doorway
  walk line). Fallbacks in order: (0.76, 0.25) if the validator rejects the wall clearance (box edge 5 mm from the
  wall); then (0.75, -0.30), which explains (0.75, 0.25) but breaks the LevelDataM2 doorway-decoy bound (T1 widens it).
- `"rev": 1`, `"requires": ["decoy"]`, pace `{0.35, 0.52, 2, 6.0}` (the wait is the joke).
- Targets: exit 17-21 s; 2 pauses (spawn + decoy rest), decoy rest <= 6 s; >= 15 explained samples; rest cell >= 0.6 m
  from every walk segment (C5 warning absent); slack 8-12; rush loses.
- Hint (S1): new memory hint, section 8.

#### level4 - The Stool (slot 4, fix)
- Base: design_act1 level4 (mirror list; salon loses herringbone -> default parquet).
- `"rev": 1`, lesson careful (unchanged), pace `{0.25, 0.45, 2, 6.0}`.
- Targets: exit 14-16 s; route 100 % careful, 0 topples in replay; slack 8-12; revert mirror if not exact.
- Hint with `{careful}` (S1).

#### level5 - The Armchair (slot 5, fix)
- Base: design_act1 level5: sit station dwell 0.5 -> 1.5; TV station dwell 8.0 -> 6.5.
- `"rev": 1`, lesson sit, pace `{0.25, 0.50, 2, 6.0}` (pinned time excluded).
- Targets: exit 16-20 s; pinned >= 2.0 s with no pratfall; home pause (excluding pinned) <= 6 s; Step35b rush loses;
  slack 8-12.

#### level6 - The Lamp (slot 6, fix)
- Base: design_act1 level6: station 0 -> (2.0, 0.6) facing 270, dwell 10.0, glances `[{3.0, 40, 1.0}, {7.0, -40, 1.5}]`
  (the review's (2.0, -0.25) is inside the CoffeeTable). Bedroom walls arches, floor default parquet.
- `"rev": 1`, lesson dark, pace `{0.12, 0.32, 1, 6.0}` with at least one mid-route pause of 2-5 s.
- Targets: exit 18-22 s Normal (Difficile within 2 s); exactly 1 toggle (C5 collapse); the dark-boundary pause happens
  with station 0's lit cone on the lamp and the lamp beyond 4.0 m (C5's synchronised dark check prints it); slack 8-15.
- Knobs: station 0 dwell 9.5; spawn to (-3.25, -3.85).
- Hint with `{action}` (S1).

#### level7 - The Office (slot 7, fix)
- Base: design_act1 level7: rotation +90 (full list), dwells 2.5 -> 2.0, walls sage, floor marble (hard).
- `"rev": 1`, lesson glide, pace `{0.35, 0.55, 2, 6.0}`.
- Targets: exit 18-22 s; spawn wait <= 6 s; >= 3 glide stops; >= 10 explained samples; slack 6-10; decoy check:
  `decoy_cells.py` reports one ok cell per decoy (rotation maps (-2.25, 1.25) to (1.25, 2.25) etc.).

### Act 2

#### level8 - The Doors (slot 8, fix)
- Base: design_act2a level8 (startStation 1; Paul's three stations retuned; sofa dwell 12 with head turns -70 and +80).
- **Overrides**: salon keeps `wallFinish: "arches"` (not sage: level 7 is sage/marble) with `floorFinish: "lightoak"`;
  other rooms as the base (chambre wallpaper/lightoak, couloir limewash/parquet, cuisine whitetile/tealtile).
- `"rev": 1`, lesson door, pace `{0.22, 0.45, 3, 6.0}`.
- `"viaChecks"`: `[{"name": "par_la_cuisine", "x": 3.75, "z": 1.75, "sizeX": 1.0, "sizeZ": 1.0, "maxRatio": 1.35},
  {"name": "par_le_couloir", "x": 7.25, "z": 7.75, "sizeX": 1.0, "sizeZ": 1.0, "maxRatio": 1.35}]` (a zone is the set of
  cells whose centre lies inside it; the route must visit one of them). Until C6 lands, prove both routes with the base's
  two variant files (`level8_viaA`, `level8_viaB`).
- Targets: exit 15-21 s (soft); both routes viable within 1.35x; the main schedule waits for the sofa head turn to 110
  before the doormat; slack 7-10; rush counter-routes (waits removed; corridor straight at 6 s) lose.
- Knobs: sofa dwell 12, its head turn to 260 hold 3.0 -> 2.0, window post dwell 7.

#### level9 - The Robot (slot 9, fix)
- Base: design_act2a level9 (kitchen deleted with its door, window and two props; Claire startStation 1, glances
  +-80 hold 2.0; robot lane z 8.25 from x 5.25 to 11.25 at speed 0.5; salon rug removed).
- **Overrides**: chambre `wallFinish: "arches"`, **no floorFinish** (default parquet); salon grasscloth / herringbone;
  entree unchanged. Optional mirror (D13, section 4.3) after the unmirrored version passes; revert if 3 audit runs fail.
- `"rev": 1`, lesson robot, `"requires": ["hum"]`, pace `{0.22, 0.45, 4, 6.0}`.
- Targets: exit 15-22 s; >= 40 masked samples; no robot contact on the route; all 3 rooms on the route; slack 6-9;
  rush (crossing the band at full speed from 6 s) loses. Difficile and one shifted start checked by hand (sweep off).
- Knobs: robot speed 0.5 -> 0.4; Claire's glance hold 2.0 -> 2.5.
- Code: hum disc (C8) strongly recommended.

#### level12 - The Dog (slot 10, fix)
- Base: design_act2b level12 (sofas resized into CanapeOuest + CanapeMilieu, PlanteSalon added, Rex on four facings at
  (7.25, 3.5), Paul startStation 1, station 2 faces north dwell 4).
- **Overrides (palette)**: chambre wallpaper / default parquet (no lightoak); salon **keeps sageribbed** walls with
  `floorFinish: "lightoak"` (level 9 next door is grasscloth/herringbone); couloir limewash/lightoak; cuisine
  limewash/tealtile; entree `wallFinish: "quatrefoil"`, `floorFinish: "verde"`.
- `"rev": 1`, lesson pet, pace `{0.22, 0.45, 3, 6.0}`.
- Targets: exit 18-26 s (Difficile within +6 s); pet binds; 3+ pauses (spawn, CanapeOuest, CanapeMilieu); slack 6-9;
  waits-removed rush loses; no dead room (cuisine holds Paul station 0).
- Knobs in order: Rex D0 dwell, D0b dwell, Paul station 2 dwell, Paul Canape dwell; CanapeMilieu x 7.35 if Paul's walk
  does not fit gap 1.
- Tests (T1): Step45b made time-aware, Step45g redrawn.

#### level11 - The Vase (slot 11, fix)
- Base: design_act2a level11 (Lea startStation 1; station 2 moved to (10.75, 2.75) facing 270 dwell 6; station 0 faces
  south dwell 10 with head turn 80 hold 2.5; station 3 dwell 8). Finishes as the base. Remove the unused salon rug.
- `"rev": 1`, lesson load, pace `{0.22, 0.45, 3, 6.0}`.
- Targets: exit 19-27 s; the last leg into the doormat is careful and starts inside the head turn to 260; slack 5-8;
  rush counter-routes lose (leave at 0.3 s; waits removed; drop the vase at the spawn then full speed).
- Knobs: Lea station 2 dwell 6 -> 5; station 0 glance hold 2.5; waiting spot (9.75, 1.25).

#### level15 - Let Sleeping Dogs Lie (slot 12, rebuild)
- Base: design_act2a level15 (4 rooms: bureau, salon, cuisine, entree; robot deleted; Claire and Hugo replaced by Mamie
  (granny loop, 3 stations, sits on Canape) and Rex napping at (11.75, 1.25) facing west; lesson rock).
- **Overrides**: salon `wallFinish: "quatrefoil"` with **no floorFinish** (default parquet) instead of herringbone
  (level 11's corridor is herringbone); bureau pinstripe / parquet; cuisine subwaytile / ivorytile; entree limewash / verde.
  Slot is 12 (D4), after the dog lesson.
- `"rev": 1`, lesson rock (no advisory), pace `{0.22, 0.45, 4, 6.0}` with rocks counted as travel.
- Targets: exit 19-28 s; rock binds; >= 3 rocks in Rex's view; Mamie never sees the chair out of place; all 4 rooms used;
  materials <= 24, draw calls <= 120; slack 5-8; rush (hall in one go; stops at the end of each nap) loses; spawn wait <= 6 s.
- Knobs: Rex asleep 3.5 / awake 1.8; Mamie M0 dwell 3.5; Rex at (11.25, 1.25) if the doormat pass reads badly.

#### level13 - Wheels and a Vase (slot 13, **fix**, was "keep")
- Base: design_act2b level13 (Max station 1 to the front desk (11.75, 1.75) facing 270 dwell 3.5, station 0 dwell 8;
  Claire station 1 faces 180 dwell 5; decoys unchanged at x 2.84 / 5.84; plateau and couloir floors tile).
- `"rev": 1` (kills the 8.4 s record), lesson load, decoy gate implicit, pace `{0.22, 0.45, 4, 6.0}`.
- `"viaChecks"`: `cafeteria` zone (12.25, 3.75) 1 x 1 (inside the cafeteria, before door (12.25, 2.95)) and `direct` zone
  (9.25, 1.25) 1 x 1 (plateau side of door (9.95, 1.25)), `maxRatio` 1.5.
  Until C6, the two variant files of the base (`level13_noDirect`, `level13_noCafe`).
- Targets: exit 23-32 s Normal, Difficile <= 50 s; >= 8 explained samples (Max only); slack 5-7; the three rush
  counter-routes lose (waits removed; straight full speed; drop the vase then full speed). Max's habit warning accepted (D24).
- Knobs: Max station 1 dwell 2.5, Claire station 1 dwell 6.

#### level14 - The Mezzanine (slot 14, fix)
- Base: design_act2b level14 (mezzanine 2.0 m wide, both ramps replaced on audit cell lines, Lea station 1 into the
  kitchen, Mamie dwells 3 / 2.5 (sit) / 12 / 12).
- **Overrides**: entree `wallFinish: "limewash"`, `floorFinish: "ivorytile"` (level 13's accueil is travertine/marble);
  couloir `wallFinish: "pinstripe"`, `floorFinish: "verde"`. Second sit = soft deadline (D8).
- `"rev": 1`, lesson split, `"requires": ["sit"]` only if it binds (else omit), pace `{0.22, 0.45, 4, 6.0}`.
- Targets: exit 36-50 s; second sit 6-10 s after the strict exit; >= 7 route cells on the top; slack 5-8 (must stay above
  level 17's); Difficile within +8 s; rush loses.
- Knobs: Mamie station 2 and 3 dwells (never the route); Lea's wander seed or her station dwell 6.

#### level18 - The Wardrobe (slot 15, fix)
- Base: design_act2b level18, **override hold 5.0 -> 4.8** in all 34 glances (fallback 4.7 if slack > 7). Then the
  exact mirror x -> -x (D13; all room sizes are multiples of 0.5), so the exit turns NW. Glance yaws -80 -> +80.
  Keep the hand-written glance list (the C1 glanceEvery test uses a fixture copy of the old list).
- `"rev": 1`, lesson wardrobe, pace `{0.30, 0.50, 2, 6.0}`.
- Targets: exit 18-24 s; hide 3.5-5.5 s; spawn or doorway wait <= 5 s; slack 5-7 (above level 17's); Step56a stays
  green after T1 mirrors its coordinates.
- Hint with `{action}` (S1).

#### level17 - The Whole House (slot 16, act 2 exam, fix)
- Base: design_act2b level17 (Mamie 5 stations with a sit on the player at the spawn and porte_bureau opened by
  inhabitants; Rex awake 12.4 / asleep 6 at (7.0, 1.0) facing 340; Lea station 0 faces 30 dwell 12, station 2 dwell 9;
  robot unchanged; one finish pair per room).
- **Overrides**:
  - Replace CanapeBas by `{"name": "BuffetBas", "kind": "cabinet", "x": 6.0, "z": 3.05, "yaw": 0, "sizeX": 1.8,
    "sizeY": 1.0, "sizeZ": 0.45, "occluder": true}` with colours already used in the level (materials 29/32). Check by
    ray before the audit: from the dog's eye (7.0, 0.35, 1.0) to each of the 5 loaded sample points (top at 1.12 m)
    along the north lane and the ramp W foot, the ray must cross the cabinet below 1.0 m (hand check: 0.78 m at the ramp
    foot, 0.86 m at z 3.75).
  - Mamie's sit on the loaded chair (s1) stays only if probe C9 passes. Fallback: drop s1 (Mamie still walks past and
    opens porte_bureau), and requires keeps the other ids.
  - Palette: couloir `wallFinish: "limewash"`, floor verde (level 18's hall is travertine/verde); entree
    `wallFinish: "grasscloth"`, floor marble (level 19's entree is quatrefoil/marble). Others as the base.
- `"rev": 1`, lesson final, `"requires": ["door", "pet", "split", "hum", "load"]`, pace `{0.22, 0.45, 5, 6.0}`.
- Targets: exit 27-37 s (soft); 5+ pauses; every requires id binds (pet is the new one); the route passes within 2.5 m of
  the robot while within 2.25 m of Lea; **slack 4-5, the lowest of act 2**; materials <= 32, draw calls <= 160; Difficile
  within +8 s; waits-removed rush loses; Step57b premise holds.
- Knobs in order: Lea s2 dwell, Rex nap, Lea s0 dwell, robot start index; Mamie s4 dwell 26 if exit > 40 s.

### Act 3

#### level19 - Hide and Seek, Family Size (slot 17, fix)
- Base: design_act3a level19 (bathroom deleted; mezzanine, ramps and three props deleted; salon and gallery hard;
  kitchen opened on the gallery and closed from the entree; Maman one station with her 42 glances; Papa sofa + stove loop).
- No overrides. Maman's glances may be rewritten with `glanceEvery` (C1) if identical after expansion.
- `"rev": 1`, lesson wardrobe, pace `{0.22, 0.45, 5, 6.0}` (4 mid-route), hides counted as waiting.
- Targets: exit 46-62 s Normal, Difficile 55-80 s; route <= 38 m; >= 2 hides Normal, >= 3 Difficile; at least one pause
  timed on Papa in the salon and one moment where Papa is in the gallery while the route hides; slack 5-7; draw calls
  about 105-115; rush (waits removed; straight) loses.
- Knobs: Papa P0 dwell 12 -> 14, P1 8 -> 10; TableSalle 0.5 m; Maman's first glance offset.
- Tests (T1): Level19Lesson no longer "climbs the mezzanine": wardrobe, hides >= 2 (Normal), leaves == hides.

#### level21 - The Catwalk (slot 18, fix)
- Base: design_act3a level21 (spawn in the meeting room; porte_cafet leaf deleted; robot deleted; bookcases cut into two
  gaps; two empty desks with decoys D1 (13.75, 6.34), D2 (15.75, 6.34); Bertrand, Sofia and Kevin replaced).
- **Override (D19)**: openspace stays `floor: "hard"` with `floorFinish: "tile"`, walls grasscloth. Meeting room soft
  carpet + grasscloth, bureau carpet + arches, couloir tile + limewash, archives carpet + sageribbed, hall marble +
  travertine, cafet unchanged.
- Decoys checked with `decoy_cells.py`: each explains exactly one lane cell ((13.75, 5.75), (15.75, 5.75)) at 0.59 m. Do
  not round them.
- `"rev": 1`, lesson split, `"requires": ["decoy"]`, pace `{0.22, 0.45, 6, 6.0}` (5 mid-route).
- `"viaChecks"`: `par_le_bureau` zone (1.25, 8.25) 1 x 1 (bureau side of door (1.25, 7.45)) and `par_le_couloir` zone
  (5.25, 3.25) 1 x 1 (couloir side of door (4.45, 3.25)), `maxRatio` 1.6. Until C6, the base's two variant files.
- Targets: exit 27-38 s (soft; the base's 40-60 s is withdrawn, D5); >= 8 explained samples; the route stands on a west
  gap cell and an east gap cell while the matching watcher could turn to it within 3 s; no habit warning; slack 5-7;
  draw calls <= 160 (cut order: TableCafet, EtagereDirecteur, shorter Rayonnage); rush loses.
- Knobs: Kevin K1 dwell 1.5 -> 1.0 or K1 z 7.75 (decoy-free schedule exists); K1 z 8.75 or longer K0 (no schedule); K0
  dwell 2.0 -> 1.5 if share > 45 %.

#### level20 - Midnight Munchies (slot 19, rebuild)
- Base: design_act3b level20 (spawn in the bureau; exit at a new west garden door; salon-kitchen gap; porte_salon leaf
  next to Maman; porte_cuisine opened by Papa; porte_entree deleted; three wardrobes deleted; Maman pingpong in the
  corridor, Papa four-station loop, Rex entree <-> salon).
- **Overrides**:
  - D18 re-teach: Papa's P0 -> P1 walk must pass the bureau doorway at 4.0-7.0 m from the lamp's first waiting cell
    (inside his 8 m lit range, beyond his 3.2 m dark range) while his cone covers it; the first designed pause is that
    beat. Knob: Papa P0 dwell.
  - `porte_cuisine`: add `"playerLocked": true` (C1/C3a/C6).
  - `"litZones": [{"name": "lumiere_bureau", "x": 11.25, "z": 6.2, "sizeX": 1.5, "sizeZ": 2.4}]` once C4 lands (the
    study light left on). The lit crossing must stay shorter than Maman's back-turned window minus 0.6 s.
  - `"lighting": "night"` (visual only; harmless before C10).
  - cuisine `wallFinish: "whitetile"`, `floorFinish: "tile"` (level 21's cafet is subwaytile/tile).
- `"rev": 1`, lesson dark, `"requires": ["household"]` + `"lit"` when C4 is in, pace `{0.22, 0.45, 4, 6.0}` (3 mid-route).
- Targets: exit 47-63 s Normal, Difficile 3-10 s later; route 18-22 m; exactly 1 toggle (C5 collapse); the route passes
  the kitchen door front while Maman is 3.5-4.6 m away; enters the kitchen after Papa opened it; never opens porte_salon;
  every room holds a station or a route cell; slack 4-8; budgets <= 160 / 32.
- Knobs in order: Rex R0 dwell; Papa P0 dwell; Maman M2 x 5.25-6.25; Maman dwells; Papa P1 dwell.

#### level22 - Skeletons in the Closet (slot 20, fix)
- Base: design_act3b level22 (pantry door to galerie_est; FauteuilMamie into the boudoir; ArmoireOffice in the pantry;
  gallery rug shortened; Comtesse pingpong over three stations; Alfred real patrol; Mamie boudoir / gallery / salon loop;
  manor finishes).
- No overrides.
- `"rev": 1`, lesson wardrobe, pace `{0.22, 0.45, 5, 6.0}` (4 mid-route; Difficile max pause 6.0 is a note).
- `"viaChecks"`: `aile_sud` zone (14.75, 4.25) 1 x 1 (pantry side of porte_office: the door-memory twist must be playable)
  and `aile_nord` zone (18.25, 10.75) 1 x 1 (gallery east of the library door), `maxRatio` 1.5 each.
- Targets: exit 41-56 s Normal, Difficile <= +20 s; >= 2 hides of 3-6 s and no hide/leave pair under 2 s (C5 collapse);
  no habit warning for Alfred, the Comtesse or Mamie; humans 0.6 m apart; slack 4-6; budgets <= 145/160, <= 31/32.
- Knobs: Alfred A2 dwell; Mamie M0 dwell; Comtesse C2 dwell; Alfred A1 z; Mamie M2 facing 225.

#### level25 - The Showroom (slot 21, new)
- Base: design_act3c level25, **with these geometry overrides (D14, checked with decoy_cells.py: 19 decoys, 19 explained
  walkable cells)**:
  - magasin: `x 9.95, z 6.0, sizeX 14.9, sizeZ 12.0` (x 2.5-17.4). reserve: `x 19.2, z 6.0, sizeX 3.4, sizeZ 6.0`
    (x 17.5-20.9, cells on .25/.75). Stockroom door `x 17.45, z 6.25, width 1.5`.
  - player `(19.75, 6.25)` yaw 270.
  - TableOuest `(8.25, 3.0)`, TableEst `(12.25, 3.0)` (both 1.6 x 0.75 x 0.9).
  - Cartons at x 20.3 (inside the narrower stockroom).
  - Decoys (all `kenney.chair`, kind chair, colour #8C5A36), explained cell in brackets:
    - west dining: (7.75, 2.30, 0) [7.75, 1.75], (8.75, 2.30, 0) [8.75, 1.75], (7.75, 3.70, 180) [7.75, 4.25], (8.75, 3.70, 180) [8.75, 4.25]
    - east dining: (11.75, 2.30, 0), (12.75, 2.30, 0), (11.75, 3.70, 180), (12.75, 3.70, 180) [same pattern]
    - NW sale row: (7.75, 8.30, 180), (8.75, 8.30, 180), (9.75, 8.30, 180) [z 7.75]
    - NE sale row: (11.75, 8.30, 180), (12.75, 8.30, 180), (13.75, 8.30, 180) [z 7.75]
    - lobby: (3.75, 4.80, 0), (4.75, 4.80, 0), (5.75, 4.80, 0) [z 4.25]
    - new arrivals: (19.75, 5.20, 270) [19.75, 5.75], (19.75, 7.30, 270) [19.75, 6.75]
  - NW rug centred on (8.75, 8.3).
  - Marcel (hurried, wander, seed swept 1-12) dwells G0 2.5, G1 2.0, G2 1.5, G3 2.0, G4 1.5, G5 1.5, G6 2.5 (mean 1.93 s,
    no habit warning).
  - Nina (teen, loop): glances +-25 deg (the teen warning fires at 30 deg or more).
- Fields: no `lesson`; `"requires": ["decoy"]`, `"doorMemory": false`, pace `{0.25, 0.45, 6, 6.0}`. `"viaChecks"`: south
  lane zone (10.5, 0.75) 1 x 1 and north lane zone (10.5, 11.25) 1 x 1, `maxRatio` 1.5.
- Targets: exit 24-36 s Normal (soft; the base's 45-70 s is withdrawn, D5), Difficile solvable within +20 s; >= 40
  explained samples; no schedule without decoys (the gate); all 3 rooms used; budgets <= 110/120 draw calls, <= 22/24
  materials; audit < 60 s; slack 4-6; rush loses. Record the chosen seed in the task report.
- Fallback: Marcel `loop` over G0 G1 G5 G2 G3 G6 G4 and the hint drops "at random"; drop Nina if share > 45 %.
- Also: add `"level25"` to `levels.json` between level22 and level24 (after C2), strings in section 8.

#### level24 - The Great Escape (slot 22, fix)
- Base: design_act3c level24 (chair body; kids' room and bathroom deleted; salle shrunk into Mamie's salon; couloir_est
  split by the new palier; Rex pingpong on the landing; Theo, Mamie, Lea retuned; robot 3-point loop in the hall).
- **Overrides**:
  - Decoys (critic fix, checked: 4 decoys, 4 explained walkable cells): (5.25, 4.80, yaw 0) [5.25, 4.25], (6.75, 4.80, 0)
    [6.75, 4.25], (5.25, 6.20, 180) [5.25, 6.75], (6.75, 6.20, 180) [6.75, 6.75]. TableSalle stays (6.0, 5.5) 1.6 x 0.9.
  - D16: delete the Mezzanine platform and both ramps; galerie becomes a plain dining room (type dining, lightoak /
    sageribbed). Requires C6. Fallback: keep them and lesson final as in the base.
  - Lea at E1 facing the doormat check: arrival on the doormat while Lea is in the hall (exitwatch binds).
- `"rev": 1`, lesson final, `"requires": ["door", "pet", "decoy", "hum", "exitwatch"]` (if hum does not bind, use
  `contact`), pace `{0.25, 0.45, 8, 6.0}`.
- `"viaChecks"`: `aile_nord` zone (14.25, 9.75) 1 x 1 (palier) and `aile_sud` zone (12.75, 1.75) 1 x 1 (Mamie's salon),
  `maxRatio` 1.35.
- Targets: exit 32-46 s Normal (soft), Difficile within +20 s; 8+ pauses; >= 10 explained samples (hub) and >= 10 hum
  samples (hall); every one of the 8 rooms holds a route cell or a station; **slack 4-5, the lowest of act 3**; budgets
  <= 150/160, <= 31/32; rush (waits removed; straight) loses; audit 60-90 s, run alone.
- Knobs in order: Theo G1 dwell and glances; Mamie M1 dwell; Lea E1/E2; Rex A dwell 10 or B at (11.75, 12.25).

### Cut levels

- **level10, level16, level23**: removed from `levels.json` only. Files, strings and Strings.cs members stay. Tests that
  load them by id keep working; tests that require them to be listed are retargeted or deleted (T1). Their ids are never
  reused. Saves keep them in `won`/`best` as harmless orphans (the progress line counts listed ids only).

---

## 6. Code features in scope for wave 2

Full designs with file and line references: `wave1/code_features.json`. Scope decisions:

| Id | Feature | Priority | Owner files | Used by |
|---|---|---|---|---|
| C1 | Schema v2: `rev`, `requires`, `pace`, `viaChecks`, `litZones`, `lighting`, `OpeningDef.playerLocked`, `StationDef.glanceEvery` (expanded in `LevelJson.Parse`), new lesson ids (`rug`, `hum`, `contact`, `household`, `decoy`, `exitwatch`, `lit`), `ManifestDef`/`ActDef` + `LevelManifest.ParseFull`; validation of all of them | must, first | LevelDef.cs, LevelValidator.cs | every level task (unknown keys fail to load: MissingMemberHandling.Error) |
| C2 | Progression v2: `levels.json` rev 2 with `previous` and `acts`, save `unlocked` + `order`, new unlock rule, one-shot migration, record keys with rev (`level6~1@difficile`), level select default on the first unwon card, act tags | must | SaveData.cs, SaveStore.cs, LevelLoader.cs, RecordLine.cs, LevelSelect.cs, levels.json, CoreM5Tests.cs, SaveM5Tests.cs, DifficultyM7Tests.cs, ProbeTestsM5Ui.cs | all |
| C3a | Held start (GameState.Started, HoldStart off under probes/test runs, ReleaseStart for replays) + player-locked leaf runtime | must | GameState.cs, InputReader.cs, RouteReplayer.cs, new ProbeTestsHeldStart.cs | all, level 20 |
| C3b | HUD: card held until start + "Move to start", inhabitant names on the card, hint tokens `{action}`/`{careful}` per device, locked-door hint, lit-zone hint, exit marker over walls (door icon, amber, edge-clamped, fades within 3 m, eye glyph when a human sees the player on the exit) | must (marker should) | Hud.cs, new ProbeTestsHudV2.cs | all |
| C4 | Lit zones runtime: `SightRangeFactor` = 1 in a zone, LampLight skips zone lights, fixture + unshadowed spot + floor pool | should | FurnitureController.cs, LampLight.cs, LevelBuilder.cs (one hook), new LitZoneView.cs | level 20 |
| C5 | Audit A: pace metrics + `pace` gate, pinned time apart, dead rooms + `-strictRooms`, `-json` report, collapse in-place toggle and hide/leave flicker runs, rest-on-walk-line warning, time-synchronised facing-aware dark check | must | LevelAudit.cs (first), test_v2_audit_*.json fixtures | all |
| C6 | Audit B: `requires` list with the new ids, `viaChecks` (MustVisit), player-locked leaves (no reach cells, failure if never opened), lit cells, `exitwatch` | must (lit, exitwatch should) | LevelAudit.cs (after C5), test_v2_req_*.json fixtures | 2, 3, 8, 9, 13, 17, 20, 21, 22, 24, 25 |
| C7 | Rush counter-route probe over every listed level (waits removed; vase drop + rush; straight path), category Slow, documented exemptions | should | new ProbeTestsRush.cs, RouteReplayer.cs (after C3a) | all |
| C8 | Robot hum disc (radius = Tuning.RobotHumRadius) + hum audio max distance about 3.5 m | should | Robot.cs, Sfx.cs | 9, 17, 24 |
| C9 | Loaded-sit probe: a sitter on a chair carrying a vase; assert the vase holds and sits sensibly | must (gates level 17's sit) | new ProbeTestsLoadedSit.cs, test_v2_loaded_sit.json | 17 |
| C10 | Night lighting preset (`lighting: night`, visual only) | should, after the visual-polish workflow merges | Main.cs, RoomLights.cs, GardenBackdrop.cs, WindowImage.cs | 20 |

Deferred to wave 3 (D9, D28): timed-return goal, two exits, relaxed audit, first-time tips (UX2), seeded wander per
attempt, walk-in closet, wall-backed validator rule, new finish slices, deliberate-alert audit for lures.

Landing order: C1 -> (C2, C3a, C5, C8, C9, S1 in parallel) -> (C3b after C3a; C6 after C5; C7 after C3a; C4 after C1)
-> level tasks -> T1 -> I1. Level tasks may start right after C1 with the interim measuring script (section 4.5) and
must re-verify after C5/C6.

Mutation tags (I1 adds the mutation.sh lines from each task's report): UNLOCK_WON, UNLOCK_MIGRATED, MIGRATE_PREDECESSOR,
HOLD_START, LIT_FACTOR, LOCKED_LEAF, PACE_PAUSE, REQUIRES_BIND, VIA_MUSTVISIT.

---

## 7. Progression and save migration

- `levels.json`: `{ "rev": 2, "previous": [the 24 v1 ids in v1 order], "levels": [section 3 order], "acts": [{"from": 0,
  "nameKey": "act1.name"}, {"from": 7, "nameKey": "act2.name"}, {"from": 16, "nameKey": "act3.name"}] }`. C2 writes it
  with 21 entries; LV12 inserts `level25` once its level passes.
- `LevelManifest.Parse(json) -> List<string>` stays; `ParseFull` returns the rest. Unknown manifest keys are ignored today.
- Save: `unlocked` (list of ids, missing = empty) and `order` (manifest rev applied, missing or < 1 reads as 1). Save
  version stays 1. A wrong-typed `unlocked` is a parse problem like `won`.
- Unlock rule: index i is playable when i == 0, or order[i] is won, or order[i-1] is won, or order[i] is in `unlocked`.
- Migration (once, on load, when `order` < manifest rev): every id of `previous` that was playable under the previous
  rule (index 0 or its predecessor in `previous` won) and is still listed joins `unlocked`; then `order` = rev and the
  save is written atomically with the log line `[SaveStore] progress migrated to order rev 2: +N unlocked`. Nothing is
  removed from `won` or `best`.
- Worked cases with the v2 order: (1) won level1-level10: level12 (slot 10) opens after level9, level11 opens through
  `unlocked` (its v1 predecessor level10 is won), level15 stays locked. (2) won level1-level17 except level18: level18
  opens after level14, level17 is won, level19 opens after level17. (3) fresh save: only level1. (4) a migrated save
  loaded again: no change, no write.
- Records: `RecordId = rev > 0 ? id + "~" + rev : id`; best times stored under `DifficultyDef.RecordKey(RecordId, d)`;
  `won` keeps the bare id. Old bare-id records stay in the file, unread.
- Level select: default selection = the card of `SaveStore.FirstUnwonLevel`; act tag on the first card of each act;
  22 cards in the existing 6-column grid.

---

## 8. Strings (task S1 owns Core/Strings.cs)

All "tu" register, French accents correct, no em-dash, names as in the data (D22). `{action}` and `{careful}` are
resolved per device by C3b.

| Key | EN | FR |
|---|---|---|
| act1.name | One piece, one rule | Un meuble, une règle |
| act2.name | The household | La maisonnée |
| act3.name | Far from home | Loin de chez soi |
| hud.start (+ pad/touch variants) | Move to start | Bouge pour commencer |
| hud.door.locked | Locked | Fermée à clé |
| hud.lit | In the light: the dark won't hide you | Dans la lumière : le noir ne te cache plus |
| hud.person (format) | {0}, {1} (name, personality label) | {0}, {1} |
| level3.hint | They remember where you stood. Park beside another chair and nobody counts. | Ils se souviennent de ta place. Gare-toi à côté d'une autre chaise : personne ne compte. |
| level4.hint | Too fast and the stool topples. Hold {careful} to tiptoe. | Trop vite, et le tabouret tombe. Maintiens {careful} pour aller doucement. |
| level6.hint | Eyes don't reach far in the dark. Switch off ({action}) when nobody's looking. | Dans le noir, on voit moins loin. Éteins-toi ({action}) quand personne ne regarde. |
| level8.hint | Two closed doors, two ways out: the kitchen is quicker, the corridor is safer. A door seen swinging gives you away. | Deux portes fermées, deux chemins : la cuisine est plus rapide, le couloir plus sûr. Une porte qu'on voit bouger te trahit. |
| level9.hint | Claire hears every hop on the parquet, except right beside the robot. Don't let it bump into you. | Claire entend chaque saut sur le parquet, sauf tout près du robot. Ne le laisse pas te cogner. |
| level12.hint | Rex sees low: the sofas hide you from him. Paul sees over them. | Rex voit bas : les canapés te cachent de lui. Paul, lui, voit par-dessus. |
| level11.hint | Slow down ({careful}) before every turn or the vase falls. Lea can see the doormat through the doorway. | Ralentis ({careful}) avant chaque virage, sinon le vase tombe. Lea voit le paillasson par la porte. |
| level15.name | Let Sleeping Dogs Lie | Chien qui dort |
| level15.hint | The rocker swings a moment after every stop, less if you brake gently ({careful}). Rex only sees what moves. | Le fauteuil se balance un instant après chaque arrêt, moins si tu freines en douceur ({careful}). Rex ne voit que ce qui bouge. |
| level13.hint | Ease into every start and turn ({careful}): the vase falls at the slightest jolt. Max watches the front door, not the cafeteria. | Démarre et tourne en douceur ({careful}) : le vase tombe à la moindre secousse. Max surveille l'accueil, pas la cafétéria. |
| level14.hint | Mamie sits on you first, then comes back for more: be across the mezzanine before she does. | Mamie s'assoit d'abord sur toi, puis elle revient : traverse la mezzanine avant son retour. |
| level18.hint | The stool fits in the wardrobe: {action} to hide inside, {action} to come back out. | Le tabouret tient dans l'armoire : {action} pour t'y cacher, {action} pour en sortir. |
| level17.hint | Mamie sits first. Rex sees the bridge. Lea hears everything the robot doesn't cover. | Mamie s'assoit d'abord. Rex voit le pont. Lea entend tout ce que le robot ne couvre pas. |
| level19.hint | Maman watches the gallery, regular as clockwork. Now and then Papa leaves the sofa for the kitchen, and he takes the gallery too. | Maman surveille la galerie, réglée comme une horloge. De temps en temps, Papa quitte le canapé pour la cuisine, et lui aussi passe par la galerie. |
| level21.hint | Bertrand and Sofia watch the catwalk from their desks. Kevin runs back and forth all day, and never looks twice at an office chair. | Bertrand et Sofia surveillent la passerelle depuis leurs bureaux. Kevin fait des allers-retours toute la journée, et ne regarde jamais deux fois une chaise de bureau. |
| level20.hint | Switched off, you are only seen up close, and some eyes reach further than others: mind the distance, not the clock. Maman paces the corridor and notices every door you open. | Éteinte, on ne te voit que de près, et certains yeux portent plus loin que d'autres : surveille la distance, pas l'horloge. Maman fait les cent pas dans le couloir et remarque chaque porte que tu ouvres. |
| level22.hint | Alfred never stands still. Mamie never stays in one room. The Comtesse remembers every door in her house. | Alfred ne tient pas en place. Mamie change sans cesse de pièce. La Comtesse se souvient de chaque porte de sa maison. |
| level25.name | The Showroom | Le magasin de meubles |
| level25.hint | Marcel does his rounds at random and never counts the chairs. Freeze only where a chair belongs. | Marcel fait sa ronde au hasard et ne compte jamais les chaises. Ne t'arrête que là où une chaise a sa place. |
| level24.hint | The whole family is up. Rex walks the landing, Lea keeps the hall, Theo and Mamie come and go. | Toute la famille est debout. Rex arpente le palier, Lea garde l'entrée, Theo et Mamie vont et viennent. |

Unchanged: level1, level2, level5, level7 hints and every name except level15 and level25. Keep the level10, level16
and level23 entries. If level25 falls back to a loop, its hint becomes "Marcel does his rounds and never counts the
chairs. ..." / "Marcel fait sa ronde et ne compte jamais les chaises. ...". Each hint must be checked against the final
level data by its level task (R5); the strings task applies corrections reported by level tasks.

---

## 9. Tests to touch (task T1 unless owned by a code task)

- LevelDataM2Tests: PlayOrder (v2 list), manifest count 22, WaveB rows (level9 rooms 3, level15 rock / 4 rooms / dog +
  granny:loop / 0 robots, level10 row moved to an "archived files still validate" test), the number-order test replaced
  by "manifest is the v2 order and every listed level validates", line 222, level1 dwell 3.5, level3 decoy bound if the
  fallback is used.
- ProbeTestsM5Levels: Step40 count from the manifest (cap per run = route end + 30 s), Step45a (drop level16, "listed"
  instead of adjacency), Step45r (no order check), level10/level16 replays deleted, Step45b time-aware, Step45g redrawn,
  Step45m rewritten for level15's rock, Step45o (level9 lane z 8.25), Step57b rows for level17, level8 premises (first
  open time).
- ProbeTestsM7Design: Step64b_Level10Hard and Level16Hard deleted, Step64b for level25 added, the other Step64b hard
  replays follow the new routes; the level16 difficulty-scaling test keeps loading level16 by id.
- ProbeTestsM7LevelsA (Level19Lesson, Level20Lesson), ProbeTestsM7LevelsB (Level21Lesson + one decoy-explained stop,
  Level22Lesson), ProbeTestsM7LevelsC (level23 steps kept by id or deleted; level24 premise chair; a level25 replay at
  Normal and Difficile with 0 discoveries and explained samples > 0), ProbeTestsM6Levels (Level11DropAtSpawn legs),
  ProbeTestsM4Levels, ProbeTestsM5House, ProbeTestsM6Textures, ProbeTestsM7Walls, ProbeTestsM8Lights, ProbeTestsM9*
  (re-shoot lists), LevelDataM4Tests (level6), CoreM5Tests level8/level12 premises (after C2).
- Owned by code tasks: CoreM5Tests unlock test, SaveM5Tests, DifficultyM7Tests, ProbeTestsM5Ui new step (C2);
  ProbeTestsHeldStart (C3a); ProbeTestsHudV2 (C3b); ProbeTestsRush (C7); ProbeTestsLoadedSit (C9); LevelDefV2Tests (C1).

---

## 10. Acceptance criteria for wave 2

### 10.1 Per level (Normal unless stated; all at Normal and Difficile: 0 defects)

| Slot | Id | Exit band s (soft) | Pace gate share / min pauses / max pause | Slack samples | Lesson + requires | Via checks | rev |
|---|---|---|---|---|---|---|---|
| 1 | level1 | 9-12 | 0.12-0.35 / 1 / 6.0 | >= 15 (12) | - | - | 1 |
| 2 | level2 | 12-15 | 0.15-0.35 / 1 / 6.0 | >= 12 | rug | - | 1 |
| 3 | level3 | 17-21 | 0.35-0.52 / 2 / 6.0 | 8-12 | decoy | - | 1 |
| 4 | level4 | 14-16 | 0.25-0.45 / 2 / 6.0 | 8-12 | careful | - | 1 |
| 5 | level5 | 16-20 | 0.25-0.50 / 2 / 6.0 | 8-12 | sit | - | 1 |
| 6 | level6 | 18-22 | 0.12-0.32 / 1 mid / 6.0 | 8-15 | dark | - | 1 |
| 7 | level7 | 18-22 | 0.35-0.55 / 2 / 6.0 | 6-10 | glide (+ decoy gate) | - | 1 |
| 8 | level8 | 15-21 | 0.22-0.45 / 3 / 6.0 | 7-10 | door | kitchen, corridor (1.35) | 1 |
| 9 | level9 | 15-22 | 0.22-0.45 / 4 / 6.0 | 6-9 | robot + hum | - | 1 |
| 10 | level12 | 18-26 | 0.22-0.45 / 3 / 6.0 | 6-9 | pet | - | 1 |
| 11 | level11 | 19-27 | 0.22-0.45 / 3 / 6.0 | 5-8 | load | - | 1 |
| 12 | level15 | 19-28 | 0.22-0.45 / 4 / 6.0 | 5-8 | rock | - | 1 |
| 13 | level13 | 23-32 (Dif <= 50) | 0.22-0.45 / 4 / 6.0 | 5-7 | load (+ decoy gate) | cafeteria, direct (1.5) | 1 |
| 14 | level14 | 36-50 | 0.22-0.45 / 4 / 6.0 | 5-8 | split (+ sit if binds) | - | 1 |
| 15 | level18 | 18-24 | 0.30-0.50 / 2 / 6.0 | 5-7 | wardrobe | - | 1 |
| 16 | level17 | 27-37 | 0.22-0.45 / 5 / 6.0 | 4-5, lowest of act 2 | final + door, pet, split, hum, load | - | 1 |
| 17 | level19 | 46-62 (Dif 55-80) | 0.22-0.45 / 5 (4 mid) / 6.0 | 5-7 | wardrobe | - | 1 |
| 18 | level21 | 27-38 | 0.22-0.45 / 6 (5 mid) / 6.0 | 5-7 | split + decoy | bureau, corridor (1.6) | 1 |
| 19 | level20 | 47-63 (Dif +3..10) | 0.22-0.45 / 4 (3 mid) / 6.0 | 4-8 | dark + household (+ lit) | - | 1 |
| 20 | level22 | 41-56 (Dif <= +20) | 0.22-0.45 / 5 (4 mid) / 6.0 | 4-6 | wardrobe | south wing, north wing (1.5) | 1 |
| 21 | level25 | 24-36 (Dif <= +20) | 0.25-0.45 / 6 / 6.0 | 4-6 | decoy | south lane, north lane (1.5) | - |
| 22 | level24 | 32-46 (Dif <= +20) | 0.25-0.45 / 8 / 6.0 | 4-5, lowest of act 3 | final + door, pet, decoy, hum, exitwatch | north wing, south wing (1.35) | 1 |

Also for every level: lesson binds with no `lessonAdvisory`; `-strictRooms` reports no dead room; the obstacle in the
title is on the route (the audit's mechanics-on-path line names it); budgets within class (120/24 small, 160/32 house);
`designerRoute` and `designerRouteHard` rewritten with `-writeRoutes` and replaying; no new habit warning (D24); no rest
on a walk line warning; rush counter-routes of C7 lose (exemptions: levels 1 and 2 for the "straight path" variant only,
if documented); every hint checked against the data.

### 10.2 Global

- `levels.json` is the v2 order (22 ids, rev 2, previous, acts). Cut files unchanged on disk.
- EditMode suite green; PlayMode suite green (Slow category included in the final run).
- New tests green: LevelDefV2Tests, migration cases of section 7, held start (held 3 s: Steps == 0, no routine motion,
  creak 0; first input starts; a replayed designer route wins on the same exit step with the hold on), HUD names and
  tokens, rush probe, loaded-sit probe, audit fixtures (pace pass/fail, dead room, each requires id binds and does not
  bind, via pass/fail, locked leaf never opened).
- Final full audit by I1: `-auditLevels` (all listed) `-difficulty normal,difficile -slack -strictRooms -json
  Build/levels_v2/final.json`, 0 defects, every row of 10.1 met or listed in the I1 report with a reason.
- Act curves: level 17 has the lowest slack of act 2 and level 24 of act 3; no level is easier by slack than the one two
  slots before it, except the documented new-verb dips (level 18 after 14, level 25 after 22).
- Mutation lines added for the new rules and `mutation.sh` passes on them.
- Docs: CONTRACT_M2 11.8 and PRD 6.3 amended for level 1, PRD level table and order updated, IDEAS entries closed
  (QW4, QW2, NA2, bug 15, bug 20, bug 27), `docs/levels_v2/STATUS.md` with the final numbers.

### 10.3 Amendment 2026-11-20 (product owner decision, task RULEFIX)

The audit's search puts every spare second as early as possible, so levels 3, 6, 8, 13, 17, 19 and 21 failed the pace
rules on a long spawn wait, not on their design. Changed rules (LevelAudit.cs, `MaxSpawnWait`, `SpawnWaitEnd`):

- **Spawn wait** = every sample before the player's first move (in-place actions included, pinned samples left out). It
  has its own limit, **8 s**, a defect at every difficulty. It is **not** a pause for the 6.0 s max-pause rule and is
  **not** loitering for the 8 s loitering rule. It still counts in the waiting share.
- **Minimum pause count**: the spawn wait's pause still counts (10.1 lists "spawn" pauses: levels 3, 12, and the
  "N (N-1 mid)" rows). The audit prints a note when a level meets its minimum only thanks to it, and the JSON report
  gives `spawnWait` and `spawnPauses`. "Mid-route" pauses are now the pauses that start after the first move (a pause
  after a sit at the spawn is a spawn pause).
- **Pinned time** (sat on by an inhabitant) is not loitering either (it was already out of the waiting share). The
  search's own 8 s wait anchor (1 m) is unchanged and still counts pinned and spawn samples.
- Self-test fixtures: `test_v2_audit_pace_fail` reworked (its long pause is now mid-route), `test_v2_audit_pace_spawn`
  and `test_v2_audit_loiter_pinned` added, `test_m5_audit_fidget` watcher dwell 13 -> 21 s (its loitering stays above
  8 s once the spawn wait is left out). Mutation markers `PACE_SPAWN_WAIT` and `LOITER_PINNED`.

---

## 11. Top risks

1. **Unity lock contention.** One editor at a time for about 25 agents; level 24 alone audits in about 60-90 s, a full
   run in 25+ minutes. Mitigation: batch variants per call, at most 6 audit runs per level, code tasks compile once per
   milestone, the final full run only in I1.
2. **Coupled clocks** in 12, 17, 19, 21, 24 (two or three routines plus a dog or robot): a 2 s slip can push a schedule a
   whole cycle or force an 8 s wait. Every level section lists its knobs in order; escalate after 6 runs.
3. **Parallel visual-polish workflow** edits SaveData.cs, Tuning.cs, Hud.cs, LevelBuilder.cs, Robot.cs, GardenBackdrop.cs:
   C2, C3b, C4, C8, C10 must merge on top and never revert; C10 waits for that workflow.
4. **Schema first.** Any level file with a v2 field fails to load until C1 lands; C1 must be small and early.
5. **Decoy geometry is a 5 cm game.** Every decoy edit goes through `decoy_cells.py`; the audit is the arbiter.
6. **Skilled players still beat the strict audit** (no relaxed audit in v2). The rush probe catches only the obvious
   rushes; the owner's playtest after wave 2 is part of acceptance of acts 2-3.
7. **Level 24 without the mezzanine** depends on C6's `requires`; pet, decoy and hum binding in a two-wing level is
   designed, not proven.
8. **Test churn**: T1 is large (about 20 test files). It runs after all levels land; level tasks must report the premises
   they break precisely.

---

## 12. Corrections to the review and to wave 1, recorded

- Level 1 has no cover for the chair (pure facing). Level 6's target cell is inside the CoffeeTable. Level 3's doorway
  rest lies on the watcher's walk. Level 9's hum is required today. Level 12's sofas are required today; what was missing
  is pauses. Level 17's robot and mezzanine bind; its dog does not. Level 22's door memory applies to every human. Level
  20 "walks without stopping" only after 17 solver toggles. Height is never cover from a human. The fixed sentinel is not
  new in 18 (only the metronome is).
- The critic's "mirror is cheap in act 2" holds only for level 18 (D13). The audit's decoy necessity gate already exists
  (D15). `floorColor`/`wallColor` are not rendered (finishes are the lever).

## 13. Open questions for the product owner

1. Lures (pillar 3): accept audit work in wave 3 so two or three levels require a lure, or keep the game pure timing?
2. Dirty runs: may a skilled player spend discoveries to beat a level faster (suspicion as a budget), or must the rush
   probe resist that too?
3. Timed-return goal and two exits: wave 3, or drop?
4. Night: is the C10 preset worth doing for level 20 alone (and level 25's night guard)?
5. Waiting gate 22-45 % instead of 25-40 %: acceptable?
