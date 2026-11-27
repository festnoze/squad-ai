// Owned by severed (rule v1.5, contract section 29, test id R21). When a capture cuts a living rival's territory into
// separate pieces, the rival keeps only the piece where it is; the other pieces of that split become neutral (default) or
// the cutter's. Pure NUnit + PainterIO.Core (no UnityEngine), NUnit 3.5 features only.
//
// Geometry (contract 10.0 item 2, SimTestKit conventions): integer coordinates are cell edges, n + H is a cell-center line.
// The corridor scenario: A (the cutter) owns [-12, -4] x [-8, 8] and starts at (-4.9375, 1.0625) heading East with legs
// E 11, S 2, W 11: exit at x = -4 (t = 0.15625), return at x = -4 at t = 23.0625 / 6 = 3.84375 s (not a tick time at 30,
// 60 or 144 Hz). The loop encloses the cell rows y = -0.9375 .. 1.0625 (17 rows) from x = -4 to x = 6.125, across the
// whole width of B, which owns [-4, 4] x [-6, 6] (64 columns): B keeps its band-free rows as two pieces, NORTH (rows
// 1.1875 .. 5.9375, 39 rows, 2496 cells) and SOUTH (rows -5.9375 .. -1.0625, 40 rows, 2560 cells, the larger one).
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public class SeveredTerritoryTests
    {
        private const double H = SimTestKit.H;
        private const double East = SimTestKit.East, West = SimTestKit.West, North = SimTestKit.North, South = SimTestKit.South;

        /// <summary>A's return time in the corridor scenario.</summary>
        private const double CorridorReturn = 23.0625 / 6.0;

        private const int NorthCells = 39 * 64, SouthCells = 40 * 64, BandCells = 17 * 64;

        private static Vec2d V(double x, double y) => new Vec2d(x, y);

        // ------------------------------------------------------------------------------------------------------------
        // Scenario builders

        /// <summary>How B moves in the corridor scenario (public: it is a test case parameter).</summary>
        public enum Victim { HomeNorth, TrailingFromSouth, InTheBand, HomeFarIsland }

        private sealed class Corridor
        {
            public Simulation Sim;
            public SimTestKit.EventLog Log;
            public int A, B;
            public int[] NorthPiece, SouthPiece, Band;

            public void RunUntil(double time, bool traitInvariants = false)
            {
                int guard = 0;
                while (!Sim.Ended && Sim.Time < time - 1e-9)
                {
                    Sim.Step();
                    SimTestKit.AssertInvariants(Sim);
                    if (traitInvariants) TraitTestKit.AssertTraitInvariants(Sim);
                    AssertSeveredInvariants(Sim);
                    if (++guard > 1000000) Assert.Fail("run did not terminate");
                }
            }
        }

        /// <summary>
        /// The corridor scenario. cutterFirst: A is player 0 and B player 1 (else B is 0 and A is 1). victim: how B moves.
        /// HomeFarIsland: B's main land is a disc at (0, 20) where it circles, and the [-4, 4] x [-6, 6] rectangle is an island.
        /// islandFar: B also owns the far island [10, 14] x [10, 14].
        /// </summary>
        private static Corridor BuildCorridor(int rate, SeveredTerritoryRule rule, Victim victim, bool cutterFirst = true,
                                              int humanIndex = -1, bool islandFar = false, RuleTraits traits = null)
        {
            var sb = new SimTestKit.SimBuilder(rate);
            sb.Config.SeveredTerritory = rule;
            if (traits != null) sb.Config.Traits = traits;
            sb.HumanIndex = humanIndex;
            Action addA = () => sb.AddRect(-12, -8, -4, 8, V(-5 + H, 1 + H), East, SimTestKit.Legs((East, 11), (South, 2), (West, 11)));
            Action addB = () =>
            {
                Action<OwnerGrid, byte> land = (g, id) =>
                {
                    SimTestKit.FillRect(g, id, -4, -6, 4, 6);
                    if (islandFar) SimTestKit.FillRect(g, id, 10, 10, 14, 14);
                    if (victim == Victim.HomeFarIsland) g.FillDisc(V(0, 20), 3.5, id);
                };
                switch (victim)
                {
                    case Victim.HomeNorth:
                        sb.Add(V(H, 4 + H), East, new HomeCirclerController(V(H, 4 + H)), land);
                        break;
                    case Victim.TrailingFromSouth:
                        sb.Add(V(H, -4 + H), South, SimTestKit.Legs((South, 3), (East, 8), (South, 2), (West, 16)), land);
                        break;
                    case Victim.InTheBand:
                        sb.Add(V(-2 + H, H), East, SimTestKit.Legs((East, 4), (West, 4), (East, 4), (West, 4), (East, 4), (West, 4),
                                                                    (East, 4), (West, 4)), land);
                        break;
                    default:
                        sb.Add(V(H, 20 + H), East, new HomeCirclerController(V(H, 20 + H)), land);
                        break;
                }
            };
            if (cutterFirst)
            {
                addA();
                addB();
            }
            else
            {
                addB();
                addA();
            }
            var c = new Corridor { A = cutterFirst ? 0 : 1, B = cutterFirst ? 1 : 0 };
            c.Sim = sb.Build();
            c.Log = new SimTestKit.EventLog(c.Sim);
            OwnerGrid grid = c.Sim.Grid;
            c.NorthPiece = TraitTestKit.RectCells(grid, -4, 1.125, 4, 6);
            c.SouthPiece = TraitTestKit.RectCells(grid, -4, -6, 4, -1.0);
            c.Band = TraitTestKit.RectCells(grid, -4, -1.0, 4, 1.125);
            Assert.AreEqual(NorthCells, c.NorthPiece.Length, "north piece size");
            Assert.AreEqual(SouthCells, c.SouthPiece.Length, "south piece size");
            Assert.AreEqual(BandCells, c.Band.Length, "band size");
            return c;
        }

        /// <summary>
        /// After every tick: each TerritorySevered event has a valid victim (alive, still owning cells), a cutter that is
        /// another player, ascending distinct non-empty cells, and its cells now belong to the recipient (neutral when -1).
        /// </summary>
        private static void AssertSeveredInvariants(Simulation sim)
        {
            IReadOnlyList<SimEvent> events = sim.LastEvents;
            for (int k = 0; k < events.Count; k++)
            {
                SimEvent e = events[k];
                if (e.Type != SimEventType.TerritorySevered) continue;
                string at = "tick " + sim.Tick + ": " + e + ": ";
                Assert.IsTrue(e.Player >= 0 && e.Player < sim.Players.Count, at + "victim index");
                Assert.IsTrue(e.Other >= 0 && e.Other < sim.Players.Count && e.Other != e.Player, at + "cutter index");
                Assert.IsTrue(sim.Players[e.Player].Alive, at + "the victim is alive");
                Assert.That(sim.Grid.CountOf(sim.Players[e.Player].Id), Is.GreaterThan(0), at + "the victim keeps a piece");
                Assert.IsNotNull(e.Cells, at + "cells");
                Assert.That(e.Cells.Length, Is.GreaterThan(0), at + "empty severance");
                for (int c = 1; c < e.Cells.Length; c++) Assert.IsTrue(e.Cells[c] > e.Cells[c - 1], at + "cells ascending and distinct");
                SeveredTerritoryRule rule = sim.Config.SeveredTerritory;
                Assert.AreNotEqual(SeveredTerritoryRule.Off, rule, at + "an event with the rule off");
                if (rule == SeveredTerritoryRule.Neutral) Assert.AreEqual(-1, e.Recipient, at + "Neutral: no recipient");
                else Assert.AreEqual(e.Other, e.Recipient, at + "Capturer: the cutter receives");
                // Later events of the same Step may change these cells again only through another capture; none does here.
                byte owner = e.Recipient >= 0 ? sim.Players[e.Recipient].Id : OwnerGrid.Neutral;
                bool laterReturn = false;
                for (int j = k + 1; j < events.Count; j++) laterReturn |= events[j].Type == SimEventType.Return;
                if (!laterReturn)
                {
                    for (int c = 0; c < e.Cells.Length; c++) Assert.AreEqual(owner, sim.Grid.Cells[e.Cells[c]], at + "cell owner after the split");
                }
            }
        }

        private static bool SameSet(int[] sortedExpected, int[] actual)
        {
            return SimTestKit.SameCells(sortedExpected, actual);
        }

        // ------------------------------------------------------------------------------------------------------------
        // 1. The corridor capture splits B: it keeps the piece with its pawn, the other piece goes neutral

        [Test]
        public void R21_CorridorCaptureKeepsThePawnPieceAndNeutralizesTheOther()
        {
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.HomeNorth);
            Assert.AreEqual(SeveredTerritoryRule.Neutral, new SimConfig().SeveredTerritory, "Neutral is the default");
            c.RunUntil(4.5);
            Simulation sim = c.Sim;
            OwnerGrid g = sim.Grid;
            byte a = sim.Players[c.A].Id, b = sim.Players[c.B].Id;

            SimEvent ret = c.Log.Single(SimEventType.Return, c.A);
            Assert.That(ret.Time, Is.EqualTo(CorridorReturn).Within(1e-9));
            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.AreEqual(c.B, cut.Player, "victim");
            Assert.AreEqual(c.A, cut.Other, "cutter");
            Assert.AreEqual(-1, cut.Recipient, "neutral");
            Assert.AreEqual(ret.Time, cut.Time, "same instant as the capture");
            Assert.AreEqual(c.Log.IndexOf(ret) + 1, c.Log.IndexOf(cut), "raised right after the Return");
            Assert.IsTrue(SameSet(c.SouthPiece, cut.Cells), "the severed cells are exactly the south piece (" + cut.Cells.Length + ")");

            Assert.AreEqual(BandCells, TraitTestKit.CountOwned(g, c.Band, a), "the band is A's");
            Assert.AreEqual(NorthCells, TraitTestKit.CountOwned(g, c.NorthPiece, b), "B keeps the north piece (its pawn)");
            Assert.AreEqual(SouthCells, TraitTestKit.CountOwned(g, c.SouthPiece, OwnerGrid.Neutral), "the south piece is neutral");
            Assert.AreEqual(NorthCells, g.CountOf(b), "B owns nothing else");
            Assert.IsTrue(sim.Players[c.B].Alive && sim.Players[c.B].Home);

            // Score, percentage and ranking read the new owners.
            Assert.That(sim.AreaPercent(c.B), Is.EqualTo(100.0 * NorthCells / g.ArenaCellCount).Within(1e-12));
            Assert.AreEqual(2, sim.RankOf(c.B));
            Assert.AreEqual(1, sim.RankOf(c.A));
            Assert.AreEqual(0, c.Log.Count(SimEventType.Eliminated));
        }

        // ------------------------------------------------------------------------------------------------------------
        // 2. The pawn outside on a trail: the piece with its exit cell is kept

        [Test]
        public void R21_TrailingVictimKeepsThePieceItLeftHomeFrom()
        {
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.TrailingFromSouth);
            c.RunUntil(4.5);
            OwnerGrid g = c.Sim.Grid;
            byte b = c.Sim.Players[c.B].Id;
            SimEvent exit = c.Log.First(SimEventType.Exit, c.B);
            Assert.IsNotNull(exit);
            SimTestKit.AssertNear(V(H, -6), exit.Point, 1e-9, "B left home through the south edge");
            Assert.IsFalse(c.Sim.Players[c.B].Home, "B is still out on its trail");

            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.AreEqual(c.B, cut.Player);
            Assert.IsTrue(SameSet(c.NorthPiece, cut.Cells), "the north piece is severed");
            Assert.AreEqual(SouthCells, TraitTestKit.CountOwned(g, c.SouthPiece, b), "B keeps the piece it left home from");
            Assert.AreEqual(NorthCells, TraitTestKit.CountOwned(g, c.NorthPiece, OwnerGrid.Neutral));
        }

        // ------------------------------------------------------------------------------------------------------------
        // 3. Anchor cell captured: the largest piece is kept

        [Test]
        public void R21_AnchorCellCapturedKeepsTheLargestPiece()
        {
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.InTheBand);
            c.RunUntil(4.5);
            OwnerGrid g = c.Sim.Grid;
            byte b = c.Sim.Players[c.B].Id;
            // B was home in the band: its cell was taken, it starts an exit at its head (R9) ...
            SimEvent stolen = c.Log.Single(SimEventType.TerritoryStolen, c.B);
            Assert.AreEqual(c.A, stolen.Other);
            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.IsTrue(c.Log.IndexOf(cut) < c.Log.IndexOf(stolen), "the split is resolved before the stolen-cell exit");
            // ... and its anchor cell is in no remaining piece: the larger south piece is kept.
            Assert.IsTrue(SameSet(c.NorthPiece, cut.Cells), "the smaller north piece is severed");
            Assert.AreEqual(SouthCells, g.CountOf(b), "B keeps the larger south piece only");
            Assert.AreEqual(SouthCells, TraitTestKit.CountOwned(g, c.SouthPiece, b));
            Assert.IsTrue(c.Sim.Players[c.B].Alive);
            Assert.IsFalse(c.Sim.Players[c.B].Home, "B trails toward its current color");
        }

        // ------------------------------------------------------------------------------------------------------------
        // 4. Islands that were already separate are not judged

        [Test]
        public void R21_UntouchedPreExistingIslandIsKept()
        {
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.HomeNorth, islandFar: true);
            int[] island = TraitTestKit.RectCells(c.Sim.Grid, 10, 10, 14, 14);
            c.RunUntil(4.5);
            OwnerGrid g = c.Sim.Grid;
            byte b = c.Sim.Players[c.B].Id;
            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.IsTrue(SameSet(c.SouthPiece, cut.Cells), "only the south piece of the split is severed");
            Assert.AreEqual(island.Length, TraitTestKit.CountOwned(g, island, b), "the far island stays B's");
            Assert.AreEqual(NorthCells + island.Length, g.CountOf(b));
        }

        [Test]
        public void R21_SplitOfAnIslandWithoutThePawnKeepsItsLargestPiece()
        {
            // B's pawn circles on its main land (a disc at (0, 20)); the rectangle is an island the corridor cuts. The anchor
            // is in no piece of that split, so the island keeps its larger (south) piece; the main land is not judged.
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.HomeFarIsland);
            OwnerGrid g = c.Sim.Grid;
            byte b = c.Sim.Players[c.B].Id;
            int before = g.CountOf(b);
            int main = before - NorthCells - SouthCells - BandCells;
            Assert.That(main, Is.GreaterThan(1000), "the main disc");
            c.RunUntil(4.5);
            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.IsTrue(SameSet(c.NorthPiece, cut.Cells), "the smaller piece of the island is severed");
            Assert.AreEqual(main + SouthCells, g.CountOf(b), "the main land and the larger island piece stay B's");
        }

        // ------------------------------------------------------------------------------------------------------------
        // 5. The Capturer and Off options

        [Test]
        public void R21_CapturerOptionGivesTheSeveredPieceToTheCutter()
        {
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Capturer, Victim.HomeNorth);
            int aBefore = c.Sim.Grid.CountOf(c.Sim.Players[c.A].Id);
            c.RunUntil(4.5);
            OwnerGrid g = c.Sim.Grid;
            byte a = c.Sim.Players[c.A].Id, b = c.Sim.Players[c.B].Id;
            SimEvent ret = c.Log.Single(SimEventType.Return, c.A);
            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.AreEqual(c.A, cut.Other);
            Assert.AreEqual(c.A, cut.Recipient, "the cutter receives the piece");
            Assert.IsTrue(SameSet(c.SouthPiece, cut.Cells));
            Assert.AreEqual(SouthCells, TraitTestKit.CountOwned(g, c.SouthPiece, a));
            Assert.AreEqual(NorthCells, g.CountOf(b));
            Assert.AreEqual(aBefore + ret.Cells.Length + SouthCells, g.CountOf(a), "A owns its land, its capture and the piece");
            Assert.IsFalse(TraitTestKit.Contains(ret.Cells, c.SouthPiece[0]), "the Return lists only the capture");
        }

        [Test]
        public void R21_OffOptionKeepsBothPiecesAsBefore()
        {
            Corridor off = BuildCorridor(60, SeveredTerritoryRule.Off, Victim.HomeNorth);
            Corridor on = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.HomeNorth);
            off.RunUntil(4.5);
            on.RunUntil(4.5);
            OwnerGrid g = off.Sim.Grid;
            byte b = off.Sim.Players[off.B].Id;
            Assert.AreEqual(0, off.Log.Count(SimEventType.TerritorySevered), "no severance with the rule off");
            Assert.AreEqual(NorthCells + SouthCells, g.CountOf(b), "B keeps two non-contiguous pieces (pre-v1.5 behaviour)");
            Assert.AreEqual(SouthCells, TraitTestKit.CountOwned(g, off.SouthPiece, b));
            // Same capture either way: the rule only acts after it.
            Assert.IsTrue(SimTestKit.SameCells(off.Log.Single(SimEventType.Return, off.A).Cells, on.Log.Single(SimEventType.Return, on.A).Cells));
            // With the rule off, everything except the severed cells is identical.
            int diff = 0;
            for (int k = 0; k < g.Cells.Length; k++)
            {
                if (g.Cells[k] != on.Sim.Grid.Cells[k]) diff++;
            }
            Assert.AreEqual(SouthCells, diff, "the two grids differ by the severed piece only");
        }

        // ------------------------------------------------------------------------------------------------------------
        // 6. Symmetric: the human splits a bot, a bot splits the human

        [TestCase(true, 0)]    // A (player 0) is the human, it cuts the bot B
        [TestCase(true, 1)]    // A cuts the human B (player 1)
        [TestCase(false, 0)]   // the bot A (player 1) cuts the human B (player 0)
        [TestCase(false, 1)]   // the human A (player 1) cuts the bot B (player 0)
        public void R21_HumanAndBotsAreJudgedTheSame(bool cutterFirst, int humanIndex)
        {
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.HomeNorth, cutterFirst, humanIndex);
            Assert.IsTrue(c.Sim.Players[humanIndex].IsHuman);
            c.RunUntil(4.5);
            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.AreEqual(c.B, cut.Player);
            Assert.AreEqual(c.A, cut.Other);
            Assert.IsTrue(SameSet(c.SouthPiece, cut.Cells));
            Assert.AreEqual(NorthCells, c.Sim.Grid.CountOf(c.Sim.Players[c.B].Id));
        }

        /// <summary>
        /// R18 + R21: B returns at the very instant of A's corridor capture (B leaves the north piece through its top edge
        /// at (-1.9375, 6), legs N 10, E 4, S, and comes back onto it at (2.0625, 6) at t = 23.0625 / 6). Both captures
        /// apply; B is judged with its fresh capture as gained cells: it keeps the north piece (its return cell) plus the new
        /// land, and loses the south piece.
        /// </summary>
        [Test]
        public void R21_VictimReturningAtTheSameInstantKeepsItsCaptureAndThePieceItReturnedOnto()
        {
            var sb = new SimTestKit.SimBuilder(60);
            sb.AddRect(-12, -8, -4, 8, V(-5 + H, 1 + H), East, SimTestKit.Legs((East, 11), (South, 2), (West, 11)));
            sb.Add(V(-2 + H, 5 + H), North, SimTestKit.Legs((North, 10), (East, 4), (South, 20)),
                   (g, id) => SimTestKit.FillRect(g, id, -4, -6, 4, 6));
            Simulation sim = sb.Build();
            var log = new SimTestKit.EventLog(sim);
            int[] south = TraitTestKit.RectCells(sim.Grid, -4, -6, 4, -1.0);
            int[] north = TraitTestKit.RectCells(sim.Grid, -4, 1.125, 4, 6);
            while (sim.Time < 4.2 - 1e-9)
            {
                sim.Step();
                SimTestKit.AssertInvariants(sim);
                AssertSeveredInvariants(sim);
            }
            SimEvent retA = log.Single(SimEventType.Return, 0), retB = log.Single(SimEventType.Return, 1);
            Assert.AreEqual(retA.Time, retB.Time, "one instant");
            Assert.That(retA.Time, Is.EqualTo(CorridorReturn).Within(1e-9));
            Assert.That(retB.Cells.Length, Is.GreaterThan(1000), "B's own capture applies");
            SimEvent cut = log.Single(SimEventType.TerritorySevered);
            Assert.AreEqual(1, cut.Player);
            Assert.AreEqual(0, cut.Other);
            Assert.IsTrue(SimTestKit.SameCells(south, cut.Cells), "B loses the south piece only");
            byte b = sim.Players[1].Id;
            Assert.AreEqual(north.Length, TraitTestKit.CountOwned(sim.Grid, north, b));
            Assert.AreEqual(retB.Cells.Length, TraitTestKit.CountOwned(sim.Grid, retB.Cells, b), "B keeps its fresh capture");
            Assert.AreEqual(north.Length + retB.Cells.Length, sim.Grid.CountOf(b));
        }

        // ------------------------------------------------------------------------------------------------------------
        // 7. The lasso pocket path

        /// <summary>
        /// A (charged) owns [-12, -4] x [-8, 8], starts at (-4.9375, 1.0625) heading East: legs E 11, S 2, W 9, N 4, W 3. The
        /// N leg crosses the first leg at X = (-2.9375, 1.0625) at t = 4.0 (lasso): pocket = the band of rows -0.9375 ..
        /// 1.0625 from x = -2.9375 to 6.0625, across B ([-2, 4] x [-6, 6], 48 columns). The ordinary capture (the loop-erased
        /// outline) only encloses [-4, -2.9375] x [1.0625, 3.0625], which is neutral: B loses cells only through the pocket.
        /// Return at x = -4 at t = 26 / 6 + 1.0625 / 6.
        /// </summary>
        [Test]
        public void R21_LassoPocketThatSplitsARivalSeversThePieceWithoutItsPawn()
        {
            var sb = new SimTestKit.SimBuilder(60);
            sb.AddRect(-12, -8, -4, 8, V(-5 + H, 1 + H), East,
                       SimTestKit.Legs((East, 11), (South, 2), (West, 9), (North, 4), (West, 3)));
            sb.Add(V(1 + H, 4 + H), East, new HomeCirclerController(V(1 + H, 4 + H)), (g, id) => SimTestKit.FillRect(g, id, -2, -6, 4, 6));
            Simulation sim = sb.Build();
            sim.DebugSetCharged(0, true);
            var log = new SimTestKit.EventLog(sim);
            OwnerGrid grid = sim.Grid;
            int[] north = TraitTestKit.RectCells(grid, -2, 1.125, 4, 6);
            int[] south = TraitTestKit.RectCells(grid, -2, -6, 4, -1.0);
            int[] band = TraitTestKit.RectCells(grid, -2, -1.0, 4, 1.125);
            while (sim.Time < 5.0 - 1e-9)
            {
                sim.Step();
                SimTestKit.AssertInvariants(sim);
                AssertSeveredInvariants(sim);
            }
            SimEvent pocket = log.Single(SimEventType.LassoPocket, 0);
            Assert.That(pocket.Time, Is.EqualTo(4.0).Within(1e-9));
            SimEvent ret = log.Single(SimEventType.Return, 0);
            Assert.IsFalse(ret.Chased);
            Assert.AreEqual(band.Length, TraitTestKit.CountIn(ret.Cells, band), "the pocket takes B's band");
            SimEvent cut = log.Single(SimEventType.TerritorySevered);
            Assert.AreEqual(1, cut.Player);
            Assert.AreEqual(0, cut.Other);
            Assert.IsTrue(SimTestKit.SameCells(south, cut.Cells), "the piece without B's pawn is severed");
            Assert.AreEqual(north.Length, grid.CountOf(sim.Players[1].Id));
            Assert.AreEqual(south.Length, TraitTestKit.CountOwned(grid, south, OwnerGrid.Neutral));
        }

        // ------------------------------------------------------------------------------------------------------------
        // 8. Traits: no trait takes cells from a living rival, the trait paths around the rule

        [Test]
        public void R21_SeveredCellsArePlainNeutralUnderTheFireTraits()
        {
            // Fire (SparkSpeed, Propagation every 4 s, ScorchedEarth): the severed piece is not scorched, and the first
            // growth instant after the split (t = 4.0) lets A's band grow into it like into any neutral ground.
            RuleTraits fire = new RuleTraits(new[]
            {
                new TraitSpec(TraitId.Propagation, 4.0, 1), new TraitSpec(TraitId.ScorchedEarth, 15.0), new TraitSpec(TraitId.SparkSpeed, 2.1),
            });
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.HomeNorth, traits: fire);
            c.RunUntil(CorridorReturn + 0.05, true);
            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.IsTrue(SameSet(c.SouthPiece, cut.Cells));
            for (int k = 0; k < cut.Cells.Length; k++) Assert.IsFalse(c.Sim.View.IsScorched(cut.Cells[k]), "severed cells are never scorched");
            c.RunUntil(4.5, true);
            SimEvent grew = null;
            foreach (SimEvent e in c.Log.Of(SimEventType.TerritoryGrew, c.A))
            {
                if (e.Time > CorridorReturn) grew = e;
            }
            Assert.IsNotNull(grew, "A grew at t = 4.0");
            Assert.That(TraitTestKit.CountIn(grew.Cells, c.SouthPiece), Is.GreaterThan(0), "A grows into the severed (neutral) piece");
        }

        [Test]
        public void R21_CaptureAugmentedByCoalescenceIsJudgedTheSame()
        {
            Corridor c = BuildCorridor(60, SeveredTerritoryRule.Neutral, Victim.HomeNorth, traits: TraitTestKit.One(TraitId.Coalescence, 2.0));
            c.RunUntil(4.5, true);
            SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
            Assert.IsTrue(SameSet(c.SouthPiece, cut.Cells));
            Assert.AreEqual(NorthCells, c.Sim.Grid.CountOf(c.Sim.Players[c.B].Id));
        }

        // ------------------------------------------------------------------------------------------------------------
        // 9. Determinism: 30, 60 and 144 Hz give the same outcome and the same grid

        [TestCase(SeveredTerritoryRule.Neutral, Victim.HomeNorth)]
        [TestCase(SeveredTerritoryRule.Capturer, Victim.HomeNorth)]
        [TestCase(SeveredTerritoryRule.Neutral, Victim.TrailingFromSouth)]
        [TestCase(SeveredTerritoryRule.Neutral, Victim.InTheBand)]
        public void R21_SameOutcomeAndGridAt30_60_144Hz(SeveredTerritoryRule rule, Victim victim)
        {
            SimTestKit.Outcome reference = null;
            byte[] referenceGrid = null;
            int[] referenceSevered = null;
            foreach (int rate in SimTestKit.CrossRates)
            {
                Corridor c = BuildCorridor(rate, rule, victim);
                c.RunUntil(4.5);
                Assert.AreEqual((long)(4.5 * rate), c.Sim.Tick, "4.5 s is a common tick time");
                SimEvent cut = c.Log.Single(SimEventType.TerritorySevered);
                var outcome = new SimTestKit.Outcome(rate, c.Log, c.Sim);
                if (reference == null)
                {
                    reference = outcome;
                    referenceGrid = (byte[])c.Sim.Grid.Cells.Clone();
                    referenceSevered = cut.Cells;
                    continue;
                }
                SimTestKit.AssertSameOutcome(reference, outcome, "R21 " + rule + " " + victim);
                Assert.IsTrue(SimTestKit.SameCells(referenceSevered, cut.Cells), rate + " Hz: severed cells differ");
                Assert.AreEqual(referenceGrid, c.Sim.Grid.Cells, rate + " Hz: grid differs from 30 Hz");
            }
        }

        [Test]
        public void R21_SameSeedSameStateHashWithTheRule()
        {
            foreach (int rate in SimTestKit.CrossRates)
            {
                Corridor a = BuildCorridor(rate, SeveredTerritoryRule.Neutral, Victim.HomeNorth);
                Corridor b = BuildCorridor(rate, SeveredTerritoryRule.Neutral, Victim.HomeNorth);
                while (a.Sim.Time < 4.5 - 1e-9)
                {
                    a.Sim.Step();
                    b.Sim.Step();
                    if (a.Sim.Tick % 15 == 0 || a.Sim.LastEvents.Count > 0)
                        Assert.AreEqual(a.Sim.StateHash(), b.Sim.StateHash(), rate + " Hz tick " + a.Sim.Tick);
                }
                Assert.AreEqual(1, a.Log.Count(SimEventType.TerritorySevered));
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // 10. Bot rounds: the rule happens in real play and keeps every invariant

        /// <summary>A bot-only round of the trait tests' lineup with the given rule (classic traits, lasso spawns on).</summary>
        private static Simulation BotRound(ulong seed, SeveredTerritoryRule rule, int rate)
        {
            var controllers = new IController[TraitTestKit.Lineup.Length];
            for (int i = 0; i < controllers.Length; i++)
                controllers[i] = new BotController(BotPersonality.Preset(TraitTestKit.Lineup[i]), BotTests.BotSeed(seed, i));
            var config = new SimConfig { Seed = seed, TickRate = rate, LassoEnabled = true, SeveredTerritory = rule };
            return new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
        }

        private static IEnumerable<object[]> BotCases()
        {
#if UNITY_5_3_OR_NEWER
            yield return new object[] { SeveredTerritoryRule.Neutral, 60 };
#else
            yield return new object[] { SeveredTerritoryRule.Neutral, 60 };
            yield return new object[] { SeveredTerritoryRule.Neutral, 30 };
            yield return new object[] { SeveredTerritoryRule.Capturer, 60 };
            yield return new object[] { SeveredTerritoryRule.Neutral, 144 };
#endif
        }

        [TestCaseSource(nameof(BotCases))]
        public void R21_BotRoundsSeverTerritoryAndKeepTheInvariants(SeveredTerritoryRule rule, int rate)
        {
#if UNITY_5_3_OR_NEWER
            const int seeds = 2;
#else
            const int seeds = 8;
#endif
            int severed = 0, severedCells = 0;
            for (int s = 0; s < seeds; s++)
            {
                Simulation sim = BotRound(500UL + (ulong)s, rule, rate);
                while (!sim.Ended)
                {
                    sim.Step();
                    string broken = BotTests.CheckInvariants(sim);
                    if (broken != null) Assert.Fail("seed " + s + " tick " + sim.Tick + ": " + broken);
                    AssertSeveredInvariants(sim);
                    foreach (SimEvent e in sim.LastEvents)
                    {
                        if (e.Type != SimEventType.TerritorySevered) continue;
                        severed++;
                        severedCells += e.Cells.Length;
                    }
                }
            }
            TestContext.WriteLine(rule + " " + rate + " Hz: " + severed + " severances, " + severedCells + " cells over " + seeds + " rounds");
#if !UNITY_5_3_OR_NEWER
            Assert.That(severed, Is.GreaterThan(0), "bots split each other's territory in real play");
#endif
        }
    }
}
