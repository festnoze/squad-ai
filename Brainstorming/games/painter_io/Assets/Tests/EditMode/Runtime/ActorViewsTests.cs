// Owned by B2 (actors). EditMode checks of the actor geometry rules of contract 12.3 that a screenshot cannot measure:
// the thread profile (exposed width tied to TrailHalfWidth, neck only over the first 0.3 u, thinning inside HeadGrace),
// the display curve, the FieldStroke triangle list conventions of 12.2, the cut thread pieces and the retraction front
// on the real demo trail (drawn gap = sim gap, front never over the pearl), droplets, flash blinks and splash drops.
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class ActorViewsTests
    {
        private readonly List<Object> created = new List<Object>();

        [TearDown]
        public void TearDown()
        {
            foreach (Object o in created)
            {
                if (o != null) Object.DestroyImmediate(o);
            }
            created.Clear();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Thread profile (12.3).

        [Test]
        public void B2_ThreadExposedWidthWithinTolerance()
        {
            const double length = 9.0;
            for (double s = ThreadView.NeckLength; s <= length - Tuning.HeadGrace; s += 0.01)
            {
                float r = ThreadView.RadiusAt(s, 0.0, length, true, true, false);
                Assert.That(Mathf.Abs(r - (float)Tuning.TrailHalfWidth), Is.LessThanOrEqualTo(0.03f + 1e-5f), "s = " + s);
                Assert.AreEqual(ThreadView.VisibleRadius, r, 1e-5f, "exposed radius s = " + s);
            }
        }

        [Test]
        public void B2_ThreadNeckOnlyOverFirst03u()
        {
            Assert.AreEqual(ThreadView.VisibleRadius * ThreadView.NeckWiden, ThreadView.RadiusAt(0.0, 0.0, 9.0, true, true, false), 1e-5f);
            Assert.AreEqual(ThreadView.VisibleRadius, ThreadView.RadiusAt(0.3, 0.0, 9.0, true, true, false), 1e-5f);
            float previous = float.MaxValue;
            for (double s = 0.0; s <= 0.3; s += 0.01)
            {
                float r = ThreadView.RadiusAt(s, 0.0, 9.0, true, true, false);
                Assert.That(r, Is.LessThanOrEqualTo(previous + 1e-6f), "neck narrows monotonically, s = " + s);
                Assert.That(r, Is.LessThanOrEqualTo(ThreadView.VisibleRadius * 2.2f + 1e-5f));
                previous = r;
            }
            // A downstream piece (after a cut) has no neck.
            Assert.AreEqual(ThreadView.VisibleRadius, ThreadView.RadiusAt(4.0, 4.0, 9.0, false, true, false), 1e-5f);
        }

        [Test]
        public void B2_ThreadTipThinningStaysInsideHeadGrace()
        {
            Assert.That(ThreadView.TipThinLength, Is.LessThan((float)Tuning.HeadGrace));
            const double length = 6.0;
            float tip = ThreadView.RadiusAt(length, 0.0, length, true, true, false);
            Assert.AreEqual(ThreadView.VisibleRadius * ThreadView.TipThinFactor, tip, 1e-5f);
            Assert.That(tip, Is.GreaterThan(0.1f), "slight thinning only");
            Assert.AreEqual(ThreadView.VisibleRadius, ThreadView.RadiusAt(length - ThreadView.TipThinLength - 1e-3, 0.0, length, true, true, false), 1e-5f);
        }

        [Test]
        public void B2_UpstreamPieceEndsInPinchedTaper()
        {
            const double end = 5.0;
            float last = ThreadView.RadiusAt(end, 0.0, end, true, false, true);
            Assert.That(last, Is.LessThan(0.035f), "pinched end");
            float previous = float.MaxValue;
            for (double s = end - ThreadView.TaperLength; s <= end + 1e-9; s += 0.02)
            {
                float r = ThreadView.RadiusAt(s, 0.0, end, true, false, true);
                Assert.That(r, Is.LessThanOrEqualTo(previous + 1e-6f), "taper narrows, s = " + s);
                previous = r;
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Display curve.

        [Test]
        public void B2_TrailCurvePassesThroughSimPoints()
        {
            var trail = new Trail();
            trail.Start(new Vec2d(0.0, 0.0));
            for (int k = 1; k <= 120; k++)
            {
                double a = k * 0.05;
                trail.Append(new Vec2d(3.0 * System.Math.Sin(a), 3.0 - 3.0 * System.Math.Cos(a)));
            }
            int segment = -1;
            for (int k = 0; k < trail.Count; k++)
            {
                Vector2 c = TrailCurve.Evaluate(trail.Points, trail.Arc, trail.Arc[k], ref segment);
                Assert.That(Vector2.Distance(c, TrailCurve.ToVector(trail.Points[k])), Is.LessThan(1e-4f), "point " + k);
            }
            segment = -1;
            for (double s = 0.0; s <= trail.Length; s += 0.037)
            {
                Vector2 c = TrailCurve.Evaluate(trail.Points, trail.Arc, s, ref segment);
                Vec2d exact = trail.PointAt(s);
                Assert.That(Vector2.Distance(c, TrailCurve.ToVector(exact)), Is.LessThan(0.01f), "smoothing stays on the trail, s = " + s);
            }
            Assert.That(Vector2.Distance(TrailCurve.Evaluate(trail.Points, trail.Arc, trail.Length + 1.0, ref segment),
                                         TrailCurve.ToVector(trail.Points[trail.Count - 1])), Is.LessThan(1e-5f));
        }

        // ------------------------------------------------------------------------------------------------------------
        // FieldStroke triangle list conventions (12.2 item 2).

        [Test]
        public void B2_StrokeBuilderEmitsTriangleListWithCaps()
        {
            var b = new StrokeBuilder();
            b.Begin();
            b.BeginPiece();
            for (int k = 0; k < 5; k++) b.AddSample(new Vector2(k * 0.15f, 0f), 0.17f);
            b.EndPiece();
            int caps = 2 * (StrokeBuilder.CapSegments + 2);
            Assert.AreEqual(2 * 5 + caps, b.Vertices.Count);
            Assert.AreEqual(6 * 4 + 2 * 3 * StrokeBuilder.CapSegments, b.Indices.Count);
            Assert.AreEqual(0, b.Indices.Count % 3, "triangle list");
            foreach (Vector2 uv in b.Uvs)
            {
                Assert.AreEqual(1f, uv.x, "uv0.x = amplitude multiplier");
                Assert.That(uv.y == -1f || uv.y == 0f || uv.y == 1f, "uv0.y = cross coordinate");
            }
            float half = Vector3.Distance(b.Vertices[0], b.Vertices[1]) * 0.5f;
            Assert.AreEqual(LiquidLayers.SupportForVisibleRadius(0.17f, 1f), half, 1e-4f, "strip half width = support radius");
            Bounds bounds = b.Bounds;
            Assert.That(bounds.min.x, Is.LessThanOrEqualTo(-1f - half + 1e-3f), "bounds grown by 1 u");
            Assert.That(bounds.max.x, Is.GreaterThanOrEqualTo(0.6f + 1f + half - 1e-3f), "bounds grown by 1 u");
        }

        // ------------------------------------------------------------------------------------------------------------
        // The demo trail (DemoScenario, headless).

        [Test]
        public void B2_DemoThreadOutIsOnePieceFromExitToRenderPos()
        {
            Simulation sim = RunDemoTo(DemoScenario.ThreadOut);
            PlayerState h = sim.Players[DemoScenario.Human];
            Assert.IsFalse(h.Home);
            Assert.IsNull(h.Spark);
            Vector2 tip = Lerp(h.PrevPos, h.Pos, 0.5);
            var b = new StrokeBuilder();
            Assert.AreEqual(1, ThreadView.BuildPieces(b, h, tip, double.NaN));
            Assert.That(Vector2.Distance(b.Centers[0], TrailCurve.ToVector(h.Trail.Points[0])), Is.LessThan(1e-4f), "starts at the exit point");
            Assert.AreEqual(ThreadView.VisibleRadius * ThreadView.NeckWiden, b.Radii[0], 1e-4f, "neck at the exit point");
            Assert.That(Vector2.Distance(b.Centers[b.Centers.Count - 1], tip), Is.LessThan(1e-5f), "tip at RenderPos");
            for (int k = 1; k < b.Centers.Count; k++)
            {
                Assert.That(Vector2.Distance(b.Centers[k], b.Centers[k - 1]), Is.LessThanOrEqualTo(ThreadView.SampleSpacing + 0.01f), "sampled every 0.15 u");
            }
        }

        [Test]
        public void B2_DemoCutThreadHasTaperedUpstreamAndDownstreamFromFront()
        {
            Simulation sim = RunDemoTo(DemoScenario.CutDroplets);
            PlayerState h = sim.Players[DemoScenario.Human];
            Assert.IsNotNull(h.Spark, "the demo is chased at CutDroplets");
            const double alpha = 0.5;
            Vector2 tip = Lerp(h.PrevPos, h.Pos, alpha);
            double sr = h.Spark.PrevS + (h.Spark.S - h.Spark.PrevS) * alpha;
            var b = new StrokeBuilder();
            Assert.AreEqual(2, ThreadView.BuildPieces(b, h, tip, sr));
            // Upstream piece: ends at s_cut - 0.25 with a pinched taper.
            int upLast = b.PieceLength(0) - 1;
            Vector2 upEnd = TrailCurve.ToVector(h.Trail.PointAt(h.Spark.SCut - ThreadView.CutGap));
            Assert.That(Vector2.Distance(b.Centers[upLast], upEnd), Is.LessThan(0.02f), "upstream ends 0.25 u before the cut");
            Assert.That(b.Radii[upLast], Is.LessThan(0.035f), "pinched taper");
            // Downstream piece: from the front (RenderSparkS) to the interpolated head.
            int downFirst = b.PieceStarts[1];
            Vector2 front = TrailCurve.ToVector(h.Trail.PointAt(sr));
            Assert.That(Vector2.Distance(b.Centers[downFirst], front), Is.LessThan(0.02f), "downstream starts at RenderSparkS");
            Assert.That(Vector2.Distance(b.Centers[b.Centers.Count - 1], tip), Is.LessThan(1e-5f), "tip at RenderPos");
        }

        [Test]
        public void B2_RetractionFrontMatchesSimAndLeavesDroplets()
        {
            GameSession session = DemoSessionAt(DemoScenario.CutDroplets);
            var root = new GameObject("B2TestRoot");
            created.Add(root);
            var view = new RetractionView(DemoScenario.Human, root.transform, null, null);
            var ctx = new ActorContext { Session = session, Sim = session.Sim, Time = 1f, Lobes = 1f };
            view.Tick(ctx);
            PlayerState h = session.Sim.Players[DemoScenario.Human];
            Assert.IsTrue(view.HasFront);
            double sr = session.RenderSparkS(DemoScenario.Human);
            Assert.That(Vector2.Distance(view.FrontWorld, TrailCurve.ToVector(h.Trail.PointAt(sr))), Is.LessThan(0.02f), "front at RenderSparkS");
            Assert.AreEqual(sr, view.LeadS, 1e-9, "the bulb's leading edge is the spark while far from the pearl");
            double lr = TrailCurve.RenderLength(h, session.RenderPos(DemoScenario.Human));
            Assert.AreEqual(lr, view.RenderLength, 1e-9);
            // Droplets every 0.45 u behind the bulb, radii 0.07 to 0.12.
            double travel = sr - h.Spark.SCut;
            Assert.That(view.DropletCount, Is.GreaterThanOrEqualTo((int)((travel - 0.8) / RetractionView.DropletSpacing)));
            Assert.That(view.DropletCount, Is.LessThanOrEqualTo((int)(travel / RetractionView.DropletSpacing) + 1));
            DestroyViewMeshes(root);
        }

        [Test]
        public void B2_RetractionFrontNeverOverlapsThePearl()
        {
            GameSession session = DemoSessionAt(DemoScenario.ThreadOut);
            Simulation sim = session.Sim;
            PlayerState h = sim.Players[DemoScenario.Human];
            // A spark right behind the head (as if just cut there).
            sim.DebugForceCut(DemoScenario.Human, h.Trail.Length - 0.5, DemoScenario.FirstCutter);
            Assert.IsNotNull(h.Spark);
            var root = new GameObject("B2TestRoot");
            created.Add(root);
            var view = new RetractionView(DemoScenario.Human, root.transform, null, null);
            var ctx = new ActorContext { Session = session, Sim = sim, Time = 1f, Lobes = 1f };
            view.Tick(ctx);
            double clear = view.RenderLength - Tuning.HeadRadius - RetractionView.PearlClearance;
            // The view works with float radii (0.45f, 0.03f): allow their 1e-7 rounding.
            Assert.That(view.LeadS, Is.LessThanOrEqualTo(clear + 1e-6), "the bulb stays behind the pearl rim");
            Assert.That(view.LeadS, Is.LessThan(h.Spark.S), "the bulb was pulled back from the spark");
            DestroyViewMeshes(root);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Droplets, flash, splash.

        [Test]
        public void B2_DropletRadiiDeterministicAndInRange()
        {
            for (int p = 0; p < 4; p++)
            {
                for (int k = 0; k < 200; k++)
                {
                    float r = RetractionView.DropletRadius(p, k);
                    Assert.That(r, Is.InRange(RetractionView.DropletMinRadius, RetractionView.DropletMaxRadius));
                    Assert.AreEqual(r, RetractionView.DropletRadius(p, k));
                }
            }
            Assert.AreEqual(RetractionView.DropletSpacing, RetractionView.DropletS(2.0, 3) - RetractionView.DropletS(2.0, 2), 1e-9);
        }

        [Test]
        public void Gate_DropletsGrowFromTheCutTowardTheFront()
        {
            // Reference look (docs/reference_gouttes.png): small droplets next to the cut point, larger toward the front.
            for (int p = 0; p < 4; p++)
            {
                float nearCut = (RetractionView.DropletRadius(p, 0) + RetractionView.DropletRadius(p, 1)) * 0.5f;
                float farOut = (RetractionView.DropletRadius(p, 12) + RetractionView.DropletRadius(p, 13)) * 0.5f;
                Assert.That(nearCut, Is.LessThan(0.095f), "player " + p);
                Assert.That(farOut, Is.GreaterThan(0.10f), "player " + p);
                Assert.That(farOut - nearCut, Is.GreaterThan(0.01f), "player " + p);
            }
        }

        [Test]
        public void B2_CutFlashBlinksThreeTimesOver06s()
        {
            int rises = 0;
            bool on = false;
            for (float t = 0f; t < CutFlash.Duration; t += 0.002f)
            {
                bool now = CutFlash.Intensity(t) > 0.5f;
                if (now && !on) rises++;
                on = now;
            }
            Assert.AreEqual(3, rises);
            Assert.AreEqual(0f, CutFlash.Intensity(CutFlash.Duration + 0.01f));
        }

        [Test]
        public void B2_SplashHas8To12Drops()
        {
            for (int seed = -500; seed < 500; seed += 7)
            {
                Assert.That(SplashView.DropCount(seed), Is.InRange(SplashView.MinDrops, SplashView.MaxDrops));
            }
        }

        [Test]
        public void B2_SparkEdgePulseSpeedsUpAsTheSparkCloses()
        {
            Assert.That(SparkEdgeIndicator.PulseHz(0.3), Is.GreaterThan(SparkEdgeIndicator.PulseHz(1.5)));
            Assert.That(SparkEdgeIndicator.PulseHz(1.5), Is.GreaterThan(SparkEdgeIndicator.PulseHz(5.0)));
            Assert.AreEqual(SparkEdgeIndicator.SlowHz, SparkEdgeIndicator.PulseHz(double.PositiveInfinity), 1e-6f);
        }

        // ------------------------------------------------------------------------------------------------------------

        private static Simulation RunDemoTo(long tick)
        {
            Simulation sim = DemoScenario.CreateSimulation(out DemoScenario.Monitor _);
            while (sim.Tick < tick && !sim.Ended) sim.Step();
            return sim;
        }

        private static GameSession DemoSessionAt(long tick)
        {
            GameSession session = DemoScenario.CreateSession(out DemoScenario.Monitor _);
            while (session.Sim.Tick < tick && !session.Sim.Ended) session.Sim.Step();
            return session;
        }

        private static Vector2 Lerp(Vec2d a, Vec2d b, double t)
        {
            return new Vector2((float)(a.X + (b.X - a.X) * t), (float)(a.Y + (b.Y - a.Y) * t));
        }

        private void DestroyViewMeshes(GameObject root)
        {
            foreach (MeshFilter f in root.GetComponentsInChildren<MeshFilter>(true))
            {
                if (f.sharedMesh != null && f.sharedMesh != LiquidLayers.QuadMesh) created.Add(f.sharedMesh);
            }
        }
    }
}
