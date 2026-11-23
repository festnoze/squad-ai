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
    /// Step 79 (Options icons, product owner 2026-11-20), on the real Boot scene: the Par défaut and Retour buttons carry
    /// their icons (reset arrow, back arrow, UiIconLibrary), the Language row shows the flag of the chosen language (French
    /// flag in French, US flag in English) and swaps it live, whichever way the language changes; the keyboard and gamepad
    /// order is unchanged; and on 1920 x 1080, 2400 x 1080 (20:9) and 1440 x 1080 (4:3) every row is on screen, apart from
    /// the next, its icon inside it and clear of its label, its label not cut. It writes the page's screenshots in French
    /// and in English to TestResults/options (gitignored, never under docs/), or to the absolute folder in OOS_SHOTS_DIR.
    /// </summary>
    public sealed class ProbeTestsOptionsIcons
    {
        private const string DefaultShotDir = "TestResults/options";

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private Menu Menu => main.Menu;

        private static string ShotDir
        {
            get
            {
                string custom = Environment.GetEnvironmentVariable("OOS_SHOTS_DIR");
                return string.IsNullOrEmpty(custom) ? DefaultShotDir : custom;
            }
        }

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
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
            Strings.SetLanguage(Strings.English);
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

        /// <summary>The language, set as the Options row sets it (SaveStore.SetOptions switches Strings, which relabels).</summary>
        private static void SetLanguage(string language)
        {
            SaveOptions o = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions
            {
                Sensitivity = o.Sensitivity, Volume = o.Volume, Music = o.Music, Cone = o.Cone, Quality = o.Quality, Difficulty = o.Difficulty,
                Language = language, Walls = o.Walls, WallOpacity = o.WallOpacity,
            });
        }

        private Button[] Rows => new[]
        {
            Menu.OptionsSensitivityButton, Menu.OptionsVolumeButton, Menu.OptionsMusicButton, Menu.OptionsConeButton, Menu.OptionsWallsButton,
            Menu.OptionsWallOpacityButton, Menu.OptionsQualityButton, Menu.OptionsDifficultyButton, Menu.OptionsLanguageButton,
            Menu.OptionsResetButton, Menu.OptionsBackButton,
        };

        [UnityTest]
        public IEnumerator Step79a_OptionsIconsFlagsNavigationAndFit()
        {
            UiIconLibrary library = UiIconLibrary.Load();
            Assert.IsNotNull(library, "premise: the UI icon library was never built (UiIconLibraryBuilder)");
            Assert.IsNotNull(library.reset, "reset.png is not in the UI icon library");
            Assert.IsNotNull(library.back, "back.png is not in the UI icon library");
            Assert.IsNotNull(library.flagFrench, "flag_fr.png is not in the UI icon library");
            Assert.IsNotNull(library.flagEnglish, "flag_us.png is not in the UI icon library");
            Assert.AreNotSame(library.flagFrench, library.flagEnglish, "the two flags are one sprite");
            Assert.AreSame(library.flagFrench, UiIconLibrary.LanguageFlag(Strings.French));
            Assert.AreSame(library.flagEnglish, UiIconLibrary.LanguageFlag(Strings.English));
            Assert.AreSame(library.flagEnglish, UiIconLibrary.LanguageFlag("de"), "an unknown language is English, its flag the US one");

            // French, the title, then Options.
            SetLanguage(Strings.French);
            Menu.ShowTitle();
            yield return UntilSelected(Menu.PlayButton.gameObject);
            Menu.TitleOptionsButton.onClick.Invoke();
            Assert.IsTrue(Menu.OptionsOpen, "premise: Options did not open from the title");
            yield return UntilSelected(Menu.OptionsSensitivityButton.gameObject);
            Assert.AreEqual(Menu.OptionsSensitivityButton.gameObject, Selected, "Options no longer opens on its first row");

            // Par défaut and Retour carry their icons, tinted like their labels, opaque.
            AssertIcon(Menu.OptionsResetButton, "OptionsResetIcon", library.reset);
            AssertIcon(Menu.OptionsBackButton, "OptionsBackIcon", library.back);
            Assert.AreEqual("Par défaut", Menu.Labels["OptionsResetLabel"].text, "the Par défaut label");
            Assert.AreEqual("Retour", Menu.Labels["OptionsBackLabel"].text, "the Retour label");

            // The Language row: the French flag in French, drawn untinted.
            Image flag = Menu.OptionsLanguageIcon;
            Assert.IsNotNull(flag, "the Language row has no icon");
            Assert.AreSame(flag.transform, Menu.OptionsLanguageButton.transform.Find("OptionsLanguageIcon"), "the Language icon is not the row's own");
            Assert.AreSame(library.flagFrench, flag.sprite, "the Language row does not show the French flag in French");
            Assert.AreEqual(Color.white, flag.color, "the flag is tinted (its colours must show as drawn)");

            // The keyboard and gamepad order is unchanged: Language, Par défaut, Retour, then back to the first row.
            Assert.AreSame(Menu.OptionsResetButton, Menu.OptionsLanguageButton.navigation.selectOnDown, "down from Language is not Par défaut");
            Assert.AreSame(Menu.OptionsBackButton, Menu.OptionsResetButton.navigation.selectOnDown, "down from Par défaut is not Retour");
            Assert.AreSame(Menu.OptionsSensitivityButton, Menu.OptionsBackButton.navigation.selectOnDown, "the Options chain no longer wraps");
            Assert.AreSame(Menu.OptionsLanguageButton, Menu.OptionsResetButton.navigation.selectOnUp, "up from Par défaut is not Language");
            Assert.AreSame(Menu.OptionsResetButton, Menu.OptionsBackButton.navigation.selectOnUp, "up from Retour is not Par défaut");
            InputReader.InjectMenuUp();
            yield return null;
            Assert.AreEqual(Menu.OptionsBackButton.gameObject, Selected, "D-pad up from the first row is not Retour");
            InputReader.InjectMenuUp();
            yield return null;
            Assert.AreEqual(Menu.OptionsResetButton.gameObject, Selected, "D-pad up from Retour is not Par défaut");
            InputReader.InjectMenuUp();
            yield return null;
            Assert.AreEqual(Menu.OptionsLanguageButton.gameObject, Selected, "D-pad up from Par défaut is not Language");

            // The French page, the Language row selected (its flag on the red selection), on the three screens.
            yield return new WaitForSecondsRealtime(0.25f);
            yield return Shoot("options_fr_1920x1080.png", 1920, 1080);
            yield return Shoot("options_fr_2400x1080.png", 2400, 1080);
            yield return Shoot("options_fr_1440x1080.png", 1440, 1080);

            // A on Language: English, the flag swaps at once, Par défaut and Retour relabel.
            InputReader.InjectMenuSubmit();
            yield return null;
            Assert.AreEqual(Strings.English, SaveStore.Options.LanguageId, "A on the Language row did not switch to English");
            Assert.AreSame(library.flagEnglish, flag.sprite, "the Language row does not show the US flag in English");
            Assert.AreEqual("Defaults", Menu.Labels["OptionsResetLabel"].text, "the Defaults label");
            Assert.AreEqual("Back", Menu.Labels["OptionsBackLabel"].text, "the Back label");
            Assert.AreEqual(Menu.OptionsLanguageButton.gameObject, Selected, "the language switch moved the selection");

            // The English page, Back selected, on the three screens.
            InputReader.InjectMenuDown();
            yield return null;
            InputReader.InjectMenuDown();
            yield return null;
            Assert.AreEqual(Menu.OptionsBackButton.gameObject, Selected, "D-pad down twice from Language is not Back");
            yield return new WaitForSecondsRealtime(0.25f);
            yield return Shoot("options_en_1920x1080.png", 1920, 1080);
            yield return Shoot("options_en_2400x1080.png", 2400, 1080);
            yield return Shoot("options_en_1440x1080.png", 1440, 1080);

            // The language changed another way (SaveStore.SetOptions, Strings.LanguageChanged): the flag follows too.
            SetLanguage(Strings.French);
            Assert.AreSame(library.flagFrench, flag.sprite, "the flag did not follow a language change made elsewhere");

            // Par défaut keeps the language (and so the flag) and brings the walls to their default, both at 10 %.
            SaveOptions before = SaveStore.Options;
            SaveStore.SetOptions(new SaveOptions { Language = before.Language, Walls = SaveOptions.WallsNone, WallOpacity = 50 });
            Menu.OptionsResetButton.onClick.Invoke();
            Assert.AreEqual(Strings.French, SaveStore.Options.LanguageId, "Par défaut changed the language");
            Assert.AreSame(library.flagFrench, flag.sprite, "Par défaut changed the flag");
            Assert.AreEqual(SaveOptions.WallsBoth, SaveStore.Options.Walls, "Par défaut did not bring the walls back to both");
            Assert.AreEqual(10, SaveStore.Options.WallOpacity, "Par défaut did not bring the wall opacity back to 10 %");

            // Retour still closes the page.
            Menu.OptionsBackButton.onClick.Invoke();
            Assert.IsFalse(Menu.OptionsOpen, "Retour did not close Options");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        private static void AssertIcon(Button button, string name, Sprite sprite)
        {
            Transform icon = button.transform.Find(name);
            Assert.IsNotNull(icon, $"{button.name} has no icon");
            Image image = icon.GetComponent<Image>();
            Assert.IsNotNull(image, $"{name} is not an image");
            Assert.AreSame(sprite, image.sprite, $"{name} does not show its library sprite");
            Assert.IsTrue(image.enabled && image.gameObject.activeInHierarchy, $"{name} is hidden");
            Assert.AreEqual(1f, image.color.a, 1e-4f, $"{name} is not opaque");
            Assert.IsTrue(image.preserveAspect, $"{name} is stretched");
            Assert.IsFalse(image.raycastTarget, $"{name} takes clicks from its button");
        }

        /// <summary>The rectangle of <paramref name="rect"/> in <paramref name="root"/>'s local space (the canvas' units).</summary>
        private static Rect In(RectTransform rect, RectTransform root)
        {
            var corners = new Vector3[4];
            rect.GetWorldCorners(corners);
            Vector3 min = root.InverseTransformPoint(corners[0]);
            Vector3 max = root.InverseTransformPoint(corners[2]);
            return Rect.MinMaxRect(Mathf.Min(min.x, max.x), Mathf.Min(min.y, max.y), Mathf.Max(min.x, max.x), Mathf.Max(min.y, max.y));
        }

        private static float PreferredWidth(Text text)
        {
            return text.cachedTextGeneratorForLayout.GetPreferredWidth(text.text,
                text.GetGenerationSettings(new Vector2(float.MaxValue, float.MaxValue))) / text.pixelsPerUnit;
        }

        /// <summary>
        /// The page laid out for the current render size: every row on the canvas and below the one above it, its icon
        /// inside it and left of its label, its label's text not wider than its room, Retour above the music credits line.
        /// </summary>
        private void AssertFits(string context)
        {
            Canvas root = Menu.GetComponent<Canvas>();
            var rootRect = (RectTransform)root.transform;
            Rect canvas = rootRect.rect;
            const float slack = 0.5f;
            float above = float.MaxValue;
            foreach (Button button in Rows)
            {
                Rect row = In((RectTransform)button.transform, rootRect);
                string at = $"{context} {button.name}";
                Assert.IsTrue(row.xMin >= canvas.xMin - slack && row.xMax <= canvas.xMax + slack && row.yMin >= canvas.yMin - slack
                    && row.yMax <= canvas.yMax + slack, $"{at} leaves the screen: {row} in {canvas}");
                Assert.LessOrEqual(row.yMax, above + slack, $"{at} overlaps the row above it");
                above = row.yMin;
                Assert.IsTrue(Menu.Labels.TryGetValue(button.name + "Label", out Text label), $"{at} has no label");
                Rect room = In(label.rectTransform, rootRect);
                float wide = PreferredWidth(label);
                Assert.LessOrEqual(wide, room.width + slack, $"{at}: the label \"{label.text}\" ({wide:0} units) is wider than its room ({room.width:0})");
                Transform iconTransform = button.transform.Find(button.name + "Icon");
                if (iconTransform == null)
                {
                    continue;
                }
                Rect icon = In((RectTransform)iconTransform, rootRect);
                Assert.IsTrue(icon.xMin >= row.xMin - slack && icon.xMax <= row.xMax + slack && icon.yMin >= row.yMin - slack
                    && icon.yMax <= row.yMax + slack, $"{at}: its icon {icon} sticks out of the row {row}");
                float textStart = label.alignment == TextAnchor.MiddleLeft ? room.xMin : room.center.x - wide / 2f;
                Assert.LessOrEqual(icon.xMax, textStart + slack, $"{at}: its icon runs into the label \"{label.text}\"");
            }
            Assert.IsTrue(Menu.Labels.TryGetValue("OptionsMusicCredits", out Text credits), "premise: the music credits line");
            Rect creditsRect = In(credits.rectTransform, rootRect);
            Assert.Greater(above, creditsRect.yMax, $"{context}: Retour runs into the music credits line");
            Assert.GreaterOrEqual(creditsRect.yMin, canvas.yMin - slack, $"{context}: the music credits line leaves the screen");
            TestContext.WriteLine($"[Step79a] {context}: canvas {canvas.width:0} x {canvas.height:0}, Retour bottom {above:0}, credits top {creditsRect.yMax:0}");
        }

        /// <summary>
        /// Renders the menu canvas over the scene into a <paramref name="width"/> x <paramref name="height"/> PNG under
        /// <see cref="ShotDir"/> (ProbeTestsCredits' helper: the menu's root canvas switches to Screen Space Camera on the game
        /// camera, which renders into a texture of that size), checks the layout at that size, then puts everything back.
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
                AssertFits($"{file} ({width} x {height})");
                // The title tour shifts the lens sideways every LateUpdate: unshifted for this one render.
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
