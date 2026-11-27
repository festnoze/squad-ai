using System;

namespace PainterIO.Core
{
    /// <summary>Spatial queries on the ownership grid for bots, the spark HUD distance and the ring spawner (contract 5.3).</summary>
    public static class GridQueries
    {
        /// <summary>
        /// Nearest cell owned by owner (Euclidean distance from p to the cell center) within maxRadius (distance &lt;=
        /// maxRadius). Exact ring search: Chebyshev rings of cells around the cell of p (clamped into the grid) are scanned
        /// outward; every center of ring r is at least (r - 0.5) CellSize from p, so the search stops as soon as that bound
        /// reaches the best distance found or exceeds maxRadius. Ties keep the first cell met (deterministic scan order).
        /// Returns false (target = p, distance = +inf) when no owned cell is within maxRadius.
        /// </summary>
        public static bool NearestOwned(OwnerGrid g, byte owner, Vec2d p, double maxRadius, out Vec2d target, out double distance)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            target = p;
            distance = double.PositiveInfinity;
            if (!(maxRadius >= 0.0) || g.CountOf(owner) == 0) return false;
            GridRaster.CheckFinite(p, nameof(p));

            int size = g.Size;
            double origin = g.Origin, cs = g.CellSize;
            byte[] cells = g.Cells;
            // Cell of the clamped point. For a p outside the grid, |p - c| >= |clamp(p) - c| for every center c (the grid
            // box is convex), so the ring bound computed for the clamped point stays valid for p.
            int ci = ClampCell(Math.Floor((p.X - origin) / cs), size);
            int cj = ClampCell(Math.Floor((p.Y - origin) / cs), size);
            int maxRing = Math.Max(Math.Max(ci, size - 1 - ci), Math.Max(cj, size - 1 - cj));

            double bestD2 = double.PositiveInfinity;
            int bestI = -1, bestJ = -1;
            double maxR2 = maxRadius * maxRadius;
            for (int r = 0; r <= maxRing; r++)
            {
                double bound = (r - 0.5) * cs;
                if (bound > 0.0)
                {
                    if (bound * bound >= bestD2 || bound > maxRadius) break;
                }
                int jLo = cj - r, jHi = cj + r, iLo = ci - r, iHi = ci + r;
                for (int j = Math.Max(jLo, 0); j <= Math.Min(jHi, size - 1); j++)
                {
                    bool edgeRow = j == jLo || j == jHi;
                    int row = j * size;
                    double dy = origin + (j + 0.5) * cs - p.Y;
                    if (edgeRow)
                    {
                        for (int i = Math.Max(iLo, 0); i <= Math.Min(iHi, size - 1); i++)
                        {
                            if (cells[row + i] == owner) Consider(i, j, origin, cs, p, dy, ref bestD2, ref bestI, ref bestJ);
                        }
                    }
                    else
                    {
                        if (iLo >= 0 && cells[row + iLo] == owner) Consider(iLo, j, origin, cs, p, dy, ref bestD2, ref bestI, ref bestJ);
                        if (iHi < size && iHi != iLo && cells[row + iHi] == owner) Consider(iHi, j, origin, cs, p, dy, ref bestD2, ref bestI, ref bestJ);
                    }
                }
            }
            if (bestI < 0 || bestD2 > maxR2) return false;
            target = g.CellCenter(bestI, bestJ);
            distance = Math.Sqrt(bestD2);
            return true;
        }

        /// <summary>
        /// True when every arena (non-Void) cell whose center is within radius of center is Neutral (ring spawn, R15).
        /// Void cells and the parts of the disc outside the grid are ignored.
        /// </summary>
        public static bool IsNeutralDisc(OwnerGrid g, Vec2d center, double radius)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            if (!(radius >= 0.0)) return true;
            GridRaster.CheckFinite(center, nameof(center));
            g.GetDiscCellRange(center, radius, out int i0, out int i1, out int j0, out int j1);
            int size = g.Size;
            double origin = g.Origin, cs = g.CellSize;
            byte[] cells = g.Cells;
            double r2 = radius * radius;
            for (int j = j0; j <= j1; j++)
            {
                double dy = origin + (j + 0.5) * cs - center.Y;
                int row = j * size;
                for (int i = i0; i <= i1; i++)
                {
                    byte o = cells[row + i];
                    if (o == OwnerGrid.Neutral || o == OwnerGrid.Void) continue;
                    double dx = origin + (i + 0.5) * cs - center.X;
                    if (dx * dx + dy * dy <= r2) return false;
                }
            }
            return true;
        }

        private static void Consider(int i, int j, double origin, double cs, Vec2d p, double dy,
                                     ref double bestD2, ref int bestI, ref int bestJ)
        {
            double dx = origin + (i + 0.5) * cs - p.X;
            double d2 = dx * dx + dy * dy;
            if (d2 < bestD2)
            {
                bestD2 = d2;
                bestI = i;
                bestJ = j;
            }
        }

        private static int ClampCell(double v, int size)
        {
            if (!(v > 0.0)) return 0;
            if (v >= size - 1) return size - 1;
            return (int)v;
        }
    }
}
