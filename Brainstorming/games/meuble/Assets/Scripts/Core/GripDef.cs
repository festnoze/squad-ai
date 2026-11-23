using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// GRIP (product owner, 2026-11-22), presentation only: where a carrier holds each player furniture body. The rules
    /// never read it: the carried furniture still follows <see cref="InhabitantRoutine.CarryAnchor"/> (CarryForward ahead
    /// of the carrier's rule position, CarryHeight or DogDragLift up), the carrier's rule position never moves for it.
    ///
    /// Every point is in the furniture's own frame (x right, y up from its base, z forward; metres), the frame of the
    /// carried furniture, which takes the carrier's yaw: the carrier stands on its -z side, facing +z. The points were
    /// measured on the fitted models (scratchpad furn.py on the Kenney GLBs, FurnitureKit for the procedural office and
    /// rocking chairs): docs/next/progress/GRIP.md lists them.
    ///
    /// - Humans: the two wrists (the palm bones, Palm.L and Palm.R) and the way the fingers point, so the hands rest on
    ///   the furniture (the top of a backrest, the sides of the stool's seat, a lamp's pole) instead of sinking into it;
    ///   <see cref="HumanStand"/>, how far behind the furniture's centre the body stands (its model steps back or forward
    ///   from the rule position by HumanStand - CarryForward, eased with the carry), and a forward lean for the low stool.
    /// - The dog: <see cref="Snout"/>, the point it bites (a leg low down, the low back of an armchair, a lamp's pole, a seat's
    ///   rear rim), never the top of a seat. Its model lowers its head to it (<see cref="GripMath.SolveNeckBend"/>) and
    ///   steps so the snout lands on it.
    /// </summary>
    public sealed class GripDef
    {
        public string Kind;
        /// <summary>Human: the left and right wrist targets (the carrier's left is -x).</summary>
        public Vector3 LeftWrist;
        public Vector3 RightWrist;
        /// <summary>Human: the direction the fingers point from each wrist (need not be normalised).</summary>
        public Vector3 LeftFingers;
        public Vector3 RightFingers;
        /// <summary>Human: the body's distance behind the furniture's centre while carrying, metres along the facing.</summary>
        public float HumanStand;
        /// <summary>Human: the spine's forward lean while carrying, degrees.</summary>
        public float HumanLean;
        /// <summary>The dog: the point it bites.</summary>
        public Vector3 Snout;

        /// <summary>Human: how far the body's model stands behind its rule position while carrying (negative: ahead of it).</summary>
        public float HumanHoldBack(float carryForward) => HumanStand - carryForward;

        /// <summary>The grip of a body kind, a new instance on every call; null or unknown gives the chair's.</summary>
        public static GripDef For(string kind)
        {
            switch (kind)
            {
                case "stool":
                    // The bar stool: seat rim r 0.175 at y 0.50 (cushion 0.45 to 0.55), four legs at x +-0.088, z +-0.097, foot
                    // ring at y 0.16 to 0.18. Hands on the seat's sides, fingers forward along them; the body a little ahead of
                    // its rule position and leaning, so the near straight arms reach the seat lifted only 0.30 m (0.55 of 0.56 m). The dog bites the
                    // near left leg low (the PO's "a leg or the low rung, near floor height", not the seat).
                    return new GripDef
                    {
                        Kind = "stool",
                        LeftWrist = new Vector3(-0.20f, 0.53f, -0.05f), RightWrist = new Vector3(0.20f, 0.53f, -0.05f),
                        LeftFingers = new Vector3(0.15f, -0.2f, 1f), RightFingers = new Vector3(-0.15f, -0.2f, 1f),
                        HumanStand = 0.42f, HumanLean = 14f,
                        Snout = new Vector3(-0.075f, 0.28f, -0.10f), // MUTATION:GRIP_STOOL_LOW
                    };
                case "armchair":
                    // The lounge chair: backrest z -0.425 to -0.24, top at 1.05, x +-0.33; a solid base up to 0.21. Hands on the
                    // backrest's top; the dog bites the low back of it, just above the base.
                    return new GripDef
                    {
                        Kind = "armchair",
                        LeftWrist = new Vector3(-0.24f, 1.08f, -0.44f), RightWrist = new Vector3(0.24f, 1.08f, -0.44f),
                        LeftFingers = new Vector3(0f, -0.45f, 1f), RightFingers = new Vector3(0f, -0.45f, 1f),
                        HumanStand = 0.75f, HumanLean = 0f,
                        Snout = new Vector3(0f, 0.28f, -0.43f),
                    };
                case "floor_lamp":
                    // The round floor lamp: a 0.02 m pole at the centre from the domed foot (0.18) to the shade (1.26). Both
                    // hands round the pole from behind, the right one higher; the dog bites the pole just above the foot.
                    return new GripDef
                    {
                        Kind = "floor_lamp",
                        LeftWrist = new Vector3(-0.035f, 0.80f, -0.045f), RightWrist = new Vector3(0.035f, 1.00f, -0.045f),
                        LeftFingers = new Vector3(1f, 0f, 0.6f), RightFingers = new Vector3(-1f, 0f, 0.6f),
                        HumanStand = 0.40f, HumanLean = 0f,
                        Snout = new Vector3(0f, 0.34f, -0.03f),
                    };
                case "office_chair":
                    // FurnitureKit.OfficeChair: the padded backrest from y 0.62 to 1.0, its back face at z -0.305, 0.495 wide;
                    // the seat from 0.43 to 0.50, its rear rim at z -0.275. Hands on the backrest's top; the dog bites the
                    // seat's rear rim (the base below is a tangle of spokes and casters).
                    return new GripDef
                    {
                        Kind = "office_chair",
                        LeftWrist = new Vector3(-0.17f, 1.03f, -0.34f), RightWrist = new Vector3(0.17f, 1.03f, -0.34f),
                        LeftFingers = new Vector3(0f, -0.45f, 1f), RightFingers = new Vector3(0f, -0.45f, 1f),
                        HumanStand = 0.68f, HumanLean = 0f,
                        Snout = new Vector3(0f, 0.42f, -0.28f),
                    };
                case "rocking_chair":
                    // FurnitureKit.RockingChair: the back posts at x +-0.28 lean back 12 deg to the top (1.04, z -0.32), the
                    // runners reach z -0.41 at the floor; the seat's rear rim at z -0.21, y 0.42 to 0.47. Hands on the posts' tops; the dog bites
                    // the seat's rear rim between the runners (on a back post, its body would stand on the runner).
                    return new GripDef
                    {
                        Kind = "rocking_chair",
                        LeftWrist = new Vector3(-0.22f, 1.07f, -0.37f), RightWrist = new Vector3(0.22f, 1.07f, -0.37f),
                        LeftFingers = new Vector3(0f, -0.45f, 1f), RightFingers = new Vector3(0f, -0.45f, 1f),
                        HumanStand = 0.72f, HumanLean = 0f,
                        Snout = new Vector3(0f, 0.42f, -0.21f),
                    };
                default:
                    // The Kenney chair: the backrest's top rail at y 0.82 to 0.90, z -0.225 to -0.135, x +-0.225; the seat
                    // 0.36 to 0.46; the legs at the corners (+-0.205), a stretcher ring at y 0.10 to 0.13. Hands on the top
                    // rail, the fingers over it; the body 0.56 m behind the centre (0.11 m behind the rule position), so the
                    // backrest stays a forearm ahead of the belly. The dog bites the left back leg low.
                    return new GripDef
                    {
                        Kind = "chair",
                        LeftWrist = new Vector3(-0.15f, 0.935f, -0.245f), RightWrist = new Vector3(0.15f, 0.935f, -0.245f),
                        LeftFingers = new Vector3(0f, -0.45f, 1f), RightFingers = new Vector3(0f, -0.45f, 1f),
                        HumanStand = 0.56f, HumanLean = 0f,
                        Snout = new Vector3(-0.205f, 0.26f, -0.23f),
                    };
            }
        }
    }

    /// <summary>
    /// GRIP, presentation only: the dog's head lowered onto the point it bites. The neck chain (its base, then the segments
    /// to the head bone) and the snout tip ahead of the head bone are given in the dog's body plane (x forward, y up, metres
    /// from its feet). A bend of the neck turns the first segment by a third of it, the second by two thirds and the last by
    /// all of it (nose down), and the head follows by <paramref name="headFollow"/> times the bend, so the head comes down in
    /// a smooth curve with the muzzle pointing at the bite.
    /// </summary>
    public static class GripMath
    {
        /// <summary>The largest neck bend the solver uses, degrees.</summary>
        public const float MaxNeckBend = 80f;

        /// <summary>Turns <paramref name="v"/> (x forward, y up) nose down by <paramref name="degrees"/>.</summary>
        public static Vector2 Down(Vector2 v, float degrees)
        {
            float a = degrees * Mathf.Deg2Rad;
            float c = Mathf.Cos(a);
            float s = Mathf.Sin(a);
            return new Vector2(v.x * c + v.y * s, v.y * c - v.x * s);
        }

        /// <summary>Where the snout tip is for a neck bend of <paramref name="bend"/> degrees.</summary>
        public static Vector2 Tip(Vector2 neckBase, Vector2[] segments, Vector2 tipFromHead, float bend, float headFollow)
        {
            Vector2 p = neckBase;
            int n = segments != null ? segments.Length : 0;
            for (int i = 0; i < n; i++)
            {
                p += Down(segments[i], bend * (i + 1) / n);
            }
            return p + Down(tipFromHead, bend * headFollow);
        }

        /// <summary>
        /// The neck bend, degrees in [0, <see cref="MaxNeckBend"/>], that puts the snout tip at <paramref name="targetHeight"/>
        /// (0 when the tip is already at or below it, MaxNeckBend when it cannot get down to it). The tip's height falls as the
        /// bend grows over that range, so a bisection finds it.
        /// </summary>
        public static float SolveNeckBend(Vector2 neckBase, Vector2[] segments, Vector2 tipFromHead, float headFollow, float targetHeight)
        {
            if (Tip(neckBase, segments, tipFromHead, 0f, headFollow).y <= targetHeight)
            {
                return 0f;
            }
            if (Tip(neckBase, segments, tipFromHead, MaxNeckBend, headFollow).y >= targetHeight)
            {
                return MaxNeckBend;
            }
            float lo = 0f;
            float hi = MaxNeckBend;
            for (int i = 0; i < 18; i++)
            {
                float mid = 0.5f * (lo + hi);
                if (Tip(neckBase, segments, tipFromHead, mid, headFollow).y > targetHeight)
                {
                    lo = mid;
                }
                else
                {
                    hi = mid;
                }
            }
            return 0.5f * (lo + hi);
        }
    }
}
