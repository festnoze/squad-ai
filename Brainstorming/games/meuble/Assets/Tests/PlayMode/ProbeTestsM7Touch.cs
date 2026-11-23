using System;
using System.Collections;
using System.Collections.Generic;
using OutOfSight.Core;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace OutOfSight.Tests
{
    /// <summary>
    /// M7 (docs/CONTRACT_M7.md 1.5), on the real Boot scene: the touch controls driven by injected fingers with
    /// <see cref="InputReader.ForceTouchUI"/> (no touchscreen in a headless run). Step63a: a drag on the left half moves
    /// the furniture like the left stick, a drag on the right half orbits the camera (sensitivity option included), a tap
    /// on the player lamp switches it (task DOORAUTO: it replaced the action button, which is gone), and the careful and
    /// pause buttons work. Step63b: the overlay is hidden with no touch and shown when forced, the controls line swaps to the
    /// touch names, and every button is at least 140 px at 1080p.
    /// Touch processing is per rendered frame (TouchControls.Update); every game wait is bounded by fixed steps.
    /// </summary>
    public sealed class ProbeTestsM7Touch
    {
        private const float Dt = Tuning.FixedStep;

        private int exceptions;
        private readonly List<string> logged = new List<string>();

        private Main main;
        private GameState Game => main.Game;
        private FurnitureController Furniture => Game.Furniture;
        private static TouchControls Touch => TouchControls.Instance;

        [UnitySetUp]
        public IEnumerator LoadBoot()
        {
            exceptions = 0;
            logged.Clear();
            GamePause.IsPaused = false;
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
            SaveStore.ResetForTests();
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

        private static IEnumerator Steps(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static int StepsFor(float seconds) => Mathf.CeilToInt(seconds / Dt);

        private static IEnumerator StepUntil(Func<bool> until, int maxSteps)
        {
            for (int i = 0; i < maxSteps && !until(); i++)
            {
                yield return new WaitForFixedUpdate();
            }
        }

        private static IEnumerator Frames(int count)
        {
            for (int i = 0; i < count; i++)
            {
                yield return null;
            }
        }

        /// <summary>Forces the touch overlay on and checks it shows (premise of every Step63a scenario).</summary>
        private IEnumerator ShowTouch()
        {
            Assert.IsNotNull(Touch, "no TouchControls in the run");
            Assert.IsFalse(Game.Paused, "premise: the game is playing after boot");
            InputReader.ForceTouchUI = true;
            yield return Frames(2);
            Assert.IsTrue(Touch.Visible, "premise: ForceTouchUI did not show the touch overlay");
        }

        /// <summary>Every inhabitant frozen where it stands, facing away from the furniture.</summary>
        private void FreezeInhabitantsAway()
        {
            Vector3 f = YawMath.Planar(Furniture.transform.position);
            foreach (Inhabitant h in Game.Level.Inhabitants)
            {
                Vector3 at = h.Routine.Position;
                h.Pin(at, YawMath.YawOf(YawMath.Planar(at) - f));
            }
        }

        /// <summary>One finger down on the centre of <paramref name="button"/> for two frames, then up.</summary>
        private static IEnumerator Tap(RectTransform button, int finger)
        {
            InputReader.InjectTouch(finger, TouchControls.ScreenCenter(button));
            yield return Frames(2);
            InputReader.ReleaseTouch(finger);
            yield return Frames(1);
        }

        // ----- 63a: the stick, the orbit and the buttons -----

        [UnityTest]
        public IEnumerator Step63a_TouchStickMovesFurniture()
        {
            yield return ShowTouch();
            FreezeInhabitantsAway();
            yield return Steps(2);
            Assert.AreEqual(Vector2.zero, InputReader.Move(), "premise: something moves the furniture before the touch");
            Vector3 start = YawMath.Planar(Furniture.transform.position);
            float yaw0 = main.OrbitCamera.Yaw;

            Vector2 land = new Vector2(Screen.width * 0.25f, Screen.height * 0.4f);
            float radius = Tuning.TouchStickRadius * Screen.height / 1080f;
            InputReader.InjectTouch(0, land);
            yield return Frames(1);
            Assert.AreEqual(Vector2.zero, InputReader.Move(), "the thumb landing alone moved the stick");
            // Past the rim, straight up: a full stick forward.
            InputReader.InjectTouch(0, land + new Vector2(0f, radius * 1.5f));
            yield return Frames(1);
            Vector2 move = InputReader.Move();
            Assert.AreEqual(0f, move.x, 0.01f, "a drag up on the left half gave a sideways stick");
            Assert.AreEqual(1f, move.y, 0.01f, "a drag up past the rim on the left half is not a full stick forward");

            yield return StepUntil(() => (YawMath.Planar(Furniture.transform.position) - start).magnitude > 0.3f, StepsFor(2f));
            float travelled = (YawMath.Planar(Furniture.transform.position) - start).magnitude;
            Assert.Greater(travelled, 0.3f, "the touch stick did not move the furniture");
            Assert.AreEqual(yaw0, main.OrbitCamera.Yaw, 0.01f, "a drag on the left half orbited the camera");

            InputReader.ReleaseTouch(0);
            yield return Frames(1);
            Assert.AreEqual(Vector2.zero, InputReader.Move(), "the stick did not center when the thumb lifted");
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step63a_TouchDragOrbitsCamera()
        {
            yield return ShowTouch();
            SaveStore.SetOptions(new SaveOptions { Sensitivity = 2.0f, Volume = 80, Cone = SaveOptions.ConeAlways });
            OrbitCamera cam = main.OrbitCamera;
            Vector2 land = new Vector2(Screen.width * 0.75f, Screen.height * 0.5f);
            InputReader.InjectTouch(1, land);
            yield return Frames(1);
            float yaw0 = cam.Yaw;
            // 100 px of a 1080 pixel high screen to the right, applied by the next frame's LateUpdate.
            InputReader.InjectTouch(1, land + new Vector2(100f * Screen.height / 1080f, 0f));
            yield return Frames(2);
            float turned = Mathf.DeltaAngle(yaw0, cam.Yaw);
            float expected = 100f * Tuning.TouchOrbitDegPerPixel * 2.0f;
            Assert.AreEqual(expected, turned, 0.5f, $"a 100 px drag on the right half at sensitivity 2 turned {turned:0.00} deg, not {expected:0.00}");
            Assert.AreEqual(Vector2.zero, InputReader.Move(), "a drag on the right half moved the stick");

            // A finger held still does not orbit.
            float held = cam.Yaw;
            yield return Frames(3);
            Assert.AreEqual(held, cam.Yaw, 0.01f, "a finger held still kept orbiting");
            InputReader.ReleaseTouch(1);
            yield return Frames(1);
            AssertClean();
        }

        [UnityTest]
        public IEnumerator Step63a_TouchButtonsActionCarefulPause()
        {
            yield return ShowTouch();
            Furniture.SetBody(BodyDef.For("floor_lamp"));
            Assert.IsNotNull(Furniture.Lamp, "premise: the lamp body has no light");
            FreezeInhabitantsAway();
            yield return Steps(2);

            // DOORAUTO: a tap on the player lamp is E: it switches the lamp. A tap away from it does not.
            bool on = Furniture.Lamp.On;
            int toggles = Furniture.ToggleCount;
            Assert.IsTrue(TouchControls.PlayerLampScreenRect(out Rect lampRect), "premise: the player lamp is not on screen");
            Vector2 away = new Vector2(lampRect.xMax < Screen.width * 0.5f ? Screen.width * 0.9f : Screen.width * 0.1f, Screen.height * 0.5f);
            Assert.IsFalse(lampRect.Contains(away), "premise: the tap away lands on the lamp");
            InputReader.InjectTouch(2, away);
            yield return Frames(2);
            InputReader.ReleaseTouch(2);
            yield return Frames(1);
            yield return Steps(StepsFor(Tuning.LampToggleTime) + 2);
            Assert.AreEqual(toggles, Furniture.ToggleCount, "a tap away from the lamp switched it");
            InputReader.InjectTouch(2, lampRect.center);
            yield return Frames(2);
            InputReader.ReleaseTouch(2);
            yield return Frames(1);
            yield return StepUntil(() => Furniture.ToggleCount != toggles && !Furniture.ActionActive, StepsFor(Tuning.LampToggleTime) + 20);
            Assert.AreEqual(toggles + 1, Furniture.ToggleCount, "a tap on the player lamp did not switch it");
            Assert.AreEqual(!on, Furniture.Lamp.On, "the lamp is not in the state the switch should give");
            Assert.AreEqual(Vector2.zero, InputReader.Move(), "a tap on the lamp moved the stick");
            // The chair has no lamp: no lamp rectangle, so a tap there is only the start press.
            Furniture.SetBody(BodyDef.For("chair"));
            Assert.IsFalse(TouchControls.PlayerLampScreenRect(out _), "a chair has a lamp rectangle");
            Furniture.SetBody(BodyDef.For("floor_lamp"));
            yield return Steps(2);

            // The careful button is a toggle.
            Assert.IsFalse(InputReader.CarefulHeld(), "premise: careful before the toggle");
            yield return Tap(Touch.CarefulButton, 3);
            Assert.IsTrue(InputReader.CarefulHeld(), "the careful button did not turn careful mode on");
            yield return Steps(2);
            Assert.IsTrue(Furniture.Careful, "careful mode did not reach the furniture");
            yield return Tap(Touch.CarefulButton, 3);
            Assert.IsFalse(InputReader.CarefulHeld(), "a second tap did not turn careful mode off");

            // The pause button pauses, and the overlay gives way to the pause menu.
            Assert.IsFalse(Game.Paused, "premise: the game is playing before the pause tap");
            yield return Tap(Touch.PauseButton, 4);
            Assert.IsTrue(Game.Paused, "the pause button did not pause");
            Assert.IsTrue(main.Menu.PauseOpen, "the pause button did not open the pause menu");
            Assert.IsFalse(Touch.Visible, "the touch overlay shows over the pause menu");
            AssertClean();
        }

        // ----- 63b: visibility, the controls line and the button sizes -----

        [UnityTest]
        public IEnumerator Step63b_OverlayHiddenWithoutTouchAndButtonsBig()
        {
            Assert.IsNotNull(Touch, "no TouchControls in the run");
            Assert.IsFalse(InputReader.ForceTouchUI, "premise: the touch overlay is forced");
            Assert.IsTrue(main.Hud.Labels.TryGetValue("Controls", out Text controls), "premise: no controls line");
            yield return Frames(2);
            Assert.IsFalse(Touch.Visible, "the touch overlay shows with no touch");
            Assert.AreEqual(Strings.HudControls, controls.text, "the controls line is not the keyboard one with no touch");

            InputReader.ForceTouchUI = true;
            yield return Frames(2);
            Assert.IsTrue(Touch.Visible, "ForceTouchUI did not show the touch overlay");
            Assert.AreEqual(Strings.HudControlsTouch, controls.text, "the controls line does not show the touch names");

            var corners = new Vector3[4];
            // DOORAUTO: no action button any more (a door is a push, the lamp a tap on itself).
            Assert.IsNull(Touch.transform.Find("TouchOverlay/ActionButton"), "the action button is still built");
            foreach (RectTransform b in new[] { Touch.CarefulButton, Touch.PauseButton })
            {
                b.GetWorldCorners(corners);
                float w = (corners[2].x - corners[0].x) * 1080f / Screen.height;
                float h = (corners[2].y - corners[0].y) * 1080f / Screen.height;
                Assert.GreaterOrEqual(Mathf.Min(w, h), 140f, $"{b.name} is {w:0} x {h:0} px at 1080p, under 140");
                Assert.IsTrue(corners[0].x >= 0f && corners[2].x <= Screen.width && corners[0].y >= 0f && corners[2].y <= Screen.height,
                    $"{b.name} is not fully on screen");
                Assert.Greater(TouchControls.ScreenCenter(b).x, Screen.width * 0.5f, $"{b.name} is not on the right");
            }
            Assert.Less(TouchControls.ScreenCenter(Touch.CarefulButton).y, Screen.height * 0.5f, "the careful button is not at the bottom");
            Assert.Greater(TouchControls.ScreenCenter(Touch.PauseButton).y, Screen.height * 0.5f, "the pause button is not at the top");

            InputReader.ForceTouchUI = false;
            yield return Frames(2);
            Assert.IsFalse(Touch.Visible, "the touch overlay stayed after touch ended");
            Assert.AreEqual(Strings.HudControls, controls.text, "the controls line kept the touch names");
            AssertClean();
        }
    }
}
