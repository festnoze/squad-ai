// Owned by B0a. Contract 11.4: the actor field layer, the iso level, channel masks, the shared code-built quad and the
// blob support radius formula (binding for B1 and B2).
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class LiquidLayers
    {
        /// <summary>Layer rendered only by the actor field camera.</summary>
        public const int Field = 31;

        public const float IsoLevel = 0.5f;

        private static Mesh quad;

        /// <summary>(1,0,0,0), (0,1,0,0), (0,0,1,0), (0,0,0,1) for players 0..3; zero otherwise.</summary>
        public static Vector4 ChannelMask(int player)
        {
            switch (player)
            {
                case 0: return new Vector4(1f, 0f, 0f, 0f);
                case 1: return new Vector4(0f, 1f, 0f, 0f);
                case 2: return new Vector4(0f, 0f, 1f, 0f);
                case 3: return new Vector4(0f, 0f, 0f, 1f);
                default: return Vector4.zero;
            }
        }

        /// <summary>
        /// Built in code once: vertices (+/-0.5, +/-0.5, 0), uv0 in [0,1]^2, 2 triangles facing the camera (-Z), normals
        /// (0, 0, -1). Rebuilt if something destroyed it.
        /// </summary>
        public static Mesh QuadMesh
        {
            get
            {
                if (quad == null) quad = BuildQuad();
                return quad;
            }
        }

        /// <summary>
        /// Support radius of a blob f = A (1 - r^2)^2 whose 0.5 iso contour has radius visibleRadius:
        /// v / sqrt(1 - sqrt(0.5 / max(A, 0.51))) (below A = 0.51 the support of A = 0.51 is kept while the amplitude
        /// fades to 0).
        /// </summary>
        public static float SupportForVisibleRadius(float visibleRadius, float amplitude = 1f)
        {
            float a = Mathf.Max(amplitude, 0.51f);
            return visibleRadius / Mathf.Sqrt(1f - Mathf.Sqrt(IsoLevel / a));
        }

        private static Mesh BuildQuad()
        {
            var mesh = new Mesh { name = "PIO_Quad", hideFlags = HideFlags.HideAndDontSave };
            mesh.vertices = new[]
            {
                new Vector3(-0.5f, -0.5f, 0f), new Vector3(0.5f, -0.5f, 0f),
                new Vector3(-0.5f, 0.5f, 0f), new Vector3(0.5f, 0.5f, 0f),
            };
            mesh.uv = new[] { new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(0f, 1f), new Vector2(1f, 1f) };
            var n = new Vector3(0f, 0f, -1f);
            mesh.normals = new[] { n, n, n, n };
            // Clockwise as seen from the camera at z = -50 looking +Z (Unity's front face).
            mesh.triangles = new[] { 0, 2, 1, 2, 3, 1 };
            mesh.RecalculateBounds();
            mesh.UploadMeshData(false);
            return mesh;
        }
    }
}
