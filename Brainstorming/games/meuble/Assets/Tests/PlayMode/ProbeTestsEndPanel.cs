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
    /// Step 73 (end panel emphasis, 2026-11-19), on the real Boot scene under GameRules.M2: the win panel's Next level is
    /// its primary action the way the fail panel's Retry is (first in the row, larger, bold, in the same selection red,
    /// at rest since nothing selects it), the touch overlay hides under both panels, and both panels fit a 20:9 phone,
    /// 16:9 and a 4:3 tablet: every button inside the canvas, apart from the others and from the text lines. It writes
    /// the panels' screenshots, with the touch strings, to Build/shots/endpanel (the HUD canvas rendered through the camera).
    /// </summary>
    public sealed class ProbeTestsEndPanel
    {
        private const string ShotDir = "Build/shots/endpanel";
        // The screens checked: a 20:9 phone (the shortest canvas, 966 units), 16:9, a 4:3 tablet (the narrowest, 1663 units).
        private static readonly Vector2Int[] Screens = { new Vector2Int(2400, 1080), new Vector2Int(1920, 1080), new Vector2Int(1440, 1080) };
        // The least room left between a button and the canvas edge, in reference units.
        private const float EdgeMargin = 16f;

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;
        private Menu Menu => main.Menu;
        private Hud Hud => main.Hud;
        private FurnitureController Chair => Game.Furniture;
        private Inhabitant Habitant => Game.MainInhabitant;

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
            yield return Steps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
                if (main.Game.Furniture != null)
                {
                    main.Game.Furniture.ScriptedDirection = null;
                }
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

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static IEnumerator Until(Func<bool> until, int maxSteps)
        {
            for (int i = 0; i < maxSteps && !until(); i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        /// <summary>Every inhabitant frozen facing away from the exit, the chair driven onto the doormat (ProbeTestsM3Look's way).</summary>
        private IEnumerator WinCurrentLevel()
        {
            ZoneDef exit = Game.Def.Exit;
            var exitCenter = new Vector3(exit.X, 0f, exit.Z);
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Vector3 at = h.Routine.Position;
                h.Pin(at, YawToward(exitCenter, at));
            }
            RoomDef room = Game.Def.RoomAt(exitCenter) ?? (Game.Def.AllRooms().Count > 0 ? Game.Def.AllRooms()[0] : null);
            Vector3 roomCenter = room != null ? new Vector3(room.X, 0f, room.Z) : Vector3.zero;
            Vector3 d = YawMath.Planar(exitCenter - roomCenter);
            Vector3 approach = Mathf.Abs(d.x) * (room != null ? room.SizeZ : 1f) >= Mathf.Abs(d.z) * (room != null ? room.SizeX : 1f)
                ? new Vector3(Mathf.Sign(d.x), 0f, 0f)
                : new Vector3(0f, 0f, Mathf.Sign(d.z));
            if (approach.sqrMagnitude == 0f)
            {
                approach = Vector3.right;
            }
            Chair.Teleport(exitCenter - approach * 0.9f, YawMath.YawOf(approach));
            Chair.ScriptedDirection = approach;
            yield return Until(() => Game.State != PlayState.Playing, 150);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Won, Game.State, $"premise: {Game.LevelId} was not won");
        }

        /// <summary>The touch strings on the panels (a phone): forced touch UI, then a language round trip relabels them.</summary>
        private static void TouchStrings()
        {
            InputReader.ForceTouchUI = true;
            Strings.SetLanguage(Strings.English);
            Strings.SetLanguage(Strings.French);
        }

        private static Vector2 Size(Button button) => ((RectTransform)button.transform).rect.size;

        private static Text Label(Button button) => button.GetComponentInChildren<Text>();

        /// <summary>The primary button is larger than every secondary one, its label bold and bigger.</summary>
        private static void AssertPrimary(Button primary, string name, params Button[] secondary)
        {
            Assert.IsNotNull(primary, $"no {name} button");
            Assert.AreEqual(FontStyle.Bold, Label(primary).fontStyle, $"{name}'s label is not bold");
            foreach (Button other in secondary)
            {
                Assert.Greater(Size(primary).x, Size(other).x, $"{name} is not wider than {other.name}");
                Assert.Greater(Size(primary).y, Size(other).y, $"{name} is not taller than {other.name}");
                Assert.Greater(Label(primary).fontSize, Label(other).fontSize, $"{name}'s label is not bigger than {other.name}'s");
                Assert.AreNotEqual(FontStyle.Bold, Label(other).fontStyle, $"{other.name}'s label is bold too");
                Assert.Less(((RectTransform)primary.transform).anchoredPosition.x, ((RectTransform)other.transform).anchoredPosition.x,
                    $"{name} is not first in its row, before {other.name}");
            }
        }

        [UnityTest]
        public IEnumerator Step73a_NextLevelIsRedAndPrimaryLikeRetryAndBothPanelsFitAPhone()
        {
            Strings.SetLanguage(Strings.French);
            Assert.IsTrue(Game.HasNextLevel, "premise: the first level has a next level");
            yield return WinCurrentLevel();
            Assert.IsTrue(Hud.WinButtonsVisible && Hud.WinNextVisible, "premise: the win panel and its Next level are not up");
            TouchStrings();
            yield return null;
            yield return null;
            Assert.IsTrue(InputReader.TouchUIActive, "premise: the touch UI is not active");
            Assert.IsTrue(TouchControls.Instance == null || !TouchControls.Instance.Visible, "the touch overlay shows over the win panel");
            Assert.IsFalse(Hud.CreakGaugeVisible || Hud.SuspicionGaugeVisible || Hud.BalanceVisible, "the play band's gauges show under the win panel");
            Assert.IsTrue(Hud.Labels.TryGetValue("Controls", out Text controls) && !controls.enabled, "the controls line shows under the win panel");

            // Next level: red at rest (nothing selects it), the very red of a selected menu button, primary in its row.
            Button next = Hud.WinNextLevelButton;
            Assert.AreEqual(Hud.PrimaryRed, next.colors.normalColor, "Next level is not red at rest");
            Assert.AreEqual(Hud.PrimaryRed, next.colors.selectedColor, "Next level is not red when selected");
            Assert.AreEqual(Hud.PrimaryRed, Hud.WinReplayButton.colors.selectedColor, "premise: the selection red of the other buttons changed");
            Assert.AreNotEqual(Hud.PrimaryRed, Hud.WinReplayButton.colors.normalColor, "Replay is red at rest too");
            Assert.AreNotEqual(Hud.PrimaryRed, Hud.WinMenuButton.colors.normalColor, "Menu is red at rest too");
            Assert.IsNull(EventSystem.current.currentSelectedGameObject, "a win panel button is selected (Enter would fire twice)");
            AssertPrimary(next, "WinNextLevel", Hud.WinReplayButton, Hud.WinMenuButton);
            Assert.IsTrue(Hud.Labels.TryGetValue("WinNext", out Text winNext) && winNext.text == Strings.WinNextTouch, "the touch hint is not on the win panel");

            foreach (Vector2Int screen in Screens)
            {
                yield return Shoot($"win_fr_{screen.x}x{screen.y}.png", screen.x, screen.y,
                    new[] { next, Hud.WinReplayButton, Hud.WinMenuButton },
                    new[] { Hud.Labels["WinPanelTitle"].rectTransform, Hud.Labels["WinPanelBody"].rectTransform,
                        Hud.Labels["WinPanelAction"].rectTransform, winNext.rectTransform, Menu.RecordLine != null ? Menu.RecordLine.BestRect : null });
            }
            Strings.SetLanguage(Strings.English);
            yield return Shoot("win_en_2400x1080.png", 2400, 1080, new[] { next, Hud.WinReplayButton, Hud.WinMenuButton }, new RectTransform[0]);
            Strings.SetLanguage(Strings.French);

            // Next level loads the next level; caught there (ProbeTestsM3Look Step65a's way), with no touch UI while driving.
            string nextId = Game.NextLevelId;
            InputReader.ForceTouchUI = false;
            next.onClick.Invoke();
            yield return Until(() => Game.LevelId == nextId && Game.State == PlayState.Playing, 10);
            Assert.AreEqual(nextId, Game.LevelId, "the Next level button did not load the next level");
            Vector3 at = Habitant.Routine.Position;
            Vector3 near = at + new Vector3(0.8f, 0f, 0.4f);
            Chair.Teleport(near, Chair.Yaw);
            Habitant.Pin(at, YawToward(at, near));
            Chair.ScriptedDirection = Vector3.forward;
            yield return Until(() => Game.State != PlayState.Playing, 150);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "premise: the next level was not caught");
            Assert.IsTrue(Hud.FailVisible, "premise: the fail panel is not up");
            TouchStrings();
            yield return Until(() => EventSystem.current.currentSelectedGameObject == Hud.FailRetryButton.gameObject, 5);
            Assert.AreEqual(Hud.FailRetryButton.gameObject, EventSystem.current.currentSelectedGameObject, "Retry is not selected by default");
            yield return null;
            Assert.IsTrue(TouchControls.Instance == null || !TouchControls.Instance.Visible, "the touch overlay shows over the fail panel");
            Assert.IsFalse(Hud.CreakGaugeVisible || Hud.SuspicionGaugeVisible, "the play band's gauges show under the fail panel");
            Assert.IsFalse(controls.enabled, "the controls line shows under the fail panel");

            // Retry: red through its selection, the same red as Next level, and primary in its row the same way.
            Assert.AreEqual(next.colors.normalColor, Hud.FailRetryButton.colors.selectedColor, "Retry's red and Next level's differ");
            AssertPrimary(Hud.FailRetryButton, "FailRetry", Hud.FailMenuButton);
            Assert.AreEqual(Size(next), Size(Hud.FailRetryButton), "Next level and Retry are not the same size");
            Assert.AreEqual(Label(next).fontSize, Label(Hud.FailRetryButton).fontSize, "Next level and Retry labels differ in size");
            Assert.IsTrue(Hud.Labels.TryGetValue("FailPanelAction", out Text failAction) && failAction.text == Strings.FailActionTouch,
                "the touch hint is not on the fail panel");

            foreach (Vector2Int screen in Screens)
            {
                yield return Shoot($"fail_fr_{screen.x}x{screen.y}.png", screen.x, screen.y,
                    new[] { Hud.FailRetryButton, Hud.FailMenuButton },
                    new[] { Hud.Labels["FailPanelTitle"].rectTransform, Hud.Labels["FailPanelBody"].rectTransform, failAction.rectTransform });
            }

            // Retry: the play band comes back with the level.
            Hud.FailRetryButton.onClick.Invoke();
            yield return Steps(2);
            Assert.AreEqual(PlayState.Playing, Game.State, "Retry did not restart the level");
            Assert.IsTrue(controls.enabled, "the controls line did not come back after Retry");
            Assert.IsTrue(Hud.CreakGaugeVisible && Hud.SuspicionGaugeVisible, "the gauges did not come back after Retry");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>The button is drawn: every Canvas above it is enabled (panels are switched by their Canvas, never their GameObject).</summary>
        private static bool Drawn(Button button)
        {
            if (button == null || !button.gameObject.activeInHierarchy)
            {
                return false;
            }
            foreach (Canvas canvas in button.GetComponentsInParent<Canvas>(true))
            {
                if (!canvas.enabled)
                {
                    return false;
                }
            }
            return true;
        }

        /// <summary>
        /// Step 73b (end screen fix, 2026-11-20): the final screen after the last level drew the win panel's Replay/Menu row
        /// over its own Replay/Menu principal row. Now exactly one row is drawn there, Rejouer then Menu principal, the
        /// latter the primary (larger, bold, red through its default selection), and it fits 20:9, 16:9 and 4:3.
        /// </summary>
        [UnityTest]
        public IEnumerator Step73b_EndScreenShowsOneRowWithMenuAsPrimary()
        {
            Strings.SetLanguage(Strings.French);
            string last = Game.LevelOrder[Game.LevelOrder.Count - 1];
            Game.LoadLevel(last);
            Game.Rules = GameRules.M2;
            yield return Steps(2);
            Assert.IsTrue(Game.IsLastLevel, "premise: the last level of levels.json is up");
            yield return WinCurrentLevel();
            Assert.IsTrue(Hud.EndVisible, "premise: the end screen is not up");
            Assert.IsFalse(Hud.WinButtonsVisible, "the win panel's own buttons count as up on the end screen");
            Assert.IsFalse(Hud.WinNextVisible, "the end screen offers a next level");

            // Exactly the end row is drawn: no second Rejouer/Menu principal, no Next level placeholder.
            var drawn = new List<string>();
            foreach (Button button in Hud.WinPanel.GetComponentsInChildren<Button>(true))
            {
                if (Drawn(button))
                {
                    drawn.Add(button.name);
                }
            }
            CollectionAssert.AreEquivalent(new[] { Hud.EndReplayButton.name, Hud.EndButton.name }, drawn,
                "the end screen does not draw exactly Rejouer and Menu principal: " + string.Join(", ", drawn));

            // Menu principal is the primary: larger and bold, right of Rejouer, red through its default selection.
            Button menu = Hud.EndButton;
            Button replay = Hud.EndReplayButton;
            Assert.AreEqual(FontStyle.Bold, Label(menu).fontStyle, "Menu principal's label is not bold");
            Assert.AreNotEqual(FontStyle.Bold, Label(replay).fontStyle, "Rejouer's label is bold too");
            Assert.Greater(Size(menu).x, Size(replay).x, "Menu principal is not wider than Rejouer");
            Assert.Greater(Size(menu).y, Size(replay).y, "Menu principal is not taller than Rejouer");
            Assert.Less(((RectTransform)replay.transform).anchoredPosition.x, ((RectTransform)menu.transform).anchoredPosition.x,
                "Rejouer is not left of Menu principal");
            Assert.AreEqual(Size(Hud.WinNextLevelButton), Size(menu), "Menu principal and Next level are not the same size");
            Assert.AreEqual(Label(Hud.WinNextLevelButton).fontSize, Label(menu).fontSize, "Menu principal and Next level labels differ in size");
            yield return Until(() => EventSystem.current.currentSelectedGameObject == menu.gameObject, 5);
            Assert.AreEqual(menu.gameObject, EventSystem.current.currentSelectedGameObject, "Menu principal is not selected by default");
            Assert.AreEqual(Hud.PrimaryRed, menu.colors.selectedColor, "Menu principal is not red when selected");
            Assert.AreNotEqual(Hud.PrimaryRed, replay.colors.normalColor, "Rejouer is red at rest");

            TouchStrings();
            yield return null;
            Assert.IsTrue(Hud.Labels.TryGetValue("WinPanelAction", out Text action) && action.text == Strings.WinActionTouch,
                "the end screen's hint does not name the Rejouer button on a phone");
            foreach (Vector2Int screen in Screens)
            {
                yield return Shoot($"end_fr_{screen.x}x{screen.y}.png", screen.x, screen.y, new[] { replay, menu },
                    new[] { Hud.Labels["WinPanelTitle"].rectTransform, Hud.Labels["WinPanelBody"].rectTransform, action.rectTransform,
                        Hud.Labels["EndTime"].rectTransform, Menu.RecordLine != null ? Menu.RecordLine.BestRect : null });
            }
            InputReader.ForceTouchUI = false;
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>The rectangle of <paramref name="rect"/> in the local space of <paramref name="root"/> (reference units).</summary>
        private static Rect LocalRect(RectTransform root, RectTransform rect)
        {
            var corners = new Vector3[4];
            rect.GetWorldCorners(corners);
            Vector3 min = root.InverseTransformPoint(corners[0]);
            Vector3 max = root.InverseTransformPoint(corners[2]);
            return Rect.MinMaxRect(min.x, min.y, max.x, max.y);
        }

        /// <summary>
        /// Lays the HUD out for a <paramref name="width"/> x <paramref name="height"/> screen (its root canvas switched to
        /// Screen Space Camera on the game camera, which renders into a texture of that size), checks that every one of
        /// <paramref name="buttons"/> is inside the canvas and apart from the others and from the shown
        /// <paramref name="texts"/>, writes the PNG under <see cref="ShotDir"/>, then puts everything back.
        /// </summary>
        private IEnumerator Shoot(string file, int width, int height, Button[] buttons, RectTransform[] texts)
        {
            Camera cam = main.Camera;
            Canvas root = Hud.GetComponent<Canvas>();
            Assert.IsNotNull(cam, "premise: Main has no camera");
            Assert.IsNotNull(root, "premise: the HUD has no root canvas");
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
                // Frames for the CanvasScaler (its own Update) to take the texture's size and the button tints to settle.
                yield return null;
                yield return null;
                yield return new WaitForSecondsRealtime(0.2f);
                Canvas.ForceUpdateCanvases();
                var rootRect = (RectTransform)root.transform;
                Rect canvas = rootRect.rect;
                TestContext.WriteLine($"[Step73a] {file}: canvas {canvas.width:0} x {canvas.height:0} units, scale {root.scaleFactor:0.000}");
                Assert.AreEqual(width / (float)height, canvas.width / canvas.height, 0.01f, $"premise: the canvas did not take the {width} x {height} shape");
                for (int i = 0; i < buttons.Length; i++)
                {
                    Rect a = LocalRect(rootRect, (RectTransform)buttons[i].transform);
                    TestContext.WriteLine($"  {buttons[i].name}: x {a.xMin:0}..{a.xMax:0}, y {a.yMin:0}..{a.yMax:0}");
                    Assert.GreaterOrEqual(a.xMin, canvas.xMin + EdgeMargin, $"{buttons[i].name} is cut on the left at {width} x {height}");
                    Assert.LessOrEqual(a.xMax, canvas.xMax - EdgeMargin, $"{buttons[i].name} is cut on the right at {width} x {height}");
                    Assert.GreaterOrEqual(a.yMin, canvas.yMin + EdgeMargin, $"{buttons[i].name} is cut at the bottom at {width} x {height}");
                    Text label = Label(buttons[i]);
                    Assert.LessOrEqual(label.preferredWidth, ((RectTransform)buttons[i].transform).rect.width - 24f,
                        $"{buttons[i].name}'s label \"{label.text}\" overflows its plate");
                    for (int j = i + 1; j < buttons.Length; j++)
                    {
                        Assert.IsFalse(a.Overlaps(LocalRect(rootRect, (RectTransform)buttons[j].transform)),
                            $"{buttons[i].name} overlaps {buttons[j].name} at {width} x {height}");
                    }
                    foreach (RectTransform text in texts)
                    {
                        Text graphic = text != null ? text.GetComponent<Text>() : null;
                        if (graphic == null || !graphic.enabled || !graphic.gameObject.activeInHierarchy || string.IsNullOrEmpty(graphic.text))
                        {
                            continue;
                        }
                        Rect t = LocalRect(rootRect, text);
                        Assert.IsFalse(a.Overlaps(t), $"{buttons[i].name} overlaps the text \"{graphic.text}\" at {width} x {height}");
                        Assert.GreaterOrEqual(t.yMin, canvas.yMin + EdgeMargin, $"the text \"{graphic.text}\" is cut at the bottom at {width} x {height}");
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
