// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: Conduction (behaviour trait), P1 = HomeSpeedFactor
// (1.30). Tick-rate dependent exactly like turning already is (the factor applies per whole tick): no cross-rate test.
using System;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class ConductionTraitTests
    {
        // Player 0 owns [-10, -2] x [-4, 4] and heads East from (-3 + H, H): home for a few ticks, exits at x = -2, then
        // trails. Player 1 idles far away.
        private static Simulation Runner(RuleTraits traits, int rate = 60)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-10, -4, -2, 4, V(-3 + H, H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            return sb.Build();
        }

        [Test]
        public void Conduction_HomeTicksAreFasterTrailingTicksKeepPawnSpeed()
        {
            Simulation sim = Runner(TraitTestKit.One(TraitId.Conduction));
            var log = new EventLog(sim);
            double homeStep = 6.0 * 1.3 / 60.0, trailStep = 6.0 / 60.0;
            int homeTicks = 0, trailTicks = 0;
            for (int k = 0; k < 40; k++)
            {
                PlayerState p = sim.Players[0];
                bool ownAtStart = sim.Grid.Cells[p.Cell] == p.Id;
                sim.Step();
                AssertInvariants(sim);
                double moved = Vec2d.Distance(p.PrevPos, p.Pos);
                if (ownAtStart)
                {
                    homeTicks++;
                    Assert.That(moved, Is.EqualTo(homeStep).Within(1e-12), "tick " + k + " started on own land: PawnSpeed x 1.3");
                }
                else
                {
                    trailTicks++;
                    Assert.That(moved, Is.EqualTo(trailStep).Within(1e-12), "tick " + k + " started off its land: PawnSpeed");
                }
            }
            Assert.That(homeTicks, Is.GreaterThanOrEqualTo(7));
            Assert.That(trailTicks, Is.GreaterThanOrEqualTo(20));
            // The exit tick runs at the home speed for the whole tick (its cell was own at tick start).
            SimEvent exit = log.Single(SimEventType.Exit, 0);
            Assert.That(exit.Point.X, Is.EqualTo(-2.0).Within(1e-9));
            Assert.That(exit.Time, Is.EqualTo((1.0 - H) / 7.8).Within(1e-9), "exit at the home speed 7.8 u/s");
        }

        [Test]
        public void Conduction_SparkSpeedStaysOnTheBasePawnSpeed()
        {
            Simulation sim = Runner(TraitTestKit.One(TraitId.Conduction));
            Assert.AreEqual(Tuning.SparkSpeedFactor * Tuning.PawnSpeed, sim.Config.SparkSpeed, 1e-12);
            Assert.AreEqual(Tuning.PawnSpeed, sim.Config.PawnSpeed);
            Assert.AreEqual(7.8, sim.View.HomeSpeed, 1e-12, "SimView.HomeSpeed = PawnSpeed x factor");
            Assert.AreEqual(1.3, ConductionTrait.HomeSpeedFactorOf(sim.View.Traits), 1e-15);
            Assert.AreEqual(1.0, ConductionTrait.HomeSpeedFactorOf(RuleTraits.Classic));
            // A chase: the spark runs at 1.8 x 6 while the victim trails at 6.
            RunUntilTime(sim, 1.0);
            sim.DebugForceCut(0, 0.5, 1);
            double sCut = 0.5, tCut = sim.Time;
            RunUntilTime(sim, 1.5);
            PlayerState v = sim.Players[0];
            Assert.IsNotNull(v.Spark);
            Assert.That(v.Spark.S, Is.EqualTo(sCut + 10.8 * (sim.Time - tCut)).Within(1e-9));
        }

        [Test]
        public void Conduction_ParameterAndClassic()
        {
            Simulation slow = Runner(TraitTestKit.One(TraitId.Conduction, 0.5));
            slow.Step();
            Assert.That(Vec2d.Distance(slow.Players[0].PrevPos, slow.Players[0].Pos), Is.EqualTo(0.05).Within(1e-12), "factor 0.5 at home");
            Simulation classic = Runner(RuleTraits.Classic);
            classic.Step();
            Assert.That(Vec2d.Distance(classic.Players[0].PrevPos, classic.Players[0].Pos), Is.EqualTo(0.1).Within(1e-12), "classic");
        }

        [Test]
        public void Conduction_HeadGraceCheckUsesTheLargestSpeedFactor()
        {
            // 60 Hz: PawnSpeed x Dt = 0.1 and with Conduction 1.3 the step is 0.13. HeadGrace 0.11 is legal only without it.
            Func<RuleTraits, Simulation> make = traits =>
            {
                var sb = new SimBuilder(60);
                sb.Config.HeadGrace = 0.11;
                sb.Config.Traits = traits;
                sb.AddIdle(IdleCorners[0]);
                sb.AddIdle(IdleCorners[2]);
                return sb.Build();
            };
            Assert.IsNotNull(make(RuleTraits.Classic));
            Assert.IsNotNull(make(TraitTestKit.One(TraitId.Conduction, 1.05)), "0.105 < 0.11");
            Assert.IsNotNull(make(TraitTestKit.One(TraitId.Conduction, 0.8)), "a factor below 1 never raises the step");
            Assert.Throws<ArgumentException>(() => make(TraitTestKit.One(TraitId.Conduction)), "0.13 >= 0.11");
            Assert.Throws<ArgumentException>(() => make(TraitTestKit.Electric));
        }

        [Test]
        public void Conduction_BotTravelEstimateUsesTheHomeSpeedOnOwnLand()
        {
            // A bot at the center of its start disc (radius 3.5) estimates the time to reach a point 6 u away in a straight
            // line: classic 6 / 6 = 1 s; with Conduction about 3.5 / 7.8 + 2.5 / 6 (own land first, then PawnSpeed).
            Func<RuleTraits, SimView> make = traits =>
            {
                var cfg = new SimConfig { Traits = traits };
                var sim = new Simulation(cfg, new IController[] { null, null }, new SimSetup { HumanIndex = -1 });
                return sim.View;
            };
            SimView classic = make(RuleTraits.Classic);
            Vec2d start = classic.Player(0).Pos;
            Vec2d target = start + new Vec2d(6.0 / Math.Sqrt(2.0), 6.0 / Math.Sqrt(2.0));
            Assert.AreEqual(1.0, BotController.InterceptTravelTime(classic, 0, target), 1e-12, "classic: distance / PawnSpeed");
            SimView conduction = make(TraitTestKit.One(TraitId.Conduction));
            double t = BotController.InterceptTravelTime(conduction, 0, target);
            Assert.That(t, Is.EqualTo(3.5 / 7.8 + 2.5 / 6.0).Within(0.03), "own-land part at 7.8 u/s, the rest at 6 u/s");
            SimView reach = make(TraitTestKit.One(TraitId.ArcReach));
            Assert.AreEqual((6.0 - 0.63 * 0.4) / 6.0, BotController.InterceptTravelTime(reach, 0, target), 1e-12,
                            "ArcReach: the cut happens 0.252 u earlier");
        }
    }
}
