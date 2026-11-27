// Owned by BI (wave B-2; first version by B0a). Contract 23.3, 18.2 step 2 and 24.1: the scripted demo round as a reusable
// SimSetup, scripted controllers and BeforeTick hooks keyed on the integer Tick (TickRate 60), with named checkpoint ticks
// and an assertion helper. Everything outside the UNITY_5_3_OR_NEWER block uses PainterIO.Core only, so the scenario also
// runs in a plain dotnet process (handy to tune the geometry without the Unity lock).
// Wave D-2 (traits-infra, docs/BIOME_TRAITS.md section 5): the demo runs CLASSIC by default (the probe hash
// 246577239DE179C4 is unchanged); CreateSession takes BiomeTraitTable.ResolveScripted(biome), so the command line can give
// it traits (-traits default = the biome's line of the table, -traits "<key>", -trait <Id>=0|1, -classic). The story
// below is the classic one: Monitor.Evaluate asserts it only for a classic round; a traited round is judged by
// Monitor.EvaluateTraited (no story, only what every trait set must keep). TraitShots lists the extra screenshots of a
// traited round (growth, kill reward, scorched ground, reach arc), keyed on sim ticks.
//
// The story under rule v1.4 (contract 24: a chased return survives but captures nothing). Player 0 is the human (coral),
// 1 the rival (teal), 2 and 3 the cutters (saffron and lilac):
// 1. Clean capture: the human leaves its puddle to the south, draws a loop to the south-west and comes home unchased: the
//    loop is captured and fills in (ThreadOut, MidFill).
// 2. Saved chase: the human crosses its puddle, leaves it to the north and draws a big loop to the west. The first cutter
//    leaves its puddle, touches the loop near its origin and turns back home. The spark starts far behind the head: the
//    human gets home in time, survives and captures nothing; the thread and the droplets evaporate (CutDroplets,
//    SavedReturn).
// 3. Pocket: the human crosses its puddle and leaves it to the east, over the rival's puddle that lies next to it. A
//    BeforeTick hook gives it a lasso charge; it curls a loop that crosses its own trail: a pending pocket next to its own
//    puddle and over the rival's (PocketPending).
// 4. Fatal cut: the human heads east, away from home; the second cutter touches the trail right behind the head and the
//    spark catches it (Caught).
using System;
using System.Collections.Generic;
using System.Text;
using PainterIO.Core;

namespace PainterIO.Runtime
{
    /// <summary>The scripted demo round of contract 18.2 step 2 (v1.4 story of 24.1), shared by DevShot, the player probe and the tests.</summary>
    public static class DemoScenario
    {
        public const int TickRate = 60;

        public const int Human = 0;
        public const int Rival = 1;
        public const int FirstCutter = 2;
        public const int SecondCutter = 3;
        public const int PlayerCount = 4;

        // Checkpoint ticks: the state after that many ticks (a screenshot is taken in the first rendered frame with
        // Sim.Tick >= the checkpoint). The values come from the event ticks of the scenario (the tests assert them).
        /// <summary>Phase 1: the human's thread is out (long loop, no spark).</summary>
        public const long ThreadOut = 140;
        /// <summary>Phase 1: the human got home unchased; the fill wave is half way (liquid FillDuration 0.35 s).</summary>
        public const long MidFill = 191;
        /// <summary>Phase 2: the loop was cut near its origin; the retraction front has left a droplet chain behind it.</summary>
        public const long CutDroplets = 421;
        /// <summary>Phase 2: just after the saved chased return (no capture): the thread and the droplets evaporate.</summary>
        public const long SavedReturn = 504;
        /// <summary>Phase 3: the pending lasso pocket is drawn next to the human's puddle and over the rival's.</summary>
        public const long PocketPending = 732;
        /// <summary>Phase 4: the spark has caught the human (splash in flight).</summary>
        public const long Caught = 836;

        /// <summary>BeforeTick hook: the human receives its lasso charge at the start of this tick.</summary>
        public const long ChargeTick = 612;

        /// <summary>Tick count after which the scenario is over (the test and the probe run at least this far).</summary>
        public const long EndTick = Caught + 30;

        /// <summary>Checkpoint names in tick order (DevShot and the probe capture them in this order).</summary>
        public static readonly string[] CheckpointNames = { "ThreadOut", "MidFill", "CutDroplets", "SavedReturn", "PocketPending", "Caught" };
        /// <summary>Checkpoint ticks, same order as CheckpointNames (strictly increasing).</summary>
        public static readonly long[] CheckpointTicks = { ThreadOut, MidFill, CutDroplets, SavedReturn, PocketPending, Caught };

        // Layout (world units).
        public static readonly Vec2d HumanHome = new Vec2d(-3.0, -4.0);
        public static readonly Vec2d RivalHome = new Vec2d(4.5, -5.0);
        public static readonly Vec2d RivalHome2 = new Vec2d(9.0, -6.5);
        public static readonly Vec2d RivalOrbit = new Vec2d(9.5, -7.0);
        public static readonly Vec2d FirstCutterHome = new Vec2d(4.0, 6.5);
        public static readonly Vec2d SecondCutterHome = new Vec2d(10.0, 5.5);
        public const double DiscRadius = 3.5;

        /// <summary>Sim time at which the first cutter leaves its orbit for the human's second loop.</summary>
        public const double FirstCutterStart = 5.25;
        /// <summary>Sim time at which the second cutter leaves its orbit for the human's last leg.</summary>
        public const double SecondCutterStart = 12.25;

        // The human's path: control points of a Catmull-Rom curve, sampled into waypoints. Phase 1 (the south-west loop)
        // ends back on the disc center, so the curve from (-3, -1) on is exactly the one of the B0a demo.
        private static readonly Vec2d[] HumanPath =
        {
            // Phase 1: clean capture to the south-west.
            new Vec2d(-3.0, -4.0), new Vec2d(-3.0, -6.5), new Vec2d(-3.3, -9.6), new Vec2d(-5.0, -11.2),
            new Vec2d(-7.4, -10.8), new Vec2d(-8.7, -8.6), new Vec2d(-8.2, -6.2), new Vec2d(-6.4, -4.6),
            new Vec2d(-4.6, -4.4), new Vec2d(-3.0, -4.0),
            // Phase 2: the big loop to the west, cut near its origin, saved return.
            new Vec2d(-3.0, -1.0), new Vec2d(-2.6, 2.5), new Vec2d(-3.2, 5.8),
            new Vec2d(-5.5, 8.2), new Vec2d(-8.6, 7.8), new Vec2d(-10.2, 4.5), new Vec2d(-9.0, 0.8),
            new Vec2d(-6.6, -1.6), new Vec2d(-4.5, -3.4), new Vec2d(-2.8, -4.4),
            // Phase 3: east over the rival's puddle, lasso pocket.
            new Vec2d(0.0, -4.3), new Vec2d(3.0, -4.2), new Vec2d(5.3, -4.4), new Vec2d(5.8, -6.0), new Vec2d(4.5, -7.2),
            new Vec2d(2.2, -7.2), new Vec2d(1.4, -5.8), new Vec2d(1.4, -3.0), new Vec2d(1.8, -1.0),
            // Phase 4: away from home, fatal cut.
            new Vec2d(3.2, 0.0), new Vec2d(6.0, 0.2), new Vec2d(9.0, 0.2), new Vec2d(14.0, 0.2), new Vec2d(24.0, 0.2),
        };

        private static readonly Vec2d[] FirstCutterPath =
        {
            new Vec2d(0.8, 3.2), new Vec2d(-2.6, 1.4), new Vec2d(-1.6, 0.4), new Vec2d(1.5, 2.6), new Vec2d(4.0, 6.0),
        };

        private static readonly Vec2d[] SecondCutterPath =
        {
            new Vec2d(7.3, 2.6), new Vec2d(7.1, -1.6), new Vec2d(8.6, -1.0), new Vec2d(9.4, 2.6), new Vec2d(10.0, 5.5),
        };

        /// <summary>Default sim config of the demo: TickRate 60, default turn rate, no random ring spawns, classic rules.</summary>
        public static SimConfig CreateConfig()
        {
            return new SimConfig { TickRate = TickRate, LassoEnabled = false, Seed = 1 };
        }

        /// <summary>Wave D-2: the demo config with a trait set (null = classic, identical to CreateConfig()).</summary>
        public static SimConfig CreateConfig(RuleTraits traits)
        {
            SimConfig config = CreateConfig();
            config.Traits = traits ?? RuleTraits.Classic;
            return config;
        }

        /// <summary>Start positions, headings and territories (the human is player 0). names may be null.</summary>
        public static SimSetup CreateSetup(string[] names = null)
        {
            return new SimSetup
            {
                PlayerCount = PlayerCount,
                StartPositions = new[] { HumanHome, RivalOrbit + new Vec2d(1.5, 0.0), FirstCutterHome, SecondCutterHome },
                StartHeadings = new[] { -Math.PI * 0.5, Math.PI * 0.5, Math.PI, Math.PI },
                Territory = PaintTerritories,
                Names = names,
                HumanIndex = Human,
            };
        }

        /// <summary>Fresh scripted controllers (the waypoint controllers keep per-run progress: never share them).</summary>
        public static IController[] CreateControllers()
        {
            return new IController[]
            {
                new WaypointController(SampleCurve(HumanPath, 0.75)),
                new HomeCirclerController(RivalOrbit),
                new PhasedController(new HomeCirclerController(FirstCutterHome), FirstCutterStart,
                                     new PathThenCircleController(FirstCutterPath, FirstCutterHome)),
                new PhasedController(new HomeCirclerController(SecondCutterHome), SecondCutterStart,
                                     new PathThenCircleController(SecondCutterPath, SecondCutterHome)),
            };
        }

        /// <summary>Subscribes the scenario's BeforeTick hooks (the lasso charge) to sim.</summary>
        public static void AttachHooks(Simulation sim)
        {
            if (sim == null) throw new ArgumentNullException(nameof(sim));
            sim.BeforeTick += OnBeforeTick;
        }

        /// <summary>A headless demo round with its hooks and a monitor (Core only).</summary>
        public static Simulation CreateSimulation(out Monitor monitor)
        {
            return CreateSimulation(out monitor, null);
        }

        /// <summary>Wave D-2: a headless demo round under a trait set (null = classic) with its hooks and a monitor.</summary>
        public static Simulation CreateSimulation(out Monitor monitor, RuleTraits traits)
        {
            var sim = new Simulation(CreateConfig(traits), CreateControllers(), CreateSetup());
            AttachHooks(sim);
            monitor = new Monitor(sim);
            return sim;
        }

        /// <summary>Index of a checkpoint in CheckpointNames / CheckpointTicks, -1 when unknown.</summary>
        public static int CheckpointIndex(string name)
        {
            return Array.IndexOf(CheckpointNames, name);
        }

#if UNITY_5_3_OR_NEWER
        /// <summary>
        /// The demo round as a real (non-attract) GameSession: AwaitingStart = false, CountsForStats = false, names as in
        /// GameSession.CreateRound, hooks attached and a monitor watching it. Its biome follows the command line (-biome)
        /// or SaveData.Biome (GameDirector applies it when the session starts). Wave D-2: its traits are
        /// BiomeTraitTable.ResolveScripted(that biome): classic unless the command line gives trait flags.
        /// </summary>
        public static GameSession CreateSession(out Monitor monitor)
        {
            return CreateSession(out monitor, null, BiomeTraitTable.ResolveScripted(GameSession.ActiveBiome()));
        }

        /// <summary>The demo round in a forced biome (GameSession.Biome; the probe and the tests use it), traits as above.</summary>
        public static GameSession CreateSession(out Monitor monitor, BiomeId biome)
        {
            return CreateSession(out monitor, biome, BiomeTraitTable.ResolveScripted(biome));
        }

        /// <summary>
        /// Wave D-2: the demo round with an explicit trait set (null = classic) and an optional forced biome (null follows
        /// -biome / SaveData.Biome). Tests and per-biome trait runs use it.
        /// </summary>
        public static GameSession CreateSession(out Monitor monitor, BiomeId? biome, RuleTraits traits)
        {
            var session = new GameSession(CreateConfig(traits), CreateSetup(GameSession.DefaultNames(PlayerCount, Human)),
                                          CreateControllers(), false);
            if (biome.HasValue) session.Biome = biome.Value;
            AttachHooks(session.Sim);
            monitor = new Monitor(session.Sim);
            return session;
        }
#endif

        private static void OnBeforeTick(Simulation sim)
        {
            if (sim.Tick == ChargeTick && sim.Players[Human].Alive) sim.DebugSetCharged(Human, true);
        }

        private static void PaintTerritories(OwnerGrid g)
        {
            g.FillDisc(HumanHome, DiscRadius, (byte)(Human + 1));
            g.FillDisc(RivalHome, DiscRadius, (byte)(Rival + 1));
            g.FillDisc(RivalHome2, DiscRadius, (byte)(Rival + 1));
            g.FillDisc(FirstCutterHome, DiscRadius, (byte)(FirstCutter + 1));
            g.FillDisc(SecondCutterHome, DiscRadius, (byte)(SecondCutter + 1));
        }

        /// <summary>Uniform Catmull-Rom through the control points, sampled about every spacing u (endpoints kept).</summary>
        public static List<Vec2d> SampleCurve(IReadOnlyList<Vec2d> control, double spacing)
        {
            var output = new List<Vec2d>();
            int n = control.Count;
            if (n == 0) return output;
            for (int k = 0; k < n - 1; k++)
            {
                Vec2d p0 = control[Math.Max(0, k - 1)], p1 = control[k], p2 = control[k + 1], p3 = control[Math.Min(n - 1, k + 2)];
                int steps = Math.Max(1, (int)Math.Ceiling(Vec2d.Distance(p1, p2) / spacing));
                for (int s = 1; s <= steps; s++)
                {
                    double t = s / (double)steps, t2 = t * t, t3 = t2 * t;
                    Vec2d p = 0.5 * ((2.0 * p1) + (p2 - p0) * t + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                                     + (3.0 * p1 - p0 - 3.0 * p2 + p3) * t3);
                    output.Add(p);
                }
            }
            return output;
        }

        /// <summary>Uses the first controller before switchTime (sim time) and the second one from then on.</summary>
        public sealed class PhasedController : IController
        {
            private readonly IController before;
            private readonly IController after;
            private readonly double switchTime;

            public PhasedController(IController before, double switchTime, IController after)
            {
                this.before = before;
                this.after = after;
                this.switchTime = switchTime;
            }

            public double? DesiredHeading(SimView view, int playerIndex)
            {
                IController active = view.Time >= switchTime - 1e-9 ? after : before;
                return active != null ? active.DesiredHeading(view, playerIndex) : null;
            }
        }

        /// <summary>Follows waypoints, then orbits a home center forever (a cutter going back to its puddle).</summary>
        public sealed class PathThenCircleController : IController
        {
            private readonly WaypointController path;
            private readonly HomeCirclerController circle;

            public PathThenCircleController(IReadOnlyList<Vec2d> waypoints, Vec2d home)
            {
                path = new WaypointController(waypoints);
                circle = new HomeCirclerController(home);
            }

            public double? DesiredHeading(SimView view, int playerIndex)
            {
                double? heading = path.DesiredHeading(view, playerIndex);
                return heading ?? circle.DesiredHeading(view, playerIndex);
            }
        }

        /// <summary>State of the human recorded at a checkpoint (the state after that many ticks).</summary>
        public struct CheckpointState
        {
            public bool Recorded;
            public long Tick;
            public bool Alive;
            public bool Home;
            public double TrailLength;
            public bool HasSpark;
            public double SparkTravel;     // S - SCut
            public double SparkGap;        // L - S
            public int PocketCells;
        }

        /// <summary>
        /// Assertion helper: watches a demo round (events and checkpoint states) and reports whether the expected events
        /// happened. Event ticks are Sim.Tick after the Step that raised them.
        /// </summary>
        public sealed class Monitor
        {
            private readonly Simulation sim;

            /// <summary>First cut of the human's trail (phase 2, near the loop origin).</summary>
            public long FirstCutTick = -1;
            public double FirstCutS = double.NaN;
            public double FirstCutTrailLength = double.NaN;
            /// <summary>First Return of the human that captured cells (phase 1, unchased under v1.4).</summary>
            public long FirstReturnTick = -1;
            public int FirstReturnCells;
            public bool FirstReturnChased;
            public double FirstReturnMargin;
            /// <summary>First chased (saved) Return of the human (phase 2): Cells must be empty under v1.4.</summary>
            public long SavedReturnTick = -1;
            public int SavedReturnCells;
            public bool SavedReturnChased;
            public double SavedReturnMargin;
            /// <summary>Cells of the human just before the saved return and just after it (equal under v1.4).</summary>
            public int CellsBeforeSavedReturn = -1;
            public int CellsAfterSavedReturn = -1;
            public long PocketTick = -1;               // first LassoPocket of the human after the saved return
            public int PocketCells;
            public int PocketCellsOverRival;
            public double PocketDistanceToHome = double.PositiveInfinity;
            public long SecondCutTick = -1;
            public double SecondCutGap = double.NaN;   // L - s_cut at the second cut
            public long CaughtTick = -1;
            public EliminationCause HumanCause = EliminationCause.None;
            public int HumanEvents;
            public readonly CheckpointState[] Checkpoints = new CheckpointState[CheckpointTicks.Length];

            private int humanCellsBeforeStep;
            private bool cellsAfterPending;

            public Monitor(Simulation sim)
            {
                this.sim = sim ?? throw new ArgumentNullException(nameof(sim));
                sim.EventRaised += OnEvent;
                sim.BeforeTick += OnBeforeTick;
            }

            /// <summary>Records the checkpoint whose tick equals the current Tick when no later Step will do it.</summary>
            public void Finish()
            {
                OnBeforeTick(sim);
            }

            /// <summary>The recorded state of a named checkpoint (Recorded false when unknown or not reached).</summary>
            public CheckpointState Checkpoint(string name)
            {
                int k = CheckpointIndex(name);
                return k >= 0 ? Checkpoints[k] : default(CheckpointState);
            }

            private void OnBeforeTick(Simulation s)
            {
                if (cellsAfterPending)
                {
                    cellsAfterPending = false;
                    CellsAfterSavedReturn = s.Grid.CountOf(s.Players[Human].Id);
                }
                humanCellsBeforeStep = s.Grid.CountOf(s.Players[Human].Id);
                for (int k = 0; k < CheckpointTicks.Length; k++)
                {
                    if (CheckpointTicks[k] == s.Tick && !Checkpoints[k].Recorded) Checkpoints[k] = Capture(s);
                }
            }

            private static CheckpointState Capture(Simulation s)
            {
                PlayerState h = s.Players[Human];
                var state = new CheckpointState
                {
                    Recorded = true,
                    Tick = s.Tick,
                    Alive = h.Alive,
                    Home = h.Home,
                    TrailLength = h.Trail.Length,
                    HasSpark = h.Spark != null,
                    PocketCells = h.Pocket != null ? h.Pocket.Count : 0,
                };
                if (h.Spark != null)
                {
                    state.SparkTravel = h.Spark.S - h.Spark.SCut;
                    state.SparkGap = h.Trail.Length - h.Spark.S;
                }
                return state;
            }

            private void OnEvent(SimEvent e)
            {
                long tick = sim.Tick + 1;   // the Step that raises the event ends with Tick + 1
                if (e.Player == Human) HumanEvents++;
                switch (e.Type)
                {
                    case SimEventType.Cut:
                        if (e.Player != Human) break;
                        if (FirstCutTick < 0)
                        {
                            FirstCutTick = tick;
                            FirstCutS = e.S;
                            FirstCutTrailLength = sim.Players[Human].Trail.Length;
                        }
                        else if (SecondCutTick < 0 && SavedReturnTick >= 0)
                        {
                            SecondCutTick = tick;
                            SecondCutGap = sim.Players[Human].Trail.Length - e.S;
                        }
                        break;
                    case SimEventType.Return:
                        if (e.Player != Human) break;
                        int cells = e.Cells != null ? e.Cells.Length : 0;
                        if (FirstReturnTick < 0 && cells > 0)
                        {
                            FirstReturnTick = tick;
                            FirstReturnCells = cells;
                            FirstReturnChased = e.Chased;
                            FirstReturnMargin = e.Margin;
                        }
                        if (SavedReturnTick < 0 && e.Chased)
                        {
                            SavedReturnTick = tick;
                            SavedReturnCells = cells;
                            SavedReturnChased = true;
                            SavedReturnMargin = e.Margin;
                            CellsBeforeSavedReturn = humanCellsBeforeStep;
                            cellsAfterPending = true;
                        }
                        break;
                    case SimEventType.LassoPocket:
                        if (e.Player == Human && SavedReturnTick >= 0 && PocketTick < 0)
                        {
                            PocketTick = tick;
                            PocketCells = e.Cells != null ? e.Cells.Length : 0;
                            AnalysePocket(e.Cells);
                        }
                        break;
                    case SimEventType.Eliminated:
                        if (e.Player == Human && CaughtTick < 0)
                        {
                            CaughtTick = tick;
                            HumanCause = e.Cause;
                        }
                        break;
                }
            }

            private void AnalysePocket(int[] cells)
            {
                if (cells == null) return;
                OwnerGrid g = sim.Grid;
                byte rival = (byte)(Rival + 1), human = (byte)(Human + 1);
                int size = g.Size;
                int reach = (int)Math.Ceiling(2.0 / g.CellSize);
                foreach (int c in cells)
                {
                    if (g.Cells[c] == rival) PocketCellsOverRival++;
                }
                // Distance from the pocket to the human's puddle: nearest human cell around the pocket cells (2 u window).
                double best = double.PositiveInfinity;
                foreach (int c in cells)
                {
                    int ci = c % size, cj = c / size;
                    for (int dj = -reach; dj <= reach; dj++)
                    {
                        int j = cj + dj;
                        if (j < 0 || j >= size) continue;
                        for (int di = -reach; di <= reach; di++)
                        {
                            int i = ci + di;
                            if (i < 0 || i >= size || g.Cells[j * size + i] != human) continue;
                            double d = Math.Sqrt(di * di + dj * dj) * g.CellSize;
                            if (d < best) best = d;
                        }
                    }
                }
                PocketDistanceToHome = best;
            }

            /// <summary>
            /// Evaluates the scenario. Returns true when every expectation holds; failures lists the others. Call after
            /// the run (and after Finish when the run stopped exactly on a checkpoint tick).
            /// </summary>
            public bool Evaluate(out List<string> failures)
            {
                failures = new List<string>();
                // Phase 1: a clean capture without any spark.
                if (FirstReturnTick < 0) failures.Add("no capturing return (phase 1)");
                else
                {
                    if (FirstReturnChased) failures.Add("the capturing return was chased (v1.4: a chased return captures nothing)");
                    if (FirstCutTick >= 0 && FirstCutTick <= FirstReturnTick) failures.Add("the human was cut before the clean capture");
                }
                // Phase 2: a cut near the loop origin, then a saved chased return that captures nothing.
                if (FirstCutTick < 0) failures.Add("no cut on the human's second loop");
                else if (FirstCutS > 0.3 * FirstCutTrailLength)
                    failures.Add("the first cut is not near the loop origin (s_cut " + F(FirstCutS) + " of L " + F(FirstCutTrailLength) + ")");
                if (SavedReturnTick < 0) failures.Add("no saved chased return");
                else
                {
                    if (SavedReturnCells != 0) failures.Add("the saved chased return captured " + SavedReturnCells + " cells (v1.4: none)");
                    if (!(SavedReturnMargin > 0.0)) failures.Add("the saved return has no positive margin (" + F(SavedReturnMargin) + ")");
                    if (FirstCutTick >= 0 && SavedReturnTick < FirstCutTick) failures.Add("the saved return came before the cut");
                    if (FirstReturnTick >= 0 && SavedReturnTick < FirstReturnTick) failures.Add("the saved return came before the clean capture");
                    if (CellsAfterSavedReturn >= 0 && CellsAfterSavedReturn != CellsBeforeSavedReturn)
                        failures.Add("the human's territory changed at the saved return (" + CellsBeforeSavedReturn + " -> " + CellsAfterSavedReturn + ")");
                }
                // Phase 3.
                if (PocketTick < 0) failures.Add("no LassoPocket after the saved return");
                else
                {
                    if (PocketCellsOverRival <= 0) failures.Add("the pocket does not lie over the rival's puddle");
                    if (PocketDistanceToHome > 1.5) failures.Add("the pocket is not next to the human's puddle (" + F(PocketDistanceToHome) + " u)");
                }
                // Phase 4.
                if (CaughtTick < 0) failures.Add("the human was not eliminated");
                else
                {
                    if (HumanCause != EliminationCause.Spark) failures.Add("the human was eliminated by " + HumanCause + ", not by the spark");
                    if (PocketTick >= 0 && CaughtTick < PocketTick) failures.Add("the human was caught before the pocket");
                    if (SecondCutTick < 0) failures.Add("no second cut");
                    else if (SecondCutGap > 2.5) failures.Add("the second cut is not right behind the head (gap " + F(SecondCutGap) + " u)");
                }
                if (sim.EventCapHits != 0) failures.Add("EventCapHits = " + sim.EventCapHits);

                // Checkpoints.
                CheckpointState s = Checkpoint("ThreadOut");
                if (!s.Recorded) failures.Add("ThreadOut not reached");
                else if (!s.Alive || s.Home || s.HasSpark || s.TrailLength < 6.0 || (FirstReturnTick >= 0 && ThreadOut >= FirstReturnTick))
                    failures.Add("ThreadOut: expected a long uncut thread before the clean capture (" + Describe(s) + ")");
                s = Checkpoint("MidFill");
                if (!s.Recorded) failures.Add("MidFill not reached");
                else if (!s.Alive || !s.Home || FirstReturnTick < 0 || MidFill - FirstReturnTick < 4 || MidFill - FirstReturnTick > 18)
                    failures.Add("MidFill: expected home 4 to 18 ticks after the clean capture (return tick " + FirstReturnTick + ", " + Describe(s) + ")");
                s = Checkpoint("CutDroplets");
                if (!s.Recorded) failures.Add("CutDroplets not reached");
                else if (!s.Alive || s.Home || !s.HasSpark || s.SparkTravel < 2.0 || s.SparkGap < 3.0)
                    failures.Add("CutDroplets: expected a chase with a droplet chain >= 2 u and a gap >= 3 u (" + Describe(s) + ")");
                s = Checkpoint("SavedReturn");
                if (!s.Recorded) failures.Add("SavedReturn not reached");
                else if (!s.Alive || !s.Home || s.HasSpark || SavedReturnTick < 0 || SavedReturn - SavedReturnTick < 2 || SavedReturn - SavedReturnTick > 12)
                    failures.Add("SavedReturn: expected home 2 to 12 ticks after the saved return (return tick " + SavedReturnTick + ", " + Describe(s) + ")");
                s = Checkpoint("PocketPending");
                if (!s.Recorded) failures.Add("PocketPending not reached");
                else if (!s.Alive || s.Home || s.HasSpark || s.PocketCells <= 0 || PocketTick < 0 || PocketTick > PocketPending)
                    failures.Add("PocketPending: expected a pending pocket without a spark (" + Describe(s) + ")");
                s = Checkpoint("Caught");
                if (!s.Recorded) failures.Add("Caught not reached");
                else if (s.Alive || CaughtTick < 0 || CaughtTick > Caught || Caught - CaughtTick > 20)
                    failures.Add("Caught: expected the human caught 0 to 20 ticks before (caught tick " + CaughtTick + ", " + Describe(s) + ")");
                return failures.Count == 0;
            }

            /// <summary>Wave D-2: the watched round runs with at least one trait (the classic story is then not asserted).</summary>
            public bool Traited => !sim.Config.Traits.IsClassic;

            /// <summary>
            /// Wave D-2: what a demo round must keep under ANY trait set (the classic story of Evaluate does not hold: for
            /// example Feu's 2.1x spark catches the human in phase 2). Phase 1 is a clean unchased capture before any cut,
            /// EventCapHits stays 0 and every checkpoint tick is reached. Returns true when every check holds.
            /// </summary>
            public bool EvaluateTraited(out List<string> failures)
            {
                failures = new List<string>();
                if (FirstReturnTick < 0) failures.Add("no capturing return (phase 1)");
                else
                {
                    if (FirstReturnChased) failures.Add("the capturing return was chased");
                    if (FirstCutTick >= 0 && FirstCutTick <= FirstReturnTick) failures.Add("the human was cut before the clean capture");
                }
                if (sim.EventCapHits != 0) failures.Add("EventCapHits = " + sim.EventCapHits);
                for (int k = 0; k < Checkpoints.Length; k++)
                {
                    if (!Checkpoints[k].Recorded) failures.Add(CheckpointNames[k] + " not reached");
                }
                return failures.Count == 0;
            }

            /// <summary>One line per fact, for logs.</summary>
            public string Report()
            {
                var sb = new StringBuilder();
                sb.Append("capture tick=").Append(FirstReturnTick).Append(" cells=").Append(FirstReturnCells)
                  .Append(" chased=").Append(FirstReturnChased);
                sb.Append(" | firstCut tick=").Append(FirstCutTick).Append(" s=").Append(F(FirstCutS)).Append(" L=").Append(F(FirstCutTrailLength));
                sb.Append(" | savedReturn tick=").Append(SavedReturnTick).Append(" cells=").Append(SavedReturnCells)
                  .Append(" margin=").Append(F(SavedReturnMargin)).Append(" territory=").Append(CellsBeforeSavedReturn)
                  .Append("->").Append(CellsAfterSavedReturn);
                sb.Append(" | pocket tick=").Append(PocketTick).Append(" cells=").Append(PocketCells).Append(" overRival=")
                  .Append(PocketCellsOverRival).Append(" toHome=").Append(F(PocketDistanceToHome));
                sb.Append(" | secondCut tick=").Append(SecondCutTick).Append(" gap=").Append(F(SecondCutGap));
                sb.Append(" | caught tick=").Append(CaughtTick).Append(" cause=").Append(HumanCause);
                for (int k = 0; k < Checkpoints.Length; k++)
                {
                    sb.Append(" | ").Append(CheckpointNames[k]).Append(": ").Append(Describe(Checkpoints[k]));
                }
                return sb.ToString();
            }

            private static string Describe(CheckpointState s)
            {
                if (!s.Recorded) return "not recorded";
                return "tick=" + s.Tick + " alive=" + s.Alive + " home=" + s.Home + " L=" + F(s.TrailLength) + " spark=" + s.HasSpark
                       + " travel=" + F(s.SparkTravel) + " gap=" + F(s.SparkGap) + " pocket=" + s.PocketCells;
            }

            private static string F(double v)
            {
                return v.ToString("0.###", System.Globalization.CultureInfo.InvariantCulture);
            }
        }

        /// <summary>
        /// Wave D-2 (BIOME_TRAITS 6, player screenshots): the extra screenshots of a traited demo round, planned from the
        /// sim only (events and BeforeTick reads; it never steers the sim). A shot is due at a tick; the caller captures
        /// it in the first rendered frame with Sim.Tick &gt;= that tick, like the checkpoints. Each kind is planned once:
        ///   grow    first TerritoryGrew of the human + GrowDelay ticks (Propagation front over its own puddle);
        ///   reward  first kill reward (TerritoryInherited, SpeedBoosted, ShieldStarted) + RewardDelay ticks (about the
        ///           middle of a fill wave, before the death beat of a dead human ends);
        ///   scorch  first elimination whose freed cells are scorched (ScorchedEarth without a surviving inheritor)
        ///           + ScorchDelay ticks;
        ///   reach   first tick where an enemy head comes within ContactRadius x 1.25 (plus ReachLeadTicks of base pawn
        ///           travel, so the captured frame, a tick or two later, still precedes the cut) of an exposed point of a
        ///           trail of the human, or the human's head near another trail, when ArcReach widened the contact.
        /// Nothing is planned in a classic round.
        /// </summary>
        public sealed class TraitShots
        {
            public const long GrowDelay = 10;
            public const long RewardDelay = 18;
            public const long ScorchDelay = 30;

            /// <summary>Lead of the reach shot in ticks of base pawn travel (frames land up to two ticks after the plan).</summary>
            public const double ReachLeadTicks = 2.0;

            /// <summary>The reach arc shows within this multiple of the contact radius (BIOME_TRAITS 5).</summary>
            public const double ReachScale = 1.25;

            private readonly Simulation sim;
            private readonly List<KeyValuePair<long, string>> due = new List<KeyValuePair<long, string>>();
            private readonly HashSet<string> planned = new HashSet<string>();
            private int[] pendingFreed;
            private readonly bool active;
            private readonly bool watchReach;

            public TraitShots(Simulation sim)
            {
                this.sim = sim ?? throw new ArgumentNullException(nameof(sim));
                RuleTraits traits = sim.Config.Traits;
                active = traits != null && !traits.IsClassic;
                watchReach = active && sim.Config.ContactScale > 1.0 + 1e-9;
                if (!active) return;
                sim.EventRaised += OnEvent;
                sim.BeforeTick += OnBeforeTick;
            }

            /// <summary>Shot names planned so far (in planning order), for logs.</summary>
            public IEnumerable<string> Planned => planned;

            /// <summary>Pending shots (due tick, name).</summary>
            public int PendingCount => due.Count;

            /// <summary>The next shot whose tick has come (removed from the queue), or false.</summary>
            public bool TryTake(long tick, out string name)
            {
                name = null;
                int best = -1;
                for (int k = 0; k < due.Count; k++)
                {
                    if (due[k].Key > tick) continue;
                    if (best < 0 || due[k].Key < due[best].Key) best = k;
                }
                if (best < 0) return false;
                name = due[best].Value;
                due.RemoveAt(best);
                return true;
            }

            /// <summary>Unsubscribes from the sim.</summary>
            public void Detach()
            {
                if (!active) return;
                sim.EventRaised -= OnEvent;
                sim.BeforeTick -= OnBeforeTick;
            }

            private void Plan(string name, long tick)
            {
                if (!planned.Add(name)) return;
                due.Add(new KeyValuePair<long, string>(tick, name));
            }

            // Raised during Step: the tick that raises it ends with Tick + 1.
            private void OnEvent(SimEvent e)
            {
                long tick = sim.Tick + 1;
                switch (e.Type)
                {
                    case SimEventType.TerritoryGrew:
                        if (e.Player == Human && e.Cells != null && e.Cells.Length > 0) Plan("grow", tick + GrowDelay);
                        break;
                    case SimEventType.TerritoryInherited:
                    case SimEventType.SpeedBoosted:
                    case SimEventType.ShieldStarted:
                        Plan("reward", tick + RewardDelay);
                        break;
                    case SimEventType.Eliminated:
                        if (e.Cells != null && e.Cells.Length > 0 && sim.Config.Traits.Has(TraitId.ScorchedEarth) && !planned.Contains("scorch"))
                            pendingFreed = e.Cells;
                        break;
                }
            }

            // Runs before each Step, on the state left by the previous one.
            private void OnBeforeTick(Simulation s)
            {
                if (pendingFreed != null)
                {
                    int[] cells = pendingFreed;
                    pendingFreed = null;
                    for (int k = 0; k < cells.Length; k += Math.Max(1, cells.Length / 16))
                    {
                        if (!s.View.IsScorched(cells[k])) continue;
                        Plan("scorch", s.Tick + ScorchDelay);
                        break;
                    }
                }
                if (watchReach && !planned.Contains("reach") && ReachVisible(s)) Plan("reach", s.Tick);
            }

            private static bool ReachVisible(Simulation s)
            {
                double radius = s.Config.ContactRadius * ReachScale + ReachLeadTicks * s.Config.PawnSpeed * s.Config.Dt;
                double grace = s.Config.HeadGrace;
                int n = s.Players.Count;
                for (int v = 0; v < n; v++)
                {
                    PlayerState victim = s.Players[v];
                    if (!victim.Alive || victim.Home || victim.Trail.Length <= grace) continue;
                    for (int a = 0; a < n; a++)
                    {
                        if (a == v || (a != Human && v != Human)) continue;
                        PlayerState attacker = s.Players[a];
                        if (!attacker.Alive) continue;
                        if (victim.Trail.ClosestPointWithin(attacker.Pos, radius, victim.Trail.Length - grace, out _, out _)) return true;
                    }
                }
                return false;
            }
        }
    }
}
