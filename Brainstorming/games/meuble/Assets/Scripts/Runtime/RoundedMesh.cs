using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// M9 soft shapes: the rounded meshes of the room objects (beds, bathroom, kitchen), so they share the soft look of the
    /// inhabitants instead of reading as sharp boxes. A shape is a sweep: a stack of horizontal rings, each a rounded
    /// rectangle (half extents, centre, corner radius, height) carrying its own profile normal, joined band by band, with an
    /// optional flat cap closing the first ring (facing down) and the last one (facing up). One corner segment count for the
    /// whole sweep keeps the rings' vertices in step.
    /// <list type="bullet">
    /// <item>Normals are analytic (the caller's profile normal turned by each vertex's outward direction in plan), so a quarter
    /// circle sampled with one or two segments still shades round; two rings at the same place with different normals make
    /// a crease (their empty band is skipped).</item>
    /// <item>UVs in metres, as every PrimitiveKit mesh (M4.2): a flat band and the caps project on the floor plane, any
    /// other band runs U around the rings and V along the profile, so a surface's detail repeats at its tile.</item>
    /// <item>Built in the frame of the part (x and z centred, y from 0 up), cached by geometry and kept across level
    /// rebuilds (DontUnloadUnusedAsset), so CombinedMesh's cache by mesh keeps working.</item>
    /// </list>
    /// Triangles: 8 (m + 1) per band and 4 m + 2 per cap, with m the corner segments.
    /// </summary>
    public static class RoundedMesh
    {
        /// <summary>One ring of a sweep: a rounded rectangle at height <see cref="Y"/> and its profile normal.</summary>
        public struct Ring
        {
            public float HalfX;
            public float HalfZ;
            public float CenterX;
            public float CenterZ;
            public float Y;
            /// <summary>The corner radius in plan, clamped to the half extents (their smaller: a stadium).</summary>
            public float Radius;
            /// <summary>The profile normal: its outward (in plan) and upward components.</summary>
            public float NormalOut;
            public float NormalUp;
        }

        /// <summary>A ring centred on the axis.</summary>
        public static Ring At(float halfX, float halfZ, float y, float radius, float normalOut, float normalUp)
        {
            return new Ring { HalfX = halfX, HalfZ = halfZ, Y = y, Radius = radius, NormalOut = normalOut, NormalUp = normalUp };
        }

        /// <summary>A ring centred at (<paramref name="centerX"/>, <paramref name="centerZ"/>).</summary>
        public static Ring At(float halfX, float halfZ, float centerX, float centerZ, float y, float radius, float normalOut, float normalUp)
        {
            return new Ring
            {
                HalfX = halfX, HalfZ = halfZ, CenterX = centerX, CenterZ = centerZ, Y = y, Radius = radius,
                NormalOut = normalOut, NormalUp = normalUp,
            };
        }

        private static readonly Dictionary<string, Mesh> Cache = new Dictionary<string, Mesh>();

        /// <summary>
        /// A rounded block of <paramref name="size"/> standing on y = 0: its corners rounded by <paramref name="corner"/> in
        /// plan, its bottom and top edges by quarter circles of <paramref name="bottomRound"/> and <paramref name="topRound"/>
        /// sampled with the given segments (0: a sharp edge). A cap closes the bottom and the top when asked.
        /// </summary>
        public static Mesh Slab(Vector3 size, float corner, float bottomRound, int bottomSegments, float topRound, int topSegments,
            int cornerSegments, bool capBottom, bool capTop)
        {
            float hx = size.x * 0.5f;
            float hz = size.z * 0.5f;
            float h = size.y;
            float limit = Mathf.Min(hx, hz);
            float br = bottomSegments > 0 ? Mathf.Clamp(bottomRound, 0f, Mathf.Min(limit, h)) : 0f;
            float tr = topSegments > 0 ? Mathf.Clamp(topRound, 0f, Mathf.Min(limit, h - br)) : 0f;
            corner = Mathf.Clamp(corner, 0f, limit);
            var rings = new List<Ring>();
            void Add(float inset, float y, float normalOut, float normalUp)
            {
                // The corner in plan follows the edge rounding inward, never quite sharp.
                var ring = At(hx - inset, hz - inset, y, Mathf.Max(corner - inset, corner * 0.5f), normalOut, normalUp);
                if (rings.Count > 0)
                {
                    Ring last = rings[rings.Count - 1];
                    if (Mathf.Abs(last.Y - ring.Y) < 1e-5f && Mathf.Abs(last.HalfX - ring.HalfX) < 1e-5f)
                    {
                        return;
                    }
                }
                rings.Add(ring);
            }
            if (br > 0f)
            {
                for (int k = 0; k <= bottomSegments; k++)
                {
                    float phi = (-90f + 90f * k / bottomSegments) * Mathf.Deg2Rad;
                    Add(br * (1f - Mathf.Cos(phi)), br + br * Mathf.Sin(phi), Mathf.Cos(phi), Mathf.Sin(phi));
                }
            }
            else
            {
                Add(0f, 0f, 1f, 0f);
            }
            if (tr > 0f)
            {
                for (int k = 0; k <= topSegments; k++)
                {
                    float phi = 90f * k / topSegments * Mathf.Deg2Rad;
                    Add(tr * (1f - Mathf.Cos(phi)), h - tr + tr * Mathf.Sin(phi), Mathf.Cos(phi), Mathf.Sin(phi));
                }
            }
            else
            {
                Add(0f, h, 1f, 0f);
            }
            return Sweep(rings, cornerSegments, capBottom, capTop);
        }

        /// <summary>The sweep of <paramref name="rings"/> (bottom to top along the profile), see the class summary.</summary>
        public static Mesh Sweep(IList<Ring> rings, int cornerSegments, bool capStart, bool capEnd)
        {
            int m = Mathf.Max(1, cornerSegments);
            string key = Key(rings, m, capStart, capEnd);
            if (Cache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            int count = 4 * (m + 1) + 1;
            var points = new Vector3[rings.Count][];
            var normals = new Vector3[rings.Count][];
            var around = new float[rings.Count][];
            for (int i = 0; i < rings.Count; i++)
            {
                Points(rings[i], m, out points[i], out normals[i], out around[i]);
            }

            var vertices = new List<Vector3>();
            var vertexNormals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            var along = new float[count];
            for (int i = 1; i < rings.Count; i++)
            {
                Vector3[] a = points[i - 1];
                Vector3[] b = points[i];
                float span = 0f;
                for (int j = 0; j < count; j++)
                {
                    span += (b[j] - a[j]).magnitude;
                }
                if (span < 1e-5f)
                {
                    // A crease: the same ring twice, two normals.
                    continue;
                }
                bool flat = Mathf.Abs(rings[i - 1].NormalUp) > 0.7f && Mathf.Abs(rings[i].NormalUp) > 0.7f
                    && Mathf.Abs(rings[i - 1].Y - rings[i].Y) < 0.5f * span / count;
                int start = vertices.Count;
                for (int row = 0; row < 2; row++)
                {
                    int r = i - 1 + row;
                    for (int j = 0; j < count; j++)
                    {
                        Vector3 p = points[r][j];
                        vertices.Add(p);
                        vertexNormals.Add(normals[r][j]);
                        if (flat)
                        {
                            uvs.Add(new Vector2(p.x, p.z));
                        }
                        else
                        {
                            float u = (around[i - 1][j] + around[i][j]) * 0.5f;
                            float v = along[j] + (row == 0 ? 0f : (b[j] - a[j]).magnitude);
                            uvs.Add(new Vector2(u, v));
                        }
                    }
                }
                for (int j = 0; j < count; j++)
                {
                    along[j] += (b[j] - a[j]).magnitude;
                }
                for (int j = 0; j < count - 1; j++)
                {
                    int p0 = start + j;
                    int p1 = p0 + 1;
                    int q0 = start + count + j;
                    int q1 = q0 + 1;
                    Triangle(vertices, vertexNormals, triangles, p0, q0, p1);
                    Triangle(vertices, vertexNormals, triangles, p1, q0, q1);
                }
            }
            if (capStart)
            {
                Cap(rings[0], points[0], count, Vector3.down, vertices, vertexNormals, uvs, triangles);
            }
            if (capEnd)
            {
                Cap(rings[rings.Count - 1], points[rings.Count - 1], count, Vector3.up, vertices, vertexNormals, uvs, triangles);
            }

            var mesh = new Mesh { name = "Rounded" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(vertexNormals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Cache[key] = mesh;
            return mesh;
        }

        /// <summary>
        /// The <paramref name="m"/> segment rounded rectangle of a ring, counterclockwise from +x seen from above, its first
        /// point repeated at the end (the U seam): the points, their normals and their distance around.
        /// </summary>
        private static void Points(Ring ring, int m, out Vector3[] points, out Vector3[] normals, out float[] around)
        {
            int count = 4 * (m + 1) + 1;
            points = new Vector3[count];
            normals = new Vector3[count];
            around = new float[count];
            float ax = Mathf.Max(0f, ring.HalfX);
            float az = Mathf.Max(0f, ring.HalfZ);
            float radius = Mathf.Clamp(ring.Radius, 0f, Mathf.Min(ax, az));
            int index = 0;
            for (int c = 0; c < 4; c++)
            {
                float sx = c == 0 || c == 3 ? 1f : -1f;
                float sz = c < 2 ? 1f : -1f;
                for (int k = 0; k <= m; k++)
                {
                    float angle = (c * 90f + 90f * k / m) * Mathf.Deg2Rad;
                    float ox = Mathf.Cos(angle);
                    float oz = Mathf.Sin(angle);
                    points[index] = new Vector3(ring.CenterX + sx * (ax - radius) + radius * ox, ring.Y, ring.CenterZ + sz * (az - radius) + radius * oz);
                    normals[index] = new Vector3(ox * ring.NormalOut, ring.NormalUp, oz * ring.NormalOut).normalized;
                    index++;
                }
            }
            points[index] = points[0];
            normals[index] = normals[0];
            for (int j = 1; j < count; j++)
            {
                around[j] = around[j - 1] + (points[j] - points[j - 1]).magnitude;
            }
        }

        /// <summary>A flat cap over a ring, facing <paramref name="facing"/>, UVs on the floor plane. Nothing for a ring with no area.</summary>
        private static void Cap(Ring ring, Vector3[] points, int count, Vector3 facing, List<Vector3> vertices, List<Vector3> normals,
            List<Vector2> uvs, List<int> triangles)
        {
            if (ring.HalfX < 1e-4f || ring.HalfZ < 1e-4f)
            {
                return;
            }
            int start = vertices.Count;
            for (int j = 0; j < count - 1; j++)
            {
                vertices.Add(points[j]);
                normals.Add(facing);
                uvs.Add(new Vector2(points[j].x, points[j].z));
            }
            for (int j = 1; j < count - 2; j++)
            {
                Triangle(vertices, normals, triangles, start, start + j, start + j + 1);
            }
        }

        /// <summary>One triangle, wound so its face agrees with its vertex normals (Unity's clockwise front); none if it has no area.</summary>
        private static void Triangle(List<Vector3> vertices, List<Vector3> normals, List<int> triangles, int a, int b, int c)
        {
            Vector3 face = Vector3.Cross(vertices[b] - vertices[a], vertices[c] - vertices[a]);
            if (face.sqrMagnitude < 1e-14f)
            {
                return;
            }
            Vector3 n = normals[a] + normals[b] + normals[c];
            if (Vector3.Dot(face, n) < 0f)
            {
                (b, c) = (c, b);
            }
            triangles.Add(a);
            triangles.Add(b);
            triangles.Add(c);
        }

        private static string Key(IList<Ring> rings, int m, bool capStart, bool capEnd)
        {
            CultureInfo c = CultureInfo.InvariantCulture;
            var key = new StringBuilder("sweep").Append(m).Append(capStart ? 'S' : 's').Append(capEnd ? 'E' : 'e');
            foreach (Ring r in rings)
            {
                key.Append('|').Append(r.HalfX.ToString("0.#####", c)).Append(',').Append(r.HalfZ.ToString("0.#####", c))
                    .Append(',').Append(r.CenterX.ToString("0.#####", c)).Append(',').Append(r.CenterZ.ToString("0.#####", c))
                    .Append(',').Append(r.Y.ToString("0.#####", c)).Append(',').Append(r.Radius.ToString("0.#####", c))
                    .Append(',').Append(r.NormalOut.ToString("0.###", c)).Append(',').Append(r.NormalUp.ToString("0.###", c));
            }
            return key.ToString();
        }
    }
}
