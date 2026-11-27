// Owned by A4 (sim). Contract 10.1 "Rules" list: one test (or a few) per rule id, named after it. Every test checks the
// invariants after every tick (SimTestKit run helpers) and EventCapHits == 0.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class RulesTests
    {
        private const double Eps = 1e-7;   // EventEpsilonSeconds (catch candidates are shifted by it)

        // ------------------------------------------------------------------------------------------------------------
        // R2 / construction

        [Test]
        public void R2_DefaultStartDiscsAreSymmetricAndHome()
        {
            var cfg = new SimConfig();
            var ctrls = new IController[4];
            for (int i = 0; i < 4; i++) ctrls[i] = new ConstantHeadingController(0.0);
            var sim = new Simulation(cfg, ctrls);
            double d = Tuning.StartDiscOffset;
            Vec2d[] expected = { V(-d, -d), V(d, -d), V(d, d), V(-d, d) };
            int count0 = sim.Grid.CountOf(1);
            double area = Math.PI * Tuning.StartDiscRadius * Tuning.StartDiscRadius / (Tuning.CellSize * Tuning.CellSize);
            Assert.That(count0, Is.EqualTo(area).Within(area * 0.02), "disc cell count vs pi r^2");
            for (int i = 0; i < 4; i++)
            {
                PlayerState p = sim.Players[i];
                Assert.AreEqual(count0, sim.Grid.CountOf(p.Id), "same cell count for player " + i);
                Assert.AreEqual(expected[i], p.Pos, "start position " + i);
                Assert.IsTrue(p.Home, "home at start " + i);
                Assert.AreEqual(p.Id, sim.Grid.Cells[p.Cell], "current cell owned " + i);
                Vec2d toCenter = (-p.Pos).Normalized();
                Assert.That(Geo.WrapAngle(p.Heading - toCenter.Angle()), Is.EqualTo(0.0).Within(1e-12), "heading toward center " + i);
                Assert.AreEqual((byte)(i + 1), p.Id);
                Assert.AreEqual(i == 0, p.IsHuman, "HumanIndex defaults to 0");
            }
            Assert.AreEqual(5400, sim.EndTick);
            Assert.AreEqual(0.0, sim.Time);
            AssertInvariants(sim);
        }

        [Test]
        public void R2_ConstructorRejectsHeadGraceNotAboveStep()
        {
            var cfg = Config(60);
            cfg.HeadGrace = cfg.PawnSpeed / cfg.TickRate;   // equal: must throw
            Assert.Throws<ArgumentException>(() => new Simulation(cfg, new IController[] { null }));
        }

        [Test]
        public void R2_ConfigIsClonedAndEndTickFollowsTheContract()
        {
            var cfg = Config(144);
            cfg.RoundDuration = 1.013;
            var sim = new Simulation(cfg, new IController[] { null, null });
            cfg.TickRate = 30;
            Assert.AreEqual(144, sim.Config.TickRate, "the round keeps its own config copy");
            Assert.AreEqual((long)Math.Ceiling(1.013 * 144 - 1e-9), sim.EndTick);
            RunUntilTime(sim, 10.0);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(sim.EndTick, sim.Tick);
            Assert.AreEqual(1.013, sim.Time, "Time is RoundDuration after the last tick");
            Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R5 exit at a cell edge

        [TestCase(30)]
        [TestCase(60)]
        [TestCase(144)]
        public void R5_ExitStartsExactlyOnTheCellEdge(int rate)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-4, -4, 4, 4, V(2 + H, H), East, new ConstantHeadingController(East));
            Simulation sim = b.Build();
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.5);
            SimEvent exit = log.Single(SimEventType.Exit, 0);
            Assert.That(exit.Time, Is.EqualTo((4.0 - (2 + H)) / 6.0).Within(1e-9), "exit time");
            AssertNear(V(4.0, H), exit.Point, 1e-9, "exit point on the edge x = 4");
            PlayerState p = sim.Players[0];
            Assert.IsFalse(p.Home);
            AssertNear(V(4.0, H), p.Trail.Points[0], 1e-9, "trail starts at the crossing point");
            Assert.That(p.Trail.Length, Is.EqualTo(p.Pos.X - 4.0).Within(1e-9), "trail = exact path since the exit");
        }

        // ------------------------------------------------------------------------------------------------------------
        // R9 territory loss

        // A (player 0) returns with a trail enclosing x in (0, 10.0625), y in (-5.9375, 6.0625); its head starts at
        // (headX, -5.9375) moving West toward its edge x = 0, so the return happens at t = headX / 6.
        private static void AddReturningA(SimBuilder b)
        {
            b.AddRect(-8, -8, 0, 8, V(-4, H), West, new ConstantHeadingController(West));
        }

        private static void SetReturningTrail(Simulation sim, double headX)
        {
            sim.DebugSetTrail(0, new[] { V(0, 6 + H), V(10 + H, 6 + H), V(10 + H, -6 + H), V(headX, -6 + H) });
        }

        [Test]
        public void R9_StolenHomeCellStartsAnExitAtTheHead()
        {
            var b = new SimBuilder(60);
            AddReturningA(b);
            int bIdx = b.AddRect(8, -3, 14, 3, V(9 + H, -2.4375), North, new ConstantHeadingController(North));
            Simulation sim = b.Build();
            SetReturningTrail(sim, 2.0925);
            int bStart = sim.Grid.CountOf(2);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.45);

            double tr = 2.0925 / 6.0;
            SimEvent ret = log.Single(SimEventType.Return, 0);
            SimEvent stolen = log.Single(SimEventType.TerritoryStolen, bIdx);
            SimEvent exit = log.Single(SimEventType.Exit, bIdx);
            Assert.That(ret.Time, Is.EqualTo(tr).Within(1e-9));
            Assert.AreEqual(ret.Time, stolen.Time, "same instant");
            Assert.AreEqual(ret.Time, exit.Time, "same instant");
            Assert.AreEqual(0, stolen.Other, "Other = the returning player that took the cell");
            Assert.That(log.IndexOf(ret) < log.IndexOf(stolen) && log.IndexOf(stolen) < log.IndexOf(exit), "Return, TerritoryStolen, Exit");
            Vec2d headAtReturn = V(9 + H, -2.4375 + 6.0 * tr);
            AssertNear(headAtReturn, exit.Point, 1e-9, "exit at the head");
            PlayerState pb = sim.Players[bIdx];
            Assert.IsTrue(pb.Alive);
            Assert.IsFalse(pb.Home);
            AssertNear(headAtReturn, pb.Trail.Points[0], 1e-9, "trail starts at the head");
            int bNow = sim.Grid.CountOf(2);
            Assert.That(bNow, Is.GreaterThan(0));
            Assert.That(bNow, Is.LessThan(bStart));
            Assert.AreEqual(RectCellCount(sim.Grid, 10.1, -3, 14, 3), bNow, "B keeps only the cells right of the trail rim");
        }

        [Test]
        public void R9b_TrailingPlayerReturnsOnlyOnItsCurrentColor()
        {
            var b = new SimBuilder(60);
            AddReturningA(b);
            int bIdx = b.AddRect(8, -3, 14, 3, V(9 + H, H), West,
                                 new HeadingScheduleController((0.0, West), (1.0 / 3.0, North), (0.5, East)));
            Simulation sim = b.Build();
            SetReturningTrail(sim, 3 + H);
            var log = new EventLog(sim);

            RunUntilTime(sim, 0.7);
            SimEvent exitB = log.Single(SimEventType.Exit, bIdx);
            Assert.That(exitB.Time, Is.EqualTo((1 + H) / 6.0).Within(1e-9));
            SimEvent retA = log.Single(SimEventType.Return, 0);
            Assert.That(retA.Time, Is.EqualTo((3 + H) / 6.0).Within(1e-9));
            Assert.AreEqual(0, log.Count(SimEventType.TerritoryStolen), "B was trailing: nothing to steal");
            // B is back over its stolen exit cells (now A's): no return there.
            PlayerState pb = sim.Players[bIdx];
            Assert.IsFalse(pb.Home);
            Assert.AreEqual(1, sim.Grid.Cells[pb.Cell], "B stands on a cell that A took");
            Assert.AreEqual(1, OwnerAt(sim, 8 + H, H), "B's exit cell now belongs to A");
            Assert.AreEqual(0, log.Count(SimEventType.Return, bIdx));

            RunUntilTime(sim, 1.2);
            SimEvent retB = log.Single(SimEventType.Return, bIdx);
            Assert.That(retB.Time, Is.EqualTo(0.5 + (10.125 - (7 + H)) / 6.0).Within(1e-9), "returns on its current color x >= 10.125");
            Assert.IsTrue(sim.Players[bIdx].Home);
        }

        [Test]
        public void R9_ZeroCellsEliminatesWithFinalCellsBeforeTheCapture()
        {
            var b = new SimBuilder(60);
            AddReturningA(b);
            int bIdx = b.AddRect(6, -3, 9, 3, V(7 + H, -2.4375), North, new ConstantHeadingController(North));
            Simulation sim = b.Build();
            SetReturningTrail(sim, 2.0925);
            int bStart = sim.Grid.CountOf(2);
            Assert.AreEqual(24 * 48, bStart);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.45);

            SimEvent elim = log.Single(SimEventType.Eliminated, bIdx);
            Assert.AreEqual(EliminationCause.TerritoryLost, elim.Cause);
            Assert.AreEqual(0, elim.Other, "Other = the returning player that took the last cells");
            Assert.AreEqual(0, elim.Cells.Length, "nothing left to free");
            Assert.That(elim.Time, Is.EqualTo(2.0925 / 6.0).Within(1e-9));
            PlayerState pb = sim.Players[bIdx];
            Assert.IsFalse(pb.Alive);
            Assert.AreEqual(bStart, pb.FinalCells, "FinalCells = cells held just before the capture");
            Assert.AreEqual(EliminationCause.TerritoryLost, pb.Cause);
            Assert.AreEqual(2, sim.RankOf(bIdx));
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.LastSurvivor, sim.Result.Reason);
            Assert.AreEqual(new List<int> { 0 }, sim.Result.Winners);
            Assert.AreEqual(bStart, sim.Result.FinalCells[bIdx]);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R10 contacts

        [Test]
        public void R10_HeadThroughHeadDoesNothing()
        {
            var b = new SimBuilder(60);
            b.AddRect(-12, -2, -8, 2, V(-9 + H, H), East, new ConstantHeadingController(East));
            b.AddRect(-2, -12, 2, -8, V(H, -9 + H), North, new ConstantHeadingController(North));
            Simulation sim = b.Build();
            var log = new EventLog(sim);
            double minDistance = double.PositiveInfinity;
            RunUntilTime(sim, 2.2, true, s =>
            {
                double dd = Vec2d.Distance(s.Players[0].Pos, s.Players[1].Pos);
                if (dd < minDistance) minDistance = dd;
            });
            Assert.That(minDistance, Is.LessThan(1e-6), "the heads met");
            Assert.AreEqual(0, log.Count(SimEventType.Cut));
            Assert.IsTrue(sim.Players[0].Alive && sim.Players[1].Alive);
            Assert.IsFalse(sim.Players[0].Home || sim.Players[1].Home, "both trailing all along");
        }

        [Test]
        public void R10_OwnTrailNeverCuts()
        {
            var b = new SimBuilder(60);
            b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East,
                      Legs((East, 4), (North, 2), (West, 2), (South, 4), (East, 10)));
            Simulation sim = b.Build();
            var log = new EventLog(sim);
            // The S leg (x = 1.0625) runs over the first leg's point (1.0625, 0.0625), exposed long ago (arc 1.0625).
            double closest = double.PositiveInfinity;
            RunUntilTime(sim, 3.0, true, s =>
            {
                double dd = Vec2d.Distance(s.Players[0].Pos, V(1 + H, H));
                if (s.Time > 1.5 && dd < closest) closest = dd;
            });
            Assert.That(closest, Is.LessThan(1e-9), "the head went over its own exposed trail");
            Assert.AreEqual(0, log.Count(SimEventType.Cut));
            Assert.IsNull(sim.Players[0].Spark);
            Assert.IsTrue(sim.Players[0].Alive);
            Assert.AreEqual(0, sim.Players[0].CutsMade);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R11 spark spawn

        [Test]
        public void R11_SuperposedPassesPickTheLatestPass()
        {
            var b = new SimBuilder(60);
            b.AddRect(-6, -3, 0, 3, V(-1 + H, H), East, Legs((East, 7), (West, 4), (North, 10)));
            int att = b.AddRect(2, 12, 6, 16, V(4 + H, 12.6925), South, new ConstantHeadingController(South));
            Simulation sim = b.Build();
            var log = new EventLog(sim);
            RunUntilTime(sim, 2.1);
            SimEvent cut = log.Single(SimEventType.Cut, 0);
            Assert.AreEqual(att, cut.Other);
            Assert.That(cut.Time, Is.EqualTo(2.0).Within(1e-9));
            Assert.That(cut.S, Is.EqualTo(8.0625).Within(1e-9), "second pass at x = 4.0625: 6.0625 + 2");
            AssertNear(V(4 + H, H), cut.Point, 1e-9, "cut point");
            Assert.That(sim.Players[0].Spark.SCut, Is.EqualTo(8.0625).Within(1e-9));
        }

        [Test]
        public void R11_TwoAttackersSameInstantLargestSWins()
        {
            var b = new SimBuilder(60);
            b.AddRect(-6, -3, 0, 3, V(-1 + H, H), East, new ConstantHeadingController(East));
            int a1 = b.AddRect(1, 12, 5, 16, V(3 + H, 12.6925), South, new ConstantHeadingController(South));
            int a2 = b.AddRect(5, 12, 9, 16, V(7 + H, 12.6925), South, new ConstantHeadingController(South));
            Simulation sim = b.Build();
            var log = new EventLog(sim);
            RunUntilTime(sim, 2.1);
            SimEvent cut = log.Single(SimEventType.Cut, 0);
            Assert.That(cut.Time, Is.EqualTo(2.0).Within(1e-9));
            Assert.AreEqual(a2, cut.Other, "the cut closest to the head (largest s) wins");
            Assert.That(cut.S, Is.EqualTo(7 + H).Within(1e-9));
            Assert.AreEqual(a2, sim.Players[0].Spark.Attacker);
            Assert.AreEqual(1, sim.Players[a2].CutsMade);
            Assert.AreEqual(0, sim.Players[a1].CutsMade, "only the winning attacker gets CutsMade++");
        }

        [Test]
        public void R11b_ChasedVictimCutsAnotherPlayerDuringItsFlight()
        {
            var b = new SimBuilder(60);
            b.AddRect(-12, -2, -8, 2, V(-10, H), East, new ConstantHeadingController(East));
            int credited = b.AddIdle(IdleCorners[1]);
            int c = b.AddRect(0, -12, 4, -8, V(2, -10), East, new ConstantHeadingController(East));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-8, H), V(-2 + H, H) });
            sim.DebugSetTrail(c, new[] { V(2 + H, -8), V(2 + H, 4 + H), V(3 + H, 4 + H) });
            sim.DebugForceCut(0, 0.0, credited);
            var log = new EventLog(sim);
            bool chasedAtCut = false;
            RunUntil(sim, s =>
            {
                if (s.LastEvents.Count > 0 && s.Players[c].Spark != null) chasedAtCut = s.Players[0].Spark != null;
                return s.Players[c].Spark != null;
            }, 1.0);
            SimEvent cut = log.Single(SimEventType.Cut, c);
            Assert.AreEqual(0, cut.Other, "the chased victim is the attacker");
            Assert.That(cut.Time, Is.EqualTo((2 + H - 0.63 + (2 - H)) / 6.0).Within(1e-9));
            Assert.That(cut.S, Is.EqualTo(8 + H).Within(1e-9));
            Assert.IsTrue(chasedAtCut, "player 0 still had its spark when it cut");
            Assert.AreEqual(1, sim.Players[0].CutsMade);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R12 spark motion

        [Test]
        public void R12b_SparkKeepsGoingAfterItsAttackerDiesAndKillsAreCredited()
        {
            var b = new SimBuilder(60);
            b.AddRect(-12, -2, -8, 2, V(-10, H), East, new ConstantHeadingController(East));
            int a = b.AddRect(2, 12, 6, 16, V(4, 14), South, new ConstantHeadingController(South));
            int c = b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-8, H), V(6 + H, H) });
            sim.DebugSetTrail(a, new[] { V(4 + H, 12), V(4 + H, 3 + H) });
            double la = sim.Players[a].Trail.Length;
            sim.DebugForceCut(a, la - 2.88, c);
            var log = new EventLog(sim);
            double prevS = double.NegativeInfinity;
            RunUntilTime(sim, 2.0, true, s =>
            {
                Spark sp = s.Players[0].Spark;
                if (sp == null) return;
                Assert.That(sp.S, Is.EqualTo(sp.SCut + s.Config.SparkSpeed * (s.Time - sp.TimeCut)).Within(1e-9), "closed form S");
                Assert.That(sp.S, Is.GreaterThan(prevS), "the spark keeps moving");
                prevS = sp.S;
            });

            SimEvent cut = log.Single(SimEventType.Cut, 0);
            Assert.AreEqual(a, cut.Other);
            Assert.That(cut.Time, Is.EqualTo((3 + H - (H + 0.63)) / 6.0).Within(1e-9));
            Assert.That(cut.S, Is.EqualTo(12 + H).Within(1e-9));
            SimEvent caughtA = log.Single(SimEventType.SparkCaught, a);
            Assert.That(caughtA.Time, Is.EqualTo(0.6 + Eps).Within(1e-9));
            Assert.AreEqual(c, caughtA.Other);
            SimEvent caughtV = log.Single(SimEventType.SparkCaught, 0);
            Assert.AreEqual(a, caughtV.Other, "the dead attacker's spark");
            double expected = cut.Time + (sim.Config.PawnSpeed * cut.Time + (14 + H) - cut.S) / 4.8;
            Assert.That(caughtV.Time, Is.EqualTo(expected + Eps).Within(1e-9));
            Assert.That(caughtV.Time, Is.GreaterThan(caughtA.Time));
            Assert.AreEqual(1, sim.Players[a].Kills, "Kills credited even though the attacker is dead");
            Assert.AreEqual(1, sim.Players[c].Kills);
            Assert.AreEqual(RoundEndReason.LastSurvivor, sim.Result.Reason);
            Assert.AreEqual(new[] { 2, 3, 1 }, sim.Result.Ranks);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R13 race and R14 cut at closure (victim returns toward x = 0; attacker crosses its right leg at x = 4.0625)

        private static Simulation RaceSetup(int rate, double headX, double attackerX)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-6, H), West, new ConstantHeadingController(West));
            b.AddRect(7, -2, 10, 2, V(attackerX, H), West, new ConstantHeadingController(West));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 3 + H), V(4 + H, 3 + H), V(4 + H, -2 + H), V(headX, -2 + H) });
            return sim;
        }

        [Test]
        public void R13b_CutThenReturnInOneTickIsSavedAndChased()
        {
            // TickRate 30, tick 15 starts at t = 0.5: cut at u = 0.3 (t = 0.51), return at u = 0.7 (t = 0.523333).
            Simulation sim = RaceSetup(30, 6.0 * (0.5 + 0.7 / 30.0), 4 + H + 0.63 + 6.0 * (0.5 + 0.3 / 30.0));
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            SimEvent cut = log.Single(SimEventType.Cut, 0);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.That(cut.Time, Is.EqualTo(0.51).Within(1e-9));
            Assert.That(ret.Time, Is.EqualTo(0.5 + 0.7 / 30.0).Within(1e-9));
            Assert.AreEqual(15, log.Ticks[log.IndexOf(cut)], "cut in tick 15");
            Assert.AreEqual(15, log.Ticks[log.IndexOf(ret)], "return in the same tick");
            Assert.That(log.IndexOf(cut), Is.LessThan(log.IndexOf(ret)), "Cut then Return");
            Assert.IsTrue(ret.Chased, "saved");
            Assert.That(ret.Margin, Is.GreaterThan(0.0));
            // Margin = (L - S) / SparkSpeed at the return: L = L0 + 6 t_r with L0 = 4.0625 + 5 + (4.0625 - x_head).
            double l = (4 + H) + 5 + (4 + H - 6.0 * ret.Time) + 6.0 * ret.Time;
            double s = 7 + H + 10.8 * (ret.Time - cut.Time);
            Assert.That(ret.Margin, Is.EqualTo((l - s) / 10.8).Within(1e-9));
            Assert.AreEqual(0, log.Count(SimEventType.SparkCaught));
            Assert.IsTrue(sim.Players[0].Alive && sim.Players[0].Home);
            Assert.IsNull(sim.Players[0].Spark, "the spark is extinguished");
            // Contract 24 (R13 v1.4): saved, but a chased return captures nothing.
            Assert.IsNotNull(ret.Cells);
            Assert.AreEqual(0, ret.Cells.Length, "Return.Cells is empty when Chased");
            Assert.AreEqual(12 * 8 * 64, sim.Grid.CountOf(1), "territory unchanged");
            Assert.AreEqual(0, sim.Players[0].Captures);
        }

        [Test]
        public void R13b_ReturnThenCutTimeInOneTickGivesNoCut()
        {
            Simulation sim = RaceSetup(30, 6.0 * (0.5 + 0.3 / 30.0), 4 + H + 0.63 + 6.0 * (0.5 + 0.7 / 30.0));
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.That(ret.Time, Is.EqualTo(0.51).Within(1e-9));
            Assert.IsFalse(ret.Chased);
            Assert.AreEqual(0.0, ret.Margin);
            Assert.AreEqual(0, log.Count(SimEventType.Cut));
        }

        // ------------------------------------------------------------------------------------------------------------
        // R13c / R13d (contract 24): player 0 (A) follows the PocketScenario path (charged lasso pocket at t = 3.5 that
        // holds B's cell (7.0625, -1.9375), return at PocketReturnTime); a third player C owns the column [0.5, 4] x
        // [-28, -5]. In R13c, C comes up x = 1.0625, touches A's first leg (s = 1.0625) at t = 4.25, after the pocket, and
        // turns back home at t = 26/6 (its back-and-forth trail captures nothing). The spark starts 23.5 u behind A's head
        // (catch at about t = 9.15), so A is saved with a margin of about 1.5 s. In R13d (control) C circles inside its
        // column and nothing cuts A.

        private const double PocketCutTime = 4.25;
        private const int PocketCutA = 12 * 8 * 64, PocketCutB = 56 * 40, PocketCutC = 28 * 184;

        private static Simulation PocketCutScenario(int rate, bool cut)
        {
            var sb = new SimBuilder(rate);
            sb.AddRect(-12, -4, 0, 4, V(-1 + H, H), East,
                       Legs((East, 9), (South, 4), (West, 4), (North, 5), (East, 2), (South, 4), (West, 7)));
            sb.AddRect(6, -6, 13, -1, V(10.5, -3.5), West, new HomeCirclerController(V(10.5, -3.5)));
            if (cut)
                sb.AddRect(0.5, -28, 4, -5, V(1 + H, H - 0.63 - 6.0 * PocketCutTime), North,
                           new HeadingScheduleController((0.0, North), (26.0 / 6.0, South)));
            else
                sb.AddRect(0.5, -28, 4, -5, V(2.25, -15), North, new HomeCirclerController(V(2.25, -15)));
            Simulation sim = sb.Build();
            Assert.AreEqual(PocketCutA, sim.Grid.CountOf(1));
            Assert.AreEqual(PocketCutB, sim.Grid.CountOf(2));
            Assert.AreEqual(PocketCutC, sim.Grid.CountOf(3));
            sim.DebugSetCharged(0, true);
            return sim;
        }

        [Test]
        public void R13c_PocketThenCutThenSavedReturnErasesThePocketAndCapturesNothing()
        {
            CrossRate("R13c", rate => PocketCutScenario(rate, true), 6.0, (rate, sim, log) =>
            {
                SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
                Assert.That(pocket.Time, Is.EqualTo(3.5).Within(1e-9));
                Assert.IsTrue(Array.BinarySearch(pocket.Cells, CellIndex(sim.Grid, 7 + H, -2 + H)) >= 0, "B's cell is in the pocket");
                SimEvent cut = log.Single(SimEventType.Cut, 0);
                Assert.AreEqual(2, cut.Other);
                Assert.That(cut.Time, Is.EqualTo(PocketCutTime).Within(1e-9));
                Assert.That(cut.S, Is.EqualTo(1 + H).Within(1e-9), "near the trail origin");
                Assert.That(log.IndexOf(pocket), Is.LessThan(log.IndexOf(cut)), "the pocket was pending before the cut");
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(PocketReturnTime).Within(1e-9));
                Assert.IsTrue(ret.Chased, "saved from the spark");
                Assert.That(ret.Margin, Is.GreaterThan(1.0));
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught));
                Assert.AreEqual(0, ret.Cells.Length, "no ordinary capture and no pocket");

                PlayerState a = sim.Players[0];
                Assert.IsTrue(a.Alive && a.Home, "A survives");
                Assert.IsNull(a.Spark);
                Assert.AreEqual(0, a.Pocket.Count, "the pocket is erased, not validated");
                Assert.AreEqual(1, a.PocketsMade);
                Assert.AreEqual(0, a.Captures);
                Assert.AreEqual(PocketCutA, sim.Grid.CountOf(1), "A's owned cell count is unchanged");
                Assert.AreEqual(2, OwnerAt(sim, 7 + H, -2 + H), "the rival cell inside the pocket keeps its owner");
                Assert.AreEqual(PocketCutB, sim.Grid.CountOf(2), "B keeps every cell");
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 7.5, -0.5), "neutral pocket cells stay neutral");
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 2.0, -1.0), "the ordinary capture region stays neutral");
                Assert.AreEqual(PocketCutC, sim.Grid.CountOf(3), "C's back-and-forth trail captured nothing");
                Assert.IsTrue(sim.Players[2].Home, "C is back home");
            }, s =>
            {
                Assert.AreEqual(PocketCutA, s.Grid.CountOf(1), "A's territory never changes");
                Assert.AreEqual(2, OwnerAt(s, 7 + H, -2 + H), "B's cell never changes owner");
            });
        }

        [Test]
        public void R13d_SameScenarioWithoutTheCutTheReturnCapturesThePocketAndTheOrdinaryArea()
        {
            CrossRate("R13d", rate => PocketCutScenario(rate, false), 6.0, (rate, sim, log) =>
            {
                Assert.AreEqual(0, log.Count(SimEventType.Cut), "control: nobody cuts A");
                SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
                Assert.That(pocket.Time, Is.EqualTo(3.5).Within(1e-9));
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(PocketReturnTime).Within(1e-9));
                Assert.IsFalse(ret.Chased);
                Assert.AreEqual(0.0, ret.Margin);
                Assert.IsTrue(IsSubset(pocket.Cells, ret.Cells), "the pocket is validated into the capture");
                Assert.That(ret.Cells.Length, Is.GreaterThan(pocket.Cells.Length), "pocket + ordinary capture");
                Assert.AreEqual(PocketCutA + ret.Cells.Length, sim.Grid.CountOf(1), "the score rises by the capture");
                Assert.AreEqual(1, OwnerAt(sim, 7 + H, -2 + H), "the rival cell inside the pocket is taken");
                Assert.AreEqual(1, OwnerAt(sim, 7.5, -0.5), "the loop interior is captured through the pocket");
                Assert.AreEqual(1, OwnerAt(sim, 2.0, -1.0), "the ordinary capture happened");
                Assert.AreEqual(PocketCutC, sim.Grid.CountOf(3), "C is not involved");
                PlayerState a = sim.Players[0];
                Assert.AreEqual(1, a.Captures);
                Assert.AreEqual(0, a.Pocket.Count, "pocket cleared at the return");
            });
        }

        [TestCase(30)]
        [TestCase(60)]
        [TestCase(144)]
        public void R14_CutAtTheClosureInstantIsIgnored(int rate)
        {
            Simulation sim = RaceSetup(rate, 6.0 * 0.51, 4 + H + 0.63 + 6.0 * 0.51);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.That(ret.Time, Is.EqualTo(0.51).Within(1e-9));
            Assert.IsFalse(ret.Chased);
            Assert.AreEqual(0, log.Count(SimEventType.Cut), "returns resolve first: the cut has no effect\n" + log.Dump());
            Assert.IsNull(sim.Players[0].Spark);
            Assert.AreEqual(0, sim.Players[1].CutsMade);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R15 ring

        // A (player 0) owns y < 0 and moves East along y = -0.6875; B (player 1) owns y > 0 and moves East along
        // y = +0.6875: mirror images, so both enter the pickup disc of a ring at the origin at bit-identical instants.
        private const double RingY = 0.6875;
        private static readonly double ChordHalf = Math.Sqrt(1.05 * 1.05 - RingY * RingY);
        private const double EnterTime = 0.55;

        [Test]
        public void R15_ContestedRingGoesToTheOneLeftWhenTheOtherLeaves()
        {
            double x0 = -ChordHalf - 6.0 * EnterTime;
            var b = new SimBuilder(60);
            b.AddRect(-6, -6, 6, 0, V(x0, -RingY), East, new ConstantHeadingController(East));
            b.AddRect(-6, 0, 6, 6, V(x0, RingY), East, new HeadingScheduleController((0.0, East), (0.6, North)));
            Simulation sim = b.Build();
            sim.DebugPlaceRing(V(0, 0));
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            Assert.AreEqual(0, log.Count(SimEventType.RingPicked), "both in contact: nobody picks");
            Assert.IsNotNull(sim.Ring);
            double xb = sim.Players[1].Pos.X;
            double bOut = 0.6 + (Math.Sqrt(1.05 * 1.05 - xb * xb) - RingY) / 6.0;
            RunUntilTime(sim, 1.0);
            SimEvent pick = log.Single(SimEventType.RingPicked);
            Assert.AreEqual(0, pick.Player);
            Assert.That(pick.Time, Is.EqualTo(bOut).Within(1e-9), "A picks at B's exit instant");
            Assert.IsTrue(sim.Players[0].Charged);
            Assert.IsNull(sim.Ring);
            Assert.That(sim.NextRingTime, Is.EqualTo(pick.Time + sim.Config.LassoRespawn).Within(1e-12));
        }

        [Test]
        public void R15_ContestedRingGoesToTheOneLeftWhenTheOtherIsEliminated()
        {
            double x0 = -ChordHalf - 6.0 * EnterTime;
            var b = new SimBuilder(60);
            b.AddRect(-6, -6, 6, 0, V(x0, -RingY), East, new ConstantHeadingController(East));
            b.AddRect(10, 10, 14, 14, V(12, 12), East, new ConstantHeadingController(East));
            int idle = b.AddIdle(IdleCorners[3]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(1, new[] { V(x0 - 5, RingY), V(x0, RingY) });
            sim.DebugForceCut(1, 5.0 - 4.8 * 0.65, idle);   // caught at t = 0.65, while both are in contact
            sim.DebugPlaceRing(V(0, 0));
            var log = new EventLog(sim);
            RunUntilTime(sim, 1.0);
            SimEvent caught = log.Single(SimEventType.SparkCaught, 1);
            Assert.That(caught.Time, Is.EqualTo(0.65 + Eps).Within(1e-9));
            SimEvent pick = log.Single(SimEventType.RingPicked);
            Assert.AreEqual(0, pick.Player);
            Assert.That(pick.Time, Is.EqualTo(caught.Time).Within(1e-12), "picked at the elimination instant");
            Assert.That(log.IndexOf(pick), Is.GreaterThan(log.IndexOf(caught)));
        }

        [Test]
        public void R15_ChargedHeadOnTheRingThatSpendsItsChargeInALassoPicksAtOnce()
        {
            // The charged head comes down x = -0.9375 through the ring and crosses its own old segment (y = 0.0925, off
            // the tick lattice) at t = 1.97 / 6 while still in contact: the lasso spends the charge, the ring goes at once.
            var b = new SimBuilder(60);
            b.AddRect(10, -14, 14, -10, V(12, -12), South, new ConstantHeadingController(South));
            b.AddIdle(IdleCorners[0]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-8, 0.0925), V(1 + H, 0.0925), V(1 + H, 2 + H), V(-1 + H, 2 + H) });
            sim.DebugSetCharged(0, true);
            Vec2d ring = V(-0.4375, 0.5);
            sim.DebugPlaceRing(ring);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.25);
            Assert.That(Vec2d.Distance(sim.Players[0].Pos, ring), Is.LessThan(1.05), "sitting on the ring");
            Assert.IsNotNull(sim.Ring, "charged: the ring stays");
            RunUntilTime(sim, 0.6);
            SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
            Assert.That(pocket.Time, Is.EqualTo((2 + H - 0.0925) / 6.0).Within(1e-9), "crossing at (-0.9375, 0.0925)");
            Assert.That(Vec2d.Distance(pocket.Point, ring), Is.LessThan(1.05), "the crossing happens on the ring");
            SimEvent pick = log.Single(SimEventType.RingPicked, 0);
            Assert.That(pick.Time, Is.EqualTo(pocket.Time).Within(1e-12), "picked as soon as the charge is spent");
            Assert.IsTrue(sim.Players[0].Charged);
            Assert.AreEqual(1, sim.Players[0].PocketsMade);
        }

        [Test]
        public void R15_ChargedPlayerLeavesTheRing()
        {
            var b = new SimBuilder(60);
            b.AddRect(-6, -6, 6, 0, V(-4, -0.4375), East, new ConstantHeadingController(East));
            b.AddRect(-6, 0, 6, 6, V(-2, 4.0625), East, new HeadingScheduleController((0.0, East), (0.5, South)));
            Simulation sim = b.Build();
            sim.DebugSetCharged(0, true);
            sim.DebugPlaceRing(V(0, 0.4));
            var log = new EventLog(sim);
            RunUntilTime(sim, 1.2);
            Assert.That(sim.Players[0].Pos.X, Is.GreaterThan(1.5), "A went through the ring");
            Assert.AreEqual(0, log.Count(SimEventType.RingPicked, 0), "a charged player leaves the ring in place");
            Assert.IsTrue(sim.Players[0].Charged);
            // B (uncharged) comes down x = 1 through the ring later and takes it.
            RunUntilTime(sim, 2.0);
            Assert.AreEqual(1, log.Count(SimEventType.RingPicked, 1));
            Assert.IsNull(sim.Ring);
        }

        [Test]
        public void R15b_FirstRingAtFifteenSecondsOnNeutralGround()
        {
            var cfg = new SimConfig { TurnRateDeg = 0.0, LassoEnabled = true, Seed = 12345 };
            var ctrls = new IController[4];
            double d = Tuning.StartDiscOffset;
            Vec2d[] centers = { V(-d, -d), V(d, -d), V(d, d), V(-d, d) };
            for (int i = 0; i < 4; i++) ctrls[i] = new HomeCirclerController(centers[i]);
            var sim = new Simulation(cfg, ctrls);
            var log = new EventLog(sim);
            while (sim.Time < 15.0 - 1e-9)
            {
                Assert.IsNull(sim.Ring, "no ring before 15 s");
                sim.Step();
                AssertInvariants(sim);
            }
            Assert.AreEqual(900, sim.Tick);
            Assert.IsNotNull(sim.Ring, "the ring appears at the first tick with Time >= 15 s");
            SimEvent spawned = log.Single(SimEventType.RingSpawned);
            Assert.AreEqual(15.0, spawned.Time);
            Assert.AreEqual(15.0, sim.Ring.SpawnTime);
            Assert.IsTrue(GridQueries.IsNeutralDisc(sim.Grid, sim.Ring.Pos, sim.Config.RingClearance), "neutral ground");
            for (int i = 0; i < 4; i++)
                Assert.That(Vec2d.Distance(sim.Players[i].Pos, sim.Ring.Pos), Is.GreaterThanOrEqualTo(sim.Config.RingMinHeadDistance));
            Assert.That(sim.Arena.SignedDistance(sim.Ring.Pos), Is.LessThan(-sim.Config.ArenaMargin));
        }

        [Test]
        public void R15b_NextRingFifteenSecondsAfterThePickupNeverTwo()
        {
            var b = new SimBuilder(60, lassoSpawns: true);
            Vec2d center = V(-16, -16);
            b.AddIdle(center);
            b.AddIdle(IdleCorners[1]);
            b.ForcedRingPos = V(-16 + 1.5, -16);   // on player 0's orbit
            Simulation sim = b.Build();
            var log = new EventLog(sim);
            RunUntil(sim, s => s.Ring != null, 16.0);
            Assert.AreEqual(15.0, sim.Time);
            RunUntil(sim, s => s.Ring == null, 20.0);
            SimEvent pick = log.Single(SimEventType.RingPicked, 0);
            double next = pick.Time + 15.0;
            Assert.AreEqual(next, sim.NextRingTime);
            int spawnsAtPick = log.Count(SimEventType.RingSpawned);
            while (sim.Time < next - 1e-9)
            {
                Assert.IsNull(sim.Ring, "no ring before pickup + 15 s");
                sim.Step();
                AssertInvariants(sim);
            }
            Assert.IsNotNull(sim.Ring);
            Assert.That(sim.Time - next, Is.LessThan(sim.Config.Dt + 1e-12), "spawned at the first tick with Time >= pickup + 15 s");
            Assert.AreEqual(spawnsAtPick + 1, log.Count(SimEventType.RingSpawned));
            // Player 0 is charged: it orbits through the ring and leaves it; never a second ring.
            RunUntilTime(sim, sim.Time + 10.0, true, s =>
            {
                Assert.That(log.Count(SimEventType.RingSpawned), Is.LessThanOrEqualTo(log.Count(SimEventType.RingPicked) + 1));
            });
            Assert.AreEqual(1, log.Count(SimEventType.RingPicked), "charged: the ring stays");
            Assert.IsNotNull(sim.Ring);
        }

        [Test]
        public void R15b_ChargeIsKeptAcrossExits()
        {
            var b = new SimBuilder(60);
            // Two out-and-back excursions from the rectangle (exit x = 0), no self crossing.
            b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East,
                      Legs((East, 3), (North, 2), (West, 3), (South, 4), (East, 3), (South, 1), (West, 5)));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetCharged(0, true);
            var log = new EventLog(sim);
            RunUntilTime(sim, 4.0);
            Assert.AreEqual(2, log.Count(SimEventType.Exit, 0));
            Assert.AreEqual(2, log.Count(SimEventType.Return, 0));
            Assert.AreEqual(0, log.Count(SimEventType.LassoPocket));
            Assert.IsTrue(sim.Players[0].Charged, "an unused charge persists across exits");
        }

        [Test]
        public void R15b_LassoDisabledGivesNoRingInNinetySecondsAndTimeUpTieSharesFirst()
        {
            var cfg = new SimConfig { TurnRateDeg = 0.0, LassoEnabled = false };
            var ctrls = new IController[4];
            double d = Tuning.StartDiscOffset;
            Vec2d[] centers = { V(-d, -d), V(d, -d), V(d, d), V(-d, d) };
            for (int i = 0; i < 4; i++) ctrls[i] = new HomeCirclerController(centers[i]);
            var sim = new Simulation(cfg, ctrls);
            var log = new EventLog(sim);
            while (!sim.Ended)
            {
                sim.Step();
                Assert.IsNull(sim.Ring);
                if (sim.Tick % 60 == 0) AssertInvariants(sim);
            }
            AssertInvariants(sim);
            Assert.AreEqual(0, log.Count(SimEventType.RingSpawned));
            Assert.AreEqual(90.0, sim.Time);
            Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason);
            Assert.AreEqual(90.0, sim.Result.EndTime);
            Assert.AreEqual(new[] { 1, 1, 1, 1 }, sim.Result.Ranks, "exact tie shares first place");
            Assert.AreEqual(4, sim.Result.Winners.Count);
            Assert.AreEqual(0, log.Count(SimEventType.Exit), "circlers never left home");
        }

        // ------------------------------------------------------------------------------------------------------------
        // R16 lasso

        [Test]
        public void R16_InvalidTinyLoopThenValidBigLoopInOneTick()
        {
            var b = new SimBuilder(60);
            b.AddDisc(V(-16, -16), 3.5, V(-16, -16), East, new ConstantHeadingController(East));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            double y = H, x1 = 1.95, x2 = 2.0;
            // The head (1.42, y) moves East: at t = 0.53 / 6 (u = 0.3 of tick 5) it crosses the tiny loop's segment
            // x = x1 (area 0.106 u^2, invalid), 0.05 u later (u = 0.8, same tick) the big loop's segment x = x2 (valid).
            sim.DebugSetTrail(0, new[]
            {
                V(x2, 3 + H), V(x2, -3 + H), V(-3, -3 + H), V(-3, y + 0.2), V(x1, y + 0.2), V(x1, y - 0.2),
                V(1.42, y - 0.2), V(1.42, y),
            });
            sim.DebugSetCharged(0, true);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.5);
            SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
            Assert.AreEqual(0, log.Count(SimEventType.LassoCrossNoCharge), "the invalid tiny loop emits nothing");
            AssertNear(V(x2, y), pocket.Point, 1e-9, "the pocket comes from the big loop");
            Assert.That(pocket.Time, Is.EqualTo((x2 - 1.42) / 6.0).Within(1e-9));
            Assert.That(pocket.Cells.Length, Is.GreaterThan(800), "big loop: about 5 x 3 u");
            Assert.IsFalse(sim.Players[0].Charged, "charge spent once");
            Assert.AreEqual(1, sim.Players[0].PocketsMade);
            Assert.AreEqual(pocket.Cells.Length, sim.Players[0].Pocket.Count);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R17 pending pocket (SimTestKit.PocketScenario, the S5 path)

        [Test]
        public void R17b_PendingPocketKeepsOwnersGivesNoSafetyAndItsContourIsExposed()
        {
            Simulation sim = PocketScenario(60, true, out int b, out int c, true);
            var log = new EventLog(sim);
            int aStart = sim.Grid.CountOf(1);
            int bStart = sim.Grid.CountOf(2);
            RunUntilTime(sim, 3.55);
            SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
            Assert.That(pocket.Time, Is.EqualTo(3.5).Within(1e-9));
            AssertNear(V(4 + H, H), pocket.Point, 1e-9, "X");
            PlayerState a = sim.Players[0];
            Assert.That(a.Pocket.Count, Is.GreaterThan(900));
            Assert.AreEqual(aStart, sim.Grid.CountOf(1), "a pending pocket does not count");
            Assert.AreEqual(bStart, sim.Grid.CountOf(2), "owners keep their cells");
            Assert.AreEqual(2, OwnerAt(sim, 7 + H, -2 + H), "B cell inside the pocket is still B's");
            Assert.IsTrue(a.Pocket.Get(CellIndex(sim.Grid, 7 + H, -2 + H)), "that cell is in the pocket");

            // The cut on the loop's bottom leg at t = 4.0 (arc 8.0625 + 4 + 3 = 15.0625) spawns the spark.
            RunUntilTime(sim, 4.05);
            SimEvent cut = log.Single(SimEventType.Cut, 0);
            Assert.AreEqual(c, cut.Other);
            Assert.That(cut.Time, Is.EqualTo(4.0).Within(1e-9));
            Assert.That(cut.S, Is.EqualTo(15.0625).Within(1e-9), "a point of the pocket contour");
            Assert.IsNotNull(a.Spark);

            // Crossing the pocket (x = 6.0625 going South from y = 0.0625 at t = 4.1667) sets no Home, ends no exit.
            int ticksInPocket = 0;
            RunUntilTime(sim, 4.6, true, s =>
            {
                if (s.Time > 25.0 / 6.0 + 0.02)
                {
                    Assert.IsTrue(s.Players[0].Pocket.Get(s.Players[0].Cell), "head inside the pocket at t=" + s.Time);
                    Assert.IsFalse(s.Players[0].Home, "a pocket gives no safety");
                    ticksInPocket++;
                }
            });
            Assert.That(ticksInPocket, Is.GreaterThan(20));
            Assert.AreEqual(0, log.Count(SimEventType.Return, 0));
            Assert.AreEqual(aStart, sim.Grid.CountOf(1));
            // The spark (gap 8 u) catches A at 4 + 8 / 4.8 before its return: the pocket disappears, B keeps its cells.
            RunUntilTime(sim, 5.8);
            SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
            Assert.That(caught.Time, Is.EqualTo(4.0 + 8.0 / 4.8 + Eps).Within(1e-9));
            Assert.AreEqual(0, a.Pocket.Count, "elimination erases the pocket");
            Assert.AreEqual(2, OwnerAt(sim, 7 + H, -2 + H), "rival cells inside the pocket keep their owner");
            Assert.AreEqual(0, sim.Grid.CountOf(1));
            Assert.AreEqual(b, 1);
        }

        [Test]
        public void R17b_LassoDuringAChaseLeavesTheSparkUnchanged()
        {
            Simulation sim = PocketScenario(60, true, out _, out _, false);
            var log = new EventLog(sim);
            RunUntilTime(sim, 3.0);
            sim.DebugForceCut(0, 0.5, 1);   // far behind: the catch would come long after the return
            Spark spark = sim.Players[0].Spark;
            double sCut = spark.SCut, tCut = spark.TimeCut;
            Assert.AreEqual(3.0, tCut);
            RunUntilTime(sim, 6.0, true, s =>
            {
                Spark sp = s.Players[0].Spark;
                if (sp == null) return;
                Assert.AreSame(spark, sp, "same spark object");
                Assert.AreEqual(sCut, sp.SCut, "SCut unchanged");
                Assert.AreEqual(tCut, sp.TimeCut, "TimeCut unchanged");
                Assert.That(sp.S, Is.EqualTo(sCut + s.Config.SparkSpeed * (s.Time - tCut)).Within(1e-9), "S(t) unchanged");
            });
            SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
            Assert.That(pocket.Time, Is.EqualTo(3.5).Within(1e-9), "the lasso happened during the chase");
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsTrue(ret.Chased);
            Assert.That(ret.Margin, Is.GreaterThan(0.0));
            Assert.That(ret.Time, Is.EqualTo(28.0 / 6.0 + (6 + H) / 6.0).Within(1e-9));
            // Contract 24 (R17 v1.4): a lasso during a chase is allowed but cannot pay off.
            Assert.AreEqual(0, ret.Cells.Length, "the chased return validates no pocket");
            Assert.AreEqual(0, sim.Players[0].Pocket.Count, "the pocket is erased");
            Assert.AreEqual(2, OwnerAt(sim, 7 + H, -2 + H), "the rival cell inside the pocket keeps its owner");
        }

        // ------------------------------------------------------------------------------------------------------------
        // R18 simultaneous returns

        [Test]
        public void R18_SimultaneousReturnsConflictingCellsKeepTheirPreviousOwner()
        {
            var b = new SimBuilder(60);
            b.AddRect(-10, -6, -2, 6, V(-6, H), West, new ConstantHeadingController(West));
            b.AddRect(2, -6, 10, 6, V(6, H), East, new ConstantHeadingController(East));
            int c = b.AddRect(-1, -2.5, 1, 2.5, V(H, -1.0), North, new ConstantHeadingController(North));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-2, 4 + H), V(1 + H, 4 + H), V(1 + H, -4 + H), V(-1.75, -4 + H) });
            sim.DebugSetTrail(1, new[] { V(2, -3 + H), V(-1 - H, -3 + H), V(-1 - H, 3 + H), V(1.75, 3 + H) });
            int cStart = sim.Grid.CountOf(3);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.1);
            SimEvent ra = log.Single(SimEventType.Return, 0);
            SimEvent rb = log.Single(SimEventType.Return, 1);
            Assert.That(ra.Time, Is.EqualTo(0.25 / 6.0).Within(1e-9));
            Assert.AreEqual(ra.Time, rb.Time, "simultaneous");
            Assert.AreEqual(0, log.Count(SimEventType.Cut));
            // Overlap x in [-1.0625, 1.0625], y in [-2.9375, 3.0625]: claimed by both.
            Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 0.6, 2.8), "neutral cell claimed twice stays neutral");
            Assert.AreEqual(3, OwnerAt(sim, H, H), "rival cell claimed twice keeps its owner");
            Assert.AreEqual(cStart, sim.Grid.CountOf(3), "C keeps all its cells");
            Assert.IsTrue(sim.Players[c].Home);
            Assert.AreEqual(1, OwnerAt(sim, -1.5, 3.5), "only in A's capture");
            Assert.AreEqual(2, OwnerAt(sim, 1.5, -2.5), "only in B's capture");
            var setA = new HashSet<int>(ra.Cells);
            foreach (int cell in rb.Cells) Assert.IsFalse(setA.Contains(cell), "no cell is given to both");
            Assert.IsFalse(setA.Contains(CellIndex(sim.Grid, 0.6, 2.8)));
        }

        [Test]
        public void R18b_ReturnOntoACellTakenBySimultaneousReturnRestartsAnExit()
        {
            var b = new SimBuilder(60);
            b.AddRect(-10, -6, -2, 6, V(-6, H), West, new ConstantHeadingController(West));
            int pb = b.AddRect(2, -1, 8, 1, V(5, -0.5), East, new ConstantHeadingController(East));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-2, 4 + H), V(3 + H, 4 + H), V(3 + H, -4 + H), V(-1.75, -4 + H) });
            sim.DebugSetTrail(pb, new[] { V(8, H), V(9 + H, H), V(9 + H, 5 + H), V(1 + H, 5 + H), V(1 + H, 0.5625), V(1.75, 0.5625) });
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.1);
            double tr = 0.25 / 6.0;
            SimEvent ra = log.Single(SimEventType.Return, 0);
            SimEvent rb = log.First(SimEventType.Return, pb);
            Assert.IsNotNull(rb);
            Assert.That(ra.Time, Is.EqualTo(tr).Within(1e-9));
            Assert.AreEqual(ra.Time, rb.Time);
            Assert.That(rb.Cells.Length, Is.GreaterThan(500), "B gets its own capture");
            Assert.IsTrue(Array.BinarySearch(rb.Cells, CellIndex(sim.Grid, 6 + H, 3 + H)) >= 0, "a cell outside A's region");
            SimEvent stolen = log.Single(SimEventType.TerritoryStolen, pb);
            Assert.AreEqual(0, stolen.Other);
            Assert.AreEqual(ra.Time, stolen.Time);
            SimEvent exit = log.Single(SimEventType.Exit, pb);
            Assert.That(log.IndexOf(rb) < log.IndexOf(stolen) && log.IndexOf(stolen) < log.IndexOf(exit));
            AssertNear(V(1.75 + 0.25, 0.5625), exit.Point, 1e-9, "B exits at its head");
            Assert.AreEqual(1, OwnerAt(sim, 2 + H, 0.5625), "A took B's return cell");
            Assert.IsFalse(sim.Players[pb].Home, "B must reach its current color");
            RunUntilTime(sim, 0.4);
            Assert.AreEqual(2, log.Count(SimEventType.Return, pb));
            SimEvent second = log.Of(SimEventType.Return, pb)[1];
            Assert.That(second.Time, Is.EqualTo(tr + (3.125 - 2.0) / 6.0).Within(1e-9), "back on B's color at x = 3.125");
            Assert.IsTrue(sim.Players[pb].Home);
        }

        // Contract 24 + R18 + R9: the R18b geometry with B chased (spark far behind). B's chased return claims no cell, so
        // the region both captures overlapped (x in (1.0625, 3.0625), y in (1, 4.0625)) goes to A instead of staying
        // neutral, and B's own planned area stays neutral. A still takes B's return cell: B is saved (no spark any more),
        // then immediately restarts an exit at its head and returns, unchased, on its current color.
        [Test]
        public void R18b_ChasedReturnerClaimsNoCellAndStillRestartsAnExitWhenItsCellIsTaken()
        {
            var b = new SimBuilder(60);
            b.AddRect(-10, -6, -2, 6, V(-6, H), West, new ConstantHeadingController(West));
            int pb = b.AddRect(2, -1, 8, 1, V(5, -0.5), East, new ConstantHeadingController(East));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-2, 4 + H), V(3 + H, 4 + H), V(3 + H, -4 + H), V(-1.75, -4 + H) });
            sim.DebugSetTrail(pb, new[] { V(8, H), V(9 + H, H), V(9 + H, 5 + H), V(1 + H, 5 + H), V(1 + H, 0.5625), V(1.75, 0.5625) });
            sim.DebugForceCut(pb, 0.5, -1);   // 18.75 u behind the head: the catch would come long after the return
            int bStart = sim.Grid.CountOf(2);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.1);
            double tr = 0.25 / 6.0;
            SimEvent ra = log.Single(SimEventType.Return, 0);
            SimEvent rb = log.First(SimEventType.Return, pb);
            Assert.IsNotNull(rb);
            Assert.AreEqual(ra.Time, rb.Time, "simultaneous");
            Assert.That(ra.Time, Is.EqualTo(tr).Within(1e-9));
            Assert.IsFalse(ra.Chased);
            Assert.IsTrue(rb.Chased, "B was saved from its spark");
            Assert.That(rb.Margin, Is.GreaterThan(1.0));
            Assert.AreEqual(0, rb.Cells.Length, "a chased return captures nothing");
            Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 6 + H, 3 + H), "B's planned area stays neutral");
            Assert.AreEqual(1, OwnerAt(sim, 2.0, 2.0), "the overlap goes to A: the chased return claimed no cell (R18)");
            Assert.IsTrue(Array.BinarySearch(ra.Cells, CellIndex(sim.Grid, 2.0, 2.0)) >= 0);
            SimEvent stolen = log.Single(SimEventType.TerritoryStolen, pb);
            Assert.AreEqual(0, stolen.Other);
            SimEvent exit = log.Single(SimEventType.Exit, pb);
            Assert.That(log.IndexOf(rb) < log.IndexOf(stolen) && log.IndexOf(stolen) < log.IndexOf(exit));
            AssertNear(V(1.75 + 0.25, 0.5625), exit.Point, 1e-9, "B exits at its head");
            PlayerState pB = sim.Players[pb];
            Assert.IsTrue(pB.Alive);
            Assert.IsFalse(pB.Home, "B must reach its current color");
            Assert.IsNull(pB.Spark, "the new exit starts without a spark");
            Assert.That(sim.Grid.CountOf(2), Is.LessThan(bStart), "B gained nothing and lost the cells under A's capture");
            RunUntilTime(sim, 0.4);
            Assert.AreEqual(0, log.Count(SimEventType.SparkCaught));
            Assert.AreEqual(2, log.Count(SimEventType.Return, pb));
            SimEvent second = log.Of(SimEventType.Return, pb)[1];
            Assert.IsFalse(second.Chased);
            Assert.That(second.Time, Is.EqualTo(tr + (3.125 - 2.0) / 6.0).Within(1e-9), "back on B's color at x = 3.125");
            Assert.IsTrue(pB.Home);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R19 round end and ranking

        [Test]
        public void R19_LastSurvivorWinsImmediately()
        {
            var b = new SimBuilder(60);
            b.AddRect(-12, -2, -8, 2, V(-10, H), East, new ConstantHeadingController(East));
            b.AddRect(8, -2, 12, 2, V(10, H), West, new ConstantHeadingController(West));
            int idle = b.AddIdle(IdleCorners[0]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-8, H), V(-5 + H, H) });
            sim.DebugSetTrail(1, new[] { V(8, H), V(5 - H, H) });
            sim.DebugForceCut(0, sim.Players[0].Trail.Length - 4.8 * 0.2, idle);   // caught at 0.2
            sim.DebugForceCut(1, sim.Players[1].Trail.Length - 4.8 * 0.4, idle);   // caught at 0.4
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.3);
            Assert.IsFalse(sim.Ended);
            Assert.AreEqual(3, sim.RankOf(0), "final rank of the first eliminated: 1 + 2 alive");
            RunUntilTime(sim, 1.0);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.LastSurvivor, sim.Result.Reason);
            Assert.That(sim.Result.EndTime, Is.EqualTo(0.4 + Eps).Within(1e-9));
            Assert.AreEqual(new[] { 3, 2, 1 }, sim.Result.Ranks);
            Assert.AreEqual(new List<int> { idle }, sim.Result.Winners);
            long tick = sim.Tick;
            sim.Step();
            Assert.AreEqual(tick, sim.Tick, "Step is a no-op once Ended");
            SimEvent end = log.Single(SimEventType.RoundEnded);
            Assert.That(end.Time, Is.EqualTo(sim.Result.EndTime).Within(1e-12));
            Assert.AreEqual(sim.Players[idle].OwnedCells(sim.Grid), sim.Result.FinalCells[idle]);
        }

        [Test]
        public void R19_AllEliminatedAtTheSameInstantShareFirst()
        {
            var b = new SimBuilder(60);
            b.AddRect(-12, -2, -8, 2, V(-10, H), East, new ConstantHeadingController(East));
            b.AddRect(8, -2, 12, 2, V(10, H), West, new ConstantHeadingController(West));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-8, H), V(-5 + H, H) });
            sim.DebugSetTrail(1, new[] { V(8, H), V(5 - H, H) });
            int c0 = sim.Grid.CountOf(1), c1 = sim.Grid.CountOf(2);
            sim.DebugForceCut(0, sim.Players[0].Trail.Length, 1);
            sim.DebugForceCut(1, sim.Players[1].Trail.Length, 0);
            var log = new EventLog(sim);
            StepN(sim, 1);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.AllEliminated, sim.Result.Reason);
            Assert.AreEqual(new[] { 1, 1 }, sim.Result.Ranks);
            Assert.AreEqual(new List<int> { 0, 1 }, sim.Result.Winners);
            Assert.AreEqual(sim.Players[0].EliminatedAt, sim.Players[1].EliminatedAt, "same instant");
            Assert.AreEqual(new[] { c0, c1 }, sim.Result.FinalCells);
            Assert.AreEqual(1, sim.Players[0].Kills);
            Assert.AreEqual(1, sim.Players[1].Kills);
            Assert.AreEqual(2, log.Count(SimEventType.SparkCaught));
        }

        [Test]
        public void R19_CompetitionRankingAndFinalRankOfTheEliminated()
        {
            var b = new SimBuilder(60);
            b.Config.RoundDuration = 1.0;
            b.AddRect(-12, -4, -4, 4, V(-8, 0), North, new HomeCirclerController(V(-8, 0)));
            b.AddRect(4, -4, 12, 4, V(8, 0), North, new HomeCirclerController(V(8, 0)));
            b.AddRect(-4, 8, 4, 12, V(0, 10), North, new HomeCirclerController(V(0, 10)));
            int d = b.AddRect(-4, -12, 4, -8, V(0, -10), North, new ConstantHeadingController(North));
            Simulation sim = b.Build();
            Assert.AreEqual(4096, sim.Grid.CountOf(1));
            Assert.AreEqual(4096, sim.Grid.CountOf(2));
            Assert.AreEqual(2048, sim.Grid.CountOf(3));
            sim.DebugSetTrail(d, new[] { V(H, -8), V(H, -4) });
            sim.DebugForceCut(d, sim.Players[d].Trail.Length - 4.8 * 0.5, 0);
            Assert.AreEqual(1, sim.RankOf(0), "provisional rank");
            Assert.AreEqual(3, sim.RankOf(2), "provisional rank");
            RunUntil(sim, s => !s.Players[d].Alive, 1.0);
            Assert.AreEqual(4, sim.RankOf(d), "final as soon as its Step returns");
            RunUntilTime(sim, 2.0);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason);
            Assert.AreEqual(new[] { 1, 1, 3, 4 }, sim.Result.Ranks, "competition ranking (1, 1, 3)");
            Assert.AreEqual(new List<int> { 0, 1 }, sim.Result.Winners);
            Assert.AreEqual(4, sim.RankOf(d));
            Assert.AreEqual(2048, sim.Result.FinalCells[d], "FinalCells of the eliminated: before its group");
            Assert.That(sim.Result.FinalAreaPercent[0], Is.EqualTo(100.0 * 4096 / sim.Grid.ArenaCellCount).Within(1e-12));
            Assert.That(sim.AreaPercent(0), Is.EqualTo(sim.Result.FinalAreaPercent[0]).Within(1e-12));
        }

        [Test]
        public void R19_PendingPocketNeverCounts()
        {
            var sb = new SimBuilder(60);
            sb.Config.RoundDuration = 4.0;
            sb.AddRect(-12, -4, 0, 4, V(-1 + H, H), East,
                       Legs((East, 9), (South, 4), (West, 4), (North, 5), (East, 2), (South, 4), (West, 7)));
            sb.AddRect(12, -14, 22, -4, V(17, -9), North, new HomeCirclerController(V(17, -9)));
            Simulation sim = sb.Build();
            sim.DebugSetCharged(0, true);
            var log = new EventLog(sim);
            RunUntilTime(sim, 10.0);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(1, log.Count(SimEventType.LassoPocket, 0));
            Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason);
            int pocket = sim.Players[0].Pocket.Count;
            Assert.AreEqual(6144, sim.Result.FinalCells[0], "the pending pocket is not counted");
            Assert.AreEqual(6400, sim.Result.FinalCells[1]);
            Assert.That(6144 + pocket, Is.GreaterThan(6400), "the pocket would have changed the ranking");
            Assert.AreEqual(new[] { 2, 1 }, sim.Result.Ranks);
        }

        [Test]
        public void R19_SinglePlayerRoundRunsToTimeUp()
        {
            var b = new SimBuilder(60);
            b.Config.RoundDuration = 0.5;
            b.AddIdle(V(-16, -16));
            Simulation sim = b.Build();
            RunUntilTime(sim, 1.0);
            Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason, "no last-survivor win with one player");
            Assert.AreEqual(new[] { 1 }, sim.Result.Ranks);
        }

        [Test]
        public void R19b_ReturnAtExactlyRoundDurationCountsForTheRanking()
        {
            // TickRate 48: a step is exactly 0.125 u, so the head lands on the edge x = 0 at exactly t = 0.5.
            var b = new SimBuilder(48);
            b.Config.RoundDuration = 0.5;
            b.AddRect(-8, -4, 0, 4, V(-4, H), West, new ConstantHeadingController(West));   // 64 x 64 = 4096 cells
            b.AddRect(8, -4, 16.5, 4, V(12, 0), North, new HomeCirclerController(V(12, 0))); // 68 x 64 = 4352 cells
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 2 + H), V(5 + H, 2 + H), V(5 + H, H), V(3.0, H) });
            Assert.AreEqual(4096, sim.Grid.CountOf(1));
            Assert.AreEqual(4352, sim.Grid.CountOf(2));
            var log = new EventLog(sim);
            RunUntilTime(sim, 1.0);
            Assert.IsTrue(sim.Ended);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.AreEqual(0.5, ret.Time, 1e-12);
            Assert.That(log.IndexOf(ret), Is.LessThan(log.IndexOf(log.Single(SimEventType.RoundEnded))));
            Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason);
            Assert.That(sim.Result.FinalCells[0], Is.GreaterThan(4352), "the capture at t = RoundDuration counts");
            Assert.AreEqual(new[] { 1, 2 }, sim.Result.Ranks);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R4 border

        [Test]
        public void R4_BorderHoldsAPerpendicularPushAndSlidesAnObliqueOne()
        {
            var b = new SimBuilder(60);
            b.AddRect(26, -6, 32, 12, V(30 + H, H), East,
                      new HeadingScheduleController((0.0, East), (0.5, Math.PI / 3.0)));
            Simulation sim = b.Build();
            RunUntilTime(sim, 0.3);
            Vec2d held = sim.Players[0].Pos;
            RunUntilTime(sim, 0.5, true, s =>
            {
                Assert.AreEqual(held, s.Players[0].Pos, "held against the border");
            });
            double inset = 32 - 0.45;
            Assert.That(held.X, Is.LessThanOrEqualTo(inset));
            Assert.That(held.X, Is.EqualTo(inset).Within(1e-9), "D3: held on the inset line, not one step short");
            Assert.AreEqual(H, held.Y, "a push along the normal does not slide");
            RunUntilTime(sim, 1.0);
            RunUntilTime(sim, 1.5, true, s =>
            {
                PlayerState p = s.Players[0];
                Assert.That(p.Pos.Y - p.PrevPos.Y, Is.EqualTo(0.1).Within(1e-9), "slides at full speed along the wall");
                Assert.That(p.Pos.X, Is.LessThanOrEqualTo(inset + 1e-12));
                Assert.That(p.Pos.X, Is.EqualTo(inset).Within(1e-9), "slides on the inset line");
            });
            Assert.IsTrue(sim.Players[0].Home);
        }

        // Contract 23.2 D3: before holding, Arena.Step advances to the inset line, so the held stop point and everything
        // drawn from it (trail, capture near the wall) no longer depend on the tick rate. Player 0 pushes East along the
        // wall normal, is held from t = 1.248, slides North for 1 s from t = 2, then goes West home: its Return cells hug
        // the wall column and must be identical at 30, 60 and 144 Hz (before D3 the head stopped at x = 31.4625 at 30 and
        // 60 Hz but 31.5208 at 144 Hz, on both sides of the cell edge x = 31.5). Player 1 pushes West tilted 5 degrees (inside
        // the 10 degree hold cone), player 2 pushes North-East into the corner arc.
        [Test]
        public void R4_HeldStopPointIsOnTheInsetLineAndIdenticalAtEveryRate()
        {
            double inset = 32 - 0.45;
            double tilt = 5.0 * Math.PI / 180.0;
            const double sampleTime = 11.0 / 6.0;   // a tick time at every rate; all three heads are held by then
            var held = new Dictionary<int, Vec2d[]>();
            CrossRate("D3 held stop point", rate =>
            {
                var b = new SimBuilder(rate);
                b.AddRect(20, -4, 26, 10, V(24 + H, H), East,
                          new HeadingScheduleController((0.0, East), (2.0, North), (3.0, West)));
                b.AddRect(-26, -10, -20, 4, V(-24 - H, -H), Math.PI - tilt, new ConstantHeadingController(Math.PI - tilt));
                b.AddRect(20, 20, 25, 25, V(22 + H, 22), Math.PI / 4.0, new ConstantHeadingController(Math.PI / 4.0));
                return b.Build();
            }, 4.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                Vec2d[] p = held[rate];
                for (int i = 0; i < 3; i++)
                    Assert.That(sim.Arena.SignedDistance(p[i]) + sim.Config.ArenaMargin, Is.InRange(-1e-9, 0.0), at + "player " + i + " held on the inset line");
                Assert.AreEqual(inset, p[0].X, 1e-9, at + "East wall");
                Assert.AreEqual(H, p[0].Y, at + "pushed along the normal");
                Assert.AreEqual(-inset, p[1].X, 1e-9, at + "West wall");
                Assert.AreEqual(-H + (inset - (24 + H)) * Math.Tan(tilt), p[1].Y, 1e-9, at + "advanced along the tilted push");
                Assert.AreEqual(H, (p[2].X - p[2].Y), 1e-9, at + "on the straight North-East path");
                Assert.AreEqual(10 - 0.45, Vec2d.Distance(p[2], V(22, 22)), 1e-9, at + "on the inset corner arc");
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(3.0 + (inset - 26.0) / 6.0).Within(1e-9), at + "back home from the inset line");
                Assert.That(ret.Cells.Length, Is.GreaterThan(5 * 6 * 64), at + "the region between the wall run and the territory");
                Assert.IsTrue(sim.Players[1].Pos == p[1] && sim.Players[2].Pos == p[2], at + "still held at the end");
            }, s =>
            {
                double t = s.Time;
                if (Math.Abs(t - sampleTime) < 1e-9)
                    held[s.Config.TickRate] = new[] { s.Players[0].Pos, s.Players[1].Pos, s.Players[2].Pos };
                if (t > 1.7 && t < 2.0 + 1e-9) Assert.AreEqual(s.Players[0].PrevPos, s.Players[0].Pos, "player 0 held");
                if (t > 1.7) Assert.AreEqual(s.Players[1].PrevPos, s.Players[1].Pos, "player 1 held");
                if (t > 1.7) Assert.AreEqual(s.Players[2].PrevPos, s.Players[2].Pos, "player 2 held");
            });
            Assert.AreEqual(3, held.Count);
            for (int i = 0; i < 3; i++)
            {
                Assert.That(Vec2d.Distance(held[30][i], held[60][i]), Is.LessThanOrEqualTo(1e-9), "player " + i + ": 30 vs 60 Hz");
                Assert.That(Vec2d.Distance(held[30][i], held[144][i]), Is.LessThanOrEqualTo(1e-9), "player " + i + ": 30 vs 144 Hz");
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Determinism (section 6)

        private static Simulation DeterminismRound(ulong seed)
        {
            var b = new SimBuilder(60, lassoSpawns: true);
            b.Config.Seed = seed;
            b.Config.LassoFirstSpawn = 1.0;
            b.Config.LassoRespawn = 1.0;
            b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East,
                      new WaypointController(new[] { V(6, 0), V(6, 6), V(-2, 6), V(-2, 2), V(-6, 2) }));
            for (int k = 0; k < 3; k++) b.AddIdle(IdleCorners[k]);
            return b.Build();
        }

        [Test]
        public void Determinism_SameSeedSameControllersSameStateHash()
        {
            Simulation s1 = DeterminismRound(77), s2 = DeterminismRound(77), s3 = DeterminismRound(78);
            var log1 = new EventLog(s1);
            var log3 = new EventLog(s3);
            for (int k = 0; k < 360; k++)
            {
                s1.Step();
                s2.Step();
                s3.Step();
                AssertInvariants(s1);
                Assert.AreEqual(s1.StateHash(), s2.StateHash(), "tick " + k);
            }
            SimEvent r1 = log1.First(SimEventType.RingSpawned), r3 = log3.First(SimEventType.RingSpawned);
            Assert.IsNotNull(r1);
            Assert.IsNotNull(r3);
            Assert.AreNotEqual(r1.Point, r3.Point, "another seed draws another ring");
            Assert.AreNotEqual(s1.StateHash(), s3.StateHash());
            AssertInvariants(s2);
            AssertInvariants(s3);
            Assert.That(s1.Players[0].Captures, Is.GreaterThan(0), "the waypoint path returned home");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Controllers (5.6) and SimView

        [Test]
        public void Controllers_ScheduleSwitchesOnTheFirstTickWithTimeAtLeastTheEntry()
        {
            var b = new SimBuilder(60);
            var ctl = new HeadingScheduleController((0.5, North), (0.0, East));
            b.AddRect(-12, -4, 0, 4, V(-6, H), West, ctl);
            Simulation sim = b.Build();
            Assert.AreEqual(East, ctl.DesiredHeading(sim.View, 0), "sorted by time");
            RunUntilTime(sim, 0.5);
            Assert.AreEqual(East, sim.Players[0].Heading);
            StepN(sim, 1);
            Assert.AreEqual(North, sim.Players[0].Heading, "switched on the tick with Time = 0.5");
        }

        [Test]
        public void Controllers_WaypointAndHomeCircler()
        {
            var b = new SimBuilder(60);
            var wp = new WaypointController(new[] { V(-6, 2), V(-6, -2) });
            b.AddRect(-12, -4, 0, 4, V(-9, 0), East, wp);
            b.AddIdle(V(16, 16));
            Simulation sim = b.Build();
            RunUntilTime(sim, 5.0);
            Assert.AreEqual(2, wp.NextIndex(0), "both waypoints reached");
            Assert.AreEqual(0, sim.Players[1].Captures);
            Assert.IsTrue(sim.Players[1].Home, "the circler stays home");
            double r = Vec2d.Distance(sim.Players[1].Pos, V(16, 16));
            Assert.That(r, Is.EqualTo(HomeCirclerController.OrbitRadius).Within(0.2));
        }

        [Test]
        public void SimView_SparkCatchEtaFollowsTheClosedForm()
        {
            var b = new SimBuilder(60);
            b.AddRect(-12, -4, 0, 4, V(-6, H), East, new ConstantHeadingController(East));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, H), V(5 + H, H) });
            Assert.IsTrue(double.IsPositiveInfinity(sim.View.SparkCatchEta(0)));
            sim.DebugForceCut(0, 1.0, 1);
            Assert.That(sim.View.SparkCatchEta(0), Is.EqualTo((5 + H - 1.0) / 4.8).Within(1e-12));
            StepN(sim, 6);
            Assert.That(sim.View.SparkCatchEta(0), Is.EqualTo((5 + H - 1.0) / 4.8 - 0.1).Within(1e-9));
            Assert.AreEqual(sim.Players[0], sim.View.Player(0));
            Assert.AreEqual(2, sim.View.PlayerCount);
        }

        [Test]
        public void DebugSetTrail_ThrowsWhenTheHeadIsOnOwnTerritory()
        {
            var b = new SimBuilder(60);
            b.AddRect(-12, -4, 0, 4, V(-6, H), East, null);
            Simulation sim = b.Build();
            Assert.Throws<InvalidOperationException>(() => sim.DebugSetTrail(0, new[] { V(2, H), V(-1, H) }));
        }
    }
}
