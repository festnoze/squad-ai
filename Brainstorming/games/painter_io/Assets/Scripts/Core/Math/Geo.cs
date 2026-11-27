using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Geometry helpers shared by the whole Core (contract 5.1). Pure functions, double precision, no allocation.
    /// </summary>
    public static class Geo
    {
        public const double Tiny = 1e-12;

        private const double TwoPi = 2.0 * Math.PI;

        /// <summary>Wraps an angle to (-pi, pi]. NaN and infinities give NaN.</summary>
        public static double WrapAngle(double a)
        {
            if (double.IsNaN(a) || double.IsInfinity(a)) return double.NaN;
            a %= TwoPi; // now in (-2pi, 2pi), same sign as the input
            if (a <= -Math.PI) a += TwoPi;
            else if (a > Math.PI) a -= TwoPi;
            return a;
        }

        /// <summary>
        /// R3 turn: rotates current toward target the shortest way by at most maxDelta radians. Returns target itself
        /// (as given, not wrapped) when maxDelta &lt;= 0 (instant turns) or when the target is within reach; otherwise
        /// the partially turned angle, wrapped to (-pi, pi]. An exact half turn goes counter-clockwise.
        /// </summary>
        public static double MoveTowardsAngle(double current, double target, double maxDelta)
        {
            if (maxDelta <= 0.0) return target;
            double delta = WrapAngle(target - current);
            if (Math.Abs(delta) <= maxDelta) return target;
            return WrapAngle(current + (delta > 0.0 ? maxDelta : -maxDelta));
        }

        /// <summary>Parameter t in [0, 1] of the point of segment s0-s1 closest to p (0 for a degenerate segment).</summary>
        public static double ClosestParamOnSegment(Vec2d p, Vec2d s0, Vec2d s1)
        {
            double ex = s1.X - s0.X, ey = s1.Y - s0.Y;
            double len2 = ex * ex + ey * ey;
            if (!(len2 > 0.0)) return 0.0;
            double t = ((p.X - s0.X) * ex + (p.Y - s0.Y) * ey) / len2;
            if (t <= 0.0) return 0.0;
            if (t >= 1.0) return 1.0;
            return t;
        }

        public static double DistancePointSegment(Vec2d p, Vec2d s0, Vec2d s1)
        {
            double t = ClosestParamOnSegment(p, s0, s1);
            return Vec2d.Distance(p, Vec2d.Lerp(s0, s1, t));
        }

        /// <summary>
        /// Earliest u in [0, 1] such that the moving point q(u) = a + u (b - a) is within r of segment s0-s1, with
        /// tSeg = the segment parameter of the closest point at that instant. Returns u = 0 when already within r.
        /// The region {distance &lt;= r} is the union of the band |h| &lt;= r over the segment span and two end disks,
        /// so the first entry is the min of: entry through one of the two long sides (a linear equation in u, only
        /// when the motion has a component across the segment) and entry into an end disk (a quadratic solved in
        /// its cancellation-free form C / q, which needs no division by |b - a|^2). Zero-length motion and motion
        /// parallel to the segment therefore need no special case and never divide by a near-zero determinant.
        /// </summary>
        public static bool SweepCircleSegment(Vec2d a, Vec2d b, double r, Vec2d s0, Vec2d s1, out double u, out double tSeg)
        {
            u = 0.0;
            tSeg = 0.0;
            if (!(r >= 0.0)) return false;

            double r2 = r * r;
            double t0 = ClosestParamOnSegment(a, s0, s1);
            Vec2d c0 = Vec2d.Lerp(s0, s1, t0);
            double ax = a.X - c0.X, ay = a.Y - c0.Y;
            if (ax * ax + ay * ay <= r2)
            {
                tSeg = t0;
                return true;
            }

            double dx = b.X - a.X, dy = b.Y - a.Y;
            double best = double.PositiveInfinity;

            // Long sides of the band. Skipped for a degenerate segment (the end disks cover it).
            double ex = s1.X - s0.X, ey = s1.Y - s0.Y;
            double len2 = ex * ex + ey * ey;
            double len = Math.Sqrt(len2);
            if (len > Tiny)
            {
                // Unit normal n = Perp(e) / |e|; h = signed distance of the moving point to the segment line.
                double nx = -ey / len, ny = ex / len;
                double h0 = (a.X - s0.X) * nx + (a.Y - s0.Y) * ny;
                double hd = dx * nx + dy * ny;
                double uSide = double.PositiveInfinity;
                // Entering the band needs |h0| > r and motion toward the line; the sign tests rule out hd == 0.
                if (h0 > r && hd < 0.0) uSide = (h0 - r) / -hd;
                else if (h0 < -r && hd > 0.0) uSide = (-r - h0) / hd;
                if (uSide <= 1.0)
                {
                    double qx = a.X + dx * uSide - s0.X, qy = a.Y + dy * uSide - s0.Y;
                    double ts = (qx * ex + qy * ey) / len2;
                    if (ts >= 0.0 && ts <= 1.0) best = uSide;
                }
            }

            // End disks (cover the short sides of the band and the degenerate segment).
            double uDisk = EarliestDiskEntry(a, dx, dy, s0, r2);
            if (uDisk < best) best = uDisk;
            uDisk = EarliestDiskEntry(a, dx, dy, s1, r2);
            if (uDisk < best) best = uDisk;

            if (!(best <= 1.0)) return false;
            u = best;
            tSeg = ClosestParamOnSegment(new Vec2d(a.X + dx * u, a.Y + dy * u), s0, s1);
            return true;
        }

        /// <summary>
        /// Smallest u in [0, 1] with |a + u d - c| = r for a point starting outside the disk (C &gt; 0), or +inf.
        /// Roots of A u^2 + B u + C with A = |d|^2, B = 2 d.(a - c); the entering root is C / q with
        /// q = (-B + sqrt(B^2 - 4AC)) / 2 when B &lt; 0, stable for A ~ 0 (it tends to the linear root -C / B).
        /// </summary>
        private static double EarliestDiskEntry(Vec2d a, double dx, double dy, Vec2d c, double r2)
        {
            double wx = a.X - c.X, wy = a.Y - c.Y;
            double cc = wx * wx + wy * wy - r2;
            if (cc <= 0.0) return 0.0; // inside already (not reached when the caller checked u = 0 first)
            double bb = 2.0 * (dx * wx + dy * wy);
            if (!(bb < 0.0)) return double.PositiveInfinity; // not approaching
            double aa = dx * dx + dy * dy;
            double disc = bb * bb - 4.0 * aa * cc;
            if (disc < 0.0) return double.PositiveInfinity;
            double q = 0.5 * (-bb + Math.Sqrt(disc));
            double root = cc / q;
            return root <= 1.0 ? root : double.PositiveInfinity;
        }

        /// <summary>
        /// Proper crossing test (contract 5.1) used by Trail.SelfCrossings and LoopErase. True iff the segments are
        /// not parallel (|Cross(da, db)| &gt; 1e-12 |da| |db|), a0 is strictly off the line of b
        /// (|Cross(db, a0 - b0)| &gt; 1e-12 |db|), ta in (0, 1] and tb in [0, 1). Half-open on b: an old vertex belongs
        /// to the old segment that starts there, so a moving segment passing exactly through it counts once; a crossing
        /// exactly at the moving segment's end counts. Touching without reaching the line, collinear overlap and a0 on
        /// the line return false. ta and tb are the crossing parameters when the segments are not parallel, else 0.
        /// Exact vertex hits are decided in floating point: they are exact for axis-aligned and dyadic coordinates
        /// (the test scenarios), and a general-position vertex hit has probability zero.
        /// Rounding band (gate A, from the A4 / A6 finding): the 1e-12 |db| band that rejects a START a0 near b's line
        /// also applies to the END a1. An a1 inside the band counts as reaching the line at a1 (ta = 1, tb = projection
        /// of a1 on b). Without it a crossing that lands in the band at a tick end got ta = 1 + O(1e-16) and was lost by
        /// both ticks (the next tick's segment starts in the band and is rejected by the a0 rule): no R16 lasso, and
        /// LoopErase kept the loop, so an uncharged return captured a self loop (against R8). With it the crossing is
        /// counted exactly once.
        /// </summary>
        public static bool ProperIntersect(Vec2d a0, Vec2d a1, Vec2d b0, Vec2d b1, out double ta, out double tb)
        {
            ta = 0.0;
            tb = 0.0;
            double dax = a1.X - a0.X, day = a1.Y - a0.Y;
            double dbx = b1.X - b0.X, dby = b1.Y - b0.Y;
            double denom = dax * dby - day * dbx;
            double lenA = Math.Sqrt(dax * dax + day * day);
            double lenB = Math.Sqrt(dbx * dbx + dby * dby);
            if (!(Math.Abs(denom) > 1e-12 * lenA * lenB)) return false;

            double band = 1e-12 * lenB;
            double wx = b0.X - a0.X, wy = b0.Y - a0.Y;
            // Cross(w, db) = Cross(db, a0 - b0): signed distance of a0 to the line of b, times |db|.
            double crossWdb = wx * dby - wy * dbx;
            double crossWda = wx * day - wy * dax;
            ta = crossWdb / denom;
            tb = crossWda / denom;
            if (!(Math.Abs(crossWdb) > band)) return false;
            if (ta > 1.0)
            {
                // The end stops short of the line, or lands in the rounding band (then it reaches the line at a1).
                if (Math.Abs((b0.X - a1.X) * dby - (b0.Y - a1.Y) * dbx) > band) return false;
                ta = 1.0;
                tb = ((a1.X - b0.X) * dbx + (a1.Y - b0.Y) * dby) / (lenB * lenB);
            }
            return ta > 0.0 && tb >= 0.0 && tb < 1.0;
        }

        /// <summary>Shoelace area of the implicitly closed polygon, counter-clockwise positive; 0 below 3 points.</summary>
        public static double SignedArea(IReadOnlyList<Vec2d> poly)
        {
            if (poly == null) return 0.0;
            int n = poly.Count;
            if (n < 3) return 0.0;
            // Relative to the first vertex: smaller products, same result.
            Vec2d o = poly[0];
            double sum = 0.0;
            for (int i = 1; i + 1 < n; i++)
            {
                Vec2d p = poly[i], q = poly[i + 1];
                sum += (p.X - o.X) * (q.Y - o.Y) - (q.X - o.X) * (p.Y - o.Y);
            }
            return 0.5 * sum;
        }

        /// <summary>
        /// Winding number of the implicitly closed polygon around p (non-zero rule helper; +1 inside a CCW polygon).
        /// Edge crossings use the half-open rule y0 &lt;= p.Y &lt; y1 so a vertex on the ray is counted once. A point
        /// exactly on the boundary may get either value.
        /// </summary>
        public static int WindingNumber(Vec2d p, IReadOnlyList<Vec2d> poly)
        {
            if (poly == null) return 0;
            int n = poly.Count;
            if (n < 2) return 0;
            int wn = 0;
            Vec2d v0 = poly[n - 1];
            for (int i = 0; i < n; i++)
            {
                Vec2d v1 = poly[i];
                if (v0.Y <= p.Y)
                {
                    if (v1.Y > p.Y && IsLeft(v0, v1, p) > 0.0) wn++;
                }
                else if (v1.Y <= p.Y && IsLeft(v0, v1, p) < 0.0)
                {
                    wn--;
                }
                v0 = v1;
            }
            return wn;
        }

        // > 0 when p is left of the directed line v0 -> v1.
        private static double IsLeft(Vec2d v0, Vec2d v1, Vec2d p)
        {
            return (v1.X - v0.X) * (p.Y - v0.Y) - (p.X - v0.X) * (v1.Y - v0.Y);
        }
    }
}
