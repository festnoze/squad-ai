using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M7 (docs/CONTRACT_M7.md 1.4), on the real Boot scene: the Qualité option of the Options page, clicked from the
    /// pause menu, switches QualitySettings, the active URP asset, the render scale and the bloom at once (Bas, Moyen,
    /// Haut), and each tier survives a level restart (Step62a). Mirrors the harness of ProbeTestsM6Options.
    /// </summary>
    public sealed class ProbeTestsM7Quality
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private string tempDir;

        private Main main;
        private GameState Game => main.Game;
        private Menu Menu => main.Menu;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            tempDir = null;
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            // Also puts the quality back to the platform default (Haut in the editor) for the next test.
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Cursor.lockState = CursorLockMode.None;
            if (tempDir != null)
            {
                try
                {
                    Directory.Delete(tempDir, true);
                }
                catch (Exception)
                {
                    // A leftover temporary folder is harmless.
                }
            }
            yield return null;
        }

        private void OnLog(string condition, string stack, LogType type)
        {
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
            {
                exceptions++;
                logged.Add(condition);
            }
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>
        /// Plain frames until <paramref name="done"/>, at most <paramref name="frames"/> of them: the injected pause press
        /// is read in an Update, and a long frame (the render of BloomReaches) can run two fixed steps before any Update.
        /// </summary>
        private static IEnumerator Frames(Func<bool> done, int frames = 30)
        {
            for (int i = 0; i < frames && !done(); i++)
            {
                yield return null;
            }
        }

        private void AssertTier(string level, string asset, float scale, bool bloom, string when)
        {
            Assert.AreEqual(level, QualitySettings.names[QualitySettings.GetQualityLevel()], $"{when}: the quality level");
            Assert.IsNotNull(GraphicsSettings.currentRenderPipeline, $"{when}: no render pipeline asset is active");
            Assert.AreEqual(asset, GraphicsSettings.currentRenderPipeline.name, $"{when}: the active URP asset");
            Assert.AreEqual(scale, QualityTier.ActiveRenderScale, 1e-4f, $"{when}: the render scale");
            Assert.AreEqual(bloom, QualityTier.BloomReaches(main.Camera), $"{when}: the bloom the camera gets");
        }

        // ----- 62a: Bas, Moyen and Haut applied at once, and kept over a level restart -----

        [UnityTest]
        public IEnumerator Step62a_QualityTiersSwitchAtOnceAndSurviveRestart()
        {
            tempDir = Path.Combine(Path.GetTempPath(), "outofsight_quality_tests_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempDir);
            SaveStore.PathOverride = Path.Combine(tempDir, SaveStore.FileName);
            CollectionAssert.AreEqual(new[] { QualityTier.LevelLow, QualityTier.LevelMedium, QualityTier.LevelHigh }, QualitySettings.names,
                "premise: QualitySettings holds Bas, Moyen and Haut (run OutOfSight/Project Setup)");
            Assert.IsNull(SaveStore.Options.Quality, "premise: a fresh save holds no quality choice");
            AssertTier(QualityTier.LevelHigh, "PC_RPAsset", 1f, true, "the PC default");
            // The look's own checks (lighting's) on Haut, as they stand now: the same problems again once back on Haut.
            string lookBefore = string.Join(", ", main.LookProblems());

            InputReader.InjectPausePress();
            yield return Frames(() => Menu.PauseOpen);
            Assert.IsTrue(Menu.PauseOpen, "premise: the pause menu opened");
            Menu.OpenOptions();
            yield return null;
            Assert.IsTrue(Menu.OptionsOpen, "premise: Options opened from the pause menu");
            Assert.IsNotNull(Menu.OptionsQualityButton, "Options has no Qualité row");
            Text label = Menu.Labels.TryGetValue("OptionsQualityLabel", out Text t) ? t : null;
            Assert.IsNotNull(label, "the Qualité row has no label");
            Assert.AreEqual(string.Format(Strings.OptionsQuality, Strings.OptionsQualityHigh), label.text);

            var tiers = new[]
            {
                (SaveOptions.QualityLow, QualityTier.LevelLow, "Mobile_RPAsset", Tuning.QualityLowRenderScale, false, Strings.OptionsQualityLow),
                (SaveOptions.QualityMedium, QualityTier.LevelMedium, "Mobile_RPAsset", Tuning.QualityMediumRenderScale, true, Strings.OptionsQualityMedium),
                (SaveOptions.QualityHigh, QualityTier.LevelHigh, "PC_RPAsset", 1f, true, Strings.OptionsQualityHigh),
            };
            foreach (var (tier, level, asset, scale, bloom, name) in tiers)
            {
                // A click applies the tier at once: no frame passes before the checks.
                Menu.OptionsQualityButton.onClick.Invoke();
                Assert.AreEqual(tier, SaveStore.Options.Quality, $"the click did not choose {name}");
                Assert.AreEqual(string.Format(Strings.OptionsQuality, name), label.text, "the row does not show the tier");
                AssertTier(level, asset, scale, bloom, name + " at once");
                Assert.AreEqual(!bloom, QualityTier.BloomSuppressed, $"{name}: the bloom override volume");

                // A level restart keeps it.
                Menu.CloseOptions();
                InputReader.InjectPausePress();
                yield return Frames(() => !Menu.PauseOpen);
                Assert.IsFalse(Menu.PauseOpen, "premise: the game resumed");
                Game.Restart();
                yield return Steps(3);
                Assert.IsNotNull(Game.Level, "premise: the level was rebuilt");
                AssertTier(level, asset, scale, bloom, name + " after a restart");
                Assert.AreEqual(tier, SaveStore.Options.Quality, $"a restart changed the quality option ({name})");

                InputReader.InjectPausePress();
                yield return Frames(() => Menu.PauseOpen);
                Assert.IsTrue(Menu.PauseOpen, "premise: the pause menu opened again");
                Menu.OpenOptions();
                yield return null;
                Assert.IsTrue(Menu.OptionsOpen, "premise: Options opened again");
            }
            Assert.AreEqual(lookBefore, string.Join(", ", main.LookProblems()), "back on Haut, the look is not the PC look again");
            Menu.CloseOptions();
            InputReader.InjectPausePress();
            yield return Frames(() => !Menu.PauseOpen);
            Assert.AreEqual(0, exceptions, "unexpected log errors: " + string.Join(" | ", logged));
        }
    }
}
