using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// PRD 4.1, per inhabitant and per fixed step: the furniture is seen when at least one of its five
    /// sample points is in range, in the cone, and not behind an Occluder. Five raycasts at most.
    /// M4 (docs/CONTRACT_M4.md 2.3, amendment 9.3): the range for the player furniture's own sample points is
    /// scaled by <see cref="FurnitureController.SightRangeFactor"/> (a switched-off lamp: 0.4 x 10 = 4 m).
    /// </summary>
    public sealed class Vision : MonoBehaviour
    {
        public Inhabitant Owner;

        public bool SeesPlayer { get; private set; }

        /// <summary>M4: the range factor used for the player on the last step (1, or LampOffLight for a dark lamp).</summary>
        public float RangeFactor { get; private set; } = 1f;

        /// <summary>Which sample points were visible on the last step (debug and probe).</summary>
        public readonly bool[] SampleVisible = new bool[Tuning.SampleCount];
        public readonly Vector3[] Samples = new Vector3[Tuning.SampleCount];

        public bool Step(FurnitureController furniture)
        {
            SeesPlayer = false;
            if (Owner == null || Owner.Routine == null || furniture == null)
            {
                return false;
            }
            furniture.GetSamplePoints(Samples);
            RangeFactor = furniture.SightRangeFactor;
            SeesPlayer = Test(Owner.EyePosition, Owner.EyeForward, Samples, RangeFactor, SampleVisible);
            return SeesPlayer;
        }

        /// <summary>M4: the full three check test with the range scaled by <paramref name="rangeFactor"/> (CONTRACT_M4 2.3).</summary>
        public static bool Test(Vector3 eye, Vector3 forward, Vector3[] samples, float rangeFactor, bool[] visible = null)
        {
            float range = Tuning.ViewRange * rangeFactor;
            bool any = false;
            for (int i = 0; i < samples.Length; i++)
            {
                bool v = VisionMath.IsInCone(eye, forward, samples[i], range, Tuning.ViewHalfAngle)
                    && !Occluded(eye, samples[i]);
                if (visible != null)
                {
                    visible[i] = v;
                }
                any |= v;
            }
            return any;
        }

        /// <summary>The full three check test at the normal range, shared with the level audit.</summary>
        public static bool Test(Vector3 eye, Vector3 forward, Vector3[] samples, bool[] visible = null)
        {
            return Test(eye, forward, samples, 1f, visible);
        }

        public static bool Occluded(Vector3 eye, Vector3 point)
        {
            Vector3 d = point - eye;
            float distance = d.magnitude;
            if (distance < 1e-4f)
            {
                return false;
            }
            return Physics.Raycast(eye, d / distance, distance, Layers.OccluderMask, QueryTriggerInteraction.Ignore);
        }
    }
}
