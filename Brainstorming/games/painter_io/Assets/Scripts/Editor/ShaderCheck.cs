using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.Rendering;
using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;

namespace PainterIO.Editor
{
    /// <summary>
    /// Shader verification (docs/CONTRACT.md 12.1 as amended in v1.2), run by Builder.SetupAndCompile.
    /// For every .shader and .shadergraph of a folder: forced synchronous import, main Shader asset, synchronous compilation
    /// of every pass of the ACTIVE subshader, then FAIL when the shader is null, has errors (ShaderHasError, Error messages,
    /// errors logged during its import), is the internal error shader, lacks the _PIO_ShaderId marker property (a Shader
    /// Graph that fails to generate imports as an error shader without properties), declares another _PIO_* property (a
    /// _PIO_* global must never be a property), or when its active subshader is not a "RenderPipeline"="UniversalPipeline"
    /// one (a fallback is in use, so the real passes were never compiled). The folder also FAILS when two shader assets share
    /// a file name without extension, when an .hlsl has no .meta, and when a File-mode Custom Function of a graph references
    /// an .hlsl GUID that does not resolve or a function the file does not define.
    /// RunTemplates checks the thin Shader Graph templates (Assets/Shaders/Templates) the same way; RenderTemplates renders
    /// each template on a quad into a RenderTexture through a temporary camera and checks the pixels; RenderFieldContributors
    /// does the same for FieldBlob and FieldStroke against the contract 12.2 formulas (RenderTemplatesBatch runs all four).
    ///
    /// Batch mode pitfall handled here: until a camera renders, the URP pipeline instance does not exist and
    /// Shader.globalRenderPipeline is empty, so every "UniversalPipeline" subshader is unsupported and a Shader Graph runs its
    /// FallBack "Hidden/Shader Graph/FallbackError" (1 pass, queue 2000). Compiling "every pass" then compiles the fallback
    /// and reports a false green. <see cref="EnsureUniversalPipelineActive"/> renders one warm-up frame first.
    /// </summary>
    public static class ShaderCheck
    {
        public const string ShaderFolder = "Assets/Resources/Shaders";
        public const string TemplateFolder = "Assets/Shaders/Templates";
        public const string MarkerProperty = "_PIO_ShaderId";
        public const string GraphShaderPathPrefix = "Shader Graphs/PainterIO/";
        public const string PipelineTag = "UniversalPipeline";
        public const string UrpUnlitPath = "Packages/com.unity.render-pipelines.universal/Shaders/Unlit.shader";
        public static readonly string[] TemplateNames = { "ThinUnlitOpaque", "ThinUnlitTransparent" };

        private const string LogTag = "[ShaderCheck] ";

        /// <summary>Checks every shader of Assets/Resources/Shaders. Logs each failure; true when green.</summary>
        public static bool Run()
        {
            return CheckFolder(ShaderFolder, out _);
        }

        /// <summary>
        /// Checks the thin Shader Graph templates: the folder checks of <see cref="CheckFolder"/> plus the presence of both
        /// templates, their shader path and render queue. Logs each failure; true when green.
        /// </summary>
        public static bool RunTemplates()
        {
            bool ok = CheckFolder(TemplateFolder, out List<string> failures);
            foreach (string name in TemplateNames)
            {
                string path = TemplateFolder + "/" + name + ".shadergraph";
                Shader shader = AssetDatabase.LoadAssetAtPath<Shader>(path);
                if (shader == null)
                {
                    Fail(failures, path + ": template missing or not imported as a Shader");
                    ok = false;
                    continue;
                }
                int expectedQueue = name.Contains("Transparent") ? 3000 : 2000;
                if (shader.renderQueue != expectedQueue)
                {
                    Fail(failures, $"{path}: render queue {shader.renderQueue}, expected {expectedQueue}");
                    ok = false;
                }
            }
            Debug.Log(LogTag + (ok ? "PASS" : "FAIL") + " templates (" + TemplateFolder + ")");
            return ok;
        }

        /// <summary>Batch entry: Run + RunTemplates, exit code 0 when both are green.</summary>
        public static void RunBatch()
        {
            int code = 1;
            try
            {
                bool shaders = Run();
                bool templates = RunTemplates();
                code = shaders && templates ? 0 : 1;
            }
            catch (Exception e)
            {
                Debug.LogError(LogTag + "threw: " + e);
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        /// <summary>
        /// Batch entry: Run and RunTemplates, then RenderTemplates (pixel proof that both templates import AND render) and
        /// RenderFieldContributors (pixel proof of the FieldBlob / FieldStroke blend state and formulas), exit code 0 when all
        /// are green. -executeMethod PainterIO.Editor.ShaderCheck.RenderTemplatesBatch [-shotDir &lt;dir&gt;]
        /// </summary>
        public static void RenderTemplatesBatch()
        {
            int code = 1;
            try
            {
                string dir = Builder.ArgOr("-shotDir", "TestResults");
                bool shaders = Run();
                bool imported = RunTemplates();
                bool rendered = RenderTemplates(dir);
                bool fields = RenderFieldContributors(dir);
                code = shaders && imported && rendered && fields ? 0 : 1;
                Debug.Log(LogTag + (code == 0 ? "RenderTemplatesBatch PASS" : "RenderTemplatesBatch FAIL"));
            }
            catch (Exception e)
            {
                Debug.LogError(LogTag + "threw: " + e);
            }
            if (Application.isBatchMode)
            {
                EditorApplication.Exit(code);
            }
        }

        // -------------------------------------------------------------------------------------------------------------
        // Folder check
        // -------------------------------------------------------------------------------------------------------------

        /// <summary>The checks of contract 12.1 over every .shader and .shadergraph under <paramref name="folder"/>.</summary>
        public static bool CheckFolder(string folder, out List<string> failures)
        {
            failures = new List<string>();
            if (!Directory.Exists(folder))
            {
                Fail(failures, folder + ": folder missing");
                return false;
            }

            var shaderFiles = new List<string>();
            var byName = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string file in Directory.GetFiles(folder, "*", SearchOption.AllDirectories))
            {
                string path = file.Replace('\\', '/');
                string ext = Path.GetExtension(path).ToLowerInvariant();
                if (ext == ".hlsl" && !File.Exists(path + ".meta"))
                {
                    Fail(failures, path + ": .hlsl without its hand-written .meta (fixed GUID required before import)");
                }
                if (ext != ".shader" && ext != ".shadergraph")
                {
                    continue;
                }
                shaderFiles.Add(path);
                string key = Path.GetFileNameWithoutExtension(path);
                if (byName.TryGetValue(key, out string other))
                {
                    Fail(failures, $"{path}: shader name '{key}' exists twice ({other}); Resources.Load would be ambiguous");
                }
                else
                {
                    byName[key] = path;
                }
            }
            shaderFiles.Sort(StringComparer.Ordinal);

            bool asyncBefore = ShaderUtil.allowAsyncCompilation;
            ShaderUtil.allowAsyncCompilation = false;
            try
            {
                if (!EnsureUniversalPipelineActive())
                {
                    Fail(failures, $"Shader.globalRenderPipeline is '{Shader.globalRenderPipeline}', not '{PipelineTag}': URP subshaders cannot be checked");
                }
                foreach (string path in shaderFiles)
                {
                    CheckShader(path, failures);
                }
            }
            finally
            {
                ShaderUtil.allowAsyncCompilation = asyncBefore;
            }

            bool ok = failures.Count == 0;
            Debug.Log($"{LogTag}{(ok ? "PASS" : "FAIL")} {folder}: {shaderFiles.Count} shader(s), {failures.Count} failure(s)");
            return ok;
        }

        private static void CheckShader(string path, List<string> failures)
        {
            bool isGraph = path.EndsWith(".shadergraph", StringComparison.OrdinalIgnoreCase);
            if (isGraph)
            {
                CheckGraphFunctionFiles(path, failures);
            }

            var logged = new List<string>();
            Application.LogCallback capture = (message, stack, type) =>
            {
                if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert)
                {
                    lock (logged)
                    {
                        logged.Add(message);
                    }
                }
            };
            Application.logMessageReceivedThreaded += capture;
            Shader shader;
            int passes = 0;
            var passNames = new List<string>();
            try
            {
                AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
                shader = AssetDatabase.LoadAssetAtPath<Shader>(path);
                if (shader != null)
                {
                    var material = new Material(shader) { hideFlags = HideFlags.HideAndDontSave };
                    try
                    {
                        passes = material.passCount;
                        for (int i = 0; i < passes; i++)
                        {
                            passNames.Add(material.GetPassName(i));
                            ShaderUtil.CompilePass(material, i, true);
                        }
                    }
                    finally
                    {
                        UnityEngine.Object.DestroyImmediate(material);
                    }
                }
            }
            finally
            {
                Application.logMessageReceivedThreaded -= capture;
            }

            if (shader == null)
            {
                Fail(failures, path + ": no Shader main asset after import");
                return;
            }
            CheckActiveSubshader(path, shader, passes, failures);
            if (ShaderUtil.ShaderHasError(shader))
            {
                Fail(failures, $"{path}: ShaderUtil.ShaderHasError ({shader.name})");
            }
            foreach (ShaderMessage m in ShaderUtil.GetShaderMessages(shader))
            {
                if (m.severity == ShaderCompilerMessageSeverity.Error)
                {
                    Fail(failures, $"{path}: compile error '{m.message}' {m.file}:{m.line} ({m.platform})");
                }
            }
            if (shader.name.Contains("InternalErrorShader"))
            {
                Fail(failures, $"{path}: imported as the internal error shader");
            }
            if (shader.FindPropertyIndex(MarkerProperty) < 0)
            {
                Fail(failures, $"{path}: no {MarkerProperty} property (error shader, or marker forgotten)");
            }
            int count = shader.GetPropertyCount();
            for (int i = 0; i < count; i++)
            {
                string property = shader.GetPropertyName(i);
                if (property.StartsWith("_PIO_", StringComparison.Ordinal) && property != MarkerProperty)
                {
                    Fail(failures, $"{path}: property {property} shadows a _PIO_* global (declare it only in LiquidCommon.hlsl)");
                }
            }
            if (isGraph)
            {
                string expected = GraphShaderPathPrefix + Path.GetFileNameWithoutExtension(path);
                if (shader.name != expected)
                {
                    Fail(failures, $"{path}: shader name '{shader.name}', expected '{expected}' (graph m_Path 'Shader Graphs/PainterIO')");
                }
            }
            foreach (string message in logged)
            {
                Fail(failures, $"{path}: error logged during import or compilation: {FirstLine(message)}");
            }
            Debug.Log($"{LogTag}{path}: '{shader.name}', queue {shader.renderQueue}, {passes} pass(es) compiled: {string.Join(", ", passNames)}");
        }

        /// <summary>
        /// The material must run the shader's own URP subshader, not a FallBack: ShaderData.ActiveSubshaderIndex &gt;= 0, its
        /// "RenderPipeline" tag is UniversalPipeline, and the material sees exactly its passes.
        /// </summary>
        private static void CheckActiveSubshader(string path, Shader shader, int materialPasses, List<string> failures)
        {
            ShaderData data = ShaderUtil.GetShaderData(shader);
            if (data == null || data.ActiveSubshaderIndex < 0 || data.ActiveSubshader == null)
            {
                Fail(failures, $"{path}: no active subshader (none supported: a FallBack would run instead)");
                return;
            }
            string pipeline = data.ActiveSubshader.FindTagValue(new ShaderTagId("RenderPipeline")).name;
            if (pipeline != PipelineTag)
            {
                Fail(failures, $"{path}: active subshader {data.ActiveSubshaderIndex} has RenderPipeline tag '{pipeline}', expected '{PipelineTag}'");
            }
            if (data.ActiveSubshader.PassCount != materialPasses)
            {
                Fail(failures, $"{path}: material sees {materialPasses} pass(es), active subshader has {data.ActiveSubshader.PassCount} (FallBack in use?)");
            }
        }

        /// <summary>
        /// Makes sure the URP pipeline instance exists, so Shader.globalRenderPipeline = "UniversalPipeline" and URP
        /// subshaders are the active ones. In batch mode nothing has rendered yet: one 4 x 4 camera render creates the
        /// pipeline. If the tag is still wrong afterwards (no graphics device), sets it directly. True when the tag is right.
        /// </summary>
        public static bool EnsureUniversalPipelineActive()
        {
            if (Shader.globalRenderPipeline == PipelineTag)
            {
                return true;
            }
            string before = Shader.globalRenderPipeline;
            GameObject go = null;
            RenderTexture rt = null;
            try
            {
                rt = new RenderTexture(4, 4, 16, GraphicsFormat.R8G8B8A8_UNorm) { hideFlags = HideFlags.HideAndDontSave };
                rt.Create();
                go = new GameObject("PIO_PipelineWarmup") { hideFlags = HideFlags.HideAndDontSave };
                var camera = go.AddComponent<Camera>();
                camera.enabled = false;
                camera.cullingMask = 0;
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.targetTexture = rt;
                camera.Render();
            }
            catch (Exception e)
            {
                Debug.LogWarning(LogTag + "pipeline warm-up render threw: " + e.Message);
            }
            finally
            {
                if (go != null)
                {
                    UnityEngine.Object.DestroyImmediate(go);
                }
                if (rt != null)
                {
                    rt.Release();
                    UnityEngine.Object.DestroyImmediate(rt);
                }
            }
            if (Shader.globalRenderPipeline != PipelineTag)
            {
                Debug.LogWarning($"{LogTag}warm-up render left Shader.globalRenderPipeline = '{Shader.globalRenderPipeline}'; setting '{PipelineTag}'");
                Shader.globalRenderPipeline = PipelineTag;
            }
            Debug.Log($"{LogTag}Shader.globalRenderPipeline '{before}' -> '{Shader.globalRenderPipeline}' (pipeline: {(GraphicsSettings.currentRenderPipeline != null ? GraphicsSettings.currentRenderPipeline.name : "none")})");
            return Shader.globalRenderPipeline == PipelineTag;
        }

        [Serializable]
        private sealed class GraphEntry
        {
            public string m_Type = null;
            public string m_ObjectId = null;
            public int m_SourceType = -1;
            public string m_FunctionName = null;
            public string m_FunctionSource = null;
        }

        /// <summary>
        /// Every File-mode Custom Function node of a graph must reference, by GUID, an existing .hlsl that defines
        /// &lt;FunctionName&gt;_float (Single precision graphs) or &lt;FunctionName&gt;_half. A regenerated .meta (new random GUID)
        /// silently breaks the reference: this names the cause instead of leaving an error shader.
        /// </summary>
        private static void CheckGraphFunctionFiles(string graphPath, List<string> failures)
        {
            string text;
            try
            {
                text = File.ReadAllText(graphPath);
            }
            catch (Exception e)
            {
                Fail(failures, graphPath + ": unreadable: " + e.Message);
                return;
            }
            if (text.IndexOf("\n\n", StringComparison.Ordinal) < 0 && text.IndexOf("\n\r\n", StringComparison.Ordinal) < 0)
            {
                Fail(failures, graphPath + ": no blank line between JSON objects (the multi-JSON format needs one)");
            }
            foreach (string json in SplitMultiJson(text))
            {
                GraphEntry entry;
                try
                {
                    entry = JsonUtility.FromJson<GraphEntry>(json);
                }
                catch (Exception e)
                {
                    Fail(failures, graphPath + ": invalid JSON object: " + FirstLine(e.Message));
                    continue;
                }
                if (entry == null || entry.m_Type != "UnityEditor.ShaderGraph.CustomFunctionNode" || entry.m_SourceType != 0)
                {
                    continue;
                }
                string guid = entry.m_FunctionSource ?? "";
                string hlsl = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrEmpty(hlsl) || !File.Exists(hlsl))
                {
                    Fail(failures, $"{graphPath}: Custom Function {entry.m_FunctionName} references .hlsl GUID '{guid}' that resolves to no file (was its .meta regenerated?)");
                    continue;
                }
                if (!hlsl.EndsWith(".hlsl", StringComparison.OrdinalIgnoreCase))
                {
                    Fail(failures, $"{graphPath}: Custom Function {entry.m_FunctionName} source {hlsl} is not an .hlsl");
                    continue;
                }
                string source = File.ReadAllText(hlsl);
                string name = entry.m_FunctionName ?? "";
                if (source.IndexOf(" " + name + "_float(", StringComparison.Ordinal) < 0
                    && source.IndexOf(" " + name + "_half(", StringComparison.Ordinal) < 0)
                {
                    Fail(failures, $"{graphPath}: {hlsl} defines neither {name}_float nor {name}_half");
                }
            }
        }

        /// <summary>Splits a Shader Graph file into its JSON objects the way Shader Graph does (blank-line separated).</summary>
        private static IEnumerable<string> SplitMultiJson(string text)
        {
            int start = 0;
            while (start < text.Length)
            {
                int begin = text.IndexOf('{', start);
                if (begin < 0)
                {
                    yield break;
                }
                int end = text.IndexOf("\n\n", begin, StringComparison.Ordinal);
                if (end < 0)
                {
                    end = text.IndexOf("\n\r\n", begin, StringComparison.Ordinal);
                }
                if (end < 0)
                {
                    end = text.LastIndexOf('}') + 1;
                }
                if (end <= begin)
                {
                    yield break;
                }
                yield return text.Substring(begin, end - begin);
                start = end + 2;
            }
        }

        // -------------------------------------------------------------------------------------------------------------
        // Render check of the templates
        // -------------------------------------------------------------------------------------------------------------

        private const int TestLayer = 30;
        private const int TestSize = 64;
        private static readonly Color TemplateVertexColor = new Color(0.8f, 0.1f, 0.1f, 1f);
        private static readonly Vector2 TemplateUv1 = new Vector2(0.3f, 0.5f);
        private static readonly Vector4 TemplateFade = new Vector4(0.6f, 0f, 0f, 0f);
        private const float Tolerance = 0.025f;

        /// <summary>
        /// Renders each template on a full-view quad into a linear 64 x 64 RenderTexture through a temporary orthographic
        /// camera and checks the pixels. Scene (camera at z = -10 looking +z, view [-1, 1]^2, clear blue):
        /// a white URP Unlit occluder in FRONT of the template on the left half (queue 1990, so drawn before it), the
        /// template quad at z = 0 (vertex color (0.8, 0.1, 0.1, 1), uv1 (0.3, 0.5), _PIO_PlayerFade.x = 0.6), and a green
        /// URP Unlit quad BEHIND the template on the bottom-right quadrant drawn after it (queue 3100, ZTest LEqual).
        /// Template color T = (vertex r, uv1.x, fade.x) = (0.8, 0.3, 0.6), alpha a = vertex a * uv1.y = 0.5.
        /// Opaque: left = T (ZTest Always: drawn over the nearer occluder), top-right = T, bottom-right = green (ZWrite off:
        /// the farther green still passes its depth test). Transparent: left = T a + white (1 - a), top-right =
        /// T a + blue (1 - a), bottom-right = green. Writes TestResults/B0b_render_&lt;template&gt;.png for a visual check.
        /// </summary>
        public static bool RenderTemplates(string shotDir = "TestResults")
        {
            var failures = new List<string>();
            bool asyncBefore = ShaderUtil.allowAsyncCompilation;
            ShaderUtil.allowAsyncCompilation = false;
            Vector4 fadeBefore = Shader.GetGlobalVector("_PIO_PlayerFade");
            var created = new List<UnityEngine.Object>();
            RenderTexture rt = null;
            using var errors = new LoggedErrors(failures, "template render check");
            try
            {
                EnsureUniversalPipelineActive();
                Shader unlit = AssetDatabase.LoadAssetAtPath<Shader>(UrpUnlitPath);
                if (unlit == null)
                {
                    Fail(failures, UrpUnlitPath + " not found (editor helper for the occluders)");
                    return false;
                }
                rt = new RenderTexture(new RenderTextureDescriptor(TestSize, TestSize, GraphicsFormat.R8G8B8A8_UNorm, 24))
                {
                    name = "PIO_TemplateCheck",
                    filterMode = FilterMode.Point,
                    hideFlags = HideFlags.HideAndDontSave,
                };
                rt.Create();

                var cameraObject = Track(created, new GameObject("PIO_TemplateCheckCamera"));
                var camera = cameraObject.AddComponent<Camera>();
                camera.orthographic = true;
                camera.orthographicSize = 1f;
                camera.aspect = 1f;
                camera.transform.position = new Vector3(0f, 0f, -10f);
                camera.transform.rotation = Quaternion.identity;
                camera.nearClipPlane = 0.1f;
                camera.farClipPlane = 50f;
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0f, 0f, 1f, 1f);
                camera.cullingMask = 1 << TestLayer;
                camera.allowHDR = false;
                camera.allowMSAA = false;
                camera.useOcclusionCulling = false;
                camera.targetTexture = rt;
                camera.enabled = false;

                Material white = Track(created, new Material(unlit) { name = "PIO_CheckWhite" });
                white.SetColor("_BaseColor", Color.white);
                white.renderQueue = 1990;
                Material green = Track(created, new Material(unlit) { name = "PIO_CheckGreen" });
                green.SetColor("_BaseColor", Color.green);
                green.renderQueue = 3100;

                MakeQuad(created, "PIO_CheckWhiteQuad", new Rect(-1.2f, -1.2f, 1.2f, 2.4f), -1f, white, Color.white, Vector2.zero);
                MakeQuad(created, "PIO_CheckGreenQuad", new Rect(0f, -1.2f, 1.2f, 1.2f), 0.5f, green, Color.white, Vector2.zero);

                Shader.SetGlobalVector("_PIO_PlayerFade", TemplateFade);
                Color t = new Color(TemplateVertexColor.r, TemplateUv1.x, TemplateFade.x, 1f);
                float a = TemplateVertexColor.a * TemplateUv1.y;

                foreach (string name in TemplateNames)
                {
                    string path = TemplateFolder + "/" + name + ".shadergraph";
                    Shader shader = AssetDatabase.LoadAssetAtPath<Shader>(path);
                    if (shader == null)
                    {
                        Fail(failures, path + ": not imported as a Shader");
                        continue;
                    }
                    bool transparent = name.Contains("Transparent");
                    Material material = Track(created, new Material(shader) { name = "PIO_Check_" + name });
                    GameObject quad = MakeQuad(created, "PIO_CheckTemplate_" + name, new Rect(-1.2f, -1.2f, 2.4f, 2.4f), 0f,
                        material, TemplateVertexColor, TemplateUv1);

                    // The first render of a fresh editor can come out wrong while shaders warm up: throw one away.
                    camera.Render();
                    camera.Render();
                    Texture2D pixels = ReadBack(rt);
                    created.Add(pixels);
                    SaveShot(pixels, shotDir, name);

                    Color left = transparent ? Blend(t, Color.white, a) : t;
                    Color topRight = transparent ? Blend(t, new Color(0f, 0f, 1f, 1f), a) : t;
                    CheckRegion(failures, name, "left (ZTest Always over a nearer occluder)", pixels, 16, 32, left);
                    CheckRegion(failures, name, "top-right", pixels, 48, 48, topRight);
                    CheckRegion(failures, name, "bottom-right (ZWrite off: a farther quad drawn later shows)", pixels, 48, 16, Color.green);

                    UnityEngine.Object.DestroyImmediate(quad);
                }
            }
            catch (Exception e)
            {
                Fail(failures, "render check threw: " + e);
            }
            finally
            {
                Shader.SetGlobalVector("_PIO_PlayerFade", fadeBefore);
                for (int i = created.Count - 1; i >= 0; i--)
                {
                    if (created[i] != null)
                    {
                        UnityEngine.Object.DestroyImmediate(created[i]);
                    }
                }
                if (rt != null)
                {
                    rt.Release();
                    UnityEngine.Object.DestroyImmediate(rt);
                }
                ShaderUtil.allowAsyncCompilation = asyncBefore;
            }
            errors.Flush();
            bool ok = failures.Count == 0;
            Debug.Log($"{LogTag}{(ok ? "PASS" : "FAIL")} template render check: {failures.Count} failure(s)");
            return ok;
        }

        // -------------------------------------------------------------------------------------------------------------
        // Render check of the actor field contributors
        // -------------------------------------------------------------------------------------------------------------

        private const float FieldScale = 0.5f;          // _PIO_ActorScale during the check (proves the multiply)
        private const float FieldTolerance = 0.01f;     // half-float RT

        /// <summary>
        /// Renders FieldBlob and FieldStroke (from Resources/Shaders) into a 64 x 64 R16G16B16A16_SFloat RenderTexture cleared
        /// to (0, 0, 0, 0), with the camera settings of ActorFieldCamera (contract 12.2: allowHDR off, MSAA off, no post), view
        /// [-1, 1]^2 and _PIO_ActorScale = 0.5, then compares pixels with the contract formulas:
        /// blobs (LiquidLayers-style quad scaled to [-1, 1]^2): one with _Channel (1,0,0,0) _Amplitude 1, two with
        /// (0,0,0,1) amplitude 0.8 (additive alpha as data): R = 1 f(q) 0.5, A = 2 x 0.8 f(q) 0.5 with f(q) = saturate(1 - |q|^2)^2;
        /// stroke (triangle list in world space, identity transform, y in [-0.5, 0.5], uv0.y = cross coordinate -1..1, uv0.x
        /// = amplitude multiplier 1 at the left end to 0.5 at the right end) with _Channel (0,1,0,0) amplitude 0.6:
        /// G = 0.6 m(x) saturate(1 - c^2)^2 0.5. Writes TestResults/B0b_render_Field*.png (R, G, A shown as R, G, B).
        /// </summary>
        public static bool RenderFieldContributors(string shotDir = "TestResults")
        {
            var failures = new List<string>();
            bool asyncBefore = ShaderUtil.allowAsyncCompilation;
            ShaderUtil.allowAsyncCompilation = false;
            float scaleBefore = Shader.GetGlobalFloat("_PIO_ActorScale");
            var created = new List<UnityEngine.Object>();
            RenderTexture rt = null;
            using var errors = new LoggedErrors(failures, "field render check");
            try
            {
                EnsureUniversalPipelineActive();
                Shader blob = AssetDatabase.LoadAssetAtPath<Shader>(ShaderFolder + "/FieldBlob.shader");
                Shader stroke = AssetDatabase.LoadAssetAtPath<Shader>(ShaderFolder + "/FieldStroke.shader");
                if (blob == null || stroke == null)
                {
                    Fail(failures, "FieldBlob.shader or FieldStroke.shader missing from " + ShaderFolder);
                    return false;
                }
                GraphicsFormat format = GraphicsFormat.R16G16B16A16_SFloat;
                if (!SystemInfo.IsFormatSupported(format, GraphicsFormatUsage.Blend))
                {
                    Fail(failures, "R16G16B16A16_SFloat blending unsupported on this editor device");
                    return false;
                }
                // URP 17 Render Graph refuses a camera output texture without depth ("the output Render Texture must have a
                // depth buffer"; nothing is drawn). The actor field RT of ActorFieldCamera needs one too (16 bits is enough).
                rt = new RenderTexture(new RenderTextureDescriptor(TestSize, TestSize, format, 16))
                {
                    name = "PIO_FieldCheck",
                    filterMode = FilterMode.Point,
                    hideFlags = HideFlags.HideAndDontSave,
                };
                rt.Create();

                var cameraObject = Track(created, new GameObject("PIO_FieldCheckCamera"));
                var camera = cameraObject.AddComponent<Camera>();
                camera.orthographic = true;
                camera.orthographicSize = 1f;
                camera.aspect = 1f;
                camera.transform.position = new Vector3(0f, 0f, -10f);
                camera.transform.rotation = Quaternion.identity;
                camera.nearClipPlane = 0.1f;
                camera.farClipPlane = 50f;
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0f, 0f, 0f, 0f);
                camera.cullingMask = 1 << TestLayer;
                camera.allowHDR = false;
                camera.allowMSAA = false;
                camera.useOcclusionCulling = false;
                camera.targetTexture = rt;
                camera.enabled = false;

                Shader.SetGlobalFloat("_PIO_ActorScale", FieldScale);

                // Blobs: the quad of LiquidLayers.QuadMesh (+/-0.5, uv0 in [0,1]^2) scaled by 2 covers the view exactly.
                Material blobMaterial = Track(created, new Material(blob) { name = "PIO_CheckFieldBlob" });
                Mesh quad = Track(created, BuildUnitQuad());
                var blobs = new List<GameObject>
                {
                    MakeFieldRenderer(created, "PIO_CheckBlobR", quad, blobMaterial, new Vector3(2f, 2f, 1f), new Vector4(1, 0, 0, 0), 1f),
                    MakeFieldRenderer(created, "PIO_CheckBlobA1", quad, blobMaterial, new Vector3(2f, 2f, 1f), new Vector4(0, 0, 0, 1), 0.8f),
                    MakeFieldRenderer(created, "PIO_CheckBlobA2", quad, blobMaterial, new Vector3(2f, 2f, 1f), new Vector4(0, 0, 0, 1), 0.8f),
                };
                camera.Render();
                camera.Render();
                Texture2D blobPixels = ReadBackFloat(rt);
                created.Add(blobPixels);
                SaveFieldShot(created, blobPixels, shotDir, "FieldBlob");
                int[,] blobSamples = { { 32, 32 }, { 48, 32 }, { 40, 52 }, { 20, 14 }, { 2, 2 } };
                for (int k = 0; k < blobSamples.GetLength(0); k++)
                {
                    int px = blobSamples[k, 0];
                    int py = blobSamples[k, 1];
                    Vector2 w = PixelToWorld(px, py);
                    float s = Mathf.Clamp01(1f - w.sqrMagnitude);
                    float f = s * s;
                    var expected = new Vector4(1f * f * FieldScale, 0f, 0f, 2f * 0.8f * f * FieldScale);
                    CheckField(failures, "FieldBlob", blobPixels, px, py, expected);
                }
                foreach (GameObject go in blobs)
                {
                    UnityEngine.Object.DestroyImmediate(go);
                }

                // Stroke: one straight strip, 3 sample columns, vertices only on the two edges (cross coordinate -1 / +1).
                Material strokeMaterial = Track(created, new Material(stroke) { name = "PIO_CheckFieldStroke" });
                Mesh strip = Track(created, BuildStrokeStrip());
                MakeFieldRenderer(created, "PIO_CheckStroke", strip, strokeMaterial, Vector3.one, new Vector4(0, 1, 0, 0), 0.6f);
                camera.Render();
                camera.Render();
                Texture2D strokePixels = ReadBackFloat(rt);
                created.Add(strokePixels);
                SaveFieldShot(created, strokePixels, shotDir, "FieldStroke");
                int[,] strokeSamples = { { 32, 32 }, { 8, 36 }, { 56, 28 }, { 44, 40 }, { 32, 56 }, { 20, 8 } };
                for (int k = 0; k < strokeSamples.GetLength(0); k++)
                {
                    int px = strokeSamples[k, 0];
                    int py = strokeSamples[k, 1];
                    Vector2 w = PixelToWorld(px, py);
                    float c = w.y / StripHalfWidth;
                    float s = Mathf.Clamp01(1f - c * c);
                    float multiplier = Mathf.Lerp(1f, 0.5f, (w.x - StripXMin) / (StripXMax - StripXMin));
                    float g = Mathf.Abs(c) >= 1f ? 0f : 0.6f * multiplier * s * s * FieldScale;
                    CheckField(failures, "FieldStroke", strokePixels, px, py, new Vector4(0f, g, 0f, 0f));
                }
            }
            catch (Exception e)
            {
                Fail(failures, "field render check threw: " + e);
            }
            finally
            {
                Shader.SetGlobalFloat("_PIO_ActorScale", scaleBefore);
                for (int i = created.Count - 1; i >= 0; i--)
                {
                    if (created[i] != null)
                    {
                        UnityEngine.Object.DestroyImmediate(created[i]);
                    }
                }
                if (rt != null)
                {
                    rt.Release();
                    UnityEngine.Object.DestroyImmediate(rt);
                }
                ShaderUtil.allowAsyncCompilation = asyncBefore;
            }
            errors.Flush();
            bool ok = failures.Count == 0;
            Debug.Log($"{LogTag}{(ok ? "PASS" : "FAIL")} field contributor render check: {failures.Count} failure(s)");
            return ok;
        }

        /// <summary>
        /// Collects every Error, Exception and Assert logged while it is alive (render graph errors are only logged, the
        /// render itself does not throw) and turns them into failures on Flush.
        /// </summary>
        private sealed class LoggedErrors : IDisposable
        {
            private readonly List<string> failures;
            private readonly string context;
            private readonly List<string> messages = new List<string>();
            private bool flushed;

            public LoggedErrors(List<string> failures, string context)
            {
                this.failures = failures;
                this.context = context;
                Application.logMessageReceivedThreaded += OnLog;
            }

            private void OnLog(string message, string stack, LogType type)
            {
                if ((type == LogType.Error || type == LogType.Exception || type == LogType.Assert)
                    && (message == null || !message.StartsWith(LogTag, StringComparison.Ordinal)))
                {
                    lock (messages)
                    {
                        messages.Add(message);
                    }
                }
            }

            public void Flush()
            {
                if (flushed)
                {
                    return;
                }
                flushed = true;
                Application.logMessageReceivedThreaded -= OnLog;
                lock (messages)
                {
                    foreach (string message in messages)
                    {
                        Fail(failures, $"{context}: error logged: {FirstLine(message)}");
                    }
                }
            }

            public void Dispose()
            {
                Flush();
            }
        }

        private const float StripXMin = -1.2f;
        private const float StripXMax = 1.2f;
        private const float StripHalfWidth = 0.5f;

        private static Vector2 PixelToWorld(int px, int py)
        {
            return new Vector2((px + 0.5f) / TestSize * 2f - 1f, (py + 0.5f) / TestSize * 2f - 1f);
        }

        /// <summary>Same layout as LiquidLayers.QuadMesh: vertices (+/-0.5, +/-0.5, 0), uv0 in [0,1]^2, 2 triangles.</summary>
        private static Mesh BuildUnitQuad()
        {
            var mesh = new Mesh { name = "PIO_CheckUnitQuad" };
            mesh.SetVertices(new List<Vector3>
            {
                new Vector3(-0.5f, -0.5f, 0f), new Vector3(0.5f, -0.5f, 0f), new Vector3(0.5f, 0.5f, 0f), new Vector3(-0.5f, 0.5f, 0f),
            });
            mesh.SetUVs(0, new List<Vector2> { new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1) });
            mesh.SetTriangles(new[] { 0, 2, 1, 0, 3, 2 }, 0);
            mesh.RecalculateBounds();
            return mesh;
        }

        /// <summary>FieldStroke mesh convention: triangle list, world-space vertices, uv0 = (amplitude multiplier, cross).</summary>
        private static Mesh BuildStrokeStrip()
        {
            var vertices = new List<Vector3>();
            var uvs = new List<Vector2>();
            float[] xs = { StripXMin, 0f, StripXMax };
            foreach (float x in xs)
            {
                float multiplier = Mathf.Lerp(1f, 0.5f, (x - StripXMin) / (StripXMax - StripXMin));
                vertices.Add(new Vector3(x, -StripHalfWidth, 0f));
                uvs.Add(new Vector2(multiplier, -1f));
                vertices.Add(new Vector3(x, StripHalfWidth, 0f));
                uvs.Add(new Vector2(multiplier, 1f));
            }
            var triangles = new List<int>();
            for (int i = 0; i + 1 < xs.Length; i++)
            {
                int a = 2 * i;
                triangles.AddRange(new[] { a, a + 1, a + 3, a, a + 3, a + 2 });
            }
            var mesh = new Mesh { name = "PIO_CheckStrokeStrip" };
            mesh.SetVertices(vertices);
            mesh.SetUVs(0, uvs);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateBounds();
            return mesh;
        }

        private static GameObject MakeFieldRenderer(List<UnityEngine.Object> created, string name, Mesh mesh, Material material,
            Vector3 scale, Vector4 channel, float amplitude)
        {
            var go = Track(created, new GameObject(name));
            go.layer = TestLayer;
            go.transform.position = Vector3.zero;
            go.transform.localScale = scale;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            var block = new MaterialPropertyBlock();
            block.SetVector("_Channel", channel);
            block.SetFloat("_Amplitude", amplitude);
            renderer.SetPropertyBlock(block);
            return go;
        }

        private static Texture2D ReadBackFloat(RenderTexture rt)
        {
            RenderTexture previous = RenderTexture.active;
            var texture = new Texture2D(rt.width, rt.height, TextureFormat.RGBAFloat, false, true)
            {
                hideFlags = HideFlags.HideAndDontSave,
            };
            try
            {
                RenderTexture.active = rt;
                texture.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
                texture.Apply();
            }
            finally
            {
                RenderTexture.active = previous;
            }
            return texture;
        }

        private static void CheckField(List<string> failures, string shader, Texture2D pixels, int px, int py, Vector4 expected)
        {
            Color c = pixels.GetPixel(px, py);
            var got = new Vector4(c.r, c.g, c.b, c.a);
            if ((got - expected).magnitude > FieldTolerance)
            {
                Fail(failures, $"{shader}: pixel ({px}, {py}) = {got.ToString("F4")}, expected {expected.ToString("F4")}");
                return;
            }
            Debug.Log($"{LogTag}{shader} pixel ({px}, {py}): OK {got.ToString("F4")}");
        }

        private static void SaveFieldShot(List<UnityEngine.Object> created, Texture2D pixels, string dir, string name)
        {
            var view = Track(created, new Texture2D(pixels.width, pixels.height, TextureFormat.RGBA32, false, true));
            for (int y = 0; y < pixels.height; y++)
            {
                for (int x = 0; x < pixels.width; x++)
                {
                    Color c = pixels.GetPixel(x, y);
                    view.SetPixel(x, y, new Color(c.r, c.g, c.a, 1f));
                }
            }
            view.Apply();
            SaveShot(view, dir, name);
        }

        private static T Track<T>(List<UnityEngine.Object> created, T obj) where T : UnityEngine.Object
        {
            obj.hideFlags = HideFlags.HideAndDontSave;
            created.Add(obj);
            return obj;
        }

        private static GameObject MakeQuad(List<UnityEngine.Object> created, string name, Rect rect, float z, Material material,
            Color vertexColor, Vector2 uv1)
        {
            var mesh = Track(created, new Mesh { name = name + "_Mesh" });
            mesh.SetVertices(new List<Vector3>
            {
                new Vector3(rect.xMin, rect.yMin, 0f), new Vector3(rect.xMax, rect.yMin, 0f),
                new Vector3(rect.xMax, rect.yMax, 0f), new Vector3(rect.xMin, rect.yMax, 0f),
            });
            mesh.SetUVs(0, new List<Vector2> { new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1) });
            mesh.SetUVs(1, new List<Vector2> { uv1, uv1, uv1, uv1 });
            mesh.SetColors(new List<Color> { vertexColor, vertexColor, vertexColor, vertexColor });
            mesh.SetNormals(new List<Vector3> { Vector3.back, Vector3.back, Vector3.back, Vector3.back });
            mesh.SetTriangles(new[] { 0, 2, 1, 0, 3, 2 }, 0);
            mesh.RecalculateBounds();
            var go = Track(created, new GameObject(name));
            go.layer = TestLayer;
            go.transform.position = new Vector3(0f, 0f, z);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            renderer.sharedMaterial = material;
            renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            renderer.receiveShadows = false;
            return go;
        }

        private static Texture2D ReadBack(RenderTexture rt)
        {
            RenderTexture previous = RenderTexture.active;
            var texture = new Texture2D(rt.width, rt.height, TextureFormat.RGBA32, false, true)
            {
                hideFlags = HideFlags.HideAndDontSave,
            };
            try
            {
                RenderTexture.active = rt;
                texture.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
                texture.Apply();
            }
            finally
            {
                RenderTexture.active = previous;
            }
            return texture;
        }

        private static void SaveShot(Texture2D pixels, string dir, string name)
        {
            try
            {
                Directory.CreateDirectory(dir);
                string file = Path.Combine(dir, "B0b_render_" + name + ".png");
                File.WriteAllBytes(file, pixels.EncodeToPNG());
                Debug.Log(LogTag + "wrote " + file);
            }
            catch (Exception e)
            {
                Debug.LogWarning(LogTag + "could not save the render of " + name + ": " + e.Message);
            }
        }

        private static Color Blend(Color source, Color destination, float alpha)
        {
            return new Color(
                source.r * alpha + destination.r * (1f - alpha),
                source.g * alpha + destination.g * (1f - alpha),
                source.b * alpha + destination.b * (1f - alpha),
                1f);
        }

        private static void CheckRegion(List<string> failures, string template, string region, Texture2D pixels, int cx, int cy,
            Color expected)
        {
            // Five samples around the region center (all inside the region).
            int[,] offsets = { { 0, 0 }, { -6, -6 }, { 6, -6 }, { -6, 6 }, { 6, 6 } };
            for (int k = 0; k < offsets.GetLength(0); k++)
            {
                Color c = pixels.GetPixel(cx + offsets[k, 0], cy + offsets[k, 1]);
                if (Mathf.Abs(c.r - expected.r) > Tolerance || Mathf.Abs(c.g - expected.g) > Tolerance
                    || Mathf.Abs(c.b - expected.b) > Tolerance)
                {
                    Fail(failures, $"{template} {region}: pixel ({cx + offsets[k, 0]}, {cy + offsets[k, 1]}) = {Format(c)}, expected {Format(expected)}");
                    return;
                }
            }
            Debug.Log($"{LogTag}{template} {region}: OK {Format(pixels.GetPixel(cx, cy))}");
        }

        // -------------------------------------------------------------------------------------------------------------

        private static string Format(Color c)
        {
            return $"({c.r:0.000}, {c.g:0.000}, {c.b:0.000})";
        }

        private static string FirstLine(string message)
        {
            if (string.IsNullOrEmpty(message))
            {
                return "";
            }
            int newline = message.IndexOf('\n');
            return newline < 0 ? message : message.Substring(0, newline);
        }

        private static void Fail(List<string> failures, string message)
        {
            failures.Add(message);
            Debug.LogError(LogTag + "FAIL " + message);
        }
    }
}
