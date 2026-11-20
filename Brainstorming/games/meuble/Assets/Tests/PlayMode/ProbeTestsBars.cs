using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Step 75 (HUD gauge redesign, 2026-11-19), on the real Boot scene under GameRules.M2: the creak and suspicion gauges
    /// are capsules with their icon on a badge at the left end, a label in the menus' display face, a threshold marker
    /// where the consequence starts (the creak warning, the discovery that would lose), a fill that eases toward the
    /// value; they fit a 20:9 phone, 16:9 and a 4:3 tablet beside the eye and clear of the touch controls. It writes the
    /// HUD at 0, 30, 70 and 100 percent, the creak warning and the touch layout to docs/m9/bars (the HUD canvas rendered
    /// through the camera, ProbeTestsEndPanel's way), each with a close-up of the bottom band.
    /// </summary>
    public sealed class ProbeTestsBars
    {
        private const string ShotDir = "docs/m9/bars";
        private static readonly Vector2Int[] Screens = { new Vector2Int(2400, 1080), new Vector2Int(1920, 1080), new Vector2Int(1440, 1080) };
        private const float EdgeMargin = 16f;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private float forcedCreak;
        private float forcedSuspicion;
        private bool forcedWarning;
        private bool forcing;
        private GameState Game => main.Game;
        private Hud Hud => main.Hud;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
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
            Assert.IsNotNull(Hud, "premise: Main built no HUD");
            Game.Rules = GameRules.M2;
            Game.FixedStepped += Force;
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            if (main != null && main.Game != null)
            {
                main.Game.FixedStepped -= Force;
            }
            InputReader.ForceTouchUI = false;
            InputReader.ResetInjections();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
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

        /// <summary>After every step (GameState has just set the HUD), the gauge values under test replace the game's.</summary>
        private void Force()
        {
            if (forcing)
            {
                Hud.SetCreak(forcedCreak, forcedWarning);
                Hud.SetSuspicion(forcedSuspicion);
            }
        }

        private void SetLevels(float creak, float suspicion, bool warning)
        {
            forcing = true;
            forcedCreak = creak;
            forcedSuspicion = suspicion;
            forcedWarning = warning;
            Hud.SetCreak(creak, warning);
            Hud.SetSuspicion(suspicion);
            Hud.SnapGauges();
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private RectTransform Part(string name)
        {
            var rect = Hud.transform.Find(name) as RectTransform;
            Assert.IsNotNull(rect, $"premise: the HUD has no {name}");
            return rect;
        }

        [UnityTest]
        public IEnumerator Step75a_GaugesAreCapsulesThatReadOnEveryScreen()
        {
            Strings.SetLanguage(Strings.French);
            Assert.IsTrue(Hud.CreakGaugeVisible && Hud.SuspicionGaugeVisible, "premise: the gauges do not show");

            // The markers: the creak warning's start at the difficulty's fill time, the discovery that would lose.
            Assert.AreEqual(Game.Creak.WarningStart, Hud.CreakThreshold, 1e-4f, "the creak marker is not where the warning starts");
            float step = Tuning.SuspicionPerDiscovery * Game.Difficulty.SuspicionFactor;
            Assert.AreEqual(Tuning.SuspicionLose - step, Hud.SuspicionThreshold, 1e-4f, "the suspicion marker is not one discovery from the loss");
            Assert.IsTrue(Hud.Labels.TryGetValue("CreakLabel", out Text creakLabel) && creakLabel.text == Strings.HudCreak, "the creak gauge lost hud.creak");
            Assert.IsTrue(Hud.Labels.TryGetValue("SuspicionLabel", out Text suspicionLabel) && suspicionLabel.text == Strings.HudSuspicion,
                "the suspicion gauge lost hud.suspicion");
            Assert.AreEqual(Hud.DisplayFont, creakLabel.font, "the gauge label is not in the menus' display face");

            // The drawn fill eases toward the value: a discovery's jump is not drawn at once, and is within a second.
            SetLevels(0f, 0f, false);
            yield return null;
            SetLevelsNoSnap(0f, 0.34f);
            yield return null;
            Assert.Less(Hud.SuspicionFillDrawn, 0.335f, "the suspicion fill jumped instead of easing");
            Assert.AreEqual(0.34f, Hud.SuspicionShown, 1e-5f, "SuspicionShown is not the exact value");
            yield return new WaitForSecondsRealtime(1f);
            Assert.AreEqual(0.34f, Hud.SuspicionFillDrawn, 0.01f, "the suspicion fill did not reach the value within a second");

            foreach (float level in new[] { 0f, 0.3f, 0.7f, 1f })
            {
                SetLevels(level, level, false);
                yield return null;
                Assert.AreEqual(level, Hud.CreakFillDrawn, 1e-3f, "SnapGauges did not draw the creak value");
                Assert.AreEqual(level, Hud.SuspicionFillDrawn, 1e-3f, "SnapGauges did not draw the suspicion value");
                foreach (Vector2Int screen in Screens)
                {
                    yield return Shoot($"bars_{Mathf.RoundToInt(level * 100f):000}_{screen.x}x{screen.y}.png", screen.x, screen.y, false);
                }
            }
            // The creak warning (the flash) and the English labels.
            SetLevels(0.92f, 0.5f, true);
            yield return Shoot("bars_warning_1920x1080.png", 1920, 1080, false);
            Strings.SetLanguage(Strings.English);
            SetLevels(0.55f, 0.8f, false);
            yield return Shoot("bars_en_2400x1080.png", 2400, 1080, false);
            Strings.SetLanguage(Strings.French);

            // The touch layout: the gauges clear of the stick, the action button and the careful toggle.
            InputReader.ForceTouchUI = true;
            yield return null;
            yield return null;
            Assert.IsTrue(TouchControls.Instance != null && TouchControls.Instance.Visible, "premise: the touch overlay does not show");
            SetLevels(0.7f, 0.7f, false);
            foreach (Vector2Int screen in Screens)
            {
                yield return Shoot($"bars_touch_{screen.x}x{screen.y}.png", screen.x, screen.y, true);
            }
            InputReader.ForceTouchUI = false;
            forcing = false;
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        private void SetLevelsNoSnap(float creak, float suspicion)
        {
            forcing = true;
            forcedCreak = creak;
            forcedSuspicion = suspicion;
            forcedWarning = false;
            Hud.SetCreak(creak, false);
            Hud.SetSuspicion(suspicion);
        }

        private static Rect LocalRect(RectTransform root, RectTransform rect)
        {
            var corners = new Vector3[4];
            rect.GetWorldCorners(corners);
            Vector3 min = root.InverseTransformPoint(corners[0]);
            Vector3 max = root.InverseTransformPoint(corners[2]);
            return Rect.MinMaxRect(min.x, min.y, max.x, max.y);
        }

        private static Rect ScreenRect(Camera cam, RectTransform rect)
        {
            var corners = new Vector3[4];
            rect.GetWorldCorners(corners);
            Vector2 a = RectTransformUtility.WorldToScreenPoint(cam, corners[0]);
            Vector2 b = RectTransformUtility.WorldToScreenPoint(cam, corners[2]);
            return Rect.MinMaxRect(Mathf.Min(a.x, b.x), Mathf.Min(a.y, b.y), Mathf.Max(a.x, b.x), Mathf.Max(a.y, b.y));
        }

        /// <summary>The gap (screen pixels, negative when they overlap) between the round touch control <paramref name="disc"/> and <paramref name="rect"/>.</summary>
        private static float DiscGap(Rect disc, Rect rect)
        {
            Vector2 c = disc.center;
            float r = disc.width * 0.5f;
            var nearest = new Vector2(Mathf.Clamp(c.x, rect.xMin, rect.xMax), Mathf.Clamp(c.y, rect.yMin, rect.yMax));
            return (c - nearest).magnitude - r;
        }

        /// <summary>
        /// Lays the HUD out for a <paramref name="width"/> x <paramref name="height"/> screen (the root canvas, and with
        /// <paramref name="touch"/> the touch overlay, switched to Screen Space Camera on the game camera rendering into a
        /// texture of that size), checks the gauges' layout, writes the PNG and a close-up of the bottom band under
        /// <see cref="ShotDir"/>, then puts everything back.
        /// </summary>
        private IEnumerator Shoot(string file, int width, int height, bool touch)
        {
            Camera cam = main.Camera;
            Canvas root = Hud.GetComponent<Canvas>();
            Canvas overlay = touch ? TouchControls.Instance.ActionButton.GetComponentInParent<Canvas>().rootCanvas : null;
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
            RenderTexture previousTarget = cam.targetTexture;
            float previousPlane = root.planeDistance;
            cam.targetTexture = rt;
            cam.aspect = width / (float)height;
            root.renderMode = RenderMode.ScreenSpaceCamera;
            root.worldCamera = cam;
            root.planeDistance = cam.nearClipPlane + 0.02f;
            if (overlay != null)
            {
                overlay.renderMode = RenderMode.ScreenSpaceCamera;
                overlay.worldCamera = cam;
                overlay.planeDistance = cam.nearClipPlane + 0.01f;
            }
            try
            {
                yield return null;
                yield return null;
                yield return new WaitForSecondsRealtime(0.15f);
                Canvas.ForceUpdateCanvases();
                var rootRect = (RectTransform)root.transform;
                Rect canvas = rootRect.rect;
                Assert.AreEqual(width / (float)height, canvas.width / canvas.height, 0.01f, $"premise: the canvas did not take the {width} x {height} shape");
                Rect creak = LocalRect(rootRect, Part("CreakGauge"));
                Rect suspicion = LocalRect(rootRect, Part("SuspicionGauge"));
                Rect eye = LocalRect(rootRect, Part("EyeBackdrop"));
                Rect controls = LocalRect(rootRect, Hud.Labels["Controls"].rectTransform);
                TestContext.WriteLine($"[Step75a] {file}: canvas {canvas.width:0} x {canvas.height:0}, creak {creak}, suspicion {suspicion}, eye {eye}");
                foreach (Rect gauge in new[] { creak, suspicion })
                {
                    Assert.GreaterOrEqual(gauge.xMin, canvas.xMin + EdgeMargin, $"a gauge {gauge} is cut on the left at {width} x {height}");
                    Assert.LessOrEqual(gauge.xMax, canvas.xMax - EdgeMargin, $"a gauge {gauge} is cut on the right at {width} x {height}");
                    Assert.GreaterOrEqual(gauge.yMin, canvas.yMin + EdgeMargin, $"a gauge {gauge} is cut at the bottom at {width} x {height}");
                    Assert.IsFalse(gauge.Overlaps(eye), $"a gauge {gauge} covers the eye {eye} at {width} x {height}");
                    Assert.Greater(gauge.yMin, controls.yMin + 40f, $"a gauge {gauge} sits on the controls line at {width} x {height}");
                }
                Assert.Less(creak.xMax, eye.xMin, "the creak gauge is not left of the eye");
                Assert.Greater(suspicion.xMin, eye.xMax, "the suspicion gauge is not right of the eye");
                foreach (string name in new[] { "CreakLabel", "SuspicionLabel" })
                {
                    Text label = Hud.Labels[name];
                    Assert.LessOrEqual(label.preferredWidth, label.rectTransform.rect.width, $"\"{label.text}\" overflows its gauge at {width} x {height}");
                }
                if (overlay != null)
                {
                    Transform touchRoot = TouchControls.Instance.ActionButton.parent;
                    var discs = new[] { TouchControls.Instance.ActionButton, TouchControls.Instance.CarefulButton, touchRoot.Find("StickBase") as RectTransform };
                    foreach (RectTransform gauge in new[] { Part("CreakGauge"), Part("SuspicionGauge") })
                    {
                        Rect g = ScreenRect(cam, gauge);
                        foreach (RectTransform disc in discs)
                        {
                            Assert.IsNotNull(disc, "premise: a touch control is missing");
                            float gap = DiscGap(ScreenRect(cam, disc), g);
                            TestContext.WriteLine($"  {gauge.name} to {disc.name}: {gap:0} px");
                            Assert.Greater(gap, 0f, $"{gauge.name} is under the touch control {disc.name} at {width} x {height}");
                        }
                    }
                }

                cam.ResetProjectionMatrix();
                var request = new RenderPipeline.StandardRequest { destination = rt };
                Assert.IsTrue(RenderPipeline.SupportsRenderRequest(cam, request), "premise: the pipeline cannot render the camera to a texture");
                RenderPipeline.SubmitRenderRequest(cam, request);
                RenderTexture previous = RenderTexture.active;
                RenderTexture.active = rt;
                var texture = new Texture2D(width, height, TextureFormat.RGB24, false);
                texture.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                texture.Apply();
                RenderTexture.active = previous;
                Directory.CreateDirectory(ShotDir);
                File.WriteAllBytes(Path.Combine(ShotDir, file), texture.EncodeToPNG());
                // The close-up: the bottom band, the gauges and the eye at the screen's own pixels.
                int cropW = Mathf.Min(width, Mathf.RoundToInt(height * 1.1f));
                int cropH = Mathf.RoundToInt(height * 0.24f);
                var crop = new Texture2D(cropW, cropH, TextureFormat.RGB24, false);
                crop.SetPixels(texture.GetPixels((width - cropW) / 2, 0, cropW, cropH));
                crop.Apply();
                File.WriteAllBytes(Path.Combine(ShotDir, "band_" + file), crop.EncodeToPNG());
                UnityEngine.Object.Destroy(crop);
                UnityEngine.Object.Destroy(texture);
            }
            finally
            {
                root.renderMode = RenderMode.ScreenSpaceOverlay;
                root.worldCamera = null;
                root.planeDistance = previousPlane;
                if (overlay != null)
                {
                    overlay.renderMode = RenderMode.ScreenSpaceOverlay;
                    overlay.worldCamera = null;
                }
                cam.targetTexture = previousTarget;
                cam.ResetAspect();
                rt.Release();
                UnityEngine.Object.Destroy(rt);
            }
            yield return null;
            Canvas.ForceUpdateCanvases();
        }
    }
}
