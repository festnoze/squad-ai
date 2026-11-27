// Owned by kill-core (wave D-2). docs/BIOME_TRAITS.md section 7: KillShield (behaviour trait, kill reward), P1 = Duration
// (3.0 s). Its timing is exact (the shield end is a section 6 event candidate): cross-rate equality required.
using System;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class KillShieldTraitTests
    {
        /// <summary>The victim's catch time (the kill): not a tick time at 30, 60 or 144 Hz.</summary>
        private const double KillTime = 1.013;

        /// <summary>
        /// Victim (player 0): land far away, teleported at t = 0 to a trail East on y = -15 + H with a spark of the killer that
        /// catches it at KillTime. Killer (player 1): owns [-10, -2] x [-4, 4] and follows 'killer' from (-3 + H, H) heading
        /// East (exit at x = -2, t = 0.15625). Enemy (player 2): heads North on x = enemyX from a land below, so that its head
        /// comes within ContactRadius of the line y = H at t = contactTime. Player 3 idles.
        /// </summary>
        private static Simulation Build(int rate, RuleTraits traits, IController killer, double contactTime, double enemyX)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddRect(-10, -4, -2, 4, V(-3 + H, H), East, killer);
            double y0 = H - 0.63 - 6.0 * contactTime;
            sb.AddRect(enemyX - 2.0625, y0 - 2.0, enemyX + 1.9375, y0 + 0.75, V(enemyX, y0), North, new ConstantHeadingController(North));
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, KillTime);
            return sim;
        }

        /// <summary>The killer trails East on y = H; the enemy crosses its trail at x = 5 + H (s = 7.0625) at contactTime.</summary>
        private static Simulation Crossing(int rate, RuleTraits traits, double contactTime)
        {
            return Build(rate, traits, new ConstantHeadingController(East), contactTime, 5 + H);
        }

        [Test]
        public void KillShield_ShieldBlocksCutsEndsExactlyAndAHeadOverTheTrailCutsAtThatInstant()
        {
            // The enemy is in contact with the killer's trail from t = 3.95 to 4.16; the shield (kill at KillTime + eps) ends
            // at 4.0130001, inside that contact: the cut happens at exactly the shield end (7.1), at s = 7.0625.
            TraitTestKit.CrossRate("KillShield timing", rate => Crossing(rate, TraitTestKit.One(TraitId.KillShield), 3.95), 4.3, run =>
            {
                string at = run.Rate + " Hz: ";
                SimEvent started = run.Log.Single(SimEventType.ShieldStarted, 1);
                SimEvent ended = run.Log.Single(SimEventType.ShieldEnded, 1);
                SimEvent cut = run.Log.Single(SimEventType.Cut, 1);
                Assert.That(started.Time, Is.EqualTo(KillTime).Within(1e-6), at + "shield at the kill");
                Assert.AreEqual(0, started.Other);
                Assert.IsFalse(started.Chased, at + "no spark to extinguish");
                Assert.That(started.Value, Is.EqualTo(started.Time + 3.0).Within(1e-12), at + "end = t_kill + Duration");
                Assert.That(ended.Time, Is.EqualTo(started.Value).Within(1e-9), at + "ShieldEnded at the exact end time");
                Assert.AreEqual(started.Value, ended.Value);
                Assert.That(cut.Time, Is.EqualTo(ended.Time).Within(1e-9), at + "the head already over the trail cuts at the shield end");
                Assert.That(run.Log.IndexOf(cut), Is.GreaterThan(run.Log.IndexOf(ended)), at + "the cut comes after the end");
                Assert.AreEqual(2, cut.Other);
                Assert.That(cut.S, Is.EqualTo(7 + H).Within(1e-9), at + "closest exposed point");
                Assert.IsTrue(run.Sim.Players[1].ExitWasCut);
                Assert.IsFalse(run.Sim.View.IsShielded(1));
            });

            // Control: without the trait the cut happens when the contact starts.
            Simulation classic = Crossing(60, RuleTraits.Classic, 3.95);
            var log = new EventLog(classic);
            RunUntilTime(classic, 4.3);
            Assert.That(log.Single(SimEventType.Cut, 1).Time, Is.EqualTo(3.95).Within(1e-6), "classic: cut at the contact start");

            // A longer shield (until 6.013) outlasts the whole contact: no cut at all.
            Simulation longer = Crossing(60, TraitTestKit.One(TraitId.KillShield, 5.0), 3.95);
            var longLog = new EventLog(longer);
            RunUntilTime(longer, 4.3);
            Assert.AreEqual(0, longLog.Count(SimEventType.Cut), "the enemy crossed a shielded trail");
            Assert.IsTrue(longer.View.IsShielded(1));
        }

        [Test]
        public void KillShield_SimViewExposesTheShieldAndForcedCutsAreRefused()
        {
            Simulation sim = Crossing(60, TraitTestKit.One(TraitId.KillShield), 3.95);
            Assert.IsFalse(sim.View.IsShielded(1));
            Assert.AreEqual(double.NegativeInfinity, sim.View.ShieldEndTime(1));
            RunUntilTime(sim, 2.0);
            Assert.IsTrue(sim.View.IsShielded(1));
            Assert.IsTrue(sim.Players[1].Shielded);
            Assert.That(sim.View.ShieldEndTime(1), Is.EqualTo(KillTime + 3.0).Within(1e-6));
            sim.DebugForceCut(1, 1.0, 2);
            Assert.IsNull(sim.Players[1].Spark, "DebugForceCut is refused on a shielded trail");
            Assert.IsFalse(sim.Players[1].ExitWasCut);
            RunUntilTime(sim, 4.02);
            Assert.IsFalse(sim.View.IsShielded(1));
            Assert.AreEqual(double.NegativeInfinity, sim.View.ShieldEndTime(1));
        }

        [Test]
        public void KillShield_ACutComputedForTheSameInstantAsTheKillIsDropped()
        {
            // The enemy touches the killer's trail (x = 1 + H) 0.5 eps before the kill instant: both land in one group. Step
            // b gives the shield, so step c re-validates the cut and drops it; no cut follows while the shield lasts.
            double contact = KillTime + 0.5 * Tuning.EventEpsilonSeconds;
            TraitTestKit.CrossRate("same-instant cut", rate => Build(rate, TraitTestKit.One(TraitId.KillShield),
                                                                     new ConstantHeadingController(East), contact, 1 + H), 1.5, run =>
            {
                string at = run.Rate + " Hz: ";
                Assert.AreEqual(1, run.Log.Count(SimEventType.ShieldStarted, 1), at + "shielded");
                Assert.AreEqual(0, run.Log.Count(SimEventType.Cut), at + "the same-instant cut is dropped\n" + run.Log.Dump());
                Assert.IsNull(run.Sim.Players[1].Spark);
            });

            Simulation classic = Build(60, RuleTraits.Classic, new ConstantHeadingController(East), contact, 1 + H);
            var log = new EventLog(classic);
            RunUntilTime(classic, 1.5);
            Assert.That(log.Single(SimEventType.Cut, 1).Time, Is.EqualTo(contact).Within(1e-6), "classic: the cut applies");
        }

        /// <summary>
        /// The killer exits East, goes North 2 at x = 3 + H, then West: it returns home at x = -2 at t = 4/3 + 5.0625 / 6.
        /// It is cut at t = 5/6 by player 3 (its spark would catch it at about 1.5755 s, before that return). The enemy
        /// heads North on x = 20 + H, far from the killer's path.
        /// </summary>
        private static Simulation ChasedKiller(int rate, RuleTraits traits)
        {
            Simulation sim = Build(rate, traits, Legs((East, 6), (North, 2), (West, 20)), 3.5, 20 + H);
            sim.BeforeTick += s =>
            {
                if (s.Tick == (long)Math.Round(5.0 / 6.0 * s.Config.TickRate)) s.DebugForceCut(1, 0.5, 3);
            };
            return sim;
        }

        private const double ChasedReturnTime = 4.0 / 3.0 + (3 + H + 2.0) / 6.0;

        [Test]
        public void KillShield_AChasedKillerLosesItsSparkSurvivesAndItsLoopStaysLost()
        {
            TraitTestKit.CrossRate("chased killer", rate => ChasedKiller(rate, TraitTestKit.One(TraitId.KillShield)), 2.3, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent started = run.Log.Single(SimEventType.ShieldStarted, 1);
                Assert.IsTrue(started.Chased, at + "the spark on the killer's trail was extinguished");
                Assert.AreEqual(0, run.Log.Count(SimEventType.SparkCaught, 1), at + "the killer survives");
                SimEvent ret = run.Log.Single(SimEventType.Return, 1);
                Assert.That(ret.Time, Is.EqualTo(ChasedReturnTime).Within(1e-6), at + "return");
                Assert.IsTrue(ret.Chased, at + "ExitWasCut: the loop stays lost");
                Assert.AreEqual(0, ret.Cells.Length, at + "captures nothing");
                Assert.AreEqual(0.0, ret.Margin, at + "no spark at the return");
                Assert.IsTrue(sim.Players[1].Alive && sim.Players[1].Home);
                Assert.IsFalse(sim.Players[1].ExitWasCut, at + "cleared at the return");
                Assert.AreEqual(1, sim.Players[3].CutsMade);
                Assert.AreEqual(1, sim.Players[1].Kills);
            });

            Simulation classic = ChasedKiller(60, RuleTraits.Classic);
            var log = new EventLog(classic);
            RunUntilTime(classic, 2.3);
            Assert.That(log.Single(SimEventType.SparkCaught, 1).Time, Is.EqualTo(5.0 / 6.0 + 3.5625 / 4.8).Within(1e-6),
                        "classic: the killer is caught before its return");

            Simulation zero = ChasedKiller(60, TraitTestKit.One(TraitId.KillShield, 0.0));
            var zeroLog = new EventLog(zero);
            RunUntilTime(zero, 2.3);
            Assert.AreEqual(0, zeroLog.Count(SimEventType.ShieldStarted), "Duration 0: no shield");
            Assert.AreEqual(1, zeroLog.Count(SimEventType.SparkCaught, 1), "Duration 0: nothing extinguished");
        }

        [Test]
        public void KillShield_AfterTheShieldACutExitCanBeCutAgain()
        {
            // The chased killer of the previous test, still trailing East (it never turns home here): its spark is
            // extinguished at the kill, and the enemy, already over its trail when the shield ends, cuts again: a new spark
            // (section 6 candidates need a trailing victim WITHOUT a spark, not an uncut exit).
            Simulation sim = Crossing(60, TraitTestKit.One(TraitId.KillShield), 3.95);
            sim.BeforeTick += s =>
            {
                if (s.Tick == 50) s.DebugForceCut(1, 0.5, 3);
            };
            var log = new EventLog(sim);
            RunUntilTime(sim, 4.1);
            Assert.IsTrue(log.Single(SimEventType.ShieldStarted, 1).Chased);
            Assert.AreEqual(1, log.Count(SimEventType.Cut, 1), "the cut after the shield");
            Assert.IsNotNull(sim.Players[1].Spark, "a new spark");
            Assert.AreEqual(2, sim.Players[1].Spark.Attacker);
            Assert.IsTrue(sim.Players[1].ExitWasCut);
        }

        [Test]
        public void KillShield_ASecondKillExtendsTheShieldAndItEndsOnce()
        {
            var sb = new SimBuilder(60);
            sb.Config.Traits = TraitTestKit.One(TraitId.KillShield);
            sb.AddRect(10, 10, 14, 14, V(12 + H, 12 + H), East, new ConstantHeadingController(East));
            sb.AddRect(-10, -4, -2, 4, V(-6 + H, H), North, new HomeCirclerController(V(-6, 0)));
            sb.AddIdle(IdleCorners[2]);
            sb.AddRect(10, -14, 14, -10, V(12 + H, -12 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[3]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, KillTime);
            KillTestKit.ForceKillAt(sim, 2.0, 3, 1, V(-20 + H, 10 + H));
            var log = new EventLog(sim);
            RunUntilTime(sim, 5.2);
            var started = log.Of(SimEventType.ShieldStarted, 1);
            Assert.AreEqual(2, started.Count);
            Assert.That(started[0].Value, Is.EqualTo(KillTime + 3.0).Within(1e-6));
            Assert.That(started[1].Value, Is.EqualTo(5.0).Within(1e-6), "extended to the second kill + Duration");
            SimEvent ended = log.Single(SimEventType.ShieldEnded, 1);
            Assert.That(ended.Time, Is.EqualTo(started[1].Value).Within(1e-9), "one end, at the extended time");
        }

        [Test]
        public void KillShield_TerritoryLossToZeroCellsStillEliminatesAShieldedPlayer()
        {
            // R9 (contract): A's return at t = 0.349 encloses all of B's land. B killed V at t = 0.1 and is shielded.
            var b = new SimBuilder(60);
            b.Config.Traits = TraitTestKit.One(TraitId.KillShield);
            b.AddRect(-8, -8, 0, 8, V(-4, H), West, new ConstantHeadingController(West));
            int bIdx = b.AddRect(6, -3, 9, 3, V(7 + H, -2.4375), North, new ConstantHeadingController(North));
            int v = b.AddRect(20, -24, 24, -20, V(22 + H, -22 + H), East, new ConstantHeadingController(East));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 6 + H), V(10 + H, 6 + H), V(10 + H, -6 + H), V(2.0925, -6 + H) });
            KillTestKit.ForceKillAt(sim, 0.1, v, bIdx, V(-20 + H, -20 + H));
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.3);
            Assert.IsTrue(sim.View.IsShielded(bIdx), "B is shielded before the capture");
            RunUntilTime(sim, 0.45);
            SimEvent elim = log.Single(SimEventType.Eliminated, bIdx);
            Assert.AreEqual(EliminationCause.TerritoryLost, elim.Cause, "territory loss to 0 cells still eliminates");
            Assert.IsFalse(sim.View.IsShielded(bIdx));
            Assert.IsFalse(sim.Players[bIdx].Shielded, "an elimination ends the shield");
            Assert.AreEqual(0, log.Count(SimEventType.ShieldEnded), "silently");
        }
    }
}
