using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M6 (docs/CONTRACT_M6.md 2.1, 2.2 and 2.3), on the real Boot scene: options applied at once and surviving a
    /// level restart and a SaveStore reload (Step51a, Step51b), every menu navigated with injected gamepad input
    /// alone, no real device (Step52a), and the eye states' shapes, the edge pulse's pattern and the alerted cone's
    /// dashed outline (Step52b). Mirrors the harness of ProbeTestsM5Ui (fresh Main per test, fixed step waits).
    /// </summary>
    public sealed class ProbeTestsM6Options
    {
        private int exceptions;
        private readonly List<string> logged = new List<string>();
        private readonly List<string> tempDirs = new List<string>();

        private Main main;
        private GameState Game => main.Game;
        private Menu Menu => main.Menu;
        private Hud Hud => main.Hud;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            tempDirs.Clear();
            Application.logMessageReceived += OnLog;
            Time.timeScale = 1f;
            yield return SceneManager.LoadSceneAsync("Boot", LoadSceneMode.Single);
            yield return WaitForMain();
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
            }
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Cursor.lockState = CursorLockMode.None;
            foreach (string dir in tempDirs)
            {
                try
                {
                    Directory.Delete(dir, true);
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

        private IEnumerator WaitForMain()
        {
            int guard = 0;
            while ((Main.Instance == null || Main.Instance.Game == null || Main.Instance.Game.Level == null) && guard++ < 200)
            {
                yield return null;
            }
            main = Main.Instance;
            Assert.IsNotNull(main, "Boot scene has no Main");
            Assert.IsNotNull(Game.Level, "the level was never built");
        }

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private string NewTempDir()
        {
            string dir = Path.Combine(Path.GetTempPath(), "outofsight_options_tests_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            tempDirs.Add(dir);
            return dir;
        }

        private void AssertClean()
        {
            Assert.AreEqual(0, exceptions, "unexpected log errors: " + string.Join(" | ", logged));
        }

        // ----- 51a: options applied at once -----

        [UnityTest]
        public IEnumerator Step51a_OptionsAppliedAtOnce()
        {
            Assert.IsFalse(Menu.IsOpen, "premise: the game is playing, not on a menu, right after boot");

            // Sensitivity scales the right stick's orbit rate (over the same held real time).
            InputReader.InjectLookStick(new Vector2(1f, 0f));
            SaveStore.SetOptions(new SaveOptions { Sensitivity = 1.0f, Volume = 80, Cone = SaveOptions.ConeAlways });
            float before1 = main.OrbitCamera.Yaw;
            yield return new WaitForSecondsRealtime(0.2f);
            float delta1 = Mathf.Abs(Mathf.DeltaAngle(before1, main.OrbitCamera.Yaw));
            Assert.Greater(delta1, 0.5f, "premise: the right stick orbits the camera at sensitivity 1.0");

            SaveStore.SetOptions(new SaveOptions { Sensitivity = 2.0f, Volume = 80, Cone = SaveOptions.ConeAlways });
            float before2 = main.OrbitCamera.Yaw;
            yield return new WaitForSecondsRealtime(0.2f);
            float delta2 = Mathf.Abs(Mathf.DeltaAngle(before2, main.OrbitCamera.Yaw));
            InputReader.ClearLookStick();
            Assert.Greater(delta2, delta1 * 1.3f,
                $"sensitivity 2.0 did not scale the orbit rate (1.0 moved {delta1:0.00} deg, 2.0 moved {delta2:0.00} deg)");

            // Volume sets AudioListener.volume at once.
            SaveStore.SetOptions(new SaveOptions { Sensitivity = 1.0f, Volume = 30, Cone = SaveOptions.ConeAlways });
            Assert.AreEqual(0.3f, SaveStore.AppliedVolume, 0.01f, "the volume option was not applied to AudioListener.volume");
            SaveStore.SetOptions(new SaveOptions { Sensitivity = 1.0f, Volume = 0, Cone = SaveOptions.ConeAlways });
            Assert.AreEqual(0f, SaveStore.AppliedVolume, 0.01f);

            // "Jamais" hides every cone renderer while the eye indicator still works.
            Inhabitant h = Game.MainInhabitant;
            Assert.IsNotNull(h, "premise: the level has an inhabitant");
            VisionConeView cone = Game.Level.Cones.Find(c => c != null && c.Owner == h);
            Assert.IsNotNull(cone, "premise: the inhabitant has a cone view");

            SaveStore.SetOptions(new SaveOptions { Sensitivity = 1.0f, Volume = 80, Cone = SaveOptions.ConeAlways });
            yield return Steps(1);
            Assert.IsTrue(cone.MeshVisible, "premise: the cone renderer shows under \"Toujours\"");

            SaveStore.SetOptions(new SaveOptions { Sensitivity = 1.0f, Volume = 80, Cone = SaveOptions.ConeNever });
            yield return Steps(1);
            Assert.IsFalse(cone.MeshVisible, "\"Jamais\" did not hide the cone renderer");
            Assert.IsFalse(cone.OutlineVisible, "\"Jamais\" did not hide the alert outline with the cone");

            FurnitureController chair = Game.Furniture;
            Vector3 chairAt = YawMath.Planar(chair.transform.position);
            h.Pin(h.Routine.Position, YawMath.YawOf(chairAt - h.Routine.Position), 0f, true);
            yield return Steps(2);
            Assert.IsTrue(Game.Seen, "premise: the eye indicator's own rule must keep working while the cone is hidden");
            Assert.AreNotEqual(HudEye.Closed, Hud.Eye, "the eye indicator must still show seen while the cone is hidden");

            SaveStore.SetOptions(new SaveOptions { Sensitivity = 1.0f, Volume = 80, Cone = SaveOptions.ConeAlways });
            AssertClean();
        }

        // ----- 51b: options survive a level restart and a SaveStore reload -----

        [UnityTest]
        public IEnumerator Step51b_OptionsSurviveRestartAndReload()
        {
            string dir = NewTempDir();
            SaveStore.PathOverride = Path.Combine(dir, SaveStore.FileName);
            SaveStore.SetOptions(new SaveOptions { Sensitivity = 1.75f, Volume = 50, Cone = SaveOptions.ConeNever });
            yield return Steps(1);
            Assert.AreEqual(0.5f, SaveStore.AppliedVolume, 0.01f, "premise: the volume was applied");

            // A level restart (R, or Recommencer) never touches the options.
            Game.Restart();
            yield return Steps(2);
            Assert.AreEqual(1.75f, SaveStore.Options.Sensitivity, 1e-6f, "a restart changed the sensitivity");
            Assert.AreEqual(50, SaveStore.Options.Volume, "a restart changed the volume");
            Assert.AreEqual(SaveOptions.ConeNever, SaveStore.Options.Cone, "a restart changed the cone option");
            Assert.AreEqual(0.5f, SaveStore.AppliedVolume, 0.01f, "a restart must not reset the applied volume");

            // A fresh SaveStore.Load() (as the next run of the player would do) reads the same options back.
            SaveStore.Load();
            Assert.AreEqual(1.75f, SaveStore.Options.Sensitivity, 1e-6f, "the sensitivity did not survive a reload");
            Assert.AreEqual(50, SaveStore.Options.Volume, "the volume did not survive a reload");
            Assert.AreEqual(SaveOptions.ConeNever, SaveStore.Options.Cone, "the cone option did not survive a reload");

            AssertClean();
        }

        // ----- 52a: every menu navigable with injected gamepad input alone -----

        [UnityTest]
        public IEnumerator Step52a_MenusNavigableWithInjectedGamepadAlone()
        {
            Assert.IsFalse(Menu.IsOpen, "premise: no menu is open after boot");
            InputReader.InjectPausePress();
            yield return Steps(2);
            Assert.IsTrue(Menu.PauseOpen, "Start (gamepad) did not open the pause menu");
            Assert.AreEqual(Menu.ResumeButton.gameObject, EventSystem.current.currentSelectedGameObject, "premise: Reprendre is selected");

            // Menu.Update (a regular Update, not FixedUpdate) consumes each injected press: a plain frame wait (not
            // WaitForFixedUpdate, which resumes before that frame's own Update) lets it run.
            InputReader.InjectMenuDown();
            yield return null;
            Assert.AreEqual(Menu.RestartButton.gameObject, EventSystem.current.currentSelectedGameObject, "D-pad down from Reprendre is not Recommencer");

            InputReader.InjectMenuDown();
            yield return null;
            Assert.AreEqual(Menu.MainMenuButton.gameObject, EventSystem.current.currentSelectedGameObject, "D-pad down from Recommencer is not Menu principal");

            InputReader.InjectMenuDown();
            yield return null;
            Assert.AreEqual(Menu.PauseOptionsButton.gameObject, EventSystem.current.currentSelectedGameObject, "D-pad down from Menu principal is not Options");

            InputReader.InjectMenuSubmit();
            yield return null;
            Assert.IsTrue(Menu.OptionsOpen, "A (gamepad) on Options did not open it");
            yield return null;
            Assert.AreEqual(Menu.OptionsSensitivityButton.gameObject, EventSystem.current.currentSelectedGameObject,
                "Options did not select Sensibilité by default");

            float before = SaveStore.Options.Sensitivity;
            InputReader.InjectMenuSubmit();
            yield return null;
            Assert.Greater(Mathf.Abs(SaveStore.Options.Sensitivity - before), 0.01f, "A (gamepad) on Sensibilité did not change a value");

            InputReader.InjectBack();
            yield return null;
            Assert.IsFalse(Menu.OptionsOpen, "B (gamepad) did not leave Options");
            Assert.IsTrue(Menu.PauseOpen, "B from Options must return to the pause menu it came from, not close it");

            InputReader.InjectPausePress();
            yield return Steps(2);
            Assert.IsFalse(Menu.PauseOpen, "Start (gamepad) did not resume");

            SaveStore.ResetOptions();
            AssertClean();
        }

        // ----- 52b: the eye states' shape, the edge pattern and the alerted cone's outline -----

        [UnityTest]
        public IEnumerator Step52b_EyeShapesEdgePatternAndConeOutline()
        {
            // The three eye states differ by shape (CONTRACT_M6 2.3): closed lid, half open "?", wide open "!".
            const int w = 96, h = 56;
            float[] closed = ProceduralArt.EyeCoverage(HudEye.Closed, w, h);
            float[] calm = ProceduralArt.EyeCoverage(HudEye.Calm, w, h);
            float[] alarm = ProceduralArt.EyeCoverage(HudEye.Alarm, w, h);
            AssertDiffersByShape(closed, calm, w, h, "closed", "calm");
            AssertDiffersByShape(closed, alarm, w, h, "closed", "alarm");
            AssertDiffersByShape(calm, alarm, w, h, "calm", "alarm");

            Assert.AreEqual(HudEye.Closed, Hud.Eye, "premise: nobody watches the chair right after boot");
            Assert.IsFalse(Hud.PulsePatternVisible, "the closed state must show no pattern");

            Inhabitant inhabitant = Game.MainInhabitant;
            FurnitureController chair = Game.Furniture;
            Assert.IsNotNull(inhabitant, "premise: the level has an inhabitant");
            Vision vision = Game.Level.Visions.Find(v => v != null && v.Owner == inhabitant);
            VisionConeView cone = Game.Level.Cones.Find(c => c != null && c.Owner == inhabitant);
            Assert.IsNotNull(vision, "premise: the inhabitant has a Vision component");
            Assert.IsNotNull(cone, "premise: the inhabitant has a cone view");
            Assert.IsFalse(vision.SeesPlayer, "premise: nobody watches the chair right after boot");
            Assert.IsFalse(cone.OutlineVisible, "an unseen (not alerted) watcher's cone must show no dashed outline");

            Vector3 chairAt = YawMath.Planar(chair.transform.position);
            inhabitant.Pin(inhabitant.Routine.Position, YawMath.YawOf(chairAt - inhabitant.Routine.Position), 0f, true);
            yield return Steps(2);
            // The cone sets its outline in its LateUpdate: two fixed steps may both run within one slow frame (a loaded
            // machine), so one plain frame lets that LateUpdate read the new sight before the outline is checked.
            yield return null;
            Assert.IsTrue(Game.Seen, "premise: the inhabitant sees the still chair");
            Assert.IsTrue(vision.SeesPlayer, "premise: its own Vision test agrees");
            Assert.AreEqual(HudEye.Calm, Hud.Eye, "premise: seen and still must be calm");
            Assert.IsFalse(Hud.PulsePatternVisible, "the calm (seen, still) state must show no edge pattern");
            // VisionConeView.LateUpdate's own "alarm" (CONTRACT_M5 17) is "this watcher sees the furniture at all", the
            // same one that already turns the fan red: the dashed outline rides the very same flag, so it is on here too.
            Assert.IsTrue(cone.OutlineVisible, "a watcher that sees the furniture at all (its cone already shows red) must show the dashed outline too");

            // Seen AND moving (well under CaughtGrace's 0.20 s, so the level stays Playing): the HUD's own edge pattern,
            // tied to seenMoving specifically, switches on; the cone's outline was already on (it only sees, calm or not).
            chair.ScriptedDirection = Vector3.forward;
            yield return Steps(3);
            chair.ScriptedDirection = null;
            Assert.AreEqual(PlayState.Playing, Game.State, "premise: still playing (under the caught grace)");
            Assert.Greater(Game.SeenMoving, 0f, "premise: seen and moving must have accumulated");
            Assert.IsTrue(Hud.PulsePatternVisible, "seen moving must show the edge pattern");
            Assert.IsTrue(cone.OutlineVisible, "still seen: the cone's dashed outline must stay on");

            yield return Steps(1);
            Assert.AreEqual(0f, Game.SeenMoving, 0f, "premise: stopping resets seenMoving");
            // WaitForFixedUpdate resumes before that frame's own Update(): one more frame lets Hud.Update() read the
            // just reset seenMoving (Game.SeenMoving above already reflects it: GameState's own fixed step value).
            yield return null;
            Assert.IsFalse(Hud.PulsePatternVisible, "back to calm, the edge pattern must hide again");
            Assert.IsTrue(cone.OutlineVisible, "still watched calmly: the cone's dashed outline must still show");

            // The controls line (CONTRACT_M6 2.2): the gamepad names swap in with the last device used. A plain frame
            // (not WaitForFixedUpdate, which resumes before that frame's own Update) lets Hud.Update() read it.
            Assert.AreEqual(Strings.HudControls, Hud.Labels["Controls"].text, "premise: the keyboard controls line shows by default");
            InputReader.InjectLastDevice(true);
            yield return null;
            Assert.IsTrue(Hud.ControlsShowGamepad, "the last device (gamepad) did not swap the controls line");
            Assert.AreEqual(Strings.HudControlsGamepad, Hud.Labels["Controls"].text);
            InputReader.InjectLastDevice(false);
            yield return null;
            Assert.IsFalse(Hud.ControlsShowGamepad, "the keyboard did not swap the controls line back");
            Assert.AreEqual(Strings.HudControls, Hud.Labels["Controls"].text);

            AssertClean();
        }

        private static void AssertDiffersByShape(float[] a, float[] b, int w, int h, string nameA, string nameB)
        {
            int differ = 0;
            for (int i = 0; i < a.Length; i++)
            {
                differ += Mathf.Abs(a[i] - b[i]) > 0.5f ? 1 : 0;
            }
            Assert.Greater(differ, w * h * 3 / 100, $"the {nameA} and {nameB} eyes have the same shape ({differ} pixels differ)");
        }
    }
}
