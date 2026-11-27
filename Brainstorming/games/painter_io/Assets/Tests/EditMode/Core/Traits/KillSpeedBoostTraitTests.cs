// Owned by kill-core (wave D-2). docs/BIOME_TRAITS.md section 7: KillSpeedBoost (behaviour trait, kill reward), P1 = PerKill
// (0.10), P2 = Cap (0.30). The multiplier applies per whole tick from the tick after the kill: tick-rate dependent by
// design, like Conduction and turning (60 Hz scenarios). The spark rule of 7.1 (the spark follows the victim's speed) is
// checked across rates with a constant multiplier.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class KillSpeedBoostTraitTests
    {
        /// <summary>
        /// Killer (player 0) owns [-20, 0] x [-3, 3] and heads East from (-19 + H, H) (home for about 3 s). Victims 1..4 own
        /// small lands far away and are caught by its spark at t = 0.1, 0.3, 0.5 and 0.7 s. Player 5 idles.
        /// </summary>
        private static Simulation Serial(RuleTraits traits)
        {
            var sb = new SimBuilder(60);
            sb.Config.Traits = traits;
            sb.AddRect(-20, -3, 0, 3, V(-19 + H, H), East, new ConstantHeadingController(East));
            for (int k = 0; k < 4; k++)
                sb.AddRect(-20 + 6 * k, 10, -17 + 6 * k, 13, V(-18.5 + 6 * k, 11.5), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            for (int k = 0; k < 4; k++) KillTestKit.ForceKillAt(sim, 0.1 + 0.2 * k, 1 + k, 0, V(-20 + H + 6 * k, -12 + H));
            return sim;
        }

        [Test]
        public void KillSpeedBoost_EachKillAddsPerKillUpToTheCapFromTheNextTick()
        {
            Simulation sim = Serial(TraitTestKit.One(TraitId.KillSpeedBoost));
            var log = new EventLog(sim);
            PlayerState killer = sim.Players[0];
            for (int k = 0; k < 60; k++)
            {
                double before = killer.SpeedMultiplier;
                sim.Step();
                TraitTestKit.AssertTraitInvariants(sim);
                double moved = Vec2d.Distance(killer.PrevPos, killer.Pos);
                Assert.That(moved, Is.EqualTo(0.1 * before).Within(1e-12), "tick " + k + ": PawnSpeed x the multiplier at tick start");
            }
            List<SimEvent> boosts = log.Of(SimEventType.SpeedBoosted, 0);
            Assert.AreEqual(3, boosts.Count, "three boosts, the fourth kill finds the cap");
            Assert.That(boosts[0].Value, Is.EqualTo(1.1).Within(1e-12));
            Assert.That(boosts[1].Value, Is.EqualTo(1.2).Within(1e-12));
            Assert.That(boosts[2].Value, Is.EqualTo(1.3).Within(1e-12));
            Assert.AreEqual(1.3, killer.SpeedMultiplier, "capped at 1 + Cap");
            Assert.AreEqual(4, killer.Kills);
            for (int k = 0; k < 3; k++)
            {
                Assert.AreEqual(1 + k, boosts[k].Other, "Other = the victim");
                Assert.AreEqual(log.Single(SimEventType.Eliminated, 1 + k).Time, boosts[k].Time, "at the kill instant");
            }
            Assert.AreEqual(1.3, sim.View.SpeedMultiplier(0));
            Assert.AreEqual(1.0, sim.View.SpeedMultiplier(5));
            Assert.AreEqual(6.0 * 1.3, sim.View.EffectiveSpeed(0), 1e-12);
            Assert.AreEqual(0.0, sim.View.EffectiveSpeed(1), "eliminated");
        }

        [Test]
        public void KillSpeedBoost_ParametersAndClassic()
        {
            Simulation big = Serial(TraitTestKit.One(TraitId.KillSpeedBoost, 0.25, 0.4));
            RunUntilTime(big, 1.0);
            Assert.AreEqual(1.4, big.Players[0].SpeedMultiplier, 1e-12, "1.25, then 1.4 (cap)");
            foreach (RuleTraits traits in new[] { RuleTraits.Classic, TraitTestKit.One(TraitId.KillSpeedBoost, 0.0), TraitTestKit.One(TraitId.KillShield) })
            {
                Simulation sim = Serial(traits);
                var log = new EventLog(sim);
                RunUntilTime(sim, 1.0);
                Assert.AreEqual(4, sim.Players[0].Kills, traits + ": the kills happened");
                Assert.AreEqual(1.0, sim.Players[0].SpeedMultiplier, traits + ": no boost");
                Assert.AreEqual(0, log.Count(SimEventType.SpeedBoosted), traits.ToString());
            }
        }

        [Test]
        public void KillSpeedBoost_StacksWithConductionAndTheHeadGraceCheckUsesTheMaximumReachableSpeed()
        {
            Simulation sim = Serial(RuleTraits.Parse("KillSpeedBoost;Conduction"));
            RunUntilTime(sim, 0.2);
            PlayerState killer = sim.Players[0];
            Assert.AreEqual(1.1, killer.SpeedMultiplier, 1e-12);
            sim.Step();
            Assert.That(Vec2d.Distance(killer.PrevPos, killer.Pos), Is.EqualTo(0.1 * 1.1 * 1.3).Within(1e-12), "PawnSpeed x 1.1 x 1.3 at home");
            Assert.AreEqual(6.0 * 1.1 * 1.3, sim.View.EffectiveSpeed(0), 1e-12);

            // 60 Hz: the largest reachable step is 0.1 x (1 + Cap) x Conduction max; HeadGrace 0.15.
            Func<RuleTraits, Simulation> make = traits =>
            {
                var sb = new SimBuilder(60);
                sb.Config.HeadGrace = 0.15;
                sb.Config.Traits = traits;
                sb.AddIdle(IdleCorners[0]);
                sb.AddIdle(IdleCorners[2]);
                return sb.Build();
            };
            Assert.IsNotNull(make(TraitTestKit.One(TraitId.KillSpeedBoost, 0.1, 0.4)), "0.14 < 0.15");
            Assert.IsNotNull(make(RuleTraits.Parse("Conduction(1.3);KillSpeedBoost(0.1,0.1)")), "0.143 < 0.15");
            Assert.Throws<ArgumentException>(() => make(RuleTraits.Parse("Conduction(1.3);KillSpeedBoost(0.1,0.2)")), "0.156 >= 0.15: factors multiply");
            Assert.Throws<ArgumentException>(() => make(TraitTestKit.ElectricV11), "Electricite v1.1: 0.169 >= 0.15");
        }

        /// <summary>
        /// The victim (player 0, multiplier m) trails East from (-10, H) with L = 10 and is cut at t = 0 so that the spark
        /// reaches it 1.013 s later (closed form of 7.1). Player 1 idles (the attacker).
        /// </summary>
        private static Simulation Chase(int rate, double multiplier, bool follows)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = TraitTestKit.One(TraitId.KillSpeedBoost);
            sb.Config.SparkFollowsVictimSpeed = follows;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            sim.Players[0].SpeedMultiplier = multiplier;   // test only: as if boosted by earlier kills
            KillTestKit.ForceChase(sim, 0, 1, V(-10, H), 10.0, 1.013);
            return sim;
        }

        [TestCase(true)]
        [TestCase(false)]
        public void KillSpeedBoost_TheSparkSpeedIsFixedAtTheCutFromTheVictimsMultiplier(bool follows)
        {
            double expected = follows ? 10.8 * 1.2 : 10.8;
            TraitTestKit.CrossRate("spark speed " + follows, rate => Chase(rate, 1.2, follows), 1.2, run =>
            {
                SimEvent caught = run.Log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(1.013).Within(1e-6), run.Rate + " Hz: closed form with Spark.Speed");
            }, s =>
            {
                PlayerState v = s.Players[0];
                if (v.Spark == null) return;
                Assert.AreEqual(expected, v.Spark.Speed, 1e-12, "Spark.Speed");
                Assert.That(v.Spark.S, Is.EqualTo(v.Spark.SCut + expected * (s.Time - v.Spark.TimeCut)).Within(1e-9), "S closed form");
            });
            Simulation sim = Chase(60, 1.2, follows);
            Assert.AreEqual(expected, sim.Players[0].Spark.Speed, 1e-12);
            Assert.AreEqual(1.013, sim.View.SparkCatchEta(0), 1e-9, "SparkCatchEta: gap / (Spark.Speed - PawnSpeed x multiplier)");
            sim.Step();
            Assert.That(Vec2d.Distance(sim.Players[0].PrevPos, sim.Players[0].Pos), Is.EqualTo(0.12).Within(1e-12), "the victim runs at 7.2 u/s");
        }

        [Test]
        public void KillSpeedBoost_ABoostGainedDuringTheChaseLeavesTheRunningSpark()
        {
            // The chased victim (player 0) kills player 2 at t = 0.5: its multiplier becomes 1.1 from the next tick (31 at
            // 60 Hz) while its spark keeps 10.8 u/s. Without the boost the catch is at 1.013 s; with it the victim runs
            // faster from t = 31/60: 10.8 t = 10 + 6 (31/60) + 6.6 (t - 31/60) - sCut, i.e. t = 1.0839 s.
            var sb = new SimBuilder(60);
            sb.Config.Traits = TraitTestKit.One(TraitId.KillSpeedBoost);
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            sb.AddRect(10, 10, 14, 14, V(12 + H, 12 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 0, 1, V(-10, H), 10.0, 1.013);
            KillTestKit.ForceKillAt(sim, 0.5, 2, 0, V(-20 + H, -12 + H));
            var log = new EventLog(sim);
            RunUntilTime(sim, 1.2, true, s =>
            {
                if (s.Players[0].Spark != null) Assert.AreEqual(10.8, s.Players[0].Spark.Speed, 1e-12, "the running spark keeps its speed");
            });
            Assert.AreEqual(1, log.Count(SimEventType.SpeedBoosted, 0));
            double sCut = 10.0 - 1.013 * 4.8;
            double expected = (10.0 + 6.0 * (31.0 / 60.0) - 6.6 * (31.0 / 60.0) - sCut) / (10.8 - 6.6);
            Assert.That(log.Single(SimEventType.SparkCaught, 0).Time, Is.EqualTo(expected).Within(1e-6));
        }

        [Test]
        public void KillSpeedBoost_BotTravelEstimatesUseTheMultiplier()
        {
            var cfg = new SimConfig { Traits = TraitTestKit.One(TraitId.KillSpeedBoost) };
            var sim = new Simulation(cfg, new IController[] { null, null }, new SimSetup { HumanIndex = -1 });
            Vec2d start = sim.Players[0].Pos;
            Vec2d target = start + new Vec2d(6.0 / Math.Sqrt(2.0), 6.0 / Math.Sqrt(2.0));
            Assert.AreEqual(1.0, BotController.InterceptTravelTime(sim.View, 0, target), 1e-12);
            sim.Players[0].SpeedMultiplier = 1.2;
            Assert.AreEqual(1.0 / 1.2, BotController.InterceptTravelTime(sim.View, 0, target), 1e-12, "distance / (PawnSpeed x 1.2)");
        }
    }
}
