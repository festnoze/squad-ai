// Owned by BI since wave B-2 (written by B1). Contract 12.2 item 3: the static composite quad. It covers [-40, 40]^2 at z = 0 (the camera clamp of
// contract 14 keeps the view inside it) and is drawn by the main camera with the LiquidComposite graph, queue
// Geometry-100 (1900), ZWrite Off, ZTest Always (graph settings). The mesh carries the world position of each vertex
// in uv1, which the thin graph feeds to PIO_CompositeSG as the pixel's world position. Contract 25.2: the composite
// shader is the current biome's (BiomeTheme.CompositeShader, liquid fallback); SetShader swaps it live.
using UnityEngine;
using UnityEngine.Rendering;

namespace PainterIO.Runtime
{
    public sealed class LiquidSurface : MonoBehaviour
    {
        /// <summary>Half size of the composite quad, world units.</summary>
        public const float HalfExtent = 40f;
        /// <summary>Render queue of the composite material (Geometry - 100).</summary>
        public const int RenderQueue = 1900;

        private Mesh mesh;
        private Material material;
        private MeshRenderer meshRenderer;

        /// <summary>The LiquidComposite material.</summary>
        public Material Material => material;

        /// <summary>The quad's renderer.</summary>
        public MeshRenderer Renderer => meshRenderer;

        public static LiquidSurface Create(Transform parent, Shader composite)
        {
            if (composite == null) throw new System.ArgumentNullException(nameof(composite), "LiquidComposite shader missing");
            if (!composite.isSupported) Debug.LogError("[PainterIO] LiquidComposite shader is not supported on this device");
            var go = new GameObject("LiquidSurface");
            if (parent != null) go.transform.SetParent(parent, false);
            go.layer = 0;
            go.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            var s = go.AddComponent<LiquidSurface>();
            s.mesh = BuildMesh();
            go.AddComponent<MeshFilter>().sharedMesh = s.mesh;
            s.material = new Material(composite) { name = "PIO LiquidComposite", renderQueue = RenderQueue };
            MeshRenderer r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = s.material;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.lightProbeUsage = LightProbeUsage.Off;
            r.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r.motionVectorGenerationMode = MotionVectorGenerationMode.ForceNoMotion;
            r.allowOcclusionWhenDynamic = false;
            s.meshRenderer = r;
            return s;
        }

        /// <summary>Swaps the composite shader (biome change) and keeps the render queue (Geometry - 100).</summary>
        public void SetShader(Shader composite)
        {
            if (composite == null || material == null) return;
            if (material.shader != composite)
            {
                if (!composite.isSupported) Debug.LogError("[PainterIO] composite shader " + composite.name + " is not supported on this device");
                material.shader = composite;
                material.name = "PIO " + composite.name.Substring(composite.name.LastIndexOf('/') + 1);
            }
            material.renderQueue = RenderQueue;
        }

        private void LateUpdate()
        {
            // The surface maps uv1 = world position: keep the quad on the world origin whatever its parent does.
            if (transform.position != Vector3.zero || transform.rotation != Quaternion.identity)
            {
                transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
            }
        }

        private void OnDestroy()
        {
            LiquidRenderer.SafeDestroy(material);
            LiquidRenderer.SafeDestroy(mesh);
        }

        private static Mesh BuildMesh()
        {
            float e = HalfExtent;
            var m = new Mesh { name = "PIO LiquidSurface", hideFlags = HideFlags.HideAndDontSave };
            m.vertices = new[]
            {
                new Vector3(-e, -e, 0f), new Vector3(e, -e, 0f), new Vector3(-e, e, 0f), new Vector3(e, e, 0f),
            };
            m.uv = new[] { new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(0f, 1f), new Vector2(1f, 1f) };
            m.SetUVs(1, new[] { new Vector2(-e, -e), new Vector2(e, -e), new Vector2(-e, e), new Vector2(e, e) });
            m.colors = new[] { Color.white, Color.white, Color.white, Color.white };
            var n = new Vector3(0f, 0f, -1f);
            m.normals = new[] { n, n, n, n };
            // Clockwise as seen from the camera at z = -50 looking +Z (the graph draws both faces anyway).
            m.triangles = new[] { 0, 2, 1, 2, 3, 1 };
            m.bounds = new Bounds(Vector3.zero, new Vector3(2f * e, 2f * e, 1f));
            m.UploadMeshData(false);
            return m;
        }
    }
}
