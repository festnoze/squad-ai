using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// SPECTATOR (docs/next/progress/SPECTATOR.md): the free camera of a level watched in spectator mode
    /// (GameState.Spectator). It flies through the house with no collision at all (it moves its transform, it has no
    /// collider and casts nothing), so it goes through walls, ceilings and props. It lives on the game camera next to the
    /// <see cref="OrbitCamera"/>, which it disables while active and hands back (snapped) at <see cref="End"/>.
    /// <list type="bullet">
    /// <item>Keyboard and mouse: WASD/ZQSD or the arrows fly along the view (physical keys, so both layouts work), Space or
    /// E up, Ctrl or Q (A on AZERTY) down, Shift faster, the wheel scales the speed; the mouse looks while the cursor is
    /// captured (as the game camera) or while the right button is held.</item>
    /// <item>Gamepad: left stick flies, right stick looks, right trigger up, left trigger down, left stick press faster.</item>
    /// <item>Touch (TouchControls' overlay): the left thumb stick flies, a drag on the right half looks, a two-finger pinch
    /// goes up (spread) or down (pinch in).</item>
    /// </list>
    /// It starts at the pose the orbit camera has after the build, so the switch is seamless. It holds still while the
    /// game is paused. The level's WallFader gets the camera itself as its target (as the title tour does): no shared wall
    /// ever separates the camera from itself, so inside the house nothing is lowered and nothing flickers; outer walls still
    /// get out of the way when the camera is outside them. RoomCeilings already follows the camera's height.
    /// </summary>
    [DefaultExecutionOrder(260)] // after OrbitCamera (200) and TitleCameraTour (250), before WallFader (300) and RoomCeilings (310)
    public sealed class SpectatorCamera : MonoBehaviour
    {
        /// <summary>Flying speed at the start of a session, metres per second.</summary>
        public const float BaseSpeed = 3f;

        /// <summary>Speed bounds the wheel can reach, metres per second.</summary>
        public const float MinSpeed = 0.5f;
        public const float MaxSpeed = 15f;

        /// <summary>Speed factor per wheel notch.</summary>
        public const float WheelStep = 1.25f;

        /// <summary>Speed factor while Shift (or the left stick press) is held.</summary>
        public const float FastFactor = 3f;

        /// <summary>Metres up per pixel (of a 1080 pixel high screen) the two pinched fingers spread apart.</summary>
        public const float PinchMetresPerPixel = 0.012f;

        /// <summary>How far outside the house's interior box the camera may fly, metres.</summary>
        public const float BoundsMargin = 12f;

        /// <summary>The camera's height range, metres.</summary>
        public const float MinHeight = -1f;
        public const float MaxHeight = 25f;

        /// <summary>The view's pitch range, degrees (positive looks down, as the orbit camera's).</summary>
        public const float PitchLimit = 85f;

        /// <summary>The free camera drives the game camera now.</summary>
        public bool Active { get; private set; }

        /// <summary>Current flying speed (before the Shift factor), metres per second.</summary>
        public float Speed { get; private set; } = BaseSpeed;

        public float Yaw { get; private set; }
        public float Pitch { get; private set; }

        private GameState game;
        private OrbitCamera orbit;
        private Rect area;
        private bool hasArea;
        private readonly List<InputReader.TouchPoint> touches = new List<InputReader.TouchPoint>();
        private int pinchA = int.MinValue;
        private int pinchB = int.MinValue;
        private float pinchLast;

        /// <summary>
        /// Takes over the camera for a spectator session of the level <paramref name="state"/> just built, from the pose the
        /// orbit camera has now. Called by GameState at every spectator build (a restart included).
        /// </summary>
        public void Begin(GameState state, OrbitCamera orbitCamera)
        {
            game = state;
            orbit = orbitCamera;
            if (orbit != null)
            {
                orbit.enabled = false;
            }
            Vector3 euler = transform.rotation.eulerAngles;
            Yaw = euler.y;
            Pitch = Mathf.Clamp(Mathf.DeltaAngle(0f, euler.x), -PitchLimit, PitchLimit);
            Speed = BaseSpeed;
            pinchA = pinchB = int.MinValue;
            hasArea = false;
            if (game != null && game.Level != null)
            {
                if (game.Def != null)
                {
                    area = game.Def.InteriorBounds();
                    hasArea = area.width > 0f && area.height > 0f;
                }
                WallFader fader = game.Level.Root != null ? game.Level.Root.GetComponent<WallFader>() : null;
                if (fader != null)
                {
                    // The camera and the "player" on the same side of every wall plane: only the outer walls the camera
                    // stands outside of get out of the way (the title tour's rule).
                    fader.Target = transform;
                    fader.Furniture = null;
                }
            }
            Active = true;
        }

        /// <summary>Tests and tools: puts the free camera at <paramref name="position"/>, looking along yaw and pitch (degrees).</summary>
        public void SetPose(Vector3 position, float yaw, float pitch)
        {
            Yaw = yaw;
            Pitch = Mathf.Clamp(pitch, -PitchLimit, PitchLimit);
            transform.SetPositionAndRotation(Clamp(position), Quaternion.Euler(Pitch, Yaw, 0f));
        }

        /// <summary>Hands the camera back to the orbit camera (a level built without spectator mode). Nothing when inactive.</summary>
        public void End()
        {
            if (!Active)
            {
                return;
            }
            Active = false;
            game = null;
            if (orbit != null)
            {
                orbit.enabled = true;
                orbit.Snap();
            }
        }

        private void LateUpdate()
        {
            if (!Active)
            {
                return;
            }
            if (game == null || game.Level == null || !game.Spectator)
            {
                End();
                return;
            }
            if (GamePause.IsPaused)
            {
                pinchA = pinchB = int.MinValue;
                return;
            }
            Step(Time.unscaledDeltaTime);
        }

        /// <summary>One frame of the free camera: look, then fly, then the pose.</summary>
        private void Step(float dt)
        {
            bool input = false;
            float sens = SaveStore.Options.Sensitivity;

            // Look: the mouse (captured, or with the right button held), the right stick, the touch drag.
            if (Cursor.lockState == CursorLockMode.Locked || InputReader.LookButtonHeld())
            {
                Vector2 mouse = InputReader.LookDeltaPixels();
                if (mouse.sqrMagnitude > 0f)
                {
                    Yaw += mouse.x * Tuning.MouseSensitivity * sens;
                    Pitch -= mouse.y * Tuning.MouseSensitivity * sens;
                    input = true;
                }
            }
            Vector2 stick = InputReader.LookStick();
            if (stick.sqrMagnitude > 0f)
            {
                Yaw += stick.x * 140f * sens * dt;
                Pitch -= stick.y * 90f * sens * dt;
                input = true;
            }
            float pinch = ReadPinch();
            if (pinchA == int.MinValue)
            {
                // No pinch: a one-finger drag on the right half looks (two fingers never also turn the view).
                Vector2 drag = InputReader.TouchLookDelta();
                if (drag.sqrMagnitude > 0f)
                {
                    Yaw += drag.x * Tuning.TouchOrbitDegPerPixel * sens;
                    Pitch -= drag.y * Tuning.TouchOrbitDegPerPixel * sens;
                    input = true;
                }
            }
            Pitch = Mathf.Clamp(Pitch, -PitchLimit, PitchLimit);

            // Speed: the wheel scales it, Shift multiplies it.
            float notches = InputReader.ZoomNotches();
            if (Mathf.Abs(notches) > 0.01f)
            {
                Speed = Mathf.Clamp(Speed * Mathf.Pow(WheelStep, notches), MinSpeed, MaxSpeed);
                input = true;
            }
            float speed = Speed * (InputReader.SpectatorFast() ? FastFactor : 1f);

            // Fly along the view (pitch included), up and down along the world's vertical.
            Quaternion view = Quaternion.Euler(Pitch, Yaw, 0f);
            Vector2 move = InputReader.Move();
            float vertical = InputReader.SpectatorVertical();
            Vector3 position = transform.position;
            if (move.sqrMagnitude > 0f || Mathf.Abs(vertical) > 0f)
            {
                Vector3 direction = view * new Vector3(move.x, 0f, move.y) + Vector3.up * vertical;
                position += Vector3.ClampMagnitude(direction, 1f) * speed * dt;
                input = true;
            }
            if (Mathf.Abs(pinch) > 0f)
            {
                position.y += pinch;
                input = true;
            }
            position = Clamp(position);
            transform.SetPositionAndRotation(position, view);
            if (input)
            {
                game.DismissSpectatorCard();
            }
        }

        /// <summary>The camera's position kept over the house: its interior box grown by <see cref="BoundsMargin"/>, and the height range.</summary>
        private Vector3 Clamp(Vector3 p)
        {
            if (hasArea)
            {
                p.x = Mathf.Clamp(p.x, area.xMin - BoundsMargin, area.xMax + BoundsMargin);
                p.z = Mathf.Clamp(p.z, area.yMin - BoundsMargin, area.yMax + BoundsMargin);
            }
            p.y = Mathf.Clamp(p.y, MinHeight, MaxHeight);
            return p;
        }

        /// <summary>
        /// This frame's vertical move from a two-finger pinch, metres (spread apart: up). Zero with fewer than two fingers;
        /// the first frame of a pinch only records the distance.
        /// </summary>
        private float ReadPinch()
        {
            InputReader.ReadTouches(touches);
            if (touches.Count < 2)
            {
                pinchA = pinchB = int.MinValue;
                return 0f;
            }
            InputReader.TouchPoint a = touches[0];
            InputReader.TouchPoint b = touches[1];
            float scale = Mathf.Max(1f, Screen.height) / 1080f;
            float distance = Vector2.Distance(a.Position, b.Position) / scale;
            float delta = 0f;
            if (a.Id == pinchA && b.Id == pinchB)
            {
                delta = (distance - pinchLast) * PinchMetresPerPixel;
            }
            pinchA = a.Id;
            pinchB = b.Id;
            pinchLast = distance;
            return delta;
        }
    }
}
