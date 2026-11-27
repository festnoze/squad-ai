// Owned by the v1.4 rule verifier (adversarial audit of contract section 24, R13 v1.4 and R17 v1.4).
// Claim under attack: "a chased return never captures anything, and an unchased return still captures exactly as before".
// Every test attacks one edge of that claim: cut and return in one tick (both orders), a cut at the exact closing instant
// (R14, mid-tick and on a tick boundary, and closer than EventEpsilonSeconds across a tick boundary), simultaneous returns
// where only one is chased (R18), a chased return in the TimeUp group (R19), a chased returner whose cells are all taken
// at the same instant (R9), a lasso pocket made before and during the chase (R17), the spark reaching the head exactly at
// the return instant (R13 tie), a second exit after a saved return, the D2 / Kills / CutsMade stats and RankOf, and a
// bot-round fuzz that recomputes every isolated unchased capture with CaptureSolver from the state at the tick start.
// Pure NUnit 3.5 + PainterIO.Core (no UnityEngine). The SimTestKit run helpers check the 10.1 invariants and
// EventCapHits == 0 after every tick.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class RuleV14AuditTests
    {
        private const double Eps = 1e-7;            // EventEpsilonSeconds
        private const double SparkSpeed = 10.8;     // 1.8 x 6
        private const double Closing = 4.8;         // SparkSpeed - PawnSpeed
        private const int VictimCells = 12 * 8 * 64;   // [-12, 0] x [-4, 4]

        // ------------------------------------------------------------------------------------------------------------
        // Helpers

        private static byte[] Snapshot(Simulation sim) => (byte[])sim.Grid.Cells.Clone();

        private static int CountDiff(byte[] a, byte[] b)
        {
            Assert.AreEqual(a.Length, b.Length);
            int changed = 0;
            for (int k = 0; k < a.Length; k++)
            {
                if (a[k] != b[k]) changed++;
            }
            return changed;
        }

        /// <summary>Cells of the grid owned by id, ascending.</summary>
        private static int[] CellsOf(byte[] cells, byte id)
        {
            var list = new List<int>();
            for (int k = 0; k < cells.Length; k++)
            {
                if (cells[k] == id) list.Add(k);
            }
            return list.ToArray();
        }

        /// <summary>Section 7 capture recomputed from scratch: LoopErase of the trail plus the crossing, then CaptureSolver.</summary>
        private static int[] SolverCapture(OwnerGrid g, byte id, IReadOnlyList<Vec2d> trail, Vec2d crossing, CellMask pocket)
        {
            var pts = new List<Vec2d>(trail);
            if (pts.Count == 0 || Vec2d.Distance(pts[pts.Count - 1], crossing) >= 1e-9) pts.Add(crossing);
            List<Vec2d> outline = LoopErase.Erase(pts);
            int[] cells = CaptureSolver.Compute(g, id, outline, pocket != null && pocket.Count > 0 ? pocket : null);
            return cells ?? new int[0];
        }

        /// <summary>A fresh OwnerGrid of the same arena holding a copy of the given cells.</summary>
        private static OwnerGrid GridFrom(Simulation sim, byte[] cells)
        {
            var g = new OwnerGrid(sim.Arena, sim.Config.CellSize);
            for (int k = 0; k < cells.Length; k++)
            {
                if (cells[k] != OwnerGrid.Void && cells[k] != OwnerGrid.Neutral) g.Set(k, cells[k]);
            }
            return g;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Race layout. The victim (player 0) owns [-12, 0] x [-4, 4]; its trail is (0, 3.0625) -> (4.0625, 3.0625) ->
        // (4.0625, -1.9375) -> head (6 tRet, -1.9375), heading West, so it returns at x = 0 at t = tRet. The attacker
        // (player 1) owns [7, 11] x [-2.5, 2.5], goes West on y = H and touches the victim's right leg (s = 7.0625) when its
        // head reaches x = 4.6925, at t = tCut. With tCut = NaN the attacker circles at home (control: nobody cuts).

        private static Simulation BuildRace(int rate, double tRet, double tCut)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-6, H), West, new ConstantHeadingController(West));
            if (double.IsNaN(tCut)) b.AddRect(7, -2.5, 11, 2.5, V(9, 0), West, new HomeCirclerController(V(9, 0)));
            else b.AddRect(7, -2.5, 11, 2.5, V(4 + H + 0.63 + 6.0 * tCut, H), West, new ConstantHeadingController(West));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 3 + H), V(4 + H, 3 + H), V(4 + H, -2 + H), V(6.0 * tRet, -2 + H) });
            Assert.AreEqual(VictimCells, sim.Grid.CountOf(1));
            return sim;
        }

        /// <summary>The control run: same victim, same rate and return time, nobody cuts. Returns its Return event.</summary>
        private static SimEvent ControlReturn(int rate, double tRet, out byte[] gridAfter)
        {
            Simulation sim = BuildRace(rate, tRet, double.NaN);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsFalse(ret.Chased, "control return is unchased");
            Assert.That(ret.Cells.Length, Is.GreaterThan(1000), "control return captures the planned area");
            gridAfter = Snapshot(sim);
            return ret;
        }

        private static void AssertSavedWithNothing(Simulation sim, EventLog log, byte[] start, string at)
        {
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsTrue(ret.Chased, at + "chased");
            Assert.That(ret.Margin, Is.GreaterThan(0.0), at + "saved with a positive margin");
            Assert.IsNotNull(ret.Cells, at + "Cells not null");
            Assert.AreEqual(0, ret.Cells.Length, at + "a chased return captures nothing");
            Assert.AreEqual(0, CountDiff(start, sim.Grid.Cells), at + "no owner changed anywhere");
            PlayerState v = sim.Players[0];
            Assert.IsTrue(v.Alive && v.Home, at + "saved and home");
            Assert.IsNull(v.Spark, at + "spark extinguished");
            Assert.AreEqual(0, v.Pocket.Count, at + "no pocket left");
            Assert.AreEqual(0, v.Captures, at + "D2: an empty Return is not a capture");
            Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "nobody caught");
            Assert.IsTrue(double.IsPositiveInfinity(sim.View.SparkCatchEta(0)), at + "no stale spark visible to controllers");
        }

        private static void AssertUnchasedLikeControl(Simulation sim, EventLog log, int rate, double tRet, string at)
        {
            SimEvent ret = log.Single(SimEventType.Return, 0);
            SimEvent control = ControlReturn(rate, tRet, out byte[] controlGrid);
            // Return.Time is the group time: up to eps earlier when a simultaneous cut anchors the group.
            Assert.That(ret.Time, Is.EqualTo(control.Time).Within(2 * Eps), at + "same return instant as the control");
            Assert.IsFalse(ret.Chased, at + "unchased\n" + log.Dump());
            Assert.AreEqual(0.0, ret.Margin, at + "margin 0 when unchased");
            Assert.IsTrue(SameCells(control.Cells, ret.Cells), at + "captures exactly what the uncut control captures ("
                          + ret.Cells.Length + " vs " + control.Cells.Length + ")\n" + log.Dump());
            Assert.AreEqual(VictimCells + control.Cells.Length, sim.Grid.CountOf(1), at + "owned cells rose by the capture");
            Assert.AreEqual(0, CountDiff(controlGrid, sim.Grid.Cells), at + "grid identical to the control grid");
            Assert.AreEqual(1, sim.Players[0].Captures, at + "D2: one capture");
            Assert.IsNull(sim.Players[0].Spark, at + "no spark");
        }

        // ------------------------------------------------------------------------------------------------------------
        // 1. A cut and a return inside the same tick, both orders, at 30, 60 and 144 Hz (tick k starts at t = 0.5 at
        // every rate; the two events sit at u = 0.3 and u = 0.7 of that tick).

        [TestCase(30)]
        [TestCase(60)]
        [TestCase(144)]
        public void V14_CutThenReturnInsideOneTickIsSavedAndCapturesNothing(int rate)
        {
            double dt = 1.0 / rate;
            double tCut = 0.5 + 0.3 * dt, tRet = 0.5 + 0.7 * dt;
            Simulation sim = BuildRace(rate, tRet, tCut);
            byte[] start = Snapshot(sim);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            string at = rate + " Hz: ";
            SimEvent cut = log.Single(SimEventType.Cut, 0);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.That(cut.Time, Is.EqualTo(tCut).Within(1e-9), at + "cut time");
            Assert.That(ret.Time, Is.EqualTo(tRet).Within(1e-9), at + "return time");
            Assert.AreEqual(log.Ticks[log.IndexOf(cut)], log.Ticks[log.IndexOf(ret)], at + "same tick");
            Assert.That(log.IndexOf(cut), Is.LessThan(log.IndexOf(ret)), at + "Cut then Return");
            Assert.That(cut.S, Is.EqualTo(7 + H).Within(1e-9), at + "cut on the right leg");
            double l = (4 + H) + 5 + (4 + H);
            double s = 7 + H + SparkSpeed * (tRet - tCut);
            Assert.That(ret.Margin, Is.EqualTo((l - s) / SparkSpeed).Within(1e-9), at + "margin (L - S) / SparkSpeed");
            AssertSavedWithNothing(sim, log, start, at);
            Assert.AreEqual(1, sim.Players[1].CutsMade, at + "the cut is credited");
            Assert.AreEqual(0, sim.Players[1].Kills, at + "no kill");
            Assert.AreEqual(1, sim.RankOf(0), at + "provisional rank: the victim keeps its 6144 cells");
            Assert.AreEqual(2, sim.RankOf(1), at + "provisional rank of the attacker (1280 cells)");
        }

        [TestCase(30)]
        [TestCase(60)]
        [TestCase(144)]
        public void V14_ReturnThenCutInsideOneTickCapturesExactlyLikeTheUncutControl(int rate)
        {
            double dt = 1.0 / rate;
            double tRet = 0.5 + 0.3 * dt, tCut = 0.5 + 0.7 * dt;
            Simulation sim = BuildRace(rate, tRet, tCut);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            string at = rate + " Hz: ";
            Assert.AreEqual(0, log.Count(SimEventType.Cut), at + "the victim was home before the contact");
            Assert.AreEqual(0, sim.Players[1].CutsMade, at + "no cut credited");
            AssertUnchasedLikeControl(sim, log, rate, tRet, at);

            // "Exactly as before": the same cells as the pure section 7 computation on the starting grid.
            Simulation fresh = BuildRace(rate, tRet, tCut);
            int[] solver = SolverCapture(fresh.Grid, 1, new[] { V(0, 3 + H), V(4 + H, 3 + H), V(4 + H, -2 + H) }, V(0, -2 + H), null);
            Assert.IsTrue(SameCells(solver, log.Single(SimEventType.Return, 0).Cells), at + "== CaptureSolver on the outline");
        }

        // ------------------------------------------------------------------------------------------------------------
        // 2. R14: a cut at the exact instant the trail closes has no effect, so the return is UNCHASED and must capture
        // exactly like the control. Mid-tick (t = 0.51 is no tick time at 30 / 60 / 144 Hz) and on a tick boundary
        // (t = 0.5 is a tick time at every rate listed; t = 0.51 is one at 100 Hz).

        [TestCase(30, 0.51)]
        [TestCase(60, 0.51)]
        [TestCase(144, 0.51)]
        [TestCase(30, 0.5)]
        [TestCase(48, 0.5)]
        [TestCase(60, 0.5)]
        [TestCase(144, 0.5)]
        [TestCase(240, 0.5)]
        [TestCase(100, 0.51)]
        public void V14_R14_CutExactlyAtTheReturnInstantIsIgnoredAndTheReturnCaptures(int rate, double t)
        {
            Simulation sim = BuildRace(rate, t, t);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            string at = rate + " Hz, t = " + t + ": ";
            AssertUnchasedLikeControl(sim, log, rate, t, at);
            Assert.AreEqual(0, sim.Players[1].CutsMade, at + "no cut credited: the cut had no effect");
            AssertCutAtClosureLeftNoCutOrOnlyThePreviousTickOne(log, rate, t, at);
        }

        /// <summary>
        /// Mid-tick the grouping drops the cut, so no Cut event exists. On a tick boundary, rounding can put the cut at the
        /// end of the previous tick (u = 1 - tiny) and the return at the start of the next: the engine then cancels the
        /// cut at the return (R14) but cannot withdraw the Cut event raised one tick earlier. Pin that residue down.
        /// </summary>
        private static void AssertCutAtClosureLeftNoCutOrOnlyThePreviousTickOne(EventLog log, int rate, double t, string at)
        {
            SimEvent ret = log.Single(SimEventType.Return, 0);
            double ticks = t * rate;
            bool boundary = Math.Abs(ticks - Math.Round(ticks)) < 1e-6;
            List<SimEvent> cuts = log.Of(SimEventType.Cut, 0);
            if (!boundary)
            {
                Assert.AreEqual(0, cuts.Count, at + "mid-tick: returns resolve first, no Cut at all\n" + log.Dump());
                return;
            }
            Assert.That(cuts.Count, Is.LessThanOrEqualTo(1), at + "at most one Cut");
            if (cuts.Count == 1)
            {
                Assert.AreEqual(log.Ticks[log.IndexOf(ret)] - 1, log.Ticks[log.IndexOf(cuts[0])], at + "Cut only in the previous tick");
                Assert.That(ret.Time - cuts[0].Time, Is.LessThan(Eps), at + "and less than eps before the return");
            }
        }

        // Contract 3.1 / section 6: events closer than EventEpsilonSeconds are simultaneous, and R14 makes the return
        // win. Inside one tick the grouping gives that; here the cut comes 0.8 eps before the return and the two sit on
        // both sides of a tick boundary (t = 0.5 at 30 / 60 / 144 Hz, t = 0.51 at 100 Hz) or inside one tick (t = 0.51
        // at 30 / 60 / 144 Hz). The outcome must not depend on where the tick boundary falls.
        [TestCase(30, 0.5)]
        [TestCase(60, 0.5)]
        [TestCase(144, 0.5)]
        [TestCase(30, 0.51)]
        [TestCase(60, 0.51)]
        [TestCase(144, 0.51)]
        [TestCase(100, 0.51)]
        public void V14_R14_CutLessThanEpsBeforeTheReturnIsATieEvenAcrossATickBoundary(int rate, double t)
        {
            double tCut = t - 0.4 * Eps, tRet = t + 0.4 * Eps;
            Simulation sim = BuildRace(rate, tRet, tCut);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.6);
            string at = rate + " Hz, t = " + t + ": ";
            AssertUnchasedLikeControl(sim, log, rate, tRet, at);
            Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "nobody caught");
            Assert.AreEqual(0, sim.Players[1].CutsMade, at + "no cut credited: the cut had no effect");
            AssertCutAtClosureLeftNoCutOrOnlyThePreviousTickOne(log, rate, t, at);
        }

        // ------------------------------------------------------------------------------------------------------------
        // 3. R18 with one chased returner. Geometry of RulesTests.R18: A (player 0) returns West to x = -2 and B (player 1)
        // returns East to x = 2 at t = 0.25 / 6; their planned areas overlap on x in [-1.0625, 1.0625]; C (player 2) owns
        // the middle column [-1, 1] x [-2.5, 2.5]. B is chased (spark far behind, attacker C): B claims no cell, so A gets
        // its FULL solo capture (identical to a run where B is not trailing at all), including the overlap and C's cells
        // inside A's loop. Without the cut (control) the overlap stays neutral, so the test discriminates.

        private static Simulation BuildR18(int rate, bool bTrailing, bool bChased)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-10, -6, -2, 6, V(-6, H), West, new ConstantHeadingController(West));
            b.AddRect(2, -6, 10, 6, V(6, H), East, new ConstantHeadingController(East));
            b.AddRect(-1, -2.5, 1, 2.5, V(H, -1.0), North, new ConstantHeadingController(North));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(-2, 4 + H), V(1 + H, 4 + H), V(1 + H, -4 + H), V(-1.75, -4 + H) });
            if (bTrailing) sim.DebugSetTrail(1, new[] { V(2, -3 + H), V(-1 - H, -3 + H), V(-1 - H, 3 + H), V(1.75, 3 + H) });
            if (bChased) sim.DebugForceCut(1, 0.5, 2);
            return sim;
        }

        [Test]
        public void V14_R18_ChasedAndUnchasedSimultaneousReturnsTheUnchasedKeepsItsFullCapture()
        {
            CrossRate("R18 one chased", rate => BuildR18(rate, true, true), 0.1, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent ra = log.Single(SimEventType.Return, 0);
                SimEvent rb = log.Single(SimEventType.Return, 1);
                Assert.AreEqual(ra.Time, rb.Time, at + "simultaneous");
                Assert.That(ra.Time, Is.EqualTo(0.25 / 6.0).Within(1e-9), at + "return time");
                Assert.IsFalse(ra.Chased, at + "A unchased");
                Assert.IsTrue(rb.Chased, at + "B chased");
                Assert.AreEqual(0, rb.Cells.Length, at + "B claims nothing");

                // A's solo capture: the same A with B home (not trailing).
                Simulation solo = BuildR18(rate, false, false);
                var soloLog = new EventLog(solo);
                RunUntilTime(solo, 0.1);
                SimEvent soloA = soloLog.Single(SimEventType.Return, 0);
                Assert.IsTrue(SameCells(soloA.Cells, ra.Cells), at + "A's capture is exactly its solo capture ("
                              + ra.Cells.Length + " vs " + soloA.Cells.Length + ")");
                Assert.AreEqual(1, OwnerAt(sim, 0.6, 2.8), at + "the overlap is A's: nothing lost to the R18 conflict");
                Assert.AreEqual(1, OwnerAt(sim, H, H), at + "C's cell inside A's loop is A's");
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 1.5, -2.5), at + "B's planned area stays neutral");

                PlayerState pb = sim.Players[1], pc = sim.Players[2];
                Assert.AreEqual(8 * 12 * 64, sim.Grid.CountOf(2), at + "B's territory unchanged");
                Assert.IsTrue(pb.Alive && pb.Home, at + "B saved");
                Assert.IsNull(pb.Spark);
                Assert.AreEqual(0, pb.Captures, at + "B: no capture");
                Assert.AreEqual(1, sim.Players[0].Captures, at + "A: one capture");
                Assert.AreEqual(1, pc.CutsMade, at + "C credited with the forced cut");
                Assert.AreEqual(0, pc.Kills, at + "no kill");
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "nobody caught");
            });

            // Control: nobody chased, the overlap is claimed twice and stays neutral, so A gets strictly less.
            foreach (int rate in CrossRates)
            {
                Simulation sim = BuildR18(rate, true, false);
                var log = new EventLog(sim);
                RunUntilTime(sim, 0.1);
                Simulation solo = BuildR18(rate, false, false);
                var soloLog = new EventLog(solo);
                RunUntilTime(solo, 0.1);
                int[] a = log.Single(SimEventType.Return, 0).Cells, soloA = soloLog.Single(SimEventType.Return, 0).Cells;
                Assert.IsTrue(IsSubset(a, soloA) && a.Length < soloA.Length, rate + " Hz: control loses the overlap");
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 0.6, 2.8), rate + " Hz: control overlap neutral");
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // 4. A chased return in the TimeUp group. RoundDuration 0.5 (a tick time at every rate). A (player 0, [-8, 0] x
        // [-4, 4], 4096 cells) returns West to x = 0 at exactly t = 0.5 chased (spark forced at t = 0, catch due at 0.8 s,
        // attacker C); B (player 1, [8, 16.5] x [-4, 4], 4352 cells) returns East to x = 8 at the same instant, unchased.
        // Under the old rule A's capture would rank it first (control); under v1.4 A keeps 4096 cells and B wins.

        private static Simulation BuildTimeUp(int rate, bool chased)
        {
            var b = new SimBuilder(rate);
            b.Config.RoundDuration = 0.5;
            b.AddRect(-8, -4, 0, 4, V(-4, H), West, new ConstantHeadingController(West));
            b.AddRect(8, -4, 16.5, 4, V(12, 0), East, new ConstantHeadingController(East));
            int c = b.AddIdle(IdleCorners[3]);
            Simulation sim = b.Build();
            Assert.AreEqual(4096, sim.Grid.CountOf(1));
            Assert.AreEqual(4352, sim.Grid.CountOf(2));
            sim.DebugSetTrail(0, new[] { V(0, 2 + H), V(5 + H, 2 + H), V(5 + H, H), V(3.0, H) });
            sim.DebugSetTrail(1, new[] { V(8, -3 + H), V(4 + H, -3 + H), V(4 + H, -2 + H), V(5.0, -2 + H) });
            if (chased) sim.DebugForceCut(0, sim.Players[0].Trail.Length - Closing * 0.8, c);
            return sim;
        }

        [Test]
        public void V14_R19_ChasedReturnInTheTimeUpGroupCapturesNothingAndIsRankedOnItsOldLand()
        {
            CrossRate("chased return at time up", rate => BuildTimeUp(rate, true), 1.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                Assert.IsTrue(sim.Ended, at + "ended");
                Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason, at + "time up");
                SimEvent ra = log.Single(SimEventType.Return, 0);
                SimEvent rb = log.Single(SimEventType.Return, 1);
                SimEvent end = log.Single(SimEventType.RoundEnded);
                Assert.That(ra.Time, Is.EqualTo(0.5).Within(1e-9), at + "A returns at the last instant");
                Assert.That(rb.Time, Is.EqualTo(0.5).Within(1e-9), at + "B returns at the last instant");
                Assert.That(log.IndexOf(ra), Is.LessThan(log.IndexOf(end)), at + "returns resolve before the ranking");
                Assert.IsTrue(ra.Chased, at + "A chased");
                Assert.That(ra.Margin, Is.EqualTo(Closing * 0.3 / SparkSpeed).Within(1e-9), at + "A's margin");
                Assert.AreEqual(0, ra.Cells.Length, at + "A captures nothing");
                Assert.IsFalse(rb.Chased, at + "B unchased");
                Assert.That(rb.Cells.Length, Is.GreaterThan(200), at + "B captures");
                Assert.AreEqual(4096, sim.Result.FinalCells[0], at + "A ranked on its unchanged land");
                Assert.AreEqual(4352 + rb.Cells.Length, sim.Result.FinalCells[1], at + "B ranked with its capture");
                Assert.AreEqual(new[] { 2, 1, 3 }, sim.Result.Ranks, at + "B first, A second");
                Assert.AreEqual(new List<int> { 1 }, sim.Result.Winners, at + "winner");
                Assert.AreEqual(2, sim.RankOf(0), at + "RankOf matches the result");
                Assert.AreEqual(0, sim.Players[0].Captures, at + "A: no capture");
                Assert.AreEqual(1, sim.Players[1].Captures, at + "B: one capture");
                Assert.AreEqual(1, sim.Players[2].CutsMade, at + "C credited");
                Assert.AreEqual(0, sim.Players[2].Kills, at + "no kill");
                Assert.IsTrue(sim.Players[0].Alive, at + "A alive");
            });
            // Control: the same returns without the spark; A's capture would have made A first.
            foreach (int rate in CrossRates)
            {
                Simulation sim = BuildTimeUp(rate, false);
                RunUntilTime(sim, 1.0);
                Assert.That(sim.Result.FinalCells[0], Is.GreaterThan(sim.Result.FinalCells[1]), rate + " Hz: control, A first");
                Assert.AreEqual(new[] { 1, 2, 3 }, sim.Result.Ranks, rate + " Hz: control ranks");
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // 5. A chased return whose every cell (including the return cell) is captured at the same instant by an unchased
        // return. A (player 0, [-8, 8] x... see AuditTests R9) loops around x in (0, 10.0625), y in (-5.9375, 6.0625) and
        // returns at t = 2.0925 / 6; B (player 1) owns [6, 9] x [-3, 3] (inside A's loop), trails inside A's loop and
        // returns South onto y = 3 at the same instant, chased (spark far behind, attacker C). B is saved (empty capture),
        // loses its return cell (TerritoryStolen + Exit), then its last cell (TerritoryLost, Other = A): no spark kill.

        private const double ReturnA = 2.0925 / 6.0;

        private static Simulation BuildAllTaken(int rate, bool bTrailing, bool bChased)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-8, -8, 0, 8, V(-4, H), West, new ConstantHeadingController(West));
            b.AddRect(6, -3, 9, 3, V(7.5, 0), South, new ConstantHeadingController(South));
            int c = b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 6 + H), V(10 + H, 6 + H), V(10 + H, -6 + H), V(2.0925, -6 + H) });
            if (bTrailing)
                sim.DebugSetTrail(1, new[] { V(6, H), V(4 + H, H), V(4 + H, 5.4375), V(7 + H, 5.4375), V(7 + H, 3 + 2.0925) });
            if (bChased) sim.DebugForceCut(1, 0.5, c);
            return sim;
        }

        [Test]
        public void V14_R9_ChasedReturnerWhoseCellsAreAllTakenAtTheSameInstantIsSavedThenLosesItsLand()
        {
            CrossRate("chased returner loses every cell", rate => BuildAllTaken(rate, true, true), 0.5, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent ra = log.Single(SimEventType.Return, 0);
                SimEvent rb = log.Single(SimEventType.Return, 1);
                Assert.That(ra.Time, Is.EqualTo(ReturnA).Within(1e-9), at + "A's return");
                Assert.AreEqual(ra.Time, rb.Time, at + "simultaneous");
                Assert.IsFalse(ra.Chased, at + "A unchased");
                Assert.IsTrue(rb.Chased, at + "B chased");
                Assert.AreEqual(0, rb.Cells.Length, at + "B captures nothing");
                byte[] startCells = BuildAllTaken(rate, true, true).Grid.Cells;
                int[] bStart = CellsOf(startCells, 2);
                Assert.AreEqual(24 * 48, bStart.Length, at + "B's start land");
                Assert.IsTrue(IsSubset(bStart, ra.Cells), at + "A took every cell of B");
                SimEvent stolen = log.Single(SimEventType.TerritoryStolen, 1);
                SimEvent exit = log.Single(SimEventType.Exit, 1);
                SimEvent elim = log.Single(SimEventType.Eliminated, 1);
                Assert.AreEqual(0, stolen.Other, at + "stolen by A");
                Assert.That(log.IndexOf(rb) < log.IndexOf(stolen) && log.IndexOf(stolen) < log.IndexOf(exit)
                            && log.IndexOf(exit) < log.IndexOf(elim), at + "Return, TerritoryStolen, Exit, Eliminated");
                Assert.AreEqual(EliminationCause.TerritoryLost, elim.Cause, at + "cause");
                Assert.AreEqual(0, elim.Other, at + "Other = the returner that took the last cells");
                Assert.AreEqual(0, elim.Cells.Length, at + "nothing left to free");
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "the spark never caught");
                PlayerState pb = sim.Players[1];
                Assert.IsFalse(pb.Alive, at + "B eliminated");
                Assert.IsNull(pb.Spark, at + "no spark left");
                Assert.AreEqual(24 * 48, pb.FinalCells, at + "FinalCells = the land before the group");
                Assert.AreEqual(0, pb.Captures, at + "B: no capture");
                Assert.AreEqual(3, sim.RankOf(1), at + "1 + two players alive after its group");
                Assert.AreEqual(1, sim.Players[2].CutsMade, at + "C credited with the forced cut");
                Assert.AreEqual(0, sim.Players[2].Kills, at + "a TerritoryLost elimination is no spark kill");
                Assert.AreEqual(0, sim.Players[0].Kills, at + "A gets no kill either");
                Assert.AreEqual(1, sim.Players[0].Captures, at + "A: one capture");

                // A's capture is exactly what it is when B is home and does not return (B claims nothing).
                Simulation solo = BuildAllTaken(rate, false, false);
                var soloLog = new EventLog(solo);
                RunUntilTime(solo, 0.5);
                Assert.IsTrue(SameCells(soloLog.Single(SimEventType.Return, 0).Cells, ra.Cells), at + "A's full solo capture");
                // Control: B unchased claims its planned area, which A also claims: those cells stay neutral.
                Simulation both = BuildAllTaken(rate, true, false);
                var bothLog = new EventLog(both);
                RunUntilTime(both, 0.5);
                int[] aBoth = bothLog.Single(SimEventType.Return, 0).Cells;
                Assert.IsTrue(IsSubset(aBoth, ra.Cells) && aBoth.Length < ra.Cells.Length, at + "control: A loses the overlap");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // 6. R17 v1.4: a lasso pocket made BEFORE the cut (cut at t = 4.0) or DURING the chase (cut at t = 3.0, pocket at
        // t = 3.5) is lost at the saved return. SimTestKit.PocketScenario (charged), the cut is forced on A's first leg
        // (s = 1.0625) at the given tick with attacker B. The pocket holds B's cell (7.0625, -1.9375).

        [TestCase(3.0)]
        [TestCase(4.0)]
        public void V14_R17_PocketMadeBeforeOrDuringTheChaseIsLostAtTheSavedReturn(double cutTime)
        {
            CrossRate("pocket and chase, cut at " + cutTime, rate =>
            {
                Simulation sim = PocketScenario(rate, true, out int b, out _, false);
                long cutTick = (long)Math.Round(cutTime * rate);
                sim.BeforeTick += s =>
                {
                    if (s.Tick == cutTick) s.DebugForceCut(0, 1 + H, b);
                };
                bool sparkAtPocket = false;
                double sCutAtPocket = double.NaN;
                sim.EventRaised += e =>
                {
                    if (e.Type != SimEventType.LassoPocket) return;
                    Spark sp = sim.Players[0].Spark;
                    sparkAtPocket = sp != null;
                    if (sp != null) sCutAtPocket = sp.SCut;
                };
                byte[] start = Snapshot(sim);
                sim.EventRaised += e =>
                {
                    if (e.Type != SimEventType.Return || e.Player != 0) return;
                    Assert.AreEqual(cutTime < 3.5, sparkAtPocket, "spark present when the pocket formed iff cut before 3.5");
                    if (sparkAtPocket) Assert.AreEqual(1 + H, sCutAtPocket, 1e-12, "the lasso did not move the spark");
                    Assert.AreEqual(0, CountDiff(start, sim.Grid.Cells), "nothing changed at the return instant");
                };
                return sim;
            }, 6.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
                Assert.That(pocket.Time, Is.EqualTo(3.5).Within(1e-9), at + "pocket at 3.5");
                Assert.IsTrue(Array.BinarySearch(pocket.Cells, CellIndex(sim.Grid, 7 + H, -2 + H)) >= 0, at + "B's cell in the pocket");
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(PocketReturnTime).Within(1e-9), at + "return time");
                Assert.IsTrue(ret.Chased, at + "chased");
                double l = 6.0 * (PocketReturnTime - 0.15625);
                double s = 1 + H + SparkSpeed * (PocketReturnTime - cutTime);
                Assert.That(ret.Margin, Is.EqualTo((l - s) / SparkSpeed).Within(1e-9), at + "margin");
                Assert.That(ret.Margin, Is.GreaterThan(0.0), at + "saved");
                Assert.AreEqual(0, ret.Cells.Length, at + "no ordinary capture and no pocket");
                PlayerState a = sim.Players[0];
                Assert.IsTrue(a.Alive && a.Home, at + "A saved");
                Assert.IsNull(a.Spark, at + "no spark");
                Assert.AreEqual(0, a.Pocket.Count, at + "pocket erased");
                Assert.IsFalse(a.Charged, at + "the charge was spent on the lost pocket");
                Assert.AreEqual(1, a.PocketsMade, at + "PocketsMade counts the made pocket");
                Assert.AreEqual(0, a.Captures, at + "no capture");
                Assert.AreEqual(VictimCells, sim.Grid.CountOf(1), at + "A's land unchanged");
                Assert.AreEqual(2, OwnerAt(sim, 7 + H, -2 + H), at + "B's cell in the pocket keeps its owner");
                Assert.AreEqual(1, sim.Players[1].CutsMade, at + "B credited with the forced cut");
                Assert.AreEqual(0, sim.Players[1].Kills, at + "no kill");
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "nobody caught");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // 7. R13 tie: the spark reaches the head exactly at the return instant (S4 tie geometry, t_c = t_r = 0.5), and
        // catch roots 0.5 eps (saved) and 1.5 eps (eliminated) before the return.

        private static Simulation BuildTie(int rate, double g)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-6, H), West, new ConstantHeadingController(West));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 2 + H), V(8 + H, 2 + H), V(8 + H, H), V(3.0, H) });
            sim.DebugForceCut(0, sim.Players[0].Trail.Length - g, 1);
            return sim;
        }

        [TestCase(0.0)]
        [TestCase(0.5)]
        public void V14_R13_SparkReachingTheHeadAtTheReturnInstantSavesWithNothing(double rootEpsBefore)
        {
            double tc = 0.5 - rootEpsBefore * Eps;
            CrossRate("tie " + rootEpsBefore, rate => BuildTie(rate, Closing * tc), 1.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(0.5).Within(1e-6), at + "return at the tie");
                Assert.That(ret.Margin, Is.LessThan(1e-6), at + "the spark was at the head");
                byte[] start = BuildTie(rate, Closing * tc).Grid.Cells;
                AssertSavedWithNothingAllowZeroMargin(sim, log, start, at);
                Assert.AreEqual(1, sim.Players[1].CutsMade, at + "attacker credited");
                Assert.AreEqual(0, sim.Players[1].Kills, at + "no kill");
                Assert.IsFalse(sim.Ended, at + "both alive");
            });
        }

        private static void AssertSavedWithNothingAllowZeroMargin(Simulation sim, EventLog log, byte[] start, string at)
        {
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsTrue(ret.Chased, at + "chased");
            Assert.That(ret.Margin, Is.GreaterThanOrEqualTo(0.0), at + "margin");
            Assert.AreEqual(0, ret.Cells.Length, at + "a chased return captures nothing");
            Assert.AreEqual(0, CountDiff(start, sim.Grid.Cells), at + "no owner changed anywhere");
            PlayerState v = sim.Players[0];
            Assert.IsTrue(v.Alive && v.Home, at + "saved");
            Assert.IsNull(v.Spark, at + "spark extinguished");
            Assert.AreEqual(0, v.Captures, at + "no capture");
            Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "not caught");
        }

        [Test]
        public void V14_R13_CatchOnePointFiveEpsBeforeTheReturnEliminatesAndCreditsTheKill()
        {
            double tc = 0.5 - 1.5 * Eps;
            CrossRate("caught 1.5 eps before", rate => BuildTie(rate, Closing * tc), 1.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                Assert.AreEqual(0, log.Count(SimEventType.Return), at + "no return after the elimination");
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(tc + Eps).Within(1e-9), at + "caught at t_c + eps");
                SimEvent elim = log.Single(SimEventType.Eliminated, 0);
                Assert.AreEqual(EliminationCause.Spark, elim.Cause, at + "cause");
                Assert.AreEqual(VictimCells, elim.Cells.Length, at + "all its land freed");
                Assert.AreEqual(0, sim.Grid.CountOf(1), at + "nothing left");
                PlayerState v = sim.Players[0];
                Assert.AreEqual(VictimCells, v.FinalCells, at + "FinalCells before the group");
                Assert.AreEqual(1, sim.Players[1].Kills, at + "kill credited");
                Assert.AreEqual(1, sim.Players[1].CutsMade, at + "cut credited");
                Assert.IsTrue(sim.Ended, at + "last survivor");
                Assert.AreEqual(new[] { 2, 1 }, sim.Result.Ranks, at + "ranks");
                Assert.AreEqual(2, sim.RankOf(0), at + "RankOf of the eliminated");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // 8. A second exit after a saved return captures normally (no stale spark, pocket or chase state). A (player 0)
        // returns West to x = 0 at t = 3.0625 / 6, chased (catch due at t = 1.0); it runs on into its land, turns East at
        // t = 1 (x = -2.9375), exits at x = 0, turns North at t = 2 (x = 3.0625), West at t = 7/3 (y = 2.0625) and returns
        // at x = 0: an unchased capture equal to the pure section 7 result on the starting grid.

        private static Simulation BuildSecondExit(int rate, bool chased)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-6, H), West,
                      new HeadingScheduleController((0.0, West), (1.0, East), (2.0, North), (14.0 / 6.0, West)));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 2 + H), V(5 + H, 2 + H), V(5 + H, H), V(3 + H, H) });
            if (chased) sim.DebugForceCut(0, sim.Players[0].Trail.Length - Closing * 1.0, 1);
            return sim;
        }

        [Test]
        public void V14_SecondExitAfterASavedReturnCapturesNormallyWithNoStaleChaseState()
        {
            double tr1 = (3 + H) / 6.0, tr2 = 14.0 / 6.0 + (3 + H) / 6.0;
            CrossRate("second exit", rate => BuildSecondExit(rate, true), 3.2, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                List<SimEvent> rets = log.Of(SimEventType.Return, 0);
                Assert.AreEqual(2, rets.Count, at + "two returns\n" + log.Dump());
                Assert.That(rets[0].Time, Is.EqualTo(tr1).Within(1e-9), at + "first return");
                Assert.IsTrue(rets[0].Chased, at + "first return chased");
                Assert.AreEqual(0, rets[0].Cells.Length, at + "first return captures nothing");
                SimEvent exit = log.Single(SimEventType.Exit, 0);
                Assert.That(exit.Time, Is.EqualTo(1.0 + (3 - H) / 6.0).Within(1e-9), at + "second exit at x = 0");
                Assert.That(rets[1].Time, Is.EqualTo(tr2).Within(1e-9), at + "second return");
                Assert.IsFalse(rets[1].Chased, at + "second return unchased");
                Assert.AreEqual(0.0, rets[1].Margin, at + "no margin");
                Simulation fresh = BuildSecondExit(rate, true);
                int[] solver = SolverCapture(fresh.Grid, 1, new[] { V(0, H), V(3 + H, H), V(3 + H, 2 + H) }, V(0, 2 + H), null);
                Assert.That(solver.Length, Is.GreaterThan(300), at + "a real planned area");
                Assert.IsTrue(SameCells(solver, rets[1].Cells), at + "captures exactly the section 7 result ("
                              + rets[1].Cells.Length + " vs " + solver.Length + ")");
                Assert.AreEqual(VictimCells + solver.Length, sim.Grid.CountOf(1), at + "land rose by the capture");
                Assert.AreEqual(1, sim.Players[0].Captures, at + "D2: only the second return counts");
                Assert.AreEqual(1, sim.Players[1].CutsMade, at + "one cut");
                Assert.AreEqual(0, sim.Players[1].Kills, at + "no kill");
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "nobody caught");
            }, s =>
            {
                if (s.Time > tr1 + 1e-6)
                {
                    Assert.IsNull(s.Players[0].Spark, "no spark after the saved return");
                    Assert.IsTrue(double.IsPositiveInfinity(s.View.SparkCatchEta(0)), "no catch ETA");
                    Assert.AreEqual(0, s.Players[0].Pocket.Count, "no pocket");
                }
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // 9. Fuzz over bot rounds (60 Hz, lasso on): for every Return isolated in its tick (no other Return, Eliminated,
        // Exit or lasso event of that player earlier in the tick, the player trailing at the tick start), an unchased
        // Return.Cells equals CaptureSolver on the tick-start grid, trail, pocket and the crossing point, and a chased one
        // is empty and leaves the grid exactly as it was. Chased must equal "had a spark at that instant". At the end,
        // Captures, Kills and CutsMade match the events.

        private sealed class TickSnapshot
        {
            public byte[] Cells;
            public List<Vec2d>[] Trails;
            public CellMask[] Pockets;
            public bool[] HadSpark;
            public double[] SparkTimeCut;
            public int[] SparkAttacker;
            public readonly List<SimEvent> Events = new List<SimEvent>();
        }

        [Test]
        public void V14_Fuzz_BotRoundsChasedReturnsAreEmptyAndUnchasedReturnsMatchTheSolver()
        {
#if UNITY_5_3_OR_NEWER
            const int seeds = 2;
#else
            const int seeds = 6;
#endif
            int chasedSeen = 0, exactChecked = 0;
            for (ulong seed = 1; seed <= (ulong)seeds; seed++)
            {
                BotStyle[] styles = { BotStyle.Balanced, BotStyle.Balanced, BotStyle.Greedy, BotStyle.Aggressive };
                var controllers = new IController[4];
                for (int i = 0; i < 4; i++)
                    controllers[i] = new BotController(BotPersonality.Preset(styles[i]), seed * 7919UL + (ulong)i * 104729UL + 17UL);
                var sim = new Simulation(new SimConfig { Seed = seed, TickRate = 60, LassoEnabled = true }, controllers,
                                         new SimSetup { HumanIndex = -1 });
                int n = sim.Players.Count;
                var snap = new TickSnapshot
                {
                    Trails = new List<Vec2d>[n], Pockets = new CellMask[n], HadSpark = new bool[n], SparkTimeCut = new double[n], SparkAttacker = new int[n],
                };
                for (int i = 0; i < n; i++)
                {
                    snap.Trails[i] = new List<Vec2d>();
                    snap.Pockets[i] = new CellMask(sim.Grid.Size);
                }
                var returnsWithCells = new int[n];
                var kills = new int[n];
                var cuts = new int[n];
                sim.BeforeTick += s =>
                {
                    snap.Cells = Snapshot(s);
                    snap.Events.Clear();
                    for (int i = 0; i < n; i++)
                    {
                        PlayerState p = s.Players[i];
                        snap.Trails[i].Clear();
                        for (int k = 0; k < p.Trail.Count; k++) snap.Trails[i].Add(p.Trail.Points[k]);
                        snap.Pockets[i].Clear();
                        snap.Pockets[i].UnionWith(p.Pocket);
                        snap.HadSpark[i] = p.Spark != null;
                        snap.SparkTimeCut[i] = p.Spark != null ? p.Spark.TimeCut : double.NaN;
                        snap.SparkAttacker[i] = p.Spark != null ? p.Spark.Attacker : -1;
                    }
                };
                sim.EventRaised += e =>
                {
                    snap.Events.Add(e);
                    if (e.Type == SimEventType.Return && e.Cells.Length > 0) returnsWithCells[e.Player]++;
                    if (e.Type == SimEventType.SparkCaught && e.Other >= 0) kills[e.Other]++;
                    if (e.Type == SimEventType.Cut) cuts[e.Other]++;
                };
                while (!sim.Ended)
                {
                    sim.Step();
                    AssertInvariants(sim);
                    int returnsThisTick = 0;
                    foreach (SimEvent e in snap.Events)
                    {
                        if (e.Type == SimEventType.Return) returnsThisTick++;
                    }
                    for (int k = 0; k < snap.Events.Count; k++)
                    {
                        SimEvent e = snap.Events[k];
                        if (e.Type != SimEventType.Return) continue;
                        string at = "seed " + seed + " t=" + e.Time + " player " + e.Player + ": ";
                        int pi = e.Player;
                        bool cutEarlier = false;
                        bool isolated = returnsThisTick == 1 && snap.Trails[pi].Count > 0;
                        for (int j = 0; j < k; j++)
                        {
                            SimEvent x = snap.Events[j];
                            if (x.Type == SimEventType.Cut && x.Player == pi) cutEarlier = true;
                            if (x.Type == SimEventType.Eliminated || x.Type == SimEventType.TerritoryStolen) isolated = false;
                            if (x.Player == pi && (x.Type == SimEventType.Exit || x.Type == SimEventType.LassoPocket
                                                   || x.Type == SimEventType.LassoCrossNoCharge)) isolated = false;
                        }
                        bool hadSpark = snap.HadSpark[pi] || cutEarlier;
                        if (e.Chased)
                        {
                            chasedSeen++;
                            Assert.AreEqual(0, e.Cells.Length, at + "a chased return captures nothing");
                            Assert.IsTrue(hadSpark, at + "Chased without a spark");
                        }
                        else
                        {
                            // Unchased with a spark is only allowed as an R14 tie (spark spawned less than eps before).
                            if (snap.HadSpark[pi])
                            {
                                Assert.That(e.Time - snap.SparkTimeCut[pi], Is.LessThan(Eps), at + "unchased although it had a spark");
                                if (snap.SparkAttacker[pi] >= 0) cuts[snap.SparkAttacker[pi]]--;   // R14: credit taken back
                            }
                            Assert.IsFalse(cutEarlier, at + "unchased although cut earlier in this tick");
                        }
                        if (!isolated) continue;
                        OwnerGrid before = GridFrom(sim, snap.Cells);
                        if (e.Chased)
                        {
                            bool otherChange = false;
                            foreach (SimEvent x in snap.Events)
                            {
                                if (x.Type == SimEventType.Eliminated) otherChange = true;
                            }
                            if (!otherChange) Assert.AreEqual(0, CountDiff(snap.Cells, sim.Grid.Cells), at + "grid unchanged");
                        }
                        else
                        {
                            int[] expected = SolverCapture(before, sim.Players[pi].Id, snap.Trails[pi], e.Point, snap.Pockets[pi]);
                            Assert.IsTrue(SameCells(expected, e.Cells), at + "unchased capture == CaptureSolver ("
                                          + e.Cells.Length + " vs " + expected.Length + ")");
                            exactChecked++;
                        }
                    }
                }
                for (int i = 0; i < n; i++)
                {
                    PlayerState p = sim.Players[i];
                    Assert.AreEqual(returnsWithCells[i], p.Captures, "seed " + seed + " player " + i + ": D2 Captures");
                    Assert.AreEqual(kills[i], p.Kills, "seed " + seed + " player " + i + ": Kills == SparkCaught by it");
                    Assert.AreEqual(cuts[i], p.CutsMade, "seed " + seed + " player " + i + ": CutsMade == Cut events");
                    Assert.AreEqual(sim.Result.Ranks[i], sim.RankOf(i), "seed " + seed + " player " + i + ": RankOf");
                }
                Assert.AreEqual(0, sim.EventCapHits, "EventCapHits");
            }
            TestContext.WriteLine("V14 fuzz: " + seeds + " rounds, " + chasedSeen + " chased returns, " + exactChecked
                                  + " unchased captures recomputed exactly");
            Assert.That(exactChecked, Is.GreaterThan(20 * seeds), "the fuzz must actually check captures");
        }
    }
}
