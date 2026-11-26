# Contract M5 v4 + v5 amendments (section 16) - "La maison": 17 levels that combine mechanics

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
- `tools/unity.sh` for every Unity call, with `OUTOFSIGHT_AGENT=<agent>`;
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

Unchanged rules: v3 15.1 to 15.6. The dog uses the `dog` row of `PersonalityDef`. Since section 20, the
bark also sends the dog to hold the furniture until a human puts it back.

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

---

## 16. v5 amendments (binding; they override sections 1 to 15 and v3 where they conflict)

From the contract critic's review of v4 (5 blockers, 11 majors). Decided by the integrator. The
machine has 2.9 GB of free RAM, so there is no second Unity editor: one lock, two waves.

### 16.1 Binding text (B4)

- v3 sections 2, 3, 4, 6 and 8 stay binding **as amended by v3 15.x**:
  - the platform and ramp JSON;
  - the leaf rules;
  - the bark, its accumulator, `sleep` stations and the dog eye;
  - the save format, unlocking, and Play picking the first unwon level;
  - the moving and still sight tables.
- v3 sections 1, 5, 7, 9 to 13 and 15.9 are replaced by v4 and v5.
- **The stub list of 16.12 is binding.** The integrator lands it before any builder starts, with
  the LevelDef fields first (`LevelJson` rejects unknown members).

### 16.2 Two waves (M10)

- **Wave 5A:**
  - doors, the dog, the split level, personalities, patterns, the save and the level select;
  - the audit's performance rework and its extension to these mechanics;
  - levels 8, 12, 14 and 16.
  - Gate 5A: verify, critic, fix wave, mutations.
- **Wave 5B:**
  - the robot, the rocking chair and the load;
  - levels 9, 10, 11, 13, 15 and 17;
  - step 40 over 17 levels.
  - Gate 5B closes M5.
- levels.json grows with each wave in play order: wave 5A ships 11 levels (1 to 7, 8, 12, 14,
  16), renumbered only at the end of 5B.
  - The level ids keep their final numbers (`level12` stays `level12`); only the manifest order
    matters.
  - LevelDataM2Tests' manifest count is 11 after 5A and 17 after 5B.

### 16.3 Audit performance (B1, B2, M1, M2)

- **A dedicated `audit` agent** owns `Editor/LevelAudit.cs`. It starts in wave 5A with
  **performance first**, on the 7 M4 levels, before any extension.
- **Out of the gate for levels 8 to 17:** the start-delay sweep and the slack report. Both stay
  behind `-sweep` and `-slack`, for design use only.
- **Noise tables.** `Heard[sample, cell]` is precomputed per noise class, with the listener's
  hearing factor, the robot hum masking and the margin already applied. A move becomes table
  lookups.
- **Occlusion cache.**
  - Key: the quantized eye position (0.01 m, y included) and the door mask.
  - Value: which ring points are visible, ignoring the cone. Range, angle and yaw then cost a
    cone test only, so turns and glances hit the cache.
  - Rays that miss every leaf's swing volume are shared by every mask.
  - Misses are batched with `RaycastCommand`.
- **Per-watcher everything:** eye height (sitting, floor), range, half angle, hearing factor, and
  still-seen tables per tolerance class (at most 3), with `InPlaceRadius` and `ExplainedRadius`
  derived from each tolerance. A warning is printed when a tidy or watchful level puts a spawn
  or decoy off the cell grid.
- **The loop length** is the longest routine's period, or none for wander, in which case there
  is no sweep.
- **Deterministic budget.** A cap on nodes expanded and rays cast per level
  (`Tuning.AuditNodeCap`, `Tuning.AuditRayCap`, set by the audit agent after measuring). Seconds
  are printed and warned above 240, never enforced.
- **Variants are table edits, never rebuilt levels.**
  - `pet`: the dog's tables recomputed with a 1.6 m eye.
  - `split`: platform and ramp cells barred to the player.
- **Flags:** `-auditLevels <ids>`, `-fixtures <ids>`, `-skipFixtures`, `-sweep`, `-slack`.
- **Integrator:**
  - `verify.sh`'s audit stage timeout becomes 1.3 times the sum of the per-level warnings
    (computed from the manifest), or the stage runs in batches;
  - Audit-mode mutations pass `-auditLevels` and `-fixtures`.

### 16.4 Tooling (B2, M11)

- `tools/unity.sh` never takes over a live holder. The holder refreshes the lock's timestamp
  every 60 s, and a lock is stale only when its process is dead (integrator, done before wave 5A).
- **Builders run filtered tests only** (`--filter`). The full PlayMode suite, the full audit and
  the player are run by the integrator.

### 16.5 The load: a kinematic rule (B3, M5), option A

- **The rule.** The load falls when `|v(t) - v(t - Tuning.LoadWindow)| >= Tuning.LoadFallDeltaV`.
  - v is the furniture's planar velocity, measured each fixed step.
  - The window is 0.5 s; the threshold is 1.8 m/s.
- **The load does not change how the furniture drives.**
  - `LoadAccelFactor` and the doubled glide are dropped.
  - The M1 instant stop is unchanged: the chair's full stop is a change of 1.5 m/s, so the load
    holds.
- **What falls and what holds:**
  - falls:
    - a 90 deg turn at full chair speed (2.12);
    - any full-speed reversal;
    - the office chair's full start or full glide (2.8);
    - careful U-turns of the stool (2.4) and of the office chair (2.8);
  - holds:
    - the chair's straight starts and stops (1.5);
    - every careful straight move;
    - a careful 90 deg chair turn (1.06);
    - a careful chair reversal (1.5);
    - the robot shove (0.5).
- **The visual.** The spring of section 6 drives only the sway of the load's visual; it decides
  nothing.
- **The balance gauge** shows `|dv| / LoadFallDeltaV` over the window.
- **`Core/MotionProfile`** (core): a pure synthesis of the driving rules (acceleration, braking,
  careful mode, the stool's stages, the glide), the velocity per step for a sequence of wishes.
  - It feeds the EditMode targets, the samples per cell, the slide samples and the audit's
    `load` lesson.
  - Probe step 44 checks it against FurnitureController within 0.05 m/s.
- **The load is inside the sample box.** With a load, the furniture's sample box grows by the
  load's height (`Tuning.LoadHeight` 0.25), and so do the audit's rings. A vase seen above a sofa
  is a furniture seen.
- **The audit.**
  - The search state gains the velocity of the last 0.5 s (the last move direction and the
    samples since).
  - A schedule that drops the load is invalid.
  - Lesson `load`: the schedule found with the load rule off drops the load when simulated.
- **No load on the rocking chair or the floor lamp** (validator).
- PRD 3.4 is rewritten accordingly (integrator).

### 16.6 The split level (B5)

- **Ramps.** Replace v3 15.4's step-offset rule with a continuity rule: a move is allowed when
  the floor along it is continuous with a slope of at most `RampMaxSlope`. Only height
  discontinuities are forbidden.
- **Lesson `split`:** no schedule when the platform and ramp cells are barred to the player (a
  cell mask).
- **Widths.** Ramps and corridors used by the armchair are at least 1.5 m wide, with their axis
  on the audit's cell grid. Elsewhere, 1.2 m.
- **The mezzanine must matter** in level 14 and level 17: the `split` check binds. Either the
  route needs it, or watchers stand on it and the edge hides the floor below from them.

### 16.7 Patterns (M2)

- **The LCG:** `x = (int)((1103515245L * x + 12345L) & 0x7FFFFFFF)`. Advance before each draw.
  The seed is in [0, 2^31 - 1].
- **Draws are indexed by visit:**
  - the k-th station visited is `f(seed, k)`;
  - resumes and interruptions never advance k, and the station already drawn for the current
    visit is reused;
  - pingpong keeps its direction state.
- **The walk check** (audit) enumerates the reachable ordered pairs: n for a loop, 2(n - 1) for
  pingpong, n(n - 1) for wander. Every one must avoid closed leaves.
- **Habits are audit warnings on manifest levels, not validator errors:**
  - dreamer dwells average 4 s or more;
  - watchful glances in every dwell of 2 s or more;
  - granny sits at least once in any 60 s;
  - hurried dwells average 2 s or less;
  - teen dwells 3 s or more on average, with glances under 30 deg.

### 16.8 The robot (M3)

- **No collider;** inhabitants may walk across its disc (cosmetic; written back to the PRD).
- **No shove** during any action (rock, door, toggle, fall, righting, push), while lying, pinned
  or carried. The robot just reverses.
- **"Blocked by a wall" reads "blocked by any collider".** The shove's velocity profile is
  constant over 0.5 s (0.5 m/s), so the load holds.
- **The audit's contact zone:** `RobotRadius` + the footprint's half diagonal + 0.1 m (replay
  release) + the robot's travel over the margin. It is checked at every sample along moves, and
  at the spawn during the start delay. Hum masking in the audit holds only if every sample of
  the margin window is within `RobotHumRadius` minus that travel.
- **The validator:**
  - at most one robot per level;
  - its loop on floor level (not on a platform or ramp), outside leaf swing sectors;
  - at least 1 m from the spawn, seat homes and the exit;
  - `start` is a waypoint index.
- **Pairing:** the robot is paired with good listeners (default, watchful or tidy), so the hum
  matters.

### 16.9 The rocking chair (M4)

- **"Comes to rest":** the first step at or below both moving thresholds after a step above
  them, measured on travel and yaw only. A step inside an action, a shove, a put-down or a pin
  never counts. Holding a key into a wall therefore does not loop rocks.
- **No load on it** (16.5).
- **The audit** searches it at full speed, with 8-sample stops. Careful stops (0.4 s) are a game
  nicety, not searched.

### 16.10 Levels, revised (M7, M8)

| Level | Name | Body (load) | Rooms | People | Mechanics | Lesson | Wave |
|---|---|---|---|---|---|---|---|
| 8 | Les portes | chair | 4 | dreamer (loop) | 2 closed leaves | door | 5A |
| 9 | Le robot | chair | 4 | watchful (loop) | robot, hard floors and rugs | robot | 5B |
| 10 | Le fauteuil à bascule | rocking_chair | 4 or 5 | granny (loop, sits) | rocking | rock | 5B |
| 11 | Le vase | chair (vase) | 4 | tidy (loop) | load | load | 5B |
| 12 | Le chien | stool | 5 | dreamer (loop), dog (sleeps) | dog, low cover | pet | 5A |
| 13 | Roulettes et vase | office_chair (vase) | 5 | hurried (pingpong), watchful (loop) | load, glide, office chair decoys | load | 5B |
| 14 | La mezzanine | armchair | 6 | granny (sits on the player), tidy (wander) | platform and ramp, sitting | split | 5A |
| 15 | La bascule et le robot | rocking_chair | 6 | teen (wander), watchful (loop) | robot (a shove means a rock), rocking | robot | 5B |
| 16 | La nuit | floor_lamp | 4 | watchful (loop), hurried (pingpong), dog | dark, dog, 1 closed leaf away from switch-off spots | dark | 5A |
| 17 | La maison | chair (vase) | 7 at most | granny, teen, tidy, dog | doors, robot, platform, load | final | 5B |

- `person.dog` "Le chien" / "Il voit bas et aboie quand tu bouges." is added for the intro card.
- `intro.here` "Ici : {0}" takes the names joined by ", ".
- **Strings changed:**
  - `level11.hint` "Pas de virage brusque avec le vase. Maj pour aller doucement."
  - `level15.name` "La bascule et le robot"
  - `level15.hint` "Près du robot, on n'entend pas tes pas. Une chute s'entend toujours."
  - `person.hurried.trait` "Il marche vite et entend mal."
  - `person.tidy.trait` "Le moindre meuble déplacé, elle le remarque."
  - `person.watchful.trait` "Elle jette souvent un œil autour d'elle."
- `CameraMaxDistanceHouse` 16 is written back to PRD 3.1. The distance bound scales with the
  house extent, up to 16 m; levels 1 to 7 keep 2.5 to 6.0.

### 16.11 Budgets and gate (M6, M9)

- **Character palette.** ModelKit uses a fixed palette for characters: 8 shared colours plus one
  tint per personality. Every human and the dog map onto it, so 3 humans and a dog add at most
  12 materials.
- **The material budget counts material slots** (draw calls), not renderers.
- **Before freezing 160 and 32,** the house agent builds an 8-room mock level
  (`test_m5_house_mock8.json`) after M4.2, and the integrator measures it in the built player.
  The numbers are revised then if needed.
- The Animated Woman (41 bones) stays allowed under the human bone limit only if the watchers
  agent finds it at 40 or fewer after import; otherwise the 5 staged same-rig Quaternius humans
  (31 bones) are used.
- **Step 45** is one test per level, each under its own `[Timeout]`. RouteReplayer caps a run at
  the route end + 30 s of game time.
- **"The probe writes the real save"** is killed by an EditMode test of a pure
  `SaveStore.ChoosePath(bool editor, bool probe, bool look, string persistent, string temp)`.
- **The player stage timeout** (`verify.sh`, the `timeout 300` on the probe run) becomes 900.
  60 fps is reported per level; the gate fails only when a level's median frame time is above
  33 ms (under 30 fps on PC).
- `PROBE_STEPS` and `EDIT_TESTS` gain every new step and killer test (integrator).

### 16.12 Agents (eight builders)

core, house, watchers, bodies, game, ui-save, **audit** (`Editor/LevelAudit.cs`) and **levels**
(`Resources/Levels/*`, `RouteReplayer.cs`, `ProbeTestsM5Levels.cs`, the manifest test). The rest
of section 11 stands. `ProbeTestsM42Rig.cs` (M4.2) goes to watchers.

**Stub list (binding, landed by the integrator; the owner in brackets fills it):**
- **Core:**
  - `PersonalityDef` [core]:
    - `Id, NameKey, TraitKey, Model, Tint`;
    - `WalkSpeed, ViewRange, HalfAngle, EyeHeight, HearingFactor, SuspicionFactor, Tolerance,
      CarryFactor`;
    - `Memory, Hears, CountsForCatch, CountsForExit, Sits, Barks`;
    - `For(string)`, `ForInhabitant(InhabitantDef)` (a dog's kind wins);
    - id constants.
    - An explicit `InhabitantDef.Model`, `BodyColor` or `HeadColor` wins over the personality's.
  - `RoutinePatterns` [core]: `Loop`, `PingPong`, `Wander` and `int WanderNext(ref int x, int
    current, int n)`.
  - `InhabitantRoutine` [core]:
    - `Personality, Pattern, Seed, VisitIndex, Floor`;
    - `Asleep, InvestigatePlanner, Seats, SeatOwner`;
    - `BeginPutAway(Vector3)`, `JustPutAway`.
  - `RoutineFactory.Create` [core], with the v3 15.6 signature.
  - `SeatRegistry`, `SaveData`, `RecordResult` [core], as in v3 section 9.
  - `Hearing` [core]: `NoiseKind.Bark` and `Crash`; `Hears(listener, e, factor)`;
    `IsMasked(kind, at, robots)`; `RadiusOf` and `RetargetsAlerted` extended.
  - `FurnitureMemory(float tolerance)` and `Tolerance`; `SuspicionMeter.GainFactor` [core].
  - `BodyDef.Rocks`, `BodyKinds.RockingChair` and its row [core].
  - `MotionProfile` [core]: `Synthesize(body, careful, wishes, dt)`, `StopDistance`,
    `SlideSamples`.
  - `LoadBalance` [core]: `DeltaV`, `Ratio`, `Fallen`, `Step(dt, velocity)`, `Reset`, plus
    `SwayTilt` for the visual.
  - `RobotPath` [core]: a constructor taking a `RobotDef`, `PositionAt(t)`, `HeadingAt(t)`,
    `Reverse(t)`, `Length`.
  - `FloorMap` and `DoorGeometry` [house], as in v3 15.2 and 15.4.
  - `LevelDef` [house]:
    - `Platforms`, `Ramps`;
    - `Robots`, each a `RobotDef` with `Name`, `Loop`, `Speed` and `Start`;
    - `Floor`, `FloorHeightAt`;
    - `SpawnDef.Load`;
    - `InhabitantDef.Kind`, `Personality`, `Pattern`, `Seed`;
    - `StationDef.Sleep`;
    - `OpeningDef.Leaf`, `Hinge`, `Id`, `Swing`;
    - `RouteStepDef.Door`, `ActionOpen`;
    - lesson constants `Door`, `Pet`, `Final`, `Robot`, `Rock`, `Load`, `Split`.
- **Runtime:**
  - `FurnitureController` [bodies]:
    - `BeginExternalAction(float)`;
    - `bool BeginPush(Vector3 dir, float dist, float time)`;
    - `BodyAction.Rock`, `Push` and `External`;
    - `Rocking`, `RockCount`;
    - `Load` (a `LoadBalance`), `SetLoad(string kind)`, `LoadFallCount`;
    - `GlideTime`, `StopDistance`.
  - `InputReader` [bodies]: `BackPressed()`, `InjectBack()`.
  - `Robot` [watchers draws it, game steps it]: `Robot.Create(RobotDef, Transform parent)`,
    `Path`, `SetPose(Vector3, float)`.
  - `LoadView` [watchers]: `LoadView.Create(string kind, Transform furniture, Vector3
    bodySize)`, `SetTilt(Vector2)`, `SpawnClue(Vector3)`.
  - `LevelInstance` [house]: `Robots`, `Leaves`, `OpenMask`, `AreaMask()`, `PlannerFor(int)`,
    `Floor`.
    - LevelBuilder calls `Robot.Create`; `FurnitureController.SetLoad` creates the LoadView.
  - `DoorLeaf` [house], as in v3 section 9; `NavPlanner.TryPlan(from, to, corners, areaMask)`
    [house].
  - `Inhabitant.Personality` [watchers].
  - `Vision.Test(eye, fwd, samples, range, halfAngle, visible)` [game].
  - `Hud` [game]: `HudEye.Dog`, `ShowDoorHint(bool)`, `SetBalance(float ratio, bool visible)`,
    `ShowPeople(IList<string>)`, `WinPanel`.
  - `GameState` [game]: `ShoveCount`, `CrashCount`, `ClueActive`, `BarkCount`.
  - Save and menus [ui-save]:
    - `SaveStore`: `PathOverride`, `UnlockAll`, `Current`, `Load`, `Save`, `RecordWin`,
      `Recorded`, `ResetForTests`, `ChoosePath`;
    - `LevelSelect`, `RecordLine`;
    - `Menu.LevelsButton`, `Menu.LevelSelectOpen`, `Menu.OpenLevelSelect()`.
- **Editor:** the flags of 16.3; `Result.RuntimeSeconds`, `Nodes`, `Rays` [audit].

---

## 17. Wave 5A.1 fix wave (binding; from the adversarial result critique of wave 5A)

The critique (six dimensions, an adversarial refuter per dimension) confirmed 1 blocker, 5 majors and
21 minors. The full list is the integrator's file `scratchpad/integrator/critic5a_synthesis.txt`.
Decisions:

- **Budgets count draw calls as material slots** (16.11), in the audit, the probe and the tests. The
  house number stays 160 and 32 for now. The 8-room mock is at 195 slots, so the number is decided in
  5B against level 17 (7 rooms at most), by cutting slots first (brows, multi-slot props).
- **The built player measures the frame time** per level (median and p95 over the start view). The
  gate fails above `Tuning.FrameTimeFailMs` 33 ms; 60 fps is reported.
- **The dog's cone is cyan** (`Tuning.DogConeColor` 0.25, 0.85, 0.85): yellow and red stay the humans'
  calm and alarm, deep blue stays the x-ray. Its derived values move to Tuning.
- **Level 12's cover is a real sofa**, so the hint stays true, and a human hears the dog during the
  route window. Level 14 starts with the armchair in view and brings Mamie's first sit to about 8 s.
  Level 16 stays at 24 materials in play, dog cone included.
- **A leaf is sampled on all 30 steps of its swing** (v3 15.2).
- **The dark lesson's free-pass check** uses only watchers with memory and each one's own dark range.
- Deferred to 5B, tracked: audit fidelity items m2, m3, m4 (E action modelling, fixtures for a door
  seen and tolerance classes, the rest height of the samples), the cone under the mezzanine (m14) and
  the dog fan superset (m20).

**5A.1 level layout changes** (written back from the levels agent):
- level 12: the kitchen-salon door is removed, the entree door is at z 5.75, the Banc is replaced by
  two low sofas (so `level12.hint` "le canapé te cache de lui" is true), and Paul starts at a new salon
  window station, within earshot of the dog during the route;
- level 14: the bookshelf is 1.2 m high (the armchair is in view at the start), Mamie starts at
  station 0 (first sit at 5 s), and Lea's first kitchen dwell is 24 s;
- level 16: the decor colour #6B4226 is dropped (24 materials in play, dog cone included).

---

## 18. Wave 5B decisions (binding)

- **The rock and the load live in GameState**, as the game agent built them when the bodies agent
  could not run:
  - the rock: the 16.9 come-to-rest rule, then `BeginExternalAction` for RockTime (RockCarefulTime
    when careful), with a pitch visual and a creak;
  - the load: `GameState.Load` (a LoadBalance fed with the furniture velocity after its step) sways
    the LoadView, drops the clue, emits the crash, and grows the sample box through Vision.
  - `FurnitureController.SetLoad`, `Load` and `LoadFallCount` are not needed. The level builder makes
    the LoadView directly (no reflection, which managed code stripping could break in the player).
- **The shove** is a real `FurnitureController.BeginPush(direction, distance, time)` with
  MotionProfile semantics. It replaces the game's stand-in extension method, which GameState calls
  through the same signature.
- **The balance gauge** sits to the left of the creak gauge (no room above the controls line). A
  clue costs one discovery per fall. A stool that tips over keeps its load (only the kinematic rule
  drops it).

---

## 19. Wave 5B.1 fix wave (binding; from the adversarial result critique of wave 5B)

The critique synthesis lists every item with its evidence (B1 to B3, M1 to M10, m1 to m15). The
integrator's decisions:

- **B1, the load's triangles.** The load is its own object for the budgets, as the audit already
  counts it: the probe subtracts the LoadView from the furniture and checks the load on its own key
  ("Load vase") against the 400 triangle budget. PRD 7.4 is written back.
- **B3, the shove.** `|| shoveMoving` goes (the push action already makes the furniture move), and
  so does the `!Shoving` that repeats `!furniture.ActionActive` in StepRock. The marker moves to
  FurnitureController.EndStep ("the push is not moving"), killed by Step42b_, Step42c_, Step42g_.
- **M5, a free vase drop.** Open question 25 stands: a fallen load costs one discovery, never the
  level. The levels make it cost: a listener with memory within crash range of the start area and of
  the early corners on levels 11 and 17, and a counter-route "drop at the spawn, then full speed" that
  must not win.
- **M8, audit fidelity m2, m3, m4** (E action modelling, door-seen and tolerance-class fixtures, the
  sample height) are **deferred to M6**, with the full M7 sight rework (ring, centre and intermediate
  moves, the sliver fixture). M7's minimum lands now: a post-search fidelity replay of every schedule
  with the game's own Vision.Test points (5 points, release offsets, intermediate positions every
  0.1 m, the move yaw) that fails on any sighting.
- **m4, the character slot merge** is removed (code, flag and mutation row): every level holds its
  draw-call budget without it (verify 5B), so section 17's "cut slots first" is not needed.
- **m12, hints:** `level13.hint` "Maj pour démarrer et tourner : chaque arrêt glisse, et le vase
  tombe au moindre à-coup." and `level15.hint` "Près du robot, on n'entend pas tes pas. Le fauteuil
  se balance après chaque arrêt."
- **m13:** `Tuning.BalanceWarning` is 0.9 (the gauge turns red only near a real fall).
- **Level 17** (M3): the first leg out of the bedroom before about 15 s, the whole route under about
  45 s, no loitering stretch above the 8 s cap under the fixed wait rule (M2).
- **Level 10** (M4): a schedule that only waits and drives must stop inside a cone between two watch
  windows (a real rock lesson); Step45p asserts the rock is seen within the caught grace.
- Waiting for the improvement loop: m3 probe gaps beyond the contract minimum, m8, m10, m15, and the
  rest of the minors the fix wave does not reach.

**19.1 Scope cut (product owner, 2026-11-15: very few credits left; overrides section 19 and the
agent prompts where they ask for more).** Do the smallest work that turns the gate green, nothing more:
- **levels:** fix ONLY the levels the new audit rejects, with the smallest data change (a station,
  a glance, a spawn), then re-audit just those levels with -writeRoutes and run PlayMode filtered on
  their Step45 replays. The level 17 dead time (M3), the level 10 rock lesson (M4), the vase drop
  cost (M5), their counter-routes and the RouteReplayer guard go to the improvement loop, unless a
  rejected level needs them anyway. No final full audit and no Step40 run: the integrator's verify
  does that.
- **integrate:** the mutation.sh rows and the verify.sh lists only, plus a short PRD v1.10 (the 3.4
  rewrite and five to ten lines of section 11 5B notes) and a README 5B gate section of a few lines.
  The CONTRACT_M5 section 12, 13 and 16.12 cleanup is skipped.
- Every agent: few Unity runs, short reports.

---

## 20. The dog's hold (binding; product owner, 2026-11-19: "the dog does nothing when it detects you")

Amends v3 4 and 15.5 (the bark stays exactly as it was: 0.2 s grace, 6 m noise at the dog, 3 s cooldown,
never a catch). What follows the bark is new:

- **The run.** With the memory rule on, a bark sends its dog running to the furniture
  (`InhabitantRoutine.BeginRun`): mode Investigating ("!" over the dog), `Tuning.DogRunSpeed` 2.6 m/s
  (faster than every body), turns telegraphed as always, the investigate planner (current doors). One run
  at a time. A furniture that moved on is chased again from where the dog stopped; one it cannot reach
  ends the run. A hidden or carried furniture starts none.
- **The hold.** Within `InvestigateReach + CarryReachMargin` (0.9 m) the dog holds it: the furniture is
  **pinned** with the sat-on pin (no input, never moving, no action, the creak paused), the HUD shows
  `hud.dogHold` ("Le chien te bloque : on vient te remettre en place.", the dog eye as its icon) instead
  of the sat-on line, and the dog barks at it every `Tuning.DogHoldBarkInterval` 0.8 s (a sound only: no
  bark of the rule, no noise event, `BarkCount` unchanged).
- **The human, as always.** The nearest human free to come (memory, Routine or Alerted, not frozen, on no
  lamp, clue or door errand) is sent with `Investigate`, "!" over him. On arrival, his memory decides,
  exactly as a sighting would (`FurnitureMemory.OutOfPlace`, tolerance and same-kind decoys): out of
  place, **one discovery** (his suspicion gain; suspicion 1 loses as usual), then the usual carry back
  to his slot; in place, nothing. No path: he gives up and accepts the furniture where it stands (M2.1
  11.4). Any other human who sees it out of place meanwhile discovers it and carries it as usual.
- **The end.** The dog lets go on the put down, when the sent human goes back to his routine without a
  carry, when nobody could be sent for `Tuning.DogHoldMaxWait` 6 s, or when the dog is interrupted; it
  then resumes its routine as after an investigation.
- **Decision: a setback, not a catch.** The dog never catches (v3 4 holds). Its hold costs what a human's
  discovery costs: the ground gained (the carry back) and one discovery when the furniture is out of place,
  never the level by itself (the same rule as a fallen load, open question 25).
- **Audit.** Unchanged: a schedule the awake dog sees moving is already forbidden (v3 8), so an audited
  schedule never starts a run, and the designer routes already assert 0 barks.
- **Probe.** Step38h (out of place: run, pin, loop barks, call, one discovery, carry back, release) and
  Step38i (in place: no discovery, no carry, release). Tests that freeze the dog with a pin keep the old
  behaviour (a frozen dog never runs).
