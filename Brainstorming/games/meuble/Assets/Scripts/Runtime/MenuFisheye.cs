using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.RenderGraphModule;
using UnityEngine.Rendering.RenderGraphModule.Util;
using UnityEngine.Rendering.Universal;

namespace OutOfSight
{
    /// <summary>
    /// FISHEYE (docs/next/progress/FISHEYE.md): a barrel distortion and a peripheral blur (sharp centre, soft or
    /// radially streaked edges) on the title menu's moving 3D background (the <see cref="TitleCameraTour"/>), and
    /// nothing else. Both are in the same pass and the same shader; the blur's taps are skipped where it is 0.
    /// - How: no renderer asset changes. While the tour is <see cref="TitleCameraTour.Active"/>, this component enqueues
    ///   <see cref="MenuFisheyePass"/> on the tour camera's own renderer from RenderPipelineManager.beginCameraRendering,
    ///   for that camera only. The pass is one full-screen Render Graph blit after post-processing; the menu canvas, the
    ///   title logo (its own camera, a texture shown by an overlay canvas) and the HUD are overlay UI drawn after the final
    ///   blit, so they are never distorted. In a level (the tour inactive) nothing is enqueued: gameplay renders exactly as
    ///   before on PC_Renderer and Mobile_Renderer.
    /// - Values: <see cref="MenuCameraSettings"/>, from StreamingAssets/menu_camera.json, read when the title opens over the
    ///   title house and, while it stays open, read again whenever the file's write time changes (checked every
    ///   <see cref="CheckSeconds"/> s, a stat call, no read when unchanged).
    /// - The shader (Assets/Settings/MenuFisheye.shader) is created from code, so it is in Always Included Shaders
    ///   (ProjectSetup). Missing or unsupported: the effect is off with one warning.
    /// </summary>
    [DefaultExecutionOrder(260)] // after TitleCameraTour (250), which sets Active in its LateUpdate
    public sealed class MenuFisheye : MonoBehaviour
    {
        public const string ShaderName = "OutOfSight/Menu Fisheye";

        /// <summary>How often the open title checks whether menu_camera.json changed, in seconds.</summary>
        public const float CheckSeconds = 2f;

        /// <summary>Tests: the last frame the pass was enqueued, and for which camera.</summary>
        public static int EnqueuedFrame { get; private set; } = -1;
        public static Camera EnqueuedCamera { get; private set; }

        /// <summary>Tests: how many times the pass was enqueued, all cameras together.</summary>
        public static int EnqueuedCount { get; private set; }

        /// <summary>Tests: the last frame <see cref="MenuFisheyePass"/> was recorded into a render graph (it really ran in the renderer).</summary>
        public static int RecordedFrame { get; internal set; } = -1;

        /// <summary>Tests: the last values sent to the shader, (strength, fit, vignette, unused) and (centre x, centre y, aspect, 1 / r2 max).</summary>
        public static Vector4 LastParams { get; internal set; }
        public static Vector4 LastLens { get; internal set; }

        /// <summary>Tests: the last peripheral blur values sent to the shader (strength, clear radius, motion, unused).</summary>
        public static Vector4 LastBlur { get; internal set; }

        /// <summary>The values in use (the built-in defaults until the title first opens).</summary>
        public MenuCameraSettings Settings { get; private set; } = MenuCameraSettings.Defaults;

        /// <summary>How many times the file was read (tests).</summary>
        public int Loads { get; private set; }

        /// <summary>True while the tour runs, the values do something and the shader is usable: the pass is enqueued.</summary>
        public bool Active => tour != null && tour.Active && Settings.Visible && pass != null;

        private TitleCameraTour tour;
        private Camera view;
        private Material material;
        private MenuFisheyePass pass;
        private bool wasActive;
        private float checkClock;
        private DateTime stamp;
        private static bool warned;

        /// <summary>Adds the effect to the tour's camera (once).</summary>
        public static MenuFisheye Attach(TitleCameraTour tour)
        {
            if (tour == null)
            {
                return null;
            }
            MenuFisheye fisheye = tour.GetComponent<MenuFisheye>();
            if (fisheye == null)
            {
                fisheye = tour.gameObject.AddComponent<MenuFisheye>();
            }
            return fisheye;
        }

        private void Awake()
        {
            tour = GetComponent<TitleCameraTour>();
            view = GetComponent<Camera>();
            Shader shader = Shader.Find(ShaderName);
            if (shader == null || !shader.isSupported)
            {
                if (!warned)
                {
                    warned = true;
                    Debug.LogWarning($"[MenuCamera] shader {ShaderName} {(shader == null ? "missing" : "unsupported")}: no fish-eye on the title");
                }
                return;
            }
            material = new Material(shader) { name = "Menu Fisheye", hideFlags = HideFlags.HideAndDontSave };
            pass = new MenuFisheyePass(material);
        }

        private void OnEnable()
        {
            RenderPipelineManager.beginCameraRendering += OnBeginCamera;
        }

        private void OnDisable()
        {
            RenderPipelineManager.beginCameraRendering -= OnBeginCamera;
        }

        private void OnDestroy()
        {
            if (material != null)
            {
                Destroy(material);
            }
        }

        private void LateUpdate()
        {
            bool open = tour != null && tour.Active;
            if (open && !wasActive)
            {
                // The title just opened over the title house: read the file again.
                Reload();
            }
            else if (open)
            {
                checkClock += Time.unscaledDeltaTime;
                if (checkClock >= CheckSeconds)
                {
                    checkClock = 0f;
                    if (WriteTime(MenuCameraSettings.FilePath) != stamp)
                    {
                        Reload();
                        Debug.Log($"[MenuCamera] {MenuCameraSettings.FilePath} changed: {Settings}");
                    }
                }
            }
            wasActive = open;
        }

        /// <summary>Reads menu_camera.json now (the title's opening does it; tests call it directly).</summary>
        public void Reload()
        {
            checkClock = 0f;
            stamp = WriteTime(MenuCameraSettings.FilePath);
            Settings = MenuCameraSettings.Load();
            Loads++;
        }

        private static DateTime WriteTime(string path)
        {
            try
            {
                return path != null && File.Exists(path) ? File.GetLastWriteTimeUtc(path) : DateTime.MinValue;
            }
            catch (Exception)
            {
                return DateTime.MinValue;
            }
        }

        private void OnBeginCamera(ScriptableRenderContext context, Camera cam)
        {
            // Only the tour's own camera, only while the title is open over the title house.
            if (cam != view || !Active)
            {
                return;
            }
            UniversalAdditionalCameraData data = cam.GetUniversalAdditionalCameraData();
            ScriptableRenderer renderer = data != null ? data.scriptableRenderer : null;
            if (renderer == null)
            {
                return;
            }
            pass.Settings = Settings;
            renderer.EnqueuePass(pass);
            EnqueuedFrame = Time.frameCount;
            EnqueuedCamera = cam;
            EnqueuedCount++;
        }

        /// <summary>
        /// The source uv an output pixel at <paramref name="uv"/> samples (the shader's formula): with d = uv - centre and
        /// r2 its squared radius in screen heights over the farthest corner's, centre + d * (1 + k r2) / ((1 + k) zoom).
        /// </summary>
        public static Vector2 SourceUv(Vector2 uv, Vector2 centre, float aspect, float strength, float zoom)
        {
            float k = Mathf.Max(0f, strength);
            float inv = 1f / FarthestCornerSquared(centre, aspect);
            Vector2 d = uv - centre;
            float r2 = (d.x * d.x * aspect * aspect + d.y * d.y) * inv;
            return centre + d * ((1f + k * r2) / ((1f + k) * Mathf.Max(0.01f, zoom)));
        }

        /// <summary>The squared distance, in screen heights, from <paramref name="centre"/> to the farthest screen corner.</summary>
        public static float FarthestCornerSquared(Vector2 centre, float aspect)
        {
            float dx = Mathf.Max(centre.x, 1f - centre.x) * aspect;
            float dy = Mathf.Max(centre.y, 1f - centre.y);
            return Mathf.Max(1e-6f, dx * dx + dy * dy);
        }

        /// <summary>The lens centre in uv: the camera's optical axis (the tour's lens shift moves it right of the middle).</summary>
        public static Vector2 LensCentre(Matrix4x4 projection)
        {
            // NDC x of the axis is -m[0, 2] (the tour writes m[0, 2] = -Tuning.TitleTourLensShift), likewise for y.
            return new Vector2(Mathf.Clamp01(0.5f - 0.5f * projection[0, 2]), Mathf.Clamp01(0.5f - 0.5f * projection[1, 2]));
        }
    }

    /// <summary>
    /// FISHEYE: the full-screen pass, Render Graph only (Unity 6). It blits the camera colour through the fish-eye material
    /// into one pooled texture of the same size (no MSAA, no depth) and makes that texture the camera colour, so the final
    /// blit reads it: one full-screen draw, no copy back. It asks for an intermediate colour texture so a camera that would
    /// draw straight to the back buffer (no post-processing on a phone) still has one to read.
    /// </summary>
    public sealed class MenuFisheyePass : ScriptableRenderPass
    {
        private static readonly int ParamsId = Shader.PropertyToID("_FisheyeParams");
        private static readonly int LensId = Shader.PropertyToID("_FisheyeLens");
        private static readonly int BlurId = Shader.PropertyToID("_FisheyeBlur");


        public MenuCameraSettings Settings;
        private readonly Material material;
        private static bool warnedBackBuffer;

        public MenuFisheyePass(Material material)
        {
            this.material = material;
            renderPassEvent = RenderPassEvent.AfterRenderingPostProcessing;
            requiresIntermediateTexture = true;
            profilingSampler = new ProfilingSampler("Menu Fisheye");
        }

        public override void RecordRenderGraph(RenderGraph renderGraph, ContextContainer frameData)
        {
            UniversalResourceData resources = frameData.Get<UniversalResourceData>();
            UniversalCameraData cameraData = frameData.Get<UniversalCameraData>();
            if (resources.isActiveTargetBackBuffer)
            {
                if (!warnedBackBuffer)
                {
                    warnedBackBuffer = true;
                    Debug.LogWarning("[MenuCamera] the title camera draws straight to the back buffer: no fish-eye");
                }
                return;
            }
            MenuCameraSettings s = Settings ?? MenuCameraSettings.Defaults;
            RenderTextureDescriptor target = cameraData.cameraTargetDescriptor;
            float aspect = target.height > 0 ? target.width / (float)target.height : 16f / 9f;
            Vector2 centre = MenuFisheye.LensCentre(cameraData.camera.projectionMatrix);
            float k = s.FisheyeStrength;
            var parameters = new Vector4(k, 1f / ((1f + k) * s.FisheyeZoom), s.FisheyeVignette, 0f);
            var lens = new Vector4(centre.x, centre.y, aspect, 1f / MenuFisheye.FarthestCornerSquared(centre, aspect));
            material.SetVector(ParamsId, parameters);
            var blur = new Vector4(s.PeripheralBlur, s.PeripheralBlurRadius, s.PeripheralBlurMotion, 0f);
            material.SetVector(LensId, lens);
            material.SetVector(BlurId, blur);
            MenuFisheye.LastParams = parameters;
            MenuFisheye.LastLens = lens;
            MenuFisheye.LastBlur = blur;

            TextureHandle source = resources.activeColorTexture;
            TextureDesc desc = renderGraph.GetTextureDesc(source);
            desc.name = "_MenuFisheyeColor";
            desc.clearBuffer = false;
            desc.msaaSamples = MSAASamples.None;
            desc.bindTextureMS = false;
            TextureHandle destination = renderGraph.CreateTexture(desc);
            renderGraph.AddBlitPass(new RenderGraphUtils.BlitMaterialParameters(source, destination, material, 0), "Menu Fisheye");
            resources.cameraColor = destination;
            MenuFisheye.RecordedFrame = Time.frameCount;
        }
    }

    /// <summary>
    /// FISHEYE: the title camera's tunable values, read from an optional JSON file so they can be tuned on Windows without
    /// a rebuild (the pattern of <see cref="CardNumberSettings"/>): StreamingAssets/menu_camera.json (in a Windows build:
    /// OutOfSight_Data/StreamingAssets/menu_camera.json; in the editor: Assets/StreamingAssets/menu_camera.json, shipped
    /// with these defaults). A missing file, a missing key, a wrong type or bad JSON falls back to the built-in default
    /// with a warning; every value is clamped. On Android the file is inside the APK and is not read: the built-in
    /// defaults (the shipped file's values) apply.
    /// </summary>
    public sealed class MenuCameraSettings
    {
        public const string FileName = "menu_camera.json";

        /// <summary>Tests only: a file to read instead of StreamingAssets/menu_camera.json.</summary>
        public static string PathOverride;

        /// <summary>The built-in values (the shipped file carries the same).</summary>
        public static readonly MenuCameraSettings Defaults = new MenuCameraSettings();

        public const float MaxStrength = 1f;
        public const float MinZoom = 0.5f;
        public const float MaxZoom = 2f;

        /// <summary>fisheyeStrength: the barrel coefficient k, 0 (off) to 1; the centre shows 1 + k times larger than the corners.</summary>
        public float FisheyeStrength { get; private set; } = 0.3f;

        /// <summary>fisheyeZoom: 1 = auto-fit (the farthest corner on its corner: no black, no stretched edge), above 1 crops more, below 1 shows black borders; 0.5 to 2.</summary>
        public float FisheyeZoom { get; private set; } = 1f;

        /// <summary>fisheyeVignette: darkening towards the corners, 0 (none) to 1.</summary>
        public float FisheyeVignette { get; private set; } = 0.2f;

        /// <summary>peripheralBlur: the blur of the periphery (the centre stays sharp), 0 (off, no extra tap) to 1.</summary>
        public float PeripheralBlur { get; private set; } = 0.3f;

        /// <summary>
        /// peripheralBlurRadius: the sharp centre's size, where the blur starts, as a share of the way from the lens centre
        /// to the screen's edge on each side (each corner is 1, the middle of each edge 0.71), 0 to 1; the blur then ramps
        /// up smoothly over 0.45 more.
        /// </summary>
        public float PeripheralBlurRadius { get; private set; } = 0.4f;

        /// <summary>peripheralBlurMotion: 0 = a plain soft blur, 1 = a radial (zoom) streak, in between a mix; 0 to 1.</summary>
        public float PeripheralBlurMotion { get; private set; } = 0.6f;

        /// <summary>True when the pass changes the picture at all.</summary>
        public bool Visible => FisheyeStrength > 0f || FisheyeVignette > 0f || !Mathf.Approximately(FisheyeZoom, 1f) || PeripheralBlur > 0f;

        /// <summary>The file read on this platform, or null where it is not read (Android: inside the APK).</summary>
        public static string FilePath
        {
            get
            {
                if (!string.IsNullOrEmpty(PathOverride))
                {
                    return PathOverride;
                }
                return Application.platform == RuntimePlatform.Android ? null : Path.Combine(Application.streamingAssetsPath, FileName);
            }
        }

        public override string ToString()
        {
            return string.Format(CultureInfo.InvariantCulture,
                "fisheyeStrength {0}, fisheyeZoom {1}, fisheyeVignette {2}, peripheralBlur {3}, peripheralBlurRadius {4}, peripheralBlurMotion {5}",
                FisheyeStrength, FisheyeZoom, FisheyeVignette, PeripheralBlur, PeripheralBlurRadius, PeripheralBlurMotion);
        }

        /// <summary>The settings from <see cref="FilePath"/>, or the defaults (with a warning when the file is missing or bad).</summary>
        public static MenuCameraSettings Load()
        {
            string path = FilePath;
            if (path == null)
            {
                return Defaults;
            }
            string json;
            try
            {
                if (!File.Exists(path))
                {
                    Debug.LogWarning($"[MenuCamera] {path} not found: the built-in values apply");
                    return Defaults;
                }
                json = File.ReadAllText(path);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[MenuCamera] {path} cannot be read ({e.Message}): the built-in values apply");
                return Defaults;
            }
            var problems = new List<string>();
            MenuCameraSettings settings = Parse(json, problems);
            if (problems.Count > 0)
            {
                Debug.LogWarning($"[MenuCamera] {path}: " + string.Join("; ", problems));
            }
            return settings;
        }

        /// <summary>
        /// The settings in <paramref name="json"/>: each key read, checked and clamped, the default kept for a missing or
        /// wrong one; bad JSON gives the defaults. Every fallback and clamp adds a line to <paramref name="problems"/>.
        /// </summary>
        public static MenuCameraSettings Parse(string json, List<string> problems)
        {
            var s = new MenuCameraSettings();
            JObject o;
            try
            {
                o = JObject.Parse(json ?? string.Empty);
            }
            catch (Exception e)
            {
                problems?.Add("bad JSON, the built-in values apply (" + e.Message + ")");
                return s;
            }
            s.FisheyeStrength = CardNumberSettings.Number(o, "fisheyeStrength", s.FisheyeStrength, 0f, MaxStrength, problems);
            s.FisheyeZoom = CardNumberSettings.Number(o, "fisheyeZoom", s.FisheyeZoom, MinZoom, MaxZoom, problems);
            s.FisheyeVignette = CardNumberSettings.Number(o, "fisheyeVignette", s.FisheyeVignette, 0f, 1f, problems);
            s.PeripheralBlur = CardNumberSettings.Number(o, "peripheralBlur", s.PeripheralBlur, 0f, 1f, problems);
            s.PeripheralBlurRadius = CardNumberSettings.Number(o, "peripheralBlurRadius", s.PeripheralBlurRadius, 0f, 1f, problems);
            s.PeripheralBlurMotion = CardNumberSettings.Number(o, "peripheralBlurMotion", s.PeripheralBlurMotion, 0f, 1f, problems);
            return s;
        }
    }
}
