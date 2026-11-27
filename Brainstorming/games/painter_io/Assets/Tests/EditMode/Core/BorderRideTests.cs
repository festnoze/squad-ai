// Rule v1.9 (contract 33, border ride): trigger after exactly BorderRideDelay of contact, x BorderRideFactor speed,
// cross-rate outcomes, boundary following around the rounded corner of the classic square and around the convex and reflex
// vertices of a polygon without user input, end on steering inward, La Revanche (no ride while chased, a spark ends it),
// Off ignores every ride parameter, and the section 9 bot targets with the ride on.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class BorderRideTests
    {
        private const double Speed = 6.0;
        private const double RideSpeed = 18.0;
        private const double TopLine = 32.0 - 0.45;   // inset line of the top side of the classic square

        // North wall scenario: player 0 owns [-12, -4] x [20, 32] and starts at (-5 + H, 22 + H) heading East; at t = 0.5
        // (x = -2 + H) it turns North (exactly into the top side: held, R4) and touches the contact tolerance at tc. The ride
        // starts at tc + 1 toward the West (a push straight in rides along +OutwardNormal.Perp(), here -x) and enters home
        // again at x = -4. Player 1 idles far away.
        private const double TurnTime = 0.5;
        private const double RideX = -2.0 + H;
        private static readonly double ContactTime = TurnTime + (TopLine - BorderRide.ContactTolerance - (22.0 + H)) / Speed;
        private static readonly double RideTime = ContactTime + 1.0;
        private static readonly double ReturnTime = RideTime + (RideX - (-4.0)) / RideSpeed;

        private static Simulation NorthWall(int rate, BorderRideRule rule, IController controller = null)
        {
            var sb = new SimBuilder(rate);
            sb.Config.BorderRide = rule;
            sb.AddRect(-12, 20, -4, 32, V(-5 + H, 22 + H), East,
                       controller ?? new HeadingScheduleController((0.0, East), (TurnTime, North)));
            sb.AddIdle(IdleCorners[2]);
            return sb.Build();
        }

        [Test]
        public void BorderRide_StartsAfterExactlyOneSecondOfContactAndNotBefore()
        {
            Simulation sim = NorthWall(60, BorderRideRule.On);
            PlayerState p = sim.Players[0];
            bool sawContact = false;
            RunUntilTime(sim, ReturnTime - 0.02, true, s =>
            {
                bool expected = s.Time > RideTime + 1e-12;
                Assert.AreEqual(expected, p.BorderRiding, "riding at t = " + s.Time);
                Assert.AreEqual(expected, s.View.IsBorderRiding(0));
                if (!double.IsNaN(p.BorderContactStart)) sawContact = true;
            });
            Assert.IsTrue(sawContact);
            Assert.That(p.BorderContactStart, Is.EqualTo(ContactTime).Within(1e-9), "exact contact instant");
            Assert.That(p.BorderRideStart, Is.EqualTo(RideTime).Within(1e-9), "contact + BorderRideDelay");
            Assert.That(sim.View.BorderRideStartTime(0), Is.EqualTo(RideTime).Within(1e-9));
            Assert.AreEqual(1, p.BorderRideSign, "a push straight in rides along +OutwardNormal.Perp() (West on the top side)");
        }

        [Test]
        public void BorderRide_RidesAtThreeTimesTheSpeedAlongTheBorder()
        {
            Simulation sim = NorthWall(60, BorderRideRule.On);
            PlayerState p = sim.Players[0];
            RunUntilTime(sim, RideTime + 1.0 / 60.0 + 1e-9);   // past the tick where the ride starts
            int checkedTicks = 0;
            while (sim.Time < ReturnTime - 2.0 / 60.0)
            {
                sim.Step();
                AssertInvariants(sim);
                Assert.IsTrue(p.BorderRiding);
                Assert.That(Vec2d.Distance(p.PrevPos, p.Pos), Is.EqualTo(RideSpeed / 60.0).Within(1e-9), "x3 step at t = " + sim.Time);
                Assert.That(p.Pos.Y, Is.EqualTo(TopLine).Within(1e-9), "on the inset line");
                Assert.That(p.Pos.X, Is.EqualTo(RideX - RideSpeed * (sim.Time - RideTime)).Within(1e-9), "closed form along the side");
                Assert.That(p.Heading, Is.EqualTo(Math.PI).Within(1e-9), "heading = the boundary tangent (West)");
                Assert.That(sim.View.EffectiveSpeed(0), Is.EqualTo(RideSpeed).Within(1e-12));
                checkedTicks++;
            }
            Assert.That(checkedTicks, Is.GreaterThanOrEqualTo(4));
        }

        [Test]
        public void BorderRide_CrossRate_SameOutcomesAndSameRideInstantAt30_60_144Hz()
        {
            ulong first = 0;
            CrossRate("border ride", rate => NorthWall(rate, BorderRideRule.On), ReturnTime + 0.1, (rate, sim, log) =>
            {
                PlayerState p = sim.Players[0];
                Assert.That(p.BorderRideStart, Is.EqualTo(RideTime).Within(1e-9), rate + " Hz ride instant");
                SimEvent ret = log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(ReturnTime).Within(1e-6), rate + " Hz return at the closed-form time");
                Assert.That(ret.Cells.Length, Is.GreaterThan(0), "the ride closes a loop");
            });
            // Same rate, same seed and inputs: the same StateHash (StateHash is compared within one tick rate, 10.0 item 3).
            foreach (int rate in CrossRates)
            {
                Simulation a = NorthWall(rate, BorderRideRule.On), b = NorthWall(rate, BorderRideRule.On);
                RunUntilTime(a, ReturnTime + 0.1, false);
                RunUntilTime(b, ReturnTime + 0.1, false);
                Assert.AreEqual(a.StateHash(), b.StateHash(), rate + " Hz determinism");
                if (rate == 60) first = a.StateHash();
            }
            Assert.AreNotEqual(0UL, first);
        }

        [Test]
        public void BorderRide_EndsWhenThePlayerSteersInward()
        {
            double steer = 19.0 / 6.0;   // 3.1667 s, during the ride and before home
            Assert.That(steer, Is.GreaterThan(RideTime + 1.0 / 60.0));
            Assert.That(steer, Is.LessThan(ReturnTime));
            var controller = new HeadingScheduleController((0.0, East), (TurnTime, North), (steer, South));
            Simulation sim = NorthWall(60, BorderRideRule.On, controller);
            PlayerState p = sim.Players[0];
            RunUntilTime(sim, steer);
            Assert.IsTrue(p.BorderRiding, "riding just before the steer");
            sim.Step();
            AssertInvariants(sim);
            Assert.IsFalse(p.BorderRiding, "a new heading into the interior ends the ride");
            Assert.That(p.PrevPos.Y - p.Pos.Y, Is.EqualTo(Speed / 60.0).Within(1e-9), "normal speed at once, straight inward");
            Assert.That(p.Pos.X, Is.EqualTo(p.PrevPos.X).Within(1e-9));
            Assert.IsTrue(double.IsNaN(p.BorderContactStart), "the delay starts over at the next contact");
            StepN(sim, 30);
            Assert.IsFalse(p.BorderRiding);
        }

        [Test]
        public void BorderRide_SmallJoystickWobbleIsNotANewInput()
        {
            // 10 degrees off North (within InputTolerance) during the ride: still riding at x3.
            double wobble = 19.0 / 6.0;
            var controller = new HeadingScheduleController((0.0, East), (TurnTime, North), (wobble, North + 10.0 * Math.PI / 180.0));
            Simulation sim = NorthWall(60, BorderRideRule.On, controller);
            PlayerState p = sim.Players[0];
            RunUntilTime(sim, wobble + 1.0 / 60.0 + 1e-9);
            Assert.IsTrue(p.BorderRiding);
            Assert.That(Vec2d.Distance(p.PrevPos, p.Pos), Is.EqualTo(RideSpeed / 60.0).Within(1e-9));
        }

        [Test]
        public void BorderRide_NoBoostWhileChased()
        {
            Simulation sim = NorthWall(60, BorderRideRule.On);
            var log = new EventLog(sim);
            long cutTick = (long)Math.Round(2.2 * 60);
            sim.BeforeTick += s => { if (s.Tick == cutTick) s.DebugForceCut(0, 0.0, -1); };
            PlayerState p = sim.Players[0];
            bool chasedAfterRideTime = false;
            RunUntil(sim, s =>
            {
                Assert.IsFalse(p.BorderRiding, "no ride while a spark chases (t = " + s.Time + ")");
                if (p.Spark != null)
                {
                    Assert.IsTrue(double.IsNaN(p.BorderContactStart), "a chased player accumulates no contact time");
                    if (s.Time > RideTime + 0.05) chasedAfterRideTime = true;
                }
                return !p.Alive;
            }, 6.0);
            Assert.IsTrue(chasedAfterRideTime, "the chase covered the instant the ride would have started");
            Assert.AreEqual(1, log.Count(SimEventType.SparkCaught, 0), "the 1.8x spark still catches the held head");
            Assert.IsFalse(sim.View.IsBorderRiding(0));
        }

        [Test]
        public void BorderRide_ASparkEndsTheRideAtOnce()
        {
            Simulation sim = NorthWall(60, BorderRideRule.On);
            long cutTick = (long)Math.Round(3.1 * 60);   // 3.1 s: riding since RideTime = 3.078 s
            bool ridingAtCut = false;
            PlayerState p = sim.Players[0];
            sim.BeforeTick += s =>
            {
                if (s.Tick != cutTick) return;
                ridingAtCut = p.BorderRiding;
                s.DebugForceCut(0, 0.0, -1);
            };
            RunUntilTime(sim, cutTick / 60.0 + 1.0 / 60.0 + 1e-9);
            Assert.IsTrue(ridingAtCut, "the spark appeared during a ride");
            Assert.IsNotNull(p.Spark);
            Assert.IsFalse(p.BorderRiding, "the spark ended the ride");
            // The ride is over: the desired heading (North, straight into the side) applies again, so the head is held (R4).
            Assert.That(Vec2d.Distance(p.PrevPos, p.Pos), Is.LessThanOrEqualTo(Speed / 60.0 + 1e-9), "no boost from the cut tick on");
            Assert.That(p.Pos.Y, Is.EqualTo(TopLine).Within(1e-9));
            StepN(sim, 30);
            Assert.IsFalse(p.BorderRiding);
        }

        [Test]
        public void BorderRide_FollowsTheRoundedCornerOfTheSquareWithoutInput()
        {
            // Leaning 5 degrees East of North into the top side: held, then rides East, round the corner arc (center
            // (22, 22), inset radius 9.55) and down the right side, the desired heading never changing.
            double heading = North - 5.0 * Math.PI / 180.0;
            var sb = new SimBuilder(60);
            sb.Config.BorderRide = BorderRideRule.On;
            sb.AddRect(12, 24, 16, 28, V(14 + H, 26 + H), heading, new ConstantHeadingController(heading));
            sb.AddIdle(IdleCorners[0]);
            Simulation sim = sb.Build();
            PlayerState p = sim.Players[0];
            Assert.IsTrue(RunUntil(sim, s => p.BorderRiding, 5.0), "the ride starts");
            Assert.AreEqual(-1, p.BorderRideSign, "rides East (the side the heading leans to)");
            double start = p.BorderRideStart;
            RunUntilTime(sim, start + 2.0, true, s =>
            {
                Assert.IsTrue(p.BorderRiding, "still riding at t = " + s.Time);
                Assert.That(Vec2d.Distance(p.PrevPos, p.Pos), Is.GreaterThan(0.95 * RideSpeed / 60.0), "never slowed by the arc");
                Assert.That(sim.Arena.SignedDistance(p.Pos) + sim.Arena.Margin, Is.InRange(-1e-6, 0.0), "on the inset line");
            });
            Assert.That(p.Pos.X, Is.EqualTo(TopLine).Within(1e-9), "on the right side");
            Assert.That(p.Pos.Y, Is.LessThan(15.0), "past the corner, going down");
            Assert.That(Math.Abs(Geo.WrapAngle(p.Heading - South)), Is.LessThan(1e-9), "heading South along the right side");
        }

        // Polygon arena: an L with a chamfered corner, counter-clockwise. Convex vertices (interior angle < 180, where a
        // plain R4 slide is held): (15, -20) and (20, -15) at 135 degrees, (20, 0) and (0, 20) at 90 degrees. Reflex vertex
        // (0, 0) at 270 degrees.
        private static Simulation PolygonRide(out PlayerState p)
        {
            var outline = new[]
            {
                V(-20, -20), V(15, -20), V(20, -15), V(20, 0), V(0, 0), V(0, 20), V(-20, 20),
            };
            double heading = South + 5.0 * Math.PI / 180.0;   // leaning East into the bottom side
            var sb = new SimBuilder(60);
            sb.Config.BorderRide = BorderRideRule.On;
            sb.Config.ArenaBoundary = new ArenaPolygon(outline, V(-10, -10));
            sb.AddRect(-6, -16, -2, -12, V(-4 + H, -14 + H), heading, new ConstantHeadingController(heading));
            sb.AddIdle(V(-10, 10));
            Simulation sim = sb.Build();
            p = sim.Players[0];
            return sim;
        }

        private static void RunRiding(Simulation sim, PlayerState p, double until)
        {
            RunUntilTime(sim, until, true, s =>
            {
                Assert.IsTrue(p.BorderRiding, "still riding at t = " + s.Time + " pos " + p.Pos);
                Assert.That(Vec2d.Distance(p.PrevPos, p.Pos), Is.GreaterThan(0.5 * RideSpeed / 60.0), "never stuck at t = " + s.Time + " pos " + p.Pos);
                Assert.That(sim.Arena.SignedDistance(p.Pos), Is.LessThanOrEqualTo(-sim.Arena.Margin), "in the inset shape");
            });
        }

        [Test]
        public void BorderRide_TurnsAtConvexPolygonVerticesWithoutInput()
        {
            Simulation sim = PolygonRide(out PlayerState p);
            Assert.IsTrue(RunUntil(sim, s => p.BorderRiding, 5.0), "the ride starts on the bottom side");
            Assert.AreEqual(1, p.BorderRideSign, "rides East (the side the heading leans to)");
            double start = p.BorderRideStart;
            // Bottom side, the two 135 degree vertices of the chamfer, then up the right side.
            RunRiding(sim, p, start + 2.0);
            Assert.That(p.Pos.X, Is.EqualTo(20.0 - 0.45).Within(0.011), "on the right side after two obtuse convex vertices");
            Assert.That(p.Pos.Y, Is.InRange(-14.0, -1.0));
            // The 90 degree pocket at (20, 0): turns West along y = -0.45.
            RunRiding(sim, p, start + 3.0);
            Assert.That(p.Pos.Y, Is.EqualTo(-0.45).Within(0.011), "along the top of the lower arm after the 90 degree pocket");
            Assert.That(p.Pos.X, Is.InRange(1.0, 18.0));
        }

        [Test]
        public void BorderRide_WrapsAroundAReflexPolygonVertexWithoutInput()
        {
            Simulation sim = PolygonRide(out PlayerState p);
            Assert.IsTrue(RunUntil(sim, s => p.BorderRiding, 5.0));
            double start = p.BorderRideStart;
            // West along y = -0.45, around the reflex vertex (0, 0) (an arc of radius 0.45) and up the inner side of the upper
            // arm (the edge x = 0, interior x < 0: inset line x = -0.45).
            RunRiding(sim, p, start + 3.9);
            Assert.That(p.Pos.X, Is.EqualTo(-0.45).Within(0.011), "on the inner side after the reflex vertex");
            Assert.That(p.Pos.Y, Is.GreaterThan(2.0));
            Assert.That(Math.Abs(Geo.WrapAngle(p.Heading - North)), Is.LessThan(1e-6), "heading North");
        }

        [Test]
        public void BorderRide_OffIgnoresEveryRideParameter()
        {
            Simulation plain = NorthWall(60, BorderRideRule.Off);
            var sb = new SimBuilder(60);
            sb.Config.BorderRide = BorderRideRule.Off;
            sb.Config.BorderRideFactor = 7.0;
            sb.Config.BorderRideDelay = 0.1;
            sb.AddRect(-12, 20, -4, 32, V(-5 + H, 22 + H), East, new HeadingScheduleController((0.0, East), (TurnTime, North)));
            sb.AddIdle(IdleCorners[2]);
            Simulation tuned = sb.Build();
            PlayerState p = plain.Players[0];
            RunUntilTime(plain, 4.0, true, s =>
            {
                Assert.IsFalse(p.BorderRiding);
                Assert.IsTrue(double.IsNaN(p.BorderContactStart));
            });
            RunUntilTime(tuned, 4.0);
            Assert.AreEqual(plain.StateHash(), tuned.StateHash(), "Off reads no ride parameter");
            Assert.That(p.Pos.Y, Is.EqualTo(TopLine).Within(1e-9), "held against the top side (R4), no ride");
            Assert.That(p.Pos.X, Is.EqualTo(RideX).Within(1e-9));
            Assert.AreEqual(BorderRideRule.Off, new SimConfig().BorderRide, "the Core default is Off");
        }

#if !UNITY_5_3_OR_NEWER
        [TestCase(true)]
        [TestCase(false)]
        public void BorderRide_SeededBotOnlyRoundsStillMeetSection9Targets(bool lasso)
        {
            BotTests.Summary s = BotTests.RunSeeds(50, BotTests.Lineup(BotTests.BotOnlyLineup), -1, lasso, out List<BotTests.RoundStats> rounds,
                                                   borderRide: true);
            TestContext.WriteLine(s.Format("Bot-only rounds with the border ride, lasso " + (lasso ? "on" : "off")));
            Assert.AreEqual(50, rounds.Count);
            for (int i = 0; i < BotTests.BotOnlyLineup.Length; i++)
            {
                double required = BotTests.BotOnlyLineup[i] == BotStyle.Greedy ? 4.0 : 5.0;
                Assert.That(s.MeanCaptures[i], Is.GreaterThanOrEqualTo(required), "average captures of player " + i);
            }
            Assert.That(s.CutShare, Is.GreaterThanOrEqualTo(0.85), "share of matches with a cut");
            Assert.That(s.SparkKillShare, Is.InRange(0.35, 0.85), "share of matches with at least one Spark elimination");
            Assert.That(s.MeanCoverage, Is.InRange(30.0, 85.0), "average total coverage at the end (%)");
            Assert.That(s.TimeUpShare, Is.GreaterThanOrEqualTo(0.40), "share of matches reaching TimeUp");
            Assert.AreEqual(0L, s.HeldTicks, "ticks where a bot pushed into the border and was held");
            Assert.AreEqual(0, s.ChasedCaptures, "a chased (saved) return never captures");
        }

        [Test]
        public void BorderRide_BotRoundsReport()
        {
            // Information for the report: how often plain bot rounds touch the border and ride (bots do not seek the ride).
            long contactTicks = 0, rideTicks = 0, rides = 0;
            for (ulong seed = 1; seed <= 10; seed++)
            {
                var config = new SimConfig { Seed = seed, LassoEnabled = true, BorderRide = BorderRideRule.On };
                var controllers = new IController[4];
                for (int i = 0; i < 4; i++) controllers[i] = new BotController(BotPersonality.Preset(BotTests.BotOnlyLineup[i]), BotTests.BotSeed(seed, i));
                var sim = new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
                var was = new bool[4];
                while (!sim.Ended)
                {
                    sim.Step();
                    for (int i = 0; i < 4; i++)
                    {
                        PlayerState p = sim.Players[i];
                        if (!double.IsNaN(p.BorderContactStart)) contactTicks++;
                        if (p.BorderRiding) rideTicks++;
                        if (p.BorderRiding && !was[i]) rides++;
                        was[i] = p.BorderRiding;
                    }
                }
            }
            TestContext.WriteLine("10 bot rounds with the border ride: contact ticks " + contactTicks + ", rides " + rides + ", riding ticks " + rideTicks);
            Assert.That(rideTicks, Is.LessThanOrEqualTo(contactTicks + rideTicks));
        }
#endif
    }
}
