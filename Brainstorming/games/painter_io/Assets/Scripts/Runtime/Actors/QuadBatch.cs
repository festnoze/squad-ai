// Owned by BI since wave B-2 (written by B2). Contract 12.1 (per-object data through vertex attributes, never a MaterialPropertyBlock on a
// graph renderer) and 12.3 (beads and overlays). A QuadBatch is ONE dynamic world-space mesh of quads drawn by the main
// camera with the Bead or the Overlay graph: a droplet chain, the splash drops, all pearls, all overlays. It is rebuilt
// every frame from preallocated lists (no per-frame managed garbage once the lists reached their capacity).
// Contract 25.2: every batch remembers whether it draws beads or overlays; on a biome change ActorViews swaps the shader
// of every live batch (QuadBatch.RebindAll) to the biome's Bead / Overlay shader, with the SAME vertex data.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    /// <summary>Overlay shape ids understood by Overlay.hlsl (UV1.x). Ids 0-5 are shared by every biome overlay shader.
    /// Ids 6-15 are RESERVED for biome effects (FireFx uses 10-12, ElectricFx 6-10, each with its own overlay shader):
    /// a future shared shape takes id 16 or above. Wave D-2 (traits-fx): ids 16-21 are the shared trait shapes drawn by
    /// TraitFxView (Streak and Shimmer use their own vertex layouts, see Overlay.hlsl).</summary>
    public enum OverlayShape
    {
        Ring = 0,
        Halo = 1,
        Chevron = 2,
        Glint = 3,
        Flash = 4,
        Disc = 5,
        Streak = 16,
        Arc = 17,
        Aura = 18,
        Film = 19,
        Timer = 20,
        Shimmer = 21,
    }

    /// <summary>What a QuadBatch draws, so a biome change can give it the biome's matching shader.</summary>
    public enum QuadBatchKind { Bead = 0, Overlay = 1 }

    /// <summary>One dynamic mesh of camera-facing quads in world space (identity transform), Bead or Overlay graph.</summary>
    public sealed class QuadBatch
    {
        private static readonly List<QuadBatch> live = new List<QuadBatch>();

        /// <summary>Hard cap (16-bit indices: 4 vertices per quad).</summary>
        public const int MaxQuads = 16000;

        /// <summary>Render queues: every bead and overlay draws after the composite (1900), in this order.</summary>
        public const int QueueDroplets = 3001;
        public const int QueueSplash = 3002;
        public const int QueuePearls = 3003;
        public const int QueueOverlays = 3004;
        public const int QueueIndicators = 3005;

        /// <summary>Shadow offset toward the light (contract 12.2), used for bead quad margins.</summary>
        public const float ShadowReach = 0.12f;

        private readonly GameObject go;
        private readonly Mesh mesh;
        private readonly MeshRenderer renderer;
        private readonly List<Vector3> vertices = new List<Vector3>(64);
        private readonly List<Color> colors = new List<Color>(64);
        private readonly List<Vector4> uv0 = new List<Vector4>(64);
        private readonly List<Vector4> uv1 = new List<Vector4>(64);
        private readonly List<Vector4> uv2 = new List<Vector4>(64);
        private readonly List<int> indices = new List<int>(96);
        private readonly int queue;
        private Material material;
        private Vector2 min, max;
        private bool open;

        public QuadBatch(string name, Transform parent, Shader shader, int renderQueue, int sortingOrder)
            : this(name, parent, shader, renderQueue, sortingOrder, renderQueue == QueueDroplets || renderQueue == QueueSplash || renderQueue == QueuePearls ? QuadBatchKind.Bead : QuadBatchKind.Overlay)
        {
        }

        public QuadBatch(string name, Transform parent, Shader shader, int renderQueue, int sortingOrder, QuadBatchKind kind)
        {
            Kind = kind;
            queue = renderQueue;
            live.Add(this);
            go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = Vector3.zero;
            go.transform.localRotation = Quaternion.identity;
            go.transform.localScale = Vector3.one;
            mesh = new Mesh { name = name };
            mesh.MarkDynamic();
            var filter = go.AddComponent<MeshFilter>();
            filter.sharedMesh = mesh;
            renderer = go.AddComponent<MeshRenderer>();
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.lightProbeUsage = LightProbeUsage.Off;
            renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
            renderer.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
            renderer.allowOcclusionWhenDynamic = false;
            renderer.sortingOrder = sortingOrder;
            if (shader != null)
            {
                material = new Material(shader) { name = name, renderQueue = renderQueue };
                renderer.sharedMaterial = material;
            }
            renderer.enabled = false;
        }

        /// <summary>Quads added since Begin.</summary>
        public int Count { get; private set; }

        /// <summary>Bead or Overlay: the biome shader this batch takes on a biome change.</summary>
        public QuadBatchKind Kind { get; }

        public bool HasMaterial => material != null;

        /// <summary>Live batches (created and not destroyed), for RebindAll.</summary>
        public static int LiveCount => live.Count;

        /// <summary>Gives every live batch the shader of its kind (biome change, contract 25.2); null shaders are skipped.</summary>
        public static void RebindAll(Shader bead, Shader overlay)
        {
            for (int i = live.Count - 1; i >= 0; i--)
            {
                QuadBatch b = live[i];
                if (b == null) continue;
                b.SetShader(b.Kind == QuadBatchKind.Bead ? bead : overlay);
            }
        }

        /// <summary>Swaps the material's shader (keeps the render queue); creates the material if the batch had none.</summary>
        public void SetShader(Shader shader)
        {
            if (shader == null || renderer == null) return;
            if (material == null)
            {
                material = new Material(shader) { name = go != null ? go.name : "QuadBatch", renderQueue = queue };
                renderer.sharedMaterial = material;
                return;
            }
            if (material.shader != shader) material.shader = shader;
            material.renderQueue = queue;
        }

        public Material Material => material;

        public MeshRenderer Renderer => renderer;

        public Mesh Mesh => mesh;

        public void Begin()
        {
            vertices.Clear();
            colors.Clear();
            uv0.Clear();
            uv1.Clear();
            uv2.Clear();
            indices.Clear();
            Count = 0;
            min = new Vector2(float.MaxValue, float.MaxValue);
            max = new Vector2(float.MinValue, float.MinValue);
            open = true;
        }

        /// <summary>
        /// A bead (Bead.hlsl): center and radius in world units, stretch along dir (1 = round), linear albedo, opacity,
        /// shadow strength (0..1), specular lobes (1 or 2), highlight boost (0..1).
        /// </summary>
        public void AddBead(Vector2 center, float radius, Vector2 dir, float stretch, Color linearColor, float opacity,
                            float shadow, float lobes, float boost)
        {
            if (!open || Count >= MaxQuads || !(radius > 1e-4f) || !(opacity > 0.001f)) return;
            if (float.IsNaN(center.x) || float.IsNaN(center.y)) return;
            float s = Mathf.Clamp(stretch, 0.25f, 4f);
            float ext = radius * Mathf.Max(s, 1f / s) * 1.08f + (shadow > 0f ? ShadowReach + radius * 0.1f : 0f) + 0.04f;
            Vector2 d = dir.sqrMagnitude > 1e-10f ? dir.normalized : Vector2.right;
            var c = new Color(linearColor.r, linearColor.g, linearColor.b, Mathf.Clamp01(opacity));
            var a = new Vector4(radius, s, d.x, d.y);
            var b = new Vector4(Mathf.Clamp01(shadow), lobes, Mathf.Clamp01(boost), 0f);
            int baseIndex = vertices.Count;
            for (int k = 0; k < 4; k++)
            {
                float ox = (k & 1) == 0 ? -ext : ext;
                float oy = (k & 2) == 0 ? -ext : ext;
                vertices.Add(new Vector3(center.x + ox, center.y + oy, 0f));
                uv0.Add(new Vector4(ox, oy, 0f, 0f));
                uv1.Add(a);
                uv2.Add(b);
                colors.Add(c);
            }
            AddQuadIndices(baseIndex);
            Grow(center, ext, ext);
            Count++;
        }

        /// <summary>
        /// An overlay shape (Overlay.hlsl): center in world units, half size of the quad along its local x and y (world
        /// units), rotation of the local frame (radians, counter-clockwise), shape parameters (a, b, c) in local units
        /// (the quad spans [-1, 1]), linear color, opacity, specular lobes.
        /// </summary>
        public void AddOverlay(Vector2 center, Vector2 halfSize, float rotation, OverlayShape shape, Vector3 abc,
                               Color linearColor, float opacity, float lobes)
        {
            if (!open || Count >= MaxQuads || !(opacity > 0.001f)) return;
            if (!(halfSize.x > 1e-5f) || !(halfSize.y > 1e-5f)) return;
            if (float.IsNaN(center.x) || float.IsNaN(center.y)) return;
            float cs = Mathf.Cos(rotation), sn = Mathf.Sin(rotation);
            var ax = new Vector2(cs, sn) * halfSize.x;
            var ay = new Vector2(-sn, cs) * halfSize.y;
            var c = new Color(linearColor.r, linearColor.g, linearColor.b, Mathf.Clamp01(opacity));
            var a = new Vector4((float)shape, abc.x, abc.y, abc.z);
            var b = new Vector4(cs, sn, 0f, lobes);
            int baseIndex = vertices.Count;
            for (int k = 0; k < 4; k++)
            {
                float lx = (k & 1) == 0 ? -1f : 1f;
                float ly = (k & 2) == 0 ? -1f : 1f;
                Vector2 p = center + ax * lx + ay * ly;
                vertices.Add(new Vector3(p.x, p.y, 0f));
                uv0.Add(new Vector4(lx, ly, halfSize.x, 0f));
                uv1.Add(a);
                uv2.Add(b);
                colors.Add(c);
            }
            AddQuadIndices(baseIndex);
            float r = Mathf.Max(halfSize.x, halfSize.y);
            Grow(center, r, r);
            Count++;
        }

        /// <summary>Uploads the quads (or hides the renderer when there are none).</summary>
        public void End()
        {
            open = false;
            if (mesh == null || renderer == null) return;
            if (Count == 0 || material == null)
            {
                if (renderer.enabled) renderer.enabled = false;
                if (mesh.vertexCount > 0) mesh.Clear(true);
                return;
            }
            mesh.Clear(true);
            mesh.SetVertices(vertices);
            mesh.SetColors(colors);
            mesh.SetUVs(0, uv0);
            mesh.SetUVs(1, uv1);
            mesh.SetUVs(2, uv2);
            mesh.SetTriangles(indices, 0, false);
            Vector2 center = (min + max) * 0.5f;
            Vector2 size = max - min;
            mesh.bounds = new Bounds(new Vector3(center.x, center.y, 0f), new Vector3(size.x + 0.1f, size.y + 0.1f, 1f));
            if (!renderer.enabled) renderer.enabled = true;
        }

        /// <summary>Hides the batch at once (between sessions).</summary>
        public void Hide()
        {
            Begin();
            End();
        }

        public void Destroy()
        {
            live.Remove(this);
            LiquidRenderer.SafeDestroy(material);
            LiquidRenderer.SafeDestroy(mesh);
            LiquidRenderer.SafeDestroy(go);
        }

        private void AddQuadIndices(int b)
        {
            indices.Add(b);
            indices.Add(b + 2);
            indices.Add(b + 1);
            indices.Add(b + 2);
            indices.Add(b + 3);
            indices.Add(b + 1);
        }

        private void Grow(Vector2 c, float ex, float ey)
        {
            if (c.x - ex < min.x) min.x = c.x - ex;
            if (c.y - ey < min.y) min.y = c.y - ey;
            if (c.x + ex > max.x) max.x = c.x + ex;
            if (c.y + ey > max.y) max.y = c.y + ey;
        }
    }

    /// <summary>
    /// A FieldBlob contributor (contract 12.2 mesh conventions): LiquidLayers.QuadMesh on layer 31, transform scale
    /// (2 S stretch, 2 S / stretch, 1) with S = SupportForVisibleRadius(visibleRadius, A), Z rotation = direction angle,
    /// MaterialPropertyBlock _Channel / _Amplitude.
    /// </summary>
    public sealed class FieldBlobDrawer
    {
        private static readonly int ChannelId = Shader.PropertyToID("_Channel");
        private static readonly int AmplitudeId = Shader.PropertyToID("_Amplitude");

        private readonly GameObject go;
        private readonly MeshRenderer renderer;
        private readonly MaterialPropertyBlock block = new MaterialPropertyBlock();
        private Vector4 channel;
        private float amplitude = -1f;
        private bool visible;

        public FieldBlobDrawer(string name, Transform parent, Material sharedMaterial)
        {
            go = new GameObject(name) { layer = LiquidLayers.Field };
            go.transform.SetParent(parent, false);
            var filter = go.AddComponent<MeshFilter>();
            filter.sharedMesh = LiquidLayers.QuadMesh;
            renderer = go.AddComponent<MeshRenderer>();
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            renderer.lightProbeUsage = LightProbeUsage.Off;
            renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;
            renderer.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
            renderer.allowOcclusionWhenDynamic = false;
            renderer.sharedMaterial = sharedMaterial;
            renderer.enabled = false;
        }

        public bool Visible => visible;

        /// <summary>Places the blob (world center, visible radius, amplitude, stretch along the direction angle).</summary>
        public void Show(int player, Vector2 center, float visibleRadius, float amplitudeValue, float stretch, float angleRad)
        {
            if (renderer.sharedMaterial == null || !(visibleRadius > 1e-4f) || !(amplitudeValue > 1e-4f)
                || float.IsNaN(center.x) || float.IsNaN(center.y))
            {
                Hide();
                return;
            }
            float s = LiquidLayers.SupportForVisibleRadius(visibleRadius, amplitudeValue);
            float st = Mathf.Clamp(stretch, 0.25f, 4f);
            Transform t = go.transform;
            t.position = new Vector3(center.x, center.y, 0f);
            t.rotation = Quaternion.Euler(0f, 0f, angleRad * Mathf.Rad2Deg);
            t.localScale = new Vector3(2f * s * st, 2f * s / st, 1f);
            Vector4 ch = LiquidLayers.ChannelMask(player);
            if (ch != channel || !Mathf.Approximately(amplitudeValue, amplitude))
            {
                channel = ch;
                amplitude = amplitudeValue;
                block.SetVector(ChannelId, channel);
                block.SetFloat(AmplitudeId, amplitude);
                renderer.SetPropertyBlock(block);
            }
            if (!renderer.enabled) renderer.enabled = true;
            visible = true;
        }

        public void Hide()
        {
            if (renderer != null && renderer.enabled) renderer.enabled = false;
            visible = false;
        }

        public void Destroy()
        {
            if (go != null) UnityEngine.Object.Destroy(go);
        }
    }

    /// <summary>Loads the actor shaders from Resources (never Shader.Find) and logs a missing one once.</summary>
    internal static class ActorShaders
    {
        private static readonly HashSet<string> Reported = new HashSet<string>();

        public static Shader Load(string name)
        {
            Shader s = null;
            try
            {
                s = Resources.Load<Shader>("Shaders/" + name);
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] ActorViews: loading shader " + name + " failed: " + e.Message);
            }
            if (s == null && Reported.Add(name)) Debug.LogError("[PainterIO] ActorViews: shader Shaders/" + name + " not found in Resources");
            return s;
        }
    }
}
