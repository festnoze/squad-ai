using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight
{
    /// <summary>
    /// Dollhouse view through the walls (docs/CONTRACT_M2.md 6), as see-through walls (M7 walls pass, product owner
    /// 2026-11-18 and 2026-11-19): a wall that stands between the camera and the player furniture fades to a light opacity
    /// (<see cref="Tuning.WallFadeAlpha"/>), so the room shows through it while the whole wall, its doorways and its
    /// junctions stay readable. The floor continues under every wall footprint (LevelBuilder), so a faded wall never shows
    /// the garden through it.
    ///
    /// A fade unit is one wall line: its faces, its cap (with the closures that keep the junctions solid and, on an outer
    /// line, its outside faces), its door frames, its windows when it is shared. Every part of a unit is registered with the
    /// same rule, so they fade and come back together:
    /// <list type="bullet">
    /// <item>a shared (two faced) line: faded when its centre plane separates the camera from the player (<see cref="Add(Renderer, Vector3, Vector3)"/>);</item>
    /// <item>an outer (one faced) line: faded whenever the camera is on its outer side (<see cref="AddOuter"/>), exactly when its
    /// single inward face is seen from behind and culled, so its cap and its door frames never stay solid over a wall the
    /// camera sees through.</item>
    /// </list>
    /// A faded part goes ShadowsOnly: its collider stays, so the wall still blocks sight, the player and the NavMesh exactly
    /// as before, it keeps casting its shadow, so the lighting never changes with the camera, and it no longer marks the
    /// x-ray stencil (an inhabitant behind it is seen through it, never as a silhouette on top). Its translucent look is a
    /// copy drawn each frame through Graphics.RenderMesh with the one shared see-through material (<see cref="GhostMaterial"/>,
    /// URP Lit, alpha blended, back faces culled, no depth write, drawn just before the regular transparents so the vision
    /// cones and the markers always show over it) and the part's own texture, colour and finish in a property block built
    /// once per part: no object, no allocation per frame, the same draws as a standing wall (its shadow and one colour draw).
    ///
    /// The change is smooth: the copy's opacity moves between 1 and <see cref="Tuning.WallFadeAlpha"/> over
    /// <see cref="Tuning.WallFadeSeconds"/>; a part fades at once (its copy starts opaque) and is drawn again only once its
    /// copy is opaque. A level start, a new target or a camera jump (<see cref="Tuning.WallFadeSnapDistance"/>) snaps
    /// instead; <see cref="Apply"/> always snaps (tests and tools, which draw with <see cref="DrawFaded"/>).
    ///
    /// M5 wave 5A.1 (critique m15): an entry may also carry a box (a transform and its size, read at its current pose every
    /// frame), and then also fades while a sight line from the camera to the player furniture crosses that box (grown by
    /// Tuning.LeafFadeMargin). A door leaf uses it: open in the player's room, it never hides the furniture.
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
            /// <summary>An outer wall: faded whenever the camera is on the back of <see cref="Normal"/> (its inward normal).</summary>
            public bool Outer;
            /// <summary>M5: the box whose current pose also fades the renderer (null: the plane rule only).</summary>
            public Transform Box;
            public Vector3 HalfSize;
            /// <summary>The copy's opacity: 1 standing (no copy drawn), <see cref="Tuning.WallFadeAlpha"/> faded.</summary>
            public float Alpha = 1f;
            /// <summary>The part's own texture, colour and finish for the see-through copy, built on its first fade.</summary>
            public MaterialPropertyBlock Block;
            public Color BaseColor;
            public float Applied = -1f;
        }

        private static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        private static readonly int BaseMapId = Shader.PropertyToID("_BaseMap");
        private static readonly int BaseMapStId = Shader.PropertyToID("_BaseMap_ST");
        private static readonly int SmoothnessId = Shader.PropertyToID("_Smoothness");
        private static readonly int MetallicId = Shader.PropertyToID("_Metallic");
        private static Material ghost;

        /// <summary>The player furniture: the walls between it and the camera fade.</summary>
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
        private bool started;
        private Vector3 lastCamera;
        private Transform lastTarget;

        public int Count => entries.Count;

        /// <summary>
        /// The one see-through material every faded part is drawn with (URP Lit, alpha blended, back faces culled, no depth
        /// write, queue just before the regular transparents); each part brings its own texture, colour and opacity.
        /// </summary>
        public static Material GhostMaterial
        {
            get
            {
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

        /// <summary>True while at least one part is drawn see-through (the probe counts <see cref="GhostMaterial"/> then).</summary>
        public bool AnyFaded { get; private set; }

        /// <summary>
        /// Wave 5B (tests): the fade plane a renderer is registered with (its first entry); false when it never fades. For an
        /// outer wall the normal is its inward one (<see cref="IsOuter"/>).
        /// </summary>
        public bool PlaneOf(Renderer renderer, out Vector3 point, out Vector3 normal)
        {
            foreach (Entry e in entries)
            {
                if (e.Renderer == renderer)
                {
                    point = e.Point;
                    normal = e.Normal;
                    return true;
                }
            }
            point = default;
            normal = default;
            return false;
        }

        /// <summary>True when <paramref name="renderer"/> is registered with the outer wall rule (tests).</summary>
        public bool IsOuter(Renderer renderer)
        {
            foreach (Entry e in entries)
            {
                if (e.Renderer == renderer)
                {
                    return e.Outer;
                }
            }
            return false;
        }

        /// <summary>The opacity a registered part is drawn at (1 standing), or -1 when it never fades (tests).</summary>
        public float AlphaOf(Renderer renderer)
        {
            foreach (Entry e in entries)
            {
                if (e.Renderer == renderer)
                {
                    return e.Alpha;
                }
            }
            return -1f;
        }

        /// <summary>Number of parts faded on the last update (probe and tests).</summary>
        public int HiddenCount { get; private set; }

        /// <summary>Number of parts fading or coming back on the last update (0: every part is standing or faded).</summary>
        public int Moving { get; private set; }

        /// <summary>Registers a part of a shared wall: faded when the plane (point, normal) separates camera and target.</summary>
        public void Add(Renderer renderer, Vector3 point, Vector3 normal)
        {
            Register(renderer, point, normal, false, null, Vector3.zero);
        }

        /// <summary>
        /// Registers a part of an outer wall whose inward normal is <paramref name="inward"/>: faded whenever the camera is on
        /// the outer side of the plane (point, inward), where the wall's single inward face is seen from behind.
        /// </summary>
        public void AddOuter(Renderer renderer, Vector3 point, Vector3 inward)
        {
            Register(renderer, point, inward, true, null, Vector3.zero);
        }

        /// <summary>
        /// M5: registers a renderer that fades when the plane (point, normal) separates camera and target, or when a sight
        /// line from the camera to the player furniture crosses the box of <paramref name="box"/> (centred on it, at its
        /// current pose, <paramref name="size"/> in its local axes).
        /// </summary>
        public void Add(Renderer renderer, Vector3 point, Vector3 normal, Transform box, Vector3 size)
        {
            Register(renderer, point, normal, false, box, size * 0.5f + Vector3.one * Tuning.LeafFadeMargin);
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
        }

        /// <summary>Applies the rule for a camera position at once, no transition (also callable from tests and tools).</summary>
        public void Apply(Vector3 camera)
        {
            Step(camera, true, 0f);
        }

        /// <summary>
        /// The rule for every part, then its opacity: snapped, or moved toward its target by <paramref name="dt"/> over
        /// <see cref="Tuning.WallFadeSeconds"/>. A part is drawn itself only while it fully stands; otherwise its copy is.
        /// </summary>
        private void Step(Vector3 camera, bool snap, float dt)
        {
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
            float low = Mathf.Clamp01(Tuning.WallFadeAlpha);
            float rate = dt * (1f - low) / Mathf.Max(1e-3f, Tuning.WallFadeSeconds);
            for (int i = 0; i < entries.Count; i++)
            {
                Entry e = entries[i];
                if (e.Renderer == null)
                {
                    continue;
                }
                float side = Vector3.Dot(camera - e.Point, e.Normal);
                bool hidden = e.Outer ? side < 0f : side * Vector3.Dot(player - e.Point, e.Normal) < 0f;
                if (!hidden && e.Box != null)
                {
                    bool crossed = CrossesBox(camera, points, count, e.Box, e.HalfSize); // MUTATION:LEAF_FADE
                    hidden = crossed;
                }
                float target = hidden ? low : 1f;
                e.Alpha = snap ? target : Mathf.MoveTowards(e.Alpha, target, rate);
                bool standing = !hidden && e.Alpha >= 1f;
                ShadowCastingMode mode = standing ? e.Shown : ShadowCastingMode.ShadowsOnly;
                if (e.Renderer.shadowCastingMode != mode)
                {
                    e.Renderer.shadowCastingMode = mode;
                }
                if (hidden)
                {
                    HiddenCount++;
                }
                if (!standing)
                {
                    AnyFaded = true;
                    if (e.Alpha > low && e.Alpha < 1f)
                    {
                        Moving++;
                    }
                }
            }
        }

        /// <summary>
        /// Draws every part that does not fully stand, see-through at its opacity, for this frame (every camera, or only
        /// <paramref name="only"/>). LateUpdate calls it; a tool rendering a camera by hand calls it after <see cref="Apply"/>.
        /// </summary>
        public void DrawFaded(Camera only = null)
        {
            if (!AnyFaded)
            {
                return;
            }
            Material material = GhostMaterial;
            for (int i = 0; i < entries.Count; i++)
            {
                Entry e = entries[i];
                Renderer r = e.Renderer;
                if (r == null || e.Alpha >= 1f || !r.enabled || !r.gameObject.activeInHierarchy)
                {
                    continue;
                }
                Mesh mesh = e.Filter != null ? e.Filter.sharedMesh : null;
                if (mesh == null)
                {
                    continue;
                }
                if (e.Block == null)
                {
                    Prepare(e);
                }
                if (e.Applied != e.Alpha)
                {
                    e.Applied = e.Alpha;
                    Color c = e.BaseColor;
                    e.Block.SetColor(BaseColorId, new Color(c.r, c.g, c.b, c.a * e.Alpha));
                }
                var parameters = new RenderParams(material)
                {
                    layer = 0,
                    camera = only,
                    shadowCastingMode = ShadowCastingMode.Off,
                    receiveShadows = true,
                    matProps = e.Block,
                };
                Matrix4x4 matrix = r.localToWorldMatrix;
                for (int sub = 0; sub < mesh.subMeshCount; sub++)
                {
                    Graphics.RenderMesh(parameters, mesh, sub, matrix);
                }
            }
        }

        /// <summary>
        /// The see-through copy's property block, once per part: its own detail (base map and tiling, normal map) as its
        /// property block shows it, else its material's base map, and its material's colour, smoothness and metallic.
        /// </summary>
        private static void Prepare(Entry e)
        {
            Renderer r = e.Renderer;
            var block = new MaterialPropertyBlock();
            r.GetPropertyBlock(block, 0);
            if (block.isEmpty)
            {
                r.GetPropertyBlock(block);
            }
            Material own = r.sharedMaterial;
            if (own != null)
            {
                if (!block.HasTexture(BaseMapId) && own.HasProperty(BaseMapId) && own.GetTexture(BaseMapId) != null)
                {
                    block.SetTexture(BaseMapId, own.GetTexture(BaseMapId));
                    block.SetVector(BaseMapStId, own.GetVector(BaseMapStId));
                }
                block.SetFloat(SmoothnessId, own.HasProperty(SmoothnessId) ? own.GetFloat(SmoothnessId) : 0.1f);
                block.SetFloat(MetallicId, own.HasProperty(MetallicId) ? own.GetFloat(MetallicId) : 0f);
                e.BaseColor = own.HasProperty(BaseColorId) ? own.GetColor(BaseColorId) : Color.white;
            }
            else
            {
                e.BaseColor = Color.white;
            }
            e.Block = block;
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
