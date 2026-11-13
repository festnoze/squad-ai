using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// Third person orbit camera (PRD 3.1). No collision code: walls are single sided, so the camera may
    /// stand outside the room and look through the back of the nearest wall.
    /// M3 (docs/CONTRACT_M3.md 6): while the game is paused the camera holds still and reads no input; on the
    /// title screen it is in showcase mode, a slow orbit pulled back to show the room.
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

        // Showcase framing: degrees per second (one turn in two minutes), the orbit pitch, and how far the view
        // looks up from the chair, which frames the chair in the lower third, under the title's buttons.
        private const float ShowcaseSpeed = Tuning.ShowcaseSpeed;
        private const float ShowcasePitch = Tuning.ShowcasePitch;
        private const float ShowcaseTilt = Tuning.ShowcaseTilt;

        private Vector3 focus;
        private Vector3 focusVelocity;
        private float savedPitch;
        private float savedDistance;

        public void SetTarget(FurnitureController target, float yaw)
        {
            Target = target;
            Yaw = yaw;
            Pitch = Showcase ? ShowcasePitch : Tuning.PitchDefault;
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
                // Mouse look only while the cursor is captured (click to capture, Escape to release).
                if (Cursor.lockState == CursorLockMode.Locked)
                {
                    Vector2 delta = InputReader.LookDeltaPixels();
                    Yaw += delta.x * Tuning.MouseSensitivity;
                    Pitch = Mathf.Clamp(Pitch - delta.y * Tuning.MouseSensitivity, Tuning.PitchMin, Tuning.PitchMax);
                }
                Vector2 stick = InputReader.LookStick();
                Yaw += stick.x * 140f * Time.unscaledDeltaTime;
                Pitch = Mathf.Clamp(Pitch - stick.y * 90f * Time.unscaledDeltaTime, Tuning.PitchMin, Tuning.PitchMax);
                Distance = Mathf.Clamp(Distance - InputReader.ZoomNotches() * 0.35f, Tuning.OrbitDistanceMin, Tuning.OrbitDistanceMax);
            }

            // Critically damped spring on the focus point (SmoothDamp is one), 0.12 s.
            focus = Vector3.SmoothDamp(focus, TargetPoint(), ref focusVelocity, Tuning.CameraSmoothTime);
            Apply();
        }

        private void Apply()
        {
            Quaternion orbit = Quaternion.Euler(Pitch, Yaw, 0f);
            Quaternion view = Showcase ? Quaternion.Euler(Pitch - ShowcaseTilt, Yaw, 0f) : orbit;
            transform.SetPositionAndRotation(focus - orbit * Vector3.forward * Distance, view);
        }
    }
}
