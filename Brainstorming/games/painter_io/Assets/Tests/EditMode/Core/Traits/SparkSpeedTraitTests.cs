// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: SparkSpeed (config trait), P1 = Factor (2.1 or 1.5),
// overrides SparkSpeedFactor. Cross-rate equality required (section 6).
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class SparkSpeedTraitTests
    {
        // Victim (player 0): home far away, trailing East on y = H from (-10, H) to (0, H) (L = 10), forced cut at t = 0 with
        // a gap G = 10 - sCut chosen so the catch t_c = G / (SparkSpeed - PawnSpeed) = 1.013 s is not a tick time.
        private const double CatchTime = 1.013;

        private static Simulation Chase(int rate, RuleTraits traits, double factor)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            sim.DebugSetTrail(0, new[] { V(-10, H), V(0, H) });
            double gap = CatchTime * (factor - 1.0) * Tuning.PawnSpeed;
            sim.DebugForceCut(0, 10.0 - gap, 1);
            return sim;
        }

        [Test]
        public void SparkSpeed_OverridesTheSparkFactorOnTheBasePawnSpeed()
        {
            Simulation fire = Chase(60, TraitTestKit.One(TraitId.SparkSpeed), 2.1);
            Assert.AreEqual(2.1, fire.Config.SparkSpeedFactor);
            Assert.AreEqual(12.6, fire.Config.SparkSpeed, 1e-12);
            Simulation electric = Chase(60, TraitTestKit.One(TraitId.SparkSpeed, 1.5), 1.5);
            Assert.AreEqual(9.0, electric.Config.SparkSpeed, 1e-12);
            Assert.AreEqual(CatchTime, electric.View.SparkCatchEta(0), 1e-9, "SparkCatchEta uses the trait speed: gap / (9 - 6)");
            Assert.AreEqual(CatchTime, fire.View.SparkCatchEta(0), 1e-9, "gap / (12.6 - 6)");
        }

        [TestCase(2.1)]
        [TestCase(1.5)]
        [TestCase(1.8)]
        public void SparkSpeed_CatchTimeFollowsTheClosedFormAtEveryRate(double factor)
        {
            RuleTraits traits = factor == 1.8 ? RuleTraits.Classic : TraitTestKit.One(TraitId.SparkSpeed, factor);
            TraitTestKit.CrossRate("SparkSpeed " + factor, rate => Chase(rate, traits, factor), 2.0, run =>
            {
                SimEvent caught = run.Log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(CatchTime).Within(1e-6), run.Rate + " Hz catch time");
                Assert.AreEqual(EliminationCause.Spark, run.Sim.Players[0].Cause);
            }, s =>
            {
                // R12 closed form with the trait's spark speed, every tick while the chase lasts.
                PlayerState v = s.Players[0];
                if (v.Spark != null)
                    Assert.That(v.Spark.S, Is.EqualTo(v.Spark.SCut + factor * 6.0 * (s.Time - v.Spark.TimeCut)).Within(1e-9));
            });
        }
    }
}
