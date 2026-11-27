// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: ArcReach (config trait), P1 = ContactScale (1.40):
// cut contact radius = (HeadRadius + TrailHalfWidth) x scale. Cross-rate equality required (section 6).
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class ArcReachTraitTests
    {
        // Victim (player 0): home far away, trailing East on y = H from (-10, H) to (0, H). Attacker (player 1): leaves its
        // land heading North on x = -5 + H from y = StartY. With reach R the cut happens when H - y(t) = R:
        // t = (H - StartY - R) / 6 = 0.513 s for R = 0.882 (ArcReach 1.4) and 0.555 s for R = 0.63 (classic).
        private const double StartY = H - 0.882 - 6.0 * 0.513;

        private static Simulation Scene(int rate, RuleTraits traits, IController attacker = null)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-28, 20, -24, 24, V(-26 + H, 22 + H), East, new ConstantHeadingController(East));
            sb.AddRect(-7, -6, -3, -3.5, V(-5 + H, StartY), North, attacker ?? new ConstantHeadingController(North));
            Simulation sim = sb.Build();
            sim.DebugSetTrail(0, new[] { V(-10, H), V(0, H) });
            return sim;
        }

        [Test]
        public void ArcReach_ScalesTheContactRadius()
        {
            Simulation sim = Scene(60, TraitTestKit.One(TraitId.ArcReach));
            Assert.AreEqual(1.4, sim.Config.ContactScale);
            Assert.AreEqual(0.63 * 1.4, sim.Config.ContactRadius, 1e-12);
            Assert.AreEqual(0.63 * 1.1, Scene(60, TraitTestKit.One(TraitId.ArcReach, 1.1)).Config.ContactRadius, 1e-12);
            Assert.AreEqual(0.63, Scene(60, RuleTraits.Classic).Config.ContactRadius, 1e-12);
        }

        [TestCase(true, 0.513)]
        [TestCase(false, 0.555)]
        public void ArcReach_CutsAtTheLargerDistanceAtEveryRate(bool reach, double cutTime)
        {
            RuleTraits traits = reach ? TraitTestKit.One(TraitId.ArcReach) : RuleTraits.Classic;
            TraitTestKit.CrossRate("ArcReach " + reach, rate => Scene(rate, traits), 1.0, run =>
            {
                SimEvent cut = run.Log.Single(SimEventType.Cut, 0);
                Assert.AreEqual(1, cut.Other, "the attacker");
                Assert.That(cut.Time, Is.EqualTo(cutTime).Within(1e-6), run.Rate + " Hz cut time");
                Assert.That(cut.S, Is.EqualTo(10.0 - 5.0 + H).Within(1e-9), "s_cut = the closest exposed point (foot of the perpendicular)");
                Assert.IsNotNull(run.Sim.Players[0].Spark);
            });
        }

        [Test]
        public void ArcReach_AHeadThatStopsBetweenTheTwoRadiiCutsOnlyWithTheTrait()
        {
            // The attacker turns back when its head is 0.75 u from the trail (0.63 < 0.75 < 0.882), at t = 0.535 s.
            double turn = (H - 0.75 - StartY) / 6.0;
            Simulation with = Scene(60, TraitTestKit.One(TraitId.ArcReach), new HeadingScheduleController((0.0, North), (turn, South)));
            Simulation without = Scene(60, RuleTraits.Classic, new HeadingScheduleController((0.0, North), (turn, South)));
            var logWith = new EventLog(with);
            var logWithout = new EventLog(without);
            RunUntilTime(with, 1.5);
            RunUntilTime(without, 1.5);
            Assert.AreEqual(1, logWith.Count(SimEventType.Cut, 0), "ArcReach: the head within 0.882 u cuts");
            Assert.AreEqual(0, logWithout.Count(SimEventType.Cut, 0), "classic: 0.75 u is out of reach");
        }
    }
}
