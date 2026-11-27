// Owned by A6 (audit). Adversarial edge-case tests against the brief (docs/REGLES_DU_JEU.txt sections 2-7) and the
// contract readings (CONTRACT.md sections 4, 6, 7, 8, 10.0). Each test name starts with the rule id it attacks.
// Pure NUnit 3.5 + PainterIO.Core (no UnityEngine). The SimTestKit run helpers check the 10.1 invariants and
// EventCapHits == 0 after every tick. Cross-rate tests use more rates than the 10.0 protocol (every rate here is a
// multiple of 6, so schedule switch times on multiples of 1/6 s stay on tick times).
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class AuditTests
    {
        private const double Eps = 1e-7;            // EventEpsilonSeconds
        private const double SparkSpeed = 10.8;     // 1.8 x 6
        private const double Closing = 4.8;         // SparkSpeed - PawnSpeed

        /// <summary>Supported tick rates that keep 1/6 s switch times on tick times (contract 3.1: 30..240).</summary>
        private static readonly int[] AuditRates = { 30, 48, 60, 90, 120, 144, 240 };

        /// <summary>SimTestKit.CrossRate over AuditRates: same events, times within 1e-6 s, same cells and ranks.</summary>
        private static Outcome CrossRateAll(string label, Func<int, Simulation> build, double until,
                                            Action<int, Simulation, EventLog> check, Action<Simulation> afterTick = null)
        {
            Outcome reference = null, at60 = null;
            foreach (int rate in AuditRates)
            {
                Simulation sim = build(rate);
                var log = new EventLog(sim);
                RunUntilTime(sim, until, true, afterTick);
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
        // R5 / R7: exit and return inside one tick

        // Player 0 owns [-12, 0] x [-4, 4], [0.125, 4] x [-4, 4] and the bridge [-12, 4] x [4, 6]: a one-cell neutral
        // column x in [0, 0.125] open only at the bottom. The head goes East on y = H from x = -0.83: it exits at x = 0
        // and returns at x = 0.125, both inside tick 4 at 30 Hz. The trail cell closes the upper column (31 cells
        // enclosed by own territory + trail, plus the trail cell as rim): exactly 32 cells, the lower column stays neutral.
        private static Simulation BuildGapColumn(int rate)
        {
            var b = new SimBuilder(rate);
            b.Add(V(-0.83, H), East, new ConstantHeadingController(East), (g, id) =>
            {
                FillRect(g, id, -12, -4, 0, 4);
                FillRect(g, id, 0.125, -4, 4, 4);
                FillRect(g, id, -12, 4, 4, 6);
            });
            b.AddIdle(IdleCorners[1]);
            return b.Build();
        }

        [Test]
        public void R5_ExitAndReturnInsideOneTickAcrossAOneCellGapCapturesTheClosedColumn()
        {
            CrossRateAll("exit+return in one tick", BuildGapColumn, 0.5, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent exit = log.Single(SimEventType.Exit, 0);
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(exit.Time, Is.EqualTo(0.83 / 6.0).Within(1e-9), at + "exit at x = 0");
                Assert.That(ret.Time, Is.EqualTo(0.955 / 6.0).Within(1e-9), at + "return at x = 0.125");
                AssertNear(V(0, H), exit.Point, 1e-9, at + "exit point");
                AssertNear(V(0.125, H), ret.Point, 1e-9, at + "return point");
                if (rate == 30)
                {
                    Assert.AreEqual(4, log.Ticks[log.IndexOf(exit)], at + "exit in tick 4");
                    Assert.AreEqual(4, log.Ticks[log.IndexOf(ret)], at + "return in the same tick");
                }
                Assert.AreEqual(32, ret.Cells.Length, at + "31 enclosed column cells + the trail cell (rim)");
                Assert.AreEqual(1, OwnerAt(sim, H, 2.0), at + "upper column captured");
                Assert.AreEqual(1, OwnerAt(sim, H, H), at + "trail cell captured as rim");
                Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, H, -2.0), at + "lower column open to the outside");
                Assert.IsTrue(sim.Players[0].Home);
                Assert.AreEqual(1, sim.Players[0].Captures);
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // R13: races decided across tick boundaries and inside a single tick (S4 geometry: the victim heads West to its
        // edge x = 0 from x = d; the spark starts g = L - s_cut behind the head, so t_c = g / 4.8 and t_r = d / 6).

        private static Simulation BuildRace(int rate, double d, double g, double roundDuration = 90.0)
        {
            var b = new SimBuilder(rate);
            b.Config.RoundDuration = roundDuration;
            b.AddRect(-12, -4, 0, 4, V(-6, H), West, new ConstantHeadingController(West));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 2 + H), V(8 + H, 2 + H), V(8 + H, H), V(d, H) });
            sim.DebugForceCut(0, sim.Players[0].Trail.Length - g, 1);
            return sim;
        }

        [Test]
        public void R13_CatchRootJustBeforeATickBoundaryLosesToAReturnOnThatBoundary()
        {
            // t_r = 0.5 is a tick time at every rate; t_c = 0.5 - 0.5 eps, so t_r < t_c + eps: the return wins although the
            // catch root lies in the previous tick (the candidate u0 + eps / dt spills into the next tick).
            const double tc = 0.5 - 0.5e-7;
            CrossRateAll("race across a tick boundary, saved", rate => BuildRace(rate, 3.0, Closing * tc), 0.8, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(0.5).Within(1e-9), at + "return on the tick boundary");
                Assert.IsTrue(ret.Chased, at + "chased");
                Assert.That(ret.Margin, Is.GreaterThanOrEqualTo(0.0), at + "margin");
                Assert.That(ret.Margin, Is.LessThan(1e-6), at + "the spark was at the head");
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "R13: t_r < t_c + eps is saved\n" + log.Dump());
                Assert.IsTrue(sim.Players[0].Alive);
            });
        }

        [Test]
        public void R13_CatchRootThreeEpsBeforeATickBoundaryBeatsAReturnOnThatBoundary()
        {
            const double tc = 0.5 - 3e-7;
            CrossRateAll("race across a tick boundary, caught", rate => BuildRace(rate, 3.0, Closing * tc), 0.8, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(tc + Eps).Within(1e-9), at + "caught at t_c + eps, before the boundary");
                Assert.AreEqual(0, log.Count(SimEventType.Return), at + "no return after the elimination");
                Assert.IsFalse(sim.Players[0].Alive);
            });
        }

        [Test]
        public void R13_ReturnBetweenOneAndTwoEpsAfterTheImpactIsEliminatedAtEveryRate()
        {
            // t_r = t_c + 1.5 eps: R13 says eliminated (t_r >= t_c + eps). The catch candidate (t_c + eps) and the return
            // are 0.5 eps apart, so they share a group whenever they fall in the same tick; the return must not win then.
            const double tc = 0.5 - 1.5e-7;
            CrossRateAll("return 1.5 eps after the impact", rate => BuildRace(rate, 3.0, Closing * tc), 0.8, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(tc + Eps).Within(1e-9), at + "caught at t_c + eps");
                Assert.AreEqual(0, log.Count(SimEventType.Return), at + "R13: t_r >= t_c + eps is not saved\n" + log.Dump());
            });
            // The same gap in the middle of a tick (t_r = 0.51 is not a tick time at any audit rate).
            const double tc2 = 0.51 - 1.5e-7;
            CrossRateAll("mid-tick", rate => BuildRace(rate, 6.0 * 0.51, Closing * tc2), 0.8, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                Assert.AreEqual(1, log.Count(SimEventType.SparkCaught, 0), at + "caught\n" + log.Dump());
                Assert.AreEqual(0, log.Count(SimEventType.Return), at + "not saved");
            });
        }

        [Test]
        public void R13_SparkSpawnedAndCatchingInsideTheSameTick()
        {
            // 30 Hz (dt = 33 ms). The spark spawns 0.05 u behind the head at t = 0: root at 0.05 / 4.8 = 10.4 ms.
            // Head 0.12 u from home (return at 20 ms): caught inside tick 0. Head 0.03 u from home (5 ms): saved.
            Simulation caughtSim = BuildRace(30, 0.12, 0.05);
            var caughtLog = new EventLog(caughtSim);
            StepN(caughtSim, 3);
            SimEvent caught = caughtLog.Single(SimEventType.SparkCaught, 0);
            Assert.AreEqual(0, caughtLog.Ticks[caughtLog.IndexOf(caught)], "caught in the tick the spark spawned in");
            Assert.That(caught.Time, Is.EqualTo(0.05 / Closing + Eps).Within(1e-12));
            AssertNear(V(0.12 - 6.0 * caught.Time, H), caught.Point, 1e-9, "SparkCaught.Point = head at the catch");
            Assert.That(caught.DistanceHome, Is.EqualTo(0.12 - 6.0 * caught.Time + H).Within(1e-6),
                        "distance to the nearest own cell center, measured before Neutralize");
            Assert.AreEqual(0, caughtLog.Count(SimEventType.Return));

            Simulation savedSim = BuildRace(30, 0.03, 0.05);
            var savedLog = new EventLog(savedSim);
            StepN(savedSim, 3);
            SimEvent ret = savedLog.Single(SimEventType.Return, 0);
            Assert.AreEqual(0, savedLog.Ticks[savedLog.IndexOf(ret)]);
            Assert.That(ret.Time, Is.EqualTo(0.005).Within(1e-12));
            Assert.IsTrue(ret.Chased);
            Assert.That(ret.Margin, Is.EqualTo((0.05 - Closing * 0.005) / SparkSpeed).Within(1e-12), "(L - S) / SparkSpeed");
            Assert.AreEqual(0, savedLog.Count(SimEventType.SparkCaught));
        }

        // ------------------------------------------------------------------------------------------------------------
        // R19 + R13: an impact exactly at t = RoundDuration is an event of that instant (brief 6.4: resolve the events of
        // that instant first, then rank); a return at the same instant still wins the tie (brief 6.1).

        [Test]
        public void R19_SparkImpactExactlyAtRoundDurationEliminatesBeforeTheRanking()
        {
            CrossRateAll("impact at the round end", rate =>
            {
                var b = new SimBuilder(rate);
                b.Config.RoundDuration = 1.0;
                b.AddRect(-12, -4, 0, 4, V(-6, H), East, new ConstantHeadingController(East));   // 6144 cells
                b.AddIdle(IdleCorners[1]);                                                       // disc, fewer cells
                Simulation sim = b.Build();
                sim.DebugSetTrail(0, new[] { V(0, H), V(5 + H, H) });
                sim.DebugForceCut(0, sim.Players[0].Trail.Length - Closing * 1.0, 1);           // t_c = 1.0 exactly
                return sim;
            }, 2.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                Assert.IsTrue(sim.Ended, at + "ended");
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(1.0).Within(1e-6), at + "caught at the last instant");
                Assert.IsFalse(sim.Players[0].Alive, at + "the impact at t = RoundDuration counts");
                Assert.AreEqual(new[] { 2, 1 }, sim.Result.Ranks, at + "the caught player is not ranked on its cells");
                Assert.AreEqual(new List<int> { 1 }, sim.Result.Winners, at + "winners");
                Assert.AreEqual(6144, sim.Result.FinalCells[0], at + "FinalCells = cells before the eliminating group");
            });
        }

        [Test]
        public void R19_ReturnAndImpactBothExactlyAtRoundDurationTheReturnWinsAndCounts()
        {
            // d = 6 (t_r = 1.0) and g = 4.8 (t_c = 1.0): exact tie on the last instant. The return wins and counts: the
            // player is saved and ranked alive. Contract 24 (R13 v1.4): being chased, it captures nothing, so it is ranked
            // on its unchanged 6144 cells (still more than the idle disc). R19b covers an unchased capture at that instant.
            CrossRateAll("tie at the round end", rate => BuildRace(rate, 6.0, Closing * 1.0, 1.0), 2.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                Assert.IsTrue(sim.Ended, at + "ended");
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(1.0).Within(1e-6), at + "return at the last instant");
                Assert.IsTrue(ret.Chased, at + "chased");
                Assert.AreEqual(0, ret.Cells.Length, at + "contract 24: a chased return captures nothing");
                Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), at + "the return wins the tie");
                Assert.IsTrue(sim.Players[0].Alive, at + "saved");
                Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason, at + "time up");
                Assert.AreEqual(6144, sim.Result.FinalCells[0], at + "saved and ranked on its unchanged territory");
                Assert.AreEqual(new[] { 1, 2 }, sim.Result.Ranks, at + "ranks: alive, so ranked by cells (not as eliminated)");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // R9: last-cell loss while trailing (with a pending spark), and simultaneous eliminations of different causes.

        // A (player 0) returns at t = 2.0925 / 6 with a trail enclosing x in (0, 10.0625), y in (-5.9375, 6.0625).
        private const double ReturnA = 2.0925 / 6.0;

        private static void AddReturningA(SimBuilder b)
        {
            b.AddRect(-8, -8, 0, 8, V(-4, H), West, new ConstantHeadingController(West));
        }

        private static void SetReturningTrail(Simulation sim)
        {
            sim.DebugSetTrail(0, new[] { V(0, 6 + H), V(10 + H, 6 + H), V(10 + H, -6 + H), V(2.0925, -6 + H) });
        }

        [Test]
        public void R9_TrailingPlayerWhoseLastCellsAreCapturedIsEliminatedAndItsSparkVanishes()
        {
            var b = new SimBuilder(60);
            AddReturningA(b);
            int pb = b.AddRect(6, -3, 9, 3, V(7 + H, H), East, new ConstantHeadingController(East));
            int pc = b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            SetReturningTrail(sim);
            sim.DebugSetTrail(pb, new[] { V(9, H), V(20 + H, H) });      // trailing far East, away from everything
            sim.DebugForceCut(pb, 0.5, pc);                               // spark far behind: catch at ~2.2 s
            int bStart = sim.Grid.CountOf(2);
            Assert.AreEqual(24 * 48, bStart);
            var log = new EventLog(sim);
            RunUntilTime(sim, 3.0);

            SimEvent elim = log.Single(SimEventType.Eliminated, pb);
            Assert.AreEqual(EliminationCause.TerritoryLost, elim.Cause, "R9: zero cells eliminates even while trailing");
            Assert.AreEqual(0, elim.Other, "Other = the returning player that took the last cells");
            Assert.That(elim.Time, Is.EqualTo(ReturnA).Within(1e-9));
            Assert.AreEqual(0, log.Count(SimEventType.SparkCaught), "the spark died with its victim\n" + log.Dump());
            PlayerState vb = sim.Players[pb];
            Assert.IsFalse(vb.Alive);
            Assert.IsNull(vb.Spark);
            Assert.IsTrue(vb.Trail.IsEmpty);
            Assert.AreEqual(bStart, vb.FinalCells, "FinalCells = cells held just before the capture");
            Assert.AreEqual(0, sim.Players[pc].Kills, "a TerritoryLost elimination credits no spark kill");
            Assert.AreEqual(3, sim.RankOf(pb), "1 + two players alive after its group");
            Assert.IsFalse(sim.Ended);
        }

        [Test]
        public void R19_SimultaneousEliminationsOfDifferentCausesShareARankAndTheLastOneStandingWins()
        {
            // A's return takes all of B's cells (B is home: TerritoryStolen, Exit, then TerritoryLost) at the very
            // instant C's spark catches C (root eps before the return, so its candidate falls on the return).
            var b = new SimBuilder(60);
            AddReturningA(b);
            int pb = b.AddRect(6, -3, 9, 3, V(7.5, 0), North, new HomeCirclerController(V(7.5, 0)));
            int pc = b.AddRect(-24, 20, -20, 24, V(-22, 22), East, new ConstantHeadingController(East));
            Simulation sim = b.Build();
            SetReturningTrail(sim);
            sim.DebugSetTrail(pc, new[] { V(-20, 22 + H), V(-10 + H, 22 + H) });
            sim.DebugForceCut(pc, sim.Players[pc].Trail.Length - Closing * (ReturnA - Eps), 0);
            int bStart = sim.Grid.CountOf(2), cStart = sim.Grid.CountOf(3);
            var log = new EventLog(sim);
            RunUntilTime(sim, 1.0);

            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.LastSurvivor, sim.Result.Reason);
            SimEvent eb = log.Single(SimEventType.Eliminated, pb);
            SimEvent ec = log.Single(SimEventType.Eliminated, pc);
            Assert.AreEqual(EliminationCause.TerritoryLost, eb.Cause);
            Assert.AreEqual(EliminationCause.Spark, ec.Cause);
            Assert.AreEqual(sim.Players[pb].EliminatedAt, sim.Players[pc].EliminatedAt, "same group, same instant");
            Assert.AreEqual(1, log.Count(SimEventType.TerritoryStolen, pb), "B was home on a stolen cell");
            Assert.AreEqual(new[] { 1, 2, 2 }, sim.Result.Ranks, "eliminated at the same instant share a rank");
            Assert.AreEqual(new List<int> { 0 }, sim.Result.Winners);
            Assert.AreEqual(bStart, sim.Result.FinalCells[pb]);
            Assert.AreEqual(cStart, sim.Result.FinalCells[pc]);
            Assert.AreEqual(1, sim.Players[0].Kills, "C's spark was dealt by A");
        }

        // ------------------------------------------------------------------------------------------------------------
        // R15: two heads entering the ring at the same analytic instant from perpendicular directions (their entry
        // parameters differ only by rounding) contest it: nobody picks until one of them leaves (brief 6.4).

        [Test]
        public void R15_RingEnteredAtTheSameInstantFromPerpendicularDirectionsIsContested()
        {
            const double r = 1.05, off = 0.6875, enter = 0.4, bTurn = 0.5;
            double half = Math.Sqrt(r * r - off * off);
            double dist = half + 6.0 * enter;
            Vec2d dirB = Vec2d.FromAngle(0.75 * Math.PI);                  // B moves North-West
            Vec2d nB = V(Math.Sqrt(0.5), Math.Sqrt(0.5));                   // B's chord is offset to the North-East
            Vec2d startA = V(-dist, -off);
            Vec2d startB = nB * off - dirB * dist;
            var b = new SimBuilder(60);
            b.AddRect(-20, -12, -16, -8, V(-18, -10), East, new ConstantHeadingController(East));
            b.AddRect(16, -12, 20, -8, V(18, -10), East,
                      new HeadingScheduleController((0.0, 0.75 * Math.PI), (bTurn, -0.25 * Math.PI)));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { startA - V(3, 0), startA });
            sim.DebugSetTrail(1, new[] { startB - dirB * 3.0, startB });
            sim.DebugPlaceRing(V(0, 0));
            var log = new EventLog(sim);
            RunUntilTime(sim, bTurn);
            Assert.AreEqual(0, log.Count(SimEventType.RingPicked),
                            "both heads entered at t = " + enter + ": contested, nobody picks\n" + log.Dump());
            RunUntilTime(sim, 0.7);
            SimEvent pick = log.Single(SimEventType.RingPicked);
            Assert.AreEqual(0, pick.Player, "A picks once B has left");
            Assert.That(pick.Time, Is.EqualTo(bTurn + (bTurn - enter)).Within(1e-6), "at B's exit instant (U-turn)");
        }

        // ------------------------------------------------------------------------------------------------------------
        // R16 / 5.1: a self crossing that lands within the rounding band of the old segment's line at a tick end must be
        // counted exactly once over the two ticks (A4's finding; Geo.ProperIntersect now applies its rounding band to the
        // moving segment's end as well as its start, see Geo_ProperIntersect_EndInTheRoundingBandCountsOnce).

        [Test]
        public void R16_CrossingLandingInTheRoundingBandAtATickEndIsCountedExactlyOnce()
        {
            // A4's exact positions (R10 path at 60 Hz, ticks 99 and 100).
            Vec2d o0 = V(1.0, 0.0625), o1 = V(1.1, 0.0625);
            Vec2d a = V(1.0625, 0.16250000000000017);
            Vec2d m = V(1.0625, 0.06250000000000017);
            Vec2d c = V(1.0625, -0.03749999999999984);
            var trail = new Trail();
            trail.Start(o0);
            foreach (Vec2d p in new[] { o1, V(1.1, 1.5), V(1.0625, 1.5), a }) trail.Append(p);
            var list = new List<SelfCrossing>();
            int first = trail.SelfCrossings(a, m, 0.0, trail.Length + 0.1 - 1.0, list);
            Vec2d xPoint = first == 1 ? list[0].Point : V(double.NaN, double.NaN);
            trail.Append(m);
            int second = trail.SelfCrossings(m, c, 0.0, trail.Length + 0.1 - 1.0, list);
            Assert.AreEqual(1, first + second, "a crossing is counted by exactly one of two consecutive tick segments");
            Assert.AreEqual(1, first, "the tick whose end reaches the line counts it (ta = 1)");
            AssertNear(m, xPoint, 1e-12, "X = the tick end");

            // LoopErase must remove the same loop (else R8 breaks: an uncharged return would capture the self loop).
            List<Vec2d> erased = LoopErase.Erase(new[] { o0, o1, V(1.1, 1.5), V(1.0625, 1.5), a, m, c });
            Assert.AreEqual(3, erased.Count, "loop erased: [o0, X, end]");
            AssertNear(o0, erased[0], 0.0, "first point");
            AssertNear(c, erased[2], 0.0, "last point");
        }

        // ------------------------------------------------------------------------------------------------------------
        // R10 / R11: an exposure-induced first contact at the Simulation level: the attacker enters the trail's contact
        // band while the nearest trail point is still inside HeadGrace; the cut happens when the exposed end E(t) = L - 1
        // comes within 0.63 u, with s_cut = L(t_cut) - HeadGrace, identically at every rate.

        // Victim: East on y = H from x = -0.9375, exit at x = 0 (L(t) = 6 t - 0.9375). Attacker: South on x = 3.0625,
        // reaching y = H + 0.63 at t1 = 0.75 when the victim's head is 0.5 u past that column. With tau = 6 (t - t1):
        // (tau - 0.5)^2 + (0.63 - tau)^2 = 0.63^2, i.e. 2 tau^2 - 2.26 tau + 0.25 = 0.
        private static readonly double ExposureTau = (2.26 - Math.Sqrt(2.26 * 2.26 - 2.0)) / 4.0;
        private static readonly double ExposureCut = 0.75 + ExposureTau / 6.0;

        [Test]
        public void R11_ExposureInducedCutGivesSCutEqualToLMinusHeadGraceAtEveryRate()
        {
            CrossRateAll("exposure-induced cut", rate =>
            {
                var b = new SimBuilder(rate);
                b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East, new ConstantHeadingController(East));
                b.AddRect(1, 5, 5, 9, V(3 + H, H + 0.63 + 4.5), South, new ConstantHeadingController(South));
                return b.Build();
            }, 1.2, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent cut = log.Single(SimEventType.Cut, 0);
                Assert.AreEqual(1, cut.Other, at + "attacker");
                Assert.That(cut.Time, Is.EqualTo(ExposureCut).Within(1e-9), at + "cut time");
                double l = 6.0 * ExposureCut - (1 - H);
                Assert.That(cut.S, Is.EqualTo(l - 1.0).Within(1e-9), at + "s_cut = L - HeadGrace (the exposed end)");
                AssertNear(V(l - 1.0, H), cut.Point, 1e-9, at + "Cut.Point = PointAt(s_cut)");
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(ExposureCut + 1.0 / Closing + Eps).Within(1e-9), at + "gap HeadGrace closes at 4.8 u/s");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // R4 / R12 / R13: a trailing head held against the border does not grow its trail, so the spark gains on it at
        // the full SparkSpeed. Contract 23.2 D3: the head starts 0.05 u short of the inset line x = 31.55, so its first
        // held tick advances it to the line (L grows by 0.05 u during that tick only), then it stays exactly there.

        [Test]
        public void R13_HeadHeldAgainstTheBorderIsCaughtAtTheFullSparkSpeed()
        {
            var b = new SimBuilder(60);
            b.AddRect(20, -4, 26, 4, V(24, H), East, new ConstantHeadingController(East));
            b.AddIdle(IdleCorners[0]);
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(26, H), V(31.5, H) });       // inset wall at 31.55: the next step is held
            double l = sim.Players[0].Trail.Length;
            sim.DebugForceCut(0, l - 1.08, 1);
            var log = new EventLog(sim);
            Vec2d held = Vec2d.Zero;
            RunUntilTime(sim, 0.5, true, s =>
            {
                if (!s.Players[0].Alive) return;
                if (s.Tick == 1)
                {
                    held = s.Players[0].Pos;
                    Assert.That(held.X, Is.EqualTo(32 - 0.45).Within(1e-9), "D3: on the inset line after the first held tick");
                    Assert.AreEqual(H, held.Y, "pushed along the normal: no slide");
                    Assert.That(s.Players[0].Trail.Length, Is.EqualTo(l + 0.05).Within(1e-9), "the trail grew to the line");
                }
                else
                {
                    Assert.AreEqual(held, s.Players[0].Pos, "held");
                }
            });
            SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
            Assert.That(caught.Time, Is.EqualTo((1.08 + 0.05) / SparkSpeed + Eps).Within(1e-9), "L constant once held: (gap + 0.05) / SparkSpeed");
        }

        // R4 / R1 / R8: an excursion that slides along the East wall while trailing, then returns. The trail stays in the
        // inset shape, the capture is only the region between trail and territory (C3 at the Simulation level), and the
        // outer rim band stays neutral (R1).
        [Test]
        public void R4_SlideAlongTheWallWhileTrailingCapturesOnlyTheRegionBetweenTrailAndTerritory()
        {
            var b = new SimBuilder(60);
            b.AddRect(20, -4, 26, 10, V(24 + H, H), East,
                      new HeadingScheduleController((0.0, East), (1.5, 80.0 * Math.PI / 180.0), (2.5, West)));
            b.AddIdle(IdleCorners[3]);
            Simulation sim = b.Build();
            var log = new EventLog(sim);
            double inset = 32 - 0.45;
            RunUntilTime(sim, 4.0, true, s =>
            {
                PlayerState p = s.Players[0];
                Assert.That(s.Arena.SignedDistance(p.Pos), Is.LessThanOrEqualTo(-s.Config.ArenaMargin + 1e-9), "head in the inset");
                if (s.Time > 1.6 && s.Time < 2.5)
                    Assert.That(p.Pos.Y - p.PrevPos.Y, Is.EqualTo(0.1).Within(1e-9), "slides at full speed while trailing");
            });
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.AreEqual(1, log.Count(SimEventType.Exit, 0));
            // Head x at the wall: contract 23.2 D3 holds it on the inset line itself (before D3 it stopped one step short,
            // at 24.0625 + 0.1 k <= 31.55, i.e. 31.4625); the slide runs from y = H to about 6.06.
            double wallX = inset;
            Assert.That(ret.Point.Y, Is.EqualTo(sim.Players[0].Pos.Y).Within(1e-9), "returned West along the top leg");
            double yTop = sim.Players[0].Pos.Y;
            Assert.That(yTop, Is.EqualTo(H + 6.0 * (2.5 - 1.5)).Within(0.11), "slid about 6 u");
            double area = (wallX - 26.0) * (yTop - H);
            double cells = area / (0.125 * 0.125);
            Assert.That(ret.Cells.Length, Is.GreaterThanOrEqualTo((int)(cells * 0.97)), "region between trail and territory");
            Assert.That(ret.Cells.Length, Is.LessThanOrEqualTo((int)(cells * 1.10)), "nothing else (no map painting)");
            Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 31.9, 3.0), "R1: the rim band stays neutral");
            Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 29.0, -2.0), "below the excursion: untouched");
            Assert.AreEqual(1, OwnerAt(sim, 29.0, 3.0), "inside the excursion");
        }

        // ------------------------------------------------------------------------------------------------------------
        // R13b / R14 at every audit rate: a cut and a return 13 ms apart (inside one tick at 30 Hz, in different ticks
        // elsewhere) in both orders, and a cut at the exact closure instant. Victim returns West to x = 0 from x = headX
        // on y = -1.9375; the attacker goes West on y = H and touches the victim's right leg (x = 4.0625) when it reaches
        // x = 4.6925.

        private static Simulation BuildCutReturn(int rate, double tReturn, double tCut)
        {
            var b = new SimBuilder(rate);
            b.AddRect(-12, -4, 0, 4, V(-6, H), West, new ConstantHeadingController(West));
            b.AddRect(7, -2, 10, 2, V(4 + H + 0.63 + 6.0 * tCut, H), West, new ConstantHeadingController(West));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 3 + H), V(4 + H, 3 + H), V(4 + H, -2 + H), V(6.0 * tReturn, -2 + H) });
            return sim;
        }

        [Test]
        public void R13b_CutThenReturnSameOutcomeAtEveryRate()
        {
            const double tCut = 0.51, tRet = 0.5 + 0.7 / 30.0;
            CrossRateAll("cut then return", rate => BuildCutReturn(rate, tRet, tCut), 0.6, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent cut = log.Single(SimEventType.Cut, 0);
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(cut.Time, Is.EqualTo(tCut).Within(1e-9), at + "cut time");
                Assert.That(ret.Time, Is.EqualTo(tRet).Within(1e-9), at + "return time");
                Assert.That(log.IndexOf(cut), Is.LessThan(log.IndexOf(ret)), at + "Cut then Return");
                Assert.IsTrue(ret.Chased, at + "chased");
                double l = (4 + H) + 5 + (4 + H);   // trail length at the return (the head reached x = 0)
                double s = 7 + H + SparkSpeed * (tRet - tCut);
                Assert.That(ret.Margin, Is.EqualTo((l - s) / SparkSpeed).Within(1e-9), at + "margin");
                Assert.AreEqual(0, ret.Cells.Length, at + "contract 24: saved but captures nothing");
                Assert.AreEqual(12 * 8 * 64, sim.Grid.CountOf(1), at + "territory unchanged");
            });
        }

        [Test]
        public void R13b_ReturnThenCutTimeSameOutcomeAtEveryRate()
        {
            const double tRet = 0.51, tCut = 0.5 + 0.7 / 30.0;
            CrossRateAll("return then cut time", rate => BuildCutReturn(rate, tRet, tCut), 0.6, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                Assert.That(log.Single(SimEventType.Return, 0).Time, Is.EqualTo(tRet).Within(1e-9), at + "return");
                Assert.AreEqual(0, log.Count(SimEventType.Cut), at + "the victim was home before the contact");
                Assert.AreEqual(0, sim.Players[1].CutsMade, at + "no cut credited");
            });
        }

        [Test]
        public void R14_CutAtTheExactClosureInstantIsIgnoredAtEveryRate()
        {
            CrossRateAll("cut at closure", rate => BuildCutReturn(rate, 0.51, 0.51), 0.6, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.IsFalse(ret.Chased, at + "not chased");
                Assert.AreEqual(0, log.Count(SimEventType.Cut), at + "returns resolve first\n" + log.Dump());
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // R11: two attackers touching the same trail point at the same instant from opposite sides (equal s): the lowest
        // attacker index gets the spark and the only CutsMade.

        [Test]
        public void R11_TwoAttackersSameInstantSameSTheLowestIndexWins()
        {
            CrossRateAll("equal s tie", rate =>
            {
                var b = new SimBuilder(rate);
                b.AddRect(-6, -3, 0, 3, V(-1 + H, H), East, new ConstantHeadingController(East));
                b.AddRect(2, 12, 6, 16, V(4 + H, H + 0.63 + 12.0), South, new ConstantHeadingController(South));
                b.AddRect(2, -16, 6, -12, V(4 + H, H - 0.63 - 12.0), North, new ConstantHeadingController(North));
                return b.Build();
            }, 2.05, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent cut = log.Single(SimEventType.Cut, 0);
                Assert.That(cut.Time, Is.EqualTo(2.0).Within(1e-9), at + "both touch at t = 2");
                Assert.That(cut.S, Is.EqualTo(4 + H).Within(1e-9), at + "same point");
                Assert.AreEqual(1, cut.Other, at + "ties on s go to the lowest attacker index");
                Assert.AreEqual(1, sim.Players[0].Spark.Attacker, at + "spark attacker");
                Assert.AreEqual(1, sim.Players[1].CutsMade, at + "winner credited");
                Assert.AreEqual(0, sim.Players[2].CutsMade, at + "only the winner gets CutsMade++");
            });
        }

        // R10: an attacker cuts whether it is home or trailing. The victim's trail crosses the attacker's territory; the
        // attacker, moving inside its own color, touches it there.
        [Test]
        public void R10_AnAttackerStandingOnItsOwnColorCutsATrailCrossingIt()
        {
            bool homeAtCut = false;
            CrossRateAll("home attacker", rate =>
            {
                var b = new SimBuilder(rate);
                b.AddRect(-12, -4, 0, 4, V(-1 + H, H), East, new ConstantHeadingController(East));
                b.AddRect(3, -10, 6, 4, V(4.5, H - 0.63 - 9.0), North, new ConstantHeadingController(North));
                Simulation sim = b.Build();
                sim.EventRaised += e =>
                {
                    if (e.Type == SimEventType.Cut) homeAtCut = sim.Players[1].Home;
                };
                return sim;
            }, 2.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent cut = log.Single(SimEventType.Cut, 0);
                Assert.AreEqual(1, cut.Other, at + "attacker");
                Assert.That(cut.Time, Is.EqualTo(1.5).Within(1e-9), at + "cut time");
                Assert.That(cut.S, Is.EqualTo(4.5).Within(1e-9), at + "cut on the attacker's own color");
                Assert.IsTrue(homeAtCut, at + "the attacker was home when it cut");
                Assert.AreEqual(0, log.Count(SimEventType.Exit, 1), at + "the attacker never left home");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // R16: a near miss (tangency short of the line) and a superposed U-turn back through the trail's corner create no
        // pocket and keep the charge; the same head then makes a real crossing, which spends it.

        [Test]
        public void R16_NearMissAndSuperposedUTurnDoNotCountThenARealCrossingDoes()
        {
            CrossRateAll("tangency and U-turn", rate =>
            {
                var b = new SimBuilder(rate);
                b.AddRect(-12, -4, 0, 4, V(-6, H), East,
                          new HeadingScheduleController((0.0, South), (2.0 / 6.0, East), (8.0 / 6.0, North), (11.0 / 6.0, South)));
                b.AddIdle(IdleCorners[1]);
                Simulation sim = b.Build();
                // Old segment along y = H from x = 0 to 8.0625, then up to y = 4.1125. The head starts at (3.0625, 2.1125)
                // going South: after 2 u it stops 0.05 u above the old segment (near miss) and turns East along it.
                sim.DebugSetTrail(0, new[] { V(0, H), V(8 + H, H), V(8 + H, 4.1125), V(3 + H, 4.1125), V(3 + H, 2.1125) });
                sim.DebugSetCharged(0, true);
                return sim;
            }, 2.8, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                // E leg (y = 0.1125) from x = 3.0625 to 9.0625: crosses the vertical old leg x = 8.0625 at t = 7/6, a real
                // crossing of an old segment whose loop is the 5 x 4 rectangle [3.0625, 8.0625] x [0.1125, 4.1125].
                List<SimEvent> pockets = log.Of(SimEventType.LassoPocket, 0);
                Assert.AreEqual(1, pockets.Count, at + "exactly one pocket\n" + log.Dump());
                Assert.That(pockets[0].Time, Is.EqualTo(7.0 / 6.0).Within(1e-9), at + "the real crossing at x = 8.0625");
                AssertNear(V(8 + H, 0.1125), pockets[0].Point, 1e-9, at + "X");
                // The near miss at t = 1/3 (0.05 u above y = H) did not count, and neither did the superposed U-turn (N 3
                // then S 6 back down the same line, through the corner where the E leg ends).
                Assert.AreEqual(0, log.Count(SimEventType.LassoCrossNoCharge, 0), at + "no other crossing at all");
                Assert.AreEqual(1, sim.Players[0].PocketsMade, at + "charge spent once");
                Assert.IsFalse(sim.Players[0].Charged, at + "spent");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // R17 / brief 5.4: the return validates the pocket and the ordinary capture at once, each cell counted once:
        // Return.Cells of the charged run == sorted union of the pocket and the uncharged run's capture (same path).

        [Test]
        public void R17_ReturnCapturesPocketAndOrdinaryCaptureAsOneExactSetUnion()
        {
            var plain = new Dictionary<int, int[]>();
            CrossRateAll("uncharged reference", rate => PocketScenario(rate, false, out _, out _, false), 6.0, (rate, sim, log) =>
            {
                plain[rate] = log.Single(SimEventType.Return, 0).Cells;
            });
            CrossRateAll("charged union", rate => PocketScenario(rate, true, out _, out _, false), 6.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                int[] pocket = log.Single(SimEventType.LassoPocket, 0).Cells;
                int[] ret = log.Single(SimEventType.Return, 0).Cells;
                var union = new SortedSet<int>(pocket);
                union.UnionWith(plain[rate]);
                var expected = new int[union.Count];
                union.CopyTo(expected);
                Assert.That(pocket.Length, Is.GreaterThan(900), at + "a real pocket");
                Assert.That(expected.Length, Is.LessThan(pocket.Length + plain[rate].Length), at + "the two portions overlap");
                Assert.IsTrue(SameCells(expected, ret), at + "Return.Cells == pocket U ordinary capture, each cell once ("
                              + ret.Length + " vs " + expected.Length + ")");
            });
        }

        // R17 + R18: a pending pocket is part of the return's claim, so pocket cells also claimed by a simultaneous
        // return keep their previous owner. The pocket is set directly (PlayerState.Pocket is a public CellMask).
        [Test]
        public void R18_PocketCellsClaimedByASimultaneousReturnKeepTheirPreviousOwner()
        {
            var b = new SimBuilder(60);
            // Rule v1.8 (contract 32): the synthetic pocket lies far from A's land and trail (a real pocket always lies on
            // the trail), so the single-domain rule would sever it as an island; this test is about R18, so it runs with
            // the pre-v1.8 rules.
            b.Config.SingleDomain = SingleDomainRule.Off;
            b.AddRect(-8, -8, 0, 8, V(-4, H), West, new ConstantHeadingController(West));
            int pc = b.AddRect(14, -6, 20, 6, V(17, H), East, new ConstantHeadingController(East));
            Simulation sim = b.Build();
            // A returns West to x = 0 at t = 0.5 / 6 with a small loop; C returns East to x = 14 at the same instant with a
            // capture x in (11.0625, 14), y in (-0.9375, 1.0625).
            sim.DebugSetTrail(0, new[] { V(0, 1 + H), V(1 + H, 1 + H), V(1 + H, H), V(0.5, H) });
            sim.DebugSetTrail(pc, new[] { V(14, 1 + H), V(11 + H, 1 + H), V(11 + H, -1 + H), V(13.5, -1 + H) });
            // A's synthetic pending pocket: the neutral block [10, 12] x [-2, 2].
            for (double y = -2 + H; y < 2; y += 0.125)
                for (double x = 10 + H; x < 12; x += 0.125)
                    sim.Players[0].Pocket.Set(CellIndex(sim.Grid, x, y));
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.1);
            SimEvent ra = log.Single(SimEventType.Return, 0);
            SimEvent rc = log.Single(SimEventType.Return, pc);
            Assert.AreEqual(ra.Time, rc.Time, "simultaneous");
            Assert.That(ra.Time, Is.EqualTo(0.5 / 6.0).Within(1e-9));
            Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 11.5, 0.5), "pocket cell claimed by both: stays neutral");
            Assert.AreEqual(1, OwnerAt(sim, 10.5, 0.5), "pocket-only cell goes to A");
            Assert.AreEqual(1, OwnerAt(sim, 11.5, 1.5), "pocket-only cell above C's capture goes to A");
            Assert.AreEqual(2, OwnerAt(sim, 13.0, 0.5), "C-only cell goes to C");
            Assert.AreEqual(1, OwnerAt(sim, 0.5, 0.5), "A's ordinary capture");
            Assert.AreEqual(0, sim.Players[0].Pocket.Count, "pocket cleared at the return");
            var setA = new HashSet<int>(ra.Cells);
            foreach (int cell in rc.Cells) Assert.IsFalse(setA.Contains(cell), "no cell given to both");
        }

        // ------------------------------------------------------------------------------------------------------------
        // R18b both ways: two simultaneous returns where each capture contains the other's return cell. Both get their
        // capture, both lose the cell they stand on to the other, both restart an exit at their head (TerritoryStolen,
        // Other = the taker) and must reach their CURRENT color; the doubly claimed gap stays neutral.

        [Test]
        public void R18b_MutualStealingBothSimultaneousReturnersRestartAnExit()
        {
            var b = new SimBuilder(60);
            b.AddRect(-8, -4, -1, 4, V(-4, H), West, new ConstantHeadingController(West));
            b.AddRect(1, -4, 8, 4, V(4, H), East, new ConstantHeadingController(East));
            Simulation sim = b.Build();
            // A's loop x in (-1, 3.0625), y in (-0.9375, 3.0625) holds B's head and B's return cell; B's loop
            // x in (-3.0625, 1), y in (-2.9375, 1.0625) holds A's head and A's return cell. Returns at t = 0.25 / 6.
            sim.DebugSetTrail(0, new[] { V(-1, 3 + H), V(3 + H, 3 + H), V(3 + H, -1 + H), V(-0.75, -1 + H) });
            sim.DebugSetTrail(1, new[] { V(1, -3 + H), V(-3 - H, -3 + H), V(-3 - H, 1 + H), V(0.75, 1 + H) });
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.1);
            double tr = 0.25 / 6.0;
            SimEvent ra = log.Single(SimEventType.Return, 0), rb = log.First(SimEventType.Return, 1);
            Assert.That(ra.Time, Is.EqualTo(tr).Within(1e-9));
            Assert.AreEqual(ra.Time, rb.Time, "simultaneous");
            Assert.AreEqual(0, log.Count(SimEventType.Cut), "no head came near an exposed trail");
            SimEvent sa = log.Single(SimEventType.TerritoryStolen, 0), sb = log.Single(SimEventType.TerritoryStolen, 1);
            Assert.AreEqual(1, sa.Other, "B took A's return cell");
            Assert.AreEqual(0, sb.Other, "A took B's return cell");
            Assert.AreEqual(2, OwnerAt(sim, -1 - H, -1 + H), "A's return cell now B's");
            Assert.AreEqual(1, OwnerAt(sim, 1 + H, 1 + H), "B's return cell now A's");
            Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, 0.0, 0.5), "gap claimed by both stays neutral");
            Assert.AreEqual(1, OwnerAt(sim, 2.0, 2.0), "B's land taken by A only");
            Assert.AreEqual(2, OwnerAt(sim, -2.0, -2.0), "A's land taken by B only");
            Assert.That(ra.Cells.Length, Is.GreaterThan(200), "A got the rest of its capture");
            Assert.That(rb.Cells.Length, Is.GreaterThan(200), "B got the rest of its capture");
            Assert.IsFalse(sim.Players[0].Home || sim.Players[1].Home, "both trailing again");
            Assert.AreEqual(2, log.Count(SimEventType.Exit), "one new exit each, at the head");
            // A crosses B's new land (x down to -3.0625, B's rim column) and finds its own color at x = -3.125; B mirrors
            // it at x = 3.125: second returns at tr + 2.125 / 6, not on the stolen cells.
            RunUntilTime(sim, 0.6);
            Assert.AreEqual(2, log.Count(SimEventType.Return, 0), "A reached its current color again\n" + log.Dump());
            Assert.AreEqual(2, log.Count(SimEventType.Return, 1), "B reached its current color again");
            Assert.That(log.Of(SimEventType.Return, 0)[1].Time, Is.EqualTo(tr + 2.125 / 6.0).Within(1e-9), "A on its current color");
            Assert.That(log.Of(SimEventType.Return, 1)[1].Time, Is.EqualTo(tr + 2.125 / 6.0).Within(1e-9), "B on its current color");
            Assert.IsTrue(sim.Players[0].Home && sim.Players[1].Home);
        }

        // ------------------------------------------------------------------------------------------------------------
        // R5 / GR-Edge at the Simulation level (A2 emulated it): ticks that end exactly on the territory edge give
        // exactly one Exit at the edge time and, coming back, exactly one Return; the back-and-forth line captures 0.

        [Test]
        public void R5_ExitAndReturnOnTickEndingEdgesHappenOnceAtTheEdgeTimeAndALineCapturesNothing()
        {
            CrossRateAll("GR-Edge sim", rate =>
            {
                var b = new SimBuilder(rate);
                b.AddRect(-4, -4, 4, 4, V(3.5, H), East, new HeadingScheduleController((0.0, East), (1.0 / 6.0, West)));
                b.AddIdle(IdleCorners[1]);
                return b.Build();
            }, 0.5, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent exit = log.Single(SimEventType.Exit, 0);
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(exit.Time, Is.EqualTo(1.0 / 12.0).Within(1e-9), at + "exit at the edge time");
                Assert.That(ret.Time, Is.EqualTo(0.25).Within(1e-9), at + "return at the edge time");
                AssertNear(V(4, H), exit.Point, 1e-9, at + "exit point on the edge");
                AssertNear(V(4, H), ret.Point, 1e-9, at + "return point on the edge");
                Assert.AreEqual(0, ret.Cells.Length, at + "a back-and-forth line captures nothing (R8, C2)");
                Assert.IsTrue(sim.Players[0].Home, at + "the empty return still ends the exit safely (R7)");
                Assert.AreEqual(0, sim.Players[0].Captures, at + "D2: a Return with no cell is not a capture");
            });
        }

        // R7 / contract 23.2 D2: PlayerState.Captures counts only the Returns that applied cells, while the Return event is
        // still emitted for every return. Player 0 owns [-4, 4]^2: a 0.0625 u poke out of its East edge and straight back
        // (exit at x = 4, U-turn at t = 1/6, empty return), then a real excursion East 1.0625 u, North 1 u, West home.
        [Test]
        public void R7_CapturesCountsOnlyReturnsWithCellsButEveryReturnIsEmitted()
        {
            CrossRateAll("D2 captures counter", rate =>
            {
                var b = new SimBuilder(rate);
                b.AddRect(-4, -4, 4, 4, V(3 + H, H), East,
                          new HeadingScheduleController((0.0, East), (1.0 / 6.0, West), (0.5, East), (1.0, North), (7.0 / 6.0, West)));
                b.AddIdle(IdleCorners[1]);
                return b.Build();
            }, 2.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                List<SimEvent> returns = log.Of(SimEventType.Return, 0);
                Assert.AreEqual(2, log.Count(SimEventType.Exit, 0), at + "two exits");
                Assert.AreEqual(2, returns.Count, at + "a Return event for each exit, the empty one included");
                Assert.That(returns[0].Time, Is.EqualTo((1.0 + H) / 6.0).Within(1e-9), at + "the poke returns at x = 4");
                Assert.AreEqual(0, returns[0].Cells.Length, at + "the poke encloses nothing (C2)");
                Assert.That(returns[1].Time, Is.EqualTo(7.0 / 6.0 + (1 + H) / 6.0).Within(1e-9), at + "the excursion returns at x = 4");
                // Interior: the 8 x 7 cells strictly between the legs and the rectangle. Rim: the 8 cells of each
                // horizontal leg and the 7 of the vertical leg that touch it by a side, plus the two outer corner cells
                // that touch it only by a corner (D1; the 4-adjacency Rim gave 79).
                Assert.AreEqual(8 * 7 + 8 + 7 + 8 + 2, returns[1].Cells.Length, at + "the excursion captures interior + rim");
                Assert.AreEqual(1, sim.Players[0].Captures, at + "D2: only the return with cells counts");
                Assert.IsTrue(sim.Players[0].Home);
            });
        }

        // R5 / GridRaster corner tie: a head crossing exactly through the lattice corner where two own blocks touch
        // diagonally (both side cells neutral) never leaves its color: no exit.
        [Test]
        public void R5_HeadThroughTheExactCornerBetweenTwoDiagonalOwnBlocksDoesNotExit()
        {
            foreach (int rate in AuditRates)
            {
                var b = new SimBuilder(rate);
                b.Add(V(-2, -2), Math.PI / 4.0, new ConstantHeadingController(Math.PI / 4.0), (g, id) =>
                {
                    FillRect(g, id, -4, -4, 0, 0);
                    FillRect(g, id, 0, 0, 4, 4);
                });
                b.AddIdle(IdleCorners[1]);
                Simulation sim = b.Build();
                var log = new EventLog(sim);
                RunUntilTime(sim, 0.6);   // reaches (0.55, 0.55): through the corner (0, 0) at t = 0.4714
                Assert.That(sim.Players[0].Pos.X, Is.GreaterThan(0.3), rate + " Hz: went through the corner");
                Assert.AreEqual(0, log.Count(SimEventType.Exit), rate + " Hz: the corner point is own color on both sides\n" + log.Dump());
                Assert.IsTrue(sim.Players[0].Home);

                // Without the upper block the same path leaves exactly at the corner point, once.
                var b2 = new SimBuilder(rate);
                b2.AddRect(-4, -4, 0, 0, V(-2, -2), Math.PI / 4.0, new ConstantHeadingController(Math.PI / 4.0));
                b2.AddIdle(IdleCorners[1]);
                Simulation sim2 = b2.Build();
                var log2 = new EventLog(sim2);
                RunUntilTime(sim2, 0.6);
                SimEvent exit = log2.Single(SimEventType.Exit, 0);
                Assert.That(exit.Time, Is.EqualTo(2.0 * Math.Sqrt(2.0) / 6.0).Within(1e-9), rate + " Hz: exit at the corner instant");
                AssertNear(V(0, 0), exit.Point, 1e-9, rate + " Hz: exit point = the corner");
                AssertNear(V(0, 0), sim2.Players[0].Trail.Points[0], 1e-9, rate + " Hz: the trail starts at the corner");
                Assert.AreEqual(0, log2.Count(SimEventType.Return), rate + " Hz: no flicker return");
            }
        }

        // R12 / R17: a lasso appends X as a normal point (no shortcut, no extra length), so a catch right after a lasso in
        // the same chase still follows t_c = t_cut + gap / 4.8 exactly.
        [Test]
        public void R13_CatchRightAfterALassoFollowsTheUnchangedArcLength()
        {
            const double tCut = 20.0 / 6.0, tCatch = 3.51;
            CrossRateAll("catch after lasso", rate =>
            {
                Simulation sim = PocketScenario(rate, true, out _, out _, false);
                long cutTick = (long)Math.Round(tCut * rate);
                sim.BeforeTick += s =>
                {
                    if (s.Tick == cutTick) s.DebugForceCut(0, s.Players[0].Trail.Length - Closing * (tCatch - tCut), 1);
                };
                return sim;
            }, 4.0, (rate, sim, log) =>
            {
                string at = rate + " Hz: ";
                SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
                SimEvent caught = log.Single(SimEventType.SparkCaught, 0);
                Assert.That(pocket.Time, Is.EqualTo(3.5).Within(1e-9), at + "lasso during the chase");
                Assert.That(caught.Time, Is.EqualTo(tCatch + Eps).Within(1e-9), at + "catch time unchanged by the lasso");
                Assert.That(log.IndexOf(pocket), Is.LessThan(log.IndexOf(caught)), at + "pocket then catch");
                Assert.AreEqual(0, sim.Players[0].Pocket.Count, at + "the pocket vanished with the elimination");
            });
        }

        // R5 / R7 diagonal edge, contract 23.2 D1 (this test was R7_GlidingAlongAnOwnDiagonalEdgeFlickersHarmlessly).
        // Before D1 the Rim of section 7 step 5 was 4-adjacent: a 45-degree trail leg is rastered as a staircase of two
        // cell diagonals, the outer one touches the Interior only at cell corners, so every capture left one neutral notch
        // per cell along a diagonal edge. A home head gliding along that edge then made an empty Exit / Return pair at
        // every notch, about 34 Hz (the old version of this test, on a hand-painted notched edge, counted 67 pairs in 2 s,
        // each one a Captures++ and a CaptureSolver call). With the 8-adjacency Rim the capture contains the whole
        // staircase, so gliding along a diagonal edge the player really captured stays on own cells: no Exit, no Return.
        // Non-vacuity: the same glide over the same territory with the D1 cells set back to neutral (exactly what the
        // 4-adjacency Rim produced) still flickers, and with D2 those empty Returns leave Captures unchanged.

        /// <summary>
        /// 60 Hz, instant turns. Player 0 owns [-12, 0] x [-6, 8] and starts at (-3, -3 + H) heading North-East on the
        /// line y = x + H (half a cell off the lattice diagonals, no corner tie). Trip 1: exit at (0, H), tip at t = 2.0,
        /// South 9 u, West, return at x = 0 (t about 4.41): the capture has a 45-degree edge on y = x + H. Trip 2: West
        /// until 28/6 s, North 2 u, then North-East from (-1.51, -1.45), on the same line again (the leg sums keep
        /// y - x = H): through the exit junction and along the captured diagonal edge; at t = 6.5 the head is at x = 4.85,
        /// 0.6 u short of the tip.
        /// </summary>
        private static Simulation BuildDiagonalGlide(Action<Simulation> beforeTick)
        {
            const double NorthEast = Math.PI / 4.0;
            var b = new SimBuilder(60);
            b.Add(V(-3, -3 + H), NorthEast,
                  new HeadingScheduleController((0.0, NorthEast), (2.0, South), (3.5, West), (28.0 / 6.0, North), (5.0, NorthEast)),
                  (g, id) => FillRect(g, id, -12, -6, 0, 8));
            b.AddIdle(IdleCorners[1]);
            Simulation sim = b.Build();
            if (beforeTick != null) sim.BeforeTick += beforeTick;
            return sim;
        }

        private const double GlideStart = 5.0, GlideEnd = 6.5;

        [Test]
        public void R7_GlidingAlongAnOwnCapturedDiagonalEdgeNoLongerFlickers()
        {
            // D1 run. The trail is copied at the start of every tick, so the outline of the return (trail + crossing
            // point, as EventResolver.ComputeCapture builds it) can be rebuilt afterwards.
            List<Vec2d> lastTrail = null;
            Simulation sim = BuildDiagonalGlide(s =>
            {
                if (!s.Players[0].Home) lastTrail = new List<Vec2d>(s.Players[0].Trail.Points);
            });
            var log = new EventLog(sim);
            RunUntilTime(sim, GlideStart);
            SimEvent exit = log.Single(SimEventType.Exit, 0);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            AssertNear(V(0, H), exit.Point, 1e-9, "trip 1 exits at the junction");
            Assert.That(ret.Cells.Length, Is.GreaterThan(1500), "trip 1 captures the region between trail and rectangle");
            Assert.IsTrue(sim.Players[0].Home);
            int territory = sim.Grid.CountOf(1);

            // The D1 cells of that capture: trail cells captured as Rim with no 4-neighbour in the Interior.
            var outline = new List<Vec2d>(lastTrail);
            if (Vec2d.Distance(outline[outline.Count - 1], ret.Point) >= 1e-9) outline.Add(ret.Point);
            var trailCells = new CellMask(sim.Grid.Size);
            GridRaster.RasterPolyline(sim.Grid, LoopErase.Erase(outline), trailCells);
            var captured = new HashSet<int>(ret.Cells);
            int size = sim.Grid.Size;
            var d1Cells = new List<int>();
            foreach (int idx in ret.Cells)
            {
                if (!trailCells.Get(idx)) continue;
                bool touches4 = false;
                foreach (int nb in new[] { idx - 1, idx + 1, idx - size, idx + size })
                    touches4 |= captured.Contains(nb) && !trailCells.Get(nb);
                if (!touches4) d1Cells.Add(idx);
            }
            Assert.That(d1Cells.Count, Is.GreaterThan(30), "the outer staircase diagonal of the 45-degree leg");
            foreach (int idx in d1Cells) Assert.AreEqual(1, sim.Grid.Cells[idx], "D1: the stair cell " + idx + " is captured");

            // The glide along the captured diagonal edge: no Exit, no Return, territory unchanged.
            int eventsBefore = log.All.Count;
            RunUntilTime(sim, GlideEnd, true, s => Assert.AreEqual(territory, s.Grid.CountOf(1), "territory unchanged during the glide"));
            Assert.That(sim.Players[0].Pos.X, Is.InRange(4.8, 4.9), "glided 6.4 u along the edge, short of the tip");
            Assert.That(sim.Players[0].Pos.Y - sim.Players[0].Pos.X, Is.EqualTo(H).Within(1e-9), "on the line of the captured leg");
            Assert.AreEqual(eventsBefore, log.All.Count, "no event during the glide:\n" + log.Dump());
            Assert.IsTrue(sim.Players[0].Home);
            Assert.AreEqual(1, sim.Players[0].Captures);

            // Legacy replay: the same run with the D1 cells set back to neutral just before the glide (the territory of
            // the former 4-adjacency Rim). The glide crosses those notches: empty Exit / Return pairs, harmless.
            Simulation legacy = BuildDiagonalGlide(s =>
            {
                if (s.Tick == (long)Math.Round(GlideStart * 60))
                    foreach (int idx in d1Cells) s.Grid.Set(idx, OwnerGrid.Neutral);
            });
            var legacyLog = new EventLog(legacy);
            RunUntilTime(legacy, GlideStart + 1e-3);
            int legacyTerritory = legacy.Grid.CountOf(1);
            Assert.AreEqual(territory - d1Cells.Count, legacyTerritory, "the notched territory of the 4-adjacency Rim");
            int legacyEventsBefore = legacyLog.All.Count;
            RunUntilTime(legacy, GlideEnd);
            int flickers = 0;
            for (int k = legacyEventsBefore; k < legacyLog.All.Count; k++)
            {
                SimEvent e = legacyLog.All[k];
                if (e.Type != SimEventType.Return) continue;
                flickers++;
                Assert.AreEqual(0, e.Cells.Length, "a notch flicker captures nothing");
            }
            TestContext.WriteLine("diagonal glide over a captured 45-degree edge: 0 Exit/Return pairs with the 8-adjacency Rim (D1), "
                                  + flickers + " pairs in " + (GlideEnd - GlideStart) + " s over the same edge notched as the "
                                  + "4-adjacency Rim left it (" + d1Cells.Count + " notch cells)");
            Assert.That(flickers, Is.GreaterThan(20), "the glide does cross the legacy notches (one pair per cell column)");
            Assert.AreEqual(legacyTerritory, legacy.Grid.CountOf(1), "flickers change no owner");
            Assert.AreEqual(1, legacy.Players[0].Captures, "D2: empty Returns do not count as captures");
            Assert.AreEqual(0, legacyLog.Count(SimEventType.Cut), "never exposed");
        }

        // ------------------------------------------------------------------------------------------------------------
        // Property fuzz (determinism, invariants, counters, ranking): random roaming players with real turn rates, rings
        // and lassos, many cuts, chases, captures of rival land and eliminations. 60 Hz only (scripted with SimView).

        /// <summary>Deterministic roaming controller: wanders out, curls when charged, heads home, reacts to its spark.</summary>
        private sealed class RoamController : IController
        {
            private readonly Rng rng;
            private int mode;              // 0 home, 1 out, 2 going home, 3 curl
            private double until, nextTurn, heading = double.NaN;

            public RoamController(ulong seed)
            {
                rng = new Rng(seed);
            }

            public double? DesiredHeading(SimView view, int index)
            {
                PlayerState me = view.Player(index);
                double t = view.Time;
                if (double.IsNaN(heading)) heading = me.Heading;
                if (me.Home && mode != 0 && mode != 1)
                {
                    mode = 0;
                    until = t + rng.Range(0.2, 1.0);
                }
                switch (mode)
                {
                    case 0:
                        if (t >= until)
                        {
                            mode = 1;
                            heading = rng.Range(-Math.PI, Math.PI);
                            until = t + rng.Range(1.0, 3.5);
                            nextTurn = t + rng.Range(0.3, 1.0);
                            if (rng.NextDouble() < 0.25)
                            {
                                // A wall run: straight out to the border (R4 hold / slide while trailing).
                                heading = me.Pos.Angle();
                                until = t + 6.0;
                                nextTurn = until;
                            }
                        }
                        break;
                    case 1:
                        if (t >= nextTurn)
                        {
                            heading += rng.Range(-1.6, 1.6);
                            nextTurn = t + rng.Range(0.3, 1.0);
                            if (me.Charged && !me.Home && rng.NextDouble() < 0.4)
                            {
                                mode = 3;
                                until = t + rng.Range(0.6, 1.2);
                            }
                        }
                        if (mode == 1 && !me.Home && (t >= until || (me.Spark != null && rng.NextDouble() < 0.1))) mode = 2;
                        break;
                    case 3:
                        heading = me.Heading + 2.5;
                        if (t >= until) mode = 2;
                        break;
                }
                if ((mode == 0 || mode == 1) && !me.Charged && view.Ring != null && Vec2d.Distance(view.Ring.Pos, me.Pos) < 12.0)
                {
                    // Go for a nearby ring (exercises R15 contests and charged lassos).
                    if (mode == 0)
                    {
                        mode = 1;
                        until = t + 3.0;
                        nextTurn = t + 1.0;
                    }
                    heading = (view.Ring.Pos - me.Pos).Angle();
                }
                if (mode == 2 && GridQueries.NearestOwned(view.Grid, me.Id, me.Pos, 100.0, out Vec2d target, out _))
                    heading = (target - me.Pos).Angle();
                // Near the wall: turn back toward the center (the head still reaches the wall and holds or slides).
                if (view.Arena.SignedDistance(me.Pos) > -0.6) heading = (-me.Pos).Angle();
                return heading;
            }
        }

        private static Simulation BuildRoam(ulong seed, double duration)
        {
            var cfg = new SimConfig
            {
                Seed = seed, RoundDuration = duration, LassoFirstSpawn = 2.0, LassoRespawn = 3.0, LassoEnabled = true,
            };
            var ctrls = new IController[4];
            var starts = new Vec2d[4];
            for (int i = 0; i < 4; i++)
            {
                ctrls[i] = new RoamController(seed * 1000 + (ulong)i);
                starts[i] = V((i == 0 || i == 3) ? -6 : 6, i < 2 ? -6 : 6);
            }
            var setup = new SimSetup { PlayerCount = 4, StartPositions = starts, HumanIndex = -1 };
            return new Simulation(cfg, ctrls, setup);
        }

        /// <summary>Invariants beyond SimTestKit.AssertInvariants, checked after every tick of the fuzz.</summary>
        private static void AssertDeepInvariants(Simulation sim, double tickStart)
        {
            OwnerGrid g = sim.Grid;
            for (int i = 0; i < sim.Players.Count; i++)
            {
                PlayerState p = sim.Players[i];
                string who = "t=" + sim.Time + " player " + i + ": ";
                if (p.Alive)
                {
                    // R5: the current cell is the cell of the head (a head on an edge may belong to either side).
                    int ci = p.Cell % g.Size, cj = p.Cell / g.Size;
                    double x0 = g.Origin + ci * g.CellSize, y0 = g.Origin + cj * g.CellSize;
                    Assert.That(p.Pos.X, Is.InRange(x0 - 1e-9, x0 + g.CellSize + 1e-9), who + "Pos inside Cell (x)");
                    Assert.That(p.Pos.Y, Is.InRange(y0 - 1e-9, y0 + g.CellSize + 1e-9), who + "Pos inside Cell (y)");
                    Assert.That(sim.Arena.SignedDistance(p.Pos), Is.LessThanOrEqualTo(-sim.Config.ArenaMargin + 1e-9), who + "R1 inset");
                    if (p.Spark != null)
                    {
                        Assert.IsFalse(p.Home, who + "a spark only exists while trailing");
                        Assert.That(p.Spark.S, Is.GreaterThanOrEqualTo(p.Spark.SCut - 1e-9), who + "spark never goes back");
                        Assert.That(p.Spark.PrevS, Is.LessThanOrEqualTo(p.Spark.S + 1e-12), who + "PrevS <= S");
                        if (!sim.Ended)
                            Assert.That(p.Spark.S, Is.EqualTo(p.Spark.SCut + SparkSpeed * (sim.Time - p.Spark.TimeCut)).Within(1e-9),
                                        who + "R12 closed form");
                    }
                    if (p.Home) Assert.AreEqual(0, p.Pocket.Count, who + "no pending pocket at home");
                }
                else
                {
                    Assert.IsTrue(p.Trail.IsEmpty && p.Spark == null && p.Pocket.Count == 0 && !p.Charged, who + "dead player is clean");
                    Assert.AreEqual(0, g.CountOf(p.Id), who + "dead player owns nothing");
                    Assert.IsFalse(double.IsNaN(p.EliminatedAt), who + "EliminatedAt set");
                }
            }
            double prev = double.NegativeInfinity;
            foreach (SimEvent e in sim.LastEvents)
            {
                if (e.Type == SimEventType.RingSpawned) continue;   // stamped with the end-of-tick time
                Assert.That(e.Time, Is.InRange(tickStart - 1e-12, tickStart + sim.Config.Dt + 1e-12), "event time inside its tick: " + e);
                Assert.That(e.Time, Is.GreaterThanOrEqualTo(prev), "events in resolution (time) order: " + e);
                prev = e.Time;
                if (e.Type == SimEventType.Return || e.Type == SimEventType.Eliminated || e.Type == SimEventType.LassoPocket)
                {
                    for (int k = 1; k < e.Cells.Length; k++) Assert.That(e.Cells[k], Is.GreaterThan(e.Cells[k - 1]), "ascending distinct cells: " + e);
                }
                // Contract 24 (R13 v1.4): a chased return is saved but never captures.
                if (e.Type == SimEventType.Return && e.Chased) Assert.AreEqual(0, e.Cells.Length, "a chased return captures nothing: " + e);
            }
        }

        /// <summary>R19 ranking rebuilt from FinalCells and EliminatedAt (competition ranking).</summary>
        private static int[] ExpectedRanks(Simulation sim)
        {
            int n = sim.Players.Count;
            var ranks = new int[n];
            for (int i = 0; i < n; i++)
            {
                PlayerState p = sim.Players[i];
                int above = 0;
                for (int j = 0; j < n; j++)
                {
                    if (j == i) continue;
                    PlayerState q = sim.Players[j];
                    if (p.Alive) above += q.Alive && q.FinalCells > p.FinalCells ? 1 : 0;
                    else above += q.Alive || q.EliminatedAt > p.EliminatedAt ? 1 : 0;
                }
                ranks[i] = 1 + above;
            }
            return ranks;
        }

        [Test]
        public void Determinism_RoamingFuzzKeepsEveryInvariantAndCounterAndRanksFollowR19()
        {
            var totals = new Dictionary<SimEventType, int>();
            foreach (SimEventType t in Enum.GetValues(typeof(SimEventType))) totals[t] = 0;
            int chasedReturns = 0, wallTicks = 0;
            // Same 6 seeds in dotnet and in Unity: the non-vacuity floors at the end of this test are calibrated on these 6
            // rounds (2 seeds gave only 5 cuts, under the "> 5" floor). The 6 rounds take about 10 s in the Editor.
            const ulong seeds = 6;
            for (ulong seed = 1; seed <= seeds; seed++)
            {
                Simulation sim = BuildRoam(seed, 40.0);
                Simulation twin = seed == 1 ? BuildRoam(seed, 40.0) : null;
                var log = new EventLog(sim);
                while (!sim.Ended)
                {
                    double t0 = sim.Time;
                    sim.Step();
                    AssertInvariants(sim);
                    AssertDeepInvariants(sim, t0);
                    for (int i = 0; i < 4; i++)
                    {
                        PlayerState p = sim.Players[i];
                        if (p.Alive && !p.Home && sim.Arena.SignedDistance(p.Pos) > -sim.Config.ArenaMargin - 0.11) wallTicks++;
                    }
                    if (twin != null)
                    {
                        twin.Step();
                        Assert.AreEqual(sim.StateHash(), twin.StateHash(), "same seed, same hash at tick " + sim.Tick);
                    }
                }
                string ctx = "seed " + seed + ": ";
                foreach (SimEvent e in log.All)
                {
                    totals[e.Type]++;
                    if (e.Type == SimEventType.Return && e.Chased) chasedReturns++;
                }
                for (int i = 0; i < 4; i++)
                {
                    PlayerState p = sim.Players[i];
                    // Contract 23.2 D2: Captures counts the Return events that applied at least one cell.
                    int capturingReturns = 0;
                    foreach (SimEvent e in log.Of(SimEventType.Return, i)) capturingReturns += e.Cells.Length > 0 ? 1 : 0;
                    Assert.AreEqual(capturingReturns, p.Captures, ctx + "Captures == Return events with cells, player " + i);
                    Assert.AreEqual(log.Count(SimEventType.LassoPocket, i), p.PocketsMade, ctx + "PocketsMade, player " + i);
                    int cuts = 0, kills = 0;
                    foreach (SimEvent e in log.All)
                    {
                        if (e.Type == SimEventType.Cut && e.Other == i) cuts++;
                        if (e.Type == SimEventType.SparkCaught && e.Other == i) kills++;
                    }
                    Assert.AreEqual(cuts, p.CutsMade, ctx + "CutsMade, player " + i);
                    Assert.AreEqual(kills, p.Kills, ctx + "Kills, player " + i);
                    // Exit and Return alternate; an elimination closes an open exit; at the end the exit is open iff
                    // the player is alive and trailing.
                    int open = 0;
                    foreach (SimEvent e in log.All)
                    {
                        if (e.Player != i) continue;
                        if (e.Type == SimEventType.Exit) open++;
                        else if (e.Type == SimEventType.Return) open--;
                        else if (e.Type == SimEventType.Eliminated) open = 0;
                        Assert.That(open, Is.InRange(0, 1), ctx + "Exit / Return alternate, player " + i + " at " + e);
                    }
                    Assert.AreEqual(p.Alive && !p.Home ? 1 : 0, open, ctx + "open exit iff trailing, player " + i);
                    Assert.AreEqual(sim.Result.FinalCells[i], p.FinalCells, ctx + "Result.FinalCells");
                    Assert.AreEqual(sim.Result.Ranks[i], sim.RankOf(i), ctx + "RankOf == Result.Ranks");
                }
                Assert.AreEqual(ExpectedRanks(sim), sim.Result.Ranks, ctx + "R19 ranking from FinalCells and EliminatedAt");
                Assert.AreEqual(log.Count(SimEventType.RoundEnded), 1, ctx + "one RoundEnded");
                // R1: heads stay ArenaMargin inside the rim, so no trail cell, capture or pocket ever reaches the outer
                // band (cell centers within 0.45 - half a cell diagonal of the rim stay neutral forever).
                OwnerGrid g = sim.Grid;
                double band = -(sim.Config.ArenaMargin - 0.5 * Math.Sqrt(2.0) * g.CellSize);
                for (int j = 0; j < g.Size; j++)
                    for (int ii = 0; ii < g.Size; ii++)
                    {
                        byte owner = g.Cells[g.Index(ii, j)];
                        if (owner == OwnerGrid.Neutral || owner == OwnerGrid.Void) continue;
                        Assert.That(sim.Arena.SignedDistance(g.CellCenter(ii, j)), Is.LessThanOrEqualTo(band),
                                    ctx + "R1: owned cell in the rim band at (" + ii + ", " + j + ")");
                    }
            }
            string summary = "";
            foreach (KeyValuePair<SimEventType, int> kv in totals) summary += kv.Key + "=" + kv.Value + " ";
            TestContext.WriteLine("roaming fuzz totals: " + summary + "chasedReturns=" + chasedReturns + " wallTicks=" + wallTicks);
            // Non-vacuous: the sample must exercise the rules it claims to check.
            Assert.That(totals[SimEventType.Return], Is.GreaterThan(60), summary);
            Assert.That(totals[SimEventType.Cut], Is.GreaterThan(5), summary);
            Assert.That(totals[SimEventType.SparkCaught], Is.GreaterThan(0), summary);
            Assert.That(chasedReturns, Is.GreaterThan(0), "a chased return (saved) " + summary);
            Assert.That(totals[SimEventType.LassoPocket], Is.GreaterThan(0), summary);
            Assert.That(totals[SimEventType.RingPicked], Is.GreaterThan(2), summary);
            Assert.That(wallTicks, Is.GreaterThan(0), "some trailing head reached the wall (R1 / R4 coverage)");
        }
    }
}
