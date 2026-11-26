using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// M5 (docs/CONTRACT_M5.md 6 and 16.5, PRD 3.4): the visual of the load carried on the player furniture, a vase, a stack
    /// of books or a potted plant. A visual only: no collider, and it decides nothing (the kinematic rule of
    /// <see cref="LoadBalance"/> does). CONTRACT_M5 18: LevelBuilder.ApplyLoad creates the view on the furniture's Visual;
    /// GameState.StepLoad drives <see cref="SetTilt"/> from GameState.Load, and GameState spawns and clears the clue.
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
    /// dark wood, FurnitureKit.FrameColor), so a load adds 2 or 3 material slots. The vase and the pot show the plaster
    /// detail; the sprig and the foliage are named "Leaves" and the books "Books", as the props'. M6 (CONTRACT_M6 2.4):
    /// the soil (FurnitureKit.FrameColor, its own finish) and the foliage (Moss002) now show their own detail too, so
    /// they no longer share the near-black frame material.
    /// </summary>
    public sealed class LoadView : MonoBehaviour
    {
        public const string Vase = "vase";
        public const string Books = "books";
        public const string Plant = "plant";
        /// <summary>
        /// NEWFURN (docs/next/progress/NEWFURN.md): the plant stand's banana pot, a banana plant in a terracotta pot,
        /// <see cref="Tuning.BananaLoadHeight"/> tall (LoadKinds.HeightOf), as wide as the stand's tray.
        /// </summary>
        public const string Banana = LoadKinds.Banana;

        /// <summary>
        /// The M5 kinds a level's <c>player.load</c> may name on any loaded body (LoadHeight tall, inside a chair's footprint).
        /// NEWFURN: the plant stand's <see cref="Banana"/> pot is a load too (<see cref="IsKind"/>), listed apart.
        /// </summary>
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
            return LoadKinds.IsKind(kind);
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
        /// <para>m15 (CONTRACT_M5 19): on a split level (the furniture's FloorMap) the clue lies on one floor surface, in its
        /// frame: on a ramp's slope in <see cref="FurnitureController.RampFrame"/>'s frame (never half buried), and when its
        /// spread would cross a platform edge or a ramp's foot or head it moves to the nearest point within
        /// <see cref="Tuning.ClueSearchRadius"/> where it lies whole on one surface (the same height preferred, never past a
        /// wall or a railing): it stays on the platform it fell on. A flat level keeps the caller's point.</para>
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
            Vector3 rest = ClueRest(at, yaw, SpreadOf(go.transform), out Quaternion frame);
            go.transform.SetPositionAndRotation(rest, frame);
            Clue = go;
            Fallen = true;
            if (Carried != null)
            {
                Carried.gameObject.SetActive(false); // MUTATION:LOAD_HIDE
            }
            return go;
        }

        /// <summary>The floor the furniture under this view stands on (the flat floor without one).</summary>
        private FloorMap FloorUnder()
        {
            FurnitureController body = Furniture != null ? Furniture.GetComponentInParent<FurnitureController>() : null;
            return body != null ? body.Floor : FloorMap.Flat;
        }

        /// <summary>The planar radius of a clue's pieces about its root (its local frame), metres.</summary>
        private static float SpreadOf(Transform clue)
        {
            float spread = 0f;
            Matrix4x4 toLocal = clue.worldToLocalMatrix;
            foreach (MeshFilter f in clue.GetComponentsInChildren<MeshFilter>(true))
            {
                if (f.sharedMesh == null || !f.sharedMesh.isReadable)
                {
                    continue;
                }
                Matrix4x4 m = toLocal * f.transform.localToWorldMatrix;
                foreach (Vector3 v in f.sharedMesh.vertices)
                {
                    Vector3 p = m.MultiplyPoint3x4(v);
                    spread = Mathf.Max(spread, new Vector2(p.x, p.z).magnitude);
                }
            }
            return spread;
        }

        /// <summary>The ring samples of the clue's spread.</summary>
        private const int ClueDirections = 16;

        /// <summary>
        /// m15: where a clue of <paramref name="spread"/> fallen at <paramref name="at"/> rests and its <paramref name="frame"/>
        /// (see <see cref="SpawnClue"/>): the caller's point, turned by <paramref name="yaw"/>, on a flat level; else the
        /// candidate nearest <paramref name="at"/> (rings of <see cref="Tuning.ClueSearchStep"/>, a height change costing
        /// twice its distance) where the clue lies whole on one surface, reached without crossing a wall or a railing.
        /// Without any, the caller's point in its own floor frame.
        /// </summary>
        private Vector3 ClueRest(Vector3 at, float yaw, float spread, out Quaternion frame)
        {
            frame = Quaternion.Euler(0f, yaw, 0f);
            FloorMap floor = FloorUnder();
            if (floor == null || floor.IsFlat)
            {
                return at;
            }
            float baseHeight = floor.HeightAt(at);
            Vector3 best = at;
            Quaternion bestFrame = frame;
            float bestCost = float.MaxValue;
            int rings = Mathf.CeilToInt(Tuning.ClueSearchRadius / Tuning.ClueSearchStep);
            for (int k = 0; k <= rings; k++)
            {
                float d = k * Tuning.ClueSearchStep;
                if (d > bestCost)
                {
                    break;
                }
                int directions = k == 0 ? 1 : ClueDirections;
                for (int j = 0; j < directions; j++)
                {
                    Vector3 c = floor.OnFloor(at + YawMath.Forward(j * 360f / directions) * d);
                    float cost = d + 2f * Mathf.Abs(c.y - baseHeight);
                    if (cost >= bestCost)
                    {
                        continue;
                    }
                    bool fits = LiesOnOneSurface(floor, c, yaw, spread, out Vector3 rest, out Quaternion f); // MUTATION:CLUE_SURFACE
                    if (!fits)
                    {
                        continue;
                    }
                    if (k > 0 && ClueBlocked(at, c, spread))
                    {
                        continue;
                    }
                    best = rest;
                    bestFrame = f;
                    bestCost = cost;
                }
            }
            if (bestCost < float.MaxValue)
            {
                frame = bestFrame;
                return best;
            }
            float lift = 0f;
            Vector3 on = floor.OnFloor(at);
            if (FurnitureController.RampFrame(floor, on, yaw, new Vector3(2f * spread, 0f, 2f * spread), ref frame, ref lift))
            {
                on += Vector3.up * lift;
            }
            return on;
        }

        /// <summary>
        /// m15: true when a clue of <paramref name="spread"/> centred on the floor point <paramref name="c"/> lies whole on one
        /// surface: the plane of its floor frame there (a ramp's slope, <see cref="FurnitureController.RampFrame"/>, or level)
        /// meets the floor at its centre and at <see cref="ClueDirections"/> points of its rim and of its half rim, within
        /// <see cref="Tuning.ClueSurfaceTolerance"/>. <paramref name="rest"/> and <paramref name="frame"/>: its pose there.
        /// </summary>
        private static bool LiesOnOneSurface(FloorMap floor, Vector3 c, float yaw, float spread, out Vector3 rest, out Quaternion frame)
        {
            frame = Quaternion.Euler(0f, yaw, 0f);
            float lift = 0f;
            FurnitureController.RampFrame(floor, c, yaw, new Vector3(2f * spread, 0f, 2f * spread), ref frame, ref lift);
            rest = c + Vector3.up * lift;
            Vector3 n = frame * Vector3.up;
            if (n.y < 1e-3f || Mathf.Abs(floor.HeightAt(c) - rest.y) > Tuning.ClueSurfaceTolerance)
            {
                return false;
            }
            for (int ring = 1; ring <= 2; ring++)
            {
                float r = spread * ring * 0.5f;
                for (int j = 0; j < ClueDirections; j++)
                {
                    Vector3 p = c + YawMath.Forward(j * 360f / ClueDirections) * r;
                    float plane = rest.y - (n.x * (p.x - rest.x) + n.z * (p.z - rest.z)) / n.y;
                    if (Mathf.Abs(floor.HeightAt(p) - plane) > Tuning.ClueSurfaceTolerance)
                    {
                        return false;
                    }
                }
            }
            return true;
        }

        /// <summary>
        /// m15: true when moving the clue from <paramref name="at"/> to <paramref name="c"/> (and its spread past it) crosses a
        /// wall, a platform's side, a railing or a furniture other than the player's (Tuning.ClueProbeHeight over the floor).
        /// </summary>
        private bool ClueBlocked(Vector3 at, Vector3 c, float spread)
        {
            Vector3 from = at + Vector3.up * Tuning.ClueProbeHeight;
            Vector3 to = c + Vector3.up * Tuning.ClueProbeHeight;
            Vector3 way = to - from;
            float length = way.magnitude;
            if (length < 1e-5f)
            {
                return false;
            }
            FurnitureController body = Furniture != null ? Furniture.GetComponentInParent<FurnitureController>() : null;
            foreach (RaycastHit hit in Physics.RaycastAll(from, way / length, length + spread, Layers.ChairBlockerMask, QueryTriggerInteraction.Ignore))
            {
                if (hit.collider != null && (body == null || !hit.collider.transform.IsChildOf(body.transform)))
                {
                    return true;
                }
            }
            return false;
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
                case Banana:
                    return BananaWidth * 0.5f;
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
                    Part(parent, "Soil", CachedMesh("soil", () => DiscMesh(SoilRadius, PotHeight - SoilDrop)), FurnitureKit.FrameColor, layer, Surface.Soil);
                    Part(parent, "Leaves", CachedMesh("foliage", () => FoliageMesh(new Vector3(0f, Tuning.LoadHeight - FoliageRadius, 0f))),
                        LeafGreen, layer, Surface.Foliage);
                    break;
                case Banana:
                    // NEWFURN: the banana plant of the level props (FurnitureKit.BananaPot), upright on the tray.
                    FurnitureKit.BananaPot(parent, BananaSize, Vector3.zero, Quaternion.identity, layer);
                    break;
                default:
                    Part(parent, "Vase", CachedMesh("vase", VaseMesh), VaseBlue, layer, Surface.Plaster);
                    Part(parent, "Leaves", CachedMesh("sprig", () => SprigMesh(Matrix4x4.identity)), LeafGreen, layer, Surface.Foliage);
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
                case Banana:
                    // NEWFURN: the banana plant on its side, the pot's mouth toward +x and its leaves spread on the floor past it,
                    // about centred on the clue (from -0.26 to +0.30 m), and its soil spilled out of the mouth.
                    FurnitureKit.BananaPot(parent, BananaSize, new Vector3(-0.26f, BananaLyingLift, 0f), Quaternion.Euler(0f, 0f, -82f), layer);
                    Part(parent, "Soil", CachedMesh("clue banana soil", SpilledSoilMesh), FurnitureKit.FrameColor, layer, Surface.Soil);
                    break;
                case Plant:
                    Part(parent, "Pot", CachedMesh("clue pot", LyingPotMesh), PotBrown, layer, Surface.Plaster);
                    Part(parent, "Soil", CachedMesh("clue soil", SpilledSoilMesh), FurnitureKit.FrameColor, layer, Surface.Soil);
                    Part(parent, "Leaves", CachedMesh("clue foliage", () => FoliageMesh(new Vector3(0.24f, FoliageRadius, 0.07f))),
                        LeafGreen, layer, Surface.Foliage);
                    break;
                default:
                    Part(parent, "Shards", CachedMesh("clue shards", ShardsMesh), VaseBlue, layer, Surface.Plaster);
                    Part(parent, "Leaves", CachedMesh("clue sprig", () => SprigMesh(Matrix4x4.TRS(new Vector3(0.17f, 0.02f, 0.12f),
                        Quaternion.Euler(0f, 35f, 0f) * Quaternion.Euler(84f, 0f, 0f), Vector3.one)
                        * Matrix4x4.Translate(new Vector3(0f, -VaseHeight, 0f)))), LeafGreen, layer, Surface.Foliage);
                    break;
            }
        }

        private static GameObject Part(Transform parent, string name, Mesh mesh, Color colour, int layer, Surface surface)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            // M6 (CONTRACT_M6 2.4): the soil and the foliage have their own fixed finish, cached apart from every other
            // use of the same colour (FurnitureKit.FrameColor, here the soil, is also the metal frame and the robot's
            // bumper); every other part here (books, the vase, the pot, the shards) keeps the plain default, as before.
            bool fixedFinish = TextureLibrary.FinishOf(surface, out _, out _);
            renderer.sharedMaterial = fixedFinish ? PrimitiveKit.LitSurface(colour, surface) : PrimitiveKit.Lit(colour, 0.25f);
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
        // NEWFURN: the banana pot's box (as wide as the plant stand's tray, BananaLoadHeight tall), and how high its lying pot
        // rests on the floor (a little under the pot's rim radius, 0.3 of that width, as the axis rises toward the leaves).
        private const float BananaWidth = 0.40f;
        private static readonly Vector3 BananaSize = new Vector3(BananaWidth, Tuning.BananaLoadHeight, BananaWidth);
        private const float BananaLyingLift = BananaWidth * 0.25f;
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

        /// <summary>Three vertices per rib from left edge to midrib to right edge, with pointed ends.</summary>
        public void AddLeafBlade(Vector3[] ribs)
        {
            int rows = ribs.Length / 3;
            for (int side = 1; side >= -1; side -= 2)
            {
                int start = vertices.Count;
                for (int row = 0; row < rows; row++)
                {
                    int section = 3 * Mathf.Clamp(row, 1, rows - 2);
                    Vector3 along = ribs[3 * Mathf.Min(rows - 1, row + 1) + 1] - ribs[3 * Mathf.Max(0, row - 1) + 1];
                    for (int column = 0; column < 3; column++)
                    {
                        Vector3 across = ribs[section + Mathf.Min(2, column + 1)] - ribs[section + Mathf.Max(0, column - 1)];
                        Vector3 normal = side * Vector3.Cross(along, across).normalized;
                        Add(ribs[row * 3 + column], normal, new Vector2(column * 0.5f, row / (float)(rows - 1)));
                    }
                }
                for (int row = 0; row < rows - 1; row++)
                {
                    for (int column = 0; column < 2; column++)
                    {
                        int a = start + 3 * row + column;
                        int b = a + 3;
                        if (row > 0) { Triangle(a, a + 1, b + 1, normals[a]); }
                        if (row < rows - 2) { Triangle(a, b + 1, b, normals[b]); }
                    }
                }
            }
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

        /// <summary>
        /// PLANT (2026-11-24): a faceted low-poly ellipsoid (a leaf cluster) of <paramref name="radii"/> centred on
        /// <paramref name="m"/>'s origin: <paramref name="rings"/> bands from pole to pole, <paramref name="segments"/> points
        /// around each ring (every other ring turned by half a step, so the facets read as an icosphere's), each point pushed
        /// out or in by <paramref name="bulge"/>(ring, segment), a factor near 1. Flat normals; each face carries UVs in
        /// metres in its own plane (exact, so the detail repeats at its tile). 2 * segments * (rings - 1) triangles.
        /// </summary>
        public void AddBlob(Matrix4x4 m, Vector3 radii, int segments, int rings, System.Func<int, int, float> bulge)
        {
            var grid = new Vector3[rings + 1, segments];
            for (int r = 0; r <= rings; r++)
            {
                float polar = Mathf.PI * r / rings;
                bool pole = r == 0 || r == rings;
                for (int s = 0; s < segments; s++)
                {
                    float az = 2f * Mathf.PI * (s + 0.5f * (r % 2)) / segments;
                    var dir = new Vector3(Mathf.Sin(polar) * Mathf.Sin(az), Mathf.Cos(polar), Mathf.Sin(polar) * Mathf.Cos(az));
                    grid[r, s] = m.MultiplyPoint3x4(Vector3.Scale(dir, radii) * bulge(r, pole ? 0 : s));
                }
            }
            Vector3 centre = m.MultiplyPoint3x4(Vector3.zero);
            for (int r = 0; r < rings; r++)
            {
                // The ring turned by half a step sits between its neighbour's points: pair each point with the right ones.
                bool upperTurned = r % 2 == 1;
                for (int s = 0; s < segments; s++)
                {
                    int next = (s + 1) % segments;
                    Vector3 a0 = grid[r, s];
                    Vector3 a1 = grid[r, next];
                    Vector3 b0 = grid[r + 1, s];
                    Vector3 b1 = grid[r + 1, next];
                    if (upperTurned)
                    {
                        Facet(a0, b1, b0, centre);
                        Facet(a0, a1, b1, centre);
                    }
                    else
                    {
                        Facet(a0, a1, b0, centre);
                        Facet(a1, b1, b0, centre);
                    }
                }
            }
        }

        /// <summary>One flat triangle facing away from <paramref name="centre"/>, UVs in metres in its own plane (degenerate ones are skipped).</summary>
        private void Facet(Vector3 a, Vector3 b, Vector3 c, Vector3 centre)
        {
            Vector3 n = Vector3.Cross(b - a, c - a);
            if (n.sqrMagnitude < 1e-14f)
            {
                return;
            }
            n.Normalize();
            if (Vector3.Dot(n, (a + b + c) / 3f - centre) < 0f)
            {
                n = -n;
            }
            Vector3 u = (b - a).normalized;
            Vector3 v = Vector3.Cross(n, u);
            // Offset each face by its position, so neighbouring faces do not all start the texture at the same corner.
            var origin = new Vector2(a.x + a.z, a.y);
            int ia = Add(a, n, origin);
            int ib = Add(b, n, origin + new Vector2(Vector3.Dot(b - a, u), Vector3.Dot(b - a, v)));
            int ic = Add(c, n, origin + new Vector2(Vector3.Dot(c - a, u), Vector3.Dot(c - a, v)));
            Triangle(ia, ib, ic, n);
        }

        /// <summary>
        /// PLANT: a tapered round rod from <paramref name="from"/> to <paramref name="to"/> (radius <paramref name="r0"/> then
        /// <paramref name="r1"/>), open at both ends (they sit in the soil, a fork or a leaf cluster).
        /// </summary>
        public void AddRod(Vector3 from, Vector3 to, float r0, float r1, int segments)
        {
            Vector3 along = to - from;
            Matrix4x4 m = Matrix4x4.TRS(from, Quaternion.FromToRotation(Vector3.up, along), Vector3.one);
            AddLathe(m, new[] { new Vector2(r0, 0f), new Vector2(r1, along.magnitude) }, segments, false, false);
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
