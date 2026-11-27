using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>Visitor of GridRaster.TraverseSegment: return false to stop.</summary>
    public delegate bool CellVisitor(int i, int j, double uEnter);

    /// <summary>A cell entered by a head at tick parameter U (section 6 visit lists).</summary>
    public struct CellEntry
    {
        public int Index;
        public double U;
    }

    /// <summary>
    /// Grid rasterization (contract 5.3): segment traversal for walls and bots, the head traversal of the event engine
    /// (section 6), and scanline polygon rasters for lasso pockets (section 8).
    /// Crossing parameters are always computed directly from the crossed lattice line, u = (Origin + n CellSize - a) / d,
    /// never accumulated, so axis-aligned moves give exact entry times and a segment ending exactly on an edge gives u = 1.
    /// </summary>
    public static class GridRaster
    {
        /// <summary>Corner tie tolerance on the two crossing parameters (contract 5.3).</summary>
        public const double CornerTieEpsilon = 1e-12;

        /// <summary>
        /// Amanatides-Woo traversal of segment a->b, 4-connected, for walls (RasterPolyline) and bots. The first visited
        /// cell is the one containing a + Tiny*(b-a) (a point exactly on a cell edge starts in the cell the segment moves
        /// into), with uEnter = 0. Then visits, in order, every cell whose entry parameter lies in (0, 1], including a cell
        /// entered exactly at u = 1, so the raster of a polyline does not depend on collinear subdivision. On an exact
        /// corner tie (|tMaxX - tMaxY| &lt;= 1e-12) it visits the x-neighbour, then the diagonal cell, both at the tie
        /// parameter (3 cells in total). Cells outside the grid are skipped (never passed to the visitor).
        /// </summary>
        public static void TraverseSegment(OwnerGrid g, Vec2d a, Vec2d b, CellVisitor visitor)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (visitor == null) throw new ArgumentNullException(nameof(visitor));
            var walker = new SegmentWalker(g, a, b);
            while (walker.Next(out int i, out int j, out double u))
            {
                if (!visitor(i, j, u)) return;
            }
        }

        /// <summary>
        /// Head traversal for the event engine (section 6). Starts in startCell (a lies inside it or within 1e-9 of it;
        /// negative initial crossing parameters are clamped to 0). Clears output, then outputs (startCell, 0) and every
        /// next cell with its entry parameter U, keeping entries with U in [0, uMax] INCLUSIVE at both ends: a head that
        /// starts exactly on an edge and moves across it enters the next cell at U = 0, and a tick that ends exactly on an
        /// edge enters the next cell at U = 1. On a corner tie (|tMaxX - tMaxY| &lt;= 1e-12) it steps diagonally in ONE
        /// entry, with no intermediate cell. U is non-decreasing along the output. The walk stops at the grid border
        /// (a head never gets there: R1 keeps it ArenaMargin inside the arena).
        /// </summary>
        public static void TraverseFrom(OwnerGrid g, int startCell, Vec2d a, Vec2d b, double uMax, List<CellEntry> output)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (output == null) throw new ArgumentNullException(nameof(output));
            int size = g.Size;
            if ((uint)startCell >= (uint)(size * size))
                throw new ArgumentOutOfRangeException(nameof(startCell), startCell, "cell index outside the grid");
            CheckFinite(a, nameof(a));
            CheckFinite(b, nameof(b));

            output.Clear();
            output.Add(new CellEntry { Index = startCell, U = 0.0 });

            double origin = g.Origin, cs = g.CellSize;
            int i = startCell % size;
            int j = startCell / size;
            double dx = b.X - a.X, dy = b.Y - a.Y;
            int stepX = dx > 0.0 ? 1 : (dx < 0.0 ? -1 : 0);
            int stepY = dy > 0.0 ? 1 : (dy < 0.0 ? -1 : 0);

            double tMaxX = CrossingParam(origin, cs, stepX > 0 ? i + 1 : i, a.X, dx);
            double tMaxY = CrossingParam(origin, cs, stepY > 0 ? j + 1 : j, a.Y, dy);
            // The head may sit on (or within 1e-9 beyond) the edge it is about to cross: it enters at U = 0.
            // (<= also turns a -0.0 from a start exactly on the edge into +0.0.)
            if (tMaxX <= 0.0) tMaxX = 0.0;
            if (tMaxY <= 0.0) tMaxY = 0.0;

            while (true)
            {
                double u;
                if (Math.Abs(tMaxX - tMaxY) <= CornerTieEpsilon)
                {
                    // Exact corner: one diagonal entry (both parameters finite here: |inf - x| is never tiny).
                    u = Math.Min(tMaxX, tMaxY);
                    if (!(u <= uMax)) return;
                    i += stepX;
                    j += stepY;
                    tMaxX = CrossingParam(origin, cs, stepX > 0 ? i + 1 : i, a.X, dx);
                    tMaxY = CrossingParam(origin, cs, stepY > 0 ? j + 1 : j, a.Y, dy);
                }
                else if (tMaxX < tMaxY)
                {
                    u = tMaxX;
                    if (!(u <= uMax)) return;
                    i += stepX;
                    tMaxX = CrossingParam(origin, cs, stepX > 0 ? i + 1 : i, a.X, dx);
                }
                else
                {
                    u = tMaxY;
                    if (!(u <= uMax)) return;
                    j += stepY;
                    tMaxY = CrossingParam(origin, cs, stepY > 0 ? j + 1 : j, a.Y, dy);
                }
                if ((uint)i >= (uint)size || (uint)j >= (uint)size) return;
                output.Add(new CellEntry { Index = j * size + i, U = u });
            }
        }

        /// <summary>
        /// Earliest uEnter &gt; 0 of a cell visited by TraverseSegment whose owner satisfies pred. The start cell never
        /// counts. Returns false (u = 0) when no visited cell matches. Bots and tests only: the event engine never uses it.
        /// </summary>
        public static bool FirstEntry(OwnerGrid g, Vec2d a, Vec2d b, Func<byte, bool> pred, out double u)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (pred == null) throw new ArgumentNullException(nameof(pred));
            byte[] cells = g.Cells;
            int size = g.Size;
            var walker = new SegmentWalker(g, a, b);
            while (walker.Next(out int i, out int j, out double uEnter))
            {
                if (uEnter > 0.0 && pred(cells[j * size + i]))
                {
                    u = uEnter;
                    return true;
                }
            }
            u = 0.0;
            return false;
        }

        /// <summary>
        /// Supercover walls: ADDS to output (does not clear it) every non-Void cell visited by TraverseSegment along each
        /// segment of the polyline (R1: Void cells are never walls). A single point adds the cell containing it.
        /// </summary>
        public static void RasterPolyline(OwnerGrid g, IReadOnlyList<Vec2d> points, CellMask output)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (points == null) throw new ArgumentNullException(nameof(points));
            CheckMask(g, output);
            int n = points.Count;
            if (n == 0) return;
            byte[] cells = g.Cells;
            int size = g.Size;
            if (n == 1)
            {
                AddSegment(g, cells, size, points[0], points[0], output);
                return;
            }
            for (int k = 0; k + 1 < n; k++) AddSegment(g, cells, size, points[k], points[k + 1], output);
        }

        /// <summary>
        /// Cells whose center has non-zero winding inside poly (implicitly closed), plus the TraverseSegment cells of its
        /// boundary (closing edge included). Void excluded. ADDS to output (does not clear it). Scanline per cell row:
        /// O(edges log edges + rows x active edges + cells), never a per-cell WindingNumber loop.
        /// </summary>
        public static void RasterPolygon(OwnerGrid g, IReadOnlyList<Vec2d> poly, CellMask output)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (poly == null) throw new ArgumentNullException(nameof(poly));
            CheckMask(g, output);
            int n = poly.Count;
            if (n == 0) return;
            ScanInterior(g, poly, output);
            byte[] cells = g.Cells;
            int size = g.Size;
            if (n == 1)
            {
                AddSegment(g, cells, size, poly[0], poly[0], output);
                return;
            }
            for (int k = 0; k < n; k++) AddSegment(g, cells, size, poly[k], poly[k + 1 == n ? 0 : k + 1], output);
        }

        /// <summary>
        /// Number of non-Void cells whose center has non-zero winding inside poly (boundary cells are not added). Same
        /// scanline as RasterPolygon, so it agrees exactly with the interior part of the pocket raster (section 8).
        /// </summary>
        public static int CountInterior(OwnerGrid g, IReadOnlyList<Vec2d> poly)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (poly == null) throw new ArgumentNullException(nameof(poly));
            return ScanInterior(g, poly, null);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Internals

        /// <summary>Parameter at which a + u d crosses the lattice line Origin + line * cs; +inf without motion on the axis.</summary>
        internal static double CrossingParam(double origin, double cs, int line, double a, double d)
        {
            if (d == 0.0) return double.PositiveInfinity;
            return (origin + line * cs - a) / d;
        }

        internal static void CheckFinite(Vec2d p, string name)
        {
            if (double.IsNaN(p.X) || double.IsNaN(p.Y) || double.IsInfinity(p.X) || double.IsInfinity(p.Y))
                throw new ArgumentException("point must be finite: " + p, name);
        }

        private static void CheckMask(OwnerGrid g, CellMask output)
        {
            if (output == null) throw new ArgumentNullException(nameof(output));
            if (output.Size != g.Size)
                throw new ArgumentException("CellMask size " + output.Size + " differs from grid size " + g.Size, nameof(output));
        }

        private static void AddSegment(OwnerGrid g, byte[] cells, int size, Vec2d a, Vec2d b, CellMask output)
        {
            var walker = new SegmentWalker(g, a, b);
            while (walker.Next(out int i, out int j, out double _))
            {
                int idx = j * size + i;
                if (cells[idx] != OwnerGrid.Void) output.Set(idx);
            }
        }

        /// <summary>
        /// First row (or column) index whose cell center coordinate is &gt;= v: ceil((v - Origin) / cs - 0.5), unclamped.
        /// Shared vertices of two edges map to the same index, which keeps the half-open rule consistent.
        /// </summary>
        private static double FirstCenterAtOrAfter(double origin, double cs, double v)
        {
            return Math.Ceiling((v - origin) / cs - 0.5);
        }

        /// <summary>
        /// Scanline non-zero winding fill. Row j (center y_c) is crossed by edge (p, q) iff min(p.Y, q.Y) &lt;= y_c &lt;
        /// max(p.Y, q.Y) (the half-open rule y0 &lt;= y &lt; y1 of Geo.WindingNumber); an upward edge counts +1 and a
        /// downward edge -1, like Geo.WindingNumber, which sums the crossings strictly to the right of the point. With the
        /// row crossings sorted by x and S_k their prefix sums, centers in [x_k, x_k+1) have winding -S_k.
        /// Adds the non-Void interior cells to output when it is not null; returns their count.
        /// </summary>
        private static int ScanInterior(OwnerGrid g, IReadOnlyList<Vec2d> poly, CellMask output)
        {
            int n = poly.Count;
            if (n < 3) return 0;
            int size = g.Size;
            double origin = g.Origin, cs = g.CellSize;
            byte[] cells = g.Cells;
            ScanScratch s = ScanScratch.Get(n);

            // Edge table: rows [jA, jB] inclusive, clamped to the grid.
            int edgeCount = 0;
            int rowMin = int.MaxValue, rowMax = int.MinValue;
            Vec2d p = poly[n - 1];
            CheckFinite(p, nameof(poly));
            for (int k = 0; k < n; k++)
            {
                Vec2d q = poly[k];
                CheckFinite(q, nameof(poly));
                if (p.Y != q.Y)
                {
                    double yLo = p.Y < q.Y ? p.Y : q.Y;
                    double yHi = p.Y < q.Y ? q.Y : p.Y;
                    double jA = FirstCenterAtOrAfter(origin, cs, yLo);
                    double jB = FirstCenterAtOrAfter(origin, cs, yHi) - 1.0;
                    if (jA < 0.0) jA = 0.0;
                    if (jB > size - 1) jB = size - 1;
                    if (jA <= jB)
                    {
                        int e = edgeCount++;
                        s.EdgeX0[e] = p.X;
                        s.EdgeY0[e] = p.Y;
                        s.EdgeSlope[e] = (q.X - p.X) / (q.Y - p.Y);
                        s.EdgeW[e] = q.Y > p.Y ? 1 : -1;
                        s.EdgeRowA[e] = (int)jA;
                        s.EdgeRowB[e] = (int)jB;
                        s.Order[e] = e;
                        s.SortKey[e] = (int)jA;
                        if ((int)jA < rowMin) rowMin = (int)jA;
                        if ((int)jB > rowMax) rowMax = (int)jB;
                    }
                }
                p = q;
            }
            if (edgeCount == 0) return 0;
            Array.Sort(s.SortKey, s.Order, 0, edgeCount);

            int count = 0;
            int next = 0;          // next edge (in Order) to activate
            int activeCount = 0;
            for (int j = rowMin; j <= rowMax; j++)
            {
                // Activate the edges starting at this row, drop the ones that ended.
                while (next < edgeCount && s.EdgeRowA[s.Order[next]] <= j) s.Active[activeCount++] = s.Order[next++];
                int kept = 0;
                for (int a = 0; a < activeCount; a++)
                {
                    int e = s.Active[a];
                    if (s.EdgeRowB[e] >= j) s.Active[kept++] = e;
                }
                activeCount = kept;
                if (activeCount == 0) continue;

                double yc = origin + (j + 0.5) * cs;
                for (int a = 0; a < activeCount; a++)
                {
                    int e = s.Active[a];
                    s.CrossX[a] = s.EdgeX0[e] + (yc - s.EdgeY0[e]) * s.EdgeSlope[e];
                    s.CrossW[a] = s.EdgeW[e];
                }
                SortCrossings(s.CrossX, s.CrossW, activeCount);

                int row = j * size;
                int prefix = 0;
                for (int a = 0; a + 1 < activeCount; a++)
                {
                    prefix += s.CrossW[a];
                    if (prefix == 0) continue;
                    double lo = FirstCenterAtOrAfter(origin, cs, s.CrossX[a]);
                    double hi = FirstCenterAtOrAfter(origin, cs, s.CrossX[a + 1]);   // exclusive
                    if (lo < 0.0) lo = 0.0;
                    else if (lo > size) lo = size;
                    if (hi > size) hi = size;
                    else if (hi < 0.0) hi = 0.0;
                    int iEnd = (int)hi;
                    for (int i = (int)lo; i < iEnd; i++)
                    {
                        int idx = row + i;
                        if (cells[idx] == OwnerGrid.Void) continue;
                        count++;
                        output?.Set(idx);
                    }
                }
            }
            return count;
        }

        private static void SortCrossings(double[] xs, int[] ws, int count)
        {
            if (count > 24)
            {
                Array.Sort(xs, ws, 0, count);
                return;
            }
            for (int a = 1; a < count; a++)
            {
                double x = xs[a];
                int w = ws[a];
                int b = a - 1;
                while (b >= 0 && xs[b] > x)
                {
                    xs[b + 1] = xs[b];
                    ws[b + 1] = ws[b];
                    b--;
                }
                xs[b + 1] = x;
                ws[b + 1] = w;
            }
        }

        /// <summary>Per-thread scratch arrays of the scanline (no allocation once grown).</summary>
        private sealed class ScanScratch
        {
            [ThreadStatic] private static ScanScratch instance;

            public double[] EdgeX0 = new double[0], EdgeY0 = new double[0], EdgeSlope = new double[0], CrossX = new double[0];
            public int[] EdgeW = new int[0], EdgeRowA = new int[0], EdgeRowB = new int[0], Order = new int[0],
                SortKey = new int[0], Active = new int[0], CrossW = new int[0];

            public static ScanScratch Get(int edges)
            {
                ScanScratch s = instance ?? (instance = new ScanScratch());
                if (s.EdgeX0.Length < edges)
                {
                    int cap = Math.Max(edges, 2 * s.EdgeX0.Length);
                    s.EdgeX0 = new double[cap]; s.EdgeY0 = new double[cap]; s.EdgeSlope = new double[cap]; s.CrossX = new double[cap];
                    s.EdgeW = new int[cap]; s.EdgeRowA = new int[cap]; s.EdgeRowB = new int[cap]; s.Order = new int[cap];
                    s.SortKey = new int[cap]; s.Active = new int[cap]; s.CrossW = new int[cap];
                }
                return s;
            }
        }
    }

    /// <summary>
    /// Allocation-free iterator over the cells of GridRaster.TraverseSegment (shared by TraverseSegment, FirstEntry,
    /// RasterPolyline, RasterPolygon and CaptureSolver). Yields in-grid cells only. A segment starting far outside the
    /// grid is first clipped to the grid box grown by one cell, so the walk length stays bounded by the grid.
    /// </summary>
    internal struct SegmentWalker
    {
        private readonly double origin, cs, ax, ay, dx, dy;
        private readonly int size, stepX, stepY;
        private int i, j;
        private double tMaxX, tMaxY;
        private int state;            // 0 = start cell pending, 1 = walking, 2 = diagonal of a corner pending, 3 = done
        private double pendingU;

        public SegmentWalker(OwnerGrid g, Vec2d a, Vec2d b)
        {
            GridRaster.CheckFinite(a, nameof(a));
            GridRaster.CheckFinite(b, nameof(b));
            origin = g.Origin;
            cs = g.CellSize;
            size = g.Size;
            ax = a.X;
            ay = a.Y;
            dx = b.X - a.X;
            dy = b.Y - a.Y;
            stepX = dx > 0.0 ? 1 : (dx < 0.0 ? -1 : 0);
            stepY = dy > 0.0 ? 1 : (dy < 0.0 ? -1 : 0);
            pendingU = 0.0;
            state = 0;

            // Clip against the grid box grown by one cell (cells outside it are never visited anyway).
            double lo = origin - cs, hi = origin + (size + 1) * cs;
            double u0 = 0.0, u1 = 1.0;
            if (!ClipAxis(ax, dx, lo, hi, ref u0, ref u1) || !ClipAxis(ay, dy, lo, hi, ref u0, ref u1))
            {
                i = j = -2;
                tMaxX = tMaxY = double.PositiveInfinity;
                state = 3;
                return;
            }
            if (u0 > 0.0)
            {
                // a is far outside: start from the clip point (an out-of-grid cell that is never yielded).
                i = ClampToBand(Math.Floor((ax + dx * u0 - origin) / cs), size);
                j = ClampToBand(Math.Floor((ay + dy * u0 - origin) / cs), size);
                state = 1;
            }
            else
            {
                i = StartIndex((ax - origin) / cs, dx, size);
                j = StartIndex((ay - origin) / cs, dy, size);
            }
            tMaxX = GridRaster.CrossingParam(origin, cs, stepX > 0 ? i + 1 : i, ax, dx);
            tMaxY = GridRaster.CrossingParam(origin, cs, stepY > 0 ? j + 1 : j, ay, dy);
        }

        /// <summary>Next visited in-grid cell; false when the traversal is over.</summary>
        public bool Next(out int ci, out int cj, out double u)
        {
            while (true)
            {
                switch (state)
                {
                    case 0:
                        state = 1;
                        if (InGrid(i, j))
                        {
                            ci = i; cj = j; u = 0.0;
                            return true;
                        }
                        break;
                    case 2:
                        // Second half of a corner tie: the diagonal cell (the x-neighbour was yielded first).
                        state = 1;
                        j += stepY;
                        tMaxY = GridRaster.CrossingParam(origin, cs, stepY > 0 ? j + 1 : j, ay, dy);
                        if (InGrid(i, j))
                        {
                            ci = i; cj = j; u = pendingU;
                            return true;
                        }
                        break;
                    case 1:
                    {
                        if (MovingAwayOutside())
                        {
                            state = 3;
                            break;
                        }
                        double uNext;
                        if (Math.Abs(tMaxX - tMaxY) <= GridRaster.CornerTieEpsilon)
                        {
                            uNext = Math.Min(tMaxX, tMaxY);
                            if (!(uNext <= 1.0))
                            {
                                state = 3;
                                break;
                            }
                            i += stepX;
                            tMaxX = GridRaster.CrossingParam(origin, cs, stepX > 0 ? i + 1 : i, ax, dx);
                            pendingU = uNext;
                            state = 2;
                        }
                        else if (tMaxX < tMaxY)
                        {
                            uNext = tMaxX;
                            if (!(uNext <= 1.0))
                            {
                                state = 3;
                                break;
                            }
                            i += stepX;
                            tMaxX = GridRaster.CrossingParam(origin, cs, stepX > 0 ? i + 1 : i, ax, dx);
                        }
                        else
                        {
                            uNext = tMaxY;
                            if (!(uNext <= 1.0))
                            {
                                state = 3;
                                break;
                            }
                            j += stepY;
                            tMaxY = GridRaster.CrossingParam(origin, cs, stepY > 0 ? j + 1 : j, ay, dy);
                        }
                        if (InGrid(i, j))
                        {
                            ci = i; cj = j; u = uNext;
                            return true;
                        }
                        break;
                    }
                    default:
                        ci = cj = -1;
                        u = 0.0;
                        return false;
                }
            }
        }

        private bool InGrid(int x, int y) => (uint)x < (uint)size && (uint)y < (uint)size;

        // Outside the grid on an axis and not moving back toward it: nothing more can be visited.
        private bool MovingAwayOutside()
        {
            return (i < 0 && stepX <= 0) || (i >= size && stepX >= 0) || (j < 0 && stepY <= 0) || (j >= size && stepY >= 0);
        }

        // Start cell index on one axis: floor, except that a coordinate exactly on a lattice line with motion toward
        // negative values starts in the lower cell (the cell containing a + Tiny * d). Clamped to the clip band.
        private static int StartIndex(double f, double d, int size)
        {
            double fl = Math.Floor(f);
            if (fl == f && d < 0.0) fl -= 1.0;
            return ClampToBand(fl, size);
        }

        private static int ClampToBand(double v, int size) => v < -1.0 ? -1 : (v > size ? size : (int)v);

        private static bool ClipAxis(double a, double d, double lo, double hi, ref double u0, ref double u1)
        {
            if (d == 0.0) return a >= lo && a <= hi;
            double tA = (lo - a) / d, tB = (hi - a) / d;
            if (tA > tB)
            {
                double t = tA;
                tA = tB;
                tB = t;
            }
            if (tA > u0) u0 = tA;
            if (tB < u1) u1 = tB;
            return u0 <= u1;
        }
    }
}
