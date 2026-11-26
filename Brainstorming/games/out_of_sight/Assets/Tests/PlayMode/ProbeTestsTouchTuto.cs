using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// TOUCHTUTO (docs/next/progress/TOUCHTUTO.md), on the real Boot scene with injected fingers and
    /// <see cref="InputReader.ForceTouchUI"/> (no touchscreen in a headless run):
    /// <list type="bullet">
    /// <item>TouchTuto01: level 1 built held shows the touch tutorial only with the touch controls up; it draws over the HUD
    /// and the touch overlay and under the menus, its zone panels follow the thirds split, its texts follow the language,
    /// and it replaces the start line, the controls line and the intro card; the pause hides it; level 2 never shows it.</item>
    /// <item>TouchTuto02: under the tutorial a thumb on the stick zone and a drag on the camera zone steer nothing; the
    /// first lift starts the level with no move and no camera turn and the tutorial goes (the card does not come back);
    /// a restart of level 1 shows it again, and a plain tap starts it.</item>
    /// </list>
    /// The suite runs with the held start off (HeldStartTestRun): each test turns it on for its own builds.
    /// </summary>
    public sealed class ProbeTestsTouchTuto
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private string language;

        private Main main;
        private GameState Game => main.Game;
        private Hud Hud => main.Hud;
        private static TouchControls Touch => TouchControls.Instance;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            language = Strings.Language;
            GameState.HoldStart = false;
            GamePause.IsPaused = false;
            InputReader.ResetInjections();
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
            Assert.IsNotNull(Touch, "no TouchControls in the run");
            yield return new WaitForFixedUpdate();
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Strings.SetLanguage(language);
            // Back to the suite's value (HeldStartTestRun), never to the player's default.
            GameState.HoldStart = false;
            Time.timeScale = 1f;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = false;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
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

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "unexpected log errors: " + string.Join(" | ", logged));
        }

        private static IEnumerator Frames(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return null;
            }
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        /// <summary>Builds <paramref name="id"/> with the held start on and checks it waits for its first input.</summary>
        private void LoadHeld(string id)
        {
            GameState.HoldStart = true;
            Game.LoadLevel(id);
            Assert.AreEqual(id, Game.Def.Id, "premise: the level loaded");
            Assert.AreEqual(PlayState.Playing, Game.State, id + ": premise: playing");
            Assert.IsFalse(Game.Started, id + ": a build with the hold on started at once");
        }

        /// <summary>The screen rect (pixels) of a RectTransform on a Screen Space Overlay canvas.</summary>
        private static Rect ScreenRect(RectTransform rect)
        {
            var corners = new Vector3[4];
            rect.GetWorldCorners(corners);
            return Rect.MinMaxRect(corners[0].x, corners[0].y, corners[2].x, corners[2].y);
        }

        [UnityTest]
        public IEnumerator TouchTuto01_ShownOnLevel1WithTouchOnly()
        {
            // No touch: the plain held card, no tutorial.
            InputReader.ForceTouchUI = false;
            LoadHeld("level1");
            yield return Frames(3);
            Assert.IsFalse(TouchControls.TutorialShowing, "the tutorial shows with no touch");
            Assert.IsTrue(Hud.StartLineVisible, "premise: the held card shows its start line");

            // Touch: the tutorial, over the HUD and the touch overlay, under the menus.
            InputReader.ForceTouchUI = true;
            yield return Frames(3);
            Assert.IsTrue(Touch.TutorialVisible, "level 1 held on touch shows no tutorial");
            TouchTutorial tutorial = Touch.Tutorial;
            Assert.IsNotNull(tutorial, "premise: the tutorial was built");
            int overlay = Touch.transform.Find("TouchOverlay").GetComponent<Canvas>().sortingOrder;
            int menu = main.Menu.GetComponent<Canvas>().sortingOrder;
            Assert.Greater(tutorial.Canvas.sortingOrder, overlay, "the tutorial draws under the touch overlay");
            Assert.Greater(tutorial.Canvas.sortingOrder, Hud.GetComponent<Canvas>().sortingOrder, "the tutorial draws under the HUD");
            Assert.Less(tutorial.Canvas.sortingOrder, menu, "the tutorial draws over the menus");

            // It replaces the start line, the controls line and the intro card; the level still waits.
            Assert.IsTrue(Hud.TutorialCovering, "the HUD does not know the tutorial covers it");
            Assert.IsTrue(Hud.CardHeld, "premise: the level still waits for its first input");
            Assert.IsFalse(Hud.StartLineVisible, "the start line shows under the tutorial");
            Assert.IsFalse(Hud.ControlsVisible, "the controls line shows under the tutorial");
            Assert.AreEqual(0f, Hud.TitleCardAlpha, 1e-4f, "the intro card shows under the tutorial");

            // The zone panels follow the thirds split.
            Rect move = ScreenRect(tutorial.MoveZone);
            Rect camera = ScreenRect(tutorial.CameraZone);
            float split = TouchControls.StickZoneRight;
            Assert.Less(move.xMax, split, "the move panel crosses the split");
            Assert.Greater(camera.xMin, split, "the camera panel crosses the split");
            Assert.IsTrue(move.xMin >= 0f && camera.xMax <= Screen.width && move.yMin >= 0f && move.yMax <= Screen.height,
                "a zone panel leaves the screen");
            Assert.Greater(camera.width, move.width * 1.5f, "the camera panel is not the larger share");

            // The texts, English then French (titles in capitals).
            Strings.SetLanguage(Strings.English);
            yield return Frames(2);
            Assert.AreEqual(Strings.TutoTap, tutorial.Labels["TapLine"].text);
            Assert.AreEqual("MOVE", tutorial.Labels["MoveTitle"].text);
            Assert.AreEqual(Strings.TutoZoomCaption, tutorial.Labels["ZoomCaption"].text);
            Strings.SetLanguage(Strings.French);
            yield return Frames(2);
            Assert.AreEqual("Touche l'écran pour jouer", tutorial.Labels["TapLine"].text);
            Assert.AreEqual("SE DÉPLACER", tutorial.Labels["MoveTitle"].text);
            Assert.AreEqual("TOURNER", tutorial.Labels["TurnTitle"].text);
            Strings.SetLanguage(Strings.English);
            yield return Frames(1);

            // The pause hides it; back from it, it shows again.
            Game.Paused = true;
            yield return Frames(2);
            Assert.IsFalse(Touch.TutorialVisible, "the tutorial shows under the pause");
            Game.Paused = false;
            yield return Frames(2);
            Assert.IsTrue(Touch.TutorialVisible, "the tutorial did not come back after the pause");

            // Level 2 held on touch: no tutorial, the plain held card and the controls line.
            LoadHeld("level2");
            yield return Frames(3);
            Assert.IsFalse(Touch.TutorialVisible, "level 2 shows the level 1 tutorial");
            Assert.IsFalse(Hud.TutorialCovering, "the HUD still hides under a tutorial that is gone");
            Assert.IsTrue(Hud.StartLineVisible, "level 2's held card shows no start line");
            Assert.IsTrue(Hud.ControlsVisible, "level 2 shows no controls line");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator TouchTuto02_TapAnywhereStartsWithoutMovingAndRestartShowsAgain()
        {
            InputReader.ForceTouchUI = true;
            LoadHeld("level1");
            yield return Frames(3);
            Assert.IsTrue(Touch.TutorialVisible, "premise: level 1 held on touch shows the tutorial");
            OrbitCamera cam = main.OrbitCamera;
            Vector3 chair0 = Game.Furniture.transform.position;
            float yaw0 = cam.Yaw;
            float k = Screen.height / 1080f;

            // A thumb on the stick zone pushed past the rim and a finger dragged on the camera zone: neither steers.
            Vector2 thumb = new Vector2(Screen.width * 0.15f, Screen.height * 0.4f);
            Vector2 finger = new Vector2(Screen.width * 0.7f, Screen.height * 0.5f);
            InputReader.InjectTouch(0, thumb);
            InputReader.InjectTouch(1, finger);
            yield return Frames(1);
            InputReader.InjectTouch(0, thumb + new Vector2(0f, Tuning.TouchStickRadius * k * 1.5f));
            InputReader.InjectTouch(1, finger + new Vector2(120f * k, 0f));
            yield return Frames(2);
            Assert.AreEqual(Vector2.zero, InputReader.Move(), "a thumb under the tutorial moved the stick");
            Assert.AreEqual(Vector2.zero, InputReader.TouchLookDelta(), "a drag under the tutorial orbited");
            Assert.AreEqual(yaw0, cam.Yaw, 0.01f, "a drag under the tutorial turned the camera");
            yield return Steps(2);
            Assert.IsFalse(Game.Started, "fingers resting on the tutorial started the level before a lift");
            Assert.IsTrue(Touch.TutorialVisible, "the tutorial went before a finger lifted");

            // The first lift: the start press. The tutorial goes with the wait.
            InputReader.ReleaseTouch(0);
            yield return Frames(1);
            yield return Steps(2);
            Assert.IsTrue(Game.Started, "lifting a finger from the tutorial did not start the level");
            yield return Frames(2);
            Assert.IsFalse(Touch.TutorialVisible, "the tutorial stayed after the level started");
            Assert.IsFalse(Hud.TutorialCovering, "the HUD still hides under a tutorial that is gone");
            Assert.IsTrue(Hud.ControlsVisible, "the controls line did not come back");
            Assert.AreEqual(0f, Hud.TitleCardAlpha, 1e-4f, "the intro card came back after the tutorial");

            // The finger still down steers nothing until it lifts.
            InputReader.InjectTouch(1, finger + new Vector2(240f * k, 0f));
            yield return Frames(2);
            Assert.AreEqual(yaw0, cam.Yaw, 0.01f, "a finger left from the tutorial turned the camera");
            InputReader.ReleaseTouch(1);
            yield return Frames(1);
            Assert.Less(Vector3.Distance(YawMath.Planar(Game.Furniture.transform.position), YawMath.Planar(chair0)), 1e-4f,
                "the tutorial tap moved the furniture");

            // Every build of level 1 holds it again: a restart shows the tutorial again, and a plain tap starts it.
            Game.Restart();
            yield return Frames(3);
            Assert.IsFalse(Game.Started, "premise: the restart holds the level");
            Assert.IsTrue(Touch.TutorialVisible, "a restart of level 1 did not show the tutorial again");
            InputReader.InjectTouch(2, new Vector2(Screen.width * 0.8f, Screen.height * 0.6f));
            yield return Frames(1);
            InputReader.ReleaseTouch(2);
            yield return Frames(1);
            yield return Steps(2);
            Assert.IsTrue(Game.Started, "a tap on the tutorial did not start the restarted level");
            yield return Frames(2);
            Assert.IsFalse(Touch.TutorialVisible, "the tutorial stayed after the restarted level started");
            AssertClean();
        }
    }
}
