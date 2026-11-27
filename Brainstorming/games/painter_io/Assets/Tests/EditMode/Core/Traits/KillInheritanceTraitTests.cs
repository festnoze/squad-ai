// Owned by kill-core (wave D-2). docs/BIOME_TRAITS.md section 7: KillInheritance (behaviour trait, kill reward), P1 = Share
// (1.0). Cross-rate equality required (the inheritance happens at the exact kill instant and depends only on the cells).
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class KillInheritanceTraitTests
    {
        /// <summary>The victim's catch time of the basic scenario: not a tick time at 30, 60 or 144 Hz.</summary>
        private const double CatchTime = 1.013;

        /// <summary>The catch time of the trailing-killer scenario: the killer is then inside the victim's land.</summary>
        private const double TrailCatchTime = 1.763;

        /// <summary>
        /// Victim (player 0) owns [0, 8] x [-4, 4]; at t = 0 it is teleported to a trail East on y = -15 + H from x = -15 + H
        /// (L = 10) with a spark of the killer (player 1) that catches it at catchTime. The killer owns [-10, 0] x [-4, 4]
        /// (it touches the victim's land along x = 0). Players 2 and 3 idle far away, so the round goes on.
        /// </summary>
        private static Simulation Build(int rate, RuleTraits traits, IController killer, Vec2d killerStart, double killerHeading,
                                        double catchTime)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
            sb.AddRect(-10, -4, 0, 4, killerStart, killerHeading, killer);
            sb.AddIdle(IdleCorners[2]);
            sb.AddIdle(IdleCorners[1]);
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, catchTime);
            return sim;
        }

        /// <summary>The killer stays home (orbit inside its land).</summary>
        private static Simulation HomeKiller(int rate, RuleTraits traits)
        {
            return Build(rate, traits, new HomeCirclerController(V(-5, 0)), V(-5 + H, H), North, CatchTime);
        }

        /// <summary>
        /// The killer exits North at x = -1 + H (t = 0.15625), goes North to y = 5 + H (t = 1/3), East to x = 5 + H (t = 4/3)
        /// and South: it enters the victim's land at t = 1.5104 and is at y = 2.4846 at TrailCatchTime.
        /// </summary>
        private static Simulation TrailingKiller(int rate, RuleTraits traits)
        {
            return Build(rate, traits, Legs((North, 2), (East, 6), (South, 10)), V(-1 + H, 3 + H), North, TrailCatchTime);
        }

        [Test]
        public void KillInheritance_TheSurvivingKillerTakesTheVictimsLandAtEveryRate()
        {
            TraitTestKit.CrossRate("KillInheritance", rate => HomeKiller(rate, TraitTestKit.One(TraitId.KillInheritance)), 1.2, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                int[] land = TraitTestKit.RectCells(sim.Grid, 0, -4, 8, 4);
                Assert.AreEqual(64 * 64, land.Length);
                SimEvent caught = run.Log.Single(SimEventType.SparkCaught, 0);
                SimEvent dead = run.Log.Single(SimEventType.Eliminated, 0);
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 1);
                Assert.That(caught.Time, Is.EqualTo(CatchTime).Within(1e-6), at + "catch time");
                Assert.AreEqual(1, caught.Other, at + "the killer is the spark's attacker");
                Assert.AreEqual(dead.Time, inherited.Time, at + "the inheritance happens at the kill instant");
                Assert.AreEqual(run.Log.IndexOf(dead) + 1, run.Log.IndexOf(inherited), at + "right after the victim's Eliminated");
                Assert.AreEqual(0, inherited.Other, at + "Other = the victim");
                AssertNear(caught.Point, inherited.Point, 1e-12, at + "Point = the victim's head at the kill");
                Assert.IsTrue(SameCells(land, dead.Cells), at + "Eliminated still lists every freed cell");
                Assert.IsTrue(SameCells(land, inherited.Cells), at + "every freed cell is inherited");
                Assert.AreEqual(land.Length, TraitTestKit.CountOwned(sim.Grid, land, 2), at + "the land is the killer's");
                Assert.AreEqual(land.Length, sim.Players[0].FinalCells, at + "FinalCells: the victim's cells before the group");
                Assert.AreEqual(1, sim.Players[1].Kills);
                Assert.IsTrue(sim.Players[1].Home, at + "a home killer stays home");
                Assert.IsFalse(sim.Ended);
            });
        }

        [Test]
        public void KillInheritance_ClassicAndDisabledLeaveTheLandNeutral()
        {
            foreach (RuleTraits traits in new[]
                     {
                         RuleTraits.Classic, new RuleTraits(new[] { new TraitSpec(TraitId.KillInheritance, 1.0, double.NaN, false) }),
                         TraitTestKit.One(TraitId.KillInheritance, 0.0),
                     })
            {
                Simulation sim = HomeKiller(60, traits);
                var log = new EventLog(sim);
                RunUntilTime(sim, 1.2);
                int[] land = TraitTestKit.RectCells(sim.Grid, 0, -4, 8, 4);
                Assert.AreEqual(1, log.Count(SimEventType.Eliminated, 0), traits + ": the kill happened");
                Assert.AreEqual(0, log.Count(SimEventType.TerritoryInherited), traits + ": no inheritance");
                Assert.AreEqual(land.Length, TraitTestKit.CountOwned(sim.Grid, land, OwnerGrid.Neutral), traits + ": the land is neutral");
            }
        }

        [Test]
        public void KillInheritance_ADeadKillerGivesNothingAndScorchedEarthStillScorches()
        {
            // The killer (player 1) is itself killed by player 2 at t = 0.5 (player 2 inherits ITS land); its spark keeps
            // running (R12) and catches the victim at CatchTime: Kills is credited, but the victim's land stays neutral and
            // is scorched (ScorchedEarth marks only cells that stay neutral).
            RuleTraits traits = RuleTraits.Parse("KillInheritance;ScorchedEarth");
            TraitTestKit.CrossRate("dead killer", rate =>
            {
                Simulation sim = HomeKiller(rate, traits);
                KillTestKit.ForceKillAt(sim, 0.5, 1, 2, V(10 + H, 10 + H));
                return sim;
            }, 1.2, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                int[] land = TraitTestKit.RectCells(sim.Grid, 0, -4, 8, 4);
                int[] killerLand = TraitTestKit.RectCells(sim.Grid, -10, -4, 0, 4);
                SimEvent first = run.Log.Single(SimEventType.TerritoryInherited, 2);
                Assert.AreEqual(1, first.Other, at + "player 2 killed the killer and took its land");
                Assert.IsTrue(SameCells(killerLand, first.Cells));
                Assert.AreEqual(0, run.Log.Count(SimEventType.TerritoryInherited, 1), at + "a dead killer inherits nothing");
                Assert.IsFalse(sim.Players[0].Alive);
                Assert.AreEqual(1, sim.Players[1].Kills, at + "Kills credited even if dead (R12)");
                Assert.AreEqual(land.Length, TraitTestKit.CountOwned(sim.Grid, land, OwnerGrid.Neutral), at + "neutral land");
                foreach (int c in land) Assert.IsTrue(sim.View.IsScorched(c), at + "the neutral land is scorched");
                foreach (int c in killerLand) Assert.IsFalse(sim.View.IsScorched(c), at + "inherited land is not scorched");
            });
        }

        [Test]
        public void KillInheritance_AKillerEliminatedInTheSameGroupGetsNothing()
        {
            // Players 0 and 1 chase each other's trail with identical geometry: both are caught in the same group.
            TraitTestKit.CrossRate("mutual kill", rate =>
            {
                var sb = new SimBuilder(rate);
                sb.Config.Traits = TraitTestKit.One(TraitId.KillInheritance);
                sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
                sb.AddRect(-10, -4, -2, 4, V(-5 + H, H), East, new ConstantHeadingController(East));
                sb.AddIdle(IdleCorners[2]);
                sb.AddIdle(IdleCorners[1]);
                Simulation sim = sb.Build();
                KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, CatchTime);
                KillTestKit.ForceChase(sim, 1, 0, V(-15 + H, -20 + H), 10.0, CatchTime);
                return sim;
            }, 1.2, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent a = run.Log.Single(SimEventType.Eliminated, 0), b = run.Log.Single(SimEventType.Eliminated, 1);
                Assert.AreEqual(a.Time, b.Time, at + "one group");
                Assert.AreEqual(0, run.Log.Count(SimEventType.TerritoryInherited), at + "both killers died in the group");
                Assert.AreEqual(a.Cells.Length, TraitTestKit.CountOwned(sim.Grid, a.Cells, OwnerGrid.Neutral), at + "land of 0 neutral");
                Assert.AreEqual(b.Cells.Length, TraitTestKit.CountOwned(sim.Grid, b.Cells, OwnerGrid.Neutral), at + "land of 1 neutral");
                Assert.AreEqual(1, sim.Players[0].Kills);
                Assert.AreEqual(1, sim.Players[1].Kills);
                Assert.IsFalse(sim.Ended, at + "two idle players remain");
            });
        }

        [Test]
        public void KillInheritance_AnInheritedCellUnderTheTrailingKillerReturnsItAtThatInstant()
        {
            // Section 7.2: the killer trails over the victim's land when it inherits it, so its current cell becomes its own:
            // it returns at that instant through the normal section 6 state check. Unchased: the return captures the strip
            // its trail encloses between the two lands' top edge (y = 4) and the trail.
            TraitTestKit.CrossRate("inherited under the head", rate => TrailingKiller(rate, TraitTestKit.One(TraitId.KillInheritance)), 1.8, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 1);
                SimEvent ret = run.Log.Single(SimEventType.Return, 1);
                Assert.That(inherited.Time, Is.EqualTo(TrailCatchTime).Within(1e-6), at + "kill time");
                Assert.AreEqual(inherited.Time, ret.Time, at + "returns at the inheritance instant");
                Assert.That(run.Log.IndexOf(ret), Is.GreaterThan(run.Log.IndexOf(inherited)), at + "after the inheritance");
                Assert.IsFalse(ret.Chased, at + "unchased");
                Assert.That(ret.Cells.Length, Is.GreaterThan(300), at + "the strip is captured with the trail");
                int strip = CellIndex(sim.Grid, 2 + H, 4.5 + H);
                Assert.IsTrue(TraitTestKit.Contains(ret.Cells, strip), at + "a cell of the strip");
                Assert.AreEqual(2, sim.Grid.Cells[strip]);
                AssertNear(V(5 + H, 5 + H - 6.0 * (ret.Time - 4.0 / 3.0)), ret.Point, 1e-9, at + "return point = the head at that instant");
                Assert.IsTrue(sim.Players[1].Home, at + "home again");
                Assert.AreEqual(1, sim.Players[1].Captures);
            });

            // Control: without the trait the land becomes neutral and the killer keeps trailing over it.
            Simulation classic = TrailingKiller(60, RuleTraits.Classic);
            var log = new EventLog(classic);
            RunUntilTime(classic, 1.8);
            Assert.AreEqual(0, log.Count(SimEventType.Return, 1), "classic: no return");
            Assert.IsFalse(classic.Players[1].Home);
        }

        [Test]
        public void KillInheritance_AChasedKillerReturnsAtThatInstantButCapturesNothing()
        {
            // The killer is cut at t = 1.5 (its spark would catch it at about 2.346 s); the inheritance at TrailCatchTime
            // makes it return: saved (v1.4), Chased, Cells empty, Margin > 0 (the spark is still on its trail). It keeps the
            // inherited land (an inheritance is not a capture) but the strip is not captured.
            TraitTestKit.CrossRate("chased killer", rate =>
            {
                Simulation sim = TrailingKiller(rate, TraitTestKit.One(TraitId.KillInheritance));
                sim.BeforeTick += s =>
                {
                    if (s.Tick == (long)System.Math.Round(1.5 * s.Config.TickRate)) s.DebugForceCut(1, 4.0, 2);
                };
                return sim;
            }, 1.8, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent ret = run.Log.Single(SimEventType.Return, 1);
                Assert.AreEqual(run.Log.Single(SimEventType.TerritoryInherited, 1).Time, ret.Time, at + "returns at the inheritance instant");
                Assert.IsTrue(ret.Chased, at + "chased");
                Assert.AreEqual(0, ret.Cells.Length, at + "a chased return captures nothing");
                Assert.That(ret.Margin, Is.GreaterThan(0.0), at + "the spark was still behind");
                Assert.IsTrue(sim.Players[1].Alive && sim.Players[1].Home, at + "saved");
                Assert.IsFalse(sim.Players[1].ExitWasCut, at + "cleared at the return");
                Assert.AreEqual(OwnerGrid.Neutral, sim.Grid.Cells[CellIndex(sim.Grid, 2 + H, 4.5 + H)], at + "the strip stays neutral");
                Assert.AreEqual(2, sim.Grid.Cells[CellIndex(sim.Grid, 4 + H, H)], at + "the inherited land is kept");
            });
        }

        [Test]
        public void KillInheritance_WithKillShieldTheChasedKillerLosesItsSparkAndItsLoopStaysLost()
        {
            Simulation sim = TrailingKiller(60, RuleTraits.Parse("KillInheritance;KillShield"));
            sim.BeforeTick += s =>
            {
                if (s.Tick == 90) s.DebugForceCut(1, 4.0, 2);
            };
            var log = new EventLog(sim);
            RunUntilTime(sim, 1.8);
            SimEvent shield = log.Single(SimEventType.ShieldStarted, 1);
            Assert.IsTrue(shield.Chased, "the shield extinguished the killer's spark");
            SimEvent ret = log.Single(SimEventType.Return, 1);
            Assert.AreEqual(shield.Time, ret.Time);
            Assert.IsTrue(ret.Chased, "ExitWasCut: a cut exit never captures");
            Assert.AreEqual(0, ret.Cells.Length);
            Assert.AreEqual(0.0, ret.Margin, "no spark left at the return");
            Assert.AreEqual(OwnerGrid.Neutral, sim.Grid.Cells[CellIndex(sim.Grid, 2 + H, 4.5 + H)], "the strip stays neutral");
        }

        [Test]
        public void KillInheritance_ShareKeepsTheCoreOfTheLandNearItsCentroid()
        {
            Simulation sim = HomeKiller(60, TraitTestKit.One(TraitId.KillInheritance, 0.5));
            var log = new EventLog(sim);
            RunUntilTime(sim, 1.2);
            int[] land = TraitTestKit.RectCells(sim.Grid, 0, -4, 8, 4);
            SimEvent inherited = log.Single(SimEventType.TerritoryInherited, 1);
            Assert.AreEqual(land.Length / 2, inherited.Cells.Length, "round(0.5 x 4096)");
            Assert.AreEqual(land.Length / 2, TraitTestKit.CountOwned(sim.Grid, land, 2));
            Assert.AreEqual(land.Length / 2, TraitTestKit.CountOwned(sim.Grid, land, OwnerGrid.Neutral));
            Assert.AreEqual(2, sim.Grid.Cells[CellIndex(sim.Grid, 4 + H, H)], "the center goes to the killer");
            Assert.AreEqual(OwnerGrid.Neutral, sim.Grid.Cells[CellIndex(sim.Grid, H, -4 + H)], "a corner stays neutral");
            for (int k = 1; k < inherited.Cells.Length; k++) Assert.That(inherited.Cells[k], Is.GreaterThan(inherited.Cells[k - 1]));
        }

        [Test]
        public void KillInheritance_ATerritoryLostEliminationIsNoKill()
        {
            // R9 (contract): A's return encloses all of B's land; B is eliminated with cause TerritoryLost, nobody inherits.
            var b = new SimBuilder(60);
            b.Config.Traits = TraitTestKit.One(TraitId.KillInheritance);
            b.AddRect(-8, -8, 0, 8, V(-4, H), West, new ConstantHeadingController(West));
            int bIdx = b.AddRect(6, -3, 9, 3, V(7 + H, -2.4375), North, new ConstantHeadingController(North));
            Simulation sim = b.Build();
            sim.DebugSetTrail(0, new[] { V(0, 6 + H), V(10 + H, 6 + H), V(10 + H, -6 + H), V(2.0925, -6 + H) });
            var log = new EventLog(sim);
            RunUntilTime(sim, 0.45);
            Assert.AreEqual(EliminationCause.TerritoryLost, log.Single(SimEventType.Eliminated, bIdx).Cause);
            Assert.AreEqual(0, log.Count(SimEventType.TerritoryInherited));
            Assert.AreEqual(0, sim.Players[0].Kills);
        }

        [Test]
        public void KillInheritance_ALastSurvivorTrailingOverTheInheritedLandReturnsBeforeTheRoundEnds()
        {
            // Two players: the kill ends the round in its own group (R19 g), so there is no later candidate pass; the
            // same-instant return of the killer (the inherited land is under its head) is applied before the round end
            // check, as that pass would. Found by the v1.1 balance rounds (Home != owner(Cell) at a last-survivor kill).
            TraitTestKit.CrossRate("last survivor over inherited land", rate =>
            {
                var sb = new SimBuilder(rate);
                sb.Config.Traits = TraitTestKit.One(TraitId.KillInheritance);
                sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
                sb.AddRect(-10, -4, 0, 4, V(-1 + H, 3 + H), North, Legs((North, 2), (East, 6), (South, 10)));
                Simulation sim = sb.Build();
                KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, TrailCatchTime);
                return sim;
            }, 1.8, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                Assert.IsTrue(sim.Ended, at + "ended");
                Assert.AreEqual(RoundEndReason.LastSurvivor, sim.Result.Reason);
                SimEvent ret = run.Log.Single(SimEventType.Return, 1);
                SimEvent ended = run.Log.Single(SimEventType.RoundEnded);
                Assert.AreEqual(ret.Time, ended.Time, at + "same instant");
                Assert.That(run.Log.IndexOf(ret), Is.LessThan(run.Log.IndexOf(ended)), at + "the return comes before the round end");
                Assert.IsFalse(ret.Chased);
                Assert.That(ret.Cells.Length, Is.GreaterThan(300), at + "the strip is captured");
                Assert.IsTrue(sim.Players[1].Home, at + "Home == (owner(Cell) == Id) holds at the end");
                Assert.AreEqual(sim.Grid.CountOf(2), sim.Result.FinalCells[1], at + "FinalCells include the inheritance and the capture");
            });
        }

        [Test]
        public void KillInheritance_ALastSurvivorRoundCountsTheInheritedLand()
        {
            // Two players: the kill ends the round (R19 g), after the inheritance (applied in the elimination step).
            var sb = new SimBuilder(60);
            sb.Config.Traits = TraitTestKit.One(TraitId.KillInheritance);
            sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
            sb.AddRect(-10, -4, 0, 4, V(-5 + H, H), North, new HomeCirclerController(V(-5, 0)));
            Simulation sim = sb.Build();
            KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, CatchTime);
            int killerCells = sim.Grid.CountOf(2), victimCells = sim.Grid.CountOf(1);
            RunUntilTime(sim, 1.2);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.LastSurvivor, sim.Result.Reason);
            Assert.AreEqual(new List<int> { 1 }, sim.Result.Winners);
            Assert.AreEqual(killerCells + victimCells, sim.Result.FinalCells[1], "the winner's FinalCells include the inherited land");
            Assert.AreEqual(victimCells, sim.Result.FinalCells[0]);
            Assert.AreEqual(new[] { 2, 1 }, sim.Result.Ranks);
        }
    }
}
