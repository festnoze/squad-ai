using System;
using System.Collections;
using System.Collections.Generic;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M3 probe step 26 (docs/CONTRACT_M3.md 6 and 9): the title screen, the pause, the end screen, the world
    /// markers below the HUD band and the look setup, on the real Boot scene under GameRules.M2.
    /// Every wait counts fixed steps (WaitForFixedUpdate, which keeps running while the game is paused) or is
    /// bounded by them, never by rendered frames. Every scenario asserts its premise first (the menu exists, the
    /// title is open, the level was won...) so a stub cannot pass, and the pause cases end with a control that
    /// shows the same input acts once the game runs.
    /// </summary>
    public sealed class ProbeTestsM3Look
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private int ruleSteps;

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
            ruleSteps = 0;
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
            Assert.IsNotNull(Menu, "premise: Main built no Menu");
            Game.Rules = GameRules.M2;
            Game.FixedStepped += CountRuleStep;
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
                main.Game.FixedStepped -= CountRuleStep;
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

        private void CountRuleStep() => ruleSteps++;

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

        /// <summary>Waits until <paramref name="until"/> holds, at most <paramref name="maxSteps"/> fixed steps.</summary>
        private static IEnumerator Until(Func<bool> until, int maxSteps)
        {
            for (int i = 0; i < maxSteps && !until(); i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static float YawToward(Vector3 from, Vector3 to) => YawMath.YawOf(to - from);

        private void AssertMenuLabel(string name, string expected)
        {
            Assert.IsTrue(Menu.Labels.TryGetValue(name, out Text text), $"menu label {name} missing");
            Assert.AreEqual(expected, text.text, $"menu label {name}");
        }

        /// <summary>Every inhabitant frozen facing away from the exit, the chair driven onto the doormat.</summary>
        private IEnumerator WinCurrentLevel()
        {
            ZoneDef exit = Game.Def.Exit;
            var exitCenter = new Vector3(exit.X, 0f, exit.Z);
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Vector3 at = h.Routine.Position;
                h.Pin(at, YawToward(exitCenter, at));
            }
            Vector3 approach = ExitApproach(exitCenter);
            Chair.Teleport(exitCenter - approach * 0.9f, YawMath.YawOf(approach));
            Chair.ScriptedDirection = approach;
            yield return Until(() => Game.State != PlayState.Playing, 150);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Won, Game.State, $"premise: {Game.LevelId} was not won");
        }

        /// <summary>From the center of the exit's room onto the doormat, axis aligned (the doormat lies against a wall).</summary>
        private Vector3 ExitApproach(Vector3 exitCenter)
        {
            RoomDef room = Game.Def.RoomAt(exitCenter) ?? (Game.Def.AllRooms().Count > 0 ? Game.Def.AllRooms()[0] : null);
            Vector3 roomCenter = room != null ? new Vector3(room.X, 0f, room.Z) : Vector3.zero;
            Vector3 d = YawMath.Planar(exitCenter - roomCenter);
            Vector3 axis = Mathf.Abs(d.x) * (room != null ? room.SizeZ : 1f) >= Mathf.Abs(d.z) * (room != null ? room.SizeX : 1f)
                ? new Vector3(Mathf.Sign(d.x), 0f, 0f)
                : new Vector3(0f, 0f, Mathf.Sign(d.z));
            return axis.sqrMagnitude > 0f ? axis : Vector3.right;
        }

        private IEnumerator PressPause(bool expectPaused)
        {
            InputReader.InjectPausePress();
            yield return Until(() => Game.Paused == expectPaused, 5);
            Assert.AreEqual(expectPaused, Game.Paused, expectPaused ? "a pause press did not pause" : "a second pause press did not resume");
        }

        // ----- The title -----

        [UnityTest]
        public IEnumerator Step26_TitlePausesAndPlayStartsLevel1()
        {
            // An editor run never sees the title by itself (docs/CONTRACT_M3.md 6).
            Assert.IsFalse(Menu.IsOpen, "the title opened by itself in an editor run");
            Assert.IsFalse(Game.Paused);
            Assert.IsTrue(Hud.Visible);
            Assert.GreaterOrEqual(Game.LevelOrder.Count, 2, "premise: levels.json lists at least two levels");
            string first = Game.LevelOrder[0];
            Game.LoadLevel(Game.LevelOrder[1]);
            yield return Steps(2);

            Menu.ShowTitle();
            Assert.IsTrue(Menu.TitleOpen && Menu.IsOpen, "ShowTitle did not open the title");
            Assert.AreEqual(TitleCameraTour.LevelId, Game.LevelId, "the title is not over the title house (M7 title camera)");
            Assert.IsTrue(Game.Paused, "the title does not pause the game");
            Assert.IsTrue(GamePause.IsPaused);
            Assert.IsTrue(AudioListener.pause, "the audio listener is not paused under the title");
            Assert.IsFalse(Hud.Visible, "the HUD shows under the title");
            Assert.AreEqual(CursorLockMode.None, Cursor.lockState, "the cursor is not free on the title");
            Assert.IsTrue(main.OrbitCamera.Showcase, "the title camera is not orbiting");
            AssertMenuLabel("Title", Strings.Title);
            AssertMenuLabel("PlayLabel", Strings.TitlePlay);
            AssertMenuLabel("QuitLabel", Strings.TitleQuit);
            AssertMenuLabel("Credits", Strings.TitleCredits);
            Assert.IsNotNull(EventSystem.current, "no EventSystem");
            Assert.AreNotEqual(Menu.PlayButton.gameObject, EventSystem.current.currentSelectedGameObject,
                "Jouer is selected in the frame the title opened: that frame's Enter would submit it");
            // Menu selects on its next Update, a rendered frame: the title house's heavy load runs several fixed steps in
            // one long frame, so a wait in fixed steps can end before that frame (same as Step26_EndScreenEnter...).
            for (int i = 0; i < 10 && EventSystem.current.currentSelectedGameObject != Menu.PlayButton.gameObject; i++)
            {
                yield return null;
            }
            Assert.AreEqual(Menu.PlayButton.gameObject, EventSystem.current.currentSelectedGameObject, "Jouer is not selected for Enter");

            float elapsed = Game.Elapsed;
            int steps = Game.Steps;
            Vector3 chairAt = Chair.transform.position;
            float yaw = main.OrbitCamera.Yaw;
            int rules = ruleSteps;
            yield return Steps(60);
            Assert.AreEqual(elapsed, Game.Elapsed, "the level clock ran under the title");
            Assert.AreEqual(steps, Game.Steps);
            Assert.AreEqual(rules, ruleSteps, "fixed step rules ran under the title");
            Assert.AreEqual(chairAt, Chair.transform.position);
            Assert.Greater(Mathf.Abs(Mathf.DeltaAngle(yaw, main.OrbitCamera.Yaw)), 0.5f, "the title camera does not orbit");

            // A pause press on the title is ignored: Play is the only way in.
            InputReader.InjectPausePress();
            yield return Steps(3);
            Assert.IsTrue(Menu.TitleOpen);
            Assert.IsFalse(Menu.PauseOpen, "Escape opened the pause menu over the title");
            Assert.IsTrue(Game.Paused);

            Menu.PlayButton.onClick.Invoke();
            Assert.IsFalse(Menu.IsOpen, "Jouer did not close the title");
            Assert.IsFalse(Game.Paused, "Jouer did not unpause");
            Assert.IsFalse(AudioListener.pause);
            Assert.IsTrue(Hud.Visible, "the HUD did not come back");
            Assert.IsFalse(main.OrbitCamera.Showcase);
            Assert.AreEqual(first, Game.LevelId, "Jouer did not start the first level");
            Assert.AreEqual(PlayState.Playing, Game.State);
            yield return Steps(10);
            Assert.Greater(Game.Elapsed, 0.15f, "the level clock does not run after Jouer");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- The pause -----

        [UnityTest]
        public IEnumerator Step26_PauseStopsEveryRuleAndHoldsVisuals()
        {
            Assert.IsFalse(Menu.IsOpen, "premise: no menu open");
            Assert.AreEqual(PlayState.Playing, Game.State);
            // The chair keeps being driven, so it would move, hop and fill the creak gauge if any rule ran. The
            // inhabitant is frozen looking away, so the drive is never seen.
            Habitant.Pin(Habitant.Routine.Position, YawToward(Chair.transform.position, Habitant.Routine.Position));
            Chair.ScriptedDirection = Vector3.forward;
            Vector3 before = Chair.transform.position;
            yield return Steps(6);
            Assert.Greater(YawMath.Planar(Chair.transform.position - before).magnitude, 0.05f, "premise: the driven chair does not move");

            yield return PressPause(true);
            Assert.IsTrue(Menu.PauseOpen, "the pause menu is not open");
            Assert.IsTrue(AudioListener.pause, "the audio listener is not paused");
            Assert.IsFalse(Hud.Visible, "the HUD shows under the pause menu");
            Assert.AreEqual(CursorLockMode.None, Cursor.lockState);
            Assert.AreEqual(Menu.ResumeButton.gameObject, EventSystem.current.currentSelectedGameObject, "Reprendre is not selected");
            AssertMenuLabel("PauseTitle", Strings.PauseTitle);
            AssertMenuLabel("ResumeLabel", Strings.PauseResume);
            AssertMenuLabel("RestartLabel", Strings.PauseRestart);
            AssertMenuLabel("MainMenuLabel", Strings.PauseMenu);

            float elapsed = Game.Elapsed;
            int steps = Game.Steps;
            int rules = ruleSteps;
            int hops = Chair.HopCount;
            float creak = Game.Creak.Value;
            Vector3 chairAt = Chair.transform.position;
            Vector3 visual = Chair.Visual.position;
            Vector3 eye = Habitant.VisualEyePosition;
            float worstChair = 0f;
            float worstEye = 0f;
            for (int i = 0; i < 100; i++)
            {
                yield return new WaitForFixedUpdate();
                Assert.AreEqual(elapsed, Game.Elapsed, $"Elapsed moved during the pause (fixed step {i})");
                worstChair = Mathf.Max(worstChair, (Chair.Visual.position - visual).magnitude);
                worstEye = Mathf.Max(worstEye, (Habitant.VisualEyePosition - eye).magnitude);
            }
            Assert.AreEqual(steps, Game.Steps);
            Assert.AreEqual(rules, ruleSteps, "fixed step rules ran during the pause");
            Assert.AreEqual(hops, Chair.HopCount, "the chair hopped during the pause");
            Assert.AreEqual(creak, Game.Creak.Value, "the creak gauge moved during the pause");
            Assert.AreEqual(chairAt, Chair.transform.position, "the chair moved during the pause");
            Assert.Less(worstChair, 1e-4f, "the chair's interpolated visual moved during the pause (alpha not held at 1)");
            Assert.Less(worstEye, 1e-4f, "the inhabitant's interpolated eye moved during the pause");

            yield return PressPause(false);
            Assert.IsFalse(Menu.IsOpen, "a second press did not close the pause menu");
            Assert.IsFalse(AudioListener.pause);
            Assert.IsTrue(Hud.Visible);
            yield return Steps(5);
            Assert.Greater(Game.Elapsed, elapsed, "the level clock does not run after the resume");
            Assert.Greater(YawMath.Planar(Chair.transform.position - chairAt).magnitude, 0.02f, "the chair does not move after the resume");
            Chair.ScriptedDirection = null;
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>The inhabitant's interpolated pose holds while paused in the middle of a walk.</summary>
        [UnityTest]
        public IEnumerator Step26_PauseHoldsAWalkingInhabitant()
        {
            Assert.IsFalse(Menu.IsOpen, "premise: no menu open");
            int guard = 0;
            Time.timeScale = 4f;
            try
            {
                while (Habitant.Routine.LastActivity != RoutineActivity.Walking && Game.State == PlayState.Playing && guard++ < 2000)
                {
                    yield return new WaitForFixedUpdate();
                }
            }
            finally
            {
                Time.timeScale = 1f;
            }
            yield return Steps(3);
            Assert.AreEqual(RoutineActivity.Walking, Habitant.Routine.LastActivity, "premise: the inhabitant never walked");
            Vector3 routineAt = Habitant.Routine.Position;
            yield return Steps(1);
            Assert.Greater((Habitant.Routine.Position - routineAt).magnitude, 1e-4f, "premise: the walking routine does not move");

            yield return PressPause(true);
            routineAt = Habitant.Routine.Position;
            Vector3 body = Habitant.transform.position;
            Vector3 eye = Habitant.VisualEyePosition;
            float worst = 0f;
            for (int i = 0; i < 100; i++)
            {
                yield return new WaitForFixedUpdate();
                worst = Mathf.Max(worst, (Habitant.VisualEyePosition - eye).magnitude);
            }
            Assert.AreEqual(routineAt, Habitant.Routine.Position, "the routine walked during the pause");
            Assert.AreEqual(body, Habitant.transform.position);
            Assert.Less(worst, 1e-4f, "the inhabitant's interpolated visual moved during the pause (alpha not held at 1)");
            yield return PressPause(false);
            yield return Steps(5);
            Assert.Greater((Habitant.Routine.Position - routineAt).magnitude, 1e-4f, "the routine does not walk after the resume");
        }

        [UnityTest]
        public IEnumerator Step26_RAndEnterDoNothingWhilePaused()
        {
            Assert.IsTrue(Game.HasNextLevel, "premise: the first level has a next level");
            yield return WinCurrentLevel();
            Assert.IsTrue(Hud.WinNextVisible, "premise: the win panel offers the next level");
            Assert.AreEqual(Strings.WinTitle, Hud.WinTitleText, "a level with a next level shows the end title");
            Assert.IsFalse(Hud.EndVisible, "a level with a next level shows the end screen");
            string level = Game.LevelId;
            int restarts = Game.Restarts;

            yield return PressPause(true);
            InputReader.InjectRestartPress();
            InputReader.InjectNextLevelPress();
            yield return Steps(20);
            Assert.AreEqual(restarts, Game.Restarts, "R restarted the level while paused");
            Assert.AreEqual(level, Game.LevelId, "Enter loaded the next level while paused");
            Assert.AreEqual(PlayState.Won, Game.State);
            Assert.IsTrue(Game.Paused, "R or Enter closed the pause");

            yield return PressPause(false);
            Assert.IsTrue(Hud.WinVisible, "the win panel did not come back with the HUD");
            yield return Steps(10);
            Assert.AreEqual(level, Game.LevelId, "an Enter pressed during the pause acted after it");
            Assert.AreEqual(restarts, Game.Restarts, "an R pressed during the pause acted after it");

            // Control: the same presses act once the game runs.
            InputReader.InjectRestartPress();
            yield return Steps(3);
            Assert.AreEqual(restarts + 1, Game.Restarts, "control: an injected R does not restart a running game");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        [UnityTest]
        public IEnumerator Step26_PauseMenuButtons()
        {
            Assert.IsFalse(Menu.IsOpen, "premise: no menu open");
            yield return PressPause(true);
            Menu.ResumeButton.onClick.Invoke();
            Assert.IsFalse(Game.Paused, "Reprendre did not resume");
            Assert.IsFalse(Menu.IsOpen);

            yield return Steps(5);
            int restarts = Game.Restarts;
            yield return PressPause(true);
            Menu.RestartButton.onClick.Invoke();
            Assert.IsFalse(Game.Paused, "Recommencer did not resume");
            Assert.AreEqual(restarts + 1, Game.Restarts, "Recommencer did not restart the level");
            Assert.AreEqual(0f, Game.Elapsed);

            // On the first level itself: Menu principal must rebuild it, not show it as it was left (M3.1, N2).
            Assert.AreEqual(Game.LevelOrder[0], Game.LevelId, "premise: the first level is up");
            Vector3 spawn = Game.Def.Player.Position;
            Habitant.Pin(Habitant.Routine.Position, YawToward(Chair.transform.position, Habitant.Routine.Position));
            Chair.Teleport(spawn + new Vector3(0.8f, 0f, 0.4f), Chair.Yaw);
            yield return Steps(10);
            Assert.Greater(YawMath.Planar(Chair.transform.position - spawn).magnitude, 0.5f, "premise: the chair left its spawn");
            Assert.Greater(Game.Elapsed, 0f);
            yield return PressPause(true);
            Menu.MainMenuButton.onClick.Invoke();
            Assert.IsTrue(Menu.TitleOpen, "Menu principal did not open the title");
            Assert.IsFalse(Menu.PauseOpen);
            Assert.IsTrue(Game.Paused);
            Assert.AreEqual(TitleCameraTour.LevelId, Game.LevelId, "the title is not over the title house (M7 title camera)");
            Assert.Less(YawMath.Planar(Chair.transform.position - Game.Def.Player.Position).magnitude, 0.05f, "the title shows the level as it was left (chair moved)");
            Assert.AreEqual(0f, Game.Elapsed, "the title shows the level as it was left (clock)");
            Menu.PlayButton.onClick.Invoke();
            Assert.IsFalse(Game.Paused);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- The end screen -----

        [UnityTest]
        public IEnumerator Step26_EndScreenAfterTheLastLevel()
        {
            Assert.GreaterOrEqual(Game.LevelOrder.Count, 2, "premise: levels.json lists at least two levels");
            string first = Game.LevelOrder[0];
            string last = Game.LevelOrder[Game.LevelOrder.Count - 1];
            Game.LoadLevel(last);
            Game.Rules = GameRules.M2;
            yield return Steps(2);
            Assert.IsTrue(Game.IsLastLevel, "premise: the last level of levels.json is up");
            Assert.IsFalse(Game.HasNextLevel);

            yield return WinCurrentLevel();
            Assert.IsTrue(Hud.WinVisible, "no win panel after the last level");
            Assert.IsTrue(Hud.EndVisible, "the win panel is not the end screen after the last level");
            Assert.AreEqual(Strings.EndTitle, Hud.WinTitleText, "end.title missing");
            Assert.AreEqual(Strings.EndBody, Hud.WinBodyText, "end.body missing");
            Assert.IsFalse(Hud.WinNextVisible, "the end screen offers a next level");
            Assert.IsTrue(Hud.Labels.TryGetValue("EndMenuButtonLabel", out Text label) && label.text == Strings.PauseMenu,
                "the end screen button is not Menu principal");
            Assert.AreEqual(CursorLockMode.None, Cursor.lockState, "the cursor is not free on the end screen");
            yield return Until(() => EventSystem.current.currentSelectedGameObject == Hud.EndButton.gameObject, 5);
            Assert.AreEqual(Hud.EndButton.gameObject, EventSystem.current.currentSelectedGameObject, "the end button is not selected");

            // GameState leaves Enter to the selected button on the end screen (M3.1, S2).
            InputReader.InjectNextLevelPress();
            yield return Steps(5);
            Assert.AreEqual(last, Game.LevelId, "GameState acted on Enter on the end screen");
            Assert.IsTrue(Hud.EndVisible);

            // Enter submits the selected button: the editor starts the first level again, and never shows the title.
            Submit();
            yield return Until(() => Game.LevelId == first, 10);
            Assert.AreEqual(first, Game.LevelId, "Enter on the end screen did not go back to the first level");
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.IsFalse(Menu.IsOpen, "the title opened in an editor run");
            Assert.IsFalse(Hud.WinVisible);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>
        /// M3.1 (S2): the player branch, run in the editor through Menu.TitleAfterEnd. Enter on the end screen opens
        /// the title over a fresh first level, and the same frame cannot go on to Jouer: nothing is selected until the
        /// next frame, a second submit in that frame does nothing, and only then Jouer gets the selection.
        /// </summary>
        [UnityTest]
        public IEnumerator Step26_EndScreenEnterOpensTheTitleOnlyOnce()
        {
            Menu.TitleAfterEnd = true;
            string last = Game.LevelOrder[Game.LevelOrder.Count - 1];
            Game.LoadLevel(last);
            Game.Rules = GameRules.M2;
            yield return Steps(2);
            yield return WinCurrentLevel();
            Assert.IsTrue(Hud.EndVisible, "premise: the end screen is not up");
            yield return Until(() => EventSystem.current.currentSelectedGameObject == Hud.EndButton.gameObject, 5);
            Assert.AreEqual(Hud.EndButton.gameObject, EventSystem.current.currentSelectedGameObject, "premise: the end button is not selected");

            Submit();
            Assert.IsTrue(Menu.TitleOpen, "Enter on the end screen did not open the title (player branch)");
            Assert.AreEqual(TitleCameraTour.LevelId, Game.LevelId, "the title is not over the title house (M7 title camera)");
            Assert.IsTrue(Game.Paused);
            Assert.IsNull(EventSystem.current.currentSelectedGameObject, "a button of the title is selected in the frame of the Enter");
            Submit();
            InputReader.InjectNextLevelPress();
            yield return Steps(3);
            Assert.IsTrue(Menu.TitleOpen, "the Enter that opened the title also pressed Jouer");
            Assert.IsTrue(Game.Paused);
            // Menu selects on its next Update, a rendered frame: the title house is a heavy load, and the long frame it
            // makes runs several fixed steps at once, so a wait in fixed steps can end before that frame.
            for (int i = 0; i < 10 && EventSystem.current.currentSelectedGameObject != Menu.PlayButton.gameObject; i++)
            {
                yield return null;
            }
            Assert.AreEqual(Menu.PlayButton.gameObject, EventSystem.current.currentSelectedGameObject, "Jouer never got the selection");

            // Control: a later Enter does press Jouer.
            Submit();
            Assert.IsFalse(Menu.TitleOpen, "control: Enter on the selected Jouer does not start the game");
            Assert.IsFalse(Game.Paused);
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>Enter as the UI module sends it: a submit event to the selected object.</summary>
        private static void Submit()
        {
            GameObject selected = EventSystem.current.currentSelectedGameObject;
            if (selected != null)
            {
                ExecuteEvents.Execute(selected, new BaseEventData(EventSystem.current), ExecuteEvents.submitHandler);
            }
        }

        // ----- M8 touch redesign: the fail and win panels' own buttons (a phone has neither Enter nor R) -----

        /// <summary>Every button of a row is at least 140 px at 1080p, the touch target size (docs/CONTRACT_M7.md 1.5, Step63b).</summary>
        private static void AssertButtonBig(Button button, string name)
        {
            Assert.IsNotNull(button, $"no {name} button");
            var corners = new Vector3[4];
            ((RectTransform)button.transform).GetWorldCorners(corners);
            float w = (corners[2].x - corners[0].x) * 1080f / Screen.height;
            float h = (corners[2].y - corners[0].y) * 1080f / Screen.height;
            Assert.GreaterOrEqual(Mathf.Min(w, h), 140f, $"{name} is {w:0} x {h:0} px at 1080p, under 140");
        }

        /// <summary>
        /// A win with a next level: Next level is big, clickable and loads it exactly like Enter (GameState still
        /// reads Enter directly, docs/CONTRACT_M3.md 6; the button is a second, unselected way to the same call, so a
        /// click never double-fires it, Hud.WinButtonsVisible doc). Caught on the next level: Retry is big, selected
        /// by default (M3.1's pattern) and restarts the same level through its onClick, like R already does.
        /// </summary>
        [UnityTest]
        public IEnumerator Step65a_FailAndWinButtonsWorkThroughTheirOnClick()
        {
            Assert.IsTrue(Game.HasNextLevel, "premise: the first level has a next level");
            string next = Game.NextLevelId;

            yield return WinCurrentLevel();
            Assert.IsTrue(Hud.WinButtonsVisible, "the win panel's own buttons are not up");
            Assert.AreEqual(CursorLockMode.None, Cursor.lockState, "the cursor is not free for the win panel's buttons");
            AssertButtonBig(Hud.WinNextLevelButton, "WinNextLevel");
            AssertButtonBig(Hud.WinReplayButton, "WinReplay");
            AssertButtonBig(Hud.WinMenuButton, "WinMenu");

            Hud.WinNextLevelButton.onClick.Invoke();
            yield return Until(() => Game.LevelId == next, 10);
            Assert.AreEqual(next, Game.LevelId, "the Next level button did not load the next level");
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.IsFalse(Hud.WinVisible, "the win panel is still shown");

            // Caught on the new level: the chair moves right next to the inhabitant, in plain sight.
            Vector3 at = Habitant.Routine.Position;
            Vector3 near = at + new Vector3(0.8f, 0f, 0.4f);
            Chair.Teleport(near, Chair.Yaw);
            Habitant.Pin(at, YawToward(at, near));
            Chair.ScriptedDirection = Vector3.forward;
            yield return Until(() => Game.State != PlayState.Playing, 150);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "premise: the next level was not caught");
            Assert.IsTrue(Hud.FailVisible);
            Assert.AreEqual(CursorLockMode.None, Cursor.lockState, "the cursor is not free for the fail panel's buttons");
            AssertButtonBig(Hud.FailRetryButton, "FailRetry");
            AssertButtonBig(Hud.FailMenuButton, "FailMenu");
            yield return Until(() => EventSystem.current.currentSelectedGameObject == Hud.FailRetryButton.gameObject, 5);
            Assert.AreEqual(Hud.FailRetryButton.gameObject, EventSystem.current.currentSelectedGameObject, "Retry is not selected by default");

            string caughtLevel = Game.LevelId;
            int restarts = Game.Restarts;
            Hud.FailRetryButton.onClick.Invoke();
            yield return Steps(2);
            Assert.AreEqual(caughtLevel, Game.LevelId, "Retry did not keep the same level");
            Assert.AreEqual(restarts + 1, Game.Restarts, "Retry did not restart the level");
            Assert.AreEqual(PlayState.Playing, Game.State);
            Assert.IsFalse(Hud.FailVisible, "the fail panel is still shown");
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        // ----- World markers and the HUD -----

        /// <summary>
        /// M3.1 (S1): the eye and the gauges are a band at the bottom of the screen, nothing moves a marker any more,
        /// and around the chair (where the camera looks) no "?" ever reaches the band: an alerted inhabitant is stood
        /// on every floor spot of three rings around the chair, plus the spot whose marker projects where the M3
        /// band was.
        /// </summary>
        [UnityTest]
        public IEnumerator Step26_MarkersStayClearOfTheHud()
        {
            Assert.IsTrue(Hud.Visible && Hud.CreakGaugeVisible && Hud.SuspicionGaugeVisible, "premise: the HUD and its gauges show");
            Assert.IsNotNull(Hud.View, "premise: the HUD has no camera for the markers");
            yield return Steps(2);
            Rect band = Hud.BandScreenRect;
            Assert.Greater(band.width, 0f, "premise: the HUD band has no size");
            Assert.Less(band.yMax, Screen.height * 0.35f, $"the HUD band {band} is not at the bottom of the screen");
            Assert.Greater(band.width, Screen.width * 0.3f, "the band does not hold the eye and both gauges");

            Inhabitant h = Habitant;
            Vector3 chairAt = YawMath.Planar(Chair.transform.position);
            Camera cam = Hud.View;
            // Only spots on the level's floor: an inhabitant never stands outside the house, next to the lens.
            var spots = new List<Vector3>();
            foreach (float radius in new[] { 1.0f, 1.8f, 2.6f })
            {
                for (int k = 0; k < 12; k++)
                {
                    Vector3 spot = chairAt + YawMath.Forward(k * 30f) * radius;
                    if (Game.Def.RoomAt(spot) != null)
                    {
                        spots.Add(spot);
                    }
                }
            }
            Assert.GreaterOrEqual(spots.Count, 12, "premise: too few spots on the floor around the chair");
            // Where the M3 band was: the top of the screen, right of the eye.
            Ray ray = cam.ScreenPointToRay(new Vector3(Screen.width * 0.62f, Screen.height * 0.93f, 0f));
            Assert.Less(ray.direction.y, -1e-3f, "premise: the camera looks down");
            float markerHeight = 2.1f;
            float t = (markerHeight - ray.origin.y) / ray.direction.y;
            Vector3 top = YawMath.Planar(ray.origin + ray.direction * t);
            spots.Add(top);

            int shown = 0;
            foreach (Vector3 spot in spots)
            {
                h.Pin(spot, YawToward(spot, chairAt), 0f, true);
                h.Routine.Alert(chairAt, NoiseKind.Hop);
                yield return Steps(3);
                yield return null;
                Canvas marker = null;
                foreach (Canvas c in Hud.MarkerCanvases)
                {
                    if (c != null && c.enabled)
                    {
                        marker = c;
                    }
                }
                if (marker == null)
                {
                    continue;
                }
                Rect r = Hud.ScreenRectOf((RectTransform)marker.transform);
                if (r.width <= 0f)
                {
                    continue;
                }
                shown++;
                Assert.IsFalse(r.Overlaps(band), $"the marker of an inhabitant at {spot} overlaps the HUD band ({r} vs {band})");
                if (spot == top)
                {
                    Assert.Greater(r.yMin, Screen.height * 0.75f, $"the marker at the top of the screen was moved ({r})");
                }
            }
            Assert.GreaterOrEqual(shown, 10, "premise: too few markers were on screen to check");
        }

        // ----- The x-ray: where a hidden inhabitant looks -----

        /// <summary>
        /// M3.1 (B2): an inhabitant pinned in the next room, behind the shared wall, is rendered to a texture three
        /// times: looking to the camera's right, to its left, and gone. Against the empty render, the hidden body
        /// shows as the blue silhouette, and what the gaze adds (the cone over the wall and the facing chevron) lies
        /// on the side the inhabitant looks at, never mostly on the other.
        /// </summary>
        [UnityTest]
        public IEnumerator Step26_XRayShowsWhereAHiddenInhabitantLooks()
        {
            string level = null;
            foreach (string id in Game.LevelOrder)
            {
                Game.LoadLevel(id);
                if (Game.Def.AllRooms().Count >= 2)
                {
                    level = id;
                    break;
                }
            }
            Assert.IsNotNull(level, "premise: no level of levels.json has two rooms");
            Game.Rules = GameRules.M2;
            yield return Steps(2);
            RoomDef home = Game.Def.RoomAt(Chair.transform.position);
            RoomDef other = Game.Def.AllRooms().Find(r => r != home);
            Assert.IsNotNull(other, "premise: no room besides the chair's");
            Vector3 chairAt = YawMath.Planar(Chair.transform.position);
            var there = new Vector3(other.X, 0f, other.Z);
            Inhabitant h = Habitant;
            for (int i = 1; i < Game.Level.Inhabitants.Count; i++)
            {
                Game.Level.Inhabitants[i].Pin(new Vector3(90f + 5f * i, 0f, 90f), 0f);
            }
            float viewYaw = YawMath.YawOf(there - chairAt);
            Game.Camera.SetView(viewYaw, 24f);
            Camera cam = main.Camera;
            int width = 960;
            int height = Mathf.Max(1, Mathf.RoundToInt(960f * Screen.height / Mathf.Max(1, Screen.width)));

            VisionConeView cone = Game.Level.Cones.Find(c => c != null && c.Owner == h);
            Assert.IsNotNull(cone, "premise: the inhabitant has no vision cone");
            Assert.IsNotNull(cone.Facing, "premise: the cone has no facing chevron");

            h.Pin(there, viewYaw + 90f);
            yield return Settle();
            Vector3 chest = there + Vector3.up * 1.2f;
            Assert.IsTrue(Physics.Linecast(cam.transform.position, chest, Layers.OccluderMask, QueryTriggerInteraction.Ignore),
                "premise: no wall between the camera and the inhabitant");
            Color32[] right = RenderPixels(cam, width, height);
            Vector2 chevronRight = Pixel(cam, cone.Facing.position, width, height);
            float chevronRadius = Mathf.Max(6f, (Pixel(cam, cone.Facing.position + cam.transform.right * 0.32f, width, height) - chevronRight).magnitude);
            h.Pin(there, viewYaw - 90f);
            yield return Settle();
            Color32[] left = RenderPixels(cam, width, height);
            Vector2 chevronLeft = Pixel(cam, cone.Facing.position, width, height);
            h.Pin(new Vector3(90f, 0f, 90f), 0f);
            yield return Settle();
            Color32[] none = RenderPixels(cam, width, height);

            Vector2 head = Pixel(cam, there + Vector3.up * Tuning.EyeHeight, width, height);
            Vector2 feet = Pixel(cam, there, width, height);
            Vector2 side = Pixel(cam, there + Vector3.up * Tuning.EyeHeight + cam.transform.right * 0.3f, width, height);
            float halfWidth = Mathf.Max(4f, Mathf.Abs(side.x - head.x));
            var body = Rect.MinMaxRect(head.x - halfWidth, Mathf.Min(feet.y, head.y) - 2f, head.x + halfWidth, Mathf.Max(feet.y, head.y) + 8f);

            // The silhouette: blue pixels over the body, absent from the empty render.
            int blue = CountIn(right, width, height, body, c => c.b - c.r > 64);
            int blueEmpty = CountIn(none, width, height, body, c => c.b - c.r > 64);
            Assert.Greater(blue, 30, $"no silhouette over the hidden body ({blue} blue pixels in {body})");
            Assert.Less(blueEmpty * 4, blue, "the body box is blue without the inhabitant: the silhouette test proves nothing");

            // The gaze: what each render adds to the empty one, outside the body, on each side of the head.
            foreach ((Color32[] image, float sign, Vector2 chevronAt, string name) in
                new[] { (right, 1f, chevronRight, "right"), (left, -1f, chevronLeft, "left") })
            {
                Assert.Greater((chevronAt.x - head.x) * sign, 0f, $"looking {name}: the chevron is not ahead of the face");
                int toward = 0;
                int away = 0;
                var chevronPixels = new List<Vector2>();
                for (int y = 0; y < height; y++)
                {
                    for (int x = 0; x < width; x++)
                    {
                        int i = y * width + x;
                        if (Difference(image[i], none[i]) < 26)
                        {
                            continue;
                        }
                        Color32 c = image[i];
                        if ((new Vector2(x, y) - chevronAt).magnitude <= chevronRadius && c.r > 190 && c.g > 150 && c.b < 115)
                        {
                            chevronPixels.Add(new Vector2((x - chevronAt.x) * sign, y));
                        }
                        float dx = (x - head.x) * sign;
                        if (body.Contains(new Vector2(x, y)) || Mathf.Abs(dx) < 3f)
                        {
                            continue;
                        }
                        if (dx > 0f)
                        {
                            toward++;
                        }
                        else
                        {
                            away++;
                        }
                    }
                }
                Assert.Greater(toward, 60, $"looking {name}: almost nothing shows on that side ({toward} pixels)");
                Assert.Greater(toward, 3 * away, $"looking {name}: the gaze shows on the wrong side ({toward} toward, {away} away)");
                Assert.Greater(chevronPixels.Count, 15, $"looking {name}: no facing chevron drawn ({chevronPixels.Count} pixels)");

                // Which way it points: an arrowhead narrows to its tip. Across the gaze, its far quarter along the gaze
                // is much narrower than its near quarter (an arrow drawn backward fails this).
                float near = float.MaxValue;
                float far = float.MinValue;
                foreach (Vector2 q in chevronPixels)
                {
                    near = Mathf.Min(near, q.x);
                    far = Mathf.Max(far, q.x);
                }
                float quarter = (far - near) * 0.25f;
                float tip = Extent(chevronPixels, q => q.x >= far - quarter);
                float tail = Extent(chevronPixels, q => q.x <= near + quarter);
                Assert.Less(tip, tail * 0.7f,
                    $"looking {name}: the chevron does not point along the gaze ({tip:0.0} px wide at its far end, {tail:0.0} px at its near end)");
            }
            Assert.AreEqual(0, exceptions, "logged errors: " + string.Join(" | ", logged));
        }

        /// <summary>The extent across the gaze (max y minus min y) of the points that pass <paramref name="keep"/>.</summary>
        private static float Extent(List<Vector2> points, Func<Vector2, bool> keep)
        {
            float low = float.MaxValue;
            float high = float.MinValue;
            foreach (Vector2 q in points)
            {
                if (keep(q))
                {
                    low = Mathf.Min(low, q.y);
                    high = Mathf.Max(high, q.y);
                }
            }
            return high >= low ? high - low + 1f : 0f;
        }

        /// <summary>Fixed steps for the rules, then two frames so every LateUpdate (cone, chevron, head) has run.</summary>
        private static IEnumerator Settle()
        {
            yield return Steps(3);
            yield return null;
            yield return null;
        }

        private static Color32[] RenderPixels(Camera cam, int width, int height)
        {
            RenderTexture rt = RenderTexture.GetTemporary(width, height, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            Assert.IsTrue(RenderPipeline.SupportsRenderRequest(cam, request), "premise: the pipeline cannot render the camera to a texture");
            RenderPipeline.SubmitRenderRequest(cam, request);
            RenderTexture previous = RenderTexture.active;
            RenderTexture.active = rt;
            var texture = new Texture2D(width, height, TextureFormat.RGBA32, false);
            texture.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            texture.Apply();
            RenderTexture.active = previous;
            RenderTexture.ReleaseTemporary(rt);
            Color32[] pixels = texture.GetPixels32();
            UnityEngine.Object.Destroy(texture);
            return pixels;
        }

        private static Vector2 Pixel(Camera cam, Vector3 world, int width, int height)
        {
            Vector3 v = cam.WorldToViewportPoint(world);
            return new Vector2(v.x * width, v.y * height);
        }

        private static int CountIn(Color32[] pixels, int width, int height, Rect box, Func<Color32, bool> test)
        {
            int count = 0;
            for (int y = Mathf.Max(0, (int)box.yMin); y < Mathf.Min(height, (int)box.yMax); y++)
            {
                for (int x = Mathf.Max(0, (int)box.xMin); x < Mathf.Min(width, (int)box.xMax); x++)
                {
                    count += test(pixels[y * width + x]) ? 1 : 0;
                }
            }
            return count;
        }

        private static int Difference(Color32 a, Color32 b)
        {
            return Mathf.Max(Mathf.Abs(a.r - b.r), Mathf.Max(Mathf.Abs(a.g - b.g), Mathf.Abs(a.b - b.b)));
        }

        // ----- The look setup -----

        [UnityTest]
        public IEnumerator Step26_LookSetup()
        {
            List<string> problems = main.LookProblems();
            Assert.IsEmpty(problems, string.Join("\n", problems));
            Assert.AreNotEqual(0, XRay.ConeLayer, "premise: the VisionCone layer is not declared");
            Assert.IsNotEmpty(Game.Level.Cones, "premise: the level has no vision cone");
            foreach (VisionConeView cone in Game.Level.Cones)
            {
                Assert.AreEqual(XRay.ConeLayer, cone.gameObject.layer, $"{cone.name} is not on the x-ray cone layer");
            }
            foreach (Inhabitant inhabitant in Game.Level.Inhabitants)
            {
                Assert.AreEqual(Layers.Inhabitant, inhabitant.gameObject.layer, $"{inhabitant.name} is not on the Inhabitant layer");
            }
            yield return null;
        }
    }
}
