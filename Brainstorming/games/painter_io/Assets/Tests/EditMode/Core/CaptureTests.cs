using System;
using System.Collections.Generic;
using System.Diagnostics;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    // A2 capture tests (contract 7 and 10.1 C1-C7). Outlines are built by hand as already loop-erased polylines (no
    // dependence on Trail or LoopErase). Every scenario is also checked against ReferenceCapture, a direct two-flood
    // implementation of the section 7 semantics (ReachBefore and ReachAfter), so the one-flood solver is proven equal to
    // the definition and not only to hand-picked expectations.
    public class CaptureTests
    {
        private const byte P1 = 1;
        private const byte P2 = 2;
        private const byte P3 = 3;
        private const double Cs = Tuning.CellSize;

        private static Vec2d V(double x, double y) => new Vec2d(x, y);

        // ------------------------------------------------------------------------------------------------------------
        // C1 - C7

        [Test]
        public void C1_SquareLoopFromDisc_AreaWithin3Percent_RimCaptured()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            const double r = Tuning.StartDiscRadius;
            g.FillDisc(V(0, 0), r, P1);
            // Square of side 16 on cell-center lines, from inside the disc around and back into it.
            const double x0 = 0.5625, y0 = 0.5625, x1 = 16.5625, y1 = 16.5625;
            var outline = new[] { V(2.0625, y0), V(x1, y0), V(x1, y1), V(x0, y1), V(x0, 2.0625) };

            int[] captured = CaptureSolver.Compute(g, P1, outline, null);

            // Analytic area of the region enclosed by the trail centerline and the disc, minus the disc:
            // (x1 - x0)(y1 - y0) - area(square corner region inside the disc).
            double xm = Math.Sqrt(r * r - y0 * y0);
            double inDisc = Simpson(x => Math.Sqrt(Math.Max(0.0, r * r - x * x)) - y0, x0, xm, 20000);
            double expectedArea = (x1 - x0) * (y1 - y0) - inDisc;
            // Re-checked for contract 23.2 D1: on axis-aligned legs the 8-adjacency Rim adds only a few cells where the
            // outline turns (the outer corners touch the Interior by a corner), so the error stays the half-cell rim band
            // of the closed outline (about perimeter x CellSize / 2): +1.45 % measured, well inside the 3 % tolerance.
            double relativeError = (captured.Length * Cs * Cs - expectedArea) / expectedArea;
            TestContext.WriteLine("C1: captured " + (captured.Length * Cs * Cs).ToString("F4") + " u^2 vs analytic " +
                                  expectedArea.ToString("F4") + " u^2, relative error " + (100.0 * relativeError).ToString("F2") + " % (tolerance 3 %)");
            Assert.AreEqual(expectedArea, captured.Length * Cs * Cs, expectedArea * 0.03, "captured area vs analytic area");

            // Exact shape: Interior = cells strictly inside the closed outline (not own, not trail), plus the Rim.
            AssertPolygonInteriorPlusRim(g, P1, outline, captured, null);
            AssertMatchesReference(g, P1, outline, null, captured);
        }

        // Contract 23.2 D1: a 45-degree trail leg is rastered as a staircase of two cell diagonals. The outer diagonal
        // touches the Interior only at cell corners, so the former 4-adjacency Rim left it neutral (one stair notch per
        // cell along the edge). With the 8-adjacency Rim the whole staircase is captured: a head that later runs along
        // the same line only visits own cells.
        [Test]
        public void C1_DiagonalEdgeRimIsCapturedWithoutStairNotches()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, 0), Tuning.StartDiscRadius, P1);
            // East along a cell-center line, back up-left at 45 degrees on x + y = 12.0625 (half a cell off the lattice
            // diagonals, so no corner tie), then down into the disc on a cell-center line.
            var a = V(12.0, 0.0625);
            var b = V(2.5625, 9.5);
            var outline = new[] { V(2.0625, 0.0625), a, b, V(2.5625, 1.5) };
            int[] captured = CaptureSolver.Compute(g, P1, outline, null);
            AssertPolygonInteriorPlusRim(g, P1, outline, captured, null);
            AssertMatchesReference(g, P1, outline, null, captured);

            var capturedSet = new HashSet<int>(captured);
            var trail = new CellMask(g.Size);
            GridRaster.RasterPolyline(g, outline, trail);
            // Cells of the diagonal leg away from its two corners (0.5 u margin): all captured, and the D1 cells (8- but
            // not 4-adjacent to the Interior) are a real part of them.
            Vec2d dir = (b - a).Normalized();
            Vec2d inA = a + dir * 0.5, inB = b - dir * 0.5;
            int legCells = 0, d1Cells = 0;
            GridRaster.TraverseSegment(g, inA, inB, (i, j, u) =>
            {
                int idx = g.Index(i, j);
                Assert.IsTrue(trail.Get(idx), "the leg cell (" + i + ", " + j + ") is a trail cell");
                Assert.IsTrue(capturedSet.Contains(idx), "stair notch left neutral at (" + i + ", " + j + ")");
                legCells++;
                bool touches4 = false;
                foreach (int nb in new[] { idx - 1, idx + 1, idx - g.Size, idx + g.Size })
                    touches4 |= capturedSet.Contains(nb) && !trail.Get(nb);
                if (!touches4) d1Cells++;
                return true;
            });
            Assert.That(legCells, Is.GreaterThan(120), "the leg (8.7 u of x) crosses 2 cells per 0.125 u of x");
            Assert.That(d1Cells, Is.GreaterThan(legCells / 3), "the outer staircase diagonal is captured only by the 8-adjacency Rim");
            // A parallel line a tenth of a cell off the leg (same two diagonals) also stays on captured cells.
            Vec2d off = dir.Perp() * (0.1 * Cs);
            GridRaster.TraverseSegment(g, inA + off, inB + off, (i, j, u) =>
            {
                Assert.IsTrue(capturedSet.Contains(g.Index(i, j)), "a glide along the edge leaves the capture at (" + i + ", " + j + ")");
                return true;
            });
        }

        [Test]
        public void C2_BackAndForthLine_CapturesNothing()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, 0), Tuning.StartDiscRadius, P1);
            var cases = new[]
            {
                new[] { V(2.0625, 0.0625), V(10.0625, 0.0625), V(2.0625, 0.0625) },                       // exact U-turn
                new[] { V(2.0625, 0.0625), V(10.0625, 0.0625), V(10.0625, 0.1), V(2.0625, 0.1) },         // same cells
                new[] { V(2.0625, 0.0625), V(10.0625, 0.0625), V(10.0625, 0.1875), V(2.0625, 0.1875) },   // adjacent rows
                new[] { V(1.5, 1.5), V(9.3, 7.7), V(1.5, 1.5) },                                         // diagonal U-turn
                new[] { V(1.5, 1.5), V(9.3, 7.7), V(9.31, 7.6), V(1.49, 1.41) },                          // diagonal, touching rasters
            };
            foreach (Vec2d[] outline in cases)
            {
                int[] captured = CaptureSolver.Compute(g, P1, outline, null);
                Assert.AreEqual(0, captured.Length, "a back-and-forth line captures nothing");
                AssertMatchesReference(g, P1, outline, null, captured);
            }
        }

        [Test]
        public void C3_BorderHuggingExcursion_CapturesOnlyRegionBetweenTrailAndTerritory()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, -24), Tuning.StartDiscRadius, P1);
            // Down to the border (y = -31.4375 is 0.5625 u from the rim, inside the head margin), along it, then back home.
            const double yb = -31.4375;
            var outline = new[] { V(0.0625, -24.0625), V(0.0625, yb), V(20.0625, yb), V(2.0625, -24.0625) };
            int[] captured = CaptureSolver.Compute(g, P1, outline, null);

            Assert.That(captured.Length, Is.GreaterThan(3000), "the triangle between trail and disc is captured");
            AssertPolygonInteriorPlusRim(g, P1, outline, captured, null);
            foreach (int idx in captured)
            {
                Vec2d c = g.CellCenter(idx % g.Size, idx / g.Size);
                Assert.That(c.Y, Is.GreaterThanOrEqualTo(yb - 1e-9), "the band between trail and rim stays neutral (R1)");
            }
            Assert.That(captured.Length, Is.LessThan(0.30 * g.ArenaCellCount));
            AssertMatchesReference(g, P1, outline, null, captured);

            // Along the border and back the same way: the rim is no wall, nothing is enclosed.
            var alongAndBack = new[] { V(0.0625, -24.0625), V(0.0625, yb), V(20.0625, yb), V(20.0625, yb + 0.125), V(0.1875, yb + 0.125), V(0.1875, -24.0625) };
            int[] none = CaptureSolver.Compute(g, P1, alongAndBack, null);
            Assert.AreEqual(0, none.Length);
            AssertMatchesReference(g, P1, alongAndBack, null, none);
        }

        [Test]
        public void C4_HoleEnclosedByOwnTerritory_NotCaptured()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, 0), 5.0, P1);
            g.FillDisc(V(0, 0), 2.5, OwnerGrid.Neutral);   // annulus: a hole enclosed by own territory alone
            g.FillDisc(V(0.6, 0.6), 0.3, P2);              // a rival speck inside the hole
            Func<int, bool> inHole = idx => g.Cells[idx] != P1 && Vec2d.Distance(g.CellCenter(idx % g.Size, idx / g.Size), V(0, 0)) < 5.0;

            // Unrelated return on the right of the annulus.
            var unrelated = new[] { V(4.0625, 0.0625), V(10.0625, 0.0625), V(10.0625, 3.0625), V(3.5625, 3.0625) };
            int[] captured = CaptureSolver.Compute(g, P1, unrelated, null);
            Assert.That(captured.Length, Is.GreaterThan(500));
            foreach (int idx in captured) Assert.IsFalse(inHole(idx), "hole cell " + idx + " captured");
            AssertPolygonInteriorPlusRim(g, P1, unrelated, captured, null);
            AssertMatchesReference(g, P1, unrelated, null, captured);

            // A loop that winds around the whole annulus: the new ring is captured, the old hole still is not (step 4).
            var around = new[] { V(4.0625, 0.0625), V(8.0625, 0.0625), V(8.0625, 8.0625), V(-7.9375, 8.0625), V(-7.9375, -7.9375), V(6.0625, -7.9375), V(3.0625, -2.9375) };
            captured = CaptureSolver.Compute(g, P1, around, null);
            foreach (int idx in captured) Assert.IsFalse(inHole(idx), "hole cell " + idx + " captured by the enclosing loop");
            Assert.That(captured.Length, Is.GreaterThan(150 * 64), "the region between annulus and loop is captured");
            AssertPolygonInteriorPlusRim(g, P1, around, captured, inHole);
            AssertMatchesReference(g, P1, around, null, captured);
        }

        [Test]
        public void C5_SelfLoop_NotCapturedWithoutPocket_CapturedWithPocket()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, 0), Tuning.StartDiscRadius, P1);
            // Trail: (2.0625, y0) -> (12.0625, y0) -> (12.0625, 6.0625) -> (8.0625, 6.0625) -> (8.0625, -1.9375) -> (2.0625, -1.9375).
            // Its fourth segment crosses the first at X = (8.0625, y0); the loop-erased outline (built by hand) is:
            const double y0 = 0.0625;
            var outline = new[] { V(2.0625, y0), V(8.0625, y0), V(8.0625, -1.9375), V(2.0625, -1.9375) };
            var loop = new[] { V(8.0625, y0), V(12.0625, y0), V(12.0625, 6.0625), V(8.0625, 6.0625), V(8.0625, y0) };

            int[] plain = CaptureSolver.Compute(g, P1, outline, null);
            Assert.That(plain.Length, Is.GreaterThan(0), "the stub between outline and disc is captured");
            AssertPolygonInteriorPlusRim(g, P1, outline, plain, null);
            var plainSet = new HashSet<int>(plain);
            List<int> loopInside = CellsStrictlyInsideBox(g, 8.0625, y0, 12.0625, 6.0625);
            Assert.That(loopInside.Count, Is.GreaterThan(1000));
            foreach (int idx in loopInside) Assert.IsFalse(plainSet.Contains(idx), "self loop cell captured without pocket");
            AssertMatchesReference(g, P1, outline, null, plain);

            var pocket = new CellMask(g.Size);
            GridRaster.RasterPolygon(g, loop, pocket);
            int[] withPocket = CaptureSolver.Compute(g, P1, outline, pocket);
            var withSet = new HashSet<int>(withPocket);
            foreach (int idx in loopInside) Assert.IsTrue(withSet.Contains(idx), "self loop cell missing with pocket");
            AssertUnion(g, P1, plain, pocket, withPocket);
            AssertMatchesReference(g, P1, outline, pocket, withPocket);
        }

        [Test]
        public void C6_CaptureTakesRivalCells()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, 0), Tuning.StartDiscRadius, P1);
            GridTestKit.FillRect(g, 5.0, 1.0, 8.0, 4.0, P2);      // rival block inside the loop
            GridTestKit.FillRect(g, 20.0, 0.0, 22.0, 2.0, P2);    // rival block outside
            GridTestKit.FillRect(g, 10.0, 4.0, 14.0, 6.0, P3);    // rival block straddling the trail x = 12.0625
            int insideP2 = 24 * 24;
            var outline = new[] { V(2.0625, 0.0625), V(12.0625, 0.0625), V(12.0625, 10.0625), V(0.0625, 10.0625), V(0.0625, 2.0625) };
            int[] captured = CaptureSolver.Compute(g, P1, outline, null);

            int p2Taken = 0, p3Taken = 0;
            foreach (int idx in captured)
            {
                Assert.AreNotEqual(P1, g.Cells[idx], "own cells are never returned");
                if (g.Cells[idx] == P2) p2Taken++;
                if (g.Cells[idx] == P3)
                {
                    p3Taken++;
                    Assert.That(g.CellCenter(idx % g.Size, idx / g.Size).X, Is.LessThanOrEqualTo(12.0625), "outside part kept");
                }
            }
            Assert.AreEqual(insideP2, p2Taken, "the whole inside rival block, nothing outside");
            Assert.AreEqual(17 * 16, p3Taken, "the straddling block up to and including the trail column");
            AssertPolygonInteriorPlusRim(g, P1, outline, captured, null);
            AssertMatchesReference(g, P1, outline, null, captured);
        }

        [Test]
        public void C7_CrossOwnFirstSegmentNearHome_StubOnly_ChargedAddsLoop()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, 0), Tuning.StartDiscRadius, P1);
            const double y0 = 0.0625;
            // Exit point: the first non-own cell edge along y0 (the start of the trail, R5).
            Assert.IsTrue(GridRaster.FirstEntry(g, V(0, y0), V(10, y0), o => o != P1, out double u));
            Vec2d exit = V(10 * u, y0);
            Assert.AreEqual(3.5, exit.X, 1e-12);
            // Trail: exit -> (12.0625, y0) -> (12.0625, 8.0625) -> (4.5625, 8.0625) -> (4.5625, -1.9375) -> (2.0625, -1.9375):
            // it circles out and crosses its first segment at X = (4.5625, y0), about 1 u from home, then enters home.
            var x = V(4.5625, y0);
            var outline = new[] { exit, x, V(4.5625, -1.9375), V(2.0625, -1.9375) };
            var loop = new[] { x, V(12.0625, y0), V(12.0625, 8.0625), V(4.5625, 8.0625), x };

            int[] uncharged = CaptureSolver.Compute(g, P1, outline, null);
            Assert.That(uncharged.Length, Is.GreaterThan(0));
            foreach (int idx in uncharged)
            {
                Vec2d c = g.CellCenter(idx % g.Size, idx / g.Size);
                Assert.IsTrue(c.X <= 4.5625 + 1e-9 && c.Y <= y0 + 1e-9, "uncharged capture is the stub only (R8): " + c);
            }
            AssertPolygonInteriorPlusRim(g, P1, outline, uncharged, null);
            AssertMatchesReference(g, P1, outline, null, uncharged);

            var pocket = new CellMask(g.Size);
            GridRaster.RasterPolygon(g, loop, pocket);
            int[] charged = CaptureSolver.Compute(g, P1, outline, pocket);
            var chargedSet = new HashSet<int>(charged);
            foreach (int idx in CellsStrictlyInsideBox(g, 4.5625, y0, 12.0625, 8.0625)) Assert.IsTrue(chargedSet.Contains(idx));
            Assert.That(charged.Length, Is.GreaterThan(uncharged.Length + 7 * 7 * 64));
            AssertUnion(g, P1, uncharged, pocket, charged);
            AssertMatchesReference(g, P1, outline, pocket, charged);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Solver properties

        [Test]
        public void Capture_IsPure_SortedWithoutVoidOrOwn()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(-16, -16), Tuning.StartDiscRadius, P1);
            g.FillDisc(V(-10, -16), 2, P2);
            var outline = new[] { V(-14.0625, -16.0625), V(-5.0625, -16.0625), V(-5.0625, -5.0625), V(-16.0625, -5.0625), V(-16.0625, -14.0625) };
            var pocket = new CellMask(g.Size);
            GridRaster.RasterPolygon(g, new[] { V(-30, -30), V(-26, -30), V(-26, -26) }, pocket);   // reaches into Void
            byte[] before = (byte[])g.Cells.Clone();
            int version = g.Version;
            int pocketVersion = pocket.Version;

            int[] captured = CaptureSolver.Compute(g, P1, outline, pocket);
            Assert.AreEqual(version, g.Version);
            CollectionAssert.AreEqual(before, g.Cells, "Compute never mutates the grid");
            Assert.AreEqual(pocketVersion, pocket.Version, "nor the pocket");
            for (int k = 0; k < captured.Length; k++)
            {
                if (k > 0) Assert.That(captured[k], Is.GreaterThan(captured[k - 1]), "ascending, no duplicate");
                Assert.AreNotEqual(OwnerGrid.Void, g.Cells[captured[k]]);
                Assert.AreNotEqual(P1, g.Cells[captured[k]]);
            }
            AssertMatchesReference(g, P1, outline, pocket, captured);

            // Same call twice gives the same answer (pooled buffers carry no state between calls).
            CollectionAssert.AreEqual(captured, CaptureSolver.Compute(g, P1, outline, pocket));
            Assert.Throws<ArgumentException>(() => CaptureSolver.Compute(g, OwnerGrid.Neutral, outline, null));
            Assert.Throws<ArgumentException>(() => CaptureSolver.Compute(g, P1, outline, new CellMask(16)));
        }

        [Test]
        public void Capture_NoInterior_ReturnsPocketOnly()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, 0), Tuning.StartDiscRadius, P1);
            var line = new[] { V(2.0625, 0.0625), V(10.0625, 0.0625), V(2.0625, 0.0625) };
            var pocket = new CellMask(g.Size);
            GridRaster.RasterPolygon(g, new[] { V(1.05, 1.05), V(6.05, 1.05), V(6.05, 4.05), V(1.05, 4.05) }, pocket);
            int[] captured = CaptureSolver.Compute(g, P1, line, pocket);
            AssertUnion(g, P1, new int[0], pocket, captured);
            Assert.That(captured.Length, Is.LessThan(pocket.Count), "own cells of the pocket are excluded");
            Assert.AreEqual(0, CaptureSolver.Compute(g, P1, new Vec2d[0], null).Length);
            Assert.AreEqual(0, CaptureSolver.Compute(g, P2, line, null).Length, "a player without cells and no enclosure gets nothing");
        }

        [Test]
        public void Capture_MatchesTwoFloodReference_RandomCases()
        {
            // Full arena and a small arena (B often clamped to the grid, trails near Void cells).
            RunRandomReferenceCases(GridTestKit.NewArena(), 25, 101);
            RunRandomReferenceCases(new Arena(6.0, 2.0, 0.45), 300, 202);
        }

        private static void RunRandomReferenceCases(Arena arena, int count, ulong seed)
        {
            var rng = new Rng(seed);
            double h = arena.HalfSize;
            for (int n = 0; n < count; n++)
            {
                var g = new OwnerGrid(arena, Cs);
                int discs = 1 + rng.NextInt(3);
                for (int k = 0; k < discs; k++)
                    g.FillDisc(V(rng.Range(-0.7 * h, 0.7 * h), rng.Range(-0.7 * h, 0.7 * h)), rng.Range(0.4, 0.25 * h), P1);
                if (rng.NextInt(3) == 0)
                {
                    // An annulus hole somewhere in own territory.
                    var c = V(rng.Range(-0.5 * h, 0.5 * h), rng.Range(-0.5 * h, 0.5 * h));
                    double ro = rng.Range(0.3 * h, 0.45 * h);
                    g.FillDisc(c, ro, P1);
                    g.FillDisc(c, ro * rng.Range(0.3, 0.7), OwnerGrid.Neutral);
                }
                int rivals = rng.NextInt(4);
                for (int k = 0; k < rivals; k++)
                    g.FillDisc(V(rng.Range(-h, h), rng.Range(-h, h)), rng.Range(0.3, 0.3 * h), (byte)(2 + rng.NextInt(3)));
                if (g.CountOf(P1) == 0) g.FillDisc(V(0, 0), 1.0, P1);

                var own = new List<int>();
                for (int idx = 0; idx < g.Cells.Length; idx++) if (g.Cells[idx] == P1) own.Add(idx);
                var outline = new List<Vec2d>();
                Vec2d pt = CenterOf(g, own[rng.NextInt(own.Count)]);
                outline.Add(pt);
                int steps = 1 + rng.NextInt(9);
                for (int s = 0; s < steps; s++)
                {
                    pt = arena.ClampInside(pt + Vec2d.FromAngle(rng.Range(-Math.PI, Math.PI)) * rng.Range(0.3, 0.8 * h));
                    outline.Add(pt);
                }
                outline.Add(CenterOf(g, own[rng.NextInt(own.Count)]) + V(rng.Range(-0.05, 0.05), rng.Range(-0.05, 0.05)));
                if (rng.NextInt(5) == 0) outline.Add(arena.ClampInside(V(rng.Range(-h, h), rng.Range(-h, h))));   // ends anywhere

                CellMask pocket = null;
                if (rng.NextInt(2) == 0)
                {
                    pocket = new CellMask(g.Size);
                    var poly = new List<Vec2d>();
                    int pv = 3 + rng.NextInt(4);
                    for (int k = 0; k < pv; k++) poly.Add(V(rng.Range(-h, h), rng.Range(-h, h)));
                    GridRaster.RasterPolygon(g, poly, pocket);
                }
                int[] captured = CaptureSolver.Compute(g, P1, outline, pocket);
                AssertMatchesReference(g, P1, outline, pocket, captured);
            }
        }

        [Test]
        [Category("Perf")]
        public void Capture_Perf_FullSizeBox()
        {
            // Scenario A: a loop along the rim from a start disc encloses most of the arena (large Interior BFS).
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(-16, -16), Tuning.StartDiscRadius, P1);
            var rimLoop = new[]
            {
                V(-16, -16), V(-16, -31.4), V(21, -31.4), V(28.5, -28.5), V(31.4, -21), V(31.4, 21), V(28.5, 28.5),
                V(21, 31.4), V(-21, 31.4), V(-28.5, 28.5), V(-31.4, 21), V(-31.4, -16), V(-16.2, -16),
            };
            double msA = MeasureMs(g, rimLoop, out int capturedA, out double minA);
            Assert.That(capturedA, Is.GreaterThan(g.ArenaCellCount / 2));

            // Scenario B: own cells in opposite corners, short excursion (large ReachAfter span fill).
            OwnerGrid g2 = GridTestKit.NewGrid();
            g2.FillDisc(V(-20, -20), Tuning.StartDiscRadius, P1);
            g2.FillDisc(V(20, 20), Tuning.StartDiscRadius, P1);
            var shortLoop = new[] { V(18.0625, 20.0625), V(12.0625, 20.0625), V(12.0625, 26.0625), V(20.0625, 26.0625), V(20.0625, 22.0625) };
            double msB = MeasureMs(g2, shortLoop, out int capturedB, out double minB);
            Assert.That(capturedB, Is.GreaterThan(1000));

            // TestContext (not Console) so the numbers also land in Unity's JUnit report.
            TestContext.WriteLine("[A2 perf] CaptureSolver.Compute full-size box: rim loop avg " + msA.ToString("F3") + " ms, min " +
                              minA.ToString("F3") + " ms (" + capturedA + " cells); opposite corners avg " + msB.ToString("F3") +
                              " ms, min " + minB.ToString("F3") + " ms (" + capturedB + " cells)");
#if UNITY_5_3_OR_NEWER
            // The Editor runs Mono with Debug code optimization by default: the 3 ms budget applies to players
            // (IL2CPP); this bound only catches an algorithmic regression.
            const double boundMs = 30.0;
#else
            const double boundMs = 10.0;   // budget 3 ms desktop; 10 ms asserted to avoid flakiness
#endif
            Assert.That(msA, Is.LessThan(boundMs));
            Assert.That(msB, Is.LessThan(boundMs));
        }

        /// <summary>Average and best wall time of Compute over 15 runs after two warm-up calls (JIT, pooled buffers).</summary>
        private static double MeasureMs(OwnerGrid g, Vec2d[] outline, out int captured, out double minMs)
        {
            captured = CaptureSolver.Compute(g, P1, outline, null).Length;
            CaptureSolver.Compute(g, P1, outline, null);
            const int runs = 15;
            double total = 0.0;
            minMs = double.PositiveInfinity;
            var sw = new Stopwatch();
            for (int k = 0; k < runs; k++)
            {
                sw.Restart();
                CaptureSolver.Compute(g, P1, outline, null);
                sw.Stop();
                double ms = sw.Elapsed.TotalMilliseconds;
                total += ms;
                if (ms < minMs) minMs = ms;
            }
            return total / runs;
        }

#if !UNITY_5_3_OR_NEWER
        [Test]
        public void Capture_NoGridSizedAllocationPerCall()
        {
            OwnerGrid g = GridTestKit.NewGrid();
            g.FillDisc(V(0, 0), Tuning.StartDiscRadius, P1);
            var outline = new[] { V(2.0625, 0.5625), V(16.5625, 0.5625), V(16.5625, 16.5625), V(0.5625, 16.5625), V(0.5625, 2.0625) };
            var pocket = new CellMask(g.Size);
            GridRaster.RasterPolygon(g, new[] { V(-10.05, -10.05), V(-5.05, -10.05), V(-5.05, -5.05) }, pocket);
            CaptureSolver.Compute(g, P1, outline, pocket);   // warm-up: pools are allocated once
            long before = GC.GetAllocatedBytesForCurrentThread();
            int[] captured = CaptureSolver.Compute(g, P1, outline, pocket);
            long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
            long resultBytes = 4L * captured.Length + 64;
            Assert.That(allocated - resultBytes, Is.LessThan(16 * 1024), "only the returned array is allocated (" + allocated + " bytes)");
        }
#endif

        // ------------------------------------------------------------------------------------------------------------
        // Helpers

        /// <summary>
        /// Direct implementation of the section 7 semantics (two independent 4-connected floods over B), used as the
        /// oracle: TrailCells = RasterPolyline(outline); B = bbox(OwnP, TrailCells, P) + 1 clamped; seeds = non-wall
        /// border cells of B and Void cells of B; Interior = not Void, not wall-after, not ReachAfter, ReachBefore;
        /// Rim = trail cells 8-adjacent to Interior (contract 23.2 D1); Captured = (Interior + Rim + P) - Void - OwnP.
        /// </summary>
        private static int[] ReferenceCapture(OwnerGrid g, byte player, IReadOnlyList<Vec2d> outline, CellMask pocket)
        {
            int size = g.Size, n = size * size;
            var trail = new CellMask(size);
            if (outline.Count > 0) GridRaster.RasterPolyline(g, outline, trail);
            var own = new bool[n];
            int i0 = int.MaxValue, j0 = int.MaxValue, i1 = int.MinValue, j1 = int.MinValue;
            for (int idx = 0; idx < n; idx++)
            {
                bool inBox = false;
                if (g.Cells[idx] == player) { own[idx] = true; inBox = true; }
                if (trail.Get(idx)) inBox = true;
                if (pocket != null && pocket.Get(idx)) inBox = true;
                if (!inBox) continue;
                int i = idx % size, j = idx / size;
                i0 = Math.Min(i0, i); i1 = Math.Max(i1, i); j0 = Math.Min(j0, j); j1 = Math.Max(j1, j);
            }
            if (i0 > i1) return new int[0];
            i0 = Math.Max(i0 - 1, 0); j0 = Math.Max(j0 - 1, 0); i1 = Math.Min(i1 + 1, size - 1); j1 = Math.Min(j1 + 1, size - 1);

            var wallAfter = new bool[n];
            for (int idx = 0; idx < n; idx++) wallAfter[idx] = own[idx] || trail.Get(idx);
            bool[] reachBefore = Flood(g, own, i0, j0, i1, j1);
            bool[] reachAfter = Flood(g, wallAfter, i0, j0, i1, j1);

            var interior = new bool[n];
            for (int j = j0; j <= j1; j++)
                for (int i = i0; i <= i1; i++)
                {
                    int idx = j * size + i;
                    interior[idx] = g.Cells[idx] != OwnerGrid.Void && !wallAfter[idx] && !reachAfter[idx] && reachBefore[idx];
                }
            var result = new List<int>();
            for (int j = j0; j <= j1; j++)
                for (int i = i0; i <= i1; i++)
                {
                    int idx = j * size + i;
                    if (g.Cells[idx] == OwnerGrid.Void || own[idx]) continue;
                    bool rim = trail.Get(idx) && AnyOf8Neighbours(interior, size, i, j, i0, j0, i1, j1);
                    if (interior[idx] || rim || (pocket != null && pocket.Get(idx))) result.Add(idx);
                }
            return result.ToArray();
        }

        /// <summary>True when one of the 8 neighbours of (i, j) inside [i0, i1] x [j0, j1] is set in mask (D1 Rim).</summary>
        private static bool AnyOf8Neighbours(bool[] mask, int size, int i, int j, int i0, int j0, int i1, int j1)
        {
            for (int dj = -1; dj <= 1; dj++)
            {
                int nj = j + dj;
                if (nj < j0 || nj > j1) continue;
                for (int di = -1; di <= 1; di++)
                {
                    int ni = i + di;
                    if ((di == 0 && dj == 0) || ni < i0 || ni > i1) continue;
                    if (mask[nj * size + ni]) return true;
                }
            }
            return false;
        }

        private static bool[] Flood(OwnerGrid g, bool[] wall, int i0, int j0, int i1, int j1)
        {
            int size = g.Size;
            var reach = new bool[size * size];
            var queue = new Queue<int>();
            for (int j = j0; j <= j1; j++)
                for (int i = i0; i <= i1; i++)
                {
                    int idx = j * size + i;
                    bool border = i == i0 || i == i1 || j == j0 || j == j1;
                    bool seed = (border && !wall[idx]) || g.Cells[idx] == OwnerGrid.Void;
                    if (seed && !wall[idx]) { reach[idx] = true; queue.Enqueue(idx); }
                }
            while (queue.Count > 0)
            {
                int idx = queue.Dequeue();
                int i = idx % size, j = idx / size;
                if (i > i0) Visit(idx - 1);
                if (i < i1) Visit(idx + 1);
                if (j > j0) Visit(idx - size);
                if (j < j1) Visit(idx + size);
            }
            return reach;

            void Visit(int k)
            {
                if (reach[k] || wall[k]) return;
                reach[k] = true;
                queue.Enqueue(k);
            }
        }

        private static void AssertMatchesReference(OwnerGrid g, byte player, IReadOnlyList<Vec2d> outline, CellMask pocket, int[] captured)
        {
            int[] expected = ReferenceCapture(g, player, outline, pocket);
            if (expected.Length != captured.Length)
                Assert.Fail("capture differs from the two-flood reference: " + captured.Length + " cells vs " + expected.Length + FirstDiff(expected, captured));
            for (int k = 0; k < expected.Length; k++)
                if (expected[k] != captured[k]) Assert.Fail("capture differs from the two-flood reference" + FirstDiff(expected, captured));
        }

        private static string FirstDiff(int[] expected, int[] actual)
        {
            var e = new HashSet<int>(expected);
            var a = new HashSet<int>(actual);
            foreach (int x in expected) if (!a.Contains(x)) return " (missing cell " + x + ")";
            foreach (int x in actual) if (!e.Contains(x)) return " (extra cell " + x + ")";
            return "";
        }

        /// <summary>
        /// For an outline that starts and ends inside own territory with the closing edge inside it too: Interior =
        /// cells whose center has non-zero winding inside the closed outline, minus own, trail and excluded cells; the
        /// capture must equal Interior plus the trail cells 8-adjacent to it (D1), exactly.
        /// </summary>
        private static void AssertPolygonInteriorPlusRim(OwnerGrid g, byte player, IReadOnlyList<Vec2d> outline, int[] captured, Func<int, bool> exclude)
        {
            int size = g.Size, n = size * size;
            var trail = new CellMask(size);
            GridRaster.RasterPolyline(g, outline, trail);
            var interior = new bool[n];
            for (int idx = 0; idx < n; idx++)
            {
                byte o = g.Cells[idx];
                if (o == OwnerGrid.Void || o == player || trail.Get(idx)) continue;
                if (exclude != null && exclude(idx)) continue;
                if (Geo.WindingNumber(CenterOf(g, idx), outline) != 0) interior[idx] = true;
            }
            var expected = new List<int>();
            for (int idx = 0; idx < n; idx++)
            {
                if (interior[idx]) { expected.Add(idx); continue; }
                if (!trail.Get(idx) || g.Cells[idx] == player) continue;
                int i = idx % size, j = idx / size;
                if (AnyOf8Neighbours(interior, size, i, j, 0, 0, size - 1, size - 1)) expected.Add(idx);
            }
            int[] exp = expected.ToArray();
            if (exp.Length != captured.Length)
                Assert.Fail("capture is not polygon interior + rim: " + captured.Length + " cells vs " + exp.Length + FirstDiff(exp, captured));
            for (int k = 0; k < exp.Length; k++)
                if (exp[k] != captured[k]) Assert.Fail("capture is not polygon interior + rim" + FirstDiff(exp, captured));
        }

        /// <summary>with == without union (pocket minus own minus Void), as sets (R17: each cell counted once).</summary>
        private static void AssertUnion(OwnerGrid g, byte player, int[] without, CellMask pocket, int[] with)
        {
            var expected = new SortedSet<int>(without);
            foreach (int idx in GridTestKit.Indices(pocket))
                if (g.Cells[idx] != player && g.Cells[idx] != OwnerGrid.Void) expected.Add(idx);
            CollectionAssert.AreEqual(new List<int>(expected), with);
        }

        private static List<int> CellsStrictlyInsideBox(OwnerGrid g, double x0, double y0, double x1, double y1)
        {
            var list = new List<int>();
            for (int idx = 0; idx < g.Cells.Length; idx++)
            {
                Vec2d c = CenterOf(g, idx);
                if (c.X > x0 + Cs && c.X < x1 - Cs && c.Y > y0 + Cs && c.Y < y1 - Cs) list.Add(idx);
            }
            return list;
        }

        private static Vec2d CenterOf(OwnerGrid g, int idx) => g.CellCenter(idx % g.Size, idx / g.Size);

        private static double Simpson(Func<double, double> f, double a, double b, int steps)
        {
            if (steps % 2 == 1) steps++;
            double h = (b - a) / steps;
            double sum = f(a) + f(b);
            for (int k = 1; k < steps; k++) sum += f(a + k * h) * (k % 2 == 1 ? 4.0 : 2.0);
            return sum * h / 3.0;
        }
    }
}
