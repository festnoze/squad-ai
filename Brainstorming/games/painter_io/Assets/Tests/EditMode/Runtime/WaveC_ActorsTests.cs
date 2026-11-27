// Owned by the wave C actors package. EditMode checks of the two actors fixes of docs/waveC/fix_plan.json:
// visuals-chase-front-not-brightest (actors part): the front glint is 0.5 u half size, its flicker never drops below 0.7
// opacity over 120 consecutive flicker steps, a soft halo in the front color is drawn under it (shared Halo shape id) and
// both sort above droplets, threads and pearls; feel-08: the home chevron keeps a constant screen size through the chase
// zoom (its size divided by the view width is the same at view scale 1.0 and 1.44) and is drawn as halo disc, navy drop
// shadow, then the chevron. The drawn quads are read back from the QuadBatch mesh (uv0.z = half size, uv1.x = shape id).
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class WaveC_ActorsTests
    {
        private const float Portrait = 9f / 16f;
        private readonly List<Object> created = new List<Object>();
        private readonly List<QuadBatch> batches = new List<QuadBatch>();

        [TearDown]
        public void TearDown()
        {
            foreach (QuadBatch b in batches) b.Destroy();
            batches.Clear();
            foreach (Object o in created)
            {
                if (o != null) Object.DestroyImmediate(o);
            }
            created.Clear();
        }

        // ------------------------------------------------------------------------------------------------------------
        // Front glint (visuals-chase-front-not-brightest, actors part).

        [Test]
        public void WaveC_GlintOpacityNeverBelowFloorOver120FlickerSteps()
        {
            float[] starts = { 0f, 1.37f, 61.9f, 1234.5f };
            for (int player = 0; player < 4; player++)
            {
                foreach (float t0 in starts)
                {
                    float min = float.MaxValue, max = float.MinValue;
                    int firstStep = Mathf.FloorToInt(t0 * RetractionView.GlintFlickerHz);
                    for (int step = firstStep; step < firstStep + 120; step++)
                    {
                        for (int k = 0; k < 8; k++)
                        {
                            float t = (step + (k + 0.5f) / 8f) / RetractionView.GlintFlickerHz;
                            float o = RetractionView.GlintOpacity(t, player);
                            Assert.That(o, Is.GreaterThanOrEqualTo(0.7f), "absolute floor, player " + player + " t = " + t);
                            Assert.That(o, Is.GreaterThanOrEqualTo(RetractionView.GlintMinOpacity - 1e-6f), "steady flicker low end");
                            Assert.That(o, Is.LessThanOrEqualTo(RetractionView.GlintMaxOpacity + 1e-6f), "steady flicker high end");
                            min = Mathf.Min(min, o);
                            max = Mathf.Max(max, o);
                        }
                    }
                    Assert.That(max - min, Is.GreaterThan(0.08f), "it still flickers (player " + player + ")");
                }
            }
            Assert.AreEqual(0.8f, RetractionView.GlintMinOpacity, 1e-6f);
            Assert.AreEqual(1f, RetractionView.GlintMaxOpacity, 1e-6f);
            Assert.AreEqual(0.7f, RetractionView.GlintFloor, 1e-6f);
        }

        [Test]
        public void WaveC_GlintHalfSizeIs05uWithHaloUnderItOnTheDemoFront()
        {
            Assert.AreEqual(0.5f, RetractionView.GlintHalfSize, 1e-6f, "cross-package value of the fix plan");
            GameSession session = DemoSessionAt(DemoScenario.CutDroplets);
            var root = new GameObject("WaveCActorsRoot");
            created.Add(root);
            var view = new RetractionView(DemoScenario.Human, root.transform, null, null);
            QuadBatch overlays = NewOverlayBatch(root.transform);
            var ctx = new ActorContext { Session = session, Sim = session.Sim, Time = 1f, Lobes = 1f, Overlays = overlays };
            Color front = Palette.LinearColorOf(DemoScenario.Human);
            for (int frame = 0; frame < 120; frame++)
            {
                ctx.Time = 1f + frame / 60f;
                view.Tick(ctx);
                Assert.IsTrue(view.HasFront, "the demo is chased at CutDroplets");
                overlays.Begin();
                view.DrawGlint(ctx);
                overlays.End();
                DrawnQuad[] quads = ReadQuads(overlays);
                Assert.AreEqual(2, quads.Length, "halo then glint");
                Assert.AreEqual((float)OverlayShape.Halo, quads[0].Shape, "the halo is drawn first (under the glint)");
                Assert.AreEqual(RetractionView.GlintHaloHalfSize, quads[0].Half, 1e-4f, "halo half size 1.2 u");
                Assert.AreEqual(1.2f, quads[0].Half, 1e-4f);
                Assert.AreEqual(0.35f, quads[0].Color.a, 1e-4f, "halo opacity");
                Assert.AreEqual(front.r, quads[0].Color.r, 1e-4f, "halo in the front color");
                Assert.AreEqual(front.g, quads[0].Color.g, 1e-4f, "halo in the front color");
                Assert.AreEqual(front.b, quads[0].Color.b, 1e-4f, "halo in the front color");
                Assert.AreEqual((float)OverlayShape.Glint, quads[1].Shape);
                Assert.AreEqual(0.5f, quads[1].Half, 1e-4f, "glint half size 0.5 u");
                Assert.That(quads[1].Color.a, Is.GreaterThanOrEqualTo(0.7f), "glint opacity floor, frame " + frame);
                Assert.That(Vector2.Distance(quads[0].Center, quads[1].Center), Is.LessThan(1e-4f), "halo centered under the glint");
                Assert.That(Vector2.Distance(quads[1].Center, view.FrontWorld), Is.LessThan(0.6f), "glint on the front bulb");
            }
            DestroyViewMeshes(root);
        }

        [Test]
        public void WaveC_HaloAndGlintSortAboveDropletsThreadsAndPearls()
        {
            // Threads and the bulb are drawn by the field composite (queue 1900); droplets, splash drops and pearls are bead
            // batches; the halo and the glint are in the overlay batch, drawn after all of them.
            Assert.That(QuadBatch.QueueOverlays, Is.GreaterThan(1900), "above the composite (threads, bulb)");
            Assert.That(QuadBatch.QueueOverlays, Is.GreaterThan(QuadBatch.QueueDroplets));
            Assert.That(QuadBatch.QueueOverlays, Is.GreaterThan(QuadBatch.QueueSplash));
            Assert.That(QuadBatch.QueueOverlays, Is.GreaterThan(QuadBatch.QueuePearls));
        }

        [Test]
        public void WaveC_GlintShapeUnchangedForFireAndElectric()
        {
            // The fire and electric overlay shape 3 interiors are designed for the 0.5 u half size and these parameters.
            Assert.AreEqual(new Vector3(0.22f, 0.3f, 0.08f), RetractionView.GlintShapeFor(BiomeTheme.Get(BiomeId.Fire)));
            Assert.AreEqual(new Vector3(0.22f, 0.3f, 0.08f), RetractionView.GlintShapeFor(BiomeTheme.Get(BiomeId.Electric)));
            Assert.AreEqual(RetractionView.LiquidGlintShape, RetractionView.GlintShapeFor(BiomeTheme.Get(BiomeId.Liquid)));
            Assert.AreEqual(RetractionView.LiquidGlintShape, RetractionView.GlintShapeFor(null));
        }

        // ------------------------------------------------------------------------------------------------------------
        // Home chevron (feel-08).

        [Test]
        public void WaveC_ChevronScreenSizeIsConstantThroughTheChaseZoom()
        {
            float[] aspects = { Portrait, 1080f / 2400f, 16f / 9f };
            foreach (float aspect in aspects)
            {
                for (float pulse = 0f; pulse <= 1f; pulse += 0.25f)
                {
                    float a = HomeArrow.ChevronHalfSize(1f, pulse) / CameraRig.ViewWidthFor(aspect, 1f);
                    float b = HomeArrow.ChevronHalfSize(1.44f, pulse) / CameraRig.ViewWidthFor(aspect, 1.44f);
                    Assert.AreEqual(a, b, 1e-6f, "size / view width, aspect " + aspect + " pulse " + pulse);
                    float da = (HomeArrow.ChevronDistance(0.45f, 1f, pulse) - 0.45f) / CameraRig.ViewWidthFor(aspect, 1f);
                    float db = (HomeArrow.ChevronDistance(0.45f, 1.44f, pulse) - 0.45f) / CameraRig.ViewWidthFor(aspect, 1.44f);
                    Assert.AreEqual(da, db, 1e-6f, "rim distance / view width, aspect " + aspect);
                }
            }
            Assert.AreEqual(0.62f, HomeArrow.ChevronHalfSize(1f, 0f), 1e-6f);
            Assert.AreEqual(0.62f * 1.44f, HomeArrow.ChevronHalfSize(1.44f, 0f), 1e-6f);
            Assert.AreEqual(0.45f + 0.65f * 1.44f, HomeArrow.ChevronDistance(0.45f, 1.44f, 0f), 1e-6f);
            Assert.AreEqual(0.62f, HomeArrow.ChevronHalfSize(0f, 0f), 1e-6f, "no rig: view scale 1");
            Assert.AreEqual(0.62f, HomeArrow.ChevronHalfSize(float.NaN, 0f), 1e-6f, "no rig: view scale 1");

            // At 540 px width in portrait the chevron (Overlay.hlsl shape 2: arms from (-0.26, +-0.4) to (0.45, 0), half
            // thickness a = 0.16 local) spans at least 20 x 14 px at any zoom (it was about 12 x 8 px at the chase zoom).
            foreach (float scale in new[] { 1f, 1.1f, 1.44f })
            {
                float halfPx = HomeArrow.ChevronHalfSize(scale, 0f) / CameraRig.ViewWidthFor(Portrait, scale) * 540f;
                float t = HomeArrow.ChevronShape.x;
                float across = 2f * (0.4f + t) * halfPx;
                float along = (0.45f + 0.26f + 2f * t) * halfPx;
                Assert.That(across, Is.GreaterThanOrEqualTo(20f), "across, scale " + scale);
                Assert.That(along, Is.GreaterThanOrEqualTo(14f), "along, scale " + scale);
            }
        }

        [Test]
        public void WaveC_ChevronDrawsHaloThenShadowThenChevronAtConstantScreenSize()
        {
            GameSession session = DemoScenario.CreateSession(out DemoScenario.Monitor _);
            var root = new GameObject("WaveCActorsRoot");
            created.Add(root);
            QuadBatch overlays = NewOverlayBatch(root.transform);
            var ctx = new ActorContext { Session = session, Sim = session.Sim, Lobes = 1f, Overlays = overlays };
            Color human = Palette.LinearColorOf(session.HumanIndex);
            var pearl = new Vector2(3f, -2f);
            Vector2 dir = new Vector2(0.6f, -0.8f);
            const float time = 0.0f;   // pulse 0
            float[] ratio = new float[2];
            float[] scales = { 1f, 1.44f };
            for (int i = 0; i < scales.Length; i++)
            {
                ctx.ViewScale = scales[i];
                overlays.Begin();
                HomeArrow.DrawChevron(ctx, pearl, dir, 0.45f, time);
                overlays.End();
                DrawnQuad[] q = ReadQuads(overlays);
                Assert.AreEqual(3, q.Length, "halo, shadow, chevron");
                float half = HomeArrow.ChevronHalfSize(scales[i], 0f);
                Vector2 at = pearl + dir * HomeArrow.ChevronDistance(0.45f, scales[i], 0f);

                Assert.AreEqual((float)OverlayShape.Halo, q[0].Shape, "1. halo disc");
                Assert.AreEqual(1.3f * half, q[0].Half, 1e-4f, "halo radius 1.3x the chevron half size");
                Assert.AreEqual(0.45f, q[0].Color.a, 1e-4f, "halo alpha");
                Assert.AreEqual(human.r, q[0].Color.r, 1e-4f, "halo in the human color");
                Assert.AreEqual(human.g, q[0].Color.g, 1e-4f, "halo in the human color");
                Assert.That(Vector2.Distance(q[0].Center, at), Is.LessThan(1e-4f));

                Assert.AreEqual((float)OverlayShape.Chevron, q[1].Shape, "2. drop shadow");
                Assert.AreEqual(half, q[1].Half, 1e-4f);
                Assert.AreEqual(0.6f, q[1].Color.a, 1e-4f, "shadow alpha");
                Assert.That(q[1].Color.r + q[1].Color.g + q[1].Color.b, Is.LessThan(0.1f), "navy shadow");
                Vector2 offset = q[1].Center - at;
                Assert.AreEqual(0.05f * scales[i], offset.x, 1e-4f, "shadow offset x");
                Assert.AreEqual(-0.05f * scales[i], offset.y, 1e-4f, "shadow offset y");

                Assert.AreEqual((float)OverlayShape.Chevron, q[2].Shape, "3. chevron on top");
                Assert.AreEqual(half, q[2].Half, 1e-4f);
                Assert.That(Vector2.Distance(q[2].Center, at), Is.LessThan(1e-4f));
                Assert.That(Mathf.Min(q[2].Color.r, Mathf.Min(q[2].Color.g, q[2].Color.b)), Is.GreaterThan(0.7f), "white-ish chevron");
                ratio[i] = q[2].Half / CameraRig.ViewWidthFor(Portrait, scales[i]);
            }
            Assert.AreEqual(ratio[0], ratio[1], 1e-6f, "chevron size / view width at view scale 1.0 and 1.44");
            // The chevron stays below the spark's pure white (sRGB < 235) so the spark keeps the brightest pixels.
            Assert.That(HomeArrow.ChevronColor.gamma.r * 255f, Is.LessThan(235f));
            Assert.That(HomeArrow.ChevronColor.gamma.r * 255f, Is.GreaterThan(215f), "still reads as white");
        }

        // ------------------------------------------------------------------------------------------------------------

        private struct DrawnQuad
        {
            public float Shape;
            public float Half;
            public Vector2 Center;
            public Color Color;
        }

        private QuadBatch NewOverlayBatch(Transform parent)
        {
            Shader shader = Resources.Load<Shader>("Shaders/" + BiomeTheme.LiquidOverlayShader);
            if (shader == null) shader = Shader.Find("Hidden/InternalErrorShader");
            Assert.IsNotNull(shader, "an overlay shader (the batch uploads its mesh only with a material)");
            var b = new QuadBatch("WaveCOverlays", parent, shader, QuadBatch.QueueOverlays, 40);
            batches.Add(b);
            return b;
        }

        private static DrawnQuad[] ReadQuads(QuadBatch batch)
        {
            Mesh mesh = batch.Mesh;
            if (batch.Count == 0) return new DrawnQuad[0];
            Assert.AreEqual(batch.Count * 4, mesh.vertexCount, "mesh uploaded");
            Vector3[] v = mesh.vertices;
            Color[] c = mesh.colors;
            var uv0 = new List<Vector4>();
            var uv1 = new List<Vector4>();
            mesh.GetUVs(0, uv0);
            mesh.GetUVs(1, uv1);
            var quads = new DrawnQuad[batch.Count];
            for (int k = 0; k < quads.Length; k++)
            {
                Vector3 sum = v[4 * k] + v[4 * k + 1] + v[4 * k + 2] + v[4 * k + 3];
                quads[k] = new DrawnQuad
                {
                    Shape = uv1[4 * k].x,
                    Half = uv0[4 * k].z,
                    Center = new Vector2(sum.x, sum.y) * 0.25f,
                    Color = c[4 * k],
                };
            }
            return quads;
        }

        private static GameSession DemoSessionAt(long tick)
        {
            GameSession session = DemoScenario.CreateSession(out DemoScenario.Monitor _);
            while (session.Sim.Tick < tick && !session.Sim.Ended) session.Sim.Step();
            return session;
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
