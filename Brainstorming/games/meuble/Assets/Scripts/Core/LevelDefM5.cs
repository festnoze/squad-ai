using System.Collections.Generic;
using Newtonsoft.Json;
using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>M5 (docs/CONTRACT_M5_v3.md 2 and 15.4): a raised, axis-aligned walkable area.</summary>
    public sealed class PlatformDef
    {
        public string Name;
        public float X;
        public float Z;
        public float SizeX;
        public float SizeZ;
        public float Height;
        public string Color;
    }

    /// <summary>M5: a ramp from the floor (its foot) up to a named platform's height (its head); Yaw points uphill.</summary>
    public sealed class RampDef
    {
        public float X;
        public float Z;
        public float Width;
        public float Length;
        public float Yaw;
        public string Platform;
    }

    /// <summary>M5: a planar point.</summary>
    public sealed class PointDef
    {
        public float X;
        public float Z;

        [JsonIgnore] public Vector3 Position => new Vector3(X, 0f, Z);
    }

    /// <summary>M5 (docs/CONTRACT_M5.md 4, 16.8): a robot vacuum following a loop of waypoints.</summary>
    public sealed class RobotDef
    {
        public string Name;
        public List<PointDef> Loop = new List<PointDef>();
        /// <summary>m/s; 0 means Tuning.RobotSpeed.</summary>
        [JsonProperty(DefaultValueHandling = DefaultValueHandling.Ignore)]
        public float Speed;
        /// <summary>The waypoint index it starts at.</summary>
        [JsonProperty(DefaultValueHandling = DefaultValueHandling.Ignore)]
        public int Start;
    }

    /// <summary>
    /// M6 (docs/CONTRACT_M6.md 2.5): the wardrobe, a prop of kind "wardrobe", 1.0 x 2.0 x 0.6 m, a full occluder. Its
    /// <b>front</b> is its local +z face, facing <c>YawMath.Forward(prop.Yaw)</c>; the front face lies SizeZ / 2 ahead of the
    /// prop centre. Pure rules shared by GameState, the validator and the audit:
    /// <list type="bullet">
    /// <item><see cref="Fits"/>: a body fits when its width and depth are at most <see cref="Tuning.WardrobeFitWidth"/> and its
    /// height plus a load's at most <see cref="Tuning.WardrobeFitHeight"/> (the stool and the floor lamp).</item>
    /// <item><see cref="InFront"/>: the furniture centre stands ahead of the front face by more than 0 and at most
    /// <see cref="Tuning.WardrobeReach"/>, and within half the wardrobe width sideways from its axis (no facing
    /// condition, as for a door).</item>
    /// </list>
    /// </summary>
    public static class WardrobeRule
    {
        public const string Kind = "wardrobe";

        private const float Eps = 1e-4f;

        public static bool IsWardrobe(PropDef prop) => prop != null && prop.Kind == Kind;

        /// <summary>The planar unit normal of the front face (local +z).</summary>
        public static Vector3 Front(PropDef wardrobe) => YawMath.Forward(wardrobe.Yaw);

        /// <summary>A body of <paramref name="size"/> (w, h, d) carrying <paramref name="extraHeight"/> on top fits inside.</summary>
        public static bool Fits(Vector3 size, float extraHeight)
        {
            bool narrow = size.x <= Tuning.WardrobeFitWidth + Eps && size.z <= Tuning.WardrobeFitWidth + Eps; // MUTATION:WARDROBE_FIT
            return narrow && size.y + Mathf.Max(0f, extraHeight) <= Tuning.WardrobeFitHeight + Eps;
        }

        /// <summary>
        /// Where a planar point stands relative to the front face: <paramref name="ahead"/> along the front normal from the
        /// face (positive in front), <paramref name="lateral"/> sideways from the wardrobe's axis.
        /// </summary>
        public static void FrontFrame(PropDef wardrobe, Vector3 point, out float ahead, out float lateral)
        {
            Vector3 front = Front(wardrobe);
            Vector3 right = new Vector3(front.z, 0f, -front.x);
            Vector3 d = YawMath.Planar(point - wardrobe.Position);
            ahead = Vector3.Dot(d, front) - wardrobe.SizeZ * 0.5f;
            lateral = Vector3.Dot(d, right);
        }

        /// <summary>The furniture centre stands in the entry zone in front of the wardrobe (see the class summary).</summary>
        public static bool InFront(PropDef wardrobe, Vector3 point)
        {
            FrontFrame(wardrobe, point, out float ahead, out float lateral);
            return ahead > 0f && ahead <= Tuning.WardrobeReach + Eps && Mathf.Abs(lateral) <= wardrobe.SizeX * 0.5f + Eps;
        }

        /// <summary>A furniture of <paramref name="size"/> at <paramref name="point"/> may enter <paramref name="wardrobe"/>.</summary>
        public static bool CanEnter(PropDef wardrobe, Vector3 point, Vector3 size, float extraHeight)
        {
            return IsWardrobe(wardrobe) && Fits(size, extraHeight) && InFront(wardrobe, point);
        }

        /// <summary>The centre of the entry zone (the strip WardrobeReach deep along the whole front face), planar.</summary>
        public static Vector3 EntryCenter(PropDef wardrobe)
        {
            return wardrobe.Position + Front(wardrobe) * (wardrobe.SizeZ * 0.5f + Tuning.WardrobeReach * 0.5f);
        }
    }
}
