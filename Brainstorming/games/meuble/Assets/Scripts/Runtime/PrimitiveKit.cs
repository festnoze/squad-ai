using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Meuble
{
    /// <summary>
    /// Procedural primitives (PRD 7.1): generated low poly meshes and one shared URP material per color.
    /// Unity's built in primitives are not used: their sphere alone is 768 triangles, and they come with
    /// colliders nobody asked for.
    ///
    /// Caches are static and survive level rebuilds. Every cached object is flagged DontUnloadUnusedAsset
    /// and checked for null before reuse, because a scene load may unload unreferenced runtime assets.
    /// </summary>
    public static class PrimitiveKit
    {
        public const string LitShaderName = "Universal Render Pipeline/Lit";
        public const string UnlitShaderName = "Universal Render Pipeline/Unlit";

        private static readonly Dictionary<Color32, Material> LitCache = new Dictionary<Color32, Material>();
        private static readonly Dictionary<Color32, Material> UnlitCache = new Dictionary<Color32, Material>();
        private static readonly Dictionary<Color32, Material> TransparentCache = new Dictionary<Color32, Material>();
        private static readonly Dictionary<string, Mesh> MeshCache = new Dictionary<string, Mesh>();

        // ----- Materials -----

        public static Material Lit(Color color, float smoothness = 0.25f)
        {
            Color32 key = color;
            if (LitCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            Shader shader = Shader.Find(LitShaderName);
            if (shader == null)
            {
                Debug.LogError("[PrimitiveKit] URP Lit shader not found (is it in Always Included Shaders?)");
                shader = Shader.Find("Hidden/InternalErrorShader");
            }
            var m = new Material(shader) { name = "Lit " + ColorUtility.ToHtmlStringRGB(color), enableInstancing = true };
            m.SetColor("_BaseColor", color);
            m.SetFloat("_Smoothness", smoothness);
            m.SetFloat("_Metallic", 0f);
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            LitCache[key] = m;
            return m;
        }

        public static Material Unlit(Color color)
        {
            Color32 key = color;
            if (UnlitCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            var m = new Material(FindUnlit()) { name = "Unlit " + ColorUtility.ToHtmlStringRGB(color), enableInstancing = true };
            m.SetColor("_BaseColor", color);
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            UnlitCache[key] = m;
            return m;
        }

        /// <summary>Alpha blended, double sided, no depth write: the floor vision cone.</summary>
        public static Material UnlitTransparent(Color color)
        {
            Color32 key = color;
            if (TransparentCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            var m = new Material(FindUnlit()) { name = "Transparent " + ColorUtility.ToHtmlStringRGBA(color) };
            m.SetFloat("_Surface", 1f);
            m.SetFloat("_Blend", 0f);
            m.SetFloat("_Cull", (float)CullMode.Off);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_DstBlendAlpha", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_ZWrite", 0f);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            m.SetColor("_BaseColor", color);
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            TransparentCache[key] = m;
            return m;
        }

        /// <summary>
        /// M3: an unlit material whose colour is <paramref name="color"/> (sRGB) times <paramref name="intensity"/>,
        /// so it can rise above 1 and feed the bloom (the window pane). Cached by colour and intensity.
        /// </summary>
        public static Material Emissive(Color color, float intensity)
        {
            string key = ColorUtility.ToHtmlStringRGB(color) + "x" + intensity.ToString("0.###", System.Globalization.CultureInfo.InvariantCulture);
            if (EmissiveCache.TryGetValue(key, out Material cached) && cached != null)
            {
                return cached;
            }
            var m = new Material(FindUnlit()) { name = "Emissive " + key, enableInstancing = true };
            m.SetColor("_BaseColor", new Color(color.r * intensity, color.g * intensity, color.b * intensity, 1f));
            m.hideFlags = HideFlags.DontUnloadUnusedAsset;
            EmissiveCache[key] = m;
            return m;
        }

        private static readonly Dictionary<string, Material> EmissiveCache = new Dictionary<string, Material>();

        private static Shader FindUnlit()
        {
            Shader shader = Shader.Find(UnlitShaderName);
            if (shader == null)
            {
                Debug.LogError("[PrimitiveKit] URP Unlit shader not found (is it in Always Included Shaders?)");
                shader = Shader.Find("Hidden/InternalErrorShader");
            }
            return shader;
        }

        /// <summary>Number of distinct materials created so far (budget check, PRD 7.4).</summary>
        public static int MaterialCount => LitCache.Count + UnlitCache.Count + TransparentCache.Count + EmissiveCache.Count;

        // ----- Meshes (unit size, scaled by the transform) -----

        /// <summary>Unit cube centered on the origin: 24 vertices, 12 triangles.</summary>
        public static Mesh BoxMesh
        {
            get
            {
                if (MeshCache.TryGetValue("box", out Mesh cached) && cached != null)
                {
                    return cached;
                }
                Mesh mesh = BuildBox();
                MeshCache["box"] = mesh;
                return mesh;
            }
        }

        /// <summary>Unit quad in the xy plane, front face toward -z (Unity's built in quad orientation).</summary>
        public static Mesh QuadMesh
        {
            get
            {
                if (MeshCache.TryGetValue("quad", out Mesh cached) && cached != null)
                {
                    return cached;
                }
                var mesh = new Mesh { name = "Quad" };
                mesh.vertices = new[]
                {
                    new Vector3(-0.5f, -0.5f, 0f), new Vector3(-0.5f, 0.5f, 0f),
                    new Vector3(0.5f, 0.5f, 0f), new Vector3(0.5f, -0.5f, 0f),
                };
                mesh.normals = new[] { Vector3.back, Vector3.back, Vector3.back, Vector3.back };
                mesh.uv = new[] { new Vector2(0, 0), new Vector2(0, 1), new Vector2(1, 1), new Vector2(1, 0) };
                mesh.triangles = new[] { 0, 1, 2, 0, 2, 3 };
                mesh.RecalculateBounds();
                Keep(mesh);
                MeshCache["quad"] = mesh;
                return mesh;
            }
        }

        /// <summary>
        /// M3.1: one mesh made of axis aligned boxes (each a centre and a size in the mesh frame), so many static decor
        /// boxes draw as one renderer. Cached by geometry: a rebuilt level reuses its meshes instead of leaking new ones.
        /// </summary>
        public static Mesh BoxesMesh(IList<Bounds> boxes)
        {
            var key = new System.Text.StringBuilder("boxes");
            System.Globalization.CultureInfo c = System.Globalization.CultureInfo.InvariantCulture;
            foreach (Bounds b in boxes)
            {
                key.Append('|').Append(b.center.x.ToString("0.####", c)).Append(',').Append(b.center.y.ToString("0.####", c))
                    .Append(',').Append(b.center.z.ToString("0.####", c)).Append(',').Append(b.size.x.ToString("0.####", c))
                    .Append(',').Append(b.size.y.ToString("0.####", c)).Append(',').Append(b.size.z.ToString("0.####", c));
            }
            string k = key.ToString();
            if (MeshCache.TryGetValue(k, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh unit = BoxMesh;
            Vector3[] unitVertices = unit.vertices;
            Vector3[] unitNormals = unit.normals;
            int[] unitTriangles = unit.triangles;
            var vertices = new List<Vector3>(unitVertices.Length * boxes.Count);
            var normals = new List<Vector3>(unitVertices.Length * boxes.Count);
            var triangles = new List<int>(unitTriangles.Length * boxes.Count);
            foreach (Bounds b in boxes)
            {
                int start = vertices.Count;
                for (int i = 0; i < unitVertices.Length; i++)
                {
                    // A positive per axis scale keeps both the winding and the face normals of a box.
                    vertices.Add(b.center + Vector3.Scale(unitVertices[i], b.size));
                    normals.Add(unitNormals[i]);
                }
                foreach (int t in unitTriangles)
                {
                    triangles.Add(start + t);
                }
            }
            var mesh = new Mesh { name = "Boxes" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            Keep(mesh);
            MeshCache[k] = mesh;
            return mesh;
        }

        /// <summary>UV sphere of unit diameter.</summary>
        public static Mesh SphereMesh(int segments, int rings)
        {
            string key = $"sphere{segments}x{rings}";
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh mesh = BuildCapsule(0.5f, 1f, segments, rings);
            mesh.name = "Sphere";
            MeshCache[key] = mesh;
            return mesh;
        }

        /// <summary>Capsule of the given radius and total height, resting on y = 0.</summary>
        public static Mesh CapsuleMesh(float radius, float height, int segments, int capRings)
        {
            string key = $"capsule{radius:0.###}x{height:0.###}x{segments}x{capRings}";
            if (MeshCache.TryGetValue(key, out Mesh cached) && cached != null)
            {
                return cached;
            }
            Mesh mesh = BuildCapsule(radius, height, segments, capRings * 2);
            // Rest the capsule on the floor instead of centering it.
            Vector3[] v = mesh.vertices;
            for (int i = 0; i < v.Length; i++)
            {
                v[i].y += height * 0.5f;
            }
            mesh.vertices = v;
            mesh.RecalculateBounds();
            mesh.name = "Capsule";
            MeshCache[key] = mesh;
            return mesh;
        }

        private static Mesh BuildBox()
        {
            var vertices = new List<Vector3>(24);
            var normals = new List<Vector3>(24);
            var triangles = new List<int>(36);
            Vector3[] faceNormals = { Vector3.right, Vector3.left, Vector3.up, Vector3.down, Vector3.forward, Vector3.back };
            foreach (Vector3 n in faceNormals)
            {
                // Two axes spanning the face, chosen so the winding is clockwise seen from outside.
                Vector3 u = n.y != 0f ? Vector3.right : Vector3.up;
                Vector3 w = Vector3.Cross(n, u);
                int start = vertices.Count;
                Vector3 c = n * 0.5f;
                vertices.Add(c - u * 0.5f - w * 0.5f);
                vertices.Add(c + u * 0.5f - w * 0.5f);
                vertices.Add(c + u * 0.5f + w * 0.5f);
                vertices.Add(c - u * 0.5f + w * 0.5f);
                for (int i = 0; i < 4; i++)
                {
                    normals.Add(n);
                }
                triangles.AddRange(new[] { start, start + 1, start + 2, start, start + 2, start + 3 });
            }
            var mesh = new Mesh { name = "Box" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            FixWinding(mesh);
            Keep(mesh);
            return mesh;
        }

        /// <summary>Flips any triangle whose geometric normal disagrees with its vertex normal.</summary>
        private static void FixWinding(Mesh mesh)
        {
            Vector3[] v = mesh.vertices;
            Vector3[] n = mesh.normals;
            int[] t = mesh.triangles;
            for (int i = 0; i < t.Length; i += 3)
            {
                Vector3 face = Vector3.Cross(v[t[i + 1]] - v[t[i]], v[t[i + 2]] - v[t[i]]);
                if (Vector3.Dot(face, n[t[i]]) < 0f)
                {
                    (t[i + 1], t[i + 2]) = (t[i + 2], t[i + 1]);
                }
            }
            mesh.triangles = t;
        }

        /// <summary>
        /// Capsule (or sphere when height == 2 * radius) centered on the origin, axis along y.
        /// <paramref name="rings"/> is the number of latitude bands over both caps together.
        /// </summary>
        private static Mesh BuildCapsule(float radius, float height, int segments, int rings)
        {
            rings = Mathf.Max(2, rings + (rings % 2));
            float half = Mathf.Max(0f, height * 0.5f - radius);
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var triangles = new List<int>();
            // Latitudes from the north pole to the south pole. The equator is duplicated to open the cylinder.
            var latitudes = new List<(float angle, float offset)>();
            for (int r = 0; r <= rings / 2; r++)
            {
                latitudes.Add((Mathf.PI * 0.5f - Mathf.PI * 0.5f * r / (rings / 2), half));
            }
            for (int r = 0; r <= rings / 2; r++)
            {
                latitudes.Add((-Mathf.PI * 0.5f * r / (rings / 2), -half));
            }
            for (int l = 0; l < latitudes.Count; l++)
            {
                (float phi, float offset) = latitudes[l];
                for (int s = 0; s <= segments; s++)
                {
                    float theta = 2f * Mathf.PI * s / segments;
                    var n = new Vector3(Mathf.Cos(phi) * Mathf.Sin(theta), Mathf.Sin(phi), Mathf.Cos(phi) * Mathf.Cos(theta));
                    vertices.Add(n * radius + new Vector3(0f, offset, 0f));
                    normals.Add(n);
                }
            }
            int stride = segments + 1;
            for (int l = 0; l < latitudes.Count - 1; l++)
            {
                for (int s = 0; s < segments; s++)
                {
                    int a = l * stride + s;
                    int b = a + 1;
                    int c = a + stride;
                    int d = c + 1;
                    // Skip the degenerate triangles at the poles and in a zero height cylinder band.
                    if (Area(vertices[a], vertices[b], vertices[c]) > 1e-10f)
                    {
                        triangles.AddRange(new[] { a, b, c });
                    }
                    if (Area(vertices[b], vertices[d], vertices[c]) > 1e-10f)
                    {
                        triangles.AddRange(new[] { b, d, c });
                    }
                }
            }
            var mesh = new Mesh { name = "Capsule" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            FixWinding(mesh);
            Keep(mesh);
            return mesh;
        }

        private static float Area(Vector3 a, Vector3 b, Vector3 c)
        {
            return Vector3.Cross(b - a, c - a).sqrMagnitude;
        }

        private static void Keep(Object o)
        {
            o.hideFlags = HideFlags.DontUnloadUnusedAsset;
        }

        // ----- Object helpers -----

        public static GameObject Group(Transform parent, string name, Vector3 localPosition, float yawDeg = 0f)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPosition;
            go.transform.localRotation = Quaternion.Euler(0f, yawDeg, 0f);
            if (parent != null)
            {
                go.layer = parent.gameObject.layer;
            }
            return go;
        }

        /// <summary>A box of <paramref name="size"/> whose center sits at <paramref name="localCenter"/>.</summary>
        public static GameObject Box(Transform parent, string name, Vector3 localCenter, Vector3 size, Material material,
            int layer, bool collider)
        {
            GameObject go = Part(parent, name, BoxMesh, localCenter, Quaternion.identity, size, material, layer);
            if (collider)
            {
                go.AddComponent<BoxCollider>();
            }
            return go;
        }

        /// <summary>
        /// M3 (docs/CONTRACT_M3.md 1): with <paramref name="visual"/> false, a box that carried a collider is built
        /// as a collider-only GameObject (same name, transform, scale, layer and BoxCollider, but no MeshFilter and
        /// no MeshRenderer: the budget counters walk MeshFilters), and a box without a collider is not built at all
        /// (returns null). With <paramref name="visual"/> true this is <see cref="Box(Transform, string, Vector3, Vector3, Material, int, bool)"/>.
        /// </summary>
        public static GameObject Box(Transform parent, string name, Vector3 localCenter, Vector3 size, Material material,
            int layer, bool collider, bool visual)
        {
            if (visual)
            {
                return Box(parent, name, localCenter, size, material, layer, collider);
            }
            if (!collider)
            {
                return null;
            }
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localCenter;
            go.transform.localRotation = Quaternion.identity;
            go.transform.localScale = size;
            go.AddComponent<BoxCollider>();
            return go;
        }

        public static GameObject Part(Transform parent, string name, Mesh mesh, Vector3 localPosition, Quaternion localRotation,
            Vector3 localScale, Material material, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPosition;
            go.transform.localRotation = localRotation;
            go.transform.localScale = localScale;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = ShadowCastingMode.On;
            renderer.receiveShadows = true;
            return go;
        }
    }
}
