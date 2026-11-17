using UnityEngine;

namespace Meuble.Core
{
    /// <summary>Geometric half of the vision test (PRD 4.1, checks 1 and 2). Occlusion is the Runtime's job.</summary>
    public static class VisionMath
    {
        /// <summary>
        /// True when <paramref name="point"/> is at most <paramref name="range"/> from the eye and within
        /// <paramref name="halfAngleDeg"/> of the forward vector. A true cone: one angle, measured in 3D.
        /// </summary>
        public static bool IsInCone(Vector3 eye, Vector3 forward, Vector3 point, float range, float halfAngleDeg)
        {
            Vector3 toPoint = point - eye;
            float distance = toPoint.magnitude;
            if (distance > range)
            {
                return false;
            }
            if (distance < 1e-5f)
            {
                return true;
            }
            float fwdLength = forward.magnitude;
            if (fwdLength < 1e-6f)
            {
                return false;
            }
            float cos = Vector3.Dot(forward / fwdLength, toPoint / distance);
            // The tolerance keeps a point placed exactly on the half angle inside despite float rounding.
            bool inside = cos >= Mathf.Cos(halfAngleDeg * Mathf.Deg2Rad) - 1e-6f;
            return inside; // MUTATION:CONE (mutation.sh inverts this line)
        }

        /// <summary>
        /// Fills <paramref name="output"/> (length 5) with the sample points of a furniture box resting on the
        /// floor at <paramref name="basePosition"/>: its center, then the four top corners, each pulled
        /// <paramref name="inset"/> inward (PRD 4.1).
        /// </summary>
        public static void SamplePoints(Vector3 basePosition, float yawDeg, Vector3 size, float inset, Vector3[] output)
        {
            float hx = size.x * 0.5f - inset;
            float hz = size.z * 0.5f - inset;
            float top = size.y - inset;
            output[0] = basePosition + new Vector3(0f, size.y * 0.5f, 0f);
            output[1] = basePosition + YawMath.Rotate(new Vector3(-hx, top, -hz), yawDeg);
            output[2] = basePosition + YawMath.Rotate(new Vector3(hx, top, -hz), yawDeg);
            output[3] = basePosition + YawMath.Rotate(new Vector3(hx, top, hz), yawDeg);
            output[4] = basePosition + YawMath.Rotate(new Vector3(-hx, top, hz), yawDeg);
        }
    }
}
