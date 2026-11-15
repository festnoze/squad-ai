using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace Meuble
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 6 and 16.5, PRD 3.4): the visual of the load carried on the player furniture, a vase, a stack
    /// of books or a potted plant. A visual only: no collider, and it decides nothing (the kinematic rule of
    /// <see cref="LoadBalance"/> does; FurnitureController.SetLoad creates the view and drives its sway).
    /// <list type="bullet">
    /// <item><see cref="Create"/> puts the carried object on the top of the furniture box: its base at the box top
    /// (<c>bodySize.y</c>), centred over the highest part of the furniture's own meshes (a chair's backrest rail, a stool's
    /// seat), kept inside the footprint, and exactly <see cref="Tuning.LoadHeight"/> tall, so it fills the sample box's growth
    /// of 16.5. Parent it to the furniture's Visual so it follows the hop and the jitter.</item>
    /// <item><see cref="SetTilt"/> leans it around its base (the sway of <see cref="LoadBalance.SwayTiltLocal"/>: x to the
    /// furniture's right, y to its front, the length the angle in degrees).</item>
    /// <item><see cref="SpawnClue"/> leaves the broken load on the floor (shards and the sprig of a vase, scattered books, a
    /// pot on its side with its spilled soil) under the level root, and hides the carried one; <see cref="ClearClue"/>
    /// takes the clue away (an inhabitant put it away). Destroying the view leaves its clue on the floor.</item>
    /// </list>
    /// Budgets (CONTRACT_M5 16.11, 17): every colour is a decor colour the levels already draw (the books, the plants, the
    /// dark wood, FurnitureKit.FrameColor), so a load adds 2 or 3 material slots and usually no material. The vase and the
    /// pot show the plaster detail; the sprig and the foliage are named "Leaves" and the books "Books", as the props'.
    /// </summary>
    public sealed class LoadView : MonoBehaviour
    {
        public const string Vase = "vase";
        public const string Books = "books";
        public const string Plant = "plant";

        /// <summary>The kinds a level's <c>player.load</c> may name.</summary>
        public static readonly string[] Kinds = { Vase, Books, Plant };

        /// <summary>The name of every clue root starts with this, followed by the kind.</summary>
        public const string CluePrefix = "LoadClue ";

        // The decor palette (FurnitureKit's book colours and its plant), never red (PRD 7.2).
        private static readonly Color VaseBlue = new Color32(0x5B, 0x93, 0xD9, 0xFF);
        private static readonly Color LeafGreen = new Color32(0x3F, 0x8F, 0x4F, 0xFF);
        private static readonly Color BookYellow = new Color32(0xE3, 0xB2, 0x3C, 0xFF);
        private static readonly Color BookGreen = new Color32(0x2F, 0x6E, 0x4E, 0xFF);
        private static readonly Color PotBrown = new Color32(0x8C, 0x5A, 0x36, 0xFF);

        /// <summary>The top band of the furniture's meshes whose centroid the load is centred on, metres.</summary>
        private const float TopBand = 0.03f;

        /// <summary>A shard's thickness, metres.</summary>
        private const float ShardThickness = 0.008f;

        public string Kind { get; private set; }

        /// <summary>The transform the view hangs under (the furniture, or its Visual).</summary>
        public Transform Furniture { get; private set; }

        public Vector3 BodySize { get; private set; }

        /// <summary>The pivot of the carried object, at its base: <see cref="SetTilt"/> turns it.</summary>
        public Transform Carried { get; private set; }

        /// <summary>The last tilt set, degrees (x to the furniture's right, y to its front).</summary>
        public Vector2 Tilt { get; private set; }

        /// <summary>The broken load on the floor, or null.</summary>
        public GameObject Clue { get; private set; }

        public bool ClueActive => Clue != null && Clue.activeInHierarchy;

        /// <summary>True from <see cref="SpawnClue"/> until <see cref="Restore"/>: the carried object is hidden.</summary>
        public bool Fallen { get; private set; }

        /// <summary>True when <paramref name="kind"/> is a load kind.</summary>
        public static bool IsKind(string kind)
        {
            return kind == Vase || kind == Books || kind == Plant;
        }

        /// <summary>
        /// The load of <paramref name="kind"/> on the furniture <paramref name="furniture"/> whose box is
        /// <paramref name="bodySize"/> (its base on the furniture's origin, centred): null, with one warning, for an unknown
        /// kind or no furniture.
        /// </summary>
        public static LoadView Create(string kind, Transform furniture, Vector3 bodySize)
        {
            if (furniture == null || !IsKind(kind))
            {
                Debug.LogWarning($"[LoadView] no load '{kind}' on {(furniture != null ? furniture.name : "no furniture")}");
                return null;
            }
            float radius = FootprintRadius(kind);
            Vector3 seat = TopCentre(furniture, bodySize, radius);
            int layer = furniture.gameObject.layer;
            var go = new GameObject("Load " + kind) { layer = layer };
            go.transform.SetParent(furniture, false);
            go.transform.localPosition = seat;
            go.transform.localRotation = Quaternion.identity;
            LoadView view = go.AddComponent<LoadView>();
            view.Kind = kind;
            view.Furniture = furniture;
            view.BodySize = bodySize;
            var pivot = new GameObject("Carried") { layer = layer };
            pivot.transform.SetParent(go.transform, false);
            view.Carried = pivot.transform;
            BuildCarried(kind, view.Carried, layer);
            return view;
        }

        /// <summary>
        /// Leans the carried object around its base: <paramref name="degrees"/>.x toward the furniture's right,
        /// <paramref name="degrees"/>.y toward its front, by the vector's length in degrees (visual only).
        /// </summary>
        public void SetTilt(Vector2 degrees)
        {
            Tilt = degrees;
            if (Carried == null)
            {
                return;
            }
            float angle = degrees.magnitude;
            Carried.localRotation = angle > 1e-4f
                ? Quaternion.AngleAxis(angle, new Vector3(degrees.y, 0f, -degrees.x) / angle)
                : Quaternion.identity;
        }

        /// <summary>
        /// The load falls: its broken version lies on the floor at <paramref name="at"/> (world; the floor point the caller
        /// chose), turned like the furniture, under the level root; the carried object is hidden. A previous clue is taken
        /// away first. Returns the clue's root.
        /// </summary>
        public GameObject SpawnClue(Vector3 at)
        {
            ClearClue();
            Transform root = Furniture != null ? Furniture.root : null;
            Transform parent = root != null && root != Furniture ? root : null;
            var go = new GameObject(CluePrefix + Kind);
            go.transform.SetParent(parent, false);
            float yaw = Furniture != null ? Furniture.eulerAngles.y : 0f;
            go.transform.SetPositionAndRotation(at, Quaternion.Euler(0f, yaw, 0f));
            BuildClue(Kind, go.transform, go.layer);
            Clue = go;
            Fallen = true;
            if (Carried != null)
            {
                Carried.gameObject.SetActive(false); // MUTATION:LOAD_HIDE
            }
            return go;
        }

        /// <summary>Takes the clue off the floor (an inhabitant put it away). Nothing without one.</summary>
        public void ClearClue()
        {
            if (Clue == null)
            {
                return;
            }
            Clue.SetActive(false);
            if (Application.isPlaying)
            {
                Destroy(Clue);
            }
            else
            {
                DestroyImmediate(Clue);
            }
            Clue = null;
        }

        /// <summary>The carried object back on the furniture, upright (a fresh load; the clue is left as it is).</summary>
        public void Restore()
        {
            Fallen = false;
            if (Carried != null)
            {
                Carried.gameObject.SetActive(true);
            }
            SetTilt(Vector2.zero);
        }

        /// <summary>World bounds of the carried object's renderers (tests), or an empty box at the view.</summary>
        public Bounds CarriedBounds => BoundsOf(Carried != null ? Carried : transform);

        /// <summary>World bounds of the renderers under <paramref name="t"/>, or an empty box at it.</summary>
        public static Bounds BoundsOf(Transform t)
        {
            var bounds = new Bounds(t != null ? t.position : Vector3.zero, Vector3.zero);
            bool any = false;
            if (t == null)
            {
                return bounds;
            }
            foreach (Renderer r in t.GetComponentsInChildren<Renderer>(true))
            {
                if (!any)
                {
                    bounds = r.bounds;
                    any = true;
                }
                else
                {
                    bounds.Encapsulate(r.bounds);
                }
            }
            return bounds;
        }

        // ----- Placement -----

        /// <summary>The planar radius of a load kind's footprint (its farthest point from its axis), metres.</summary>
        public static float FootprintRadius(string kind)
        {
            switch (kind)
            {
                case Books:
                    return 0.5f * Mathf.Sqrt(0.2f * 0.2f + 0.14f * 0.14f);
                case Plant:
                    return 0.07f;
                default:
                    return 0.062f;
            }
        }

        /// <summary>
        /// The base of the load in <paramref name="furniture"/>'s space: at the box top (y = size.y), over the centroid of the
        /// furniture meshes' top band (the highest part: a chair's backrest rail, a stool's seat), pulled inside the
        /// footprint by the load's radius. The box centre when no readable mesh is found.
        /// </summary>
        public static Vector3 TopCentre(Transform furniture, Vector3 size, float radius)
        {
            float top = float.MinValue;
            var points = new List<Vector3>();
            Matrix4x4 toLocal = furniture.worldToLocalMatrix;
            foreach (MeshFilter f in furniture.GetComponentsInChildren<MeshFilter>(true))
            {
                Mesh mesh = f.sharedMesh;
                if (mesh == null || !mesh.isReadable || f.GetComponentInParent<LoadView>() != null)
                {
                    continue;
                }
                Matrix4x4 m = toLocal * f.transform.localToWorldMatrix;
                foreach (Vector3 v in mesh.vertices)
                {
                    Vector3 p = m.MultiplyPoint3x4(v);
                    points.Add(p);
                    top = Mathf.Max(top, p.y);
                }
            }
            float x = 0f;
            float z = 0f;
            int n = 0;
            foreach (Vector3 p in points)
            {
                if (p.y >= top - TopBand)
                {
                    x += p.x;
                    z += p.z;
                    n++;
                }
            }
            if (n > 0)
            {
                x /= n;
                z /= n;
            }
            float hx = Mathf.Max(0f, size.x * 0.5f - radius);
            float hz = Mathf.Max(0f, size.z * 0.5f - radius);
            return new Vector3(Mathf.Clamp(x, -hx, hx), size.y, Mathf.Clamp(z, -hz, hz));
        }

        // ----- The carried objects (local: base at y = 0, axis on +y, the front on +z) -----

        private static void BuildCarried(string kind, Transform parent, int layer)
        {
            switch (kind)
            {
                case Books:
                    Part(parent, "Books 1", CachedMesh("books1", () => BookMesh(0.20f, 0.14f, 0f, 0f)), BookYellow, layer, Surface.Plain);
                    Part(parent, "Books 2", CachedMesh("books2", () => BookMesh(0.18f, 0.13f, BookThickness, -9f)), VaseBlue, layer, Surface.Plain);
                    Part(parent, "Books 3", CachedMesh("books3", () => BookMesh(0.16f, 0.12f, 2f * BookThickness, 14f)), BookGreen, layer, Surface.Plain);
                    break;
                case Plant:
                    Part(parent, "Pot", CachedMesh("pot", PotMesh), PotBrown, layer, Surface.Plaster);
                    Part(parent, "Soil", CachedMesh("soil", () => DiscMesh(SoilRadius, PotHeight - SoilDrop)), FurnitureKit.FrameColor, layer, Surface.Plain);
                    Part(parent, "Leaves", CachedMesh("foliage", () => FoliageMesh(new Vector3(0f, Tuning.LoadHeight - FoliageRadius, 0f))),
                        LeafGreen, layer, Surface.Plain);
                    break;
                default:
                    Part(parent, "Vase", CachedMesh("vase", VaseMesh), VaseBlue, layer, Surface.Plaster);
                    Part(parent, "Leaves", CachedMesh("sprig", () => SprigMesh(Matrix4x4.identity)), LeafGreen, layer, Surface.Plain);
                    break;
            }
        }

        private static void BuildClue(string kind, Transform parent, int layer)
        {
            switch (kind)
            {
                case Books:
                    Part(parent, "Books 1", CachedMesh("clue books1", () => LyingBook(0.20f, 0.14f, new Vector3(-0.16f, 0f, 0.05f), 22f)), BookYellow, layer, Surface.Plain);
                    Part(parent, "Books 2", CachedMesh("clue books2", () => LyingBook(0.18f, 0.13f, new Vector3(0.13f, 0f, -0.09f), -37f)), VaseBlue, layer, Surface.Plain);
                    Part(parent, "Books 3", CachedMesh("clue books3", () => OpenBook(0.16f, 0.12f, new Vector3(0.03f, 0f, 0.21f), 71f)), BookGreen, layer, Surface.Plain);
                    break;
                case Plant:
                    Part(parent, "Pot", CachedMesh("clue pot", LyingPotMesh), PotBrown, layer, Surface.Plaster);
                    Part(parent, "Soil", CachedMesh("clue soil", SpilledSoilMesh), FurnitureKit.FrameColor, layer, Surface.Plain);
                    Part(parent, "Leaves", CachedMesh("clue foliage", () => FoliageMesh(new Vector3(0.24f, FoliageRadius, 0.07f))),
                        LeafGreen, layer, Surface.Plain);
                    break;
                default:
                    Part(parent, "Shards", CachedMesh("clue shards", ShardsMesh), VaseBlue, layer, Surface.Plaster);
                    Part(parent, "Leaves", CachedMesh("clue sprig", () => SprigMesh(Matrix4x4.TRS(new Vector3(0.17f, 0.02f, 0.12f),
                        Quaternion.Euler(0f, 35f, 0f) * Quaternion.Euler(84f, 0f, 0f), Vector3.one)
                        * Matrix4x4.Translate(new Vector3(0f, -VaseHeight, 0f)))), LeafGreen, layer, Surface.Plain);
                    break;
            }
        }

        private static GameObject Part(Transform parent, string name, Mesh mesh, Color colour, int layer, Surface surface)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = PrimitiveKit.Lit(colour);
            renderer.shadowCastingMode = ShadowCastingMode.On;
            renderer.receiveShadows = true;
            PrimitiveKit.Detail(renderer, surface);
            return go;
        }

        // ----- Meshes (metres, UVs in metres; cached, so a rebuilt level reuses them) -----

        private static readonly Dictionary<string, Mesh> Meshes = new Dictionary<string, Mesh>();

        internal static Mesh CachedMesh(string key, System.Func<Mesh> build)
        {
            if (Meshes.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh mesh = build();
            mesh.name = "Load " + key;
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            Meshes[key] = mesh;
            return mesh;
        }

        private const int Segments = 14;
        private const float VaseHeight = 0.17f;
        private const float PotHeight = 0.11f;
        private const float FoliageRadius = 0.07f;
        private const float BookThickness = Tuning.LoadHeight / 3f;
        // The soil sits this far under the pot's open rim, filling the pot's width there.
        private const float SoilDrop = 0.006f;
        private const float SoilRadius = 0.045f + (0.062f - 0.045f) * (PotHeight - SoilDrop) / PotHeight;

        // The vase's profile (radius, height): a round belly, a neck and a lip; the sprig rises out of it to LoadHeight.
        private static readonly Vector2[] VaseProfile =
        {
            new Vector2(0.040f, 0f), new Vector2(0.054f, 0.028f), new Vector2(0.062f, 0.068f), new Vector2(0.052f, 0.115f),
            new Vector2(0.031f, 0.148f), new Vector2(0.036f, VaseHeight),
        };

        private static readonly Vector2[] PotProfile =
        {
            new Vector2(0.045f, 0f), new Vector2(0.062f, PotHeight),
        };

        private static Mesh VaseMesh()
        {
            var b = new MeshBuilder();
            b.AddLathe(Matrix4x4.identity, VaseProfile, Segments, true, true);
            return b.Build();
        }

        private static Mesh PotMesh()
        {
            var b = new MeshBuilder();
            b.AddLathe(Matrix4x4.identity, PotProfile, Segments, true, false);
            return b.Build();
        }

        private static Mesh LyingPotMesh()
        {
            var b = new MeshBuilder();
            // On its side, its mouth toward +x, turned up by its taper so it rests along a whole side on the floor.
            Vector2 foot = PotProfile[0];
            Vector2 rim = PotProfile[1];
            float taper = Mathf.Atan2(rim.x - foot.x, rim.y - foot.y);
            float rest = foot.x * Mathf.Cos(taper);
            Matrix4x4 m = Matrix4x4.TRS(new Vector3(-0.08f, rest, 0.02f), Quaternion.Euler(0f, 0f, -90f + taper * Mathf.Rad2Deg), Vector3.one);
            b.AddLathe(m, PotProfile, Segments, true, false);
            return b.Build();
        }

        private static Mesh SpilledSoilMesh()
        {
            var b = new MeshBuilder();
            b.AddDisc(Matrix4x4.TRS(new Vector3(0.09f, 0.004f, 0.02f), Quaternion.identity, new Vector3(1.3f, 1f, 0.8f)), 0.09f, Segments);
            b.AddDisc(Matrix4x4.Translate(new Vector3(0.2f, 0.003f, -0.06f)), 0.035f, 8);
            return b.Build();
        }

        private static Mesh DiscMesh(float radius, float y)
        {
            var b = new MeshBuilder();
            b.AddDisc(Matrix4x4.Translate(new Vector3(0f, y, 0f)), radius, Segments);
            return b.Build();
        }

        /// <summary>A rough ball of foliage (a coarse sphere) of <see cref="FoliageRadius"/> at <paramref name="centre"/>.</summary>
        private static Mesh FoliageMesh(Vector3 centre)
        {
            var profile = new Vector2[6];
            for (int i = 0; i < profile.Length; i++)
            {
                float a = Mathf.PI * i / (profile.Length - 1);
                profile[i] = new Vector2(FoliageRadius * Mathf.Sin(a), centre.y - FoliageRadius * Mathf.Cos(a));
            }
            profile[0].x = 0.001f;
            profile[profile.Length - 1].x = 0.001f;
            var b = new MeshBuilder();
            b.AddLathe(Matrix4x4.Translate(new Vector3(centre.x, 0f, centre.z)), profile, 9, false, false);
            return b.Build();
        }

        /// <summary>Three leaves rising out of the vase's mouth to LoadHeight, as tilted boxes.</summary>
        private static Mesh SprigMesh(Matrix4x4 frame)
        {
            var b = new MeshBuilder();
            float leaf = Tuning.LoadHeight - VaseHeight + 0.01f;
            var size = new Vector3(0.026f, leaf, 0.012f);
            for (int i = 0; i < 3; i++)
            {
                float yaw = 120f * i + 20f;
                float lean = i == 0 ? 6f : 18f;
                Quaternion q = Quaternion.Euler(0f, yaw, 0f) * Quaternion.Euler(lean, 0f, 0f);
                // The leaf's base sits in the mouth; its top corner reaches LoadHeight at most.
                float h = Mathf.Cos(lean * Mathf.Deg2Rad) * leaf + Mathf.Sin(lean * Mathf.Deg2Rad) * size.z * 0.5f;
                Vector3 baseAt = new Vector3(0f, Tuning.LoadHeight - h, 0f);
                b.AddBox(frame * Matrix4x4.TRS(baseAt + q * new Vector3(0f, leaf * 0.5f, 0f), q, Vector3.one), size);
            }
            return b.Build();
        }

        private static Mesh BookMesh(float length, float depth, float y, float yaw)
        {
            var b = new MeshBuilder();
            b.AddBox(Matrix4x4.TRS(new Vector3(0f, y + BookThickness * 0.5f, 0f), Quaternion.Euler(0f, yaw, 0f), Vector3.one),
                new Vector3(length, BookThickness - 0.002f, depth));
            return b.Build();
        }

        private static Mesh LyingBook(float length, float depth, Vector3 at, float yaw)
        {
            var b = new MeshBuilder();
            float t = BookThickness - 0.002f;
            b.AddBox(Matrix4x4.TRS(at + new Vector3(0f, t * 0.5f, 0f), Quaternion.Euler(0f, yaw, 0f), Vector3.one), new Vector3(length, t, depth));
            return b.Build();
        }

        /// <summary>A book fallen open, face down: two half covers leaning on each other like a small tent.</summary>
        private static Mesh OpenBook(float length, float depth, Vector3 at, float yaw)
        {
            var b = new MeshBuilder();
            float half = length * 0.5f;
            const float lift = 18f;
            float t = 0.012f;
            Quaternion turn = Quaternion.Euler(0f, yaw, 0f);
            for (int side = -1; side <= 1; side += 2)
            {
                Quaternion q = turn * Quaternion.Euler(0f, 0f, -side * lift);
                Vector3 centre = at + turn * new Vector3(side * half * 0.5f * Mathf.Cos(lift * Mathf.Deg2Rad), half * 0.5f * Mathf.Sin(lift * Mathf.Deg2Rad) + t * 0.5f, 0f);
                b.AddBox(Matrix4x4.TRS(centre, q, Vector3.one), new Vector3(half, t, depth));
            }
            return b.Build();
        }

        /// <summary>The vase broken on the floor: its foot, and shards scattered around it (one mesh).</summary>
        private static Mesh ShardsMesh()
        {
            var b = new MeshBuilder();
            b.AddLathe(Matrix4x4.identity, new[] { VaseProfile[0], VaseProfile[1], new Vector2(0.06f, 0.045f) }, Segments, false, true);
            // Deterministic scatter: (distance, bearing, size, yaw) of each shard.
            Vector4[] shards =
            {
                new Vector4(0.13f, 20f, 0.055f, 15f), new Vector4(0.19f, 95f, 0.045f, 70f), new Vector4(0.11f, 160f, 0.06f, 140f),
                new Vector4(0.24f, 215f, 0.04f, 200f), new Vector4(0.16f, 280f, 0.05f, 300f), new Vector4(0.27f, 330f, 0.035f, 10f),
                new Vector4(0.09f, 245f, 0.03f, 120f),
            };
            foreach (Vector4 s in shards)
            {
                Vector3 at = YawMath.Forward(s.y) * s.x;
                b.AddShard(Matrix4x4.TRS(at, Quaternion.Euler(0f, s.w, 0f), Vector3.one), s.z, ShardThickness);
            }
            return b.Build();
        }
    }

    /// <summary>
    /// M5: a small builder of static procedural meshes in metres, with UVs in metres (so PrimitiveKit.Detail measures them),
    /// normals per face (flat around boxes and shards, smooth around a lathe), every face wound to face its normal.
    /// Used by <see cref="LoadView"/> and <see cref="Robot"/>.
    /// </summary>
    internal sealed class MeshBuilder
    {
        private readonly List<Vector3> vertices = new List<Vector3>();
        private readonly List<Vector3> normals = new List<Vector3>();
        private readonly List<Vector2> uvs = new List<Vector2>();
        private readonly List<int> triangles = new List<int>();

        public int VertexCount => vertices.Count;

        private int Add(Vector3 p, Vector3 n, Vector2 uv)
        {
            vertices.Add(p);
            normals.Add(n);
            uvs.Add(uv);
            return vertices.Count - 1;
        }

        /// <summary>A triangle facing <paramref name="facing"/> (its winding is chosen so Unity draws that side).</summary>
        private void Triangle(int a, int b, int c, Vector3 facing)
        {
            Vector3 n = Vector3.Cross(vertices[b] - vertices[a], vertices[c] - vertices[a]);
            triangles.Add(a);
            if (Vector3.Dot(n, facing) >= 0f)
            {
                triangles.Add(b);
                triangles.Add(c);
            }
            else
            {
                triangles.Add(c);
                triangles.Add(b);
            }
        }

        private void Quad(int a, int b, int c, int d, Vector3 facing)
        {
            Triangle(a, b, c, facing);
            Triangle(a, c, d, facing);
        }

        /// <summary>A box of <paramref name="size"/> centred on <paramref name="m"/>'s origin, its UVs projected per face in metres.</summary>
        public void AddBox(Matrix4x4 m, Vector3 size)
        {
            Vector3 h = size * 0.5f;
            Vector3[] axes = { Vector3.right, Vector3.up, Vector3.forward };
            for (int axis = 0; axis < 3; axis++)
            {
                for (int sign = -1; sign <= 1; sign += 2)
                {
                    Vector3 n = axes[axis] * sign;
                    Vector3 u = axes[(axis + 1) % 3];
                    Vector3 v = axes[(axis + 2) % 3];
                    float hu = Vector3.Dot(h, u);
                    float hv = Vector3.Dot(h, v);
                    float hn = Vector3.Dot(h, axes[axis]);
                    var corners = new int[4];
                    Vector3 worldN = m.MultiplyVector(n).normalized;
                    for (int k = 0; k < 4; k++)
                    {
                        float su = k == 0 || k == 3 ? -1f : 1f;
                        float sv = k < 2 ? -1f : 1f;
                        Vector3 local = n * hn + u * (su * hu) + v * (sv * hv);
                        corners[k] = Add(m.MultiplyPoint3x4(local), worldN, new Vector2(su * hu, sv * hv));
                    }
                    Quad(corners[0], corners[1], corners[2], corners[3], worldN);
                }
            }
        }

        /// <summary>
        /// A surface of revolution around <paramref name="m"/>'s +y: <paramref name="profile"/> is (radius, height) from the
        /// bottom up. Caps close the bottom and the top. UVs: the arc length around, the profile length up (metres).
        /// </summary>
        public void AddLathe(Matrix4x4 m, Vector2[] profile, int segments, bool capBottom, bool capTop)
        {
            float run = 0f;
            for (int i = 0; i + 1 < profile.Length; i++)
            {
                Vector2 a = profile[i];
                Vector2 b = profile[i + 1];
                Vector2 along = b - a;
                float length = along.magnitude;
                if (length < 1e-6f)
                {
                    continue;
                }
                // The outward normal of the profile segment (radius out, height up).
                var n2 = new Vector2(along.y, -along.x) / length;
                float meanRadius = 0.5f * (a.x + b.x);
                int start = vertices.Count;
                for (int s = 0; s <= segments; s++)
                {
                    float angle = 2f * Mathf.PI * s / segments;
                    var dir = new Vector3(Mathf.Sin(angle), 0f, Mathf.Cos(angle));
                    Vector3 normal = m.MultiplyVector(dir * n2.x + Vector3.up * n2.y).normalized;
                    float u = angle * meanRadius;
                    Add(m.MultiplyPoint3x4(dir * a.x + Vector3.up * a.y), normal, new Vector2(u, run));
                    Add(m.MultiplyPoint3x4(dir * b.x + Vector3.up * b.y), normal, new Vector2(u, run + length));
                }
                for (int s = 0; s < segments; s++)
                {
                    int i0 = start + 2 * s;
                    int i1 = i0 + 2;
                    float mid = 2f * Mathf.PI * (s + 0.5f) / segments;
                    Vector3 facing = m.MultiplyVector(new Vector3(Mathf.Sin(mid), 0f, Mathf.Cos(mid)) * n2.x + Vector3.up * n2.y);
                    Quad(i0, i1, i1 + 1, i0 + 1, facing);
                }
                run += length;
            }
            if (capBottom && profile[0].x > 1e-4f)
            {
                AddCap(m, profile[0].x, profile[0].y, segments, false);
            }
            if (capTop && profile[profile.Length - 1].x > 1e-4f)
            {
                AddCap(m, profile[profile.Length - 1].x, profile[profile.Length - 1].y, segments, true);
            }
        }

        /// <summary>A flat disc facing up (in <paramref name="m"/>'s frame) of <paramref name="radius"/> at its origin.</summary>
        public void AddDisc(Matrix4x4 m, float radius, int segments)
        {
            AddCap(m, radius, 0f, segments, true);
        }

        private void AddCap(Matrix4x4 m, float radius, float y, int segments, bool up)
        {
            Vector3 n = m.MultiplyVector(up ? Vector3.up : Vector3.down).normalized;
            int centre = Add(m.MultiplyPoint3x4(new Vector3(0f, y, 0f)), n, Vector2.zero);
            int first = vertices.Count;
            for (int s = 0; s <= segments; s++)
            {
                float angle = 2f * Mathf.PI * s / segments;
                var p = new Vector3(Mathf.Sin(angle) * radius, y, Mathf.Cos(angle) * radius);
                Add(m.MultiplyPoint3x4(p), n, new Vector2(p.x, p.z));
            }
            for (int s = 0; s < segments; s++)
            {
                Triangle(centre, first + s, first + s + 1, n);
            }
        }

        /// <summary>A flat irregular shard (a thin triangular prism) of about <paramref name="size"/> lying on its frame's floor.</summary>
        public void AddShard(Matrix4x4 m, float size, float thickness)
        {
            Vector3[] outline =
            {
                new Vector3(-0.5f * size, 0f, -0.3f * size), new Vector3(0.55f * size, 0f, -0.15f * size), new Vector3(-0.05f * size, 0f, 0.5f * size),
            };
            Vector3 up = m.MultiplyVector(Vector3.up).normalized;
            var top = new int[3];
            var bottom = new int[3];
            for (int k = 0; k < 3; k++)
            {
                Vector3 p = outline[k];
                top[k] = Add(m.MultiplyPoint3x4(p + Vector3.up * thickness), up, new Vector2(p.x, p.z));
                bottom[k] = Add(m.MultiplyPoint3x4(p), -up, new Vector2(p.x, p.z));
            }
            Triangle(top[0], top[1], top[2], up);
            Triangle(bottom[0], bottom[1], bottom[2], -up);
            for (int k = 0; k < 3; k++)
            {
                Vector3 a = outline[k];
                Vector3 b = outline[(k + 1) % 3];
                Vector3 side = Vector3.Cross(b - a, Vector3.up).normalized;
                Vector3 centre = (outline[0] + outline[1] + outline[2]) / 3f;
                if (Vector3.Dot(side, (a + b) * 0.5f - centre) < 0f)
                {
                    side = -side;
                }
                Vector3 sideWorld = m.MultiplyVector(side).normalized;
                float len = (b - a).magnitude;
                int i0 = Add(m.MultiplyPoint3x4(a), sideWorld, new Vector2(0f, 0f));
                int i1 = Add(m.MultiplyPoint3x4(b), sideWorld, new Vector2(len, 0f));
                int i2 = Add(m.MultiplyPoint3x4(b + Vector3.up * thickness), sideWorld, new Vector2(len, thickness));
                int i3 = Add(m.MultiplyPoint3x4(a + Vector3.up * thickness), sideWorld, new Vector2(0f, thickness));
                Quad(i0, i1, i2, i3, sideWorld);
            }
        }

        public Mesh Build()
        {
            var mesh = new Mesh();
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            return mesh;
        }
    }
}
