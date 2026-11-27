// Owned by inherit (rule v1.6, contract section 30). Pure geometry of the KillInheritance bridge band.
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Rule v1.6 (single domain and kill inheritance bridge, contract 30, docs/BIOME_TRAITS.md 7.3). When KillInheritance
    /// gives a victim's land to its killer and that land does not touch the killer's domain, the kill line becomes a band
    /// of territory: the killer's trail from its exit up to its head at the cut (Q, when it is still out on the exit that
    /// made the cut), the link Q to the cut point P on the victim's trail, and the victim's trail from P back to its exit
    /// (the part that tied it to its land). This class only builds that line and rasterizes the band; the event engine
    /// (EventResolver.StepKillRewards) decides whether the band is applied and writes it.
    /// Band cells: every non-Void cell whose center lies within halfWidth of the line, plus the supercover raster of the line
    /// (GridRaster.RasterPolyline, the footprint a closure gives a trail), so the band is 4-connected and never thinner than
    /// one cell. The result depends only on the line geometry (distances to segments and the supercover raster do not depend
    /// on how a straight path was subdivided into trail points), so it is identical at every tick rate.
    /// </summary>
    internal static class InheritanceBridge
    {
        /// <summary>
        /// Appends the points of the trail prefix [0, s] to output: Points[0], every stored point with Arc &lt; s, then
        /// PointAt(s) (skipped when closer than Trail.MinPointSpacing to the last appended point).
        /// </summary>
        public static void AppendPrefix(Trail trail, double s, List<Vec2d> output)
        {
            int n = trail.Count;
            if (n == 0) return;
            IReadOnlyList<Vec2d> pts = trail.Points;
            IReadOnlyList<double> arc = trail.Arc;
            if (s > trail.Length) s = trail.Length;
            AddPoint(output, pts[0]);
            for (int k = 1; k < n && arc[k] < s; k++) AddPoint(output, pts[k]);
            if (s > 0.0) AddPoint(output, trail.PointAt(s));
        }

        /// <summary>Appends p unless it is closer than Trail.MinPointSpacing to the last point of output.</summary>
        public static void AddPoint(List<Vec2d> output, Vec2d p)
        {
            if (output.Count > 0 && Vec2d.Distance(output[output.Count - 1], p) < Trail.MinPointSpacing) return;
            output.Add(p);
        }

        /// <summary>
        /// Clears output, then fills it with the band cells of the line (ascending, non-Void): the supercover raster of the
        /// line plus every cell whose center lies within halfWidth of a segment (of the point for a one-point line).
        /// scratch is a CellMask of the grid size (cleared here).
        /// </summary>
        public static void BandCells(OwnerGrid g, IReadOnlyList<Vec2d> line, double halfWidth, CellMask scratch, List<int> output)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            output.Clear();
            scratch.Clear();
            int n = line.Count;
            if (n == 0) return;
            GridRaster.RasterPolyline(g, line, scratch);
            if (halfWidth > 0.0 && !double.IsInfinity(halfWidth))
            {
                if (n == 1) AddCapsule(g, line[0], line[0], halfWidth, scratch);
                for (int k = 0; k + 1 < n; k++) AddCapsule(g, line[k], line[k + 1], halfWidth, scratch);
            }
            scratch.CopyIndices(output);
            byte[] cells = g.Cells;
            int w = 0;
            for (int k = 0; k < output.Count; k++)
            {
                if (cells[output[k]] != OwnerGrid.Void) output[w++] = output[k];
            }
            output.RemoveRange(w, output.Count - w);
        }

        /// <summary>Sets every cell of the grid whose center lies within r of the segment a-b (Void filtered later).</summary>
        private static void AddCapsule(OwnerGrid g, Vec2d a, Vec2d b, double r, CellMask mask)
        {
            double cs = g.CellSize, o = g.Origin;
            int size = g.Size;
            int i0 = Math.Max(0, (int)Math.Floor((Math.Min(a.X, b.X) - r - o) / cs));
            int i1 = Math.Min(size - 1, (int)Math.Floor((Math.Max(a.X, b.X) + r - o) / cs));
            int j0 = Math.Max(0, (int)Math.Floor((Math.Min(a.Y, b.Y) - r - o) / cs));
            int j1 = Math.Min(size - 1, (int)Math.Floor((Math.Max(a.Y, b.Y) + r - o) / cs));
            for (int j = j0; j <= j1; j++)
            {
                double y = o + (j + 0.5) * cs;
                for (int i = i0; i <= i1; i++)
                {
                    var center = new Vec2d(o + (i + 0.5) * cs, y);
                    if (Geo.DistancePointSegment(center, a, b) <= r) mask.Set(j * size + i);
                }
            }
        }
    }
}
