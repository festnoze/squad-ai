using UnityEngine;
using UnityEngine.InputSystem;

namespace Viewpoint
{
    /// <summary>
    /// The whole input map of the game (PRD section 8), read straight from the
    /// devices of the Input System instead of an .inputactions asset: nothing has
    /// to be wired in a scene, and a PlayMode probe can drive the game without a
    /// device by raising <see cref="SimulatedInput"/>.
    ///
    /// Keys are named by PHYSICAL location (the Key enum of the Input System
    /// already is), which is what makes ZQSD and WASD both work without a layout
    /// switch.
    ///
    /// Every device access is guarded: a headless run has no keyboard and no
    /// mouse, and Keyboard.current is null there.
    /// </summary>
    public static class ViewpointInput
    {
        /// <summary>
        /// When true every reader below answers from the Simulated fields ONLY,
        /// and the real devices are ignored. Meant for the probes.
        /// </summary>
        public static bool SimulatedInput;

        // Held state. x is +1 to the right, y is +1 FORWARD (Unity convention:
        // the player controller pushes it through transform.forward).
        public static Vector2 SimulatedMove;

        /// Pixels of mouse motion for this frame, y up like the Input System.
        public static Vector2 SimulatedLook;

        /// Wheel delta for this frame, y positive when scrolling up.
        public static Vector2 SimulatedScroll;

        public static bool SimulatedJumpHeld;
        public static bool SimulatedSprintHeld;
        public static bool SimulatedRewindHeld;

        // Edge state. These are NOT consumed by a read: a probe that presses one
        // is expected to call ClearSimulatedPresses() once the frame is over.
        public static bool SimulatedJumpPressed;
        public static bool SimulatedInteractPressed;
        public static bool SimulatedFullscreenPressed;
        public static bool SimulatedStartPressed;
        public static bool SimulatedPausePressed;
        public static bool SimulatedDropPressed;
        public static bool SimulatedPlacePressed;
        public static bool SimulatedRaisePressed;
        public static bool SimulatedWheelDown;
        public static bool SimulatedWheelUp;

        /// <summary>
        /// A notch of a real wheel reports 120 on Windows and a fraction of a
        /// unit on a trackpad, so a notch is anything past a hair of noise.
        /// </summary>
        private const float WheelThreshold = 0.01f;

        /// <summary>
        /// Clears every one shot flag and every per frame delta. A probe calls
        /// this at the end of the frame in which it pressed something, exactly
        /// like a device stops reporting the press on the next frame.
        /// </summary>
        public static void ClearSimulatedPresses()
        {
            SimulatedLook = Vector2.zero;
            SimulatedScroll = Vector2.zero;
            SimulatedJumpPressed = false;
            SimulatedInteractPressed = false;
            SimulatedFullscreenPressed = false;
            SimulatedStartPressed = false;
            SimulatedPausePressed = false;
            SimulatedDropPressed = false;
            SimulatedPlacePressed = false;
            SimulatedRaisePressed = false;
            SimulatedWheelDown = false;
            SimulatedWheelUp = false;
        }

        /// <summary>
        /// Clears the simulated state completely, held actions included, and
        /// hands the game back to the real devices.
        /// </summary>
        public static void ResetSimulation()
        {
            ClearSimulatedPresses();
            SimulatedMove = Vector2.zero;
            SimulatedJumpHeld = false;
            SimulatedSprintHeld = false;
            SimulatedRewindHeld = false;
            SimulatedInput = false;
        }

        /// <summary>
        /// Raw move axes, NOT normalized: the player controller normalizes the
        /// world direction it builds from them, as the original does.
        /// </summary>
        public static Vector2 MoveVector
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedMove;
                }
                Keyboard keyboard = Keyboard.current;
                if (keyboard == null)
                {
                    return Vector2.zero;
                }
                float x = 0f;
                float y = 0f;
                if (keyboard[Key.D].isPressed)
                {
                    x += 1f;
                }
                if (keyboard[Key.A].isPressed)
                {
                    x -= 1f;
                }
                if (keyboard[Key.W].isPressed)
                {
                    y += 1f;
                }
                if (keyboard[Key.S].isPressed)
                {
                    y -= 1f;
                }
                return new Vector2(x, y);
            }
        }

        /// Mouse motion of this frame in pixels, y UP (the sign of the Input System).
        public static Vector2 LookDelta
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedLook;
                }
                Mouse mouse = Mouse.current;
                if (mouse == null)
                {
                    return Vector2.zero;
                }
                return mouse.delta.ReadValue();
            }
        }

        /// Wheel motion of this frame, y positive scrolling up.
        public static Vector2 ScrollDelta
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedScroll;
                }
                Mouse mouse = Mouse.current;
                if (mouse == null)
                {
                    return Vector2.zero;
                }
                return mouse.scroll.ReadValue();
            }
        }

        public static bool JumpHeld
        {
            get { return SimulatedInput ? SimulatedJumpHeld : KeyHeld(Key.Space); }
        }

        public static bool JumpPressed
        {
            get { return SimulatedInput ? SimulatedJumpPressed : KeyPressed(Key.Space); }
        }

        public static bool SprintHeld
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedSprintHeld;
                }
                return KeyHeld(Key.LeftShift) || KeyHeld(Key.RightShift);
            }
        }

        public static bool InteractPressed
        {
            get { return SimulatedInput ? SimulatedInteractPressed : KeyPressed(Key.E); }
        }

        public static bool RewindHeld
        {
            get { return SimulatedInput ? SimulatedRewindHeld : KeyHeld(Key.R); }
        }

        public static bool FullscreenPressed
        {
            get { return SimulatedInput ? SimulatedFullscreenPressed : KeyPressed(Key.F11); }
        }

        public static bool StartPressed
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedStartPressed;
                }
                return KeyPressed(Key.Enter) || KeyPressed(Key.NumpadEnter);
            }
        }

        public static bool PausePressed
        {
            get { return SimulatedInput ? SimulatedPausePressed : KeyPressed(Key.Escape); }
        }

        public static bool DropPressed
        {
            get { return SimulatedInput ? SimulatedDropPressed : KeyPressed(Key.F); }
        }

        public static bool PlacePressed
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedPlacePressed;
                }
                Mouse mouse = Mouse.current;
                if (mouse == null)
                {
                    return false;
                }
                return mouse.leftButton.wasPressedThisFrame;
            }
        }

        public static bool RaisePressed
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedRaisePressed;
                }
                Mouse mouse = Mouse.current;
                if (mouse == null)
                {
                    return false;
                }
                return mouse.rightButton.wasPressedThisFrame;
            }
        }

        /// Wheel down: one clockwise quarter turn of the held photo.
        public static bool WheelDown
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedWheelDown;
                }
                return ScrollDelta.y < -WheelThreshold;
            }
        }

        /// Wheel up: one counter clockwise quarter turn of the held photo.
        public static bool WheelUp
        {
            get
            {
                if (SimulatedInput)
                {
                    return SimulatedWheelUp;
                }
                return ScrollDelta.y > WheelThreshold;
            }
        }

        private static bool KeyHeld(Key key)
        {
            Keyboard keyboard = Keyboard.current;
            if (keyboard == null)
            {
                return false;
            }
            return keyboard[key].isPressed;
        }

        private static bool KeyPressed(Key key)
        {
            Keyboard keyboard = Keyboard.current;
            if (keyboard == null)
            {
                return false;
            }
            return keyboard[key].wasPressedThisFrame;
        }
    }
}
