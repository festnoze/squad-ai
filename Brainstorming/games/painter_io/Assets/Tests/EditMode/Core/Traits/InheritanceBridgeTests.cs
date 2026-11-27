// Owned by inherit (rule v1.6, contract section 30, test id R22): single domain and kill inheritance bridge. In rounds with
// KillInheritance (the Feu set) the territory of every living player stays ONE 8-connected domain: inherited land that does
// not touch the killer's domain is joined by a band made of the kill line (the killer's trail from its exit to the cut and
// the victim's trail from the cut back to its land), or severed when no bridge can be made. Pure NUnit + PainterIO.Core
// (no UnityEngine), NUnit 3.5 features only.
//
// Geometry (contract 10.0 item 2, SimTestKit conventions: integer coordinates are cell edges, n + H is a cell-center line).
// The reproduction scenario: K (player 0, the killer) owns A = [-12, -4] x [-4, 4] and starts at (-4.9375, -1.9375) heading
// East with legs E 3, S 8, E 14, N 10: exit at x = -4 (t = 0.15625), South on x = -1.9375 from t = 0.5, East on y = -9.9375
// from t = 11/6, North on x = 12.0625 from t = 25/6, into B at y = -4 at about t = 5.14. V (player 1, the victim) owns
// B = [6, 14] x [-4, 4] and is teleported to a trail that leaves B at (10.0625, -4), goes South to y = -7.9375 and West to
// x = 2.0625, its head heading West. K's head comes within ContactRadius of V's trail at t = 1.395 (Q = (-1.9375, -7.3075),
// cut point P = (-1.9375, -7.9375), s_cut = 15.9375); V's spark (Feu: 2.1 x 6 = 12.6 u/s) catches V at t = 2.0571, while K
// is still out (on y = -9.9375): K inherits B, which does not touch A. Players 2 and 3 idle in far corners.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class InheritanceBridgeTests
    {
        /// <summary>The kill instant of the reproduction scenario (catch of V's spark): 1.395 + 4.37 / 6.6.</summary>
        private const double ReproKill = 0.5 + 5.37 / 6.0 + 4.37 / 6.6;

        /// <summary>The kill instant of the closed-killer scenario: 1.22833 + 16.87 / 6.6.</summary>
        private const double ClosedKill = 0.5 + 4.37 / 6.0 + 16.87 / 6.6;

        // ------------------------------------------------------------------------------------------------------------
        // Scenario builders

        private static HeadingScheduleController KillerPath() => Legs((East, 3), (South, 8), (East, 14), (North, 10));

        /// <summary>
        /// The reproduction scenario (header). third: player 2 owns C = [1.5, 5.5] x [-9, -2] across V's trail and circles
        /// at home around (3.5, -4) (else it idles in a corner). killer: K's controller (null = the scripted legs).
        /// </summary>
        private static Simulation Repro(int rate, InheritanceBridgeRule rule, bool third = false, IController killer = null)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = TraitTestKit.FireV11;
            sb.Config.InheritanceBridge = rule;
            // Rule v1.8 (contract 32): InheritanceBridge = Off reproduces the pre-v1.6 island only with SingleDomain = Off
            // (with the v1.8 default, Off behaves as AnchorOnly).
            if (rule == InheritanceBridgeRule.Off) sb.Config.SingleDomain = SingleDomainRule.Off;
            sb.AddRect(-12, -4, -4, 4, V(-5 + H, -2 + H), East, killer ?? KillerPath());
            sb.AddRect(6, -4, 14, 4, V(10 + H, H), West, new ConstantHeadingController(West));
            if (third) sb.AddRect(1.5, -9, 5.5, -2, V(3.5, -4 + 1.5), West, new HomeCirclerController(V(3.5, -4)));
            else sb.AddIdle(IdleCorners[1]);
            sb.AddIdle(IdleCorners[0]);
            Simulation sim = sb.Build();
            sim.DebugSetTrail(1, new[] { V(10 + H, -4), V(10 + H, -8 + H), V(2 + H, -8 + H) });
            return sim;
        }

        /// <summary>
        /// The closed-killer scenario: K (player 0, land A) runs E 3, S 6, W 4, N 20: it touches V's trail (South leg on
        /// x = -1.9375, contact at t = 1.2283, Q = (-1.9375, -6.3075)) and comes home into A at t = 2.8229, its loop
        /// enclosing the strip between its trail and A (the South leg becomes its territory). V (player 1, land B) is
        /// teleported to a trail that leaves B at (10.0625, -4), goes South to y = -6.9375 and West to x = -11.4375, then
        /// runs W 3 and North: its spark catches it at ClosedKill = 3.7844, while K is home. breakQ: at t = 3 player 2's
        /// land is painted over K's cells around Q (a stand-in for a capture of the killer's former trail).
        /// </summary>
        private static Simulation Closed(int rate, InheritanceBridgeRule rule, bool breakQ)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = TraitTestKit.FireV11;
            sb.Config.InheritanceBridge = rule;
            if (rule == InheritanceBridgeRule.Off) sb.Config.SingleDomain = SingleDomainRule.Off;
            sb.AddRect(-12, -4, -4, 4, V(-5 + H, -2 + H), East, Legs((East, 3), (South, 6), (West, 4), (North, 20)));
            sb.AddRect(6, -4, 14, 4, V(10 + H, H), West, Legs((West, 3), (North, 40)));
            sb.AddIdle(IdleCorners[1]);
            sb.AddIdle(IdleCorners[3]);
            Simulation sim = sb.Build();
            sim.DebugSetTrail(1, new[] { V(10 + H, -4), V(10 + H, -7 + H), V(-11.5 + H, -7 + H) });
            if (breakQ)
            {
                bool done = false;
                sim.BeforeTick += s =>
                {
                    if (done || s.Time < 3.0 - 1e-9) return;
                    done = true;
                    FillRect(s.Grid, s.Players[2].Id, -2.75, -7.25, -1.25, -5.5);
                };
            }
            return sim;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Independent oracle: 8-connected pieces per player (scan + flood, no Core code).

        /// <summary>Number of 8-connected pieces of each player id 1..players (index = id).</summary>
        internal static int[] PieceCounts(OwnerGrid g, int players)
        {
            int size = g.Size;
            byte[] cells = g.Cells;
            var seen = new bool[cells.Length];
            var counts = new int[players + 1];
            var stack = new Stack<int>();
            for (int c = 0; c < cells.Length; c++)
            {
                byte o = cells[c];
                if (seen[c] || o == OwnerGrid.Neutral || o == OwnerGrid.Void || o > players) continue;
                counts[o]++;
                seen[c] = true;
                stack.Push(c);
                while (stack.Count > 0)
                {
                    int x = stack.Pop();
                    int xi = x % size, xj = x / size;
                    for (int dj = -1; dj <= 1; dj++)
                    {
                        for (int di = -1; di <= 1; di++)
                        {
                            int ni = xi + di, nj = xj + dj;
                            if ((di == 0 && dj == 0) || ni < 0 || nj < 0 || ni >= size || nj >= size) continue;
                            int nc = nj * size + ni;
                            if (seen[nc] || cells[nc] != o) continue;
                            seen[nc] = true;
                            stack.Push(nc);
                        }
                    }
                }
            }
            return counts;
        }

        /// <summary>Fails when a living player owns more than one 8-connected piece.</summary>
        internal static void AssertSingleDomain(Simulation sim, string at)
        {
            int[] counts = PieceCounts(sim.Grid, sim.Players.Count);
            for (int i = 0; i < sim.Players.Count; i++)
            {
                if (sim.Players[i].Alive && counts[i + 1] > 1)
                    Assert.Fail(at + "player " + i + " owns " + counts[i + 1] + " separate pieces (t = " + TraitTestKit.F(sim.Time) + ")");
            }
        }

        private static int Pieces(Simulation sim, int player) => PieceCounts(sim.Grid, sim.Players.Count)[player + 1];

        private static byte Owner(Simulation sim, double x, double y) => sim.Grid.Cells[CellIndex(sim.Grid, x, y)];

        // ------------------------------------------------------------------------------------------------------------
        // 1. The reproduction: with the pre-v1.6 behaviour the closure into the inherited land captures nothing

        [Test]
        public void R22_ReproductionOffKeepsTwoPiecesAndTheClosureIntoTheInheritedLandCapturesNothing()
        {
            // Root cause (docs/inherit_fix.json): the inherited land B is an island; driving the trail from A into B is a
            // return (B's cells are own) but walls = A + B + trail enclose nothing (the gap between A and B stays open),
            // section 7 gives no Interior, hence no Rim: the trail is dropped and the domain stays in two pieces.
            Simulation sim = Repro(60, InheritanceBridgeRule.Off);
            var log = new EventLog(sim);
            RunUntilTime(sim, 5.3);
            SimEvent inherited = log.Single(SimEventType.TerritoryInherited, 0);
            Assert.That(inherited.Time, Is.EqualTo(ReproKill).Within(1e-6), "the kill time");
            Assert.AreEqual(0, log.Count(SimEventType.InheritanceBridged), "Off: no bridge");
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsFalse(ret.Chased);
            Assert.AreEqual(0, ret.Cells.Length, "Off: the closure into B captures nothing (the bug)");
            Assert.AreEqual(2, Pieces(sim, 0), "Off: A and B stay two pieces");
            Assert.AreEqual(OwnerGrid.Neutral, Owner(sim, 5 + H, -10 + H), "Off: the trail did not become domain");
            Assert.AreEqual(0, sim.Players[0].InheritanceBridges);
        }

        // ------------------------------------------------------------------------------------------------------------
        // 2. The bridge with the killer still out: band, trail cut at Q, the closure into B then captures

        [Test]
        public void R22_BridgeWithTheKillerStillOutSplitsItsTrailAndTheClosureIntoTheInheritedLandCaptures()
        {
            TraitTestKit.CrossRate("bridge, killer out", rate => Repro(rate, InheritanceBridgeRule.Bridge), 5.3, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 0);
                SimEvent bridge = run.Log.Single(SimEventType.InheritanceBridged, 0);
                Assert.That(inherited.Time, Is.EqualTo(ReproKill).Within(1e-6), at + "kill time");
                Assert.AreEqual(inherited.Time, bridge.Time, at + "the bridge at the kill instant");
                Assert.AreEqual(run.Log.IndexOf(inherited) + 1, run.Log.IndexOf(bridge), at + "right after the inheritance");
                Assert.AreEqual(1, bridge.Other, at + "Other = the victim");
                AssertNear(inherited.Point, bridge.Point, 1e-12, at + "Point = the victim's head at the kill");
                Assert.That(bridge.Cells.Length, Is.GreaterThan(500), at + "band cells");
                for (int k = 1; k < bridge.Cells.Length; k++) Assert.That(bridge.Cells[k], Is.GreaterThan(bridge.Cells[k - 1]), at + "ascending");
                Assert.AreEqual(0, run.Log.Count(SimEventType.TerritorySevered), at + "nothing severed: the band joined everything");
                Assert.AreEqual(1, sim.Players[0].InheritanceBridges);

                SimEvent ret = run.Log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.GreaterThan(5.0), at + "the closure into B");
                Assert.IsFalse(ret.Chased);
                Assert.That(ret.Cells.Length, Is.GreaterThan(1000), at + "the loop between the band and the trail is captured");
                Assert.AreEqual(sim.Players[0].Id, Owner(sim, 5 + H, -9 + H), at + "a cell enclosed below the band");
                Assert.AreEqual(sim.Players[0].Id, Owner(sim, 11 + H, -6 + H), at + "a cell enclosed right of the band");
                Assert.AreEqual(sim.Players[0].Id, Owner(sim, 5 + H, -10 + H), at + "the trail became domain");
                Assert.AreEqual(1, Pieces(sim, 0), at + "one domain");
                Assert.IsTrue(sim.Players[0].Home);
            }, s => AssertSingleDomain(s, "every tick: "));
        }

        [Test]
        public void R22_TheBandIsTheKillLineWithThicknessAndTheKillersTrailRestartsAtTheCutPoint()
        {
            Simulation sim = Repro(60, InheritanceBridgeRule.Bridge);
            var log = new EventLog(sim);
            RunUntilTime(sim, ReproKill + 0.02);
            byte k = sim.Players[0].Id;
            SimEvent bridge = log.Single(SimEventType.InheritanceBridged, 0);
            // (a) the killer's trail from its exit to Q, (b) the link Q-P, (c) the victim's trail from P back to B.
            Assert.AreEqual(k, Owner(sim, -3 + H, -2 + H), "(a) the killer's East leg");
            Assert.AreEqual(k, Owner(sim, -2 + H, -5 + H), "(a) the killer's South leg");
            Assert.AreEqual(k, Owner(sim, -2 + H, -7.5 + H), "(b) the link Q-P");
            Assert.AreEqual(k, Owner(sim, 5 + H, -8 + H), "(c) the victim's West leg");
            Assert.AreEqual(k, Owner(sim, 10 + H, -6 + H), "(c) the victim's South leg up to B");
            // The burnt part of the victim's trail (from P to its head) is not part of the line.
            Assert.AreEqual(OwnerGrid.Neutral, Owner(sim, -4 + H, -8 + H), "the burnt part beyond P");
            // Thickness: cells whose center lies within 0.45 u of the line: 7 cells across a straight leg, never one.
            int across = 0;
            for (int j = -6; j <= 6; j++)
            {
                if (Owner(sim, 5 + H, -8 + H + j * 0.125) == k) across++;
            }
            Assert.AreEqual(7, across, "7 cells across the band (half width 0.45 u)");
            foreach (int c in bridge.Cells) Assert.AreEqual(k, sim.Grid.Cells[c], "every band cell is the killer's");
            Assert.AreEqual(1, Pieces(sim, 0), "one domain right after the kill");

            // The trail: the part from the exit to Q became territory; the rest is still the active trail, starting at Q.
            PlayerState killer = sim.Players[0];
            Assert.IsFalse(killer.Home, "still out");
            Assert.IsFalse(killer.ExitWasCut);
            AssertNear(V(-2 + H, -8 + H + 0.63), killer.Trail.Points[0], 1e-9, "the trail now starts at Q");
            Assert.That(killer.Trail.Length, Is.EqualTo(2.63 + 6.0 * (sim.Time - 11.0 / 6.0)).Within(1e-9), "Q to the head");
            AssertNear(killer.Pos, killer.Trail.Points[killer.Trail.Count - 1], 1e-9, "trail end == Pos");
        }

        [Test]
        public void R22_TheRestOfTheTrailKeepsWorking_ASparkRunsOnTheSplitTrail()
        {
            // After the bridge, player 2 cuts the killer's remaining trail at s = 4 (forced at t = 2.5, a common tick time):
            // the spark runs on the split trail (L(2.5) = 2.63 + 4 = 6.63), so it catches the killer at 2.5 + 2.63 / 6.6.
            TraitTestKit.CrossRate("spark on the split trail", rate =>
            {
                Simulation sim = Repro(rate, InheritanceBridgeRule.Bridge);
                bool done = false;
                sim.BeforeTick += s =>
                {
                    if (done || s.Time < 2.5 - 1e-9) return;
                    done = true;
                    s.DebugForceCut(0, 4.0, 2);
                };
                return sim;
            }, 3.2, run =>
            {
                SimEvent caught = run.Log.Single(SimEventType.SparkCaught, 0);
                Assert.That(caught.Time, Is.EqualTo(2.5 + 2.63 / 6.6).Within(1e-6), run.Rate + " Hz: closed form on the split trail");
                Assert.AreEqual(2, caught.Other);
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // 3. The killer already closed: its trail is domain, the band starts at Q

        [Test]
        public void R22_BridgeWhenTheKillerAlreadyClosedStartsAtItsFormerTrail()
        {
            TraitTestKit.CrossRate("bridge, killer closed", rate => Closed(rate, InheritanceBridgeRule.Bridge, false), 4.0, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent ret = run.Log.Single(SimEventType.Return, 0);
                Assert.That(ret.Time, Is.EqualTo(2.0 + 1.0 / 6.0 + 3.9375 / 6.0).Within(1e-6), at + "the killer closed first");
                Assert.That(ret.Cells.Length, Is.GreaterThan(0));
                SimEvent bridge = run.Log.Single(SimEventType.InheritanceBridged, 0);
                Assert.That(bridge.Time, Is.EqualTo(ClosedKill).Within(1e-6), at + "kill time");
                Assert.IsTrue(sim.Players[0].Home, at + "home at the kill: no trail to split");
                byte k = sim.Players[0].Id;
                Assert.IsTrue(TraitTestKit.Contains(bridge.Cells, CellIndex(sim.Grid, -1.6875, -7 + H)), at + "the link from Q (new cell)");
                Assert.AreEqual(k, Owner(sim, -1.6875, -7 + H), at + "the link from Q");
                Assert.AreEqual(k, Owner(sim, 5 + H, -7 + H), at + "the victim's West leg");
                Assert.AreEqual(k, Owner(sim, 10 + H, -5 + H), at + "the victim's South leg up to B");
                Assert.AreEqual(k, Owner(sim, 10 + H, H), at + "the inherited land");
                Assert.AreEqual(OwnerGrid.Neutral, Owner(sim, -8 + H, -7 + H), at + "the burnt part beyond P");
                Assert.AreEqual(1, Pieces(sim, 0), at + "one domain");
                Assert.AreEqual(0, run.Log.Count(SimEventType.TerritorySevered), at);
            }, s => AssertSingleDomain(s, "every tick: "));
        }

        // ------------------------------------------------------------------------------------------------------------
        // 4. A band over a third player's land is a capture for that player (rule v1.5 applies)

        [Test]
        public void R22_TheBandOverAThirdPlayersLandIsACaptureAndSplitsItByTheV15Rule()
        {
            TraitTestKit.CrossRate("band over a third player", rate => Repro(rate, InheritanceBridgeRule.Bridge, true), ReproKill + 0.05, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent bridge = run.Log.Single(SimEventType.InheritanceBridged, 0);
                byte k = sim.Players[0].Id, c = sim.Players[2].Id;
                Assert.AreEqual(k, Owner(sim, 3.5, -8 + H), at + "the band crosses C's land");
                Assert.IsTrue(TraitTestKit.Contains(bridge.Cells, CellIndex(sim.Grid, 3.5, -8 + H)), at + "listed in the band");
                SimEvent severed = run.Log.Single(SimEventType.TerritorySevered, 2);
                Assert.AreEqual(0, severed.Other, at + "the killer is the cutter");
                Assert.AreEqual(-1, severed.Recipient, at + "Neutral (default)");
                Assert.That(run.Log.IndexOf(severed), Is.GreaterThan(run.Log.IndexOf(bridge)), at + "after the bridge");
                Assert.AreEqual(OwnerGrid.Neutral, Owner(sim, 3.5, -8.75), at + "C's south strip (without its pawn) is severed");
                Assert.AreEqual(c, Owner(sim, 3.5, -4 + H), at + "C keeps the piece of its pawn");
                Assert.IsTrue(sim.Players[2].Alive && sim.Players[2].Home);
                Assert.AreEqual(1, Pieces(sim, 2), at + "C keeps one domain");
                Assert.AreEqual(1, Pieces(sim, 0), at + "the killer has one domain");
            }, s => AssertSingleDomain(s, "every tick: "));
        }

        // ------------------------------------------------------------------------------------------------------------
        // 5. Fallbacks: no bridge, the killer keeps the piece of its anchor and the rest is severed (neutral)

        [Test]
        public void R22_AChasedKillerMakesNoBridgeAndKeepsItsAnchorPieceOnly()
        {
            // The killer's trail is cut at t = 11/6 (forced, by player 2): v1.4, a cut exit never becomes territory.
            TraitTestKit.CrossRate("chased killer", rate =>
            {
                Simulation sim = Repro(rate, InheritanceBridgeRule.Bridge);
                bool done = false;
                sim.BeforeTick += s =>
                {
                    if (done || s.Time < 11.0 / 6.0 - 1e-9) return;
                    done = true;
                    s.DebugForceCut(0, 0.5, 2);
                };
                return sim;
            }, ReproKill + 0.05, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 0);
                Assert.AreEqual(0, run.Log.Count(SimEventType.InheritanceBridged), at + "no bridge");
                SimEvent severed = run.Log.Single(SimEventType.TerritorySevered, 0);
                Assert.AreEqual(-1, severed.Other, at + "the single-domain rule: no cutter");
                Assert.AreEqual(-1, severed.Recipient);
                Assert.AreEqual(inherited.Time, severed.Time);
                Assert.AreEqual(run.Log.IndexOf(inherited) + 1, run.Log.IndexOf(severed), at + "right after the inheritance");
                Assert.IsTrue(SameCells(inherited.Cells, severed.Cells), at + "exactly the inherited land is severed");
                foreach (int cell in severed.Cells)
                {
                    Assert.AreEqual(OwnerGrid.Neutral, sim.Grid.Cells[cell], at + "neutral");
                    Assert.IsFalse(sim.View.IsScorched(cell), at + "never scorched");
                }
                Assert.AreEqual(sim.Players[0].Id, Owner(sim, -8 + H, H), at + "the killer keeps A (its exit cell)");
                PlayerState killer = sim.Players[0];
                Assert.IsTrue(killer.ExitWasCut && killer.Spark != null, at + "still chased");
                AssertNear(V(-4, -2 + H), killer.Trail.Points[0], 1e-12, at + "the trail is untouched");
                Assert.AreEqual(1, Pieces(sim, 0));
            });
        }

        [Test]
        public void R22_ABrokenBridgeSeversTheInheritedLand()
        {
            // The killer closed, then its former trail cells around Q were taken (painted for player 2 at t = 3): the line
            // it made is no longer its land, so no band can start there.
            TraitTestKit.CrossRate("broken bridge", rate => Closed(rate, InheritanceBridgeRule.Bridge, true), 4.0, run =>
            {
                Simulation sim = run.Sim;
                string at = run.Rate + " Hz: ";
                SimEvent inherited = run.Log.Single(SimEventType.TerritoryInherited, 0);
                Assert.AreEqual(0, run.Log.Count(SimEventType.InheritanceBridged), at + "no bridge");
                SimEvent severed = run.Log.Single(SimEventType.TerritorySevered, 0);
                Assert.IsTrue(SameCells(inherited.Cells, severed.Cells), at + "the inherited land is severed");
                Assert.AreEqual(OwnerGrid.Neutral, Owner(sim, 10 + H, H), at + "B is neutral");
                Assert.AreEqual(sim.Players[0].Id, Owner(sim, -8 + H, H), at + "the killer keeps A (home: its pawn cell)");
                Assert.AreEqual(1, Pieces(sim, 0));
            });
        }

        [Test]
        public void R22_AnchorOnlyKeepsOneDomainWithoutTheBand()
        {
            Simulation sim = Repro(60, InheritanceBridgeRule.AnchorOnly);
            var log = new EventLog(sim);
            RunUntilTime(sim, ReproKill + 0.05, true, s => AssertSingleDomain(s, "AnchorOnly: "));
            SimEvent inherited = log.Single(SimEventType.TerritoryInherited, 0);
            Assert.AreEqual(0, log.Count(SimEventType.InheritanceBridged));
            Assert.IsTrue(SameCells(inherited.Cells, log.Single(SimEventType.TerritorySevered, 0).Cells));
            AssertNear(V(-4, -2 + H), sim.Players[0].Trail.Points[0], 1e-12, "the trail is untouched");
            Assert.AreEqual(OwnerGrid.Neutral, Owner(sim, 5 + H, -8 + H), "no band");
        }

        [Test]
        public void R22_AKillerDyingInTheSameGroupLeavesTheLandNeutralAndScorched()
        {
            // Existing rule (section 7): both players are caught in one group, nothing is inherited, the freed land stays
            // neutral and ScorchedEarth scorches it; v1.6 adds nothing (no bridge, no severance).
            TraitTestKit.CrossRate("mutual kill", rate =>
            {
                var sb = new SimBuilder(rate);
                sb.Config.Traits = TraitTestKit.FireV11;
                sb.AddRect(0, -4, 8, 4, V(4 + H, H), East, new ConstantHeadingController(East));
                sb.AddRect(-10, -4, -2, 4, V(-5 + H, H), East, new ConstantHeadingController(East));
                sb.AddIdle(IdleCorners[2]);
                sb.AddIdle(IdleCorners[1]);
                Simulation sim = sb.Build();
                KillTestKit.ForceChase(sim, 0, 1, V(-15 + H, -15 + H), 10.0, 1.013);
                KillTestKit.ForceChase(sim, 1, 0, V(-15 + H, -20 + H), 10.0, 1.013);
                return sim;
            }, 1.2, run =>
            {
                string at = run.Rate + " Hz: ";
                SimEvent a = run.Log.Single(SimEventType.Eliminated, 0), b = run.Log.Single(SimEventType.Eliminated, 1);
                Assert.AreEqual(a.Time, b.Time, at + "one group");
                Assert.AreEqual(0, run.Log.Count(SimEventType.TerritoryInherited));
                Assert.AreEqual(0, run.Log.Count(SimEventType.InheritanceBridged));
                Assert.AreEqual(0, run.Log.Count(SimEventType.TerritorySevered));
                foreach (int c in a.Cells) Assert.IsTrue(run.Sim.View.IsScorched(c), at + "scorched");
                foreach (int c in b.Cells) Assert.IsTrue(run.Sim.View.IsScorched(c), at + "scorched");
            });
        }

        // ------------------------------------------------------------------------------------------------------------
        // 6. Bots: every own cell is home after an inheritance

        /// <summary>Delegates to first until 'at' (sim time), then to then.</summary>
        private sealed class SwitchController : IController
        {
            private readonly IController first, then;
            private readonly double at;

            public SwitchController(IController first, double at, IController then)
            {
                this.first = first;
                this.at = at;
                this.then = then;
            }

            public double? DesiredHeading(SimView view, int playerIndex)
            {
                return view.Time < at - 1e-9 ? first.DesiredHeading(view, playerIndex) : then.DesiredHeading(view, playerIndex);
            }
        }

        [Test]
        public void R22_ABotGoesHomeIntoTheJoinedLandAfterAnInheritance()
        {
            // K is scripted until it cut V (t = 1.6), then a Balanced bot drives it: it heads for its nearest own cell (A at
            // first). The kill at ReproKill bridges B to A through the band, which is now its nearest own cell: the bot
            // closes into the joined land instead of going back to A.
            var bot = new BotController(BotPersonality.Preset(BotStyle.Balanced), 11UL);
            Simulation sim = Repro(60, InheritanceBridgeRule.Bridge, false, new SwitchController(KillerPath(), 1.6, bot));
            var log = new EventLog(sim);
            RunUntilTime(sim, ReproKill + 0.01);
            Assert.IsFalse(sim.Players[0].Home, "still out at the kill");
            Assert.AreEqual(BotMode.Return, bot.Mode, "the bot heads home");
            Assert.IsTrue(RunUntil(sim, s => s.Players[0].Home, 4.0), "the bot gets home");
            Assert.AreEqual(1, log.Count(SimEventType.InheritanceBridged, 0), "the bridge happened");
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.That(ret.Time, Is.GreaterThan(ReproKill), "the bot returned after the bridge");
            SimEvent bridge = log.Single(SimEventType.InheritanceBridged, 0);
            SimEvent inherited = log.Single(SimEventType.TerritoryInherited, 0);
            int cell = sim.Players[0].Cell;
            Assert.IsTrue(TraitTestKit.Contains(bridge.Cells, cell) || TraitTestKit.Contains(inherited.Cells, cell),
                          "the return cell belongs to the band or to the inherited land, not to A");
            Assert.AreEqual(1, Pieces(sim, 0));
        }

        // ------------------------------------------------------------------------------------------------------------
        // 7. The invariant in long Fire bot rounds, determinism, and the Off option

        /// <summary>(seed, rate) of the invariant rounds; each runs with the balanced lineup and with four Aggressive bots.</summary>
#if UNITY_5_3_OR_NEWER
        private static readonly int[][] InvariantRounds = { new[] { 1, 60 } };
#else
        private static readonly int[][] InvariantRounds =
        {
            new[] { 1, 60 }, new[] { 2, 60 }, new[] { 3, 60 }, new[] { 4, 60 }, new[] { 5, 30 }, new[] { 6, 144 },
        };
#endif

        private static Simulation AggressiveRound(ulong seed, RuleTraits traits, int rate)
        {
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++) controllers[i] = new BotController(BotPersonality.Preset(BotStyle.Aggressive), BotTests.BotSeed(seed, i));
            var config = new SimConfig { Seed = seed, TickRate = rate, LassoEnabled = true, Traits = traits };
            return new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
        }

        [Test]
        public void R22_NoLivingPlayerEverOwnsTwoPiecesInFireBotRounds()
        {
            int rounds = 0, bridges = 0, severances = 0, kills = 0, checks = 0;
            foreach (int[] row in InvariantRounds)
            {
                ulong seed = (ulong)row[0];
                int rate = row[1];
                {
                    for (int lineup = 0; lineup < 2; lineup++)
                    {
                        Simulation sim = lineup == 0 ? TraitTestKit.BotRound(seed, TraitTestKit.FireV11, true, rate) : AggressiveRound(seed, TraitTestKit.FireV11, rate);
                        string label = (lineup == 0 ? "balanced" : "aggressive") + " seed " + seed + " " + rate + " Hz: ";
                        sim.EventRaised += e =>
                        {
                            if (e.Type == SimEventType.InheritanceBridged) bridges++;
                            if (e.Type == SimEventType.TerritorySevered && e.Other < 0) severances++;
                            if (e.Type == SimEventType.SparkCaught) kills++;
                        };
                        int version = sim.Grid.Version;
                        while (!sim.Ended)
                        {
                            sim.Step();
                            TraitTestKit.AssertTraitInvariants(sim);
                            if (sim.Grid.Version == version) continue;
                            version = sim.Grid.Version;
                            AssertSingleDomain(sim, label);
                            checks++;
                        }
                        rounds++;
                    }
                }
            }
            string summary = rounds + " rounds, " + kills + " kills, " + bridges + " bridges, " + severances + " single-domain severances, "
                             + checks + " grid checks";
            TestContext.WriteLine(summary);
#if !UNITY_5_3_OR_NEWER
            Assert.That(bridges, Is.GreaterThan(0), "bridges happened: " + summary);
#endif
        }

        [Test]
        public void R22_SameSeedSameHashWithTheBridge()
        {
            Simulation a = AggressiveRound(2UL, TraitTestKit.FireV11, 60), b = AggressiveRound(2UL, TraitTestKit.FireV11, 60);
            int bridges = 0;
            a.EventRaised += e => { if (e.Type == SimEventType.InheritanceBridged) bridges++; };
            while (!a.Ended)
            {
                a.Step();
                b.Step();
                if (a.Tick % 15 == 0 || a.Ended) Assert.AreEqual(a.StateHash(), b.StateHash(), "twin StateHash at tick " + a.Tick);
            }
            Assert.IsTrue(b.Ended);
            TestContext.WriteLine("bridges in the twin round: " + bridges);
        }

        /// <summary>
        /// Rolling hashes of Feu v1.1 bot rounds (TraitTestKit.RollingRoundHash every 30 ticks): the pre-v1.6 value, which
        /// SimConfig.InheritanceBridge = Off must reproduce exactly (the v1.6 code is fully switchable), and the value of
        /// the default rules (docs/inherit_fix.json lists them).
        /// </summary>
        private static readonly object[] FireRows =
        {
            new object[] { 1UL, 60, true, 0x982984A543ECCFE4UL, 0x6A081F4785E9DCEBUL },
            new object[] { 3UL, 60, false, 0xD9E2762A577C962CUL, 0x3B68A996FF6CCED3UL },
            new object[] { 4UL, 30, true, 0x1D2C63CC32B1A93BUL, 0x444396D4DF17FBAAUL },
            new object[] { 5UL, 144, true, 0x3B965B4C4764194FUL, 0xFABA4ABCAD0A5181UL },
        };

        [TestCaseSource(nameof(FireRows))]
        public void R22_OffReproducesThePreV16FireHashesAndTheDefaultIsPinned(ulong seed, int rate, bool lasso, ulong preV16, ulong v16)
        {
            // Rule v1.8 (contract 32): both columns are read with SimConfig.SingleDomain = Off (the v1.6 rules); the v1.8
            // default values of these rounds are pinned by SingleDomainTests (R23).
            Assert.AreEqual(preV16.ToString("X16"), TraitTestKit.RollingRoundHash(OffRound(seed, lasso, rate, InheritanceBridgeRule.Off), 30, false).ToString("X16"),
                            "InheritanceBridge = Off reproduces the pre-v1.6 Feu hash");
            Assert.AreEqual(v16.ToString("X16"), TraitTestKit.RollingRoundHash(OffRound(seed, lasso, rate, InheritanceBridgeRule.Bridge), 30, false).ToString("X16"),
                            "the rule v1.6 default (Bridge, SingleDomain = Off)");
        }

        /// <summary>A Feu v1.1 bot round with the given bridge rule and SimConfig.SingleDomain = Off (the v1.6 rules).</summary>
        internal static Simulation OffRound(ulong seed, bool lasso, int rate, InheritanceBridgeRule bridge = InheritanceBridgeRule.Off)
        {
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++)
                controllers[i] = new BotController(BotPersonality.Preset(TraitTestKit.Lineup[i]), BotTests.BotSeed(seed, i));
            var config = new SimConfig
            {
                Seed = seed, TickRate = rate, LassoEnabled = lasso, Traits = TraitTestKit.FireV11, InheritanceBridge = bridge,
                SingleDomain = SingleDomainRule.Off,
            };
            return new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
        }

        [Test]
        public void R22_TheRuleBelongsToTheKillInheritancePath()
        {
            var cfg = new SimConfig();
            Assert.AreEqual(InheritanceBridgeRule.Bridge, cfg.InheritanceBridge, "Bridge is the default");
            Assert.AreEqual(0.45, cfg.InheritanceBandHalfWidth, "half width 0.45 u");
            Assert.AreEqual(17, (int)SimEventType.InheritanceBridged, "appended at the end");
            // Rule v1.8 (contract 32) made the single domain a core rule (SingleDomainTests); with SingleDomain = Off the
            // v1.6 rule is back on the KillInheritance path only.
            Func<RuleTraits, Simulation> v16 = traits =>
            {
                var controllers = new IController[] { null, null };
                return new Simulation(new SimConfig { Traits = traits, SingleDomain = SingleDomainRule.Off }, controllers);
            };
            Assert.IsFalse(v16(RuleTraits.Classic).View.SingleDomain, "classic");
            Assert.IsFalse(v16(TraitTestKit.Fire).View.SingleDomain, "Feu without KillInheritance");
            Assert.IsFalse(v16(TraitTestKit.LiquidV11).View.SingleDomain, "Liquide v1.1");
            Assert.IsFalse(v16(TraitTestKit.ElectricV11).View.SingleDomain, "Electricite v1.1");
            Assert.IsFalse(v16(TraitTestKit.One(TraitId.KillInheritance, 0.0)).View.SingleDomain, "Share 0");
            Assert.IsTrue(v16(TraitTestKit.FireV11).View.SingleDomain, "Feu v1.1");
            Simulation off = OffRound(1UL, true, 60);
            Assert.IsFalse(off.View.SingleDomain, "Off");
            Assert.IsTrue(TraitTestKit.BotRound(1UL, RuleTraits.Classic, true).View.SingleDomain, "v1.8 default: classic too");
        }
    }
}
