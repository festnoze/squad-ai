using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using Object = UnityEngine.Object;

namespace OutOfSight.Editor
{
    /// <summary>
    /// WINDOWS3D (2026-11-24, docs/next/progress/WINDOWS3D.md): bakes Assets/Resources/WindowModel.asset (<see cref="WindowModel"/>)
    /// from the art handoff's wood casement window (Assets/ThirdParty/Models/WoodWindow/wood_casement_window.glb, copied from
    /// ArtHandoff/WoodWindow, whose INTEGRATION.md it follows) and keeps the glazing material Assets/Settings/WindowGlass.mat
    /// (shader <see cref="WindowModel.GlassShaderName"/>, the handoff's reference values). Called by ModelCatalogBuilder.Build
    /// (SetupAndCompile and every player build), after the dressing bake whose wall arrays and GLB reader it uses. Idempotent:
    /// rebakes only when the GLB, the bake or the arrays' slice list changed.
    /// <list type="bullet">
    /// <item>The frame: every primitive but the <see cref="GlassSlot"/> one, through DressingBuilder.Bake: the satin walnut
    /// samples the walnut_veneer slice of the wall arrays (the GLB's own image, byte for byte the living room pack's, already a
    /// dressing slice) tinted by its vertex colour; the gaskets and the hardware are flat colours with their own metallic and
    /// smoothness. Drawn with the wall material: no material of its own.</item>
    /// <item>The glass: the <see cref="GlassSlot"/> primitive alone (the six quads, 36 indices), as glTFast imports it (x negated,
    /// the winding turned over, V flipped), the UV 0 to 1 of each pane kept: the shader draws its streaks from them and takes
    /// its angle from the model's object space.</item>
    /// </list>
    /// </summary>
    public static class WindowModelBuilder
    {
        public const string GlbPath = "Assets/ThirdParty/Models/WoodWindow/wood_casement_window.glb";
        public const string AssetPath = "Assets/Resources/WindowModel.asset";
        public const string GlassMaterialPath = "Assets/Settings/WindowGlass.mat";

        /// <summary>The GLB's glazing slot, found by its name (INTEGRATION.md: never by its import index).</summary>
        public const string GlassSlot = "Clear glazing";

        /// <summary>Bumped when the bake itself changes, so the model rebakes once.</summary>
        private const string BakeVersion = "windows3d-1";

        // The handoff's reference glazing material (INTEGRATION.md, the prefab settings): the shader's own defaults.
        private static readonly Color GlassTint = new Color(0.93f, 0.98f, 1f, 1f);
        private const float GlassVeil = 0.006f;
        private const float GlassReflection = 0.88f;

        [MenuItem("OutOfSight/Build Window Model")]
        public static void Build()
        {
            var log = new StringBuilder("[WindowModelBuilder]\n");
            Build(log);
            AssetDatabase.SaveAssets();
            Debug.Log(log.ToString());
        }

        public static void Build(StringBuilder log)
        {
            if (!File.Exists(GlbPath))
            {
                Debug.LogError($"[WindowModelBuilder] no window model at {GlbPath}: the windows keep their flat look");
                return;
            }
            Material glassMaterial = EnsureGlassMaterial(log);
            if (glassMaterial == null)
            {
                return;
            }
            string hash = SourceHash();
            var model = AssetDatabase.LoadAssetAtPath<WindowModel>(AssetPath);
            if (model != null && model.sourceHash == hash && model.frame != null && model.glass != null)
            {
                if (model.glassMaterial != glassMaterial)
                {
                    model.glassMaterial = glassMaterial;
                    EditorUtility.SetDirty(model);
                    log.Append("  relinked the glass material of ").Append(AssetPath).Append('\n');
                    return;
                }
                log.Append("  unchanged ").Append(AssetPath).Append('\n');
                return;
            }
            if (model == null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(AssetPath) ?? "Assets/Resources");
                model = ScriptableObject.CreateInstance<WindowModel>();
                AssetDatabase.CreateAsset(model, AssetPath);
            }
            foreach (Object o in AssetDatabase.LoadAllAssetsAtPath(AssetPath))
            {
                if (o is Mesh)
                {
                    Object.DestroyImmediate(o, true);
                }
            }
            Mesh frame = DressingBuilder.Bake("wood_casement_window", GlbPath, null, out int frameTriangles, name => name != GlassSlot);
            frame.name = "WindowFrame";
            CheckWood(frame);
            Mesh glass = BakeGlass(out int glassTriangles);
            AssetDatabase.AddObjectToAsset(frame, model);
            AssetDatabase.AddObjectToAsset(glass, model);
            model.frame = frame;
            model.glass = glass;
            model.glassMaterial = glassMaterial;
            model.frameTriangles = frameTriangles;
            model.glassTriangles = glassTriangles;
            model.sourceHash = hash;
            EditorUtility.SetDirty(model);
            log.Append($"  frame: {frame.vertexCount} vertices, {frameTriangles} triangles, bounds {frame.bounds.min.ToString("0.###")} to {frame.bounds.max.ToString("0.###")}\n");
            log.Append($"  glass: {glass.vertexCount} vertices, {glassTriangles} triangles, bounds {glass.bounds.min.ToString("0.###")} to {glass.bounds.max.ToString("0.###")}\n");
            log.Append("  baked ").Append(AssetPath).Append('\n');
        }

        /// <summary>
        /// The glazing material asset: the handoff's shader and reference values, the shader's transparent queue. Being
        /// referenced by Resources/WindowModel.asset is what keeps the shader in the player (a shader only named in code is
        /// stripped). Null, with one error, when the shader does not compile or is missing.
        /// </summary>
        private static Material EnsureGlassMaterial(StringBuilder log)
        {
            Shader shader = Shader.Find(WindowModel.GlassShaderName);
            if (shader == null)
            {
                Debug.LogError($"[WindowModelBuilder] shader {WindowModel.GlassShaderName} not found (Assets/Settings/WindowGlass.shader): the windows keep their flat look");
                return null;
            }
            var m = AssetDatabase.LoadAssetAtPath<Material>(GlassMaterialPath);
            bool created = m == null;
            if (created)
            {
                m = new Material(shader) { name = Path.GetFileNameWithoutExtension(GlassMaterialPath) };
                AssetDatabase.CreateAsset(m, GlassMaterialPath);
            }
            bool changed = created || m.shader != shader || m.GetColor("_Tint") != GlassTint || !Mathf.Approximately(m.GetFloat("_Veil"), GlassVeil)
                || !Mathf.Approximately(m.GetFloat("_ReflectionStrength"), GlassReflection) || m.renderQueue != (int)RenderQueue.Transparent
                || m.enableInstancing;
            if (changed)
            {
                m.shader = shader;
                m.SetColor("_Tint", GlassTint);
                m.SetFloat("_Veil", GlassVeil);
                m.SetFloat("_ReflectionStrength", GlassReflection);
                m.renderQueue = (int)RenderQueue.Transparent;
                // The shader declares no instancing: one draw per window, each in its own object space.
                m.enableInstancing = false;
                EditorUtility.SetDirty(m);
                log.Append(created ? "  created " : "  updated ").Append(GlassMaterialPath).Append('\n');
            }
            return m;
        }

        /// <summary>One error when no vertex of the frame samples a dressing slice: the walnut would draw as a flat colour.</summary>
        private static void CheckWood(Mesh frame)
        {
            var finish = new List<Vector4>();
            frame.GetUVs(WallArray.FinishChannel, finish);
            int first = WallArray.Slices.Length + 1;
            if (!finish.Exists(f => f.x >= first - 0.5f))
            {
                Debug.LogError("[WindowModelBuilder] the window's wood names no dressing slice (is walnut_veneer still in WallArray.DressingSlices?)");
            }
        }

        /// <summary>The <see cref="GlassSlot"/> primitive of the GLB, as glTFast imports it (see the class summary).</summary>
        private static Mesh BakeGlass(out int triangleCount)
        {
            byte[] glb = File.ReadAllBytes(GlbPath);
            if (glb.Length < 20 || BitConverter.ToUInt32(glb, 0) != 0x46546C67)
            {
                throw new InvalidOperationException($"[WindowModelBuilder] {GlbPath} is not a binary glTF");
            }
            int jsonLength = BitConverter.ToInt32(glb, 12);
            JObject gltf = JObject.Parse(Encoding.UTF8.GetString(glb, 20, jsonLength));
            int bin = 20 + jsonLength + 8;
            var materials = (JArray)gltf["materials"];
            var vertices = new List<Vector3>();
            var normals = new List<Vector3>();
            var uvs = new List<Vector2>();
            var triangles = new List<int>();
            foreach (JToken node in gltf["nodes"])
            {
                if (node["mesh"] == null)
                {
                    continue;
                }
                foreach (JToken primitive in gltf["meshes"][(int)node["mesh"]]["primitives"])
                {
                    JToken material = primitive["material"] != null ? materials[(int)primitive["material"]] : null;
                    if ((string)material?["name"] != GlassSlot)
                    {
                        continue;
                    }
                    JToken attributes = primitive["attributes"];
                    if (attributes["TEXCOORD_0"] == null)
                    {
                        throw new InvalidOperationException($"[WindowModelBuilder] {GlbPath}: the '{GlassSlot}' slot has no UV (the shader draws its streaks from them)");
                    }
                    float[] p = DressingBuilder.Read(gltf, glb, bin, (int)attributes["POSITION"], out _);
                    float[] n = DressingBuilder.Read(gltf, glb, bin, (int)attributes["NORMAL"], out _);
                    float[] t = DressingBuilder.Read(gltf, glb, bin, (int)attributes["TEXCOORD_0"], out _);
                    int[] indices = DressingBuilder.ReadIndices(gltf, glb, bin, (int)primitive["indices"]);
                    int start = vertices.Count;
                    int count = p.Length / 3;
                    for (int k = 0; k < count; k++)
                    {
                        vertices.Add(new Vector3(-p[3 * k], p[3 * k + 1], p[3 * k + 2]));
                        normals.Add(new Vector3(-n[3 * k], n[3 * k + 1], n[3 * k + 2]));
                        uvs.Add(new Vector2(t[2 * k], 1f - t[2 * k + 1]));
                    }
                    // Mirrored by the x flip: the winding turns over (the shader draws both faces anyway).
                    for (int i = 0; i + 2 < indices.Length; i += 3)
                    {
                        triangles.Add(start + indices[i]);
                        triangles.Add(start + indices[i + 2]);
                        triangles.Add(start + indices[i + 1]);
                    }
                }
            }
            if (triangles.Count == 0)
            {
                throw new InvalidOperationException($"[WindowModelBuilder] {GlbPath} has no '{GlassSlot}' slot");
            }
            var mesh = new Mesh { name = "WindowGlass" };
            mesh.SetVertices(vertices);
            mesh.SetNormals(normals);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            triangleCount = triangles.Count / 3;
            return mesh;
        }

        private static string SourceHash()
        {
            using (var sha = System.Security.Cryptography.SHA1.Create())
            {
                // The wood's vertices name their slice index: a change of the arrays' slice list rebakes.
                var all = new List<byte>(Encoding.UTF8.GetBytes(BakeVersion + "|" + GlassSlot + "|" + string.Join(",", WallArray.DressingSlices)
                    + "|" + WallArray.Slices.Length));
                all.AddRange(File.ReadAllBytes(GlbPath));
                return BitConverter.ToString(sha.ComputeHash(all.ToArray())).Replace("-", string.Empty);
            }
        }
    }
}
