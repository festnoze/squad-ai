using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// LEVELNUM round 2 (docs/next/progress/LEVELNUM.md), on the real Boot scene with the start hold on (the player's
    /// case): the held intro card lays a greyish-black dim (0.6 since LEVELNUM2) over the scene, under every HUD text,
    /// with the level select's number (level1 is 1, level22 is 19, level19 is 18 since levels.json rev 3) as holes in it (nearly clear
    /// glass inside, digits from the baked Inter distance field). The number starts at startZoom (12.4) times its settled
    /// size and zooms out over zoomSeconds (2 s, expo ease-out) to settledHeight (half the screen height), centred, inside
    /// the screen's width on a 20:9 phone and a 16:9 PC screen. The zoom freezes while paused, a restart replays it,
    /// reduced motion shows the final state at once, and the first input takes the dim, the holes and the card away
    /// together in a short fade. It writes the zoom at t = 0, 0.15, 0.3, 0.6, 1.0 s and the final state to
    /// Build/shots/levelnum (the HUD canvas rendered through the camera, ProbeTestsBars' way), on level1 and on level22 (a
    /// two-digit card; the night level20 left the line-up in rev 3, ACT3A). The built player's own shots come from "-autoShot" (Menu.AutoShot).
    /// </summary>
    public sealed class ProbeTestsLevelNum
    {
        private const string ShotDir = "Build/shots/levelnum";
        private static readonly Vector2Int[] Screens = { new Vector2Int(2400, 1080), new Vector2Int(1920, 1080) };
        private static readonly float[] Ages = { 0f, 0.15f, 0.3f, 0.6f, 1f };
        private const float EdgeMargin = 16f;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;
        private Hud Hud => main.Hud;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            GameState.HoldStart = false;
            GamePause.IsPaused = false;
            Hud.ReducedMotion = false;
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            InputReader.ResetInjections();
            InputReader.InjectLastDevice(false);
            SaveStore.ResetForTests();
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
            Assert.IsNotNull(Hud, "premise: Main has no HUD");
            GamePause.IsPaused = false;
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            InputReader.InjectLastDevice(false);
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            GameState.HoldStart = false;
            Hud.ReducedMotion = false;
            Hud.ShotStep = 0f;
            CardNumberSettings.PathOverride = null;
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

        /// <summary>
        /// LevelNum03 (round 3): card_number.json. The shipped file parses with no problem and carries the built-in values;
        /// bad JSON, missing keys and wrong types fall back to the defaults, out-of-range values are clamped, each with a
        /// problem line; an edited file shows at the next restart (R) with no relaunch, and a missing file gives the defaults.
        /// </summary>
        [UnityTest]
        [Timeout(120000)]
        public IEnumerator LevelNum03_SettingsFileIsReadAtEveryCardWithSafeFallbacks()
        {
            var problems = new List<string>();
            string shipped = Path.Combine(Application.streamingAssetsPath, CardNumberSettings.FileName);
            Assert.IsTrue(File.Exists(shipped), "no card_number.json in StreamingAssets");
            CardNumberSettings s = CardNumberSettings.Parse(File.ReadAllText(shipped), problems);
            CollectionAssert.IsEmpty(problems, "the shipped file has problems");
            CardNumberSettings d = CardNumberSettings.Defaults;
            Assert.AreEqual(d.DimOpacity, s.DimOpacity, 1e-6f, "dimOpacity differs from the built-in default");
            Assert.AreEqual(d.WashOpacity, s.WashOpacity, 1e-6f, "washOpacity differs from the built-in default");
            Assert.AreEqual(d.StartZoom, s.StartZoom, 1e-6f, "startZoom differs from the built-in default");
            Assert.AreEqual(d.ZoomSeconds, s.ZoomSeconds, 1e-6f, "zoomSeconds differs from the built-in default");
            Assert.AreEqual(d.SettledHeight, s.SettledHeight, 1e-6f, "settledHeight differs from the built-in default");
            Assert.AreEqual(d.FadeSeconds, s.FadeSeconds, 1e-6f, "fadeSeconds differs from the built-in default");
            Assert.AreEqual(d.DimColor, s.DimColor, "dimColor differs from the built-in default");
            Assert.AreEqual(d.WashColor, s.WashColor, "washColor differs from the built-in default");
            // LEVELNUM2 keys.
            Assert.AreEqual(d.Font, s.Font, "font differs from the built-in default");
            Assert.AreEqual(d.Easing, s.Easing, "easing differs from the built-in default");
            Assert.AreEqual(d.FadeInSeconds, s.FadeInSeconds, 1e-6f, "fadeInSeconds differs from the built-in default");
            Assert.AreEqual(d.EdgeOpacity, s.EdgeOpacity, 1e-6f, "edgeOpacity differs from the built-in default");
            Assert.AreEqual(d.EdgeWidth, s.EdgeWidth, 1e-6f, "edgeWidth differs from the built-in default");
            Assert.AreEqual(d.EdgeColor, s.EdgeColor, "edgeColor differs from the built-in default");
            Assert.AreEqual(d.InnerShadeOpacity, s.InnerShadeOpacity, 1e-6f, "innerShadeOpacity differs from the built-in default");
            Assert.AreEqual(d.InnerShadeWidth, s.InnerShadeWidth, 1e-6f, "innerShadeWidth differs from the built-in default");
            Assert.That(d.WashOpacity, Is.InRange(0.03f, 0.07f), "the wash is not nearly clear (about 0.04)");
            Assert.That(d.DimOpacity, Is.InRange(0.55f, 0.65f), "the dim is not about 0.6");
            Assert.AreEqual(0.5f, d.SettledHeight, 1e-6f, "the settled height is not half the screen");
            Assert.AreEqual(6.2f, d.StartZoom * d.SettledHeight, 0.05f, "the start size is not about 6.2 screen heights");
            Assert.That(d.EdgeOpacity, Is.InRange(0.05f, 0.5f), "the hairline edge is not subtle");
            foreach (string face in LevelDigitFont.Names)
            {
                LevelDigitFont f = LevelDigitFont.Get(face);
                Assert.IsNotNull(f, $"the digit face {face} is not in Resources/LevelDigits");
                Assert.IsNotNull(f.Atlas, $"the digit face {face} has no atlas");
                for (char c = '0'; c <= '9'; c++)
                {
                    Assert.IsTrue(f.TryGetGlyph(c, out _), $"the digit face {face} has no '{c}'");
                }
            }
            Assert.AreEqual(0f, CardNumber.Ease("expo", 0f), 1e-6f, "expo does not start at 0");
            Assert.AreEqual(1f, CardNumber.Ease("expo", 1f), 1e-6f, "expo does not land exactly on 1");
            foreach (string e in CardNumber.Easings)
            {
                float previous = 0f;
                for (int i = 1; i <= 50; i++)
                {
                    float v = CardNumber.Ease(e, i / 50f);
                    Assert.GreaterOrEqual(v, previous - 1e-6f, $"{e} goes back");
                    Assert.LessOrEqual(v, 1f + 1e-6f, $"{e} overshoots");
                    previous = v;
                }
            }

            problems.Clear();
            s = CardNumberSettings.Parse("{ not json", problems);
            Assert.AreEqual(1, problems.Count, "bad JSON gave no problem line");
            Assert.AreEqual(d.DimOpacity, s.DimOpacity, 1e-6f, "bad JSON did not give the defaults");

            problems.Clear();
            s = CardNumberSettings.Parse("{ \"font\": \"Comic\", \"easing\": 3, \"edgeWidth\": 99, \"edgeOpacity\": 0.5 }", problems);
            Assert.AreEqual(d.Font, s.Font, "an unknown font did not fall back");
            Assert.AreEqual(d.Easing, s.Easing, "a number as easing did not fall back");
            Assert.AreEqual(8f, s.EdgeWidth, 1e-6f, "edgeWidth was not clamped to 8");
            Assert.AreEqual(0.5f, s.EdgeOpacity, 1e-6f, "edgeOpacity was not read");
            Assert.IsTrue(problems.Exists(p => p.StartsWith("font")), "an unknown font gave no problem line");
            Assert.IsTrue(problems.Exists(p => p.StartsWith("easing")), "a bad easing gave no problem line");

            problems.Clear();
            s = CardNumberSettings.Parse("{ \"washOpacity\": 0.45, \"dimOpacity\": \"dark\", \"startZoom\": 99, "
                + "\"zoomSeconds\": -1, \"dimColor\": [2, 0.5, -1], \"washColor\": [1, 1] }", problems);
            Assert.AreEqual(0.45f, s.WashOpacity, 1e-6f, "washOpacity was not read");
            Assert.AreEqual(d.DimOpacity, s.DimOpacity, 1e-6f, "a text dimOpacity did not fall back");
            Assert.AreEqual(30f, s.StartZoom, 1e-6f, "startZoom was not clamped to 30");
            Assert.AreEqual(0f, s.ZoomSeconds, 1e-6f, "zoomSeconds was not clamped to 0");
            Assert.AreEqual(new Color(1f, 0.5f, 0f, 1f), s.DimColor, "dimColor was not clamped per channel");
            Assert.AreEqual(d.WashColor, s.WashColor, "a two-channel washColor did not fall back");
            Assert.AreEqual(d.SettledHeight, s.SettledHeight, 1e-6f, "a missing settledHeight did not fall back");
            TestContext.WriteLine("[LevelNum03] " + string.Join(" | ", problems));
            Assert.GreaterOrEqual(problems.Count, 8, "a fallback or a clamp gave no problem line");

            // An edited file shows at the next restart, with no relaunch; a deleted one gives the defaults.
            GameState.HoldStart = true;
            Game.LoadLevel("level1");
            Assert.AreEqual(d.WashOpacity, Hud.CardSettings.WashOpacity, 1e-6f, "premise: the shipped values are not in use");
            string temp = Path.Combine(Application.temporaryCachePath, "card_number_test.json");
            File.WriteAllText(temp, "{ \"dimOpacity\": 0.8, \"washOpacity\": 0.25, \"startZoom\": 4, \"zoomSeconds\": 0.8, "
                + "\"settledHeight\": 0.4, \"fadeSeconds\": 1.2, \"dimColor\": [0.1, 0.1, 0.1], \"washColor\": [1, 1, 1], "
                + "\"font\": \"bebas\", \"easing\": \"linear\" }");
            CardNumberSettings.PathOverride = temp;
            Game.Restart();
            Assert.AreEqual(0.25f, Hud.CardSettings.WashOpacity, 1e-6f, "the restart did not read the edited file");
            Assert.AreEqual(0.8f, Hud.CardDimAlpha, 1e-6f, "the dim does not follow the file");
            Assert.AreEqual("bebas", Hud.LevelNumberFont, "the face does not follow the file");
            Assert.AreEqual("linear", Hud.CardSettings.Easing, "the easing does not follow the file");
            Assert.AreEqual(0.8f, Hud.NumberZoomSeconds, 1e-6f, "the zoom length does not follow the file");
            Assert.AreEqual(1.2f, Hud.HeldCardFadeSeconds, 1e-6f, "the fade does not follow the file");
            Hud.ShotStep = 1e-6f;
            yield return Frames(2);
            Assert.AreEqual(4f * Hud.LevelNumberFinalScale, Hud.LevelNumberScale, 1e-3f, "the zoom does not start at the file's startZoom");
            Rect canvas = ((RectTransform)Hud.transform).rect;
            Hud.LevelNumberAge = 5f;
            Assert.AreEqual(canvas.height * 0.4f, Hud.LevelNumberInkRect.height, 1f, "the settled height does not follow the file");
            Hud.ShotStep = 0f;
            File.Delete(temp);
            Game.Restart();
            Assert.AreEqual(d.WashOpacity, Hud.CardSettings.WashOpacity, 1e-6f, "a missing file did not give the defaults");
            Assert.AreEqual(d.Font, Hud.LevelNumberFont, "a missing file did not give the default face");
            yield return Frames(2);
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }

        private static IEnumerator Frames(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return null;
            }
        }

        /// <summary>LevelNum01: the number, the dim, the holes, the zoom and the layout on level1 and level22, with the shots.</summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator LevelNum01_NumberHolesInTheDimZoomAndFit()
        {
            Assert.AreEqual(18, LevelSelect.DisplayNumber(Game.LevelOrder, "level19"), "level19 is not shown as the level select's 18 (rev 3)");
            Assert.AreEqual(17, LevelSelect.DisplayNumber(Game.LevelOrder, "level25"), "level25 (act 3 opener) is not shown as the level select's 17");
            Assert.AreEqual(0, LevelSelect.DisplayNumber(Game.LevelOrder, "level20"), "the parked level20 got a number");
            Assert.AreEqual(0, LevelSelect.DisplayNumber(Game.LevelOrder, "test_v2_litzone"), "a level outside levels.json got a number");
            Assert.IsTrue(Hud.LevelNumberHolesReady, $"the dim has no holes: {CardNumber.DimShaderName} or {CardNumber.MaskShaderName} is missing");
            Assert.Less(Hud.transform.Find("CardBackdrop").GetSiblingIndex(), Hud.transform.Find("TitleCard").GetSiblingIndex(),
                "the dim is not under the card's text");
            Directory.CreateDirectory(ShotDir);
            foreach (string id in new[] { "level1", "level22" })
            {
                int expected = LevelSelect.DisplayNumber(Game.LevelOrder, id);
                Assert.Greater(expected, 0, $"premise: {id} is not in levels.json");
                GameState.HoldStart = true;
                Game.LoadLevel(id);
                Assert.IsFalse(Game.Started, "premise: the build with the hold on did not hold");
                yield return Frames(2);
                Assert.IsTrue(Hud.CardHeld, $"{id}: the card is not held");
                Assert.AreEqual(expected, Hud.LevelNumberShown, $"{id}: the card does not show the level select's number");
                Assert.AreEqual(1f, Hud.CardBackdropAlpha, 1e-4f, $"{id}: the backdrop does not follow the held card");
                Assert.That(Hud.CardDimShown, Is.InRange(0.5f, 0.7f), $"{id}: the dim is not about 0.6");
                Assert.AreEqual(Hud.CardSettings.Font, Hud.LevelNumberFont, $"{id}: the digit face was not loaded");

                foreach (Vector2Int screen in Screens)
                {
                    foreach (float age in Ages)
                    {
                        yield return Shoot($"{id}_{screen.x}x{screen.y}_t{Mathf.RoundToInt(age * 100f):000}.png", screen.x, screen.y, age);
                    }
                    yield return Shoot($"{id}_{screen.x}x{screen.y}_final.png", screen.x, screen.y, 5f);
                }
            }
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// LevelNum02: pause freezes the zoom, a restart replays it, reduced motion shows the final state at once, and the
        /// first input takes the dim, the number and the card away together within a short fade.
        /// </summary>
        [UnityTest]
        [Timeout(120000)]
        public IEnumerator LevelNum02_PauseRestartReducedMotionAndRelease()
        {
            GameState.HoldStart = true;
            Game.LoadLevel("level1");
            Assert.AreEqual(0f, Hud.LevelNumberAge, 1e-6f, "the zoom did not start with the card");
            yield return Frames(2);

            // Paused, the zoom stands still; it goes on after the resume.
            Hud.LevelNumberAge = 0.1f;
            Game.Paused = true;
            float t0 = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - t0 < 0.3f)
            {
                yield return null;
            }
            Assert.AreEqual(0.1f, Hud.LevelNumberAge, 1e-6f, "the zoom ran while paused");
            Game.Paused = false;
            t0 = Time.realtimeSinceStartup;
            while (Time.realtimeSinceStartup - t0 < Hud.NumberZoomSeconds + 0.6f)
            {
                yield return null;
            }
            Assert.Greater(Hud.LevelNumberAge, Hud.NumberZoomSeconds, "the zoom did not finish after the resume");
            Assert.AreEqual(Hud.LevelNumberFinalScale, Hud.LevelNumberScale, 1e-4f, "the number did not settle at its final size");

            // A restart replays the zoom from the top: the number fills the screen height again.
            Game.Restart();
            Assert.AreEqual(0f, Hud.LevelNumberAge, 1e-6f, "a restart did not replay the zoom");
            Hud.ShotStep = 1e-6f;
            yield return Frames(2);
            Assert.IsTrue(Hud.CardHeld, "a restart did not hold the card again");
            Rect canvas = ((RectTransform)Hud.transform).rect;
            Assert.Greater(Hud.LevelNumberInkRect.height, canvas.height * 5f, "the restarted zoom does not start extremely zoomed");
            Hud.ShotStep = 0f;

            // Reduced motion: no zoom, the final state at once.
            Hud.ReducedMotion = true;
            Game.Restart();
            yield return Frames(1);
            Assert.AreEqual(Hud.LevelNumberFinalScale, Hud.LevelNumberScale, 1e-4f, "reduced motion still zooms");
            Hud.ReducedMotion = false;

            // The first input: the card, the dim and the number go together, within the short fade.
            InputReader.InjectMoveVector(Vector2.up);
            int guard = 0;
            while (!Game.Started && guard++ < 20)
            {
                yield return new WaitForFixedUpdate();
            }
            InputReader.ClearMoveVector();
            Assert.IsTrue(Game.Started, "the move input did not start the level");
            yield return null;
            float released = Time.realtimeSinceStartup;
            bool partial = false;
            while (Time.realtimeSinceStartup - released < Hud.HeldCardFadeSeconds + 0.25f)
            {
                Assert.AreEqual(Hud.TitleCardAlpha, Hud.CardBackdropAlpha, 1e-5f, "the backdrop and the card did not fade together");
                partial |= Hud.TitleCardAlpha > 0.01f && Hud.TitleCardAlpha < 0.99f;
                yield return null;
            }
            Assert.IsTrue(partial, "the card did not fade (no frame between shown and gone)");
            Assert.AreEqual(0f, Hud.TitleCardAlpha, 1e-4f, "the card outlived its short fade");
            Assert.AreEqual(0f, Hud.CardDimShown, 1e-4f, "the dim outlived the card");
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Lays the HUD out for a <paramref name="width"/> x <paramref name="height"/> screen (the root canvas switched to
        /// Screen Space Camera on the game camera rendering into a texture of that size), poses the number at
        /// <paramref name="age"/> seconds of its zoom with the HUD clock held still, checks the layout, writes the PNG, then
        /// puts everything back.
        /// </summary>
        private IEnumerator Shoot(string file, int width, int height, float age)
        {
            Camera cam = main.Camera;
            Canvas root = Hud.GetComponent<Canvas>();
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
            RenderTexture previousTarget = cam.targetTexture;
            float previousPlane = root.planeDistance;
            cam.targetTexture = rt;
            cam.aspect = width / (float)height;
            root.renderMode = RenderMode.ScreenSpaceCamera;
            root.worldCamera = cam;
            root.planeDistance = cam.nearClipPlane + 0.02f;
            Hud.ShotStep = 1e-6f;
            try
            {
                yield return null;
                yield return null;
                Hud.LevelNumberAge = age;
                yield return null;
                Canvas.ForceUpdateCanvases();
                var rootRect = (RectTransform)root.transform;
                Rect canvas = rootRect.rect;
                Assert.AreEqual(width / (float)height, canvas.width / canvas.height, 0.01f, $"premise: the canvas did not take the {width} x {height} shape");
                Assert.IsTrue(Hud.CardHeld, $"{file}: the card is not held");
                Rect ink = Hud.LevelNumberInkRect;
                TestContext.WriteLine($"[LevelNum] {file}: canvas {canvas.width:0} x {canvas.height:0}, ink {ink}, scale {Hud.LevelNumberScale:0.000}");
                if (age <= 0f)
                {
                    Assert.AreEqual(Hud.CardSettings.StartZoom * Hud.LevelNumberFinalScale, Hud.LevelNumberScale, 1e-3f, $"{file}: the zoom does not start at startZoom times");
                    Assert.Greater(ink.height, canvas.height * 5f, $"{file}: the number does not start extremely zoomed");
                }
                if (age >= Hud.NumberZoomSeconds)
                {
                    Assert.AreEqual(Hud.LevelNumberFinalScale, Hud.LevelNumberScale, 1e-4f, $"{file}: the number did not settle");
                    Assert.AreEqual(canvas.height * Hud.CardSettings.SettledHeight, ink.height, 1f, $"{file}: the settled number is not settledHeight tall");
                    Assert.Greater(ink.height, canvas.height * 0.4f, $"{file}: the settled number is small");
                    Assert.LessOrEqual(ink.yMax, canvas.yMax, $"{file}: the settled number is cut at the top");
                    Assert.GreaterOrEqual(ink.xMin, canvas.xMin + EdgeMargin, $"{file}: the number is cut on the left");
                    Assert.LessOrEqual(ink.xMax, canvas.xMax - EdgeMargin, $"{file}: the number is cut on the right");
                    Assert.AreEqual(0f, ink.center.x, 1f, $"{file}: the number is not centred");
                    Assert.AreEqual(0f, ink.center.y, 1f, $"{file}: the number is not centred");
                    // The holes exist: the mask is fully covered somewhere, over a share that fits a big number.
                    float share = Hud.LevelNumberCoveredShare(out float highest);
                    TestContext.WriteLine($"  holes: {share:P1} of the screen, highest coverage {highest:0.00}");
                    Assert.Greater(highest, 0.9f, $"{file}: the mask has no solid hole");
                    Assert.That(share, Is.InRange(0.01f, 0.6f), $"{file}: the holes cover {share:P1} of the screen");
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
                File.WriteAllBytes(Path.Combine(ShotDir, file), texture.EncodeToPNG());
                Object.Destroy(texture);
            }
            finally
            {
                Hud.ShotStep = 0f;
                root.renderMode = RenderMode.ScreenSpaceOverlay;
                root.worldCamera = null;
                root.planeDistance = previousPlane;
                cam.targetTexture = previousTarget;
                cam.ResetAspect();
                rt.Release();
                Object.Destroy(rt);
            }
            yield return null;
            Canvas.ForceUpdateCanvases();
        }
    }
}
