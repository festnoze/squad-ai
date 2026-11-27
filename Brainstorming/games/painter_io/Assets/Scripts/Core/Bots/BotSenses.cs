// Owned by A5 (bots). Read-only geometric queries used by BotController (contract section 9).
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Pure queries on data reachable from SimView, for the section 9 bots. Nothing here mutates the grid, a trail or any
    /// other object reachable from SimView (contract 5.5): only public getters and read-only indexers are used (no Trail
    /// query that touches its internal scratch buffers).
    /// </summary>
    internal static class BotSenses
    {
        /// <summary>Angular step between the rays that sample a 60 degree sector (9 rays: -30 .. +30 degrees).</summary>
        internal const double SectorStepRad = 7.5 * Math.PI / 180.0;

        /// <summary>Half the number of sector rays on each side of the axis.</summary>
        internal const int SectorHalfRays = 4;

        /// <summary>Radial step of the sector samples (u).</summary>
        internal const double SectorRadialStep = 1.0;

        /// <summary>
        /// Distance from p to the trail restricted to the arcs [0, maxArc] (the exposed prefix when maxArc = L - HeadGrace).
        /// Stops early and returns the first distance found that is &lt;= stopAtOrBelow. +inf when the prefix is empty.
        /// Cost: one point-segment distance per stored segment of the prefix.
        /// </summary>
        internal static double DistanceToTrailPrefix(Trail trail, double maxArc, Vec2d p, double stopAtOrBelow)
        {
            int n = trail.Count;
            if (n == 0 || !(maxArc >= 0.0)) return double.PositiveInfinity;
            IReadOnlyList<Vec2d> pts = trail.Points;
            if (n == 1) return Vec2d.Distance(p, pts[0]);
            IReadOnlyList<double> arc = trail.Arc;
            double best = double.PositiveInfinity;
            Vec2d a = pts[0];
            double s0 = 0.0;
            for (int k = 0; k < n - 1; k++)
            {
                if (s0 > maxArc) break;
                Vec2d b = pts[k + 1];
                double s1 = arc[k + 1];
                Vec2d end = b;
                if (s1 > maxArc)
                {
                    double len = s1 - s0;
                    end = len > 0.0 ? Vec2d.Lerp(a, b, (maxArc - s0) / len) : a;
                }
                double d = Geo.DistancePointSegment(p, a, end);
                if (d < best)
                {
                    best = d;
                    if (best <= stopAtOrBelow) return best;
                }
                a = b;
                s0 = s1;
            }
            return best;
        }

        /// <summary>
        /// Section 9 excursion scoring: samples the cells of the 60 degree sector with apex E (the edge point), axis theta,
        /// radii 1 .. maxOut. Cell values: neutral 1, rival rivalValue, own and Void 0. Each sample is weighted by its
        /// radius (area element of the polar sampling), so the score approximates a per-cell sum. total is normalized to
        /// the weight sum (0 .. max(1, rivalValue)); left and right are the unnormalized halves (counter-clockwise side of
        /// the axis and clockwise side), the axis ray counting half on each side. Sample points outside the grid read
        /// Void (OwnerGrid.OwnerAt).
        /// </summary>
        internal static void ScoreSector(OwnerGrid g, byte me, Vec2d apex, double theta, double maxOut, double rivalValue,
                                         out double total, out double left, out double right)
        {
            double sum = 0.0, weights = 0.0;
            left = 0.0;
            right = 0.0;
            for (int a = -SectorHalfRays; a <= SectorHalfRays; a++)
            {
                Vec2d dir = Vec2d.FromAngle(theta + a * SectorStepRad);
                for (double r = 1.0; r <= maxOut + 1e-9; r += SectorRadialStep)
                {
                    byte o = g.OwnerAt(apex + dir * r);
                    double v;
                    if (o == me || o == OwnerGrid.Void) v = 0.0;
                    else if (o == OwnerGrid.Neutral) v = 1.0;
                    else v = rivalValue;
                    double wv = r * v;
                    weights += r;
                    sum += wv;
                    if (a > 0) left += wv;
                    else if (a < 0) right += wv;
                    else
                    {
                        left += 0.5 * wv;
                        right += 0.5 * wv;
                    }
                }
            }
            total = weights > 0.0 ? sum / weights : 0.0;
        }

        /// <summary>Holes in the own land shorter than this along the ray (rim notches, one-cell gaps) are not an edge.</summary>
        internal const double MinEdgeRun = 1.0;

        /// <summary>
        /// Section 9 edge point E: the first point along dir from the head that enters a cell not owned by me
        /// (GridRaster.FirstEntry over reach u), skipping holes: when own land comes back within MinEdgeRun along the ray
        /// (a notch of the 4-adjacency rim, a one-cell gap), the search goes on from where it comes back, so the plan
        /// starts at the real edge of the land. False when the whole ray stays on own cells inside the grid.
        /// </summary>
        internal static bool EdgePoint(OwnerGrid g, Func<byte, bool> notMine, Func<byte, bool> mine, Vec2d head, Vec2d dir,
                                       double reach, out Vec2d edge)
        {
            Vec2d from = head;
            Vec2d far = head + dir * reach;
            for (int hole = 0; hole < 8; hole++)
            {
                if (!GridRaster.FirstEntry(g, from, far, notMine, out double u)) break;
                Vec2d e = Vec2d.Lerp(from, far, u);
                Vec2d probe = e + dir * MinEdgeRun;
                if (!GridRaster.FirstEntry(g, e, probe, mine, out double back))
                {
                    edge = e;
                    return true;
                }
                from = Vec2d.Lerp(e, probe, back);   // own land again: keep looking beyond the hole
            }
            edge = head;
            return false;
        }

        /// <summary>
        /// True when the segment a-b properly crosses (Geo.ProperIntersect) a stored trail segment whose end arc is
        /// &lt;= maxArc (the older part of the trail). A bounding-box test skips most segments.
        /// </summary>
        internal static bool CrossesTrail(Trail trail, double maxArc, Vec2d a, Vec2d b)
        {
            int n = trail.Count;
            if (n < 2) return false;
            IReadOnlyList<Vec2d> pts = trail.Points;
            IReadOnlyList<double> arc = trail.Arc;
            double minX = Math.Min(a.X, b.X), maxX = Math.Max(a.X, b.X);
            double minY = Math.Min(a.Y, b.Y), maxY = Math.Max(a.Y, b.Y);
            Vec2d p = pts[0];
            for (int k = 0; k < n - 1; k++)
            {
                Vec2d q = pts[k + 1];
                if (arc[k + 1] > maxArc) break;
                if (Math.Max(p.X, q.X) >= minX && Math.Min(p.X, q.X) <= maxX && Math.Max(p.Y, q.Y) >= minY && Math.Min(p.Y, q.Y) <= maxY
                    && Geo.ProperIntersect(a, b, p, q, out _, out _)) return true;
                p = q;
            }
            return false;
        }    }
}
