// Owned by B3. PlayMode tests of contract 13 with the Input System test fixture (virtual devices, events processed by
// the player loop): keyboard 8 directions write HumanController.Desired and release the ready gate, Escape toggles the
// pause and leaving it re-arms the gate; mouse drag (dead zone, press-frame ownership) and hover arming (8 px); touch
// floating stick with steering finger ownership. Also checks the main camera of contract 14 follows the human.
// Other packages may log while they are being built: this test only fails on errors logged by SteeringInput / CameraRig.
using System;
using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using PainterIO.Runtime;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace PainterIO.Tests
{
    public class SteeringInputPlayTests : InputTestFixture
    {
        private const double Tolerance = 1e-4;
        private GameObject game;
        private readonly List<string> ownErrors = new List<string>();

        [UnitySetUp]
        public IEnumerator SetUpGame()
        {
            ownErrors.Clear();
            if (GameDirector.Instance != null)
            {
                UnityEngine.Object.Destroy(GameDirector.Instance.gameObject);
                yield return null;
            }
            Application.logMessageReceived += OnLog;
        }

        [UnityTearDown]
        public IEnumerator TearDownGame()
        {
            Application.logMessageReceived -= OnLog;
            if (game != null) UnityEngine.Object.Destroy(game);
            game = null;
            yield return null;
        }

        private void OnLog(string condition, string stackTrace, LogType type)
        {
            if (type != LogType.Error && type != LogType.Exception && type != LogType.Assert) return;
            if (condition.Contains("SteeringInput") || condition.Contains("CameraRig") || condition.Contains("MenuBackPressed"))
            {
                ownErrors.Add(type + ": " + condition);
            }
        }

        private GameDirector Boot()
        {
            game = new GameObject("Game");
            return game.AddComponent<GameDirector>();
        }

        private IEnumerator StartRealRound(GameDirector d)
        {
            yield return null;
            d.StartRound();
            yield return null;
            Assert.AreEqual(GameState.Playing, d.State);
            Assert.IsNotNull(d.Session.HumanController, "a real round has an ExternalController");
        }

        /// <summary>Diagnostic: the UI objects (and whether they are Selectables) under a screen point.</summary>
        private static string UiHitsAt(Vector2 pos)
        {
            EventSystem es = EventSystem.current;
            if (es == null) return "no EventSystem";
            var hits = new List<RaycastResult>();
            es.RaycastAll(new PointerEventData(es) { position = pos }, hits);
            if (hits.Count == 0) return "none";
            var names = new List<string>();
            foreach (RaycastResult h in hits)
            {
                if (h.gameObject == null) continue;
                names.Add(h.gameObject.name + (h.gameObject.GetComponentInParent<Selectable>() != null ? " (Selectable)" : ""));
            }
            return string.Join(", ", names);
        }

        private static void AssertHeading(double expected, double? actual, string what)
        {
            Assert.IsTrue(actual.HasValue, what + ": Desired was written");
            Assert.That(Math.Abs(Math.IEEERemainder(actual.Value - expected, 2.0 * Math.PI)), Is.LessThan(Tolerance),
                        what + ": expected " + expected + ", got " + actual.Value);
        }

        // ------------------------------------------------------------------------------------------------------------

        [UnityTest]
        public IEnumerator Keyboard_EightDirectionsReleaseTheGateAndEscapeTogglesThePause()
        {
            LogAssert.ignoreFailingMessages = true;
            Keyboard keyboard = InputSystem.AddDevice<Keyboard>();
            GameDirector d = Boot();
            yield return StartRealRound(d);
            GameSession s = d.Session;
            yield return null;
            Assert.IsNull(s.HumanController.Desired, "no input, no write");
            Assert.IsNotNull(SteeringInput.Current, "SteeringInput built");
            bool gateWasClosed = s.AwaitingStart;

            Press(keyboard.rightArrowKey);
            yield return null;
            AssertHeading(0.0, s.HumanController.Desired, "right arrow");
            Assert.AreEqual(SteeringDevice.Keyboard, SteeringInput.Current.ActiveDevice);
            if (gateWasClosed) Assert.IsFalse(s.AwaitingStart, "the first write released the ready gate");
            else Debug.Log("[SteeringInputPlayTests] the gate had auto-started before the first key (slow frame)");

            Press(keyboard.wKey);
            yield return null;
            AssertHeading(Math.PI * 0.25, s.HumanController.Desired, "right + W");

            Release(keyboard.rightArrowKey);
            Release(keyboard.wKey);
            yield return null;
            yield return null;
            AssertHeading(Math.PI * 0.25, s.HumanController.Desired, "released keys keep the course");
            Assert.IsNull(SteeringInput.Current.LastWrittenHeading, "nothing written without input");

            Press(keyboard.downArrowKey);
            Press(keyboard.leftArrowKey);
            yield return null;
            AssertHeading(-Math.PI * 0.75, s.HumanController.Desired, "down-left");
            Release(keyboard.downArrowKey);
            Release(keyboard.leftArrowKey);
            yield return null;

            // Escape pauses, Escape again leaves the pause through the ready gate.
            Press(keyboard.escapeKey);
            yield return null;
            Release(keyboard.escapeKey);
            yield return null;
            Assert.IsTrue(d.IsPaused, "Escape paused the round");
            Assert.IsTrue(s.Runner.Paused);

            Press(keyboard.escapeKey);
            yield return null;
            Release(keyboard.escapeKey);
            yield return null;
            Assert.IsFalse(d.IsPaused, "Escape resumed");
            Assert.IsTrue(s.AwaitingStart, "back to the ready gate");
            Assert.IsNull(s.HumanController.Desired, "waits for a new deliberate input");

            Press(keyboard.aKey);
            yield return null;
            AssertHeading(Math.PI, s.HumanController.Desired, "A (west)");
            Assert.IsFalse(s.AwaitingStart, "the input released the gate after the pause");
            Release(keyboard.aKey);
            yield return null;

            // Escape on the results screen goes to the menu; in the menu it raises MenuBackPressed.
            int menuBacks = 0;
            Action onBack = () => menuBacks++;
            SteeringInput.MenuBackPressed += onBack;
            try
            {
                d.ToMenu();
                yield return null;
                Assert.AreEqual(GameState.Menu, d.State);
                Press(keyboard.escapeKey);
                yield return null;
                Release(keyboard.escapeKey);
                yield return null;
                Assert.AreEqual(1, menuBacks, "Escape in the menu asks for the quit panel");
                Assert.AreEqual(GameState.Menu, d.State, "and does not leave the menu");
                if (UiRoot.Instance != null) Assert.IsTrue(UiRoot.Instance.IsQuitPanelOpen, "the quit panel opened once (not toggled twice)");
            }
            finally
            {
                SteeringInput.MenuBackPressed -= onBack;
            }
            Assert.IsEmpty(ownErrors, string.Join("\n", ownErrors));
        }

        [UnityTest]
        public IEnumerator Mouse_DragSteersAndHoverArmsAfterEightPixels()
        {
            LogAssert.ignoreFailingMessages = true;
            Mouse mouse = InputSystem.AddDevice<Mouse>();
            var start = new Vector2(Mathf.Max(200f, Screen.width * 0.5f), Mathf.Max(200f, Screen.height * 0.4f));
            Set(mouse.position, start);
            GameDirector d = Boot();
            yield return StartRealRound(d);
            GameSession s = d.Session;
            yield return null;

            // Hover is not armed: a 5 px move writes nothing.
            Set(mouse.position, start + new Vector2(5f, 0f));
            yield return null;
            yield return null;
            Assert.IsNull(s.HumanController.Desired, "hover arms only after 8 px");

            // Left-button drag: the press anchors, the dead zone holds, then the heading follows the drag.
            Press(mouse.leftButton);
            yield return null;
            Assert.AreEqual(SteeringDevice.MouseDrag, SteeringInput.Current.ActiveDevice, "the press took ownership");
            Assert.IsNull(s.HumanController.Desired, "a press alone does not steer");
            Set(mouse.position, start + new Vector2(5f, 2f));
            yield return null;
            Assert.IsNull(s.HumanController.Desired, "inside the dead zone");
            Set(mouse.position, start + new Vector2(5f, 80f));
            yield return null;
            AssertHeading(Math.PI * 0.5, s.HumanController.Desired, "drag up");
            Set(mouse.position, start + new Vector2(-60f, 80f));
            yield return null;
            double? afterLeash = s.HumanController.Desired;
            Assert.IsTrue(afterLeash.HasValue);
            Assert.That(afterLeash.Value, Is.GreaterThan(Math.PI * 0.5 + 0.3), "the leashed anchor makes the drag turn left at once");
            Release(mouse.leftButton);
            yield return null;
            double kept = s.HumanController.Desired.Value;
            yield return null;
            Assert.AreEqual(kept, s.HumanController.Desired.Value, 1e-9, "release keeps the course (no hover before 8 px)");

            // Hover: once the cursor moved 8 px it owns Desired and heads the pawn toward the cursor.
            Camera cam = CameraRig.Current != null ? CameraRig.Current.Camera : null;
            Assert.IsNotNull(cam, "main camera");
            if (cam.pixelHeight <= 0 || cam.pixelWidth <= 0)
            {
                Debug.Log("[SteeringInputPlayTests] no game view size in this run: hover direction check skipped");
            }
            else
            {
                Vector2 far = new Vector2(2f, 2f);   // bottom-left corner of the screen, far from the centered pawn
                Set(mouse.position, far);
                yield return null;
                Assert.AreEqual(SteeringDevice.Hover, SteeringInput.Current.ActiveDevice, "hover armed");
                Vector2 pawn = s.RenderPos(s.HumanIndex);
                Vector3 screen = cam.WorldToScreenPoint(new Vector3(pawn.x, pawn.y, 0f));
                double expected = Math.Atan2(far.y - screen.y, far.x - screen.x);
                Assert.IsTrue(s.HumanController.Desired.HasValue);
                Assert.That(Math.Abs(Math.IEEERemainder(s.HumanController.Desired.Value - expected, 2.0 * Math.PI)), Is.LessThan(0.05),
                            "heads toward the cursor");
            }
            Assert.IsEmpty(ownErrors, string.Join("\n", ownErrors));
        }

        [UnityTest]
        public IEnumerator Touch_FloatingStickOwnsTheFirstFingerOnly()
        {
            LogAssert.ignoreFailingMessages = true;
            InputSystem.AddDevice<Touchscreen>();
            var p0 = new Vector2(Mathf.Max(200f, Screen.width * 0.5f), Mathf.Max(300f, Screen.height * 0.3f));
            GameDirector d = Boot();
            yield return StartRealRound(d);
            GameSession s = d.Session;
            yield return null;

            Assert.IsNotNull(Touchscreen.current, "virtual touchscreen");
            string uiAtPress = UiHitsAt(p0);
            BeginTouch(1, p0);
            yield return null;
            Assert.AreEqual(SteeringDevice.Touch, SteeringInput.Current.ActiveDevice,
                            "the first finger steers (press at " + p0 + ", screen " + Screen.width + "x" + Screen.height + ", UI hits: " + uiAtPress + ")");
            Assert.IsTrue(SteeringInput.Current.HasSteeringPointer);
            Assert.IsNull(s.HumanController.Desired, "a press alone does not steer");

            MoveTouch(1, p0 + new Vector2(0f, -100f));
            yield return null;
            AssertHeading(-Math.PI * 0.5, s.HumanController.Desired, "swipe down");

            // A second finger is ignored while the first one steers, and for its whole lifetime.
            BeginTouch(2, p0 + new Vector2(150f, 0f));
            yield return null;
            MoveTouch(2, p0 + new Vector2(150f, 150f));
            yield return null;
            AssertHeading(-Math.PI * 0.5, s.HumanController.Desired, "second finger ignored");

            // The leash: the anchor is 0.20 in behind the finger, so a small move back up turns the pawn north.
            float leash = SteeringInput.InchesToPixels(SteeringInput.MaxRadiusInches, Screen.dpi);
            MoveTouch(1, p0 + new Vector2(0f, -100f + leash + 20f));
            yield return null;
            AssertHeading(Math.PI * 0.5, s.HumanController.Desired, "reversal after the leash");

            EndTouch(1, p0 + new Vector2(0f, -100f + leash + 20f));
            yield return null;
            Assert.IsFalse(SteeringInput.Current.HasSteeringPointer, "finger lifted");
            MoveTouch(2, p0 + new Vector2(150f, 400f));
            yield return null;
            MoveTouch(2, p0 + new Vector2(-150f, 400f));
            yield return null;
            AssertHeading(Math.PI * 0.5, s.HumanController.Desired, "the second finger never steers; lifting kept the course");
            EndTouch(2, p0 + new Vector2(-150f, 400f));
            yield return null;

            // A new finger becomes the steering finger again.
            BeginTouch(3, p0);
            yield return null;
            MoveTouch(3, p0 + new Vector2(100f, 0f));
            yield return null;
            AssertHeading(0.0, s.HumanController.Desired, "new steering finger");
            EndTouch(3, p0 + new Vector2(100f, 0f));
            yield return null;
            Assert.IsEmpty(ownErrors, string.Join("\n", ownErrors));
        }

        [UnityTest]
        public IEnumerator Camera_FollowsTheHumanWithTheContractView()
        {
            LogAssert.ignoreFailingMessages = true;
            Keyboard keyboard = InputSystem.AddDevice<Keyboard>();
            GameDirector d = Boot();
            yield return StartRealRound(d);
            GameSession s = d.Session;
            yield return null;
            CameraRig rig = CameraRig.Current;
            Assert.IsNotNull(rig);
            Camera cam = rig.Camera;
            Assert.IsTrue(cam.orthographic);
            Assert.AreEqual(-50f, cam.transform.position.z, 1e-4f);
            Assert.AreEqual(0, cam.cullingMask & (1 << LiquidLayers.Field), "the field layer is never drawn by the main camera");
            Assert.AreEqual(CameraRig.BaseOrthoSize(cam.aspect), cam.orthographicSize, 1e-3f, "base view at rest");
            Vector2 human = s.RenderPos(s.HumanIndex);
            Assert.IsTrue(rig.ViewRect.Contains(human), "the human is in view at the round start");

            Press(keyboard.upArrowKey);
            float t0 = Time.realtimeSinceStartup;
            while (s.Sim.Time < 1.5 && Time.realtimeSinceStartup - t0 < 10f) yield return null;
            Release(keyboard.upArrowKey);
            yield return null;
            human = s.RenderPos(s.HumanIndex);
            Rect view = rig.ViewRect;
            Assert.IsTrue(view.Contains(human), "the camera keeps up with the human");
            Assert.That(Vector2.Distance(view.center, human), Is.LessThan(CameraRig.LookaheadDistance + 1.5f), "close follow");
            Assert.That(view.xMin, Is.GreaterThanOrEqualTo(-36.01f));
            Assert.That(view.yMin, Is.GreaterThanOrEqualTo(-36.01f));
            Assert.IsEmpty(ownErrors, string.Join("\n", ownErrors));
        }
    }
}
