// Owned by B3. Contract 13: touch floating stick (dpi clamp, dead zone, leash), press-frame UI rule, steering finger
// ownership, mouse drag and hover, keyboard 8 directions, device precedence, Escape / Android back per state, re-anchor
// after a session start or a pause end. Writes GameSession.HumanController.Desired (radians) from deliberate input only;
// GameDirector's ready gate calls Begin on the first write while the session awaits the human.
//
// Execution order -200: input is read before GameDirector.Update (-100) advances the sim, so a write is seen by the
// ready gate and by the next tick in the same frame (one frame less input lag).
//
// The math is factored into public static functions (EditMode tests: InputCameraMathTests).
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;
using UnityEngine.UI;

namespace PainterIO.Runtime
{
    /// <summary>The device that currently owns HumanController.Desired (contract 13 precedence).</summary>
    public enum SteeringDevice { None, Touch, MouseDrag, Keyboard, Hover }

    [DefaultExecutionOrder(-200)]
    public sealed class SteeringInput : MonoBehaviour
    {
        /// <summary>Floating stick dead zone (inches).</summary>
        public const float DeadZoneInches = 0.05f;
        /// <summary>Floating stick leash: beyond this distance (inches) the anchor follows the finger.</summary>
        public const float MaxRadiusInches = 0.20f;
        /// <summary>Screen.dpi used when the platform reports 0.</summary>
        public const float DefaultDpi = 160f;
        public const float MinDpi = 120f;
        public const float MaxDpi = 560f;
        /// <summary>Hover steering arms once the cursor has moved this far (pixels) since the session start or pause end.</summary>
        public const float HoverArmPixels = 8f;
        /// <summary>Hover steering is inactive while the cursor is within this distance (world units) of the pawn.</summary>
        public const float HoverDeadRadius = 2.5f;

        /// <summary>The live instance (null before GameDirector built it or after teardown).</summary>
        public static SteeringInput Current { get; private set; }

        /// <summary>
        /// Raised on every Escape / Android back press while GameDirector.State == Menu (contract 13), after
        /// UiRoot.HandleBack has opened the "Quitter ?" panel (or closed the open menu panel). A hook for listeners such as
        /// tests or sounds; each subscriber runs in its own try/catch.
        /// </summary>
        public static event Action MenuBackPressed;

        /// <summary>The device that owns Desired at the moment (None after a session start or a pause end).</summary>
        public SteeringDevice ActiveDevice => owner;

        /// <summary>True while a steering finger or a left-button drag is held.</summary>
        public bool HasSteeringPointer => touchId >= 0 || dragging;

        /// <summary>The heading written during the last frame (null when nothing was written).</summary>
        public double? LastWrittenHeading { get; private set; }

        private GameDirector director;
        private readonly List<RaycastResult> hits = new List<RaycastResult>();
        private SteeringDevice owner = SteeringDevice.None;
        private int touchId = -1;
        private Vector2 touchAnchor;
        private readonly HashSet<int> touchesDown = new HashSet<int>();
        private readonly HashSet<int> touchesDownBefore = new HashSet<int>();
        private bool dragging;
        private Vector2 dragAnchor;
        private Vector2 hoverOrigin;
        private bool errorLogged;
        private readonly HashSet<Delegate> loggedSubscribers = new HashSet<Delegate>();

        // ------------------------------------------------------------------------------------------------------------
        // Pure math (tested in EditMode).

        /// <summary>Contract 13: Screen.dpi clamped to [120, 560]; 160 when the platform reports 0 (or NaN).</summary>
        public static float ClampDpi(float reportedDpi)
        {
            if (float.IsNaN(reportedDpi) || reportedDpi <= 0f) return DefaultDpi;
            return Mathf.Clamp(reportedDpi, MinDpi, MaxDpi);
        }

        /// <summary>Inches to screen pixels with the clamped dpi of reportedDpi.</summary>
        public static float InchesToPixels(float inches, float reportedDpi)
        {
            return inches * ClampDpi(reportedDpi);
        }

        /// <summary>
        /// One floating stick update (contract 13). delta = position - anchor. When |delta| &gt; maxRadiusPx the anchor follows:
        /// anchor = position - normalize(delta) * maxRadiusPx. Returns true with heading = atan2(delta.y, delta.x) when
        /// |delta| &gt;= deadZonePx (and |delta| &gt; 0); otherwise false and the course is kept.
        /// </summary>
        public static bool StepStick(ref Vector2 anchor, Vector2 position, float deadZonePx, float maxRadiusPx, out double heading)
        {
            heading = 0.0;
            Vector2 delta = position - anchor;
            float length = delta.magnitude;
            if (length <= 0f) return false;
            if (length > maxRadiusPx) anchor = position - delta / length * Mathf.Max(0f, maxRadiusPx);
            if (length < deadZonePx) return false;
            heading = Math.Atan2(delta.y, delta.x);
            return true;
        }

        /// <summary>
        /// Keyboard 8 directions (arrows / WASD): the sum of the held directions, opposite keys cancel. Null when no direction
        /// remains. Screen up = world up, so up is +pi/2.
        /// </summary>
        public static double? KeyboardHeading(bool up, bool down, bool left, bool right)
        {
            int x = (right ? 1 : 0) - (left ? 1 : 0);
            int y = (up ? 1 : 0) - (down ? 1 : 0);
            if (x == 0 && y == 0) return null;
            return Math.Atan2(y, x);
        }

        /// <summary>A world distance in screen pixels for an orthographic camera (pixelHeight / (2 * orthographicSize) per u).</summary>
        public static float HoverDeadRadiusPixels(float worldRadius, float orthographicSize, float pixelHeight)
        {
            if (!(orthographicSize > 0f) || !(pixelHeight > 0f)) return float.PositiveInfinity;
            return worldRadius * pixelHeight / (2f * orthographicSize);
        }

        /// <summary>
        /// Hover steering (contract 13): heading from the pawn's screen position to the cursor, only while the cursor is MORE
        /// than deadRadiusPx away from it.
        /// </summary>
        public static bool HoverHeading(Vector2 pawnScreen, Vector2 cursor, float deadRadiusPx, out double heading)
        {
            heading = 0.0;
            Vector2 delta = cursor - pawnScreen;
            if (!(delta.magnitude > deadRadiusPx)) return false;
            heading = Math.Atan2(delta.y, delta.x);
            return true;
        }

        /// <summary>True once the cursor is at least HoverArmPixels away from where it was when hover was last reset.</summary>
        public static bool IsHoverArmed(Vector2 origin, Vector2 cursor)
        {
            return (cursor - origin).sqrMagnitude >= HoverArmPixels * HoverArmPixels;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Lifecycle.

        /// <summary>Contract 11.1 entry point: builds the input root and subscribes to the director.</summary>
        public static SteeringInput Create(GameDirector d)
        {
            var go = new GameObject("SteeringInput");
            var s = go.AddComponent<SteeringInput>();
            s.director = d;
            if (d != null)
            {
                d.SessionStarted += s.OnSessionStarted;
                d.StateChanged += s.OnStateChanged;
                d.PausedChanged += s.OnPausedChanged;
            }
            Current = s;
            s.ResetPointers();
            return s;
        }

        private void OnDestroy()
        {
            if (Current == this) Current = null;
            if (director == null) return;
            director.SessionStarted -= OnSessionStarted;
            director.StateChanged -= OnStateChanged;
            director.PausedChanged -= OnPausedChanged;
        }

        private void OnSessionStarted(GameSession s)
        {
            // Contract 13: drop any active touch, re-anchor on the next press; hover re-arms after 8 px.
            ResetPointers();
        }

        private void OnStateChanged(GameState state)
        {
            if (state != GameState.Playing) ResetPointers();
        }

        private void OnPausedChanged(bool paused)
        {
            ResetPointers();
        }

        private void ResetPointers()
        {
            touchId = -1;
            dragging = false;
            owner = SteeringDevice.None;
            hoverOrigin = CursorPosition();
        }

        private void Update()
        {
            LastWrittenHeading = null;
            try
            {
                Process();
            }
            catch (Exception e)
            {
                if (errorLogged) return;
                errorLogged = true;
                Debug.LogError("[PainterIO] SteeringInput failed: " + e);
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // Per frame.

        private void Process()
        {
            Keyboard keyboard = Keyboard.current;
            Mouse mouse = Mouse.current;
            Touchscreen touchscreen = Touchscreen.current;

            if (keyboard != null && keyboard.escapeKey.wasPressedThisFrame) Back();

            GameSession session = director != null ? director.Session : null;
            bool steer = CanSteer(session);

            float dpi = Screen.dpi;
            float deadZone = InchesToPixels(DeadZoneInches, dpi);
            float maxRadius = InchesToPixels(MaxRadiusInches, dpi);

            bool touchHasHeading = UpdateTouch(touchscreen, steer, deadZone, maxRadius, out double touchHeading);
            bool dragHasHeading = UpdateDrag(mouse, steer, deadZone, maxRadius, out double dragHeading);
            double? keyHeading = ReadKeyboard(keyboard);
            bool pointerSteering = touchId >= 0 || dragging;

            // Precedence: a pointer drag (touch or mouse) overrides everything while held; a held key overrides hover;
            // hover takes over only after the cursor moved HoverArmPixels since it was last blocked or reset.
            if (keyHeading.HasValue && !pointerSteering) owner = SteeringDevice.Keyboard;
            bool hoverHasHeading = UpdateHover(mouse, session, steer && !pointerSteering && !keyHeading.HasValue, out double hoverHeading);

            if (!steer) return;
            double? heading = null;
            switch (owner)
            {
                case SteeringDevice.Touch:
                    if (touchId >= 0 && touchHasHeading) heading = touchHeading;
                    break;
                case SteeringDevice.MouseDrag:
                    if (dragging && dragHasHeading) heading = dragHeading;
                    break;
                case SteeringDevice.Keyboard:
                    heading = keyHeading;
                    break;
                case SteeringDevice.Hover:
                    if (hoverHasHeading) heading = hoverHeading;
                    break;
            }
            if (!heading.HasValue) return;
            session.HumanController.Desired = heading.Value;
            LastWrittenHeading = heading.Value;
        }

        private bool CanSteer(GameSession s)
        {
            if (s == null || s.IsClosed || s.IsAttract || s.HumanController == null) return false;
            if (director.State != GameState.Playing || director.IsPaused || director.InResultsBeat) return false;
            return s.HumanAlive && !s.Sim.Ended;
        }

        private bool UpdateTouch(Touchscreen screen, bool steer, float deadZone, float maxRadius, out double heading)
        {
            heading = 0.0;
            // Press frames are detected here, not with press.wasPressedThisFrame: a touch is new when its id was not down
            // at the previous update. Every down touch is recorded each frame (even while steering is off), so a touch
            // that began while another finger steered, during a pause or in a menu never becomes the steering finger.
            touchesDownBefore.Clear();
            foreach (int id in touchesDown) touchesDownBefore.Add(id);
            touchesDown.Clear();
            if (screen == null)
            {
                touchId = -1;
                return false;
            }
            var touches = screen.touches;
            for (int i = 0; i < touches.Count; i++)
            {
                TouchControl t = touches[i];
                if (!t.press.isPressed) continue;
                int id = t.touchId.ReadValue();
                if (id != 0) touchesDown.Add(id);
            }
            if (!steer)
            {
                touchId = -1;
                return false;
            }
            bool result = false;
            if (touchId >= 0)
            {
                bool alive = false;
                for (int i = 0; i < touches.Count; i++)
                {
                    TouchControl t = touches[i];
                    if (t.touchId.ReadValue() != touchId) continue;
                    if (t.press.isPressed)
                    {
                        alive = true;
                        result = StepStick(ref touchAnchor, t.position.ReadValue(), deadZone, maxRadius, out heading);
                    }
                    break;
                }
                if (!alive) touchId = -1;
            }
            if (touchId < 0)
            {
                // The first touch that begins while no steering finger exists and whose press position hits no Selectable.
                // Only press-frame touches qualify: a touch ignored at its press stays ignored for its whole lifetime.
                for (int i = 0; i < touches.Count; i++)
                {
                    TouchControl t = touches[i];
                    if (!t.press.isPressed) continue;
                    int id = t.touchId.ReadValue();
                    if (id == 0 || touchesDownBefore.Contains(id)) continue;
                    Vector2 pos = t.position.ReadValue();
                    if (HitsSelectable(pos)) continue;
                    touchId = id;
                    touchAnchor = pos;
                    owner = SteeringDevice.Touch;
                    result = false;
                    break;
                }
            }
            return result;
        }

        private bool UpdateDrag(Mouse mouse, bool steer, float deadZone, float maxRadius, out double heading)
        {
            heading = 0.0;
            if (mouse == null || !steer)
            {
                dragging = false;
                return false;
            }
            Vector2 pos = mouse.position.ReadValue();
            if (dragging)
            {
                if (mouse.leftButton.isPressed) return StepStick(ref dragAnchor, pos, deadZone, maxRadius, out heading);
                dragging = false;
            }
            if (mouse.leftButton.wasPressedThisFrame && mouse.leftButton.isPressed && !HitsSelectable(pos))
            {
                dragging = true;
                dragAnchor = pos;
                owner = SteeringDevice.MouseDrag;
            }
            return false;
        }

        private static double? ReadKeyboard(Keyboard k)
        {
            if (k == null) return null;
            bool up = k.upArrowKey.isPressed || k.wKey.isPressed;
            bool down = k.downArrowKey.isPressed || k.sKey.isPressed;
            bool left = k.leftArrowKey.isPressed || k.aKey.isPressed;
            bool right = k.rightArrowKey.isPressed || k.dKey.isPressed;
            return KeyboardHeading(up, down, left, right);
        }

        private bool UpdateHover(Mouse mouse, GameSession s, bool allowed, out double heading)
        {
            heading = 0.0;
            if (mouse == null) return false;
            Vector2 cursor = mouse.position.ReadValue();
            if (!allowed)
            {
                // Blocked (no steering, a drag or a held key): arming restarts from here.
                hoverOrigin = cursor;
                if (owner == SteeringDevice.Hover) owner = SteeringDevice.None;
                return false;
            }
            if (owner != SteeringDevice.Hover)
            {
                if (!IsHoverArmed(hoverOrigin, cursor)) return false;
                owner = SteeringDevice.Hover;
            }
            Camera cam = MainCamera();
            if (cam == null || s == null || s.HumanIndex < 0) return false;
            Vector2 pawn = s.RenderPos(s.HumanIndex);
            Vector3 screen = cam.WorldToScreenPoint(new Vector3(pawn.x, pawn.y, 0f));
            float dead = HoverDeadRadiusPixels(HoverDeadRadius, cam.orthographicSize, cam.pixelHeight);
            if (!HoverHeading(new Vector2(screen.x, screen.y), cursor, dead, out heading)) return false;
            // The cursor resting on a button (pause, leaderboard) keeps the course instead of steering into the corner.
            return !HitsSelectable(cursor);
        }

        private static Camera MainCamera()
        {
            CameraRig rig = CameraRig.Current;
            if (rig != null && rig.Camera != null) return rig.Camera;
            return Camera.main;
        }

        private static Vector2 CursorPosition()
        {
            try
            {
                Mouse m = Mouse.current;
                return m != null ? m.position.ReadValue() : Vector2.zero;
            }
            catch (Exception)
            {
                return Vector2.zero;
            }
        }

        /// <summary>Contract 13 press-frame rule: RaycastAll at pos; true if any hit has a Selectable on itself or a parent.</summary>
        private bool HitsSelectable(Vector2 pos)
        {
            EventSystem es = EventSystem.current;
            if (es == null) return false;
            var ped = new PointerEventData(es) { position = pos };
            hits.Clear();
            es.RaycastAll(ped, hits);
            for (int i = 0; i < hits.Count; i++)
            {
                GameObject go = hits[i].gameObject;
                if (go != null && go.GetComponentInParent<Selectable>() != null) return true;
            }
            return false;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Escape / Android back.

        private void Back()
        {
            if (director == null) return;
            switch (director.State)
            {
                case GameState.Playing:
                    director.SetPaused(!director.IsPaused);
                    break;
                case GameState.Results:
                    director.ToCountryScreen();   // rule v1.7: the results always go on to the country screen
                    break;
                case GameState.Menu:
                    // B4's UiRoot.HandleBack closes Options, else toggles the "Quitter ?" panel; it is deduplicated per frame
                    // with UiRoot's own Escape handling, so both paths together act once.
                    UiRoot ui = UiRoot.Instance;
                    if (ui != null) ui.HandleBack();
                    RaiseMenuBack();
                    break;
            }
        }

        private void RaiseMenuBack()
        {
            Action handler = MenuBackPressed;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action)d)();
                }
                catch (Exception e)
                {
                    if (loggedSubscribers.Add(d)) Debug.LogError("[PainterIO] MenuBackPressed subscriber failed: " + e);
                }
            }
        }
    }
}
