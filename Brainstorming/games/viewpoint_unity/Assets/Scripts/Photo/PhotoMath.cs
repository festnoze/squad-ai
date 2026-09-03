using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Pure geometry of the photo mechanic: the placement frustum used both to
    /// erase world objects and to size the backdrop, and the pinhole projection
    /// used to draw thumbnails.
    /// <para>
    /// Camera space convention here is DESIGN space: x right, y up, -z forward,
    /// so depth is <c>-local.z</c>. Nothing is mirrored in this file; callers
    /// hand it design-space points and mirror on their own side if they need to.
    /// </para>
    /// </summary>
    public static class PhotoMath
    {
        /// <summary>
        /// Square photos, like a polaroid. The fov is vertical (and horizontal,
        /// since the aspect is 1). Narrower than the player camera on purpose:
        /// the photo is a window inside the view, not the whole view.
        /// </summary>
        public const float PhotoFovDeg = 50f;

        /// <summary>Square frame: width over height.</summary>
        public const float PhotoAspect = 1f;

        /// <summary>
        /// Erase reach used when a photo definition declares no
        /// <c>erase_depth</c> (PRD 6.1; the original reads it as
        /// <c>def.get("erase_depth", DEFAULT_ERASE_DEPTH)</c> in the placer).
        /// It is NOT tied to the backdrop: since v6.1 the backdrop stands far
        /// behind the carve, so the two depths are independent numbers.
        /// </summary>
        public const float DefaultEraseDepth = 12f;

        /// <summary>
        /// Half height of the frustum cross-section at the given forward depth.
        /// Zero at the apex, and linear in depth.
        /// </summary>
        /// <param name="depth">Forward distance from the eye, in meters.</param>
        /// <param name="fovDeg">Vertical field of view, in degrees.</param>
        public static float HalfExtentAt(float depth, float fovDeg)
        {
            return depth * Mathf.Tan(fovDeg * 0.5f * Mathf.Deg2Rad);
        }

        /// <summary>
        /// True when a camera-space point sits inside the photo frustum.
        /// </summary>
        /// <param name="local">Point in camera space (design space, -z forward).</param>
        /// <param name="fovDeg">Vertical field of view, in degrees.</param>
        /// <param name="aspect">Width over height of the frame.</param>
        /// <param name="near">Nearest kept depth; anything closer is out.</param>
        /// <param name="far">Farthest kept depth; anything beyond is out.</param>
        public static bool PointInFrustum(Vector3 local, float fovDeg, float aspect, float near, float far)
        {
            float depth = -local.z;
            if (depth < near || depth > far)
            {
                return false;
            }
            float halfV = HalfExtentAt(depth, fovDeg);
            float halfH = halfV * aspect;
            return Mathf.Abs(local.x) <= halfH && Mathf.Abs(local.y) <= halfV;
        }

        /// <summary>
        /// Pinhole projection of a camera-space point onto the photo plane.
        /// Returns normalized coordinates in [-1, 1] on both axes for points
        /// inside the frustum, (0, 0) at the photo center, y up.
        /// </summary>
        /// <param name="local">Point in camera space (design space, -z forward).</param>
        /// <param name="fovDeg">Vertical field of view, in degrees.</param>
        /// <param name="aspect">Width over height of the frame.</param>
        public static Vector2 ProjectPoint(Vector3 local, float fovDeg, float aspect)
        {
            // The depth floor keeps the divide finite for points at or behind
            // the apex; the caller is expected to have culled those already.
            float depth = Mathf.Max(0.01f, -local.z);
            float halfV = HalfExtentAt(depth, fovDeg);
            return new Vector2(local.x / (halfV * aspect), local.y / halfV);
        }

        /// <summary>
        /// Full size of a quad that exactly fills the frustum at the given depth.
        /// </summary>
        /// <param name="depth">Forward distance from the eye, in meters.</param>
        /// <param name="fovDeg">Vertical field of view, in degrees.</param>
        /// <param name="aspect">Width over height of the frame.</param>
        public static Vector2 BackdropSize(float depth, float fovDeg, float aspect)
        {
            float h = 2f * HalfExtentAt(depth, fovDeg);
            return new Vector2(h * aspect, h);
        }
    }
}
