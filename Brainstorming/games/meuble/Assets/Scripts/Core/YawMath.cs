using UnityEngine;

namespace Meuble.Core
{
    /// <summary>
    /// Yaw convention of the whole game: degrees around +y, 0 faces +z, 90 faces +x
    /// (Unity's own Quaternion.Euler(0, yaw, 0) convention).
    /// </summary>
    public static class YawMath
    {
        public static float YawOf(Vector3 direction)
        {
            return Mathf.Atan2(direction.x, direction.z) * Mathf.Rad2Deg;
        }

        public static Vector3 Forward(float yawDeg)
        {
            float r = yawDeg * Mathf.Deg2Rad;
            return new Vector3(Mathf.Sin(r), 0f, Mathf.Cos(r));
        }

        /// <summary>Rotates a horizontal offset by a yaw (same as Quaternion.Euler(0, yaw, 0) * v for y = 0).</summary>
        public static Vector3 Rotate(Vector3 v, float yawDeg)
        {
            float r = yawDeg * Mathf.Deg2Rad;
            float c = Mathf.Cos(r);
            float s = Mathf.Sin(r);
            return new Vector3(v.x * c + v.z * s, v.y, -v.x * s + v.z * c);
        }

        public static Vector3 Planar(Vector3 v)
        {
            return new Vector3(v.x, 0f, v.z);
        }
    }
}
