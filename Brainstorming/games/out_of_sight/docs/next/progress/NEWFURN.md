# NEWFURN - the plant stand ("La sellette") and level30

Date: 2026-11-26. Task: a new player furniture that "moves for longer, creaks faster, and carries a vase with a banana
plant which, if it falls, irrevocably calls the nearest human", and one advanced level that introduces and showcases it.

## 1. The body: the plant stand (`plant_stand`)

A slender red plant stand, a round tray on three splayed legs, with a big terracotta pot and a banana plant on top. It is
the slowest walker after the floor lamp, its creak gauge fills 40 % faster than every other body's, and the banana pot it
carries falls at a smaller jolt than a vase. When the pot falls, the nearest human comes to it, and nothing calls that
human off.

| | chair | plant stand | where |
|---|---|---|---|
| top speed | 1.5 m/s | 0.8 m/s | `Tuning.PlantStandMaxSpeed` |
| acceleration | 10 m/s2 | 3 m/s2 (0.27 s to top speed) | `Tuning.PlantStandAccel` |
| a 0.5 m cell from rest | 0.41 s | 0.76 s (audit: 7 samples a cell, careful 13; chair 4) | `MotionProfile`, `LevelAudit.CellSamples` |
| turn rate | 360 deg/s | 200 deg/s | `Tuning.PlantStandTurnRate` |
| footprint, height | 0.45 x 0.90 | 0.42 x 0.65 (tray), + 0.55 m pot = 1.20 m sample box | `Tuning.PlantStandWidth/Height`, `Tuning.BananaLoadHeight` |
| controller radius | 0.28 m | 0.23 m (a door needs 0.56 m) | `Tuning.PlantStandRadius` |
| creak fill | 20 s (Normal) | 12 s (Facile 15 s, Difficile 9.6 s) | `Tuning.PlantStandCreakFactor` = 0.6, `BodyRules.CreakFillTime` |
| hop rate | 14 rad/s | 9 rad/s (slower, heavier thumps; fewer hop sounds) | `Tuning.PlantStandHopFrequency`, `BodyRules.HopFrequency` |
| seat | yes | no (nobody sits on a plant stand) | `BodyDef.IsSeat` |
| model | Kenney chair | procedural (`FurnitureKit.PlantStand`) | `BodyDef.Model` null |

- **Moves for longer.** Every move takes about twice the chair's time, so every exposure window must be about twice as
  long, and every stop costs more to recover from.
- **Creaks faster.** The gauge drains like every body's (10 s), but fills in 0.6 of the difficulty's fill time. Waiting is
  expensive: at Normal the stand can stand still about 10 s before the audit's cap (0.85), and over a long stretch it must
  spend more than about 45 % of its time moving. `BodyRules` keeps these per-body traits out of `BodyDef`, whose member
  list is pinned by `CoreM5BBodyTests`.
- **The banana pot** is the level's load `"banana"` (`player.load`), the M5 kinematic load rule (`LoadBalance`: the change
  of velocity over 0.5 s) at its own threshold, `Tuning.BananaFallDeltaV` = 1.0 m/s (a vase: 1.8). On the plant stand:
  - holds: a straight start or stop at full speed (0.8 m/s change), a careful 90 deg turn (0.57), a careful reversal
    (0.8), a full speed turn after a stop of 0.4 s;
  - falls: a 90 deg turn at full speed (1.13), a reversal at full speed (1.6), any turn right after a short stop.
  - The balance gauge (HUD) reads the pot's own threshold (`LoadBalance.Ratio`). A wall bump at full speed (0.8) holds.
  - `LoadKinds` (Core) owns the load table: height (`HeightOf`), fall (`FallDeltaVOf`), the audit's refusal
    (`AuditDeltaVOf`, the fall minus the same 0.1 m/s margin the vase keeps: 0.9), and `CallsNearestHuman`.
  - The validator: the banana pot rides only on the plant stand, and the plant stand carries nothing else (a plant stand
    without a load is allowed, it just shows an empty tray).

## 2. The irrevocable call

When the banana pot falls (`GameState.Fall`), it lands on the floor (the usual clue, a crash heard within 6 m) and calls
the nearest human:

- **Who** (`SummonRule`, `GameState.StepSummon`, step 5 of the fixed step, the same step as the fall): among the humans
  free to come (Routine or Alerted, not frozen, with memory: never the dog), the one with the shortest walk to the pot.
  The walk is measured with the household's planner (the doors as they are), from any room, with no distance limit; a tie
  goes to the lower index. When nobody is free (everyone busy investigating, carrying or switching a lamp on), the call
  waits and is tried again on every step.
- **Irrevocable** (`InhabitantRoutine.BeginSummon`, `Summoned`): the human drops its routine (a seated one stands up,
  telegraphed), walks to the pot, faces it, looks around it (head 70 deg to one side, then to the other, 0.8 s each, every
  turn telegraphed), picks it up (0.6 s), then resumes its routine. While called, its mode stays Investigating: no noise,
  sighting or lamp retargets it, `CancelInvestigation` does nothing, and no second call replaces the first. It is the
  clue's finder from the first step, so nobody else looks for the pot.
- **What it means for the player** (the existing suspicion rules): the called human walks through rooms it never visits
  otherwise, and anyone who sees the furniture moving catches it at once (as always). The pot found costs one discovery
  (+0.34 suspicion, as a vase's clue does), counted when it is picked up. Once it resumes its routine, the human observes
  again, so a plant stand standing out of place in its sight is the usual discovery and carry back. The stand goes on
  without its pot: the load rule is over and the sample box shrinks back to the stand (the floor cones keep aiming at the
  taller target, a superset).
- **The dog** hears nothing (as for every noise) and is never called.
- **Feedback**: the crash (`Sfx.PlayCrash`), the called human's "hein?" (`Sfx.PlayHein`) and a speech bubble
  (`ReactionKind.Summoned`, four lines: "Hm?! My banana plant!", "Hein ?! Mon bananier !"...), the "!" of an investigating
  inhabitant, and the pot lying on its side with its soil spilled.

## 3. The model

- `FurnitureKit.PlantStand`: one mesh ("Stand", 314 triangles, budget 400), one renderer, one material (the player's red
  lacquer; a decoy's wood): a round tray with a rim and a dished top on three tapered, splayed legs with round feet, braced
  by a round shelf a third of the way up. Everything stays inside the 0.42 x 0.65 x 0.42 box, UVs in metres.
- The banana pot (`LoadView` kind `"banana"`, `FurnitureKit.BananaPot`): the banana plant of the level props
  (`FurnitureKit.BananaMeshes`, 396 triangles, counted apart from the stand as every load is) in a 0.40 x 0.55 x 0.40 box,
  with the materials of a banana prop in the default plant colours (#3F8F4F leaves, #8C5A36 pot), so a level with banana
  plants pays nothing new for it. Fallen: the same plant lying on its side, its soil spilled out of the pot's mouth.
- `GripDef` row: the carrier's hands on the tray's sides; the dog bites the near leg low.
- The level select's body icon (`LevelMiniature.Furniture`): a tray on three legs with the pot and three leaves.
- `Strings`: `body.plant_stand` ("The Plant Stand" / "La sellette") and its trait, the four `react.summoned.default.*` lines.

## 4. Level audit support (`Assets/Editor/LevelAudit.cs`)

- Speed: the body's samples a cell come from `BodyDef` as for every body (7 at full speed, 13 careful).
- Creak: the search, the freeze unrolling, the gauge check and the hidden creak slack fill in `BodyRules.CreakFillTime`
  (the difficulty's fill times the body's factor), as `GameState` sets `CreakGauge.FillTime`.
- The pot: the search's load model refuses at the load's own refusal (`LoadKinds.AuditDeltaVOf`, 0.9 m/s for the pot; a
  vase keeps exactly `Tuning.AuditLoadDeltaV`), the path check and the lesson use the load's own fall (`FirstFall` with a
  threshold), the sample box grows by the load's own height, and "a full start drops the load" is measured at the load's
  threshold.
- The call: a note says the pot's fall calls the nearest human for good and that the schedule never drops it; along the
  found schedule, one simulated fall a second names who would come (each human's share, and the longest walk to the pot,
  with the same `SummonRule` and the level's planner); the load lesson names who the counter-schedule's fall would call.
- A "sellette" note prints the samples a cell and the creak fill against the difficulty's.
- Existing levels are unchanged: every new value is keyed by the plant stand or the banana pot.

## 5. level30 - The Plant Stand / La sellette

| Id | Title (EN / FR) | Body | Rooms | Humans | Dog | Solver exit (Normal) | Defects |
|---|---|---|---|---|---|---|---|
| level30 | The Plant Stand / La sellette | plant stand + banana pot | 12 | Bernard (watchful), Mamie (granny), Lea (tidy) | Rex | 86.0 s | 0 |

**Concept.** Bernard's prized banana plant lives on a red plant stand in the guest room. The stand wants out to the
veranda, at the other end of a family house: three bands of rooms joined at their ends (a snake), the north band west to
east, a straight crossing of the long corridor, the middle band east to west, the south band west to east. Every beat is
built for the slow body: windows of about 4 to 6 s for exposures of 3 to 4.5 s, corners in safe places where braking costs
time but no sight, and no wait long enough to creak.

### 5.1 Beat sheet (designed first)

| # | Step | Threat | Intended action | Window | Alternative |
|---|---|---|---|---|---|
| 1 | Guest room (spawn, carpet) | none; Bernard walks the corridor behind the wall | set off: the gauge fills in 12 s, and Bernard (2 m away through the wall) hears a creak | free | |
| 2 | Bathroom chicane (tiles) | nobody, but a cabinet and the bathtub force four 90 deg corners | stop or tiptoe ({careful}) before each corner: a full speed corner drops the pot, and the nearest human (Bernard, 19.5 m by path) comes all the way | free (the practice room) | |
| 3 | Study, west wall | Rex in the far corner, looking across the study (the desk hides the north lane from his low eye) | wait at the door, go down the west wall while he naps, into the bookcase's shadow | nap 6.1 s (5.5 s + the 0.6 s wake beat) for 5 cells and 2 corners (about 4.3 s) | |
| 4 | Study, to the corridor door | none: Rex only sees what moves, Bernard cannot see past the door frame | stand still beside the door | free (up to the loiter limit) | |
| 5 | Corridor crossing | Bernard at the far west end, 8.5 m away, looking down the corridor (runner: silent) | cross straight over during one of his glances: 4 cells, no corner (about 3 s) | 4.5 s glance every 9 s | |
| 6 | Salon, east half | Mamie dozing in her armchair, facing the window (195 deg): her east glance (135 deg) stops short of the entry | follow the runner west behind her back, to the pocket right behind her armchair (never in her sight) | free | |
| 7 | Salon, west half and the library door | Mamie's west glance (255 deg, 3 s every 14 s), which also looks into the library through the door | leave the pocket when she turns back; through the door and out of its line | about 9 s free in 14 s for 6 cells (about 4.5 s) | |
| 8 | Library, laundry (soft, tiles) | none | down to the laundry door, out of Lea's earshot | free | |
| 9 | Kitchen | Lea at her stove: 5 s with her back to the room, then 2 s facing it over one shoulder, then the other (each turn telegraphed); a tall dresser hides the lane's west half; she hears every hop off the runner | wait behind the dresser, cross the east half and the pantry door while her back is turned | 5 s + the 0.6 s telegraph and the first part of her turn, for 5 cells (about 3.3 s) | |
| 10 | Pantry, veranda, doormat | none | reach the doormat | free | |

The windows are long by the house's standards (HARDLEVELS: 1.4 to 4.5 s), but so is every move: the stand needs 0.69 s a
cell, so a 4 cell crossing that takes a chair 1.5 s takes it 3 s, and every corner adds a stop (0.4 s) or a slow leg (1.3 s
a cell). The audit's schedule keeps 0.3 s of slack each way (its margin), so no window is frame perfect.

**The pot, taught and exploited.** The bathroom is a safe chicane right after the spawn: four corners with nobody around,
where a careless corner drops the pot and calls Bernard (or Mamie) on a 15 to 20 m walk through the house, past Rex. Later,
every corner sits in a pocket (behind the study's bookcase, behind Mamie, behind the dresser) where braking costs only
time. Along the solver's route a fall would call Mamie 41 % of the time, Lea 31 % and Bernard 28 %; the longest walk to
the pot is 21.1 m. The counter-schedule computed without the load rule drops the pot at 2.1 s, on its very first corner.

**The creak, exploited.** The 12 s gauge forbids long waits anywhere near Bernard (7 m), Lea (7 m) or Mamie (4.2 m): the
schedule's longest pause is 2.8 s and its gauge never passes 0.13, but a player who waits out a whole glance cycle in the
study or behind Mamie fills half the gauge.

### 5.2 Topology (then)

Rooms on the 0.5 m grid (`Build/newfurn/tools/gen30.py`, lvlib): 14 x 11 m, three bands. Doors only where a beat needs them
(11 doorways, no leaves): the guest room opens only into the bathroom, the bathroom only into the study, the study only
onto the corridor; the corridor's doors into the salon and the study face each other (the straight crossing); the
dressing and the dining room are dead ends off the corridor; the library joins the salon to the laundry, the kitchen joins
the laundry to the pantry, and only the pantry opens onto the veranda.

Plan (one character per 0.25 m across, 0.25 m per row; `S` spawn, `E` doormat, `b` Bernard, `m` Mamie (in the salon; the
second `m` is where she starts, in the kitchen), `l` Lea, `d` Rex, `#` tall furniture, gaps in walls = doorways):

```
+---------------+-----------+---------------+-----------+
|               |           |               |           |
|               |           |               |           |
|               |                        d  |           |
|               |           |               |           |
|               |           |               |           |
|               |           |               |           |
|      C H           S #    |      B U      |    D R    |
|               |           |               |           |
|               |           |        #      |           |
|               |           |               |           |
|        S      |           |               |           |
|               |           |               |           |
|               |           |               |           |
+---------------+-----------+-------- ------+------ ----+
|                                                       |
|                                                       |
|  b                       C O                          |
|                                                       |
|                                                       |
+---------------+-------------------- --+-------- ------+
|               |                       |               |
|               |                       |               |
|                                       |               |
|               |                       |               |
|#              |                       |               |
|               |                       |               |
|      L I      |          S L          |      S M      |
|               |                       |               |
|               |          m            |               |
|               |                       |               |
|               |                       |               |
+---------- --+-+-------------+---------+-+-------------+
|             |#              |      #    |             |
|             |               |           |             |
|             |      l        |           |             |
|             |               |           |             |
|             |               |                         |
|             |               |           |             |
|    L A      |      # I      |    P A    |    V E      |
|             |               |           |             |
|                          m              |          E  |
|             |               |           |             |
|             |               |           |             |
+-------------+---------------+-----------+-------------+
CH=chambre, SB=salle_de_bain, BU=bureau, DR=dressing, CO=couloir, LI=bibliotheque, SL=salon, SM=salle_a_manger,
LA=buanderie, KI=cuisine, PA=office, VE=veranda
```

The solver's route: chambre, salle_de_bain (the chicane along the cabinet and the bathtub), bureau (down the west wall,
along the bookcase's shadow), the corridor straight across at x 9.25, the salon's north runner to the library door, the
library and the laundry down the x 2.75 column, the kitchen runner, the pantry, the veranda to the doormat.

Furniture and floors: carpet in the guest room and the library; runners on the corridor (from Bernard to the study door),
on the salon's north lane (behind Mamie) and on the kitchen's south lane (under Lea). The study's desk (0.75 m) hides the
north lane from Rex's low eye; its 2 m bookcase casts the shadow of beat 3; the kitchen's 1.9 m dresser casts the pocket
of beat 9. Mamie's armchair faces south (yaw 180: an armchair's front faces its yaw), its sit station 0.7 m in front of it.

### 5.3 Routines (last)

- *Bernard* (watchful: 10 m, 60 deg, hearing x1.0, tolerance 0.5 m): starts in the kitchen, leaves at 0.5 s through the
  laundry, the library and the salon, and stands for good at the corridor's west end (0.75, 6.75), looking east down the
  corridor. Every 9 s his head glances alternately left and right (+-80 deg), each held 4.5 s.
- *Mamie* (granny: 7 m, 55 deg, hearing x0.6): starts in the kitchen, follows Bernard 2.5 s later (she walks slower, so
  nobody catches anybody up), and sits for good in the salon armchair, facing the window (195 deg). Every 7 s she glances
  alternately west (255 deg) and east (135 deg), each held 3 s.
- *Lea* (tidy: 10 m, 55 deg, hearing x1.0, tolerance 0.4 m): cooks at the stove from the first second, a loop of four
  stations at the same spot: back to the room 5 s, turn to face it (175 deg) 2 s, back to the stove 5 s, face it over the
  other shoulder (185 deg) 2 s. Every turn of more than 30 deg is telegraphed. Her station is more than 2.25 m from both
  kitchen doorways (a doorway's 0.1 m of wall carries no rug, so she would hear it).
- *Rex* (dog, sees motion only, 6 m, 70 deg): naps in the study's far corner facing south-west, asleep 5.5 s (plus the
  0.6 s wake beat), awake 2.5 s.
- The three humans start in the kitchen (they meet there); closest approaches: Bernard and Mamie 0.85 m, Bernard and Lea
  1.62 m, Mamie and Lea 1.20 m (the audit's limit is 0.6 m).

### 5.4 Audit (Normal, `-writeRoutes`): 0 defects

`Build/newfurn.log` and `Build/newfurn.json`, command:
`pwsh -NoProfile -File tools/unity.ps1 -Agent NEWFURN -UnityArgs "run . --timeout 3000 -- -executeMethod OutOfSight.Editor.LevelAudit.RunBatch -auditLevels level30 -skipFixtures -difficulty normal -writeRoutes -json Build/newfurn.json -logFile Build/newfurn.log"`

- Exit 86.0 s; 75 cell moves, 35 of them careful; designerRoute written (54 points).
- Pace: waiting 12.5 s (15 %), 7 pauses (all mid-route), longest 2.8 s; spawn wait 0.3 s; longest loiter 3.1 s (around the
  study door, 20.7 to 32.4 s); longest wait 5.2 s; creak gauge at most 0.13. The level's pace gate: minShare 0.10,
  maxShare 0.45, minPauses 4, maxPause 6.0 (the slow body moves most of the time, so its waiting share is low).
- Pauses: 1.7-4.5 s in the guest room; 23.0-27.4 s at the study's south wall (the corridor glance); 35.4-39.2 s in the
  salon's north-east (Mamie's west glance); 53.7-57.6 s in the library (Lea's back-turned phase).
- Lesson `load` binds: the schedule computed without the load rule drops the pot at 2.14 s (a 1.13 m/s change), and that
  fall would call Bernard (19.5 m of walk). `requires rug` binds: with rugs and soft floors heard as hard floors there is
  no schedule.
- The pot holds along the schedule: peak change 0.89 m/s (the game's fall 1.0, the audit's refusal 0.9).
- Fidelity replay (the game's 5 sight points, 0.1 m release): 0 observations.
- Budgets: 150 of 160 draw calls, 31 of 33 materials, 21840 triangles; the stand 314 triangles and the pot 396, counted
  apart (400 each).
- Warnings only: the dressing and the dining room are dead ends (maze pockets, no post).
- Difficile was not audited (Normal only, as asked): no designerRouteHard, so Difficile's stars use the Normal route.

### 5.5 Method and iterations

Seven audit runs (`Build/newfurn_r1.log` to `Build/newfurn_r6.log`, then `Build/newfurn.log`):
1. r1, r2: no schedule. Lea, then at the stove 1.95 m from the laundry door, heard every hop on its tiles; her kitchen
   crossing was longer than her back-turned phase. Added the dresser pocket and a longer back-turned phase.
2. r3: a schedule (92.7 s) but 11 s of loitering in the bathroom: three periodic gates (Rex 8.6 s, Bernard 9 s, Mamie's
   east glance through the salon door every 14 s) rarely lined up. Mamie now faces 195 deg, so her east glance stops short
   of the corridor door; and Lea's loop used to send her back to the salon every cycle (a loop visits its start station),
   so the three humans now start in the kitchen. 163 draw calls: two props removed.
3. r4, r5: the doorway between the kitchen runner and the pantry was 1.7 m from Lea (rugs may not cross a doorway); r6
   with a hurried Lea passed the noise but cost 3 more materials (another model). Final: the kitchen widened to 4 m and Lea
   moved so both doorways are beyond her 2.25 m.
4. Final runs: Lea back to tidy and the dining table removed (34 to 31 materials), the kettle moved on the narrower
   counter, the two door mats (no longer in anyone's earshot) removed: 160 to 150 draw calls.

A quick 2D sight tool (`Build/newfurn/tools/vis.py`: cones, walls, doorways, tall props, the stand's 9 samples) checked each
watcher's view before every audit run; `variants.py` writes copies of the level with the exit moved earlier on the route
(audited by absolute path), to tell which stretch has no schedule. `plan.py` draws the plan above.

## 6. Integration

- `Assets/Resources/Levels/levels.json`: "level30" appended at the end of "levels" (rev 5 and "previous" untouched; acts
  untouched, so level30 falls in act 4).
- `Assets/Scripts/Core/Strings.cs`: `level30.name` ("The Plant Stand" / "La sellette"), `level30.hint` (threats only, "tu",
  `{careful}`, the data's names), `body.plant_stand` and its trait, `react.summoned.default.1..4`.
- **Test pins (owned by another agent, not edited here):** with level30 in the play order the card count grows by one
  (`LevelDataM2Tests` PlayOrder and its count, `ProbeTestsM5Levels` V2LevelCount, `StarsTests` and `ProbeTestsStars` star
  totals +3, and the level select grid of 6 x 4 gains a row past 24 cards).
- **Tests edited because the change broke them:** `CoreM5BTests` and `LevelDataM4Tests` pin `BodyKinds.All` (the plant stand
  appended); `ProbeTestsM4Levels.Step35a_DecoysOfEveryKindTakeTheirBodySize` needs a free spot for a plant stand decoy in
  level1 ((-3.4, -1.5), between the spawn and the lamp, west of every walk).
- **New tests (not run):** `Assets/Tests/EditMode/PlantStandTests.cs` (the row, the cell time, the creak at every
  difficulty, the hop rate, the pot's height, fall, refusal and call, what drops the pot, the validator's load rules on
  level30, SummonRule, BeginSummon's walk, look around, pick up and irrevocability, the dog and busy humans).
- Compile: `OutOfSight.Editor.Builder.SetupAndCompile`, 0 "error CS" (`Build/newfurn_compile.log`).

## 7. Files

- Core: `PlantStandRules.cs` (new: BodyRules, LoadKinds, SummonRule), `BodyDef.cs` (the row), `LevelDef.cs`
  (`BodyKinds.PlantStand`), `Tuning.cs` (the NEWFURN block), `LoadBalance.cs` (per-load threshold), `InhabitantRoutine.cs`
  (`BeginSummon`, `Summoned`), `LevelValidator.cs` (load rules), `Reactions.cs` (`Summoned`), `GripDef.cs`, `Strings.cs`.
- Runtime: `GameState.cs` (creak fill, load threshold and height, `StepSummon`, the pot's discovery), `FurnitureController.cs`
  (hop rate), `FurnitureKit.cs` (`PlantStand`, `PlantStandMesh`, `BananaPot`), `LoadView.cs` (the banana pot, carried and
  fallen), `LevelBuilder.cs` (cone target height), `LevelMiniature.cs` (the icon).
- Editor: `LevelAudit.cs` (creak, load, call notes).
- Level: `Assets/Resources/Levels/level30.json`, `levels.json`.
- Tests: `PlantStandTests.cs` (new), `CoreM5BTests.cs`, `LevelDataM4Tests.cs`, `ProbeTestsM4Levels.cs`.
- Design sources (not part of the game): `Build/newfurn/tools/` (`lvlib.py`, `gen30.py`, `vis.py`, `variants.py`,
  `plan.py`), `Build/newfurn/level30_pass1.json` (the first passing version, with the two mats).

## 8. Test filters and how to play

- EditMode: `PlantStandTests|CoreM5BBodyTests|CoreM5BMotionTests|LevelDataM4Tests|GripTests|LevelDefV2Tests|LevelDataM2Tests|PlantPlacementTests|DressingTests|StarsTests|LevelDataM8RoomTypeTests|ModelM5Tests`
- PlayMode: `Step35a_|SoftMovers_ProceduralBodiesStayInTheirBoxWithMetricUvs|Step44w_|Step80a_ReactionTables` (plus a
  replay of level30's route if a route probe is wanted).
- PC: rebuild the player, then `Build/Play/OutOfSight.exe --level level30`. In the game it is the card after level35, under
  the act 4 tag.

## 9. Known limits

- Difficile is not audited: Bernard's 10 m at the 1.15 range factor (11.5 m) reaches further into the corridor, which may
  close the crossing.
- The salon and the kitchen are the gentler gates (about 9 s free in 14 s, and a 5 s back-turned phase); the study and the
  corridor are the tight ones.
- Draw calls 150 of 160: a few slots are left for later decor.
- The fallen pot's call is not simulated by the audit (the schedule never drops it); the notes name who would come.