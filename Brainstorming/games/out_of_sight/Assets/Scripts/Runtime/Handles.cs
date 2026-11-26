using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// Door and cupboard handles (product owner request, 2026-11-19): visual only, never a collider, so no footprint, sight
    /// ray or NavMesh changes. PRD 7.4 budgets: a handle never brings a material of its own nor a renderer of its own.
    /// <list type="bullet">
    /// <item>Material: on wooden furniture and on the door leaves, the household's dark metal (<see cref="Material"/>,
    /// FurnitureKit.DarkMaterial: the near-black of every inhabitant and of Kenney's "metalDark", drawn by every level); in
    /// the kitchen and the bathroom (sink unit, washbasin), the brushed Metal those room objects already draw for their
    /// taps.</item>
    /// <item>Draw calls: a static piece draws its handles in its one combined "Handles" renderer while its wood parts merge
    /// into one (FurnitureKit's part batch), which saves more than it adds; a door leaf draws them as a second sub-mesh of
    /// its own leaf mesh (<see cref="LeafMesh"/>, one more slot per leaf); a wardrobe draws its closed self combined and its
    /// animated parts only while its doors swing (WardrobeDoors).</item>
    /// </list>
    /// </summary>
    public static class Handles
    {
        /// <summary>The handle height above the floor on a door tall enough for it (a real door's or wardrobe's).</summary>
        public const float Height = 1.05f;
        /// <summary>A bar pull: the bar's width and depth, its gap off the door face, the posts holding it.</summary>
        public const float BarWidth = 0.026f;
        public const float BarDepth = 0.02f;
        public const float BarStandoff = 0.028f;
        public const float PostSize = 0.016f;
        /// <summary>A door leaf's lever: its backplate (rose), the stem out of it, the lever bar toward the hinge.</summary>
        public const float RoseThickness = 0.012f;
        public const float StemLength = 0.04f;
        public const float LeverLength = 0.14f;
        public const float LeverSection = 0.026f;
        /// <summary>From the leaf's free edge to the lever's stem.</summary>
        public const float LeverInset = 0.075f;

        /// <summary>The household's dark metal (no material of its own).</summary>
        public static Material Material => FurnitureKit.DarkMaterial;

        /// <summary>
        /// The height of a handle on a door from <paramref name="bottom"/> to <paramref name="top"/>: <see cref="Height"/>,
        /// kept within the door (<paramref name="margin"/> from each end), so a low cupboard has it near its top.
        /// </summary>
        public static float HeightOn(float bottom, float top, float margin)
        {
            float lo = bottom + margin;
            float hi = top - margin;
            return hi < lo ? (bottom + top) * 0.5f : Mathf.Clamp(Height, lo, hi);
        }

        /// <summary>
        /// A vertical bar pull of <paramref name="length"/> on a door face: the bar <see cref="BarStandoff"/> off the face and
        /// its two posts, as boxes (name, centre, size) given to <paramref name="add"/>. <paramref name="onFace"/> is the
        /// point of the face behind the bar's middle, <paramref name="outward"/> the face's normal along z (+1 or -1). 3 boxes.
        /// </summary>
        public static void Bar(Action<string, Vector3, Vector3> add, string name, Vector3 onFace, float outward, float length)
        {
            float barZ = onFace.z + outward * (BarStandoff + BarDepth * 0.5f);
            add(name, new Vector3(onFace.x, onFace.y, barZ), new Vector3(BarWidth, length, BarDepth));
            float postZ = onFace.z + outward * (BarStandoff * 0.5f);
            float postY = length * 0.5f - PostSize;
            add(name + "PostA", new Vector3(onFace.x, onFace.y - postY, postZ), new Vector3(PostSize, PostSize, BarStandoff));
            add(name + "PostB", new Vector3(onFace.x, onFace.y + postY, postZ), new Vector3(PostSize, PostSize, BarStandoff));
        }

        /// <summary>
        /// A door leaf's lever on one face: the rose (a vertical backplate), the stem out of it, and the lever bar pointing
        /// toward the hinge (<paramref name="towardHinge"/>, -1 or +1 along x). 3 boxes.
        /// </summary>
        public static void Lever(Action<string, Vector3, Vector3> add, string name, Vector3 onFace, float outward, float towardHinge)
        {
            add(name + "Rose", onFace + new Vector3(0f, 0f, outward * RoseThickness * 0.5f), new Vector3(0.05f, 0.1f, RoseThickness));
            float leverY = onFace.y + 0.02f;
            add(name + "Stem", new Vector3(onFace.x, leverY, onFace.z + outward * (RoseThickness + StemLength * 0.5f)),
                new Vector3(LeverSection, LeverSection, StemLength));
            float leverZ = onFace.z + outward * (RoseThickness + StemLength + LeverSection * 0.5f);
            add(name + "Lever", new Vector3(onFace.x + towardHinge * (LeverLength * 0.5f - LeverSection * 0.5f), leverY, leverZ),
                new Vector3(LeverLength, LeverSection, LeverSection));
        }

        /// <summary>
        /// The pulls of a pair of cupboard doors either side of x = 0 (a room object's): one vertical <see cref="PullMesh"/> on
        /// each door, near the edge facing the middle (<paramref name="gap"/> from x = 0) at <see cref="HeightOn"/> the doors'
        /// span, standing on the face at <paramref name="faceZ"/>, given to <paramref name="add"/> (name, mesh, position).
        /// </summary>
        public static void Pulls(Action<string, Mesh, Vector3> add, float doorWidth, float gap, float bottom, float top, float faceZ, float outward)
        {
            float length = Mathf.Min(0.14f, (top - bottom) * 0.35f);
            float y = HeightOn(bottom, top, length * 0.5f + 0.03f);
            Mesh mesh = PullMesh(new Vector3(BarWidth, length, PullDepth), outward);
            for (int i = 0; i < 2; i++)
            {
                float side = i == 0 ? -1f : 1f;
                add("Pull" + i, mesh, new Vector3(side * (gap + Mathf.Min(0.05f, doorWidth * 0.25f)), y, faceZ + outward * PullDepth * 0.5f));
            }
        }

        /// <summary>The depth a <see cref="PullMesh"/> stands off its door face.</summary>
        public const float PullDepth = 0.024f;

        private static readonly Dictionary<string, Mesh> PullCache = new Dictionary<string, Mesh>();

        /// <summary>
        /// A small cupboard's pull, for a room object near its triangle budget (PRD 7.4: 400 per piece): a box of
        /// <paramref name="size"/> centred on the origin without the face against the door (<paramref name="outward"/> is
        /// the door's normal along z) nor the bottom one (the camera always looks down on it): 8 triangles, UVs in metres
        /// (V along each face's longer side, as PrimitiveKit's boxes), so a detail tiles on it at its surface's tile.
        /// Cached by size and side.
        /// </summary>
        public static Mesh PullMesh(Vector3 size, float outward)
        {
            string key = string.Format(CultureInfo.InvariantCulture, "{0:0.####}x{1:0.####}x{2:0.####}{3}", size.x, size.y, size.z, outward < 0f ? "-" : "+");
            if (PullCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Vector3 h = size * 0.5f;
            float o = outward < 0f ? -1f : 1f;
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            // One quad: its corners a, b, c, d in order around it (either way: the winding is fixed below so it faces its normal).
            void Quad(Vector3 normal, Vector3 a, Vector3 b, Vector3 c, Vector3 d, float width, float height)
            {
                int start = vertices.Count;
                vertices.AddRange(new[] { a, b, c, d });
                normals.AddRange(new[] { normal, normal, normal, normal });
                bool swap = width > height;
                Vector2 Uv(float u, float v) => swap ? new Vector2(v * height, u * width) : new Vector2(u * width, v * height);
                uvs.AddRange(new[] { Uv(0f, 0f), Uv(0f, 1f), Uv(1f, 1f), Uv(1f, 0f) });
                // Unity's front faces: Cross(b - a, c - a) along the normal (as its own quad, PrimitiveKit.QuadMesh); flip the
                // pair when a-b-c turns the other way.
                bool front = Vector3.Dot(Vector3.Cross(b - a, c - a), normal) > 0f;
                triangles.AddRange(front
                    ? new[] { start, start + 1, start + 2, start, start + 2, start + 3 }
                    : new[] { start, start + 2, start + 1, start, start + 3, start + 2 });
            }
            float f = o * h.z;
            float back = -o * h.z;
            // The front face, away from the door.
            Quad(new Vector3(0f, 0f, o), new Vector3(-h.x, -h.y, f), new Vector3(-h.x, h.y, f), new Vector3(h.x, h.y, f), new Vector3(h.x, -h.y, f), size.x, size.y);
            // The top.
            Quad(Vector3.up, new Vector3(-h.x, h.y, back), new Vector3(-h.x, h.y, f), new Vector3(h.x, h.y, f), new Vector3(h.x, h.y, back), size.x, size.z);
            // The two sides.
            Quad(Vector3.left, new Vector3(-h.x, -h.y, back), new Vector3(-h.x, h.y, back), new Vector3(-h.x, h.y, f), new Vector3(-h.x, -h.y, f), size.z, size.y);
            Quad(Vector3.right, new Vector3(h.x, -h.y, f), new Vector3(h.x, h.y, f), new Vector3(h.x, h.y, back), new Vector3(h.x, -h.y, back), size.z, size.y);
            var mesh = new Mesh { name = "Pull" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            PullCache[key] = mesh;
            return mesh;
        }

        private static readonly Dictionary<string, Mesh> LeafCache = new Dictionary<string, Mesh>();

        /// <summary>
        /// A door leaf of <paramref name="size"/> (DoorGeometry's leaf box: x from the hinge at -x to the free end, y up, z
        /// across the wall) with its two levers, one on each face, near the free end at <see cref="Height"/> above the leaf's
        /// bottom: the leaf box (<see cref="PrimitiveKit.BoxMeshSized"/>, UVs in metres) as sub-mesh 0 and the levers as
        /// sub-mesh 1, all in the unit box frame its transform scales by <paramref name="size"/> (DoorLeaf's "Leaf"). Its
        /// renderer takes the leaf's material in slot 0 and <see cref="Material"/> in slot 1. Cached by size.
        /// </summary>
        public static Mesh LeafMesh(Vector3 size)
        {
            string key = string.Format(CultureInfo.InvariantCulture, "{0:0.####}x{1:0.####}x{2:0.####}", size.x, size.y, size.z);
            if (LeafCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh box = PrimitiveKit.BoxMeshSized(size);
            var vertices = new List<Vector3>(box.vertices);
            var normals = new List<Vector3>(box.normals);
            var uvs = new List<Vector2>();
            box.GetUVs(0, uvs);
            int[] leaf = box.triangles;
            var levers = new List<int>();
            Vector3[] unitVertices = PrimitiveKit.BoxMesh.vertices;
            Vector3[] unitNormals = PrimitiveKit.BoxMesh.normals;
            int[] unitTriangles = PrimitiveKit.BoxMesh.triangles;
            var inverse = new Vector3(1f / size.x, 1f / size.y, 1f / size.z);
            void Add(string name, Vector3 center, Vector3 boxSize)
            {
                int start = vertices.Count;
                for (int i = 0; i < unitVertices.Length; i++)
                {
                    // Into the unit frame: the transform scales it back to metres, axis-aligned normals stay as they are.
                    vertices.Add(Vector3.Scale(center + Vector3.Scale(unitVertices[i], boxSize), inverse));
                    normals.Add(unitNormals[i]);
                    uvs.Add(Vector2.zero);
                }
                foreach (int t in unitTriangles)
                {
                    levers.Add(start + t);
                }
            }
            float x = size.x * 0.5f - LeverInset;
            float y = HeightOn(0f, size.y, 0.2f) - size.y * 0.5f;
            foreach (float face in new[] { -1f, 1f })
            {
                Lever(Add, face < 0f ? "Back" : "Front", new Vector3(x, y, face * size.z * 0.5f), face, -1f);
            }
            var mesh = new Mesh { name = "LeafWithHandles", subMeshCount = 2 };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(leaf, 0);
            mesh.SetTriangles(levers, 1);
            mesh.RecalculateBounds();
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            LeafCache[key] = mesh;
            return mesh;
        }

        /// <summary>
        /// A handle box under a door built by PrimitiveKit.Box (its transform scaled by the door's size, never rotated in
        /// its own frame): a child whose local position and scale undo that scale, so the box keeps its size in metres and
        /// moves with the door. Visual only (no collider), in <see cref="Material"/>, plain.
        /// </summary>
        public static GameObject ChildBox(Transform door, string name, Vector3 centerInParent, Vector3 size, int layer)
        {
            Vector3 doorSize = door.localScale;
            Vector3 inverse = new Vector3(1f / doorSize.x, 1f / doorSize.y, 1f / doorSize.z);
            Vector3 local = Vector3.Scale(centerInParent - door.localPosition, inverse);
            return PrimitiveKit.Part(door, name, PrimitiveKit.BoxMeshSized(size), local, Quaternion.identity, Vector3.Scale(size, inverse), Material, layer);
        }
    }
}
