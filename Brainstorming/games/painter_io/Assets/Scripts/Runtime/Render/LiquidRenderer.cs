// Owned by BI since wave B-2 (written by B1). Contract 11.1 entry point of the liquid renderer and 12.1-12.4: builds the
// TerritoryField (VisualMask, fill waves, evaporation, pockets, blur passes, reveal times), the ActorFieldCamera, the static
// LiquidSurface composite quad, applies the QualityTier and its FPS watchdog, publishes the shared shader globals and checks
// the default volume profile. Rebinds on GameDirector.SessionStarted (also raised on attract restarts).
// Contract 25.2: the composite shader, the table colors, the palette and the bloom follow BiomeTheme.Current and re-bind
// live on BiomeTheme.Changed (no restart). Bloom: on the High tier when the biome has BloomOnHigh, through the main
// camera's renderPostProcessing (HDR on) and a runtime global Volume (Bloom threshold >= 1.1, Tonemapping None).
// Wave C (infra-perf): in the player, the active URP asset's renderScale follows QualityTier.RenderScaleFor (the tier's
// render height cap) at Create, on a tier change and when Screen.height changes; the watchdog only measures real rounds
// in Playing and only real rounds re-arm it; _PIO_Time counts from the current session start (wraps at 4096 s).
using System;
using System.Globalization;
using PainterIO.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace PainterIO.Runtime
{
    public sealed class LiquidRenderer : MonoBehaviour
    {
        /// <summary>Seconds a capture takes to fill in (same as TerritoryField.FillDuration; the HUD syncs on it).</summary>
        public const float FillDuration = TerritoryField.FillDuration;

        /// <summary>FillDuration of the current biome (BiomeTheme.Current.FillDuration; 0.35 s in Liquide).</summary>
        public static float CurrentFillDuration => TerritoryField.CurrentFillDuration;

        /// <summary>Resources path of the composite graph.</summary>
        public const string CompositeShaderPath = "Shaders/LiquidComposite";
        /// <summary>Resources path of the territory blur shader.</summary>
        public const string BlurShaderPath = "Shaders/TerritoryBlur";

        private static readonly int IdColors = Shader.PropertyToID("_PIO_Colors");
        private static readonly int IdShadowOffset = Shader.PropertyToID("_PIO_ShadowOffset");
        private static readonly int IdQuality = Shader.PropertyToID("_PIO_Quality");
        private static readonly int IdGround = Shader.PropertyToID("_PIO_GroundColor");
        private static readonly int IdOutside = Shader.PropertyToID("_PIO_OutsideColor");
        private static readonly int IdArenaShape = Shader.PropertyToID("_PIO_ArenaShape");
        private static readonly int IdCountryDistance = Shader.PropertyToID("_PIO_CountryDistance");
        private Texture2D countryDistance;
        private static readonly int IdTime = Shader.PropertyToID("_PIO_Time");
        private static readonly int IdSecondary = Shader.PropertyToID("_PIO_SecondaryColors");
        private static readonly int IdBiomeParams = Shader.PropertyToID("_PIO_BiomeParams");

        /// <summary>0.12 * normalize(L.xy) with L = normalize(-0.45, 0.6, 0.66): (-0.072, 0.096) u, toward the light.</summary>
        public static readonly Vector4 ShadowOffset = new Vector4(-0.072f, 0.096f, 0f, 0f);

        /// <summary>_PIO_Time wraps at this many seconds after the session start (float precision stays below 0.5 ms).</summary>
        public const double ShaderTimeWrap = 4096.0;

        private double timeEpoch;
#if !UNITY_EDITOR
        private int renderScaleHeight = -1;
        private float appliedRenderScale = -1f;
#endif

        private readonly Vector4[] colors = new Vector4[4];
        private readonly Vector4[] secondary = new Vector4[4];
        private Camera boundCamera;
        private Volume bloomVolume;
        private VolumeProfile bloomProfile;
        private Bloom bloom;
        private bool bloomOn;
        private GameDirector director;
        private GameSession boundSession;
        private TerritoryField territory;
        private ActorFieldCamera actorField;
        private LiquidSurface surface;
        private DebugBlobs debugBlobs;
        private bool updateErrorLogged;

        /// <summary>The live renderer (null when none exists).</summary>
        public static LiquidRenderer Instance { get; private set; }

        /// <summary>The territory field (null if it failed to build).</summary>
        public TerritoryField Territory => territory;

        /// <summary>The actor field camera (null if it failed to build).</summary>
        public ActorFieldCamera ActorField => actorField;

        /// <summary>The composite quad (null if it failed to build).</summary>
        public LiquidSurface Surface => surface;

        /// <summary>True while the bloom of the current biome is on (High tier and BiomeTheme.Current.BloomOnHigh).</summary>
        public bool BloomActive => bloomOn;

        /// <summary>The session the renderer is bound to.</summary>
        public GameSession BoundSession => boundSession;

        public static LiquidRenderer Create(GameDirector d)
        {
            var go = new GameObject("LiquidRenderer");
            var r = go.AddComponent<LiquidRenderer>();
            r.director = d;
            Instance = r;
            r.Build();
            if (d != null)
            {
                d.SessionStarted += r.OnSessionStarted;
                d.StateChanged += r.OnStateChanged;
                if (d.Session != null) r.OnSessionStarted(d.Session);
            }
            return r;
        }

        private void Build()
        {
            timeEpoch = Time.unscaledTimeAsDouble;
            Guard("QualityTier", () =>
            {
                QualityTier.Refresh();
                QualityTier.Changed += OnTierChanged;
                SaveData.Changed += OnSaveDataChanged;
                BiomeTheme.Changed += OnBiomeChanged;
            });
            Guard("render scale", ApplyRenderScale);
            Guard("globals", PublishStaticGlobals);
            Guard("TerritoryField", () => territory = new TerritoryField(LoadShader(BlurShaderPath)));
            Guard("ActorFieldCamera", () => actorField = ActorFieldCamera.Create(transform));
            Guard("LiquidSurface", () => surface = LiquidSurface.Create(transform, LoadComposite(BiomeTheme.Current)));
            Guard("VolumeProfileCheck", CheckVolumeProfile);
            Guard("DebugBlobs", () => debugBlobs = DebugBlobs.TryCreate(transform, director));
            Guard("RenderLab", () => RenderLab.TryCreate(transform, director, this));
            Guard("frame globals", PublishFrameGlobals);
            Guard("camera theme", ApplyCameraTheme);
        }

        private void OnDestroy()
        {
            if (director != null)
            {
                director.SessionStarted -= OnSessionStarted;
                director.StateChanged -= OnStateChanged;
            }
            if (boundSession != null) boundSession.EventRaised -= OnSimEvent;
            boundSession = null;
            QualityTier.Changed -= OnTierChanged;
            SaveData.Changed -= OnSaveDataChanged;
            BiomeTheme.Changed -= OnBiomeChanged;
            SafeDestroy(bloomProfile);
            SafeDestroy(countryDistance);
            if (territory != null) territory.Dispose();
            territory = null;
            if (Instance == this) Instance = null;
        }

        private void OnSessionStarted(GameSession s)
        {
            if (boundSession != null) boundSession.EventRaised -= OnSimEvent;
            boundSession = s;
            if (s != null) s.EventRaised += OnSimEvent;
            // Only a real round re-arms the watchdog: the attract restarts behind the menu are never measured, so they
            // must not grant another step either (contract 12.4: at most one step per real session).
            if (s != null && !s.IsAttract) QualityTier.BeginSession();
            // Every session start rebuilds the territory field (round start, REJOUER, menu return, attract restart), so
            // the shader clock restarting here is never seen, and it never reaches the wrap in practice.
            timeEpoch = Time.unscaledTimeAsDouble;
            Guard("Country border", () => UpdateCountryBorder(s?.Sim.Arena));
            Guard("TerritoryField.Bind", () => territory?.Bind(s));
            if (debugBlobs != null) debugBlobs.Bind(s);
        }

        private void OnStateChanged(GameState state)
        {
            // Nothing state-specific: the field follows the bound session in every state (menu attract included).
        }

        private void OnSimEvent(SimEvent e)
        {
            if (territory != null) territory.OnSimEvent(e);
        }

        private void OnTierChanged()
        {
            Guard("render scale", ApplyRenderScale);
            PublishFrameGlobals();
            Guard("camera theme", ApplyCameraTheme);
        }

        /// <summary>
        /// Player only: sets the active URP asset's renderScale to QualityTier.RenderScaleFor(Screen.height, tier, android),
        /// computed from scratch (GameDirector's earlier 1920 px Android cap gives the same value on High). Never in the
        /// editor, so the asset on disk is never dirtied. Logs once per change of the applied value.
        /// </summary>
        private void ApplyRenderScale()
        {
#if !UNITY_EDITOR
            int height = Screen.height;
            renderScaleHeight = height;
            var urp = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            if (urp == null) return;
            RenderTier tier = QualityTier.Current;
            float scale = QualityTier.RenderScaleFor(height, tier, Application.platform == RuntimePlatform.Android);
            if (Mathf.Abs(urp.renderScale - scale) > 1e-4f) urp.renderScale = scale;
            if (Mathf.Abs(appliedRenderScale - scale) > 1e-4f)
            {
                appliedRenderScale = scale;
                Debug.Log("[PainterIO] render scale " + scale.ToString("0.000", CultureInfo.InvariantCulture) + " (tier " + tier
                          + ", height " + height.ToString(CultureInfo.InvariantCulture) + ")");
            }
#endif
        }

        /// <summary>
        /// _PIO_Time: seconds since the session epoch, wrapped at ShaderTimeWrap (4096 s, where a float still resolves
        /// 0.5 ms), never negative.
        /// </summary>
        internal static float ShaderTimeFor(double now, double epoch)
        {
            double t = (now - epoch) % ShaderTimeWrap;
            if (!(t >= 0.0)) t = t < 0.0 ? t + ShaderTimeWrap : 0.0;
            return (float)t;
        }

        /// <summary>Contract 25.2: re-binds the composite, the table colors and the bloom of the new biome (no restart).</summary>
        private void OnBiomeChanged(BiomeTheme theme)
        {
            if (this == null)
            {
                BiomeTheme.Changed -= OnBiomeChanged;   // destroyed in edit mode without OnDestroy
                return;
            }
            Guard("biome composite", () =>
            {
                if (surface != null) surface.SetShader(LoadComposite(theme));
            });
            Guard("globals", PublishStaticGlobals);
            Guard("frame globals", PublishFrameGlobals);
            Guard("camera theme", ApplyCameraTheme);
        }

        private void OnSaveDataChanged()
        {
            // Quality forced from the options, or the human's color changed.
            QualityTier.Refresh();
            PublishFrameGlobals();
        }

        private void LateUpdate()
        {
            try
            {
                GameSession s = director != null ? director.Session : boundSession;
                if (s != null && s != boundSession) OnSessionStarted(s);
                // Measured: real rounds in Playing only (never the menu attract nor Results).
                bool running = s != null && !s.IsAttract && director != null && director.State == GameState.Playing
                               && !s.IsClosed && !s.Runner.Paused && !s.Sim.Ended && !s.AwaitingStart;
                QualityTier.Tick(Time.unscaledDeltaTime, running);
#if !UNITY_EDITOR
                if (Screen.height != renderScaleHeight) Guard("render scale", ApplyRenderScale);
#endif
                PublishFrameGlobals();
                if (Camera.main != boundCamera) ApplyCameraTheme();
                if (territory != null) territory.Update(Time.unscaledDeltaTime);
            }
            catch (Exception e)
            {
                if (updateErrorLogged) return;
                updateErrorLogged = true;
                Debug.LogError("[PainterIO] LiquidRenderer update failed: " + e);
            }
        }

        private void PublishStaticGlobals()
        {
            Shader.SetGlobalVector(IdShadowOffset, ShadowOffset);
            BiomeTheme theme = BiomeTheme.Current;
            Shader.SetGlobalVector(IdGround, ToVector(theme.Ground.linear));
            Shader.SetGlobalVector(IdOutside, ToVector(theme.OutsideArena.linear));
            Shader.SetGlobalVector(IdBiomeParams, theme.ShaderParams);
            Shader.SetGlobalVector(IdArenaShape, new Vector4((float)Tuning.ArenaHalfSize, (float)Tuning.ArenaCornerRadius, 0f, 0f));
        }

        private void PublishFrameGlobals()
        {
            for (int i = 0; i < 4; i++)
            {
                colors[i] = ToVector(Palette.LinearColorOf(i));
                secondary[i] = ToVector(Palette.SecondaryColorOf(i).linear);
            }
            Shader.SetGlobalVectorArray(IdColors, colors);
            Shader.SetGlobalVectorArray(IdSecondary, secondary);
            Shader.SetGlobalVector(IdQuality, QualityTier.ShaderFlags);
            float t = ShaderTimeFor(Time.unscaledTimeAsDouble, timeEpoch);
            Shader.SetGlobalVector(IdTime, new Vector4(t, 0f, 0f, 0f));
            GameSession s = boundSession;
            if (s != null && s.Sim != null)
            {
                Arena a = s.Sim.Arena;
                Shader.SetGlobalVector(IdArenaShape, new Vector4((float)a.HalfSize, (float)a.CornerRadius,
                    countryDistance != null ? 1f : 0f, 0f));
            }
        }

        private void UpdateCountryBorder(Arena arena)
        {
            SafeDestroy(countryDistance);
            countryDistance = null;
            if (arena?.Polygon == null) return;

            const int size = 384;
            var pixels = new Color32[size * size];
            double cell = 2 * arena.HalfSize / size;
            for (int y = 0; y < size; y++)
            for (int x = 0; x < size; x++)
            {
                var p = new Vec2d((x + 0.5) * cell - arena.HalfSize, (y + 0.5) * cell - arena.HalfSize);
                float distance = (float)arena.SignedDistance(p);
                byte value = (byte)Mathf.RoundToInt(Mathf.Clamp01(distance * 0.25f + 0.5f) * 255);
                pixels[y * size + x] = new Color32(value, value, value, 255);
            }
            countryDistance = new Texture2D(size, size, TextureFormat.RGBA32, false, true)
            {
                name = "Country border distance",
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp
            };
            countryDistance.SetPixels32(pixels);
            countryDistance.Apply(false, true);
            Shader.SetGlobalTexture(IdCountryDistance, countryDistance);
        }

        /// <summary>
        /// The main camera follows the biome: clear color = the theme's OutsideArena; on the High tier with a BloomOnHigh
        /// biome, HDR + renderPostProcessing on and the runtime bloom Volume enabled with the theme's settings (contract
        /// 12.1: threshold >= 1.1, no tonemapping); otherwise post-processing off (the saturated liquid stays exact).
        /// </summary>
        private void ApplyCameraTheme()
        {
            BiomeTheme theme = BiomeTheme.Current;
            Camera cam = Camera.main;
            boundCamera = cam;
            bool wantBloom = theme.BloomOnHigh && QualityTier.BloomAllowed;
            if (cam != null)
            {
                cam.backgroundColor = theme.OutsideArena;
                cam.allowHDR = wantBloom;
                UniversalAdditionalCameraData data = cam.GetUniversalAdditionalCameraData();
                if (data != null) data.renderPostProcessing = wantBloom;
            }
            if (wantBloom) EnsureBloomVolume(theme);
            if (bloomVolume != null) bloomVolume.enabled = wantBloom;
            if (wantBloom != bloomOn) Debug.Log("[PainterIO] bloom " + (wantBloom ? "on (" + theme.CommandName + ")" : "off"));
            bloomOn = wantBloom;
        }

        private void EnsureBloomVolume(BiomeTheme theme)
        {
            if (bloomVolume == null)
            {
                var go = new GameObject("BiomeBloomVolume") { layer = 0 };
                go.transform.SetParent(transform, false);
                bloomProfile = ScriptableObject.CreateInstance<VolumeProfile>();
                bloomProfile.name = "PIO BiomeBloom";
                bloomProfile.hideFlags = HideFlags.HideAndDontSave;
                bloom = bloomProfile.Add<Bloom>(true);
                Tonemapping tone = bloomProfile.Add<Tonemapping>(true);
                tone.mode.Override(TonemappingMode.None);
                bloomVolume = go.AddComponent<Volume>();
                bloomVolume.isGlobal = true;
                bloomVolume.priority = 100f;
                bloomVolume.weight = 1f;
                bloomVolume.sharedProfile = bloomProfile;
            }
            bloom.active = true;
            bloom.threshold.Override(Mathf.Max(1.1f, theme.BloomThreshold));
            bloom.intensity.Override(Mathf.Max(0f, theme.BloomIntensity));
            bloom.scatter.Override(Mathf.Clamp01(theme.BloomScatter));
        }

        private static Shader LoadComposite(BiomeTheme theme)
        {
            Shader s = theme != null ? theme.ResolveComposite() : null;
            return s != null ? s : LoadShader(CompositeShaderPath);
        }
        // Contract 12.1: the shipped DefaultVolumeProfile has Tonemapping None and Bloom intensity 0 (verified on the asset
        // by B1). At runtime the cameras render without post-processing; this logs if the default stack ever changes.
        private static void CheckVolumeProfile()
        {
            VolumeStack stack;
            try
            {
                VolumeManager vm = VolumeManager.instance;
                if (vm == null || !vm.isInitialized) return;
                stack = vm.stack;
            }
            catch (Exception e)
            {
                Debug.Log("[PainterIO] volume profile check skipped: " + e.Message);
                return;
            }
            if (stack == null) return;
            var tone = stack.GetComponent<Tonemapping>();
            if (tone != null && tone.mode.value != TonemappingMode.None)
            {
                Debug.LogWarning("[PainterIO] default volume profile: tonemapping " + tone.mode.value + " (contract 12.1 wants None)");
            }
            var bloom = stack.GetComponent<Bloom>();
            if (bloom != null && bloom.intensity.value > 0f)
            {
                Debug.LogWarning("[PainterIO] default volume profile: bloom intensity " + bloom.intensity.value + " (contract 12.1 wants 0)");
            }
        }

        private static Shader LoadShader(string path)
        {
            var s = Resources.Load<Shader>(path);
            if (s == null) throw new InvalidOperationException("Resources.Load<Shader>(\"" + path + "\") returned null");
            return s;
        }

        private static Vector4 ToVector(Color c)
        {
            return new Vector4(c.r, c.g, c.b, c.a);
        }

        private static void Guard(string part, Action action)
        {
            try
            {
                action();
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] LiquidRenderer " + part + " failed: " + e);
            }
        }

        /// <summary>Destroy in play mode, DestroyImmediate in edit mode (tests); null-safe.</summary>
        public static void SafeDestroy(UnityEngine.Object o)
        {
            if (o == null) return;
            if (Application.isPlaying) Destroy(o);
            else DestroyImmediate(o);
        }
    }
}
