# Painter IO - Build Contract v2.1

Status: v2.1, 2026-11-27 (v2.1 adds the designer's rule v1.8: one single domain in every round type (section 32); v2.0 adds the designer's rule change v1.7: countries first, 15 min cap, conquest goal (section 31); v1.0 amended after the contract review into v1.1, v1.2 restores Shader Graph (section 22), v1.3 records the wave A as-built amendments (section 23), v1.4 is the user's La Revanche rule change (section 24), v1.5 adds the three biomes (section 25), v1.6 records the wave C as-built amendments and folds the accepted wave B readings (section 26), v1.7 adds the biome traits and the wave D feedback (sections 27, 28), v1.8 adds the designer's severed territory rule, rule v1.5 (section 29), v1.9 adds the designer's single domain rule and the kill inheritance bridge, rule v1.6 (section 30)). This file is
the single source of truth for every agent that builds Painter IO.
The game design brief is `docs/REGLES_DU_JEU.txt` (French, v0.1). The visual reference is `docs/reference_gouttes.png`.

Precedence when two sources disagree:
1. `docs/REGLES_DU_JEU.txt` for any gameplay rule (what must happen).
2. This contract for how it is implemented (algorithms, APIs, files, constants).
3. If this contract contradicts the brief, the brief wins and the agent reports the contradiction in its report under `contract_issues`.
   Exception: interpretations that this contract states explicitly as "the contract's reading" (for example R8) are decided;
   an agent that disagrees reports it and does not change the behaviour without the user's approval.

Writing rules for everything produced (code, comments, docs, reports, UI text):
- Code, comments, docs and reports in English. Player-facing strings in French by default with an English table (section 15.6).
- Never use the em dash character (U+2014) anywhere. Use "-", a colon or parentheses.
- Avoid `async` methods. If one is unavoidable, its name starts with a lowercase `a` (example: `aLoadSave`), never an `Async` suffix.
- Do not edit a file you do not own (section 20) unless this contract says so. Need a change elsewhere: report it under `needs`.
- Never change a public signature defined here. Adding a member is allowed and must be listed under `api_additions` in the report.

---

## 0. Product summary

Painter IO is a mobile-first (portrait) arena territory game closely modeled on paper.io 2, with two signature rules from the
brief: La Revanche (a cut sends a chasing "spark" up the victim's trail) and Le Lasso (a one-charge bonus that lets a player
close a pocket on their own trail). One human plus three bots, 90 second rounds, one life.

Visual identity (from the user, normative): everything is glossy liquid paint on a deep navy table.
- A player's territory is one single puddle (a drop that stretches).
- Leaving home: a small pearl (the pawn head) detaches from the edge of the puddle and pulls a thin thread of liquid behind it.
- Coming home: the pearl merges back into the puddle and the enclosed surface fills in one single motion.
- La Revanche is surface tension: when a rival pinches the thread, it retracts from the pinch point toward the pearl, leaving
  a chain of droplets behind it. The retraction front IS the spark of the brief.
- Relief: ink, pearls and the retraction front have real-looking volume (height field, specular highlights, soft shadows),
  rendered by an orthographic top-down camera.

Targets: Windows standalone (portrait window 540x960, resizable) and Android APK (portrait, IL2CPP ARM64).
Engine: Unity 6000.3.23f1 (Unity 6.3 LTS), URP 17.3, Shader Graph 17.3, Input System 1.20, uGUI. Shader Graph is the user's
chosen tool for the visible surface shaders; three GPU-data shaders are hand-written HLSL (section 12.1). Project root:
`Brainstorming/games/painter_io`.

---

## 1. Project layout, assemblies, namespaces

```
painter_io/
  Assets/
    Scripts/Core/       PainterIO.Core.asmdef   (noEngineReferences: true; pure C#, no UnityEngine)
      Math/             Vec2d.cs Geo.cs Rng.cs
      World/            Arena.cs Tuning.cs SimConfig.cs
      Grid/             OwnerGrid.cs CellMask.cs GridRaster.cs CaptureSolver.cs GridQueries.cs
      Trail/            Trail.cs LoopErase.cs LassoGeometry.cs
      Sim/              Simulation.cs PlayerState.cs SimEvents.cs RoundResult.cs Ring.cs IController.cs
                        SimView.cs SimSetup.cs EventResolver.cs RingSpawner.cs
      Controllers/      ScriptedControllers.cs
      Bots/             BotController.cs BotPersonality.cs BotSenses.cs
    Scripts/Runtime/    PainterIO.Runtime.asmdef (refs Core, Input System, uGUI, URP)
      Game/             GameDirector.cs (also HumanOutcome) GameSession.cs SimRunner.cs SaveData.cs Strings.cs
      Input/            SteeringInput.cs
      View/             CameraRig.cs Palette.cs LiquidLayers.cs
      Render/           LiquidRenderer.cs TerritoryField.cs ActorFieldCamera.cs LiquidSurface.cs QualityTier.cs
      Actors/           ActorViews.cs ThreadView.cs PearlView.cs RetractionView.cs CutFlash.cs RingView.cs
                        ChargeRing.cs HomeArrow.cs SparkEdgeIndicator.cs RingIndicator.cs SplashView.cs
      UI/               UiRoot.cs UiKit.cs Hud.cs MenuScreen.cs ResultsScreen.cs TutorialOverlay.cs SettingsPanel.cs
                        PausePanel.cs SafeArea.cs
      Audio/            Sfx.cs SfxSynth.cs Haptics.cs
      Probe/            PlayerProbe.cs
    Scripts/Editor/     PainterIO.Editor.asmdef: Builder.cs ShaderCheck.cs
    Resources/Shaders/  every shader of the game: LiquidComposite, Bead, Overlay as *.shadergraph (thin graphs, logic in
                        *.hlsl Custom Functions); FieldBlob, FieldStroke, TerritoryBlur as hand-written *.shader; *.hlsl includes
    Resources/Fonts/    the UI font (OFL) + its license text
    Scenes/Main.unity   generated by Builder (one GameObject "Game" with GameDirector)
    Tests/EditMode/     PainterIO.Tests.EditMode.asmdef; Core/ (pure NUnit, no UnityEngine), Runtime/
    Tests/PlayMode/     PainterIO.Tests.PlayMode.asmdef
  tools/
    unity.ps1           exclusive Unity lock wrapper (copied from games/out_of_sight, proven)
    verify.ps1          full verification (section 18.4)
    CoreTests/          dotnet test project compiling Core + Tests/EditMode/Core outside Unity (section 2.2)
  docs/
    CONTRACT.md REGLES_DU_JEU.txt reference_gouttes.png
    playtest_7_7.md     device playtest record (section 18.5; template by B6, filled by the user)
    waveA/ waveB/ waveC/   one JSON report per agent
```

Namespaces: `PainterIO.Core` (all Core files, one flat namespace), `PainterIO.Runtime`, `PainterIO.Editor`,
`PainterIO.Tests`. The asmdefs already exist; do not rename them.

---

## 2. Tooling (all agents)

### 2.1 Unity
- Unity cannot open the project twice. EVERY Unity invocation goes through the lock wrapper, from PowerShell
  (Git Bash can hang for hours on this machine, do not use it for Unity):
  `pwsh -NoProfile -File tools/unity.ps1 -Agent <yourname> -UnityArgs "<args>"` run from the project root.
  No argument inside `-UnityArgs` may contain a space.
- Run EditMode tests: `-UnityArgs "test . --mode EditMode --report-format junit --output TestResults/<you>_edit.xml --timeout 1800"`.
  Optional `--filter <regex>`.
- Compile check + scene/setup (after wave B0 exists): `-UnityArgs "run . --timeout 1800 -- -executeMethod PainterIO.Editor.Builder.SetupAndCompile -logFile Logs/<you>_setup.log"`.
- Read the JUnit report, never the exit code alone: a run with zero tests exits 0. Exit 8 means red tests; any other
  non-zero means the run did not complete (read the log).
- Long Unity commands: run them in the background and poll the output file. Expect to wait for the lock behind other agents.

### 2.2 dotnet fast loop for Core (no Unity lock needed)
`tools/CoreTests/` holds two projects:
- `PainterIO.Core.csproj`: `netstandard2.1`, `LangVersion 9.0`, `<Compile Include="../../Assets/Scripts/Core/**/*.cs" />`.
- `PainterIO.CoreTests.csproj`: `net9.0`, references the Core project and NUnit 3.x (`NUnit`, `NUnit3TestAdapter`,
  `Microsoft.NET.Test.Sdk`), `<Compile Include="../../Assets/Tests/EditMode/Core/**/*.cs" />`.
- Run: `dotnet test tools/CoreTests/PainterIO.CoreTests.csproj -v q`.
Core code must compile under C# 9 / .NET Standard 2.1 (Unity's level): no `record struct`, no file-scoped namespaces,
no global usings, no `init`-only setters, no `System.Numerics` dependence beyond what netstandard2.1 offers.
Tests under `Tests/EditMode/Core/` use only NUnit + PainterIO.Core (they also run inside Unity). Use NUnit features that
exist in Unity's NUnit 3.5 (Assert.That, Assert.AreEqual, TestCase, Test, SetUp). No `Assert.Multiple`.

### 2.3 Reports
Every agent writes `docs/wave<X>/<package>.json` and returns the same object:
`{ "package", "summary", "files": [...], "api_additions": [...], "contract_issues": [...], "tests": {"added": n, "passing": n, "failing": [...]}, "open_issues": [...], "needs": [...] }`.

---

## 3. Units, coordinates, constants

- Simulation space: 2D, double precision, x right, y up, unit = 1 world unit ("u"). Time in seconds (double).
- Unity world mapping: sim (x, y) maps to Unity `new Vector3((float)x, (float)y, 0f)`. The play plane is Unity XY.
  The main camera looks along +Z from z = -50, orthographic, no rotation, so screen up = +y.
- Angles: radians in Core, 0 = +x, counter-clockwise positive.

### 3.1 `Tuning` (Core/World/Tuning.cs) - all gameplay constants, `public const double` (or int/bool)

| Name | Value | Meaning |
|---|---|---|
| ArenaHalfSize | 32.0 | arena is a rounded square [-32, 32]^2 |
| ArenaCornerRadius | 10.0 | corner radius of the rounded square |
| ArenaMargin | 0.45 | head center stays inside the shape inset by this (= HeadRadius); see R1 for the neutral rim band |
| CellSize | 0.125 | ownership grid cell; grid is 512 x 512 |
| PlayerCount | 4 | one human + three bots |
| StartDiscRadius | 3.5 | starting territory disc radius |
| StartDiscOffset | 16.0 | disc centers at (-16,-16), (16,-16), (16,16), (-16,16) for player index 0..3 |
| PawnSpeed | 6.0 | u/s, constant |
| TurnRateDeg | 540.0 | max heading change per second; 0 means instant turns (tests) |
| HeadRadius | 0.45 | pearl radius (collision for cuts and pickups) |
| TrailHalfWidth | 0.18 | trail collision half width; cut contact distance = HeadRadius + TrailHalfWidth = 0.63 |
| HeadGrace | 1.0 | the last 1.0 u of a trail (arc length) behind its own head is not exposed |
| SparkSpeedFactor | 1.8 | spark speed = 1.8 x PawnSpeed, constant |
| RoundDuration | 90.0 | seconds |
| LassoEnabled | true | ring spawns enabled in Core (tests). The runtime default is OFF (SaveData.LassoOn, section 15.2) |
| LassoFirstSpawn | 15.0 | first ring at t = 15 s |
| LassoRespawn | 15.0 | next ring 15 s after each pickup |
| RingRadius | 0.6 | ring pickup radius; pickup distance = HeadRadius + RingRadius |
| RingMinHeadDistance | 4.0 | spawn point at least this far from every live head |
| RingClearance | 1.0 | all arena cells within this radius of the spawn point must be neutral |
| LassoMinArc | 1.0 | a crossed segment must end at arc length <= L(crossing instant) - LassoMinArc |
| LassoMinArea | 0.75 | loop interior area required to form a pocket: (cells whose center has non-zero winding) x CellSize^2, in u^2 |
| BorderHoldAngleDeg | 10.0 | pushing within this angle of the outward normal holds the head still |
| TickRate | 60 | simulation ticks per second (supported range 30..240) |
| EventEpsilonSeconds | 1e-7 | events closer than this are simultaneous |
| MaxEventsPerTick | 64 | safety cap of the event loop (groups per tick) |
| BotCount | 3 | |

Derived: grid Size = round(2 * ArenaHalfSize / CellSize) = 512. HeadGrace must exceed PawnSpeed / TickRate for every
supported tick rate (1.0 > 0.2): the segment a head draws during one tick is never exposed during that tick. The Simulation
constructor throws ArgumentException if HeadGrace <= PawnSpeed * Dt.
The values 90 s, 1.8 and 15 s are initial settings the brief wants adjustable: at runtime they come from SaveData test
settings and command-line overrides (sections 11.2, 15.2); Tuning keeps the defaults.

### 3.2 `SimConfig` (Core/World/SimConfig.cs)
A mutable class with one public field per Tuning entry (same names, initialized from Tuning) plus `public ulong Seed = 1;`
and `public int PlayerCount = Tuning.PlayerCount;`. Derived read-only properties: `double Dt => 1.0 / TickRate`,
`double SparkSpeed => SparkSpeedFactor * PawnSpeed`, `double ContactRadius => HeadRadius + TrailHalfWidth`,
`double PickupRadius => HeadRadius + RingRadius`. Method `SimConfig Clone()`.

---

## 4. Gameplay rules (normative, ids are cited by tests)

R1 Arena. Rounded square of half size 32 and corner radius 10. Cells whose center lies outside the shape are VOID: never
owned, never walls, always "outside" for enclosure. The border neither kills nor closes territory. Decided consequence: a
head center never comes closer than ArenaMargin to the rim, so the outer band of cells (about 3 cells wide) can never be a
trail cell, is always reachable from outside and stays neutral forever (puddles never touch the rim). R20 still counts these
cells, so 100 % is unreachable by design.

R2 Start. Player i starts at the center of its disc (StartDiscOffset corner), heading toward the arena center, home, with
its disc cells owned (cells whose center is within StartDiscRadius). All four discs have the same cell count (symmetric).

R3 Motion. Each tick, a player's heading turns toward its desired heading by at most TurnRateDeg * dt (shortest way;
instant if TurnRateDeg = 0), then the head moves PawnSpeed * dt along the heading, subject to R4. A controller that
returns null keeps the previous desired heading (finger lifted keeps the course).

R4 Border. If the step would leave the inset shape (signed distance > -ArenaMargin), the head slides: the displacement
is projected onto the border tangent and rescaled to the full step length, then clamped inside. If the angle between
the desired displacement and the outward normal is below BorderHoldAngleDeg, the head does not move this tick (held
against the border until the heading changes). Within a tick, motion is the straight segment p0 -> p1 that results.

R5 Home and exit. Each player has a current cell `PlayerState.Cell`: the cell the simulation considers its head center to be
in. It is set at spawn (and by DebugSetTrail) from TryCellOf(Pos), then changed ONLY by the in-tick head traversal of
section 6 (a head center lying exactly on a cell edge belongs to the cell it is moving into), never recomputed from a
position. A player is home while its current cell is owned by itself. When its current cell becomes a cell not owned by
itself, an exit starts: the trail begins exactly at the crossing point (on the cell edge; at the head when the cause is a
grid change, R9). While home, nothing is vulnerable. Crossing other colors is allowed.

R6 Trail. The trail is the exact path of the head since the exit, as a polyline with cumulative arc length. Its end is
always the current head position at the end of each tick. Self crossing is allowed and harmless (except R16 lasso).

R7 Return and capture. When a trailing player's current cell becomes a cell owned by itself, the exit closes at the crossing
point: capture is computed (section 7), applied, the trail is erased, the spark (if any) is extinguished, the pending pocket
is validated into the capture, and the player is home again. A return that encloses nothing still ends safely.

R8 Enclosure semantics. Inside = cells not reachable from outside the map when walls are (own territory + trail outline).
Captured = cells newly enclosed compared with walls = own territory only. A back-and-forth line captures nothing.
An excursion along the border cannot paint the map (outside the arena is reachable). Self loops of the trail are NOT
captured by an ordinary return (the outline is loop-erased, section 7); only a lasso pocket captures a self loop.
This is the contract's reading of brief 3.2/3.3 together with 5.2/5.5/7.6: a region enclosed by the trail alone (a self
loop) is captured only through a lasso pocket, otherwise the lasso bonus would add nothing. Intended consequence: an
uncharged big loop closed by crossing the player's own trail, even 1 u outside home, then a return, captures only the
loop-erased outline region. Auditors must not change this without the user's approval.

R9 Territory loss. Captured cells change owner, including cells owned by a rival. If a rival takes the current cell of a
player that is home (including a player that returned at the same instant, R18), that player immediately starts an exit at
its head position (the trail starts there; the player must reach its CURRENT color to return). A player whose owned cell
count drops to 0 is eliminated (cause TerritoryLost).

R10 Contacts. Heads pass through heads with no effect. A cut happens when an enemy head (circle of HeadRadius) touches
the exposed part of a trail (capsule of TrailHalfWidth): distance(enemy head center, trail centerline point) <=
ContactRadius, where the touched point has arc length s <= L_victim(t) - HeadGrace. Trails crossing trails do nothing.
A player never cuts its own trail. An attacker cuts whether it is home or trailing.

R11 Spark spawn. The first cut of an exit spawns the spark exactly at s_cut, the value returned by Trail.FirstContact (5.4):
at the earliest contact instant, for each trail segment in contact, the closest EXPOSED centerline point to the attacker's
head center; s_cut is the largest arc length among them. At a tangential first contact this is the touched point; when the
contact starts because a point leaves the HeadGrace zone it is L - HeadGrace; if several passes of the same trail are
touched at the same instant it is the most recent pass. If several attackers cut the same trail at the same instant, take
the largest s (closest to the head along the trail); Spark.Attacker and the Cut event's Other are the attacker that gave it
(ties on s: lowest player index), and only that attacker gets CutsMade++. A trail carries at most one spark per exit;
later cuts change nothing (no move, no speed up). The attacker keeps playing.

R12 Spark motion. s_spark(t) = s_cut + SparkSpeed * (t - t_cut), along the trail's own arc length (it follows the real
path, crossings in passing order, loops included, no shortcut), always evaluated in this closed form (never accumulated).
It keeps going if the attacker dies.

R13 Race (amended by the user in v1.4, section 24). If the victim returns (R7) at time t_r and the spark would reach the head at
t_c (s_spark(t_c) = L(t_c)): t_r < t_c + EventEpsilonSeconds means SAVED (return wins ties): the victim survives, the exit closes,
the trail is erased, the spark is extinguished, BUT THE RETURN CAPTURES NOTHING (no ordinary capture, and the pending pocket of
that exit is erased, not validated); otherwise the victim is eliminated at t_c (cause Spark): exit cancelled, pocket erased, all
its territory becomes neutral. The attacker gets nothing automatically. Section 6
implements this with an epsilon shift of the catch candidate, valid across tick boundaries.

R14 Cut at closure. A cut at the exact instant a trail closes has no effect (returns resolve first).

R15 Ring. The ring spawns on neutral ground at t = LassoFirstSpawn (if LassoEnabled), then LassoRespawn seconds after
each pickup; at most one ring exists. A live player without charge whose head is within PickupRadius picks it up,
provided it is the only eligible player in contact at that instant; otherwise the ring stays until exactly one eligible
player is in contact (another player leaving, dying, or a charged player in contact spending its charge all count).
A charged player leaves the ring in place. A charge persists across exits; capacity 1.

R16 Lasso. While trailing and charged, the first proper crossing (Geo.ProperIntersect) of the head path with an OLDER
segment of its own trail (segment end arc <= L - LassoMinArc) whose loop is a valid pocket (LassoGeometry.IsValidPocket)
consumes the charge and adds the loop polygon to the pending pocket (hatched in the player's color). "First" means the first
VALID crossing: crossings whose loop is invalid are skipped, even later in the same tick. Tangency, touching the segment just
drawn, and a superposed U-turn do not count. Without charge, the same crossing does nothing visible and creates no pocket.

R17 Pocket. A pocket is pending: it does not count for score, owners keep their cells, crossing it gives no safety (Home is
decided by the current cell's owner only, R5), the whole trail including the loop and the pocket contour stays exposed.
Returning home captures pocket + ordinary capture as one set union. Elimination erases the pocket. A lasso during a chase
does not touch the spark (Spark.SCut, TimeCut and S(t) unchanged).

R18 Simultaneous returns. Returns at the same instant are each computed against the grid as it was just before that
instant. A cell claimed by two or more of them keeps its previous owner (or stays neutral). Each player gets the rest.

R19 Round end. Last survivor wins immediately (only if the round started with >= 2 players). If all remaining players
are eliminated at the same instant, they share first place. At t = RoundDuration, events of that instant resolve first,
then the alive player(s) with the largest owned cell count win (exact tie shares first place). Pending pockets never
count. Ranking: alive players by cell count descending (ties share a rank), then eliminated players by elimination time
descending (same instant shares a rank). Shared ranks use standard competition ranking (1, 1, 3). The rank of an
eliminated player is final as soon as the Step that eliminated it returns: 1 + the number of players alive after its event
group (players eliminated in the same group share it; if no player remains alive they share rank 1).
FinalCells of an eliminated player = its owned cell count at the start of the event group that eliminated it (a
TerritoryLost elimination keeps the area held just before the capture that took the last piece).

R20 Area. Area percent = owned cells / arena (non-void) cells * 100.

---

## 5. Core API (signatures are binding)

All types in namespace `PainterIO.Core`. `IReadOnlyList<T>` from System.Collections.Generic.

### 5.1 Math (Core/Math)
```csharp
public readonly struct Vec2d : IEquatable<Vec2d> {
  public readonly double X, Y;
  public Vec2d(double x, double y);
  public static readonly Vec2d Zero;
  public static Vec2d operator +(Vec2d a, Vec2d b); operator -(a,b); operator -(a); operator *(Vec2d a, double k);
  public static Vec2d operator *(double k, Vec2d a); public static Vec2d operator /(Vec2d a, double k);
  public double Length { get; } public double LengthSq { get; }
  public Vec2d Normalized();               // Zero stays Zero
  public static double Dot(Vec2d a, Vec2d b); public static double Cross(Vec2d a, Vec2d b);
  public static double Distance(Vec2d a, Vec2d b);
  public static Vec2d Lerp(Vec2d a, Vec2d b, double t);
  public static Vec2d FromAngle(double radians); public double Angle();   // atan2(Y, X)
  public Vec2d Perp();                      // (-Y, X)
}
public static class Geo {
  public const double Tiny = 1e-12;
  public static double WrapAngle(double a);                                   // to (-pi, pi]
  public static double MoveTowardsAngle(double current, double target, double maxDelta); // maxDelta <= 0 => target
  public static double ClosestParamOnSegment(Vec2d p, Vec2d s0, Vec2d s1);    // clamped [0,1]
  public static double DistancePointSegment(Vec2d p, Vec2d s0, Vec2d s1);
  // Earliest u in [0,1] such that |a + u(b-a) - segment| <= r. If already within r at u=0 returns u=0.
  // Must handle |b - a| ~ 0 and motion parallel to the segment (no division by a near-zero determinant).
  public static bool SweepCircleSegment(Vec2d a, Vec2d b, double r, Vec2d s0, Vec2d s1, out double u, out double tSeg);
  // Crossing test used by Trail.SelfCrossings and LoopErase. True iff all of: the segments are not parallel
  // (|Cross(a1-a0, b1-b0)| > 1e-12 |a1-a0| |b1-b0|); ta in (0, 1] and tb in [0, 1) (half-open: an old vertex belongs to the
  // segment that starts there, and a crossing exactly at the moving segment's end counts); and a0 is strictly off the line
  // of b (|Cross(b1-b0, a0-b0)| > 1e-12 |b1-b0|), so a head that starts its tick on an old segment does not count it twice.
  // Touching without reaching the line, collinear overlap and a0 on the line return false.
  public static bool ProperIntersect(Vec2d a0, Vec2d a1, Vec2d b0, Vec2d b1, out double ta, out double tb);
  public static double SignedArea(IReadOnlyList<Vec2d> poly);                 // shoelace, CCW positive
  public static int WindingNumber(Vec2d p, IReadOnlyList<Vec2d> poly);         // nonzero rule helper
}
public sealed class Rng {            // xorshift64*, deterministic across platforms
  public Rng(ulong seed);            // seed 0 is remapped to a fixed non-zero constant
  public ulong NextULong(); public double NextDouble();   // [0,1)
  public int NextInt(int maxExclusive); public double Range(double a, double b);
}
```

### 5.2 World (Core/World)
```csharp
public sealed class Arena {
  public Arena(double halfSize, double cornerRadius, double margin);
  public double HalfSize { get; } public double CornerRadius { get; } public double Margin { get; }
  public double SignedDistance(Vec2d p);    // exact rounded-square SDF, < 0 inside the full shape
  public bool Contains(Vec2d p);            // SignedDistance(p) <= 0
  public Vec2d OutwardNormal(Vec2d p);      // gradient of the SDF (unit)
  public Vec2d ClampInside(Vec2d p);        // nearest point with SignedDistance <= -Margin
  // R4: returns p1 given p0 and the desired displacement d (|d| = PawnSpeed*dt).
  public Vec2d Step(Vec2d p0, Vec2d d, double holdAngleRad);
  public double ShapeArea { get; }          // analytic: (2h)^2 - (4 - pi) r^2
}
```

### 5.3 Grid (Core/Grid)
```csharp
public sealed class CellMask {             // bitset over Size*Size cells
  public CellMask(int size);
  public int Size { get; } public int Count { get; }       // number of set cells (maintained)
  public bool Get(int index); public void Set(int index); public void Unset(int index);
  public void Clear(); public void UnionWith(CellMask other);
  public int Version { get; }                              // increments on every mutation
  public void CopyIndices(List<int> output);               // ascending order
}
public sealed class OwnerGrid {
  public const byte Neutral = 0; public const byte Void = 255;   // players are 1..4 (player index + 1)
  public OwnerGrid(Arena arena, double cellSize);
  public int Size { get; } public double CellSize { get; } public double Origin { get; }   // Origin = -HalfSize
  public byte[] Cells { get; }             // index = j * Size + i; outsiders must treat it as read-only
  public int Version { get; }              // increments on every mutation
  public int ArenaCellCount { get; }
  public int CountOf(byte owner);          // maintained incrementally, O(1)
  public int Index(int i, int j);
  public bool TryCellOf(Vec2d p, out int i, out int j);    // false when outside the grid (floor convention)
  public byte OwnerAt(Vec2d p);            // Void outside the grid
  public Vec2d CellCenter(int i, int j);
  public void Set(int index, byte owner);  // ignores Void cells; maintains counts and Version
  public void FillDisc(Vec2d center, double radius, byte owner);   // cells whose center is within radius
  public void Neutralize(byte owner, List<int> changed);           // all cells of owner -> Neutral
}
public delegate bool CellVisitor(int i, int j, double uEnter);       // return false to stop
public struct CellEntry { public int Index; public double U; }       // a cell entered by a head at tick parameter U
public static class GridRaster {
  // Amanatides-Woo traversal of segment a->b, 4-connected, for walls (RasterPolyline) and bots. The first visited cell is
  // the one containing a + Tiny*(b-a), with uEnter = 0. Visits, in order, every cell whose entry parameter lies in (0, 1],
  // including a cell entered exactly at u = 1 (so the raster of a polyline does not depend on collinear subdivision). On an
  // exact corner tie (|tMaxX - tMaxY| <= 1e-12) it visits the x-neighbour, then the diagonal cell (3 cells in total).
  public static void TraverseSegment(OwnerGrid g, Vec2d a, Vec2d b, CellVisitor visitor);
  // Head traversal for the event engine (section 6). Starts in startCell (a lies inside it or within 1e-9 of it; negative
  // initial tMax values are clamped to 0). Clears output, then outputs (startCell, 0) and every next cell with its entry
  // parameter U, keeping entries with U in [0, uMax] INCLUSIVE at both ends (a head that starts exactly on an edge and moves
  // across it enters at U = 0). On a corner tie (|tMaxX - tMaxY| <= 1e-12) it steps diagonally in ONE entry, with no
  // intermediate cell.
  public static void TraverseFrom(OwnerGrid g, int startCell, Vec2d a, Vec2d b, double uMax, List<CellEntry> output);
  // Earliest uEnter > 0 of a cell visited by TraverseSegment whose owner satisfies pred. The start cell never counts.
  // Bots and tests only: the event engine never uses it.
  public static bool FirstEntry(OwnerGrid g, Vec2d a, Vec2d b, Func<byte, bool> pred, out double u);
  public static void RasterPolyline(OwnerGrid g, IReadOnlyList<Vec2d> points, CellMask output);   // supercover walls (TraverseSegment per segment)
  // Cells whose center has non-zero winding inside poly, plus the TraverseSegment cells of its boundary. Void excluded.
  // Scanline per cell row (edge crossings at the row's center y with the half-open rule y0 <= y < y1, sorted, winding
  // accumulated): O(rows x edges + cells). Never a per-cell WindingNumber loop.
  public static void RasterPolygon(OwnerGrid g, IReadOnlyList<Vec2d> poly, CellMask output);
  // Number of non-Void cells whose center has non-zero winding inside poly (boundary cells are not added). Same scanline.
  public static int CountInterior(OwnerGrid g, IReadOnlyList<Vec2d> poly);
}
public static class CaptureSolver {
  // Section 7. Pure: does not mutate g. Returns captured cell indices, ascending, excluding Void and cells
  // already owned by player. outline = loop-erased trail; pocket may be null.
  public static int[] Compute(OwnerGrid g, byte player, IReadOnlyList<Vec2d> outline, CellMask pocket);
}
public static class GridQueries {
  // Nearest cell owned by owner (Euclidean, from p to cell center) within maxRadius. Ring search outward, exact.
  public static bool NearestOwned(OwnerGrid g, byte owner, Vec2d p, double maxRadius, out Vec2d target, out double distance);
  public static bool IsNeutralDisc(OwnerGrid g, Vec2d center, double radius);   // all arena cells in disc neutral
}
```

### 5.4 Trail (Core/Trail)
```csharp
public struct SelfCrossing { public double U; public int Segment; public Vec2d Point; }
public sealed class Trail {
  public Trail();
  public int Count { get; }                          // points
  public IReadOnlyList<Vec2d> Points { get; }        // Points[0] = exit point
  public IReadOnlyList<double> Arc { get; }          // cumulative arc length, Arc[0] = 0
  public double Length { get; }                      // Arc[Count-1], 0 when Count <= 1
  public bool IsEmpty { get; }                       // Count == 0
  public int Version { get; }                        // increments on every mutation
  public void Clear();
  public void Start(Vec2d exitPoint);                // Clear then add the first point
  public void Append(Vec2d p);                       // ignores a point closer than 1e-9 to the last
  public Vec2d PointAt(double s);                    // clamped to [0, Length]
  public Vec2d DirectionAt(double s);                // unit tangent of the segment containing s
  public int SegmentIndexAt(double s);               // segment k spans [Arc[k], Arc[k+1]]
  // R10 contact search for ONE tick. The enemy head moves q(u) = a + u (b - a), u in [0, 1] (the full tick segment).
  // The owner's exposed limit is E(u) = Length + max(0, u - uOwnerStart) * growthPerUnitU - headGrace; exposed arcs are
  // [0, E(u)]. There is a contact at u iff distance(q(u), trail restricted to arcs [0, E(u)]) <= radius. Returns the
  // smallest such u in [uMin, 1] and sCut: for each segment in contact at u, that segment's closest EXPOSED point to q(u);
  // sCut = the largest arc among them (within radius + 1e-9). A first touch gives the touched point, a contact that starts
  // because a point leaves the grace zone gives E(u), superposed passes give the most recent pass.
  // Algorithm, per candidate segment k with arcs [s0, s1] (from the spatial hash over the capsule swept on [uMin, 1]; if
  // uMin < uOwnerStart < 1, split the range at uOwnerStart so E is affine on each part):
  //  (0) if distance(q(uMin), sub-segment [s0, min(s1, E(uMin))]) <= radius, the segment result is uMin;
  //  (1) (uG, sigma) = earliest contact of q with the whole segment on the range (Geo.SweepCircleSegment, handles |b-a| ~ 0
  //      and motion parallel to the segment); if s0 + sigma (s1 - s0) <= E(uG), the segment result is uG;
  //  (2) otherwise solve |q(u) - F(u)| = radius with F(u) = the point at arc E(u) (affine in u while E(u) is in [s0, s1]),
  //      a quadratic, for the smallest u >= uMin with E(u) in [s0, s1].
  // The segment result is the min of (0), (1), (2); this is exact because the feasible set is convex in (u, arc).
  // The overall result is the min over segments.
  public bool FirstContact(Vec2d a, Vec2d b, double radius, double uMin, double uOwnerStart,
                           double growthPerUnitU, double headGrace, out double u, out double sCut);
  // R16 crossing search for ONE tick: the owner's head moves a->b (the full tick segment, a = p0 at tick start; u in [0, 1]).
  // Returns ALL crossings Geo.ProperIntersect(a, b, Points[k], Points[k+1]) with u > uMin, against stored segments k with
  // Arc[k+1] <= maxSegmentEndArc, sorted by U ascending, then Segment descending (deterministic, most recent pass first).
  // Clears output first; returns the count.
  public int SelfCrossings(Vec2d a, Vec2d b, double uMin, double maxSegmentEndArc, List<SelfCrossing> output);
  // Closed loop polygon: point, Points[segmentIndex+1 .. Count-1], then head (= point at a crossing). Called BEFORE the
  // crossing point is appended to the trail (so the point is not duplicated).
  public List<Vec2d> LoopPolygon(int segmentIndex, Vec2d point, Vec2d head);
}
public static class LoopErase {
  // Removes every self loop. Walk the polyline; for each new segment, among the kept non-adjacent segments it properly
  // crosses (Geo.ProperIntersect), take the one with the SMALLEST index j; truncate the kept path after segment j, append
  // the crossing point, and continue with the rest of the new segment (no re-test needed: by minimality of j the rest of the
  // segment crosses no kept segment of index < j). Result is a simple polyline from first to last point.
  public static List<Vec2d> Erase(IReadOnlyList<Vec2d> points);
}
public static class LassoGeometry {
  // GridRaster.CountInterior(g, loop) * g.CellSize^2 >= minArea (non-zero winding, so lobes of opposite orientation never
  // cancel and the test agrees with the pocket raster).
  public static bool IsValidPocket(OwnerGrid g, IReadOnlyList<Vec2d> loop, double minArea);
}
```
Performance: FirstContact and SelfCrossings must use a uniform spatial hash of segments (bucket 2 u) maintained by Append,
so a typical query costs <= 5 us and a 2000-point trail stays well under 0.1 ms. LoopErase may be O(n log n) or O(n * k)
with the same hash.

### 5.5 Simulation (Core/Sim)
```csharp
public interface IController {
  // Called once per tick, before motion, for alive players only. Return the desired heading (radians) or null to keep it.
  double? DesiredHeading(SimView view, int playerIndex);
}
public enum EliminationCause { None = 0, Spark = 1, TerritoryLost = 2 }
public enum RoundEndReason { None = 0, LastSurvivor = 1, AllEliminated = 2, TimeUp = 3 }
public enum SimEventType { Exit, Return, Cut, SparkCaught, Eliminated, TerritoryStolen, LassoPocket,
                           LassoCrossNoCharge, RingSpawned, RingPicked, RoundEnded }
public sealed class SimEvent {
  public SimEventType Type; public double Time;  // Time = the group time of section 6
  public int Player = -1;
  public int Other = -1;    // Cut: the attacker (R11). SparkCaught, and Eliminated with Cause Spark: Spark.Attacker.
                            // TerritoryStolen, and Eliminated with Cause TerritoryLost: the returning player that took the
                            // cell (lowest index if several). Otherwise -1.
  public Vec2d Point;       // Cut: PointAt(s_cut). Exit / Return: crossing point. LassoPocket / LassoCrossNoCharge: X. SparkCaught: head.
  public double S;          // Cut: s_cut
  public int[] Cells;       // Return: captured (applied) cells; Eliminated: freed cells; LassoPocket: pocket cells added
  public bool Chased;       // Return: the player had a spark at the return instant
  public double Margin;     // Return while chased: (L - S) / SparkSpeed at the return instant, i.e. seconds the spark still
                            // needed to reach the return point; else 0
  public double DistanceHome;   // SparkCaught: distance to nearest own cell (NearestOwned, maxRadius 100) computed BEFORE
                                // Neutralize (u), or -1
  public EliminationCause Cause;
}
public sealed class Spark {
  public double SCut; public double TimeCut; public int Attacker;
  public double S;          // closed form SCut + SparkSpeed (Time - TimeCut) at the end of the last tick
  public double PrevS;      // S at the start of the last tick (SCut when spawned during it); render interpolation
}
public sealed class Ring { public Vec2d Pos; public double SpawnTime; }
public sealed class PlayerState {
  public int Index; public byte Id;             // Id = Index + 1 (grid owner value)
  public string Name; public bool IsHuman;
  public Vec2d Pos; public Vec2d PrevPos;       // PrevPos = position at the start of the last tick (render interpolation)
  public int Cell;                              // grid index of the head's current cell (R5); changed only by section 6
  public double Heading; public double DesiredHeading;
  public bool Alive = true; public bool Home = true;
  public Trail Trail = new Trail();             // empty when home
  public Spark Spark;                           // null when no chase
  public bool Charged;
  public CellMask Pocket;                       // pending pocket cells (Count 0 when none)
  public double EliminatedAt = double.NaN; public EliminationCause Cause;
  public int FinalCells;                        // eliminated: owned cells at the start of the eliminating group (R19); alive: at round end
  public int Captures, CutsMade, Kills, PocketsMade;   // Kills: victims eliminated by this player's sparks (credited even if dead)
  public int OwnedCells(OwnerGrid g) => g.CountOf(Id);
}
public sealed class RoundResult {
  public RoundEndReason Reason; public double EndTime;
  public int[] Ranks;                           // per player index, 1 = first, competition ranking (1, 1, 3)
  public int[] FinalCells; public double[] FinalAreaPercent;
  public List<int> Winners;                     // player indices with rank 1
}
public sealed class SimSetup {                  // optional overrides (tests, probe, attract mode)
  public int PlayerCount = Tuning.PlayerCount;
  public Vec2d[] StartPositions;                // null => R2 defaults
  public double[] StartHeadings;                // null => toward center
  public Action<OwnerGrid> Territory;           // null => R2 discs; otherwise fills the grid itself
  public string[] Names; public int HumanIndex = 0;   // HumanIndex -1 => all bots (attract mode)
  public Vec2d? ForcedRingPos;                  // when set, RingSpawner uses it instead of a random cell (probe, tests)
}
public sealed class Simulation {
  public Simulation(SimConfig config, IController[] controllers, SimSetup setup = null);   // throws if HeadGrace <= PawnSpeed * Dt
  public SimConfig Config { get; } public Arena Arena { get; } public OwnerGrid Grid { get; }
  public IReadOnlyList<PlayerState> Players { get; }
  public long Tick { get; }
  public long EndTick { get; }                                  // (long)Math.Ceiling(RoundDuration * TickRate - 1e-9)
  public double Time { get; }      // Tick / (double)TickRate (one division, never accumulated, never Tick * dt); RoundDuration after the last tick
  public bool Ended { get; } public RoundResult Result { get; }
  public Ring Ring { get; } public double NextRingTime { get; }
  public IReadOnlyList<SimEvent> LastEvents { get; }            // events of the last Step, in resolution order
  public event Action<SimEvent> EventRaised;                    // raised in resolution order during Step
  public event Action<Simulation> BeforeTick;                   // raised at the start of Step(), before controllers are polled
                                                                // (tests, probe: handlers key on the integer Tick, may call Debug* hooks)
  public int EventCapHits { get; }                              // times the event loop hit MaxEventsPerTick (tests assert 0)
  public SimView View { get; }
  public void Step();                                           // one tick; no-op when Ended
  public double AreaPercent(int playerIndex);
  // R19 competition rank. Eliminated player: final as soon as the Step that eliminated it returns. Alive player: final once
  // Ended (equals Result.Ranks); before that, a provisional rank by current cell count among alive players.
  public int RankOf(int playerIndex);
  public ulong StateHash();                                     // FNV-1a over grid cells, player pos (rounded 1e-9), Cell, flags, trails, spark S
  // Test and probe hooks (public, documented as test-only):
  public void DebugSetTrail(int player, IReadOnlyList<Vec2d> points);   // player becomes trailing with this trail; head = last point; exact state in 10.0 item 4
  public void DebugForceCut(int victim, double sCut, int attacker);     // spawns a spark now (TimeCut = Time, S = PrevS = sCut) as if cut; no-op if a
                                                                        // spark exists; sCut >= L gives a catch at the next tick start
  public void DebugSetCharged(int player, bool charged);
  public void DebugPlaceRing(Vec2d pos);
}
public sealed class SimView {                   // read-only facade handed to controllers and views
  public SimView(Simulation sim);
  public double Time { get; } public SimConfig Config { get; } public Arena Arena { get; } public OwnerGrid Grid { get; }
  public int PlayerCount { get; } public PlayerState Player(int index); public Ring Ring { get; }
  public double SparkCatchEta(int index);       // seconds until the spark reaches the head at current speeds, +inf if none
}
```
Controllers must never mutate anything reachable from SimView.

### 5.6 Controllers (Core/Controllers/ScriptedControllers.cs)
```csharp
public sealed class ConstantHeadingController : IController { public ConstantHeadingController(double heading); }
public sealed class HeadingScheduleController : IController {     // (time, heading) pairs, step function; an entry applies
  public HeadingScheduleController(params (double time, double heading)[] schedule); }   // on the first tick with Time >= time - 1e-9
public sealed class WaypointController : IController {            // steers to each waypoint in turn (reached within 0.3 u)
  public WaypointController(IReadOnlyList<Vec2d> waypoints, bool loop = false); }
public sealed class HomeCirclerController : IController {         // stays inside own start disc forever (orbit radius 1.5 u)
  public HomeCirclerController(Vec2d center); }
public sealed class ExternalController : IController {            // runtime human input: set Desired from outside
  public double? Desired; }                                        // returns Desired then leaves it as is
```

### 5.7 Bots (Core/Bots)
```csharp
public enum BotStyle { Cautious, Greedy, Aggressive, Balanced }
public sealed class BotPersonality {
  public BotStyle Style; public double MinOut, MaxOut;   // excursion depth range (u), measured from the edge point E (section 9)
  public double MaxTrailLength;                          // return when trail is longer
  public double ThreatRadius;                            // enemy head distance to own trail that triggers return
  public double AttackRadius; public double AttackChance; public double LassoChance;
  public double Jitter;                                  // radians of heading noise
  public double ReactionDelay;                           // seconds: a new own spark or a new threat is ignored this long
  public double SenseRadius = 16;                        // enemies farther than this (u) are invisible to the bot
  public double HumanAttackScale = 1;                    // multiplies AttackChance when the target is the human
  public static BotPersonality Preset(BotStyle style);
}
public sealed class BotController : IController {
  public BotController(BotPersonality personality, ulong seed);
}
```
Preset starting values (A5 may tune them to meet the section 9 targets and reports the final values):

| Style | MinOut | MaxOut | MaxTrailLength | ThreatRadius | AttackRadius | AttackChance | LassoChance | Jitter | ReactionDelay |
|---|---|---|---|---|---|---|---|---|---|
| Balanced | 4 | 9 | 30 | 6 | 7 | 0.45 | 0.5 | 0.10 | 0.30 |
| Greedy | 6 | 14 | 48 | 4.5 | 5 | 0.25 | 0.8 | 0.06 | 0.40 |
| Aggressive | 3 | 7 | 24 | 5 | 11 | 0.75 | 0.3 | 0.12 | 0.25 |
| Cautious | 2.5 | 5 | 16 | 8 | 4 | 0.15 | 0.4 | 0.08 | 0.35 |

Bot behaviour (section 9) reads only SimView. Bots are deterministic given seed and view.

---

## 6. Event engine (normative, Core/Sim/EventResolver.cs + Simulation.Step)

Tick bounds. EndTick = (long)Math.Ceiling(RoundDuration * TickRate - 1e-9). For tick k (t0 = Time, dt = Config.Dt):
uEnd = 1 for k < EndTick - 1; for k = EndTick - 1: x = RoundDuration * TickRate - k and uEnd = (x > 1 - 1e-9) ? 1 : x.
After the last tick, Tick = EndTick and Time = RoundDuration exactly.

Parameter convention (normative). Every in-tick value is a TICK parameter u in [0, uEnd]: p_i(u) = p0_i + u (p1_i - p0_i),
where p1_i is the full-step target of step 1. Every query receives the full tick segment (p0, p1) and uMin = uCur and
returns tick-u values; no caller ever passes p(uCur) as a segment start. For each trailing player the engine keeps
uTrailEnd_i, the tick u at which the stored trail end equals the head: 0 at tick start, set to u at an Exit (Trail.Start),
at a TerritoryStolen exit, and at every mid-tick Append (lasso point). growth_i = |p1_i - p0_i|.
L_i(u) = Trail.Length + growth_i (u - uTrailEnd_i).

Step(), for tick k:
0. Raise BeforeTick(this).
1. For each alive player i: ask its controller (null keeps DesiredHeading), turn Heading toward DesiredHeading (R3),
   compute p1_i = Arena.Step(p0_i, FromAngle(Heading) * PawnSpeed * dt, BorderHoldAngleDeg in rad). PrevPos = p0_i.
   Visit list V_i = GridRaster.TraverseFrom(Grid, Cell_i, p0_i, p1_i, uEnd, ...). uTrailEnd_i = 0. If i has a spark:
   Spark.PrevS = Spark.S.
2. Event loop, uCur = 0. Compute every candidate event with u in [uCur, uEnd] from the CURRENT state (owners read from the
   live grid). c_i = the last index n with V_i[n].U <= uCur; the current cell of i at uCur is V_i[c_i].Index.
   - Home transition(i), i alive (replaces FirstEntry for heads): if Home_i != (owner(V_i[c_i].Index) == Id_i), the
     transition happens at u = uCur: a home player on a non-own cell exits at its head p_i(uCur) (R9); a trailing player on
     an own cell returns with crossing point p_i(uCur). Otherwise the candidate is the first n > c_i whose owner flips the
     state, at u = V_i[n].U with crossing point p_i(V_i[n].U): HomeEnter (trailing, own cell) or HomeExit (home, non-own).
   - Cut(a, v): a alive, v alive, trailing and WITHOUT a spark, a != v:
     v.Trail.FirstContact(p0_a, p1_a, ContactRadius, uCur, uTrailEnd_v, growth_v, HeadGrace); reject u > uEnd.
   - SparkCatch(v): v has a spark. S(u) = Spark.SCut + SparkSpeed (t0 + u dt - Spark.TimeCut) (closed form, never
     accumulated). f(u) = S(u) - L_v(u) is strictly increasing because SparkSpeed > PawnSpeed. Let u0 be its root. The
     candidate is u_c = max(uCur, u0 + EventEpsilonSeconds / dt) when u_c <= uEnd; otherwise there is no candidate this
     tick (the max() makes it fire at the start of a later tick). The epsilon shift implements R13 (the return wins when
     t_r < t_c + eps) even across tick boundaries.
   - Lasso(i): i alive and trailing. n = i.Trail.SelfCrossings(p0_i, p1_i, uCur, L_i(uEnd) - LassoMinArc, list). Walk the
     list in order; skip a crossing unless Arc[k+1] <= L_i(u_X) - LassoMinArc; loop = Trail.LoopPolygon(k, X, X); the
     candidate is the FIRST crossing whose loop passes LassoGeometry.IsValidPocket(Grid, loop, LassoMinArea) (charged:
     LassoPocket; uncharged: LassoCrossNoCharge). Earlier crossings with invalid loops emit nothing. Record Trail.Version.
   - Pickup (ring present): for each eligible player i (alive, not Charged), its contact interval
     I_i = { u in [0, uEnd] : |p_i(u) - Ring.Pos| <= PickupRadius } = [in_i, out_i) (roots of a quadratic, half-open at
     out_i so a leaving head no longer counts at out_i; a stationary head gives all or nothing). n(u) = number of i with u in
     I_i. The candidate is the smallest u in {uCur} union {in_i, out_i that are >= uCur}, tested in ascending order, with
     n(u) == 1; none if there is no such u.
   - TimeUp: u = uEnd on the last tick (k = EndTick - 1).
   Let uMin be the smallest candidate u. Group = all candidates with (u - uMin) * dt <= EventEpsilonSeconds; uG = the largest
   candidate u in the group. Group time t = t0 + uMin * dt: it is the Time of every event of the group, Spark.TimeCut and
   EliminatedAt (eliminations in one group compare equal for R19). Each member uses its OWN u for geometry (exit point,
   return crossing point, lasso point X = p(u_member), cut s). During and after the group, current cells use c_i at uG.
   Snapshot every player's owned cell count (for FinalCells), then apply the group in this fixed order. Each of steps b-f
   re-validates its candidate against the current state and silently drops it if invalid:
   a. Returns: compute every returning player's capture against the grid as it is now (R18 conflict rule), apply all,
      then for each returner: outline end = its crossing point, clear trail, spark = null, pocket cleared, Home = true,
      Captures++. Emit Return (Chased, and Margin when it had a spark). Then every alive player that is Home, including the
      players that just returned, whose current cell is not its own starts an exit at its head (Home = false,
      Trail.Start(p(uG)), uTrailEnd = uG; emit TerritoryStolen then Exit, Other per 5.5). Then every alive player with 0
      cells is eliminated (cause TerritoryLost).
   b. SparkCatch: only a player still alive that still has its spark (a returner in a has none): eliminate (cause Spark),
      emit SparkCaught then Eliminated.
   c. Cuts: attacker alive at the start of this instant, victim alive, trailing and spark-less. Spawn the spark at the
      largest sCut among simultaneous cuts on that victim (ties: lowest attacker index): Spark { SCut = sCut, TimeCut = t,
      Attacker, S = PrevS = sCut }; emit Cut (Other = that attacker); that attacker CutsMade++.
   d. Lasso: player alive and trailing, and Trail.Version equals the version recorded with the candidate. Charged:
      Pocket.UnionWith(RasterPolygon(loop)), Charged = false, PocketsMade++, emit LassoPocket; uncharged: emit
      LassoCrossNoCharge. Then Trail.Append(X) and uTrailEnd = u_X (the loop was taken BEFORE the append).
   e. Pickup: if the single player of the candidate is still alive and not Charged, it takes the ring (Charged = true,
      Ring = null, NextRingTime = t + LassoRespawn), emit RingPicked; otherwise nothing.
   f. Exits: player alive and still Home (a player already made to exit in a is skipped): Home = false,
      Trail.Start(crossing point), uTrailEnd = its u, emit Exit.
   g. Round end check (R19), TimeUp last.
   Eliminating a player (a no-op if it is already dead): FinalCells = its count in the snapshot taken before step a. For
   cause Spark, compute SparkCaught.DistanceHome BEFORE Neutralize. Then Neutralize (emit Eliminated with freed cells,
   Other per 5.5), clear trail, spark, pocket, charge, Alive = false, EliminatedAt = t. For cause Spark,
   Players[Spark.Attacker].Kills++ (even if that attacker is dead).
   Then set uCur = uG, recompute all candidates and loop. Termination: every applied group advances uCur, flips a Home
   flag, removes a spark, ring or charge, eliminates a player, or appends a lasso point (lasso search uses u > uCur); a
   contested pickup at uCur produces no candidate. If MaxEventsPerTick groups are reached anyway: EventCapHits++, the loop
   stops and step 3 runs normally. Core tests assert EventCapHits == 0.
3. End of tick: every alive trailing player appends p_i(uEnd) to its trail (after any event points); Pos = p_i(uEnd);
   Cell_i = the Index of the last entry of V_i; every spark: S = SCut + SparkSpeed (t0 + uEnd dt - TimeCut) (closed form);
   the ring spawner runs; Tick++; Time = Tick / (double)TickRate (RoundDuration after the last tick).
   RingSpawner: if no ring, LassoEnabled and Time >= NextRingTime: use SimSetup.ForcedRingPos when set; otherwise pick
   deterministic random arena points (Rng) with GridQueries.IsNeutralDisc(RingClearance) and distance >= RingMinHeadDistance
   to every live head, up to 200 tries; in rounds with a live human (HumanIndex >= 0), the first 100 tries sample points
   6 to 22 u from the human's head; on failure retry next tick. Emit RingSpawned.

Determinism: no wall clock, no Dictionary iteration order dependence, no float (double only), Rng only. Same seed and same
controller decisions produce the same StateHash. Equality of outcomes across tick rates is defined by section 10.0.

---

## 7. Capture algorithm (normative, CaptureSolver.Compute)

Inputs: grid G (pre-instant), player p, outline = LoopErase.Erase(trail points including the final crossing point),
pocket P (may be null).
1. TrailCells = RasterPolyline(outline). OwnP = cells owned by p.
2. Box B = bounding box of OwnP cells, TrailCells and P cells, expanded by 1 cell, clamped to the grid. Cells outside B are
   reachable from outside by definition. Seeds = every non-wall cell on the border of B plus every Void cell inside B.
3. Semantics: ReachBefore = 4-connected flood from the seeds over non-wall cells inside B with walls = OwnP; ReachAfter = the
   same with walls = OwnP + TrailCells.
4. Interior = cells in B with: not Void, not wall-after, not ReachAfter, and ReachBefore (newly enclosed only; holes that
   were already enclosed by own territory alone stay as they are).
   Required implementation of steps 3-4 (same result, one large flood): (i) ReachAfter by scanline span fill on a pooled
   bitset; (ii) U = cells of B that are not Void, not walls-after and not ReachAfter; (iii) a multi-source BFS whose seeds
   are the non-own TrailCells 4-adjacent to a ReachAfter cell, spreading only through non-own TrailCells and U cells;
   Interior = the U cells it reaches. (Any non-own path from a U cell to the outside leaves U through trail cells, and the
   last trail cell on it is adjacent to a ReachAfter cell.)
5. Rim = TrailCells that are 4-adjacent to an Interior cell (the closing boundary belongs to the capture; a bare line
   back and forth has no Interior, so no Rim, so nothing).
6. Captured = (Interior + Rim + P) minus Void minus OwnP. Return ascending indices.
Performance budget: <= 3 ms on desktop and <= 8 ms on Android Medium (IL2CPP ARM64) for a full-size box (512 x 512).
Reuse buffers (no per-call allocation of 262144-element arrays: keep a static pool keyed by grid size).

---

## 8. Lasso details (normative)

- Detection is per tick inside the event loop (section 6): the first VALID crossing counts (R16). The crossing point X
  splits the crossed segment k.
- Loop polygon = [X, Points[k+1], ..., Points[last], head point at crossing (= X)], built with Trail.LoopPolygon BEFORE X is
  appended to the trail.
- Validity = LassoGeometry.IsValidPocket(grid, loop, LassoMinArea): interior cells (non-zero winding of the cell center)
  x CellSize^2 >= LassoMinArea, so an earlier self crossing inside the loop (figure-8 lobes) cannot cancel area.
- Pocket cells = GridRaster.RasterPolygon(loop) (non-zero winding + boundary), Void excluded. Pocket is a CellMask per
  player; several lassos in one exit union (each needs a new charge).
- The trail is NOT modified by a lasso (no shortcut for the spark): the crossing point is appended as a normal point.
- The capture on return uses the loop-erased outline, so the loop interior is only captured through the pocket.
- Known limitation, accepted: two passes of the trail closer than about one cell that do not cross are joined by the wall
  raster, so a near-loop can close without a crossing. Tests C5, C7 and S5 keep gaps of at least 2 cells between passes.

---

## 9. Bots (Core/Bots)

A finite state machine per bot, reading only SimView and ignoring every enemy farther than SenseRadius (its head, trail
and spark). Decisions every 0.1 s of sim time (based on Tick), heading output every tick. A new own spark or a new threat
is ignored for ReactionDelay seconds. Target selection never reads IsHuman except through HumanAttackScale.
- Home (plan an excursion): choose a direction theta among 8 by scoring the cells of a 60 degree sector from 1 to MaxOut u
  beyond the territory edge: neutral +1; rival +1.5 if Aggressive, +0.2 if Cautious, +0.5 otherwise. Edge point E = the
  first non-owned point along theta from the head (GridRaster.FirstEntry; the head itself if already outside). Plan =
  [E + theta * depth, then a sideways leg of length width toward the higher-scoring side, then R], with
  depth = Range(MinOut, MaxOut), width = depth * Range(0.6, 1.2), R = E - theta * 1.0 (1 u inside its own land). Every plan
  point goes through Arena.ClampInside with an extra 1.0 u margin.
- Out: follow the plan with smooth turns (desired heading toward the next plan point plus Jitter noise). At each decision,
  skip any plan point that has become own territory. If R is no longer owned, R = GridQueries.NearestOwned(head,
  maxRadius 100) pushed 1.0 u deeper along the approach direction.
- Return triggers (then head straight for NearestOwned(head, maxRadius 100), never loop): trail length > MaxTrailLength;
  an enemy head within ThreatRadius of the closest exposed point of its own trail; its own spark exists (after
  ReactionDelay); Time + D_home / PawnSpeed + 2.0 >= RoundDuration (D_home from NearestOwned).
- Attack: at each decision, for each enemy v within SenseRadius that is trailing and has no spark, sample its exposed trail
  at s_k = L_v - HeadGrace - 0.3 - 0.5 k (k = 0, 1, ... while s_k >= 0 and P(s_k) is within AttackRadius of the bot's head).
  For each sample: T = |P(s_k) - head| / PawnSpeed + |heading change| / TurnRate (rad/s; 0 when TurnRateDeg = 0);
  predicted gap at contact G = L_v + PawnSpeed T - s_k; catch time C = G / (SparkSpeed - PawnSpeed); escape time
  E_v = D_v / PawnSpeed with D_v from NearestOwned(v's head, maxRadius 100) (+inf if none). A sample is lethal when
  C < E_v - 0.2. Target = the lethal sample with the largest s_k, taken with probability AttackChance (x HumanAttackScale
  when v is the human). If no sample is lethal, only Aggressive bots attack, aiming at the largest reachable s_k with
  probability AttackChance / 3 (a harassment cut). Commit to the chosen intercept for up to 1.5 s, re-aiming at the same
  s_k at each decision; abort when v gets home or gets a spark, or when a return trigger fires.
- Ring: if uncharged and the ring is within 8 u and safe (no enemy head within ThreatRadius of the bot or of the ring, and
  trail length + 2 x distance to the ring <= MaxTrailLength), go take it. Lasso: if charged and a draw (once per exit) is
  below LassoChance, curl a loop crossing an older part of the trail (at least 3 u back).
- Never steer outward into the border on purpose; avoid crossing own trail when uncharged.
Presets: player 1 Balanced, player 2 Greedy, player 3 Aggressive (Cautious is available for tests); values in 5.7.
Targets in bot-only 90 s matches over 50 seeds (asserted): no exception; each Balanced or Aggressive bot averages >= 5
captures, Greedy >= 4; cuts happen in >= 85 % of matches; at least one Spark elimination in 35 % to 85 % of matches; average
total coverage at the end between 30 % and 85 %; TimeUp is reached in >= 40 % of matches.
Reported only (logged in the A5 report, not asserted): share of bot Spark eliminations from escapable cuts (target < 10 %;
escapable when, at the Cut event, (L - s_cut) / (SparkSpeed - PawnSpeed) > 1.3 x D_home / PawnSpeed + ReactionDelay);
share of alive time spent trailing per bot (target 30 % to 75 %); human-proxy fixture (player 0 = BotController(Balanced
with ReactionDelay 0.45, SenseRadius 12, AttackChance 0.3) against the 3 presets, 50 seeds: target alive at the end in 35 %
to 75 % of rounds and first in 15 % to 45 %).

---

## 10. Core tests (required, Tests/EditMode/Core/*.cs, NUnit, names prefixed by id)

### 10.0 Cross-rate protocol (normative)
1. Cross-rate scenario tests set TurnRateDeg = 0 and use only ConstantHeadingController or HeadingScheduleController with
   switch times that are multiples of 1/6 s. Scenarios using WaypointController or bots run at 60 Hz only.
2. Axis-aligned scenario paths run on cell-center lines (Origin + (k + 0.5) CellSize). Other segments stay at least 1e-6 u
   away from lattice corners. (Dedicated edge tests such as GR-Edge deliberately do the opposite.)
3. Identical outcomes means: the same ordered list of (Type, Player, Other, Cause); event times within 1e-6 s; identical
   Cells arrays for Return and LassoPocket; the same RoundResult ranks. StateHash is compared only within one tick rate.
4. DebugSetTrail sets Heading = DesiredHeading = the direction of the last trail segment, Pos = PrevPos = last point,
   Cell = TryCellOf(head) (throws if that cell is owned by the player), Home = false.
5. S4: in the strict cases t_c is not a tick time at any of the three rates (for example t_c = 1.013 s); the exact-tie case
   puts t_c on a common tick time (a multiple of 1/6 s) to exercise the epsilon shift of section 6.

### 10.1 Required tests
Unit: Vec2d/Geo (sweep incl. parallel motion and zero-length motion; ProperIntersect half-open: a crossing at an old vertex
counted exactly once, touching / collinear / a0 on the line false), Arena (SDF, Step slide and hold), Rng determinism,
CellMask, OwnerGrid counts, GridRaster (4-connectivity, corner case = x-neighbour then diagonal, cell entered at u = 1
included, TraverseFrom: start on an edge enters at U = 0, one diagonal entry at a corner tie, negative tMax clamped,
FirstEntry exact times on axis-aligned moves), GR-Edge (a head moving +x at PawnSpeed along a cell-center line from 0.5 u
before an own/neutral boundary lying on a cell edge, so that ticks end exactly on cell edges at 60 Hz: the exit is detected
exactly once at the edge time within 1e-9 s at TickRate 30, 60 and 144; the same for a return), RasterPolygon (interior
count vs area / CellSize^2 within 2 % for a square of side >= 4 u; full raster vs area + perimeter * CellSize within 5 %;
test vertices at least 1/3 cell away from cell edges), CountInterior, LoopErase (figure 8, nested loops, crossing through
a vertex, one new segment crossing several kept segments: smallest index wins), Trail (arc, PointAt, FirstContact incl.
HeadGrace, exposure-induced contact: an attacker already over the grace zone cuts at the instant the touched point becomes
exposed with sCut = L - HeadGrace, identical at 30/60/144 Hz; an attacker moving parallel along a segment;
most-recent-pass rule; SelfCrossings incl. tangency/adjacent/U-turn false, sort order, maxSegmentEndArc filter),
LassoGeometry (figure-8 lobes of opposite orientation do not cancel). CaptureSolver:
- C1 square loop of side >= 16 u from a disc: the captured cell area is within 3 % of the analytic area of the region
  enclosed by the trail centerline and the disc, minus the disc; every trail cell 4-adjacent to the interior is captured.
- C2 back-and-forth line captures 0 cells.
- C3 excursion hugging the border and returning captures only the region between trail and own territory, never > 30%.
- C4 a hole already enclosed by own territory is not captured by an unrelated return.
- C5 a self loop of the trail is not captured without pocket; it is captured with the pocket.
- C6 capture takes rival cells.
- C7 an uncharged trail that circles out, crosses its own first segment 1 u from home, then enters home captures only the
  stub region; the same trail with a charge captures stub + loop (R8).

Rules: R2 symmetric discs; R5 exit at cell edge; R9 stolen home cell starts an exit; R9b a trailing player whose exit cells
were stolen does not return on them, it returns only on its current color; R9 zero cells eliminates (FinalCells = cells
before that capture); R10 head through head does nothing; R10 own trail never cuts; R11 superposed passes pick latest; R11
two attackers same instant pick largest s, Other and CutsMade go to that attacker; R11b a chased victim cuts another player
during its flight; R12b the spark keeps moving and catches after its attacker is eliminated (Kills credited); R13b at
TickRate 30, a cut at u = 0.3 and a return at u = 0.7 of the same tick give Cut then Return (saved, Chased, Margin > 0);
with the times swapped they give Return and no Cut; R14 cut at closure ignored; R15 contested ring: A and B enter at the
same instant, then B leaves: A picks the ring at B's exit instant; then B is eliminated instead: A picks it at that instant;
a charged head sitting on the ring that spends its charge in a lasso picks the ring at once if alone; R15 charged player
leaves ring; R15b the first ring appears at the first tick with Time >= 15 s on neutral ground, the next 15 s after the
pickup, never two at once, a charge is kept across exits, LassoEnabled = false gives no ring in 90 s; R16 an invalid tiny
loop then a valid big loop in the same tick: the pocket comes from the big one and the charge is spent once; R17b while a
pocket is pending the cells inside keep their owners, crossing the pocket sets no Home and ends no exit, a cut on the pocket
contour spawns the spark, and a lasso during a chase leaves Spark.SCut, TimeCut and S(t) unchanged; R18 simultaneous returns
conflict; R18b two simultaneous returns where A's capture contains the cell B returns onto: B gets its own capture, then
immediately starts an exit at its head and must reach its current color to return; R19 last survivor, all eliminated same
instant share first, time-up tie shares first, pocket never counts, competition ranking (1, 1, 3), RankOf of an eliminated
player is final after its Step; R19b a return at exactly t = RoundDuration counts for the ranking; R4 border hold and
slide; determinism (same seed same hash); EventCapHits == 0 in every Core test.

Brief section 7 scenarios (S ids), each run at TickRate 30, 60 and 144 with identical outcomes (10.0):
- S1 A big closed curve (that does not cross itself) without opposition recolors its interior; cutting through a rival color
  without returning changes no owner.
- S2 A cut near the trail origin while the victim is almost home: the victim wins the race and the full planned area is
  captured.
- S3 A cut just behind a far victim: the spark catches it (eliminated, territory neutral, attacker gains nothing). A second
  cut during the chase does not move or speed the spark (assert S(t) = s_cut + SparkSpeed (t - t_cut)).
- S4 Race timing with DebugSetTrail + DebugForceCut: victim moving straight toward home; return strictly before impact ->
  saved; strictly after -> eliminated; exact tie (tie built analytically: home edge on a cell boundary, distance
  D = PawnSpeed * G / (SparkSpeed - PawnSpeed) with G = L - s_cut, t_c per 10.0 item 5) -> saved. Margins +/- 0.05 s.
- S5 Charged lasso, cross back through the pocket, return: score unchanged until the return, then increases by at least the
  pocket area. Replay and get caught: pocket gone, rival cells inside the pocket keep their owner.
- S6 Same trajectory without charge: no pocket, LassoCrossNoCharge emitted. Then a chase on a figure 8 where the straight
  distance from the cut to the head is less than half the arc distance: SparkCaught time = t_cut + (L(t_c) - s_cut) /
  SparkSpeed within 1e-6 s, the spark passes the crossing twice in arc order, and the drawn spark position
  Trail.PointAt(S) never moves more than SparkSpeed * dt + 1e-9 per tick.
Bots: 50 seeded bot-only rounds (section 9 targets) run in under 60 s total in the dotnet loop; under Unity
(`#if UNITY_5_3_OR_NEWER`) the same test runs 10 seeds and asserts only no exception and the invariants. Invariants every
tick: no NaN, cells sum <= arena cells, Home == (owner(Cell) == Id) for alive players, trail empty iff home, trail end ==
Pos for trailing players, spark S <= trail length + 1e-6, EventCapHits == 0.
Runtime EditMode (Tests/EditMode/Runtime, owner B0): S4-Display. The three S4 cases are built as GameSessions at TickRate 60
and driven through SimRunner.Advance with frame deltas of exactly 1/30 s, exactly 1/144 s, and a jittered sequence
alternating 1/50 and 1/90 s. For each case: the same outcome (saved / eliminated / saved), the same Return or SparkCaught
time within EventEpsilonSeconds, and the same StateHash as the Core run (brief 7.4: two display frequencies).

---

## 11. Runtime architecture (PainterIO.Runtime)

### 11.1 GameDirector (Game/GameDirector.cs), the only MonoBehaviour in the scene
States: Boot -> Menu (attract match behind the menu) -> Playing -> Results -> (Playing | Menu).
`Awake` first applies the frame settings: Application.targetFrameRate = 60 (or the -fps value) and QualitySettings.vSyncCount
= 0 on Android; on Windows vSyncCount = 1 and targetFrameRate = -1 unless -fps is given (then vSync off and that rate). On
Android, if Screen.height > 1920, the active URP asset's renderScale = min(its value, 1920f / Screen.height) (the UI stays
native). Screen.sleepTimeout = SleepTimeout.NeverSleep while Playing, SleepTimeout.SystemSetting otherwise.
Then `Awake` builds every subsystem, each in its own try/catch that logs `[PainterIO] <subsystem> failed: <exception>` and
continues (an exception in Awake must never take down the rest):
```csharp
public sealed class GameDirector : MonoBehaviour {
  public static GameDirector Instance { get; private set; }
  public GameState State { get; }                    // enum GameState { Boot, Menu, Playing, Results }
  public GameSession Session { get; }                // current session (attract or real)
  public event Action<GameState> StateChanged;
  public event Action<GameSession> SessionStarted;   // views rebind on this
  public void StartRound();                          // new real session (human + 3 bots) from SaveData, State = Playing
  public void ToMenu();                              // attract session, State = Menu
  public void ShowResults();                         // called ONLY by GameDirector itself (results flow below)
  public bool IsPaused { get; }
  public event Action<bool> PausedChanged;
  public void SetPaused(bool paused);                // only while State == Playing in a non-attract session; sets Runner.Paused
  public void SlowMo(float timeScale, float holdSeconds, float rampSeconds);   // Runner.TimeScale for holdSeconds of real
                                                     // time, then ramps back to 1 over rampSeconds (sim outcomes unchanged)
  public HumanOutcome LastOutcome { get; }           // set before ShowResults
}
public sealed class HumanOutcome {
  public int Rank; public bool SharedRank; public double AreaPercent; public RoundEndReason Reason;
  public EliminationCause Cause; public int Attacker = -1; public double CaughtDistance = -1;
  public int Captures, CutsMade, Kills, PocketsMade; public double SurvivedSeconds;
  public bool HadSavedReturn; public double LastSavedMargin;   // last chased Return of the round, for the WHY line
}
```
Pause: triggers are the HUD pause button (B4), Escape or Android back while Playing (B3 calls SetPaused(!IsPaused)), and
OnApplicationPause(true) / OnApplicationFocus(false) while Playing (GameDirector). Leaving pause never restarts the sim
directly: it goes back through the ready gate of 11.2 (AwaitingStart = true; the sim resumes on the next steering input or
after 1.0 s). On OnApplicationPause(true), SaveData.Flush().
Ready gate: GameDirector calls Session.Begin() on the first frame where HumanController.Desired is non-null while
AwaitingStart, or after an auto-start delay of 2.5 s while SaveData.RoundsPlayed < 3 (1.0 s afterwards), unless paused.
Slow motion (readability of La Revanche, brief 4.6 and 7.7), applied on the human's events: first Cut received while
!SaveData.TutCutDone -> SlowMo(0.3, 1.2, 0.3) together with the tutorial bubble; any later Cut received ->
SlowMo(0.25, 0.12, 0.08); a Cut dealt by the human -> SlowMo(0.25, 0.08, 0.05).
Results flow: GameDirector subscribes to Session.EventRaised and is the only caller of ShowResults. When the human is
eliminated it builds LastOutcome at once (after the Step: Sim.RankOf, FinalCells, Cause, Attacker = SparkCaught.Other,
CaughtDistance = SparkCaught.DistanceHome), holds a 1.0 s death beat in real time (the camera holds on the splash; a tap
skips it; the background match keeps playing), then calls ShowResults. When the round ends with the human alive, the beat
is 0.6 s. Then it updates SaveData.BestArea, Wins (rank 1, shared included) and RoundsPlayed unless SaveData.TuningModified
or a command-line tuning override is active, and calls SaveData.Flush().
Subsystem entry points (each package implements its own static factory; signatures binding):
`LiquidRenderer.Create(GameDirector d)`, `ActorViews.Create(GameDirector d)`, `CameraRig.Create(GameDirector d)`,
`SteeringInput.Create(GameDirector d)`, `UiRoot.Create(GameDirector d)`, `Sfx.Create(GameDirector d)`,
`PlayerProbe.TryCreate(GameDirector d)` (returns null unless `-probe` is on the command line). Each returns its root
Component and subscribes to `SessionStarted` / `StateChanged`.

### 11.2 GameSession (Game/GameSession.cs)
```csharp
public sealed class GameSession {
  public GameSession(SimConfig config, SimSetup setup, IController[] controllers, bool isAttract);   // AwaitingStart = false
  public Simulation Sim { get; } public bool IsAttract { get; } public int HumanIndex { get; }   // -1 in attract
  public ExternalController HumanController { get; }       // null in attract
  public SimRunner Runner { get; }
  // Forwarded AFTER each Sim.Step returns (from Sim.LastEvents, in resolution order), on the main thread, during
  // Runner.Advance. Each subscriber is invoked in its own try/catch (logged once per subscriber, never aborts the sim), so
  // handlers see a consistent state and may read RankOf / FinalCells.
  public event Action<SimEvent> EventRaised;
  public float Alpha { get; }                              // interpolation factor between PrevPos and Pos for rendering
  public Vector2 RenderPos(int player);                    // Lerp(PrevPos, Pos, Alpha) in Unity units
  public double RenderSparkS(int player);                  // Lerp(Spark.PrevS, Spark.S, Alpha), same Alpha; NaN when no spark
  public bool HumanAlive { get; }
  public bool AwaitingStart { get; }                       // true while the round waits for the human (Runner.Paused)
  public void Begin();                                     // clears AwaitingStart and unpauses (unless GameDirector is paused)
  public static GameSession CreateRound(ulong seed, bool lassoEnabled);   // human index 0 + bots 1..3 (Balanced, Greedy, Aggressive)
  public static GameSession CreateAttract(ulong seed);                    // 4 bots, endless: restarts itself on round end
}
public sealed class SimRunner {                            // fixed-step accumulator, frame-rate independent
  public SimRunner(Simulation sim);
  public bool Paused; public float TimeScale = 1f;
  public int Advance(float deltaTime);                     // accumulates in double; steps Sim while accumulator >= dt (max 8 steps per frame), returns steps
  public float Alpha { get; }                              // accumulator / dt
}
```
CreateRound: SimConfig from Tuning, then the SaveData test settings (SparkFactor -> SparkSpeedFactor, RoundSeconds ->
RoundDuration, RingDelay -> LassoFirstSpawn and LassoRespawn), then the Windows command-line overrides `-sparkFactor <x>`,
`-roundDuration <s>`, `-ringInterval <s>`; LassoEnabled = lassoEnabled (StartRound passes SaveData.LassoOn, or the `-lasso 0|1`
override when given). SimSetup.Names: the human is "Toi" (EN "You"), each bot is named after its displayed color
(Palette.ColorIndexOf). Bot personalities from BotPersonality.Preset, with HumanAttackScale = 0.3 while
!SaveData.TutExitDone. HumanController.Desired = null, AwaitingStart = true, Runner.Paused = true: the whole sim, bots
included, waits at t = 0 and the HUD shows the full round time. CreateAttract and every probe or test session start with
AwaitingStart = false. REJOUER and Menu -> round use seed = (ulong)DateTime.UtcNow.Ticks (Runtime only; the probe and
tests pass fixed seeds).

### 11.3 Palette (View/Palette.cs)
Player colors (sRGB): 0 Coral #F2674F, 1 Teal #22C4B6, 2 Saffron #F5B731, 3 Lilac #8E6CEF.
Background navy #1E2A4D, outside arena #B4B9C1 (flat light grey shared by every biome since border_neon, was #151D38),
UI text light #F3EEE8, danger flash white #FFFFFF.
The human picks its color in the menu (index swap: the human always is sim player 0):
```csharp
public static class Palette {
  public static int HumanColor { get; set; }          // 0..3, backed by SaveData.ColorIndex
  public static int ColorIndexOf(int playerIndex);    // palette index shown for a sim player: 0 and HumanColor swapped
  public static Color ColorOf(int playerIndex);       // sRGB color of ColorIndexOf(playerIndex)
}
```
The swap applies in every session, attract included. Bot names in French: "Corail", "Lagon", "Safran", "Lilas" (name
follows the displayed color); the human is "Toi" (EN "You").

### 11.4 LiquidLayers (View/LiquidLayers.cs)
```csharp
public static class LiquidLayers {
  public const int Field = 31;                 // layer rendered only by the actor field camera
  public const float IsoLevel = 0.5f;
  public static Vector4 ChannelMask(int player);   // (1,0,0,0), (0,1,0,0), (0,0,1,0), (0,0,0,1)
  public static Mesh QuadMesh { get; }         // built in code once: vertices (+/-0.5, +/-0.5, 0), uv0 in [0,1]^2, 2 triangles
  // Support radius of a blob f = A (1 - r^2)^2 whose 0.5 iso contour has radius visibleRadius:
  // v / sqrt(1 - sqrt(0.5 / max(A, 0.51))) (below A = 0.51 the support of A = 0.51 is kept while the amplitude fades to 0).
  public static float SupportForVisibleRadius(float visibleRadius, float amplitude = 1f);
}
```

### 11.5 SaveData (Game/SaveData.cs, B0, binding for B1, B3, B4, B5)
```csharp
public static class SaveData {                       // PlayerPrefs keys "pio.<Name>"; every access in try/catch (defaults on failure)
  public static bool SoundOn { get; set; }           // default true
  public static bool HapticsOn { get; set; }         // default true
  public static bool LassoOn { get; set; }           // default FALSE (first Revanche trial without lasso, brief closing paragraph)
  public static int Language { get; set; }           // 0 FR (default), 1 EN; Strings.Language reads and writes it
  public static int Quality { get; set; }            // 0 Auto (default), 1 High, 2 Medium, 3 Low
  public static int ColorIndex { get; set; }         // 0..3, default 0
  public static float BestArea { get; set; }         // best human area percent (alive at round end, or FinalCells when eliminated)
  public static int Wins { get; set; }               // rounds where the human has rank 1, shared included
  public static int RoundsPlayed { get; set; }
  public static bool TutExitDone { get; set; }
  public static bool TutCutDone { get; set; }
  public static bool TutLassoDone { get; set; }
  public static float SparkFactor { get; set; }      // test setting, default 1.8, range 1.4..2.4 step 0.1
  public static float RoundSeconds { get; set; }     // test setting, default 90 (60 / 90 / 120)
  public static float RingDelay { get; set; }        // test setting, default 15 (10..30 step 5)
  public static bool TuningModified { get; }         // any test setting differs from Tuning
  public static event Action Changed;                // raised after every setter
  public static void Flush();                        // PlayerPrefs.Save: when Options close, when Results appear, on OnApplicationPause(true)
}
```
Consumers: Sfx reads SoundOn, Haptics reads HapticsOn, QualityTier reads Quality, Palette reads ColorIndex, StartRound
reads LassoOn and the test settings, TutorialOverlay reads and writes the Tut flags.

---

## 12. Rendering contract (the liquid look)

### 12.1 Shader policy (Unity pitfalls, mandatory)
- Every shader lives in `Assets/Resources/Shaders/` and is loaded with `Resources.Load<Shader>("Shaders/<Name>")`.
  Never `Shader.Find` (stripped from players). No `shader_feature` keywords (use uniforms or `multi_compile_local`).
- Split by what Shader Graph can express (the user chose URP + Shader Graph; v1.1 had dropped it on a wrong premise):
  - Shader Graph (`.shadergraph`, URP target, Unlit material): LiquidComposite (Opaque; Depth Write ForceDisabled, Depth
    Test Always; render queue set on the material by code), Bead and Overlay (Transparent, Alpha blend, Depth Write
    ForceDisabled, Depth Test Always). Each graph is THIN: object/world position and UV nodes feed ONE Custom Function node
    in File mode (functions `PIO_CompositeSG`, `PIO_BeadSG`, `PIO_OverlaySG` in `LiquidComposite.hlsl`, `Bead.hlsl`,
    `Overlay.hlsl`) whose outputs go to Base Color and Alpha. All the math lives in the .hlsl files. Rules that make this
    work: (1) a Custom Function in File mode references its .hlsl by GUID, so every .hlsl in Resources/Shaders ships a
    hand-written `.meta` with a fixed GUID (32 hex chars, unique, recorded in the author's report) BEFORE the graph that
    uses it is imported; (2) every `_PIO_*` global is declared in `LiquidCommon.hlsl` (included by the function files) and
    is NEVER a graph property (graph properties land in UnityPerMaterial and Shader.SetGlobal* would be silently ignored);
    per-object data (bead color and radius, overlay shape id, alpha) comes through vertex attributes (vertex color, uv1,
    uv2) written by the owning view, never through MaterialPropertyBlock, so the SRP Batcher stays valid; (3) each graph exposes exactly
    one property `_PIO_ShaderId` (Float, default 1, hidden) as the error-shader marker; (4) use the sample graphs under
    `Library/PackageCache/com.unity.render-pipelines.*/Samples~/` as templates of the multi-JSON format (GraphData,
    UniversalTarget + UniversalUnlitSubTarget, block nodes, CustomFunctionNode with m_SourceType File and the GUID), and keep
    the graph's shader path "Shader Graphs/PainterIO/<Name>".
  - Hand-written URP HLSL `.shader` (Shader Graph cannot express them): FieldBlob and FieldStroke (Blend One One on all four
    channels with alpha as data: Shader Graph Additive is Blend SrcAlpha One and Opaque forces alpha = 1) and TerritoryBlur
    (procedural full-screen triangle from SV_VertexID through cmd.DrawProcedural). They use
    `Tags { "RenderPipeline"="UniversalPipeline" }`, pass LightMode `SRPDefaultUnlit`, `HLSLPROGRAM` including
    `Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl` and `LiquidCommon.hlsl`, and declare
    `[HideInInspector] _PIO_ShaderId ("id", Float) = 1`.
  - Fallback (per graph, last resort): if a graph cannot be made to import cleanly AND render correctly in the player probe
    after a serious attempt, its owner deletes the `.shadergraph` and ships a hand-written `.shader` that calls the same
    .hlsl function, and reports it under `contract_issues`. A shader name exists exactly once in Resources/Shaders (never a
    graph and a .shader side by side).
- Runtime code loads each shader with `Resources.Load<Shader>("Shaders/<FileNameWithoutExtension>")` (works for both
  `.shader` and `.shadergraph` main assets).
- `Editor/ShaderCheck.cs` (owned by B0), for every `.shader` and `.shadergraph` in Resources/Shaders:
  `AssetDatabase.ImportAsset(path, ForceUpdate | ForceSynchronousImport)`; load the Shader (main asset);
  `ShaderUtil.allowAsyncCompilation = false`; `m = new Material(s)`; for each pass i, `ShaderUtil.CompilePass(m, i, true)`.
  FAIL if s is null, `ShaderUtil.ShaderHasError(s)`, any `ShaderUtil.GetShaderMessages(s)` entry has Error severity,
  `s.name` contains "InternalErrorShader", or `s.FindPropertyIndex("_PIO_ShaderId") < 0`. It also fails when two assets
  in Resources/Shaders share a file name without extension, and when an .hlsl lacks its .meta.
- All lighting is custom (unlit pipeline + custom shading). URP lights and shadows are off. DefaultVolumeProfile as shipped
  has Tonemapping None and Bloom intensity 0: B1 verifies it and edits it only if that is not the case. No ACES (it washes
  out the saturated paint). Bloom optional on PC High only, threshold >= 1.1, enabled by LiquidRenderer through the main
  camera's renderPostProcessing (section 14).

### 12.2 Architecture
Two field sources feed one composite:
1. Territory field (world space): `TerritoryField` keeps a VisualMask (512 x 512 RGBA32, linear, channel c = player c owns
   the cell, 255/0) built from the sim grid and uploads it when it changes. GPU passes: (a) separable Gaussian at the mask
   resolution into a 512^2 R16G16B16A16_SFloat ping-pong pair, sigma = 1.28 cells (0.16 u), 5 linearly interpolated taps per
   pass; (b) one bicubic B-spline upsample pass into the 1024^2 `_PIO_TerritoryField` (t_i per channel: interior = 1, edge
   falls smoothly to 0 over about 0.5 u) and `_PIO_TerritoryHeight` (RGBA half: H_T = PIO_Height(max t), dH_T/dx, dH_T/dy in
   world units, max t), as MRT or two passes. All passes run only when the VisualMask changes, in a CommandBuffer executed
   with Graphics.ExecuteCommandBuffer in LateUpdate, limited with cmd.EnableScissorRect to the dirty rectangle (bounding
   box of changed cells grown by 4 sigma + 2 cells); the full-texture path runs only at session start. Each pass draws a
   procedural full-screen triangle (cmd.DrawProcedural, position from SV_VertexID) with explicit `_PIO_BlurSource` and
   `_PIO_BlurTexel`; never Graphics.Blit or the URP Blitter here. Budget: <= 0.5 ms GPU per fill frame on a mid-range
   Android phone. Globals: `_PIO_TerritoryField`, `_PIO_TerritoryHeight`, `_PIO_TerritoryTexel`, `_PIO_ArenaRect`
   (minX, minY, sizeX, sizeY) = (-32, -32, 64, 64).
2. Actor field (world-rectangle space): `ActorFieldCamera` (B1) is an orthographic camera created at runtime: depth -10,
   cullingMask = 1 << LiquidLayers.Field, clear SolidColor (0,0,0,0), allowHDR = false, allowMSAA = false,
   useOcclusionCulling = false; UniversalAdditionalCameraData renderPostProcessing = false, renderShadows = false,
   requiresDepthOption = Off, requiresColorOption = Off, antialiasing = None. It updates in LateUpdate with
   `[DefaultExecutionOrder(200)]` (after CameraRig, order 100) and covers the world rectangle R = main camera view rect grown
   by 0.6 u per side: position = R.center, orthographicSize = R.height / 2, aspect = R.width / R.height, RT size =
   round(R.size * ppu * tierScale) with ppu = mainCamera.pixelHeight / (2 * mainCamera.orthographicSize). It renders ONLY
   layer LiquidLayers.Field into `_PIO_ActorField` (format and lifecycle in section 19) and publishes `_PIO_ActorRect` =
   (R.xMin, R.yMin, R.width, R.height) and `_PIO_ActorTexel`. Every consumer samples the actor field at
   uv = (worldXY - _PIO_ActorRect.xy) / _PIO_ActorRect.zw, never with screen uv. Only field contributors use layer 31.
   Contributors (FieldBlob.shader, FieldStroke.shader): `Tags { "RenderPipeline"="UniversalPipeline" "Queue"="Transparent"
   "RenderType"="Transparent" } Pass { Tags { "LightMode"="SRPDefaultUnlit" } Blend One One, One One  BlendOp Add  ZWrite Off
   ZTest Always  Cull Off  ColorMask RGBA }`. The fragment returns exactly `_Channel * f * _PIO_ActorScale` (alpha is data,
   not opacity). Per-renderer data through MaterialPropertyBlock: `_Channel` (Vector4 = LiquidLayers.ChannelMask),
   `_Amplitude` (float).
   Mesh conventions (binding for B1 and B2):
   - FieldBlob: LiquidLayers.QuadMesh. Transform scale = (2 S stretch, 2 S / stretch, 1) with
     S = SupportForVisibleRadius(visibleRadius, A); Z rotation = velocity angle. Fragment: q = uv0 * 2 - 1,
     f = _Amplitude * saturate(1 - dot(q, q))^2. Used for the pearl neck blob, the retraction bulb and pulses.
   - FieldStroke: MeshTopology.Triangles (a triangle list, not a strip), vertices in world space under an identity
     transform, uv0.x = per-vertex amplitude multiplier (A = _Amplitude * uv0.x), uv0.y = cross coordinate in [-1, 1],
     vertex color unused, f = A * saturate(1 - y * y)^2. Strip half width at each sample =
     SupportForVisibleRadius(visibleRadius(s), A(s)). ThreadView calls mesh.MarkDynamic() and sets mesh.bounds to the trail
     bounding box grown by 1 u on every rebuild.
   Field-feeding views (ThreadView, PearlView, RetractionView) update meshes and transforms in LateUpdate from
   GameSession.RenderPos and RenderSparkS.
3. Composite: `LiquidSurface` (B1) is a static quad covering [-40, 40]^2 at z = 0 (the camera clamp of section 14 keeps the
   view inside it), drawn by the main camera with the LiquidComposite graph, queue Geometry-100, ZWrite Off, ZTest Always.
   Overlays and beads use queue Transparent, ZTest Always, ZWrite Off. Per pixel at world position w, with t_i from
   `_PIO_TerritoryField` multiplied by `_PIO_PlayerFade`, a_i from the actor field divided by `_PIO_ActorScale`, and
   H = PIO_Height:
   - Territory layer: j = argmax t_i, HT = H(t_j) (from `_PIO_TerritoryHeight`, scaled by the fade of a fading player),
     cT = saturate((t_j - 0.5) / max(fwidth(t_j), 1e-4) + 0.5).
   - Actor layer, only if max a_i >= 0.003: k = argmax a_i, fA = a_k + t_k (same-color fusion: necks between pearl, thread
     and puddle appear by themselves), base = H(max over i != k of t_i) (the rival puddle under the actor, 0 on bare
     ground), HA = base + H(fA), cA = saturate((fA - 0.5) / max(fwidth(fA), 1e-4) + 0.5). Otherwise HA = 0 and cA = 0.
   - Height = max(HT, HA), continuous because H(0.5) = 0. Color = lerp(lerp(ground, color_j, cT), color_k, cA). Edges are
     antialiased only through cT and cA. Threads over a rival puddle keep their full visible radius and sit on it.
   - PIO_Height(f) = h0 * sqrt(max(0, (sqrt(f) - 0.70711) / 0.29289)) with h0 = 0.17 u, for all f >= 0 (no clamp at 1).
     For f = A (1 - r^2)^2 with A = 1 it is exactly a half-ellipsoid whose radius is the visible radius: blobs are domes and
     strokes half-cylinders. Puddle interiors (t = 1) are flat at h0 with a rounded bevel. Overlaps (f > 1) keep rising
     smoothly with no terrace.
   - Normal in table space: nTable = normalize(-dH/dx, -dH/dy, 1), H in world units, taken from the larger of HT and HA:
     the territory gradient comes from `_PIO_TerritoryHeight`, the actor gradient from forward differences of a and t at one
     actor texel.
   - Shading: `LiquidCommon.hlsl` (B1) uses the include guard `PIO_LIQUID_COMMON_INCLUDED`, is the only place that declares
     the `_PIO_*` globals, and exposes exactly: `float PIO_Height(float f);` and
     `half3 PIO_ShadeLiquid(half3 albedoLinear, float3 nTable, float thickness01, float lobes);`. Table space: x and y are
     Unity world x and y, z points out of the table toward the viewer (Unity -Z). L = normalize(-0.45, 0.6, 0.66) (key light
     from the upper left), V = (0, 0, 1), thickness01 = H / h0 (slight darkening at the meniscus foot, slight brightening
     where the liquid is thin), lobes = 1 or 2 (QualityTier). Model: Lambert wrap + strong Blinn-Phong highlight (gloss
     80-120) + a second broad soft lobe when lobes = 2 + Fresnel rim. Returns linear RGB. Overlay.hlsl and Bead.hlsl (used by their graphs)
     include this file and call only these two functions.
   - Ground: navy with subtle procedural grain (+/- 0.02 luminance) with a soft rim shadow along the arena edge. Arena
     frame (border_neon, every biome, shared PIO_ArenaFrame in CountryDistance.hlsl, no fetch): flat light grey outside
     (_PIO_OutsideColor = Palette.OutsideArena) and a thin yellow neon line just outside the edge with a soft glow on both
     sides and a slow low-amplitude pulse (docs/border_neon.json).
   - Shadows: `_PIO_ShadowOffset` = 0.12 * normalize(L.xy) = (-0.072, +0.096) u (sampling toward the light puts the shadow
     on the lower right). Ground pixel: shadow = 0.45 * smoothstep(0.35, 0.8, max_i(t_i + a_i) at w + _PIO_ShadowOffset).
     Territory surface pixel: shadow = 0.35 * smoothstep(0.35, 0.8, max_i a_i at w + _PIO_ShadowOffset). color *= 1 - shadow.
     Low tier: no shadow taps. Beads draw their own shadow ellipse at the same offset.
   - Two different colors that touch show a crease (both menisci meet, darker groove).
   - Pending pockets: diagonal stripes at 45 degrees (period 0.35 u, slow drift) in the owner's color at 55% opacity on the
     territory layer, under actors, from `_PIO_PocketMask` (512 x 512 RGBA32 linear, channel per player). Stripes have no
     relief and no gloss, so home stays identifiable (V8).
   - Palette and per-player fade through globals: `_PIO_Colors` (Vector4[4], linear), `_PIO_PlayerFade` (Vector4).
4. Composite budget (Medium): at most 7 texture fetches per pixel without actors and 12 with actors. One bilinear fetch of
   `_PIO_TerritoryHeight` (height and its precomputed gradient, so normals stay continuous) and one of `_PIO_TerritoryField`
   (owner and color); the actor field once, plus 4 forward-difference fetches (a and t) in the actor path; one shadow fetch
   of each field; one pocket fetch. The actor path runs only when max a > 0.003 (a coherent dynamic branch: actors cover a
   few % of the screen). High may use bicubic sampling and central differences. The probe logs frame times (18.2).

### 12.3 Visual elements and behaviours (who owns what is in section 20)
- Puddle (B1): the territory field. Wobble: very low amplitude (<= 0.04 u) slow noise displacement of the edge.
- Fill on return (B1): the logical grid updates instantly, the VisualMask lags: captured cells appear over
  FillDuration = 0.35 s in order of distance from the return point (a liquid wave), re-uploading and re-blurring (dirty
  rectangle only) each frame while a fill runs. Cells taken from a rival leave the rival at the same moment the wave reaches
  them. The fill starts on the Return event, together with the pearl's merge pulse.
- Evaporation on elimination (B1): the eliminated player's channel fades out over 0.6 s (`_PIO_PlayerFade`) then the
  VisualMask clears it.
- Thread (B2, ThreadView): a FieldStroke mesh along the trail (smoothed for display with Catmull-Rom, sampled every
  0.15 u, the sim trail stays exact), visible radius 0.17 u, a slight thinning just before the pearl, and a neck widened up
  to 2.2x only over the first 0.3 u from the exit point (field fusion with the puddle makes the rest of the junction).
  Elsewhere, wherever the thread is exposed, its visible half width stays within 0.03 u of TrailHalfWidth, so what visibly
  touches is what cuts. The tip always ends at the interpolated head position.
- Pearl (B2, PearlView): an analytic bead impostor (Bead graph) of visible radius HeadRadius (0.45), plus a FieldBlob neck
  (A = 1.0, visible radius 0.8 * HeadRadius) only to form the necks with its thread and puddle. Squash and stretch along
  velocity (up to 1.15 / 0.9), springy wobble on exit and turns. While trailing, the bead keeps its full round silhouette
  and is never absorbed early, even next to its puddle; the merge (bead squash 1.15 / 0.85 over 0.2 s while the neck blob
  amplitude pulses) starts exactly on the Return event, so the pearl visibly joins its puddle when the sim says home. At
  home the bead stays visible on its own puddle (V3).
- Beads (B2, Resources/Shaders/Bead.shadergraph + Bead.hlsl): pearls, droplets and splash drops are analytic bead impostors drawn at full
  resolution by the main camera after the composite: queue Transparent, Blend SrcAlpha OneMinusSrcAlpha, ZTest Always,
  ZWrite Off. On a code-built quad: q = uv * 2 - 1, alpha = saturate((1 - length(q)) * radiusInPixels) (1 px AA),
  nTable = normalize(q.x, q.y, sqrt(max(0, 1 - dot(q, q)))), color = PIO_ShadeLiquid(...). A soft shadow ellipse is drawn
  first at `_PIO_ShadowOffset`. Droplets and splash drops have no field contribution.
- Retraction = spark (B2, RetractionView): when the trail is cut, the thread is drawn only on [0, s_cut - 0.25] (the
  upstream piece ends in a pinched taper) and on [Sr, L] (the downstream piece), where Sr = GameSession.RenderSparkS (the
  same Alpha as RenderPos, so the drawn gap always equals the sim gap). The front at Sr is a teardrop FieldBlob bulb
  (visible radius 0.26) pointing toward the head with a fast jitter; a white glint flickers on it (overlay). Between s_cut
  and Sr a chain of bead droplets is left every 0.45 u (visible radius 0.07 to 0.12, deterministic per index), they shiver
  slightly. All droplets of a chain are ONE dynamic mesh (one quad per droplet with per-vertex radius and alpha), not one
  GameObject each. On a saved return the front stops where it was and the droplets are absorbed (fade 0.3 s); on a catch
  the burst plays at the pearl.
- Cut flash (B2, CutFlash): at every cut point visible on screen (any attacker, any victim), a white ring pulse blinking 3
  times over 0.6 s (overlay). Sfx and haptics per section 16.
- Home arrow (B2, HomeArrow): while the human is chased, a small chevron around the pearl pointing to
  GridQueries.NearestOwned, pulsing; the pearl pulses (scale 1.0 to 1.08 at 4 Hz), with no ring or outline. Keeps the way
  home readable.
- Spark edge indicator (B2): when the human's retraction front (at RenderSparkS) is off screen, a chevron on the screen
  edge points at it; its pulse rate increases as SparkCatchEta drops. It exposes its screen position for the tutorial
  pointer (15.4).
- Ring (B2, RingView): glossy white torus-like ring (Overlay shader with a fake normal shaded by PIO_ShadeLiquid), bob
  0.08 u, slow spin, soft halo. Charge (ChargeRing): a thin white ring orbiting the carrier's pearl, the only ring ever
  drawn around a pearl.
- Ring indicator (B2, RingIndicator): when the ring exists, is off screen and is within 24 u of the human, a small white
  ring icon on the screen edge points at it with a gentle bob. Hidden while the human is chased or charged. No text before
  the first pickup (the brief presents the lasso only at the first pickup).
- Splash (B2, SplashView): on elimination the pearl bursts into 8-12 bead drops flying out and shrinking (0.5 s).
- Exit pop: when an exit starts, the bead gets a 0.15 s squash impulse while the neck blob amplitude pulses (the drop
  detaches from the puddle).

### 12.4 Quality tiers (Render/QualityTier.cs)
High (PC default): actor field scale 0.75, bicubic territory, central differences, shadows, both specular lobes, bloom allowed.
Medium (Android default): scale 0.5, bilinear territory, shadows. Low: scale 0.35, no shadow taps, one lobe.
SaveData.Quality forces a tier; Auto uses the platform default. FPS watchdog (Auto only): ignore the first 5 s after a
session starts; step down at most once per session when the 3 s average fps is below 0.83 x min(Application.targetFrameRate
(the refresh rate when it is -1), Screen.currentResolution.refreshRateRatio.value); never step when the target is <= 30.

### 12.5 Visual acceptance (judged on player screenshots against docs/reference_gouttes.png)
V1 Puddles read as thick glossy liquid with highlight streaks on upper-left edges and a soft shadow to the lower right.
V2 Threads are round glossy tubes; where a thread leaves a puddle the junction is a smooth concave neck.
V3 Pearls are clearly beads larger than the thread, with a specular dot, visible on their own puddle too.
V4 After a cut: tapered upstream end, droplet chain (crisp beads), teardrop front moving toward the pearl, clearly unlike a pearl.
V5 Colors stay saturated (coral and teal close to the palette), background deep navy with faint grain.
V6 No aliasing staircase on puddle edges at the probe resolution (540 x 960) and on device; no visible grid blocks in
   highlights on High.
V7 The drawn front-to-pearl gap matches the sim: the front never overlaps the pearl of a player that is then saved, and the
   pearl's merge pulse starts on the Return frame (cut.png, fill.png).
V8 With a pending pocket next to the player's own puddle and over a rival puddle, home stays identifiable: the pocket has
   stripes only (no relief, no gloss), home reads as raised glossy liquid (pocket.png).

---

## 13. Input (Input/SteeringInput.cs, B3)
- Touch (Input System `Touchscreen`): floating stick anywhere on screen. dpi = Screen.dpi clamped to [120, 560], 160 when it
  reports 0. DeadZone 0.05 inch, MaxRadius 0.20 inch.
  Steering finger: the first touch that begins while no steering finger exists and whose press position hits no
  Selectable. At the press frame: `ped = new PointerEventData(EventSystem.current) { position = pos };
  EventSystem.current.RaycastAll(ped, hits);` if any hit has a Selectable on itself or a parent, that touch is ignored for
  its whole lifetime. IsPointerOverGameObject is never used (stale on the press frame). Other simultaneous touches are
  ignored until the steering finger lifts.
  On press: anchor = touch position. On move: delta = position - anchor; if |delta| >= DeadZone the desired heading
  becomes atan2(delta.y, delta.x) (screen up = world up). If |delta| > MaxRadius the anchor follows:
  anchor = position - normalize(delta) * MaxRadius. Release: keep the course (stop updating Desired).
- Mouse (PC): left-button drag works exactly like touch (same press-frame raycast rule). Hover steering arms only after the
  cursor has moved >= 8 px since the session was created or since the pause ended; then the pawn heads toward the cursor
  (direction from the human's render position projected to screen to the cursor), only while the cursor is more than 2.5 u
  (converted with the camera scale) from it. Keyboard: arrows / WASD give 8 directions. Precedence: the most recently
  active device owns Desired; a held key overrides hover until it is released; a left-button drag overrides both.
- Escape / Android back (Input System `Keyboard.escapeKey`): Playing -> GameDirector.SetPaused(!IsPaused); Results -> same as
  MENU (ToMenu); Menu -> opens the "Quitter ?" panel (15.7), on PC and Android.
- When a session starts or a pause ends (PausedChanged(false)), SteeringInput drops any active touch and re-anchors on the
  next press.
- Output: writes `GameSession.HumanController.Desired` (radians) each frame, from deliberate input only; the sim reads it at
  the next tick. While Session.AwaitingStart, the first write makes GameDirector call Begin (11.1).

## 14. Camera (View/CameraRig.cs, B3)
- Main camera created at runtime: orthographic at z = -50 looking +Z, depth 0, cullingMask = ~(1 << LiquidLayers.Field),
  clear SolidColor = the biome's OutsideArena (#B4B9C1). UniversalAdditionalCameraData: renderPostProcessing = false (LiquidRenderer sets it true only on
  High when bloom is enabled), renderShadows = false, requiresDepthOption = Off, requiresColorOption = Off,
  antialiasing = None. CameraRig updates in LateUpdate with `[DefaultExecutionOrder(100)]`.
- Visible width 18 u in portrait (orthographicSize = 9 / aspect); in landscape visible height 20 u.
- Follows the human's render position with a critically damped spring (half-life 0.12 s) plus a lookahead vector (1.2 u
  along the heading) smoothed by its own critically damped spring (half-life 0.35 s) before being added to the target.
- While the human is chased: target view width = clamp(1.15 x the width needed to contain the head, the retraction front
  (RenderSparkS) and the HomeArrow target with 1.5 u of padding, 18, 26) u, height from the aspect ratio, eased in with a
  0.25 s half-life and back to 18 u over 0.6 s after the chase. When the front is out of view even at 26 u,
  SparkEdgeIndicator takes over.
- Menu/attract: slow drift following the leading bot. Death beat (11.1): holds on the splash. Results: holds, slight zoom out.
- Clamp the camera so the view never shows more than 4 u beyond the arena edge (the composite quad covers [-40, 40]^2).

## 15. UI and UX (UI/*, B4)

### 15.1 Toolkit
uGUI built entirely from code (Canvas Screen Space Overlay, CanvasScaler reference 1080 x 1920 match 0.5, a GraphicRaycaster
on every Canvas, `InputSystemUIInputModule` on the EventSystem, never StandaloneInputModule). Text: `UnityEngine.UI.Text`
with the OFL font loaded from `Resources/Fonts` (a STATIC bold rounded font: Nunito ExtraBold/Black or Fredoka SemiBold,
downloaded from Google Fonts / fontsource as a static TTF, license text alongside); fallback
`Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf")`. No TextMeshPro. Respect `Screen.safeArea` (SafeArea.cs). Hide
screens by toggling their Canvas/CanvasGroup, not the GameObject. Every non-interactive Graphic (labels, toasts, tutorial
bubbles, vignette, indicators, leaderboard rows) has raycastTarget = false, so only Selectables block steering (13). Every
HUD text has a navy shadow (#151D38, alpha 0.7, 3 px at reference resolution) so it stays readable over a puddle of the
same color.

### 15.2 Menu
Title "Painter IO" in big rounded letters (coral, slight glossy look via outline/shadow), attract match running behind.
Color picker: 4 round swatches (the human's color, Palette.HumanColor). Big "JOUER" button. Small buttons: Options, best
score line ("Meilleur : 34 % · 5 victoires", from SaveData). Options panel: Son on/off, Vibrations on/off, Bonus lasso
on/off (default OFF in this v0.1 prototype: the brief asks for the first Revanche trial without lasso spawns, then turning
them back on; the choice is saved), Langue FR/EN, Qualité Auto/Haute/Moyenne/Basse, and a version label. Five taps on the
version label reveal a hidden "Réglages de test" section: Vitesse étincelle 1,4 to 2,4 step 0,1 (default 1,8), Durée de
manche 60 / 90 / 120 s, Délai anneau 10 to 30 s step 5 (default 15), Réinitialiser (SaveData test settings, 11.5). When any
value differs from Tuning, Results show a small "réglages modifiés" tag.

### 15.3 HUD (Playing), mirrors the reference image
Top bar: left = human area in the human color; center = countdown "01:30" in light text; right = best rival area in that
rival's color. Area labels show one decimal below 10 % ("3,4 %", EN "3.4%") and whole numbers above. The human's label
counts up over FillDuration in sync with the fill and pops (scale 1.15 for 0.2 s); on each capture >= 0.1 %, a "+2,1 %"
text in the human's color rises from the return point for 0.8 s. In the last 10 s the timer pulses (Sfx ticks, 16).
Pause button: round "II" icon, 96 px at reference resolution, top-left inside the safe area just below the area label, 60 %
opacity. The rival label is a Button that toggles a compact 4-row leaderboard below the top bar (collapsed by default);
pause and this Button are the only tap targets of the top bar.
Toasts (center-top, 1.6 s): "Lagon a été éliminé", "Tu as coupé Safran !", "Ton étincelle a eu Safran !" (Eliminated with
Cause Spark and Other == human), "Lasso prêt !", and the saved line (15.5). One toast is visible at a time, the queue holds
2 and drops entries older than 3 s; while the human has a spark, only toasts about the human are shown. Danger vignette
pulsing (white/red edge) while the human is chased.

### 15.4 Tutorial (TutorialOverlay)
Saved flags (SaveData.TutExitDone, TutCutDone, TutLassoDone).
- Step 0 (first 3 rounds, while Session.AwaitingStart): hint "Glisse ton doigt pour diriger" (EN "Swipe to steer") with an
  animated hand tracing an arc in the lower third; it hides on Begin.
- First round, after Begin: bubble "Sors de ta couleur et reviens pour agrandir ton terrain." until the first capture
  (then TutExitDone = true).
- First time the human's trail is cut: "On a coupé ton trait ! Rentre avant l'étincelle pour sauver ta boucle.", shown with
  the first-cut slow motion (11.1). The bubble has a pointer anchored on the retraction front (on the SparkEdgeIndicator
  when the front is off screen) for as long as it is shown. It hides when the human is eliminated. TutCutDone is set only
  when the human returned home while chased, or when the bubble stayed visible for >= 2.5 s of real time.
- First ring pickup only: "Lasso ! Recroise ton fil pour enfermer une poche, puis rentre." (then TutLassoDone = true).
Never repeat a step whose flag is set.

### 15.5 Results
Shown by GameDirector only (results flow in 11.1): after the 1.0 s death beat when the human is eliminated (the background
match keeps playing), or after 0.6 s when the round ends with the human alive. ResultsScreen reads GameDirector.LastOutcome
only; it never waits for Simulation.Result and never updates the rank later. Buttons ignore input for 0.5 s after the
panel appears.
- Big rank: "1er", "2e", "3e", "4e"; shared "Ex æquo 1er" / "Ex æquo 2e" (EN "1st", "2nd", "3rd", "4th", "Tied 1st").
- Final area of the human (for an eliminated human: FinalCells, the area just before elimination).
- Cause line and the WHY line that makes the Revanche learnable (brief section 7.7):
  - saved (alive at the end after a chased return): "Rentré 0,4 s avant l'étincelle !" (one decimal, from Return.Margin), or
    "Sauvé de justesse !" when Margin < 0.05 s. The same text is the toast shown during play, only for a Return with
    Chased = true.
  - caught: "Lagon t'a coupé : rattrapé à 2,3 m de chez toi." (attacker from SparkCaught.Other, distance from
    SparkCaught.DistanceHome).
  - territory lost: "Ton dernier morceau de terrain a été pris."
  - time up: "Temps écoulé."; last survivor win: "Dernier survivant !"; all eliminated: "Éliminés au même instant".
- Stats line: "7 captures · 2 coupes · 1 élimination · 1 poche · 1:12" (Captures, CutsMade, Kills, PocketsMade,
  SurvivedSeconds).
- Buttons: "REJOUER" (starts a new round immediately, new seed) and "MENU". Stats are saved by GameDirector (11.1).

### 15.6 Strings (Game/Strings.cs)
`Strings.Get(string key)` with French and English tables, `Strings.Language` backed by SaveData.Language. Every visible
text goes through it. Decimal comma in French ("0,4 s"), point in English. Keys added in v1.1 include: pause.title,
pause.resume, pause.restart, pause.menu, quit.title, quit.yes, quit.no, hint.steer, toast.spark_kill, results.saved_close,
results.last_survivor, results.all_eliminated, results.stats, results.tuning_modified, options.test_settings.

### 15.7 Pause and quit panels (UI/PausePanel.cs, inside UiRoot)
Pause panel (shown while GameDirector.IsPaused): navy dim at 60 %, title "Pause", buttons "REPRENDRE" (SetPaused(false)),
"RECOMMENCER" (StartRound) and "MENU" (ToMenu), plus toggles Son and Vibrations. Quit panel (Menu, Escape/back): "Quitter ?"
with "OUI" (Application.Quit) and "NON".

## 16. Audio and haptics (Audio/*, B5)
Procedural clips synthesized at startup (no audio assets): exit plop (droplet detach), return gloop + fill swell, cut snap
(sharp, bright), spark tension loop while the human is chased whose pitch and rate rise as SparkCatchEta drops, caught
splat, ring chime, lasso zip, toast tick, UI click, countdown tick (last 10 s, one per second), win and lose jingles.
Volume and mute from SaveData.SoundOn; muted in batchmode and with `-mute`.
Scope: events where the human is Player or Other play at full volume. Bot-only events (Exit, Return, Cut, Eliminated) play
only when their point is on screen, at -12 dB, at most one per type every 0.25 s; the cut snap plays on every on-screen cut,
louder for the human's cuts. The spark tension loop plays only for the human's own chase. In Menu (attract) and after the
human's elimination, only UI sounds play, plus on-screen events at -18 dB. The win or lose jingle plays once when Results
appear.
Haptics: `Haptics.Pulse(int ms)` never throws. It is compiled under `#if UNITY_ANDROID && !UNITY_EDITOR` (no-op elsewhere)
and returns at once when SaveData.HapticsOn is false. It uses the Android Vibrator through AndroidJavaObject
(VibrationEffect when API >= 26); every JNI call is wrapped in try/catch and the first failure logs once and disables
haptics. Haptics.cs contains an unreachable reference inside a method that is called (`static bool s_NeverTrue;` ...
`if (s_NeverTrue) Handheld.Vibrate();`) so Unity adds android.permission.VIBRATE (Builder also checks it, 17). Durations:
human cut received 60 ms, human cut dealt 30 ms, caught 120 ms, saved return while chased 40 ms, capture 20 ms.

## 17. Builder and project settings (Editor/Builder.cs, B0)
```csharp
public static class Builder {
  public static void SetupAndCompile();  // settings + scene + ShaderCheck, exit code 0/1 in batchmode
  public static void BuildWindows();     // Build/Windows/PainterIO.exe, verifies the file exists, exit code
  public static void BuildAndroid();     // Build/Android/PainterIO.apk, IL2CPP ARM64, minSdk 25, portrait, exit code
  public static void BuildAll();
}
```
SetupAndCompile: names layer 31 "LiquidField" in TagManager, writes Scenes/Main.unity (camera-less scene with one
GameObject "Game" + GameDirector; cameras are created at runtime by CameraRig/ActorFieldCamera), sets it as the only build
scene, sets PlayerSettings (product "Painter IO", company "PainterIO", portrait, Windows windowed 540 x 960 resizable,
no splash if allowed, Android package com.painterio.game, IL2CPP + ARM64, Vulkan then GLES3), uses the PC_RPAsset for
Windows and Mobile_RPAsset for Android quality levels, sets PC_RPAsset requireDepthTexture = false and
requireOpaqueTexture = false and Mobile_RPAsset supportsHDR = false, runs ShaderCheck. In batchmode always exit explicitly
(`EditorApplication.Exit(code)`); a build that reports success must also produce the file.
BuildAndroid records EditorUserBuildSettings.activeBuildTarget and its group before building and calls
SwitchActiveBuildTarget back to them afterwards, on success and on failure (as in games/out_of_sight/Assets/Editor/Builder.cs).
Builder.cs also contains, under `#if UNITY_ANDROID`, an IPostGenerateGradleAndroidProject that ensures the generated
unityLibrary/src/main/AndroidManifest.xml contains `<uses-permission android:name="android.permission.VIBRATE"/>` (inserts it
if missing and logs it); BuildAndroid fails if the permission is still absent. Runtime platform code uses
`UNITY_ANDROID && !UNITY_EDITOR`.

## 18. Verification

### 18.1 PlayMode tests (Tests/PlayMode)
Boot test: load Main scene (or instantiate GameDirector), wait 120 frames of WaitForFixedUpdate-independent real
frames, assert: no exception logged, GameDirector state Menu, LiquidSurface material has a supported shader, HUD/menu
texts non-empty, ActorField RT exists. StartRound, call Session.Begin(), then simulate 3 s: sim time advanced, human
controller writable.

### 18.2 Player probe (Probe/PlayerProbe.cs, runtime assembly)
Activated by `-probe`. Options: `-shotdir <dir>`, `-fps <n>` (Application.targetFrameRate = n, vSync off), `-mute`.
The player always runs windowed, never with -batchmode or -nographics:
`PainterIO.exe -probe -shotdir <d> -fps <n> -mute -screen-width 540 -screen-height 960 -screen-fullscreen 0 -logFile <log>`.
The probe session uses TickRate 60 whatever -fps is, starts with AwaitingStart = false, and drives every scenario change
exclusively through Simulation.BeforeTick (handlers key on the integer Tick), scripted controllers and SimSetup
(ForcedRingPos). Frame code only reads: a screenshot is taken in the first rendered frame with Tick >= its target tick,
with ScreenCapture.CaptureScreenshot, then a realtime wait (5 s max) for the file plus 0.2 s, with SimRunner.Paused during
the wait.
Sequence (deterministic, independent of frame rate):
1. Menu screenshot `menu.png` after 2 s.
2. Scripted demo round: the human exits, draws a loop, a bot cuts the loop near the origin, the human returns in time
   (capture). Then a second exit: the human, charged through DebugSetCharged in a BeforeTick handler, closes a lasso pocket
   next to its own puddle and over a rival puddle; then a bot cuts right behind the human and the spark catches it.
   Screenshots at fixed ticks: `thread.png` (thread out), `cut.png` (droplet chain visible), `fill.png` (mid fill),
   `pocket.png` (pending pocket), `results.png`.
3. Checks: every shader from Resources/Shaders loads, isSupported and has the `_PIO_ShaderId` property; no renderer without
   material; font not null; all visible UI texts non-empty; ActorField RT created; captured area increased at the first
   return; a LassoPocket event in the second exit; the human was eliminated by Spark in the second exit; every screenshot
   has at most 0.2 % magenta pixels (r > 0.85, g < 0.15, b > 0.85) and at most 98 % of its pixels of one color; zero
   exceptions/errors in the log.
4. Prints `[ProbeHash] <hex>` (Sim.StateHash at the scenario end) and `[ProbeResult] PASS` or `FAIL <reasons>`,
   then quits with exit code 0 or 1. The verify script runs it at `-fps 30` and `-fps 144`: both hashes must be equal.
5. Then a 20 s bot-controlled normal round (the human driven by a BotController) to catch runtime exceptions; it prints
   `[ProbePerf] avgMs=<x> p95Ms=<y> tier=<t>`.

### 18.3 What tests can and cannot prove
Editor tests cannot see stripped shaders, missing fonts or Awake exceptions in a player: the probe on a built player is
mandatory before declaring anything done, and screenshots must be looked at. Brief 7.7 is a human check (18.5).

### 18.4 tools/verify.ps1 (owned by A1 for the Core part, extended by B6)
Steps, each with a clear PASS/FAIL line and a non-zero exit on failure: dotnet Core tests; Unity SetupAndCompile; EditMode
(refuse 0 tests); PlayMode (refuse 0 tests); BuildWindows; probe at -fps 30 and -fps 144 (PASS + equal hashes + no
exception in the player logs); optional `-Android` builds the APK, always as the LAST step. Summary written to
`docs/verify_last.txt`.

### 18.5 Device playtest (manual gate for brief 7.7; B6 prepares it, the user runs it)
Install the Android APK on a phone. Run 3 rounds with lasso spawns off, then 3 rounds with them on (brief closing
paragraph). Observer checklist after the first cut received: (a) the player looks or points at the retraction front within
1 s; (b) the player turns toward home; (c) after the round, the player explains why they survived or died, matching the
WHY line. With lasso on: the bonus enriches trajectories and home stays identifiable. Answers are recorded in
`docs/playtest_7_7.md` (template written by B6). No agent may mark 7.7 as passed: Gate B reports it as PENDING_HUMAN.

## 19. Unity pitfalls checklist (paid for on previous projects)
- `Shader.Find` shaders are stripped in players: Resources only (12.1).
- TextMeshPro needs imported essentials: we use uGUI Text with a font asset.
- An exception in Awake cancels the rest of Awake: one try/catch per subsystem.
- `StandaloneInputModule` throws with the Input System: use `InputSystemUIInputModule`.
- Disabling a GameObject kills its coroutines and replays OnEnable: toggle Canvas/CanvasGroup instead.
- Batchmode builds return 0 on failure unless you exit explicitly; check the output file exists.
- A test run with 0 tests exits 0: always read the JUnit counts.
- Destroy is deferred to end of frame: when tearing down a session, unsubscribe events first and use DestroyImmediate
  only in edit mode.
- URP ignores `QualitySettings.shadowDistance` and light shadow bias (irrelevant here: no URP lighting).
- Render targets: actor field = GraphicsFormat.R16G16B16A16_SFloat when SystemInfo.IsFormatSupported(it,
  GraphicsFormatUsage.Blend), else R8G8B8A8_UNorm with `_PIO_ActorScale` = 0.25 (contributors multiply by it, the composite
  divides); otherwise `_PIO_ActorScale` = 1. Territory field and height: R16G16B16A16_SFloat when IsFormatSupported(it,
  GraphicsFormatUsage.Render), else R8G8B8A8_UNorm with no scaling (values are in [0, 1]; the height channel stores H / h0
  and gradients remapped to [0, 1] in that case). All masks and RTs are linear (created by GraphicsFormat; Texture2D with
  linear: true), Bilinear, Clamp, no mips, no depth. The actor RT is reallocated when its computed size changes (window
  resize or QualityTier change), then reassigned to camera.targetTexture and Shader.SetGlobalTexture, and the old one
  released. Texel sizes are published explicitly (`_PIO_ActorTexel`, `_PIO_TerritoryTexel`), never read from automatic
  `_TexelSize` of globals.

## 20. Packages, ownership and waves

Wave A (Core, pure C#):
- A1 foundation: Math/*, World/*, Grid/CellMask.cs, every other Core file as a compiling STUB with the exact public
  signatures (bodies throw NotImplementedException; this includes CellEntry, GridRaster.TraverseFrom and CountInterior,
  SelfCrossing, Trail.SelfCrossings, LassoGeometry.IsValidPocket(OwnerGrid, ...), PlayerState.Cell and Kills, Spark.PrevS,
  SimEvent.Chased, SimSetup.ForcedRingPos, Simulation.EndTick, BeforeTick, EventCapHits and RankOf, BotPersonality
  ReactionDelay / SenseRadius / HumanAttackScale), tools/CoreTests/*, tools/verify.ps1 (Core steps), Tests for Math/World.
- A2 grid: Grid/OwnerGrid.cs, GridRaster.cs (incl. TraverseFrom, CountInterior), CaptureSolver.cs (section 7 one-flood
  implementation), GridQueries.cs + their tests (C1-C7, raster tests, GR-Edge).
- A3 trail: Trail/*.cs (FirstContact algorithm of 5.4, SelfCrossings, LoopErase, LassoGeometry) + their tests.
- A4 sim: Sim/*.cs, Controllers/ScriptedControllers.cs + rules tests (R ids) + scenario tests S1-S6 under the 10.0 protocol.
- A5 bots: Bots/*.cs + bot tests (section 9 targets, invariants), preset values in 5.7.
- A6 rules auditor (after A2-A5): adversarial edge-case tests against the brief; fixes go back to owners. The contract's
  readings (R8) are not reopened without the user's approval.
- Gate A: dotnet + Unity EditMode green, report.

Wave B (Runtime):
- B0 skeleton: Game/GameDirector.cs (incl. HumanOutcome, pause, slow motion, ready gate, results flow, frame settings),
  GameSession.cs, SimRunner.cs, SaveData.cs (11.5), View/Palette.cs, View/LiquidLayers.cs, Editor/Builder.cs,
  Editor/ShaderCheck.cs, stubs for every other Runtime entry class, PlayMode boot test, EditMode Runtime test S4-Display.
- B1 liquid render: Render/*.cs, Resources/Shaders/LiquidComposite.shadergraph + LiquidComposite.hlsl, FieldBlob.shader, FieldStroke.shader,
  TerritoryBlur.shader, LiquidCommon.hlsl (each .hlsl with its fixed-GUID .meta), DefaultVolumeProfile check.
- B2 actors: Actors/*.cs (incl. RingIndicator.cs), Resources/Shaders/Overlay.shadergraph + Overlay.hlsl (rings, chevrons, glints, flash) and
  Bead.shadergraph + Bead.hlsl (pearls, droplets, splash drops).
- B3 input + camera: Input/SteeringInput.cs, View/CameraRig.cs (main camera creation and settings, section 14).
- B4 UI: UI/*.cs (incl. PausePanel.cs), Game/Strings.cs, Resources/Fonts/*.
- B5 audio: Audio/*.cs.
- B6 probe + verify: Probe/PlayerProbe.cs, tools/verify.ps1 (player steps), Android build check, docs/playtest_7_7.md
  template (18.5).
- Gate B: verify.ps1 full, screenshots reviewed against 12.5; brief 7.7 reported as PENDING_HUMAN.

Wave C: multi-lens critique (rules, feel, visuals, robustness, mobile) with adversarial refutation, then a fix wave by owner.

## 21. Changelog v1.1

Each line names the review finding(s) applied.
- Header and precedence: version v1.1; contract readings (R8) are decided and not reopened without the user (rules-10).
- Head cells: PlayerState.Cell, CellEntry, GridRaster.TraverseFrom with inclusive [0, uMax] entries and a single diagonal
  step at corner ties; home transitions come from the visit list plus a state check at uCur; FirstEntry kept for bots and
  tests only; TraverseSegment includes cells entered at u = 1 and resolves corner ties as x-neighbour then diagonal; R5, R7
  rewritten on the current cell; test GR-Edge (algo-01, rules-01).
- Section 6 parameter convention: full tick segments, tick-u everywhere, uTrailEnd, L_i(u), own-u geometry and group time,
  end-of-tick append and Pos at p(uEnd) (algo-02).
- SparkCatch in closed form with the epsilon shift u_c = max(uCur, u0 + eps/dt), valid across tick boundaries; spark S
  never accumulated; invariant tolerance 1e-6 (algo-03).
- Pickup by contact intervals (entry and exit events, re-test at uCur) and the event-cap rule (EventCapHits, stop then step
  3); R15 clarified; contested-ring tests extended (algo-04, rules-02).
- Group application re-validates every candidate (steps b-f), elimination is idempotent, a returner whose cell is taken by
  a simultaneous returner starts an exit; uCur = uG after a group; test R18b (algo-05, rules-03, rules-12).
- FirstContact exact algorithm (exposure-induced contacts, parallel motion), s_cut defined by FirstContact (closest exposed
  point), attacker attribution for simultaneous cuts, constructor check on HeadGrace (algo-06, rules-04).
- Geo.ProperIntersect half-open rule; LoopErase smallest-index rule; known near-loop limitation documented (algo-07).
- Trail.SelfCrossings (all crossings, sorted) replaces FirstSelfCrossing; first VALID crossing counts; minArc checked at
  L(u_X); LoopPolygon before the append; IsValidPocket by non-zero-winding cell count (GridRaster.CountInterior)
  (algo-08, rules-13).
- Section 10.0 cross-rate protocol (TurnRate 0, schedule times on multiples of 1/6 s, cell-center lines, definition of
  identical outcomes, DebugSetTrail state, S4 timing choice); HeadingSchedule switching rule (algo-09).
- Time = Tick / (double)TickRate, EndTick and the last-tick uEnd rule (algo-10).
- Simulation.BeforeTick, SimSetup.ForcedRingPos, probe driven only through them at TickRate 60 (algo-11).
- Capture one-flood implementation, new budgets (3 ms desktop, 8 ms Android), FirstContact 5 us, scanline RasterPolygon,
  bot test 50 seeds in dotnet / 10 in Unity (algo-12).
- RasterPolygon and C1 test tolerances and sizes (algo-13).
- R1 decides the permanently neutral rim band (algo-14).
- R11/R19 FinalCells before the eliminating group, DistanceHome before Neutralize, competition ranking, Simulation.RankOf
  (rules-05).
- Spark.PrevS, GameSession.RenderSparkS, front drawn at Lerp(PrevS, S, Alpha), pearl merge only on the Return event, V7
  (rules-06).
- S4-Display test through SimRunner at two display frequencies (rules-07; the extra probe tie screenshot was not added,
  the EditMode test covers brief 7.4).
- Section 18.5 device playtest gate (PENDING_HUMAN) and the first-cut bubble pointer (rules-08).
- Missing rule tests R9b, R11b, R12b, R13b, R15b, R16, R17b, R19b and a non-tautological S6 (rules-09).
- R8 interpretation note, test C7, S1 non-crossing curve (rules-10).
- Lasso runtime default OFF, adjustable 90 s / 1.8 / 15 s through hidden test settings and Windows command-line overrides,
  V8, pocket.png in the probe (rules-11, feel-18).
- SimEvent.Margin = (L - S) / SparkSpeed, SimEvent.Chased, "Sauvé de justesse !" (rules-14, feel-13).
- Thread neck widening limited to the first 0.3 u and exposed visible half width tied to TrailHalfWidth (rules-15, partial:
  the thick enclosure raster was rejected).
- CutFlash on every on-screen cut, haptic for cuts dealt (rules-16).
- HomeArrow pearl pulse instead of a white outline; ChargeRing is the only ring around a pearl (rules-17).
- All game shaders are hand-written URP HLSL .shader files, exact field contributor blend state, Shader Graph not used
  (unity-field-shaders-not-shadergraph, unity-shadergraph-authoring-pitfalls).
- FieldBlob / FieldStroke mesh conventions, LiquidLayers.QuadMesh, SupportForVisibleRadius clamp
  (unity-field-mesh-vertex-contract).
- Composite rewritten: territory and actor layers, continuous height, fwidth antialiasing (unity-composite-dominance-holes-cliffs).
- ActorFieldCamera execution order and world-rectangle sampling with margin (unity-actor-field-registration).
- Main and actor camera settings, culling masks, RP asset settings, static composite quad and queues
  (unity-camera-setup-culling-depth).
- PIO_Height half-ellipsoid curve without terraces (unity-height-curve-terraces).
- Bead impostors for pearls, droplets and splash drops, one mesh per droplet chain, Bead.shader owned by B2
  (unity-small-actors-need-impostors).
- LiquidCommon.hlsl guard, globals and exact function signatures, table space (unity-shade-liquid-signature-and-space).
- ShaderCheck strengthened, _PIO_ShaderId marker, magenta and flat-image screenshot checks, windowed probe command line,
  screenshot wait, V6 resolution (unity-verification-false-green).
- Frame settings in GameDirector.Awake and a watchdog relative to the target frame rate; render scale cap, sleep timeout
  and ProbePerf (unity-android-30fps-cap-breaks-watchdog, feel-04; the app icon request was not added).
- Territory blur at 512 with 5 taps, height texture, scissored command buffer passes (unity-territory-reblur-cost).
- Composite fetch budget (unity-composite-tap-budget).
- Press-frame RaycastAll for UI touches, raycastTarget off on non-interactive graphics, steering finger ownership, dpi clamp,
  smaller leash (unity-ui-touch-steers-on-press-frame, feel-07; the optional anchor visual was not added).
- VIBRATE permission (Handheld reference + Builder manifest check), Haptics never throws, events forwarded after Step with
  per-subscriber try/catch, haptic durations (unity-android-vibrate-permission, feel-12).
- Shadow offset toward the light, exact shadow formula (unity-shadow-offset-direction).
- BuildAndroid restores the build target, Android step last (unity-android-build-target-restore).
- RT formats by GraphicsFormatUsage, linear, clamp, reallocation, explicit texel sizes (unity-rt-formats-and-lifecycle).
- Pause API, pause panel, quit panel, Escape / Android back, OnApplicationPause (feel-01).
- SaveData API (11.5) and Palette.HumanColor / ColorIndexOf, names follow displayed colors (feel-02).
- Results flow: GameDirector only caller, death beat, HumanOutcome, rank strings, cause lines, stats line, new seed per
  round (feel-03; the live standings table was not added).
- Ready gate: GameSession.AwaitingStart and Begin, steer hint step 0 (feel-05).
- First-cut slow motion and hit-stops (GameDirector.SlowMo), toast queue rules, SimEvent.Other per type, PlayerState.Kills,
  attacker named in the caught line (feel-06).
- Bot attack aims at lethal cut points (feel-08).
- Bot excursion plan from the territory edge, return target fallback, round-time trigger, safe ring definition (feel-09).
- Bot preset values, ReactionDelay, SenseRadius, HumanAttackScale, stronger asserted targets and reported feel metrics
  (feel-10, partial: the escapable-cut, trailing-share and human-proxy targets are reported, not asserted).
- RingIndicator and the ring spawn preference near the human (feel-11).
- Mouse hover arming and device precedence (feel-14).
- HUD decimals, count-up, capture gain text, last 10 s pulse, text shadow, pause button and leaderboard Button (feel-15).
- Smoothed lookahead and chase framing (feel-16).
- Audio scope and priorities (feel-17).

## 22. Changelog v1.2 (main loop)
- Shader Graph restored for LiquidComposite, Bead and Overlay (thin graphs, logic in .hlsl Custom Functions with fixed-GUID
  .meta files, _PIO_* globals declared only in LiquidCommon.hlsl, per-object data through vertex attributes). FieldBlob,
  FieldStroke and TerritoryBlur stay hand-written HLSL because Shader Graph cannot express their blend state or procedural draw.
  Per-graph fallback to a .shader of the same name, never both. ShaderCheck covers both kinds. Reason: the user explicitly chose
  URP + Shader Graph; the v1.1 arbiter dropped it believing nobody had asked for it.

## 23. As-built amendments v1.3 (normative from wave B on)

### 23.1 Wave A deviations accepted into the contract (see docs/waveA/gate.json for details)
- 5.1 Geo.ProperIntersect also applies its 1e-12 |b1 - b0| rounding band to the moving segment's END: an end inside the band
  counts as reaching b's line at a1 (ta = 1, tb = projection of a1). Trail.SelfCrossings, LoopErase and BotSenses all call it.
- Section 6 rounding windows (kept as implemented): on the last tick, visit entries up to uEnd + 1e-9 are clamped to uEnd; a
  catch with t_c in (RoundDuration - eps, RoundDuration] fires at uEnd in the TimeUp group; pickup contact bounds are shifted by
  eps / dt for simultaneity; step a drops a return whose own u is strictly after its own SparkCatch candidate in the same group.
- Section 6 readings by A4: the step-a stolen-home exit applies only when the current cell was taken by a capture of that group;
  step c re-validates the victim's Trail.Version; a mid-tick round end freezes the state at uG; eliminated players get Home = true
  and Pos at the elimination point; random rings keep the whole ring disc inside the arena; SimEvent.Margin is clamped at 0; the
  round's player count is controllers.Length.
- 5.4 / R11 sCut = the closest exposed point of each PASS in contact (subdivision independent), largest arc among passes.
- Section 7 step (iii) may be a multi-source scanline span fill (same reachable set).
- 10.1 RasterPolygon full-raster tolerance: exact counts for axis-aligned squares, 5 % from side 7.25 u or for rotated squares.
- Versions: CellMask.Version and OwnerGrid.Version increment on content changes only; RasterPolyline / RasterPolygon add to their
  output and never clear it; OwnerGrid.Set(index, Void) throws. Arena.Step takes the outward normal at p0 + d.
- Section 9 readings by A5 (kept): uncharged bots detour to avoid crossing their own trail; E skips holes shorter than 1 u;
  AttackChance drawn once per enemy exit; 0.1-0.6 s home dwell; final presets Balanced MinOut/MaxOut/MaxTrailLength 4.5/10/34,
  Greedy 5.5/13/45, others as in 5.7.

### 23.2 Decisions applied in wave B by package A7 (Core amendments)
- D1 Rim (section 7 step 5) uses 8-adjacency: TrailCells 8-adjacent to an Interior cell. It removes the stair notches on
  diagonal edges that made a head gliding along its own edge flicker Exit/Return at about 30 Hz. A bare back-and-forth line still
  has no Interior, so it still captures nothing (C2 unchanged).
- D2 PlayerState.Captures counts only Returns whose Cells.Length > 0. The Return event is still emitted for every return.
- D3 R4 hold: before holding, Arena.Step advances along the desired displacement up to the inset line (clamped), so a held head
  stops on the inset line whatever the tick rate (within 1e-9 u).
- D4 Tangency exactly at a tick end (half-open rule vs brief 5.2) stays as a known limitation: it needs lattice-aligned scripted
  paths with TurnRateDeg 0 and cannot happen in play.

### 23.3 Wave B integration notes
- Exit/Return debounce for presentation: views, sounds, haptics, toasts and HumanOutcome ignore an exit whose Return has empty
  Cells and that lasted < 0.25 s. The pearl detach animation and the exit plop start only when the trail length exceeds 0.35 u
  or the exit has lasted 0.25 s; the merge pulse and return sound play only for a Return with Cells.Length > 0 or after a
  visible detach. The fill wave plays for every Return with cells.
- Bot seeds: seed_i = roundSeed * 7919 + i * 104729 + 17 (one BotController per bot player). CreateRound lineup players 1..3 =
  Balanced, Greedy, Aggressive; CreateAttract lineup players 0..3 = Balanced, Balanced, Greedy, Aggressive.
- Windows player scripting backend Mono (fast iteration builds); Android IL2CPP ARM64.
- B0 provides `Runtime/Game/DemoScenario.cs` (the scripted demo round of 18.2 step 2 as a reusable SimSetup + controllers +
  BeforeTick hooks, with named checkpoint ticks: ThreadOut, CutDroplets, MidFill, PocketPending, Caught) and
  `Runtime/Probe/DevShot.cs` (command line `-devshot <dir> [-fps n]`: plays DemoScenario in the real game view and saves one PNG
  per checkpoint plus menu.png, then quits). B1, B2 and the visual polish agent iterate with Builder.BuildWindows + DevShot and
  LOOK at the PNGs (Read tool) next to docs/reference_gouttes.png. B6's PlayerProbe reuses DemoScenario.

## 24. Rule change v1.4 (decided by the user, overrides the brief and every older section)

The user changed La Revanche on 2026-11-26: "lorsque l'on s'est fait couper son fil, et qu'on arrive a revenir chez soi, on reste en
vie, mais par contre on ne gagne pas la zone qu'on venait d'entourer, et qui a ete coupee." This replaces brief 4.4 "Tout le gain est
conserve" and brief 7.2 "La surface prevue est alors entierement capturee".

- R13 (rewritten above): a chased return (the player has a spark at the return instant) SURVIVES and CAPTURES NOTHING. In section 6
  step a, a returner with a spark gets an empty capture set (CaptureSolver is not called for it), its pending pocket is cleared without
  being validated, and it claims no cell in the R18 conflict rule. The Return event is still emitted with Chased = true, Margin as
  before and Cells = an empty array. D2 already keeps such a return out of PlayerState.Captures.
- R17: "Returning home captures pocket + ordinary capture" now applies only to an UNCHASED return. A pocket made before or during a
  chase is lost if the player is cut before returning. A lasso during a chase is allowed but cannot pay off.
- Tests: S2 becomes "a cut near the trail origin while the victim is almost home: the victim wins the race, survives, and its
  territory is exactly unchanged (no planned area captured, Return.Cells empty, Chased, Margin > 0)". R13b keeps its order assertions
  and now also asserts Return.Cells is empty when Chased. Add R13c: a charged lasso pocket, then a cut, then a saved return: pocket
  erased, rival cells inside it keep their owner, no capture. Add R13d: an unchased return in the same scenario still captures (control).
  S4 cases keep their saved / eliminated / saved outcomes. Every other test that expected a chased return to capture is updated to the
  new rule (never by weakening an unrelated assertion).
- Bots (section 9): every cut now has value (it denies the victim's capture), not only lethal ones. Attack rule: prefer a lethal sample
  (probability AttackChance, as before); otherwise a DENIAL cut on the largest reachable exposed s_k when the victim's trail length is
  >= 6 u, with probability AttackChance x 0.6 (Aggressive: x 1.0). A chased bot still goes straight home to survive. A5's asserted
  targets stay; retune presets if needed and report.
- Presentation (wave B-2 and C): the first-cut tutorial line becomes "On a coupe ton trait ! Rentre avant l'etincelle pour rester en
  vie." (EN "Your thread was cut! Get home before the spark to stay alive."), with the proper French accents in Strings (coupé,
  étincelle). The saved WHY line and toast become "Rentré 0,4 s avant l'étincelle : boucle perdue." / "Sauvé de justesse : boucle
  perdue." (EN "Home 0.4 s ahead of the spark: loop lost." / "Saved by a hair: loop lost."). On a saved chased return there is no fill
  wave: the remaining thread pieces and the droplet chain dissolve into small evaporating beads (0.4 s), the pearl merges, a soft
  "loop lost" sound plays instead of the fill swell, and the human gets the 40 ms haptic. The HUD shows no "+x %".

## 25. Biomes v1.5 (requested by the user: "d'autres types de structures que le cote aqueux liquide... le feu, comme ca se repand...
## ou aussi l'electricite. Essaye deja d'ajouter ces trois types de biomes differents.")

### 24.1 As-built notes of the v1.4 change (A8 + verifier, 2026-11-26)
- R14 across tick boundaries: a spark spawned less than EventEpsilonSeconds before its owner's return instant counts as a cut at
  closure: in step a the spark is removed, the attacker's CutsMade credit is taken back, and the return is unchased (captures). The Cut
  event already raised in the previous tick stays in the log (rare, rounding-sized).
- Bots: the denial cut replaces the v1.3 Aggressive-only harassment cut. Presets: Greedy and Aggressive ThreatRadius = 8 (was 4.5 / 5).
  BotController.DenialMinTrail = 6.0, DenialScale = 0.6, DenialScaleAggressive = 1.0.
- DemoScenario (B0a) must be rebuilt for v1.4 by BI: first a clean capture WITHOUT a spark, then a saved chase with empty Cells, then the
  pending pocket, then the fatal cut. DemoScenarioTests and SfxTests follow it (3 Unity Runtime tests are red until then).
### 25.1 Concept
A biome is a complete visual and audio theme for a round. Three biomes: Liquide (id 0, the look of section 12, default), Feu (1),
Électricité (2). The rules, constants and the whole PainterIO.Core are IDENTICAL in every biome (no Core change). The player picks the
biome in the menu (three cards with name and a small animated preview); SaveData.Biome (int, default 0) remembers it; the attract match
behind the menu uses the selected biome and switches as soon as a card is chosen. Command line `-biome liquid|fire|electric` overrides
(probe, devshot, tests). The field architecture of 12.2 (territory field, actor field, field contributors, fill ordering, pocket mask) is
shared; a biome changes only shading, beads, overlays, extra effects, palette, fill timing and sounds.

### 25.2 Architecture (binding)
```csharp
public enum BiomeId { Liquid = 0, Fire = 1, Electric = 2 }
public sealed class BiomeTheme {                       // Runtime/View/BiomeTheme.cs
  public BiomeId Id; public string NameKey;           // Strings keys biome.liquid / biome.fire / biome.electric
  public string CompositeShader;                      // "LiquidComposite" | "FireComposite" | "ElectricComposite"
  public string BeadShader;                           // "Bead" | "FireBead" | "ElectricBead"
  public string OverlayShader;                        // "Overlay" | "FireOverlay" | "ElectricOverlay"
  public Color[] PlayerColors;                        // 4 sRGB colors, index = palette index (Palette.ColorIndexOf still applies)
  public Color Ground, OutsideArena, UiAccent;
  public float FillDuration;                          // Liquid 0.35, Fire 0.60, Electric 0.25 (seconds)
  public bool BloomOnHigh;                            // Fire and Electric true (emissive look), Liquid as section 12
  public static BiomeTheme Current { get; }           // set by GameDirector when a session starts (SaveData.Biome or -biome)
  public static BiomeTheme Get(BiomeId id);
  public static event Action<BiomeTheme> Changed;
}
public interface ISfxClipSet {                        // Runtime/Audio/ISfxClipSet.cs; one implementation per biome
  BiomeId Biome { get; }
  AudioClip Exit { get; } AudioClip Return { get; } AudioClip Fill { get; } AudioClip Cut { get; } AudioClip TensionLoop { get; }
  AudioClip Caught { get; } AudioClip LoopLost { get; } AudioClip Ambient { get; }   // Ambient may be null (Liquid)
  void Build(int sampleRate);                         // synthesized at startup, no audio assets
}
public static class BiomeFx { public static Component Create(GameDirector d); }   // Runtime/Biomes/BiomeFx.cs: hosts the
                                                      // current biome's extra effects component (LiquidFx / FireFx / ElectricFx)
```
Hooks (every view reads BiomeTheme.Current, never a hard-coded shader name or color): LiquidSurface loads CompositeShader; PearlView,
RetractionView droplets and SplashView use BeadShader with the SAME vertex data (vertex color = player color linear, uv1.x = radius,
alpha); CutFlash, RingView, ChargeRing, HomeArrow and the indicators use OverlayShader with the same shape ids; TerritoryField uses
FillDuration; Palette.ColorOf returns the current theme's PlayerColors; Sfx plays the current ISfxClipSet (UI sounds shared); the HUD
uses UiAccent for the timer and highlights; LiquidRenderer enables bloom on High when BloomOnHigh. On BiomeTheme.Changed every view
re-binds its materials without a restart.
New shared data for fronts (TerritoryField, all biomes): `_PIO_RevealTime` (512 x 512 RHalf world texture: the Time.timeSinceLevelLoad
at which each cell was last revealed or changed owner visually, -1000 for cells present at session start) and `_PIO_Now` (float), so a
composite can draw a moving front (liquid ripple, fire front, electric crackle) where the reveal is recent.
Every composite variant reads the same globals as LiquidComposite and must keep: one color per player, actors above territory, same-color
fusion at necks, pending pocket stripes readable and distinct from home, antialiased edges, the 12.2 item 4 fetch budget, and a soft
contact shadow or glow that separates layers.

### 25.3 Feu (fire)
- Ground: charred dark stone and ash (#1A1412 to #241A16), faint cooled cracks; outside the arena the shared light grey #B4B9C1 past the yellow neon line (border_neon, was #100C0B).
- Player flame colors (chemical flames, readable): 0 orange-red (#FF5A2A, hot core #FFD08A), 1 copper green-teal (#22E0B8), 2 gold
  (#FFC21F), 3 potassium violet (#B472FF).
- Territory: a bed of glowing embers in the player's flame color: interior = coals (animated cellular noise, slow breathing pulse, dark
  crust between cells); edge = a band of live flames, animated domain-warped noise tongues licking outward with a slight bias toward
  screen up, emissive and additive-looking.
- Thread: a burning fuse: a thin dark cord with small flames running along it. Pearl (FireBead): a fireball, white-yellow core, flickering
  corona, a few embers shed while moving (FireFx particles).
- Fill (the spreading the user likes): fire spreads over the captured area as a bright flame front leaving fresh embers, over 0.60 s,
  driven by `_PIO_RevealTime`.
- Cut (La Revanche): the fuse is lit: a white-hot spark (bright overlay sparkle on the retraction bulb) races along the fuse toward the
  head; the burnt part behind it becomes the droplet chain drawn with FireBead as embers that cool from orange to grey ash over 1 s, with
  small smoke puffs (FireFx). A saved chased return (v1.4, no capture): the remaining fuse burns out into ash and smoke.
- Elimination: the territory burns out to smoking ash (PlayerFade + smoke), the fireball bursts into sparks. Pocket stripes: glowing ember
  stripes without flames. Sounds: soft crackle ambience, whoosh on fill, fuse hiss tension loop rising in pitch, pop on exit, burst on catch.

### 25.4 Électricité (electricity)
- Ground: very dark blue-black (#0B0F1E) with a faint hexagonal circuit grid that lights up softly near territories; outside the shared light grey #B4B9C1 past the yellow neon line (border_neon, was #070912).
- Player neon colors: 0 neon red-pink (#FF4D6D), 1 cyan (#2EF2FF), 2 electric yellow (#FFE84D), 3 violet (#A974FF).
- Territory: an electrified plasma field: interior = neon surface with a slowly flowing hex or circuit pattern; edge = a bright neon rim
  with crawling micro arcs (jagged animated noise) and occasional small lightning arcs hopping along the border.
- Thread: a live wire: thin white-hot core, jagged lightning offset flickering at 15-20 Hz, colored glow halo. Pearl (ElectricBead): a
  plasma orb with crackling filaments; small arcs jump to its own territory when within 1.5 u (ElectricFx).
- Fill: a crackling discharge spreads over the captured area as branching lightning from the return point (0.25 s), then the hex pattern
  pulses once.
- Cut: a packet of current (white-blue bright pulse with a short glow tail) races along the wire toward the head; behind it the wire is
  dead: the droplet chain drawn with ElectricBead as fading spark dots on a dim grey cable. Saved chased return: the dead wire fizzles out.
- Elimination: short circuit: the territory flickers and blacks out, the orb explodes in sparks. Pocket stripes: dashed neon. Sounds: low
  hum ambience, zap on cut, crackle burst on fill, rising buzz tension loop, discharge on catch.

### 25.5 Readability and budgets (all biomes)
The four player colors stay clearly distinguishable; home, pending pocket and rival territory stay identifiable; during a chase the
retraction front / spark / current packet is the brightest moving thing on screen; HUD layout is unchanged (accent color only). Flames,
arcs and patterns are procedural in the composite (same fetch budget as 12.2 item 4); extra particles are capped at 200 per biome and use
code-built meshes or ParticleSystem with materials from the biome's Overlay shader. Quality Low may drop animated noise octaves.

### 25.6 Packages (wave B-2)
- BI "biome infra" (phase 1): BiomeTheme.cs, ISfxClipSet.cs, Biomes/BiomeFx.cs + Biomes/LiquidFx.cs, the hooks above in the existing
  Render / Actors / UI / Audio / Game files (their B-1 owners are finished; BI is their owner for these edits), SaveData.Biome, the menu
  biome cards, Strings keys, `-biome` handling in GameDirector / DemoScenario / DevShot, `_PIO_RevealTime` / `_PIO_Now`, the liquid
  ISfxClipSet (moved out of the existing Sfx code), and the v1.4 presentation of section 24 (texts, saved-return dissolve, loop lost sound).
- B6 "probe and verify" (phase 1, contract 18 and 20), with screenshots for each biome.
- FIRE (phase 2): FireComposite.shadergraph + .hlsl, FireBead.shadergraph + .hlsl, FireOverlay.shadergraph + .hlsl (thin graphs, fixed-GUID
  .meta), Biomes/FireFx.cs, Audio/FireSfx.cs.
- ELEC (phase 2): the same with Electric*.
- LIQ (phase 2): liquid visual polish (LiquidComposite, Bead, Overlay, LiquidCommon) against V1-V8.
- Gate B (phase 3): full verify, probe in the three biomes, APK, screenshots reviewed against 12.5 and 25.5.

## 26. Wave C as-built amendments (v1.6, normative from wave C on)

Wave C (docs/waveC/fix_plan.json, seven fix packages and the final gate, reports docs/waveC/<package>.json and docs/waveC/gate.json)
changed presentation, rendering cost, audio and tooling only. The Core is untouched: the probe hash stays 246577239DE179C4 at every
frame rate and in every biome. Where this section and an older section disagree, this section wins; the older text stays for history.

### 26.1 Platform finding: the Shader Graph forward pass is target 2.0
- The URP Unlit Shader Graph target generates ONE subshader whose Universal Forward pass is `#pragma target 2.0` on every platform
  (only its GBuffer pass is 4.5). SHADER_TARGET is therefore 20 in every composite, bead and overlay forward pass, on Windows as on
  Android, and code guarded by `PLATFORM_SUPPORT_GATHER && SHADER_TARGET >= 45` (FireComposite's PIO_FIRE_GATHER, the Gather
  reveal ages and the Gather relief normal) never runs. The bilinear fallback is what ships everywhere; the Gather paths are kept as
  dead code for a future target 4.5 forward pass. No contract text may count on Gather in a Shader Graph composite.
- Plan shader rule 4 and 12.2 item 4 read: "the forward pass of every graph compiles for Direct3D 11 AND for GLES3". The EditMode
  tests WaveC_FireGraphsCompileOnEverySubshader and WaveC_OwnedGraphsCompileOnEverySubshader compile every forward pass for both
  GLES3x (Android) and D3D (Windows), base variant. ShaderCheck still compiles only the editor's API.
- Every ddx / ddy / fwidth and every implicit-LOD sample stays outside dynamic branches; inside a `[branch]` only LOD 0 samples are
  allowed (the WaveC_*KeepDerivatives* / *NoDerivative* tests parse every branch body of the biome shaders).

### 26.2 Rendering (12.2, 12.3, 12.4, 19, shader globals)
- 12.4 render height cap per tier: Medium 1600 px, Low 1280 px, High none (1920 px on Android, as 11.1). In the player only (never in
  the editor) LiquidRenderer sets the active URP asset's renderScale = cap / Screen.height when the screen is taller than the cap,
  else 1, at creation, on a tier change and when Screen.height changes, and logs `[PainterIO] render scale <s> (tier <t>, height <h>)`.
  GameDirector's 11.1 Android 1920 px cap stays (same value on High, now redundant).
- 12.2 item 2 / 19 actor field: RT size = view size x ppu x tier scale, where ppu comes from the RENDERED height (main camera
  pixelHeight x URP renderScale clamped to 0.1 - 1), rounded up to the 32 px RtQuantum.
- 12.4 watchdog: a frame longer than max(0.1 s, 4 frame budgets) resets the 3 s window and is not counted; only real rounds (never the
  attract) in the Playing state are measured; only a non-attract session start re-arms the one step. The rest of 12.4 is unchanged
  (5 s warm-up, 3 s window, 0.83 x target, never when the target is <= 30, at most one step per session).
- Shader globals (LiquidCommon.hlsl, B1 table): `_PIO_Time.x` = unscaled seconds since the current session started (reset on every
  GameDirector.SessionStarted: round start, REJOUER, menu return, attract restart), wrapping at 4096 s (LiquidRenderer.ShaderTimeFor).
  It was app time wrapped at 1024 s.
- 12.3 Retraction glint (actors): a white glint of 0.5 u half size (RetractionView.GlintHalfSize, the cross-package value the biome
  overlays are designed for) whose opacity flickers at 15 Hz between 0.8 and 1.0 (never below 0.7), over a soft halo in the front
  color (overlay shape 1, 1.2 u half size, opacity 0.35); both sort in the overlay batch (queue 3004) above droplets, threads and
  pearls. Fire and electric shape 3 receive the parameters (0.22, 0.3, 0.08); liquid passes (0.4, 0.36, 0.1).
- 12.3 Home arrow: a chevron of constant screen size (half size 0.62 u x CameraRig view scale, center 0.65 u x view scale from the pearl
  rim, pulsing +15 %), drawn as a halo disc in the human color (alpha 0.45, 1.3 x the half size), a navy drop shadow offset
  (0.05, -0.05) u x view scale at alpha 0.6, then an OFF-WHITE chevron (linear 0.78, about sRGB 229) so that only the spark reaches
  the brightest pixels during a chase (25.5). ActorContext gains ViewScale (CameraRig view scale of the frame, fallback 1). A biome
  overlay never raises a shared view's chevron albedo above its own brightness (ElectricOverlay shape 2 fill capped at 0.8 linear).

### 26.3 Biomes (25.2 - 25.5)
- 25.3 Fire flame band: laid out in world units from the wide relief field (d = sigma x inverse normal CDF of max t_wide, sigma
  0.267 u). Outward tongues reach 0.3 u on edges facing screen down and 0.85 u on edges facing up, +75 % while the fill gate is on;
  reach capped at 0.9 u on Medium and High and 0.55 u on Low. Inward tongues burn over the outer 0.42 - 0.5 u of the bed. The
  cellular coal mosaic, the flameless pocket stripes and the four distinct colors are kept.
- 25.2 / 25.3 Fire fill front: the flash exp(-age / 0.045) becomes a moving band. A Gaussian of the age centred at 0.08 s (width
  0.08 s, zero after 0.3 s) only gates a white-hot band placed from the contour (about 0.14 u inside) plus taller tongues; ages are
  clamped (0.4 s band, 0.8 s warm embers), jitter at most 0.05 u. FillDuration 0.6 s, TerritoryField and the -1000 sentinel unchanged.
- Fire tiers (12.2 item 4): the tier split reads _PIO_Quality. High: B-spline territory, 3 x 3 animated coals, 3 flame octaves.
  Medium: bilinear, 2 x 2 animated coals (same coal identities), 2 octaves. Low: 2 x 2 static jittered Voronoi coals (never
  thresholded value noise), 2 octaves on one warp, no owner or glow tap, no cracks. Twinkle per coal and per third of a second on every
  tier. Medium fetch budget: 7. Expensive layers run in coherent dynamic branches (coals where cT > 0, flames inside the band, reveal
  and owner tap within 1.2 u of a bed, cracks under a sparse mask).
- 25.5 Fire spark: FireOverlay shape 3 draws a solid white disc of radius 0.12 u (pale corona to 0.17 u) over a saturated orange halo
  #FF8A2A (radius 0.45 u, alpha 0.8) with rays 1.5 x longer. High keeps the HDR boost for bloom. Below High FireBead caps the fireball
  body and corona at linear luminance 0.7, keeping the hue, so the spark stays the brightest moving thing for every player color.
- 25.5 FireFx: the advancing fill front throws up sparks (42 per second, life 0.25 - 0.5 s, at most 4 fills); the live fuse front keeps
  at most 20 live sparks. Both stay inside the 200 cap.
- 25.4 Electric fill: "a crackling discharge of branching lightning rides the advancing front of the fill from the return point
  (0.25 s), then the hex pattern pulses once". The band sits about 0.14 - 0.8 u behind the contour (wide relief field); the clamped
  reveal age (0.4 s) only gates it. It no longer floods the whole fresh area.
- 25.4 Cut / 25.5 Electric: the dead-cable spark dots (ElectricBead small beads) peak at 1.1 x the player color and never clip to
  white; the current packet has a 0.8 opacity white-blue halo and a head quad of 1.2 x 0.69 u (1.5 x), falling off 2.25 x faster ahead
  so it never runs past the front; the electric glint (shape 3) is a 0.1 u solid white center in a white-blue core that stays below
  sRGB luma 235 without bloom.
- Electric and liquid composites: ground and territory shading run in `[branch] if (cT < 1)` / `if (cT > 0)` with color =
  lerp(ground, surface, cT) unchanged; micro arcs in their own branch; hex lines use an analytic AA width; fetch counts unchanged.
- Liquid crease: the contact of two puddles of different colors is a soft dark groove (crease width from the gap across one relief
  texel, flat-lit groove darkened by 0.25, relief gradient clamped to h0 / (2 pix)); no isolated bright specks.
- 25.5 measurement rule: luma-threshold readability checks are taken with the human color pinned to palette index 0 (SaveData
  ColorIndex), because a saturated electric yellow alone reaches luma 236.

### 26.4 UI (14, 15.1 - 15.5)
- 15.1: CanvasScaler reference 1080 x 1920, screenMatchMode EXPAND (was match 0.5). The whole design box is visible at every aspect:
  portrait screens taller than 9:16 get a canvas 1080 wide and taller than 1920, landscape and square screens one 1920 high and wider.
  The menu cards sit in a CardRow (962 wide) that scales down only when the safe area is narrower than 994 units.
- 14 / 15.2 menu attract: the drift is shown zoomed out at view scale CameraRig.AttractZoom = 1.4. Only the selected biome card's
  preview animates (15 repaints per second); unselected cards show a still frame on an opaque face. A soft navy scrim (alpha 0.45,
  60-unit feathering) sits behind the Biome label, cards, color label and swatches. A navy AttractCover fades the ended attract board
  to 0.85 over 0.5 s, seals to opaque just before the 2 s restart, and fades the new match in (no single-frame pop).
- 15.3 toasts: a toast is never scaled below 0.85; a line too long for one row wraps to two lines. With the leaderboard open it moves
  centered below the board (and below a visible tutorial bubble, read through TutorialOverlay.BubbleRect / BubbleAlpha). The rival
  chevron is alpha 0.9, 28 x 18, with a navy outline (layout unchanged, 25.5 holds).
- 15.5 results (presentation only): navy dim 0.86, cause and WHY paragraphs 880 units wide, lines stacked from their measured heights so
  an empty WHY line leaves no gap. Texts unchanged.
- Menu on screens taller than 9:16 (gate C): the title moves down by half of the extra canvas height (MenuScreen.TitleYFor,
  TallTitleShare 0.5), so the band between the title and the 'Biome' label is split above and below it; 9:16, landscape and square
  screens keep the Gate B position.
- Landscape (Windows dev mode) draws the UI at scale 0.375 (the whole box must fit 720 px); nothing is cropped.

### 26.5 Tutorial, flow and power (11.1, 11.5, 15.4, 15.6)
- 15.4 new step: after the human crossed its own trail without a charge (LassoCrossNoCharge; nothing is shown at the crossing), the
  first UNCHASED return shows the bubble tut.selfcross ("Recroiser ton fil ouvre ta boucle : rentre sans le recroiser pour tout
  peindre." / "Crossing your own thread breaks the loop: come home without crossing it to paint it all.") for 4.0 s of visible time,
  without pointer, priority Cut > Lasso > SelfCross > Exit. A chased return drops the pending lesson; a new exit cancels a pending
  lesson and hides the bubble once it has been visible for 2.5 s; SparkCaught and Eliminated cancel both. SaveData.TutSelfCrossDone is
  set once the bubble stayed visible for 2.5 s; never repeated once set, at most once per round.
- 15.4 TutCutDone: "visible for >= 2.5 s of real time" means wanted (not paused, not in the ready gate, not in the death beat), its text
  shown and faded in (alpha >= 0.95). Hidden time does not count (TutorialOverlay.CountsAsVisible). The 5 s lasso bubble timer still
  runs while hidden (accepted: TutLassoDone is saved at the pickup).
- 11.5: `public static bool TutSelfCrossDone { get; set; }` (key pio.TutSelfCrossDone) and the test-only `MemoryOnly` scope (setters
  update the cache without writing PlayerPrefs). TutorialOverlay reads and writes the four Tut flags.
- 11.1: Screen.sleepTimeout = NeverSleep only while Playing and not paused, SystemSetting otherwise (the pause panel, also after an
  automatic pause, lets the screen sleep). On Android without -fps, Application.targetFrameRate = 30 while paused, 60 restored when the
  pause ends and at StartRound / ToMenu. Windows keeps vSync.
- 15.6: new key tut.selfcross in both tables. Dev aid: `-uidemo selfcross` forces the bubble (screenshots only).
- Public static helpers instead of internal (TutorialOverlay.CountsAsVisible, GameDirector.SleepTimeoutFor returning int, since
  SleepTimeout is a class of int constants). PainterIO.Runtime now declares InternalsVisibleTo("PainterIO.Tests.EditMode").

### 26.6 Audio and haptics (16, 25.2, 25.4)
- 16 haptics: "caught 120 ms" also covers the human's elimination by territory loss. A spark death pulses once on SparkCaught, a
  territory-loss death once on Eliminated; a bot's elimination pulses nothing.
- 25.2 ISfxClipSet: all three clip sets are synthesized at startup, the current biome's synchronously and the two others on worker
  threads through the additive ISplitSfxClipSet (Synthesize pure C# and thread-safe, BuildSlot on the main thread, at most one
  AudioClip per frame; SfxSlot, SfxClipSamples). Build(rate) equals BuildSlot over Synthesize(rate). A set picked before it is ready is
  finished at once. The 25.2 interface signature is unchanged; its comment "Sfx calls Build once, the first time the biome is used"
  is obsolete.
- 16 loudness budget (binding, enforced by WaveC_AudioTests): every clip loses at most 4 dB (loops 6 dB) of K-weighted loudness over
  its loudest 100 ms through a 400 Hz 24 dB/oct high-pass (phone speaker model), and the win and lose jingles stay within 3 dB of each
  other on full range and on that model.
- 25.4 "low hum ambience": the Electricite hum is a 120 Hz buzz with 240 - 960 Hz partials (was 50 Hz mains harmonics).

### 26.7 Builder, settings and verification (17, 18.4)
- 17: PlayerSettings.runInBackground = false (PlayerProbe, DevShot and RenderLab set Application.runInBackground = true at runtime;
  a scripted plain-player launch must focus the window). Android: PlayerSettings.Android.blitType = Auto and optimizedFramePacing =
  true (ProjectSettings androidBlitType 2, androidUseSwappy 1).
- 18.4: verify.ps1 gains the opt-in step `perfslope` (registered, never in the default order): release probe -quality medium -fps
  1000 -mute windowed at 1080 x 1200 and 540 x 600 per biome, -PerfRuns interleaved rounds (default 2), slope = (best avgMs big - best
  avgMs small) / 0.972 ms per Mpix; FAIL when fire/liquid > 1.6 or electric/liquid > 1.4, when a run fails, the tier is not Medium or
  the probe hashes differ. Serialized across agents by Logs/perfslope.lock; each run waits for no other PainterIO.exe and no
  .unity.lock and a shared run is retried (240 s quiet wait, 2 retries, 30 min budget). The numbers only mean something on a quiet
  machine. The full gate runs `verify.ps1 -Android -KeepGoing` and then `-Steps perfslope`.
- Reference slopes on the dev laptop (Iris Xe, quiet machine, ms per Mpix, Medium, uncapped, best of 3 rounds, gate C final build):
  liquid 2.14, fire 2.66, electric 2.36 (Gate B build measured the same day, best of 2: liquid 2.24, fire 4.77, electric 3.14).
  Fire / liquid must stay <= 1.6 and electric / liquid <= 1.4. The small 540 x 600 size is noisy (up to x 1.5 between rounds); the
  1080 x 1200 avgMs is the steadier number (final: liquid 3.22, fire 3.90, electric 3.44 ms).

### 26.8 Accepted residuals and open decisions
- Electric fill (visuals-reveal-age-staircase residual): one hard cell-aligned cut remains where the discharge band meets older
  territory near each junction of a new area (about 35 px at 1080 width, during the 0.3 s fade). Removing it needs four point fetches
  of _PIO_RevealTime (beyond 12.2 item 4) or a reveal texture of saturating ages (a 25.2 change). Accepted as is for v1.6.
- Liquid per-pixel cost (perf-06): the branches are correct and visually neutral but give no measurable gain on Iris Xe; a real gain
  needs cheaper ground shading (woven grain) or fewer fetches, which touches V1 - V8 and the fetch budget. Deferred.
- Small hard-edged fire flame fragments can appear for one frame at a thread / bed neck during a fill (1080 High only). Accepted.
- User decisions still open (docs/waveC/fix_plan.json user_decisions): feel-01 (longer slow motion and a "cut right behind you"
  results line, would amend 11.1 and 15.5) and feel-11-standings (final standings list on the results screen). Deferred to after the
  device playtest: rules-03 (doomed pocket presentation, with the lasso back on), feel-08 home edge indicator, feel-13 predefined
  haptic effects, perf-03 persisted tier, shader warm-up, perf-04 smaller bolt quads.

### 26.9 Wave B readings folded (accepted at Gate B, listed in docs/waveB/*.json contract_issues)
- A7 / A8 / 24: 23.2 D1 - D3 and section 24 override the older text of section 7 step 5 (8-adjacent rim), section 6 step a (no
  Captures++ and no pocket validation for a chased returner), R4 / 5.2 (a held head first advances to the inset line), R7 and 10.1 S2.
  Section 24's attack rule fully replaces the v1.3 Aggressive-only harassment; lethal and denial are drawn once each per enemy exit.
  Presets: Greedy and Aggressive ThreatRadius = 8 (the 5.7 / 23.1 table is superseded). AuditTests R19 "counts" means ranked alive.
- B0a / 11.2: the attract session replaces its Simulation and SimRunner in place and raises GameSession.Restarted; GameDirector
  re-raises SessionStarted with the same session, so views read Session.Sim / Runner every frame or rebind on SessionStarted.
  HumanController is also null in scripted sessions (DemoScenario, probe), HumanIndex stays 0. SetPaused is refused outside Playing,
  in attract, once the human is eliminated, the round ended or the results beat started. LaunchArgs reads on every platform.
- B0b / B1 / 19: _PIO_ActorField carries a 16-bit depth buffer (URP 17 Render Graph draws nothing into a camera target without one);
  command buffer RTs have none. ShaderCheck warms URP up with one camera render and fails when the active subshader is not tagged
  UniversalPipeline or its pass count differs. BuildAndroid runs with -buildTarget Android (the Gradle callback inserts VIBRATE), checks
  the APK manifest and switches back to StandaloneWindows64.
- B1 / LIQ 12.2 liquid look: shadows from the relief field at 1.5 x _PIO_ShadowOffset (ground 0.70 x smoothstep(0, 0.72, t_wide + a),
  puddle 0.42 x rival actors, contact darkening 0.14, 0.32 on Low); relief from a second blur (total sigma 0.26 u) with slope gain 1.7;
  PIO_ShadeLiquid gloss 130 plus an area-light streak term and an inner second streak; actor fusion fA = a_k + t_k + a_k t_k and the
  leveled own-puddle height of LIQ.json; actor normal gT + (dHA - dHT); a soft vignette (up to 16 %) and a woven grain on the exact
  palette ground; the ripple rides the advancing edge from the wide relief field and the reveal age only gates it. Fetch budget Medium
  7 / 11 (without / with actors), Low 5 / 9.
- B2 12.3: a saved chased return dissolves the thread and droplet chain into evaporating beads (0.4 s); bead alpha edge centered on
  the true radius (+0.5 px); the drawn bulb is pulled back within 0.03 u of the pearl rim; after an unchased return the thread follows
  the fill rule (cell time = Return.Time + FillDuration x d / dMax).
- B3 13 / 14: one view scale for portrait (18 x s) and landscape (20 x s), s in [1, 26/18]; the chase view contains head, front and home
  target with 1.5 u padding; exact critically damped spring (damping 1.678347 / h); hover takes Desired back only after 8 px of motion;
  hover keeps the course over a Selectable; SteeringInput runs at DefaultExecutionOrder(-200).
- B4 15: only Selectables are raycast targets (modal dims included); 15.4 step 1 shows after Begin in every real round while
  TutExitDone is false; tutorial flags are written only by CountsForStats sessions and never in batch mode; the toast queue drops the
  oldest entry; French uses the typographic apostrophe and singular for 0 and 1; one decimal below 10.0 %; French "28 %", English
  "28%"; attacker names from Strings + Palette. The 15.4 / 15.5 lines are those of section 24.
- B5 16: the plop and the gloop follow 23.3 sentence 2; the ring chime plays at 0 dB on the human's pickup and softer (-12 dB, pitch
  0.84) on RingSpawned; bot lasso events are silent; cut snaps are exempt from the 0.25 s limit (0.05 s duplicate guard); a chased
  return that captured gives one 40 ms pulse; Sfx.PlayToastTick() is called by the HUD.
- B6 18.2 / 18.4: [ProbeHash] after the demo, then the 20 s bot round and [ProbePerf], [ProbeResult] last; probe shots menu, thread,
  fill, cut, saved, pocket, caught and results.png (checkpoints added later are captured by name); verify runs probe-fire and
  probe-electric at -fps 60 with the liquid hash; stricter checks (biome shaders required, FallbackError fails, LegacyRuntime font
  fails, paint guard >= 0.3 % of the biome color).
- BI 25.2: _PIO_RevealTime and _PIO_Now use the visual clock of the fill waves (Time - (1 - Alpha) x Dt) from a rolling epoch rebased
  every 16 s (reveals older than 30 s become -1000); only the front age is meaningful. BiomeTheme.SetCurrent(BiomeId, force);
  SecondaryColors, Bloom settings and ShaderParams with matching globals declared in LiquidCommon.hlsl.
- FIRE / ELEC 25.3 / 25.4: FireBead classifies a bead by radius and stretch (>= 0.28 u fireball, small stretched spark, small round
  ember); FireFx draws the ember cooling as an ash overlay from RetractionView's public statics. ElectricFx draws the dead grey cable as
  one strip under the droplets; orb arcs jump when the orb rim is within 1.5 u of an own cell; the short-circuit flicker is 9 Hz at
  half contrast over 0.6 s; overlay shape ids 6 - 15 are reserved for biome effects.
- Gate B: the actor RT size is rounded up to a multiple of 32 px; droplet radius grows with the chain index (0.07 - 0.085 next to the
  cut, about 0.11 after 9 droplets); the tutorial bubble and pointer fade out on a cubic curve.

## 27. Biome traits (v1.7, user decision)
docs/BIOME_TRAITS.md is normative and part of this contract: modular gameplay traits (Core/Traits/<Id>Trait.cs, one file per trait),
one default biome -> traits table (BiomeTraitTable), each trait switchable individually (hidden test settings matrix, -trait <Id>=0|1),
all traits off with "Règles classiques" / -classic (bit-identical to the classic simulation: probe hash 246577239DE179C4 unchanged).

## 28. User feedback for wave D (v1.7)
docs/WAVE_D_FEEDBACK.md is normative and part of this contract: F1 a real logo (variants per biome, app icons), F2 the liquid looks like a
DROP (domed thick body), F3 electric bases crossed by small arcs like the live wire. The logo wordmark waits for the user's choice of the
game name (Painter IO or a new name from docs/naming brainstorm); until then the logo work is not started.

## 29. Rule v1.5: severed territory (v1.8, designer decision, overrides older sections where they disagree)

The designer, 2026-11-27: "lorsque on coupe le domaine d'un ennemi, la partie dans laquelle l'ennemi n'est pas ne lui appartient plus
(pour le moment, il se retrouve avec deux parties de domaines non contigues)". A core rule (id R21), not a biome trait: "Règles
classiques" keep it. Code: Core/Grid/TerritorySplit.cs (pure analysis) and EventResolver.StepReturns (section 6 step a); tests:
Tests/EditMode/Core/SeveredTerritoryTests.cs (R21_*).

R21 Severed territory. When the captures of one section 6 step a group take cells from a living player (the victim) and leave its
territory in separate pieces, the victim keeps only one piece of each territory that was split; the other pieces of that split are
severed: they become neutral (default) or the cutter's, see the option below.
- Who: every living player that loses at least one cell to another player's capture in the group (human and bots alike, any player
  index). Every path that takes cells from a living rival goes through step a: the ordinary capture, the lasso pocket validated at the
  return, cells added by a trait's AugmentCapture (Coalescence fills only neutral holes), and the ReturnsBeforeRoundEnd path. No trait
  takes cells from a living rival elsewhere: Propagation grows into neutral cells only, KillInheritance moves the cells of a dead victim,
  ScorchedEarth only marks cells. Eliminations are not transfers and never sever.
- Connectivity: 8-adjacency (the territory connectivity dual to the 4-connected outside flood of section 7, where own cells touching at
  a corner already close a capture, and the adjacency of the D1 rim). Cells touching only at a corner are one piece.
- Which pieces are judged: only the pieces produced by this split. With Lost = cells the victim lost to other players in the group,
  Gained = cells it gained in the same group (only when it also returned), pieces = 8-connected components of its cells after the
  captures, and pre-transfer territories = 8-connected components of (its remaining old cells + Lost): two pieces are in the same split
  group when one pre-transfer territory spans both. A group of one piece is untouched. Islands that were already separate before
  (inherited land, the far side of an older split under Off) touch no Lost cell and are never judged.
- The anchor (the piece kept in a group), read on the grid BEFORE the captures of the group: the pawn's current cell at uG when the
  victim owns it (a home victim, or a victim returning at this instant); a home victim crossing out at this very instant: the last own
  cell of its visit list (the cell it is leaving); a trailing victim: the cell it left home from, i.e. the cell it owns among the cells
  whose closed square contains Trail.Points[0] (the exit point lies on that cell's edge, R5; lowest index if several). When the anchor
  cell is in a piece of the group, that piece is kept; otherwise (the anchor cell was captured, or the anchor is on another island, or
  the exit cell was lost earlier) the LARGEST piece of the group is kept (most cells, ties: the piece holding the lowest cell index).
- A piece holding Gained cells (the victim's own simultaneous capture, R18) is never severed. The kept piece never loses a cell, so a
  split never eliminates anyone (R9 eliminations come only from captures).
- Option `SimConfig.SeveredTerritory` (`SeveredTerritoryRule`, api addition): `Neutral` (default) severed cells become plain neutral:
  never scorched (a ScorchedEarth scorch still running on such a cell is forgotten), capturable, open to Propagation and Coalescence;
  `Capturer` they go to the cutter; `Off` the pre-v1.5 behaviour, bit-identical (every pinned hash of the v1.7 Core reproduces).
- The cutter of a group: the lowest-index returner of the group that took a Lost cell of that pre-transfer territory.
- Order inside step a: captures written (R18 conflict rule first), Return events, then the severance (every victim analysed on the
  grid left by the captures, then every change written, so with Capturer a cutter that is itself a victim is judged on its own land),
  TerritorySevered events, then the R9 stolen-home exits, then the TerritoryLost eliminations. The anchor rule guarantees that no home
  player's current cell is severed, so the R9 check is unchanged.
- Event (api addition, appended at the END of SimEventType, value 16): `TerritorySevered`: Time = the group time, Player = the victim,
  Other = the cutter, `SimEvent.Recipient` (new field, -1 for every other event) = the player that received the cells (= Other with
  Capturer) or -1 when they became neutral, Cells = the severed cells (ascending). One event per victim and cutter, victims ascending,
  then cutters ascending.
- Score, percentage, leaderboard, ranks and the round end read OwnerGrid counts (CountOf, AreaPercent, RankOf, EndRound), so they see
  the new owners at once. The Runtime needs no handler: TerritoryField reconciles every cell whenever Grid.Version changes (dirty
  rectangle uploads), so severed cells leave the victim's color on the next frame (no fill wave, no evaporation fade; a presentation
  for TerritorySevered, for example a fade or a toast, is optional future work). The HUD and the camera read the counts every frame.
- Determinism: the result depends only on the grid, the captured cells and the anchor (fixed scan order, union-find with lowest-index
  roots); the flood stops as soon as every frontier seed joined one piece (a bite that splits nothing explores only around the bite);
  buffers are pooled per thread and grid size (stamped, never cleared per call). Outcomes, severed cells and grids are identical at 30,
  60 and 144 Hz (R21_SameOutcomeAndGridAt30_60_144Hz); StateHash is unchanged in structure (the option is not hashed: equal states give
  equal hashes).
- Edge cases: a victim whose home cell is captured gets its R9 stolen exit AND keeps the largest piece; a trailing victim keeps the
  piece of its exit cell even when its pawn is far away; a victim that loses everything is eliminated by R9 exactly as before (no
  piece, no severance); two simultaneous cutters of the same territory: the lowest index is the cutter (and the recipient with
  Capturer); a victim split in two places in one group gets one event per cutter.
- Coalescence: its hole filling runs inside the capture (AugmentCapture), before the split; a hole made of severed cells inside the
  returner's land is filled at its next unchased return (Coalescence counts pre-existing holes).
- Pinned values: the classic rolling hash 8CB763231AC73608 and the seven pre-trait bot round hashes of TraitsClassicTests hold
  exactly with `SeveredTerritory = Off`; with the default, six of the seven changed (every round that contains a split; seed 1 is now
  C042710F17995DCB) and both columns are pinned in TraitsClassicTests (docs/severed.json lists them). The probe hash
  246577239DE179C4 is unchanged: the scripted demo contains no split (checked headless with DemoScenario under Off, Neutral and
  Capturer, classic and the three biome sets).

## 30. Rule v1.6: single domain and kill inheritance bridge (v1.9, designer decision, overrides older sections where they disagree)

The designer, 2026-11-27, about the Feu kill reward (KillInheritance): the conquered land "should be considered yours and part of
your domain, but if you go from your previous domain to the conquered one, it don't close the loop, worse, the line you make to
kill the enemy should be turned into a line of your domain (not only as a line), so that your domain stay connected, otherwise you
have 2 parts of your domain, which is against the rules (your domain must be one single domain)". Id R22. It belongs to the
KillInheritance trait path (docs/BIOME_TRAITS.md 7.3): classic rounds, Liquide and Électricité are untouched. Code:
EventResolver (StepKillRewards, JoinInheritance, BuildBand, ApplyBand, KeepReturnersWhole, WithTrailFootprint),
Core/Traits/InheritanceBridge.cs (the kill line and its band), TerritorySplit.KeepOnePiece / GainAttached (Core/Grid), Trail
Epoch / Dropped / DropPrefix; tests: Tests/EditMode/Core/Traits/InheritanceBridgeTests.cs (R22_*). Report: docs/inherit_fix.json.

Why the loop did not close (pre-v1.6): KillInheritance wrote the victim's cells for the killer without looking at where they lie,
so the inherited land B was an island next to the killer's land A (contract 29 even listed inherited land among the islands rule
v1.5 never judges). A trail from A into B IS a return (R5: B's cells are own), but section 7 takes walls = A + B + trail, and a
trail that only joins two pieces encloses nothing: no Interior, hence no Rim (CaptureSolver returns the pocket only), so the trail
was dropped (R8 / C2: a bare line captures nothing) and the domain stayed in two pieces. Nothing turned the kill line into land.

R22 Single domain. In a round where KillInheritance is enabled with Share > 0 and `SimConfig.InheritanceBridge` is not Off
(Simulation.SingleDomain, SimView.SingleDomain), at the end of every section 6 resolution step the territory of every living
player is ONE 8-connected region (the adjacency of R21). Inherited land is plain domain for every purpose (returns and closures,
the capture flood, the rim, the lasso, Propagation, Coalescence, score, bots).
- Bridge at the inheritance (step b, right after the kill traits of each kill; the killer's anchor is the v1.5 anchor read on the
  grid BEFORE that inheritance: its pawn's cell when home, its exit cell when out, else the largest piece). If the killer's
  territory is now several pieces and the rule is Bridge, the kill line is built:
  (a) the killer's trail from its exit point to Q (its head at the cut, at arc s_Q recorded at the cut), when the killer is still
      out on the exit that made the cut (same Trail.Epoch; s_Q is mapped by Trail.Dropped); refused when that exit was cut since
      (ExitWasCut: v1.4, a cut exit never becomes territory; it covers a running chase and a spark KillShield extinguished);
  (b) when the killer was home at the cut, or has closed that exit since, the line starts at Q itself, which must still lie on a
      cell of the killer (its former trail became territory at the closure); refused otherwise (the line was taken since);
  (c) the link Q to P = the cut point on the victim's trail (|QP| <= ContactRadius), then the victim's trail from P back to its
      exit point (the part that tied it to its land, copied before the elimination cleared it).
  A cut forced by DebugForceCut has no contact geometry: it never makes a bridge. Band cells = every non-Void cell whose center
  lies within `SimConfig.InheritanceBandHalfWidth` (default 0.45 u = HeadRadius: a band about 0.9 u, 7 cells wide) of the line,
  plus the supercover raster of the line (the footprint a closure gives a trail), so the band is never thinner than one cell. The
  band is applied only when it joins pieces to the kept piece (no band cell would be cut off and fewer cells would be severed than
  without it; the killer had one domain before, so what it joins is inherited land). Applying it is a capture by the killer: cells of third players are lost by them and judged by
  rule v1.5 (anchors read before the write, the cutter is the killer, SeveredTerritory option as configured), then the R9 stolen
  home exits (TerritoryStolen + Exit, Other = the killer) and the TerritoryLost eliminations. Event (api addition, appended at the
  END of SimEventType, value 17) `InheritanceBridged`: Time = group time, Player = killer, Other = victim, Point = the victim's head
  at the kill (as TerritoryInherited), Cells = the band cells that became the killer's (ascending). PlayerState.InheritanceBridges++.
- The killer's trail when part (a) was used: the prefix [exit, Q] is territory now, so Trail.DropPrefix(s_Q) cuts it: the active
  trail starts at Q (inside the band) and keeps every later point, so the stored end, uTrailEnd, L(u), the head and its current
  cell are unchanged; Trail.Version changes (cut and lasso candidates of that trail are re-validated and dropped), Epoch stays,
  Dropped grows by s_Q; the pending pocket stays pending (validated at the next unchased return); the exit is not cut (no spark).
  A later cut of the remaining trail spawns its spark on the new arcs; a later return captures with the remaining trail, whose
  exit point Q lies on the domain (TerritorySplit.ExitCell finds the band cell). When the killer's head lies on its domain after
  the bridge, the next candidate pass returns it at that instant (section 6 state check), as for an inherited cell (BIOME_TRAITS
  7.2); ReturnsBeforeRoundEnd covers a round that ends in that group.
- Single domain of the killer: after the bridge (or when no bridge could be made, or with AnchorOnly) the killer keeps the piece
  of its anchor (else the largest) and every other piece becomes plain neutral (never scorched: a running ScorchedEarth scorch is
  forgotten), with TerritorySevered (Player = the killer, Other = -1: no cutter, Recipient = -1), raised right after the kill
  rewards (after InheritanceBridged when there is one). The kept piece holds the killer's pawn when it is home, so R9 is
  unaffected. A killer whose last cell an earlier bridge band of the same group took is eliminated by TerritoryLost and gets
  nothing more; a killer eliminated in the same group gets nothing, as before (cells neutral, ScorchedEarth scorches them).
- Closures (step a, unchased returns): when the capture (Interior + Rim + pocket) would leave a part apart from the returner's
  domain (TerritorySplit.GainAttached false: a lasso pocket or a region that touches only the trail, or a trail that leaves one
  piece and enters another), the capture also takes the trail footprint (supercover raster of the whole trail up to the crossing
  point, minus own and Void cells). It is added before the traits' AugmentCapture, so Coalescence also fills the holes it closes,
  and it is part of the capture (R18 and rule v1.5 apply to it). A closure that already joins the domain is unchanged (C2 holds:
  a bare back-and-forth line still captures nothing).
- Safety net (end of step a, after the v1.5 severance, before R9): a returner that gained cells keeps one domain. The cheap check
  (GainAttached on the written grid) is exact while its territory was one domain and lost nothing; with simultaneous returns
  (R18 contested cells), a severance of its own land or the Capturer option, TerritorySplit.KeepOnePiece decides (anchor = its
  return cell). A part apart is severed as above.
- Losses of a living player to captures are judged by rule v1.5 (contract 29): with the default SeveredTerritory = Neutral it
  keeps one piece; SeveredTerritory = Off disables that half of the invariant (Off means the designer wants the pre-v1.5 splits).
- Option (api addition) `SimConfig.InheritanceBridge` (`InheritanceBridgeRule`): `Bridge` (default), `AnchorOnly` (single domain
  without the band: inherited land apart from the killer's domain is severed), `Off` (the pre-v1.6 behaviour, bit-identical:
  every pinned Feu value of the v1.8 Core reproduces). `SimConfig.InheritanceBandHalfWidth` (default
  TraitDefaults.KillInheritanceBandHalfWidth = 0.45). Neither option is hashed (equal states, equal hashes). Without
  KillInheritance, or with Share 0, none of this runs. The KillInheritance key stays "KillInheritance(1,0)".
- Bots: they read only the grid for home (GridQueries.NearestOwned, OwnerAt), so every own cell already counts for the return
  target, the round-time trigger and an enemy's escape estimate. Added: after PlayerState.InheritanceBridges grows while a bot is
  trailing, its Return mode re-targets at once and the leg to R of its plan aims at the nearest own cell (pushed 1 u deeper). The
  round-time bound D_home <= L + one cell still holds after DropPrefix (the exit point Q is own). Never active without the rule.
- Presentation: TerritoryField reconciles from the grid, so the band and the severed cells appear without a handler. The Fire
  inheritance sweep (wave D-2) is event driven: InheritanceBridged now joins the pending TerritoryInherited sweep of the same kill
  (one sweep from the kill point, along the band into the inherited land), and TerritorySevered removes its cells from the pending
  waves of the player that lost them (they evaporate with the land they came from instead of being painted, then reconcile).
- Determinism: the band depends only on the line geometry (distances to segments and the supercover raster do not depend on how
  a straight path was subdivided into trail points), Q and P are exact roots, the labelling uses a fixed scan and neighbour order
  with pooled stamped buffers (no grid-sized allocation per call). Outcomes, band cells and grids are identical at 30, 60 and 144
  Hz (R22 cross-rate tests); twin rounds give identical StateHash. Cost: two labellings and one band raster per inheritance that
  leaves pieces (a few per round); O(gain) per unchased return in single-domain rounds (GainAttached).
- Pinned values: classic (8CB763231AC73608 Off / C042710F17995DCB default and the seven TraitsClassicTests rows), the Liquide and
  Électricité values and the probe hash 246577239DE179C4 are unchanged; with InheritanceBridge = Off the Feu demo hash
  3DF3952B7C1BC26E and every Feu bot round reproduce exactly. With the default the Feu demo hash is 1F733FBFBED2D3A9 (not pinned,
  verify checks equality across rates); R22_OffReproducesThePreV16FireHashesAndTheDefaultIsPinned pins four Feu rounds in both
  columns. SimEventType gains one value (18 values).
- Edge cases and limits: KillInheritance Share < 1 keeps the core of the land near its centroid; the band ends on the victim's
  exit point at the rim, which stays neutral, so the core is joined only when it touches the domain: under v1.6 a Share < 1 core
  is usually severed (open question in docs/inherit_fix.json). The invariant assumes one domain at the start (R2 discs); a start
  territory that is already in pieces (a custom SimSetup, a start disc clipped by a Europe outline) keeps its pieces until that
  player's first inheritance, which keeps its anchor piece only.

## 31. Rule change v1.7: countries first, 15 min cap, conquest goal (v2.0, designer decision, overrides older sections where they disagree)

The designer, 2026-11-27: "Les pays ont l'air d'être une option. Je veux que ça soit le cœur du jeu. Enlève le bouton Pays, et
quand tu cliques sur JOUER tu tombes sur la liste des pays à sélectionner." and "Enlève la notion de timer, ou plutôt : il sert de
limite ultime, par exemple 15 minutes. Le but du jeu devient de conquérir 100 % du territoire pendant cette durée. Si à l'issue de
ce très long temps on n'a pas réussi, le vainqueur est celui qui a conquis la plus grande partie du territoire. Dans tous les cas
on continue sur la sélection du pays suivant." Report: docs/flow_v17.json. Code: Core/Sim/Conquest.cs, Simulation (Conquest*),
SimConfig.ConquestShare, RoundEndReason.Conquest, EventResolver step g; runtime: MenuScreen, ResultsScreen, Hud, SaveData,
SettingsPanel, GameDirector.ToCountryScreen, Strings. Tests: Tests/EditMode/Core/ConquestTests.cs, Tests/EditMode/Runtime/
FlowV17Tests.cs, EuropeLevelsTests.EveryCountryHasAReachableConquestGoal, PlayMode EuropeMenuTests.

31.1 Flow (supersedes 15.2 and the "Pays" button of docs/europe/PROGRESSION.md). The menu has no "Pays" button; JOUER opens the
country screen (EuropeScreen: the 3D map and the progression); "Jouer ce pays" starts the country round. The results offer PAYS
SUIVANT (main button, also Escape / back: GameDirector.ToCountryScreen, the menu state with the country screen open, where a win
plays the reveal of the newly unlocked flags) and REJOUER (the same country again). The square arena is no longer reachable from
the menu; StartRound with no country, the probe, DevShot, the launch flags and the tests still play it. First launch is unchanged
(menu over the attract match; the tutorial bubbles run in the first round, which is France, the only playable country).

31.2 R19 amended: round end. Checked at step g of every event group, in this order: last survivor (n >= 2, one alive: wins at
once, unchanged), all eliminated, Conquest (new: a living player owns `Simulation.ConquestTargetCells`; it wins at once, ranks by
cells as usual, EndTime = the group time), TimeUp (largest territory wins, ties shared, unchanged). Behaviour traits that grow a
territory at the end of a tick (Propagation) are checked there too (Simulation.Step, only when a trait is attached).

31.3 The goal (api additions). Strict 100 % of ArenaCellCount is NOT reachable: a head center stays in the inset shape
{SignedDistance <= -ArenaMargin} and the capture flood seeds every Void cell, so the cells between the inset line and the rim
(about 3 cells deep, 2.9 % of the square arena) are outside for every capture. The goal is therefore defined on what can be owned:
- `Conquest.ConquerableMask` / `Simulation.ConquestCellCount`: head cells = arena cells whose center lies in the inset shape and
  in a 4-connected piece of such cells holding a player position; every non-head arena cell 4-connected through non-head cells
  to the Void or the grid border is out; everything else (head cells and what they enclose) is conquerable. Pieces beyond a neck
  narrower than 2 ArenaMargin are out too. Built lazily and cached (once a player owns Conquest.LazyFloor x the goal share of the
  arena cells, or when the runtime first reads a percentage).
- `SimConfig.ConquestShare` (default `Conquest.DefaultShare` = 1.0, the goal shown as 100 %; above 1 counts as 1; <= 0 turns the
  goal off). `Conquest.TargetCells(C, share)` = ceil(C x (min(share, 1) - `Conquest.DisplaySlack`)) with slack 0.005: the
  HUD shows whole percents from 10 %, so the goal is met exactly when the displayed percentage reads the goal ("100 %" from
  99.5 %). The slack absorbs the cells a real path misses (stair notches, cut corners, specks left by rules v1.5 / v1.6) and lets a
  rival survive on a speck below 0.5 % without blocking the win.
- `Simulation.ConquestPercent(i)` = 100 x min(owned, C) / C: the one percentage shown everywhere (HUD labels, leaderboard, capture
  gains, results, best score). The numerator counts every owned cell (rim cells a trail crossed just outside the mask included),
  clamped to 100 %. `AreaPercent` (R20, over ArenaCellCount) is unchanged for the Core and the bots.
- Reachability proof (ConquestTests): scripted rim tours end rounds by Conquest on the square arena (with and without a rival
  alive on a speck) and on a non-convex polygon with a 0.6 u neck; with the goal off a full tour leaves 72 of 249 240 (square)
  and 132 of 108 237 (polygon) conquerable cells unowned, far below the slack. Every Europe level keeps more than half of its
  arena cells conquerable (EuropeLevelsTests).
- ArenaPolygon fix found by this proof: StopBeforeBorder's smallest step was 1e-4 u, so a head sliding along a country border
  moved about 0.3 u/s instead of PawnSpeed; it is `ArenaPolygon.MinBorderStep` = 0.01 u now (still far below the 2 x margin a step
  would need to skip an inlet). Square-arena rounds, the classic hashes and the probe hash are not affected.

31.4 Round time. `Tuning.RoundDuration` stays 90 s (Core default for the tests and bot rounds). The runtime sets 900 s: SaveData
round choices are 5 / 10 / 15 min (300 / 600 / 900 s), 15 by default (`SaveData.DefaultRoundSeconds`, the reference of
TuningModified); a value saved by an older version (60 / 90 / 120 s, below the first choice) reads as the default; the settings
show minutes; -roundDuration is clamped to [5, 900]. The HUD timer reads m:ss ("15:00"). The bots read RoundDuration as before.

31.5 Presentation. HUD: the labels show ConquestPercent, a slim bar under the human label fills toward the goal (human color) and
"Objectif 100 %" / "Goal 100%" sits under the timer. Results: "territoire conquis" under the area; cause line "Territoire conquis
à 100 % !" (a rival's conquest: "Safran a conquis tout le territoire."); a time-up end adds "Le plus grand territoire l'emporte."
when no saved line is shown. The Europe campaign counts a win in every winning end (rank 1: Conquest, LastSurvivor, first or
shared first at TimeUp), unchanged rule (EuropeProgress.IsCountedWin).
## 32. Rule v1.8: one single domain in every round type (v2.1, designer decision, overrides older sections where they disagree)

The designer, 2026-11-27 (translated): "I still sometimes end up with my domain cut in two. There must be a reinforced check that
the domain always stays contiguous. If the domain would end up in two parts, keep a line between the two parts. Especially since,
right now, when I join one part to the other, the game tends to consider it is not the same domain, so it does not close the loop
and does not make the link between the two." Id R23. A core rule, not a biome trait: it generalizes the single domain of rule v1.6
(section 30) from the KillInheritance path to classic rounds, Liquide and Electricite. (Numbering: the task brief called it rule
v1.7; section 31 already uses "rule change v1.7" for the conquest goal, so this one is rule v1.8.) Code: EventResolver.LinkCapture,
RimSafe, the singleDomain / linkBands / inheritanceJoin switches, TerritorySplit.KeepOnePiece(neighbours), SimConfig.SingleDomain,
PlayerState.DomainLinks. Tests: Tests/EditMode/Core/SingleDomainTests.cs and SingleDomainStressTests.cs (R23_*). Report:
docs/domain_v17.json.

32.1 Why domains were cut in two (stress diagnosis, 240 bot rounds, pre-v1.8 rules). A capture is Interior + Rim + pocket (section
7). Two passes of a trail closer than about one cell are joined by the wall raster (section 8, accepted limitation), so a near loop
far from home encloses a region whose rim touches only the trail: the capture is an island ("own return: detached capture", the
dominant cause). A lasso pocket made away from the ordinary closure is an island too (the pocket lies on the trail, but trail cells
are taken only as Rim). Contested cells of simultaneous returns (R18) can cut a gain from its domain. Once in two pieces, a trail
from one piece to the other encloses nothing (no Interior, hence no Rim, CaptureSolver returns the pocket only): "it does not close
the loop". Rule v1.6 fixed this for Feu only; classic, Liquide and Electricite had no guarantee. Enemy captures never caused a
split (rule v1.5 works), and no trait causes one (Propagation grows 4-adjacent neutral cells, Coalescence fills enclosed holes).

R23 Single domain. With `SimConfig.SingleDomain = On` (the default, `SingleDomainRule`, api addition), at the end of every section 6
resolution step the territory of every living player is ONE 8-connected region, in every round type.
- Closures (step a, unchased returns, before the traits' AugmentCapture): the capture is checked with the returner's cells, the
  capture counted as its own and the piece of its return cell kept (TerritorySplit.KeepOnePiece). When own + capture is one
  4-connected piece nothing changes (one flood, O(territory)); C2 holds (a bare back-and-forth line still captures nothing). Else
  the band of the whole trail up to the crossing point is added when it leaves fewer cells apart (8-connected pieces first, then
  4-connected pieces, so a region joined only at a corner is linked too): band = every non-Void cell whose center lies within
  `SimConfig.InheritanceBandHalfWidth` (0.45 u, about 7 cells wide) of the trail plus its supercover raster (the rule v1.6 band,
  InheritanceBridge.BandCells), minus own cells, minus the R1 rim band (EventResolver.RimSafe: cells whose center lies closer to
  the rim than ArenaMargin minus half a cell diagonal, which no trail raster reaches, stay neutral forever). It joins a detached
  lasso pocket or region, a corner-joined region, and two separate pieces the trail goes between ("the line between the two
  parts"). The band is part of the capture: Return.Cells lists it, R18 applies to it, cells of a living rival under it are taken
  (the trail is the only line the player drew; the rival's pieces are then judged by rule v1.5, then R9 and TerritoryLost), and
  Coalescence runs after it. PlayerState.DomainLinks++ (api addition, not hashed) for each such return that applied cells.
- Safety net (end of step a, after rule v1.5, before R9, as in section 30, now in every round): a returner that gained cells keeps
  one domain; when a part still lies apart (contested cells of a simultaneous return, its own land severed in the same group), it
  keeps the piece of its return cell and the rest becomes plain neutral (TerritorySevered, Other = -1, Recipient = -1, scorch
  forgotten). This is the documented fallback when no own line can join the parts.
- Enemy-caused splits keep rule v1.5 (section 29, designer decision): the victim keeps the piece of its anchor, the rest is
  neutral (SeveredTerritory option unchanged; SeveredTerritory = Off still disables that half of the invariant).
- KillInheritance (section 30) is unchanged: bridge, AnchorOnly. With SingleDomain = On, `InheritanceBridge = Off` behaves as
  AnchorOnly (an inherited island is never kept); the bridge band also leaves out the R1 rim band. The closures of Feu rounds take
  the band (no longer the one-cell trail footprint of section 30).
- Off (`SingleDomain = Off`): the pre-v1.8 behaviour, bit-identical (section 30 runs only on the KillInheritance path, with its
  footprint closures). Every pinned value of the v2.0 Core reproduces with Off: the classic pre-trait and rule v1.5 columns of
  TraitsClassicTests, the rule v1.6 Feu rows (InheritanceBridgeTests.FireRows, both columns), the Liquide / Electricite / Feu rows
  of SingleDomainTests.BiomeRows. The option is not hashed (equal states, equal hashes).
- Pre-existing pieces (a custom SimSetup territory) are kept until a trail joins them or the safety net judges that player as a
  returner; R2 discs and the Europe start discs (radius within the outline) are one piece.
- Diagonal necks: own closures never leave a corner-only joint (the 4-connected check above). A rival capture can still leave a
  victim joined only at a corner (rule v1.5 judges 8-connectivity, the designer's adjacency); measured: 13 visible occurrences
  (corner-joined part of at least 16 cells) in 240 rounds after the fix, against 58 before (open question in the report).
- Determinism: the band depends only on the trail geometry (capsule distances and the supercover raster do not depend on how a
  straight path was subdivided), the labellings use a fixed scan and neighbour order on pooled stamped buffers; outcomes, Return
  cells and grids are identical at 30, 60 and 144 Hz (R23 cross-rate tests), twin rounds give identical StateHash.
- Cost: one 4-connected flood of the returner's territory per unchased return; three more floods and one band raster only when a
  link is considered (about 1.4 per round in bot rounds).
- Bots: a link happens at a return, when the bot is home, so no plan is stale; bots read home from the grid (NearestOwned,
  OwnerAt) and the safety net only touches returners. Section 9 targets still hold (BotTests). Presentation: the band cells are
  Return cells, so the fill wave of the return paints them in every biome (TerritoryField.AddWave from the return point), and
  TerritoryField reconciles every grid change; no Runtime change was needed.
- Pinned values: with the default, every TraitsClassicTests row changed (their rounds contain links); the new column and
  TraitsClassicTests.ClassicSeed1V18 are the classic reference; SingleDomainTests.BiomeRows pins Liquide, Electricite and Feu rows
  in two columns. The player probe hash 246577239DE179C4 must be checked in the Unity EditMode run (WaveD_TraitsInfraTests); see
  docs/domain_v17.json for the result.

## 33. Rule v1.9: border ride (v2.2, designer decision, overrides older sections where they disagree)
Designer request (translated): "when the pawn runs along the border for more than one second, its speed is multiplied by 3,
and without any change of direction from the user it keeps following the border even where the border makes obtuse angles".
Code: Core/Sim/BorderRide.cs (called from EventResolver.BeginTick, section 6 step 1), Arena.FollowBorder and
ArenaPolygon.Follow (boundary following), PlayerState ride fields, SimView.IsBorderRiding / BorderRideStartTime.
- Switch: `SimConfig.BorderRide` (BorderRideRule Off / On), `BorderRideFactor` = 3.0, `BorderRideDelay` = 1.0 s. The Core
  default is Off and Off is bit-identical to the pre-v1.9 simulation (the R4 call is unchanged, no ride field is read or
  hashed). The game turns it On for real rounds (GameSession.RoundConfig); the menu attract round and the probe's
  DemoScenario keep Off (the probe hash 246577239DE179C4 is unchanged).
- Contact: a head is in contact with the boundary when its R4 step was constrained (slide or hold, Arena.Step) or when the
  step ends within BorderRide.ContactTolerance (0.02 u) of the inset line. Contact starts at the exact instant the straight
  path of the tick reaches that tolerance (bisection on the tick fraction), so a head approaching at a constant heading gets
  the same instant at every tick rate; any tick without contact clears it (PlayerState.BorderContactStart = NaN).
- Trigger: the ride starts at contact start + BorderRideDelay (sim time). When that instant falls inside a tick, the head
  moves normally up to it and rides for the rest of the tick. A held head (pushing within BorderHoldAngle of the normal)
  rides too.
- Effect: tick speed = PawnSpeed x SpeedMultiplier x the behaviours' factor (Conduction) x BorderRideFactor while riding.
  The HeadGrace check of the Simulation constructor includes BorderRideFactor when the rule is On (60 Hz: 6 x 3 / 60 =
  0.3 u per tick; with the Electricite traits 0.51 u).
- Direction: at the start, the side the desired heading leans to along the boundary (sign of its component along
  OutwardNormal.Perp(); a push straight in, |component| below 1e-9, takes +Perp). While riding the heading IS the boundary
  tangent in that direction (PlayerState.Heading is set to it every tick).
- Auto-follow: Arena.FollowBorder moves the head along the inset line in sub-steps of at most 0.05 u: on the classic square
  the tangent step is projected back onto the convex inset rounded box (sides and corner arcs); on a country polygon each
  sub-step takes the tangent of the active edge (within margin + 0.02 u) that pushes least into the other active edges, so
  at a convex vertex (where a plain R4 slide is held) the head turns onto the next edge, and at a reflex vertex it follows
  the arc of radius ArenaMargin around the vertex. The result is always inside the inset shape. A ride tick that advances
  less than 20 % of its step (a dead end narrower than the head) ends the ride.
- New input: a desired heading within BorderRide.InputTolerance (20 degrees) of the one the ride last accepted is not a new
  input (a held joystick wobbles). A new input that points into the interior by more than BorderHoldAngle from the tangent
  ends the ride; any other new input is accepted (a push along the boundary the other way reverses the ride).
- End: steering inward (above), the head leaving the boundary, a dead end, elimination, or a spark on the trail. After an
  end the head moves at its normal speed for that whole tick and the delay starts over at the next contact.
- La Revanche: no ride while a spark chases the player, and a chased player accumulates no contact time. A spark that
  appears during a ride ends it: from the next tick on (BorderRide.Move at tick start, and EndOfTick at step 3 clears the
  flag at the end of the cut tick); the rest of the cut tick (at most 1 / TickRate s) was planned at the ride speed. Spark
  speeds are unchanged (SparkSpeedOf at the cut). Closed forms: SimView.SparkCatchEta (R12/R13) assumes the trailing speed
  PawnSpeed x SpeedMultiplier, which holds because a chased player never rides; the event engine's catch candidates use the
  actual trail growth of each tick; the bot intercept and escape math (BotController) uses SpeedMultiplier only, which is
  conservative for a riding bot (it is faster than planned) and exact for a chased victim (never riding).
- Event engine: a tick's motion stays the straight segment from the start to the full-step target (PosAt is linear), so a
  ride tick that rounds a corner is drawn as its chord, and in the tick where a ride starts the cell entry times are those of
  the uniform segment (no event in the tests falls there).
- StateHash: only when the rule is On, per player the ride flags (riding, sign) and BorderContactStart (rounded to 1e-9).
- Bots: they do not seek the ride. In seeded bot-only rounds they never come within the contact tolerance of the border
  (0 contact ticks in 10 rounds), so section 9 targets are unchanged with the rule On (BorderRideTests).
- Presentation: TraitFxView draws the Conduction speed streak, 80 % longer and tinted toward the border's neon yellow, behind
  a riding pearl (no new shader, no extra fetch). No sound (no new event type).
- Tests: BorderRideTests (trigger after exactly 1 s and not before, x3 closed-form position, cross-rate outcomes and ride
  instant at 30/60/144 Hz, rounded corner, convex and reflex polygon vertices without input, end on steering inward, joystick
  wobble, no boost while chased, a spark ends the ride, Off ignores every ride parameter, section 9 bot targets with the rule
  On). See docs/border_ride.json.
