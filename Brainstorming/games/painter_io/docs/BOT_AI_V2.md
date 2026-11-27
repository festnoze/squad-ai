# Bot AI v2: design and work plan

Status: design, nothing implemented yet. Project: `games/painter_io` (code name PainterIO).
Audience: the agents that will implement the new enemy AI, and the orchestrator that splits the work between them.

This document replaces the bot behaviour of contract section 9 (`docs/CONTRACT.md`). It does not change any game rule.
Read sections 1 to 4 before any task. Sections 5 to 9 are the specification. Sections 10 to 14 are the work plan.

---

## 1. Goals

The designer asked for a new enemy AI, rebuilt from scratch, with these properties:

1. **360 degree perception, one screen wide.** A bot knows everything inside a disc around its head whose radius matches
   what a player sees on a phone screen, and nothing outside it.
2. **Always alive.** From the first tick of a level, every bot perceives and decides continuously, whether it is on
   screen or not. No level of detail, no sleeping bots.
3. **Predefined strategies.** Each bot has conquest strategies (how it grows) and security strategies (how it stays
   safe and protects its land while staying inside it).
4. **A personality of its own.** Some bots are conquerors, some are guardians of their domain. The same situation gives
   different decisions depending on the personality.
5. **Adapted reactions to other players.** When a bot sees a competitor it reacts: it falls back when it is outside its
   land and in danger, or it turns aggressive and tries to cut the competitor's line. It is more aggressive against the
   human player.
6. **Simple and fast.** Simple to implement, cheap to run on a phone, and deliverable in iterations: a first AI that
   works and is good enough quickly, then improvements milestone by milestone.

Non-goals: learning, path search on the grid, team play between bots, any change to the simulation rules.

---

## 2. What exists and what must not change

### 2.1 Game facts the AI relies on

| Fact | Value | Source |
|---|---|---|
| Arena | 64 x 64 u box, rounded square or a country polygon inside it | `Tuning.cs`, `ArenaPolygon.cs`, `EuropeCatalog.Configure` |
| Players | 4 (1 human + 3 bots), attract mode: 4 bots | `Tuning.PlayerCount` |
| Pawn speed | 6 u/s, turn rate 540 deg/s | `Tuning.PawnSpeed`, `TurnRateDeg` |
| Round | 90 s, one life | `Tuning.RoundDuration` |
| Cut contact | head within `SimConfig.ContactRadius` (0.63 u) of the exposed trail | R10 |
| Head grace | the last 1.0 u of a trail is not exposed | `Tuning.HeadGrace` |
| Spark | starts at the cut point, runs at 1.8 x the victim's speed along the trail | R11 to R13 |
| Rule v1.4 | an exit that was cut captures nothing, even if its owner gets home | contract 24 |
| Rule v1.5 | territory severed from its owner becomes neutral | contract 29 |
| Rule v1.6 | Fire biome: one single domain, kill inheritance bridge | contract 30 |
| Camera | portrait view 18 u wide, so 32 u high at 9:16 | `CameraRig.PortraitWidth` |

Consequences that drive the design:

- A bot standing on its own land has no trail and cannot be hurt. Cutting an intruder from home is free.
- Any cut costs the victim its whole loop (v1.4). So a bot must come home before anyone can touch its trail, not only
  before the spark would kill it.
- A cut close to the victim's head is the dangerous one: the spark has little distance to cover.
- Crossing your own trail is harmless. The AI does not need to avoid it.

### 2.2 Interfaces that stay as they are

- `IController.DesiredHeading(SimView view, int playerIndex)` is called once per tick for every alive player, before
  motion. It returns a heading in radians, or null to keep the current one. This is the only entry point of a bot.
- `SimView` is the only thing a bot may read. It must never mutate anything reachable from it.
- `GameSession.BotSeed(roundSeed, playerIndex)` gives each bot its seed.
- The first round of a new player is gentle: `HumanAttackScale = 0.3` when `SaveData.TutExitDone` is false.

### 2.3 Legacy bot

`Assets/Scripts/Core/Bots/` (`BotController`, `BotPersonality`, `BotSenses`) is the legacy bot. Twelve test files use it
as traffic for rule tests. **Do not edit, move or delete it before milestone M4.** The new AI lives next to it in a new
folder and does not call it. Copying a helper function from it into the new code is allowed.

---

## 3. Hard constraints for every task

1. **Pure Core.** New code goes in `Assets/Scripts/Core/Ai/`, namespace `PainterIO.Core`, no `UnityEngine` reference
   (the assembly has `noEngineReferences`). It must compile in the dotnet loop (`tools/CoreTests`).
2. **Deterministic.** Same seed and same view give the same decisions. Random numbers come only from the bot's own
   `Rng`. No clock, no `System.Random`, no static mutable state, no dependence on the render frame rate.
3. **No allocation per decision.** Buffers are allocated once in the constructor. This matters on mobile.
4. **Read only.** Never call a method that mutates the grid, a trail or a player. Use public getters and read-only
   lists (`Trail.Points`, `Trail.Arc`, `OwnerGrid.OwnerAt`, `GridQueries.NearestOwned`, `GridRaster.FirstEntry`).
5. **Trait aware by construction.** Never use `Tuning` constants for speeds or radii. Read `view.EffectiveSpeed(i)`,
   `view.Config.ContactRadius`, `view.Config.SparkSpeedOf(...)`, `view.IsShielded(i)`. This is what makes the bots
   correct in the three biomes without special cases.
6. **Works on country arenas.** Never assume a square arena. Use `view.Arena.SignedDistance` and `ClampInside`.
7. **English** for code, comments and documents. Async methods, if any, are prefixed with `a` (none are expected).
8. **File ownership.** A task edits only the files listed for it in section 11. Shared types change only through the
   task that owns them.

Tooling reminders:

```powershell
# Core tests, no Unity lock needed (run from the project root, in PowerShell, never Git Bash)
dotnet test tools/CoreTests/PainterIO.CoreTests.csproj --artifacts-path tools/CoreTests/.art/<task> -v q --filter "FullyQualifiedName~Ai"

# Anything that starts Unity goes through the project lock
pwsh -NoProfile -File tools/unity.ps1 -Agent <task> -UnityArgs "..."

# Build and probe (only the gate tasks run this)
pwsh -NoProfile -File tools/verify.ps1 -Steps setup,buildwindows,probe -KeepGoing
```

New `.cs` files need their Unity `.meta` files. They are generated by the `setup` step; keep them.

---

## 4. Architecture overview

One bot is one `AiController`. Ten times per second of simulation time it runs a decision; every tick it outputs a
heading toward its current target.

```
                 every 0.1 s of sim time                          every tick
SimView --> [ Sense ] --> AiPercept --> [ Arbiter ] --> intent + target --> [ Steering ] --> heading
              360 degrees,                 |  priority rules
              screen radius                |
                          +----------------+----------------+----------------+
                          |                |                |                |
                     [ Safety ]       [ Attack ]       [ Expand ]        [ Home ]
                     must I go        whom can I       where and how     patrol and
                     home now?        cut, is it       do I grow?        guard inside
                                      worth it?                          my land
```

Every box is a small static class with pure functions. All personality differences come from one data object,
`AiTraits`. The modules share two data types, `AiPercept` (what the bot sees now) and `AiPlan` (the current loop).
This split is what allows the modules to be written in parallel.

### 4.1 Intents

| Intent | Where | Meaning |
|---|---|---|
| `Roam` | home | walking inside its land toward the exit point of the next loop |
| `Patrol` | home | staying inside its land, walking along its border (resting, or no safe loop available) |
| `Expand` | trailing | drawing the planned loop |
| `Return` | trailing | going home by the fastest way; locked until home |
| `Attack` | home or trailing | going to cut a visible enemy trail |

### 4.2 Arbiter: the priority rules

At each decision, in this order. The first rule that applies wins.

1. **Own spark.** Trailing with a spark behind it (after `ReactionDelay`): `Return`.
2. **Safety.** Trailing and `AiSafety.MustReturn` is true (after `ReactionDelay` for a new threat): `Return`.
3. **Already returning.** Intent is `Return` and still trailing: keep `Return`, refresh the home point.
4. **Ongoing attack.** Intent is `Attack`: re-evaluate the strike on the same victim. Still valid and committed for less
   than `AttackCommitSeconds`: keep it. Otherwise `Return` when trailing, `Patrol` when home.
5. **New attack.** `AiAttack.Pick` finds a strike whose desire reaches `AttackThreshold`: `Attack`.
6. **Following a loop.** Intent is `Expand` with plan points left: keep going. Plan finished: `Return` (closes the loop).
7. **At home, resting.** Dwell time not elapsed: `Patrol`.
8. **At home, ready.** `AiExpand.Plan` gives a plan that passes `AiSafety.SafeToStart`: `Roam` to its exit point, then
   `Expand` as soon as the simulation says the bot is trailing. No acceptable plan: `Patrol`, retry in 0.5 s.

Two more transitions follow the simulation's `Home` flag, which is the only truth about safety:

- Trailing bot becomes home: intent `Patrol`, plan cleared, dwell timer started.
- Home bot becomes trailing without a plan (the land under it was taken): `Return`.

### 4.3 Decision clock

Decisions are tied to simulation time, never to frames: a decision runs when `floor((view.Time + self * 0.025) * 10)`
changes. The `self * 0.025` term staggers the bots so that their decisions do not land on the same tick. A new round
(another `SimView`, or time going backwards) resets the controller and re-seeds its `Rng`, like the legacy bot does.

---

## 5. Frozen API

These signatures are binding. Task M0 creates them with neutral stub bodies; the M1 tasks fill them in. Changing a
signature requires the orchestrator's agreement and an update of this section. All classes are `public` so the tests
can reach them.

```csharp
namespace PainterIO.Core
{
    public enum AiArchetype { Conqueror, Guardian, Hunter, Opportunist }
    public enum AiIntent { Roam, Patrol, Expand, Return, Attack }

    /// Personality. Five knobs in 0..1 (HumanFocus is a multiplier); everything else is derived (section 6).
    public sealed class AiTraits
    {
        public AiArchetype Archetype;
        public double Ambition;        // size and length of excursions
        public double Caution;         // safety margins, how early it falls back, how compact it keeps its land
        public double Aggression;      // willingness to cut trails and to steal land
        public double Skill;           // reaction time and aim precision
        public double HumanFocus = 1;  // multiplies the attack desire when the victim is the human
        public double HumanAttackScale = 1;  // tutorial gentleness, set by the runtime (0.3 on the first round)
        public double SenseRadius = Tuning.BotSenseRadius;
        public static AiTraits Preset(AiArchetype archetype);
        // Derived values: read-only properties, formulas in section 6.2.
    }

    /// One visible enemy. Rebuilt at every decision.
    public struct AiEnemy
    {
        public int Index; public bool IsHuman;
        public Vec2d Pos; public double Heading; public double Speed;  // view.EffectiveSpeed
        public bool Trailing;
        public bool Cuttable;          // trailing, not shielded, exit not already cut
        public double TrailLength;
        public double DistHome;        // from its head to its nearest own cell (0 when home)
        public double DistToMyTrail;   // from its head to my exposed trail (+inf when I am home)
        public double TimeToMyTrail;   // seconds before it can touch my trail (+inf when I am home or shielded)
    }

    /// What the bot knows now. One instance per controller, refilled in place.
    public sealed class AiPercept
    {
        public double Time; public int Self; public byte MyId;
        public Vec2d Pos; public double Heading; public double Speed;
        public bool Trailing; public double TrailLength;
        public bool Chased; public double SparkEta;      // own spark, view.SparkCatchEta
        public double ShieldLeft;                        // seconds, 0 when not shielded
        public Vec2d HomePoint; public double DistHome; public double TimeHome;  // nearest own cell
        public readonly AiEnemy[] Enemies; public int EnemyCount;  // visible enemies only
        public double ThreatTime; public int ThreatIndex;          // min TimeToMyTrail, -1 when none
        public bool RingVisible; public Vec2d RingPos;
        public double TimeLeft;                          // RoundDuration - Time
    }

    /// The current loop: outbound waypoints. The loop is closed by Return (nearest own land), not by a waypoint.
    public sealed class AiPlan
    {
        public const int MaxPoints = 8;
        public readonly Vec2d[] Points; public int Count; public int Index;
        public Vec2d Exit;          // edge point where the bot leaves its land
        public Vec2d Normal;        // outward direction at Exit
        public double OutLength;    // trail length of the loop, from Exit back to own land (estimate)
        public double Gain;         // estimated captured value
        public void Clear();
    }

    public struct AiStrike
    {
        public int Victim; public double S; public Vec2d Point;   // intercept point on the victim's trail, arc S
        public double TimeToCut; public bool Lethal; public bool ZeroExposure; public double Desire;
    }

    public static class AiSenses
    {
        public static void Sense(SimView view, int self, AiTraits traits, AiPercept into);
        public static double DistanceToExposedTrail(Trail trail, double headGrace, Vec2d p, out double arc);
        public static bool EdgePoint(OwnerGrid grid, byte me, Vec2d from, Vec2d dir, double reach, out Vec2d edge);
        public static double TurnTime(double heading, Vec2d from, Vec2d to, double turnRateRad);
    }

    public static class AiSafety
    {
        public static bool MustReturn(AiPercept p, AiTraits traits, SimConfig config);
        public static bool SafeToStart(AiPercept p, AiTraits traits, AiPlan plan, SimConfig config);
    }

    public static class AiExpand
    {
        public static bool Plan(SimView view, AiPercept p, AiTraits traits, Vec2d anchor, Rng rng, AiPlan into);
    }

    public static class AiAttack
    {
        /// exitBias: one random factor per enemy, redrawn by the controller when that enemy starts a new exit.
        public static bool Pick(SimView view, AiPercept p, AiTraits traits, double[] exitBias, int onlyVictim, out AiStrike strike);
    }

    public static class AiHome
    {
        /// Target of the Patrol intent: a point inside own land, near the border. patrolSign is +1 or -1.
        public static Vec2d PatrolTarget(SimView view, AiPercept p, AiTraits traits, ref int patrolSign, Rng rng);
    }

    public static class AiSteering
    {
        /// Heading toward target with aim noise, bent away from the arena rim when needed.
        public static double Heading(SimView view, AiPercept p, Vec2d target, double noise);
    }

    public sealed class AiController : IController
    {
        public const int DecisionsPerSecond = 10;
        public AiController(AiTraits traits, ulong seed);
        public AiTraits Traits { get; }
        public AiIntent Intent { get; }
        public long Decisions { get; }
        public int VictimIndex { get; }                  // -1 unless Intent == Attack
        public bool TryGetTarget(out Vec2d point);
        public void CopyPlan(System.Collections.Generic.List<Vec2d> output);
        public AiPercept Percept { get; }                // last snapshot, for tests and the debug overlay
        public double? DesiredHeading(SimView view, int playerIndex);
    }

    public enum BotBrain { Legacy, V2 }

    /// The only place that builds bot controllers for the runtime and the probe.
    public static class BotFactory
    {
        public static BotBrain DefaultBrain = BotBrain.Legacy;   // M1 gate switches it to V2
        public static IController Create(BotBrain brain, int slot, ulong seed, bool gentle);
        public static AiArchetype ArchetypeOfSlot(int slot);     // slot = player index, see 6.3
    }
}
```

New constant: `Tuning.BotSenseRadius = 16.0` (section 7.1).

---

## 6. Personality

### 6.1 Archetypes

| Archetype | Ambition | Caution | Aggression | Skill | HumanFocus | In one sentence |
|---|---|---|---|---|---|---|
| Conqueror | 0.85 | 0.30 | 0.35 | 0.60 | 1.2 | Big loops, grows fast, accepts risk, attacks only sure kills |
| Guardian | 0.30 | 0.85 | 0.45 | 0.60 | 1.2 | Small safe loops, compact land, long patrols, punishes intruders from home |
| Hunter | 0.45 | 0.35 | 0.90 | 0.70 | 1.6 | Medium loops, goes after exposed trails, the human first |
| Opportunist | 0.60 | 0.55 | 0.55 | 0.60 | 1.3 | Balanced, takes what is cheap |

These are starting values. The tuning task of each milestone may move them and must report the final table.

### 6.2 Derived values

`L(a, b, x) = a + (b - a) * x`.

| Property | Formula | Conqueror | Guardian | Hunter |
|---|---|---|---|---|
| `DepthMin` (u) | L(2.5, 5.5, Ambition) | 5.1 | 3.4 | 3.9 |
| `DepthMax` (u) | L(5, 14, Ambition) | 12.7 | 7.7 | 9.1 |
| `MaxTrailLength` (u) | L(16, 48, Ambition) | 43 | 26 | 30 |
| `SafetyMargin` (s) | L(0.3, 1.5, Caution) | 0.66 | 1.32 | 0.72 |
| `StartSafety` | L(0.25, 1.0, Caution) | 0.48 | 0.89 | 0.51 |
| `RiskWeight` | L(0.5, 2.5, Caution) | 1.1 | 2.2 | 1.2 |
| `CompactWeight` | 0.5 * Caution | 0.15 | 0.43 | 0.18 |
| `DwellExtra` (s) | 2.0 * Caution * (1 - Ambition) | 0.09 | 1.19 | 0.39 |
| `RivalLandValue` | L(0.2, 1.5, Aggression) | 0.66 | 0.79 | 1.37 |
| `AttackRange` (u) | L(5, 14, Aggression) | 8.2 | 9.1 | 13.1 |
| `AttackDrive` | 0.4 + 1.2 * Aggression | 0.82 | 0.94 | 1.48 |
| `ReactionDelay` (s) | L(0.45, 0.15, Skill) | 0.27 | 0.27 | 0.24 |
| `AimNoise` (rad) | L(0.14, 0.04, Skill) | 0.08 | 0.08 | 0.07 |

Fixed constants (in `AiTraits` or the module that uses them): `AttackThreshold = 0.6`, `AttackCommitSeconds = 2.0`,
`DenialValue = 0.45`, `MinDepth = 1.5`, `PatrolInset = 1.5`, `EndOfRoundSlack = 2.0`.

### 6.3 Line-ups

- Real round (players 1 to 3): Conqueror, Guardian, Hunter.
- Attract mode and the probe's bot round (players 0 to 3): Opportunist, Conqueror, Guardian, Hunter.

---

## 7. Module specifications (milestone M1)

### 7.1 Perception: `AiSenses.Sense`

**Radius.** `Tuning.BotSenseRadius = 16 u`: half the height of the portrait view at 9:16 (18 u wide, 32 u high). A bot
sees as far as a player sees up and down on a phone. A Runtime EditMode test asserts
`Tuning.BotSenseRadius == CameraRig.PortraitWidth * 0.5 * 16 / 9` so the two cannot drift apart.

**Visibility.** An enemy is visible when it is alive and either its head is within the radius of the bot's head, or
some point of its exposed trail is. So a bot can cut a line whose owner is off its screen, like a human can.
The field of view is the full disc: no blind spot behind the bot.

**Own state.** Position, heading, speed, trailing or home, trail length, own spark and its ETA, shield time left.
`HomePoint` and `DistHome` come from `GridQueries.NearestOwned(grid, myId, pos, 100)`. A bot always knows where its own
land is. `TimeHome = DistHome / Speed + TurnTime(heading, pos, HomePoint)`.

**Per visible enemy.** The `AiEnemy` fields. When the bot is trailing:

```
DistToMyTrail = distance from the enemy head to my trail restricted to arcs [0, Length - HeadGrace]
TimeToMyTrail = max(0, DistToMyTrail - ContactRadius) / enemy.Speed + TurnTime(enemy heading toward that point)
```

`TimeToMyTrail` is +inf when the bot is home or when `ShieldLeft > TimeHome + 0.5`.
`ThreatTime` is the minimum over the visible enemies (+inf when none).

**Territory.** No global scan of the grid. The modules probe the grid locally with rays and samples, inside the radius.

Cost target: one pass over each visible trail (a few hundred point-segment distances) and one `NearestOwned` per alive
player.

### 7.2 Safety: `AiSafety`

`MustReturn(p)` is true when the bot is trailing and any of these holds:

| Trigger | Condition |
|---|---|
| Trail too long | `TrailLength > MaxTrailLength` |
| Race lost soon | `ThreatTime < TimeHome + SafetyMargin` |
| End of round | `TimeLeft <= TimeHome + EndOfRoundSlack` |

The second line is the heart of the security behaviour: **the bot leaves while it can still be home before anyone can
touch its trail.** A guardian keeps a wide margin, a conqueror a thin one.

`SafeToStart(p, plan)` decides whether a loop may begin. For every visible enemy:

```
tReach = max(0, distance(enemy head, polyline Exit -> Points[0..Count-1]) - ContactRadius) / enemy.Speed
safe when tReach >= StartSafety * (plan.OutLength / p.Speed)
```

A guardian starts a loop only if it can nearly finish it before the nearest enemy arrives. A conqueror accepts half.

### 7.3 Conquest: `AiExpand.Plan`

Called when the bot is home and ready. M1 has one loop shape, the **Bite**: go out by `depth`, go sideways by `width`,
then close on the nearest own land.

1. Cast 16 rays from the head (every 22.5 degrees, plus one random phase). For each ray, `EdgePoint` gives the first
   point that is not own land, within `SenseRadius`. Skip rays with no edge, and edges closer than 1.5 u to the rim.
2. Draw `depth = rng.Range(DepthMin, DepthMax)` and `width = depth * rng.Range(0.7, 1.3)` once for the whole plan.
   Shrink both so that the loop ends `EndOfRoundSlack` seconds before the round does; give up under `MinDepth`.
3. For each candidate edge `E` with outward direction `n`, and for both sides `s` (left and right):
   - Sample the footprint on a 1 u lattice: points `E + n * a + s * b`, `a` in (0.5 .. depth), `b` in (0.5 .. width).
   - Value of a sample: neutral 1, enemy land `RivalLandValue`, own land 0, outside the arena -0.5.
   - `gain` = sum of the values. `outLength = 2 * depth + width`. `efficiency = gain / outLength`.
   - `risk` = sum over visible enemies of `max(0, 1 - distance(enemy head, footprint centre) / SenseRadius)`.
   - `score = efficiency * rng.Range(0.85, 1.15) - RiskWeight * risk - CompactWeight * distance(footprint centre, anchor) / 10 - 0.02 * distance(head, E)`
4. Keep the best candidate with `gain > 0`. Waypoints: `P1 = E + n * depth`, `P2 = P1 + s * width`, both passed through
   `Arena.ClampInside` with 1 u of extra margin. If `P1` is own land after clamping, try the next candidate.
5. Fill `AiPlan` (`Exit`, `Normal`, `Points`, `OutLength`, `Gain`). Return false when no candidate is left.

`anchor` is the bot's home anchor: its spawn point, moved by the controller to the head position each time the bot is
home and more than 2 u away from any edge found by the rays. The `CompactWeight` term is what makes a guardian keep a
compact, defensible domain while a conqueror spreads.

If `SafeToStart` rejects the plan, the controller retries once with `depth` and `width` multiplied by 0.6, then falls
back to `Patrol`.

Fallback when no ray finds an edge (the bot is deep inside a large land): walk toward the last exit point until an
edge is visible.

### 7.4 Encounters: `AiAttack.Pick`

For every visible enemy `v` with `Cuttable == true` (or only `onlyVictim` when re-evaluating an ongoing attack):

1. Sample its exposed trail at arcs `s = L - HeadGrace - 0.3 - k` (k = 0, 1, 2, ...), keeping the points `P` within
   `AttackRange` and within `SenseRadius` of the bot's head.
2. For each sample:

```
tMe      = max(0, |P - head| - ContactRadius) / mySpeed + TurnTime(toward P)
tHomeV   = v.DistHome / v.Speed
feasible = tMe < tHomeV                       (the trail is still there when I arrive)
gap      = L + v.Speed * tMe - s
lethal   = feasible and gap / (SparkSpeedOf(v) - v.Speed) < tHomeV - tMe
```

3. Keep one sample per enemy: the lethal one with the smallest `tMe`, else the feasible one with the smallest `tMe`.
4. Exposure of the bot:
   - `ZeroExposure` when the bot is home and `P` plus three points of the segment head-to-`P` are own land.
   - Otherwise `exposure = tMe + distance(P, my nearest own cell) / mySpeed`. Reject the strike when
     `TrailLength + |P - head| + distance(P, my land) > MaxTrailLength`, or when another visible enemy has
     `TimeToMyTrail < exposure + SafetyMargin`.
5. Desire:

```
value  = lethal ? 1.0 : DenialValue * min(1, L / 16)
desire = value * AttackDrive * exitBias[v]
         * (v.IsHuman ? HumanFocus * HumanAttackScale : 1)
         * (ZeroExposure ? 1.3 : 1)
         - (ZeroExposure ? 0 : Caution * exposure / 4)
```

6. Return the strike with the highest desire. The arbiter attacks when `desire >= AttackThreshold`.

`exitBias[v]` is drawn in `rng.Range(0.8, 1.2)` by the controller each time enemy `v` starts a new exit, so the same
situation does not always give the same answer, and the answer does not flicker between two decisions.

What this gives, with the starting values:

| Situation | Conqueror | Guardian | Hunter |
|---|---|---|---|
| Sure kill, 2 s of exposure | attacks | holds back | attacks |
| Sure kill, intruder on its own land | attacks | attacks | attacks |
| Denial cut on a long trail, 2 s of exposure | no | no | attacks |
| Denial cut on the human, from home | no | attacks | attacks |

The human bias the designer asked for is `HumanFocus` (1.2 to 1.6): the same opportunity is taken more often when the
line belongs to the human. Target selection reads `IsHuman` for nothing else.

### 7.5 Security at home: `AiHome.PatrolTarget`

The bot walks along its border from the inside, never leaving its land:

```
dir    = heading rotated by patrolSign * 35 degrees
edge   = EdgePoint(grid, me, head, dir, SenseRadius)
target = edge pulled back PatrolInset (1.5 u) toward the head
```

If no edge is found within 2 u in that direction (the land is tiny or the bot is in a corner), flip `patrolSign` and use
`target = head + direction(heading + patrolSign * 60 degrees) * 1.0` (a small orbit).

A bot patrols during its dwell time after each return (`rng.Range(0.2, 0.6) + DwellExtra` seconds) and whenever no
loop is safe to start. While it patrols, `AiAttack.Pick` still runs at every decision, so a patrolling guardian cuts
any line that comes through or close to its land.

### 7.6 Steering: `AiSteering.Heading`

```
h = angle(target - pos) + noise                         (noise redrawn by the controller at each decision, +-AimNoise)
probe = pos + direction(h) * 1.5
if view.Arena.SignedDistance(probe) > -view.Arena.Margin:
    try h +- 20, 40, 60, 80 degrees, nearest to the target first; keep the first heading whose probe is inside
```

This is enough to follow concave country borders without pushing into the rim. The steering is not a path finder.

### 7.7 Controller: `AiController`

Owns the `Rng`, the `AiPercept`, the `AiPlan`, the anchor, the timers (dwell, reaction, attack commitment) and the
arbiter of section 4.2. It also:

- advances the plan index when the head is within 0.5 u of the current waypoint, and skips waypoints that became own
  land;
- applies `ReactionDelay`: a threat or an own spark first seen at time t is acted on from `t + ReactionDelay`;
- re-aims an attack at every decision by calling `AiAttack.Pick` with `onlyVictim`;
- resets everything when the round changes.

---

## 8. Continuous update, on screen or not

Requirement 2 of section 1 is already how the simulation works: `Simulation.Step` calls `DesiredHeading` for every alive
player at every tick, and nothing in the Core knows about the camera. The new AI must keep it that way:

- No reference to the camera, the screen or the human's position to decide whether to think.
- No reduced decision rate for far bots.
- The perception radius is centred on the bot itself, not on the human.

The ready gate at the start of a level (`GameSession.AwaitingStart`) pauses the whole simulation, bots included. This
is intended: the level has not started yet.

Test `Ai_AllBotsActFromTheFirstSeconds` (M1): in a headless round with no runtime at all, every bot has left its land
at least once before t = 4 s, and no bot stays in `Patrol` for more than 6 s in a row while no enemy is visible.

---

## 9. Verification

### 9.1 Bench harness

`Assets/Tests/EditMode/Core/Ai/AiBenchKit.cs` runs seeded rounds without Unity and returns statistics. It is adapted
from the harness in `BotTests.cs` (`RunRound`, `Summary`, `RunSeeds`), without editing that file.

```csharp
public static AiBenchResult Run(int seeds, Func<int, ulong, IController> makeController, AiBenchOptions options);
// options: human index (-1 = bots only), arena (square or a country polygon), traits (classic, liquid, fire, electric), lasso
```

Statistics per player: captures, cells at the end, alive at the end, placed first, share of alive time spent trailing,
cuts made, kills, deaths by spark, attacks started and against whom, ticks held against the rim, time per intent.
Per run: share of rounds with a cut, with a spark kill, reaching time up; mean coverage; decision cost (mean, p99, max);
bytes allocated per decision after warm-up.

### 9.2 Gate of milestone M1

Bot-only rounds, 50 seeds, classic rules, square arena, line-up of 6.3 (asserted in the dotnet loop; 10 seeds and only
the invariants inside Unity):

| Metric | Target |
|---|---|
| Exceptions, invariant failures | 0 |
| Mean captures per bot | Conqueror and Hunter >= 4, Guardian >= 3 |
| Share of alive time spent trailing | 25 % to 70 % for every bot |
| Rounds with at least one cut | >= 85 % |
| Rounds with at least one spark kill | 30 % to 80 % |
| Rounds reaching time up | >= 40 % |
| Mean coverage at the end | 30 % to 85 % |
| Ticks held against the rim | 0 |
| Mean decision cost | < 0.2 ms (dotnet Debug) |
| Allocation per decision after warm-up | 0 byte |
| Determinism | same seed twice gives the same `Simulation.StateHash` at the end |

Personality separation (same 50 seeds; this is what proves the personalities exist):

| Metric | Target |
|---|---|
| Mean cells captured per excursion | Conqueror > Opportunist > Guardian |
| Deaths by spark per round | Guardian < Conqueror |
| Cuts made per round | Hunter highest |
| Time in `Patrol` | Guardian highest |

Human proxy (player 0 = Opportunist with `Skill` 0.4 and `HumanFocus` 1, flagged `IsHuman`, against the real line-up):

| Metric | Target |
|---|---|
| Proxy alive at the end | 35 % to 75 % of rounds |
| Proxy placed first | 15 % to 45 % of rounds |
| Attacks started against the proxy | more than against any single bot |

Country arenas (10 seeds each on France, Italy and Norway, loaded from `Assets/Resources/Europe/countries.json`):
no exception, rim-held ticks under 0.5 % of bot ticks, every bot captures at least once in 80 % of rounds.

Biomes (10 seeds each with the liquid, fire and electric trait sets): no exception, invariants hold.

Then, in the built player: `verify.ps1 -Steps setup,buildwindows,probe`, the probe hash equal at 30 and 144 fps, and
`Build/Play` refreshed for the designer's playtest. The designer's eyes are the last gate.

---

## 10. Milestones

Each milestone ends with a playable build and can be the last one.

| Milestone | Outcome for the player | Content |
|---|---|---|
| **M0 Foundations** | nothing visible | frozen API as stubs, factory and launch flag, bench harness |
| **M1 First playable AI** | bots with four personalities that grow, fall back, patrol and cut lines, the human first | sections 7 and 8, gate 9.2, v2 becomes the default |
| **M2 Smarter encounters** | bots that read the situation, defend their land, use the biome | section 12.1 |
| **M3 Life** | bots that feel alive and differ from round to round, difficulty that follows the progression | section 12.2 |
| **M4 Cleanup** | nothing visible | legacy removal, contract rewrite, device performance |

M0 and M1 are fully specified here. M2 and M3 are specified at the level of intent and acceptance; the planning agent
of each milestone writes the detailed tasks using the M1 as-built report.

---

## 11. Tasks of M0 and M1

Size: S = a few hours of agent work, M = about half a day, L = more. Every task ships its tests and a report
`docs/ai/<task-id>.json` (section 13).

### 11.1 Task list

| Id | Task | Size | Owns (creates or edits) | Depends on |
|---|---|---|---|---|
| M0-1 | API skeleton: all types and signatures of section 5 with neutral stubs (`Sense` fills the own state only, `MustReturn` false, `Plan` false, `Pick` false, `PatrolTarget` = head, `Heading` = straight to target). `AiTraits` presets and derived values with their tests. `Tuning.BotSenseRadius`. `AiController` that compiles and stays home. | S | `Core/Ai/*.cs` (all files, created), `Core/World/Tuning.cs` (one constant), `Tests/EditMode/Core/Ai/AiTraitsTests.cs` | none |
| M0-2 | Bench harness `AiBenchKit` and a smoke test that runs it on the legacy bot. Loader for country arenas in tests. | M | `Tests/EditMode/Core/Ai/AiBenchKit.cs`, `AiBenchSmokeTests.cs` | M0-1 |
| M0-3 | `BotFactory`, launch flag `-bots legacy|v2`, `GameSession.CreateRound`, `AttractControllers` and the probe's bot round built through the factory. Default stays Legacy. | S | `Core/Ai/BotFactory.cs`, `Runtime/Game/GameSession.cs`, `Runtime/Probe/PlayerProbe.cs` | M0-1 |
| M1-A | Perception (7.1) | M | `Core/Ai/AiSenses.cs`, `Tests/.../AiSensesTests.cs` | M0-1 |
| M1-B | Safety (7.2) | S | `Core/Ai/AiSafety.cs`, `Tests/.../AiSafetyTests.cs` | M0-1 |
| M1-C | Conquest (7.3) | M | `Core/Ai/AiExpand.cs`, `Tests/.../AiExpandTests.cs` | M0-1 |
| M1-D | Encounters (7.4) | M | `Core/Ai/AiAttack.cs`, `Tests/.../AiAttackTests.cs` | M0-1 |
| M1-E | Home and steering (7.5, 7.6) | S | `Core/Ai/AiHome.cs`, `Core/Ai/AiSteering.cs`, `Tests/.../AiHomeTests.cs`, `AiSteeringTests.cs` | M0-1 |
| M1-F | Debug overlay: with `-aidebug`, draw for each bot its intent, its target, its plan and its perception disc. Runtime EditMode test for the sense radius and the camera (7.1). | S | `Runtime/Debug/AiDebugOverlay.cs` (new), `Tests/EditMode/Runtime/AiSenseRadiusTests.cs` | M0-3 |
| M1-G | Controller and arbiter (4.2, 4.3, 7.7), scenario tests, test of section 8 | M | `Core/Ai/AiController.cs`, `Tests/.../AiControllerTests.cs` | M1-A to M1-E |
| M1-H | Tuning and gate 9.2: run the bench, tune `AiTraits` values and module constants, write the gate tests, switch `BotFactory.DefaultBrain` to V2, build, probe, refresh `Build/Play`, write the as-built section in `docs/CONTRACT.md` | L | `Tests/.../AiGateTests.cs`, constants in `Core/Ai/*`, `BotFactory.DefaultBrain`, `docs/CONTRACT.md` (new section), `docs/ai/M1_AS_BUILT.md` | M1-G, M0-2, M1-F |

Paths are relative to `Assets/Scripts/` for code and `Assets/` for tests.

### 11.2 Dependency graph and waves

```
Wave 0   M0-1
            |
Wave 1   M0-2   M0-3   M1-A   M1-B   M1-C   M1-D   M1-E        (7 tasks in parallel)
                  |      \      \      |      /      /
Wave 2          M1-F            M1-G                           (2 tasks in parallel)
                  \              /
Wave 3              M1-H                                       (1 task, then the designer's playtest)
```

Why wave 1 is safe in parallel: every task owns different files, and every module is a set of pure functions over the
types frozen by M0-1. The modules do not call each other, except through `AiPercept` fields:

- M1-B, M1-C, M1-D and M1-E read `AiPercept`. Their unit tests build an `AiPercept` by hand, so they do not need M1-A.
- Only M1-G calls all the modules.

Unity lock: wave 1 tasks need Unity only for a final compile check. They run the dotnet loop while iterating and take
the lock once at the end. M0-3 and M1-F are the only ones that need the Unity editor for real.

### 11.3 Lean variant (fewer agents)

When agent budget is short, the same work fits in three sequential agents with no parallelism:

1. **Agent 1:** M0-1, M1-A, M1-B, M1-E (types, perception, safety, home, steering).
2. **Agent 2:** M1-C, M1-D, M1-G (conquest, encounters, controller). A bot plays at the end of this step.
3. **Agent 3:** M0-2, M0-3, M1-H (bench, wiring, tuning, gate, build). M1-F is dropped or postponed.

### 11.4 Required unit tests per module

| Task | Tests (names start with `Ai_`) |
|---|---|
| M0-1 | presets match table 6.1; derived values match 6.2; `Preset` returns a new instance each time |
| M1-A | enemy head at 15.9 u is visible, at 16.1 u it is not; enemy whose head is out of range but whose trail is in range is visible; `DistToMyTrail` ignores the last `HeadGrace` of the trail; `TimeToMyTrail` is +inf when home; `Cuttable` is false for a shielded enemy and for an already cut exit; `Sense` does not allocate; `Sense` does not change `StateHash` |
| M1-B | each trigger of 7.2 alone makes `MustReturn` true; none of them gives false; higher `Caution` returns earlier in the same situation; a shield longer than the way home disables the race trigger; `SafeToStart` rejects a loop next to an enemy and accepts the same loop when the enemy is far |
| M1-C | on a start disc in empty space a plan is found and its waypoints are outside own land and inside the arena; a loop toward an enemy head scores lower than the same loop away from it; no plan is returned when less than the minimum loop time is left; the guardian's mean distance from its anchor is smaller than the conqueror's over 200 draws; no allocation; on a country polygon no waypoint is outside the arena |
| M1-D | a sample that is lethal by hand computation is reported lethal, a non lethal one is not; no strike on an enemy that is home, shielded, or already cut; the same strike has a higher desire against the human; `ZeroExposure` is true only when the path stays on own land; a strike beyond `MaxTrailLength` is rejected; table of 7.4 holds with `exitBias = 1` |
| M1-E | the patrol target is always own land; `patrolSign` flips in a dead end; the steering heading equals the direct angle in open space; the probe point is never outside the arena near a rim, square and polygon |
| M1-G | intent sequence on an empty arena is `Roam`, `Expand`, `Return`, `Patrol`, and the bot captures; a threat inside the margin switches to `Return` after `ReactionDelay` and not before; an own spark switches to `Return`; an attack is dropped when the victim gets home; decisions happen 10 times per second at 30, 60 and 144 Hz; same seed twice gives the same headings; a new round resets the controller; test of section 8 |

---

## 12. Later milestones

### 12.1 M2 Smarter encounters

Each item is one task that touches one module, so they can run in parallel after a short planning step. The gate is the
M1 gate plus the acceptance line of each item.

| Id | Item | Module | Acceptance |
|---|---|---|---|
| M2-1 | **Loop shapes.** Add the Strip (shallow and long, hugging the border: the guardian's loop), the Lobe (deep and narrow: the conqueror's loop) and an arc variant with 4 to 6 waypoints. Shape weights come from the traits. | `AiExpand` | each archetype uses at least 2 shapes; the guardian's mean depth drops, its captures do not |
| M2-2 | **Threat direction.** `TimeToMyTrail` ignores enemies moving away (closing speed <= 0), and counts an enemy's turn time. Fewer useless retreats. | `AiSenses`, `AiSafety` | share of returns followed by no enemy approach within 2 s drops by half; deaths do not rise |
| M2-3 | **Guard behaviour.** At home, a guardian moves toward the border side where an enemy is visible, and intercepts intruders whose trail crosses its land with priority. | `AiHome`, `AiAttack` | intruder trails crossing a guardian's land are cut in more than 60 % of cases |
| M2-4 | **Counter attack and blocking.** When threatened by an enemy that is itself exposed, compare "run home" with "cut it first" and pick by `Aggression`. Add the blocking strike: aim between the victim and its home point. | `AiAttack`, arbiter | hunters win more races than they lose; no rise in hunter deaths above 20 % |
| M2-5 | **Short memory.** An enemy seen in the last 1.5 s is remembered at its last position and counted as a threat with growing uncertainty. | `AiSenses`, `AiPercept` (new fields) | bots are cut less often by an enemy that just left their disc |
| M2-6 | **Round phases.** Opening (first 15 s): no attacks below the lethal value, larger loops. End (last 20 s): the leader stops taking risks, the others raise `Ambition` and `Aggression`. | arbiter, `AiTraits` (phase modifiers) | the leader at t = 70 s wins more often than in M1; trailing bots capture more in the last 20 s |
| M2-7 | **Biome play.** Fire: a kill is worth more with a big victim, and a big bot keeps a wider margin. Electric: after a speed boost, chain a deeper loop or a second strike. Liquid: while shielded, go deep into enemy land. | `AiAttack`, `AiExpand`, `AiSafety` | per biome bench: the bots' kill reward usage is above the M1 figure |
| M2-8 | **Ring and lasso.** Take the ring when it is safe and close, curl a pocket when charged. Only matters when the lasso option is on. | new `AiLasso` | with lasso on, pockets are made in more than 30 % of rounds |

### 12.2 M3 Life

| Id | Item | Acceptance |
|---|---|---|
| M3-1 | **Mood.** Two running values, confidence and fear, moved by events (near miss, kill, loop lost, land stolen), which shift `Ambition`, `Caution` and `Aggression` for a few seconds. | the same bot behaves measurably differently in the 5 s after a near miss |
| M3-2 | **Grudge.** A bot remembers who cut it or stole its land and multiplies its attack desire against that player for 20 s. | revenge strikes exist in the bench and are visible in the debug overlay |
| M3-3 | **Human-like steering.** Replace the per decision aim noise by gestures: hold a heading, correct in steps, overshoot a little. | trajectories pass a designer review on screenshots; gate metrics unchanged |
| M3-4 | **Mistakes.** Rare errors scaled by `1 - Skill`: staying out one beat too long, misjudging a race. | lower `Skill` gives measurably more deaths and fewer kills |
| M3-5 | **Generated personalities.** Each bot draws its five knobs around its archetype, with a matching name. | two bots of the same archetype differ in the bench statistics |
| M3-6 | **Difficulty.** One scalar per level maps to `Skill`, `HumanFocus` and the line-up. It follows the Europe progression: later countries are harder. | human proxy win rate goes down monotonically over 4 difficulty steps |
| M3-7 | **Leader focus.** Attack desire is raised against the current leader. | the leader at mid round is attacked more than the others |

### 12.3 M4 Cleanup

- Move the rule tests that use the legacy bot to `BotFactory` or to scripted controllers, then delete `Core/Bots/` and
  `BotTests.cs`. Needs the designer's agreement: some of those tests assert seeded outcomes.
- Rewrite contract sections 5.7 and 9 from the as-built reports.
- Measure the tick cost on a real Android device with the `perfslope` step.

---

## 13. Rules for the agents

1. Read sections 1 to 5 and the section of your task. Read the source files named in section 2 that your task touches.
2. Work in the dotnet loop. Take the Unity lock only when you need Unity.
3. Edit only the files your task owns. If you need a change elsewhere, write it in your report as a request.
4. Do not weaken a test to make it pass. If a target of this document looks wrong, say so in your report.
5. Never write to `Build/Windows`, `Build/Play` or `Build/Android` unless you are the gate task.
6. Finish with the full Core test run, not only your filter. Report the counts you read in the output.
7. Write your report to `docs/ai/<task-id>.json`:

```json
{
  "task": "M1-C",
  "status": "done | partial | blocked",
  "files": ["Assets/Scripts/Core/Ai/AiExpand.cs"],
  "tests": { "added": 6, "passed": 6, "failed": 0, "full_core_run": "passed 812, failed 1 (known: WaveC_Composites_KeepTheirFetchCount)" },
  "constants_changed": [{ "name": "RiskWeight", "from": "L(0.5, 2.5)", "to": "L(0.5, 2.0)", "why": "..." }],
  "deviations_from_spec": [],
  "requests_to_other_tasks": [],
  "not_verified": []
}
```

Known failing test before this work: `WaveC_Composites_KeepTheirFetchCount` (rendering, unrelated).

---

## 14. Open decisions for the designer

These have a default in this document. The work can start without an answer.

| Question | Default taken |
|---|---|
| Perception radius: half the screen height (16 u), half its width (9 u) or half its diagonal (18.4 u)? | 16 u |
| Should a bot also know its own land outside its perception disc (where home is)? | yes, a player always knows where its colour is |
| Line-up of a real round: always Conqueror, Guardian, Hunter, or drawn per level? | fixed in M1, per level in M3-6 |
| How much harder against the human? | `HumanFocus` 1.2 to 1.6, tuned at the M1 gate with the human proxy |
| Delete the legacy bot at the end? | kept until M4, deleted only with agreement |
