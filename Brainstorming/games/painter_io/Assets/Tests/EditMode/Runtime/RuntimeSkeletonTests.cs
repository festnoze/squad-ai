// Owned by B0a. EditMode checks of the wave B0a skeleton: SimRunner, GameSession factories and helpers, Palette,
// LiquidLayers and LaunchArgs. No test writes PlayerPrefs.
using System;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;

namespace PainterIO.Tests
{
    public class RuntimeSkeletonTests
    {
        [TearDown]
        public void RestoreCommandLine()
        {
            LaunchArgs.Reload();
        }

        private static Simulation IdleSim()
        {
            var config = new SimConfig { TickRate = 60, LassoEnabled = false };
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++) controllers[i] = new HomeCirclerController(Start(i));
            return new Simulation(config, controllers, new SimSetup { HumanIndex = -1 });
        }

        private static Vec2d Start(int i)
        {
            double d = Tuning.StartDiscOffset;
            switch (i)
            {
                case 0: return new Vec2d(-d, -d);
                case 1: return new Vec2d(d, -d);
                case 2: return new Vec2d(d, d);
                default: return new Vec2d(-d, d);
            }
        }

        [Test]
        public void SimRunner_StepsWholeTicksCapsAtEightAndHonoursPauseAndScale()
        {
            Simulation sim = IdleSim();
            var runner = new SimRunner(sim);
            int stepped = 0;
            runner.Stepped += s => stepped++;

            Assert.AreEqual(0, runner.Advance(0.5f / 60f), "half a tick");
            Assert.That(runner.Alpha, Is.EqualTo(0.5f).Within(1e-4f));
            Assert.AreEqual(1, runner.Advance(0.5f / 60f), "the second half completes the tick");
            Assert.AreEqual(1L, sim.Tick);
            Assert.AreEqual(SimRunner.MaxStepsPerFrame, runner.Advance(1f), "a long hitch is capped");
            Assert.That(runner.Alpha, Is.LessThan(1f));
            Assert.AreEqual(1 + SimRunner.MaxStepsPerFrame, stepped, "Stepped after each Step");

            runner.Paused = true;
            Assert.AreEqual(0, runner.Advance(1f));
            runner.Paused = false;

            long before = sim.Tick;
            runner.TimeScale = 0.25f;
            int total = 0;
            for (int k = 0; k < 40; k++) total += runner.Advance(1f / 60f);
            Assert.AreEqual(10, total, "40 frames of one tick at quarter speed give 10 ticks");
            Assert.AreEqual(before + 10, sim.Tick);
            Assert.AreEqual(0, runner.Advance(-1f), "negative deltas are ignored");
        }

        [Test]
        public void GameSession_CreateRoundWaitsForTheHumanAndUsesTheLineup()
        {
            GameSession s = GameSession.CreateRound(12345UL, false);
            Assert.IsFalse(s.IsAttract);
            Assert.AreEqual(0, s.HumanIndex);
            Assert.IsNotNull(s.HumanController);
            Assert.IsNull(s.HumanController.Desired, "finger not down yet");
            Assert.IsTrue(s.AwaitingStart);
            Assert.IsTrue(s.Runner.Paused);
            Assert.IsTrue(s.CountsForStats);
            Assert.AreEqual(4, s.Sim.Players.Count);
            Assert.IsTrue(s.Sim.Players[0].IsHuman);
            Assert.AreEqual(12345UL, s.Sim.Config.Seed);
            Assert.IsFalse(s.Sim.Config.LassoEnabled);

            Assert.AreEqual(0, s.Runner.Advance(1f), "the whole sim waits at t = 0");
            Assert.AreEqual(0.0, s.Sim.Time);
            s.Begin();
            Assert.IsFalse(s.AwaitingStart);
            Assert.IsFalse(s.Runner.Paused);
            s.HumanController.Desired = 1.0;
            Assert.That(s.Runner.Advance(5f / 60f), Is.EqualTo(5));
            Assert.AreEqual(1.0, s.Sim.Players[0].DesiredHeading, 1e-12, "the sim reads the human's input");

            s.AwaitStart();
            Assert.IsTrue(s.AwaitingStart);
            Assert.IsTrue(s.Runner.Paused);
            Assert.IsNull(s.HumanController.Desired, "the gate waits for a new input");
            s.Close();
            Assert.IsTrue(s.IsClosed);
            s.Begin();
            Assert.IsTrue(s.Runner.Paused, "a closed session never restarts");
        }

        [Test]
        public void GameSession_BotSeedsFollowTheRule()
        {
            Assert.AreEqual(7UL * 7919UL + 2UL * 104729UL + 17UL, GameSession.BotSeed(7UL, 2));
            Assert.AreEqual(unchecked(ulong.MaxValue * 7919UL + 104729UL + 17UL), GameSession.BotSeed(ulong.MaxValue, 1), "wraps");
        }

        [Test]
        public void GameSession_AttractRestartsItselfAfterTheRoundEnds()
        {
            GameSession s = GameSession.CreateAttract(99UL);
            Assert.IsTrue(s.IsAttract);
            Assert.AreEqual(-1, s.HumanIndex);
            Assert.IsNull(s.HumanController);
            Assert.IsFalse(s.AwaitingStart);
            Assert.IsFalse(s.CountsForStats);
            Assert.IsFalse(s.HumanAlive);

            Simulation first = s.Sim;
            int restarts = 0;
            s.Restarted += x => restarts++;
            int guard = 0;
            while (!first.Ended && ++guard < 100000) s.Advance(8f / 60f);
            Assert.IsTrue(first.Ended, "the attract round ends");
            Assert.AreSame(first, s.Sim, "kept on screen for a moment");
            s.Advance(GameSession.AttractRestartDelay + 0.1f);
            Assert.AreEqual(1, restarts);
            Assert.AreNotSame(first, s.Sim, "a new simulation");
            Assert.AreSame(s.Sim, s.Runner.Sim);
            Assert.That(s.Sim.Tick, Is.LessThanOrEqualTo(SimRunner.MaxStepsPerFrame));
            Assert.IsFalse(s.Sim.Ended);
        }

        [Test]
        public void GameSession_RenderPosInterpolatesAndForwardsEventsAfterTheStep()
        {
            var config = new SimConfig { TickRate = 60, LassoEnabled = false, TurnRateDeg = 0.0 };
            var controllers = new IController[] { new ConstantHeadingController(0.0), new HomeCirclerController(Start(1)) };
            var setup = new SimSetup
            {
                PlayerCount = 2,
                StartPositions = new[] { new Vec2d(-16, -16), Start(1) },
                StartHeadings = new[] { 0.0, 0.0 },
                HumanIndex = -1,
            };
            var s = new GameSession(config, setup, controllers, false);
            int exitTick = -1;
            bool sawStateAfterStep = false;
            s.EventRaised += e =>
            {
                if (e.Type == SimEventType.Exit && e.Player == 0)
                {
                    exitTick = (int)s.Sim.Tick;
                    sawStateAfterStep = !s.Sim.Players[0].Home && Math.Abs(s.ExitStartTime(0) - e.Time) < 1e-12;
                }
            };
            s.EventRaised += e => throw new InvalidOperationException("a broken subscriber must not stop the sim");
            UnityEngine.TestTools.LogAssert.ignoreFailingMessages = true;
            try
            {
                for (int k = 0; k < 60; k++) s.Runner.Advance(1f / 60f);
            }
            finally
            {
                UnityEngine.TestTools.LogAssert.ignoreFailingMessages = false;
            }
            Assert.That(exitTick, Is.GreaterThan(0), "the exit was forwarded");
            Assert.IsTrue(sawStateAfterStep, "handlers see the state after the Step");
            Assert.AreEqual(60L, s.Sim.Tick, "the throwing subscriber did not stop the sim");

            s.Runner.Advance(0.5f / 60f);
            PlayerState p = s.Sim.Players[0];
            Vector2 r = s.RenderPos(0);
            Assert.That(r.x, Is.EqualTo((float)(0.5 * (p.PrevPos.X + p.Pos.X))).Within(1e-4f));
            Assert.That(r.y, Is.EqualTo((float)p.Pos.Y).Within(1e-4f));
            Assert.That(s.ExitAge(0), Is.GreaterThan(0.0));
            Assert.IsTrue(s.HasVisibleDetach(0));
            Assert.IsTrue(double.IsNaN(s.RenderSparkS(0)));
        }

        [Test]
        public void GameSession_FlickerReturnRule()
        {
            var s = new GameSession(new SimConfig { LassoEnabled = false }, null,
                                    new IController[] { new HomeCirclerController(Start(0)), new HomeCirclerController(Start(1)),
                                                        new HomeCirclerController(Start(2)), new HomeCirclerController(Start(3)) }, false);
            var chased = new SimEvent { Type = SimEventType.Return, Player = 0, Cells = new int[0], Chased = true };
            var full = new SimEvent { Type = SimEventType.Return, Player = 0, Cells = new[] { 1 } };
            var exit = new SimEvent { Type = SimEventType.Exit, Player = 0 };
            Assert.IsFalse(s.IsFlickerReturn(chased), "a chased return is never noise");
            Assert.IsFalse(s.IsFlickerReturn(full), "a return with cells is never noise");
            Assert.IsFalse(s.IsFlickerReturn(exit));
            Assert.IsFalse(s.IsFlickerReturn(null));
        }

        [Test]
        public void Palette_SwapsTheHumanColorWithPlayerZero()
        {
            int h = Palette.HumanColor;
            Assert.AreEqual(h, Palette.ColorIndexOf(0));
            Assert.AreEqual(0, Palette.ColorIndexOf(h), "the sim player shown in the human's color gets coral");
            var seen = new bool[4];
            for (int i = 0; i < 4; i++) seen[Palette.ColorIndexOf(i)] = true;
            foreach (bool b in seen) Assert.IsTrue(b, "a permutation of the four colors");
            Assert.AreEqual(Palette.Colors[h], Palette.ColorOf(0));
            Color32 coral = Palette.Colors[0];
            Assert.AreEqual(0xF2, coral.r);
            Assert.AreEqual(0x67, coral.g);
            Assert.AreEqual(0x4F, coral.b);
            Assert.AreEqual("name.color2", Palette.ColorNameKey(2));
        }

        [Test]
        public void LiquidLayers_QuadMaskAndSupport()
        {
            Mesh quad = LiquidLayers.QuadMesh;
            Assert.IsNotNull(quad);
            Assert.AreSame(quad, LiquidLayers.QuadMesh, "built once");
            Assert.AreEqual(4, quad.vertexCount);
            Assert.AreEqual(6, quad.triangles.Length);
            Assert.That(quad.bounds.size.x, Is.EqualTo(1f).Within(1e-6f));
            Vector3[] v = quad.vertices;
            int[] t = quad.triangles;
            for (int k = 0; k < t.Length; k += 3)
            {
                Vector3 a = v[t[k]], b = v[t[k + 1]], c = v[t[k + 2]];
                float cross = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
                Assert.Less(cross, 0f, "clockwise seen from -Z (front face for the main camera)");
            }
            Assert.AreEqual(new Vector4(0, 0, 1, 0), LiquidLayers.ChannelMask(2));
            Assert.AreEqual(Vector4.zero, LiquidLayers.ChannelMask(7));
            float s = LiquidLayers.SupportForVisibleRadius(1f, 1f);
            Assert.That(s, Is.EqualTo(1f / Mathf.Sqrt(1f - Mathf.Sqrt(0.5f))).Within(1e-5f));
            // f = A (1 - r^2)^2 at the visible radius equals the iso level.
            float r = 1f / s;
            Assert.That(1f * (1f - r * r) * (1f - r * r), Is.EqualTo(LiquidLayers.IsoLevel).Within(1e-5f));
            Assert.AreEqual(LiquidLayers.SupportForVisibleRadius(1f, 0.51f), LiquidLayers.SupportForVisibleRadius(1f, 0.1f), "clamped below 0.51");
        }

        [Test]
        public void LaunchArgs_ParsesOverridesAndClamps()
        {
            LaunchArgs.Reload(new[] { "app.exe", "-fps", "144", "-sparkFactor", "2,2", "-roundDuration", "1", "-lasso", "1", "-devshot", "C:/tmp/shots" });
            Assert.AreEqual(144, LaunchArgs.Fps);
            Assert.That(LaunchArgs.SparkFactor.Value, Is.EqualTo(2.2).Within(1e-12));
            Assert.AreEqual(5.0, LaunchArgs.RoundDuration.Value, "clamped to 5 s");
            Assert.IsNull(LaunchArgs.RingInterval);
            Assert.AreEqual(true, LaunchArgs.Lasso);
            Assert.IsTrue(LaunchArgs.HasTuningOverride);
            Assert.IsTrue(LaunchArgs.Has("-DEVSHOT"));
            Assert.AreEqual("C:/tmp/shots", LaunchArgs.Value("-devshot"));
            SimConfig c = GameSession.RoundConfig(3UL, true);
            Assert.That(c.SparkSpeedFactor, Is.EqualTo(2.2).Within(1e-12));
            Assert.AreEqual(5.0, c.RoundDuration);
            Assert.IsTrue(c.LassoEnabled);

            LaunchArgs.Reload(new[] { "app.exe" });
            Assert.AreEqual(0, LaunchArgs.Fps);
            Assert.IsNull(LaunchArgs.Lasso);
            Assert.IsFalse(LaunchArgs.HasTuningOverride);
        }
    }
}
