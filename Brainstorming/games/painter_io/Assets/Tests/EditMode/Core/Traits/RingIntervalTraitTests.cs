// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: RingInterval (config trait), P1 = Seconds (10):
// overrides LassoFirstSpawn and LassoRespawn; only matters when the lasso option is on. Cross-rate equality required.
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class RingIntervalTraitTests
    {
        [Test]
        public void RingInterval_OverridesBothRingTimes()
        {
            var sb = new SimBuilder(60, true);
            sb.Config.Traits = TraitTestKit.One(TraitId.RingInterval);
            sb.AddIdle(IdleCorners[0]);
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            Assert.AreEqual(10.0, sim.Config.LassoFirstSpawn);
            Assert.AreEqual(10.0, sim.Config.LassoRespawn);
            Assert.AreEqual(10.0, sim.NextRingTime);
        }

        private static Simulation IdleRound(int rate, RuleTraits traits, bool lasso)
        {
            var sb = new SimBuilder(rate, lasso);
            sb.Config.Traits = traits;
            sb.ForcedRingPos = V(H, H);
            sb.AddIdle(IdleCorners[0]);
            sb.AddIdle(IdleCorners[2]);
            return sb.Build();
        }

        [Test]
        public void RingInterval_FirstRingAtTheTraitTimeAtEveryRate()
        {
            TraitTestKit.CrossRate("RingInterval first spawn", rate => IdleRound(rate, TraitTestKit.One(TraitId.RingInterval), true), 12.0, run =>
            {
                SimEvent spawned = run.Log.Single(SimEventType.RingSpawned);
                Assert.AreEqual(10.0, spawned.Time, 1e-12, run.Rate + " Hz: first ring at t = 10 s");
            });
            TraitTestKit.CrossRate("RingInterval 4 s", rate => IdleRound(rate, TraitTestKit.One(TraitId.RingInterval, 4.0), true), 5.0, run =>
            {
                Assert.AreEqual(4.0, run.Log.Single(SimEventType.RingSpawned).Time, 1e-12, run.Rate + " Hz: first ring at t = 4 s");
            });
        }

        [Test]
        public void RingInterval_ClassicAndLassoOffKeepTheirBehaviour()
        {
            Simulation classic = IdleRound(60, RuleTraits.Classic, true);
            var classicLog = new EventLog(classic);
            RunUntilTime(classic, 14.9);
            Assert.AreEqual(0, classicLog.Count(SimEventType.RingSpawned), "classic: nothing before 15 s");
            RunUntilTime(classic, 15.01);
            Assert.AreEqual(15.0, classicLog.Single(SimEventType.RingSpawned).Time, 1e-12);

            Simulation off = IdleRound(60, TraitTestKit.One(TraitId.RingInterval), false);
            var offLog = new EventLog(off);
            RunUntilTime(off, 30.0);
            Assert.AreEqual(0, offLog.Count(SimEventType.RingSpawned), "lasso option off: the trait spawns nothing");
        }

        [Test]
        public void RingInterval_NextRingTheTraitSecondsAfterThePickup()
        {
            // Player 1 shuttles East / West inside its own land along y = H (1 s legs between x = -3 and 3); the ring is
            // forced at (H, 1): 0.9375 u from the path, within the pickup distance 1.05, so each pass touches it.
            var sb = new SimBuilder(60, true);
            sb.Config.Traits = TraitTestKit.One(TraitId.RingInterval);
            sb.ForcedRingPos = V(H, 1.0);
            sb.AddIdle(IdleCorners[0]);
            var legs = new (double time, double heading)[24];
            for (int k = 0; k < legs.Length; k++) legs[k] = (k * 1.0, k % 2 == 0 ? East : West);
            sb.AddRect(-6, -2, 6, 2, V(-3 + H, H), East, new HeadingScheduleController(legs));
            Simulation sim = sb.Build();
            var log = new EventLog(sim);
            RunUntilTime(sim, 23.0);
            var spawns = log.Of(SimEventType.RingSpawned);
            SimEvent picked = log.Single(SimEventType.RingPicked, 1);
            Assert.That(spawns.Count, Is.EqualTo(2), "two rings: the first, then one after the pickup\n" + log.Dump());
            Assert.AreEqual(10.0, spawns[0].Time, 1e-12);
            Assert.That(picked.Time, Is.GreaterThan(10.0));
            double due = picked.Time + 10.0;
            Assert.That(spawns[1].Time, Is.GreaterThanOrEqualTo(due - 1e-12), "not before pickup + 10 s");
            Assert.That(spawns[1].Time, Is.LessThan(due + 1.0 / 60.0 + 1e-12), "at the first tick with Time >= pickup + 10 s");
        }
    }
}
