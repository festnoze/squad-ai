// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: Inertia (config trait), P1 = TurnRateDeg (420).
// Tick-rate dependent exactly like turning already is (R3 turns by TurnRate x dt per tick): no cross-rate test (section 6).
using System;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class InertiaTraitTests
    {
        private static Simulation Turner(RuleTraits traits, int rate = 60)
        {
            // One player heading East inside its land, steering North; a second idle player far away.
            var sb = new SimBuilder(rate);
            sb.Config.TurnRateDeg = Tuning.TurnRateDeg;   // the real turn rate (SimTestKit defaults to instant turns)
            sb.Config.Traits = traits;
            sb.AddRect(-12, -6, 0, 6, V(-6 + H, H), East, new ConstantHeadingController(North));
            sb.AddIdle(IdleCorners[2]);
            return sb.Build();
        }

        [Test]
        public void Inertia_SetsTheTurnRateOfTheRoundOnly()
        {
            Assert.AreEqual(420.0, Turner(TraitTestKit.One(TraitId.Inertia)).Config.TurnRateDeg);
            Assert.AreEqual(300.0, Turner(TraitTestKit.One(TraitId.Inertia, 300)).Config.TurnRateDeg, "P1 is the turn rate");
            Assert.AreEqual(Tuning.TurnRateDeg, Turner(RuleTraits.Classic).Config.TurnRateDeg, "classic");
            var off = new RuleTraits(new[] { new TraitSpec(TraitId.Inertia, 420, double.NaN, false) });
            Assert.AreEqual(Tuning.TurnRateDeg, Turner(off).Config.TurnRateDeg, "a disabled Inertia does nothing");
        }

        [TestCase(60)]
        [TestCase(144)]
        public void Inertia_TurnsAtMostTurnRateTimesDtPerTick(int rate)
        {
            Simulation slow = Turner(TraitTestKit.One(TraitId.Inertia), rate);
            Simulation fast = Turner(RuleTraits.Classic, rate);
            double dt = 1.0 / rate;
            for (int k = 1; k <= 6; k++)
            {
                slow.Step();
                fast.Step();
                AssertInvariants(slow);
                Assert.That(slow.Players[0].Heading, Is.EqualTo(k * 420.0 * dt * Math.PI / 180.0).Within(1e-12), "Inertia heading after " + k + " ticks");
                Assert.That(fast.Players[0].Heading, Is.EqualTo(k * 540.0 * dt * Math.PI / 180.0).Within(1e-12), "classic heading after " + k + " ticks");
            }
        }

        [Test]
        public void Inertia_GivesRounderCurves()
        {
            // A quarter turn takes 90 / 420 s instead of 90 / 540 s: the turning radius grows from v / w = 0.64 u to 0.82 u.
            Simulation slow = Turner(TraitTestKit.One(TraitId.Inertia));
            Simulation fast = Turner(RuleTraits.Classic);
            RunUntil(slow, s => s.Players[0].Heading >= North - 1e-12, 1.0);
            RunUntil(fast, s => s.Players[0].Heading >= North - 1e-12, 1.0);
            Assert.AreEqual(Math.Ceiling(60.0 * 90.0 / 420.0 - 1e-9), slow.Tick, "ticks for a quarter turn with Inertia");
            Assert.AreEqual(Math.Ceiling(60.0 * 90.0 / 540.0 - 1e-9), fast.Tick, "ticks for a quarter turn, classic");
            double slowX = slow.Players[0].Pos.X - (-6 + H), fastX = fast.Players[0].Pos.X - (-6 + H);
            Assert.That(slowX, Is.GreaterThan(fastX + 0.1), "the Inertia curve is wider");
        }
    }
}
