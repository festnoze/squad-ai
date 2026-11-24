using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// CEILING (product owner request, 2026-11-24, docs/next/progress/CEILING.md): a painted ceiling over every room, seen
    /// from inside (the title tour at furniture eye level, a low orbit), gone from the overhead cutaway view.
    /// <list type="bullet">
    /// <item>Geometry: one grid of quads per room (<see cref="Cell"/> apart), facing down, over the room's footprint (its wall
    /// centre lines, so its edges hide inside the walls) at the room's wall top. Built by LevelBuilder after the walls, the
    /// floors and the lights, under the level root (child <see cref="RootName"/>).</item>
    /// <item>No gameplay effect: no collider (vision raycasts, hearing, the NavMesh and LevelAudit never see it), Default
    /// layer (no x-ray stencil, no occluder), no shadow cast (the sun, the moon and the lamps light the rooms exactly as
    /// before), and every renderer is built disabled, so the budgets the audit and the probe count do not change.</item>
    /// <item>Material: the walls' one material (WallArray, OutOfSight/Wall Finishes), each vertex naming a flat warm
    /// off-white (WallArray.Flat's encoding: UV1.x -1, UV2 the linear colour): no new material, lit by URP like the walls
    /// (the trilight's ground colour from below by day, almost nothing at night, the lamps' own point lights, SSAO in the
    /// corners on Haut). Without the wall material (textures off) a URP Lit one of the same colour.</item>
    /// <item>Bounce: the room lights are spots aimed down (RoomLights, LitZoneView), which never reach a ceiling. Each one's
    /// floor pool is bounced onto its room's ceiling instead, as a glow per vertex (UV2.w, emission = colour times glow):
    /// <see cref="BounceStrength"/> times the pool's light (intensity over the squared distance) times the form factor of a
    /// floor patch below, (h^2 / (h^2 + r^2))^2 (h narrowed by <see cref="BounceSpread"/>), capped at <see cref="BounceMax"/>.
    /// The sun or the moon on the floors is bounced too (<see cref="SunBounce"/> of its light on a level floor, darker toward
    /// the walls): without it a ceiling by day stays a brown lid under the ambient's ground colour. No new real-time light.
    /// It follows the lights (tier, the night preset, a lamp's room dimming): a light switched off or dimmed rebakes its
    /// room's glow, a new sun or moon every room's.</item>
    /// <item>The rule (<see cref="ShowsFrom"/>): a room's ceiling shows only while the camera is below it by
    /// <see cref="HideMargin"/>. A plane at height H can never hide anything below H from an eye below H (the segment between
    /// two points below a plane never crosses it), and from above it is seen from behind and culled, so it can never hide
    /// the player's furniture, an inhabitant or a vision cone. It shows and hides over <see cref="FadeSeconds"/> per room: a
    /// ceiling that fully shows is its opaque renderer; while it fades, its renderer is off and a copy is drawn each frame
    /// with the wall fader's see-through material (WallFader.GhostMaterial) at its opacity, for the tracked camera only. A
    /// level start or a camera jump snaps.</item>
    /// </list>
    /// </summary>
    [DefaultExecutionOrder(310)] // after OrbitCamera (200), TitleCameraTour (250) and WallFader (300): the camera has moved
    public sealed class RoomCeilings : MonoBehaviour
    {
        public const string RootName = "Ceilings";

        /// <summary>Tests and tools: build no ceiling (the "before" shots).</summary>
        public static bool Disabled;

        /// <summary>The paint: a slightly warm off-white (sRGB).</summary>
        public static readonly Color PaintColour = new Color(0.93f, 0.90f, 0.85f);

        /// <summary>Matte paint.</summary>
        public const float Smoothness = 0.08f;

        /// <summary>The camera must stand this far below a ceiling for it to show (metres).</summary>
        public const float HideMargin = 0.1f;

        /// <summary>A ceiling shows or hides over this long (seconds, unscaled time).</summary>
        public const float FadeSeconds = 0.3f;

        /// <summary>The share of a floor pool's light its room's ceiling gets right above it (floor albedo and pool size folded in).</summary>
        public const float BounceStrength = 0.08f;

        /// <summary>
        /// The pool's spread on the ceiling: the form factor's height is this share of the true one, so a pool reads as a
        /// soft patch over its lamp (the whole bounce, walls included, would be broader and flatter).
        /// </summary>
        public const float BounceSpread = 0.65f;

        /// <summary>
        /// The share of the sun's (or the moon's) light on the floor the ceilings get back (the floors are lit from above:
        /// the house has no roof, and the ceilings cast no shadow). Uniform, darker toward the walls
        /// (<see cref="EdgeShade"/> at a wall face, none from <see cref="EdgeReach"/> in).
        /// </summary>
        public const float SunBounce = 0.25f;

        public const float EdgeShade = 0.4f;
        public const float EdgeReach = 1.0f;

        /// <summary>The bounce glow never exceeds this light (linear luminance) at any point of a ceiling: no glowing slab.</summary>
        public const float BounceMax = 0.3f;

        /// <summary>How much of the glow's own colour (the light's) tints the paint where the glow is strong.</summary>
        private const float GlowTint = 0.8f;

        /// <summary>The grid spacing of a ceiling (metres): the glow is interpolated between its vertices.</summary>
        public const float Cell = 0.5f;

        /// <summary>Tools and look tests: the bounce strength instead of <see cref="BounceStrength"/>.</summary>
        public static float? BounceOverride;

        /// <summary>Tools and look tests: the sun bounce instead of <see cref="SunBounce"/>.</summary>
        public static float? SunBounceOverride;

        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        private static readonly int SmoothnessId = Shader.PropertyToID("_Smoothness");
        private static readonly int MetallicId = Shader.PropertyToID("_Metallic");
        private static readonly int ArrayFinishId = Shader.PropertyToID(WallArray.ArrayFinishProperty);

        /// <summary>A room light whose floor pool lights a ceiling.</summary>
        private sealed class Source
        {
            public Light Light;
            /// <summary>The pool's centre (where the spot's axis meets the floor) and the light's distance to it.</summary>
            public Vector3 Pool;
            public float Distance;
            /// <summary>The intensity the glow was last baked with (0: off).</summary>
            public float Seen = -1f;
        }

        private sealed class Ceiling
        {
            public RoomDef Room;
            public float Height;
            public MeshRenderer Renderer;
            public Mesh Mesh;
            public Vector3[] Vertices;
            public List<Vector4> Paint;
            public readonly List<Source> Sources = new List<Source>();
            /// <summary>1 fully shown (its renderer), 0 gone, in between fading (its see-through copy).</summary>
            public float Level;
            public MaterialPropertyBlock Ghost;
            public float Applied = -1f;
            public float GlowMax;
        }

        private readonly List<Ceiling> ceilings = new List<Ceiling>();
        private bool wallMaterial;
        private bool started;
        private Vector3 lastEye;
        private float bakedStrength = -1f;
        private float bakedSun = -1f;

        /// <summary>The camera the rule follows; the main camera when null.</summary>
        public Camera View;

        /// <summary>Number of ceilings (one per room).</summary>
        public int Count => ceilings.Count;

        /// <summary>The room of ceiling <paramref name="i"/> (the order of LevelDef.AllRooms).</summary>
        public RoomDef RoomOf(int i) => ceilings[i].Room;

        /// <summary>The renderer of ceiling <paramref name="i"/> (enabled only while it fully shows).</summary>
        public MeshRenderer RendererOf(int i) => ceilings[i].Renderer;

        /// <summary>The height of ceiling <paramref name="i"/> (its room's wall top).</summary>
        public float HeightOf(int i) => ceilings[i].Height;

        /// <summary>How much ceiling <paramref name="i"/> shows: 1 fully, 0 not at all, in between fading.</summary>
        public float LevelOf(int i) => ceilings[i].Level;

        /// <summary>The strongest bounce glow of ceiling <paramref name="i"/> (UV2.w, over its colour) as last baked.</summary>
        public float GlowMaxOf(int i) => ceilings[i].GlowMax;

        /// <summary>The room lights whose pools ceiling <paramref name="i"/> bounces.</summary>
        public int SourcesOf(int i) => ceilings[i].Sources.Count;

        /// <summary>The rule: a ceiling at <paramref name="height"/> shows to an eye at <paramref name="eyeY"/> only from below it.</summary>
        public static bool ShowsFrom(float eyeY, float height)
        {
            return eyeY < height - HideMargin; // MUTATION:CEILING_RULE
        }

        /// <summary>The ceilings of a built level (null without).</summary>
        public static RoomCeilings Of(LevelInstance level)
        {
            return level != null && level.Root != null ? level.Root.GetComponentInChildren<RoomCeilings>(true) : null;
        }

        /// <summary>Builds the ceilings of <paramref name="def"/> under <paramref name="levelRoot"/> (at the origin), all hidden until the first update.</summary>
        public static RoomCeilings Build(LevelDef def, Transform levelRoot)
        {
            if (Disabled || def == null)
            {
                return null;
            }
            List<RoomDef> rooms = def.AllRooms();
            if (rooms.Count == 0)
            {
                return null;
            }
            var go = new GameObject(RootName) { layer = 0 };
            go.transform.SetParent(levelRoot, false);
            RoomCeilings owner = go.AddComponent<RoomCeilings>();
            Material wall = WallArray.Material;
            owner.wallMaterial = wall != null;
            Material material = wall != null ? wall : PrimitiveKit.Lit(PaintColour, Smoothness);
            for (int i = 0; i < rooms.Count; i++)
            {
                owner.ceilings.Add(owner.BuildOne(rooms[i], i, material));
            }
            owner.CollectSources(def, levelRoot, rooms);
            owner.Rebake(true);
            return owner;
        }

        private Ceiling BuildOne(RoomDef room, int index, Material material)
        {
            float height = room.WallHeight > 0f ? room.WallHeight : 2.7f;
            int nx = Mathf.Max(1, Mathf.CeilToInt(room.SizeX / Cell - 1e-3f));
            int nz = Mathf.Max(1, Mathf.CeilToInt(room.SizeZ / Cell - 1e-3f));
            int count = (nx + 1) * (nz + 1);
            var vertices = new Vector3[count];
            var normals = new Vector3[count];
            var uv = new Vector2[count];
            var finish = new List<Vector4>(count);
            var paint = new List<Vector4>(count);
            var f = new Vector4(WallArray.FlatFinish, 0f, Smoothness, 0f);
            for (int z = 0; z <= nz; z++)
            {
                for (int x = 0; x <= nx; x++)
                {
                    int k = z * (nx + 1) + x;
                    float px = room.MinX + room.SizeX * x / nx;
                    float pz = room.MinZ + room.SizeZ * z / nz;
                    vertices[k] = new Vector3(px, height, pz);
                    normals[k] = Vector3.down;
                    uv[k] = new Vector2(px, pz);
                    finish.Add(f);
                    paint.Add(Vector4.zero);
                }
            }
            // Facing down: (v00, v10, v11) and (v00, v11, v01) run clockwise seen from below.
            var triangles = new int[nx * nz * 6];
            int t = 0;
            for (int z = 0; z < nz; z++)
            {
                for (int x = 0; x < nx; x++)
                {
                    int v00 = z * (nx + 1) + x;
                    int v10 = v00 + 1;
                    int v01 = v00 + nx + 1;
                    int v11 = v01 + 1;
                    triangles[t++] = v00;
                    triangles[t++] = v10;
                    triangles[t++] = v11;
                    triangles[t++] = v00;
                    triangles[t++] = v11;
                    triangles[t++] = v01;
                }
            }
            string name = "Ceiling " + (string.IsNullOrEmpty(room.Id) ? (index + 1).ToString() : room.Id);
            var mesh = new Mesh { name = name };
            mesh.MarkDynamic();
            mesh.vertices = vertices;
            mesh.normals = normals;
            mesh.uv = uv;
            mesh.SetUVs(WallArray.FinishChannel, finish);
            mesh.SetUVs(WallArray.BandChannel, paint);
            mesh.triangles = triangles;
            mesh.RecalculateBounds();

            var go = new GameObject(name) { layer = 0 };
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            MeshRenderer renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.Off; // MUTATION:CEILING_NO_SHADOW
            renderer.receiveShadows = false;
            renderer.lightProbeUsage = LightProbeUsage.Off;
            renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
            renderer.enabled = false;
            return new Ceiling { Room = room, Height = height, Renderer = renderer, Mesh = mesh, Vertices = vertices, Paint = paint };
        }

        /// <summary>
        /// The spots aimed down of the room lights and the lit zones, each with its floor pool, given to the ceiling of the
        /// room that holds it (a light outside every room is left out).
        /// </summary>
        private void CollectSources(LevelDef def, Transform levelRoot, List<RoomDef> rooms)
        {
            var lights = new List<Light>();
            foreach (string holder in new[] { RoomLights.RootName, LitZoneView.RootName })
            {
                Transform t = levelRoot.Find(holder);
                if (t != null)
                {
                    lights.AddRange(t.GetComponentsInChildren<Light>(true));
                }
            }
            foreach (Light l in lights)
            {
                if (l == null || l.type != LightType.Spot)
                {
                    continue;
                }
                Vector3 at = l.transform.position;
                Vector3 axis = l.transform.forward;
                if (axis.y > -0.2f)
                {
                    continue;
                }
                int room = -1;
                for (int i = 0; i < rooms.Count; i++)
                {
                    if (rooms[i].Contains(at))
                    {
                        room = i;
                        break;
                    }
                }
                if (room < 0)
                {
                    continue;
                }
                float floor = def.FloorHeightAt(at.x, at.z);
                float distance = Mathf.Max(0.3f, (at.y - floor) / -axis.y);
                Vector3 pool = at + axis * distance;
                pool.y = def.FloorHeightAt(pool.x, pool.z);
                ceilings[room].Sources.Add(new Source { Light = l, Pool = pool, Distance = distance });
            }
        }

        private static float Luminance(Color c) => 0.2126f * c.r + 0.7152f * c.g + 0.0722f * c.b;

        /// <summary>
        /// Rebakes the paint and the glow of every ceiling whose lights changed since the last bake (all of them with
        /// <paramref name="all"/>, or when the strength changed). No allocation once built.
        /// </summary>
        private void Rebake(bool all)
        {
            float strength = BounceOverride ?? BounceStrength;
            if (!Mathf.Approximately(strength, bakedStrength))
            {
                bakedStrength = strength;
                all = true;
            }
            // The sun (or the moon) on the floors: its light at the floor, in its colour; a new preset rebakes them all.
            Light sun = Main.Instance != null && Main.Instance.Sun != null ? Main.Instance.Sun : RenderSettings.sun;
            Color sunLight = Color.black;
            if (sun != null && sun.isActiveAndEnabled)
            {
                sunLight = sun.color.linear * (sun.intensity * Mathf.Max(0f, -sun.transform.forward.y) * (SunBounceOverride ?? SunBounce));
            }
            if (Mathf.Abs(Luminance(sunLight) - bakedSun) > 1e-3f)
            {
                bakedSun = Luminance(sunLight);
                all = true;
            }
            Color paint = PaintColour.linear;
            float paintLuma = Mathf.Max(1e-3f, Luminance(paint));
            foreach (Ceiling c in ceilings)
            {
                bool dirty = all;
                foreach (Source s in c.Sources)
                {
                    float now = s.Light != null && s.Light.isActiveAndEnabled ? s.Light.intensity : 0f;
                    if (Mathf.Abs(now - s.Seen) > 1e-3f)
                    {
                        s.Seen = now;
                        dirty = true;
                    }
                }
                if (!dirty)
                {
                    continue;
                }
                float glowMax = 0f;
                RoomDef r = c.Room;
                float half = Mathf.Max(0f, r.WallThickness) * 0.5f;
                for (int k = 0; k < c.Vertices.Length; k++)
                {
                    Vector3 v = c.Vertices[k];
                    float wall = Mathf.Max(0f, Mathf.Min(Mathf.Min(v.x - r.MinX, r.MaxX - v.x), Mathf.Min(v.z - r.MinZ, r.MaxZ - v.z)) - half);
                    Color bounce = sunLight * (1f - EdgeShade * (1f - Mathf.SmoothStep(0f, 1f, wall / EdgeReach)));
                    foreach (Source s in c.Sources)
                    {
                        if (s.Seen <= 0f)
                        {
                            continue;
                        }
                        float h = Mathf.Max(0.5f, v.y - s.Pool.y) * BounceSpread;
                        float dx = v.x - s.Pool.x;
                        float dz = v.z - s.Pool.z;
                        float form = h * h / (h * h + dx * dx + dz * dz);
                        float pool = s.Seen / (s.Distance * s.Distance);
                        bounce += s.Light.color.linear * (strength * pool * form * form);
                    }
                    float luma = Luminance(bounce);
                    if (luma > BounceMax)
                    {
                        bounce *= BounceMax / luma;
                        luma = BounceMax;
                    }
                    // The paint, tinted toward the light's own colour where the glow is strong (a bathroom's cool, a
                    // bedroom's amber), then the glow that gives that much light over it.
                    Color shown = paint;
                    if (luma > 1e-5f)
                    {
                        Color chroma = bounce / luma;
                        float share = GlowTint * Mathf.Clamp01(luma / (0.5f * BounceMax));
                        shown = new Color(paint.r * Mathf.Lerp(1f, chroma.r, share), paint.g * Mathf.Lerp(1f, chroma.g, share),
                            paint.b * Mathf.Lerp(1f, chroma.b, share));
                        shown *= paintLuma / Mathf.Max(1e-3f, Luminance(shown));
                    }
                    float glow = luma / Mathf.Max(1e-3f, Luminance(shown));
                    glowMax = Mathf.Max(glowMax, glow);
                    c.Paint[k] = new Vector4(shown.r, shown.g, shown.b, glow);
                }
                c.GlowMax = glowMax;
                c.Mesh.SetUVs(WallArray.BandChannel, c.Paint);
            }
        }

        private void LateUpdate()
        {
            Camera cam = View != null ? View : Camera.main;
            if (cam == null)
            {
                return;
            }
            Vector3 eye = cam.transform.position;
            float jump = Tuning.WallFadeSnapDistance;
            bool snap = !started || (eye - lastEye).sqrMagnitude > jump * jump;
            started = true;
            lastEye = eye;
            Step(eye, snap, Time.unscaledDeltaTime);
            Rebake(false);
            DrawFading(cam);
        }

        /// <summary>Applies the rule for an eye at <paramref name="eye"/> at once, no fade (tests and tools rendering by hand).</summary>
        public void Apply(Vector3 eye)
        {
            started = true;
            lastEye = eye;
            Step(eye, true, 0f);
            Rebake(false);
        }

        private void Step(Vector3 eye, bool snap, float dt)
        {
            float rate = dt / FadeSeconds;
            foreach (Ceiling c in ceilings)
            {
                float target = ShowsFrom(eye.y, c.Height) ? 1f : 0f;
                c.Level = snap ? target : Mathf.MoveTowards(c.Level, target, rate); // MUTATION:CEILING_FADE
                bool solid = c.Level >= 1f;
                if (c.Renderer != null && c.Renderer.enabled != solid)
                {
                    c.Renderer.enabled = solid;
                }
            }
        }

        /// <summary>The fading ceilings, see-through at their level, for this frame and <paramref name="cam"/> only.</summary>
        private void DrawFading(Camera cam)
        {
            foreach (Ceiling c in ceilings)
            {
                if (c.Level <= 1e-3f || c.Level >= 1f || c.Renderer == null)
                {
                    continue;
                }
                if (c.Ghost == null)
                {
                    c.Ghost = new MaterialPropertyBlock();
                    c.Ghost.SetFloat(ArrayFinishId, wallMaterial ? 1f : 0f);
                    c.Ghost.SetFloat(SmoothnessId, Smoothness);
                    c.Ghost.SetFloat(MetallicId, 0f);
                    c.Applied = -1f;
                }
                // Smoothstep: the copy eases in and out instead of starting and stopping at a constant rate.
                float alpha = Mathf.SmoothStep(0f, 1f, c.Level);
                if (c.Applied != alpha)
                {
                    c.Applied = alpha;
                    Color tint = wallMaterial ? Color.white : PaintColour;
                    c.Ghost.SetColor(BaseColorId, new Color(tint.r, tint.g, tint.b, alpha));
                }
                var parameters = new RenderParams(WallFader.GhostMaterial)
                {
                    layer = 0,
                    camera = cam,
                    shadowCastingMode = ShadowCastingMode.Off,
                    receiveShadows = false,
                    matProps = c.Ghost,
                };
                Graphics.RenderMesh(parameters, c.Mesh, 0, c.Renderer.localToWorldMatrix);
            }
        }

        private void OnDestroy()
        {
            foreach (Ceiling c in ceilings)
            {
                if (c.Mesh == null)
                {
                    continue;
                }
                if (Application.isPlaying)
                {
                    Destroy(c.Mesh);
                }
                else
                {
                    DestroyImmediate(c.Mesh);
                }
            }
            ceilings.Clear();
        }
    }
}
