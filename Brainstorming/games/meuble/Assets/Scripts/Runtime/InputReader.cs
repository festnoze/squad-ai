using Meuble.Core;
using UnityEngine;
using UnityEngine.InputSystem;

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

        /// <summary>Right stick, for gamepad camera control.</summary>
        public static Vector2 LookStick()
        {
            Gamepad g = Gamepad.current;
            if (g == null)
            {
                return Vector2.zero;
            }
            Vector2 stick = g.rightStick.ReadValue();
            return stick.sqrMagnitude > 0.04f ? stick : Vector2.zero;
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
            if (injectedCareful)
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
            bool pressed = injectedPause;
            injectedPause = false;
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
    }
}
