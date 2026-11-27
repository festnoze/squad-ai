// Owned by A4 (sim). Brief section 7 scenarios S1-S6 (contract 10.1), each run at TickRate 30, 60 and 144 under the
// cross-rate protocol of contract 10.0 (TurnRateDeg 0, schedule switch times on multiples of 1/6 s, axis-aligned legs on
// cell-center lines; identical event sequences, times within 1e-6 s, identical Return / LassoPocket cells and ranks).
// The invariants of 10.1 and EventCapHits == 0 are checked after every tick (SimTestKit.CrossRate).
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class ScenarioTests
    {
        private const double Eps = 1e-7;   // EventEpsilonSeconds: a catch candidate fires eps after its root

        // ------------------------------------------------------------------------------------------------------------
        // S1: a big closed curve (no self crossing) recolors its interior; cutting through a rival color without
        // returning changes no owner.

        // A: E 9, N 6, W 10, S 3 from (-0.9375, 0.0625); exit x = 0 at 0.15625, return through y = 4 at x = -1.9375.
        // B owns [1, 7] x [5, 11] (2304 cells) and circles at (4, 8.5); A's W leg (y = 6.0625) runs through B's color.
        private static Simulation BuildS1(int rate)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East, Legs((East, 9), (North, 6), (West, 10), (South, 3)));
            b.AddRect(1, 5, 7, 11, V(4, 8.5), North, new HomeCirclerController(V(4, 8.5)));
            return b.Build();
        }

        private const double S1Return = 25.0 / 6.0 + (6 + H - 4.0) / 6.0;

        [Test]
        public void S1_BigClosedCurveRecolorsInteriorAndCrossingARivalChangesNoOwner()
        {
            CrossRate("S1", BuildS1, 5.0, (rate, sim, log) =>
            {
                Assert.That(log.Single(SimEventType.Exit, 0).Time, Is.EqualTo(0.15625).Within(1e-9));
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(S1Return).Within(1e-9));
                Assert.AreEqual(0, log.Count(SimEventType.LassoCrossNoCharge) + log.Count(SimEventType.LassoPocket),
                                "the curve does not cross itself");
                Assert.AreEqual(0, log.Count(SimEventType.Cut));
                // Region enclosed by the trail centerline and A's edge: [0, 8.0625] x [0.0625, 6.0625] plus
                // [-1.9375, 0] x [4, 6.0625]; rim cells add about half a cell along the trail.
                double area = (8 + H) * 6.0 + (2 - H) * (6 + H - 4.0);
                double cells = area / (0.125 * 0.125);
                Assert.That(ret.Cells.Length, Is.GreaterThanOrEqualTo((int)cells), "interior recolored");
                Assert.That(ret.Cells.Length, Is.LessThanOrEqualTo((int)(cells * 1.06)));
                Assert.AreEqual(1, OwnerAt(sim, 4.0, 3.0));
                Assert.AreEqual(1, OwnerAt(sim, 7.9, 0.2));
                Assert.AreEqual(1, OwnerAt(sim, -1.0, 5.0));
                Assert.AreEqual(1, OwnerAt(sim, 4.0, 6 + H), "rival cells under the trail are taken at the return");
                Assert.AreEqual(2, OwnerAt(sim, 4.0, 6.3), "beyond the trail: B keeps them");
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 9.0, 3.0), "outside the curve");
            }, s =>
            {
                // While A is out (before its return) B's color is untouched although A's trail runs through it.
                if (s.Players[0].Alive && !s.Players[0].Home)
                {
                    Assert.AreEqual(2304, s.Grid.CountOf(2), "no owner changes before the return");
                    Assert.AreEqual(2, OwnerAt(s, 4.0, 6 + H));
                }
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // S2 (contract 24, R13 v1.4): a cut near the trail origin while the victim is almost home: the victim wins the
        // race and survives, but its territory is exactly unchanged (no planned area captured, Return.Cells empty, Chased,
        // Margin > 0). This replaces the brief's "the full planned area is captured" (brief 4.4 / 7.2, overridden).

        // Same A path as S1 (return at S1Return). The attacker comes up x = 1.0625 and touches A's first leg (s = 1.0625)
        // at t = 4.0; the control run has the attacker circling at home instead (it shows what the cut denied).
        private static Simulation BuildS2(int rate, bool cut)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East, Legs((East, 9), (North, 6), (West, 10), (South, 3)));
            if (cut) b.AddRect(-1, -26, 3, -22, V(1 + H, H - 0.63 - 24.0), North, new ConstantHeadingController(North));
            else b.AddRect(-1, -26, 3, -22, V(1, -24), North, new HomeCirclerController(V(1, -24)));
            return b.Build();
        }

        [Test]
        public void S2_CutNearTheOriginVictimWinsTheRaceSurvivesAndCapturesNothing()
        {
            const int aStart = 12 * 8 * 64;
            CrossRate("S2", rate => BuildS2(rate, true), 4.8, (rate, sim, log) =>
            {
                SimEvent cut = log.Single(SimEventType.Cut, 0);
                Assert.AreEqual(1, cut.Other);
                Assert.That(cut.Time, Is.EqualTo(4.0).Within(1e-9));
                Assert.That(cut.S, Is.EqualTo(1 + H).Within(1e-9), "near the trail origin");
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(S1Return).Within(1e-9));
                Assert.IsTrue(ret.Chased);
                double l = 6.0 * ret.Time - (1 - H);
                double s = cut.S + 10.8 * (ret.Time - cut.Time);
                Assert.That(ret.Margin, Is.EqualTo((l - s) / 10.8).Within(1e-9), "seconds the spark still needed");
                Assert.That(ret.Margin, Is.GreaterThan(0.0), "the victim won the race");
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught));
                PlayerState a = sim.Players[0];
                Assert.IsTrue(a.Alive, "saved: the victim survives");
                Assert.IsTrue(a.Home);
                Assert.IsNull(a.Spark, "extinguished by the return");

                // Contract 24: the chased return captures nothing.
                Assert.IsNotNull(ret.Cells);
                Assert.AreEqual(0, ret.Cells.Length, "Return.Cells is empty when chased");
                Assert.AreEqual(0, a.Captures, "D2: an empty Return is not a capture");
                Assert.AreEqual(aStart, sim.Grid.CountOf(1), "owned cell count unchanged");
                byte[] before = BuildS2(rate, true).Grid.Cells;
                byte[] after = sim.Grid.Cells;
                int changed = 0;
                for (int k = 0; k < after.Length; k++) changed += after[k] != before[k] ? 1 : 0;
                Assert.AreEqual(0, changed, "the whole grid is exactly as it was at the start (no owner changed)");
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 4.0, 3.0), "the planned interior stays neutral");

                // What the cut denied: the same path without any cut captures the planned area.
                Simulation control = BuildS2(rate, false);
                var controlLog = new EventLog(control);
                RunUntilTime(control, 4.8);
                SimEvent planned = controlLog.Single(SimEventType.Return, 0);
                Assert.IsFalse(planned.Chased);
                Assert.That(planned.Cells.Length, Is.GreaterThan(3000), "the unchased return captures the planned area");
                Assert.AreEqual(1, OwnerAt(control, 4.0, 3.0));
            }, s =>
            {
                Assert.AreEqual(aStart, s.Grid.CountOf(1), "A's territory never changes");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // S3: a cut just behind a far victim: the spark catches it (eliminated, territory neutral, attacker gains
        // nothing); a second cut during the chase does not move or speed the spark.

        // A goes East forever from (-0.9375, 0.0625). B comes down x = 14.0625 and touches A's trail at t = 16.4375 / 6
        // when A's head is at x = 15.5 (s_cut = 14.0625, gap 1.4375 u). C comes up x = 10.0625 and touches A's trail at
        // t = 2.9, during the chase.
        private const double S3Cut = 16.4375 / 6.0;

        private static Simulation BuildS3(int rate)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East, new ConstantHeadingController(East));
            b.AddRect(12, 16, 16, 20, V(14 + H, H + 0.63 + 16.4375), South, new ConstantHeadingController(South));
            b.AddRect(8, -20, 12, -16, V(10 + H, H - 0.63 - 6.0 * 2.9), North, new ConstantHeadingController(North));
            return b.Build();
        }

        [Test]
        public void S3_CutJustBehindAFarVictimTheSparkCatchesItAndASecondCutChangesNothing()
        {
            CrossRate("S3", BuildS3, 3.2, (rate, sim, log) =>
            {
                SimEvent cut = log.Single(SimEventType.Cut, 0);
                Assert.AreEqual(1, cut.Other);
                Assert.That(cut.Time, Is.EqualTo(S3Cut).Within(1e-9));
                Assert.That(cut.S, Is.EqualTo(14 + H).Within(1e-9));
                Assert.AreEqual(0, sim.Players[2].CutsMade, "the second contact cut nothing");
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.AreEqual(1, caught.Other);
                Assert.That(caught.Time, Is.EqualTo(S3Cut + (15.5 - (14 + H)) / 4.8 + Eps).Within(1e-9));
                Assert.That(caught.Time, Is.GreaterThan(2.9), "C's contact happened during the chase");
                SimEvent elim = log.Single(SimEventType.Eliminated, 0);
                Assert.AreEqual(EliminationCause.Spark, elim.Cause);
                Assert.AreEqual(12 * 8 * 64, elim.Cells.Length, "all of A's territory freed");
                foreach (int cell in elim.Cells) Assert.AreEqual(OwnerGrid.Neutral, sim.Grid.Cells[cell], "freed cells are neutral");
                Assert.AreEqual(0, sim.Grid.CountOf(1));
                Assert.AreEqual(16 * 64, sim.Grid.CountOf(2), "the attacker gains nothing");
                Assert.AreEqual(1, sim.Players[1].Kills);
                Assert.IsFalse(sim.Ended, "B and C are still alive");
            }, s =>
            {
                Spark sp = s.Players[0].Spark;
                if (sp == null) return;
                Assert.AreEqual(14 + H, sp.SCut, 1e-9, "not moved by the second cut");
                Assert.AreEqual(1, sp.Attacker);
                Assert.That(sp.S, Is.EqualTo(sp.SCut + 10.8 * (s.Time - sp.TimeCut)).Within(1e-9), "S(t) = s_cut + v (t - t_cut)");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // S4: race timing with DebugSetTrail + DebugForceCut. The victim heads straight West to its edge x = 0 (a cell
        // boundary) from x = d; the spark starts G = L - s_cut behind the head: catch at t_c = G / 4.8, return at d / 6.

        private static Simulation BuildS4(int rate, double d, double g)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-6, H), West, new ConstantHeadingController(West));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 2 + H), V(8 + H, 2 + H), V(8 + H, H), V(d, H) });
            sim.DebugForceCut(0, sim.Players[0].Trail.Length - g, 1);
            return sim;
        }

        [Test]
        public void S4_ReturnStrictlyBeforeImpactIsSaved()
        {
            const double tc = 1.013, tr = tc - 0.05;   // t_c is not a tick time at 30, 60 or 144 Hz
            CrossRate("S4 before", rate => BuildS4(rate, 6.0 * tr, 4.8 * tc), 1.2, (rate, sim, log) =>
            {
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(tr).Within(1e-9));
                Assert.IsTrue(ret.Chased);
                Assert.That(ret.Margin, Is.EqualTo(4.8 * (tc - tr) / 10.8).Within(1e-9));
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught));
                Assert.IsTrue(sim.Players[0].Alive);
            });
        }

        [Test]
        public void S4_ReturnStrictlyAfterImpactIsEliminated()
        {
            const double tc = 1.013, tr = tc + 0.05;
            CrossRate("S4 after", rate => BuildS4(rate, 6.0 * tr, 4.8 * tc), 1.2, (rate, sim, log) =>
            {
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(tc + Eps).Within(1e-9));
                Assert.AreEqual(1, caught.Other);
                Assert.That(caught.DistanceHome, Is.EqualTo(6.0 * (tr - tc)).Within(0.1), "distance to home before Neutralize");
                Assert.AreEqual(0, log.Count(SimEventType.Return));
                Assert.IsFalse(sim.Players[0].Alive);
                Assert.AreEqual(EliminationCause.Spark, sim.Players[0].Cause);
            });
        }

        [Test]
        public void S4_ExactTieIsSaved()
        {
            // Analytic tie on a common tick time: t_c = 0.5 s (3/6 s), G = 2.4, D = PawnSpeed G / (SparkSpeed - PawnSpeed) = 3.
            const double tc = 0.5;
            double g = 4.8 * tc, d = 6.0 * g / 4.8;
            Assert.AreEqual(3.0, d, 1e-12);
            CrossRate("S4 tie", rate => BuildS4(rate, d, g), 1.2, (rate, sim, log) =>
            {
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(tc).Within(1e-6));
                Assert.IsTrue(ret.Chased);
                Assert.That(ret.Margin, Is.GreaterThanOrEqualTo(0.0));
                Assert.That(ret.Margin, Is.LessThan(1e-6), "the spark was at the head");
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), "the return wins an exact tie");
                Assert.IsTrue(sim.Players[0].Alive);
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // S5: charged lasso, cross back through the pocket, return: the score only rises at the return, by at least the
        // pocket area. Replay and get caught: the pocket disappears and the rival cells inside keep their owner.

        [Test]
        public void S5_ChargedLassoScoreRisesOnlyAtTheReturnByAtLeastThePocket()
        {
            int aStart = 12 * 8 * 64;
            CrossRate("S5", rate => PocketScenario(rate, true, out _, out _, false), 6.0, (rate, sim, log) =>
            {
                SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
                Assert.That(pocket.Time, Is.EqualTo(3.5).Within(1e-9));
                AssertNear(V(4 + H, H), pocket.Point, 1e-9, "X1");
                Assert.That(pocket.Cells.Length, Is.GreaterThanOrEqualTo(32 * 32), "the 4 x 4 square and its boundary");
                List<SimEvent> crosses = log.Of(SimEventType.LassoCrossNoCharge, 0);
                Assert.AreEqual(2, crosses.Count, "the later crossings find no charge");
                Assert.That(crosses[0].Time, Is.EqualTo(25.0 / 6.0).Within(1e-9), "back through the pocket");
                Assert.That(crosses[1].Time, Is.EqualTo(5.0).Within(1e-9));
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(PocketReturnTime).Within(1e-9));
                Assert.IsTrue(IsSubset(pocket.Cells, ret.Cells), "the pocket is validated into the capture");
                int gain = sim.Grid.CountOf(1) - aStart;
                Assert.AreEqual(ret.Cells.Length, gain);
                Assert.That(gain, Is.GreaterThanOrEqualTo(pocket.Cells.Length), "score rises by at least the pocket");
                Assert.AreEqual(1, OwnerAt(sim, 7 + H, -2 + H), "rival cell inside the pocket captured at the return");
                Assert.AreEqual(1, OwnerAt(sim, 7.5, -0.5), "loop interior captured through the pocket");
                Assert.AreEqual(0, sim.Players[0].Pocket.Count, "pocket cleared at the return");
            }, s =>
            {
                PlayerState a = s.Players[0];
                if (a.Alive && !a.Home)
                {
                    Assert.AreEqual(aStart, s.Grid.CountOf(1), "score unchanged until the return");
                    Assert.AreEqual(2, OwnerAt(s, 7 + H, -2 + H), "rival cell inside the pending pocket keeps its owner");
                }
            });
        }

        [Test]
        public void S5_CaughtWithAPendingPocketThePocketVanishesAndRivalCellsStay()
        {
            CrossRate("S5 caught", rate =>
            {
                Simulation sim = PocketScenario(rate, true, out _, out _, false);
                long cutTick = (long)Math.Round(28.0 / 6.0 * rate);
                sim.BeforeTick += s =>
                {
                    if (s.Tick == cutTick) s.DebugForceCut(0, s.Players[0].Trail.Length - 2.4, 1);
                };
                return sim;
            }, 6.0, (rate, sim, log) =>
            {
                Assert.AreEqual(1, log.Count(SimEventType.LassoPocket, 0));
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(28.0 / 6.0 + 0.5 + Eps).Within(1e-9));
                Assert.AreEqual(0, log.Count(SimEventType.Return), "caught before the return");
                PlayerState a = sim.Players[0];
                Assert.IsFalse(a.Alive);
                Assert.AreEqual(0, a.Pocket.Count, "elimination erases the pocket");
                Assert.AreEqual(2, OwnerAt(sim, 7 + H, -2 + H), "rival cells inside the pocket keep their owner");
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 7.5, -0.5), "neutral pocket cells stay neutral");
                Assert.AreEqual(0, sim.Grid.CountOf(1), "A's territory is neutral");
                Assert.AreEqual(RoundEndReason.LastSurvivor, sim.Result.Reason);
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // S6: the same trajectory without charge: no pending pocket, LassoCrossNoCharge emitted. Then a chase on a figure
        // 8: the spark follows the arc (crossing passed twice, in arc order), never a straight shortcut.

        [Test]
        public void S6_SameTrajectoryWithoutChargeNoPocketAndTheLoopIsNotCaptured()
        {
            Outcome at60 = CrossRate("S6 no charge", rate => PocketScenario(rate, false, out _, out _, false), 6.0, (rate, sim, log) =>
            {
                Assert.AreEqual(0, log.Count(SimEventType.LassoPocket));
                List<SimEvent> crosses = log.Of(SimEventType.LassoCrossNoCharge, 0);
                Assert.AreEqual(3, crosses.Count);
                Assert.That(crosses[0].Time, Is.EqualTo(3.5).Within(1e-9));
                AssertNear(V(4 + H, H), crosses[0].Point, 1e-9, "same crossing as the charged lasso");
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(PocketReturnTime).Within(1e-9));
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 7.5, -0.5), "R8: the self loop is not captured without a pocket");
                Assert.AreEqual(2, OwnerAt(sim, 7 + H, -2 + H));
                Assert.AreEqual(1, OwnerAt(sim, 2.0, -1.0), "the ordinary (loop-erased) capture happened");
            }, s =>
            {
                Assert.AreEqual(0, s.Players[0].Pocket.Count, "no pending pocket ever");
            });
            // Same path with the charge: the pocket adds the loop on top of the ordinary capture.
            Simulation charged = PocketScenario(60, true, out _, out _, false);
            var chargedLog = new EventLog(charged);
            RunUntilTime(charged, 6.0);
            int gainCharged = chargedLog.Single(SimEventType.Return, 0).Cells.Length;
            int gainPlain = 0;
            foreach (SimEvent e in at60.Events)
            {
                if (e.Type == SimEventType.Return) gainPlain = e.Cells.Length;
            }
            Assert.That(gainPlain, Is.GreaterThan(0));
            Assert.That(gainCharged, Is.GreaterThan(gainPlain + 500), "the pocket is what adds the loop");
        }

        // A: E 7, N 3, W 3, S 6 (crossing its first leg at (3.0625, 0.0625) at t = 16/6), then East 30. The spark is
        // forced at t = 22/6 at s = 1.0625 (arc), when the head is at (6.0625, -2.9375): straight distance 5.83 u, arc
        // distance 20 u. Arcs of the crossing: s1 = 3.0625 (first pass), s2 = 15.0625 (second pass).
        private const double S6Cut = 22.0 / 6.0;
        private const double S6SCut = 1 + H;

        private static Simulation BuildS6Chase(int rate)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East, Legs((East, 7), (North, 3), (West, 3), (South, 6), (East, 30)));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            long cutTick = (long)Math.Round(S6Cut * rate);
            sim.BeforeTick += s =>
            {
                if (s.Tick == cutTick) s.DebugForceCut(0, S6SCut, 1);
            };
            return sim;
        }

        [Test]
        public void S6_FigureEightChaseFollowsTheArcInPassingOrder()
        {
            Simulation current = null;
            Vec2d prevDrawn = Vec2d.Zero;
            bool havePrev = false;
            var sTrack = new List<double>();
            var drawnTrack = new List<Vec2d>();
            bool geometryChecked = false;
            CrossRate("S6 figure 8", BuildS6Chase, 8.0, (rate, sim, log) =>
            {
                Assert.AreEqual(1, log.Count(SimEventType.LassoCrossNoCharge, 0), "the figure 8 crossing");
                Assert.IsTrue(geometryChecked, "the cut geometry was checked");
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                double lCut = 6.0 * S6Cut - (1 - H);
                double expected = S6Cut + (lCut - S6SCut) / (10.8 - 6.0);
                Assert.That(caught.Time, Is.EqualTo(expected + Eps).Within(1e-6), "catch time from the arc distance");
                double lAtCatch = lCut + 6.0 * (caught.Time - S6Cut);
                Assert.That(caught.Time, Is.EqualTo(S6Cut + (lAtCatch - S6SCut) / 10.8).Within(1e-6),
                            "t_cut + (L(t_c) - s_cut) / SparkSpeed");
                // The spark passes the crossing twice, in arc order: s1 = 3.0625 then s2 = 15.0625, both drawn at X.
                Vec2d x = V(3 + H, H);
                int k1 = sTrack.FindIndex(v => v >= 3 + H), k2 = sTrack.FindIndex(v => v >= 15 + H);
                Assert.That(k1, Is.GreaterThan(0));
                Assert.That(k2, Is.GreaterThan(k1), "first pass before second pass");
                double step = 10.8 / rate + 1e-9;
                Assert.That(Vec2d.Distance(drawnTrack[k1], x), Is.LessThanOrEqualTo(step), "drawn at the crossing (first pass)");
                Assert.That(Vec2d.Distance(drawnTrack[k2], x), Is.LessThanOrEqualTo(step), "drawn at the crossing (second pass)");
                Assert.That(Vec2d.Distance(drawnTrack[(k1 + k2) / 2], x), Is.GreaterThan(1.0), "in between it went around the loop");
                sTrack.Clear();
                drawnTrack.Clear();
                geometryChecked = false;
            }, s =>
            {
                if (!ReferenceEquals(s, current))
                {
                    current = s;
                    havePrev = false;
                }
                PlayerState a = s.Players[0];
                if (a.Spark == null)
                {
                    havePrev = false;
                    return;
                }
                if (!geometryChecked)
                {
                    // First tick of the chase: the cut was forced at its start, so PrevPos is the head at the cut
                    // instant. Straight distance cut -> head < half the arc distance (L(t_cut) - s_cut).
                    Assert.That(s.Time - S6Cut, Is.EqualTo(s.Config.Dt).Within(1e-9), "first tick after the cut");
                    double lCut = 6.0 * S6Cut - (1 - H);
                    double straight = Vec2d.Distance(a.Trail.PointAt(S6SCut), a.PrevPos);
                    Assert.That(straight, Is.LessThan(0.5 * (lCut - S6SCut)));
                    AssertNear(V(6 + H, -3 + H), a.PrevPos, 1e-9, "head at the cut instant");
                    geometryChecked = true;
                }
                Vec2d drawn = a.Trail.PointAt(a.Spark.S);
                if (havePrev)
                {
                    Assert.That(Vec2d.Distance(drawn, prevDrawn), Is.LessThanOrEqualTo(10.8 * s.Config.Dt + 1e-9),
                                "the drawn spark never jumps more than SparkSpeed * dt per tick");
                }
                prevDrawn = drawn;
                havePrev = true;
                sTrack.Add(a.Spark.S);
                drawnTrack.Add(drawn);
            });
        }
    }
}
