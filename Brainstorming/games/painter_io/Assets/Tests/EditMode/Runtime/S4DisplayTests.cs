// Owned by B0a. Contract 10.1 "Runtime EditMode: S4-Display" (brief 7.4: two display frequencies). The three S4 race cases
// (saved before impact, eliminated after impact, exact tie saved) are built as GameSessions at TickRate 60 and driven
// through SimRunner.Advance with frame deltas of 1/30 s, 1/144 s and a jittered 1/50 - 1/90 s sequence. Each must give
// the same outcome, the same Return or SparkCaught time (within EventEpsilonSeconds) and the same StateHash as the plain
// Core run of the same number of ticks.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;

namespace PainterIO.Tests
{
    public class S4DisplayTests
    {
        private const double H = 0.0625;            // half a cell: n + H is a cell-center line
        private const double West = Math.PI;
        private const long RunTicks = 72;           // 1.2 s at 60 Hz, as in the Core S4 tests
        private static readonly Vec2d IdleCenter = new Vec2d(24, 24);

        private enum Expect { Saved, Eliminated }

        private sealed class Race
        {
            public string Name;
            public double D;      // victim start distance to its edge x = 0
            public double G;      // spark gap L - s_cut at the forced cut
            public Expect Expect;
        }

        private static IEnumerable<Race> Races()
        {
            const double tc = 1.013;   // not a tick time at 60 Hz
            yield return new Race { Name = "before", D = 6.0 * (tc - 0.05), G = 4.8 * tc, Expect = Expect.Saved };
            yield return new Race { Name = "after", D = 6.0 * (tc + 0.05), G = 4.8 * tc, Expect = Expect.Eliminated };
            // Exact tie on a common tick time: t_c = 0.5 s, G = 2.4, D = PawnSpeed G / (SparkSpeed - PawnSpeed) = 3.
            yield return new Race { Name = "tie", D = 3.0, G = 2.4, Expect = Expect.Saved };
        }

        private static SimConfig Config()
        {
            return new SimConfig { TickRate = 60, TurnRateDeg = 0.0, LassoEnabled = false };
        }

        private static SimSetup Setup()
        {
            return new SimSetup
            {
                PlayerCount = 2,
                StartPositions = new[] { new Vec2d(-6, H), IdleCenter },
                StartHeadings = new[] { West, 0.0 },
                Territory = g =>
                {
                    FillRect(g, 1, -12, -4, 0, 4);
                    g.FillDisc(IdleCenter, Tuning.StartDiscRadius, 2);
                },
                HumanIndex = -1,
            };
        }

        private static IController[] Controllers()
        {
            return new IController[] { new ConstantHeadingController(West), new HomeCirclerController(IdleCenter) };
        }

        private static void Prepare(Simulation sim, Race race)
        {
            sim.DebugSetTrail(0, new[] { new Vec2d(0, 2 + H), new Vec2d(8 + H, 2 + H), new Vec2d(8 + H, H), new Vec2d(race.D, H) });
            sim.DebugForceCut(0, sim.Players[0].Trail.Length - race.G, 1);
        }

        private static void FillRect(OwnerGrid g, byte owner, double x0, double y0, double x1, double y1)
        {
            for (int j = 0; j < g.Size; j++)
            {
                for (int i = 0; i < g.Size; i++)
                {
                    Vec2d c = g.CellCenter(i, j);
                    if (c.X >= x0 && c.X <= x1 && c.Y >= y0 && c.Y <= y1) g.Set(g.Index(i, j), owner);
                }
            }
        }

        private static float[] Deltas(string mode)
        {
            switch (mode)
            {
                case "30": return new[] { 1f / 30f };
                case "144": return new[] { 1f / 144f };
                default: return new[] { 1f / 50f, 1f / 90f };
            }
        }

        [Test]
        public void S4Display_SameOutcomeTimeAndHashAtThreeDisplayCadences()
        {
            foreach (Race race in Races())
            {
                foreach (string mode in new[] { "30", "144", "jitter" })
                {
                    RunCase(race, mode);
                }
            }
        }

        private static void RunCase(Race race, string mode)
        {
            string label = "S4 " + race.Name + " at display " + mode;

            // Display-driven run through GameSession + SimRunner.
            var session = new GameSession(Config(), Setup(), Controllers(), false);
            Assert.IsFalse(session.AwaitingStart, label + ": test sessions start at once");
            Prepare(session.Sim, race);
            var forwarded = new List<SimEvent>();
            session.EventRaised += e => forwarded.Add(e);
            float[] deltas = Deltas(mode);
            int frame = 0;
            while (session.Sim.Tick < RunTicks && !session.Sim.Ended)
            {
                int steps = session.Runner.Advance(deltas[frame % deltas.Length]);
                Assert.That(steps, Is.LessThanOrEqualTo(SimRunner.MaxStepsPerFrame), label);
                float alpha = session.Alpha;
                Assert.That(alpha, Is.InRange(0f, 1f), label + ": Alpha");
                double sr = session.RenderSparkS(0);
                Spark spark = session.Sim.Players[0].Spark;
                if (spark != null)
                {
                    Assert.IsFalse(double.IsNaN(sr), label + ": RenderSparkS during the chase");
                    Assert.That(sr, Is.InRange(Math.Min(spark.PrevS, spark.S) - 1e-9, Math.Max(spark.PrevS, spark.S) + 1e-9), label);
                }
                else Assert.IsTrue(double.IsNaN(sr), label + ": RenderSparkS is NaN without a spark");
                Assert.Less(++frame, 100000, label + ": runaway");
            }
            long ticks = session.Sim.Tick;

            // Plain Core run of the same number of ticks.
            var core = new Simulation(Config(), Controllers(), Setup());
            Prepare(core, race);
            var coreEvents = new List<SimEvent>();
            core.EventRaised += e => coreEvents.Add(e);
            while (core.Tick < ticks && !core.Ended) core.Step();

            Assert.AreEqual(ticks, core.Tick, label + ": tick count");
            Assert.AreEqual(Describe(coreEvents), Describe(forwarded), label + ": forwarded events == Core events");
            Assert.AreEqual(core.StateHash(), session.Sim.StateHash(), label + ": StateHash");
            Assert.AreEqual(0, session.Sim.EventCapHits, label);

            SimEvent ret = Find(forwarded, SimEventType.Return, 0);
            SimEvent caught = Find(forwarded, SimEventType.SparkCaught, 0);
            if (race.Expect == Expect.Saved)
            {
                Assert.IsNotNull(ret, label + ": saved by a return");
                Assert.IsNull(caught, label + ": no catch");
                Assert.IsTrue(ret.Chased, label + ": the return was chased");
                Assert.IsTrue(session.Sim.Players[0].Alive, label);
                Assert.That(ret.Time, Is.EqualTo(Find(coreEvents, SimEventType.Return, 0).Time).Within(Tuning.EventEpsilonSeconds), label);
            }
            else
            {
                Assert.IsNotNull(caught, label + ": caught by the spark");
                Assert.IsNull(ret, label + ": no return");
                Assert.IsFalse(session.Sim.Players[0].Alive, label);
                Assert.AreEqual(EliminationCause.Spark, session.Sim.Players[0].Cause, label);
                Assert.That(caught.Time, Is.EqualTo(Find(coreEvents, SimEventType.SparkCaught, 0).Time).Within(Tuning.EventEpsilonSeconds), label);
            }
        }

        private static SimEvent Find(List<SimEvent> events, SimEventType type, int player)
        {
            foreach (SimEvent e in events)
            {
                if (e.Type == type && e.Player == player) return e;
            }
            return null;
        }

        private static string Describe(List<SimEvent> events)
        {
            var sb = new System.Text.StringBuilder();
            foreach (SimEvent e in events) sb.Append(e.Type).Append('(').Append(e.Player).Append(',').Append(e.Other).Append(") ");
            return sb.ToString();
        }
    }
}
