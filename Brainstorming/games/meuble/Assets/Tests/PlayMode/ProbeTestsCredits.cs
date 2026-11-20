using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Step 72 (Credits page, 2026-11-19), on the real Boot scene: "Crédits" on the title between Options and Quitter, the
    /// page it opens (a page of the title: the game stays paused), its lines (Core.Credits) in both languages, its scroll
    /// by injected D-pad, by a real UI move event and to both ends, Retour and Back, and its fit on a 20:9 phone. It writes
    /// the page's screenshots to docs/m9/credits (the menu canvas rendered through the camera into a texture).
    /// </summary>
    public sealed class ProbeTestsCredits
    {
        private const string ShotDir = "docs/m9/credits";
        // A 20:9 phone at the menu's CanvasScaler (1920 x 1080 reference, match 0.5): 966 reference units high.
        private const float PhoneHalfHeight = 966f / 2f;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private Menu Menu => main.Menu;

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
            Assert.IsNotNull(Menu, "premise: Main built no Menu");
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Cursor.lockState = CursorLockMode.None;
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

        private static GameObject Selected => EventSystem.current != null ? EventSystem.current.currentSelectedGameObject : null;

        private static IEnumerator UntilSelected(GameObject wanted)
        {
            for (int i = 0; i < 20 && Selected != wanted; i++)
            {
                yield return null;
            }
        }

        private static float Bottom(RectTransform rect) => rect.anchoredPosition.y - rect.sizeDelta.y * rect.pivot.y;
        private static float Top(RectTransform rect) => rect.anchoredPosition.y + rect.sizeDelta.y * (1f - rect.pivot.y);

        [UnityTest]
        public IEnumerator Step72a_CreditsPageOpensScrollsAndComesBack()
        {
            Strings.SetLanguage(Strings.French);
            Menu.ShowTitle();
            yield return UntilSelected(Menu.PlayButton.gameObject);
            Button credits = Menu.TitleCreditsButton;
            Assert.IsNotNull(credits, "the title has no Crédits button");
            Assert.IsTrue(Menu.Labels.TryGetValue("TitleCreditsLabel", out Text label) && label.text == "Crédits", "the Crédits button's label");

            // Between Options and Quitter, on screen and in the keyboard order; Quitter last, clear of the author line on a phone.
            var options = (RectTransform)Menu.TitleOptionsButton.transform;
            var mine = (RectTransform)credits.transform;
            var quit = (RectTransform)Menu.QuitButton.transform;
            Assert.IsTrue(Bottom(options) >= Top(mine) && Bottom(mine) >= Top(quit), "Crédits is not between Options and Quitter, apart");
            Assert.AreSame(credits, Menu.TitleOptionsButton.navigation.selectOnDown, "down from Options is not Crédits");
            Assert.AreSame(Menu.QuitButton, credits.navigation.selectOnDown, "down from Crédits is not Quitter");
            Assert.AreSame(Menu.PlayButton, Menu.QuitButton.navigation.selectOnDown, "the title chain no longer wraps");
            Assert.IsTrue(Menu.Labels.TryGetValue("Credits", out Text author), "premise: the author line");
            float authorTop = -PhoneHalfHeight + 28f + author.rectTransform.sizeDelta.y / 2f;
            Assert.Greater(Bottom(quit), authorTop, "Quitter runs into the author line on a 20:9 phone");
            yield return Shoot("title_fr_1920x1080.png", 1920, 1080);

            // Open: a page of the title.
            credits.onClick.Invoke();
            Assert.IsTrue(Menu.CreditsOpen, "Crédits did not open the Credits page");
            Assert.IsTrue(Menu.TitleOpen && Menu.IsOpen, "the Credits page closed the title");
            Assert.IsFalse(Menu.TitlePageShown, "the title page shows under the Credits page");
            Assert.IsTrue(main.Game.Paused, "the game runs under the Credits page");
            Assert.IsFalse(main.Hud.Visible, "the HUD shows under the Credits page");
            Menu.OpenOptions();
            Menu.OpenLevelSelect();
            Menu.Play();
            Assert.IsTrue(Menu.CreditsOpen && !Menu.OptionsOpen && !Menu.LevelSelectOpen && Menu.TitleOpen,
                "Options, the level select or Jouer opened over the Credits page");
            yield return UntilSelected(Menu.CreditsBackButton.gameObject);
            Assert.AreEqual(Menu.CreditsBackButton.gameObject, Selected, "Retour is not selected on the Credits page");
            Assert.IsTrue(Menu.Labels.TryGetValue("CreditsTitle", out Text heading) && heading.text == "Crédits", "the page's heading");
            Assert.IsTrue(Menu.Labels.TryGetValue("CreditsBackLabel", out Text back) && back.text == Strings.SelectBack, "Retour's label");

            // Every Core.Credits line, in French, then in English after a language switch.
            for (int i = 0; i < Credits.All.Count; i++)
            {
                Assert.IsTrue(Menu.Labels.TryGetValue("CreditsLine" + i, out Text line), $"line {i} missing");
                Assert.AreEqual(Credits.All[i].French, line.text, $"line {i} in French");
            }

            // Fits a 20:9 phone: the heading, the scroll view and Retour, top to bottom, apart and on screen.
            ScrollRect scroll = Menu.CreditsScroll;
            var view = (RectTransform)scroll.transform;
            var backRect = (RectTransform)Menu.CreditsBackButton.transform;
            Assert.Less(Top(heading.rectTransform), PhoneHalfHeight, "the heading leaves the top of a 20:9 phone");
            Assert.GreaterOrEqual(Bottom(heading.rectTransform), Top(view), "the heading overlaps the list");
            Assert.Greater(Bottom(view), Top(backRect), "the list runs into Retour");
            Assert.Greater(Bottom(backRect), -PhoneHalfHeight + 20f, "Retour leaves the bottom of a 20:9 phone");

            // Long enough to scroll; opens at the top.
            Canvas.ForceUpdateCanvases();
            yield return null;
            float contentHeight = scroll.content.rect.height;
            float viewHeight = scroll.viewport.rect.height;
            TestContext.WriteLine($"[Step72a] content {contentHeight:0} of view {viewHeight:0} reference units, {Credits.All.Count} lines");
            Assert.Greater(contentHeight, viewHeight + 100f, "premise: the credits fit without scrolling, the scroll checks prove nothing");
            Assert.AreEqual(1f, scroll.verticalNormalizedPosition, 1e-3f, "the page does not open at the top");
            // A source URL is one unbreakable word: it must fit the list's width, never be cut mid-word.
            int urls = 0;
            for (int i = 0; i < Credits.All.Count; i++)
            {
                Text line = Menu.Labels["CreditsLine" + i];
                if (line.text.StartsWith("https://"))
                {
                    urls++;
                    float wide = line.cachedTextGeneratorForLayout.GetPreferredWidth(line.text,
                        line.GetGenerationSettings(new Vector2(float.MaxValue, float.MaxValue))) / line.pixelsPerUnit;
                    Assert.LessOrEqual(wide, line.rectTransform.rect.width, $"the URL line {i} is wider than the list: {line.text}");
                }
            }
            Assert.AreEqual(2, urls, "premise: the two music source URLs have lines of their own");
            Assert.IsNotNull(scroll.verticalScrollbar, "the page has no scrollbar");
            Assert.AreEqual(Navigation.Mode.None, scroll.verticalScrollbar.navigation.mode, "the scrollbar is on the keyboard path");
            yield return Shoot("credits_top_fr_1920x1080.png", 1920, 1080);
            yield return Shoot("credits_top_fr_2400x1080.png", 2400, 1080);

            // Down: the injected D-pad (Menu.Update), then a real UI move event on Retour (CreditsScrollKeys).
            float before = scroll.verticalNormalizedPosition;
            InputReader.InjectMenuDown();
            yield return null;
            float afterPad = scroll.verticalNormalizedPosition;
            Assert.Less(afterPad, before - 1e-3f, "D-pad down did not scroll the page");
            Assert.AreEqual(Menu.CreditsBackButton.gameObject, Selected, "D-pad down moved the selection off Retour");
            var move = new AxisEventData(EventSystem.current) { moveDir = MoveDirection.Down, moveVector = Vector2.down };
            ExecuteEvents.Execute(Menu.CreditsBackButton.gameObject, move, ExecuteEvents.moveHandler);
            Assert.Less(scroll.verticalNormalizedPosition, afterPad - 1e-3f, "a UI move down on Retour did not scroll the page");
            Assert.AreEqual(Menu.CreditsBackButton.gameObject, Selected, "a UI move down moved the selection off Retour");

            // To the end: the last line shows inside the view; up comes back.
            Menu.ScrollCredits(1e6f);
            Assert.AreEqual(0f, scroll.verticalNormalizedPosition, 1e-3f, "the page does not scroll to its end");
            Canvas.ForceUpdateCanvases();
            Text last = Menu.Labels["CreditsLine" + (Credits.All.Count - 1)];
            var corners = new Vector3[4];
            var viewCorners = new Vector3[4];
            last.rectTransform.GetWorldCorners(corners);
            scroll.viewport.GetWorldCorners(viewCorners);
            Assert.GreaterOrEqual(corners[0].y, viewCorners[0].y - 0.5f, "the last line is cut at the bottom of the view at the end");
            yield return Shoot("credits_bottom_fr_1920x1080.png", 1920, 1080);
            InputReader.InjectMenuUp();
            yield return null;
            Assert.Greater(scroll.verticalNormalizedPosition, 1e-3f, "D-pad up did not scroll back");

            // The language switch relabels every line in place.
            Strings.SetLanguage(Strings.English);
            for (int i = 0; i < Credits.All.Count; i++)
            {
                Assert.AreEqual(Credits.All[i].English, Menu.Labels["CreditsLine" + i].text, $"line {i} in English");
            }
            Assert.AreEqual("Credits", heading.text, "the heading was not translated");
            Menu.ScrollCredits(-1e6f);
            yield return Shoot("credits_top_en_1920x1080.png", 1920, 1080);

            // Back (Escape or gamepad B): to the title's main page, on Crédits.
            InputReader.InjectBack();
            yield return null;
            Assert.IsFalse(Menu.CreditsOpen, "Back did not leave the Credits page");
            Assert.IsTrue(Menu.TitleOpen && Menu.TitlePageShown, "Back did not come back to the title page");
            yield return UntilSelected(credits.gameObject);
            Assert.AreEqual(credits.gameObject, Selected, "Back did not come back on Crédits");

            // Retour (click or Enter), from a page scrolled down: it reopens at the top.
            credits.onClick.Invoke();
            Menu.ScrollCredits(400f);
            Menu.CreditsBackButton.onClick.Invoke();
            Assert.IsFalse(Menu.CreditsOpen, "Retour did not leave the Credits page");
            Assert.IsTrue(Menu.TitlePageShown, "Retour did not come back to the title page");
            credits.onClick.Invoke();
            Assert.AreEqual(1f, scroll.verticalNormalizedPosition, 1e-3f, "the page does not reopen at the top");

            // The title closing under it (Jouer from elsewhere) closes it too.
            Menu.CloseCredits();
            Menu.Play();
            Assert.IsFalse(Menu.CreditsOpen || Menu.TitleOpen, "Jouer left a menu open");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// Renders the menu canvas over the scene into a <paramref name="width"/> x <paramref name="height"/> PNG under
        /// <see cref="ShotDir"/>: the menu's root canvas switches to Screen Space Camera on the game camera, which renders
        /// into a texture of that size (the CanvasScaler lays the page out for it), then everything is put back.
        /// </summary>
        private IEnumerator Shoot(string file, int width, int height)
        {
            Camera cam = main.Camera;
            Canvas root = Menu.GetComponent<Canvas>();
            Assert.IsNotNull(cam, "premise: Main has no camera");
            Assert.IsNotNull(root, "premise: the menu has no root canvas");
            var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
            RenderTexture previousTarget = cam.targetTexture;
            float previousPlane = root.planeDistance;
            cam.targetTexture = rt;
            cam.aspect = width / (float)height;
            root.renderMode = RenderMode.ScreenSpaceCamera;
            root.worldCamera = cam;
            root.planeDistance = cam.nearClipPlane + 0.01f;
            try
            {
                // One frame for the CanvasScaler (its own Update) to take the texture's size, then the layout.
                yield return null;
                yield return null;
                Canvas.ForceUpdateCanvases();
                Rect canvasRect = ((RectTransform)root.transform).rect;
                TestContext.WriteLine($"[Step72a] {file}: canvas {canvasRect.width:0} x {canvasRect.height:0} units, scale {root.scaleFactor:0.000},"
                    + $" camera {cam.pixelWidth} x {cam.pixelHeight} aspect {cam.aspect:0.000}, screen {Screen.width} x {Screen.height}");
                // The title tour shifts the lens sideways every LateUpdate (TitleCameraTour, TitleTourLensShift): harmless for
                // the game's overlay menu, but it would shift a Screen Space Camera canvas. Unshifted for this one render (the
                // tour sets it again next frame); the pose stays the tour's.
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
                UnityEngine.Object.Destroy(texture);
            }
            finally
            {
                root.renderMode = RenderMode.ScreenSpaceOverlay;
                root.worldCamera = null;
                root.planeDistance = previousPlane;
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
