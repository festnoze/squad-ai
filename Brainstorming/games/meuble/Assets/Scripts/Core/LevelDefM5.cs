using System.Collections.Generic;
using Newtonsoft.Json;
using UnityEngine;

namespace Meuble.Core
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
}
