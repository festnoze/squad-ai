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
    /// Next, idea 6 (docs/IDEAS.md QW1, task FOCUS), on the real Boot scene under GameRules.M4. The PlayMode suite runs with
    /// the auto pause off (GameState.AutoPause, set by HeldStartTestRun in ProbeTestsHeldStart.cs: TestRunCallback allows
    /// one assembly attribute), so an editor window losing focus during a run never pauses a test's level; each test here
    /// turns it on itself. The game pauses itself, pause menu open, when the
    /// window loses focus (PC, OnApplicationFocus false) or the app goes to the background (Android, OnApplicationPause
    /// true), and only then:
    /// <list type="bullet">
    /// <item>FocusPause01 (test_m5_game_robot): a focus loss in play opens the pause menu, pauses the listener and the
    /// simulation (no step, no clock, no creak, every routine and robot where it was, the chair still under an injected
    /// move vector); a second loss and the app-pause path change nothing more; the regain (focus true, app pause false)
    /// does not resume; Resume from the menu does, and the simulation counts from there.</item>
    /// <item>FocusPause02: under the title there is nothing to pause (no pause menu, no count); with the auto pause off
    /// (the probe's and batch mode's default) a focus loss in play is ignored.</item>
    /// <item>FocusPause03: a held level (the intro card, the world running under it since AUTOSTART) pauses too and its
    /// world freezes; held and paused, a move vector starts nothing; after Resume the next step with the vector is step 1
    /// (the key that came back with the window is never that start).</item>
    /// <item>FocusPause04: under the win panel and the fail panel a focus loss opens no pause menu.</item>
    /// </list>
    /// The focus events are sent to the GameState exactly as Unity would (SendMessage on its GameObject). Every wait
    /// counts fixed steps (WaitForFixedUpdate) or frames under a real time guard.
    /// </summary>
    public sealed class ProbeTestsFocusPause
    {
        private const float Dt = Tuning.FixedStep;
        private const string RobotLevel = "test_m5_game_robot";

        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private Main main;
        private GameState Game => main.Game;
        private Menu Menu => main.Menu;
        private FurnitureController Chair => Game.Furniture;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            GameState.HoldStart = false;
            GameState.AutoPause = false;
            GamePause.IsPaused = false;
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
            Assert.IsNotNull(main.Menu, "Boot scene has no Menu");
            Assert.IsNotNull(Game.Level, "the level was never built");
            if (Menu.TitleOpen)
            {
                Menu.Play();
                yield return null;
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Game.Rules = GameRules.M4;
            yield return FixedSteps(2);
        }

        [UnityTearDown]
        public IEnumerator Cleanup()
        {
            InputReader.ResetInjections();
            SaveStore.ResetForTests();
            Time.timeScale = 1f;
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            // Back to the suite's values (the run callbacks), never to the player's defaults.
            GameState.HoldStart = false;
            GameState.AutoPause = false;
            Application.logMessageReceived -= OnLog;
            if (main != null && main.Game != null && main.Game.Furniture != null)
            {
                main.Game.Furniture.ScriptedDirection = null;
                main.Game.Furniture.ScriptedCareful = null;
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

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "errors were logged: " + string.Join(" | ", logged));
        }

        private static IEnumerator FixedSteps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static IEnumerator Until(System.Func<bool> done, float seconds)
        {
            float start = Time.realtimeSinceStartup;
            while (!done() && Time.realtimeSinceStartup - start < seconds)
            {
                yield return null;
            }
        }

        private static float Planar(Vector3 a, Vector3 b) => YawMath.Planar(a - b).magnitude;

        /// <summary>The window lost focus, as Unity reports it to every behaviour of the GameState's object.</summary>
        private void LoseFocus() => Game.gameObject.SendMessage("OnApplicationFocus", false);

        private void RegainFocus() => Game.gameObject.SendMessage("OnApplicationFocus", true);

        /// <summary>The app went to the background (Android), as Unity reports it.</summary>
        private void AppPause() => Game.gameObject.SendMessage("OnApplicationPause", true);

        private void AppResume() => Game.gameObject.SendMessage("OnApplicationPause", false);

        /// <summary>The pose of every routine (planar position, body and head yaw, station, activity), in level order.</summary>
        private List<string> RoutinePoses()
        {
            var poses = new List<string>();
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                InhabitantRoutine r = h.Routine;
                poses.Add(string.Format(System.Globalization.CultureInfo.InvariantCulture, "{0}: ({1:0.00000}, {2:0.00000}) body {3:0.000} head {4:0.000} station {5} {6}",
                    h.name, r.Position.x, r.Position.z, r.BodyYaw, r.HeadYaw, r.StationIndex, r.LastActivity));
            }
            return poses;
        }

        private void AssertPausedInMenu(string when)
        {
            Assert.IsTrue(Game.Paused, when + ": the game is not paused");
            Assert.IsTrue(GamePause.IsPaused, when + ": GamePause is off");
            Assert.IsTrue(Menu.PauseOpen, when + ": the pause menu is not open");
            Assert.IsFalse(Menu.TitleOpen, when + ": the title opened");
            Assert.IsTrue(AudioListener.pause, when + ": the audio listener is not paused");
        }

        /// <summary>
        /// FocusPause01: a focus loss in play opens the pause menu and freezes the simulation; a second loss, the app-pause
        /// path and the regain change nothing; Resume from the menu resumes, and the clock counts from there.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator FocusPause01_FocusLossOpensThePauseMenuAndFreezesTheLevel()
        {
            GameState.AutoPause = true;
            Game.LoadLevel(RobotLevel);
            Game.Rules = GameRules.M4;
            Assert.IsTrue(Game.Started, "premise: the hold is off");
            Assert.GreaterOrEqual(Game.Robots.Count, 1, "premise: the level has a robot");
            Assert.GreaterOrEqual(Game.Level.Inhabitants.Count, 2, "premise: the level has two watchers");
            yield return FixedSteps(10);
            Assert.AreEqual(10, Game.Steps, "premise: the level runs before the focus loss");
            Assert.IsFalse(Menu.IsOpen, "premise: no menu is open");
            int pauses = Game.FocusPauses;

            LoseFocus();
            AssertPausedInMenu("after the focus loss");
            Assert.AreEqual(pauses + 1, Game.FocusPauses, "the focus loss was not counted once");

            int steps = Game.Steps;
            float elapsed = Game.Elapsed;
            float creak = Game.Creak.Value;
            float robotTime = Game.RobotTime;
            Vector3 chair0 = Chair.transform.position;
            List<string> poses0 = RoutinePoses();
            var robots0 = new List<Vector3>();
            foreach (Robot robot in Game.Robots)
            {
                robots0.Add(robot.transform.position);
            }
            int stepped = 0;
            void OnStep() => stepped++;
            Game.FixedStepped += OnStep;
            try
            {
                // Paused: 2 s of fixed steps under a move vector move nothing and count nothing.
                InputReader.InjectMoveVector(Vector2.up);
                yield return FixedSteps(Mathf.RoundToInt(2f / Dt));
                Assert.AreEqual(steps, Game.Steps, "paused: the clock counted steps");
                Assert.AreEqual(elapsed, Game.Elapsed, "paused: Elapsed advanced");
                Assert.AreEqual(0, stepped, "paused: FixedStepped was raised");
                Assert.AreEqual(creak, Game.Creak.Value, "paused: the creak gauge moved");
                Assert.AreEqual(robotTime, Game.RobotTime, "paused: the robot timeline advanced");
                for (int k = 0; k < robots0.Count; k++)
                {
                    Assert.Less(Planar(Game.Robots[k].transform.position, robots0[k]), 1e-5f, $"paused: robot {k} moved");
                }
                CollectionAssert.AreEqual(poses0, RoutinePoses(), "paused: a routine moved");
                Assert.Less(Planar(Chair.transform.position, chair0), 1e-6f, "paused: the chair moved under a move vector");
                Assert.AreEqual(PlayState.Playing, Game.State, "paused: the level ended");

                // A second loss, the Android path and the regains: nothing more, and no resume.
                LoseFocus();
                AppPause();
                Assert.AreEqual(pauses + 1, Game.FocusPauses, "a focus loss while paused was counted again");
                AssertPausedInMenu("after a second loss");
                RegainFocus();
                AppResume();
                yield return FixedSteps(5);
                AssertPausedInMenu("after the regain");
                Assert.AreEqual(steps, Game.Steps, "the regain resumed the level by itself");

                // Resume from the menu: the level runs again, the listener too, and the clock counts from where it stopped.
                Menu.SetPaused(false);
                Assert.IsFalse(Game.Paused, "Resume did not unpause");
                Assert.IsFalse(Menu.PauseOpen, "Resume left the pause menu open");
                Assert.IsFalse(AudioListener.pause, "Resume left the listener paused");
                yield return FixedSteps(10);
                Assert.AreEqual(steps + 10, Game.Steps, "the clock does not count from the resume");
                Assert.Greater(stepped, 0, "no step ran after the resume");
                Assert.Greater(Planar(Chair.transform.position, chair0), 1e-5f, "the chair does not drive after the resume");
                InputReader.ClearMoveVector();
            }
            finally
            {
                Game.FixedStepped -= OnStep;
                InputReader.ClearMoveVector();
                Menu.SetPaused(false);
            }
            AssertClean();
        }

        /// <summary>
        /// FocusPause02: under the title a focus loss opens no pause menu and counts nothing; with the auto pause off (the
        /// probe, --look and batch mode) a focus loss in play is ignored, the level keeps running.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator FocusPause02_NothingUnderTheTitleOrWithTheAutoPauseOff()
        {
            GameState.AutoPause = true;
            Game.LoadLevel(RobotLevel);
            Game.Rules = GameRules.M4;
            yield return FixedSteps(2);
            int pauses = Game.FocusPauses;

            Menu.ShowTitle();
            Assert.IsTrue(Menu.TitleOpen, "premise: the title is open");
            Assert.IsTrue(Game.Paused, "premise: the title pauses the game");
            LoseFocus();
            AppPause();
            Assert.IsTrue(Menu.TitleOpen, "the focus loss closed the title");
            Assert.IsFalse(Menu.PauseOpen, "the focus loss opened the pause menu under the title");
            Assert.AreEqual(pauses, Game.FocusPauses, "a focus loss under the title was counted");
            RegainFocus();
            Assert.IsTrue(Menu.TitleOpen && Game.Paused, "the regain left the title");
            Menu.Play();
            yield return null;
            Assert.IsFalse(Menu.IsOpen, "premise: Play closed the title");
            Assert.IsFalse(Game.Paused, "premise: Play unpaused");

            GameState.AutoPause = false;
            yield return FixedSteps(2);
            int steps = Game.Steps;
            LoseFocus();
            AppPause();
            Assert.IsFalse(Game.Paused, "the auto pause paused with the switch off");
            Assert.IsFalse(Menu.PauseOpen, "the auto pause opened the menu with the switch off");
            Assert.AreEqual(pauses, Game.FocusPauses, "a focus loss with the switch off was counted");
            yield return FixedSteps(10);
            Assert.AreEqual(steps + 10, Game.Steps, "the level stopped with the switch off");
            AssertClean();
        }

        /// <summary>
        /// FocusPause03: a held level pauses too: since AUTOSTART the world runs under the card, and the pause freezes it
        /// (no world step, the robot timeline and every routine where they were); held and paused a move vector starts
        /// nothing; after Resume the first step with the vector is step 1 of the clock and the world's next step, so the
        /// input that came back with the window never started the level by itself.
        /// </summary>
        [UnityTest]
        [Timeout(300000)]
        public IEnumerator FocusPause03_AHeldLevelPausesAndResumesStillHeld()
        {
            GameState.AutoPause = true;
            GameState.HoldStart = true;
            Game.LoadLevel(RobotLevel);
            Game.Rules = GameRules.M4;
            Assert.IsFalse(Game.Started, "premise: the level is held");
            yield return FixedSteps(5);
            Assert.AreEqual(0, Game.Steps, "premise: the held level's clock ran");
            Assert.AreEqual(5, Game.WorldSteps, "premise: the world does not run under the held card");
            int pauses = Game.FocusPauses;

            AppPause(); // the Android path first this time
            AssertPausedInMenu("after the app pause while held");
            Assert.AreEqual(pauses + 1, Game.FocusPauses, "the app pause was not counted once");
            Assert.IsFalse(Game.Started, "the pause started the level");
            int world = Game.WorldSteps;
            float robotTime = Game.RobotTime;
            List<string> poses0 = RoutinePoses();
            Vector3 chair0 = Chair.transform.position;

            InputReader.InjectMoveVector(Vector2.up);
            try
            {
                yield return FixedSteps(10);
                Assert.IsFalse(Game.Started, "a move vector started a paused held level");
                Assert.AreEqual(0, Game.Steps);
                Assert.AreEqual(world, Game.WorldSteps, "paused while held: the world ran");
                Assert.AreEqual(robotTime, Game.RobotTime, "paused while held: the robot timeline advanced");
                CollectionAssert.AreEqual(poses0, RoutinePoses(), "paused while held: a routine moved");
                AppResume();
                RegainFocus();
                yield return FixedSteps(5);
                Assert.IsFalse(Game.Started, "the regain started the level");
                Assert.AreEqual(world, Game.WorldSteps, "the regain resumed the world by itself");
                AssertPausedInMenu("after the regain while held");

                Menu.SetPaused(false);
                Assert.IsFalse(Game.Started, "Resume itself started the level");
                yield return FixedSteps(1);
                Assert.IsTrue(Game.Started, "the first move step after Resume did not start the level");
                Assert.AreEqual(1, Game.Steps, "the first step after Resume is not step 1");
                Assert.AreEqual(world + 1, Game.WorldSteps, "the first step after Resume is not the world's next step");
                Assert.AreEqual(Dt, Game.Elapsed, 1e-6f, "Elapsed does not count from the first input");
                Assert.Greater(Planar(Chair.transform.position, chair0), 1e-5f, "the chair did not take the first input");
            }
            finally
            {
                InputReader.ClearMoveVector();
                Menu.SetPaused(false);
            }
            GameState.HoldStart = false;
            AssertClean();
        }

        /// <summary>FocusPause04: under the win panel and under the fail panel a focus loss opens no pause menu.</summary>
        [UnityTest]
        [Timeout(600000)]
        public IEnumerator FocusPause04_NothingUnderAnEndPanel()
        {
            GameState.AutoPause = true;
            Game.LoadLevel("level1");
            Game.Rules = GameRules.M4;
            yield return FixedSteps(2);
            int pauses = Game.FocusPauses;

            // The win: every inhabitant pinned facing away from the exit, the chair driven into it (ProbeTestsEndPanel's way).
            ZoneDef exit = Game.Def.Exit;
            var exitCenter = new Vector3(exit.X, 0f, exit.Z);
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Vector3 at = h.Routine.Position;
                h.Pin(at, YawMath.YawOf(at - exitCenter));
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
            yield return Until(() => Game.State != PlayState.Playing, 150f);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Won, Game.State, "premise: level1 was not won");
            yield return Until(() => main.Hud.WinVisible, 10f);
            Assert.IsTrue(main.Hud.WinVisible, "premise: the win panel is not up");

            LoseFocus();
            AppPause();
            Assert.IsFalse(Menu.PauseOpen, "the focus loss opened the pause menu under the win panel");
            Assert.IsFalse(Game.Paused, "the focus loss paused under the win panel");
            Assert.AreEqual(pauses, Game.FocusPauses, "a focus loss under the win panel was counted");
            Assert.AreEqual(PlayState.Won, Game.State, "the focus loss changed the end state");

            // The catch: the chair driven in front of a pinned watcher (ProbeTestsEndPanel's way).
            Game.Restart();
            Game.Rules = GameRules.M4;
            yield return FixedSteps(2);
            Inhabitant watcher = Game.MainInhabitant;
            Assert.IsNotNull(watcher, "premise: level1 has an inhabitant");
            Vector3 wAt = watcher.Routine.Position;
            Vector3 near = wAt + new Vector3(0.8f, 0f, 0.4f);
            Chair.Teleport(near, Chair.Yaw);
            watcher.Pin(wAt, YawMath.YawOf(YawMath.Planar(near - wAt)));
            Chair.ScriptedDirection = Vector3.forward;
            yield return Until(() => Game.State != PlayState.Playing, 150f);
            Chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Caught, Game.State, "premise: the restart was not caught");
            yield return Until(() => main.Hud.FailVisible, 10f);
            Assert.IsTrue(main.Hud.FailVisible, "premise: the fail panel is not up");

            LoseFocus();
            AppPause();
            Assert.IsFalse(Menu.PauseOpen, "the focus loss opened the pause menu under the fail panel");
            Assert.IsFalse(Game.Paused, "the focus loss paused under the fail panel");
            Assert.AreEqual(pauses, Game.FocusPauses, "a focus loss under the fail panel was counted");
            AssertClean();
        }
    }
}
