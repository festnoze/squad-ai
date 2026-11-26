using UnityEngine;

namespace OutOfSight.Core
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5_v3.md 2 and 15.4, CONTRACT_M5.md 16.6): the one floor height source of a level, from its
    /// platforms and ramps. Logic stays planar; eyes, sample points, teleports, spawns, decoys, props, visuals and the
    /// audit's sight rays add <see cref="HeightAt"/> of their planar position.
    /// <list type="bullet">
    /// <item>Inside a platform's rectangle (edges included): the platform's height.</item>
    /// <item>On a ramp (its X, Z is its centre, its Yaw points uphill, it is Width wide and Length long): linear from 0 at
    /// its foot to its platform's height at its head.</item>
    /// <item>Anywhere else: 0. Where two of them touch (a ramp head on its platform edge) the higher one wins.</item>
    /// </list>
    /// It reads the level's lists on every call (a handful of platforms and ramps), so a level edited in code after its
    /// <see cref="LevelDef.Floor"/> was first read never sees a stale height. <see cref="Flat"/> is the floor of no level.
    /// </summary>
    public sealed class FloorMap
    {
        /// <summary>The floor of no level: 0 everywhere.</summary>
        public static readonly FloorMap Flat = new FloorMap(null);

        private const float Eps = 1e-4f;

        private readonly LevelDef level;

        public FloorMap(LevelDef level)
        {
            this.level = level;
        }

        /// <summary>The level this floor was built from (null for <see cref="Flat"/>).</summary>
        public LevelDef Level => level;

        /// <summary>True when the level has no platform and no ramp: the floor is 0 everywhere.</summary>
        public bool IsFlat => level == null || ((level.Platforms == null || level.Platforms.Count == 0) && (level.Ramps == null || level.Ramps.Count == 0));

        /// <summary>The walkable floor height at a planar point: a platform's height, a ramp's interpolation, or 0.</summary>
        public float HeightAt(float x, float z)
        {
            return Raised(x, z); // MUTATION:FLOOR_MAP
        }

        /// <summary><see cref="HeightAt"/> of the planar position of <paramref name="p"/> (its y is ignored).</summary>
        public float HeightAt(Vector3 p)
        {
            return HeightAt(p.x, p.z);
        }

        /// <summary><paramref name="p"/> put on the floor: its planar position at <see cref="HeightAt"/>.</summary>
        public Vector3 OnFloor(Vector3 p)
        {
            return new Vector3(p.x, HeightAt(p.x, p.z), p.z);
        }

        private float Raised(float x, float z)
        {
            if (IsFlat)
            {
                return 0f;
            }
            float height = 0f;
            if (level.Platforms != null)
            {
                foreach (PlatformDef p in level.Platforms)
                {
                    if (p != null && Inside(p, x, z, Eps))
                    {
                        height = Mathf.Max(height, p.Height);
                    }
                }
            }
            if (level.Ramps != null)
            {
                foreach (RampDef r in level.Ramps)
                {
                    if (r != null && OnRamp(r, x, z, Eps, out float along))
                    {
                        height = Mathf.Max(height, RampHeight(r, along));
                    }
                }
            }
            return height;
        }

        /// <summary>True when the planar point lies in the platform's rectangle, grown by <paramref name="margin"/>.</summary>
        public static bool Inside(PlatformDef p, float x, float z, float margin)
        {
            return Mathf.Abs(x - p.X) <= p.SizeX * 0.5f + margin && Mathf.Abs(z - p.Z) <= p.SizeZ * 0.5f + margin;
        }

        /// <summary>
        /// True when the planar point lies on the ramp's footprint grown by <paramref name="margin"/>; <paramref name="along"/>
        /// is its distance from the foot along the uphill axis (0 at the foot, Length at the head, clamped).
        /// </summary>
        public static bool OnRamp(RampDef r, float x, float z, float margin, out float along)
        {
            Vector3 local = YawMath.Rotate(new Vector3(x - r.X, 0f, z - r.Z), -r.Yaw);
            along = Mathf.Clamp(local.z + r.Length * 0.5f, 0f, r.Length);
            return Mathf.Abs(local.x) <= r.Width * 0.5f + margin && Mathf.Abs(local.z) <= r.Length * 0.5f + margin;
        }

        /// <summary>The height of the platform a ramp leads to (0 when the level names no such platform).</summary>
        public float HeadHeight(RampDef r)
        {
            PlatformDef p = PlatformOf(level, r);
            return p != null ? p.Height : 0f;
        }

        /// <summary>The platform a ramp names, or null.</summary>
        public static PlatformDef PlatformOf(LevelDef level, RampDef r)
        {
            if (level?.Platforms == null || r == null)
            {
                return null;
            }
            foreach (PlatformDef p in level.Platforms)
            {
                if (p != null && p.Name == r.Platform)
                {
                    return p;
                }
            }
            return null;
        }

        private float RampHeight(RampDef r, float along)
        {
            float head = HeadHeight(r);
            return r.Length > Eps ? head * Mathf.Clamp01(along / r.Length) : head;
        }

        /// <summary>The slope of a ramp in degrees: atan(head height / length).</summary>
        public float SlopeOf(RampDef r)
        {
            return r.Length > Eps ? Mathf.Atan2(HeadHeight(r), r.Length) * Mathf.Rad2Deg : 90f;
        }
    }
}
