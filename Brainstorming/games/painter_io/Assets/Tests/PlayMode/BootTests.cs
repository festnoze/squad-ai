// Owned by BI since wave B-2 (written by B0a). Contract 18.1 PlayMode boot test, plus the GameDirector flows that need the MonoBehaviour lifecycle:
// the results flow on the scripted demo round (HumanOutcome, death beat) and the pause / ready gate / slow motion.
// The render and UI checks of 18.1 apply as soon as their package replaced the B0a stub (a stub root GameObject is named
// "<Subsystem> (stub)"); while a stub is in place they are skipped with a log line. No test writes PlayerPrefs.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using UnityEngine.TestTools;

namespace PainterIO.Tests
{
    public class BootTests
    {
        private readonly List<string> errors = new List<string>();
        private GameObject game;

        [UnitySetUp]
        public IEnumerator SetUp()
        {
            errors.Clear();
            if (GameDirector.Instance != null)
            {
                UnityEngine.Object.Destroy(GameDirector.Instance.gameObject);
                yield return null;
            }
            Application.logMessageReceived += OnLog;
        }

        [UnityTearDown]
        public IEnumerator TearDown()
        {
            Application.logMessageReceived -= OnLog;
            if (game != null) UnityEngine.Object.Destroy(game);
            game = null;
            yield return null;
            Assert.IsNull(GameDirector.Instance, "the director is gone after teardown");
        }

        private void OnLog(string condition, string stackTrace, LogType type)
        {
            if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert) errors.Add(type + ": " + condition);
        }

        private void AssertNoErrors(string when)
        {
            Assert.IsEmpty(errors, when + ": errors or exceptions were logged:\n" + string.Join("\n", errors));
        }

        private GameDirector Boot()
        {
            game = new GameObject("Game");
            return game.AddComponent<GameDirector>();
        }

        // ------------------------------------------------------------------------------------------------------------

        [UnityTest]
        public IEnumerator Boot_MenuThenRoundRuns()
        {
            GameDirector d = Boot();
            Assert.AreSame(d, GameDirector.Instance);
            for (int k = 0; k < 120; k++) yield return null;
            float wait = Time.realtimeSinceStartup;
            while (d.Session != null && d.Session.Sim.Tick == 0 && Time.realtimeSinceStartup - wait < 5f) yield return null;

            AssertNoErrors("after 120 frames");
            Assert.AreEqual(GameState.Menu, d.State, "menu after boot");
            Assert.IsNotNull(d.Session, "attract session");
            Assert.IsTrue(d.Session.IsAttract);
            Assert.That(d.Session.Sim.Tick, Is.GreaterThan(0), "the attract match runs behind the menu");
            Camera main = MainCamera();
            Assert.IsNotNull(main, "an orthographic main camera without the field layer exists (CameraRig, contract 14)");
            Assert.That(main.transform.position.z, Is.EqualTo(-50f).Within(1e-3f), "camera at z = -50");
            Assert.IsNotNull(Find<CameraRig>(d), "CameraRig built");
            Assert.IsNotNull(Find<LiquidRenderer>(d), "LiquidRenderer built");
            Assert.IsNotNull(Find<ActorViews>(d), "ActorViews built");
            Assert.IsNotNull(Find<SteeringInput>(d), "SteeringInput built");
            Assert.IsNotNull(Find<UiRoot>(d), "UiRoot built");
            Assert.IsNotNull(Find<Sfx>(d), "Sfx built");

            AssertRenderers();
            if (IsStub(Find<LiquidRenderer>(d))) Debug.Log("[BootTests] LiquidRenderer is still the B0a stub: LiquidSurface and ActorField checks skipped");
            else AssertLiquidRendering();
            if (IsStub(Find<UiRoot>(d))) Debug.Log("[BootTests] UiRoot is still the B0a stub: text checks skipped");
            else AssertVisibleTextsNonEmpty("menu");

            // A real round: the ready gate holds the sim at t = 0, Begin releases it.
            d.StartRound();
            yield return null;
            Assert.AreEqual(GameState.Playing, d.State);
            GameSession s = d.Session;
            Assert.IsFalse(s.IsAttract);
            Assert.AreEqual(0, s.HumanIndex);
            Assert.IsNotNull(s.HumanController, "human controller");
            s.Begin();
            Assert.IsFalse(s.AwaitingStart);

            // Simulate 3 s of real time; the test steers the human around its own disc (so it stays home and alive).
            var circler = new HomeCirclerController(new Vec2d(-Tuning.StartDiscOffset, -Tuning.StartDiscOffset));
            float t0 = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - t0 < 3f)
            {
                s.HumanController.Desired = circler.DesiredHeading(s.Sim.View, 0);
                yield return null;
            }
            Assert.AreSame(s, d.Session, "same session");
            Assert.That(s.Sim.Time, Is.GreaterThan(0.25), "sim time advanced");
            Assert.That(s.HumanController.Desired.HasValue, "human controller writable");
            Assert.That(Math.Abs(Geo.WrapAngle(s.HumanController.Desired.Value - s.Sim.Players[0].DesiredHeading)), Is.LessThan(1.0),
                        "the sim reads the human's input");
            Assert.IsTrue(s.HumanAlive);
            if (!IsStub(Find<UiRoot>(d))) AssertVisibleTextsNonEmpty("HUD");
            Debug.Log("[BootTests] round ran " + s.Sim.Time.ToString("0.00") + " s of sim in 3 s of real time");
            AssertNoErrors("after the round");
        }

        [UnityTest]
        public IEnumerator Results_DemoRoundBuildsTheOutcomeAndShowsResultsAfterTheDeathBeat()
        {
            GameDirector d = Boot();
            yield return null;
            GameSession demo = DemoScenario.CreateSession(out DemoScenario.Monitor monitor);
            d.StartRound(demo);
            Assert.AreEqual(GameState.Playing, d.State);
            Assert.AreSame(demo, d.Session);
            Assert.IsFalse(demo.AwaitingStart, "scripted sessions start at once");

            var states = new List<GameState>();
            d.StateChanged += st => states.Add(st);
            float t0 = Time.realtimeSinceStartup;
            float eliminatedAt = -1f;
            HumanOutcome atElimination = null;
            while (d.State != GameState.Results && Time.realtimeSinceStartup - t0 < 90f)
            {
                demo.Runner.TimeScale = Mathf.Max(demo.Runner.TimeScale, 3f);   // the slow motion still wins while it runs
                if (eliminatedAt < 0f && !demo.Sim.Players[DemoScenario.Human].Alive)
                {
                    eliminatedAt = Time.realtimeSinceStartup;
                    atElimination = d.LastOutcome;
                    Assert.IsNotNull(atElimination, "LastOutcome is built at once on the human's elimination");
                    Assert.IsTrue(d.InResultsBeat, "the death beat runs");
                    Assert.AreEqual(GameState.Playing, d.State, "results wait for the death beat");
                }
                yield return null;
            }
            Assert.AreEqual(GameState.Results, d.State, "results shown");
            Assert.That(eliminatedAt, Is.GreaterThan(0f), "the human was eliminated");
            Assert.That(Time.realtimeSinceStartup - eliminatedAt, Is.GreaterThan(GameDirector.DeathBeatSeconds - 0.1f), "1.0 s death beat");
            Assert.AreEqual(new[] { GameState.Results }, states.ToArray(), "Playing -> Results once");

            HumanOutcome o = d.LastOutcome;
            Assert.AreSame(atElimination, o, "the outcome is never rebuilt later");
            Assert.AreEqual(EliminationCause.Spark, o.Cause);
            Assert.AreEqual(DemoScenario.SecondCutter, o.Attacker, "attacker from SparkCaught.Other");
            Assert.That(o.CaughtDistance, Is.GreaterThan(0.0), "SparkCaught.DistanceHome");
            Assert.AreEqual(4, o.Rank, "first eliminated of four");
            Assert.IsFalse(o.SharedRank);
            Assert.AreEqual(1, o.Captures, "one capturing return: the clean capture (the saved chase captures nothing, v1.4)");
            Assert.AreEqual(1, o.PocketsMade);
            Assert.IsTrue(o.HadSavedReturn, "the second exit ended in a saved chase");
            Assert.That(o.LastSavedMargin, Is.EqualTo(monitor.SavedReturnMargin).Within(1e-9));
            Assert.AreEqual(0, monitor.SavedReturnCells, "contract 24: the saved return captured nothing");
            Assert.That(o.AreaPercent, Is.GreaterThan(0.0), "FinalCells area");
            Assert.That(o.SurvivedSeconds, Is.EqualTo(demo.Sim.Players[DemoScenario.Human].EliminatedAt).Within(1e-9));
            Assert.IsFalse(demo.CountsForStats, "the demo never records stats");

            // The background match keeps playing behind the results. Batchmode frames can be much shorter than one tick,
            // so wait on real time (not on a frame count).
            long tick = demo.Sim.Tick;
            float t1 = Time.realtimeSinceStartup;
            while (demo.Sim.Tick <= tick && Time.realtimeSinceStartup - t1 < 2f) yield return null;
            Assert.That(demo.Sim.Tick, Is.GreaterThan(tick), "background match keeps playing");
            Assert.AreEqual(GameState.Results, d.State, "results stay up while the match plays on");

            monitor.Finish();
            Assert.IsTrue(monitor.Evaluate(out List<string> failures), string.Join("; ", failures) + "\n" + monitor.Report());

            d.ToMenu();
            yield return null;
            Assert.AreEqual(GameState.Menu, d.State);
            Assert.IsTrue(demo.IsClosed, "the replaced session is closed");
            AssertNoErrors("demo round");
        }

        [UnityTest]
        public IEnumerator Pause_ReadyGateAndSlowMo()
        {
            GameDirector d = Boot();
            yield return null;
            d.StartRound();
            GameSession s = d.Session;
            Assert.IsTrue(s.AwaitingStart, "a real round waits for the human");
            Assert.IsTrue(s.Runner.Paused);
            yield return new WaitForSecondsRealtime(0.25f);
            Assert.AreEqual(0L, s.Sim.Tick, "the whole sim waits at t = 0");
            Assert.IsTrue(s.AwaitingStart, "no auto-start before the delay");

            // The first steering input releases the gate.
            s.HumanController.Desired = Math.PI * 0.25;
            yield return null;
            Assert.IsFalse(s.AwaitingStart, "input released the gate");
            yield return WaitTicks(s, 5);

            // Pause freezes the sim.
            bool? lastPaused = null;
            d.PausedChanged += p => lastPaused = p;
            d.SetPaused(true);
            Assert.IsTrue(d.IsPaused);
            Assert.AreEqual(true, lastPaused);
            Assert.IsTrue(s.Runner.Paused);
            long frozen = s.Sim.Tick;
            yield return new WaitForSecondsRealtime(0.25f);
            Assert.AreEqual(frozen, s.Sim.Tick, "paused");

            // Leaving pause goes back through the ready gate: no input, so it auto-starts after 1.0 s.
            d.SetPaused(false);
            float unpausedAt = Time.realtimeSinceStartup;
            Assert.IsFalse(d.IsPaused);
            Assert.AreEqual(false, lastPaused);
            Assert.IsTrue(s.AwaitingStart, "back to the ready gate");
            Assert.IsNull(s.HumanController.Desired, "waits for a new input");
            yield return new WaitForSecondsRealtime(0.25f);
            Assert.AreEqual(frozen, s.Sim.Tick, "still waiting");
            Assert.IsTrue(s.AwaitingStart, "still waiting");
            while (s.AwaitingStart && Time.realtimeSinceStartup - unpausedAt < 3f) yield return null;
            Assert.IsFalse(s.AwaitingStart, "the gate auto-starts after a pause");
            Assert.That(Time.realtimeSinceStartup - unpausedAt, Is.GreaterThan(GameDirector.AutoStartDelay - 0.1f), "after 1.0 s");
            yield return WaitTicks(s, 3);

            // Slow motion: the scale applies at once and ramps back to 1.
            d.SlowMo(0.25f, 0.1f, 0.1f);
            Assert.AreEqual(0.25f, s.Runner.TimeScale, 1e-6f);
            yield return new WaitForSecondsRealtime(0.4f);
            yield return null;
            Assert.AreEqual(1f, s.Runner.TimeScale, 1e-6f, "back to normal speed");

            // Pausing is refused in the menu.
            d.ToMenu();
            yield return null;
            d.SetPaused(true);
            Assert.IsFalse(d.IsPaused, "no pause in attract");
            AssertNoErrors("pause");
        }

        [UnityTest]
        public IEnumerator Biome_SessionBiomeAppliesAndViewsRebindLive()
        {
            GameDirector d = Boot();
            yield return null;
            try
            {
                // A demo session forced to Fire: GameDirector makes it current when the session starts.
                GameSession demo = DemoScenario.CreateSession(out _, BiomeId.Fire);
                d.StartRound(demo);
                Assert.AreEqual(BiomeId.Fire, BiomeTheme.Current.Id, "GameSession.Biome applied at session start");
                for (int k = 0; k < 10; k++) yield return null;
                Assert.AreEqual(BiomeTheme.Get(BiomeId.Fire).PlayerColors[Palette.ColorIndexOf(0)], Palette.ColorOf(0), "Palette follows the biome");
                Camera main = MainCamera();
                Assert.IsNotNull(main);
                Assert.AreEqual((Color)BiomeTheme.Get(BiomeId.Fire).OutsideArena, main.backgroundColor, "clear color of the biome");
                AssertCompositeOf(BiomeTheme.Get(BiomeId.Fire));
                Assert.IsNotNull(Find<BiomeFxHost>(d), "BiomeFx built");
                Assert.IsInstanceOf<FireFx>(Find<BiomeFxHost>(d).Active, "the Fire effects component is hosted");

                // Live switch without a restart (what a menu card does): every view re-binds.
                BiomeTheme.SetCurrent(BiomeId.Electric);
                for (int k = 0; k < 5; k++) yield return null;
                Assert.AreSame(demo, d.Session, "no restart");
                Assert.AreEqual((Color)BiomeTheme.Get(BiomeId.Electric).OutsideArena, main.backgroundColor);
                AssertCompositeOf(BiomeTheme.Get(BiomeId.Electric));
                Assert.IsInstanceOf<ElectricFx>(Find<BiomeFxHost>(d).Active);
                AssertRenderers();

                BiomeTheme.SetCurrent(BiomeId.Liquid);
                for (int k = 0; k < 5; k++) yield return null;
                AssertCompositeOf(BiomeTheme.Get(BiomeId.Liquid));
                Assert.IsInstanceOf<LiquidFx>(Find<BiomeFxHost>(d).Active);
                AssertNoErrors("biome switches");
            }
            finally
            {
                BiomeTheme.SetCurrent(BiomeId.Liquid);
            }
        }

        private static void AssertCompositeOf(BiomeTheme theme)
        {
            string expected = BiomeTheme.HasShader(theme.CompositeShader) ? theme.CompositeShader : BiomeTheme.LiquidCompositeShader;
            bool found = false;
            foreach (Renderer r in SceneObjects<Renderer>())
            {
                if (!r.enabled || r.sharedMaterial == null || r.sharedMaterial.shader == null) continue;
                if (r.sharedMaterial.shader.name.EndsWith("/" + expected, StringComparison.Ordinal)) found = true;
            }
            Assert.IsTrue(found, theme.Id + ": a renderer draws the " + expected + " composite (fallback included)");
        }
        // ------------------------------------------------------------------------------------------------------------

        private static IEnumerator WaitTicks(GameSession s, int ticks)
        {
            long target = s.Sim.Tick + ticks;
            float t0 = Time.realtimeSinceStartup;
            while (s.Sim.Tick < target && Time.realtimeSinceStartup - t0 < 10f) yield return null;
            Assert.That(s.Sim.Tick, Is.GreaterThanOrEqualTo(target), "the sim advances");
        }

        private static T Find<T>(GameDirector d) where T : Component
        {
            foreach (Component c in d.Subsystems)
            {
                if (c is T t) return t;
            }
            return null;
        }

        private static Camera MainCamera()
        {
            foreach (Camera c in SceneObjects<Camera>())
            {
                if (c.enabled && c.orthographic && c.targetTexture == null && (c.cullingMask & (1 << LiquidLayers.Field)) == 0) return c;
            }
            return null;
        }

        private static bool IsStub(Component c)
        {
            return c != null && c.gameObject.name.Contains("(stub)");
        }

        private static IEnumerable<T> SceneObjects<T>() where T : Component
        {
            foreach (T c in Resources.FindObjectsOfTypeAll<T>())
            {
                if (c != null && c.gameObject.scene.IsValid() && c.gameObject.activeInHierarchy) yield return c;
            }
        }

        private static void AssertRenderers()
        {
            foreach (Renderer r in SceneObjects<Renderer>())
            {
                if (!r.enabled) continue;
                Material m = r.sharedMaterial;
                Assert.IsNotNull(m, r.name + " has no material");
                Assert.IsNotNull(m.shader, r.name + " material has no shader");
                Assert.IsTrue(m.shader.isSupported, r.name + " uses an unsupported shader " + m.shader.name);
                StringAssert.DoesNotContain("InternalErrorShader", m.shader.name, r.name);
            }
        }

        private static void AssertLiquidRendering()
        {
            Renderer surface = null;
            foreach (Renderer r in SceneObjects<Renderer>())
            {
                if (r.sharedMaterial != null && r.sharedMaterial.shader != null && r.sharedMaterial.shader.name.Contains("LiquidComposite")) surface = r;
            }
            Assert.IsNotNull(surface, "a LiquidSurface renderer uses the LiquidComposite shader");
            Assert.IsTrue(surface.sharedMaterial.shader.isSupported, "LiquidComposite is supported");
            var actorField = Shader.GetGlobalTexture("_PIO_ActorField") as RenderTexture;
            Assert.IsNotNull(actorField, "_PIO_ActorField is a RenderTexture");
            Assert.IsTrue(actorField.IsCreated(), "ActorField RT created");
        }

        private static void AssertVisibleTextsNonEmpty(string screen)
        {
            int visible = 0;
            foreach (MonoBehaviour b in SceneObjects<MonoBehaviour>())
            {
                if (!b.enabled || b.GetType().FullName != "UnityEngine.UI.Text") continue;
                if (!OnVisibleCanvas(b.transform)) continue;
                PropertyInfo prop = b.GetType().GetProperty("text");
                string text = prop != null ? prop.GetValue(b) as string : null;
                Assert.IsFalse(string.IsNullOrEmpty(text), screen + ": visible Text '" + b.name + "' is empty");
                visible++;
            }
            Assert.That(visible, Is.GreaterThan(0), screen + ": at least one visible text");
        }

        private static bool OnVisibleCanvas(Transform t)
        {
            bool hasCanvas = false;
            for (Transform x = t; x != null; x = x.parent)
            {
                var group = x.GetComponent<CanvasGroup>();
                if (group != null && group.alpha <= 0.001f) return false;
                var canvas = x.GetComponent<Canvas>();
                if (canvas != null)
                {
                    if (!canvas.enabled) return false;
                    hasCanvas = true;
                }
            }
            return hasCanvas;
        }
    }
}
