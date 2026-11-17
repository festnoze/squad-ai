# Contract M2 - "Soupcon"

Build contract for milestone M2 of [PRD.md](PRD.md) (section 11, M2). The PRD gives the rules
and the starting constants. This document fixes everything else that several agents must agree
on: the exact rules, data schema, public APIs, fixed step order, file ownership and the tests that
make the gate. When this contract and the PRD disagree, the PRD wins and the contract is fixed.
Anything that remains ambiguous is decided by the integrator (the parent agent), never silently
by a builder.

Everything M1 does must keep working: `./verify.sh` stays green at every step, with every test
of M1.

---

## 1. Ground rules for builder agents

1. **Edit only the files you own** (section 9). If you need a change in a file you do not own,
   write it in your final report instead of making it.
2. **Never break the build for the others.** Changes to existing Core APIs are additive. Old
   signatures keep working, and new parameters are optional. Compile through the lock:
   `MEUBLE_AGENT=<your-name> ./verify.sh compile`. Run only your tests:
   `MEUBLE_AGENT=<name> tools/unity.sh test . --mode EditMode --filter "<Fixture>" --report-format junit --output TestResults/<name>.xml`
   Never call `unity` directly: always go through `tools/unity.sh`. It waits for the other
   agents' Unity runs.
3. **Compile errors in a file you do not own** are another agent's work in progress. Wait about a
   minute and retry. Do not touch that file.
4. **Code rules** (PRD 2 and 8.4):
   - English code and comments; French player strings, only from `Strings.cs`.
   - Async methods are prefixed with `a`.
   - No em-dash character anywhere.
   - Every constant goes in `Tuning.cs`.
   - All gameplay runs in the fixed step.
   - No `Shader.Find` outside `PrimitiveKit`, no TextMeshPro, no `StandaloneInputModule`.
   - Hide UI by disabling its Canvas.
   - Level teardown uses `DestroyImmediate`.
5. **Tests**:
   - Tests must be able to fail. Assert the premise of a scenario (see probe step 05).
   - Never wait on rendered frames. Count `WaitForFixedUpdate`, or bound the wait by game time.
   - A test that sets `Time.timeScale` restores it in a `finally` or in the TearDown.

## 2. Constants (already added to `Tuning.cs` by the integrator)

| Name | Value | Source |
|---|---|---|
| `DisplacementTolerance` | 0.75 m | PRD 4.4 |
| `DisplacementToleranceYaw` | 45 deg | PRD 4.4 starts at 30; raised because the chair turns toward its motion at 360 deg/s, so any sideways nudge is 90 deg (contract review item 7) |
| `SuspicionPerDiscovery` | 0.34 | PRD 4.4 |
| `SuspicionDecayPerSecond` | 0.02 | PRD 4.4 |
| `SuspicionLose` | 1.0 | PRD 4.4 |
| `HopNoiseRadius` | 2.0 m | new; 3 m made level 1 a one-solution puzzle (contract review item 6) |
| `CreakFillTime` | 20 s | PRD 4.6 |
| `CreakDrainTime` | 10 s | PRD 4.6 |
| `CreakWarning` | 3 s | PRD 4.6 |
| `CreakRadius` | 7 m | PRD 4.6 |
| `CreakStartDelay` | 5 s | PRD 4.6 |
| `AlertLookDuration` | 2 s | PRD 4.6 |
| `InvestigateReach` | 0.8 m (planar, inhabitant center to furniture center) | new |
| `CarrySpeed` | 1.0 m/s | new |
| `PickUpDuration`, `PutDownDuration` | 0.5 s each | new |
| `CarryForward`, `CarryHeight` | 0.45 m, 0.30 m (furniture base, relative to the carrier) | new |
| `NavAgentRadius`, `NavAgentHeight` | 0.25 m, 1.75 m | new |
| `AuditMaxWait` | 8 s | PRD 11 M2 gate |

## 3. Rules, exactly

### 3.1 Displacement memory and suspicion (PRD 4.4)

Reworked after the contract review. The first census design let decoys be "discovered" and gave
free relocations.

- **One slot per piece of furniture, per inhabitant.**
  - **Decoy slots** are fixed at the decoy pose from level start. Decoys never move and are
    never discovered.
  - **The player slot P** starts at the spawn pose: the household knows where its chair
    belongs (PRD 4.6 and 12.1 "where it belongs"). This is open question 9 for the product
    owner. The alternative is "unset until first sighting".
- **Observe, once per fixed step,** for every inhabitant in mode `Routine` or `Alerted` that is
  not frozen pinned. It only matters when the inhabitant sees the player furniture (the five
  sample vision test) and the furniture is not carried. Let C be the pose it is seen at.
  1. If C is within tolerance of P (planar distance at most 0.75 m **and** absolute yaw
     difference at most 45 deg), P takes C: the last pose at which they saw it.
  2. Otherwise, C is explained when it is within tolerance of the slot of a **decoy of the same
     kind that this inhabitant does not see this step** (decoys are tested with the static
     `Vision.Test` and their own sample points). P is unchanged. This is "the player chair is
     one among several".
  3. Otherwise it is a **discovery**, with return pose P.
- **A discovery** adds 0.34 to that inhabitant's suspicion. If the suspicion reaches 1, the level
  is lost with reason `Suspicion`. Otherwise the inhabitant investigates (section 3.4). No
  observation happens while `Investigating`, `Carrying` or `Startled`, so a discovery counts once
  per incident.
- **Suspicion** decays by 0.02 per second, clamped at 0, but only while that inhabitant is in
  `Routine` or `Alerted` (so three discoveries in a row lose, as the PRD intends). The HUD shows
  the highest suspicion among the inhabitants.

### 3.2 Hearing (PRD 4.5)

- **Noise events.**
  - While the player furniture moves, it emits one `Hop` event, radius `HopNoiseRadius`, at
    every hop landing (`FurnitureController.HopCount` increments).
  - It emits none while the chair stands on a silent floor: on a rug, or in a room whose `floor`
    is `"soft"`.
  - The creak emits one `Creak` event of radius `CreakRadius` (section 3.3).
- **Who hears.** An inhabitant hears an event when the planar distance from its position to the
  source is at most the radius. Walls do not block sound in M2.
- **Hearing triggers an alert** only in mode `Routine`, or `Alerted` for a `Creak`.
  - **An alerted inhabitant ignores `Hop` events**: only a `Creak` retargets it. Otherwise the
    head would follow a moving chair through small untelegraphed turns, and the PRD's lure
    ("make noise, then move the other way") could never work.
  - Investigating, carrying, startled and frozen pinned inhabitants ignore noise.

### 3.3 Creak gauge (PRD 4.6)

- **Range.** `CreakGauge.Value` runs from 0 to 1.
- **Each fixed step:**
  - It does nothing while carried, or while the level time is below `CreakStartDelay`.
  - While the furniture is not moving (the `MotionRule` predicate), it fills by `dt / 20`.
  - While it is moving, it drains by `dt / 10`, clamped at 0.
  - When it reaches 1, `Step` returns true (the creak) and the gauge resets to 0.
- **Warning** is true while the furniture is still and filling, and
  `Value >= 1 - CreakWarning / CreakFillTime` (that is, the last 3 s).
- **During the warning:**
  - the furniture **visual** trembles: at most 0.012 m and 1.5 deg, with no effect on the
    transform, so it never counts as motion;
  - the tension sound plays;
  - the HUD gauge flashes.
- **A creak** emits a `Creak` noise event at the furniture position (section 3.2).

### 3.4 Inhabitant modes (PRD 5.2)

`InhabitantRoutine.Mode`: `Routine`, `Alerted`, `Investigating`, `Carrying`, `Startled`.
`Pinned` is a modifier, see below. One invariant above all: **every body or head turn over
30 deg is preceded, immediately, by a full 0.6 s telegraph**, in every mode except `Startled`.
The probe analyzer checks body yaw and head yaw separately, and requires the telegraph steps
right before each turn, so:

- **A turn that moves body and head together** (the Alert look) runs both at the same time,
  right after one telegraph. Never one after the other.
- **On resume after an interruption:** an interrupted telegraph restarts in full, and an
  interrupted turn with more than 30 deg left gets a fresh telegraph.
- **An `Alert` during a telegraph or a turn** only updates the look target, without restarting
  the telegraph. Otherwise hops every 0.224 s would keep it running forever.
- **Arrival and departure turns:** an arrival turn belongs to the dwell, a departure turn to the
  walk.

- **Alerted** (`Alert(source)`, accepted only in `Routine` or `Alerted`):
  1. Save the current pose and the remaining plan. Telegraph if the look turn is over 30 deg.
  2. Turn toward the source: the head up to its 80 deg limit, and the body for the rest, both
     **at the same time**, after the one telegraph.
  3. Hold the look for `AlertLookDuration`.
  4. Telegraph if the return turn is over 30 deg, turn back to the saved pose, and resume the
     saved plan exactly where it stopped. The position is unchanged, so the plan is still valid.
  - A new `Alert` while alerted retargets: a turn with its own telegraph if over 30 deg, and
    the hold timer restarts.
- **Investigating** (`Investigate(target)`):
  1. Drop the current plan. If an Alert was in progress, keep the plan the Alert saved: that is
     the plan to resume later. The head returns to 0 inside the first telegraphed beat. Path to the target (the planner gives polyline corners). Walk each
     segment at `WalkSpeed`, with a telegraphed turn before each segment whose turn is over
     30 deg.
  2. Stop when within `InvestigateReach` of the target, or at the end of the path, or at once
     when `TryPlan` returns false. `ReachedTarget` becomes true and the routine idles, facing
     the target.
  3. GameState then either calls `BeginCarry(returnPose)` (the furniture center is within
     `InvestigateReach + 0.1` m) or `CancelInvestigation()` (the furniture moved away).
- **Carrying** (`BeginCarry(returnPose)`):
  1. Pick up for `PickUpDuration` (`IsCarrying` becomes true at the start of the pick up).
  2. Path to the **carry goal** `returnPose.Position - Forward(approachYaw) * CarryForward`,
     where `approachYaw` is the yaw of the last path segment, so that the held furniture
     arrives on its return position. Walk at `CarrySpeed`, every turn over 30 deg telegraphed.
     Then turn to face the return position (telegraphed if over 30 deg).
  3. Put down for `PutDownDuration`. `JustPutDown` is true on exactly the step the put down ends,
     and `IsCarrying` becomes false on that step.
  4. Resume the routine (see "Resume" below).
- **Resume after an investigation** (carry finished or cancelled):
  - If the investigation interrupted a dwell at station i, path back to station i, then the
    arrival turn and a full dwell there.
  - If it interrupted the walk to station j, path to station j, then the arrival turn and the
    dwell.
- **Station walks** use the planner. When `TryPlan` returns false, a station walk falls back to a
  straight line and logs one error.
- **Startled** (`Startle(target)`): as in M1. Also used for the suspicion loss.
- **Pinned** (`Pin(pos, body, head, reactive = false)`):
  - **`Pin` cancels any mode**: alert, investigation or carry.
  - A frozen pin (`reactive = false`) is M1 behavior: no motion, no reaction. A frozen pinned
    inhabitant never observes (memory) and never hears.
  - A reactive pin holds the pose in place of the station cycle, but accepts `Alert` and
    `Investigate`. Once those finish, it walks back to the pinned pose (path, telegraphed turns)
    and holds it again.
  - Probe steps use reactive pins to test hearing and memory from a known pose.
- **Path planner.** `IPathPlanner.TryPlan(from, to, corners)` fills `corners` with the polyline
  after `from`, ending at `to`, and returns false when there is no path.
  - The default is `StraightPlanner`, a single corner equal to `to`, which keeps M1 behavior.
  - Station walks also use the planner from M2 on.

### 3.5 Exit, win and lose (PRD 6.2)

- **Win**: the furniture center is inside the exit zone, the furniture is **not seen** this step
  (by any inhabitant), and it is not carried.
- **Lose**:
  - `SeenMoving`, the caught rule of M1. A carried furniture is never "moving".
  - `Suspicion`: an inhabitant's suspicion reaches 1. The startled pose comes from the inhabitant
    who reached 1. The fail panel uses the suspicion strings.
- **After a win:** Enter loads the next level of `levels.json` (when there is one), and R
  replays.

### 3.6 Fixed step order (GameState.FixedUpdate)

1. `furniture.Step(dt, allowInput: Playing && !Carried)`. A carried furniture instead calls
   `FollowCarrier(anchorPosition, carrierYaw)`.
2. Every `inhabitant.Step(dt)`.
3. Vision, for every inhabitant: the player furniture first, then every decoy. Set `Seen`.
4. The caught rule (`Rule.Step(seenPlayer, furniture.IsMoving, dt)`), then exit and win (3.5).
   Win is checked before the caught rule, as in M1.
5. If still playing, memory, for every inhabitant in `Routine` or `Alerted`: `Observe`, then
   discoveries, suspicion, and possibly a lose.
6. Investigations:
   - `ReachedTarget`: `BeginCarry` when within reach, otherwise `CancelInvestigation`.
   - The carry start attaches the furniture.
   - `JustPutDown` teleports the furniture to the return pose, sets the carrier's slot to that
     pose, and detaches it.
7. Noise: hop events (on a hard floor), then the creak gauge step, which may emit a creak. Every
   inhabitant who hears an event gets `Alert(source)`.
8. Suspicion decay.
9. HUD: eye, seen and moving pulse, creak gauge with its warning, highest suspicion. Then
   `FixedStepped` fires.

### 3.7 Rule switches

`Core/GameRules`:

```
bool DisplacementMemory = true;
bool Hearing = true;
bool Creak = true;
bool ExitOnlyUnseen = true;
static GameRules M1 => all false;
static GameRules M2 => all true;
```

- `GameRules.M1` and `GameRules.M2` return a **new instance** on every call, so a test never
  mutates a shared object.
- `GameState.Rules` defaults to M2, and GameState reads it on every step.
- **The whole M1 probe (`ProbeTests.cs`, steps 01 to 12) runs with `GameRules.M1`.** It measures
  the M1 core loop. The integrator sets it in that file's SetUp.
- The M2 probe (`ProbeTestsM2.cs`) runs with `GameRules.M2`.

## 4. Data: LevelDef v2

Fields are added and nothing is removed. Every M1 level stays valid.

```
rooms:  [ { id, x, z, sizeX, sizeZ, wallHeight, wallThickness, floor: "hard"|"soft", floorColor, wallColor } ]
        Rectangles of the interior. x, z is the center. Walls stand outside the interior.
        M1 "room" (single, centered at 0,0) is still accepted: LevelDef.AllRooms() returns
        [room] when rooms is empty.
doors:  [ { x, z, width, top } ]   (v2 form: a point on a wall line, width along the wall)
        The M1 form { wall, center, width, bottom, top } is still accepted for single-room levels.
rugs:   [ { x, z, sizeX, sizeZ, yaw, color } ]   silent floor areas
decoys: [ { kind: "chair", x, z, yaw, sizeX, sizeY, sizeZ, color } ]   static furniture of the same
        kind as the player (size defaults to the player size)
designerRoute: [ { x, z, at } ]   optional. Replay rule: at game time `at`, start driving straight
        toward (x, z) at full input; release the input when within 0.1 m; then wait for the next
        `at`. The first waypoint's `at` may be 0.
```

- **Adjacent rooms** are separated by exactly one wall thickness: room B min x equals room A
  max x plus `wallThickness`. The builder makes one wall between them.
- **A door** is a point within half a wall thickness of a wall line. It cuts a gap of `width`
  and height `top` (default 2.1) in that wall. A door whose `wall` is null is the v2 form.
  `floor` defaults to "hard".
- **All rooms of a level share one wall thickness.**
- `levels.json` is not a level: the audit and the tests read only the files named in it.
- **`LevelDef` helpers**, pure and in Core:
  - `AllRooms()`
  - `RoomAt(point)`, which returns null outside every room
  - `IsSilentFloor(point)`, true on a rug or in a soft room
  - `Census()`, which maps each kind to a count (player plus decoys)

**`LevelValidator` additions:**
- rooms do not overlap;
- every adjacent pair is separated by exactly one wall thickness;
- every door lies on a wall;
- the room graph is connected through doors;
- spawn, exit, stations, props, decoys and rugs lie inside a room;
- no station is inside a decoy;
- `designerRoute` waypoints lie inside a room, with times that do not decrease.

**`levels.json`** in `Resources/Levels`: `{ "levels": ["level1", "level2", "level3"] }`, the play
order.

## 5. Public API (signatures are binding)

The integrator lands **compiling stubs** of every member below, each in its owner's file, before
the builders start. A builder replaces the stub bodies in its own files and keeps the signatures.

```csharp
namespace Meuble.Core
{
    // GameRules.cs (core-rules)
    public sealed class GameRules { public bool DisplacementMemory, Hearing, Creak, ExitOnlyUnseen;
        public static GameRules M1 { get; } /* new instance each call */ public static GameRules M2 { get; } }

    // FurnitureMemory.cs (core-rules)
    public struct FurniturePose { public Vector3 Position; public float Yaw; public FurniturePose(Vector3 position, float yaw); }
    public enum Observation { NotSeen, Confirmed, ExplainedByDecoy, Discovery }
    public sealed class FurnitureMemory
    {
        public FurnitureMemory(FurniturePose playerSpawn, IReadOnlyList<FurniturePose> decoys, IReadOnlyList<string> decoyKinds, string playerKind);
        public FurniturePose PlayerSlot { get; }
        public static bool WithinTolerance(FurniturePose a, FurniturePose b);
        /// seenDecoys[i] tells whether decoy i is seen this step by the same inhabitant.
        public Observation Observe(bool playerSeen, FurniturePose player, IReadOnlyList<bool> seenDecoys);
        public void SetPlayerSlot(FurniturePose pose);   // after a carry back
    }

    // SuspicionMeter.cs (core-rules)
    public sealed class SuspicionMeter { public float Value { get; } public bool Lost { get; }
        public void AddDiscovery(); public void Step(float dt); public void Reset(); }

    // CreakGauge.cs (core-rules)
    public sealed class CreakGauge { public float Value { get; } public bool Warning { get; }
        public float SecondsToCreak { get; }   // while filling; float.PositiveInfinity otherwise
        public bool Step(float dt, bool moving, bool carried, float levelTime); public void Reset(); }

    // Hearing.cs (core-rules)
    public enum NoiseKind { Hop, Creak }
    public struct NoiseEvent { public Vector3 Position; public float Radius; public NoiseKind Kind;
        public NoiseEvent(Vector3 position, float radius, NoiseKind kind); }
    public static class Hearing { public static bool Hears(Vector3 listener, NoiseEvent e); }

    // PathPlanning.cs (integrator, already landed)
    public interface IPathPlanner { bool TryPlan(Vector3 from, Vector3 to, List<Vector3> corners); }
    public sealed class StraightPlanner : IPathPlanner { public static readonly StraightPlanner Instance; }

    // InhabitantRoutine.cs (core-routine): every M1 member is kept. Additions:
    public enum InhabitantMode { Routine, Alerted, Investigating, Carrying, Startled }
    //   ctor InhabitantRoutine(List<StationDef> stations, int startStation, IPathPlanner planner)  (M1 ctor kept = StraightPlanner)
    //   InhabitantMode Mode { get; }
    //   bool IsFrozen { get; }                    // frozen pin
    //   void Pin(Vector3 position, float bodyYaw, float headYaw, bool reactive)   (M1 overload = frozen)
    //   void Alert(Vector3 source, NoiseKind kind)
    //   void Investigate(Vector3 target)
    //   bool ReachedTarget { get; }
    //   void BeginCarry(FurniturePose returnPose)
    //   void CancelInvestigation()
    //   bool IsCarrying { get; }
    //   bool JustPickedUp { get; }                // true for exactly the step the pick up starts
    //   bool JustPutDown { get; }                 // true for exactly the step the put down ends
    //   FurniturePose CarryReturnPose { get; }
    //   Vector3 CarryAnchor { get; }              // Position + Forward(BodyYaw) * CarryForward + up * CarryHeight
    //   Vector3 AlertSource { get; }
    //   RoutineActivity gains: Looking, PickingUp, Carrying, PuttingDown

    // LevelDef.cs and LevelValidator.cs (runtime-world): data of section 4, plus
    //   List<RoomDef> AllRooms(); RoomDef RoomAt(Vector3 p); bool IsSilentFloor(Vector3 p);
    //   RoomDef gains Id, X, Z, Floor; OpeningDef gains X, Z; new RugDef, DecoyDef, RouteStepDef;
    //   LevelDef gains Rooms, Rugs, Decoys, DesignerRoute
    //   static class LevelManifest { static List<string> Parse(string json); }
}

namespace Meuble   // Runtime
{
    // Decoy.cs (runtime-world)
    public sealed class Decoy : MonoBehaviour { public int Id; public string Kind; public FurniturePose Pose;
        public Vector3 Size; public void GetSamplePoints(Vector3[] output); }
    // NavPlanner.cs (runtime-world)
    public sealed class NavPlanner : IPathPlanner { /* NavMesh.CalculatePath, complete paths only */ }
    // LevelBuilder.cs (runtime-world): LevelInstance gains
    //   List<Decoy> Decoys; IPathPlanner Planner; bool IsSilentAt(Vector3 p);
    //   build order: geometry, Physics.SyncTransforms, NavMesh, then inhabitants (Init with the planner)
    // Inhabitant.cs (runtime-game): void Init(InhabitantDef def, IPathPlanner planner)  (M1 Init kept)
    // FurnitureController.cs (runtime-game):
    //   int Id => 0; string Kind; bool Carried { get; }
    //   void FollowCarrier(Vector3 anchor, float yaw);   // pose + interpolation poses; IsMoving false; controller disabled
    //   void Release(FurniturePose pose);               // floor pose + interpolation poses; controller enabled
    // GameState.cs (runtime-game):
    public enum LoseReason { None, SeenMoving, Suspicion }
    //   GameRules Rules; LoseReason LoseReason; float MaxSuspicion; CreakGauge Creak;
    //   event Action<NoiseEvent> Noise; void LoadLevel(string id); bool HasNextLevel; void NextLevel();
    //   SuspicionMeter SuspicionOf(Inhabitant i); FurnitureMemory MemoryOf(Inhabitant i);
}
```

## 6. World (Runtime) requirements

- **Multi-room `LevelBuilder`:**
  - floors per room, with the floor color, and a "soft" room uses a carpet look;
  - walls generated from the room rectangles, with shared walls built once;
  - **shared (interior) walls get two faces.** Each frame (a small `WallFader` component, owned
    by runtime-world), the face whose plane separates the camera from the player furniture is
    hidden: renderer only, the collider is kept. Outer walls keep their single inward face;
  - an invisible blocker (layer Default, collides with the player only) stands 0.6 m outside the
    exit door, so a chair that crosses the doormat while seen cannot drive out into the garden;
  - door gaps with lintels and door frame decor;
  - the M1 window decor still works on single-room levels;
  - rugs: flat boxes 0.01 m high, no collider, silent;
  - decoys: the chair mesh in their own color (never red), with a box collider on a new
    **`Furniture`** layer (10). That layer collides with the player and is a NavMesh obstacle,
    but it is **not** an occluder.
- **Runtime NavMesh**:
  - built at level build from `NavMesh.GetSettingsByID(0)`, overriding radius 0.25, height 1.75,
    **climb 0.1** (otherwise the 0.75 m table top becomes walkable) and slope 30. Sources come
    from `NavMeshBuilder.CollectSources` on the level root: physics colliders on the Occluder,
    Floor and Furniture layers. Bounds: **the union of the rooms**, so no path leaves the house
    through the exit door. Then `BuildNavMeshData` and `AddNavMeshData`;
  - `NavMesh.RemoveAllNavMeshData()` runs at the start of Build: runtime data survives scene
    reloads between PlayMode tests. The data is also removed in `Teardown`;
  - `NavPlanner` wraps `NavMesh.CalculatePath` with a `NavMeshQueryFilter` for agent type 0:
    - accept only `PathComplete`;
    - drop `corners[0]` (the start point) and set y to 0;
    - make the last corner exactly `to`;
    - snap the endpoints with `NavMesh.SamplePosition` at 1 m.
  - It must also work in edit mode, because the audit uses it. **Test this first.**
- **Levels 2 and 3** (two rooms, one doorway each):
  - **Level 2 "Le couloir"** teaches hearing and rugs: a hard floor with rugs that make a silent
    path near the inhabitant.
  - **Level 3 "La salle a manger"** teaches decoys and memory: several decoy chairs around the
    dining table.
  - Each one passes the validator and the audit.
  - First-run target: 60 to 120 s. Designer route: under 60 s.
  - The levels must also work for decoys: a table never hides a chair top (PRD 6.3 note), so
    level 3 places decoys where a wall or the doorway hides them from some station.
- **Designer routes**, for levels 1, 2 and 3, can only be tuned on the integrated game. This is
  the **integration phase task** of runtime-world, once runtime-game has landed. Each route
  replays to a win with **zero discoveries, zero alerts and no creak**, under the M2 rules. The
  contract review found by hand that level 1 is winnable that way: wait at spawn until about
  16.5 s, then make one sprint north of the sofa.
- **The audit** reads the level files named in `levels.json` (never `*.json`), extended:
  - every station walk has a complete NavMesh path (instead of the capsule sweep);
  - multi-room grid;
  - for every cell, the longest contiguous stretch of the loop during which it is seen (cyclic);
  - the safe path requires each cell to be unseen at least 25 % of the loop **and** to have a
    longest seen stretch of at most `AuditMaxWait` (8 s);
  - the map printout is kept.

## 7. Game (Runtime) requirements

- **`GameState`** follows the order of 3.6 and the rule switches of 3.7. It keeps a memory and a
  suspicion meter per inhabitant, the creak gauge, and the level flow over `levels.json`.
- **HUD**:
  - a creak gauge bar next to the eye, flashing during the warning;
  - a suspicion bar under the eye, the highest across inhabitants;
  - a fail panel with the suspicion strings when the reason is `Suspicion`;
  - the win panel also shows `win.next` when there is a next level.
- **Inhabitant visuals**:
  - `Alerted`: a floating "?" above the head, as a procedural sprite in the world;
  - `Investigating` and `Carrying`: a frown (two eyebrow boxes tilted) and a "!" marker;
  - `Carrying`: arms forward, with the furniture following `CarryAnchor`.
- **Sfx** (synthesized, as in M1):
  - a creak (wood);
  - a rising tension tone during the warning;
  - a "hein ?" discovery sting (a pitched variant of hm is fine);
  - a put-down thump.

## 8. Strings (French, added to `Strings.cs` and to PRD section 9)

| Key | Text |
|---|---|
| fail.suspicion.title | LOUCHE ! |
| fail.suspicion.body | Cette chaise se promène un peu trop. |
| win.next | Appuie sur Entrée pour le niveau suivant |
| level2.name | Le couloir |
| level2.hint | Sur un tapis, personne ne t'entend. |
| level3.name | La salle à manger |
| level3.hint | Une chaise parmi d'autres ne surprend personne. |

## 9. File ownership

| Agent | Owns (creates or edits) |
|---|---|
| **core-rules** | `Core/GameRules.cs`, `Core/FurnitureMemory.cs`, `Core/SuspicionMeter.cs`, `Core/CreakGauge.cs`, `Core/Hearing.cs`, `Tests/EditMode/RulesM2Tests.cs` |
| **core-routine** | `Core/InhabitantRoutine.cs`, `Tests/EditMode/RoutineM2Tests.cs` |
| **runtime-world** | `Core/LevelDef.cs`, `Core/LevelValidator.cs`, `Tests/EditMode/LevelDataM2Tests.cs`, `Runtime/LevelBuilder.cs`, `Runtime/FurnitureKit.cs`, `Runtime/NavPlanner.cs`, `Runtime/Decoy.cs`, `Runtime/WallFader.cs`, `Runtime/Layers.cs`, `Editor/LevelAudit.cs`, `Editor/ProjectSetup.cs`, `Resources/Levels/*.json` |
| **runtime-game** | `Runtime/GameState.cs`, `Runtime/FurnitureController.cs`, `Runtime/Inhabitant.cs`, `Runtime/Vision.cs`, `Runtime/Hud.cs`, `Runtime/ProceduralArt.cs`, `Runtime/Sfx.cs`, `Runtime/Main.cs`, `Runtime/Probe.cs`, `Runtime/InputReader.cs`, `Runtime/LevelLoader.cs`, `Tests/PlayMode/ProbeTestsM2.cs` |
| **integrator** | `Core/Tuning.cs`, `Core/Strings.cs`, `Core/PathPlanning.cs`, `docs/*`, `verify.sh`, `mutation.sh`, `tools/*`, `Tests/PlayMode/ProbeTests.cs`, `Tests/EditMode/CoreTests.cs`, `README.md` |

## 10. Gate (all must be green in `./verify.sh`)

**EditMode:**
- **Creak gauge:** fill (20 s still creaks), drain (10 s from full), reset to 0 after a creak,
  start delay (nothing before 5 s), paused while carried, and the warning only during the last
  3 s.
- **Memory** (one slot per piece, section 3.1):
  - the player slot starts at the spawn pose;
  - within tolerance confirms and updates the slot;
  - over 0.75 m, or over 45 deg, is a discovery;
  - a sighting never creates a slot, and a decoy slot never moves;
  - a decoy slot explains a chair when the decoy is unseen and of the same kind, and does not
    when the decoy is seen;
  - the return pose of a discovery is the player slot.
- **Suspicion:** 3 discoveries lose (1.02); decay at 0.02/s; clamped at 0.
- **Hearing:** the radius edge (inside and outside), and `IsSilentFloor` on rugs and soft rooms.
- **Routine:**
  - `Alert` telegraphs before a look turn over 30 deg, holds 2 s, returns to the exact saved pose
    and resumes the plan;
  - a retarget during an alert;
  - investigate, then carry, then put down, then resume, in that order;
  - every turn over 30 deg in every mode is telegraphed (the M1 analyzer, extended);
  - a reactive pin returns to its pose;
  - the M1 behavior with `StraightPlanner` is unchanged.
- **Level data:** v2 round trip; levels 2 and 3 pass the validator; each negative validator rule
  has its own test.

**PlayMode (`ProbeTestsM2.cs`, on the real Boot scene):**

| Step | Assertion |
|---|---|
| 13 memory | inhabitant (reactive pin) more than 2 m away (or the chair on a rug) sees the chair at spawn: Confirmed, suspicion 0; pinned away; chair driven 1.2 m; pinned back facing it: suspicion 0.34 within one step, mode Investigating |
| 14 carry back | continuing 13: the inhabitant reaches the chair, carries it, and puts it down within 0.1 m and 5 deg of the remembered pose; scripted input during the carry has no effect; afterwards mode Routine (or reactive pin) and state Playing |
| 15 noise lure | inhabitant (reactive pin) 1.5 m away facing away; chair hops on a hard floor and the input is released on the first Hop event: telegraph at least 0.6 s, then eye forward within 15 deg of the noise source; the same with the chair on a rug (level 2, coordinates read from `Game.Def`): no reaction, and the premise that a hop happened on the rug is asserted |
| 16 creak alerts | chair still from level start; inhabitant (reactive pin) 5 m away facing away; creak at 25 s (5 s delay + 20 s); the inhabitant becomes Alerted and looks at the chair |
| 17 creak out of range | same, inhabitant 9 m away (level 2 or 3): the creak is asserted to have fired (Noise event seen), and no reaction |
| 18 never creaks | chair driven continuously for 60 s (a square loop), inhabitants frozen far away: no creak, warning never on |
| 19 exit only unseen | chair entering the exit while seen does not win; once unseen it wins |
| 20 levels 1, 2 and 3 | each boots with zero errors; its designerRoute replay (M2 rules, timeScale 8) wins with 0 discoveries, 0 alerts, no creak; level 2's route asserts it crossed a rug within 2 m of an inhabitant, level 3's route asserts at least one ExplainedByDecoy |
| 21 suspicion lose | three discoveries in a row (each one forced by teleport plus re-pin, `Pin` cancels the previous investigation) lose with reason Suspicion and the suspicion panel |

**Audit:** levels 1 to 3 pass, with every walk path complete and a safe path with waits of at
most 8 s.

**Built player:**
- the probe also loads levels 2 and 3 and screenshots their start (shots 04 and 05);
- the budgets of 7.4 hold on every level;
- 0 exceptions.

---

## 11. Amendment M2.1 (after the critique of the M2 results)

The result critique found that a playtest would measure the wrong game. Binding changes:

1. **A discovery has a grace period.**
   - `FurnitureMemory.Observe(bool playerSeen, FurniturePose player, float dt)` accumulates
     the time the chair is seen out of place, and reports `Discovery` only once that time
     reaches `Tuning.DiscoveryGrace` (0.2 s, the same as `CaughtGrace`).
   - The timer resets on a step where the chair is not seen, or is seen in place.
   - While the timer runs, `Observe` returns `Suspect`, a new enum value. The HUD uses it.
2. **The tolerance is position only** (0.75 m). Yaw is ignored. The chair turns toward its
   motion, so a yaw rule punished the act of moving instead of the displacement.
   `DisplacementToleranceYaw` is removed from the rule; the constant stays, documented as unused.
3. **Any decoy of the player's kind explains the chair** when the chair is within 0.75 m of that
   decoy's slot, **whether or not the decoy is seen**. This matches the level 3 hint. Decoy vision
   is no longer computed, which saves 5 raycasts per decoy per inhabitant per step.
4. **Remembered pose for every inhabitant.**
   - After a put down, every inhabitant's player slot becomes the put down pose.
   - When an investigation is cancelled because no path exists, the inhabitant gives up: its
     slot becomes the chair's current pose.
5. **Input after a release.** After `Release`, player input is ignored until the move input has
   been neutral for at least one fixed step. A key held through a carry never moves the chair.
6. **Readability:**
   - **The eye** has three states:
     - closed: unseen;
     - open, calm: seen and harmless, that is confirmed or explained;
     - open, alarm: seen and moving, or `Suspect`.
   - **A ghost** (a translucent outline of the chair) marks the remembered pose of the inhabitant
     who last saw the chair. A 0.75 m ring on the floor around it shows the tolerance. Both show
     only while the chair is out of place.
   - **The creak and suspicion bars** are larger and labelled (`hud.creak`, `hud.suspicion`),
     with distinct icons. The suspicion icon is no longer the Alerted "?".
7. **The audit knows M2** (it replaces the M1-style 8 s check):
   - It runs a time-expanded search: 0.5 m cells, 0.1 s samples, a horizon of 180 s, the
     deterministic routine.
   - It looks for a schedule from spawn to exit that is never seen while moving and never seen
     out of place for the discovery grace, with memory and the decoy explanation. It never moves
     on a hard floor within `HopNoiseRadius` (+0.25 m) of an inhabitant, keeps the creak gauge
     below 1, and **never waits more than 8 s in a row in one place, including at spawn**.
   - The audit fails without such a schedule. It prints the schedule's total time, its longest
     wait and its slack (the largest global time shift, early or late, that keeps it valid).
   - It can emit the schedule as a `designerRoute`.
8. **Levels** are retimed or retouched until the audit passes.
   - Level 1 may change only its `startStation` and props that no walk crosses. Any such change
     goes back into the PRD with its reason.
   - Designer routes are regenerated from the audit schedule, and must still win when every `at`
     is shifted by -0.2 s and by +0.2 s (probe step 20 replays all three offsets).
9. **Tests to add:**
   - suspicion decays only in Routine or Alerted (a GameState-level test);
   - step 19 in the real case: reach the exit while seen, then a discovery and a carry back;
   - Enter loads the next level;
   - a key held through a carry;
   - an investigation with no path does not lose;
   - the discovery grace (0.18 s out of place is not a discovery, 0.20 s is);
   - M2 mutations in `mutation.sh`: remove the discovery grace, and decay in every mode.
10. **Deferred:**
    - to M3 (look agent): inhabitants and cones visible through walls (an x-ray pass), and the
      end screen after the last level;
    - to M5: an inhabitant routing around a still chair (with doors and several inhabitants).
