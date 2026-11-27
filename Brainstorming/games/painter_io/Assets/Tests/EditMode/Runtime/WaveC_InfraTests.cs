// Owned by the wave C infra-perf package. EditMode checks of: the tier render height cap (perf-02: QualityTier.RenderScaleFor
// and the actor field's rendered height), the FPS watchdog driven frame by frame (robust-02 / perf-03: an outlier frame
// restarts the window, a steady low rate steps exactly once, frames that are not running never step) and the session
// shader clock (robust-07: _PIO_Time counts from the session start and wraps at 4096 s). The static tier state is reset
// around every test (QualityTier.ResetForTests), so no test depends on the order, the platform or PlayerPrefs.
using NUnit.Framework;
using PainterIO.Runtime;

namespace PainterIO.Tests
{
    public class WaveC_InfraTests
    {
        private const float Target = 60f;

        [SetUp]
        public void SetUp()
        {
            QualityTier.ResetForTests(RenderTier.High);
        }

        [TearDown]
        public void TearDown()
        {
            // Back to the uninitialized state: the next read applies the forced setting or the platform default.
            QualityTier.ResetForTests(null);
        }

        // Feeds the watchdog `seconds` of frames of `dt` seconds; returns the simulated time spent.
        private static float Run(float dt, float seconds, bool running = true)
        {
            int frames = (int)System.Math.Round(seconds / dt);
            for (int i = 0; i < frames; i++) QualityTier.TickWatchdog(dt, running, Target);
            return frames * dt;
        }

        [Test]
        public void WaveC_RenderScaleFor_Table()
        {
            Assert.AreEqual(0.6667f, QualityTier.RenderScaleFor(2400, RenderTier.Medium, true), 1e-4f);
            Assert.AreEqual(0.5333f, QualityTier.RenderScaleFor(2400, RenderTier.Low, true), 1e-4f);
            Assert.AreEqual(0.8f, QualityTier.RenderScaleFor(2400, RenderTier.High, true), 1e-4f);
            Assert.AreEqual(0.8333f, QualityTier.RenderScaleFor(1920, RenderTier.Medium, true), 1e-4f);
            Assert.AreEqual(1f, QualityTier.RenderScaleFor(960, RenderTier.Medium, false));
            Assert.AreEqual(1f, QualityTier.RenderScaleFor(1200, RenderTier.High, false));
            // The release acceptance window and the edges of each cap.
            Assert.AreEqual(0.8f, QualityTier.RenderScaleFor(1600, RenderTier.Low, false), 1e-4f);
            Assert.AreEqual(1f, QualityTier.RenderScaleFor(1600, RenderTier.Medium, false), "a screen at the cap is not scaled");
            Assert.AreEqual(1f, QualityTier.RenderScaleFor(1280, RenderTier.Low, true));
            Assert.AreEqual(1f, QualityTier.RenderScaleFor(1920, RenderTier.High, true));
            Assert.AreEqual(1f, QualityTier.RenderScaleFor(4000, RenderTier.High, false), "High has no cap off Android");
            Assert.AreEqual(1f, QualityTier.RenderScaleFor(0, RenderTier.Low, true), "no screen yet: no scaling");
            Assert.AreEqual(1600, QualityTier.RenderHeightCap(RenderTier.Medium, false));
            Assert.AreEqual(1280, QualityTier.RenderHeightCap(RenderTier.Low, true));
            Assert.AreEqual(1920, QualityTier.RenderHeightCap(RenderTier.High, true));
            Assert.AreEqual(0, QualityTier.RenderHeightCap(RenderTier.High, false));
        }

        [Test]
        public void WaveC_ActorField_FollowsTheRenderedHeight()
        {
            Assert.AreEqual(1600f, ActorFieldCamera.RenderedHeight(2400f, 1600f / 2400f), 0.01f);
            Assert.AreEqual(960f, ActorFieldCamera.RenderedHeight(960f, 1f));
            Assert.AreEqual(960f, ActorFieldCamera.RenderedHeight(960f, 2f), "clamped to 1: never denser than the screen");
            Assert.AreEqual(96f, ActorFieldCamera.RenderedHeight(960f, 0.01f), 1e-3f, "clamped to 0.1");
            Assert.AreEqual(960f, ActorFieldCamera.RenderedHeight(960f, float.NaN));
            Assert.AreEqual(1f, ActorFieldCamera.RenderedHeight(0f, 1f));
            // 1080 x 2400 portrait on Medium (scale 0.5), 18 u wide view, 0.6 u margin: the RT shrinks with the render scale.
            float width = 18f, height = 18f * 2400f / 1080f;
            float ppuNative = 2400f / height;
            float ppuScaled = ActorFieldCamera.RenderedHeight(2400f, QualityTier.RenderScaleFor(2400, RenderTier.Medium, true)) / height;
            int hNative = ActorFieldCamera.QuantizeSide((height + 1.2f) * ppuNative * 0.5f, 4096);
            int hScaled = ActorFieldCamera.QuantizeSide((height + 1.2f) * ppuScaled * 0.5f, 4096);
            int wScaled = ActorFieldCamera.QuantizeSide((width + 1.2f) * ppuScaled * 0.5f, 4096);
            Assert.AreEqual(1248, hNative);
            Assert.AreEqual(832, hScaled);
            Assert.AreEqual(384, wScaled);
            Assert.AreEqual(0, hScaled % ActorFieldCamera.RtQuantum, "the RtQuantum rounding is kept");
        }

        [Test]
        public void WaveC_Watchdog_OutlierThreshold()
        {
            Assert.IsTrue(QualityTier.IsOutlierFrame(0.11f, 60f));
            Assert.IsFalse(QualityTier.IsOutlierFrame(0.09f, 60f), "0.1 s floor at 60 fps");
            Assert.IsFalse(QualityTier.IsOutlierFrame(0.12f, 30f), "4 budgets at 30 fps = 0.133 s");
            Assert.IsTrue(QualityTier.IsOutlierFrame(0.14f, 30f));
            Assert.IsTrue(QualityTier.IsOutlierFrame(0.101f, 144f), "the 0.1 s floor holds at high refresh rates");
            Assert.IsFalse(QualityTier.IsOutlierFrame(1f / 60f, 60f));
        }

        [Test]
        public void WaveC_Watchdog_OneHitchDoesNotStep()
        {
            QualityTier.BeginSession();
            float t = Run(1f / 60f, 12f);
            Assert.AreEqual(12f, t, 0.02f);
            QualityTier.TickWatchdog(1.5f, true, Target);   // the process suspended for 1.5 s at t = 12 s
            Run(1f / 60f, 10f);
            Assert.AreEqual(0, QualityTier.WatchdogSteps, "a single hitch must not step the tier");
            Assert.AreEqual(RenderTier.High, QualityTier.Current);
        }

        [Test]
        public void WaveC_Watchdog_SteadyLowRateStepsOnce()
        {
            QualityTier.BeginSession();
            Run(1f / 40f, 9f);
            Assert.AreEqual(1, QualityTier.WatchdogSteps, "a steady 40 fps against 60 steps once");
            Assert.AreEqual(RenderTier.Medium, QualityTier.Current);
            Run(1f / 40f, 9f);
            Assert.AreEqual(1, QualityTier.WatchdogSteps, "at most one step per real session");
            Assert.AreEqual(RenderTier.Medium, QualityTier.Current);
        }

        [Test]
        public void WaveC_Watchdog_NotRunningNeverSteps()
        {
            QualityTier.BeginSession();
            Run(1f / 40f, 20f, false);
            Assert.AreEqual(0, QualityTier.WatchdogSteps, "frames that are not running (menu, results, pause) never step");
            Assert.AreEqual(RenderTier.High, QualityTier.Current);
        }

        [Test]
        public void WaveC_Watchdog_SlowFramesAroundAHitchStillStep()
        {
            // The outlier rule drops only the long frame: a slow rate on both sides of it is still caught.
            QualityTier.BeginSession();
            Run(1f / 40f, 6f);
            QualityTier.TickWatchdog(1.5f, true, Target);
            Run(1f / 40f, 3.5f);
            Assert.AreEqual(1, QualityTier.WatchdogSteps);
            Assert.AreEqual(RenderTier.Medium, QualityTier.Current);
        }

        [Test]
        public void WaveC_ShaderTime_CountsFromTheSessionAndWraps()
        {
            const double e = 123456.789;
            Assert.AreEqual(0f, LiquidRenderer.ShaderTimeFor(e, e));
            float later = LiquidRenderer.ShaderTimeFor(e + 5000.0, e);
            Assert.That(later, Is.LessThan(4096f));
            Assert.AreEqual(904f, later, 1e-3f);
            Assert.AreEqual(10.25f, LiquidRenderer.ShaderTimeFor(e + 10.25, e), 1e-4f);
            Assert.That(LiquidRenderer.ShaderTimeFor(e - 1.0, e), Is.GreaterThanOrEqualTo(0f), "never negative");
            Assert.AreEqual(4096.0, LiquidRenderer.ShaderTimeWrap);
        }
    }
}
