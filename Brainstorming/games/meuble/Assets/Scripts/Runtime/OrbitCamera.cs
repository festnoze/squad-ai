using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// Third person orbit camera (PRD 3.1). No collision code: walls are single sided, so the camera may
    /// stand outside the room and look through the back of the nearest wall.
    /// M3 (docs/CONTRACT_M3.md 6): while the game is paused the camera holds still and reads no input; on the
    /// title screen it is in showcase mode, a slow orbit pulled back to show the room.
    /// M5 (docs/CONTRACT_M5.md 2 and 16.10): the zoom's far bound (<see cref="MaxDistance"/>) scales with the house: a
    /// house whose longest interior side is at most Tuning.CameraHouseReferenceSide (every level of M1 to M4) keeps
    /// Tuning.OrbitDistanceMax, a longer one gets that bound times its side over the reference, up to
    /// Tuning.CameraMaxDistanceHouse. The level comes from the target furniture's floor (FloorMap.Level).
    /// Sky ceiling (2026-11-20): <see cref="Pitch"/> is the view's pitch, from Tuning.PitchMin (above the horizon) to
    /// Tuning.PitchMax; the arm follows it down to Tuning.OrbitArmPitchMin only (<see cref="ArmPitchFor"/>).
    /// </summary>
    [DefaultExecutionOrder(200)]
    public sealed class OrbitCamera : MonoBehaviour
    {
        public FurnitureController Target;

        public float Yaw { get; private set; }
        public float Pitch { get; private set; } = Tuning.PitchDefault;
        public float Distance { get; private set; } = Tuning.OrbitDistance;

        /// <summary>M3: the title screen's slow orbit (no input, pulled back).</summary>
        public bool Showcase { get; private set; }

        /// <summary>M5: the far bound of the zoom for the current house (Tuning.OrbitDistanceMax on levels 1 to 7).</summary>
        public float MaxDistance { get; private set; } = Tuning.OrbitDistanceMax;

        /// <summary>
        /// M5: the zoom's far bound for a house: Tuning.OrbitDistanceMax up to a longest interior side of
        /// Tuning.CameraHouseReferenceSide, then proportional to that side, at most Tuning.CameraMaxDistanceHouse.
        /// </summary>
        public static float MaxDistanceFor(LevelDef level)
        {
            if (level == null)
            {
                return Tuning.OrbitDistanceMax;
            }
            Rect interior = level.InteriorBounds();
            float side = Mathf.Max(interior.width, interior.height);
            float scaled = Tuning.OrbitDistanceMax * side / Tuning.CameraHouseReferenceSide;
            return Mathf.Clamp(scaled, Tuning.OrbitDistanceMax, Tuning.CameraMaxDistanceHouse);
        }

        /// <summary>M5: sets the far bound of the zoom (tests and tools); the distance is clamped into the new range.</summary>
        public void SetMaxDistance(float max)
        {
            MaxDistance = Mathf.Clamp(max, Tuning.OrbitDistanceMax, Tuning.CameraMaxDistanceHouse);
            if (!Showcase)
            {
                Distance = Mathf.Clamp(Distance, Tuning.OrbitDistanceMin, MaxDistance);
            }
        }

        // Showcase framing: degrees per second (one turn in two minutes), the orbit pitch, and how far the view
        // looks up from the chair, which frames the chair in the lower third, under the title's buttons.
        private const float ShowcaseSpeed = Tuning.ShowcaseSpeed;
        private const float ShowcasePitch = Tuning.ShowcasePitch;
        private const float ShowcaseTilt = Tuning.ShowcaseTilt;

        private Vector3 focus;
        private Vector3 focusVelocity;
        private float savedPitch;
        private float savedDistance;

        /// <summary>
        /// Garden backdrop (2026-11-19): the ring of the target's level (GardenBackdrop.RingFor), null without a level. The
        /// camera always stands inside it (<see cref="Apply"/> shortens the arm at its fence, which the ring's size keeps out
        /// of reach in play) and the far clip always holds it.
        /// </summary>
        public GardenBackdrop.Ring? Fence { get; private set; }

        public void SetTarget(FurnitureController target, float yaw)
        {
            Target = target;
            LevelDef level = target != null ? target.Floor.Level : null;
            SetMaxDistance(MaxDistanceFor(level));
            Fence = level != null ? GardenBackdrop.RingFor(level) : (GardenBackdrop.Ring?)null;
            Camera view = GetComponent<Camera>();
            if (view != null && Fence.HasValue)
            {
                view.farClipPlane = Mathf.Max(view.farClipPlane, Fence.Value.FarClip);
            }
            Yaw = yaw;
            Pitch = Showcase ? ShowcasePitch : Tuning.PitchDefault;
            Snap();
        }

        /// <summary>Garden backdrop: sets the zoom (tests and screenshots), clamped into the zoom range.</summary>
        public void SetDistance(float distance)
        {
            Distance = Mathf.Clamp(distance, Tuning.OrbitDistanceMin, MaxDistance);
            Snap();
        }

        /// <summary>M3: points the camera (tests, screenshots, the title). Pitch is clamped to the PRD range.</summary>
        public void SetView(float yaw, float pitch)
        {
            Yaw = yaw;
            Pitch = Mathf.Clamp(pitch, Tuning.PitchMin, Tuning.PitchMax);
            Snap();
        }

        /// <summary>
        /// M3: the title screen's camera. On: a slow orbit around the chair, pulled back to the longest zoom so the
        /// room shows. Off: the pitch and the zoom the player had come back.
        /// </summary>
        public void SetShowcase(bool on)
        {
            if (on == Showcase)
            {
                return;
            }
            Showcase = on;
            if (on)
            {
                savedPitch = Pitch;
                savedDistance = Distance;
                Pitch = ShowcasePitch;
                Distance = Tuning.OrbitDistanceMax;
            }
            else
            {
                Pitch = savedPitch;
                Distance = savedDistance;
            }
            Snap();
        }

        /// <summary>Jumps to the target with no smoothing (level start and restart).</summary>
        public void Snap()
        {
            if (Target == null)
            {
                return;
            }
            focus = TargetPoint();
            focusVelocity = Vector3.zero;
            Apply();
        }

        private Vector3 TargetPoint()
        {
            return Target.VisualCenter + Vector3.up * Tuning.CameraTargetHeight;
        }

        private void LateUpdate()
        {
            if (Target == null)
            {
                return;
            }
            if (Showcase)
            {
                Yaw += ShowcaseSpeed * Time.unscaledDeltaTime;
            }
            else if (!GamePause.IsPaused)
            {
                // M6 (docs/CONTRACT_M6.md 2.1): the sensitivity option multiplies the mouse and the right stick orbit rates.
                float sens = SaveStore.Options.Sensitivity; // MUTATION:CAMERA_SENSITIVITY
                // Mouse look only while the cursor is captured (click to capture, Escape to release).
                if (Cursor.lockState == CursorLockMode.Locked)
                {
                    Vector2 delta = InputReader.LookDeltaPixels();
                    Yaw += delta.x * Tuning.MouseSensitivity * sens;
                    Pitch = Mathf.Clamp(Pitch - delta.y * Tuning.MouseSensitivity * sens, Tuning.PitchMin, Tuning.PitchMax);
                }
                Vector2 stick = InputReader.LookStick();
                Yaw += stick.x * 140f * sens * Time.unscaledDeltaTime;
                Pitch = Mathf.Clamp(Pitch - stick.y * 90f * sens * Time.unscaledDeltaTime, Tuning.PitchMin, Tuning.PitchMax);
                // M7 (CONTRACT_M7 1.5): a drag on the right half of a touchscreen orbits, whatever the cursor lock, with
                // the same sensitivity option (the drag is in pixels of a 1080 pixel high screen, so every screen turns alike).
                Vector2 drag = InputReader.TouchLookDelta();
                Yaw += drag.x * Tuning.TouchOrbitDegPerPixel * sens; // MUTATION:TOUCH_ORBIT_SENS
                Pitch = Mathf.Clamp(Pitch - drag.y * Tuning.TouchOrbitDegPerPixel * sens, Tuning.PitchMin, Tuning.PitchMax);
                // M5: a notch moves the same fraction of the zoom range in every house (0.35 m on levels 1 to 7).
                float notch = 0.35f * MaxDistance / Tuning.OrbitDistanceMax;
                Distance = Mathf.Clamp(Distance - InputReader.ZoomNotches() * notch, Tuning.OrbitDistanceMin, MaxDistance);
            }

            // Critically damped spring on the focus point (SmoothDamp is one), 0.12 s.
            focus = Vector3.SmoothDamp(focus, TargetPoint(), ref focusVelocity, Tuning.CameraSmoothTime);
            Apply();
        }

        /// <summary>
        /// Sky ceiling (2026-11-20, docs/m9/backdrop/NOTES.md): the arm's pitch for a view pitch. Above
        /// Tuning.OrbitArmPitchMin + Tuning.OrbitArmPitchEase the arm is the view (the camera orbits the focus, which stays
        /// at the centre of the screen); below it the arm eases onto Tuning.OrbitArmPitchMin (a quadratic blend, no kink)
        /// and stays there, the camera never sinking toward the floor, while the view keeps tilting up toward the sky down
        /// to Tuning.PitchMin (the furniture then sits lower in the frame).
        /// </summary>
        public static float ArmPitchFor(float pitch)
        {
            const float floor = Tuning.OrbitArmPitchMin;
            const float ease = Tuning.OrbitArmPitchEase;
            if (pitch >= floor + ease)
            {
                return pitch;
            }
            if (pitch <= floor - ease)
            {
                return floor;
            }
            float t = pitch - floor + ease;
            return floor + t * t / (4f * ease);
        }

        /// <summary>From the focus toward the camera for a yaw and a view pitch (unit length; see <see cref="ArmPitchFor"/>).</summary>
        public static Vector3 ArmDirection(float yaw, float pitch)
        {
            return Quaternion.Euler(ArmPitchFor(pitch), yaw, 0f) * Vector3.back;
        }

        private void Apply()
        {
            Quaternion view = Quaternion.Euler(Showcase ? Pitch - ShowcaseTilt : Pitch, Yaw, 0f);
            Vector3 back = ArmDirection(Yaw, Pitch);
            float arm = Fence.HasValue ? GardenBackdrop.ClampArm(Fence.Value, focus, back, Distance) : Distance;
            transform.SetPositionAndRotation(focus + back * arm, view);
        }
    }
}
