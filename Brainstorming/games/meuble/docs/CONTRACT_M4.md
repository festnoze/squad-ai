# Contract M4 - "Le mobilier" (v2)

Build contract for milestone M4 of [PRD.md](PRD.md) (section 11, M4): depth through different
bodies. v2 folds in the critique of draft v1, which found 5 blockers: the armchair and wardrobe
rules had no effect on play, hiding contradicted PRD 4.6, routes could not be replayed, and
ownership clashed with M3. Same method as CONTRACT_M2 and M3:
- the PRD wins;
- the integrator decides ambiguity;
- every interpretation below goes back into the PRD (v1.5) as an M4 note or an open question,
  with its default;
- everything of M1 to M3 keeps working.

---

## 1. Ground rules

As in CONTRACT_M3 section 1:
- own your files;
- additive APIs;
- `tools/unity.sh` for every Unity call;
- tests that can fail, with premise guards;
- no em-dash;
- constants in Tuning (integrator);
- French strings in Strings (integrator);
- scratch files in `scratchpad/<agent>/`.

## 2. Bodies

`player.kind` selects the body (`BodyDef.For(kind)`, Core).

| Kind | Size x, y, z (m) | Radius | Max speed | Acceleration | Turn rate | Model | Lesson |
|---|---|---|---|---|---|---|---|
| chair | 0.45, 0.90, 0.45 | 0.28 | 1.5 | 10 | 360 | kenney.chair | reference; **must equal the M1 constants exactly** (a test checks it) |
| stool | 0.35, 0.55, 0.35 | 0.22 | 2.4 (two stage) | 14 up to 1.2 m/s, then 1.2 | 540 | kenney.stool | speed, and stopping without tipping |
| armchair | 0.85, 1.05, 0.85 | 0.45 | 0.9 | 6 | 200 | kenney.armchair | slow; the household sits on it |
| floor_lamp | 0.35, 1.80, 0.35 | 0.22 | 0.6 | 4 | 180 | kenney.floorlamp | darkness shrinks sight |
| office_chair | 0.55, 1.00, 0.55 | 0.30 | 2.8 | 8 | 360 | procedural (over budget) | inertia, planned stops |

- **Other per-body values:** `CarryForward` per body (0.45 for chair and stool, 0.65 for armchair
  and office chair, 0.40 for the lamp). The decoy size comes from the decoy kind.
- **Careful mode (every body).** While Left Shift (gamepad left trigger) is held, the max speed is
  halved. String `hud.careful` "Maj : au ralenti". It is not silent: rugs keep their M2 meaning.
- **The moving predicate becomes `MotionRule.IsMoving(speed, yawRate, actionActive)`**, written
  back to PRD 3.3. Topples, rights, toggles and sitting on the chair use `actionActive` as
  specified below. Nothing else changes.

### 2.1 Stool

- **Acceleration** is fast up to `StoolTipSpeed` (1.3 m/s), then slow (1.2 m/s²) up to 2.4 m/s.
- **The tell.** Above 1.3 m/s the visual leans 8 deg back and rattles (a "rattle" loop), so
  the player sees they are too fast.
- **Tipping.**
  - When the input is released above 1.3 m/s, or a wall stops a head-on hit (the velocity
    against the hit normal is above 1.3 m/s), the stool **tips over**.
  - It falls for 0.3 s, which counts as moving.
  - It emits a `Topple` noise event of radius 3.5 m, which behaves like a hop: it alerts only in
    Routine.
  - It then **lies on its side until the player presses a move key**, and rights itself in
    0.4 s, which also counts as moving.
- **Lying down is out of place.** An inhabitant who sees a tipped stool observes it as out of
  place, a Suspect then a Discovery after the grace, whatever its position (open question 15).
- **Careful mode** caps the speed at 1.2 m/s, safely below the threshold.

### 2.2 Armchair (the sat-on body)

- **No sight blocking by the body.** Armchair **props** (`kind: "armchair"`, occluder) are cover
  for small bodies: a stool top sits at 0.52 m.
- **The armchair body's lesson is sitting (section 3):** the household's own armchair, and slow
  round trips home before each sitting.

### 2.3 Floor lamp

- **The light.** The lamp body carries an unshadowed point light. The action key **E** (gamepad
  X) toggles it: a 0.2 s action, moving, plus a `Click` noise of radius 2.5 m.
- **While off:** every inhabitant's range **for the lamp's own sample points** is
  `LampOffLight * ViewRange` (0.4 x 10 = 4 m), and the floor cone shows that shorter range,
  dimmed. Rooms are visual only: a dimmer light in the lamp's room.
- **Switched back on.**
  - An inhabitant in Routine who sees the lamp switched off (within the normal range) becomes
    **Investigating**: it walks to the lamp, switches it on (a 0.5 s beat) and resumes.
  - This is the lamp's carry-back, and it is a discovery only if the lamp is also out of place.
  - Open question 13.
- **String:** `hud.lamp` "E : éteindre / allumer".

### 2.4 Office chair

- **Glide.**
  - When the input is released, the chair decelerates to 0 in exactly `OfficeChairStopTime`
    (0.4 s) at a constant deceleration.
  - Opposite input brakes no faster.
  - The chair is moving during the glide, and it turns with its velocity.
- **The predicted stop point** (a small ring on the floor) is drawn while it moves.
- **No hops.** Rolling emits a `Roll` noise every 0.3 s with radius 1.2 m (quieter than hops,
  silent on rugs).
- **Level 7** has decoy office chairs (kind `office_chair`).

### 2.5 Wardrobe: deferred to M5

- The body is dropped.
- The hiding prop moves to M5, with the rules of draft v1 section 8 item 2:
  - the creak gauge fills inside;
  - a creak inside opens the doors;
  - a carrier opens the wardrobe;
  - the interior is at least the body size plus 0.05 m.
- Open question 12.

## 3. Sitting (PRD 5.2)

**Data.** A station may name a seat: `"sit": "<prop name>"`, or `"sit": "player"` with `"seat":
{x, z, yaw}`, the authored home of the player's seat.

**Sitting on a prop.** The inhabitant walks to the seat front, turns its back (telegraphed if
over 30 deg) and sits.
- The `Sitting` activity lowers the eye to `SitEyeHeight` (1.15 m).
- The rig plays `_Sitting` if the model has it, otherwise Idle lowered.
- The dwell and glances play as usual.
- **Standing up** is telegraphed (0.6 s) and the eye rises over 0.5 s (interpolated).

**`sit: player`.** The check happens **at the moment of sitting**, after the back turn.
- **The player body is a seat** (chair, stool, armchair or office chair) **within 0.75 m of the
  seat home:**
  - the inhabitant sits on it;
  - every inhabitant's player slot becomes that pose;
  - **the player is pinned** for the dwell: no input, not moving, the creak gauge paused;
  - on release, input needs a neutral step;
  - HUD line `hud.satOn` "Quelqu'un est assis sur toi.".
- **Otherwise:**
  - the inhabitant sits on nothing, a **pratfall** (a 1 s fall, then standing back up): comedy,
    pillar 4;
  - it counts as **one discovery**, +0.34;
  - then an Alerted look around the seat for 2 s, and the routine resumes.
  - Pulling the chair away during the turn is the classic gag. Open question 14.
- **Telegraph.** The ghost and ring are drawn at the seat home while a `sit: player` inhabitant
  approaches, from the start of that walk.
- **Edge cases:**
  - an occupied seat (two inhabitants, M5) is skipped, never a discovery;
  - an Alerted inhabitant who is seated looks with the head only;
  - Investigate stands up first (telegraphed).

## 4. Levels 4 to 7

One body each, two rooms at most.

| Level | Body | Lesson | Must contain |
|---|---|---|---|
| 4 "Le tabouret" | stool | careful speed, the tell, tipping | low props (sofa, table) as cover for the stool; one `sit` on a prop |
| 5 "Le fauteuil" | armchair | sitting on the player | a `sit: player` station with its seat home near the spawn, so the armchair must be home in time |
| 6 "La lampe" | floor_lamp | darkness shrinks sight | a room the lamp must cross dark; an inhabitant who comes to switch it on |
| 7 "Le bureau" | office_chair | planned stops | decoy office chairs; long open floor |

Strings (the integrator adds them):

| Key | Text |
|---|---|
| level4.name | Le tabouret |
| level4.hint | Trop vite, et le tabouret tombe. Maj pour aller doucement. |
| level5.name | Le fauteuil |
| level5.hint | Sois à ta place quand quelqu'un veut s'asseoir. |
| level6.name | La lampe |
| level6.hint | Dans le noir, on voit moins loin. E pour éteindre. |
| level7.name | Le bureau |
| level7.hint | Une chaise à roulettes ne s'arrête jamais tout de suite. |
| hud.careful | Maj : au ralenti |
| hud.lamp | E : éteindre / allumer |
| hud.satOn | Quelqu'un est assis sur toi. |

`levels.json` gains levels 4 to 7. Each level is audited, and its designer route wins at -0.2,
0 and +0.2 s.

## 5. Designer routes and the audit

**Route steps gain** `careful` (bool), `action` (`"toggle"` or `"rightup"`) and `waitFor`
(optional).
- The replay releases at distance `max(0.1, v * 0.2 + 0.1)` for gliding bodies.
- `careful` holds Shift.
- `action` presses E or a move key at `at`.

**The audit becomes body aware, at the minimum the critique asked for:**
- move samples and ring radius per body;
- the stool is searched at careful speed only, so it never tips;
- every office chair stop costs 4 extra samples that must be unseen;
- the lamp is one state bit with two seen tables, and a toggle costs 2 samples plus its click
  radius;
- `sit: player` is forced presence at the seat cell from the start of the approach to the end of
  the dwell. That time counts against the 8 s wait cap, so dwells there are short.

**It also adds:**
- a **"lesson required" check per level**: no schedule with the level's mechanic disabled;
- self-test fixtures `test_tip`, `test_dark` and `test_sit`.

## 6. Binding API (the integrator lands stubs first)

```csharp
namespace Meuble.Core
{
    public sealed class BodyDef { public string Kind; public Vector3 Size; public float Radius, MaxSpeed, Accel, AccelHigh,
        TurnRate, CarryForward; public bool Glides, Tips, HasLight; public static BodyDef For(string kind); }
    // MotionRule: new overload IsMoving(float planarSpeed, float yawRate, bool actionActive)
    // NoiseKind gains Topple, Click, Roll
    // CreakGauge.Step gains an overload with a 'paused' flag (sat on, hidden later)
    // GameRules gains bool Bodies, Sitting, Lamp; new preset GameRules.M4 = M2 + Bodies + Sitting + Lamp
    // (a new instance per call, like M1 and M2). GameState.Rules defaults to M4. The M1 probe keeps M1,
    // the M2 probe keeps M2 (levels 1 to 3 have no sit station and no lamp, so nothing changes there).
    // StationDef gains: string Sit; SeatDef Seat (x, z, yaw)
    // RouteStepDef gains: bool Careful; string Action
    // RoutineActivity gains Sitting, StandingUp, Pratfall
    // InhabitantRoutine gains: bool IsSitting; bool SitTargetsPlayer; Vector3 SeatHome; event-free flags
    //   JustSat (one step), SitResult {OnPlayer, OnProp, Pratfall}; float EyeHeight (interpolated)
}
namespace Meuble
{
    // FurnitureController: BodyDef Body; bool Careful; bool Tipped; bool Pinned; bool ActionActive;
    //   void SetBody(BodyDef); void Pin(bool on); Vector3 PredictedStop (office chair)
    // InputReader: CarefulHeld(), ActionPressed(), InjectAction(), InjectCareful(bool)
    // LampLight (new, Runtime): bool On; void Toggle(); float RangeFactor => On ? 1 : LampOffLight
    // Vision.Test gains an optional range factor parameter (default 1); the audit and VisionConeView use it
}
```

## 7. File ownership

| Agent | Owns |
|---|---|
| **core** | `Core/BodyDef.cs` (new), `Core/MotionRule.cs`, `Core/Hearing.cs`, `Core/CreakGauge.cs`, `Core/GameRules.cs`, `Core/InhabitantRoutine.cs` (sitting, pratfall, eye height, lamp investigation target), `Tests/EditMode/CoreM4Tests.cs` |
| **bodies** | `Runtime/FurnitureController.cs`, `Runtime/LampLight.cs` (new), `Runtime/Vision.cs`, `Runtime/VisionConeView.cs`, `Runtime/InputReader.cs`, `Runtime/GhostView.cs` (stop ring, seat ghost), `Tests/PlayMode/ProbeTestsM4Bodies.cs` |
| **game** | `Runtime/GameState.cs` (bodies, tips, lamp, sitting, pin, noises), `Runtime/Inhabitant.cs` and `Runtime/InhabitantRig.cs` (sit, stand, pratfall poses, eye height), `Runtime/Hud.cs` (contextual hints, sat-on line), `Runtime/Sfx.cs` (topple, click, roll, rattle, pratfall), `Tests/PlayMode/ProbeTestsM4Sitting.cs` |
| **levels** | `Core/LevelDef.cs`, `Core/LevelValidator.cs`, `Runtime/LevelBuilder.cs`, `Runtime/FurnitureKit.cs` (office chair, armchair prop), `Runtime/ModelKit.cs`, `Editor/LevelAudit.cs`, `Editor/ModelCatalogBuilder.cs`, `Resources/Levels/*.json`, `Tests/EditMode/LevelDataM4Tests.cs`, `Tests/PlayMode/ProbeTestsM4Levels.cs` (step 20-style replays of levels 4 to 7) |
| **integrator** | Tuning, Strings, docs, `verify.sh`, `mutation.sh`, `tools`, stubs, Probe.cs (built player shots of levels 4 to 7) |

## 8. Gate

**One probe step per rule**, numbered from 28 (a `b` or `c` suffix for variants):
- **28 stool tip:** release at full speed tips it, the topple is heard within 3.5 m, the tell
  shows above 1.3 m/s; careful mode never tips it; a head-on wall hit tips it; it stays down
  until a key is pressed; seen lying down, it is out of place.
- **29 office chair:** after release it keeps moving for 20 steps (0.4 s); seen during the glide
  means caught; the predicted stop point is within 0.05 m of the real stop.
- **30 lamp:** off, it is not seen at 6 m but is seen at 3 m; the click is heard within 2.5 m;
  an inhabitant who sees it off comes and switches it on.
- **31 sitting on a prop:** the eye lowers to 1.15 m; standing up is telegraphed.
- **32 sat on:** the player is pinned, not caught, not creaking; input is ignored until neutral.
- **33 pratfall:** the chair is missing at sitting time: one discovery, the pratfall, the look.
- **34 chair row identity:** the chair body equals the M1 constants, so M1 probe steps 01 to 12
  stay green.
- **35 levels 4 to 7:** boot, audit, designer routes at three offsets, and the lesson-required
  check.

**Mutations to add to `mutation.sh`:**
- the stool never tips;
- the office chair stops at once;
- the lamp does not change the range;
- sat on counts as moving;
- the gauge fills while sat on;
- the sit check accepts a chair 1 m off;
- the topple makes no noise.

**Critic pass** on the result, as before.

---

## 9. v3 amendments (binding; they override sections 2 to 8 where they conflict)

From the build-readiness review of v2. Decided by the integrator.

1. **The lamp is noticed by sight.**
   - An inhabitant reacts to a switched-off lamp only when it **sees the lamp**, which already
     requires the dark range (4 m) while it is off. It then switches it on.
   - The audit forbids any sighting of the lamp body (seen while moving is a catch, and seen
     while still would start a non-deterministic switch-on). So the dark range directly widens the
     safe area, and level 6's lesson-required check works: without the dark, no schedule.
2. **The sit hook.**
   - `InhabitantRoutine` gains `Func<bool> SeatOccupied`, set by GameState. Null means occupied
     (`OnPlayer`), so the audit and EditMode tests step the routine without a GameState.
   - **While seated:**
     - `Position` is the seat home;
     - `EyePosition` uses `EyeHeight` (1.6, then interpolated to 1.15 while seated);
     - `SeatHome` is a `FurniturePose`.
   - **The pin** follows the level-triggered flag `SittingOnPlayer` and releases on the first
     `StandingUp` step.
   - **After a sit on the player**, every inhabitant's player slot becomes the seat home pose.
3. **Missing cross-owner members** (the integrator stubs all of them):
   - **`FurnitureController`:**
     - `ToppleCount`, `ToggleCount`, `RollCount`;
     - `TellActive`;
     - `LampLight Lamp`;
     - `SetBody(BodyDef)`, the single runtime path that sizes the controller, the sample box and
       the visual;
     - `Pin(bool)`; `Pin(false)` re-arms the neutral-input wait, and `Release` clears `Tipped`;
     - `Rules`, a `GameRules` set by GameState and read in `Step`.
   - **`Vision.SeesPlayer`** keeps its meaning (the scaled range). `Vision.Test` gains
     `float rangeFactor = 1`.
   - **`GhostView`:**
     - `ShowSeat(FurniturePose?)` and `ShowStopRing(Vector3?)`, separate from `Show`/`Hide`;
     - GameState's `Hide` no longer erases them.
   - **`InhabitantRoutine`:**
     - `BeginSwitchOn(Vector3 lampPosition)` and `JustSwitchedOn`;
     - `float CarryForward`, set per body by GameState.
   - **`RouteStepDef`:** `bool Careful`, `string Action` (`"toggle"` or `"rightup"`),
     `float WaitFor` (seconds, 0 by default). No other field: `LevelJson` rejects unknown
     members.
4. **Tests go where their code is.**
   - Step 28 (stool) and step 30 (lamp): `ProbeTestsM4Game.cs` (game agent), using `SetBody` on
     level 1. Bodies and game tests never wait for the levels agent.
   - Step 34 (chair row equals M1) is an EditMode field-equality test (integrator), plus a
     mutation that changes a chair value and must turn an M1 step red.
   - Step 35's audit and lesson check run in the `verify.sh` audit stage, not in PlayMode. Only
     the route replays stay in PlayMode (levels agent).
5. **One size source.**
   - `BodyDef.Size` is the truth. `LevelBuilder` calls `SetBody`, and the validator rejects
     player sizes that disagree with `BodyDef`.
   - `BodyDef.For(null or unknown)` returns the chair, a new instance on every call.
   - `BodyDef` gains `IsSeat`, and `StageSpeed` for the stool: **1.3 m/s**, the same value as
     the tip threshold.
6. **Tuning names** (the integrator adds them):

   | Name | Value |
   |---|---|
   | `StoolTipSpeed` | 1.3 |
   | `StoolHighAccel` | 1.2 |
   | `StoolFallTime` | 0.3 |
   | `StoolRightTime` | 0.4 |
   | `StoolLeanDegrees` | 8 |
   | `ToppleNoiseRadius` | 3.5 |
   | `LampOffLight` | 0.4 |
   | `LampToggleTime` | 0.2 |
   | `LampClickRadius` | 2.5 |
   | `LampSwitchOnTime` | 0.5 |
   | `OfficeChairStopTime` | 0.4 |
   | `RollNoiseRadius` | 1.2 |
   | `RollNoiseInterval` | 0.3 |
   | `CarefulFactor` | 0.5 |
   | `SitEyeHeight` | 1.15 |
   | `SitEyeRiseTime` | 0.5 |
   | `SeatHomeTolerance` | 0.75 |
   | `PratfallTime` | 1.0 |
   | `AuditStopSamples` | 4 |

   Plus `CarryForward` per body (in `BodyDef`).
7. **InputReader.**
   - E and the move keys used for righting are **latched in `Update` and consumed in the fixed
     step**.
   - Presses are ignored while `ActionActive`.
   - "Gamepad X" is `buttonWest`.
   - `ResetInjections()` is called in every PlayMode TearDown, M1 to M4 included (the
     integrator edits the M1 to M3 test files).
8. **Replay.** Scripted input is dropped while the player is pinned and for one step after.
9. **Rule switches.**
   - `Bodies` gates the stool tip, the office chair glide and careful mode.
   - `Lamp` gates the light and the switch-on.
   - `Sitting` gates sit stations, which are skipped as a plain dwell when off.
   - **`BodyDef` constants always apply**, under every rule set. Only the special rules are
     gated, so the M1 probe exercises the chair row.
10. **Premises.**
    - **Step 29:** a glide integrated as velocity-then-move gives 19 or 20 moving steps after a
      release at 2 m/s or more. Assert 19 to 20.
    - **Step 30:** first assert the lamp is seen at 6 m while it is on.
    - **Step 31:** check `VisualEyePosition` and the head bone too.
    - **Step 32:** with a second watcher, the gauge stays constant.
    - **Step 33:** include the chair pulled away during the back turn, and pushed back in time.
    - **Toggle:** 0.2 s is 10 steps, so a toggle in sight is caught. This is stated in the
      hint and in the HUD.
11. **Audit details.**
    - Noise radius per body.
    - "In place" moves to the seat home after a sit on the player, and the creak pauses while
      pinned.
    - A door clearance check per body: a 0.45 m armchair radius needs doors of at least 1.0 m.
    - A per-level lesson knob, `"lesson": "careful" | "sit" | "dark" | "glide"`:
      - **dark:** no schedule without darkness;
      - **careful:** no schedule at full stool speed;
      - **sit:** a schedule must exist, and the sitting must constrain it, so moving the seat
        home 2 m away must change the schedule;
      - **glide:** the stop samples must bind.
    - Fixtures `test_tip`, `test_dark` and `test_sit`, each with a strict and a relaxed setting.
12. **Owners of the files the review found orphaned:**
    - **core agent:** `FurnitureMemory.cs` (an `Observe` overload with `lyingDown`);
    - **bodies agent:** `LampLight.cs` dims its room itself (no `Main` change);
    - **game agent:** `Sfx.cs` (synthesized topple, click, roll, rattle, pratfall; no
      `AudioLibrary` change) and `ProceduralArt.cs` (HUD icons).
13. **Integration only:**
    - levels 4 to 7 go into `levels.json` (Step 26 and Probe iterate the manifest);
    - every new mutation gets its marker line, file and killing step.

**Sequence:**
1. M3.1 green.
2. Integrator stubs.
3. In parallel: core, bodies, game (Hud, Sfx, rig poses; GameState wiring last), and levels
   phase A (LevelDef, validator, builder, kit).
4. Game integrates GameState.
5. Levels phase B: the audit extension.
6. Levels phase C: levels 4 to 7, their routes, then the manifest.
7. Mutations.

---

## 10. M4.1 fix wave (binding; from the result critique of 2026-11-12)

The result critic found 2 blockers and 8 majors on the green M4. Decided by the integrator. Each
item names its owner.

### 10.1 Sitting on the player: the audit follows the game (B1)

- **The rule is the game's.** The seat check happens **at the moment of sitting**. Presence is
  forced only from that moment to the end of the sat-on dwell (the pin); the approach is free.
  A pratfall is a discovery, so the audit forbids it.
- **levels:**
  - the audit's forced presence for `sit: player` starts at the simulated sitting moment (from
    the routine's own sit result), not at the start of the approach;
  - `SeatPresenceRadius` derives from `Tuning.SeatHomeTolerance`;
  - the `sit` lesson check becomes: a schedule exists, **and the earliest exit of any schedule
    with sitting disabled is later than the first sitting moment** (the lesson cannot be skipped).
    The report prints both times;
  - `test_sit` is rebuilt as an independent minimal fixture (not a copy of level 5);
  - **level 5 is redesigned** so that the exit cannot be reached before the first sitting.
- **levels (PlayMode):** a "rush" counter-route on level 5 (drive straight to the exit at once)
  must not win: it is caught or still short of the exit when the first sitting happens.

### 10.2 Sitting on a prop: one interpretation, no jump (B2)

- **The seat home of a prop is the prop center** (as shipped), facing the station's facing.
- **The rule eye slides.** At the moment of sitting, `Position` slides from the station spot to
  the seat home over the sit-down (`Tuning.SitEyeRiseTime` 0.5 s, the same interpolation as the
  eye height), for a prop and for the player. No one-step jump remains anywhere. Standing up
  already slides back. (core)
- **The validator checks prop seat fronts:** the station stands 0.3 to 0.8 m from the prop center,
  in front of it along the station's facing, and faces away from it within 30 deg. Level 4's
  station moves to comply. (levels)
- **Tests on real data:**
  - core: CoreM4Tests asserts the prop-center seat home through `ResolveSeats`, and its motion
    analyzer no longer whitelists a sit jump (the slide is bounded by 0.8 m over 0.5 s);
  - game: Step 31 runs on a level resolved by `LevelJson` (the seat home is the prop center),
    and checks that the floor cone apex follows the model's eye within 0.1 m during the
    sit-down.

### 10.3 The stool: a warning band, head-on hits only, lying guidance (majors 1, 2, 3)

- **Warning band.** New `Tuning.StoolTellSpeed` **1.0 m/s**. `BodyDef` stool `StageSpeed` becomes
  1.0 (the fast stage ends at the tell speed), so the stool climbs from 1.0 to the 1.3 m/s tip
  speed at `StoolHighAccel` 1.2 m/s2, which takes **0.25 s of visible tell**. The tell (lean and
  rattle) starts at 1.0 m/s and grows to full at 1.3. The tip threshold stays 1.3. (core for
  BodyDef, bodies for the tell)
- **Short taps never tip:** a press shorter than 0.3 s from rest, then a release, does not tip.
  A test checks 0.12 s and 0.25 s presses. (bodies)
- **Head-on only.** A wall hit tips only when the angle between the velocity and the inward
  wall normal is within `Tuning.StoolHeadOnDegrees` 30 deg **and** the normal speed is above
  1.3 m/s. A graze along a wall at full speed does not tip; a test checks 45 deg. (bodies)
- **Lying guidance.**
  - HUD line `hud.tipped` "Renversé : appuie sur une direction pour te relever." while the stool
    lies. (game; string by the integrator)
  - The remembered-pose ghost is hidden while the stool lies. (game)
  - The vision sample points use the lying box while tipped (top at the stool's lying height).
    (bodies)

### 10.4 The lamp toggle in sight is caught (major 4, amendment 9.10)

- `Tuning.LampToggleTime` becomes **0.3 s** (15 steps), so a toggle seen for its whole duration
  is caught with a margin over the 0.2 s grace.
- **During the toggle, the lamp's range factor is 1** (the lit range), whatever the direction.
  The light changes visually at the start, but the rules use the lit range until the action
  ends. (bodies: `LampLight.RangeFactor` or FurnitureController; levels: the audit's toggle
  samples use the lit table)
- `level6.hint` becomes "Dans le noir, on voit moins loin. Éteins (E) quand personne ne regarde."
  (integrator)
- **game:** a probe step `Step30e_ToggleInSightIsCaught`: a watcher at 6 m sees the lit lamp;
  switching it off is caught. And `Step30f_OutOfPlaceDarkLamp`: an out-of-place dark lamp gets
  the discovery and the carry first, then the switch-on.

### 10.5 Lessons and fixtures prove what they claim (major 5, 6)

- **dark:** the audit forbids sightings of the lamp **while it is off** and sightings **while it
  moves**. A lit, still, in-place lamp may be seen (the game does nothing then). (levels)
- **glide:** the report prints the exit time with and without the stop samples, and the refuted
  naive schedule's first sighting. (levels)
- `test_tip` and `test_dark` are rebuilt as independent minimal fixtures. (levels)
- **Level 6 is redesigned:** the inhabitant's loop passes within the dark range (4 m) of the
  lamp's natural path at least once, so darkness alone is not a free pass and a careless player
  can trigger the switch-on. (levels)

### 10.6 Noise on soft floors (minor)

- **Every** furniture noise (hop, topple, click, roll) is silent on a soft floor or a rug,
  matching the level 2 hint. (game; levels for the audit's `Heard`)

### 10.7 Smaller fixes

- Fail texts are body neutral: `fail.body` "Un meuble ne bouge pas tout seul." and
  `fail.suspicionBody` "Ce meuble se promène un peu trop." (integrator)
- The seat ghost gets its own warm colour (not the memory ghost's cyan), and the furniture's
  visual slides to the seat home over 0.3 s (the rule pose still snaps). (game)
- `RouteStepDef.WaitFor` is removed (never read). (levels)
- The roll noise is gated by `Rules.Bodies`; without it, the office chair hops like the chair.
  (bodies)
- `BlockedFraction`, `GlideEpsilon` (bodies) and `TriggerHeld` (bodies, InputReader) move to
  Tuning. (integrator adds the names, owners switch to them)
- Step 33d also checks 0.70 m (sat on) and 0.80 m (pratfall). (game)
- **Slack report.** The audit prints, per level, the largest margin (in samples) for which a
  schedule still exists. It is playtest data, not a gate. (levels)

### 10.8 Gate additions (integrator)

- `verify.sh`: an expected EditMode name list (the chair-row test, the paused-gauge test, and
  the M4 core tests killed by mutations), so a deleted test turns the stage red.
- `mutation.sh`:
  - it refuses to start when a `.bak` of a previous run differs from its source (an unrestored
    mutation), and snapshots `Assets/Scripts` and `Assets/Editor` first;
  - it adds rows for the tell speed, the toggle's lit range, and the audit's sit moment (killed
    by `test_sit` through the audit stage, as a mode `Audit`).
- The project is not under version control. The integrator recommends a commit to the product
  owner and does not commit without being asked.
