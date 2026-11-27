using System;
using System.Collections.Generic;
using System.Diagnostics;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    // A3 trail tests (contract 10.1 "Trail", "LoopErase", "LassoGeometry"; algorithms of 5.4 and section 8).
    // Pure NUnit (Unity ships NUnit 3.5): Assert.That / AreEqual / IsTrue / Throws only.

    internal static class TrailTestUtil
    {
        public const double R = 0.63;      // Tuning.HeadRadius + Tuning.TrailHalfWidth
        public const double Grace = 1.0;   // Tuning.HeadGrace

        public static Trail Make(params double[] xy)
        {
            var t = new Trail();
            for (int i = 0; i + 1 < xy.Length; i += 2)
            {
                var p = new Vec2d(xy[i], xy[i + 1]);
                if (i == 0) t.Start(p);
                else t.Append(p);
            }
            return t;
        }

        public static List<Vec2d> Poly(params double[] xy)
        {
            var list = new List<Vec2d>();
            for (int i = 0; i + 1 < xy.Length; i += 2) list.Add(new Vec2d(xy[i], xy[i + 1]));
            return list;
        }

        public static void AreClose(Vec2d expected, Vec2d actual, double eps, string message = "")
        {
            Assert.AreEqual(expected.X, actual.X, eps, message + " (x) expected " + expected + " got " + actual);
            Assert.AreEqual(expected.Y, actual.Y, eps, message + " (y) expected " + expected + " got " + actual);
        }

        public static void AreClose(IList<Vec2d> expected, IList<Vec2d> actual, double eps)
        {
            Assert.AreEqual(expected.Count, actual.Count, "point count, got " + string.Join(" ", actual));
            for (int i = 0; i < expected.Count; i++) AreClose(expected[i], actual[i], eps, "point " + i);
        }

        /// <summary>Exposed limit E(u) of contract 5.4.</summary>
        public static double ExposedLimit(Trail t, double u, double uOwnerStart, double growth, double grace)
        {
            return t.Length + Math.Max(0.0, u - uOwnerStart) * growth - grace;
        }

        /// <summary>Brute force: distance from q to the part of the trail with arcs in [0, e].</summary>
        public static double ExposedDistance(Trail t, Vec2d q, double e)
        {
            if (t.Count == 0 || e < 0.0) return double.PositiveInfinity;
            if (t.Count == 1) return Vec2d.Distance(q, t.Points[0]);
            double best = double.PositiveInfinity;
            for (int k = 0; k + 1 < t.Count; k++)
            {
                double s0 = t.Arc[k], s1 = t.Arc[k + 1];
                if (s0 > e) break;
                Vec2d p0 = t.Points[k];
                Vec2d pe = e >= s1 ? t.Points[k + 1] : Vec2d.Lerp(p0, t.Points[k + 1], (e - s0) / (s1 - s0));
                best = Math.Min(best, Geo.DistancePointSegment(q, p0, pe));
            }
            return best;
        }

        /// <summary>
        /// Simulates an owner running +x along y = 0 at 6 u/s (trail (0,0)-(6,0) at t = 0, stored end = head at each tick
        /// start, as the engine keeps it) against an attacker following attacker(t), at the given tick rate. Returns the
        /// first contact time and sCut.
        /// </summary>
        public static bool RunOwnerVsAttacker(int rate, Func<double, Vec2d> attacker, double tMax, out double tHit, out double sCut)
        {
            const double speed = 6.0;
            double dt = 1.0 / rate;
            var trail = Make(0, 0, 6, 0);
            long ticks = (long)Math.Ceiling(tMax * rate);
            for (long k = 0; k < ticks; k++)
            {
                double t0 = k / (double)rate;
                double t1 = (k + 1) / (double)rate;
                if (trail.FirstContact(attacker(t0), attacker(t1), R, 0.0, 0.0, speed * dt, Grace, out double u, out double s))
                {
                    tHit = t0 + u * dt;
                    sCut = s;
                    return true;
                }
                trail.Append(new Vec2d(6.0 + speed * t1, 0.0));
            }
            tHit = double.NaN;
            sCut = double.NaN;
            return false;
        }
    }

    public class TrailBasicsTests
    {
        private const double Eps = 1e-12;

        [Test]
        public void Trail_EmptyStartAppendClear()
        {
            var t = new Trail();
            Assert.AreEqual(0, t.Count);
            Assert.IsTrue(t.IsEmpty);
            Assert.AreEqual(0.0, t.Length);
            int v0 = t.Version;

            t.Start(new Vec2d(1, 2));
            Assert.AreEqual(1, t.Count);
            Assert.IsFalse(t.IsEmpty);
            Assert.AreEqual(0.0, t.Length, "one point has no length");
            Assert.AreEqual(0.0, t.Arc[0]);
            Assert.AreEqual(new Vec2d(1, 2), t.Points[0]);
            Assert.That(t.Version, Is.Not.EqualTo(v0));

            int v1 = t.Version;
            t.Append(new Vec2d(1 + 5e-10, 2));
            Assert.AreEqual(1, t.Count, "a point closer than 1e-9 to the last is ignored");
            Assert.AreEqual(v1, t.Version, "an ignored Append is not a mutation");

            t.Append(new Vec2d(4, 6));
            Assert.AreEqual(2, t.Count);
            Assert.AreEqual(5.0, t.Length, Eps);
            Assert.That(t.Version, Is.Not.EqualTo(v1));

            t.Start(new Vec2d(0, 0));
            Assert.AreEqual(1, t.Count, "Start clears first");
            Assert.AreEqual(0.0, t.Length);
            Assert.AreEqual(new Vec2d(0, 0), t.Points[0]);

            int v2 = t.Version;
            t.Clear();
            Assert.AreEqual(0, t.Count);
            Assert.IsTrue(t.IsEmpty);
            Assert.That(t.Version, Is.Not.EqualTo(v2));

            t.Append(new Vec2d(3, 3));
            Assert.AreEqual(1, t.Count, "Append on an empty trail adds the first point");
            Assert.AreEqual(0.0, t.Arc[0]);
        }

        [Test]
        public void Trail_ArcIsCumulative()
        {
            Trail t = TrailTestUtil.Make(0, 0, 3, 0, 3, 4, 0, 4);
            Assert.AreEqual(4, t.Count);
            Assert.AreEqual(0.0, t.Arc[0]);
            Assert.AreEqual(3.0, t.Arc[1], Eps);
            Assert.AreEqual(7.0, t.Arc[2], Eps);
            Assert.AreEqual(10.0, t.Arc[3], Eps);
            Assert.AreEqual(10.0, t.Length, Eps);
            Assert.AreEqual(new Vec2d(3, 4), t.Points[2]);
        }

        [Test]
        public void Trail_PointAt_InterpolatesAndClamps()
        {
            Trail t = TrailTestUtil.Make(0, 0, 3, 0, 3, 4, 0, 4);
            Assert.AreEqual(new Vec2d(0, 0), t.PointAt(-1.0), "clamped below");
            Assert.AreEqual(new Vec2d(0, 0), t.PointAt(0.0));
            Assert.AreEqual(new Vec2d(0, 0), t.PointAt(double.NaN), "NaN gives the first point");
            TrailTestUtil.AreClose(new Vec2d(1.5, 0), t.PointAt(1.5), Eps);
            TrailTestUtil.AreClose(new Vec2d(3, 0), t.PointAt(3.0), Eps);
            TrailTestUtil.AreClose(new Vec2d(3, 2), t.PointAt(5.0), Eps);
            TrailTestUtil.AreClose(new Vec2d(1.5, 4), t.PointAt(8.5), Eps);
            Assert.AreEqual(new Vec2d(0, 4), t.PointAt(10.0), "Length gives the last point exactly");
            Assert.AreEqual(new Vec2d(0, 4), t.PointAt(99.0), "clamped above");

            Assert.AreEqual(Vec2d.Zero, new Trail().PointAt(1.0), "empty trail");
            Assert.AreEqual(new Vec2d(2, 5), TrailTestUtil.Make(2, 5).PointAt(1.0), "single point");
        }

        [Test]
        public void Trail_DirectionAt_UnitTangentOfContainingSegment()
        {
            Trail t = TrailTestUtil.Make(0, 0, 3, 0, 3, 4, 0, 4);
            TrailTestUtil.AreClose(new Vec2d(1, 0), t.DirectionAt(-1.0), Eps);
            TrailTestUtil.AreClose(new Vec2d(1, 0), t.DirectionAt(1.5), Eps);
            TrailTestUtil.AreClose(new Vec2d(0, 1), t.DirectionAt(3.0), Eps, "a vertex belongs to the segment that starts there");
            TrailTestUtil.AreClose(new Vec2d(0, 1), t.DirectionAt(5.0), Eps);
            TrailTestUtil.AreClose(new Vec2d(-1, 0), t.DirectionAt(10.0), Eps, "Length belongs to the last segment");
            TrailTestUtil.AreClose(new Vec2d(-1, 0), t.DirectionAt(50.0), Eps);
            Trail diag = TrailTestUtil.Make(0, 0, 3, 4);
            TrailTestUtil.AreClose(new Vec2d(0.6, 0.8), diag.DirectionAt(2.0), Eps);
            Assert.AreEqual(Vec2d.Zero, TrailTestUtil.Make(1, 1).DirectionAt(0.0), "no segment");
        }

        [Test]
        public void Trail_SegmentIndexAt()
        {
            Trail t = TrailTestUtil.Make(0, 0, 3, 0, 3, 4, 0, 4);
            Assert.AreEqual(0, t.SegmentIndexAt(-1.0));
            Assert.AreEqual(0, t.SegmentIndexAt(0.0));
            Assert.AreEqual(0, t.SegmentIndexAt(2.999));
            Assert.AreEqual(1, t.SegmentIndexAt(3.0));
            Assert.AreEqual(1, t.SegmentIndexAt(6.9));
            Assert.AreEqual(2, t.SegmentIndexAt(7.0));
            Assert.AreEqual(2, t.SegmentIndexAt(10.0));
            Assert.AreEqual(2, t.SegmentIndexAt(50.0));
            Assert.AreEqual(-1, TrailTestUtil.Make(1, 1).SegmentIndexAt(0.0));
            Assert.AreEqual(-1, new Trail().SegmentIndexAt(0.0));
        }

        [Test]
        public void Trail_ClosestPointWithin()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0, 10, 10); // arcs 0, 10, 20
            Assert.IsTrue(t.ClosestPointWithin(new Vec2d(5, 1), 2, 30, out double s, out double d));
            Assert.AreEqual(5.0, s, Eps);
            Assert.AreEqual(1.0, d, Eps);
            Assert.IsFalse(t.ClosestPointWithin(new Vec2d(5, 1), 2, 3, out _, out _), "arcs beyond maxArc are ignored");
            Assert.IsTrue(t.ClosestPointWithin(new Vec2d(5, 1), 3, 3, out s, out d));
            Assert.AreEqual(3.0, s, Eps);
            Assert.AreEqual(Math.Sqrt(5), d, Eps);
            Assert.IsTrue(t.ClosestPointWithin(new Vec2d(11, 5), 2, 30, out s, out d));
            Assert.AreEqual(15.0, s, Eps);

            Trail back = TrailTestUtil.Make(0, 0, 10, 0, 2, 0); // x = 5 at arcs 5 and 15
            Assert.IsTrue(back.ClosestPointWithin(new Vec2d(5, 1), 2, 100, out s, out d));
            Assert.AreEqual(15.0, s, Eps, "equal distances: the most recent pass");

            Assert.IsFalse(new Trail().ClosestPointWithin(new Vec2d(0, 0), 5, 5, out _, out _));
            Assert.IsTrue(TrailTestUtil.Make(1, 1).ClosestPointWithin(new Vec2d(1, 2), 1.5, 0, out s, out d));
            Assert.AreEqual(0.0, s);
            Assert.AreEqual(1.0, d, Eps);
        }

        [Test]
        public void Trail_PointsAndArcAreLiveReadOnlyViews()
        {
            var t = new Trail();
            IReadOnlyList<Vec2d> pts = t.Points;
            IReadOnlyList<double> arc = t.Arc;
            t.Start(new Vec2d(0, 0));
            t.Append(new Vec2d(0, 2));
            Assert.AreEqual(2, pts.Count);
            Assert.AreEqual(2.0, arc[1], Eps);
            Assert.IsFalse(pts is List<Vec2d>, "callers cannot cast the view back to a mutable list");
        }
    }

    public class TrailFirstContactTests
    {
        private const double Eps = 1e-12;
        private const double R = TrailTestUtil.R;
        private const double H = TrailTestUtil.Grace;

        [Test]
        public void Trail_FirstContact_PerpendicularApproachTouchesAtRadius()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0);
            Assert.IsTrue(t.FirstContact(new Vec2d(3, 2), new Vec2d(3, 0), R, 0, 0, 0, H, out double u, out double s));
            Assert.AreEqual((2 - R) / 2, u, Eps);
            Assert.AreEqual(3.0, s, Eps, "a first touch gives the touched point");

            Assert.IsFalse(t.FirstContact(new Vec2d(4, -2), new Vec2d(4, -1), R, 0, 0, 0, H, out u, out s),
                "stops 1 u away: no contact");
            Assert.AreEqual(double.PositiveInfinity, u, "u is +inf on false so 'u > uEnd' rejects it");
        }

        [Test]
        public void Trail_FirstContact_HeadGraceProtectsTheLastUnitOfArc()
        {
            // L = 10, HeadGrace = 1: exposed arcs [0, 9].
            Trail t = TrailTestUtil.Make(0, 0, 10, 0);
            Assert.IsFalse(t.FirstContact(new Vec2d(9.8, 2), new Vec2d(9.8, -2), R, 0, 0, 0, H, out _, out _),
                "crossing 0.8 u beyond the exposed end: no cut");

            // Crossing 0.5 u beyond the exposed end: the exposed end point (9, 0) is reached by the motion.
            Assert.IsTrue(t.FirstContact(new Vec2d(9.5, 2), new Vec2d(9.5, -2), R, 0, 0, 0, H, out double u, out double s));
            double y = Math.Sqrt(R * R - 0.25);
            Assert.AreEqual((2 - y) / 4, u, Eps);
            Assert.AreEqual(9.0, s, Eps, "sCut is the exposed limit L - HeadGrace");

            Assert.IsTrue(t.FirstContact(new Vec2d(5, 2), new Vec2d(5, -2), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual((2 - R) / 4, u, Eps);
            Assert.AreEqual(5.0, s, Eps);

            Assert.IsTrue(t.FirstContact(new Vec2d(9.8, 2), new Vec2d(9.8, -2), R, 0, 0, 0, 0.0, out u, out s),
                "without grace the same crossing cuts");
            Assert.AreEqual(9.8, s, Eps);
        }

        [Test]
        public void Trail_FirstContact_ExposureInducedContactWhileAttackerWaitsOverGraceZone()
        {
            // Stationary attacker on the centerline at x = 9.9 (inside the grace zone). The owner grows 0.5 u per tick:
            // E(u) = 9 + 0.5 u reaches 9.9 - R = 9.27 at u = 0.54, and the touched point is the exposure end.
            Trail t = TrailTestUtil.Make(0, 0, 10, 0);
            var a = new Vec2d(9.9, 0);
            Assert.IsTrue(t.FirstContact(a, a, R, 0, 0, 0.5, H, out double u, out double s));
            Assert.AreEqual(0.54, u, 1e-12);
            Assert.AreEqual(9.27, s, 1e-12);
            Assert.AreEqual(t.Length + 0.5 * u - H, s, 1e-12, "sCut = L(u) - HeadGrace");

            // The owner starts growing only at uOwnerStart = 0.2 (range split): contact 0.2 later.
            Assert.IsTrue(t.FirstContact(a, a, R, 0, 0.2, 0.5, H, out u, out s));
            Assert.AreEqual(0.74, u, 1e-12);
            Assert.AreEqual(9.27, s, 1e-12);

            // uMin after uOwnerStart (the engine's case after a mid-tick group): same instant.
            Assert.IsTrue(t.FirstContact(a, a, R, 0.3, 0.2, 0.5, H, out u, out s));
            Assert.AreEqual(0.74, u, 1e-12);

            // uOwnerStart >= 1: the owner does not grow in this query, no exposure change, no contact.
            Assert.IsFalse(t.FirstContact(a, a, R, 0, 1.0, 0.5, H, out _, out _));

            // Too slow to expose the point within the tick.
            Assert.IsFalse(t.FirstContact(a, a, R, 0, 0, 0.2, H, out _, out _));
        }

        [Test]
        public void Trail_FirstContact_ExposureInducedIsIdenticalAt30_60_144Hz()
        {
            // Stationary attacker over the grace zone: contact when the exposure end E(t) = 5 + 6t gets within R.
            var still = new Vec2d(7.3, 0.2);
            double xStill = 7.3 - Math.Sqrt(R * R - 0.04);
            double tStill = (xStill - 5.0) / 6.0;
            // Attacker drifting +x at 0.5 u/s over the trail at height 0.3: the exposure end catches up with it.
            Func<double, Vec2d> drift = time => new Vec2d(8.5 + 0.5 * time, 0.3);
            double tDrift = (3.5 - Math.Sqrt(R * R - 0.09)) / 5.5;
            double sDrift = 5.0 + 6.0 * tDrift;

            var rates = new[] { 30, 60, 144 };
            var hitStill = new double[3];
            var hitDrift = new double[3];
            for (int i = 0; i < rates.Length; i++)
            {
                Assert.IsTrue(TrailTestUtil.RunOwnerVsAttacker(rates[i], time => still, 1.0, out double th, out double sc),
                    "stationary attacker at " + rates[i] + " Hz");
                Assert.AreEqual(tStill, th, 1e-9, "contact time at " + rates[i] + " Hz");
                Assert.AreEqual(xStill, sc, 1e-9, "sCut at " + rates[i] + " Hz");
                Assert.AreEqual(5.0 + 6.0 * th, sc, 1e-9, "sCut = L(t) - HeadGrace");
                hitStill[i] = th;

                Assert.IsTrue(TrailTestUtil.RunOwnerVsAttacker(rates[i], drift, 1.0, out th, out sc),
                    "drifting attacker at " + rates[i] + " Hz");
                Assert.AreEqual(tDrift, th, 1e-9, "contact time at " + rates[i] + " Hz");
                Assert.AreEqual(sDrift, sc, 1e-9, "sCut at " + rates[i] + " Hz");
                hitDrift[i] = th;
            }
            Assert.AreEqual(hitStill[0], hitStill[2], 1e-9);
            Assert.AreEqual(hitDrift[1], hitDrift[2], 1e-9);
        }

        [Test]
        public void Trail_FirstContact_AttackerMovingParallelToASegment()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0); // exposed [0, 9]

            // Parallel at height 0.3 from the left: enters through the end disk around the exposed start point.
            Assert.IsTrue(t.FirstContact(new Vec2d(-2, 0.3), new Vec2d(2, 0.3), R, 0, 0, 0, H, out double u, out double s));
            double x = -Math.Sqrt(R * R - 0.09);
            Assert.AreEqual((x + 2) / 4, u, Eps);
            Assert.AreEqual(0.0, s, Eps);

            // Parallel at height 0.7 along the whole segment: never within R.
            Assert.IsFalse(t.FirstContact(new Vec2d(-2, 0.7), new Vec2d(12, 0.7), R, 0, 0, 0, H, out _, out _));

            // Along the centerline from beyond the far end: the first exposed point met is the exposure end (9, 0).
            Assert.IsTrue(t.FirstContact(new Vec2d(12, 0), new Vec2d(8, 0), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual((12 - 9.63) / 4, u, Eps);
            Assert.AreEqual(9.0, s, Eps);

            // Already inside at uMin while moving parallel: u = uMin, sCut = foot of the perpendicular.
            Assert.IsTrue(t.FirstContact(new Vec2d(4, 0.5), new Vec2d(6, 0.5), R, 0.25, 0, 0, H, out u, out s));
            Assert.AreEqual(0.25, u, Eps);
            Assert.AreEqual(4.5, s, Eps);
        }

        [Test]
        public void Trail_FirstContact_OverlapAtUMinDoesNotDependOnSubdivision()
        {
            // The same straight path stored as 1 segment or as 10 segments: the attacker overlapping at uMin gets the
            // perpendicular foot (4.8) in both cases, not the next vertex (5, 0), which also lies within R.
            Trail one = TrailTestUtil.Make(0, 0, 10, 0);
            Trail ten = TrailTestUtil.Make(0, 0, 1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0, 7, 0, 8, 0, 9, 0, 10, 0);
            var a = new Vec2d(4.8, 0.5);
            Assert.IsTrue(one.FirstContact(a, a, R, 0, 0, 0, H, out double u1, out double s1));
            Assert.IsTrue(ten.FirstContact(a, a, R, 0, 0, 0, H, out double u10, out double s10));
            Assert.AreEqual(0.0, u1);
            Assert.AreEqual(0.0, u10);
            Assert.AreEqual(4.8, s1, Eps);
            Assert.AreEqual(4.8, s10, Eps);

            // Tangential touch 2e-5 u before a vertex: the touched point, not the vertex (which is within R + 1e-9).
            Trail split = TrailTestUtil.Make(0, 0, 5.00002, 0, 10, 0);
            Assert.IsTrue(split.FirstContact(new Vec2d(5, 2), new Vec2d(5, 0), R, 0, 0, 0, H, out double u, out double s));
            Assert.AreEqual((2 - R) / 2, u, Eps);
            Assert.AreEqual(5.0, s, 1e-9);
        }

        [Test]
        public void Trail_FirstContact_SuperposedPassesGiveTheMostRecentPass()
        {
            // Out along y = 0 to x = 10, back over the same line to x = 2, then away. x = 5 lies at arcs 5 and 15.
            Trail t = TrailTestUtil.Make(0, 0, 10, 0, 2, 0, 2, -5);
            Assert.IsTrue(t.FirstContact(new Vec2d(5, 2), new Vec2d(5, 0), R, 0, 0, 0, H, out double u, out double s));
            Assert.AreEqual((2 - R) / 2, u, Eps);
            Assert.AreEqual(15.0, s, 1e-9, "the most recent pass");

            // Two passes crossing at (5, 5) at right angles, touched at the same instant from the bisector.
            Trail x = TrailTestUtil.Make(0, 0, 10, 10, 10, 0, 0, 10, 0, 14);
            double yC = 5 - R * Math.Sqrt(2);
            Assert.IsTrue(x.FirstContact(new Vec2d(5, 1), new Vec2d(5, 5), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual((yC - 1) / 4, u, 1e-12);
            double s2 = x.Arc[2] + (5 + yC) / Math.Sqrt(2);
            Assert.AreEqual(s2, s, 1e-9, "the later of the two touched points");
        }

        [Test]
        public void Trail_FirstContact_ZeroLengthMotion()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0);
            var far = new Vec2d(5, 2);
            Assert.IsFalse(t.FirstContact(far, far, R, 0, 0, 0, H, out _, out _));

            var near = new Vec2d(5, 0.5);
            Assert.IsTrue(t.FirstContact(near, near, R, 0.4, 0, 0, H, out double u, out double s));
            Assert.AreEqual(0.4, u, "already within R: u = uMin");
            Assert.AreEqual(5.0, s, Eps);

            var grace = new Vec2d(9.9, 0);
            Assert.IsFalse(t.FirstContact(grace, grace, R, 0, 0, 0, H, out _, out _), "owner not moving: stays protected");
            Assert.IsTrue(t.FirstContact(grace, grace, R, 0, 0, 0.5, H, out u, out s), "owner moving: exposed at u = 0.54");
            Assert.AreEqual(0.54, u, 1e-12);
        }

        [Test]
        public void Trail_FirstContact_RespectsUMin()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0);
            var a = new Vec2d(5, 1);
            var b = new Vec2d(5, -1); // in contact for u in [0.185, 0.815]
            Assert.IsTrue(t.FirstContact(a, b, R, 0, 0, 0, H, out double u, out double s));
            Assert.AreEqual(0.185, u, Eps);
            Assert.IsTrue(t.FirstContact(a, b, R, 0.5, 0, 0, H, out u, out s));
            Assert.AreEqual(0.5, u, "still inside at uMin");
            Assert.AreEqual(5.0, s, Eps);
            Assert.IsFalse(t.FirstContact(a, b, R, 0.9, 0, 0, H, out _, out _), "already through");
            Assert.IsFalse(t.FirstContact(a, b, R, 1.5, 0, 0, H, out _, out _), "uMin beyond the tick");
        }

        [Test]
        public void Trail_FirstContact_EarliestSegmentWins()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0, 10, 10, 0, 10); // arcs 0, 10, 20, 30; exposed [0, 29]
            var c = new Vec2d(5, 5);
            Assert.IsTrue(t.FirstContact(c, new Vec2d(5, 12), R, 0, 0, 0, H, out double u, out double s));
            Assert.AreEqual(4.37 / 7, u, Eps);
            Assert.AreEqual(25.0, s, Eps);
            Assert.IsTrue(t.FirstContact(c, new Vec2d(5, -2), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual(4.37 / 7, u, Eps);
            Assert.AreEqual(5.0, s, Eps);
            Assert.IsTrue(t.FirstContact(c, new Vec2d(12, 5), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual(4.37 / 7, u, Eps);
            Assert.AreEqual(15.0, s, Eps);
            Assert.IsTrue(t.FirstContact(new Vec2d(5, 11), new Vec2d(5, -2), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual(0.37 / 13, u, Eps, "the top pass is met first even though the bottom one is older");
            Assert.AreEqual(25.0, s, Eps);
        }

        [Test]
        public void Trail_FirstContact_EmptyShortOrSinglePointTrail()
        {
            var a = new Vec2d(0.3, 0);
            Assert.IsFalse(new Trail().FirstContact(a, a, R, 0, 0, 0.1, H, out _, out _), "empty");
            Trail single = TrailTestUtil.Make(0, 0);
            Assert.IsFalse(single.FirstContact(a, a, R, 0, 0, 0.1, H, out _, out _), "a fresh exit is in the grace zone");
            Assert.IsTrue(single.FirstContact(a, a, R, 0, 0, 0.1, 0.0, out double u, out double s), "no grace: exposed");
            Assert.AreEqual(0.0, u);
            Assert.AreEqual(0.0, s);
            Trail shortTrail = TrailTestUtil.Make(0, 0, 0.5, 0);
            Assert.IsFalse(shortTrail.FirstContact(a, a, R, 0, 0, 0.1, H, out _, out _), "shorter than HeadGrace");
        }

        [Test]
        public void Trail_FirstContact_LongSegmentsBucketBoundariesAndFarCoordinates()
        {
            // An 85 u diagonal segment (DebugSetTrail style) spans many hash buckets.
            Trail diag = TrailTestUtil.Make(-30, -30, 30, 30, -30, 29);
            Assert.IsTrue(diag.FirstContact(new Vec2d(0, 2), new Vec2d(0, -2), R, 0, 0, 0, H, out double u, out double s));
            double y = R * Math.Sqrt(2);
            Assert.AreEqual((2 - y) / 4, u, 1e-12);
            Assert.AreEqual((30 + y / 2) * Math.Sqrt(2), s, 1e-9);

            // A segment lying exactly on a bucket row boundary (y = 2), approached from both rows.
            Trail edge = TrailTestUtil.Make(0, 2, 10, 2);
            Assert.IsTrue(edge.FirstContact(new Vec2d(5, 0), new Vec2d(5, 2), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual((2 - R) / 2, u, Eps);
            Assert.AreEqual(5.0, s, Eps);
            Assert.IsTrue(edge.FirstContact(new Vec2d(5, 4), new Vec2d(5, 2), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual((2 - R) / 2, u, Eps);

            // Far from the origin (bucket keys with large coordinates).
            Trail farTrail = TrailTestUtil.Make(1000, -1000, 1010, -1000);
            Assert.IsTrue(farTrail.FirstContact(new Vec2d(1005, -998), new Vec2d(1005, -1000), R, 0, 0, 0, H, out u, out s));
            Assert.AreEqual((2 - R) / 2, u, 1e-9);
            Assert.AreEqual(5.0, s, 1e-9);
        }

        [Test]
        public void Trail_FirstContact_AgreesWithBruteForceSampling()
        {
            // Random trails and queries (with growth, uMin and uOwnerStart on both sides of uMin). Checks that the
            // returned u is a contact, that no sampled earlier u is one, that a false result has no sampled contact,
            // and that sCut is the largest-arc local minimum of the exposed distance within R (independent sampling).
            var rng = new Rng(20261126);
            int contacts = 0, misses = 0, exposureEnds = 0;
            for (int trailIndex = 0; trailIndex < 6; trailIndex++)
            {
                Trail t = RandomWalk(rng, 300);
                for (int qi = 0; qi < 60; qi++)
                {
                    double sPick = rng.Range(0, t.Length);
                    Vec2d basePos = t.PointAt(sPick) + Vec2d.FromAngle(rng.Range(-Math.PI, Math.PI)) * rng.Range(0, 1.2);
                    double len = rng.NextDouble() < 0.1 ? 0.0 : rng.Range(0, 0.6);
                    Vec2d a = basePos;
                    Vec2d b = basePos + Vec2d.FromAngle(rng.Range(-Math.PI, Math.PI)) * len;
                    double uMin = rng.NextDouble() < 0.3 ? 0.0 : rng.Range(0, 0.6);
                    double uOwner = rng.Range(-0.2, 1.2);
                    double growth = rng.Range(0, 0.25);
                    double grace = rng.NextDouble() < 0.5 ? H : rng.Range(0, 6);

                    bool hit = t.FirstContact(a, b, R, uMin, uOwner, growth, grace, out double u, out double s);
                    if (hit)
                    {
                        contacts++;
                        Assert.That(u, Is.GreaterThanOrEqualTo(uMin));
                        Assert.That(u, Is.LessThanOrEqualTo(1.0));
                        Vec2d q = Vec2d.Lerp(a, b, u);
                        double e = Math.Min(TrailTestUtil.ExposedLimit(t, u, uOwner, growth, grace), t.Length);
                        Assert.That(TrailTestUtil.ExposedDistance(t, q, e), Is.LessThanOrEqualTo(R + 1e-9), "u is a contact");
                        for (int i = 0; i < 200; i++)
                        {
                            double ue = uMin + (u - uMin) * i / 200.0;
                            if (u - ue < 1e-7) break;
                            double ee = TrailTestUtil.ExposedLimit(t, ue, uOwner, growth, grace);
                            Assert.That(TrailTestUtil.ExposedDistance(t, Vec2d.Lerp(a, b, ue), ee), Is.GreaterThan(R - 1e-9),
                                "no contact before u (trail " + trailIndex + " query " + qi + ")");
                        }
                        Assert.That(s, Is.LessThanOrEqualTo(e + 1e-12), "sCut is exposed");
                        Assert.That(Vec2d.Distance(q, t.PointAt(s)), Is.LessThanOrEqualTo(R + 1e-7), "sCut is touched");
                        double sRef = SampledLargestLocalMinimum(t, q, e);
                        Assert.AreEqual(sRef, s, 2e-3, "sCut vs sampled reference (trail " + trailIndex + " query " + qi + ")");
                        if (Math.Abs(s - e) < 1e-9) exposureEnds++;
                    }
                    else
                    {
                        misses++;
                        for (int i = 0; i <= 400; i++)
                        {
                            double ue = uMin + (1.0 - uMin) * i / 400.0;
                            double ee = TrailTestUtil.ExposedLimit(t, ue, uOwner, growth, grace);
                            Assert.That(TrailTestUtil.ExposedDistance(t, Vec2d.Lerp(a, b, ue), ee), Is.GreaterThan(R - 1e-9),
                                "false but a sampled contact exists (trail " + trailIndex + " query " + qi + ")");
                        }
                    }
                }
            }
            Assert.That(contacts, Is.GreaterThan(50), "the sample must exercise contacts");
            Assert.That(misses, Is.GreaterThan(20), "the sample must exercise misses");
            Assert.That(exposureEnds, Is.GreaterThan(0), "the sample must exercise exposure-end contacts");
        }

        [Test]
        public void Trail_FirstContact_Perf2000Points()
        {
            // A 2000-point trail of 60 Hz steps (0.1 u, 200 u long) wandering in a 40 x 40 u area: the stress case of one
            // exit, still far denser than a real round. The dense variant packs it into 12 x 12 u (worst case).
            // Near: every query within 1.5 u of the trail (mostly contacts, the expensive path). Uniform: queries spread
            // over the area the trail wanders in (the typical tick: most attackers are not touching this trail).
            double us = MeasureFirstContact(20.0, true, out int hits, out double usCross, out int crossCount);
            double usUniform = MeasureFirstContact(20.0, false, out int hitsUniform, out _, out _);
            double usDense = MeasureFirstContact(6.0, true, out int hitsDense, out double usCrossDense, out _);
            TestContext.WriteLine("Trail perf, 2000 points in 40 x 40 u, queries near the trail: FirstContact " + us.ToString("F3") +
                                  " us/query (" + hits + " hits of " + PerfQueries + "), SelfCrossings " + usCross.ToString("F3") +
                                  " us/query (" + crossCount + " crossings)");
            TestContext.WriteLine("Trail perf, 2000 points in 40 x 40 u, uniform queries: FirstContact " + usUniform.ToString("F3") +
                                  " us/query (" + hitsUniform + " hits)");
            TestContext.WriteLine("Trail perf, 2000 points in 12 x 12 u (dense worst case), queries near the trail: FirstContact " +
                                  usDense.ToString("F3") + " us/query (" + hitsDense + " hits), SelfCrossings " +
                                  usCrossDense.ToString("F3") + " us/query");
            Assert.That(hits, Is.GreaterThan(PerfQueries / 2), "near queries must mostly be contacts");
            Assert.That(us, Is.LessThan(50.0), "budget 5 us typical; 50 us is the flake-proof ceiling");
            Assert.That(usUniform, Is.LessThan(50.0));
            Assert.That(usCross, Is.LessThan(50.0));
            Assert.That(usDense, Is.LessThan(200.0));
        }

        private const int PerfQueries = 40000;

        private static double MeasureFirstContact(double box, bool nearTrail, out int hits, out double usCross, out int crossCount)
        {
            var rng = new Rng(777);
            Trail t = RandomWalk(rng, 2000, 0.1, 0.1, box);
            Assert.AreEqual(2000, t.Count);

            const int distinct = 4096;
            var qa = new Vec2d[distinct];
            var qb = new Vec2d[distinct];
            for (int i = 0; i < distinct; i++)
            {
                Vec2d basePos = nearTrail
                    ? t.PointAt(rng.Range(0, t.Length)) + Vec2d.FromAngle(rng.Range(-Math.PI, Math.PI)) * rng.Range(0, 1.5)
                    : new Vec2d(rng.Range(-box, box), rng.Range(-box, box));
                qa[i] = basePos;
                qb[i] = basePos + Vec2d.FromAngle(rng.Range(-Math.PI, Math.PI)) * 0.1; // one 60 Hz step
            }
            hits = 0;
            for (int i = 0; i < 2000; i++) t.FirstContact(qa[i % distinct], qb[i % distinct], R, 0, 0, 0.1, H, out _, out _);

            const int n = PerfQueries;
            var sw = Stopwatch.StartNew();
            for (int i = 0; i < n; i++)
            {
                if (t.FirstContact(qa[i % distinct], qb[i % distinct], R, 0, 0, 0.1, H, out _, out _)) hits++;
            }
            sw.Stop();
            double us = sw.Elapsed.TotalMilliseconds * 1000.0 / n;

            var crossings = new List<SelfCrossing>();
            var sw2 = Stopwatch.StartNew();
            crossCount = 0;
            for (int i = 0; i < n; i++) crossCount += t.SelfCrossings(qa[i % distinct], qb[i % distinct], 0, t.Length - 1.0, crossings);
            sw2.Stop();
            usCross = sw2.Elapsed.TotalMilliseconds * 1000.0 / n;
            return us;
        }

        internal static Trail RandomWalk(Rng rng, int count, double minStep = 0.05, double maxStep = 0.4, double box = 6.0)
        {
            var t = new Trail();
            Vec2d p = new Vec2d(rng.Range(-3, 3), rng.Range(-3, 3));
            double heading = rng.Range(-Math.PI, Math.PI);
            t.Start(p);
            int guard = 0;
            while (t.Count < count && guard++ < count * 20)
            {
                heading += rng.Range(-0.6, 0.6);
                Vec2d next = p + Vec2d.FromAngle(heading) * rng.Range(minStep, maxStep);
                if (Math.Abs(next.X) > box || Math.Abs(next.Y) > box)
                {
                    heading = Math.Atan2(-p.Y, -p.X) + rng.Range(-0.5, 0.5); // turn back toward the middle
                    continue;
                }
                p = next;
                t.Append(p);
            }
            return t;
        }

        /// <summary>
        /// Independent sCut reference: samples the exposed arcs of the segments near q every 0.0005 u and returns the
        /// largest arc that is a local minimum of the distance to q with a distance within R (+ sampling slack).
        /// </summary>
        private static double SampledLargestLocalMinimum(Trail t, Vec2d q, double e)
        {
            const double step = 0.0005;
            double best = double.NegativeInfinity;
            for (int k = 0; k + 1 < t.Count; k++)
            {
                double s0 = t.Arc[k];
                if (s0 > e) break;
                double s1 = Math.Min(t.Arc[k + 1], e);
                if (Geo.DistancePointSegment(q, t.Points[k], t.PointAt(s1)) > R + 1e-6) continue;
                int m = (int)Math.Ceiling((s1 - s0) / step);
                for (int i = 0; i <= m; i++)
                {
                    double s = i == m ? s1 : s0 + i * step;
                    double d = Vec2d.Distance(q, t.PointAt(s));
                    if (d > R + 1e-6) continue;
                    double dPrev = s - step >= 0 ? Vec2d.Distance(q, t.PointAt(s - step)) : double.PositiveInfinity;
                    double dNext = s + step <= e ? Vec2d.Distance(q, t.PointAt(s + step)) : double.PositiveInfinity;
                    if (d <= dPrev && d <= dNext && s > best) best = s;
                }
            }
            return best;
        }
    }

    public class TrailSelfCrossingTests
    {
        private const double Eps = 1e-12;

        // Arcs 0, 10, 14, 26, 30, 40, 43, 46. Segments 0 and 4 are superposed on y = 0; segment 2 runs along y = 4.
        private static Trail Zigzag() => TrailTestUtil.Make(0, 0, 10, 0, 10, 4, -2, 4, -2, 0, 8, 0, 8, -3, 5, -3);

        [Test]
        public void Trail_SelfCrossings_SingleCrossing()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0, 10, 5, 5, 5);
            var list = new List<SelfCrossing>();
            int n = t.SelfCrossings(new Vec2d(5, 5), new Vec2d(5, -1), 0, t.Length, list);
            Assert.AreEqual(1, n);
            Assert.AreEqual(1, list.Count);
            Assert.AreEqual(5.0 / 6.0, list[0].U, Eps);
            Assert.AreEqual(0, list[0].Segment);
            TrailTestUtil.AreClose(new Vec2d(5, 0), list[0].Point, Eps);
        }

        [Test]
        public void Trail_SelfCrossings_TangencyAdjacentAndUTurnAreNotCrossings()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0, 10, 5, 5, 5);
            var list = new List<SelfCrossing>();
            double all = t.Length;
            Assert.AreEqual(0, t.SelfCrossings(new Vec2d(5, 5), new Vec2d(8, 5), 0, all, list), "superposed U-turn on the last segment");
            Assert.AreEqual(0, t.SelfCrossings(new Vec2d(5, 5), new Vec2d(5, 8), 0, all, list), "leaving the segment just drawn");
            Assert.AreEqual(0, t.SelfCrossings(new Vec2d(5, 5), new Vec2d(5, 0.001), 0, all, list), "stops short of the old segment");
            Assert.AreEqual(0, t.SelfCrossings(new Vec2d(3, 0), new Vec2d(3, -2), 0, all, list), "starts on the old segment (a0 on the line)");
            Assert.AreEqual(0, t.SelfCrossings(new Vec2d(2, 0), new Vec2d(6, 0), 0, all, list), "collinear overlap");
            Assert.AreEqual(0, t.SelfCrossings(new Vec2d(11, 3), new Vec2d(11, -3), 0, all, list), "crosses the line beyond the segment");

            Assert.AreEqual(1, t.SelfCrossings(new Vec2d(5, 5), new Vec2d(5, 0), 0, all, list), "ending exactly on the old segment counts");
            Assert.AreEqual(1.0, list[0].U);
            Assert.AreEqual(new Vec2d(5, 0), list[0].Point);
        }

        [Test]
        public void Trail_SelfCrossings_SortedByUThenMostRecentSegmentFirst()
        {
            Trail t = Zigzag();
            var list = new List<SelfCrossing>();
            int n = t.SelfCrossings(new Vec2d(5, -3), new Vec2d(5, 6), 0, t.Length, list);
            Assert.AreEqual(3, n);
            Assert.AreEqual(1.0 / 3.0, list[0].U, Eps);
            Assert.AreEqual(4, list[0].Segment, "same U: the most recent pass first");
            Assert.AreEqual(1.0 / 3.0, list[1].U, Eps);
            Assert.AreEqual(0, list[1].Segment);
            Assert.AreEqual(7.0 / 9.0, list[2].U, Eps);
            Assert.AreEqual(2, list[2].Segment);
            TrailTestUtil.AreClose(new Vec2d(5, 0), list[0].Point, Eps);
            TrailTestUtil.AreClose(new Vec2d(5, 4), list[2].Point, Eps);
        }

        [Test]
        public void Trail_SelfCrossings_MaxSegmentEndArcFilter()
        {
            Trail t = Zigzag();
            var list = new List<SelfCrossing>();
            var a = new Vec2d(5, -3);
            var b = new Vec2d(5, 6);
            Assert.AreEqual(1, t.SelfCrossings(a, b, 0, 10.0, list), "Arc[1] = 10 <= 10 is kept (inclusive)");
            Assert.AreEqual(0, list[0].Segment);
            Assert.AreEqual(0, t.SelfCrossings(a, b, 0, 9.99, list));
            Assert.AreEqual(2, t.SelfCrossings(a, b, 0, 26.0, list));
            Assert.AreEqual(0, list[0].Segment);
            Assert.AreEqual(2, list[1].Segment);
            Assert.AreEqual(3, t.SelfCrossings(a, b, 0, 40.0, list));
        }

        [Test]
        public void Trail_SelfCrossings_UMinIsExclusive()
        {
            Trail t = Zigzag();
            var list = new List<SelfCrossing>();
            var a = new Vec2d(5, -3);
            var b = new Vec2d(5, 6);
            Assert.AreEqual(1, t.SelfCrossings(a, b, 1.0 / 3.0, t.Length, list));
            Assert.AreEqual(2, list[0].Segment);
            Assert.AreEqual(3, t.SelfCrossings(a, b, 0.3, t.Length, list));
        }

        [Test]
        public void Trail_SelfCrossings_ThroughAnOldVertexCountsOnce()
        {
            // The head path passes exactly through (4, 0), the vertex between segments 0 and 1.
            Trail t = TrailTestUtil.Make(0, 0, 4, 0, 8, 0, 8, 3, 6, 3);
            var list = new List<SelfCrossing>();
            Assert.AreEqual(1, t.SelfCrossings(new Vec2d(6, 3), new Vec2d(2, -3), 0, t.Length, list));
            Assert.AreEqual(1, list[0].Segment, "the vertex belongs to the segment that starts there");
            Assert.AreEqual(0.5, list[0].U, Eps);
            TrailTestUtil.AreClose(new Vec2d(4, 0), list[0].Point, Eps);
        }

        [Test]
        public void Trail_SelfCrossings_AgreesWithBruteForce()
        {
            // The spatial hash must never miss a crossing: compare with a plain scan of every stored segment.
            var rng = new Rng(99);
            var list = new List<SelfCrossing>();
            int total = 0;
            for (int run = 0; run < 4; run++)
            {
                Trail t = TrailFirstContactTests.RandomWalk(rng, 400, 0.05, 0.6, 5.0);
                for (int qi = 0; qi < 300; qi++)
                {
                    Vec2d a = new Vec2d(rng.Range(-6, 6), rng.Range(-6, 6));
                    Vec2d b = a + Vec2d.FromAngle(rng.Range(-Math.PI, Math.PI)) * rng.Range(0, 3);
                    double uMin = rng.NextDouble() < 0.5 ? 0.0 : rng.Range(0, 0.8);
                    double maxEnd = rng.Range(0, t.Length);
                    int n = t.SelfCrossings(a, b, uMin, maxEnd, list);
                    var expected = new List<SelfCrossing>();
                    for (int k = 0; k + 1 < t.Count; k++)
                    {
                        if (!(t.Arc[k + 1] <= maxEnd)) continue;
                        if (Geo.ProperIntersect(a, b, t.Points[k], t.Points[k + 1], out double ta, out _) && ta > uMin)
                            expected.Add(new SelfCrossing { U = ta, Segment = k });
                    }
                    expected.Sort((x, y) => x.U != y.U ? x.U.CompareTo(y.U) : y.Segment.CompareTo(x.Segment));
                    Assert.AreEqual(expected.Count, n, "run " + run + " query " + qi);
                    for (int i = 0; i < n; i++)
                    {
                        Assert.AreEqual(expected[i].Segment, list[i].Segment);
                        Assert.AreEqual(expected[i].U, list[i].U);
                    }
                    total += n;
                }
            }
            Assert.That(total, Is.GreaterThan(100), "the sample must exercise crossings");
        }

        [Test]
        public void Trail_SpatialHash_NearlyHorizontalSegmentOnABucketBoundary()
        {
            // 60 u long, rising 2e-7 u across the row boundary y = 2: crossings and contacts are found all along it.
            Trail t = TrailTestUtil.Make(-30, 2 - 1e-7, 30, 2 + 1e-7, 30, 10);
            var list = new List<SelfCrossing>();
            for (double x = -29.5; x < 30; x += 0.37)
            {
                Assert.AreEqual(1, t.SelfCrossings(new Vec2d(x, 2 - 1e-6), new Vec2d(x, 2 + 1e-6), 0, 60, list), "crossing at x = " + x);
                Assert.IsTrue(t.FirstContact(new Vec2d(x, 2 - 1e-6), new Vec2d(x, 2 + 1e-6), TrailTestUtil.R, 0, 0, 0, TrailTestUtil.Grace,
                    out double u, out double s), "contact at x = " + x);
                Assert.AreEqual(0.0, u);
                Assert.AreEqual(x + 30, s, 1e-6);
            }
        }

        [Test]
        public void Trail_SelfCrossings_ClearsOutputAndHandlesShortTrails()
        {
            var list = new List<SelfCrossing> { new SelfCrossing { U = 9, Segment = 9 } };
            Assert.AreEqual(0, new Trail().SelfCrossings(new Vec2d(0, 0), new Vec2d(1, 1), 0, 100, list));
            Assert.AreEqual(0, list.Count, "output cleared");
            Assert.AreEqual(0, TrailTestUtil.Make(0, 0).SelfCrossings(new Vec2d(0, 0), new Vec2d(1, 1), 0, 100, list));
            Assert.Throws<ArgumentNullException>(() => TrailTestUtil.Make(0, 0, 1, 0).SelfCrossings(new Vec2d(0, 0), new Vec2d(1, 1), 0, 100, null));
        }

        [Test]
        public void Trail_LoopPolygon_Shape()
        {
            Trail t = TrailTestUtil.Make(0, 0, 10, 0, 10, 5, 5, 5);
            var list = new List<SelfCrossing>();
            Assert.AreEqual(1, t.SelfCrossings(new Vec2d(5, 5), new Vec2d(5, -1), 0, t.Length, list));
            Vec2d x = list[0].Point;
            List<Vec2d> loop = t.LoopPolygon(list[0].Segment, x, x);
            Assert.AreEqual(5, loop.Count, "X, Points[1..3], X");
            Assert.AreEqual(x, loop[0]);
            Assert.AreEqual(new Vec2d(10, 0), loop[1]);
            Assert.AreEqual(new Vec2d(10, 5), loop[2]);
            Assert.AreEqual(new Vec2d(5, 5), loop[3]);
            Assert.AreEqual(x, loop[4]);
            Assert.AreEqual(25.0, Geo.SignedArea(loop), 1e-9, "the 5 x 5 loop, counter-clockwise");
            Assert.AreEqual(4, t.Count, "the trail is not modified");

            Assert.Throws<ArgumentOutOfRangeException>(() => t.LoopPolygon(3, x, x));
            Assert.Throws<ArgumentOutOfRangeException>(() => t.LoopPolygon(-1, x, x));
        }
    }

    public class LoopEraseTests
    {
        private const double Eps = 1e-12;

        [Test]
        public void LoopErase_SimplePolylineIsUnchanged()
        {
            List<Vec2d> input = TrailTestUtil.Poly(0, 0, 5, 0, 5, 5, 0, 5, 0, 1);
            TrailTestUtil.AreClose(input, LoopErase.Erase(input), 0.0);
            TrailTestUtil.AreClose(TrailTestUtil.Poly(0, 0, 5, 0), LoopErase.Erase(TrailTestUtil.Poly(0, 0, 0, 0, 5, 0, 5, 0)), 0.0);
            Assert.AreEqual(0, LoopErase.Erase(new List<Vec2d>()).Count);
            Assert.AreEqual(0, LoopErase.Erase(null).Count);
            TrailTestUtil.AreClose(TrailTestUtil.Poly(1, 2), LoopErase.Erase(TrailTestUtil.Poly(1, 2)), 0.0);
        }

        [Test]
        public void LoopErase_Figure8()
        {
            // Bow tie: the third segment crosses the first one at (4, 4); the lobe after the crossing is removed.
            List<Vec2d> result = LoopErase.Erase(TrailTestUtil.Poly(0, 0, 8, 8, 8, 0, 0, 8, 0, 12));
            TrailTestUtil.AreClose(TrailTestUtil.Poly(0, 0, 4, 4, 0, 8, 0, 12), result, Eps);
        }

        [Test]
        public void LoopErase_NestedLoops()
        {
            // A small loop closed at (3, 0), then a big loop around it closed at (1, 0).
            List<Vec2d> result = LoopErase.Erase(TrailTestUtil.Poly(0, 0, 5, 0, 5, 2, 3, 2, 3, -1, 10, -1, 10, 5, 1, 5, 1, -3));
            TrailTestUtil.AreClose(TrailTestUtil.Poly(0, 0, 1, 0, 1, -3), result, Eps);

            // An inward spiral whose last segment crosses an inner turn (index 4) and the first segment (index 0).
            result = LoopErase.Erase(TrailTestUtil.Poly(0, 0, 10, 0, 10, 10, 2, 10, 2, 2, 8, 2, 8, 8, 4, 8, 4, -2));
            TrailTestUtil.AreClose(TrailTestUtil.Poly(0, 0, 4, 0, 4, -2), result, Eps);
        }

        [Test]
        public void LoopErase_CrossingThroughAVertex()
        {
            // Through the vertex (4, 0) between collinear segments 0 and 1: counted once, no duplicate point.
            List<Vec2d> result = LoopErase.Erase(TrailTestUtil.Poly(0, 0, 4, 0, 8, 0, 8, 3, 4, 3, 4, -3, 6, -3));
            TrailTestUtil.AreClose(TrailTestUtil.Poly(0, 0, 4, 0, 4, -3, 6, -3), result, 0.0);

            // Through a bent vertex (4, 0): the loop (4,0)-(4,4)-(6,4)-(6,2)-(4,0) is removed.
            result = LoopErase.Erase(TrailTestUtil.Poly(0, 0, 4, 0, 4, 4, 6, 4, 6, 2, 2, -2));
            TrailTestUtil.AreClose(TrailTestUtil.Poly(0, 0, 4, 0, 2, -2), result, 0.0);
        }

        [Test]
        public void LoopErase_CrossingExactlyAtTheNewSegmentEnd()
        {
            // (5,5) -> (5,0) ends exactly on the first segment (ta = 1, it counts): the crossing point is (5, 0) itself,
            // not duplicated, and the next segment continues from it.
            List<Vec2d> result = LoopErase.Erase(TrailTestUtil.Poly(0, 0, 10, 0, 10, 5, 5, 5, 5, 0, 5, -3));
            TrailTestUtil.AreClose(TrailTestUtil.Poly(0, 0, 5, 0, 5, -3), result, 0.0);
        }

        [Test]
        public void LoopErase_OneSegmentCrossingSeveralKeptSegments_SmallestIndexWins()
        {
            // The last segment meets segments 4, 2 and 0 in that order along itself; index 0 wins even though it is met
            // last, so everything after (5, 0) on the first segment is removed.
            List<Vec2d> result = LoopErase.Erase(TrailTestUtil.Poly(0, 0, 10, 0, 10, 2, 0, 2, 0, 4, 10, 4, 10, 6, 5, 6, 5, -2));
            TrailTestUtil.AreClose(TrailTestUtil.Poly(0, 0, 5, 0, 5, -2), result, Eps);
        }

        [Test]
        public void LoopErase_RandomWalksGiveSimplePolylines()
        {
            var rng = new Rng(4242);
            long totalTicks = 0;
            for (int run = 0; run < 8; run++)
            {
                Trail walk = TrailFirstContactTests.RandomWalk(rng, 800, 0.2, 1.5);
                var input = new List<Vec2d>(walk.Points);
                var sw = Stopwatch.StartNew();
                List<Vec2d> result = LoopErase.Erase(input);
                sw.Stop();
                totalTicks += sw.ElapsedTicks;

                Assert.AreEqual(input[0], result[0], "first point kept");
                Assert.AreEqual(input[input.Count - 1], result[result.Count - 1], "last point kept");
                Assert.That(result.Count, Is.LessThan(input.Count / 2), "the walk had loops to erase");
                for (int j = 2; j + 1 < result.Count; j++)
                {
                    for (int i = 0; i + 1 < j; i++)
                    {
                        bool cross = Geo.ProperIntersect(result[j], result[j + 1], result[i], result[i + 1], out _, out _) ||
                                     Geo.ProperIntersect(result[i], result[i + 1], result[j], result[j + 1], out _, out _);
                        Assert.IsFalse(cross, "run " + run + ": segments " + i + " and " + j + " cross");
                    }
                }
            }
            double ms = totalTicks * 1000.0 / Stopwatch.Frequency / 8;
            TestContext.WriteLine("LoopErase: " + ms.ToString("F3") + " ms per 800-point walk");
        }

        [Test]
        public void LoopErase_HashedMatchesPlainScanReference()
        {
            // Same rule implemented with a plain O(n^2) scan of the kept segments: results must be identical.
            var rng = new Rng(31337);
            for (int run = 0; run < 12; run++)
            {
                Trail walk = TrailFirstContactTests.RandomWalk(rng, 500, 0.05, run % 2 == 0 ? 0.5 : 2.5, 4.0 + run);
                var input = new List<Vec2d>(walk.Points);
                List<Vec2d> expected = ReferenceErase(input);
                List<Vec2d> actual = LoopErase.Erase(input);
                Assert.AreEqual(expected.Count, actual.Count, "run " + run);
                for (int i = 0; i < expected.Count; i++) Assert.AreEqual(expected[i], actual[i], "run " + run + " point " + i);
            }
        }

        private static List<Vec2d> ReferenceErase(IReadOnlyList<Vec2d> points)
        {
            var kept = new List<Vec2d> { points[0] };
            for (int i = 1; i < points.Count; i++)
            {
                Vec2d p = points[i], c = kept[kept.Count - 1];
                if (p == c) continue;
                int jMin = -1;
                double ta = 0, tb = 0;
                for (int j = 0; j + 2 < kept.Count; j++)
                {
                    if (Geo.ProperIntersect(c, p, kept[j], kept[j + 1], out ta, out tb))
                    {
                        jMin = j;
                        break;
                    }
                }
                if (jMin >= 0)
                {
                    Vec2d x = tb == 0.0 ? kept[jMin] : ta == 1.0 ? p : Vec2d.Lerp(kept[jMin], kept[jMin + 1], tb);
                    kept.RemoveRange(jMin + 1, kept.Count - jMin - 1);
                    if (x != kept[jMin]) kept.Add(x);
                }
                if (p != kept[kept.Count - 1]) kept.Add(p);
            }
            return kept;
        }
    }

    public class LassoGeometryTests
    {
        private static OwnerGrid NewGrid() => new OwnerGrid(new Arena(Tuning.ArenaHalfSize, Tuning.ArenaCornerRadius, Tuning.ArenaMargin), Tuning.CellSize);

        [Test]
        public void LassoGeometry_Figure8LobesOfOppositeOrientationDoNotCancel()
        {
            OwnerGrid g = NewGrid();
            // Bow tie: two 4 u^2 triangles of opposite orientation (vertices off the cell centers).
            List<Vec2d> bowTie = TrailTestUtil.Poly(0.03, 0.04, 4.03, 4.04, 4.03, 0.04, 0.03, 4.04);
            Assert.AreEqual(0.0, Geo.SignedArea(bowTie), 1e-9, "the shoelace area cancels");
            List<Vec2d> oneLobe = TrailTestUtil.Poly(0.03, 0.04, 2.03, 2.04, 0.03, 4.04);
            Assert.IsTrue(LassoGeometry.IsValidPocket(g, bowTie, Tuning.LassoMinArea));
            Assert.IsTrue(LassoGeometry.IsValidPocket(g, bowTie, 6.5), "both lobes count (about 8 u^2)");
            Assert.IsFalse(LassoGeometry.IsValidPocket(g, bowTie, 9.5));
            Assert.IsFalse(LassoGeometry.IsValidPocket(g, oneLobe, 5.0), "one lobe alone is about 4 u^2");
            Assert.IsTrue(LassoGeometry.IsValidPocket(g, oneLobe, 3.0));
        }

        [Test]
        public void LassoGeometry_MinAreaThreshold()
        {
            OwnerGrid g = NewGrid();
            // Cell centers sit at 0.0625 + 0.125 m. This rectangle holds 8 x 6 = 48 centers: 48 x 0.125^2 = 0.75 u^2.
            List<Vec2d> rect48 = TrailTestUtil.Poly(0.03, 0.04, 1.03, 0.04, 1.03, 0.79, 0.03, 0.79);
            Assert.IsTrue(LassoGeometry.IsValidPocket(g, rect48, 0.75), "exactly LassoMinArea is valid (>=)");
            Assert.IsFalse(LassoGeometry.IsValidPocket(g, rect48, 0.7500001));
            List<Vec2d> tiny = TrailTestUtil.Poly(0.03, 0.04, 0.63, 0.04, 0.63, 0.64, 0.03, 0.64); // 25 centers
            Assert.IsFalse(LassoGeometry.IsValidPocket(g, tiny, Tuning.LassoMinArea));
            Assert.IsFalse(LassoGeometry.IsValidPocket(g, TrailTestUtil.Poly(0, 0, 5, 5), 0.1), "fewer than 3 points");
            Assert.IsFalse(LassoGeometry.IsValidPocket(g, null, 0.1));
        }

        [Test]
        public void LassoGeometry_LoopFromTrailCrossing()
        {
            OwnerGrid g = NewGrid();
            Trail t = TrailTestUtil.Make(0.1, 0.1, 5.1, 0.1, 5.1, 3.1, 2.1, 3.1);
            var list = new List<SelfCrossing>();
            Assert.AreEqual(1, t.SelfCrossings(new Vec2d(2.1, 3.1), new Vec2d(2.1, -0.9), 0, t.Length - Tuning.LassoMinArc, list));
            List<Vec2d> loop = t.LoopPolygon(list[0].Segment, list[0].Point, list[0].Point);
            Assert.IsTrue(LassoGeometry.IsValidPocket(g, loop, Tuning.LassoMinArea), "a 3 x 3 loop");

            // A U-turn 0.05 u wide crossed at its base: a thin sliver with no cell center inside.
            Trail thin = TrailTestUtil.Make(0.1, 0.1, 5.1, 0.1, 5.1, 0.15, 2.1, 0.15);
            Assert.AreEqual(1, thin.SelfCrossings(new Vec2d(2.1, 0.15), new Vec2d(2.1, -1), 0, thin.Length - Tuning.LassoMinArc, list));
            List<Vec2d> sliver = thin.LoopPolygon(list[0].Segment, list[0].Point, list[0].Point);
            Assert.IsFalse(LassoGeometry.IsValidPocket(g, sliver, Tuning.LassoMinArea));
        }

        [Test]
        public void LassoGeometry_VoidCellsDoNotCount()
        {
            OwnerGrid g = NewGrid();
            // 7 x 8 = 56 centers (0.875 u^2) inside the arena, the same square in the void corner beyond the rounded rim.
            List<Vec2d> inside = TrailTestUtil.Poly(0.03, 0.04, 0.93, 0.04, 0.93, 0.94, 0.03, 0.94);
            List<Vec2d> corner = TrailTestUtil.Poly(31.03, 31.04, 31.93, 31.04, 31.93, 31.94, 31.03, 31.94);
            Assert.IsTrue(LassoGeometry.IsValidPocket(g, inside, Tuning.LassoMinArea));
            Assert.IsFalse(LassoGeometry.IsValidPocket(g, corner, Tuning.LassoMinArea));
        }
    }
}
