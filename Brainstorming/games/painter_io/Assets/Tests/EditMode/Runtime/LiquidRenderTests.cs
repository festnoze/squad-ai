// Owned by B1. EditMode checks of the liquid renderer's CPU logic (contract 12.2 item 1, 12.3, 12.4): the VisualMask
// follows the grid at bind time, a capture fills in over FillDuration in distance order from the return point and ends
// equal to the grid with no reconciliation repair, an eliminated player's channel evaporates through _PIO_PlayerFade and
// is then cleared, the pocket mask follows PlayerState.Pocket, and the quality tier table. The scripted DemoScenario
// round is driven frame by frame through GameSession.Advance like GameDirector does. No test writes PlayerPrefs.
using System;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class LiquidRenderTests
    {
        private const float Frame = 1f / 60f;

        private GameSession session;
        private TerritoryField field;
        private readonly List<SimEvent> events = new List<SimEvent>();

        [SetUp]
        public void SetUp()
        {
            events.Clear();
            field = new TerritoryField(Resources.Load<Shader>(LiquidRenderer.BlurShaderPath));
            Use(DemoScenario.CreateSession(out DemoScenario.Monitor _));
        }

        private void Use(GameSession s)
        {
            if (session != null) session.Close();
            events.Clear();
            session = s;
            field.Bind(session);
            session.EventRaised += field.OnSimEvent;
            session.EventRaised += e => events.Add(e);
        }

        // Player 0 leaves its start disc to the north, draws a 5 x 5 u square and comes back unchased (contract 24: only an
        // unchased return captures); the three others orbit inside their own discs.
        private static GameSession CaptureSession()
        {
            var config = new SimConfig { TickRate = 60, LassoEnabled = false, Seed = 3 };
            var home = new Vec2d(-16, -16);
            var path = new List<Vec2d> { new Vec2d(-16, -11), new Vec2d(-11, -11), new Vec2d(-11, -16), new Vec2d(-16, -16) };
            var controllers = new IController[]
            {
                new DemoScenario.PathThenCircleController(path, home),
                new HomeCirclerController(new Vec2d(16, -16)),
                new HomeCirclerController(new Vec2d(16, 16)),
                new HomeCirclerController(new Vec2d(-16, 16)),
            };
            return new GameSession(config, new SimSetup { PlayerCount = 4, HumanIndex = 0 }, controllers, false);
        }

        [TearDown]
        public void TearDown()
        {
            if (field != null) field.Dispose();
            field = null;
            if (session != null) session.Close();
            session = null;
        }

        private void RunFrames(int frames)
        {
            for (int k = 0; k < frames; k++)
            {
                session.Advance(Frame);
                field.Update(Frame);
            }
        }

        private static byte GridOwner(OwnerGrid g, int c)
        {
            byte o = g.Cells[c];
            return o == OwnerGrid.Void ? (byte)0 : o;
        }

        private int CountVisualMismatches()
        {
            OwnerGrid g = session.Sim.Grid;
            int bad = 0;
            for (int c = 0; c < g.Cells.Length; c++)
            {
                if (field.VisualOwner(c) != GridOwner(g, c)) bad++;
            }
            return bad;
        }

        private SimEvent FirstReturnWithCells(int player)
        {
            foreach (SimEvent e in events)
            {
                if (e.Type == SimEventType.Return && e.Player == player && e.Cells != null && e.Cells.Length > 0) return e;
            }
            return null;
        }

        [Test]
        public void Gate_ActorFieldSizeStaysPutDuringTheChaseZoom()
        {
            Assert.AreEqual(416, ActorFieldCamera.QuantizeSide(416f, 4096));
            Assert.AreEqual(448, ActorFieldCamera.QuantizeSide(416.5f, 4096));
            Assert.AreEqual(32, ActorFieldCamera.QuantizeSide(0f, 4096));
            Assert.AreEqual(4096, ActorFieldCamera.QuantizeSide(5000f, 4096));
            // 540 x 960 portrait on High (scale 0.75), view width eased from 18 u to the widest chase view 26 u, 0.6 u
            // margin per side: the exact size drifts by about 8 px, the quantized size never changes (no reallocation).
            int w0 = -1, h0 = -1;
            for (float width = 18f; width <= 26.001f; width += 0.25f)
            {
                float ppu = 540f / width;
                float height = width * 960f / 540f;
                int w = ActorFieldCamera.QuantizeSide((width + 1.2f) * ppu * 0.75f, 4096);
                int h = ActorFieldCamera.QuantizeSide((height + 1.2f) * ppu * 0.75f, 4096);
                if (w0 < 0) { w0 = w; h0 = h; }
                Assert.AreEqual(w0, w, "width at view " + width);
                Assert.AreEqual(h0, h, "height at view " + width);
            }
            Assert.AreEqual(448, w0);
            Assert.AreEqual(768, h0);
        }

        [Test]
        public void B1_Bind_VisualMaskEqualsGrid()
        {
            Assert.AreEqual(session.Sim.Grid.Size, field.Size);
            Assert.AreEqual(0, CountVisualMismatches(), "after Bind every cell shows its grid owner");
            Color32[] px = field.VisualMask.GetPixels32();
            OwnerGrid g = session.Sim.Grid;
            int human = 0;
            for (int c = 0; c < px.Length; c++)
            {
                if (px[c].r == 255) human++;
                Assert.That(px[c].r + px[c].g + px[c].b + px[c].a, Is.EqualTo(GridOwner(g, c) == 0 ? 0 : 255), "one channel per owned cell");
            }
            Assert.AreEqual(g.CountOf(1), human, "red channel = player 0 cells");
        }

        [Test]
        public void B1_FillWave_DistanceOrderThenEqualsGrid()
        {
            Use(CaptureSession());
            SimEvent ret = null;
            int guard = 0;
            while (ret == null && guard++ < 600)
            {
                RunFrames(1);
                ret = FirstReturnWithCells(0);
            }
            Assert.IsNotNull(ret, "the unchased return captures cells");
            Assert.IsFalse(ret.Chased);
            Assert.That(field.ActiveWaves, Is.GreaterThanOrEqualTo(1), "the return started a fill wave");
            byte id = 1;
            OwnerGrid g = session.Sim.Grid;
            double cs = g.CellSize, org = g.Origin;
            Func<int, double> dist = c =>
            {
                double x = org + (c % g.Size + 0.5) * cs - ret.Point.X, y = org + (c / g.Size + 0.5) * cs - ret.Point.Y;
                return Math.Sqrt(x * x + y * y);
            };
            double dMax = 0.0;
            foreach (int c in ret.Cells) dMax = Math.Max(dMax, dist(c));
            Assert.That(dMax, Is.GreaterThan(1.0));

            bool sawPartial = false;
            int framesToFill = 0;
            while (framesToFill++ < 60)
            {
                // Every revealed cell is nearer than every hidden one (up to the distance covered in one frame).
                double maxShown = 0.0, minHidden = double.MaxValue;
                int shown = 0;
                foreach (int c in ret.Cells)
                {
                    if (field.VisualOwner(c) == id)
                    {
                        shown++;
                        maxShown = Math.Max(maxShown, dist(c));
                    }
                    else minHidden = Math.Min(minHidden, dist(c));
                }
                if (shown > 0 && shown < ret.Cells.Length)
                {
                    sawPartial = true;
                    double perFrame = dMax * Frame / TerritoryField.FillDuration;
                    Assert.That(maxShown, Is.LessThanOrEqualTo(minHidden + perFrame + 1e-6), "wave in distance order");
                }
                if (shown == ret.Cells.Length) break;
                RunFrames(1);
            }
            Assert.IsTrue(sawPartial, "the fill is spread over several frames");
            double seconds = framesToFill * (double)Frame;
            Assert.That(seconds, Is.InRange(TerritoryField.FillDuration - 0.05, TerritoryField.FillDuration + 0.1), "fill lasts about FillDuration");
            RunFrames(3);
            Assert.AreEqual(0, field.ActiveWaves);
            Assert.AreEqual(0, CountVisualMismatches(), "after the wave the mask equals the grid");
            Assert.AreEqual(0, field.LastReconcileFixes, "the event-driven state needed no repair");
        }

        [Test]
        public void B1_PocketMask_FollowsPendingPocket()
        {
            RunFrames((int)DemoScenario.PocketPending + 2);
            CellMask pocket = session.Sim.Players[DemoScenario.Human].Pocket;
            Assert.That(pocket.Count, Is.GreaterThan(0), "the demo has a pending pocket at PocketPending");
            Color32[] px = field.PocketMask.GetPixels32();
            int red = 0, other = 0;
            for (int c = 0; c < px.Length; c++)
            {
                if (px[c].r == 255) red++;
                if (px[c].g != 0 || px[c].b != 0 || px[c].a != 0) other++;
            }
            Assert.AreEqual(pocket.Count, red, "red channel = the human's pending pocket");
            Assert.AreEqual(0, other, "no other player has a pocket");
        }

        [Test]
        public void B1_Evaporation_FadesThenClearsChannel()
        {
            RunFrames((int)DemoScenario.Caught + 2);
            Assert.IsFalse(session.Sim.Players[DemoScenario.Human].Alive, "the demo's spark caught the human");
            double tElim = double.NaN;
            foreach (SimEvent e in events)
            {
                if (e.Type == SimEventType.Eliminated && e.Player == DemoScenario.Human) tElim = e.Time;
            }
            Assert.IsFalse(double.IsNaN(tElim));
            bool sawFading = false;
            for (int k = 0; k < 60; k++)
            {
                float f = field.PlayerFade.x;
                if (f > 0.05f && f < 0.95f) sawFading = true;
                if (field.VisualTime() > tElim + TerritoryField.EvaporationSeconds + 0.05) break;
                RunFrames(1);
            }
            RunFrames(2);
            Assert.IsTrue(sawFading, "the channel faded through intermediate values");
            Assert.AreEqual(1f, field.PlayerFade.x, 1e-6f, "the fade resets once the channel is cleared");
            int left = 0;
            for (int c = 0; c < session.Sim.Grid.Cells.Length; c++)
            {
                if (field.VisualOwner(c) == DemoScenario.Human + 1) left++;
            }
            Assert.AreEqual(0, left, "the evaporated channel is cleared from the VisualMask");
            Assert.AreEqual(0, CountVisualMismatches());
        }

        [Test]
        public void B1_QualityTier_Table()
        {
            Assert.AreEqual(0.75f, QualityTier.ScaleOf(RenderTier.High));
            Assert.AreEqual(0.5f, QualityTier.ScaleOf(RenderTier.Medium));
            Assert.AreEqual(0.35f, QualityTier.ScaleOf(RenderTier.Low));
            Assert.AreEqual(1, (int)RenderTier.High, "values match SaveData.Quality");
            Assert.AreEqual(3, (int)RenderTier.Low);
            Vector4 flags = QualityTier.ShaderFlags;
            Assert.That(flags.x, Is.EqualTo(1f).Or.EqualTo(2f));
        }
    }
}
