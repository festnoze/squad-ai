using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// PRD 4.1, per inhabitant and per fixed step: the furniture is seen when at least one of its five
    /// sample points is in range, in the cone, and not behind an Occluder. Five raycasts at most.
    /// M4 (docs/CONTRACT_M4.md 2.3, amendment 9.3): the range for the player furniture's own sample points is
    /// scaled by <see cref="FurnitureController.SightRangeFactor"/> (a switched-off lamp: 0.4 x 10 = 4 m).
    /// M5 (docs/CONTRACT_M5_v3.md 15.2 and 15.5, CONTRACT_M5.md 3): each watcher sees with its own range (its personality's,
    /// times the lamp factor), its own half angle and its own eye (the dog's at 0.35 m, on the floor under it), and a
    /// sleeping watcher sees nothing. During a door swing, <see cref="StepLeaves"/> tests the swinging leaves' samples (four
    /// more rays per leaf: nine during a swing), the leaf never hiding its own samples.
    /// M5 wave 5B (docs/CONTRACT_M5.md 6 and 16.5): with a load on the furniture, its sample box grows by the load's height
    /// (<see cref="Step(FurnitureController, float)"/>: a vase seen above a sofa is the furniture seen), and a fallen load's
    /// clue is one more sample point a watcher may see (<see cref="SeesPoint"/>).
    /// </summary>
    public sealed class Vision : MonoBehaviour
    {
        public Inhabitant Owner;

        public bool SeesPlayer { get; private set; }

        /// <summary>M4: the range factor used for the player on the last step (1, or LampOffLight for a dark lamp).</summary>
        public float RangeFactor { get; private set; } = 1f;

        /// <summary>M5: a sample of a swinging leaf was seen on the last <see cref="StepLeaves"/> (CONTRACT_M5_v3 15.2).</summary>
        public bool SeesLeaf { get; private set; }

        /// <summary>M5: the range used for the player furniture's samples on the last step (the watcher's, times the lamp).</summary>
        public float Range { get; private set; } = Tuning.ViewRange;

        /// <summary>M5: the half angle used on the last step (the watcher's).</summary>
        public float HalfAngle { get; private set; } = Tuning.ViewHalfAngle;

        /// <summary>Which sample points were visible on the last step (debug and probe).</summary>
        public readonly bool[] SampleVisible = new bool[Tuning.SampleCount];
        public readonly Vector3[] Samples = new Vector3[Tuning.SampleCount];

        /// <summary>M5 wave 5B: the height the furniture's sample box grew by on the last step (the load's, or 0).</summary>
        public float ExtraHeight { get; private set; }

        private static readonly RaycastHit[] Hits = new RaycastHit[16];

        public bool Step(FurnitureController furniture)
        {
            return Step(furniture, 0f);
        }

        /// <summary>
        /// M5 wave 5B (CONTRACT_M5 16.5): <see cref="Step(FurnitureController)"/> with the furniture's sample box grown by
        /// <paramref name="extraHeight"/> (Tuning.LoadHeight while it carries a load, 0 otherwise): the four top samples rise
        /// by it and the centre by half of it, as if the box were that much taller.
        /// </summary>
        public bool Step(FurnitureController furniture, float extraHeight)
        {
            SeesPlayer = false;
            if (Owner == null || Owner.Routine == null || furniture == null)
            {
                return false;
            }
            if (furniture.Hidden) // MUTATION:HIDDEN_SAMPLES
            {
                // M6 (CONTRACT_M6 2.5): hidden in a wardrobe, the furniture has no sample point at all.
                System.Array.Clear(SampleVisible, 0, SampleVisible.Length);
                return false;
            }
            ExtraHeight = Mathf.Max(0f, extraHeight);
            if (ExtraHeight > 0f)
            {
                Vector3 box = furniture.SampleSize + Vector3.up * ExtraHeight; // MUTATION:LOAD_BOX
                VisionMath.SamplePoints(furniture.transform.position, furniture.Yaw, box, Tuning.SampleInset, Samples);
            }
            else
            {
                furniture.GetSamplePoints(Samples);
            }
            RangeFactor = furniture.SightRangeFactor;
            InhabitantRoutine routine = Owner.Routine;
            Range = routine.ViewRange * RangeFactor;
            HalfAngle = routine.HalfAngle;
            // CONTRACT_M5_v3 4: a sleeping dog's eye is closed, it sees nothing (the only guard: GameState reads SeesPlayer).
            if (routine.Asleep) // MUTATION:DOG_ASLEEP
            {
                System.Array.Clear(SampleVisible, 0, SampleVisible.Length);
                return false;
            }
            SeesPlayer = Test(Owner.EyePosition, Owner.EyeForward, Samples, Range, HalfAngle, SampleVisible);
            return SeesPlayer;
        }

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.2): the samples of every swinging leaf, seen by this watcher? Its own range (no
        /// lamp factor: the leaf is not the lamp, as in the audit) and half angle; asleep, nothing. A leaf never hides its
        /// own samples (they lie on its mid plane, inside its collider), every other occluder does. Outside a swing a leaf
        /// has no samples, so this is free.
        /// </summary>
        public bool StepLeaves(IReadOnlyList<DoorLeaf> leaves)
        {
            SeesLeaf = false;
            if (Owner == null || Owner.Routine == null || leaves == null)
            {
                return false;
            }
            InhabitantRoutine routine = Owner.Routine;
            if (routine.Asleep)
            {
                return false;
            }
            Vector3 eye = Owner.EyePosition;
            Vector3 forward = Owner.EyeForward;
            for (int l = 0; l < leaves.Count; l++)
            {
                DoorLeaf leaf = leaves[l];
                Vector3[] samples = leaf != null ? leaf.Samples : null;
                if (samples == null || samples.Length == 0)
                {
                    continue;
                }
                for (int i = 0; i < samples.Length; i++)
                {
                    if (VisionMath.IsInCone(eye, forward, samples[i], routine.ViewRange, routine.HalfAngle)
                        && !Occluded(eye, samples[i], leaf.transform))
                    {
                        SeesLeaf = true;
                        return true;
                    }
                }
            }
            return false;
        }

        /// <summary>
        /// M5 wave 5B (CONTRACT_M5 6): a single world point (a fallen load's clue) seen by this watcher on its own range (no
        /// lamp factor) and half angle, unoccluded; asleep, nothing.
        /// </summary>
        public bool SeesPoint(Vector3 point)
        {
            if (Owner == null || Owner.Routine == null)
            {
                return false;
            }
            InhabitantRoutine routine = Owner.Routine;
            if (routine.Asleep)
            {
                return false;
            }
            Vector3 eye = Owner.EyePosition;
            return VisionMath.IsInCone(eye, Owner.EyeForward, point, routine.ViewRange, routine.HalfAngle) && !Occluded(eye, point);
        }

        /// <summary>
        /// M6 (docs/CONTRACT_M6.md 2.6): the leaf itself, open or closed, at rest or swinging, seen by this watcher? Its 4
        /// samples at its current angle (DoorGeometry.Samples), the watcher's own range (no lamp factor) and half angle, every
        /// occluder but the leaf itself; asleep, nothing. Used for door memory only.
        /// </summary>
        public bool SeesLeafBody(DoorLeaf leaf)
        {
            if (Owner == null || Owner.Routine == null || leaf == null || leaf.Geometry == null || Owner.Routine.Asleep)
            {
                return false;
            }
            InhabitantRoutine routine = Owner.Routine;
            Vector3 eye = Owner.EyePosition;
            Vector3 forward = Owner.EyeForward;
            Vector3[] samples = leaf.Geometry.Samples(leaf.Angle);
            for (int i = 0; i < samples.Length; i++)
            {
                if (VisionMath.IsInCone(eye, forward, samples[i], routine.ViewRange, routine.HalfAngle) && !Occluded(eye, samples[i], leaf.transform))
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// M6 (docs/CONTRACT_M6.md 2.5): any of these sample points (a remembered pose's sample box) seen by this watcher, on its
        /// own range (no lamp factor) and half angle, unoccluded; asleep, nothing.
        /// </summary>
        public bool SeesAny(Vector3[] samples)
        {
            if (Owner == null || Owner.Routine == null || samples == null || Owner.Routine.Asleep)
            {
                return false;
            }
            InhabitantRoutine routine = Owner.Routine;
            return Test(Owner.EyePosition, Owner.EyeForward, samples, routine.ViewRange, routine.HalfAngle, null);
        }

        /// <summary>M4: the full three check test with the range scaled by <paramref name="rangeFactor"/> (CONTRACT_M4 2.3).</summary>
        public static bool Test(Vector3 eye, Vector3 forward, Vector3[] samples, float rangeFactor, bool[] visible = null)
        {
            return Test(eye, forward, samples, Tuning.ViewRange * rangeFactor, Tuning.ViewHalfAngle, visible);
        }

        /// <summary>
        /// M5 (docs/CONTRACT_M5_v3.md 15.5): the three check test with a watcher's own range (already scaled by the
        /// lamp factor) and half angle.
        /// </summary>
        public static bool Test(Vector3 eye, Vector3 forward, Vector3[] samples, float range, float halfAngle, bool[] visible)
        {
            bool any = false;
            for (int i = 0; i < samples.Length; i++)
            {
                bool v = VisionMath.IsInCone(eye, forward, samples[i], range, halfAngle) && !Occluded(eye, samples[i]);
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

        /// <summary>
        /// M5: <see cref="Occluded(Vector3, Vector3)"/>, except that no collider under <paramref name="ignore"/> occludes
        /// (a door leaf and its own samples). Null ignores nothing.
        /// </summary>
        public static bool Occluded(Vector3 eye, Vector3 point, Transform ignore)
        {
            if (ignore == null)
            {
                return Occluded(eye, point);
            }
            Vector3 d = point - eye;
            float distance = d.magnitude;
            if (distance < 1e-4f)
            {
                return false;
            }
            int n = Physics.RaycastNonAlloc(eye, d / distance, Hits, distance, Layers.OccluderMask, QueryTriggerInteraction.Ignore);
            for (int i = 0; i < n; i++)
            {
                Collider c = Hits[i].collider;
                if (c != null && !c.transform.IsChildOf(ignore))
                {
                    return true;
                }
            }
            return false;
        }
    }
}
