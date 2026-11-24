using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>How the walls in the way get out of it (the Walls option, SaveOptions.Walls).</summary>
    public enum WallLook
    {
        /// <summary>The wall sinks to its low solid stub, its door frames and leaves with it; its baseboards stay standing.</summary>
        Lowered,
        /// <summary>The whole wall fades to the wall opacity option.</summary>
        SeeThrough,
        /// <summary>The stub stays solid and the wall above it fades to the wall opacity option.</summary>
        Both,
        /// <summary>The walls never change.</summary>
        None,
    }

    /// <summary>
    /// Dollhouse view through the walls (docs/CONTRACT_M2.md 6). M7 walls pass (product owner 2026-11-18 and 2026-11-19): a
    /// wall that stands between the camera and the player furniture gets out of the way as the Walls option says
    /// (<see cref="WallLook"/>): lowered to its stub (the default), see-through at the wall opacity option, both (the stub
    /// solid, the wall above it see-through) or not at all. The floor continues under every wall footprint and every wall
    /// keeps a low solid stub over it (LevelBuilder, <see cref="Tuning.WallStubHeight"/>, shown in the lowered and both
    /// modes, registered with <see cref="AddStub"/>), so no hole or garden ever shows where a wall stands.
    ///
    /// A fade unit is one wall line: its faces, its cap (with the closures that keep the junctions solid and, on an outer
    /// line, its outside faces), its door frames, its windows when it is shared, a shared line's baseboards. Every part of a
    /// unit is registered with the same rule, so they go and come back together (DOORFADE 2026-11-24: its door frames and
    /// leaves included, see <see cref="KeepDoor"/>):
    /// <list type="bullet">
    /// <item>a shared (two faced) line: out of the way when its centre plane separates the camera from the player
    /// (<see cref="Add(Renderer, Vector3, Vector3)"/>);</item>
    /// <item>an outer (one faced) line: out of the way whenever the camera is on its outer side (<see cref="AddOuter"/>),
    /// exactly when its single inward face is seen from behind and culled.</item>
    /// </list>
    /// Lowered, a shared wall's baseboards (<see cref="KeepStandingWhenLowered"/>) stay standing. DOORFADE (user
    /// 2026-11-24, replacing the M9 doors rule of 2026-11-19 where doors never moved): the door parts (<see cref="KeepDoor"/>:
    /// door frames, the decorative outer leaf, the door leaves) go with their wall in every look, so a frame passed by the
    /// player never stands between the camera and the player.
    ///
    /// A part out of the way goes ShadowsOnly: its collider stays, so the wall still blocks sight, the player and the
    /// NavMesh exactly as before, it keeps casting its shadow, so the lighting never changes with the camera, and it no
    /// longer marks the x-ray stencil. What shows of it is drawn each frame through Graphics.RenderMesh (no object, no
    /// allocation per frame): see-through, a copy with the one shared see-through material (<see cref="GhostMaterial"/>,
    /// URP Lit, alpha blended, back faces culled, no depth write, drawn just before the regular transparents so the vision
    /// cones and the markers show over it) and the part's own texture, colour and finish in a property block built once;
    /// lowered, while it sinks or rises, a copy squashed toward the floor with its own materials and property block.
    ///
    /// The change is smooth (<see cref="Tuning.WallFadeSeconds"/>): a part goes out of the way at once (its copy starts
    /// as it stood) and is drawn again itself only once its copy stands whole. A level start, a new target, a new option
    /// or a camera jump (<see cref="Tuning.WallFadeSnapDistance"/>) snaps instead; <see cref="Apply"/> always snaps (tests
    /// and tools, which draw with <see cref="DrawFaded"/>).
    ///
    /// M9 near walls (product owner 2026-11-19, docs/m9/FLOORS_WALLS.md section 8): in the see-through and both looks, an
    /// outer wall line between the camera and the house that covers more than <see cref="Tuning.NearWallEnterCoverage"/> of
    /// the screen (its quad clipped to the view) fades on to nothing, its cap and outside faces with it (the fixtures follow
    /// its level, its door parts vanish with it), and comes back to the opacity option under <see cref="Tuning.NearWallExitCoverage"/>;
    /// the stubs keep their look. Interior lines keep the opacity option.
    ///
    /// M5 wave 5A.1 (critique m15): an entry may also carry a box (a transform and its size, read at its current pose every
    /// frame), and then also gets out of the way while a sight line from the camera to the player furniture crosses that
    /// box (grown by Tuning.LeafFadeMargin). Only the door leaves carried one, and since the M9 doors rule they never move:
    /// the box rule no longer applies to any part.
    /// </summary>
    [DefaultExecutionOrder(300)] // after OrbitCamera (200), which moves in LateUpdate
    public sealed class WallFader : MonoBehaviour
    {
        private sealed class Entry
        {
            public Renderer Renderer;
            public MeshFilter Filter;
            public Vector3 Point;
            public Vector3 Normal;
            public ShadowCastingMode Shown;
            /// <summary>An outer wall: out of the way whenever the camera is on the back of <see cref="Normal"/> (inward).</summary>
            public bool Outer;
            /// <summary>Lowered, the plane rule leaves it standing (a door frame, a leaf, a baseboard).</summary>
            public bool KeepWhenLowered;
            /// <summary>A door leaf or a door frame: goes with its wall's plane only, never with the leaf box rule (DOORFADE).</summary>
            public bool Door;
            /// <summary>M5: the box whose current pose also moves the renderer out of the way (null: the plane rule only).</summary>
            public Transform Box;
            public Vector3 HalfSize;
            /// <summary>How much of the part stands: 1 standing (no copy), 0 fully out of the way (faded or lowered).</summary>
            public float Level = 1f;
            /// <summary>The see-through copy's property block (the part's own texture, colour and finish), built once.</summary>
            public MaterialPropertyBlock Ghost;
            public Color BaseColor;
            public float Applied = -1f;
            /// <summary>The part's own property block (its detail), read when a lowered transition starts.</summary>
            public MaterialPropertyBlock Own;
            public bool Moving;
            /// <summary>M9 near walls: the outer wall line this part goes with (<see cref="NearUnit"/>), or -1.</summary>
            public int Unit = -1;
            /// <summary>M9 near walls: 0 at the wall opacity option, 1 vanished (see-through and both looks only).</summary>
            public float Vanish;
        }

        /// <summary>
        /// M9 near walls: one outer wall line (every outer part on one plane) and the quad it covers (its centre plane, from
        /// floor to top, over its length), whose screen coverage decides whether it vanishes.
        /// </summary>
        private sealed class NearUnit
        {
            public Vector3 Point;
            public Vector3 Normal;
            public Bounds Bounds;
            public readonly Vector3[] Quad = new Vector3[4];
            public float Coverage;
            public bool Vanishing;
        }

        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapStId = Shader.PropertyToID("_BaseMap_ST");
        private static readonly int SmoothnessId = Shader.PropertyToID("_Smoothness");
        private static readonly int MetallicId = Shader.PropertyToID("_Metallic");
        private static readonly int ArrayFinishId = Shader.PropertyToID(WallArray.ArrayFinishProperty);
        private static readonly List<Material> SharedMaterials = new List<Material>(4);
        private static Material ghost;

        /// <summary>Tools rendering outside play mode: the look and the opacity (0 to 1) to use instead of the saved options.</summary>
        public static WallLook? LookOverride;
        public static float? OpacityOverride;

        /// <summary>The player furniture: the walls between it and the camera get out of the way.</summary>
        public Transform Target;

        /// <summary>
        /// M5: the player furniture whose sight points (its centre and top corners, as the probe's start view) end the sight
        /// lines of the box rule; null: the target's position only.
        /// </summary>
        public FurnitureController Furniture;

        private readonly Vector3[] points = new Vector3[Tuning.SampleCount];

        /// <summary>The camera to clear the view for; the main camera when null.</summary>
        public Camera View;

        private readonly List<Entry> entries = new List<Entry>();
        private readonly List<Renderer> stubs = new List<Renderer>();
        private readonly List<NearUnit> units = new List<NearUnit>();
        private bool unitsDirty;
        // The clipping buffers of the coverage (a quad clipped by the near plane and the four screen edges keeps at most 9
        // corners): no allocation per frame.
        private readonly Vector3[] clipA = new Vector3[16];
        private readonly Vector3[] clipB = new Vector3[16];
        private bool started;
        private Vector3 lastCamera;
        private Transform lastTarget;
        private WallLook look;
        private bool lookKnown;
        private float opacity = Tuning.WallOpacityDefault / 100f;

        public int Count => entries.Count;

        /// <summary>The look the last update used (the Walls option, or <see cref="LookOverride"/>).</summary>
        public WallLook Look => look;

        /// <summary>The Walls option as a <see cref="WallLook"/> (or <see cref="LookOverride"/>).</summary>
        public static WallLook CurrentLook
        {
            get
            {
                if (LookOverride.HasValue)
                {
                    return LookOverride.Value;
                }
                // Anything that is not a known look is the default, Both (SaveOptions.Clamped, product owner 2026-11-20).
                string walls = SaveStore.Options.Walls;
                return walls == SaveOptions.WallsLowered ? WallLook.Lowered
                    : walls == SaveOptions.WallsSeeThrough ? WallLook.SeeThrough
                    : walls == SaveOptions.WallsNone ? WallLook.None : WallLook.Both;
            }
        }

        /// <summary>The wall opacity option, 0 to 1 (or <see cref="OpacityOverride"/>).</summary>
        public static float CurrentOpacity => Mathf.Clamp01(OpacityOverride ?? SaveStore.Options.WallOpacity / 100f);

        /// <summary>
        /// The one see-through material every faded part is drawn with (alpha blended, back faces culled, no depth write,
        /// queue just before the regular transparents); each part brings its own texture, colour and opacity. Walls 4: the
        /// library's OutOfSight/Wall See-through (TextureLibrary.wallSeeThrough), lit as URP Lit, which also reads the wall
        /// finish arrays; a URP Lit one built here without it.
        /// </summary>
        public static Material GhostMaterial
        {
            get
            {
                // Walls 4 (WallArray, docs/m9/FLOORS_WALLS.md section 7): the library's see-through material, which draws a
                // wall of the one wall material from its finish arrays and any other part from its own 2D maps; the URP Lit
                // one below only without it (no library), when every part is a URP Lit one.
                Material shared = WallArray.SeeThrough;
                if (shared != null)
                {
                    return shared;
                }
                if (ghost != null)
                {
                    return ghost;
                }
                Shader shader = Shader.Find(PrimitiveKit.LitShaderName);
                if (shader == null)
                {
                    Debug.LogError("[WallFader] URP Lit shader not found (is it in Always Included Shaders?)");
                    shader = Shader.Find("Hidden/InternalErrorShader");
                }
                ghost = new Material(shader) { name = "Wall See-through" };
                ghost.SetFloat("_Surface", 1f);
                ghost.SetFloat("_Blend", 0f);
                ghost.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
                ghost.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
                ghost.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
                ghost.SetFloat("_DstBlendAlpha", (float)BlendMode.OneMinusSrcAlpha);
                ghost.SetFloat("_ZWrite", 0f);
                ghost.SetFloat("_Cull", (float)CullMode.Back);
                ghost.SetFloat("_SpecularHighlights", 1f);
                ghost.SetFloat("_EnvironmentReflections", 1f);
                ghost.SetOverrideTag("RenderType", "Transparent");
                ghost.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
                ghost.EnableKeyword("_NORMALMAP");
                ghost.SetShaderPassEnabled("ShadowCaster", false);
                ghost.SetShaderPassEnabled("DepthOnly", false);
                ghost.SetShaderPassEnabled("DepthNormals", false);
                ghost.renderQueue = (int)RenderQueue.Transparent - 1;
                ghost.hideFlags = HideFlags.DontUnloadUnusedAsset;
                return ghost;
            }
        }

        /// <summary>True while at least one part is drawn see-through.</summary>
        public bool AnyFaded { get; private set; }

        /// <summary>
        /// Raised after every update of the parts' levels (each frame, and by <see cref="Apply"/>): what follows a wall line
        /// without being one of its parts reads <see cref="LevelOf"/> then (RoomLights' wall fixtures).
        /// </summary>
        public event System.Action Stepped;

        /// <summary>
        /// Wave 5B (tests): the fade plane a renderer is registered with (its first entry); false when it never fades. For an
        /// outer wall the normal is its inward one (<see cref="IsOuter"/>).
        /// </summary>
        public bool PlaneOf(Renderer renderer, out Vector3 point, out Vector3 normal)
        {
            Entry e = Find(renderer);
            point = e != null ? e.Point : default;
            normal = e != null ? e.Normal : default;
            return e != null;
        }

        /// <summary>True when <paramref name="renderer"/> is registered with the outer wall rule (tests).</summary>
        public bool IsOuter(Renderer renderer) => Find(renderer)?.Outer ?? false;

        /// <summary>True when <paramref name="renderer"/> stays standing in the lowered look (tests).</summary>
        public bool KeepsStandingWhenLowered(Renderer renderer) => Find(renderer)?.KeepWhenLowered ?? false;

        /// <summary>Tests: true when <paramref name="renderer"/> is a door part (a leaf or a frame), which goes with its wall only.</summary>
        public bool IsDoor(Renderer renderer) => Find(renderer)?.Door ?? false;

        /// <summary>
        /// How much of a registered part stands (1 standing, 0 out of the way), or -1 when it never moves (tests). M9 near
        /// walls: a part coming back from vanished stands only once fully back.
        /// </summary>
        public float LevelOf(Renderer renderer)
        {
            Entry e = Find(renderer);
            return e != null ? Mathf.Min(e.Level, 1f - e.Vanish) : -1f;
        }

        /// <summary>
        /// M9 near walls (tests): the screen fraction (0 to 1) the outer wall line of <paramref name="renderer"/> covered on
        /// the last update while it stood between the camera and the house (0 otherwise), or -1 when the part goes with no
        /// outer wall line.
        /// </summary>
        public float CoverageOf(Renderer renderer)
        {
            Entry e = Find(renderer);
            return e != null && e.Unit >= 0 && e.Unit < units.Count ? units[e.Unit].Coverage : -1f;
        }

        /// <summary>M9 near walls (tests): true when the outer wall line of <paramref name="renderer"/> is vanishing.</summary>
        public bool VanishingOf(Renderer renderer)
        {
            Entry e = Find(renderer);
            return e != null && e.Unit >= 0 && e.Unit < units.Count && units[e.Unit].Vanishing;
        }

        /// <summary>
        /// The opacity a registered part shows at (tests): see-through or both, its copy's (the wall opacity option once
        /// faded, 0 once a near outer wall vanished); otherwise 1 standing and 0 lowered. -1 when it never moves.
        /// </summary>
        public float AlphaOf(Renderer renderer)
        {
            Entry e = Find(renderer);
            if (e == null)
            {
                return -1f;
            }
            if (look == WallLook.SeeThrough || look == WallLook.Both)
            {
                return GhostAlpha(e);
            }
            return e.Level >= 1f ? 1f : 0f;
        }

        /// <summary>The stub renderers (shown in the lowered and both looks).</summary>
        public IReadOnlyList<Renderer> Stubs => stubs;

        /// <summary>Number of parts out of the way on the last update (probe and tests).</summary>
        public int HiddenCount { get; private set; }

        /// <summary>Number of parts going or coming back on the last update (0: every part is standing or out of the way).</summary>
        public int Moving { get; private set; }

        private Entry Find(Renderer renderer)
        {
            foreach (Entry e in entries)
            {
                if (e.Renderer == renderer)
                {
                    return e;
                }
            }
            return null;
        }

        /// <summary>Registers a part of a shared wall: out of the way when the plane (point, normal) separates camera and target.</summary>
        public void Add(Renderer renderer, Vector3 point, Vector3 normal)
        {
            Register(renderer, point, normal, false, null, Vector3.zero);
        }

        /// <summary>
        /// Registers a part of an outer wall whose inward normal is <paramref name="inward"/>: out of the way whenever the
        /// camera is on the outer side of the plane (point, inward), where the wall's single inward face is seen from behind.
        /// </summary>
        public void AddOuter(Renderer renderer, Vector3 point, Vector3 inward)
        {
            Register(renderer, point, inward, true, null, Vector3.zero);
        }

        /// <summary>
        /// M5: registers a door leaf with its wall's plane (point, normal) and its box (<paramref name="box"/> at its current
        /// pose, <paramref name="size"/> in its local axes). A leaf is a door part (<see cref="KeepDoor"/>): it goes with its
        /// wall's plane only (DOORFADE), its box never moves it.
        /// </summary>
        public void Add(Renderer renderer, Vector3 point, Vector3 normal, Transform box, Vector3 size)
        {
            Register(renderer, point, normal, false, box, size * 0.5f + Vector3.one * Tuning.LeafFadeMargin);
            KeepDoor(renderer);
        }

        /// <summary>
        /// Marks a registered part as a door part (a leaf, a door frame, the decorative outer leaf). DOORFADE (user,
        /// 2026-11-24, replaces the M9 doors rule): a door part goes out of the way exactly as its wall does (its plane, the
        /// look, the timing, near outer walls included), so a frame never stands in the foreground once the player is past
        /// its doorway; it only never uses the leaf box rule.
        /// </summary>
        public void KeepDoor(Renderer renderer)
        {
            Entry e = Find(renderer);
            if (e != null)
            {
                e.Door = true;
            }
        }

        /// <summary>Lowered, the plane rule leaves a registered part standing (door frames, baseboards: the doorways read).</summary>
        public void KeepStandingWhenLowered(Renderer renderer)
        {
            Entry e = Find(renderer);
            if (e != null)
            {
                e.KeepWhenLowered = true;
            }
        }

        /// <summary>Registers a stub renderer: drawn in the lowered and both looks only.</summary>
        public void AddStub(Renderer renderer)
        {
            if (renderer != null)
            {
                stubs.Add(renderer);
                renderer.enabled = !lookKnown || look == WallLook.Lowered || look == WallLook.Both;
            }
        }

        private void Register(Renderer renderer, Vector3 point, Vector3 normal, bool outer, Transform box, Vector3 half)
        {
            if (renderer == null)
            {
                return;
            }
            entries.Add(new Entry
            {
                Renderer = renderer,
                Filter = renderer.GetComponent<MeshFilter>(),
                Point = point,
                Normal = normal.normalized,
                Shown = renderer.shadowCastingMode,
                Outer = outer,
                Box = box,
                HalfSize = half,
            });
            unitsDirty = true;
        }

        /// <summary>
        /// M9 near walls: groups the outer parts by their plane into wall lines, each with the quad it covers (its centre
        /// plane over the union of its parts' bounds), and attaches to a line the door leaves standing in its plane, so they
        /// vanish with it. Once after the level is built (the walls never move), never per frame.
        /// </summary>
        private void BuildUnits()
        {
            unitsDirty = false;
            units.Clear();
            for (int i = 0; i < entries.Count; i++)
            {
                Entry e = entries[i];
                e.Unit = -1;
                if (!e.Outer || e.Renderer == null)
                {
                    continue;
                }
                int found = FindUnit(e.Point, e.Normal, true);
                if (found < 0)
                {
                    units.Add(new NearUnit { Point = e.Point, Normal = e.Normal, Bounds = e.Renderer.bounds });
                    found = units.Count - 1;
                }
                else
                {
                    units[found].Bounds.Encapsulate(e.Renderer.bounds);
                }
                e.Unit = found;
            }
            for (int u = 0; u < units.Count; u++)
            {
                NearUnit unit = units[u];
                Vector3 along = Vector3.Cross(Vector3.up, unit.Normal).normalized;
                Vector3 c = unit.Bounds.center;
                Vector3 x = unit.Bounds.extents;
                float reach = Mathf.Abs(along.x) * x.x + Mathf.Abs(along.y) * x.y + Mathf.Abs(along.z) * x.z;
                float mid = Vector3.Dot(c, along);
                // The quad in the line's centre plane: the plane's point moved along the line to each end, at the floor and
                // the top of the line's parts.
                Vector3 o = unit.Point - along * Vector3.Dot(unit.Point, along);
                float bottom = unit.Bounds.min.y - o.y;
                float top = unit.Bounds.max.y - o.y;
                unit.Quad[0] = o + along * (mid - reach) + Vector3.up * bottom;
                unit.Quad[1] = o + along * (mid + reach) + Vector3.up * bottom;
                unit.Quad[2] = o + along * (mid + reach) + Vector3.up * top;
                unit.Quad[3] = o + along * (mid - reach) + Vector3.up * top;
            }
            for (int i = 0; i < entries.Count; i++)
            {
                Entry e = entries[i];
                if (e.Outer || e.Box == null)
                {
                    continue;
                }
                // A real door leaf of an outer doorway: registered with the plane rule, it stands in the line's plane.
                int found = FindUnit(e.Point, e.Normal, false);
                if (found >= 0)
                {
                    NearUnit unit = units[found];
                    Vector3 along = Vector3.Cross(Vector3.up, unit.Normal).normalized;
                    float a = Vector3.Dot(e.Point, along);
                    float from = Vector3.Dot(unit.Quad[0], along);
                    float to = Vector3.Dot(unit.Quad[1], along);
                    if (a >= Mathf.Min(from, to) - 0.01f && a <= Mathf.Max(from, to) + 0.01f)
                    {
                        e.Unit = found;
                    }
                }
            }
        }

        /// <summary>The outer wall line on the plane (point, normal), either facing when <paramref name="sameFacing"/> is false; -1 when none.</summary>
        private int FindUnit(Vector3 point, Vector3 normal, bool sameFacing)
        {
            for (int u = 0; u < units.Count; u++)
            {
                NearUnit unit = units[u];
                float d = Vector3.Dot(normal, unit.Normal);
                bool parallel = sameFacing ? d > 0.999f : Mathf.Abs(d) > 0.999f;
                if (parallel && Mathf.Abs(Vector3.Dot(point - unit.Point, unit.Normal)) < 0.02f)
                {
                    return u;
                }
            }
            return -1;
        }

        /// <summary>
        /// M9 near walls: the fraction of the screen (0 to 1) a unit's quad covers for a camera at <paramref name="eye"/>
        /// with the rotation and lens of <paramref name="cam"/>: the quad clipped by the near plane, projected, clipped to
        /// the viewport, its area. No allocation.
        /// </summary>
        private float Coverage(NearUnit unit, Vector3 eye, Camera cam)
        {
            Quaternion inverse = Quaternion.Inverse(cam.transform.rotation);
            float near = Mathf.Max(1e-3f, cam.nearClipPlane);
            int n = 0;
            // The near plane, in camera space (z forward).
            for (int i = 0; i < 4; i++)
            {
                Vector3 a = inverse * (unit.Quad[i] - eye);
                Vector3 b = inverse * (unit.Quad[(i + 1) & 3] - eye);
                bool aIn = a.z >= near;
                bool bIn = b.z >= near;
                if (aIn)
                {
                    clipA[n++] = a;
                }
                if (aIn != bIn)
                {
                    clipA[n++] = Vector3.Lerp(a, b, (near - a.z) / (b.z - a.z));
                }
            }
            if (n < 3)
            {
                return 0f;
            }
            // Projected to the viewport (x, y in 0..1 on screen).
            float tanY = Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad);
            float aspect = Mathf.Max(1e-3f, cam.aspect);
            for (int i = 0; i < n; i++)
            {
                Vector3 p = clipA[i];
                if (cam.orthographic)
                {
                    float size = Mathf.Max(1e-3f, cam.orthographicSize);
                    clipA[i] = new Vector3(0.5f + 0.5f * p.x / (size * aspect), 0.5f + 0.5f * p.y / size, 0f);
                }
                else
                {
                    clipA[i] = new Vector3(0.5f + 0.5f * p.x / (p.z * tanY * aspect), 0.5f + 0.5f * p.y / (p.z * tanY), 0f);
                }
            }
            // The four screen edges.
            n = ClipEdge(clipA, n, clipB, 0, 0f, true);
            n = ClipEdge(clipB, n, clipA, 0, 1f, false);
            n = ClipEdge(clipA, n, clipB, 1, 0f, true);
            n = ClipEdge(clipB, n, clipA, 1, 1f, false);
            float area = 0f;
            for (int i = 0; i < n; i++)
            {
                Vector3 a = clipA[i];
                Vector3 b = clipA[(i + 1) % n];
                area += a.x * b.y - b.x * a.y;
            }
            return Mathf.Clamp01(Mathf.Abs(area) * 0.5f);
        }

        /// <summary>One Sutherland-Hodgman pass: keeps the side of axis <paramref name="k"/> at or above (or below) <paramref name="limit"/>.</summary>
        private static int ClipEdge(Vector3[] from, int count, Vector3[] to, int k, float limit, bool above)
        {
            int n = 0;
            for (int i = 0; i < count && n < to.Length - 1; i++)
            {
                Vector3 a = from[i];
                Vector3 b = from[(i + 1) % count];
                bool aIn = above ? a[k] >= limit : a[k] <= limit;
                bool bIn = above ? b[k] >= limit : b[k] <= limit;
                if (aIn)
                {
                    to[n++] = a;
                }
                if (aIn != bIn)
                {
                    to[n++] = Vector3.Lerp(a, b, (limit - a[k]) / (b[k] - a[k]));
                }
            }
            return n;
        }

        /// <summary>
        /// M9 near walls: in the see-through and both looks, each outer wall line the camera stands outside of (between it and
        /// the house) vanishes once it covers more than <see cref="Tuning.NearWallEnterCoverage"/> of the screen, and comes
        /// back to the opacity option under <see cref="Tuning.NearWallExitCoverage"/> (hysteresis).
        /// </summary>
        private void UpdateUnits(Vector3 camera, bool seeThrough)
        {
            if (unitsDirty)
            {
                BuildUnits();
            }
            Camera cam = seeThrough && units.Count > 0 ? (View != null ? View : Camera.main) : null;
            for (int u = 0; u < units.Count; u++)
            {
                NearUnit unit = units[u];
                if (cam == null || Vector3.Dot(camera - unit.Point, unit.Normal) >= 0f)
                {
                    unit.Coverage = 0f;
                    unit.Vanishing = false;
                    continue;
                }
                unit.Coverage = Coverage(unit, camera, cam);
                float limit = unit.Vanishing ? Tuning.NearWallExitCoverage : Tuning.NearWallEnterCoverage; // MUTATION:NEAR_WALL_HYSTERESIS
                unit.Vanishing = unit.Coverage > limit; // MUTATION:NEAR_WALL_VANISH
            }
        }

        /// <summary>The see-through copy's opacity: the opacity option once faded, nothing once a near outer wall vanished.</summary>
        private float GhostAlpha(Entry e) => Mathf.Lerp(opacity, 1f, e.Level) * (1f - e.Vanish);

        /// <summary>Applies the rule for a camera position at once, no transition (also callable from tests and tools).</summary>
        public void Apply(Vector3 camera)
        {
            Step(camera, true, 0f);
        }

        /// <summary>
        /// The look and the rule for every part, then its level: snapped, or moved toward its target by <paramref name="dt"/>
        /// over <see cref="Tuning.WallFadeSeconds"/>. A part is drawn itself only while it fully stands.
        /// </summary>
        private void Step(Vector3 camera, bool snap, float dt)
        {
            WallLook wanted = CurrentLook;
            opacity = CurrentOpacity;
            if (!lookKnown || wanted != look)
            {
                look = wanted;
                lookKnown = true;
                snap = true;
                bool stub = look == WallLook.Lowered || look == WallLook.Both;
                foreach (Renderer r in stubs)
                {
                    if (r != null && r.enabled != stub)
                    {
                        r.enabled = stub;
                    }
                }
            }
            HiddenCount = 0;
            Moving = 0;
            AnyFaded = false;
            if (Target == null)
            {
                return;
            }
            Vector3 player = Target.position;
            int count = 1;
            if (Furniture != null)
            {
                Furniture.GetSamplePoints(points);
                count = points.Length;
            }
            else
            {
                points[0] = player;
            }
            bool none = look == WallLook.None;
            bool lowered = look == WallLook.Lowered;
            bool seeThrough = look == WallLook.SeeThrough || look == WallLook.Both;
            float rate = dt / Mathf.Max(1e-3f, Tuning.WallFadeSeconds);
            float vanishRate = dt / Mathf.Max(1e-3f, Tuning.NearWallVanishSeconds);
            UpdateUnits(camera, seeThrough);
            for (int i = 0; i < entries.Count; i++)
            {
                Entry e = entries[i];
                if (e.Renderer == null)
                {
                    continue;
                }
                float side = Vector3.Dot(camera - e.Point, e.Normal);
                bool plane = e.Outer ? side < 0f : side * Vector3.Dot(player - e.Point, e.Normal) < 0f;
                // DOORFADE (2026-11-24): a door part (frame, leaf) goes exactly as its wall does, same plane, look and
                // timing: once the player is past a doorway, its frame no longer stands in the foreground.
                bool hidden = !none && plane && !(lowered && e.KeepWhenLowered); // MUTATION:WALLS_KEEP_FRAMES
                // A door part never uses the leaf box rule: only its wall's plane moves it (no flicker as a leaf swings).
                if (!none && !hidden && !e.Door && e.Box != null) // MUTATION:DOORS_NO_BOX
                {
                    bool crossed = CrossesBox(camera, points, count, e.Box, e.HalfSize); // MUTATION:LEAF_FADE
                    hidden = crossed;
                }
                float target = hidden ? 0f : 1f;
                e.Level = snap ? target : Mathf.MoveTowards(e.Level, target, rate);
                // M9 near walls: a part of an outer line that covers too much of the screen goes on to nothing, smoothly.
                bool vanish = hidden && seeThrough && e.Unit >= 0 && units[e.Unit].Vanishing;
                float vanishTarget = vanish ? 1f : 0f;
                e.Vanish = snap ? vanishTarget : Mathf.MoveTowards(e.Vanish, vanishTarget, vanishRate);
                bool standing = !hidden && e.Level >= 1f && e.Vanish <= 0f;
                ShadowCastingMode mode = standing ? e.Shown : ShadowCastingMode.ShadowsOnly;
                if (e.Renderer.shadowCastingMode != mode)
                {
                    e.Renderer.shadowCastingMode = mode;
                }
                if (hidden)
                {
                    HiddenCount++;
                }
                bool moving = e.Level > 0f && e.Level < 1f;
                if (moving || (e.Vanish > 0f && e.Vanish < 1f))
                {
                    Moving++;
                }
                if (!moving)
                {
                    e.Moving = false;
                }
                AnyFaded |= seeThrough && !standing;
            }
            Stepped?.Invoke();
        }

        /// <summary>
        /// Draws what shows of every part that does not fully stand, for this frame (every camera, or only
        /// <paramref name="only"/>): see-through, its copy at its opacity; lowered, its copy squashed toward the floor while
        /// it sinks or rises. LateUpdate calls it; a tool rendering a camera by hand calls it after <see cref="Apply"/>.
        /// </summary>
        public void DrawFaded(Camera only = null)
        {
            if (look == WallLook.None)
            {
                return;
            }
            bool seeThrough = look == WallLook.SeeThrough || look == WallLook.Both;
            for (int i = 0; i < entries.Count; i++)
            {
                Entry e = entries[i];
                Renderer r = e.Renderer;
                if (r == null || (e.Level >= 1f && e.Vanish <= 0f) || !r.enabled || !r.gameObject.activeInHierarchy)
                {
                    continue;
                }
                Mesh mesh = e.Filter != null ? e.Filter.sharedMesh : null;
                if (mesh == null)
                {
                    continue;
                }
                if (seeThrough)
                {
                    DrawGhost(e, r, mesh, only);
                }
                else if (e.Level > 0f)
                {
                    DrawSinking(e, r, mesh, only);
                }
            }
        }

        private void DrawGhost(Entry e, Renderer r, Mesh mesh, Camera only)
        {
            if (e.Ghost == null)
            {
                PrepareGhost(e);
            }
            float alpha = GhostAlpha(e);
            if (alpha <= 1e-3f)
            {
                return; // M9 near walls: a vanished part draws nothing (no blended fill on a phone).
            }
            if (e.Applied != alpha)
            {
                e.Applied = alpha;
                Color c = e.BaseColor;
                e.Ghost.SetColor(BaseColorId, new Color(c.r, c.g, c.b, c.a * alpha));
            }
            var parameters = new RenderParams(GhostMaterial)
            {
                layer = 0,
                camera = only,
                shadowCastingMode = ShadowCastingMode.Off,
                receiveShadows = true,
                matProps = e.Ghost,
            };
            Matrix4x4 matrix = r.localToWorldMatrix;
            for (int sub = 0; sub < mesh.subMeshCount; sub++)
            {
                Graphics.RenderMesh(parameters, mesh, sub, matrix);
            }
        }

        /// <summary>
        /// The lowered copy: the part's mesh squashed toward the level floor to its standing fraction, with its own materials
        /// and property block, no shadow (the part itself, ShadowsOnly, keeps casting the whole wall's).
        /// </summary>
        private void DrawSinking(Entry e, Renderer r, Mesh mesh, Camera only)
        {
            if (e.Own == null)
            {
                e.Own = new MaterialPropertyBlock();
                e.Moving = false;
            }
            if (!e.Moving)
            {
                e.Moving = true;
                r.GetPropertyBlock(e.Own, 0);
                if (e.Own.isEmpty)
                {
                    r.GetPropertyBlock(e.Own);
                }
            }
            float s = Mathf.Max(0.01f, Mathf.SmoothStep(0f, 1f, e.Level));
            float floor = transform.position.y;
            Matrix4x4 squash = Matrix4x4.TRS(new Vector3(0f, floor * (1f - s), 0f), Quaternion.identity, new Vector3(1f, s, 1f));
            Matrix4x4 matrix = squash * r.localToWorldMatrix;
            r.GetSharedMaterials(SharedMaterials);
            int subMeshes = Mathf.Min(mesh.subMeshCount, SharedMaterials.Count);
            for (int sub = 0; sub < subMeshes; sub++)
            {
                Material material = SharedMaterials[sub];
                if (material == null)
                {
                    continue;
                }
                var parameters = new RenderParams(material)
                {
                    layer = r.gameObject.layer,
                    camera = only,
                    shadowCastingMode = ShadowCastingMode.Off,
                    receiveShadows = r.receiveShadows,
                    matProps = sub == 0 && !e.Own.isEmpty ? e.Own : null,
                };
                Graphics.RenderMesh(parameters, mesh, sub, matrix);
            }
        }

        /// <summary>
        /// The see-through copy's property block, once per part: its own detail (base map and tiling, normal map) as its
        /// property block shows it, else its material's base map, and its material's colour, smoothness and metallic.
        /// </summary>
        private static void PrepareGhost(Entry e)
        {
            Renderer r = e.Renderer;
            var block = new MaterialPropertyBlock();
            r.GetPropertyBlock(block, 0);
            if (block.isEmpty)
            {
                r.GetPropertyBlock(block);
            }
            Material own = r.sharedMaterial;
            // Walls 4 (WallArray): a part of the wall material shows the finish arrays (its vertices name the finish); any
            // other part its own 2D maps, set below.
            block.SetFloat(ArrayFinishId, WallArray.IsWallMaterial(own) ? 1f : 0f);
            if (own != null)
            {
                if (!block.HasTexture(BaseMapId) && own.HasProperty(BaseMapId) && own.GetTexture(BaseMapId) != null)
                {
                    block.SetTexture(BaseMapId, own.GetTexture(BaseMapId));
                    block.SetVector(BaseMapStId, own.GetVector(BaseMapStId));
                }
                block.SetFloat(SmoothnessId, own.HasProperty(SmoothnessId) ? own.GetFloat(SmoothnessId) : 0.1f);
                block.SetFloat(MetallicId, own.HasProperty(MetallicId) ? own.GetFloat(MetallicId) : 0f);
                // Window picture (2026-11-19): a window shows its picture's neutral colour, not the pane material's blue.
                e.BaseColor = WindowImage.Shows(block) ? WindowImage.Colour
                    : own.HasProperty(BaseColorId) ? own.GetColor(BaseColorId) : Color.white;
            }
            else
            {
                e.BaseColor = Color.white;
            }
            e.Ghost = block;
            e.Applied = -1f;
        }

        /// <summary>True when a segment from <paramref name="from"/> to one of the first <paramref name="count"/> points crosses the box.</summary>
        private static bool CrossesBox(Vector3 from, Vector3[] to, int count, Transform box, Vector3 half)
        {
            Quaternion inverse = Quaternion.Inverse(box.rotation);
            Vector3 origin = inverse * (from - box.position);
            for (int i = 0; i < count; i++)
            {
                if (SegmentHitsBox(origin, inverse * (to[i] - from), half))
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// Slab test: the segment origin + t * delta, t in [0, 1], meets the axis aligned box of half sizes
        /// <paramref name="half"/> centred on the origin of the local frame.
        /// </summary>
        public static bool SegmentHitsBox(Vector3 origin, Vector3 delta, Vector3 half)
        {
            float enter = 0f;
            float exit = 1f;
            for (int k = 0; k < 3; k++)
            {
                float o = origin[k];
                float d = delta[k];
                float h = half[k];
                if (Mathf.Abs(d) < 1e-8f)
                {
                    if (o < -h || o > h)
                    {
                        return false;
                    }
                    continue;
                }
                float a = (-h - o) / d;
                float b = (h - o) / d;
                if (a > b)
                {
                    (a, b) = (b, a);
                }
                enter = Mathf.Max(enter, a);
                exit = Mathf.Min(exit, b);
                if (enter > exit)
                {
                    return false;
                }
            }
            return true;
        }

        private void LateUpdate()
        {
            if (entries.Count == 0)
            {
                return;
            }
            Camera cam = View != null ? View : Camera.main;
            if (cam == null)
            {
                return;
            }
            Vector3 at = cam.transform.position;
            float jump = Tuning.WallFadeSnapDistance;
            // A level start, a new target (the title tour) or a camera jump (SetView, a restart) snaps: nothing to animate.
            bool snap = !started || Target != lastTarget || (at - lastCamera).sqrMagnitude > jump * jump;
            started = true;
            lastCamera = at;
            lastTarget = Target;
            Step(at, snap, Mathf.Min(Time.unscaledDeltaTime, 0.1f));
            DrawFaded();
        }
    }
}
