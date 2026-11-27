// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: ScorchedEarth (behaviour trait), P1 = Duration (15 s).
// The interplay with Propagation and Coalescence is tested in their own files.
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class ScorchedEarthTraitTests
    {
        /// <summary>
        /// Player 0 owns [-6, 0] x [-3, 3] and loops East 8, North 5, West around [0, 7] x [-2.4375, 2.5625]; player 1 owns
        /// [2, 6] x [-2, 2] (inside that loop) and is eliminated at t = 0.1 by a forced catch on a far trail, long before
        /// player 0 returns (t = 13/6 + 7.0625/6).
        /// </summary>
        internal static Simulation LoopAroundTheDead(int rate, RuleTraits traits, out int[] deadLand)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-6, -3, 0, 3, V(-1 + H, -2.4375), East, Legs((East, 8), (North, 5), (West, 20)));
            sb.AddRect(2, -2, 6, 2, V(4 + H, H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);   // a third player, so the elimination does not end the round
            Simulation sim = sb.Build();
            deadLand = TraitTestKit.RectCells(sim.Grid, 2, -2, 6, 2);
            sim.BeforeTick += s =>
            {
                if (s.Tick != (long)System.Math.Round(0.1 * s.Config.TickRate)) return;
                s.DebugSetTrail(1, new[] { V(10 + H, 10 + H), V(12 + H, 10 + H) });
                s.DebugForceCut(1, 3.0, 0);   // sCut > L: caught at once (u = 0 of this tick)
            };
            return sim;
        }

        [Test]
        public void ScorchedEarth_FreedCellsStayScorchedForTheDurationAndNothingElseIsEmitted()
        {
            Simulation sim = LoopAroundTheDead(60, TraitTestKit.One(TraitId.ScorchedEarth), out int[] land);
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.2);
            SimEvent dead = log.Single(SimEventType.Eliminated, 1);
            Assert.AreEqual(0.1, dead.Time, 1e-12);
            Assert.IsTrue(SameCells(land, dead.Cells), "the freed cells are the land");
            foreach (SimEvent e in log.All)
            {
                Assert.IsTrue(e.Type == SimEventType.Exit || e.Type == SimEventType.SparkCaught || e.Type == SimEventType.Eliminated,
                              "no extra event: " + e + "\n" + log.Dump());
            }
            SimView view = sim.View;
            foreach (int c in land)
            {
                Assert.IsTrue(view.IsScorched(c), "scorched right after the elimination");
                Assert.AreEqual(15.1, view.ScorchEndTime(c), 1e-12, "EliminatedAt + Duration");
                Assert.AreEqual(OwnerGrid.Neutral, sim.Grid.Cells[c], "still neutral");
            }
            int other = CellIndex(sim.Grid, -20 + H, 20 + H);
            Assert.IsFalse(view.IsScorched(other));
            Assert.AreEqual(double.NegativeInfinity, view.ScorchEndTime(other), "never scorched");
        }

        [Test]
        public void ScorchedEarth_ScorchEndsAfterTheDuration()
        {
            // Duration 2 s: player 1 (between two idle players) dies at t = 0.1 and nobody touches its land afterwards.
            var sb = new SimBuilder(60);
            sb.Config.Traits = TraitTestKit.One(TraitId.ScorchedEarth, 2.0);
            sb.AddIdle(IdleCorners[0]);
            sb.AddRect(2, -2, 6, 2, V(4 + H, H), East, new ConstantHeadingController(East));
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            int[] land = TraitTestKit.RectCells(sim.Grid, 2, -2, 6, 2);
            sim.BeforeTick += s =>
            {
                if (s.Tick != 6) return;
                s.DebugSetTrail(1, new[] { V(10 + H, 10 + H), V(12 + H, 10 + H) });
                s.DebugForceCut(1, 3.0, 0);
            };
            RunUntilTime(sim, 2.05);
            Assert.IsTrue(sim.View.IsScorched(land[0]), "t = 2.05 < 0.1 + 2");
            RunUntilTime(sim, 2.15);
            Assert.IsFalse(sim.View.IsScorched(land[0]), "t = 2.15 > 0.1 + 2");
            Assert.AreEqual(2.1, sim.View.ScorchEndTime(land[0]), 1e-12, "the end time stays readable for views");
        }

        [Test]
        public void ScorchedEarth_ScorchedCellsAreCapturedNormally()
        {
            Simulation sim = LoopAroundTheDead(60, TraitTestKit.One(TraitId.ScorchedEarth), out int[] land);
            var log = new EventLog(sim);
            RunUntilTime(sim, 4.0);
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsFalse(ret.Chased);
            Assert.AreEqual(land.Length, TraitTestKit.CountIn(ret.Cells, land), "every scorched cell inside the loop is captured");
            Assert.AreEqual(land.Length, TraitTestKit.CountOwned(sim.Grid, land, 1));
            foreach (int c in land) Assert.IsFalse(sim.View.IsScorched(c), "an owned cell is not scorched");

            // Same capture as without the trait (the scorch never changes a capture).
            Simulation classic = LoopAroundTheDead(60, RuleTraits.Classic, out int[] _);
            var classicLog = new EventLog(classic);
            RunUntilTime(classic, 4.0);
            Assert.IsTrue(SameCells(classicLog.Single(SimEventType.Return, 0).Cells, ret.Cells));
        }

        [Test]
        public void ScorchedEarth_ZeroDurationAndClassicScorchNothing()
        {
            foreach (RuleTraits traits in new[] { TraitTestKit.One(TraitId.ScorchedEarth, 0.0), RuleTraits.Classic, TraitTestKit.One(TraitId.Propagation) })
            {
                Simulation sim = LoopAroundTheDead(60, traits, out int[] land);
                RunUntilTime(sim, 0.2);
                Assert.IsFalse(sim.Players[1].Alive);
                foreach (int c in land) Assert.IsFalse(sim.View.IsScorched(c), traits + ": no scorch");
            }
        }

        [Test]
        public void ScorchedEarth_StateIsDeterministicAndHashed()
        {
            Simulation a = LoopAroundTheDead(60, TraitTestKit.One(TraitId.ScorchedEarth), out int[] _);
            Simulation b = LoopAroundTheDead(60, TraitTestKit.One(TraitId.ScorchedEarth), out int[] _);
            for (int k = 0; k < 300; k++)
            {
                a.Step();
                b.Step();
                Assert.AreEqual(a.StateHash(), b.StateHash(), "same seed, same hash at tick " + a.Tick);
            }
            Assert.IsFalse(a.Players[1].Alive);
        }
    }
}
