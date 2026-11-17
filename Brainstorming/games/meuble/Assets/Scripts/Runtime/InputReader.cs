using System;
using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;

namespace Meuble
{
    /// <summary>
    /// Device reads (Input System package only). Keys are read by physical position: wKey is the key in
    /// the W position, which an AZERTY keyboard labels Z, so ZQSD works with no separate binding (PRD 9).
    /// </summary>
    public static class InputReader
    {
        /// <summary>Movement intent, x right and y forward, magnitude at most 1.</summary>
        public static Vector2 Move()
        {
            Vector2 v = Vector2.zero;
            Keyboard k = Keyboard.current;
            if (k != null)
            {
                if (k.wKey.isPressed || k.upArrowKey.isPressed) v.y += 1f;
                if (k.sKey.isPressed || k.downArrowKey.isPressed) v.y -= 1f;
                if (k.dKey.isPressed || k.rightArrowKey.isPressed) v.x += 1f;
                if (k.aKey.isPressed || k.leftArrowKey.isPressed) v.x -= 1f;
            }
            Gamepad g = Gamepad.current;
            if (g != null)
            {
                Vector2 stick = g.leftStick.ReadValue();
                if (stick.sqrMagnitude > 0.04f)
                {
                    v += stick;
                }
            }
            // M7 (CONTRACT_M7 1.5): the floating touch stick, with the left stick's dead zone.
            if (touchStick.sqrMagnitude > StickDeadZoneSq)
            {
                v += touchStick;
            }
            return Vector2.ClampMagnitude(v, 1f);
        }

        /// <summary>Mouse motion this frame in pixels (zero when the window has no focus).</summary>
        public static Vector2 LookDeltaPixels()
        {
            Mouse m = Mouse.current;
            if (m == null || !Application.isFocused)
            {
                return Vector2.zero;
            }
            return m.delta.ReadValue();
        }

        private static Vector2? injectedLookStick;

        /// <summary>
        /// Right stick, for gamepad camera control. M6 (docs/CONTRACT_M6.md 2.1): while <see cref="InjectLookStick"/>
        /// set a value (tests: the sensitivity option scales this, and there is no real gamepad in a PlayMode test),
        /// it is returned instead of a real device's; <see cref="ClearLookStick"/> (or <see cref="ResetInjections"/>)
        /// goes back to reading one.
        /// </summary>
        public static Vector2 LookStick()
        {
            if (injectedLookStick.HasValue)
            {
                return injectedLookStick.Value;
            }
            Gamepad g = Gamepad.current;
            if (g == null)
            {
                return Vector2.zero;
            }
            Vector2 stick = g.rightStick.ReadValue();
            return stick.sqrMagnitude > 0.04f ? stick : Vector2.zero;
        }

        /// <summary>Tests: the right stick reads as <paramref name="value"/> until <see cref="ClearLookStick"/>.</summary>
        public static void InjectLookStick(Vector2 value)
        {
            injectedLookStick = value;
        }

        /// <summary>Tests: the right stick goes back to reading a real device.</summary>
        public static void ClearLookStick()
        {
            injectedLookStick = null;
        }

        /// <summary>Mouse wheel notches this frame (positive away from the user).</summary>
        public static float ZoomNotches()
        {
            Mouse m = Mouse.current;
            if (m == null)
            {
                return 0f;
            }
            float y = m.scroll.ReadValue().y;
            // Windows reports 120 per notch, other platforms 1: normalize both to notches.
            return Mathf.Abs(y) >= 20f ? y / 120f : y;
        }

        // ----- M4 (docs/CONTRACT_M4.md 2 and amendment 9.7) -----
        // Careful mode is a held state, read in the fixed step. The action key (E, gamepad X = buttonWest) and the
        // move presses that right a tipped stool are edges: a press can start and end between two fixed steps, so
        // they are latched every rendered frame (LatchPresses, called from FurnitureController.Update) and consumed
        // by the next fixed step (ActionPressed, MovePressed). A press made while an action runs is dropped, never
        // queued for after it.

        // The left stick dead zone of Move(), squared.
        private const float StickDeadZoneSq = 0.04f;

        private static bool injectedAction;
        private static bool injectedCareful;
        private static bool injectedMove;
        private static bool latchedAction;
        private static bool latchedMove;
        private static bool stickWasActive;

        /// <summary>Left Shift or the gamepad left trigger held (or an injected hold): careful mode.</summary>
        public static bool CarefulHeld()
        {
            if (injectedCareful || touchCareful)
            {
                return true;
            }
            Keyboard k = Keyboard.current;
            if (k != null && k.leftShiftKey.isPressed)
            {
                return true;
            }
            Gamepad g = Gamepad.current;
            return g != null && g.leftTrigger.ReadValue() > Tuning.TriggerHeld;
        }

        /// <summary>One action press (E or gamepad X) since the last call, latched or injected. Consumes it.</summary>
        public static bool ActionPressed()
        {
            bool pressed = injectedAction || latchedAction;
            injectedAction = false;
            latchedAction = false;
            return pressed;
        }

        /// <summary>
        /// One move press since the last call: a move key pressed, the left stick leaving its dead zone, or an
        /// injected press. Consumes it. Rights a tipped stool (CONTRACT_M4 2.1).
        /// </summary>
        public static bool MovePressed()
        {
            bool pressed = injectedMove || latchedMove;
            injectedMove = false;
            latchedMove = false;
            return pressed;
        }

        public static void InjectAction()
        {
            injectedAction = true;
        }

        public static void InjectCareful(bool held)
        {
            injectedCareful = held;
        }

        /// <summary>Tests and replays: one press of a move key, read by the next <see cref="MovePressed"/>.</summary>
        public static void InjectMovePress()
        {
            injectedMove = true;
        }

        /// <summary>
        /// Latches this frame's device presses for the next fixed step. With <paramref name="ignore"/> true (an
        /// action is running, or the furniture is pinned) the presses are dropped, and so is anything latched.
        /// Called once per rendered frame by the player furniture.
        /// </summary>
        public static void LatchPresses(bool ignore)
        {
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            bool action = (k != null && k.eKey.wasPressedThisFrame) || (g != null && g.buttonWest.wasPressedThisFrame);
            bool move = k != null && (k.wKey.wasPressedThisFrame || k.sKey.wasPressedThisFrame || k.aKey.wasPressedThisFrame
                || k.dKey.wasPressedThisFrame || k.upArrowKey.wasPressedThisFrame || k.downArrowKey.wasPressedThisFrame
                || k.leftArrowKey.wasPressedThisFrame || k.rightArrowKey.wasPressedThisFrame);
            bool stick = g != null && g.leftStick.ReadValue().sqrMagnitude > StickDeadZoneSq;
            move |= stick && !stickWasActive;
            stickWasActive = stick;
            // M7: the touch action button is the E key, and the touch stick leaving its dead zone is a move press.
            action |= touchActionPending;
            touchActionPending = false;
            bool touchMove = touchStick.sqrMagnitude > StickDeadZoneSq;
            move |= touchMove && !touchStickWasActive;
            touchStickWasActive = touchMove;
            if (ignore)
            {
                latchedAction = false;
                latchedMove = false;
                injectedAction = false;
                injectedMove = false;
                return;
            }
            latchedAction |= action;
            latchedMove |= move;
        }

        /// <summary>Clears every injected input and every latched press. Called in every PlayMode TearDown (M1 to M4).</summary>
        public static void ResetInjections()
        {
            injectedAction = false;
            injectedCareful = false;
            injectedMove = false;
            injectedPause = false;
            injectedRestart = false;
            injectedNextLevel = false;
            latchedAction = false;
            latchedMove = false;
            injectedBack = false;
            // M6: menu navigation injections, the right stick override and the last device (back to the keyboard,
            // hud.controls' default).
            injectedLookStick = null;
            injectedMenuUp = false;
            injectedMenuDown = false;
            injectedMenuLeft = false;
            injectedMenuRight = false;
            injectedMenuSubmit = false;
            lastWasGamepad = false;
            // M7: the touch fingers, the touch outputs and the forced overlay.
            injectedTouches.Clear();
            touchStick = Vector2.zero;
            touchLook = Vector2.zero;
            touchCareful = false;
            touchActionPending = false;
            touchPausePending = false;
            touchStickWasActive = false;
            lastWasTouch = false;
            ForceTouchUI = false;
        }

        // ----- M5 (docs/CONTRACT_M5.md 16.12, v3 15.9): the back command, which closes the level select. -----
        private static bool injectedBack;
        // The frame whose back press was already returned: a device press stays "pressed this frame" for every call of
        // its frame, so only the first call of that frame gets it (two readers never both act on one press).
        private static int backFrame = -1;

        /// <summary>Tests: one back press, read by the next <see cref="BackPressed"/> exactly as an Escape press.</summary>
        public static void InjectBack()
        {
            injectedBack = true;
        }

        /// <summary>
        /// M5: Escape on the keyboard or B (east) on the gamepad pressed this frame, or an injected press
        /// (<see cref="InjectBack"/>). Each press counts once: an injected press is consumed, and a device press is
        /// returned by the first call of its frame only. <see cref="PausePressed"/> still reads Escape too: the Menu
        /// decides which of the two Escape means (Back while the level select is open).
        /// </summary>
        public static bool BackPressed()
        {
            int frame = Time.frameCount;
            if (injectedBack)
            {
                injectedBack = false;
                backFrame = frame;
                return true;
            }
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            bool device = (k != null && k.escapeKey.wasPressedThisFrame) || (g != null && g.buttonEast.wasPressedThisFrame);
            if (!device || backFrame == frame)
            {
                return false;
            }
            backFrame = frame;
            return true;
        }

        private static bool injectedPause;
        private static bool injectedRestart;

        /// <summary>M3: a pause press for headless tests, consumed by the next PausePressed() call.</summary>
        public static void InjectPausePress()
        {
            injectedPause = true;
        }

        /// <summary>
        /// M3 (docs/CONTRACT_M3.md 6): Escape on the keyboard or Start on the gamepad pauses and unpauses. An
        /// injected press (<see cref="InjectPausePress"/>) counts once.
        /// </summary>
        public static bool PausePressed()
        {
            bool pressed = injectedPause || touchPausePending;
            injectedPause = false;
            touchPausePending = false;
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            return pressed
                || (k != null && k.escapeKey.wasPressedThisFrame)
                || (g != null && g.startButton.wasPressedThisFrame);
        }

        /// <summary>
        /// R on the keyboard, Y (north) on the gamepad. M3: Start no longer restarts, it pauses. An injected press
        /// (<see cref="InjectRestartPress"/>) counts once.
        /// </summary>
        public static bool RestartPressed()
        {
            bool injected = injectedRestart;
            injectedRestart = false;
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            return injected
                || (k != null && k.rKey.wasPressedThisFrame)
                || (g != null && g.buttonNorth.wasPressedThisFrame);
        }

        /// <summary>M3 tests: one press of the restart command, read by the next <see cref="RestartPressed"/>.</summary>
        public static void InjectRestartPress()
        {
            injectedRestart = true;
        }

        /// <summary>
        /// M3: drops the injected restart and next level presses. A key pressed while the game is paused is lost,
        /// so an injected one must not wait for the resume either.
        /// </summary>
        public static void DiscardGameplayPresses()
        {
            injectedRestart = false;
            injectedNextLevel = false;
            // M4: an action or move press made on a menu or while paused is lost too.
            latchedAction = false;
            latchedMove = false;
            injectedAction = false;
            injectedMove = false;
            touchActionPending = false;
        }

        /// <summary>M2: Enter (main or keypad) or the gamepad south button loads the next level after a win.</summary>
        public static bool NextLevelPressed()
        {
            Keyboard k = Keyboard.current;
            Gamepad g = Gamepad.current;
            bool injected = injectedNextLevel;
            injectedNextLevel = false;
            return injected
                || (k != null && (k.enterKey.wasPressedThisFrame || k.numpadEnterKey.wasPressedThisFrame))
                || (g != null && g.buttonSouth.wasPressedThisFrame);
        }

        private static bool injectedNextLevel;

        /// <summary>
        /// Probe and tests: one press of the next level command, read by the next <see cref="NextLevelPressed"/>
        /// exactly as an Enter key press (the PlayMode tests cannot drive a keyboard device headless).
        /// </summary>
        public static void InjectNextLevelPress()
        {
            injectedNextLevel = true;
        }

        public static bool ReleaseCursorPressed()
        {
            Keyboard k = Keyboard.current;
            return k != null && k.escapeKey.wasPressedThisFrame;
        }

        public static bool CaptureCursorPressed()
        {
            Mouse m = Mouse.current;
            return m != null && m.leftButton.wasPressedThisFrame;
        }

        // ----- M6 (docs/CONTRACT_M6.md 2.2): menu navigation and the last device used. -----
        // Every real menu (Title, Pause, Options, LevelSelect) is already driven by the InputSystemUIInputModule, which
        // reads a real device's D-pad, stick, Enter and gamepad south/east directly: a human with a gamepad already
        // navigates every menu with it. These hooks exist so a PlayMode test can do the same with no real gamepad
        // device attached (the project's style: every input is read through InputReader, never a device directly, so
        // it can be injected); Menu.Update reads them and moves the EventSystem selection along the same explicit
        // Navigation links a real D-pad press would follow.

        private static bool injectedMenuUp;
        private static bool injectedMenuDown;
        private static bool injectedMenuLeft;
        private static bool injectedMenuRight;
        private static bool injectedMenuSubmit;

        public static void InjectMenuUp() => injectedMenuUp = true;
        public static void InjectMenuDown() => injectedMenuDown = true;
        public static void InjectMenuLeft() => injectedMenuLeft = true;
        public static void InjectMenuRight() => injectedMenuRight = true;

        /// <summary>Tests: one A (south) press on the selected menu widget, read by the next <see cref="MenuSubmitPressed"/>.</summary>
        public static void InjectMenuSubmit() => injectedMenuSubmit = true;

        /// <summary>
        /// One D-pad/left stick press moving the menu selection since the last call (at most one direction per call),
        /// consumed by it. Injected only: no real device is read here (see the section note above).
        /// </summary>
        public static MenuDirection MenuMovePressed()
        {
            if (injectedMenuUp) { injectedMenuUp = false; return MenuDirection.Up; }
            if (injectedMenuDown) { injectedMenuDown = false; return MenuDirection.Down; }
            if (injectedMenuLeft) { injectedMenuLeft = false; return MenuDirection.Left; }
            if (injectedMenuRight) { injectedMenuRight = false; return MenuDirection.Right; }
            return MenuDirection.None;
        }

        /// <summary>One A (south) press on the selected menu widget since the last call. Consumes it. Injected only.</summary>
        public static bool MenuSubmitPressed()
        {
            bool pressed = injectedMenuSubmit;
            injectedMenuSubmit = false;
            return pressed;
        }

        private static bool lastWasGamepad;

        /// <summary>
        /// True when the last input activity (a key, the mouse, or a gamepad control) came from a gamepad: hud.controls
        /// shows the gamepad names while this holds, the keyboard names otherwise. Updated by <see cref="PollLastDevice"/>.
        /// </summary>
        public static bool LastInputWasGamepad => lastWasGamepad;

        /// <summary>
        /// Updates which device produced the last input: a key held, mouse motion, a click or the wheel sets the
        /// keyboard/mouse; a stick past its dead zone, a trigger past Tuning.TriggerHeld, the D-pad or a face/start
        /// button sets the gamepad. Neither active keeps the last device. Called once a rendered frame (Hud.Update),
        /// so no gameplay code needs to read a device directly.
        /// </summary>
        public static void PollLastDevice()
        {
            Keyboard k = Keyboard.current;
            Mouse m = Mouse.current;
            bool keyboardMouse = (k != null && k.anyKey.isPressed)
                || (m != null && (m.delta.ReadValue().sqrMagnitude > 0.01f || m.leftButton.isPressed || m.rightButton.isPressed
                    || Mathf.Abs(m.scroll.ReadValue().y) > 0.01f));
            Gamepad g = Gamepad.current;
            bool gamepad = g != null && (g.leftStick.ReadValue().sqrMagnitude > StickDeadZoneSq
                || g.rightStick.ReadValue().sqrMagnitude > StickDeadZoneSq || g.leftTrigger.ReadValue() > Tuning.TriggerHeld
                || g.rightTrigger.ReadValue() > Tuning.TriggerHeld || g.dpad.ReadValue().sqrMagnitude > 0.01f
                || g.buttonSouth.isPressed || g.buttonNorth.isPressed || g.buttonEast.isPressed || g.buttonWest.isPressed
                || g.startButton.isPressed);
            if (keyboardMouse)
            {
                lastWasGamepad = false;
            }
            else if (gamepad)
            {
                lastWasGamepad = true;
            }
            // M7 (CONTRACT_M7 1.5): a finger on the touchscreen makes touch the active input (checked first: Windows also
            // turns a touch into mouse input); a key, the mouse or the gamepad with no finger down ends it.
            Touchscreen ts = Touchscreen.current;
            if (ts != null && ts.primaryTouch.isInProgress)
            {
                lastWasTouch = true;
            }
            else if (keyboardMouse || gamepad)
            {
                lastWasTouch = false;
            }
        }

        /// <summary>Tests: forces the last device read by <see cref="LastInputWasGamepad"/>, with no real device.</summary>
        public static void InjectLastDevice(bool gamepad)
        {
            lastWasGamepad = gamepad;
        }

        // ----- M7 (docs/CONTRACT_M7.md 1.5): touch. -----
        // TouchControls (its own overlay) reads the fingers through ReadTouches (the real Touchscreen plus the fingers a
        // test injects), turns them into a floating stick, an orbit drag and three buttons, and writes those back here.
        // The game reads them through the same calls as the keyboard and the gamepad (Move, CarefulHeld, the latched
        // action, PausePressed); the camera reads TouchLookDelta. Nothing here changes the keyboard, mouse or gamepad.

        /// <summary>A finger on the screen: its id and its position in screen pixels (origin bottom left).</summary>
        public struct TouchPoint
        {
            public int Id;
            public Vector2 Position;
        }

        private static readonly Dictionary<int, Vector2> injectedTouches = new Dictionary<int, Vector2>();
        private static Vector2 touchStick;
        private static Vector2 touchLook;
        private static bool touchCareful;
        private static bool touchActionPending;
        private static bool touchPausePending;
        private static bool touchStickWasActive;
        private static bool lastWasTouch;
        private static int touchArgument = -1;

        /// <summary>Tests: shows the touch controls with no touchscreen, as the -touch argument does in a player.</summary>
        public static bool ForceTouchUI;

        /// <summary>
        /// The touch controls show: forced (<see cref="ForceTouchUI"/>), the -touch argument, or a finger was the last
        /// input on a touchscreen (<see cref="PollLastDevice"/>).
        /// </summary>
        public static bool TouchUIActive => ForceTouchUI || lastWasTouch || HasTouchArgument; // MUTATION:TOUCH_UI_GATE

        private static bool HasTouchArgument
        {
            get
            {
                if (touchArgument < 0)
                {
                    touchArgument = Array.IndexOf(Environment.GetCommandLineArgs(), "-touch") >= 0 ? 1 : 0;
                }
                return touchArgument == 1;
            }
        }

        /// <summary>Tests: finger <paramref name="finger"/> lands on, or moves to, <paramref name="screenPosition"/> (pixels).</summary>
        public static void InjectTouch(int finger, Vector2 screenPosition)
        {
            injectedTouches[finger] = screenPosition;
        }

        /// <summary>Tests: finger <paramref name="finger"/> lifts.</summary>
        public static void ReleaseTouch(int finger)
        {
            injectedTouches.Remove(finger);
        }

        /// <summary>
        /// The fingers down this frame: the real touchscreen's (a tap that began and ended within the frame included)
        /// and the injected ones, whose ids are negative (-1 - finger) so they never meet a real touch id.
        /// </summary>
        public static void ReadTouches(List<TouchPoint> into)
        {
            into.Clear();
            Touchscreen ts = Touchscreen.current;
            if (ts != null)
            {
                foreach (TouchControl t in ts.touches)
                {
                    if (t.isInProgress || t.press.wasPressedThisFrame)
                    {
                        into.Add(new TouchPoint { Id = t.touchId.ReadValue(), Position = t.position.ReadValue() });
                    }
                }
            }
            foreach (KeyValuePair<int, Vector2> f in injectedTouches)
            {
                into.Add(new TouchPoint { Id = -1 - f.Key, Position = f.Value });
            }
        }

        /// <summary>TouchControls: the floating stick, x right and y forward, magnitude at most 1.</summary>
        public static void SetTouchStick(Vector2 value)
        {
            touchStick = Vector2.ClampMagnitude(value, 1f);
        }

        /// <summary>TouchControls: this frame's orbit drag, in pixels of a 1080 pixel high screen.</summary>
        public static void SetTouchLook(Vector2 delta)
        {
            touchLook = delta;
        }

        /// <summary>TouchControls: the careful toggle.</summary>
        public static void SetTouchCareful(bool on)
        {
            touchCareful = on;
        }

        /// <summary>TouchControls: one tap of the action button, latched as an E press by the next <see cref="LatchPresses"/>.</summary>
        public static void PressTouchAction()
        {
            touchActionPending = true;
        }

        /// <summary>TouchControls: one tap of the pause button, read by the next <see cref="PausePressed"/>.</summary>
        public static void PressTouchPause()
        {
            touchPausePending = true;
        }

        public static Vector2 TouchStick => touchStick;

        public static bool TouchCareful => touchCareful;

        /// <summary>The orbit drag of this frame, in pixels of a 1080 pixel high screen (zero with no touch).</summary>
        public static Vector2 TouchLookDelta()
        {
            return touchLook;
        }
    }

    /// <summary>M6 (docs/CONTRACT_M6.md 2.2): a menu navigation direction injected by a test (see <see cref="InputReader.MenuMovePressed"/>).</summary>
    public enum MenuDirection
    {
        None,
        Up,
        Down,
        Left,
        Right,
    }
}
