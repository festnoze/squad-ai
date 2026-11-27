using System;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    // A1 foundation tests (contract 10.1 "Unit"): Vec2d, Geo, Arena (R1, R4), Rng, CellMask, SimConfig.
    // Pure NUnit (Unity ships NUnit 3.5): Assert.That / AreEqual / IsTrue / Throws only.

    public class Vec2dTests
    {
        private const double Eps = 1e-12;

        [Test]
        public void Vec2d_Operators()
        {
            var a = new Vec2d(1, 2);
            var b = new Vec2d(3, -4);
            Assert.AreEqual(new Vec2d(4, -2), a + b);
            Assert.AreEqual(new Vec2d(-2, 6), a - b);
            Assert.AreEqual(new Vec2d(-1, -2), -a);
            Assert.AreEqual(new Vec2d(2.5, 5), a * 2.5);
            Assert.AreEqual(new Vec2d(2.5, 5), 2.5 * a);
            Assert.AreEqual(new Vec2d(0.5, 1), a / 2);
            Assert.IsTrue(a == new Vec2d(1, 2));
            Assert.IsTrue(a != b);
            Assert.AreEqual(new Vec2d(1, 2).GetHashCode(), a.GetHashCode());
            Assert.AreEqual(0.0, Vec2d.Zero.X);
            Assert.AreEqual(0.0, Vec2d.Zero.Y);
        }

        [Test]
        public void Vec2d_LengthDotCrossDistance()
        {
            var v = new Vec2d(3, 4);
            Assert.AreEqual(5.0, v.Length, Eps);
            Assert.AreEqual(25.0, v.LengthSq, Eps);
            Assert.AreEqual(11.0, Vec2d.Dot(new Vec2d(1, 2), new Vec2d(3, 4)), Eps);
            Assert.AreEqual(1.0, Vec2d.Cross(new Vec2d(1, 0), new Vec2d(0, 1)), Eps);
            Assert.AreEqual(-1.0, Vec2d.Cross(new Vec2d(0, 1), new Vec2d(1, 0)), Eps);
            Assert.AreEqual(5.0, Vec2d.Distance(new Vec2d(1, 1), new Vec2d(4, 5)), Eps);
        }

        [Test]
        public void Vec2d_Normalized_ZeroStaysZero()
        {
            Vec2d n = new Vec2d(3, 4).Normalized();
            Assert.AreEqual(0.6, n.X, Eps);
            Assert.AreEqual(0.8, n.Y, Eps);
            Assert.AreEqual(Vec2d.Zero, Vec2d.Zero.Normalized());
            Vec2d tiny = new Vec2d(1e-200, -1e-200).Normalized();
            Assert.AreEqual(1.0, tiny.Length, 1e-12, "X*X underflows: rescaled first");
            Assert.AreEqual(Math.Sqrt(0.5), tiny.X, 1e-12);
            Vec2d huge = new Vec2d(3e200, 4e200).Normalized();
            Assert.AreEqual(0.6, huge.X, 1e-12, "X*X overflows: rescaled first");
            Assert.AreEqual(0.8, huge.Y, 1e-12);
        }

        [Test]
        public void Vec2d_Lerp_ExactAtBothEnds()
        {
            var rng = new Rng(7);
            for (int k = 0; k < 2000; k++)
            {
                var a = new Vec2d(rng.Range(-40, 40), rng.Range(-40, 40));
                var b = new Vec2d(rng.Range(-40, 40), rng.Range(-40, 40));
                Assert.IsTrue(Vec2d.Lerp(a, b, 0.0) == a, "t = 0 must return a exactly");
                Assert.IsTrue(Vec2d.Lerp(a, b, 1.0) == b, "t = 1 must return b exactly");
            }
            Vec2d mid = Vec2d.Lerp(new Vec2d(0, 0), new Vec2d(2, -4), 0.5);
            Assert.AreEqual(1.0, mid.X, Eps);
            Assert.AreEqual(-2.0, mid.Y, Eps);
            Vec2d beyond = Vec2d.Lerp(new Vec2d(0, 0), new Vec2d(1, 0), 2.0);
            Assert.AreEqual(2.0, beyond.X, Eps, "Lerp is unclamped");
        }

        [Test]
        public void Vec2d_AnglesAndPerp()
        {
            Vec2d up = Vec2d.FromAngle(Math.PI / 2);
            Assert.AreEqual(0.0, up.X, Eps);
            Assert.AreEqual(1.0, up.Y, Eps);
            Assert.AreEqual(Math.PI / 2, new Vec2d(0, 3).Angle(), Eps);
            Assert.AreEqual(Math.PI, new Vec2d(-1, 0).Angle(), Eps);
            Assert.AreEqual(-Math.PI / 4, new Vec2d(1, -1).Angle(), Eps);
            Assert.AreEqual(new Vec2d(-2, 1), new Vec2d(1, 2).Perp());
            for (double ang = -3.0; ang <= 3.0; ang += 0.25)
                Assert.AreEqual(ang, Vec2d.FromAngle(ang).Angle(), 1e-12);
        }
    }

    public class GeoTests
    {
        private const double Eps = 1e-12;

        [Test]
        public void Geo_WrapAngle_HalfOpenRange()
        {
            Assert.AreEqual(Math.PI, Geo.WrapAngle(Math.PI), Eps);
            Assert.AreEqual(Math.PI, Geo.WrapAngle(-Math.PI), Eps, "-pi maps to +pi: the range is (-pi, pi]");
            Assert.AreEqual(0.0, Geo.WrapAngle(0.0), Eps);
            Assert.AreEqual(Math.PI / 2, Geo.WrapAngle(-1.5 * Math.PI), 1e-12);
            Assert.AreEqual(0.1, Geo.WrapAngle(2 * Math.PI + 0.1), 1e-12);
            Assert.AreEqual(-0.1, Geo.WrapAngle(-2 * Math.PI - 0.1), 1e-12);
            Assert.AreEqual(1.0, Geo.WrapAngle(1.0 + 20 * Math.PI), 1e-9);
            var rng = new Rng(3);
            for (int k = 0; k < 1000; k++)
            {
                double a = rng.Range(-100, 100);
                double w = Geo.WrapAngle(a);
                Assert.IsTrue(w > -Math.PI && w <= Math.PI, "out of range: " + w);
                Assert.AreEqual(Math.Sin(a), Math.Sin(w), 1e-9);
                Assert.AreEqual(Math.Cos(a), Math.Cos(w), 1e-9);
            }
        }

        [Test]
        public void Geo_MoveTowardsAngle_ShortestWayAndLimits()
        {
            Assert.AreEqual(2.5, Geo.MoveTowardsAngle(0.0, 2.5, 0.0), "maxDelta <= 0 means instant");
            Assert.AreEqual(2.5, Geo.MoveTowardsAngle(0.0, 2.5, -1.0));
            Assert.AreEqual(0.3, Geo.MoveTowardsAngle(0.0, 0.3, 0.5), "within reach returns the target");
            Assert.AreEqual(0.2, Geo.MoveTowardsAngle(0.0, 1.0, 0.2), Eps);
            Assert.AreEqual(-0.2, Geo.MoveTowardsAngle(0.0, -1.0, 0.2), Eps);
            // Across the +-pi seam the short way goes through pi.
            Assert.AreEqual(3.1, Geo.MoveTowardsAngle(3.0, -3.0, 0.1), Eps);
            Assert.AreEqual(-3.1, Geo.MoveTowardsAngle(-3.0, 3.0, 0.1), Eps);
            Assert.AreEqual(3.15 - 2 * Math.PI, Geo.MoveTowardsAngle(3.1, -3.1, 0.05), 1e-12);
            // Exact half turn: counter-clockwise.
            Assert.AreEqual(0.1, Geo.MoveTowardsAngle(0.0, Math.PI, 0.1), Eps);
        }

        [Test]
        public void Geo_ClosestParamAndDistance()
        {
            var s0 = new Vec2d(0, 0);
            var s1 = new Vec2d(4, 0);
            Assert.AreEqual(0.25, Geo.ClosestParamOnSegment(new Vec2d(1, 3), s0, s1), Eps);
            Assert.AreEqual(0.0, Geo.ClosestParamOnSegment(new Vec2d(-2, 1), s0, s1));
            Assert.AreEqual(1.0, Geo.ClosestParamOnSegment(new Vec2d(9, -1), s0, s1));
            Assert.AreEqual(0.0, Geo.ClosestParamOnSegment(new Vec2d(9, -1), s0, s0), "degenerate segment");
            Assert.AreEqual(3.0, Geo.DistancePointSegment(new Vec2d(1, 3), s0, s1), Eps);
            Assert.AreEqual(5.0, Geo.DistancePointSegment(new Vec2d(7, 4), s0, s1), Eps);
            Assert.AreEqual(5.0, Geo.DistancePointSegment(new Vec2d(3, 4), s0, s0), Eps);
        }

        [Test]
        public void Geo_Sweep_PerpendicularApproachHitsTheSide()
        {
            bool hit = Geo.SweepCircleSegment(new Vec2d(0.5, 2), new Vec2d(0.5, 0), 0.5, new Vec2d(-1, 0), new Vec2d(1, 0), out double u, out double t);
            Assert.IsTrue(hit);
            Assert.AreEqual(0.75, u, Eps);
            Assert.AreEqual(0.75, t, Eps);
            // From below as well.
            hit = Geo.SweepCircleSegment(new Vec2d(0, -3), new Vec2d(0, 1), 1.0, new Vec2d(-1, 0), new Vec2d(1, 0), out u, out t);
            Assert.IsTrue(hit);
            Assert.AreEqual(0.5, u, Eps);
            Assert.AreEqual(0.5, t, Eps);
        }

        [Test]
        public void Geo_Sweep_AlreadyInContactReturnsZero()
        {
            bool hit = Geo.SweepCircleSegment(new Vec2d(1.5, 0.3), new Vec2d(9, 9), 0.5, new Vec2d(0, 0), new Vec2d(2, 0), out double u, out double t);
            Assert.IsTrue(hit);
            Assert.AreEqual(0.0, u);
            Assert.AreEqual(0.75, t, Eps);
        }

        [Test]
        public void Geo_Sweep_EndCapContact()
        {
            // Passes beside the end s1 = (1, 0): |(2, y) - (1, 0)| = 1.2 first at y = sqrt(0.44).
            bool hit = Geo.SweepCircleSegment(new Vec2d(2, 1), new Vec2d(2, -1), 1.2, new Vec2d(-1, 0), new Vec2d(1, 0), out double u, out double t);
            Assert.IsTrue(hit);
            Assert.AreEqual((1.0 - Math.Sqrt(0.44)) / 2.0, u, 1e-12);
            Assert.AreEqual(1.0, t);
            // Same path with a smaller radius misses (closest distance is 1).
            Assert.IsFalse(Geo.SweepCircleSegment(new Vec2d(2, 1), new Vec2d(2, -1), 0.99, new Vec2d(-1, 0), new Vec2d(1, 0), out u, out t));
        }

        [Test]
        public void Geo_Sweep_ZeroLengthMotion()
        {
            var p = new Vec2d(0.3, 0.8);
            Assert.IsFalse(Geo.SweepCircleSegment(p, p, 0.5, new Vec2d(-1, 0), new Vec2d(1, 0), out double u, out double t), "static and out of reach");
            Assert.IsTrue(Geo.SweepCircleSegment(p, p, 0.9, new Vec2d(-1, 0), new Vec2d(1, 0), out u, out t), "static and in reach");
            Assert.AreEqual(0.0, u);
            Assert.AreEqual(0.65, t, Eps);
            // A sub-Tiny motion that still crosses the contact distance is found (no near-zero division guard).
            Assert.IsTrue(Geo.SweepCircleSegment(new Vec2d(0, 0.5 + 1e-13), new Vec2d(0, 0.5 - 1e-13), 0.5, new Vec2d(-1, 0), new Vec2d(1, 0), out u, out t));
            Assert.AreEqual(0.5, u, 1e-2);
        }

        [Test]
        public void Geo_Sweep_ParallelMotion()
        {
            var s0 = new Vec2d(0, 0);
            var s1 = new Vec2d(2, 0);
            // Collinear approach: enters the disk of s0 at x = -0.5.
            Assert.IsTrue(Geo.SweepCircleSegment(new Vec2d(-5, 0), new Vec2d(5, 0), 0.5, s0, s1, out double u, out double t));
            Assert.AreEqual(0.45, u, Eps);
            Assert.AreEqual(0.0, t);
            // Offset parallel approach inside the band: disk of s0 at x = -0.4.
            Assert.IsTrue(Geo.SweepCircleSegment(new Vec2d(-5, 0.3), new Vec2d(5, 0.3), 0.5, s0, s1, out u, out t));
            Assert.AreEqual(0.46, u, Eps);
            Assert.AreEqual(0.0, t);
            // Offset beyond the radius: never in contact.
            Assert.IsFalse(Geo.SweepCircleSegment(new Vec2d(-5, 0.6), new Vec2d(5, 0.6), 0.5, s0, s1, out u, out t));
            // Moving away along the line.
            Assert.IsFalse(Geo.SweepCircleSegment(new Vec2d(-1, 0), new Vec2d(-5, 0), 0.5, s0, s1, out u, out t));
            // Reverse direction reaches the s1 disk.
            Assert.IsTrue(Geo.SweepCircleSegment(new Vec2d(7, -0.4), new Vec2d(-3, -0.4), 0.5, s0, s1, out u, out t));
            Assert.AreEqual((7.0 - 2.3) / 10.0, u, 1e-12);
            Assert.AreEqual(1.0, t);
        }

        [Test]
        public void Geo_Sweep_ContactAtExactlyUOneIncluded()
        {
            Assert.IsTrue(Geo.SweepCircleSegment(new Vec2d(0, 2), new Vec2d(0, 0.5), 0.5, new Vec2d(-1, 0), new Vec2d(1, 0), out double u, out double t));
            Assert.AreEqual(1.0, u, Eps);
            Assert.IsFalse(Geo.SweepCircleSegment(new Vec2d(0, 2), new Vec2d(0, 0.5000001), 0.5, new Vec2d(-1, 0), new Vec2d(1, 0), out u, out t));
        }

        [Test]
        public void Geo_Sweep_DegenerateSegmentIsAPoint()
        {
            var c = new Vec2d(1, 1);
            Assert.IsTrue(Geo.SweepCircleSegment(new Vec2d(-3, 1), new Vec2d(3, 1), 1.0, c, c, out double u, out double t));
            Assert.AreEqual(0.5, u, 1e-12, "contact at x = 0");
            Assert.AreEqual(0.0, t);
        }

        [Test]
        public void Geo_Sweep_MatchesBruteForceOnRandomCases()
        {
            var rng = new Rng(2026);
            int hits = 0, parallelCases = 0;
            for (int k = 0; k < 3000; k++)
            {
                var s0 = new Vec2d(rng.Range(-3, 3), rng.Range(-3, 3));
                var s1 = k % 7 == 0 ? s0 : new Vec2d(rng.Range(-3, 3), rng.Range(-3, 3));
                var a = new Vec2d(rng.Range(-5, 5), rng.Range(-5, 5));
                Vec2d b;
                if (k % 5 == 0 && s1 != s0)
                {
                    // Motion parallel to the segment.
                    b = a + (s1 - s0).Normalized() * rng.Range(-8, 8);
                    parallelCases++;
                }
                else if (k % 11 == 0)
                {
                    b = a; // zero motion
                }
                else
                {
                    b = new Vec2d(rng.Range(-5, 5), rng.Range(-5, 5));
                }
                double r = rng.Range(0.05, 1.5);
                bool hit = Geo.SweepCircleSegment(a, b, r, s0, s1, out double u, out double t);

                // Brute force: earliest sampled u with distance <= r (sampling can only find a later u).
                const int N = 4000;
                double firstSample = double.NaN;
                for (int n = 0; n <= N; n++)
                {
                    double us = n / (double)N;
                    if (Geo.DistancePointSegment(Vec2d.Lerp(a, b, us), s0, s1) <= r) { firstSample = us; break; }
                }
                if (hit)
                {
                    hits++;
                    Assert.IsTrue(u >= 0.0 && u <= 1.0);
                    Vec2d q = Vec2d.Lerp(a, b, u);
                    Assert.AreEqual(r, Math.Max(r, Geo.DistancePointSegment(q, s0, s1)), 1e-9, "not in contact at u, case " + k);
                    Assert.AreEqual(Geo.ClosestParamOnSegment(q, s0, s1), t, 1e-9);
                    if (u > 0.0)
                    {
                        // Just before u it is not yet in contact (within the solver accuracy).
                        double before = Math.Max(0.0, u - 1e-7);
                        Assert.IsTrue(Geo.DistancePointSegment(Vec2d.Lerp(a, b, before), s0, s1) >= r - 1e-6, "contact before u, case " + k);
                    }
                    if (!double.IsNaN(firstSample)) Assert.IsTrue(u <= firstSample + 1e-12, "a sample is in contact earlier, case " + k);
                }
                else
                {
                    Assert.IsTrue(double.IsNaN(firstSample), "missed contact at sampled u = " + firstSample + ", case " + k);
                }
            }
            Assert.IsTrue(hits > 300, "the random set must contain contacts: " + hits);
            Assert.IsTrue(parallelCases > 300);
        }

        [Test]
        public void Geo_ProperIntersect_SimpleCrossing()
        {
            Assert.IsTrue(Geo.ProperIntersect(new Vec2d(0, -1), new Vec2d(0, 1), new Vec2d(-1, 0), new Vec2d(1, 0), out double ta, out double tb));
            Assert.AreEqual(0.5, ta, Eps);
            Assert.AreEqual(0.5, tb, Eps);
            // y = x against x + y = 2: crossing at (1, 1).
            Assert.IsTrue(Geo.ProperIntersect(new Vec2d(-2, -2), new Vec2d(2, 2), new Vec2d(-1, 3), new Vec2d(3, -1), out ta, out tb));
            Assert.AreEqual(0.75, ta, Eps);
            Assert.AreEqual(0.5, tb, Eps);
        }

        [Test]
        public void Geo_ProperIntersect_OldVertexCountedOnce()
        {
            // Straight old polyline with a vertex at the origin, crossed exactly there.
            Vec2d[] straight = { new Vec2d(-1, -1), new Vec2d(0, 0), new Vec2d(1, 1) };
            Assert.AreEqual(1, CountCrossings(new Vec2d(-1, 1), new Vec2d(1, -1), straight));
            // Bent old polyline "<" with its apex at the origin, crossed through the apex.
            Vec2d[] bent = { new Vec2d(-1, -1), new Vec2d(0, 0), new Vec2d(-1, 1) };
            Assert.AreEqual(1, CountCrossings(new Vec2d(-0.5, 0), new Vec2d(1, 0), bent));
            // Axis-aligned polyline subdivided at the crossing point: still one crossing.
            Vec2d[] subdivided = { new Vec2d(0.5, -2), new Vec2d(0.5, 0.25), new Vec2d(0.5, 3) };
            Assert.AreEqual(1, CountCrossings(new Vec2d(-1, 0.25), new Vec2d(2, 0.25), subdivided));
            // The vertex belongs to the segment that starts there.
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(-1, 1), new Vec2d(1, -1), straight[0], straight[1], out double ta, out double tb));
            Assert.AreEqual(1.0, tb, Eps);
            Assert.IsTrue(Geo.ProperIntersect(new Vec2d(-1, 1), new Vec2d(1, -1), straight[1], straight[2], out ta, out tb));
            Assert.AreEqual(0.0, tb);
            Assert.AreEqual(0.5, ta, Eps);
        }

        [Test]
        public void Geo_ProperIntersect_CrossingAtMovingEndCounts()
        {
            Assert.IsTrue(Geo.ProperIntersect(new Vec2d(0, -1), new Vec2d(0, 0), new Vec2d(-1, 0), new Vec2d(1, 0), out double ta, out double tb));
            Assert.AreEqual(1.0, ta);
            Assert.AreEqual(0.5, tb, Eps);
        }

        [Test]
        public void Geo_ProperIntersect_EndInTheRoundingBandCountsOnce()
        {
            // A4's exact positions (two consecutive 60 Hz tick segments of a head going South across y = 0.0625): the
            // first segment ends 1.7e-16 short of the line (rounding of accumulated motion), the second starts there.
            // The crossing must be counted by exactly one of them: the first, at its end (ta = 1).
            Vec2d o0 = new Vec2d(1.0, 0.0625), o1 = new Vec2d(1.1, 0.0625);
            Vec2d a = new Vec2d(1.0625, 0.16250000000000017);
            Vec2d m = new Vec2d(1.0625, 0.06250000000000017);
            Vec2d c = new Vec2d(1.0625, -0.03749999999999984);
            bool first = Geo.ProperIntersect(a, m, o0, o1, out double ta, out double tb);
            bool second = Geo.ProperIntersect(m, c, o0, o1, out _, out _);
            Assert.IsTrue(first, "the segment whose end lands in the band reaches the line");
            Assert.AreEqual(1.0, ta);
            Assert.AreEqual(0.625, tb, Eps);
            Assert.IsFalse(second, "the next segment starts in the band: a0 rule");
            // An end that stops short of the line by more than the band still does not count.
            Assert.IsFalse(Geo.ProperIntersect(a, new Vec2d(1.0625, 0.0625 + 1e-9), o0, o1, out _, out _));
        }

        [Test]
        public void Geo_ProperIntersect_A0OnTheLineIsFalse()
        {
            // The head starts its tick on the old segment (it crossed or touched it last tick): not counted again.
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(0, 0), new Vec2d(0, 1), new Vec2d(-1, 0), new Vec2d(1, 0), out double ta, out double tb));
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(0, 0), new Vec2d(0, -1), new Vec2d(-1, 0), new Vec2d(1, 0), out ta, out tb));
            // On the line but outside the segment span: still false.
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(5, 0), new Vec2d(5, 1), new Vec2d(-1, 0), new Vec2d(1, 0), out ta, out tb));
        }

        [Test]
        public void Geo_ProperIntersect_TouchingCollinearParallelAreFalse()
        {
            // Stops short of the line.
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(0, -1), new Vec2d(0, -0.001), new Vec2d(-1, 0), new Vec2d(1, 0), out double ta, out double tb));
            // Crosses the line beyond the end of b (tb > 1) and exactly at b's end (tb = 1).
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(2, -1), new Vec2d(2, 1), new Vec2d(-1, 0), new Vec2d(1, 0), out ta, out tb));
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(1, -1), new Vec2d(1, 1), new Vec2d(-1, 0), new Vec2d(1, 0), out ta, out tb));
            Assert.AreEqual(1.0, tb, Eps);
            // Exactly at b's start (tb = 0) counts.
            Assert.IsTrue(Geo.ProperIntersect(new Vec2d(-1, -1), new Vec2d(-1, 1), new Vec2d(-1, 0), new Vec2d(1, 0), out ta, out tb));
            Assert.AreEqual(0.0, tb);
            // Collinear overlap and parallel.
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(-2, 0), new Vec2d(0.5, 0), new Vec2d(-1, 0), new Vec2d(1, 0), out ta, out tb));
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(-2, 1), new Vec2d(2, 1), new Vec2d(-1, 0), new Vec2d(1, 0), out ta, out tb));
            // Degenerate segments.
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(0, 0.5), new Vec2d(0, 0.5), new Vec2d(-1, 0), new Vec2d(1, 0), out ta, out tb));
            Assert.IsFalse(Geo.ProperIntersect(new Vec2d(0, -1), new Vec2d(0, 1), new Vec2d(0, 0), new Vec2d(0, 0), out ta, out tb));
        }

        [Test]
        public void Geo_SignedAreaAndWinding()
        {
            var ccw = new List<Vec2d> { new Vec2d(0, 0), new Vec2d(2, 0), new Vec2d(2, 3), new Vec2d(0, 3) };
            var cw = new List<Vec2d>(ccw);
            cw.Reverse();
            Assert.AreEqual(6.0, Geo.SignedArea(ccw), Eps);
            Assert.AreEqual(-6.0, Geo.SignedArea(cw), Eps);
            Assert.AreEqual(0.0, Geo.SignedArea(new List<Vec2d> { new Vec2d(0, 0), new Vec2d(1, 1) }));
            Assert.AreEqual(1, Geo.WindingNumber(new Vec2d(1, 1), ccw));
            Assert.AreEqual(-1, Geo.WindingNumber(new Vec2d(1, 1), cw));
            Assert.AreEqual(0, Geo.WindingNumber(new Vec2d(3, 1), ccw));
            Assert.AreEqual(0, Geo.WindingNumber(new Vec2d(1, -1), ccw));
            // Figure 8: lobes of opposite orientation.
            var eight = new List<Vec2d> { new Vec2d(0, 0), new Vec2d(2, 2), new Vec2d(2, 0), new Vec2d(0, 2) };
            int left = Geo.WindingNumber(new Vec2d(0.5, 1), eight);
            int right = Geo.WindingNumber(new Vec2d(1.5, 1), eight);
            Assert.AreEqual(1, Math.Abs(left));
            Assert.AreEqual(-left, right);
            Assert.AreEqual(0.0, Geo.SignedArea(eight), Eps, "signed area of a symmetric figure 8 cancels");
            // A square wound twice.
            var twice = new List<Vec2d>(ccw);
            twice.AddRange(ccw);
            Assert.AreEqual(2, Geo.WindingNumber(new Vec2d(1, 1), twice));
            // Ray through a vertex is counted once (half-open rule).
            var diamond = new List<Vec2d> { new Vec2d(0, -1), new Vec2d(1, 0), new Vec2d(0, 1), new Vec2d(-1, 0) };
            Assert.AreEqual(1, Geo.WindingNumber(new Vec2d(0, 0), diamond));
            Assert.AreEqual(0, Geo.WindingNumber(new Vec2d(-2, 0), diamond));
        }

        private static int CountCrossings(Vec2d a0, Vec2d a1, Vec2d[] poly)
        {
            int n = 0;
            for (int k = 0; k + 1 < poly.Length; k++)
                if (Geo.ProperIntersect(a0, a1, poly[k], poly[k + 1], out double ta, out double tb)) n++;
            return n;
        }
    }

    public class ArenaTests
    {
        private const double Eps = 1e-12;
        private Arena arena;

        [SetUp]
        public void SetUp()
        {
            arena = new Arena(Tuning.ArenaHalfSize, Tuning.ArenaCornerRadius, Tuning.ArenaMargin);
        }

        [Test]
        public void R1_Arena_SignedDistanceValues()
        {
            Assert.AreEqual(-32.0, arena.SignedDistance(new Vec2d(0, 0)), Eps);
            Assert.AreEqual(0.0, arena.SignedDistance(new Vec2d(32, 0)), Eps);
            Assert.AreEqual(1.0, arena.SignedDistance(new Vec2d(-33, 5)), Eps);
            Assert.AreEqual(-1.0, arena.SignedDistance(new Vec2d(3, 31)), Eps);
            Assert.AreEqual(-10.0, arena.SignedDistance(new Vec2d(22, -22)), Eps, "corner arc center");
            double c = 10.0 / Math.Sqrt(2.0);
            Assert.AreEqual(0.0, arena.SignedDistance(new Vec2d(22 + c, 22 + c)), 1e-12, "on the corner arc");
            Assert.AreEqual(Math.Sqrt(200.0) - 10.0, arena.SignedDistance(new Vec2d(-32, 32)), 1e-12, "square corner is outside");
            Assert.AreEqual(5.0, arena.SignedDistance(new Vec2d(22 + 9, 22 + 12)), 1e-12, "corner region outside: 15 - 10");
        }

        [Test]
        public void R1_Arena_SignedDistanceIsAnExactSdf()
        {
            // |grad| = 1 numerically, and the gradient agrees with OutwardNormal, away from the medial axis.
            var rng = new Rng(11);
            int checkedCount = 0;
            for (int k = 0; k < 2000; k++)
            {
                var p = new Vec2d(rng.Range(-40, 40), rng.Range(-40, 40));
                if (Math.Abs(Math.Abs(p.X) - Math.Abs(p.Y)) < 0.01 || Math.Abs(p.X) < 0.01 || Math.Abs(p.Y) < 0.01) continue;
                const double h = 1e-6;
                double gx = (arena.SignedDistance(new Vec2d(p.X + h, p.Y)) - arena.SignedDistance(new Vec2d(p.X - h, p.Y))) / (2 * h);
                double gy = (arena.SignedDistance(new Vec2d(p.X, p.Y + h)) - arena.SignedDistance(new Vec2d(p.X, p.Y - h))) / (2 * h);
                Vec2d n = arena.OutwardNormal(p);
                Assert.AreEqual(1.0, n.Length, 1e-12);
                Assert.AreEqual(gx, n.X, 1e-5, "at " + p);
                Assert.AreEqual(gy, n.Y, 1e-5, "at " + p);
                checkedCount++;
            }
            Assert.IsTrue(checkedCount > 1500);
        }

        [Test]
        public void R1_Arena_ContainsIncludesTheRim()
        {
            Assert.IsTrue(arena.Contains(new Vec2d(0, 0)));
            Assert.IsTrue(arena.Contains(new Vec2d(32, 0)), "rim included");
            Assert.IsFalse(arena.Contains(new Vec2d(32.0001, 0)));
            Assert.IsTrue(arena.Contains(new Vec2d(29, 29)), "inside the corner arc");
            Assert.IsFalse(arena.Contains(new Vec2d(31, 31)), "cut off by the corner arc");
        }

        [Test]
        public void R1_Arena_OutwardNormal()
        {
            Assert.AreEqual(new Vec2d(1, 0), arena.OutwardNormal(new Vec2d(31, 3)));
            Assert.AreEqual(new Vec2d(0, -1), arena.OutwardNormal(new Vec2d(-4, -31)));
            Assert.AreEqual(new Vec2d(-1, 0), arena.OutwardNormal(new Vec2d(-40, 10)));
            Vec2d corner = arena.OutwardNormal(new Vec2d(30, 30));
            Assert.AreEqual(Math.Sqrt(0.5), corner.X, Eps);
            Assert.AreEqual(Math.Sqrt(0.5), corner.Y, Eps);
            Vec2d far = arena.OutwardNormal(new Vec2d(-25, 26));
            Assert.AreEqual(new Vec2d(-3, 4).Normalized().X, far.X, Eps);
            Assert.AreEqual(new Vec2d(-3, 4).Normalized().Y, far.Y, Eps);
            Assert.AreEqual(1.0, arena.OutwardNormal(new Vec2d(0, 0)).Length, Eps, "always a unit vector");
        }

        [Test]
        public void R1_Arena_ClampInside()
        {
            double m = Tuning.ArenaMargin;
            var inside = new Vec2d(10.25, -7.5);
            Assert.IsTrue(arena.ClampInside(inside) == inside, "an inside point is returned unchanged");

            Vec2d side = arena.ClampInside(new Vec2d(40, 3));
            Assert.AreEqual(32 - m, side.X, 1e-9);
            Assert.AreEqual(3.0, side.Y, Eps);

            Vec2d corner = arena.ClampInside(new Vec2d(40, 40));
            double k = (10 - m) / Math.Sqrt(2.0);
            Assert.AreEqual(22 + k, corner.X, 1e-9);
            Assert.AreEqual(22 + k, corner.Y, 1e-9);

            var rng = new Rng(5);
            for (int n = 0; n < 3000; n++)
            {
                var p = new Vec2d(rng.Range(-45, 45), rng.Range(-45, 45));
                Vec2d c = arena.ClampInside(p);
                Assert.IsTrue(arena.SignedDistance(c) <= -m, "clamped point not inside: " + c);
                if (arena.SignedDistance(p) > -m)
                {
                    // Nearest point of the convex inset shape: on its boundary, p - c along the outward normal at c.
                    Assert.AreEqual(-m, arena.SignedDistance(c), 1e-9);
                    Vec2d dir = (p - c).Normalized();
                    Vec2d normal = arena.OutwardNormal(c);
                    Assert.AreEqual(1.0, Vec2d.Dot(dir, normal), 1e-6, "not the nearest point for " + p);
                    Assert.AreEqual(arena.SignedDistance(p) + m, Vec2d.Distance(p, c), 1e-9);
                }
                else
                {
                    Assert.IsTrue(c == p);
                }
            }
        }

        [Test]
        public void R1_Arena_ClampInside_MarginLargerThanCornerRadius()
        {
            var sharp = new Arena(10, 1, 2);   // inset shape is the sharp square [-8, 8]^2
            Vec2d c = sharp.ClampInside(new Vec2d(20, 20));
            Assert.AreEqual(8.0, c.X, 1e-9);
            Assert.AreEqual(8.0, c.Y, 1e-9);
            Assert.IsTrue(sharp.SignedDistance(c) <= -2.0);
        }

        [Test]
        public void R1_Arena_ShapeAreaAnalyticAndByCells()
        {
            double expected = 64.0 * 64.0 - (4.0 - Math.PI) * 100.0;
            Assert.AreEqual(expected, arena.ShapeArea, 1e-9);
            // Count the 512 x 512 cell centers inside: matches the analytic area within 0.1 %.
            double cs = Tuning.CellSize;
            int size = (int)Math.Round(2 * Tuning.ArenaHalfSize / cs);
            Assert.AreEqual(512, size);
            int inside = 0;
            for (int j = 0; j < size; j++)
                for (int i = 0; i < size; i++)
                    if (arena.Contains(new Vec2d(-Tuning.ArenaHalfSize + (i + 0.5) * cs, -Tuning.ArenaHalfSize + (j + 0.5) * cs))) inside++;
            Assert.AreEqual(expected, inside * cs * cs, expected * 0.001);
        }

        [Test]
        public void R1_Arena_RejectsInvalidParameters()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => new Arena(0, 0, 0));
            Assert.Throws<ArgumentOutOfRangeException>(() => new Arena(10, 11, 0));
            Assert.Throws<ArgumentOutOfRangeException>(() => new Arena(10, 2, -1));
            Assert.Throws<ArgumentOutOfRangeException>(() => new Arena(10, 2, 10));
        }

        [Test]
        public void R4_Arena_Step_FreeMotionIsExact()
        {
            var p0 = new Vec2d(1.5, -2.25);
            var d = new Vec2d(0.06, 0.08);
            Assert.IsTrue(arena.Step(p0, d, Deg(10)) == p0 + d);
        }

        [Test]
        public void R4_Arena_Step_SlidesAlongAStraightWall()
        {
            // Inset wall at x = 31.55. A 45 degree push slides up at the full step length.
            var p0 = new Vec2d(31.5, 0);
            Vec2d d = Vec2d.FromAngle(Deg(45)) * 0.1;
            Vec2d p1 = arena.Step(p0, d, Deg(10));
            Assert.AreEqual(31.5, p1.X, 1e-12);
            Assert.AreEqual(0.1, p1.Y, 1e-12);
            Assert.AreEqual(0.1, Vec2d.Distance(p0, p1), 1e-12, "rescaled to the full step length");
            // Pushing down-right slides down.
            p1 = arena.Step(p0, Vec2d.FromAngle(Deg(-30)) * 0.1, Deg(10));
            Assert.AreEqual(-0.1, p1.Y, 1e-12);
            Assert.IsTrue(arena.SignedDistance(p1) <= -Tuning.ArenaMargin);
        }

        [Test]
        public void R4_Arena_Step_HoldsWithinTheHoldAngle()
        {
            // Inset wall at x = 31.55 and p0 0.05 u short of it. Contract 23.2 D3: a held step first advances along d up
            // to the inset line (not along the normal), then the head stays exactly there.
            double inset = 32 - Tuning.ArenaMargin;
            var p0 = new Vec2d(31.5, 0);
            foreach (double deg in new[] { 5.0, -9.9, 0.0 })
            {
                Vec2d d = Vec2d.FromAngle(Deg(deg)) * 0.1;
                Vec2d held = arena.Step(p0, d, Deg(10));
                Assert.AreEqual(inset, held.X, 1e-9, deg + " degrees from the normal: held on the inset line");
                Assert.AreEqual(0.05 * Math.Tan(Deg(deg)), held.Y, 1e-9, deg + " degrees: advanced along d");
                Assert.IsTrue(arena.SignedDistance(held) <= -Tuning.ArenaMargin, deg + " degrees: inside the inset shape");
                Assert.IsTrue(arena.Step(held, d, Deg(10)) == held, deg + " degrees: then held exactly in place");
            }
            Vec2d slid = arena.Step(p0, Vec2d.FromAngle(Deg(10.5)) * 0.1, Deg(10));
            Assert.IsTrue(slid.Y > 0.099, "10.5 degrees: slides");
            // Hold angle 0 never holds; a push exactly along the normal has no tangent component: held on the line too.
            Assert.IsTrue(arena.Step(p0, Vec2d.FromAngle(Deg(1)) * 0.1, 0.0).Y > 0.099);
            Vec2d straight = arena.Step(p0, new Vec2d(0.1, 0), 0.0);
            Assert.AreEqual(inset, straight.X, 1e-9);
            Assert.AreEqual(0.0, straight.Y);
            Assert.IsTrue(arena.Step(straight, new Vec2d(0.1, 0), 0.0) == straight);
            // Top wall: the same rules with the normal (0, 1).
            var top = new Vec2d(-3, 31.5);
            Vec2d topHeld = arena.Step(top, Vec2d.FromAngle(Deg(95)) * 0.1, Deg(10));
            Assert.AreEqual(inset, topHeld.Y, 1e-9);
            Assert.AreEqual(-3 + 0.05 / Math.Tan(Deg(95)), topHeld.X, 1e-9);
            Assert.AreEqual(-3.1, arena.Step(top, Vec2d.FromAngle(Deg(150)) * 0.1, Deg(10)).X, 1e-12);
        }

        [Test]
        public void R4_Arena_Step_HeldStopPointDoesNotDependOnTheStepLength()
        {
            // Contract 23.2 D3: a head pushed into the border within the hold angle stops where its straight path meets the
            // inset line, whatever the step length: the same point within 1e-9 u at 30, 60, 144 and 240 Hz, on straight
            // walls and on a corner arc; once there it never moves again. (Before D3 it stopped up to one step short.)
            double hold = Deg(Tuning.BorderHoldAngleDeg);
            var cases = new[]
            {
                (start: new Vec2d(24.0625, 0.0625), heading: Deg(4)),    // East wall, 4 degrees off the normal
                (start: new Vec2d(-3.3, -24.0), heading: Deg(-97)),       // South wall, 7 degrees off the normal
                (start: new Vec2d(20.0, 19.9), heading: Deg(45)),         // North-East corner arc
            };
            foreach (var c in cases)
            {
                Vec2d reference = Vec2d.Zero;
                bool first = true;
                foreach (int rate in new[] { 30, 60, 144, 240 })
                {
                    string at = c.start + " at " + rate + " Hz: ";
                    Vec2d d = Vec2d.FromAngle(c.heading) * (Tuning.PawnSpeed / rate);
                    Vec2d p = c.start;
                    int still = 0;
                    for (int k = 0; k < 6 * rate && still < 10; k++)
                    {
                        Vec2d next = arena.Step(p, d, hold);
                        Assert.IsTrue(arena.SignedDistance(next) <= -Tuning.ArenaMargin, at + "inside the inset shape");
                        Assert.IsTrue(Vec2d.Distance(p, next) <= d.Length + 1e-12, at + "never more than one step");
                        still = next == p ? still + 1 : 0;
                        p = next;
                    }
                    Assert.AreEqual(10, still, at + "held");
                    Assert.AreEqual(-Tuning.ArenaMargin, arena.SignedDistance(p), 1e-9, at + "on the inset line");
                    Assert.AreEqual(0.0, Vec2d.Cross(Vec2d.FromAngle(c.heading), p - c.start), 1e-9, at + "on the straight path");
                    if (first)
                    {
                        reference = p;
                        first = false;
                    }
                    else
                    {
                        Assert.That(Vec2d.Distance(reference, p), Is.LessThanOrEqualTo(1e-9), at + "same stop point as at 30 Hz");
                    }
                }
            }
        }

        [Test]
        public void R4_Arena_Step_FollowsTheCornerArcThenHolds()
        {
            // Constant push at 30 degrees from the center: right wall, slide up into the corner arc, follow it, then
            // stop once the normal is within the hold angle of the push. Never leaves the inset shape.
            double hold = Deg(10);
            Vec2d d = Vec2d.FromAngle(Deg(30)) * 0.1;
            var p = new Vec2d(0, 0);
            Vec2d prev = p;
            int stillTicks = 0;
            for (int k = 0; k < 3000; k++)
            {
                prev = p;
                p = arena.Step(p, d, hold);
                Assert.IsTrue(arena.SignedDistance(p) <= -Tuning.ArenaMargin, "left the inset shape at tick " + k);
                Assert.IsTrue(Vec2d.Distance(prev, p) <= 0.1 + 1e-9, "moved more than one step at tick " + k);
                stillTicks = p == prev ? stillTicks + 1 : 0;
            }
            Assert.IsTrue(stillTicks > 100, "the head ends held against the corner");
            Assert.IsTrue(p.X > 22 && p.Y > 22, "held on the corner arc: " + p);
            // The hold test uses the normal at p + d, and an arc slide advances about 0.6 degrees per tick, so the
            // head stops with its normal just around 30 - 10 = 20 degrees.
            double normalAngle = arena.OutwardNormal(p).Angle();
            Assert.IsTrue(normalAngle > Deg(19) && normalAngle < Deg(21), "stops where the normal enters the hold cone: " + normalAngle * 180 / Math.PI);
        }

        [TestCase(30)]
        [TestCase(60)]
        [TestCase(144)]
        [TestCase(240)]
        public void R4_Arena_Step_RandomWalkNeverLeavesTheInsetShape(int tickRate)
        {
            var rng = new Rng((ulong)tickRate);
            double step = Tuning.PawnSpeed / tickRate;
            var p = new Vec2d(0, 0);
            double heading = 0;
            for (int k = 0; k < 20000; k++)
            {
                if (k % 50 == 0) heading = rng.Range(-Math.PI, Math.PI);
                Vec2d next = arena.Step(p, Vec2d.FromAngle(heading) * step, Deg(Tuning.BorderHoldAngleDeg));
                Assert.IsTrue(arena.SignedDistance(next) <= -Tuning.ArenaMargin);
                Assert.IsTrue(Vec2d.Distance(p, next) <= step + 1e-9);
                p = next;
            }
        }

        [Test]
        public void R4_Arena_Step_FromOutsideMovingInwardIsClamped()
        {
            Vec2d p1 = arena.Step(new Vec2d(40, 0), new Vec2d(-0.1, 0), Deg(10));
            Assert.IsTrue(arena.SignedDistance(p1) <= -Tuning.ArenaMargin);
            Assert.AreEqual(32 - Tuning.ArenaMargin, p1.X, 1e-9);
        }

        private static double Deg(double degrees) => degrees * Math.PI / 180.0;
    }

    public class RngTests
    {
        [Test]
        public void Rng_GoldenSequence()
        {
            // Reference values computed independently with arbitrary-precision integers (xorshift64*, shifts 12/25/27).
            var rng = new Rng(1);
            Assert.AreEqual(5180492295206395165UL, rng.NextULong());
            Assert.AreEqual(12380297144915551517UL, rng.NextULong());
            Assert.AreEqual(13389498078930870103UL, rng.NextULong());
            rng = new Rng(42);
            Assert.AreEqual(6255019084209693600UL, rng.NextULong());
            Assert.AreEqual(14430073426741505498UL, rng.NextULong());
            Assert.AreEqual(14575455857230217846UL, rng.NextULong());
        }

        [Test]
        public void Rng_SameSeedSameSequence()
        {
            var a = new Rng(123456789);
            var b = new Rng(123456789);
            for (int k = 0; k < 1000; k++)
            {
                Assert.AreEqual(a.NextULong(), b.NextULong());
                Assert.AreEqual(a.NextDouble(), b.NextDouble());
                Assert.AreEqual(a.NextInt(1000), b.NextInt(1000));
                Assert.AreEqual(a.Range(-3, 9), b.Range(-3, 9));
            }
            var c = new Rng(123456790);
            var d = new Rng(123456789);
            int same = 0;
            for (int k = 0; k < 100; k++) if (c.NextULong() == d.NextULong()) same++;
            Assert.AreEqual(0, same, "neighbouring seeds give different sequences");
        }

        [Test]
        public void Rng_SeedZeroIsRemapped()
        {
            var zero = new Rng(0);
            var remapped = new Rng(Rng.ZeroSeedReplacement);
            Assert.AreEqual(973819730272012410UL, zero.NextULong());
            remapped.NextULong();
            for (int k = 0; k < 100; k++)
            {
                ulong v = zero.NextULong();
                Assert.AreNotEqual(0UL, v);
                Assert.AreEqual(remapped.NextULong(), v);
            }
        }

        [Test]
        public void Rng_RangesAndDistribution()
        {
            var rng = new Rng(99);
            double sum = 0;
            const int N = 100000;
            int[] buckets = new int[7];
            for (int k = 0; k < N; k++)
            {
                double x = rng.NextDouble();
                Assert.IsTrue(x >= 0.0 && x < 1.0);
                sum += x;
                int i = rng.NextInt(7);
                Assert.IsTrue(i >= 0 && i < 7);
                buckets[i]++;
                double r = rng.Range(-2.5, 4.0);
                Assert.IsTrue(r >= -2.5 && r < 4.0);
            }
            Assert.AreEqual(0.5, sum / N, 0.01);
            foreach (int count in buckets) Assert.AreEqual(N / 7.0, count, N / 7.0 * 0.05);
            Assert.AreEqual(0, rng.NextInt(1));
            Assert.Throws<ArgumentOutOfRangeException>(() => rng.NextInt(0));
            Assert.Throws<ArgumentOutOfRangeException>(() => rng.NextInt(-3));
        }
    }

    public class CellMaskTests
    {
        [Test]
        public void CellMask_SetGetUnsetCountVersion()
        {
            var m = new CellMask(10);
            Assert.AreEqual(10, m.Size);
            Assert.AreEqual(0, m.Count);
            Assert.AreEqual(0, m.Version);
            m.Set(0);
            m.Set(63);
            m.Set(64);
            m.Set(99);
            Assert.AreEqual(4, m.Count);
            Assert.AreEqual(4, m.Version);
            Assert.IsTrue(m.Get(63) && m.Get(64) && m.Get(99) && m.Get(0));
            Assert.IsFalse(m.Get(1) || m.Get(62) || m.Get(65) || m.Get(98));
            m.Set(63);
            Assert.AreEqual(4, m.Count, "setting a set cell changes nothing");
            Assert.AreEqual(4, m.Version);
            m.Unset(63);
            Assert.AreEqual(3, m.Count);
            Assert.AreEqual(5, m.Version);
            Assert.IsFalse(m.Get(63));
            m.Unset(63);
            Assert.AreEqual(5, m.Version, "unsetting a clear cell changes nothing");
            m.Clear();
            Assert.AreEqual(0, m.Count);
            Assert.AreEqual(6, m.Version);
            Assert.IsFalse(m.Get(0));
            m.Clear();
            Assert.AreEqual(6, m.Version, "clearing an empty mask changes nothing");
        }

        [Test]
        public void CellMask_IndexBoundsAreChecked()
        {
            var m = new CellMask(10);
            Assert.Throws<ArgumentOutOfRangeException>(() => m.Set(100));
            Assert.Throws<ArgumentOutOfRangeException>(() => m.Set(-1));
            Assert.Throws<ArgumentOutOfRangeException>(() => m.Get(127), "inside the last word but outside Size * Size");
            Assert.Throws<ArgumentOutOfRangeException>(() => new CellMask(0));
        }

        [Test]
        public void CellMask_UnionWith()
        {
            var a = new CellMask(16);
            var b = new CellMask(16);
            a.Set(1); a.Set(70); a.Set(255);
            b.Set(70); b.Set(2); b.Set(200);
            int v = a.Version;
            a.UnionWith(b);
            Assert.AreEqual(5, a.Count);
            Assert.AreEqual(v + 1, a.Version);
            Assert.IsTrue(a.Get(1) && a.Get(2) && a.Get(70) && a.Get(200) && a.Get(255));
            Assert.AreEqual(3, b.Count, "the argument is not modified");
            v = a.Version;
            a.UnionWith(b);
            Assert.AreEqual(v, a.Version, "a union that adds nothing changes nothing");
            a.UnionWith(a);
            Assert.AreEqual(5, a.Count);
            Assert.Throws<ArgumentException>(() => a.UnionWith(new CellMask(15)));
        }

        [Test]
        public void CellMask_CopyIndicesAscendingAndClearsOutput()
        {
            var m = new CellMask(512);
            int[] set = { 262143, 5, 64, 63, 131072, 0, 4095 };
            foreach (int i in set) m.Set(i);
            var output = new List<int> { 42, 43 };
            m.CopyIndices(output);
            Assert.AreEqual(new List<int> { 0, 5, 63, 64, 4095, 131072, 262143 }, output);
            new CellMask(512).CopyIndices(output);
            Assert.AreEqual(0, output.Count);
        }

        [Test]
        public void CellMask_FullGridAndRandomAgainstReference()
        {
            var full = new CellMask(512);
            for (int i = 0; i < 512 * 512; i++) full.Set(i);
            Assert.AreEqual(262144, full.Count);
            var all = new List<int>();
            full.CopyIndices(all);
            Assert.AreEqual(262144, all.Count);
            Assert.AreEqual(262143, all[all.Count - 1]);

            var rng = new Rng(17);
            var m = new CellMask(37);
            var reference = new bool[37 * 37];
            int expected = 0;
            for (int k = 0; k < 5000; k++)
            {
                int i = rng.NextInt(37 * 37);
                if (rng.NextInt(3) == 0) { if (reference[i]) expected--; reference[i] = false; m.Unset(i); }
                else { if (!reference[i]) expected++; reference[i] = true; m.Set(i); }
                Assert.AreEqual(expected, m.Count);
            }
            var indices = new List<int>();
            m.CopyIndices(indices);
            var refIndices = new List<int>();
            for (int i = 0; i < reference.Length; i++) if (reference[i]) refIndices.Add(i);
            Assert.AreEqual(refIndices, indices);
        }
    }

    public class SimConfigTests
    {
        [Test]
        public void SimConfig_DefaultsMirrorEveryTuningConstant()
        {
            var cfg = new SimConfig();
            int matched = 0;
            foreach (FieldInfo constant in typeof(Tuning).GetFields(BindingFlags.Public | BindingFlags.Static))
            {
                if (!constant.IsLiteral) continue;
                FieldInfo field = typeof(SimConfig).GetField(constant.Name, BindingFlags.Public | BindingFlags.Instance);
                Assert.IsNotNull(field, "SimConfig lacks a field for Tuning." + constant.Name);
                Assert.AreEqual(constant.FieldType, field.FieldType, constant.Name);
                Assert.AreEqual(constant.GetRawConstantValue(), field.GetValue(cfg), constant.Name);
                matched++;
            }
            Assert.AreEqual(27, matched, "contract 3.1 lists 27 constants");
            Assert.AreEqual(1UL, cfg.Seed);
        }

        [Test]
        public void SimConfig_DerivedValues()
        {
            var cfg = new SimConfig();
            Assert.AreEqual(1.0 / 60.0, cfg.Dt, 1e-15);
            Assert.AreEqual(10.8, cfg.SparkSpeed, 1e-12);
            Assert.AreEqual(0.63, cfg.ContactRadius, 1e-12);
            Assert.AreEqual(1.05, cfg.PickupRadius, 1e-12);
            Assert.AreEqual(512, cfg.GridSize);
            Assert.AreEqual(3.0 * Math.PI, cfg.TurnRateRad, 1e-12);
            Assert.AreEqual(Math.PI / 18.0, cfg.BorderHoldAngleRad, 1e-12);
            cfg.TickRate = 144;
            cfg.PawnSpeed = 5.0;
            cfg.SparkSpeedFactor = 2.0;
            Assert.AreEqual(1.0 / 144.0, cfg.Dt, 1e-15);
            Assert.AreEqual(10.0, cfg.SparkSpeed, 1e-12);
        }

        [Test]
        public void SimConfig_CloneIsAnIndependentCopy()
        {
            var cfg = new SimConfig { Seed = 77, TickRate = 30, RoundDuration = 12.5, LassoEnabled = false };
            SimConfig copy = cfg.Clone();
            Assert.AreNotSame(cfg, copy);
            foreach (FieldInfo f in typeof(SimConfig).GetFields(BindingFlags.Public | BindingFlags.Instance))
                Assert.AreEqual(f.GetValue(cfg), f.GetValue(copy), f.Name);
            copy.TickRate = 144;
            copy.Seed = 1;
            Assert.AreEqual(30, cfg.TickRate);
            Assert.AreEqual(77UL, cfg.Seed);
        }

        [Test]
        public void SimConfig_HeadGraceExceedsOneTickAtEverySupportedRate()
        {
            // Contract 3.1: the segment a head draws in one tick is never exposed during that tick.
            var cfg = new SimConfig();
            for (int rate = 30; rate <= 240; rate++)
            {
                cfg.TickRate = rate;
                Assert.IsTrue(cfg.HeadGrace > cfg.PawnSpeed * cfg.Dt, "rate " + rate);
            }
            Assert.IsTrue(cfg.SparkSpeed > cfg.PawnSpeed, "section 6 needs a spark faster than a pawn");
        }

        [Test]
        public void R2_Tuning_StartDiscsFitInsideTheArena()
        {
            var arena = new Arena(Tuning.ArenaHalfSize, Tuning.ArenaCornerRadius, Tuning.ArenaMargin);
            double o = Tuning.StartDiscOffset;
            foreach (var c in new[] { new Vec2d(-o, -o), new Vec2d(o, -o), new Vec2d(o, o), new Vec2d(-o, o) })
                Assert.IsTrue(arena.SignedDistance(c) < -Tuning.StartDiscRadius - Tuning.ArenaMargin);
        }
    }
}
