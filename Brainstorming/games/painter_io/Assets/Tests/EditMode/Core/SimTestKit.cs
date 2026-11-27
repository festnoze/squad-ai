// Owned by A4 (sim). Shared helpers for the rule (R ids) and scenario (S ids) tests of contract section 10; other agents
// may use them. Pure NUnit + PainterIO.Core (no UnityEngine), NUnit 3.5 features only.
//
// Geometry conventions used by the tests (contract 10.0 item 2): the grid has Origin -32 and CellSize 0.125, so the
// cell-center lines are at n + 0.0625 (H) for integer n and every integer coordinate is a cell edge. Axis-aligned paths
// run on cell-center lines; rectangle territories have integer bounds, so their borders lie on cell edges.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public static class SimTestKit
    {
        /// <summary>Half a cell: n + H is a cell-center line for every integer n.</summary>
        public const double H = 0.0625;

        public const double East = 0.0;
        public const double North = Math.PI * 0.5;
        public const double West = Math.PI;
        public const double South = -Math.PI * 0.5;

        /// <summary>The tick rates of the cross-rate protocol (contract 10.0).</summary>
        public static readonly int[] CrossRates = { 30, 60, 144 };

        /// <summary>Idle corners: far from every scenario of the tests (disc radius 3.5 fits inside the arena).</summary>
        public static readonly Vec2d[] IdleCorners =
        {
            new Vec2d(-24, 24), new Vec2d(24, 24), new Vec2d(24, -24), new Vec2d(-24, -24),
        };

        /// <summary>Test config: instant turns (TurnRateDeg 0, contract 10.0 item 1), ring spawns off unless asked.</summary>
        public static SimConfig Config(int tickRate = 60, bool lassoSpawns = false)
        {
            return new SimConfig { TickRate = tickRate, TurnRateDeg = 0.0, LassoEnabled = lassoSpawns };
        }

        public static Vec2d V(double x, double y) => new Vec2d(x, y);

        // ------------------------------------------------------------------------------------------------------------
        // Territory painting.

        /// <summary>Sets owner on every cell whose center lies in [x0, x1] x [y0, y1] (Void cells are ignored by Set).</summary>
        public static void FillRect(OwnerGrid g, byte owner, double x0, double y0, double x1, double y1)
        {
            double cs = g.CellSize, o = g.Origin;
            int i0 = Math.Max(0, (int)Math.Floor((x0 - o) / cs) - 1);
            int i1 = Math.Min(g.Size - 1, (int)Math.Ceiling((x1 - o) / cs) + 1);
            int j0 = Math.Max(0, (int)Math.Floor((y0 - o) / cs) - 1);
            int j1 = Math.Min(g.Size - 1, (int)Math.Ceiling((y1 - o) / cs) + 1);
            for (int j = j0; j <= j1; j++)
            {
                for (int i = i0; i <= i1; i++)
                {
                    Vec2d c = g.CellCenter(i, j);
                    if (c.X >= x0 && c.X <= x1 && c.Y >= y0 && c.Y <= y1) g.Set(g.Index(i, j), owner);
                }
            }
        }

        /// <summary>Number of cells whose center lies in [x0, x1] x [y0, y1] (all inside the arena in the tests).</summary>
        public static int RectCellCount(OwnerGrid g, double x0, double y0, double x1, double y1)
        {
            int count = 0;
            for (int j = 0; j < g.Size; j++)
            {
                double y = g.CellCenter(0, j).Y;
                if (y < y0 || y > y1) continue;
                for (int i = 0; i < g.Size; i++)
                {
                    double x = g.CellCenter(i, 0).X;
                    if (x >= x0 && x <= x1 && g.Cells[g.Index(i, j)] != OwnerGrid.Void) count++;
                }
            }
            return count;
        }

        public static int CellIndex(OwnerGrid g, double x, double y)
        {
            Assert.IsTrue(g.TryCellOf(new Vec2d(x, y), out int i, out int j), "point outside the grid");
            return g.Index(i, j);
        }

        public static byte OwnerAt(Simulation sim, double x, double y) => sim.Grid.OwnerAt(new Vec2d(x, y));

        // ------------------------------------------------------------------------------------------------------------
        // Scripted paths.

        /// <summary>
        /// HeadingScheduleController from consecutive legs (heading, length in u) at the default PawnSpeed 6: the leg k
        /// starts at time (sum of previous lengths) / 6. Integer lengths give switch times on multiples of 1/6 s (10.0).
        /// The last leg's heading is kept forever.
        /// </summary>
        public static HeadingScheduleController Legs(params (double heading, double length)[] legs)
        {
            var schedule = new (double time, double heading)[legs.Length];
            double t = 0.0;
            for (int k = 0; k < legs.Length; k++)
            {
                schedule[k] = (t, legs[k].heading);
                t += legs[k].length / Tuning.PawnSpeed;
            }
            return new HeadingScheduleController(schedule);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Simulation builder.

        /// <summary>Builds a Simulation from players added in index order, each with its own territory painter.</summary>
        public sealed class SimBuilder
        {
            public readonly SimConfig Config;
            public int HumanIndex = -1;
            public Vec2d? ForcedRingPos;
            private readonly List<Vec2d> starts = new List<Vec2d>();
            private readonly List<double> headings = new List<double>();
            private readonly List<IController> controllers = new List<IController>();
            private readonly List<Action<OwnerGrid, byte>> painters = new List<Action<OwnerGrid, byte>>();

            public SimBuilder(int tickRate = 60, bool lassoSpawns = false)
            {
                Config = SimTestKit.Config(tickRate, lassoSpawns);
            }

            public int Count => starts.Count;

            /// <summary>Player with a rectangle territory (cells whose center lies inside). Returns its index.</summary>
            public int AddRect(double x0, double y0, double x1, double y1, Vec2d start, double heading, IController controller)
            {
                return Add(start, heading, controller, (g, id) => FillRect(g, id, x0, y0, x1, y1));
            }

            /// <summary>Player with a disc territory. Returns its index.</summary>
            public int AddDisc(Vec2d center, double radius, Vec2d start, double heading, IController controller)
            {
                return Add(start, heading, controller, (g, id) => g.FillDisc(center, radius, id));
            }

            /// <summary>Player that stays home forever: start disc at center, HomeCirclerController. Returns its index.</summary>
            public int AddIdle(Vec2d center)
            {
                return AddDisc(center, Tuning.StartDiscRadius, center, 0.0, new HomeCirclerController(center));
            }

            public int Add(Vec2d start, double heading, IController controller, Action<OwnerGrid, byte> painter)
            {
                starts.Add(start);
                headings.Add(heading);
                controllers.Add(controller);
                painters.Add(painter);
                return starts.Count - 1;
            }

            public Simulation Build()
            {
                var paint = painters.ToArray();
                var setup = new SimSetup
                {
                    PlayerCount = starts.Count,
                    StartPositions = starts.ToArray(),
                    StartHeadings = headings.ToArray(),
                    Territory = g =>
                    {
                        for (int i = 0; i < paint.Length; i++) paint[i](g, (byte)(i + 1));
                    },
                    HumanIndex = HumanIndex,
                    ForcedRingPos = ForcedRingPos,
                };
                return new Simulation(Config, controllers.ToArray(), setup);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Shared scenario: the S5 / S6 lasso path (also used by R17b and R19).

        /// <summary>
        /// Player 0 (A) owns [-12, 0] x [-4, 4] and starts at (-0.9375, 0.0625) heading East with legs E 9, S 4, W 4, N 5,
        /// E 2, S 4, W 7: exit at t = 0.15625; the N leg crosses the first leg at X1 = (4.0625, 0.0625) at t = 3.5 (loop =
        /// the 4 x 4 square [4.0625, 8.0625] x [-3.9375, 0.0625]); the S leg crosses the first leg again at (6.0625, 0.0625)
        /// at t = 25/6 and enters the loop square; the W leg crosses the N leg at (4.0625, -2.9375) at t = 5.0; return at
        /// x = 0 at t = 28/6 + 6.0625/6. Player 1 (B) owns [6, 13] x [-6, -1] (partly under the loop) and circles at home.
        /// With a cutter, player 2 comes up x = 5.0625 and touches the loop's bottom leg (y = -3.9375) at t = 4.0.
        /// </summary>
        public static Simulation PocketScenario(int rate, bool charged, out int b, out int c, bool withCutter)
        {
            var sb = new SimBuilder(rate);
            sb.AddRect(-12, -4, 0, 4, V(-1 + H, H), East,
                       Legs((East, 9), (South, 4), (West, 4), (North, 5), (East, 2), (South, 4), (West, 7)));
            b = sb.AddRect(6, -6, 13, -1, V(10.5, -3.5), West, new HomeCirclerController(V(10.5, -3.5)));
            c = -1;
            if (withCutter)
            {
                // Turns back 0.5 u after the contact, so the contact is not decided at a tick boundary.
                c = sb.AddRect(3, -30, 7, -27, V(5 + H, -3.9375 - 0.63 - 24.0), North,
                               new HeadingScheduleController((0.0, North), (4.0 + 1.0 / 12.0, South)));
            }
            Simulation sim = sb.Build();
            if (charged) sim.DebugSetCharged(0, true);
            return sim;
        }

        /// <summary>Return time of the PocketScenario path: the W leg starts at 28/6 s at x = 6.0625.</summary>
        public const double PocketReturnTime = 28.0 / 6.0 + (6 + H) / 6.0;

        // ------------------------------------------------------------------------------------------------------------
        // Event log.

        /// <summary>Records every raised event with the Tick of the Step that raised it.</summary>
        public sealed class EventLog
        {
            public readonly List<SimEvent> All = new List<SimEvent>();
            public readonly List<long> Ticks = new List<long>();
            private readonly Simulation sim;

            public EventLog(Simulation sim)
            {
                this.sim = sim;
                sim.EventRaised += e =>
                {
                    All.Add(e);
                    Ticks.Add(this.sim.Tick);
                };
            }

            /// <summary>Events of a type, optionally for one player (player -2 means any).</summary>
            public List<SimEvent> Of(SimEventType type, int player = -2)
            {
                var result = new List<SimEvent>();
                foreach (SimEvent e in All)
                {
                    if (e.Type == type && (player == -2 || e.Player == player)) result.Add(e);
                }
                return result;
            }

            public int Count(SimEventType type, int player = -2) => Of(type, player).Count;

            public SimEvent First(SimEventType type, int player = -2)
            {
                foreach (SimEvent e in All)
                {
                    if (e.Type == type && (player == -2 || e.Player == player)) return e;
                }
                return null;
            }

            /// <summary>The single event of that type (and player); fails when there are zero or several.</summary>
            public SimEvent Single(SimEventType type, int player = -2)
            {
                List<SimEvent> list = Of(type, player);
                Assert.AreEqual(1, list.Count, "expected exactly one " + type + " (player " + player + ") in:\n" + Dump());
                return list[0];
            }

            public int IndexOf(SimEvent e) => All.IndexOf(e);

            public string Dump()
            {
                var sb = new StringBuilder();
                for (int k = 0; k < All.Count; k++) sb.Append("  [tick ").Append(Ticks[k]).Append("] ").Append(All[k]).Append('\n');
                return sb.ToString();
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Running with invariants (contract 10.1: checked every tick in the scenario runs).

        public static void AssertInvariants(Simulation sim)
        {
            OwnerGrid g = sim.Grid;
            double eps = 1e-9;
            long sum = 0;
            for (int i = 0; i < sim.Players.Count; i++)
            {
                PlayerState p = sim.Players[i];
                string who = "t=" + sim.Time.ToString("R", CultureInfo.InvariantCulture) + " player " + i + ": ";
                Assert.IsFalse(double.IsNaN(p.Pos.X) || double.IsNaN(p.Pos.Y) || double.IsNaN(p.Heading), who + "NaN state");
                sum += g.CountOf(p.Id);
                Assert.AreEqual(p.Trail.IsEmpty, p.Home, who + "trail empty iff home");
                if (p.Alive)
                {
                    Assert.AreEqual(g.Cells[p.Cell] == p.Id, p.Home, who + "Home == (owner(Cell) == Id)");
                    if (!p.Home)
                    {
                        Vec2d end = p.Trail.Points[p.Trail.Count - 1];
                        Assert.That(Vec2d.Distance(end, p.Pos), Is.LessThanOrEqualTo(eps), who + "trail end == Pos");
                    }
                }
                if (p.Spark != null)
                {
                    Assert.IsFalse(double.IsNaN(p.Spark.S), who + "NaN spark");
                    Assert.That(p.Spark.S, Is.LessThanOrEqualTo(p.Trail.Length + 1e-6), who + "spark S <= trail length");
                }
            }
            Assert.That(sum, Is.LessThanOrEqualTo(g.ArenaCellCount), "cells sum <= arena cells");
            Assert.AreEqual(0, sim.EventCapHits, "EventCapHits");
        }

        /// <summary>Steps n ticks (or until the round ends), checking the invariants after each.</summary>
        public static void StepN(Simulation sim, int ticks, bool check = true)
        {
            for (int k = 0; k < ticks && !sim.Ended; k++)
            {
                sim.Step();
                if (check) AssertInvariants(sim);
            }
        }

        /// <summary>Steps while Time &lt; time (or until the round ends), checking the invariants after each tick.</summary>
        public static void RunUntilTime(Simulation sim, double time, bool check = true, Action<Simulation> afterTick = null)
        {
            int guard = 0;
            while (!sim.Ended && sim.Time < time - 1e-9)
            {
                sim.Step();
                if (check) AssertInvariants(sim);
                afterTick?.Invoke(sim);
                if (++guard > 2000000) Assert.Fail("RunUntilTime did not terminate");
            }
        }

        /// <summary>Steps until stop(sim) is true after a tick; returns false if maxTime is reached first.</summary>
        public static bool RunUntil(Simulation sim, Func<Simulation, bool> stop, double maxTime, bool check = true)
        {
            while (!sim.Ended && sim.Time < maxTime - 1e-9)
            {
                sim.Step();
                if (check) AssertInvariants(sim);
                if (stop(sim)) return true;
            }
            return false;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Cross-rate protocol (contract 10.0 item 3).

        /// <summary>What must be identical across tick rates: events (Type, Player, Other, Cause), times within 1e-6 s,
        /// Cells of Return and LassoPocket, and the RoundResult ranks.</summary>
        public sealed class Outcome
        {
            public readonly int Rate;
            public readonly List<SimEvent> Events;
            public readonly int[] Ranks;

            public Outcome(int rate, EventLog log, Simulation sim)
            {
                Rate = rate;
                Events = new List<SimEvent>(log.All);
                Ranks = sim.Ended && sim.Result != null ? (int[])sim.Result.Ranks.Clone() : null;
            }
        }

        public static void AssertSameOutcome(Outcome a, Outcome b, string label)
        {
            string ctx = label + " (" + a.Rate + " Hz vs " + b.Rate + " Hz)";
            Assert.AreEqual(Describe(a.Events), Describe(b.Events), ctx + ": event sequences differ");
            for (int k = 0; k < a.Events.Count; k++)
            {
                SimEvent x = a.Events[k], y = b.Events[k];
                Assert.That(y.Time, Is.EqualTo(x.Time).Within(1e-6), ctx + ": time of event " + k + " " + x.Type);
                if (x.Type == SimEventType.Return || x.Type == SimEventType.LassoPocket)
                {
                    Assert.IsTrue(SameCells(x.Cells, y.Cells), ctx + ": Cells of event " + k + " " + x.Type + " differ ("
                                  + (x.Cells?.Length ?? -1) + " vs " + (y.Cells?.Length ?? -1) + ")");
                }
            }
            if (a.Ranks == null || b.Ranks == null) Assert.AreEqual(a.Ranks == null, b.Ranks == null, ctx + ": round end differs");
            else Assert.AreEqual(a.Ranks, b.Ranks, ctx + ": ranks differ");
        }

        public static string Describe(IEnumerable<SimEvent> events)
        {
            var sb = new StringBuilder();
            foreach (SimEvent e in events)
            {
                sb.Append(e.Type).Append('(').Append(e.Player).Append(',').Append(e.Other).Append(',').Append(e.Cause).Append(") ");
            }
            return sb.ToString();
        }

        public static bool SameCells(int[] a, int[] b)
        {
            if (a == null || b == null) return a == b;
            if (a.Length != b.Length) return false;
            for (int k = 0; k < a.Length; k++)
            {
                if (a[k] != b[k]) return false;
            }
            return true;
        }

        /// <summary>
        /// Runs build(rate) at 30, 60 and 144 Hz until runUntil (or the round end), with invariants every tick, calls
        /// check(rate, sim, log) for each, and asserts identical outcomes (10.0 item 3). Returns the 60 Hz outcome.
        /// </summary>
        public static Outcome CrossRate(string label, Func<int, Simulation> build, double runUntil,
                                        Action<int, Simulation, EventLog> check, Action<Simulation> afterTick = null)
        {
            Outcome reference = null, at60 = null;
            foreach (int rate in CrossRates)
            {
                Simulation sim = build(rate);
                var log = new EventLog(sim);
                RunUntilTime(sim, runUntil, true, afterTick);
                AssertInvariants(sim);
                check(rate, sim, log);
                var outcome = new Outcome(rate, log, sim);
                if (rate == 60) at60 = outcome;
                if (reference == null) reference = outcome;
                else AssertSameOutcome(reference, outcome, label);
            }
            return at60;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Small assertions.

        public static void AssertNear(Vec2d expected, Vec2d actual, double tol, string message)
        {
            Assert.That(Vec2d.Distance(expected, actual), Is.LessThanOrEqualTo(tol),
                        message + ": expected " + expected + " got " + actual);
        }

        /// <summary>True when every element of sub is in sup (both ascending).</summary>
        public static bool IsSubset(int[] sub, int[] sup)
        {
            int k = 0;
            for (int s = 0; s < sub.Length; s++)
            {
                while (k < sup.Length && sup[k] < sub[s]) k++;
                if (k >= sup.Length || sup[k] != sub[s]) return false;
            }
            return true;
        }
    }
}
