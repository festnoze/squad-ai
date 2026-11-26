using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// DOGBIG (black Labrador, product owner 2026-11-21), presentation only: the house dog's model is the Quaternius Husky
    /// (rig, clips and size), dressed as a black Labrador by its fur map. A Labrador's ears hang and its tail is carried low,
    /// where the Husky's ears are pricked and its tail curls over its back, so after each clip pass the ear chains are aimed
    /// down beside the head and the tail chain back and down (Tuning.DogEarOut, DogEarForward, DogTailDroop, DogTailWeight).
    /// Every bone is aimed absolutely from where the clip left it, segment by segment from the root, so the pose never
    /// accumulates (the completed clips key these bones every frame anyway). InhabitantRig applies it in game, the title
    /// logo before it bakes its walk frames, DogShots before it renders. A model without these bones is left untouched.
    /// DOGBIG v3: it also grows the head (Tuning.DogHeadScale) and poses the bite (Bite: head roll and dip, the Jaw joint open).
    /// </summary>
    public sealed class PetPose
    {
        private static readonly string[] EarLeftNames = { "Ear1.L", "Ear2.L", "Ear3.L", "Ear4.L", "Ear4.L_end" };
        private static readonly string[] EarRightNames = { "Ear1.R", "Ear2.R", "Ear3.R", "Ear4.R", "Ear4.R_end" };
        private static readonly string[] TailNames = { "Tail1", "Tail2", "Tail3", "Tail4", "Tail5", "Tail6", "Tail6_end" };

        private readonly Transform head;
        private readonly Transform[] earLeft;
        private readonly Transform[] earRight;
        private readonly Transform[] tail;
        // DOGBIG v3: the head's rest scale, its forward and right axes in its own frame (found in the rest pose, facing the
        // model's facing), and the "Jaw" joint with its rest rotation.
        private readonly Vector3 headRestScale = Vector3.one;
        private readonly Vector3 headLocalForward = Vector3.forward;
        private readonly Vector3 headLocalRight = Vector3.right;
        private readonly Transform jaw;
        private readonly Quaternion jawRest = Quaternion.identity;

        /// <summary>
        /// DOGBIG v3: the bite, 0 to 1 (InhabitantRig eases it from Inhabitant.Biting): the head rolls and dips onto the
        /// furniture's edge and the jaw opens (Tuning.DogBiteRollDegrees, DogBitePitchDegrees, DogJawOpenDegrees).
        /// </summary>
        public float Bite;

        private PetPose(Transform head, Transform[] earLeft, Transform[] earRight, Transform[] tail, Transform jaw, Quaternion facing)
        {
            this.head = head;
            this.earLeft = earLeft;
            this.earRight = earRight;
            this.tail = tail;
            this.jaw = jaw;
            if (head != null)
            {
                headRestScale = head.localScale;
                Quaternion toHead = Quaternion.Inverse(head.rotation);
                headLocalForward = (toHead * (facing * Vector3.forward)).normalized;
                headLocalRight = (toHead * (facing * Vector3.right)).normalized;
            }
            if (jaw != null)
            {
                jawRest = jaw.localRotation;
            }
        }

        /// <summary>True when the model has an ear chain, the tail chain or the head bone.</summary>
        public bool HasBones => earLeft != null || earRight != null || tail != null || head != null;

        /// <summary>True when the model has the bite's "Jaw" joint.</summary>
        public bool HasJaw => jaw != null;

        /// <summary>
        /// The pose's bones under <paramref name="model"/> (found once, in its rest or Idle pose, the model facing
        /// <paramref name="facing"/>; null chains when a bone is missing).
        /// </summary>
        public static PetPose Find(Transform model, Quaternion facing)
        {
            if (model == null)
            {
                return new PetPose(null, null, null, null, null, facing);
            }
            return new PetPose(FindDeep(model, "Head"), Chain(model, EarLeftNames), Chain(model, EarRightNames), Chain(model, TailNames),
                FindDeep(model, "Jaw"), facing);
        }

        /// <summary>
        /// Grows the head (Tuning.DogHeadScale), poses the bite (<see cref="Bite"/>), hangs the ears (in the head's frame,
        /// <paramref name="headFacing"/>: its yaw) and lowers the tail (in the body's frame, <paramref name="bodyFacing"/>).
        /// Absolute from where the clip and the rig left the bones: never accumulates.
        /// </summary>
        public void Apply(Quaternion headFacing, Quaternion bodyFacing)
        {
            float bite = Mathf.Clamp01(Bite);
            if (head != null)
            {
                head.localScale = headRestScale * Tuning.DogHeadScale;
                if (bite > 0f)
                {
                    head.rotation = head.rotation * Quaternion.AngleAxis(Tuning.DogBiteRollDegrees * bite, headLocalForward)
                        * Quaternion.AngleAxis(Tuning.DogBitePitchDegrees * bite, headLocalRight);
                }
            }
            if (jaw != null)
            {
                // The jaw is a child of the head, its rest frame the head's: open it about the head's right axis.
                jaw.localRotation = jawRest * Quaternion.AngleAxis(Tuning.DogJawOpenDegrees * bite, Quaternion.Inverse(jawRest) * headLocalRight);
            }
            HangEar(earLeft, headFacing);
            HangEar(earRight, headFacing);
            if (tail != null)
            {
                Vector3 low = bodyFacing * new Vector3(0f, -Tuning.DogTailDroop, -1f);
                Aim(tail, low.normalized, Tuning.DogTailWeight);
            }
        }
        private void HangEar(Transform[] ear, Quaternion headFacing)
        {
            if (ear == null)
            {
                return;
            }
            // Which side the ear is on, from its root against the head bone (no guess about the import's handedness).
            float side = head != null && Vector3.Dot(ear[ear.Length - 1].position - head.position, headFacing * Vector3.right) < 0f ? -1f : 1f;
            Vector3 hang = headFacing * new Vector3(side * Tuning.DogEarOut, -1f, Tuning.DogEarForward);
            Aim(ear, hang.normalized, 1f);
        }

        /// <summary>Turns each bone of the chain, root first, so the segment to its child points along the target.</summary>
        private static void Aim(Transform[] chain, Vector3 target, float weight)
        {
            for (int i = 0; i + 1 < chain.Length; i++)
            {
                Vector3 segment = chain[i + 1].position - chain[i].position;
                if (segment.sqrMagnitude < 1e-12f)
                {
                    continue;
                }
                Quaternion turn = Quaternion.Slerp(Quaternion.identity, Quaternion.FromToRotation(segment, target), weight);
                chain[i].rotation = turn * chain[i].rotation;
            }
        }

        private static Transform[] Chain(Transform model, string[] names)
        {
            var chain = new Transform[names.Length];
            for (int i = 0; i < names.Length; i++)
            {
                chain[i] = FindDeep(model, names[i]);
                if (chain[i] == null)
                {
                    return null;
                }
            }
            return chain;
        }

        private static Transform FindDeep(Transform t, string name)
        {
            if (t.name == name)
            {
                return t;
            }
            for (int i = 0; i < t.childCount; i++)
            {
                Transform found = FindDeep(t.GetChild(i), name);
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }
    }
}
