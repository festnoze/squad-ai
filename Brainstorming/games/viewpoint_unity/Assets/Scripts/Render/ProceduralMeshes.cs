using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// The two meshes Unity has no primitive for. Both are cached: the game
    /// builds them per level and per photo, and identical rings and panels must
    /// share one mesh.
    /// </summary>
    public static class ProceduralMeshes
    {
        private static readonly Dictionary<string, Mesh> Cache = new Dictionary<string, Mesh>();

        /// <summary>
        /// Torus lying flat, its axis along +y, centered on the origin: the
        /// teleporter ring of PRD 5.7 (inner 1.05, outer 1.25), which spins in
        /// yaw. Unity ships no torus primitive, and Godot's TorusMesh that the
        /// original used has the same flat orientation.
        /// </summary>
        public static Mesh Torus(float innerRadius, float outerRadius, int majorSegments = 48, int minorSegments = 16)
        {
            if (majorSegments < 3)
            {
                majorSegments = 3;
            }

            if (minorSegments < 3)
            {
                minorSegments = 3;
            }

            string cacheKey = "torus:" + Exact(innerRadius) + ":" + Exact(outerRadius) + ":" + majorSegments + ":" + minorSegments;
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            float ringRadius = (outerRadius + innerRadius) * 0.5f;
            float tubeRadius = Mathf.Abs(outerRadius - innerRadius) * 0.5f;

            // One extra column and row duplicate the seam so the uv wraps
            // cleanly instead of running backwards across the last quad.
            int columns = majorSegments + 1;
            int rows = minorSegments + 1;

            Vector3[] vertices = new Vector3[columns * rows];
            Vector3[] normals = new Vector3[columns * rows];
            Vector2[] uvs = new Vector2[columns * rows];

            for (int i = 0; i < columns; i++)
            {
                float major = (i / (float)majorSegments) * Mathf.PI * 2f;
                float majorCos = Mathf.Cos(major);
                float majorSin = Mathf.Sin(major);

                for (int j = 0; j < rows; j++)
                {
                    float minor = (j / (float)minorSegments) * Mathf.PI * 2f;
                    float minorCos = Mathf.Cos(minor);
                    float minorSin = Mathf.Sin(minor);

                    // The surface normal of a torus is the unit vector from the
                    // point of the ring circle to the surface point, so the
                    // vertex is just that circle plus the normal times the tube
                    // radius. No RecalculateNormals needed.
                    Vector3 normal = new Vector3(majorCos * minorCos, minorSin, majorSin * minorCos);
                    Vector3 ringPoint = new Vector3(majorCos * ringRadius, 0f, majorSin * ringRadius);

                    int index = (i * rows) + j;
                    normals[index] = normal;
                    vertices[index] = ringPoint + (normal * tubeRadius);
                    uvs[index] = new Vector2(i / (float)majorSegments, j / (float)minorSegments);
                }
            }

            int[] triangles = new int[majorSegments * minorSegments * 6];
            int cursor = 0;
            for (int i = 0; i < majorSegments; i++)
            {
                for (int j = 0; j < minorSegments; j++)
                {
                    int a = (i * rows) + j;
                    int b = a + 1;
                    int c = a + rows;
                    int d = c + 1;

                    // This winding puts the front faces outward under Unity's
                    // clockwise convention (checked by hand at major = 0,
                    // minor = 0, where the normal must be +x).
                    triangles[cursor++] = a;
                    triangles[cursor++] = b;
                    triangles[cursor++] = c;
                    triangles[cursor++] = b;
                    triangles[cursor++] = d;
                    triangles[cursor++] = c;
                }
            }

            Mesh mesh = new Mesh();
            mesh.name = "Torus_" + Exact(innerRadius) + "_" + Exact(outerRadius);
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// Flat panel in the xy plane, used for the painted backdrop of a photo.
        /// Its normal is (0, 0, -1), like Unity's own Quad primitive: the
        /// backdrop sits in front of the eye along +z (design space -z after the
        /// mirror) and must face back at it.
        /// </summary>
        public static Mesh Quad(Vector2 size)
        {
            string cacheKey = "quad:" + Exact(size.x) + ":" + Exact(size.y);
            Mesh cached;
            if (Cache.TryGetValue(cacheKey, out cached) && cached != null)
            {
                return cached;
            }

            float halfX = size.x * 0.5f;
            float halfY = size.y * 0.5f;

            Vector3[] vertices =
            {
                new Vector3(-halfX, -halfY, 0f),
                new Vector3(halfX, -halfY, 0f),
                new Vector3(-halfX, halfY, 0f),
                new Vector3(halfX, halfY, 0f),
            };

            Vector3 normal = new Vector3(0f, 0f, -1f);
            Vector3[] normals = { normal, normal, normal, normal };

            // v = 0 at the bottom, matching the backdrop gradient texture.
            Vector2[] uvs =
            {
                new Vector2(0f, 0f),
                new Vector2(1f, 0f),
                new Vector2(0f, 1f),
                new Vector2(1f, 1f),
            };

            int[] triangles = { 0, 2, 1, 2, 3, 1 };

            Mesh mesh = new Mesh();
            mesh.name = "Quad_" + Exact(size.x) + "x" + Exact(size.y);
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uvs;
            mesh.triangles = triangles;
            mesh.RecalculateBounds();

            Cache[cacheKey] = mesh;
            return mesh;
        }

        /// <summary>
        /// Drops every cached mesh so the next call rebuilds one. Used by the
        /// tests. The meshes themselves are not destroyed: a renderer somewhere
        /// may still be pointing at one.
        /// </summary>
        public static void ClearCache()
        {
            Cache.Clear();
        }

        // Round trip formatting under the invariant culture: a cache key must
        // not change with the machine's decimal separator, and two sizes that
        // differ in the last bit must not collide.
        private static string Exact(float value)
        {
            return value.ToString("R", CultureInfo.InvariantCulture);
        }
    }
}
