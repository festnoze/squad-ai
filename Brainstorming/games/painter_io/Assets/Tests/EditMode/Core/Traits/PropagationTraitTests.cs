// Owned by traits-core (wave D-1). docs/BIOME_TRAITS.md section 2: Propagation (behaviour trait), P1 = Interval (4 s),
// P2 = Rings (1). Cross-rate equality required for intervals that are multiples of 1/6 s (section 6).
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using static PainterIO.Tests.SimTestKit;

namespace PainterIO.Tests
{
    public class PropagationTraitTests
    {
        // ------------------------------------------------------------------------------------------------------------
        // Helpers

        /// <summary>Steps until the next tick ends at 'time', returns the grid as it was just before that tick.</summary>
        private static byte[] StepTo(Simulation sim, double time)
        {
            RunUntilTime(sim, time - sim.Config.Dt);
            Assert.That(sim.Time, Is.EqualTo(time - sim.Config.Dt).Within(1e-9));
            var before = (byte[])sim.Grid.Cells.Clone();
            sim.Step();
            AssertInvariants(sim);
            Assert.That(sim.Time, Is.EqualTo(time).Within(1e-12));
            return before;
        }

        /// <summary>Cells under live heads (current Cell + centers within HeadRadius), the oracle's exclusion.</summary>
        private static HashSet<int> HeadCells(Simulation sim)
        {
            var set = new HashSet<int>();
            OwnerGrid g = sim.Grid;
            foreach (PlayerState p in sim.Players)
            {
                if (!p.Alive) continue;
                set.Add(p.Cell);
                for (int c = 0; c < g.Cells.Length; c++)
                {
                    if (Vec2d.Distance(g.CellCenter(c % g.Size, c / g.Size), p.Pos) <= sim.Config.HeadRadius) set.Add(c);
                }
            }
            return set;
        }

        /// <summary>The cells the oracle grows for each player over 'rings' rings from the grid 'before'.</summary>
        private static List<int>[] Oracle(byte[] before, Simulation sim, int rings, Func<int, int, bool> excludedFor = null)
        {
            int n = sim.Players.Count;
            var grown = new List<int>[n];
            for (int i = 0; i < n; i++) grown[i] = new List<int>();
            var cells = (byte[])before.Clone();
            HashSet<int> heads = HeadCells(sim);
            for (int r = 0; r < rings; r++)
            {
                var ring = TraitTestKit.OracleRing(cells, sim.Grid.Size, n, c => heads.Contains(c));
                foreach (KeyValuePair<int, byte> kv in ring)
                {
                    if (excludedFor != null && excludedFor(kv.Key, kv.Value - 1)) continue;
                    grown[kv.Value - 1].Add(kv.Key);
                }
                foreach (KeyValuePair<int, byte> kv in ring)
                {
                    if (excludedFor == null || !excludedFor(kv.Key, kv.Value - 1)) cells[kv.Key] = kv.Value;
                }
            }
            for (int i = 0; i < n; i++) grown[i].Sort();
            return grown;
        }

        private static SimEvent Grew(Simulation sim, int player)
        {
            SimEvent found = null;
            foreach (SimEvent e in sim.LastEvents)
            {
                if (e.Type != SimEventType.TerritoryGrew || e.Player != player) continue;
                Assert.IsNull(found, "one TerritoryGrew per player and instant");
                found = e;
            }
            return found;
        }

        private static Simulation TwoRects(int rate, RuleTraits traits)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-14, -3, -8, 3, V(-11, 0), 0.0, new HomeCirclerController(V(-11, 0)));
            sb.AddRect(8, -3, 14, 3, V(11, 0), 0.0, new HomeCirclerController(V(11, 0)));
            return sb.Build();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Tests

        [TestCase(4.0, 1)]
        [TestCase(4.0, 2)]
        [TestCase(1.5, 1)]
        public void Propagation_GrowsRingsAtEveryMultipleOfTheIntervalAtEveryRate(double interval, int rings)
        {
            RuleTraits traits = TraitTestKit.One(TraitId.Propagation, interval, rings);
            TraitTestKit.CrossRate("Propagation " + interval + " x " + rings, rate => TwoRects(rate, traits), 2.0 * interval + 0.5, run =>
            {
                List<SimEvent> grew = run.Log.Of(SimEventType.TerritoryGrew);
                Assert.AreEqual(4, grew.Count, run.Rate + " Hz: two instants, one event per player each\n" + TraitTestKit.Dump(grew));
                Assert.AreEqual(interval, grew[0].Time, 1e-12);
                Assert.AreEqual(0, grew[0].Player);
                Assert.AreEqual(1, grew[1].Player);
                Assert.AreEqual(2.0 * interval, grew[2].Time, 1e-12);
                if (rings == 1) Assert.AreEqual(4 * 48, grew[0].Cells.Length, "one ring around a 48 x 48 square: its four sides");
            });

            // Exact cells against an independent oracle, 60 Hz.
            Simulation sim = TwoRects(60, traits);
            for (int instant = 1; instant <= 2; instant++)
            {
                int before0 = sim.Players[0].OwnedCells(sim.Grid);
                byte[] before = StepTo(sim, instant * interval);
                List<int>[] expected = Oracle(before, sim, rings);
                for (int i = 0; i < 2; i++)
                {
                    SimEvent e = Grew(sim, i);
                    Assert.IsNotNull(e, "TerritoryGrew of player " + i + " at instant " + instant);
                    Assert.AreEqual(expected[i].ToArray(), e.Cells, "grown cells of player " + i + " at instant " + instant);
                }
                Assert.AreEqual(before0 + expected[0].Count, sim.Players[0].OwnedCells(sim.Grid));
            }
        }

        [Test]
        public void Propagation_CellsClaimedByTwoPlayersStayNeutral()
        {
            // Lands separated by one neutral cell column (centers x = -0.0625): both claim it, so it stays neutral.
            var sb = new SimBuilder(60);
            sb.Config.Traits = TraitTestKit.One(TraitId.Propagation);
            sb.AddRect(-6, -3, -0.125, 3, V(-3, 0), 0.0, new HomeCirclerController(V(-3, 0)));
            sb.AddRect(0, -3, 6, 3, V(3, 0), 0.0, new HomeCirclerController(V(3, 0)));
            Simulation sim = sb.Build();
            int[] gap = TraitTestKit.RectCells(sim.Grid, -0.1, -3, 0, 3);
            Assert.AreEqual(48, gap.Length);
            for (int instant = 1; instant <= 2; instant++)
            {
                byte[] before = StepTo(sim, 4.0 * instant);
                List<int>[] expected = Oracle(before, sim, 1);
                Assert.AreEqual(expected[0].ToArray(), Grew(sim, 0).Cells);
                Assert.AreEqual(expected[1].ToArray(), Grew(sim, 1).Cells);
            }
            Assert.AreEqual(48, TraitTestKit.CountOwned(sim.Grid, gap, OwnerGrid.Neutral), "the contested column stays neutral");
            Assert.AreEqual(OwnerGrid.Neutral, OwnerAt(sim, -H, 3 + H), "the corner cells next to both new rows too");
        }

        /// <summary>
        /// Player 0 owns [-10, -2] x [-4, 4]; it leaves East (1 u) and then shuttles North / South on x = -1.9375, the cell
        /// column right next to its land, so at t = 4 its head is at (-1.9375, -0.4375) and its trail lies along its edge.
        /// Player 1 idles far away.
        /// </summary>
        private static Simulation EdgeShuttle(int rate, RuleTraits traits)
        {
            var sb = new SimBuilder(rate);
            sb.Config.Traits = traits;
            sb.AddRect(-10, -4, -2, 4, V(-3 + H, -3.4375), East,
                       Legs((East, 1), (North, 6), (South, 5), (North, 5), (South, 5), (North, 5), (South, 5)));
            sb.AddIdle(IdleCorners[2]);
            return sb.Build();
        }

        [Test]
        public void Propagation_NeverTriggersTheOwnersReturnAtEveryRate()
        {
            TraitTestKit.CrossRate("Propagation own trail", rate => EdgeShuttle(rate, TraitTestKit.One(TraitId.Propagation)), 4.4, run =>
            {
                Simulation sim = run.Sim;
                Assert.AreEqual(0, run.Log.Count(SimEventType.Return, 0), run.Rate + " Hz: propagation never returns the player");
                Assert.IsFalse(sim.Players[0].Home);
                SimEvent grew = run.Log.Single(SimEventType.TerritoryGrew, 0);
                // The claimant's own trail raster and its 4-neighbours are excluded.
                var raster = new CellMask(sim.Grid.Size);
                GridRaster.RasterPolyline(sim.Grid, sim.Players[0].Trail.Points, raster);
                var band = new List<int>();
                raster.CopyIndices(band);
                int size = sim.Grid.Size;
                foreach (int c in new List<int>(band))
                {
                    band.Add(c + 1);
                    band.Add(c - 1);
                    band.Add(c + size);
                    band.Add(c - size);
                }
                foreach (int c in band) Assert.IsFalse(TraitTestKit.Contains(grew.Cells, c), "a cell on or next to the own trail grew");
                int[] left = TraitTestKit.RectCells(sim.Grid, -10.1, -4, -10, 4);
                Assert.AreEqual(64, TraitTestKit.CountIn(grew.Cells, left), "the far side grows normally");
                int[] rightTop = TraitTestKit.RectCells(sim.Grid, -2, 2.8, -1.9, 4);
                Assert.AreEqual(rightTop.Length, TraitTestKit.CountIn(grew.Cells, rightTop), "the edge beyond the trail band grows");
            });
        }

        [Test]
        public void Propagation_SkipsTheCellsUnderLiveHeads()
        {
            // Player 1 (land far away) starts trailing on the column next to player 0's land and shuttles along it: at t = 4
            // its head is at (-1.9375, 1.5625). Player 0 idles in its land.
            var sb = new SimBuilder(60);
            sb.Config.Traits = TraitTestKit.One(TraitId.Propagation);
            sb.AddRect(-10, -4, -2, 4, V(-6, 0), 0.0, new HomeCirclerController(V(-6, 0)));
            sb.Add(V(-2 + H, -2.4375), North, Legs((North, 5), (South, 5), (North, 5), (South, 5), (North, 5)),
                   (g, id) => FillRect(g, id, 20, -3, 26, 3));
            Simulation sim = sb.Build();
            Assert.IsFalse(sim.Players[1].Home, "custom start off its land: trailing");
            byte[] before = StepTo(sim, 4.0);
            Vec2d head = sim.Players[1].Pos;
            AssertNear(V(-2 + H, 1.5625), head, 1e-9, "head at t = 4");
            int[] grew = Grew(sim, 0).Cells;
            List<int>[] expected = Oracle(before, sim, 1);
            Assert.AreEqual(expected[0].ToArray(), grew);
            int[] column = TraitTestKit.RectCells(sim.Grid, -2, -4, -1.9, 4);
            int blocked = 0;
            foreach (int c in column)
            {
                Vec2d center = sim.Grid.CellCenter(c % sim.Grid.Size, c / sim.Grid.Size);
                bool under = Vec2d.Distance(center, head) <= 0.45 || c == sim.Players[1].Cell;
                Assert.AreEqual(under ? OwnerGrid.Neutral : (byte)1, sim.Grid.Cells[c], "column cell at y = " + center.Y);
                if (under) blocked++;
            }
            Assert.AreEqual(7, blocked, "the head covers 7 cells of the column");
            Assert.IsFalse(sim.Players[1].Home, "the rival keeps trailing over the grown cells");
        }

        [Test]
        public void Propagation_SkipsScorchedCellsUntilTheScorchEnds()
        {
            // Player 1's land touches player 0's; player 1 dies at t = 0.1. With ScorchedEarth its freed land cannot be grown
            // into before t = 15.1; without it player 0 grows into it at t = 4.
            Func<RuleTraits, Simulation> make = traits =>
            {
                var sb = new SimBuilder(60);
                sb.Config.Traits = traits;
                sb.AddRect(-10, -4, -2, 4, V(-6, 0), 0.0, new HomeCirclerController(V(-6, 0)));
                sb.AddRect(-2, -4, 4, 4, V(1, 0), 0.0, new HomeCirclerController(V(1, 0)));
                sb.AddIdle(IdleCorners[2]);
                Simulation s0 = sb.Build();
                s0.BeforeTick += s =>
                {
                    if (s.Tick != 6) return;
                    s.DebugSetTrail(1, new[] { V(10 + H, 10 + H), V(12 + H, 10 + H) });
                    s.DebugForceCut(1, 3.0, 2);
                };
                return s0;
            };
            Simulation scorched = make(RuleTraits.Parse("Propagation;ScorchedEarth"));
            Simulation plain = make(TraitTestKit.One(TraitId.Propagation));
            int[] column = TraitTestKit.RectCells(scorched.Grid, -2, -3.9, -1.9, 3.9);   // first column of the dead land
            StepTo(scorched, 4.0);
            StepTo(plain, 4.0);
            Assert.IsFalse(scorched.Players[1].Alive);
            Assert.AreEqual(0, TraitTestKit.CountIn(Grew(scorched, 0).Cells, column), "scorched cells are never grown");
            Assert.AreEqual(column.Length, TraitTestKit.CountIn(Grew(plain, 0).Cells, column), "without ScorchedEarth they are");
            StepTo(scorched, 12.0);
            Assert.AreEqual(0, TraitTestKit.CountOwned(scorched.Grid, column, 1), "still scorched at t = 12");
            StepTo(scorched, 16.0);
            Assert.AreEqual(column.Length, TraitTestKit.CountIn(Grew(scorched, 0).Cells, column), "t = 16 > 15.1: the scorch is over");
        }

        [Test]
        public void Propagation_NoGrowthOnceTheRoundEnded()
        {
            var sb = new SimBuilder(60);
            sb.Config.Traits = TraitTestKit.One(TraitId.Propagation);
            sb.Config.RoundDuration = 8.0;
            sb.AddIdle(IdleCorners[0]);
            sb.AddIdle(IdleCorners[2]);
            Simulation sim = sb.Build();
            var log = new EventLog(sim);
            RunUntilTime(sim, 9.0);
            Assert.IsTrue(sim.Ended);
            Assert.AreEqual(RoundEndReason.TimeUp, sim.Result.Reason);
            List<SimEvent> grew = log.Of(SimEventType.TerritoryGrew);
            Assert.AreEqual(2, grew.Count, "only the t = 4 instant: at t = RoundDuration the scores are final\n" + log.Dump());
            foreach (SimEvent e in grew) Assert.AreEqual(4.0, e.Time, 1e-12);
        }
    }
}
