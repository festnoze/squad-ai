using System.Collections.Generic;
using System.Globalization;
using System.Text;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// Soft movers (product owner request, 2026-11-20): the furniture bodies, their decoys and the other moving objects get
    /// the soft, rounded look the room objects got in M9 (<see cref="RoundedMesh"/>: beds, bathroom, kitchen, shelves), with
    /// each one's silhouette, box, pivot and colliders unchanged (gameplay and the audit's routes never see a mesh).
    /// <list type="bullet">
    /// <item>The Kenney bodies (chair, bar stool, lounge chair, round floor lamp): <see cref="ApplyToModel"/> runs inside
    /// ModelKit.Instantiate, before the paint, and swaps the meshes of the instance for a rounded rebuild of the same design
    /// (every part where the GLB has it, measured on it as fractions of its box), so the model root, its renderers, its
    /// material slots, its box fit and every caller (the player, the decoys, an armchair prop, the title logo's chair) are
    /// unchanged. The Kenney GLBs draw their geometry twice (two root nodes with the same mesh); the rounded parts are
    /// shared out between the two renderers instead, so the triangles stay within PRD 7.4's 400 per piece of furniture
    /// and the draw calls stay the same.</item>
    /// <item>The procedural bodies (FurnitureKit: the office chair and the rocking chair, which have no model, and the
    /// fallbacks of the four others) build from the same designs, one renderer per named part as before.</item>
    /// <item>Built in the body frame (x and z centred, y from the floor, front on +z), in metres: corners are round in the
    /// world even under the models' non uniform box fit, and the UVs are in metres (U around, V along), so every detail
    /// repeats at its tile. Normals are analytic (a corner sampled with one or two segments still shades round).</item>
    /// </list>
    /// </summary>
    public static class SoftBodies
    {
        /// <summary>False keeps the Kenney bodies' own hard meshes (BodyShots' comparison shots, tests). The procedural bodies are always soft.</summary>
        public static bool RoundModels = true;

        /// <summary>
        /// One part of a design: a mesh placed in the body frame by <see cref="Matrix"/>, the source material it draws with
        /// on a model (<see cref="Source"/>: the GLB's material name) and the renderer it joins on a procedural body
        /// (<see cref="Part"/>).
        /// </summary>
        public struct Piece
        {
            public string Source;
            public string Part;
            public Mesh Mesh;
            public Matrix4x4 Matrix;
        }

        // The GLB material names of the Kenney bodies (lower case, as ModelKit.SurfaceOf reads them).
        public const string Wood = "wood";
        public const string Carpet = "carpet";
        public const string Metal = "metal";
        public const string Lamp = "lamp";

        private static Piece Place(string source, string part, Mesh mesh, Vector3 position, Quaternion rotation)
        {
            return new Piece { Source = source, Part = part, Mesh = mesh, Matrix = Matrix4x4.TRS(position, rotation, Vector3.one) };
        }

        /// <summary>The triangles of <paramref name="pieces"/>.</summary>
        public static long Triangles(IEnumerable<Piece> pieces)
        {
            long total = 0;
            foreach (Piece p in pieces)
            {
                total += ModelKit.Triangles(p.Mesh);
            }
            return total;
        }

        // ----- Shapes -----

        /// <summary>
        /// A rounded block standing on y = 0, centred in x and z, <paramref name="height"/> tall: its half extents go linearly
        /// from <paramref name="bottomHalf"/> (x, z) to <paramref name="topHalf"/>, its plan corners are rounded by
        /// <paramref name="cornerFraction"/> of the smaller half extent (below 1 with one corner segment, so the straight sides
        /// stay), and its bottom and top edges by quarter circles of the given radii and segments (0: a sharp edge).
        /// </summary>
        public static Mesh Block(Vector2 bottomHalf, Vector2 topHalf, float height, float cornerFraction, int cornerSegments,
            float bottomRound, int bottomSegments, float topRound, int topSegments, bool capBottom, bool capTop)
        {
            float limit = Mathf.Min(Mathf.Min(bottomHalf.x, bottomHalf.y), Mathf.Min(topHalf.x, topHalf.y));
            float br = bottomSegments > 0 ? Mathf.Clamp(bottomRound, 0f, Mathf.Min(limit, height * 0.5f)) : 0f;
            float tr = topSegments > 0 ? Mathf.Clamp(topRound, 0f, Mathf.Min(limit, height - br)) : 0f;
            // The side leans by the taper: its normal tilts up where the block narrows upward.
            float slope = (topHalf.x - bottomHalf.x) / height;
            float side = Mathf.Atan2(-slope, 1f);
            // A bottom edge's normals stop short of straight down: a glossy finish would mirror the floor along it as a pale
            // line (the player's lacquer), and nobody looks at it from below.
            const float bottomNormal = -55f * Mathf.Deg2Rad;
            var rings = new List<RoundedMesh.Ring>();
            void Add(float y, float inset, float normalAngle)
            {
                float t = Mathf.Clamp01(y / height);
                float hx = Mathf.Lerp(bottomHalf.x, topHalf.x, t);
                float hz = Mathf.Lerp(bottomHalf.y, topHalf.y, t);
                float corner = cornerFraction * Mathf.Min(hx, hz);
                rings.Add(RoundedMesh.At(hx - inset, hz - inset, y, Mathf.Max(corner - inset, corner * 0.5f), Mathf.Cos(normalAngle), Mathf.Sin(normalAngle)));
            }
            if (br > 0f)
            {
                for (int k = 0; k <= bottomSegments; k++)
                {
                    float phi = (-90f + 90f * k / bottomSegments) * Mathf.Deg2Rad;
                    Add(br + br * Mathf.Sin(phi), br * (1f - Mathf.Cos(phi)), Mathf.Lerp(bottomNormal, side, (float)k / bottomSegments));
                }
            }
            else
            {
                Add(0f, 0f, side);
            }
            if (tr > 0f)
            {
                for (int k = 0; k <= topSegments; k++)
                {
                    float phi = 90f * k / topSegments * Mathf.Deg2Rad;
                    Add(height - tr + tr * Mathf.Sin(phi), tr * (1f - Mathf.Cos(phi)), Mathf.Lerp(side, 0.5f * Mathf.PI, (float)k / topSegments));
                }
            }
            else
            {
                Add(height, 0f, side);
            }
            return RoundedMesh.Sweep(rings, cornerSegments, capBottom, capTop);
        }

        /// <summary>
        /// A <see cref="Block"/> laid from <paramref name="a"/> to <paramref name="b"/>: its first half extent across
        /// <paramref name="across"/> (made square to the bar), its bottom at <paramref name="a"/>, its top at <paramref name="b"/>.
        /// </summary>
        public static Piece Bar(string source, string part, Vector3 a, Vector3 b, Vector3 across, Vector2 halfA, Vector2 halfB, float cornerFraction,
            int cornerSegments, float roundA, int segmentsA, float roundB, int segmentsB, bool capA, bool capB)
        {
            Vector3 axis = b - a;
            float length = axis.magnitude;
            Vector3 up = axis / length;
            Vector3 x = Vector3.ProjectOnPlane(across, up).normalized;
            Vector3 z = Vector3.Cross(x, up);
            Mesh mesh = Block(halfA, halfB, length, cornerFraction, cornerSegments, roundA, segmentsA, roundB, segmentsB, capA, capB);
            return Place(source, part, mesh, a, Quaternion.LookRotation(z, up));
        }

        /// <summary>
        /// A surface of revolution about y: one ring per profile entry (radius, height, and the profile normal's outward and
        /// upward parts), <paramref name="cornerSegments"/> per quarter (4 of them around: 2 an octagon, 4 sixteen sides).
        /// </summary>
        public static Mesh Revolve(IList<Vector4> profile, int cornerSegments, bool capStart, bool capEnd)
        {
            return Revolve(profile, Vector2.one, cornerSegments, capStart, capEnd);
        }

        /// <summary>
        /// <see cref="Revolve(IList{Vector4}, int, bool, bool)"/> stretched to a footprint: each ring's half extents are its
        /// radius times <paramref name="stretch"/> (x, z), its corner radius the smaller of them, so a square footprint stays
        /// round and a longer one becomes a stadium filling its box (a model's box fit may be anything).
        /// </summary>
        public static Mesh Revolve(IList<Vector4> profile, Vector2 stretch, int cornerSegments, bool capStart, bool capEnd)
        {
            var rings = new List<RoundedMesh.Ring>(profile.Count);
            foreach (Vector4 p in profile)
            {
                float hx = p.x * stretch.x;
                float hz = p.x * stretch.y;
                rings.Add(RoundedMesh.At(hx, hz, p.y, Mathf.Min(hx, hz), p.z, p.w));
            }
            return RoundedMesh.Sweep(rings, cornerSegments, capStart, capEnd);
        }

        /// <summary>The stretch of a round part filling a box of <paramref name="s"/> (x, z) at radius min(x, z) / 2.</summary>
        private static Vector2 Stretch(Vector3 s)
        {
            float r = Mathf.Min(s.x, s.z);
            return new Vector2(s.x / r, s.z / r);
        }

        private static readonly Dictionary<string, Mesh> Cache = new Dictionary<string, Mesh>();

        /// <summary>
        /// A tube along a planar <paramref name="path"/> (a rocker's runner): one ring square to the path at each point, a
        /// rounded rectangle of <paramref name="half"/> extents (x across <paramref name="side"/>, y in the path's plane), its
        /// corners rounded by <paramref name="cornerFraction"/> of the smaller one; analytic normals, UVs in metres (U around,
        /// V along), a flat cap at each end when asked. Cached by its parameters.
        /// </summary>
        public static Mesh Tube(IList<Vector3> path, Vector3 side, Vector2 half, float cornerFraction, int cornerSegments, bool capStart, bool capEnd)
        {
            CultureInfo c = CultureInfo.InvariantCulture;
            var key = new StringBuilder("tube").Append(cornerSegments).Append(capStart ? 'S' : 's').Append(capEnd ? 'E' : 'e')
                .Append(side.ToString("F4")).Append(half.ToString("F4")).Append(cornerFraction.ToString("0.###", c));
            foreach (Vector3 p in path)
            {
                key.Append('|').Append(p.ToString("F4"));
            }
            string k = key.ToString();
            if (Cache.TryGetValue(k, out Mesh cached) && cached != null)
            {
                return cached;
            }
            int m = Mathf.Max(1, cornerSegments);
            int n = path.Count;
            int count = 4 * (m + 1) + 1;
            var points = new Vector3[n][];
            var normals = new Vector3[n][];
            var around = new float[n][];
            var along = new float[n];
            var tangents = new Vector3[n];
            var axes = new (Vector3 b, Vector3 c)[n];
            float radius = cornerFraction * Mathf.Min(half.x, half.y);
            for (int i = 0; i < n; i++)
            {
                Vector3 t = (path[Mathf.Min(i + 1, n - 1)] - path[Mathf.Max(i - 1, 0)]).normalized;
                Vector3 b = Vector3.ProjectOnPlane(side, t).normalized;
                Vector3 cAxis = Vector3.Cross(t, b);
                tangents[i] = t;
                axes[i] = (b, cAxis);
                points[i] = new Vector3[count];
                normals[i] = new Vector3[count];
                around[i] = new float[count];
                int index = 0;
                for (int corner = 0; corner < 4; corner++)
                {
                    float sx = corner == 0 || corner == 3 ? 1f : -1f;
                    float sz = corner < 2 ? 1f : -1f;
                    for (int s = 0; s <= m; s++)
                    {
                        float angle = (corner * 90f + 90f * s / m) * Mathf.Deg2Rad;
                        float ox = Mathf.Cos(angle);
                        float oz = Mathf.Sin(angle);
                        points[i][index] = path[i] + b * (sx * (half.x - radius) + radius * ox) + cAxis * (sz * (half.y - radius) + radius * oz);
                        normals[i][index] = (b * ox + cAxis * oz).normalized;
                        index++;
                    }
                }
                points[i][index] = points[i][0];
                normals[i][index] = normals[i][0];
                for (int j = 1; j < count; j++)
                {
                    around[i][j] = around[i][j - 1] + (points[i][j] - points[i][j - 1]).magnitude;
                }
                if (i > 0)
                {
                    along[i] = along[i - 1] + (path[i] - path[i - 1]).magnitude;
                }
            }
            var vertices = new List<Vector3>();
            var vertexNormals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            for (int i = 1; i < n; i++)
            {
                int start = vertices.Count;
                for (int row = 0; row < 2; row++)
                {
                    int r = i - 1 + row;
                    for (int j = 0; j < count; j++)
                    {
                        vertices.Add(points[r][j]);
                        vertexNormals.Add(normals[r][j]);
                        uvs.Add(new Vector2((around[i - 1][j] + around[i][j]) * 0.5f, along[r]));
                    }
                }
                for (int j = 0; j < count - 1; j++)
                {
                    Triangle(vertices, vertexNormals, triangles, start + j, start + count + j, start + j + 1);
                    Triangle(vertices, vertexNormals, triangles, start + j + 1, start + count + j, start + count + j + 1);
                }
            }
            for (int end = 0; end < 2; end++)
            {
                if ((end == 0 && !capStart) || (end == 1 && !capEnd))
                {
                    continue;
                }
                int i = end == 0 ? 0 : n - 1;
                Vector3 facing = end == 0 ? -tangents[i] : tangents[i];
                int start = vertices.Count;
                for (int j = 0; j < count - 1; j++)
                {
                    Vector3 local = points[i][j] - path[i];
                    vertices.Add(points[i][j]);
                    vertexNormals.Add(facing);
                    uvs.Add(new Vector2(Vector3.Dot(local, axes[i].b), Vector3.Dot(local, axes[i].c)));
                }
                for (int j = 1; j < count - 2; j++)
                {
                    Triangle(vertices, vertexNormals, triangles, start, start + j, start + j + 1);
                }
            }
            var mesh = new Mesh { name = "Rounded" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(vertexNormals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Cache[k] = mesh;
            return mesh;
        }

        /// <summary>One triangle wound so its face agrees with its vertex normals (Unity's clockwise front); none if it has no area.</summary>
        private static void Triangle(List<Vector3> vertices, List<Vector3> normals, List<int> triangles, int a, int b, int c)
        {
            Vector3 face = Vector3.Cross(vertices[b] - vertices[a], vertices[c] - vertices[a]);
            if (face.sqrMagnitude < 1e-14f)
            {
                return;
            }
            if (Vector3.Dot(face, normals[a] + normals[b] + normals[c]) < 0f)
            {
                (b, c) = (c, b);
            }
            triangles.Add(a);
            triangles.Add(b);
            triangles.Add(c);
        }

        // ----- Assembly -----

        /// <summary>
        /// The <paramref name="pieces"/> of each of <paramref name="groups"/> as one submesh (in that order; a piece joins the
        /// group its <see cref="Piece.Source"/>, or with <paramref name="byPart"/> its <see cref="Piece.Part"/>, names), each
        /// placed by its matrix then by <paramref name="frame"/>: positions, normals by the inverse transpose, the winding
        /// flipped under a mirroring frame, UV0 kept. Readable, kept across level rebuilds, cached by its pieces and frame.
        /// </summary>
        public static Mesh Assemble(IList<Piece> pieces, IList<string> groups, bool byPart, Matrix4x4 frame, string name)
        {
            CultureInfo c = CultureInfo.InvariantCulture;
            var key = new StringBuilder("soft|").Append(name).Append(byPart ? "|p" : "|s");
            foreach (string g in groups)
            {
                key.Append('|').Append(g);
            }
            void Append(Matrix4x4 m)
            {
                for (int i = 0; i < 12; i++)
                {
                    key.Append(',').Append(m[i % 3, i / 3].ToString("0.#####", c));
                }
            }
            Append(frame);
            foreach (Piece p in pieces)
            {
                key.Append('|').Append(p.Mesh.GetInstanceID()).Append(byPart ? p.Part : p.Source);
                Append(p.Matrix);
            }
            string k = key.ToString();
            if (Cache.TryGetValue(k, out Mesh cached) && cached != null)
            {
                return cached;
            }
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var submeshes = new List<int>[groups.Count];
            for (int g = 0; g < groups.Count; g++)
            {
                submeshes[g] = new List<int>();
            }
            var partUvs = new List<Vector2>();
            foreach (Piece p in pieces)
            {
                int g = groups.IndexOf(byPart ? p.Part : p.Source);
                if (g < 0)
                {
                    continue;
                }
                Matrix4x4 m = frame * p.Matrix;
                Matrix4x4 normalMatrix = m.inverse.transpose;
                bool mirrored = m.determinant < 0f;
                int start = vertices.Count;
                Vector3[] v = p.Mesh.vertices;
                Vector3[] n = p.Mesh.normals;
                partUvs.Clear();
                p.Mesh.GetUVs(0, partUvs);
                for (int i = 0; i < v.Length; i++)
                {
                    vertices.Add(m.MultiplyPoint3x4(v[i]));
                    normals.Add(i < n.Length ? normalMatrix.MultiplyVector(n[i]).normalized : Vector3.up);
                    uvs.Add(i < partUvs.Count ? partUvs[i] : Vector2.zero);
                }
                for (int sub = 0; sub < p.Mesh.subMeshCount; sub++)
                {
                    int[] t = p.Mesh.GetTriangles(sub);
                    for (int i = 0; i + 2 < t.Length; i += 3)
                    {
                        submeshes[g].Add(start + t[i]);
                        submeshes[g].Add(start + (mirrored ? t[i + 2] : t[i + 1]));
                        submeshes[g].Add(start + (mirrored ? t[i + 1] : t[i + 2]));
                    }
                }
            }
            var mesh = new Mesh { name = name };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.subMeshCount = groups.Count;
            for (int g = 0; g < groups.Count; g++)
            {
                mesh.SetTriangles(submeshes[g], g);
            }
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Cache[k] = mesh;
            return mesh;
        }

        /// <summary>
        /// A procedural body's renderer: the pieces whose <see cref="Piece.Part"/> is <paramref name="part"/>, as one mesh in
        /// the frame of a GameObject named <paramref name="name"/> standing at <paramref name="pivot"/>, showing
        /// <paramref name="surface"/>.
        /// </summary>
        public static GameObject Build(Transform parent, string name, IList<Piece> pieces, string part, Vector3 pivot, Material material, int layer,
            Surface surface)
        {
            Mesh mesh = Assemble(pieces, new[] { part }, true, Matrix4x4.Translate(-pivot), "Soft " + name);
            return PrimitiveKit.Part(parent, name, mesh, pivot, Quaternion.identity, Vector3.one, material, layer, surface);
        }

        /// <summary><see cref="Build(Transform, string, IList{Piece}, string, Vector3, Material, int, Surface)"/> named after its part, standing at <see cref="Pivot"/>.</summary>
        public static GameObject Build(Transform parent, IList<Piece> pieces, string part, Material material, int layer, Surface surface)
        {
            return Build(parent, part, pieces, part, Pivot(pieces, part), material, layer, surface);
        }

        /// <summary>The foot of a part (the centre of its pieces' bounds in x and z, their lowest y): where its GameObject stands.</summary>
        public static Vector3 Pivot(IList<Piece> pieces, string part)
        {
            var bounds = new Bounds();
            bool any = false;
            foreach (Piece p in pieces)
            {
                if (p.Part != part)
                {
                    continue;
                }
                Bounds b = p.Mesh.bounds;
                for (int i = 0; i < 8; i++)
                {
                    Vector3 corner = b.center + Vector3.Scale(b.extents, new Vector3((i & 1) == 0 ? -1f : 1f, (i & 2) == 0 ? -1f : 1f, (i & 4) == 0 ? -1f : 1f));
                    Vector3 at = p.Matrix.MultiplyPoint3x4(corner);
                    if (!any)
                    {
                        bounds = new Bounds(at, Vector3.zero);
                        any = true;
                    }
                    else
                    {
                        bounds.Encapsulate(at);
                    }
                }
            }
            return new Vector3(bounds.center.x, bounds.min.y, bounds.center.z);
        }

        // ----- The Kenney models -----

        /// <summary>The rounded design standing in for the catalog model <paramref name="id"/> in a box of <paramref name="box"/>, or null (not a body model).</summary>
        public static List<Piece> ModelDesign(string id, Vector3 box)
        {
            switch (id)
            {
                case ModelCatalog.KenneyChair:
                    return Chair(box);
                case ModelCatalog.KenneyStool:
                    return Stool(box);
                case ModelCatalog.KenneyArmchair:
                    return Armchair(box, true);
                case ModelCatalog.KenneyFloorLamp:
                    return FloorLamp(box);
                default:
                    return null;
            }
        }

        /// <summary>
        /// Swaps the meshes of a box fitted model <paramref name="instance"/> of <paramref name="id"/> (under
        /// <paramref name="parent"/>, in a box of <paramref name="box"/>) for its rounded design: each renderer keeps its
        /// material slots, each slot gets the parts of its source material (every slot at least one), the rest shared out
        /// by triangles. Called by ModelKit before the paint, so the detail is measured on the new meshes and the main
        /// material (the one with the most triangles, the player's red) stays the one it was. Nothing for a model without a
        /// design; an error and the hard meshes kept when the design does not fit the instance.
        /// </summary>
        internal static void ApplyToModel(string id, GameObject instance, Transform parent, Vector3 box)
        {
            if (!RoundModels || instance == null)
            {
                return;
            }
            List<Piece> design = ModelDesign(id, box);
            if (design == null)
            {
                return;
            }
            var filters = new List<MeshFilter>();
            var slots = new List<string[]>();
            foreach (MeshRenderer r in instance.GetComponentsInChildren<MeshRenderer>(true))
            {
                MeshFilter f = r.GetComponent<MeshFilter>();
                if (f == null || f.sharedMesh == null)
                {
                    continue;
                }
                Material[] materials = r.sharedMaterials;
                var names = new string[materials.Length];
                for (int i = 0; i < materials.Length; i++)
                {
                    names[i] = materials[i] != null ? materials[i].name.Trim().ToLowerInvariant() : string.Empty;
                }
                filters.Add(f);
                slots.Add(names);
            }
            string problem = Distribute(design, slots, out List<Piece>[] assigned) ?? SameMain(filters, slots, design);
            long triangles = Triangles(design);
            if (problem == null && triangles > Tuning.BudgetFurnitureTriangles)
            {
                problem = $"{triangles} triangles, over the {Tuning.BudgetFurnitureTriangles} budget";
            }
            if (problem != null)
            {
                Debug.LogError($"[SoftBodies] {id} keeps its hard meshes: {problem}");
                return;
            }
            Matrix4x4 toBody = parent != null ? parent.worldToLocalMatrix : Matrix4x4.identity;
            for (int i = 0; i < filters.Count; i++)
            {
                Matrix4x4 nodeToBody = toBody * filters[i].transform.localToWorldMatrix;
                filters[i].sharedMesh = Assemble(assigned[i], slots[i], false, nodeToBody.inverse, "Soft " + id);
            }
        }

        /// <summary>
        /// Shares the pieces out between the renderers (their slots' source names): for each source, one piece to each renderer
        /// that draws it, the rest to whichever of them has the fewest triangles. The problem, or null.
        /// </summary>
        private static string Distribute(List<Piece> design, List<string[]> slots, out List<Piece>[] assigned)
        {
            assigned = new List<Piece>[slots.Count];
            var load = new long[slots.Count];
            for (int i = 0; i < slots.Count; i++)
            {
                assigned[i] = new List<Piece>();
            }
            if (slots.Count == 0)
            {
                return "no renderer";
            }
            var sources = new List<string>();
            foreach (Piece p in design)
            {
                if (!sources.Contains(p.Source))
                {
                    sources.Add(p.Source);
                }
            }
            foreach (string source in sources)
            {
                var users = new List<int>();
                for (int i = 0; i < slots.Count; i++)
                {
                    if (System.Array.IndexOf(slots[i], source) >= 0)
                    {
                        users.Add(i);
                    }
                }
                List<Piece> mine = design.FindAll(p => p.Source == source);
                if (users.Count == 0)
                {
                    return $"no slot draws '{source}'";
                }
                if (mine.Count < users.Count)
                {
                    return $"{mine.Count} '{source}' parts for {users.Count} renderers";
                }
                for (int k = 0; k < mine.Count; k++)
                {
                    int best = users[0];
                    if (k < users.Count)
                    {
                        best = users[k];
                    }
                    else
                    {
                        foreach (int u in users)
                        {
                            if (load[u] < load[best])
                            {
                                best = u;
                            }
                        }
                    }
                    assigned[best].Add(mine[k]);
                    load[best] += ModelKit.Triangles(mine[k].Mesh);
                }
            }
            for (int i = 0; i < slots.Count; i++)
            {
                foreach (string s in slots[i])
                {
                    if (!sources.Contains(s))
                    {
                        return $"the design has no '{s}' part";
                    }
                }
            }
            return null;
        }

        /// <summary>The problem when the design's main source (most triangles) is not the hard model's, which ModelKit paints in the main colour; else null.</summary>
        private static string SameMain(List<MeshFilter> filters, List<string[]> slots, List<Piece> design)
        {
            var before = new Dictionary<string, long>();
            var after = new Dictionary<string, long>();
            for (int i = 0; i < filters.Count; i++)
            {
                Mesh mesh = filters[i].sharedMesh;
                for (int s = 0; s < slots[i].Length && s < mesh.subMeshCount; s++)
                {
                    before[slots[i][s]] = (before.TryGetValue(slots[i][s], out long t) ? t : 0) + mesh.GetIndexCount(s) / 3;
                }
            }
            foreach (Piece p in design)
            {
                after[p.Source] = (after.TryGetValue(p.Source, out long t) ? t : 0) + ModelKit.Triangles(p.Mesh);
            }
            string Main(Dictionary<string, long> counts)
            {
                string best = null;
                foreach (KeyValuePair<string, long> pair in counts)
                {
                    if (best == null || pair.Value > counts[best])
                    {
                        best = pair.Key;
                    }
                }
                return best;
            }
            string was = Main(before);
            string now = Main(after);
            return was == now ? null : $"its main material would turn from '{was}' to '{now}'";
        }

        // ----- The designs (body frame, metres; front on +z) -----

        /// <summary>
        /// How round the chair is. PRD 7.2 holds it back: the player's chair must stay THE saturated red region of the
        /// frame (ProbeTestsM42Look Step22d), and a rounded edge shows highlights and shade instead of flat red, so the
        /// rounding keeps the chair's flat faces as large as the soft look allows. A field so the look tool and the tests
        /// can compare variants; the game never changes it.
        /// </summary>
        public struct ChairLook
        {
            /// <summary>The seat's plan corner radius, as a fraction of a leg's half width.</summary>
            public float SeatCorner;
            /// <summary>The roll of the seat's top edge, metres (2 segments).</summary>
            public float SeatRoll;
            /// <summary>A front leg's half width at the floor, as a fraction of its top's.</summary>
            public float LegFoot;
            /// <summary>A back post's half width at the floor and at the top, as fractions of a leg's.</summary>
            public float PostFoot;
            public float PostTop;
            /// <summary>How far in from the box's corners the legs stand, in leg half widths (1: flush).</summary>
            public float Inset;
            /// <summary>The top rail's depth, as a fraction of a post's.</summary>
            public float RailDepth;
            /// <summary>A leg's width, as a fraction of the box's (the GLB's: 0.2).</summary>
            public float LegWidth;
            /// <summary>The round of a post's top, metres, and how far under the box's top the top rail stops.</summary>
            public float PostRound;
            public float RailDrop;
        }

        /// <summary>
        /// The chair's rounding (see <see cref="ChairLook"/>), measured on Step22d's own view of level 1 (640 x 360, the red
        /// pixels ModelMath.IsRed counts): legs and posts a little sturdier than the GLB's (23 % of the box, 20 % on the
        /// GLB) standing 3 mm in from its edges (so their faces never share a plane with the seat's), straight posts with
        /// small rounded tops and the top rail nearly flush with them, the seat's plan corners following the legs' and a
        /// 2 cm roll on its top edge: 95 % of the hard chair's red pixels (1555 of 1637 on 2026-11-20; a rim of each rounded
        /// edge turns to shade or reflection), where tapered, inset legs, domed posts and a 3 cm roll kept only 86 %.
        /// </summary>
        public static ChairLook ChairStyle = new ChairLook
        {
            SeatCorner = 0.5f, SeatRoll = 0.02f, LegFoot = 1f, PostFoot = 1f, PostTop = 1f, Inset = 1.06f, RailDepth = 0.95f, LegWidth = 0.23f,
            PostRound = 0.015f, RailDrop = 0.002f,
        };

        /// <summary>
        /// The chair (Kenney Furniture Kit "chair", 0.2 x 0.47 x 0.2 native units, measured on its GLB): a seat from 0.19 to
        /// 0.24, 4 cm legs whose back pair runs up as the backrest's posts, an H of 2 cm stretchers at 0.05 to 0.07, a top
        /// rail (0.43 to 0.47) and a thin middle rail (0.295 to 0.335) between the posts. Rounded: a seat with rounded corners
        /// and a rolled top edge, legs and posts of rounded section with a soft foot, posts with a rounded top, rails and
        /// stretchers of round section (<see cref="ChairStyle"/>). Parts as FurnitureKit.Chair names them: the seat, the
        /// four legs (the stretchers join them) and the backrest (the rails). All wood. 342 triangles.
        /// </summary>
        public static List<Piece> Chair(Vector3 s)
        {
            ChairLook look = ChairStyle;
            float Y(float native) => native / 0.47f * s.y;
            float hx = 0.5f * look.LegWidth * s.x;
            float hz = 0.5f * look.LegWidth * s.z;
            // A little in from the corners, so the legs stand inside the seat's rounded corners (the seat overhangs them).
            float lx = s.x * 0.5f - hx * look.Inset;
            float lz = s.z * 0.5f - hz * look.Inset;
            float seatBottom = Y(0.19f);
            float seatTop = Y(0.24f);
            float seat = seatTop - seatBottom;
            var pieces = new List<Piece>
            {
                // Its top edge rolled, its bottom edge left sharp (never seen from above; a rounded one mirrors the floor).
                Place(Wood, "Seat", RoundedMesh.Slab(new Vector3(s.x, seat, s.z), Mathf.Min(hx, hz) * look.SeatCorner, 0f, 0, Mathf.Min(look.SeatRoll, seat * 0.35f), 2, 2,
                    false, true), new Vector3(0f, seatBottom, 0f), Quaternion.identity),
            };
            // The front legs reach into the seat (their tops hidden in it), the back ones up to the top as the posts.
            var top = new Vector2(hx, hz);
            Mesh frontLeg = Block(top * look.LegFoot, top, seatBottom + seat * 0.5f, 0.45f, 1, 0.012f, 1, 0f, 0, false, false);
            Mesh post = Block(top * look.PostFoot, top * look.PostTop, s.y, 0.45f, 1, 0.012f, 1, Mathf.Min(look.PostRound, hx * 0.7f), 1, false, true);
            pieces.Add(Place(Wood, "LegFL", frontLeg, new Vector3(-lx, 0f, lz), Quaternion.identity));
            pieces.Add(Place(Wood, "LegFR", frontLeg, new Vector3(lx, 0f, lz), Quaternion.identity));
            pieces.Add(Place(Wood, "LegBL", post, new Vector3(-lx, 0f, -lz), Quaternion.identity));
            pieces.Add(Place(Wood, "LegBR", post, new Vector3(lx, 0f, -lz), Quaternion.identity));
            // The H of stretchers, from leg centre to leg centre (their ends hidden in the legs).
            float y = Y(0.06f);
            var thin = new Vector2(Y(0.01f), 0.05f * s.x);
            pieces.Add(Bar(Wood, "LegFL", new Vector3(-lx, y, lz), new Vector3(-lx, y, -lz), Vector3.up, thin, thin, 0.45f, 1, 0f, 0, 0f, 0, false, false));
            pieces.Add(Bar(Wood, "LegBR", new Vector3(lx, y, -lz), new Vector3(lx, y, lz), Vector3.up, thin, thin, 0.45f, 1, 0f, 0, 0f, 0, false, false));
            pieces.Add(Bar(Wood, "LegFR", new Vector3(-lx, y, 0f), new Vector3(lx, y, 0f), Vector3.up, new Vector2(thin.x, 0.05f * s.z),
                new Vector2(thin.x, 0.05f * s.z), 0.45f, 1, 0f, 0, 0f, 0, false, false));
            // The rails between the posts: the top one a little under the posts' rounded tops and thinner than them, so
            // its ends stay inside the posts.
            var rail = new Vector2(Y(0.02f) - look.RailDrop * 0.5f, hz * look.RailDepth);
            float railY = s.y - look.RailDrop - rail.x;
            pieces.Add(Bar(Wood, "Backrest", new Vector3(-lx, railY, -lz), new Vector3(lx, railY, -lz), Vector3.up, rail, rail, 0.6f, 2, 0f, 0, 0f, 0, false, false));
            var middle = new Vector2(Y(0.02f), 0.05f * s.z);
            pieces.Add(Bar(Wood, "Backrest", new Vector3(-lx, Y(0.315f), -lz), new Vector3(lx, Y(0.315f), -lz), Vector3.up, middle, middle, 0.45f, 1,
                0f, 0, 0f, 0, false, false));
            return pieces;
        }

        /// <summary>
        /// The bar stool (Kenney "stoolBar", 0.265 x 0.435 x 0.23 native units): a hexagonal cushion from 0.355 to 0.435 on
        /// four 2 cm legs (centres at 43 % and 47 % of the half box) joined by a square ring at 0.125 to 0.145. Rounded: a
        /// round, plump cushion filling the box, legs of round section splaying a little to the floor, a round foot ring.
        /// Parts as FurnitureKit.Stool names them: the seat (carpet, in two halves) and the four legs (wood, the ring's
        /// sides join them). 268 triangles, the wood the most (it is the main material, as on the model).
        /// </summary>
        public static List<Piece> Stool(Vector3 s)
        {
            float Y(float native) => native / 0.435f * s.y;
            float r = Mathf.Min(s.x, s.z) * 0.5f;
            float y0 = Y(0.355f);
            float h = s.y - y0;
            var lower = new List<Vector4>
            {
                new Vector4(r * 0.86f, y0, 0.6f, -0.8f),
                new Vector4(r * 0.97f, y0 + 0.18f * h, 0.8f, -0.6f),
                new Vector4(r, y0 + 0.45f * h, 1f, 0f),
            };
            var upper = new List<Vector4>
            {
                new Vector4(r, y0 + 0.45f * h, 1f, 0f),
                new Vector4(r * 0.96f, y0 + 0.78f * h, 0.7f, 0.71f),
                new Vector4(r * 0.8f, s.y, 0.25f, 0.97f),
            };
            var pieces = new List<Piece>
            {
                Place(Carpet, "Seat", Revolve(lower, Stretch(s), 3, true, false), Vector3.zero, Quaternion.identity),
                Place(Carpet, "Seat", Revolve(upper, Stretch(s), 3, false, true), Vector3.zero, Quaternion.identity),
            };
            // The legs splay from 43 % (x) and 47 % (z) of the half box under the seat to 60 % and 64 % on the floor.
            var half = new Vector2(0.014f, 0.014f);
            float top = y0 + 0.25f * h;
            string[] names = { "LegFL", "LegFR", "LegBR", "LegBL" };
            Vector2[] signs = { new Vector2(-1f, 1f), new Vector2(1f, 1f), new Vector2(1f, -1f), new Vector2(-1f, -1f) };
            var tops = new Vector3[4];
            var feet = new Vector3[4];
            for (int i = 0; i < 4; i++)
            {
                tops[i] = new Vector3(signs[i].x * 0.43f * s.x * 0.5f, top, signs[i].y * 0.47f * s.z * 0.5f);
                feet[i] = new Vector3(signs[i].x * 0.6f * s.x * 0.5f, 0f, signs[i].y * 0.64f * s.z * 0.5f);
                // Lifted by its tilt so the slanted foot never dips under the floor.
                Vector3 axis = (tops[i] - feet[i]).normalized;
                feet[i].y = 1.42f * half.x * Mathf.Sqrt(1f - axis.y * axis.y) + 0.001f;
                pieces.Add(Bar(Wood, names[i], feet[i], tops[i], Vector3.right, half, half, 0.45f, 1, 0f, 0, 0f, 0, true, false));
            }
            // The foot ring, from leg axis to leg axis at the height of the GLB's ring.
            float ringY = Y(0.135f);
            var ring = new Vector2(0.011f, 0.011f);
            for (int i = 0; i < 4; i++)
            {
                Vector3 a = Vector3.Lerp(feet[i], tops[i], (ringY - feet[i].y) / (tops[i].y - feet[i].y));
                int j = (i + 1) % 4;
                Vector3 b = Vector3.Lerp(feet[j], tops[j], (ringY - feet[j].y) / (tops[j].y - feet[j].y));
                pieces.Add(Bar(Wood, names[i], a, b, Vector3.up, ring, ring, 0.45f, 1, 0f, 0, 0f, 0, false, false));
            }
            return pieces;
        }

        /// <summary>
        /// The armchair (Kenney "loungeChair", 0.49 x 0.46 x 0.41 native units, its back on the -z side once turned): 5 cm
        /// wooden feet at the corners, an upholstered base up to the seat (0.23), arms 19 % of the width up to 0.37 running
        /// into the back, the back 22 % of the depth up to 0.37 and a narrower cushion on it (63 % of the width) up to the
        /// top. Rounded: soft upholstered blocks, rolled arms running the whole depth with the back between them, feet tucked
        /// under the base's rounded corners. <paramref name="model"/> false is FurnitureKit's procedural armchair instead: no
        /// feet (the base on the floor, as its collider) and a seat cushion. Parts: Base, Backrest, ArmL, ArmR (and Cushion).
        /// 378 triangles with the feet, 372 with the cushion.
        /// </summary>
        public static List<Piece> Armchair(Vector3 s, bool model)
        {
            float X(float native) => native / 0.49f * s.x;
            float Y(float native) => native / 0.46f * s.y;
            float Z(float native) => s.z * 0.5f - native / 0.41f * s.z;
            float seat = Y(0.23f);
            float arm = Y(0.37f);
            float sink = 0.03f;
            // The GLB's arms reach the front of its box at their top (its base starts 2 cm behind): the rounded base and arms
            // fill the box's front, as the model's bounds do.
            float front = s.z * 0.5f;
            float backFront = Z(0.32f);
            float back = -s.z * 0.5f;
            // The back and its cushion stand 5 mm in from the back face, which the arms' back faces would otherwise share.
            const float inset = 0.005f;
            var pieces = new List<Piece>();
            float baseBottom = model ? Y(0.05f) : 0f;
            var baseHalf = new Vector2(s.x * 0.5f, s.z * 0.5f);
            pieces.Add(Place(Carpet, "Base", Block(baseHalf, baseHalf, seat - baseBottom, 0.09f / Mathf.Min(baseHalf.x, baseHalf.y), 2, model ? 0.04f : 0.015f, 1,
                0.035f, 1, false, true), new Vector3(0f, baseBottom, 0f), Quaternion.identity));
            if (model)
            {
                // The feet, under the base's rounded corners (their tops inside it).
                var foot = new Vector2(X(0.02f), 0.02f / 0.41f * s.z);
                Mesh feet = Block(foot * 0.8f, foot, baseBottom + 0.03f, 0.5f, 1, 0f, 0, 0f, 0, false, false);
                float fx = s.x * 0.5f - 0.085f;
                float fz = s.z * 0.5f - 0.085f;
                foreach (Vector2 at in new[] { new Vector2(-fx, fz), new Vector2(fx, fz), new Vector2(-fx, -fz), new Vector2(fx, -fz) })
                {
                    pieces.Add(Place(Wood, "Base", feet, new Vector3(at.x, 0f, at.y), Quaternion.identity));
                }
            }
            // The arms, the whole depth (their rounded corners make the chair's back corners), sunk into the base so its
            // rounded top leaves no gap.
            float armWidth = X(0.095f);
            float armBack = back;
            float armFront = front;
            Mesh armMesh = RoundedMesh.Slab(new Vector3(armWidth, arm - seat + sink, armFront - armBack), 0.07f, 0f, 0, 0.06f, 1, 2, false, true);
            float ax = s.x * 0.5f - armWidth * 0.5f;
            pieces.Add(Place(Carpet, "ArmL", armMesh, new Vector3(-ax, seat - sink, (armFront + armBack) * 0.5f), Quaternion.identity));
            pieces.Add(Place(Carpet, "ArmR", armMesh, new Vector3(ax, seat - sink, (armFront + armBack) * 0.5f), Quaternion.identity));
            // The back between the arms (its ends inside them) up to their height, and its cushion up to the top.
            float depth = backFront - back - inset;
            float backZ = (backFront + back + inset) * 0.5f;
            pieces.Add(Place(Carpet, "Backrest", RoundedMesh.Slab(new Vector3(s.x - armWidth, arm - seat + sink, depth), 0.07f, 0f, 0, 0.05f, 1, 2, false, true),
                new Vector3(0f, seat - sink, backZ), Quaternion.identity));
            pieces.Add(Place(Carpet, "Backrest", RoundedMesh.Slab(new Vector3(X(0.31f), s.y - arm + sink, depth), 0.08f, 0f, 0, 0.07f, 1, 2, false, true),
                new Vector3(0f, arm - sink, backZ), Quaternion.identity));
            if (!model)
            {
                float width = s.x - 2f * armWidth - 0.02f;
                float cushion = Mathf.Min(0.1f, arm - seat - 0.02f);
                pieces.Add(Place(Carpet, "Cushion", RoundedMesh.Slab(new Vector3(width, cushion + sink, armFront - backFront - 0.02f), 0.06f, 0f, 0, 0.04f, 1, 2, false, true),
                    new Vector3(0f, seat - sink, (armFront + backFront) * 0.5f), Quaternion.identity));
            }
            return pieces;
        }

        /// <summary>
        /// The floor lamp (Kenney "lampRoundFloor", 0.15 x 0.86 x 0.18 native units): a 2 cm foot, a thin pole and a tapered
        /// shade from 0.68 to the top, a thick walled tube. Rounded: a round domed foot, a round pole, a round shade with
        /// rolled lips, its inside showing. Parts: Foot and Pole (metal), Shade (lamp, outside and inside). 290 triangles,
        /// the shade the most (the main material, as on the model).
        /// </summary>
        public static List<Piece> FloorLamp(Vector3 s)
        {
            float Y(float native) => native / 0.86f * s.y;
            float r = Mathf.Min(s.x, s.z) * 0.5f;
            float footTop = Y(0.02f);
            var foot = new List<Vector4>
            {
                new Vector4(r * 0.68f, 0f, 0.7f, -0.7f),
                new Vector4(r * 0.71f, footTop * 0.25f, 1f, 0f),
                new Vector4(r * 0.64f, footTop * 0.78f, 0.55f, 0.83f),
                new Vector4(r * 0.4f, footTop * 1.05f, 0.12f, 0.99f),
            };
            float shadeBottom = Y(0.6815f);
            float poleTop = shadeBottom + (s.y - shadeBottom) * 0.5f;
            var pole = new List<Vector4> { new Vector4(0.014f, footTop * 0.8f, 1f, 0f), new Vector4(0.014f, poleTop, 1f, 0f) };
            float bottomR = r;
            float topR = r * 0.73f;
            float slope = (bottomR - topR) / (s.y - shadeBottom);
            var side = new Vector2(1f, slope).normalized;
            float inner = r * 0.6f;
            var outside = new List<Vector4>
            {
                new Vector4(bottomR - 0.025f, shadeBottom, 0f, -1f),
                new Vector4(bottomR - 0.007f, shadeBottom + 0.004f, 0.55f, -0.83f),
                new Vector4(bottomR, shadeBottom + 0.018f, side.x, side.y),
                new Vector4(topR + 0.003f, s.y - 0.016f, side.x, side.y),
                new Vector4(topR - 0.006f, s.y, 0.35f, 0.94f),
                new Vector4(inner, s.y, 0f, 1f),
            };
            float innerBottom = bottomR - 0.025f;
            var inwards = new Vector2(-1f, -(innerBottom - inner) / (s.y - shadeBottom)).normalized;
            var inside = new List<Vector4>
            {
                new Vector4(inner, s.y, inwards.x, inwards.y),
                new Vector4(innerBottom, shadeBottom, inwards.x, inwards.y),
            };
            return new List<Piece>
            {
                Place(Metal, "Foot", Revolve(foot, Stretch(s), 3, false, true), Vector3.zero, Quaternion.identity),
                Place(Metal, "Pole", Revolve(pole, 2, false, false), Vector3.zero, Quaternion.identity),
                Place(Lamp, "Shade", Revolve(outside, Stretch(s), 4, false, false), Vector3.zero, Quaternion.identity),
                Place(Lamp, "Shade", Revolve(inside, Stretch(s), 4, false, false), Vector3.zero, Quaternion.identity),
            };
        }
    }
}
