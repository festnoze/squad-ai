using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// The one and only bridge between DESIGN space (the Godot convention every
    /// authored number uses: x right, y up, -z forward, right handed) and Unity
    /// space (+z forward, left handed). PRD section 4.2.
    ///
    /// The conversion is a mirror on z. It must be applied exactly once, where a
    /// world or local position or direction is set, and nowhere else: applying it
    /// twice is the identity and silently puts the world back to front. Sizes are
    /// never converted, because a mirror does not change an extent.
    ///
    /// A mirror flips the sign of every rotation. Never port a rotation sign from
    /// the original GDScript: port the on-screen behavior the PRD describes.
    /// </summary>
    public static class DesignSpace
    {
        /// <summary>Forward in design space, the direction a photo looks along.</summary>
        public static readonly Vector3 DesignForward = new Vector3(0f, 0f, -1f);

        /// <summary>Forward in Unity space. ToUnity(DesignForward) == UnityForward.</summary>
        public static readonly Vector3 UnityForward = new Vector3(0f, 0f, 1f);

        /// <summary>
        /// Mirrors a design-space position or direction into Unity space. The same
        /// function serves both: a mirror is linear, so it maps directions the way
        /// it maps points.
        /// </summary>
        public static Vector3 ToUnity(Vector3 v)
        {
            return new Vector3(v.x, v.y, -v.z);
        }

        /// <summary>
        /// Design yaw in radians (Godot: counter-clockwise about +y seen from above)
        /// to Unity degrees. The sign flips with the mirror. Every level authors
        /// spawn_yaw = 0, so no level pins the sign: the unit suite does.
        /// </summary>
        public static float YawToUnityDegrees(float yawRadians)
        {
            return -yawRadians * Mathf.Rad2Deg;
        }
    }
}
