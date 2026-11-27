// Owned by A3 (trail). Contract 5.4 and section 8.
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;

namespace PainterIO.Core
{
    /// <summary>A crossing of the owner's tick segment with one of its stored trail segments (R16).</summary>
    public struct SelfCrossing
    {
        public double U;       // tick parameter of the crossing on the head segment
        public int Segment;    // index k of the crossed stored segment [Points[k], Points[k+1]]
        public Vec2d Point;    // crossing point
    }

    /// <summary>
    /// The exact path of a head since its exit (R6), as a polyline with cumulative arc length, plus a uniform spatial
    /// hash of its segments (bucket 2 u, contract 5.4 performance note) maintained by Append and Clear.
    /// Invariants: Arc[0] = 0, Arc is non-decreasing, Arc[k+1] - Arc[k] = |Points[k+1] - Points[k]| &gt;= 1e-9 (Append
    /// drops closer points), and every segment k is registered in every bucket it touches.
    /// </summary>
    public sealed class Trail
    {
        /// <summary>Append ignores a point closer than this to the last point (contract 5.4).</summary>
        public const double MinPointSpacing = 1e-9;

        /// <summary>Distance slack used to collect the segments in contact at the first contact instant (5.4 sCut).</summary>
        public const double ContactTolerance = 1e-9;

        private readonly List<Vec2d> points = new List<Vec2d>();
        private readonly List<double> arc = new List<double>();
        private readonly ReadOnlyCollection<Vec2d> pointsView;
        private readonly ReadOnlyCollection<double> arcView;
        private readonly SegmentBuckets buckets = new SegmentBuckets();

        // Query scratch (no allocation per query). stamps[k] == stamp marks segment k as already collected.
        private readonly List<int> candidates = new List<int>();
        private int[] stamps = new int[64];
        private int stamp;
        private int version;

        // Rule v1.6 (KillInheritance bridge, contract 30): the identity of the current exit and the arc length dropped from
        // its front since it started (DropPrefix).
        private int epoch;
        private double dropped;
        private readonly List<Vec2d> tailScratch = new List<Vec2d>();

        private static readonly Comparison<SelfCrossing> CrossingOrder = CompareCrossings;

        public Trail()
        {
            // Must not throw: PlayerState initializes "Trail = new Trail()".
            pointsView = points.AsReadOnly();
            arcView = arc.AsReadOnly();
        }

        /// <summary>Points.</summary>
        public int Count => points.Count;

        /// <summary>Points[0] = exit point. Live read-only view.</summary>
        public IReadOnlyList<Vec2d> Points => pointsView;

        /// <summary>Cumulative arc length, Arc[0] = 0. Live read-only view.</summary>
        public IReadOnlyList<double> Arc => arcView;

        /// <summary>Arc[Count-1], 0 when Count &lt;= 1.</summary>
        public double Length => points.Count <= 1 ? 0.0 : arc[arc.Count - 1];

        /// <summary>Count == 0.</summary>
        public bool IsEmpty => points.Count == 0;

        /// <summary>Increments on every mutation: each Clear, Start and accepted Append (an ignored Append changes nothing).</summary>
        public int Version => version;

        /// <summary>
        /// Rule v1.6 (contract 30, api addition): identity of the current exit, incremented by every Clear and Start (not by
        /// Append nor DropPrefix). Two reads with the same Epoch see the same exit.
        /// </summary>
        internal int Epoch => epoch;

        /// <summary>
        /// Rule v1.6: arc length removed from the front of the current exit by DropPrefix since its Start (0 otherwise). An
        /// arc length s recorded on this exit when Dropped was d0 is now s - (Dropped - d0).
        /// </summary>
        internal double Dropped => dropped;

        public void Clear()
        {
            Reset();
            epoch++;
            dropped = 0.0;
        }

        private void Reset()
        {
            points.Clear();
            arc.Clear();
            buckets.Clear();
            version++;
        }

        /// <summary>
        /// Rule v1.6 (KillInheritance bridge, contract 30): the part [0, s] of the trail became territory. The trail now
        /// starts at PointAt(s) and keeps every later stored point (same last point, so the head bookkeeping of section 6 is
        /// unchanged); Epoch stays (same exit) and Dropped grows by s. Version changes (cut and lasso candidates computed on
        /// the old trail are dropped by their re-validation). No-op when s &lt;= 0 or the trail is empty; s beyond Length
        /// leaves the last point only.
        /// </summary>
        internal void DropPrefix(double s)
        {
            int n = points.Count;
            if (n == 0 || !(s > 0.0)) return;
            double length = Length;
            if (s > length) s = length;
            Vec2d first = PointAt(s);
            tailScratch.Clear();
            for (int k = 1; k < n; k++)
            {
                if (arc[k] > s) tailScratch.Add(points[k]);
            }
            if (tailScratch.Count == 0) first = points[n - 1];
            Reset();
            AddPoint(first, 0.0);
            for (int k = 0; k < tailScratch.Count; k++) Append(tailScratch[k]);
            tailScratch.Clear();
            dropped += s;
        }

        /// <summary>Clear then add the first point.</summary>
        public void Start(Vec2d exitPoint)
        {
            Clear();
            AddPoint(exitPoint, 0.0);
        }

        /// <summary>
        /// Ignores a point closer than 1e-9 to the last (or a non-finite one). On an empty trail the point becomes the
        /// first point, as Start would make it.
        /// </summary>
        public void Append(Vec2d p)
        {
            int n = points.Count;
            if (n == 0)
            {
                AddPoint(p, 0.0);
                return;
            }
            double d = Vec2d.Distance(points[n - 1], p);
            if (!(d >= MinPointSpacing) || double.IsInfinity(d)) return;
            AddPoint(p, d);
        }

        private void AddPoint(Vec2d p, double distanceFromLast)
        {
            int n = points.Count;
            points.Add(p);
            arc.Add(n == 0 ? 0.0 : arc[n - 1] + distanceFromLast);
            if (n >= 1)
            {
                int segment = n - 1;
                if (segment >= stamps.Length) Array.Resize(ref stamps, Math.Max(stamps.Length * 2, segment + 1));
                buckets.Add(segment, points[segment], p);
            }
            version++;
        }

        /// <summary>Point at arc length s, clamped to [0, Length]. Zero for an empty trail.</summary>
        public Vec2d PointAt(double s)
        {
            int n = points.Count;
            if (n == 0) return Vec2d.Zero;
            if (n == 1 || !(s > 0.0)) return points[0];
            if (s >= arc[n - 1]) return points[n - 1];
            int k = SegmentIndexAt(s);
            return PointOnSegment(points[k], points[k + 1], arc[k], arc[k + 1], s);
        }

        /// <summary>Unit tangent of the segment containing s (SegmentIndexAt). Zero when there is no segment.</summary>
        public Vec2d DirectionAt(double s)
        {
            int k = SegmentIndexAt(s);
            if (k < 0) return Vec2d.Zero;
            return (points[k + 1] - points[k]).Normalized();
        }

        /// <summary>
        /// Segment k spans [Arc[k], Arc[k+1]]. A vertex arc belongs to the segment that starts there (the largest k with
        /// Arc[k] &lt;= s), except Length which belongs to the last segment. Clamped to [0, Count-2]; -1 when Count &lt; 2.
        /// </summary>
        public int SegmentIndexAt(double s)
        {
            int last = points.Count - 2;
            if (last < 0) return -1;
            if (!(s > 0.0)) return 0;
            if (s >= arc[last]) return last;
            // Largest k in [0, last - 1] with arc[k] <= s (arc[0] = 0 < s here).
            int lo = 0, hi = last - 1;
            while (lo < hi)
            {
                int mid = (lo + hi + 1) >> 1;
                if (arc[mid] <= s) lo = mid;
                else hi = mid - 1;
            }
            return lo;
        }

        // ------------------------------------------------------------------------------------------------------------
        // R10 contact search (contract 5.4)
        // ------------------------------------------------------------------------------------------------------------

        /// <summary>
        /// R10 contact search for ONE tick. The enemy head moves q(u) = a + u (b - a), u in [0, 1]. The exposed arcs are
        /// [0, E(u)] with E(u) = Length + max(0, u - uOwnerStart) * growthPerUnitU - headGrace. Returns the smallest u in
        /// [uMin, 1] with distance(q(u), exposed trail) &lt;= radius (per segment: SegmentFirstContact, the 3-case
        /// algorithm), and sCut = the largest arc among the closest exposed points of the segments in contact at u
        /// (within radius + 1e-9), ignoring a segment's start vertex when the previous segment comes closer (that vertex is
        /// not a closest point of its pass; this keeps sCut independent of the tick rate). A first touch gives the touched
        /// point, an exposure-induced contact gives E(u), superposed passes give the most recent pass.
        /// On false, u = +infinity and sCut = 0 (so a caller testing "u &gt; uEnd" rejects it too).
        /// </summary>
        public bool FirstContact(Vec2d a, Vec2d b, double radius, double uMin, double uOwnerStart,
                                 double growthPerUnitU, double headGrace, out double u, out double sCut)
        {
            u = double.PositiveInfinity;
            sCut = 0.0;
            int n = points.Count;
            if (n == 0 || !(radius >= 0.0)) return false;
            if (!(uMin >= 0.0)) uMin = 0.0;
            if (uMin > 1.0) return false;
            if (double.IsNaN(uOwnerStart)) uOwnerStart = 0.0;

            double length = Length;
            double baseE = length - headGrace;
            double g = growthPerUnitU;
            double eLo = ExposedLimit(baseE, uOwnerStart, g, uMin);
            double eHi = ExposedLimit(baseE, uOwnerStart, g, 1.0);
            double eMax = Math.Max(eLo, eHi);
            if (!(eMax >= 0.0)) return false; // nothing exposed on [uMin, 1]

            // E is affine on each range: E(u) = e0 + slope (u - ua). Split at uOwnerStart when it lies inside.
            double ra0, rb0, re0, rs0, ra1 = 0.0, rb1 = 0.0, re1 = 0.0, rs1 = 0.0;
            int rangeCount = 1;
            if (uOwnerStart > uMin && uOwnerStart < 1.0)
            {
                ra0 = uMin; rb0 = uOwnerStart; re0 = baseE; rs0 = 0.0;
                ra1 = uOwnerStart; rb1 = 1.0; re1 = baseE; rs1 = g;
                rangeCount = 2;
            }
            else if (uOwnerStart >= 1.0)
            {
                ra0 = uMin; rb0 = 1.0; re0 = baseE; rs0 = 0.0;
            }
            else
            {
                // uOwnerStart <= uMin: the engine's normal case (uTrailEnd never exceeds uCur).
                ra0 = uMin; rb0 = 1.0; re0 = baseE + (uMin - uOwnerStart) * g; rs0 = g;
            }

            if (n == 1)
            {
                // A lone exit point (arc 0) is exposed once E(u) >= 0: a degenerate segment.
                Vec2d p = points[0];
                double u1 = SegmentFirstContact(a, b, radius, p, p, 0.0, 0.0, ra0, rb0, re0, rs0);
                if (rangeCount == 2) u1 = Math.Min(u1, SegmentFirstContact(a, b, radius, p, p, 0.0, 0.0, ra1, rb1, re1, rs1));
                if (!(u1 <= 1.0)) return false;
                u = u1;
                return true;
            }

            // Candidate segments: those registered in a bucket touched by the capsule swept on [uMin, 1].
            Vec2d qMin = Vec2d.Lerp(a, b, uMin);
            double pad = radius + 1e-6;
            double minX = Math.Min(qMin.X, b.X) - pad, maxX = Math.Max(qMin.X, b.X) + pad;
            double minY = Math.Min(qMin.Y, b.Y) - pad, maxY = Math.Max(qMin.Y, b.Y) + pad;
            GatherCandidates(minX, minY, maxX, maxY, n - 1);

            double bestU = double.PositiveInfinity;
            int bestK = -1;
            for (int c = 0; c < candidates.Count; c++)
            {
                int k = candidates[c];
                double s0 = arc[k];
                if (s0 > eMax) continue; // never exposed during this query
                Vec2d p0 = points[k], p1 = points[k + 1];
                if (Math.Max(p0.X, p1.X) < minX || Math.Min(p0.X, p1.X) > maxX ||
                    Math.Max(p0.Y, p1.Y) < minY || Math.Min(p0.Y, p1.Y) > maxY) continue;
                double s1 = arc[k + 1];
                double uk = SegmentFirstContact(a, b, radius, p0, p1, s0, s1, ra0, rb0, re0, rs0);
                if (rangeCount == 2)
                {
                    double uk1 = SegmentFirstContact(a, b, radius, p0, p1, s0, s1, ra1, rb1, re1, rs1);
                    if (uk1 < uk) uk = uk1;
                }
                if (uk < bestU)
                {
                    bestU = uk;
                    bestK = k;
                    if (bestU <= uMin) break; // nothing can come earlier than uMin
                }
            }
            if (bestK < 0 || !(bestU <= 1.0)) return false;

            // sCut: at bestU, for each segment in contact, its closest exposed point; keep the largest arc.
            Vec2d q = Vec2d.Lerp(a, b, bestU);
            double eU = Math.Min(ExposedLimit(baseE, uOwnerStart, g, bestU), length);
            double tol = radius + ContactTolerance;
            double best = 0.0;
            bool found = false;
            for (int c = 0; c < candidates.Count; c++)
            {
                int k = candidates[c];
                double s0 = arc[k];
                if (s0 > eU) continue;
                Vec2d p0 = points[k], p1 = points[k + 1];
                if (Math.Max(p0.X, p1.X) < q.X - tol || Math.Min(p0.X, p1.X) > q.X + tol ||
                    Math.Max(p0.Y, p1.Y) < q.Y - tol || Math.Min(p0.Y, p1.Y) > q.Y + tol) continue;
                double s = ClosestExposedArc(q, k, eU, out double dist, out double t);
                if (dist > tol) continue;
                // A segment's start vertex is not a closest point of its pass when the previous segment comes closer:
                // dropping it keeps sCut independent of how a straight pass is subdivided into segments (tick rate).
                if (t == 0.0 && k > 0 && Geo.ClosestParamOnSegment(q, points[k - 1], points[k]) < 1.0) continue;
                if (!found || s > best)
                {
                    best = s;
                    found = true;
                }
            }
            if (!found) best = ClosestExposedArc(q, bestK, eU, out _, out _); // rounding fallback, never expected

            u = bestU;
            sCut = Math.Max(0.0, Math.Min(best, eU));
            return true;
        }

        private static double ExposedLimit(double baseE, double uOwnerStart, double g, double u)
        {
            double grow = u - uOwnerStart;
            return grow > 0.0 ? baseE + grow * g : baseE;
        }

        /// <summary>Arc of the point of segment k restricted to arcs [Arc[k], min(Arc[k+1], eU)] closest to q.</summary>
        private double ClosestExposedArc(Vec2d q, int k, double eU, out double distance, out double t)
        {
            double s0 = arc[k], s1 = arc[k + 1];
            Vec2d p0 = points[k];
            double sub = Math.Min(s1, eU);
            Vec2d pe = sub >= s1 ? points[k + 1] : PointOnSegment(p0, points[k + 1], s0, s1, sub);
            t = Geo.ClosestParamOnSegment(q, p0, pe);
            distance = Vec2d.Distance(q, Vec2d.Lerp(p0, pe, t));
            return s0 + t * (sub - s0);
        }

        /// <summary>
        /// Earliest u in [ua, ub] at which q(u) = a + u (b - a) is within r of the part of segment p0-p1 (arcs [s0, s1])
        /// that is exposed, i.e. arcs &lt;= E(u) = e0 + slope (u - ua); +infinity when none. The feasible set
        /// {(u, sigma): |q(u) - P(sigma)| &lt;= r, sigma &lt;= E(u)} is convex, so its smallest u is one of:
        /// (0) ua itself; (1) the earliest contact with the whole segment, when its touched point is exposed;
        /// (2) a contact with the moving exposure end F(u) = P(E(u)) (a quadratic in u). Contract 5.4.
        /// </summary>
        private static double SegmentFirstContact(Vec2d a, Vec2d b, double r, Vec2d p0, Vec2d p1, double s0, double s1,
                                                  double ua, double ub, double e0, double slope)
        {
            double eB = e0 + slope * (ub - ua);
            if (e0 < s0 && eB < s0) return double.PositiveInfinity; // the segment is never exposed on this range
            Vec2d qa = Vec2d.Lerp(a, b, ua);

            // (0) contact with the exposed sub-segment already at ua.
            if (e0 >= s0)
            {
                Vec2d pe = e0 >= s1 ? p1 : PointOnSegment(p0, p1, s0, s1, e0);
                if (Geo.DistancePointSegment(qa, p0, pe) <= r) return ua;
            }

            double best = double.PositiveInfinity;

            // (1) earliest contact with the whole segment (handles zero-length and parallel motion); valid when the
            // touched point is exposed at that instant.
            Vec2d qb = Vec2d.Lerp(a, b, ub);
            if (Geo.SweepCircleSegment(qa, qb, r, p0, p1, out double uu, out double tSeg))
            {
                double uG = ua + uu * (ub - ua);
                double sigma = s0 + tSeg * (s1 - s0);
                if (sigma <= e0 + slope * (uG - ua)) best = uG;
            }

            // (2) contact with the exposure end F(u) while E(u) lies in [s0, s1].
            double uLo, uHi;
            if (slope > 0.0)
            {
                uLo = ua + (s0 - e0) / slope;
                uHi = ua + (s1 - e0) / slope;
            }
            else if (slope < 0.0)
            {
                uLo = ua + (s1 - e0) / slope;
                uHi = ua + (s0 - e0) / slope;
            }
            else if (e0 >= s0 && e0 <= s1)
            {
                uLo = ua;
                uHi = ub;
            }
            else
            {
                return best;
            }
            if (uLo < ua) uLo = ua;
            if (uHi > ub) uHi = ub;
            if (!(uLo <= uHi) || uLo >= best) return best;

            // w(u) = q(u) - F(u) is affine: w(uLo + x) = wLo + x w1.
            double dx = b.X - a.X, dy = b.Y - a.Y;
            double ls = s1 - s0;
            double fx = p0.X, fy = p0.Y, fdx = 0.0, fdy = 0.0;
            if (ls > 0.0)
            {
                double ex = p1.X - p0.X, ey = p1.Y - p0.Y;
                double kLo = (e0 + slope * (uLo - ua) - s0) / ls;
                if (kLo < 0.0) kLo = 0.0;
                else if (kLo > 1.0) kLo = 1.0;
                fx += kLo * ex;
                fy += kLo * ey;
                double kd = slope / ls;
                fdx = kd * ex;
                fdy = kd * ey;
            }
            Vec2d qLo = Vec2d.Lerp(a, b, uLo);
            double wx = qLo.X - fx, wy = qLo.Y - fy;
            double w1x = dx - fdx, w1y = dy - fdy;
            double cc = wx * wx + wy * wy - r * r;
            if (cc <= 0.0) return Math.Min(best, uLo);
            double bb = 2.0 * (wx * w1x + wy * w1y);
            if (!(bb < 0.0)) return best; // not approaching
            double aa = w1x * w1x + w1y * w1y;
            double disc = bb * bb - 4.0 * aa * cc;
            if (disc < 0.0) return best;
            double qq = 0.5 * (-bb + Math.Sqrt(disc));
            double cand = uLo + cc / qq; // entering root in cancellation-free form
            if (cand <= uHi && cand < best) best = cand;
            return best;
        }

        // ------------------------------------------------------------------------------------------------------------
        // R16 crossings and loop polygon (contract 5.4, section 8)
        // ------------------------------------------------------------------------------------------------------------

        /// <summary>
        /// R16 crossing search for ONE tick: the owner's head moves a-&gt;b (full tick segment). Returns ALL crossings
        /// Geo.ProperIntersect(a, b, Points[k], Points[k+1]) (its rounding band at the moving end counts a crossing that
        /// lands on the line at a tick end exactly once) with U &gt; uMin against the segments k with
        /// Arc[k+1] &lt;= maxSegmentEndArc, sorted by U ascending then Segment descending. Point = a + U (b - a), the
        /// head position at the crossing (the engine's lasso point X). Clears output first; returns the count.
        /// </summary>
        public int SelfCrossings(Vec2d a, Vec2d b, double uMin, double maxSegmentEndArc, List<SelfCrossing> output)
        {
            if (output == null) throw new ArgumentNullException(nameof(output));
            output.Clear();
            int segCount = points.Count - 1;
            if (segCount <= 0) return 0;

            // Arcs increase, so the eligible segments are exactly k < kLimit.
            int kLimit = CountSegmentsEndingBy(maxSegmentEndArc);
            if (kLimit <= 0) return 0;

            const double pad = 1e-7;
            GatherCandidates(Math.Min(a.X, b.X) - pad, Math.Min(a.Y, b.Y) - pad,
                             Math.Max(a.X, b.X) + pad, Math.Max(a.Y, b.Y) + pad, kLimit);
            for (int c = 0; c < candidates.Count; c++)
            {
                int k = candidates[c];
                if (Geo.ProperIntersect(a, b, points[k], points[k + 1], out double ta, out _) && ta > uMin)
                {
                    output.Add(new SelfCrossing { U = ta, Segment = k, Point = Vec2d.Lerp(a, b, ta) });
                }
            }
            if (output.Count > 1) output.Sort(CrossingOrder);
            return output.Count;
        }

        private static int CompareCrossings(SelfCrossing x, SelfCrossing y)
        {
            if (x.U < y.U) return -1;
            if (x.U > y.U) return 1;
            return y.Segment.CompareTo(x.Segment); // same instant: most recent pass first
        }

        /// <summary>Number of segments k with Arc[k+1] &lt;= maxEndArc (they are the first ones).</summary>
        private int CountSegmentsEndingBy(double maxEndArc)
        {
            int segCount = points.Count - 1;
            if (!(arc[1] <= maxEndArc)) return 0;
            if (arc[segCount] <= maxEndArc) return segCount;
            // Largest k in [0, segCount - 1] with arc[k + 1] <= maxEndArc.
            int lo = 0, hi = segCount - 1;
            while (lo < hi)
            {
                int mid = (lo + hi + 1) >> 1;
                if (arc[mid + 1] <= maxEndArc) lo = mid;
                else hi = mid - 1;
            }
            return lo + 1;
        }

        /// <summary>
        /// Closed loop polygon: point, Points[segmentIndex+1 .. Count-1], then head (= point at a crossing). Called BEFORE
        /// the crossing point is appended to the trail, so the point is not duplicated (section 8).
        /// </summary>
        public List<Vec2d> LoopPolygon(int segmentIndex, Vec2d point, Vec2d head)
        {
            int n = points.Count;
            if (segmentIndex < 0 || segmentIndex > n - 2) throw new ArgumentOutOfRangeException(nameof(segmentIndex));
            var poly = new List<Vec2d>(n - segmentIndex + 1);
            poly.Add(point);
            for (int i = segmentIndex + 1; i < n; i++) poly.Add(points[i]);
            poly.Add(head);
            return poly;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Extra query (api addition): nearest point of a trail prefix within a radius, for bots and views.
        // ------------------------------------------------------------------------------------------------------------

        /// <summary>
        /// Closest point to p among the arcs [0, maxArc] of the trail, searched only within radius (spatial hash).
        /// Returns false when no such point lies within radius; otherwise s = its arc length (ties: the largest arc,
        /// the most recent pass) and distance = |p - PointAt(s)|.
        /// </summary>
        public bool ClosestPointWithin(Vec2d p, double radius, double maxArc, out double s, out double distance)
        {
            s = 0.0;
            distance = double.PositiveInfinity;
            int n = points.Count;
            if (n == 0 || !(radius >= 0.0) || !(maxArc >= 0.0)) return false;
            if (n == 1)
            {
                distance = Vec2d.Distance(p, points[0]);
                return distance <= radius;
            }
            double pad = radius + 1e-6;
            GatherCandidates(p.X - pad, p.Y - pad, p.X + pad, p.Y + pad, n - 1);
            double eU = Math.Min(maxArc, Length);
            bool found = false;
            for (int c = 0; c < candidates.Count; c++)
            {
                int k = candidates[c];
                if (arc[k] > eU) continue;
                double sk = ClosestExposedArc(p, k, eU, out double dk, out _);
                if (dk > radius) continue;
                if (!found || dk < distance || (dk == distance && sk > s))
                {
                    s = sk;
                    distance = dk;
                    found = true;
                }
            }
            return found;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------------------------------------------------

        /// <summary>Point of segment p0-p1 (arcs s0..s1) at arc s, assumed in [s0, s1].</summary>
        private static Vec2d PointOnSegment(Vec2d p0, Vec2d p1, double s0, double s1, double s)
        {
            double ls = s1 - s0;
            if (!(ls > 0.0)) return p0;
            return Vec2d.Lerp(p0, p1, (s - s0) / ls);
        }

        /// <summary>
        /// Fills candidates with every segment index &lt; idLimit registered in a bucket touched by the box, each once.
        /// When the box spans many more buckets than there are segments, every segment is listed instead (same result).
        /// </summary>
        private void GatherCandidates(double minX, double minY, double maxX, double maxY, int idLimit)
        {
            candidates.Clear();
            if (idLimit <= 0) return;
            if (buckets.BucketSpan(minX, minY, maxX, maxY) > 2L * idLimit + 8)
            {
                for (int k = 0; k < idLimit; k++) candidates.Add(k);
                return;
            }
            if (stamp == int.MaxValue)
            {
                Array.Clear(stamps, 0, stamps.Length);
                stamp = 0;
            }
            stamp++;
            buckets.Query(minX, minY, maxX, maxY, idLimit, stamps, stamp, candidates);
        }
    }

    /// <summary>
    /// Uniform spatial hash of segments, bucket SegmentBuckets.Size = 2 u (contract 5.4). A segment is registered in
    /// every bucket its points can lie in (conservative, per bucket row), so a query box that intersects a segment
    /// always finds it. Keys are looked up, never iterated in a way that affects results (determinism).
    /// Shared by Trail and LoopErase.
    /// </summary>
    internal sealed class SegmentBuckets
    {
        internal const double Size = 2.0;
        private const double InvSize = 1.0 / Size;
        private const double CellLimit = 1e9;  // bucket coordinates clamped to keep keys and loops in int range
        private const double RowPad = 1e-7;    // padding of the x extent of a segment within a bucket row (rounding)

        private readonly Dictionary<long, List<int>> map = new Dictionary<long, List<int>>();
        private readonly Stack<List<int>> pool = new Stack<List<int>>();

        internal static int Cell(double v)
        {
            double c = Math.Floor(v * InvSize);
            if (double.IsNaN(c)) return 0;
            if (c < -CellLimit) c = -CellLimit;
            else if (c > CellLimit) c = CellLimit;
            return (int)c;
        }

        private static long Key(int bx, int by) => ((long)bx << 32) | (uint)by;

        public void Clear()
        {
            foreach (KeyValuePair<long, List<int>> kv in map)
            {
                kv.Value.Clear();
                pool.Push(kv.Value);
            }
            map.Clear();
        }

        public long BucketSpan(double minX, double minY, double maxX, double maxY)
        {
            return (long)(Cell(maxX) - Cell(minX) + 1) * (Cell(maxY) - Cell(minY) + 1);
        }

        public void Add(int id, Vec2d p, Vec2d q)
        {
            double minX = Math.Min(p.X, q.X), maxX = Math.Max(p.X, q.X);
            double minY = Math.Min(p.Y, q.Y), maxY = Math.Max(p.Y, q.Y);
            int by0 = Cell(minY), by1 = Cell(maxY);
            if (by0 == by1)
            {
                int bx1 = Cell(maxX);
                for (int bx = Cell(minX); bx <= bx1; bx++) AddToBucket(bx, by0, id);
                return;
            }
            // The segment spans several rows, so dy != 0: register, per row, the buckets of its x extent in that row.
            // The pad covers the rounding of (y - p.Y) amplified by |dx / dy| (nearly horizontal segments).
            double dx = q.X - p.X, dy = q.Y - p.Y;
            double slope = Math.Abs(dx / dy);
            double pad = RowPad + slope * 4.5e-16 * (Math.Max(Math.Abs(minY), Math.Abs(maxY)) + Size);
            for (int by = by0; by <= by1; by++)
            {
                double yLo = Math.Max(minY, by * Size), yHi = Math.Min(maxY, (by + 1) * Size);
                double xa = p.X + (yLo - p.Y) * dx / dy;
                double xb = p.X + (yHi - p.Y) * dx / dy;
                double xl = Math.Max(minX, Math.Min(xa, xb) - pad);
                double xr = Math.Min(maxX, Math.Max(xa, xb) + pad);
                int bx1 = Cell(xr);
                for (int bx = Cell(xl); bx <= bx1; bx++) AddToBucket(bx, by, id);
            }
        }

        private void AddToBucket(int bx, int by, int id)
        {
            long key = Key(bx, by);
            if (!map.TryGetValue(key, out List<int> list))
            {
                list = pool.Count > 0 ? pool.Pop() : new List<int>(8);
                map.Add(key, list);
            }
            list.Add(id);
        }

        /// <summary>
        /// Appends to output every id &lt; idLimit registered in a bucket touched by the box, once (stamps[id] == stamp
        /// marks an id already appended; the caller provides a fresh stamp value).
        /// </summary>
        public void Query(double minX, double minY, double maxX, double maxY, int idLimit, int[] stamps, int stamp,
                          List<int> output)
        {
            int bx0 = Cell(minX), bx1 = Cell(maxX), by0 = Cell(minY), by1 = Cell(maxY);
            for (int by = by0; by <= by1; by++)
            {
                for (int bx = bx0; bx <= bx1; bx++)
                {
                    if (!map.TryGetValue(Key(bx, by), out List<int> list)) continue;
                    for (int i = 0; i < list.Count; i++)
                    {
                        int id = list[i];
                        if (id >= idLimit || stamps[id] == stamp) continue;
                        stamps[id] = stamp;
                        output.Add(id);
                    }
                }
            }
        }
    }
}
