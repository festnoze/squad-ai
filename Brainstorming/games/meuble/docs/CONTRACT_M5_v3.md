# Contract M5 - "La maison" v3 (ARCHIVE: superseded by CONTRACT_M5.md v4; sections 15.x stay binding where v4 says so)

Build contract for milestone M5 of [PRD.md](PRD.md) (section 11, M5): a complete small game.
Same method as M2 to M4:
- the PRD wins;
- the integrator decides;
- every interpretation goes back into the PRD;
- everything of M1 to M4 keeps working.

PRD M5 items:
- multi room houses, doors (open only when unseen), stairs as ramps;
- two inhabitants with crossed routines, one pet (sees low, ignores displacement);
- 10 levels total, level select, best times, save file;
- gate: every level passes the audit; a full playthrough by the probe on the designer routes.

v2 folds in the integrator decisions of section 14 (the critique of draft v1). It is the
**minimal M5 that meets the PRD gate**. Deferred to M6, as open questions:
- the wardrobe hiding prop (question 22);
- door memory (question 19);
- inhabitants opening doors (question 23);
- inhabitants routing around a still chair (re-deferred from CONTRACT_M2 11.10).

---

## 1. Ground rules

As in CONTRACT_M3 section 1 and CONTRACT_M4 section 1:
- own your files (section 10); never edit another owner's file, ask the integrator;
- additive APIs: no M1 to M4 member is renamed or removed;
- `tools/unity.sh` for every Unity call;
- tests that can fail, with premise guards; bound waits by game time, never by frame count;
- every PlayMode TearDown calls `InputReader.ResetInjections()`;
- no em-dash character anywhere;
- constants in Tuning, French strings in Strings (integrator);
- scratch files in `scratchpad/<agent>/`, never at the scratchpad root.

## 2. Houses

**Rooms.** A level has 3 to 5 rooms: rectangles (M2) and **L or U shapes** (unions of rectangles
sharing walls, already supported). The NavMesh comes from the room floors (M2.2).

**One split level, no stacked floors.**
- New data `platforms[]`: `{ name, x, z, sizeX, sizeZ, height, color }`, with
  `Tuning.PlatformMinHeight` 0.6 <= height <= `Tuning.PlatformMaxHeight` 1.0. Axis aligned.
- New data `ramps[]`: `{ x, z, width, length, yaw, platform }`. The ramp rises from floor 0 at its
  foot to the named platform's height at its head; `yaw` points uphill; the head edge lies on a
  platform edge. Slope `atan(height / length)` at most `Tuning.RampMaxSlope` 20 deg.
- **Railings.** Every platform edge gets a railing (height `Tuning.RailingHeight` 0.9, thickness
  0.05) except where a ramp head meets it and where the edge lies on a room wall.
  - Railings are colliders that block the player and the NavMesh.
  - They are **not occluders** (thin rails): `occluder` false, so they do not change any sight.
  - So the player reaches a platform only by a ramp and never falls.
- **Platforms and ramps are solid**: walkable colliders (the player's CharacterController climbs
  them with its existing downward push), NavMesh sources, and **occluders** (their side faces hide
  what is below their edge).
- **`LevelDef.FloorHeightAt(float x, float z)`** (Core) is the one height source: a platform's
  height inside it, the linear interpolation along a ramp, 0 elsewhere.
  - Logic stays planar (memory, poses, stations, routes, hearing distances, the audit grid).
  - Eyes, sample points, teleports, spawns, decoys, props, visuals and audit sight rays add
    `FloorHeightAt` of their planar position.
- **The validator rejects:**
  - any walkable surface above another (overlapping platforms, a ramp over a platform);
  - a platform outside the union of room floors;
  - a prop, decoy, spawn, exit or station footprint that straddles two heights or lies on a ramp;
  - a slope over 20 deg, a ramp head not on its platform's edge.
- No slabs, no WallFader change, no cross-floor hearing rule (hearing stays planar).

## 3. Doors with leaves

**Data.** A door opening (`doors[]`, M2 point form) gains:
- `leaf`: null (a doorway, as today), `"open"` or `"closed"`;
- `hinge`: `"start"` (default) or `"end"`, the end of the opening, along its wall, that carries
  the hinge. The leaf swings 90 deg into the room that lists the door (the door's room side,
  `-Outward`).
- `id`: a short name, unique in the level (the audit mask and the route action name it).

**A closed leaf:**
- is an Occluder (layer Occluder, so `Vision.Occluded` sees it);
- blocks the player (collider) and the inhabitants' NavMesh (a NavMesh source, no carving);
- has sample points (`Tuning.LeafSampleCount` 4: the corners of the leaf's mid plane, inset 0.1 m).

**An open leaf** is visual only: no collider, no occlusion, no samples.

**The player opens a closed leaf** (open question 17: the key is E, gamepad X):
- In reach: the chair's center is within `Tuning.DoorReach` 0.6 m of the leaf's center line on
  either side, and the chair faces the leaf within `Tuning.DoorFacing` 45 deg. `hud.door` shows.
- A door in reach takes E before the body action (the lamp toggle).
- Opening is a `Tuning.DoorOpenTime` 0.6 s action (30 steps) that counts as moving
  (`ActionActive`) and cannot be cancelled. The player has no input during it.
- **While the leaf swings, its sample points join the chair's.** A watcher that sees any leaf
  sample during the swing sees the furniture moving: **a leaf seen swinging is a catch** after the
  normal 0.2 s grace, and the eye opens. That is "open only when unseen", with no mercy rule (open
  question 18).
- The collider leaves at the first swing step; the leaf stays open. The player never closes doors.
- A swing sound (Sfx `door`), not a noise event.

**Inhabitants never open doors in M5.**
- **Station walks are planned once, at level load, with the authored leaves**, and never
  re-planned. So opening a door never changes a routine's timeline, only what it sees.
- Investigations, carries and stand-up returns plan on the **current** leaves: a NavMesh per mask
  of open leaves, built on the first need and cached by `levelId + mask` (`NavPlanner.Build` with
  a cache key). No carving. A plan that fails gives up as in M2.
- The validator plans every station walk with every leaf closed: no walk may need a closed leaf.
- At most `Tuning.MaxLeavesPerLevel` 2 closed leaves per level (the audit's mask count).

## 4. Watchers

**`inhabitants[].kind`**: `"human"` (default, null) or `"dog"`. A Core **`WatcherDef`** gives the
per-kind values, `WatcherDef.For(kind)`, a new instance on every call (null or unknown: human):

| Field | Human | Dog |
|---|---|---|
| `EyeHeight` | 1.6 (`Tuning.EyeHeight`) | 0.35 (`Tuning.DogEyeHeight`) |
| `ViewRange` | 10 | 6 |
| `HalfAngle` | 55 | 70 |
| `WalkSpeed` | 1.2 | 1.4 |
| `Memory` (displacement memory, suspicion, investigate, carry) | true | false |
| `Hears` | true | false |
| `CountsForCatch` | true | false |
| `CountsForExit` (exit only unseen) | true | false |
| `Sits` | true | false |
| `Barks` | false | true |
| `Model` | quaternius.man / quaternius.woman | quaternius.shiba |

- **Vision.** `Vision` and `VisionMath` take eye height, range and half angle from the watcher.
  The lamp's dark range scales the dog's range too (`RangeFactor`). A seated human's eye stays
  1.15 m (M4).
- **`InhabitantRoutine`** takes the watcher: walk speed, no sit for a dog (a dog `sit` station is
  a validator error), `stations[].sleep: true` (dog only) closes its eye for the whole dwell: it
  sees nothing. Its turns are telegraphed like a human's. Dogs have no glances (validator).

**The dog.**
- No memory, no suspicion, no hearing, never investigates, never carries, never sits, never opens
  doors, does not count for the catch or for the exit.
- **It sees low:** an occluder prop whose top is above 0.35 m hides the chair from it. Low props
  (sofa 0.85 m, a table with its cloth) are real cover against the dog, the opposite of humans.
- **The bark.** The dog has its own `CaughtRule` accumulator (same 0.2 s grace and reset). When
  it reaches the grace, the dog **barks**: a noise event `NoiseKind.Bark` **at the dog**, radius
  `Tuning.BarkRadius` 6 m, that every hearing human treats like a creak (Routine and Alerted
  humans retarget, an Alerted look toward the bark position). Then the accumulator resets and
  the dog cannot bark again for `Tuning.BarkCooldown` 3 s (open question 20).
- A bark is not a catch. The chair is caught only if a human then sees it moving.
- **HUD.** A fourth eye state, `HudEye.Dog`, "the dog sees you", when the dog sees the furniture
  and no human does. It differs from the others by **shape** (an eye with a dog ear), not only by
  colour (M6 accessibility). The dog's cone has its own colour (`Tuning.DogConeColor`, orange).
  A sleeping dog shows a "z" marker above its head.
- **Budget.** The dog may have up to `Tuning.BudgetPetBones` 46 bones (open question 16); the
  human limit stays 40.

**Two inhabitants** (content, memories per inhabitant already exist):
- one man, one woman (`quaternius.woman`, kept since M3);
- separate memories and suspicions; the loss happens at 1 for either;
- after a carry back or a sit, every inhabitant's slot updates (M2.1, M4);
- **a Core `SeatRegistry`** shared by the game and the audit: a seat (a prop name, or `"player"`)
  holds at most one sitter. A sit station whose seat is taken is a plain standing dwell;
- **"crossed"**: the audit checks that two humans stay at least `Tuning.WatcherSeparation` 0.6 m
  apart at every sample of the loop, and reports the closest approach. The level data makes their
  walks share a room at least once per loop.

## 5. Levels 8 to 10

| Level | Body | Name (`levelN.name`) | Lesson | Content |
|---|---|---|---|---|
| 8 | chair | "La cuisine et le couloir" | `door` | 3 or 4 rooms, one human, 2 closed leaves |
| 9 | stool | "Le chien" | `pet` | 3 or 4 rooms, one human and the dog, low props as cover |
| 10 | chair | "La maison" | `final` | 4 or 5 rooms, two humans, the dog, one closed leaf, one platform with its ramp |

- The levels agent may change a body with a written reason in its report.
- Each level has a designer route (from the audit) and passes the lesson-required check
  (section 8).
- levels.json lists the 10 levels in order; LevelDataM2Tests' manifest count becomes 10.
- Route actions gain `"open"` with `door: "<id>"` (`RouteStepDef.Door`): the replay presses E at
  that step. No other new field.

## 6. Level select, best times, save

**Save file (`SaveStore`, Runtime; `SaveData`, Core):**
- `Application.persistentDataPath/meuble_save.json`.
- Content: `{ "version": 1, "won": [levelIds], "best": { "<levelId>": seconds } }`.
- Written atomically: write `meuble_save.json.tmp`, then `File.Replace(tmp, path, path + ".bak")`
  when the file exists, `File.Move(tmp, path)` otherwise.
- A best time is replaced only by a strictly lower one.
- A corrupt file, an unreadable file or a `version` above 1: the file is renamed to
  `meuble_save.json.bad` (replacing an older one), a warning is logged, and the game starts fresh.
  **Never an exception out of `SaveStore`.**
- `SaveStore.PathOverride`: tests inject a path; `--probe` redirects the save into its shot
  folder, so the probe never touches the real save.

**Unlocking.** Level index i (levels.json order) is unlocked when i is 0 or the level at i - 1 is
in `won`. In the editor and under `--probe`, every level is unlocked (`SaveStore.UnlockAll`).

**Recording a win.** On `StateChanged(Won)`, the save records `Def.Id` and `Elapsed` (the fixed
step time). The win panel shows `win.best` "Record : {0} s" (one decimal) and, when the time
beat the previous best (or there was none), `win.newBest` "Nouveau record !". GameState does not
know about the save: the ui-save agent subscribes to `GameState.StateChanged`.

**Level select** (from the title: a `title.levels` "Niveaux" button between Play and Quit):
- a grid of 10 cards (2 rows of 5): the level number, its name, its best time or "-", and
  `select.locked` "Verrouillé" when locked;
- a locked card is not interactable; an unlocked one loads that level and closes the menu;
- `select.back` "Retour" returns to the title; Escape and gamepad B too;
- keyboard and gamepad navigation (Selectable explicit navigation), the first unlocked card
  selected on open;
- **Play** on the title starts the first level that is unlocked but not won (level 1 on a fresh
  save; the last level when all are won).

## 7. Budgets

3 to 5 room houses must stay within PRD 7.4 (120 renderers, 24 materials) in the built player:
- floors, baseboards, platforms, ramps and railings are **combined per material** at build time
  (one renderer per material per level), with a shared room palette;
- walls keep one renderer per wall plane, because WallFader fades per plane; a wall cap is combined
  with its wall plane;
- every collider stays as built (combining touches renderers only), so M1 to M4 sights are
  unchanged; probe step 23's collider check still passes on levels 1 to 7.

## 8. Audit

- **Sight tables.**
  - Seen while moving: humans plus the awake dog.
  - Seen while still: humans only.
  - Both use eye heights and sample heights from `FloorHeightAt`, and the watcher's range and
    angle.
- **Doors.** One table per mask of open leaves (at most 4 masks).
  - Opening is a transition `(cell, t, mask) -> (cell, t + 0.6 s, mask | bit)`, allowed from a
    reach cell facing the leaf.
  - It needs 3 unseen samples (`Tuning.AuditStopSamples` style), counting the chair's samples and
    the leaf's.
- **Watchers.** Every routine is stepped with its `WatcherDef`, its sleep stations and the shared
  `SeatRegistry`. The dog's sighting of the chair moving is forbidden (a bark breaks determinism);
  its sighting of a still chair is free.
- **Two humans.** The separation check of section 4.
- **The start-delay sweep** uses the longest loop.
- **Horizon** 300 s for levels 8 to 10, and the audit prints its runtime per level.
- **Lesson checks** (as M4, fixtures strict and relaxed):
  - `door`: no schedule with every leaf locked closed;
  - `pet`: no schedule if the dog had a human 1.6 m eye;
  - `final`: both checks bind (no schedule with the leaves locked, none with a 1.6 m dog eye).
- **Fixtures** `test_door` and `test_pet`, each strict and relaxed, with self-tests like M2 and
  M4.
- Every level 1 to 10 passes, and the M4 fixtures still pass.

## 9. API and stubs (the integrator lands them first, compiling, with `NotImplementedException`
free defaults)

**Core:**
- `WatcherDef` (section 4 table) and `WatcherDef.For(string kind)`; constants `Human`, `Dog`.
- `SeatRegistry`: `bool TryClaim(string seat, int who)`, `void Release(string seat, int who)`,
  `bool IsTaken(string seat)`, `int SitterOf(string seat)` (-1 when free), `void Clear()`.
- `SaveData`: `int Version`, `List<string> Won`, `Dictionary<string, float> Best`;
  `RecordResult RecordWin(string levelId, float seconds)` (returns `Best`, `NewBest`,
  `PreviousBest`); `bool IsUnlocked(IReadOnlyList<string> order, int index)`;
  `static SaveData Parse(string json, out string problem)` (null and a problem on any failure,
  never throws); `string ToJson()`.
- `NoiseKind.Bark`; `Hearing.RadiusOf(Bark)` is 6 and `RetargetsAlerted(Bark)` is true.
- `LevelDef`: `List<PlatformDef> Platforms`, `List<RampDef> Ramps`, `float FloorHeightAt(float x,
  float z)`, lesson constants `LessonDoor`, `LessonPet`, `LessonFinal` (added to `Lessons`).
- `OpeningDef`: `string Leaf`, `string Hinge`, `string Id`.
- `InhabitantDef.Kind`; `StationDef.Sleep`; `RouteStepDef.Door` and `RouteStepDef.ActionOpen`
  ("open").
- `InhabitantRoutine`: `WatcherDef Watcher` (set before the first step; null means human),
  `bool Asleep`, `IPathPlanner InvestigatePlanner` (null means the station planner),
  `SeatRegistry Seats` and `int SeatOwner` (null registry: every seat is free).

**Runtime:**
- `DoorLeaf` (MonoBehaviour on each leaf): `string Id`, `bool Open`, `bool Swinging`,
  `float SwingProgress`, `Vector3[] Samples` (empty unless closed or swinging),
  `bool InReach(FurnitureController f)`, `void BeginOpen()`, `void Step(float dt)`.
- `LevelInstance.Leaves` (`List<DoorLeaf>`), `LevelInstance.OpenMask` (int),
  `LevelInstance.PlannerFor(int mask)`.
- `FurnitureController.BeginExternalAction(float duration)`: an action with no input that counts
  as moving (`ActionActive`), used by the door opening.
- `Inhabitant.Watcher` (`WatcherDef`); `Vision.Watcher`.
- `HudEye.Dog`; `Hud.ShowDoorHint(bool)`; `Hud.WinPanel` (the RectTransform the record line
  attaches under).
- `SaveStore` (static): `PathOverride`, `UnlockAll`, `Current` (`SaveData`), `Load()`, `Save()`,
  `RecordWin(string levelId, float seconds)`; `event Action<RecordResult> Recorded`.
- `Menu.LevelsButton`, `Menu.LevelSelectOpen`, `Menu.OpenLevelSelect()`.
- `Main.Save` is not needed: `SaveStore` is static; `Main` calls `SaveStore.Load()` at boot and
  sets `UnlockAll` in the editor and under `--probe`.

## 10. Agents and file ownership

| Agent | Files |
|---|---|
| **core** | `Core/WatcherDef.cs` (new), `Core/SeatRegistry.cs` (new), `Core/SaveData.cs` (new), `Core/InhabitantRoutine.cs`, `Core/Hearing.cs`, `Core/VisionMath.cs`, `Core/CaughtRule.cs` (only if the dog needs it), `Tests/EditMode/CoreM5Tests.cs` |
| **house** | `Core/LevelDef.cs`, `Core/LevelValidator.cs`, `Runtime/LevelBuilder.cs`, `Runtime/FurnitureKit.cs`, `Runtime/PrimitiveKit.cs`, `Runtime/DoorLeaf.cs` (new), `Runtime/NavPlanner.cs`, `Runtime/WallFader.cs`, `Tests/EditMode/LevelDataM5Tests.cs`, `Tests/PlayMode/ProbeTestsM5House.cs` (steps 36 and 39 on fixture levels) |
| **watchers** | `Runtime/Inhabitant.cs`, `Runtime/InhabitantRig.cs`, `Runtime/Vision.cs`, `Runtime/VisionConeView.cs`, `Runtime/ModelKit.cs`, `Runtime/ModelCatalog.cs`, `Editor/ModelCatalogBuilder.cs`, the dog model files under `Assets/Models/`, `Tests/EditMode/ModelM5Tests.cs`, `Tests/PlayMode/ProbeTestsM5Watchers.cs` (step 38 vision and rig parts) |
| **game** | `Runtime/GameState.cs` (single owner: the watcher loop, the bark, the door action and leaf samples, the seat registry, the investigate planner per mask), `Runtime/FurnitureController.cs`, `Runtime/InputReader.cs`, `Runtime/Hud.cs`, `Runtime/Sfx.cs`, `Runtime/GhostView.cs`, `Tests/PlayMode/ProbeTestsM5Game.cs` (steps 36 rules, 37, 38 bark) |
| **ui-save** | `Runtime/SaveStore.cs` (new), `Runtime/LevelSelect.cs` (new), `Runtime/RecordLine.cs` (new), `Runtime/Menu.cs`, `Tests/EditMode/SaveM5Tests.cs`, `Tests/PlayMode/ProbeTestsM5Ui.cs` (step 41) |
| **levels** | `Editor/LevelAudit.cs`, `Resources/Levels/*.json` (levels 8 to 10, fixtures, levels.json), `Tests/EditMode/LevelDataM2Tests.cs` (manifest count), `Tests/PlayMode/ProbeTestsM5Levels.cs` (route replays of 8 to 10, step 40) |
| **integrator** | Tuning, Strings, docs (PRD, README, LICENSES rows given by watchers), `verify.sh`, `mutation.sh`, `tools/`, `Main.cs`, `Probe.cs` (built player shots of levels 8 to 10, the save redirect), `Tests/EditMode/LicenseTests.cs`, every stub |

**Sequence.**
1. M4 gate green; integrator stubs, Tuning and Strings.
2. core, house, watchers and ui-save in parallel; levels phase A (fixtures `test_door`,
   `test_pet`, drafts of levels 8 to 10 that load and validate).
3. game integrates GameState once core and house land.
4. levels phase B (audit extension), then phase C (routes, replays, step 40) once game lands.
5. Full verify, result critic, fix wave, mutations, PRD v1.7 notes, README gate.

## 11. Gate

**Probe steps from 36** (a `b`, `c` suffix for variants):
- **36 doors:** in reach shows `hud.door`; E opens in exactly 30 moving steps; a leaf seen swinging
  is caught after the grace while the chair itself is hidden; an open leaf no longer occludes and
  no longer blocks; a station walk is the same before and after an opening; an investigation
  uses the opened doorway.
- **37 two inhabitants:** separate memories and suspicions; every slot updated after a carry; a
  taken seat is skipped as a standing dwell; either suspicion at 1 loses.
- **38 dog:** a chair behind the sofa is hidden from the dog and seen by a human at the same
  spot; seen moving by the dog for 0.2 s barks once, at the dog, and the hearing human looks
  toward it; no second bark within 3 s; a still chair seen by the dog changes nothing; the dog
  ignores displacement; a sleeping dog sees nothing; `HudEye.Dog` shows; the dog never catches.
- **39 split level:** the ramp is climbable and the railing blocks; the eye and the sample points
  add the floor height; a chair on the platform behind its edge is hidden from a low eye below.
- **40 full playthrough:** levels 1 to 10 in order through the real level flow (Enter to the next
  level), each on its designer route at offset 0, timeScale 8; after each win the save holds the
  level in `won` and its best time; ends on the end screen.
- **41 level select and save:** locking and unlocking; Play picks the first unwon level; best
  times only improve; a corrupt and a newer file are both renamed `.bad` and the game starts
  fresh; the probe save never touches the real path.
- Levels 8 to 10 in the `verify.sh` audit stage (with their lesson checks) and in the built player
  shots (budgets, no model fallback).

**Mutations to add to `mutation.sh`:**
- the dog's eye at 1.6 m;
- the bark emitted at the chair;
- an open leaf still occludes;
- leaf samples ignored while swinging;
- the dog counts for the catch;
- a slower best time overwrites;
- the separation check accepts 0.3 m;
- the probe writes the real save;
- a locked level is playable.

**Tuning names** (the integrator adds them): `PlatformMinHeight` 0.6, `PlatformMaxHeight` 1.0,
`RampMaxSlope` 20, `RailingHeight` 0.9, `DoorReach` 0.6, `DoorFacing` 45, `DoorOpenTime` 0.6,
`LeafSampleCount` 4, `MaxLeavesPerLevel` 2, `DogEyeHeight` 0.35, `DogViewRange` 6,
`DogHalfAngle` 70, `DogWalkSpeed` 1.4, `BarkRadius` 6, `BarkCooldown` 3, `DogConeColor`,
`WatcherSeparation` 0.6, `BudgetPetBones` 46, `AuditHorizonM5` 300, `PlaythroughTimeScale` 8.

**Strings** (the integrator adds them, French verbatim, no em-dash):

| Key | Text |
|---|---|
| `level8.name` | La cuisine et le couloir |
| `level8.hint` | Une porte fermée cache tout, mais l'ouvrir prend un moment : E, seulement quand personne ne regarde. |
| `level9.name` | Le chien |
| `level9.hint` | Le chien voit bas : le canapé te cache de lui. S'il te voit bouger, il aboie et tout le monde se retourne. |
| `level10.name` | La maison |
| `level10.hint` | Tout ce que tu as appris : les portes, le chien, deux habitants et la mezzanine. |
| `hud.door` | E : ouvrir la porte |
| `title.levels` | Niveaux |
| `select.locked` | Verrouillé |
| `select.back` | Retour |
| `win.best` | Record : {0} s |
| `win.newBest` | Nouveau record ! |

**Critic pass** on the result, as before.

## 12. Open questions (written back to PRD 12.2 as 16 to 23)

16. **Pet bones:** 46 bones accepted for the dog; the human budget stays 40. Default: accepted.
17. **Door key:** E (gamepad X), the M4 action key. Default: E.
18. **Seen opening a door:** a normal catch after the grace, no mercy rule. Default: catch.
19. **Door memory** (an inhabitant noticing a door it remembers closed): deferred to M6, with the
    lamp pattern (an inhabitant who sees it comes and closes it) as the fallback design.
20. **The bark:** at the dog, 6 m, like a creak, 3 s cooldown. Default: as written.
21. **Stacked floors:** not in M5 (one split level per house). Default: deferred indefinitely.
22. **The wardrobe hiding prop:** deferred to M6.
23. **Inhabitants opening doors:** deferred to M6.

## 13. Out of scope for M5

Android, touch controls, options, quality tiers and the accessibility pass (M6); the wardrobe;
door memory; stairs between stacked floors; a second pet; routing around a still chair.

---

## 14. History: critique of draft v1 and integrator decisions

Draft v1 (sections 1 to 7 of the first version) proposed stacked floors with slabs and
cross-floor hearing, inhabitants opening doors with door memory, the wardrobe hiding prop, and a
`{ unlocked: n }` save. The contract critic found 4 blockers:
- doors break audit determinism;
- the door rule is misread;
- stacked floors are infeasible;
- ownership and stubs are missing.

**Decisions: the minimal M5 that meets the PRD gate** (now sections 2 to 11).

1. **Doors.**
   - Only the player opens a closed leaf: E while facing it within 0.6 m (`hud.door`).
   - Opening is a 0.6 s action that counts as moving and cannot be cancelled.
   - While the leaf swings, its sample points join the chair's: **a leaf seen swinging is a
     catch**, and the eye opens. That is "open only when unseen", with no mercy rule.
   - The door stays open.
   - **Inhabitants never open doors in M5**: the validator ensures no closed leaf lies on any
     station walk planned with every leaf closed.
   - An open leaf is visual only.
   - On a leaf change, the NavMesh is rebuilt synchronously, cached by door mask. No carving.
   - **No door memory** in M5 (open question 19: deferred, with the lamp pattern as fallback).
   - Open questions 17 (E) and 18 (normal catch).
2. **Floors.**
   - **No stacked floors.** Level 10 has one split-level: a raised area of 0.6 to 1.0 m reached
     by a ramp of at most 20 deg.
   - `LevelDef.FloorHeightAt(x, z)` gives the height. Logic stays planar; eyes, sample points,
     teleports and audit cells add the floor height.
   - The validator rejects any walkable surface above another.
   - No slabs, no WallFader change, no cross-floor hearing.
   - Open question 21.
3. **Watchers.**
   - `inhabitants[].kind: "human" | "dog"`, with a Core `WatcherDef`: eye height, range, half
     angle, walk speed, Memory, Hears, CountsForCatch, CountsForExit.
   - `Vision.Test` and `InhabitantRoutine` take their eye, range and angle from the watcher.
   - ModelKit's Uniform fit takes a per-entry target eye height (the dog's is 0.35 m).
4. **The dog.**
   - Eye 0.35 m, range 6 m, half angle 70 deg.
   - No memory, no hearing, no catch, no exit role.
   - **Seen moving by the dog for 0.2 s: a bark**, a noise at the dog of radius 6 m that
     retargets like a creak (open question 20).
   - Its turns are telegraphed, its range scales with the lamp, sleeping shows a marker, and it
     never opens doors.
   - A fourth HUD eye state ("the dog sees you") and a distinct cone colour.
   - 46 bones accepted for pets (open question 16).
5. **Two inhabitants** are content: memories per inhabitant are already built. Added:
   - an audit check that two inhabitants stay at least 0.6 m apart at every sample, which also
     measures "crossed";
   - a Core seat occupancy registry shared by the game and the audit.
6. **Deferred to M6:**
   - the wardrobe hiding prop (open question 22);
   - door memory;
   - inhabitants opening doors (open question 23);
   - inhabitants routing around a still chair (re-deferred explicitly from CONTRACT_M2 11.10).
7. **The audit.**
   - Two sight tables: seen while moving (humans plus the awake dog) and seen while still (humans
     only).
   - One table per mask of player-openable doors, at most 2 doors per level.
   - Opening costs 3 unseen samples, leaf samples included.
   - The start-delay sweep uses the longest loop.
   - Horizon 300 s for levels 8 to 10, with the runtime printed.
   - Lesson checks:
     - door: no schedule with the leaves locked;
     - pet: no schedule if the dog had a 1.6 m eye;
     - final: both checks bind.
   - Fixtures `test_door` and `test_pet`, each strict and relaxed.
8. **Budgets.** Walls, floors and baseboards are combined per material at build time, with a
   shared room palette, so 3 to 5 room houses stay within 120 renderers and 24 materials.
   (v2 refines this: walls stay per wall plane for WallFader, section 7.)
9. **The save.**
   - `{ version: 1, won: [levelIds], best: { id: seconds } }`.
   - Written with `File.Replace(tmp, path, bak)`.
   - A best time is replaced only by a lower one.
   - `--probe` redirects the save to the shot folder; tests inject the path.
10. **Mutations:**
    - the dog's eye at 1.6 m;
    - the bark emitted at the chair;
    - an open leaf still occludes;
    - leaf samples ignored while opening;
    - the dog counts for the catch;
    - a slower best time overwrites;
    - inhabitants closer than 0.6 m;
    - the probe writes the real save.
11. **Missing strings** to add: level 8 to 10 names and hints, `hud.door`, `title.levels`,
    `select.locked`, `win.best`, `win.newBest`.
12. **The full playthrough (step 40)** runs at one offset with timeScale 8.
13. **Ownership, API and stubs** are written in v2, after the M4 gate, with a single owner for
    GameState.

v2 additions to these decisions (integrator):
- station walks planned once at load with the authored leaves, so an opening never changes a
  routine's timeline and one sight table per mask is exact (section 3);
- railings on platform edges, not occluders, so the player never falls and logic stays planar
  (section 2);
- the dog's bark cooldown of 3 s and its own accumulator (section 4);
- a corrupt save renamed `.bad` (the `.bak` name belongs to `File.Replace`) (section 6);
- Play starts the first unwon level (section 6).

---

## 15. v3 amendments (binding; they override sections 1 to 13 where they conflict)

From the contract critic's review of v2 (5 blockers, 9 majors). Decided by the integrator.

### 15.1 One NavMesh, door areas, frozen station walks (B1)

- **One NavMeshData per level**, built once at load as today, never rebuilt for a door.
  - Every leaf doorway gets a `NavMeshBuildSourceShape.ModifierBox` source through the wall
    thickness, with its own area: `Tuning.DoorAreaBase` 3 plus the leaf index (areas 3 and 4).
    `ProjectSetup` names them "Door0" and "Door1".
  - No leaf is a NavMesh source in any pose. The open-pose swing sector is a `ModifierBox` with
    area 1 (Not Walkable), so no path ever crosses an open leaf.
  - `NavPlanner.TryPlan(from, to, corners, int areaMask)`: a new overload; the old one keeps
    `NavMesh.AllAreas`.
  - **A closed leaf's area is excluded from the mask.** `LevelInstance.OpenMask` (bit k set when
    leaf k is open) gives `LevelInstance.AreaMask()`.
- **Station walks are frozen.**
  - The routine plans each station-to-station walk once, at construction, with the mask of the
    authored leaves, into a corner cache.
  - Every other plan (investigate, switch-on, carry, both branches of the resume, the approach
    yaw) uses `InvestigatePlanner ?? planner`.
  - In the game, `InvestigatePlanner` plans with the current `AreaMask()`.
  - Opening a door therefore never changes a routine's timeline, and the audit (which forbids
    every discovery, so it never simulates an investigation) is exact with one sight table per
    mask.
- **The station-walk check** ("no walk needs a closed leaf") belongs to `LevelAudit.CheckWalks`
  (levels), not to the Core validator.

### 15.2 Door geometry and the opening, in Core (B2, M3)

- **`Core/DoorGeometry`** (house; the integrator stubs it), shared by DoorLeaf, the validator and
  the audit:
  - `Pose(float swingDegrees)`, the leaf box at an angle;
  - `Samples(float swingDegrees)`, 4 points;
  - `Center`, `InReach(Vector3 chairCenter)`, `SwingSector`.
- **Data.**
  - `leaf`: `"open"` or `"closed"`.
  - `id`: required on a leaf door, unique in the level.
  - `hinge`: `"start"` (the end of the opening with the lower world coordinate along its wall) or
    `"end"`.
  - `swing`: the id of the room the leaf swings into, required for a leaf.
  - Leaf thickness `Tuning.LeafThickness` 0.04, centered on the wall line.
- **The open leaf keeps its collider and occludes**, in its open pose against the wall. The
  validator keeps its swing sector (a quarter disc of radius = width) free of props, decoys,
  rugs, stations, seat homes and the spawn.
- **Reach and the key.**
  - Reach: the chair's planar center within `Tuning.DoorReach` **0.85 m** of the door center, and
    its footprint outside the swing sector. **No facing condition** (dropped: the audit has no
    yaw, and the replay cannot turn in place).
  - E opens the nearest closed leaf in reach, and takes E before the body action.
  - **E acts only when the furniture is still, upright, not pinned, not carried and not in an
    action.** Otherwise it does nothing. This protects the stool's tip and the office chair's
    glide.
- **During the swing** (0.6 s, 30 steps, `ActionActive`):
  - the collider moves with the leaf;
  - the 4 leaf samples at the current angle join the chair's samples **for the caught rule and
    the bark accumulator only** (not for memory, suspicion or the lamp);
  - a leaf sample seen during the swing is "seen moving".
- **Outside a swing, a leaf has no samples.** PRD 4.1 (five raycasts) is written back: 9 during
  a swing.
- **Leaves fade with their wall's center plane** (WallFader), and the probe's `ChairBlockers`
  ignores faded renderers as it does for walls.

### 15.3 The audit and doors (B2, M7)

- `Tuning.AuditOpenSamples` = round(0.6 / 0.1) = **6**, dilated by `MarginSamples`.
- The opening is checked in the **mask | bit** moving table (the collider leaves at the first
  swing step):
  - for the chair cell;
  - and for the leaf samples at each sample's swing angle.
- Walkability and neighbours are built **per mask**. A closed leaf blocks its doorway cells;
  an open leaf blocks its swing-sector cells.
- **Reach cells.** The report lists the reach cells per leaf, and **fails a closed leaf with no
  walkable reach cell**.
- **Runtime.**
  - The mask enters the search state only after an opening.
  - The start-delay sweep steps 3 s on levels 8 to 10.
  - Every level prints its runtime. Over `Tuning.AuditLevelBudgetSeconds` 240 s, the audit
    fails.
  - `verify.sh`'s audit stage timeout becomes 2400 s (integrator).

### 15.4 The split level everywhere (M1, M2)

- **`Core/FloorMap`** (house; the integrator stubs it):
  - built from `LevelDef` (`LevelDef.Floor`, cached);
  - `float HeightAt(float x, float z)`;
  - `FloorMap.Flat`: always 0, used when no level is given.
- **Every y = 0 site takes the floor height**, each in its owner's file:
  - **core:** `InhabitantRoutine.Floor`, used by `EyePosition` and `CarryAnchor`.
  - **game:**
    - FurnitureController: `Floor` for `Release` and `Teleport`;
    - GameState: the carry pick-up and put-down, and `SitOnPlayer`;
    - GhostView: the ghost, the seat and the stop ring.
  - **watchers:**
    - Inhabitant: the transform and `VisualEyePosition`;
    - VisionConeView: the floor y per cone vertex, and the target height relative to the floor.
  - **house:**
    - NavPlanner: `SamplePosition` from `HeightAt + 0.5`;
    - LevelBuilder: spawn, props, decoys, rugs.
  - **levels:** the audit's walkable capsule and its `Clear()` casts start at the cell's floor
    height; the platform and ramp boxes are excluded from the walkable test of their own cells.
- **Railings** on every platform edge and on **both sides of every ramp**:
  - except the ramp's foot and head;
  - except an edge on a room wall.
  - The player can neither fall nor hang in the air.
- **Ramps are wedges** (a convex MeshCollider), flush at the foot (y = 0) and at the head (the
  platform top).
- **The validator** adds these rules:
  - ramp yaw is a multiple of 90;
  - ramp width >= 2 x the largest player radius + 0.1 m and >= the NavMesh agent's width;
  - no platform over a door threshold.
- **The audit** forbids a move whose floor height jumps more than the CharacterController's step
  offset between neighbouring cells.
- **Step 39** compares heights with a 0.05 m tolerance (the CharacterController rests a few
  centimetres above a slope).

### 15.5 Watchers in code (B3, M4)

- **`ModelCatalog.Entry`** (watchers) gains:
  - `kind` (`"human"` or `"pet"`);
  - `targetEyeHeight` (0 means `Tuning.EyeHeight`), used by ModelKit's Uniform fit;
  - a clip map for pets: Idle, Walk; Startled falls back to Idle.
- **Ownership of the M3 checks the dog would break:** `ProbeTestsM3Models.cs`,
  `ProbeTestsM3Rig.cs` and `Probe.cs` go to the integrator. Their human checks (the clips
  `_Idle`, `_Walk` and `_Jump`, eyes at 1.6 m, 40 bones) apply to humans only; pets use
  `BudgetPetBones` 46 and Idle and Walk. levels updates `LevelAudit.CheckBudgets` the same way.
- **`Vision.Test(eye, forward, samples, range, halfAngle, visible)`**:
  - a new overload (game owns Vision for this one change);
  - `range` already includes the lamp factor;
  - the audit's `IsInCone` takes the watcher's angle.
- **Retarget.** Both hard-coded "only a Creak retargets an Alerted inhabitant" sites call
  `Hearing.RetargetsAlerted(kind)`: InhabitantRoutine (core) and GameState (game).
- **Eye resets** (`StandUp`, `ResetSitting`, Pin, Startle) use the watcher's eye height (core).
- **Waking.** A dog leaving a sleep station plays a `Tuning.WakeTelegraph` 0.6 s telegraph with
  its eye **still closed**. It then turns, telegraphed as usual if over 30 deg.
- **The bark accumulator** is held at 0 during the cooldown. The bark is gated by `Rules.Hearing`
  (no hearing, no bark).
- **The dog is excluded from** the noise reception (Emit), StepMemory, StepLamp, `LastSeer`, the
  suspicion and the carry.
- **HUD eye precedence:** Alarm > Calm (a human sees) > Dog (only the dog sees) > Closed.
- **A sleeping dog's cone is hidden**, and a "z" marker shows above it.
- **Low cover is a raycast fact, not a rule.** "A prop above 0.35 m hides the chair" is dropped.
  Level 9's cover is whatever the raycasts say: rays rise toward the top samples, so a low prop
  hides only what stands close behind it. The levels agent places it accordingly.

### 15.6 The routine factory and the seat registry (M5, minors)

- **`Core/RoutineFactory.Create(InhabitantDef def, LevelDef level, IPathPlanner stationPlanner,
  IPathPlanner investigatePlanner, SeatRegistry seats, int owner, int stationAreaMask)`** (core).
  - It sets Watcher, Seats, SeatOwner, InvestigatePlanner, Floor and the frozen station walks
    before the first step.
  - Inhabitant.Init (watchers), the audit (levels) and the tests all use it.
- **SeatRegistry.**
  - A seat is claimed at `SitNow`, released on the first StandingUp step and in `ResetSitting`;
    a pratfall claims nothing.
  - **A taken seat** makes that station a standing dwell, with no back turn, no lowered eye and
    no stand-up telegraph.
  - `SeatOccupied` (M4: "the player's seat is home") keeps its meaning and is documented next to
    `IsTaken` (taken by an inhabitant).
  - The seat ghost shows only while the walking sitter holds no rival claim at the start of its
    walk.
  - The audit's forced presence comes from the simulated sit results, not from the data.
- **The validator** requires unique prop names among props named by a `sit`.

### 15.7 The save (B4, M6)

- **Paths.**
  - In the editor, and under `--probe` or `--look`, Main points `SaveStore.PathOverride` at
    `Application.temporaryCachePath/meuble_save_test.json` and deletes it at boot.
  - Only a built player with neither flag touches the real file.
- **Test isolation.**
  - `SaveStore.ResetForTests()` clears Current, PathOverride, UnlockAll and the `Recorded`
    subscribers.
  - Every PlayMode TearDown calls it (the integrator edits M1 to M4 test files).
  - RecordLine and LevelSelect unsubscribe in OnDestroy.
- **Write.**
  - Write the `.tmp` and flush with `Flush(true)`.
  - Then `File.Replace(tmp, path, path + ".bak")`, with 3 tries 50 ms apart. If Replace still
    fails, or the target is missing: delete the target, then `File.Move`.
  - Only an IO error after all of that makes the session run in memory (a warning; nothing
    overwritten).
- **Read.**
  - A parse failure, a missing or 0 `version`, or a version above 1 means corrupt:
    1. try the `.bak`;
    2. if it is also corrupt, delete any old `.bad`, move the file to `.bad`, and start fresh.
  - An IO error on read means running in memory **without saving** for the session, so real
    progress is never overwritten.
- **Android** (M6) gets the delete-then-move fallback for free, and an EditMode test drives that
  branch.

### 15.8 Budgets (B5)

- **Combine key** = (material, layer, fade plane), combined per level at **level build**.
- Wall caps and shared-wall baseboards stay separate, as today (step 22b and their per-face fades
  are unchanged).
- What is combined:
  - segment faces per plane (one WallFader entry);
  - door frames per wall line;
  - window strips per window;
  - floors, platforms, ramps and railings per material.
- **Material ledger** for level 10 (house reports it):
  - railings use Trim;
  - platform and ramp use the room floor colours;
  - leaves use DoorWood;
  - the dog's colours map to existing palette materials where the model allows.
- The renderer budget stays the PRD 7.4 rule (renderers <= 120, materials <= 24), measured in
  the built player.

### 15.9 Ownership, stubs and test levels (M5)

- **Test levels per agent:** `Resources/Levels/test_m5_<agent>_*.json`, owned by that agent and
  never in levels.json (the `test_m4_game_sit.json` precedent).
- **Ownership changes:**
  - **game** also owns `ProceduralArt.cs` (the dog eye icon) and `Vision.cs` (15.5).
  - **watchers** owns `FootstepAudio.cs` (dog steps) and the `quaternius.shiba` entry. Models live
    in `Assets/ThirdParty/Models/Quaternius/`.
  - **levels** owns a new shared `Tests/PlayMode/RouteReplayer.cs` (from the M4 levels replay,
    with the pin rule of M4 9.8 and the `open` action), used by the 8 to 10 replays and step 40.
- **InputReader** (game) gains `BackPressed()` (Escape, gamepad B) and `InjectBack()`, stubbed by
  the integrator for ui-save.
- **Split probe steps:**
  - **36:** house writes 36 (leaf poses, the collider and occlusion swap, the fade, the area-mask
    paths); game writes 36b to 36f (E rules, the catch during the swing, walks unchanged, an
    investigation through the opened doorway).
  - **38:** watchers writes 38 (low eye vision, sleep, the wake telegraph, the cone colour, the
    rig); game writes 38b to 38f (the bark, the retarget, the cooldown, HudEye.Dog, the dog never
    catches, ignores displacement).
- **M5 rules are always on** (they are data driven); no new GameRules switch.

### 15.10 Gate additions (M8, M9, minors)

- **Fixture `test_cross`** (strict and relaxed): two humans whose walks cross. Strict passes at
  0.6 m, relaxed must fail at 0.6 m.
  - The separation covers every watcher pair over the full horizon.
  - "Crossed" means sharing a room at the same sample at least once, and the audit fails a
    two-human level that never crosses.
- **The probe save redirect is asserted in the built-player stage.**
  - The probe report prints the save path.
  - `verify.sh` checks it is under the shot folder, and that the real save file's hash (if any)
    is unchanged.
- **Mutations**, each with its marker, file and killing step:
  - the 9 of section 11, the separation one killed by `test_cross` and the probe save one killed
    by the built-player check;
  - plus: a station walk re-planned after an opening; the eye ignores `FloorHeightAt`; no wake
    telegraph.
- **Step 40.**
  - Per level, the cap is the route end + 30 s of game time, under `[Timeout(1800000)]`.
  - `verify.sh`: the PlayMode timeout becomes 3600 s, and the built-player stage 900 s.
- **Level select.**
  - The cards come from `LevelOrder` (no hard-coded 10).
  - `Menu.DefaultButton` returns the first unlocked card while the select is open.
  - The best time on a card is "{0} s" with one decimal, or "-".
  - The end screen shows the last level's record line too.
- **Strings** (changed or added):
  - `level9.hint`: "Le chien voit bas : le canapé te cache de lui. S'il te voit bouger, il aboie
    et les humains proches se retournent."
  - `select.best`: "{0} s"
  - `select.none`: "-"
- **Tuning additions:**
  - `DoorAreaBase` 3, `LeafThickness` 0.04, `LeafSampleInset` 0.1, `RailingThickness` 0.05,
    `DoorSwingDegrees` 90, `AuditOpenSamples` 6, `WakeTelegraph` 0.6,
    `AuditLevelBudgetSeconds` 240;
  - `DoorReach` becomes 0.85, and `DoorFacing` is dropped;
  - `DogConeColor` is `static readonly`.
- **The validator** also checks:
  - leaf, hinge, swing and id only on doors;
  - at most one dog, and known `kind` values;
  - `sleep` only on dog stations;
  - the lesson prerequisites (door: a closed leaf; pet: a dog; final: both, plus a platform);
  - a route `open` names an existing leaf;
  - rugs and seat homes neither on a ramp nor straddling heights.
- **Wording:** "build time" in section 7 means level build. "L or U shapes" means rooms joined by
  a full-width doorway (as supported today).
