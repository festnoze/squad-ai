# Contract M5 v4 - "La maison": 17 levels that combine mechanics (for critique)

Build contract for milestone M5 of [PRD.md](PRD.md) v1.7. The product owner rewrote M5 after the
M4 playtest:
- 10 new levels (8 to 17) that combine mechanics, in larger maze-like houses;
- several inhabitants with personalities and patterns;
- three new mechanics: the robot vacuum, the rocking chair, and the load and balance;
- the doors, the dog and the split level of the first M5 plan, kept as mechanics to combine;
- level select, best times, save.

Same method as M2 to M4:
- the PRD wins;
- the integrator decides;
- every interpretation goes back into the PRD;
- everything of M1 to M4 keeps working (levels 1 to 7 unchanged).

**Inherited, binding.** The v3 contract is archived in
[CONTRACT_M5_v3.md](CONTRACT_M5_v3.md). These sections of its section 15 stay **binding as
written there**, except where this v4 changes them:

| v3 section | Subject | v4 change |
|---|---|---|
| 15.1 | one NavMesh, door areas, frozen station walks | none |
| 15.2 | door geometry in Core, the opening, E rules, leaf samples | none |
| 15.3 | the audit and doors | none |
| 15.4 | the split level everywhere (`FloorMap`, railings, ramps) | none |
| 15.5 | watchers in code (dog, `Vision.Test` overload, retarget, eye resets, wake telegraph, HUD precedence) | `WatcherDef` becomes `PersonalityDef` (section 3) |
| 15.6 | routine factory, seat registry | the factory also takes the pattern and the personality |
| 15.7 | the save | none |
| 15.8 | budgets: the combine key | the house budgets of PRD 7.4 v1.7 (section 9) |
| 15.10 | gate additions (`test_cross`, probe save redirect, timeouts, level select details) | 17 cards; step numbers of section 12 |

v3 sections 1 to 13 and 15.9 are replaced by this document.

---

## 1. Ground rules

As in M3 and M4:
- own your files (section 11); never edit another owner's file, ask the integrator;
- additive APIs: no M1 to M4 member renamed or removed;
- `tools/unity.sh` for every Unity call, with `MEUBLE_AGENT=<agent>`;
- tests that can fail, with premise guards; waits bounded by game time, never by frames;
- every PlayMode TearDown calls `InputReader.ResetInjections()` and `SaveStore.ResetForTests()`;
- no em-dash character anywhere; comments and docs in English;
- constants in Tuning, French strings in Strings (integrator);
- scratch files in `scratchpad/<agent>/`;
- never run `mutation.sh`;
- never edit `verify.sh` or `mutation.sh` (the integrator writes them atomically).

## 2. Houses (maze-like)

- **Size.** 4 to 8 rooms per level for levels 8 to 17. Rooms are joined by doorways, with
  corridors at least 1.2 m wide, at least one loop in the room graph from level 10 on, and dead
  ends allowed.
- **The camera** (house):
  - `OrbitCamera` keeps the player framed in large houses: zoom bounds scale with the house
    extent (`Tuning.CameraMaxDistanceHouse` 16 m);
  - WallFader keeps fading the walls between the camera and the player, as today.
- **Doors, the split level, `FloorMap`, railings and ramps:** v3 15.1, 15.2 and 15.4.
- **NavMesh voxel and audit cell sizes** stay as today. Larger houses cost audit time
  (section 10).

## 3. Personalities and patterns (PRD 5.3, 5.4)

**`Core/PersonalityDef`** (core) replaces v3's `WatcherDef`.
- `PersonalityDef.For(string id)` returns a new instance on every call. Null and unknown ids
  give `default`.
- `inhabitants[].personality` selects it. `inhabitants[].kind: "dog"` selects the `dog` row,
  whatever the personality.

| id | Name key | Walk | Range | Half angle | Hearing x | Suspicion x | Tolerance | Carry x | Memory | Hears | Catch | Exit | Sits | Barks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| default | (none) | 1.2 | 10 | 55 | 1.0 | 1.0 | 0.75 | 1.0 | yes | yes | yes | yes | yes | no |
| dreamer | person.dreamer | 0.9 | 8 | 45 | 0.7 | 0.7 | 0.75 | 1.0 | yes | yes | yes | yes | yes | no |
| watchful | person.watchful | 1.2 | 10 | 60 | 1.0 | 1.5 | 0.5 | 1.0 | yes | yes | yes | yes | yes | no |
| hurried | person.hurried | 1.7 | 10 | 50 | 0.5 | 1.0 | 0.75 | 1.2 | yes | yes | yes | yes | yes | no |
| granny | person.granny | 0.8 | 7 | 55 | 0.6 | 1.0 | 0.75 | 0.8 | yes | yes | yes | yes | yes | no |
| teen | person.teen | 1.1 | 6 | 35 | 0.4 | 0.8 | 0.75 | 1.0 | yes | yes | yes | yes | yes | no |
| tidy | person.tidy | 1.2 | 10 | 55 | 1.0 | 1.3 | 0.4 | 1.3 | yes | yes | yes | yes | yes | no |
| dog | (none) | 1.4 | 6 | 70 | - | - | - | - | no | no | no | no | no | yes |

- **Column meanings.**
  - Hearing x scales every noise radius heard by that inhabitant.
  - Suspicion x scales every suspicion gain.
  - Tolerance replaces `DisplacementTolerance` in its memory.
  - Carry x scales its carry speed.
  - The eye height is 1.6 m for humans and 0.35 m for the dog.
- **Fairness invariants**, the same for every personality and tested:
  - telegraph 0.6 s for any turn over 30 deg;
  - caught grace 0.2 s;
  - the wake telegraph (v3 15.5).
- **Habits are data, not rules.** Long dwells, rare or frequent glances and frequent sits are
  authored in the stations. The validator checks the numbers:
  - dreamer dwells average 4 s or more;
  - watchful has a glance in every dwell of 2 s or more;
  - granny sits at least once per loop.
- **Patterns.** `inhabitants[].pattern`:
  - `"loop"` (default): the M1 cycle.
  - `"pingpong"`: 0, 1, ..., n-1, n-2, ..., 1, 0, 1, ...
  - `"wander"` with `seed` (int):
    - the next station index is drawn by `x = (1103515245 * x + 12345) mod 2^31`, starting from
      `x = seed`;
    - `next = (x >> 16) mod (n - 1)`, skipping the current station (an index >= current is
      shifted by 1);
    - `n >= 3` is required.
  - Every pattern is deterministic, and the audit steps the same routine.
  - **Frozen station walks** (v3 15.1) cover every ordered pair of stations the pattern can
    produce.
- **Readability.**
  - Every personality has a visual identity: a model (the Quaternius man and woman, plus
    further CC0 rigged humans if the watchers agent finds them within budget) and a clothes
    tint.
  - The level intro card lists the people of the level: `intro.here` "Ici : {0}", then one line
    per person (name and trait).

## 4. The robot vacuum (PRD 4.8)

- **Data.** `robots[]`: `{ name, loop: [{x, z}, ...], speed, start }`.
  - Speed defaults to `Tuning.RobotSpeed` 0.4. At least 2 waypoints.
  - Straight segments; the validator checks they are free of walls, props, decoys and leaves,
    with the robot radius.
- **`Core/RobotPath`** (core): position and heading at time t along the loop, and `Reverse(t)`.
  It is deterministic.
- **The body.**
  - A disc of radius `Tuning.RobotRadius` 0.17 and height 0.09 (watchers builds the visual,
    procedural).
  - Not an occluder, not a NavMesh source, no collision with inhabitants (they may walk over its
    path; it is low).
- **Contact and the shove** (game, with bodies):
  - When the robot's disc would overlap the player furniture's footprint, the furniture is
    shoved by `Tuning.RobotPushDistance` 0.25 m along the robot's heading, over
    `Tuning.RobotPushTime` 0.5 s, through `FurnitureController.BeginPush(direction, distance,
    time)`: an action that counts as moving, with no input.
  - The robot then reverses its loop.
  - A pinned or carried furniture is not shoved: the robot just reverses.
  - A shove blocked by a wall stops at the wall.
- **The hum.** `Hearing.IsMasked(kind, position, robots)`: within `Tuning.RobotHumRadius` 2.5 m
  of a robot, Hop, Roll and Click noise events are not emitted. Topple, Creak, Crash and Bark
  are emitted.
- **The audit:**
  - the robot's timeline is fixed;
  - a cell within contact distance of the robot at time t is forbidden at t;
  - the hum masking applies to the noise rule.

## 5. The rocking chair (PRD M5)

- **The body.** `BodyDef` row `rocking_chair` (core):
  - size 0.6, 1.05, 0.85; radius 0.36;
  - max speed 1.2, acceleration 6, turn rate 240;
  - CarryForward 0.65, IsSeat true, the new flag `Rocks` true;
  - model: a Kenney rocking chair if the kit has one, else procedural.
- **The rock** (bodies).
  - When the furniture comes to rest after moving, it rocks for `Tuning.RockTime` 0.8 s (40
    steps), or `Tuning.RockCarefulTime` 0.4 s if careful mode was held at that moment. A turn in
    place that stops counts as coming to rest.
  - The rock is an action (`ActionActive`): moving, and input is ignored during it.
  - The visual pitches by `Tuning.RockDegrees` 9, decaying.
  - It is gated by `Rules.Bodies`.
- **Sat on:** pinned, as M4. The sitter's rocking is visual only.
- **The audit:** every stop costs `round(0.8 / 0.1)` = 8 unseen samples (4 when careful).

## 6. Load and balance (PRD 3.4)

- **Data.** `player.load`: `"vase"`, `"books"` or `"plant"`.
  - Allowed on chair, stool, armchair, office_chair and rocking_chair (validator).
  - Visual: a small procedural or Kenney object on top (watchers builds `LoadView`; bodies drives
    its sway).
- **`Core/LoadBalance`** (core), pure:
  - state: tilt (Vector2, deg) and tilt rate;
  - `Step(dt, Vector2 accelLocal)`, with `tiltAcc = -K tilt - C rate - G accelLocal`;
  - `Fallen` when `|tilt| >= Tuning.LoadFallDegrees`.
  - `accelLocal` is the furniture's actual planar velocity change per second, in its own frame.
    It includes braking and the centripetal part of turning, because it is measured from the
    velocity, not from the input.
  - Starting constants: `LoadGain` (G) 2.5 deg per m/s2, `LoadSpring` (K) 80, `LoadDamping` (C)
    9, `LoadFallDegrees` 20.
- **The furniture with a load** (bodies):
  - acceleration and braking are scaled by `Tuning.LoadAccelFactor` 0.5, so even the chair
    brakes in a short slide (moving);
  - the office chair's glide time doubles.
- **Behaviour targets** (core tunes the constants until these EditMode tests pass, on recorded
  velocity profiles from the real body table):
  1. chair at full input for 1 s, then release: falls;
  2. chair in careful mode for 1 s, then release: holds;
  3. chair, a 90 deg direction change at full speed: falls; at careful speed: holds;
  4. office chair at full input for 1.5 s, then glide: falls; careful, then glide: holds;
  5. stool, careful start and stop: holds;
  6. a robot shove from rest: holds.
- **The fall** (game):
  - a `Crash` noise at the load, of radius `Tuning.CrashRadius` 6 m, that retargets like a
    creak;
  - the load lies broken on the floor (a clue);
  - an inhabitant with Memory who sees the clue gets one discovery, investigates it, and on
    arrival puts it away (the clue disappears);
  - the furniture continues without a load.
- **The HUD** (game): a balance gauge (`hud.balance` "Équilibre") under the creak gauge, showing
  `|tilt| / LoadFallDegrees`. It turns red above 0.75.
- **The audit:**
  - with a load, every move is searched at careful speed;
  - every stop costs the slide samples;
  - the designer route is replayed in PlayMode, where the load must hold (the final arbiter);
  - a counter-route at full speed must drop it.

## 7. Doors, the dog, the split level

Unchanged rules: v3 15.1 to 15.6. The dog uses the `dog` row of `PersonalityDef`.

## 8. Levels 8 to 17

The levels agent may change a body, a personality or a room count with a written reason. The
lesson and the combination stay.

| Level | Name (`levelN.name`) | Body (load) | Rooms | People | Mechanics | Lesson |
|---|---|---|---|---|---|---|
| 8 | Les portes | chair | 4 | dreamer (loop), watchful (pingpong) | 2 closed leaves | door |
| 9 | Le robot | chair | 4 | hurried (loop) | robot, hard floors and rugs | robot |
| 10 | Le fauteuil à bascule | rocking_chair | 5 | granny (loop, sits), teen (wander) | rocking | rock |
| 11 | Le vase | chair (vase) | 4 | tidy (loop) | load | load |
| 12 | Le chien | stool | 5 | dreamer (loop), dog (sleeps) | dog, low cover | pet |
| 13 | Roulettes et vase | office_chair (vase) | 5 | hurried (pingpong), watchful (loop) | load, glide, office chair decoys | load |
| 14 | La mezzanine | armchair | 6 | granny (sits on the player), tidy (wander) | platform and ramp, sitting | split |
| 15 | Le robot et le tabouret | stool (books) | 6 | teen (loop), dreamer (wander) | robot, load, careful | robot |
| 16 | La nuit | floor_lamp | 6 | watchful (loop), hurried (pingpong), dog | dark, dog, 1 closed leaf | dark |
| 17 | La maison | chair (vase) | 7 or 8 | granny, teen, tidy, dog | doors, robot, platform, load | final |

- levels.json lists the 17 levels in order, and LevelDataM2Tests' manifest count becomes 17.
- Route actions: `"open"` with `door` (v3), plus the M4 ones.

## 9. Budgets (PRD 7.4 v1.7)

- Levels with 5 rooms or more: renderers <= `Tuning.BudgetHouseRenderers` 160 and materials <=
  `Tuning.BudgetHouseMaterials` 32. Below 5 rooms: 120 and 24, as before.
- The combine key of v3 15.8 applies.
- Character materials are merged by palette colour across characters (ModelKit's quantization),
  so 3 humans and a dog do not multiply materials.
- The built player measures the frame time on every level. The PC target is 60 fps (the probe
  reports the median and the 95th percentile per level).

## 10. Audit (levels)

- **Inherited:** v3 15.3 (doors, masks, reach cells, runtime) and 15.5 (the dog's tables), with
  the personality's range, half angle and eye per watcher.
- **Patterns:** the audit steps each routine through `RoutineFactory` with its pattern. The
  horizon is 300 s for levels 8 to 17. The start-delay sweep steps 3 s.
- **Robot, rock and load:** sections 4, 5 and 6.
- **Eye-pose caching** is required for runtime: most samples repeat a dwelling eye pose. The
  sight row of a quantized eye pose (position 0.01 m, yaw 0.5 deg) is computed once.
- **Per-level runtime budget** `Tuning.AuditLevelBudgetSeconds` 240, printed and enforced.
- **Lesson checks**, one per new mechanic, each with a strict and a relaxed fixture:
  - `robot`: either the hum binds (no schedule with the hum disabled) or the robot binds (the
    schedule computed without the robot collides with it). The report says which.
  - `rock`: the schedule computed without rocking is seen rocking.
  - `load`: the full-speed schedule drops the load in a `LoadBalance` simulation along its
    velocity profile.
  - `split`: no schedule with the platform removed.
  - `door` and `pet`: as v3.
  - `final`: at least three of the checks above bind.
- **Fixtures:**
  - `test_door`, `test_pet`, `test_cross` (v3);
  - `test_robot`, `test_rock`, `test_load`, `test_split`.
- **Separation** (v3 15.10): every pair of humans stays at least 0.6 m apart at every sample.
  Humans that share a level must "cross" (share a room at the same sample at least once).

## 11. Agents and file ownership (seven builders and the integrator)

| Agent | Files |
|---|---|
| **core** | `Core/PersonalityDef.cs` (new), `Core/SeatRegistry.cs` (new), `Core/SaveData.cs` (new), `Core/RoutineFactory.cs` (new), `Core/LoadBalance.cs` (new), `Core/RobotPath.cs` (new), `Core/InhabitantRoutine.cs` (patterns, personality, watcher eye, frozen walks, `InvestigatePlanner`, `Floor`), `Core/Hearing.cs` (Bark, Crash, masking, per-listener factor), `Core/VisionMath.cs`, `Core/FurnitureMemory.cs` (tolerance), `Core/SuspicionMeter.cs` (gain factor), `Core/BodyDef.cs` (rocking_chair), `Core/CaughtRule.cs` if needed, `Tests/EditMode/CoreM5Tests.cs` |
| **house** | `Core/LevelDef.cs`, `Core/LevelValidator.cs`, `Core/FloorMap.cs` (new), `Core/DoorGeometry.cs` (new), `Runtime/LevelBuilder.cs`, `Runtime/FurnitureKit.cs`, `Runtime/PrimitiveKit.cs`, `Runtime/DoorLeaf.cs` (new), `Runtime/NavPlanner.cs`, `Runtime/WallFader.cs`, `Runtime/OrbitCamera.cs`, `Editor/ProjectSetup.cs` (NavMesh areas), `Tests/EditMode/LevelDataM5Tests.cs`, `Tests/PlayMode/ProbeTestsM5House.cs` |
| **watchers** | `Runtime/Inhabitant.cs`, `Runtime/InhabitantRig.cs`, `Runtime/VisionConeView.cs`, `Runtime/ModelKit.cs`, `Runtime/ModelCatalog.cs`, `Editor/ModelCatalogBuilder.cs`, `Runtime/FootstepAudio.cs`, `Runtime/Robot.cs` (new, the robot's visual and transform), `Runtime/LoadView.cs` (new, the load's visual), models under `Assets/ThirdParty/Models/`, `Tests/EditMode/ModelM5Tests.cs`, `Tests/PlayMode/ProbeTestsM5Watchers.cs` |
| **bodies** | `Runtime/FurnitureController.cs` (rock, load factor, push, external action, load sway input), `Runtime/InputReader.cs` (`BackPressed`, `InjectBack`), `Runtime/GhostView.cs`, `Tests/PlayMode/ProbeTestsM5Bodies.cs` |
| **game** | `Runtime/GameState.cs` (single owner), `Runtime/Vision.cs`, `Runtime/Hud.cs`, `Runtime/Sfx.cs`, `Runtime/ProceduralArt.cs`, `Tests/PlayMode/ProbeTestsM5Game.cs` |
| **ui-save** | `Runtime/SaveStore.cs` (new), `Runtime/LevelSelect.cs` (new), `Runtime/RecordLine.cs` (new), `Runtime/Menu.cs`, `Tests/EditMode/SaveM5Tests.cs`, `Tests/PlayMode/ProbeTestsM5Ui.cs` |
| **levels** | `Editor/LevelAudit.cs`, `Resources/Levels/*.json` (levels 8 to 17, fixtures, levels.json), `Tests/EditMode/LevelDataM2Tests.cs` (manifest count), `Tests/PlayMode/RouteReplayer.cs` (new, shared), `Tests/PlayMode/ProbeTestsM5Levels.cs` |
| **integrator** | Tuning, Strings, docs (PRD, README, LICENSES rows given by watchers), `verify.sh`, `mutation.sh`, `tools/`, `Main.cs`, `Probe.cs`, `Tests/PlayMode/ProbeTestsM3Models.cs` and `ProbeTestsM3Rig.cs` (human-only checks), `Tests/EditMode/LicenseTests.cs`, all M1 to M4 TearDowns, every stub |

- **Test levels per agent:** `Resources/Levels/test_m5_<agent>_*.json`, owned by that agent,
  never in levels.json.

**Sequence.**
1. M4.2 (textures and the feet fix) green.
2. This contract critiqued; the integrator lands the stubs, Tuning and Strings.
3. In parallel: core, house, watchers, bodies, ui-save, and levels phase A (fixtures and drafts
   of levels 8 to 17 that load and validate).
4. game integrates GameState once core, house and bodies land.
5. levels phase B (the audit extension), then phase C (routes, replays, step 40) once game lands.
6. Full verify, result critic, fix wave, mutations, PRD notes v1.8, README gate.

## 12. Gate

**Probe steps** (a `b`, `c` suffix for variants; the owner in brackets):
- **36 doors** [house 36, game 36b to 36f]: v3 15.9 split.
- **37 inhabitants** [watchers 37, game 37b to 37f]:
  - separate memories and suspicions; every slot updated after a carry; a taken seat is a
    standing dwell;
  - each personality's range, angle, hearing, suspicion gain and tolerance applied;
  - pingpong and wander orders;
  - the telegraph identical for all;
  - the intro card names the people.
- **38 dog** [watchers 38, game 38b to 38f]: v3.
- **39 split level** [house]: v3.
- **40 full playthrough** [levels]: levels 1 to 17 in order through the real level flow, each on
  its designer route at offset 0, timeScale 8, the save checked after each win, ending on the end
  screen.
- **41 level select and save** [ui-save]: v3, with 17 cards.
- **42 robot** [bodies 42, game 42b to 42e]:
  - the loop timing;
  - a contact shoves 0.25 m in 0.5 s (moving), and seen means caught;
  - the robot reverses;
  - no shove while pinned;
  - the hum masks a hop at 2.4 m but not at 2.6 m, and never a creak.
- **43 rocking chair** [bodies 43, game 43b]:
  - rocks 40 steps after a stop, 20 when careful;
  - seen rocking is caught;
  - input ignored during the rock;
  - sat on does not rock in the rules.
- **44 load** [bodies 44, game 44b to 44d]:
  - the load factor on acceleration and braking;
  - the sway follows `LoadBalance`;
  - the fall makes a 6 m crash and leaves a clue;
  - the clue costs one discovery, and the finder puts it away;
  - the balance gauge.
- **45 levels 8 to 17** [levels]: designer routes at -0.2, 0 and +0.2 s, and the counter-routes:
  the load dropped at full speed, the robot collision, and the rock seen.
- The audit stage covers levels 1 to 17 and every fixture. The built-player stage covers every
  level's shot, budgets and frame time.

**Mutations** (each with its marker, file and killing step, given by the owner):
- from v3:
  - the dog's eye at 1.6 m;
  - the bark at the chair;
  - an open leaf keeps its closed collider;
  - leaf samples ignored while swinging;
  - the dog counts for the catch;
  - a slower best time overwrites;
  - the separation accepts 0.3 m;
  - the probe writes the real save;
  - a locked level is playable;
  - a station walk re-planned after an opening;
  - the eye ignores `FloorHeightAt`;
  - no wake telegraph;
- new:
  - the hum masks nothing;
  - the hum masks creaks;
  - the shove is not moving;
  - no rock after a stop;
  - the careful rock is as long as the full one;
  - the load fall angle is ignored;
  - the load factor is 1;
  - a personality's range is ignored (the teen sees 10 m);
  - the tidy tolerance is ignored;
  - wander ignores its seed.

## 13. Tuning names (the integrator adds them)

- **From v3:**
  - `DoorAreaBase` 3, `LeafThickness` 0.04, `LeafSampleInset` 0.1, `RailingThickness` 0.05,
    `DoorSwingDegrees` 90, `DoorReach` 0.85, `DoorOpenTime` 0.6, `LeafSampleCount` 4,
    `MaxLeavesPerLevel` 2;
  - `PlatformMinHeight` 0.6, `PlatformMaxHeight` 1.0, `RampMaxSlope` 20, `RailingHeight` 0.9;
  - `DogEyeHeight` 0.35, `BarkRadius` 6, `BarkCooldown` 3, `DogConeColor` (static readonly),
    `WakeTelegraph` 0.6;
  - `WatcherSeparation` 0.6, `BudgetPetBones` 46;
  - `AuditOpenSamples` 6, `AuditHorizonM5` 300, `AuditLevelBudgetSeconds` 240,
    `PlaythroughTimeScale` 8.
- **New:**
  - robot: `RobotSpeed` 0.4, `RobotRadius` 0.17, `RobotHumRadius` 2.5, `RobotPushDistance` 0.25,
    `RobotPushTime` 0.5;
  - rock: `RockTime` 0.8, `RockCarefulTime` 0.4, `RockDegrees` 9;
  - load: `LoadAccelFactor` 0.5, `LoadGain` 2.5, `LoadSpring` 80, `LoadDamping` 9,
    `LoadFallDegrees` 20, `CrashRadius` 6;
  - `BudgetHouseRenderers` 160, `BudgetHouseMaterials` 32, `HouseBudgetRooms` 5;
  - `CameraMaxDistanceHouse` 16.
- The personality numbers are data rows in `PersonalityDef`, like `BodyDef`.

## 14. Strings (the integrator adds them; French verbatim, no em-dash)

| Key | Text |
|---|---|
| level8.name / hint | Les portes / Une porte fermée cache tout. Ouvre-la (E) quand personne ne regarde. |
| level9.name / hint | Le robot / Le robot pousse ce qu'il touche, mais son bruit couvre le tien. |
| level10.name / hint | Le fauteuil à bascule / Il se balance après chaque arrêt : arrête-toi tôt. |
| level11.name / hint | Le vase / Freine en douceur, ou le vase tombe. Maj pour aller doucement. |
| level12.name / hint | Le chien / Le chien voit bas : le canapé te cache de lui. S'il te voit bouger, il aboie. |
| level13.name / hint | Roulettes et vase / Chaque arrêt glisse, et le vase penche. |
| level14.name / hint | La mezzanine / Monte par la rampe. Mamie s'assoit souvent : sois à ta place. |
| level15.name / hint | Le robot et le tabouret / Le robot rôde, le tabouret est fragile : profite de son bruit. |
| level16.name / hint | La nuit / Éteins-toi quand personne ne regarde. Le chien veille. |
| level17.name / hint | La maison / Tout ce que tu as appris, dans une grande maison. |
| person.dreamer / .trait | Le rêveur / Il traîne et regarde peu autour de lui. |
| person.watchful / .trait | La méfiante / Elle jette souvent un œil derrière elle. |
| person.hurried / .trait | Le pressé / Il marche vite et n'écoute pas. |
| person.granny / .trait | Mamie / Elle voit mal de loin et s'assoit souvent. |
| person.teen / .trait | L'ado / Le nez sur son téléphone : il voit peu, et de près. |
| person.tidy / .trait | La maniaque / Le moindre meuble de travers, elle le remarque. |
| intro.here | Ici : {0} |
| hud.balance | Équilibre |
| hud.door | E : ouvrir la porte |
| title.levels | Niveaux |
| select.locked / back / best / none | Verrouillé / Retour / {0} s / - |
| win.best / win.newBest | Record : {0} s / Nouveau record ! |

## 15. Open questions (PRD 12.2, 16 to 27)

See PRD v1.7: pet bones, the door key, seen opening a door, door memory, the bark, stacked
floors, the wardrobe, inhabitants opening doors, personalities, a fallen load, the robot's shove,
house budgets.
