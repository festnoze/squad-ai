using System;
using System.Collections.Generic;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.UI;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace OutOfSight
{
    /// <summary>
    /// Entry point, the only component of Boot.unity (PRD 8.3). Builds every subsystem in code. Each build
    /// step runs in its own try/catch that logs, because an exception in Awake cancels the rest of Awake
    /// and one broken subsystem would otherwise silently take the whole game with it (PRD 8.4).
    /// M3 (docs/CONTRACT_M3.md 6): the look pass (one shadowed sun, SSAO and the x-ray on the renderer, bloom
    /// above 1, Neutral tonemapping, a light grade), and the menus: the title opens at start in a player only,
    /// never under --probe and never in the editor.
    /// </summary>
    [DefaultExecutionOrder(-1000)]
    public sealed class Main : MonoBehaviour
    {
        public static Main Instance { get; private set; }

        public GameState Game { get; private set; }
        public Hud Hud { get; private set; }
        public Sfx Sfx { get; private set; }

        /// <summary>Audio overhaul: the title and level music (docs/audio/AUDIO_REPORT.md 5).</summary>
        public MusicPlayer Music { get; private set; }

        public OrbitCamera OrbitCamera { get; private set; }
        public Camera Camera { get; private set; }
        public Light Sun { get; private set; }
        public int FailedSteps { get; private set; }

        /// <summary>M3: the title screen and the pause menu.</summary>
        public Menu Menu { get; private set; }

        /// <summary>M3: the global post processing volume (tests read its profile).</summary>
        public Volume PostProcessing { get; private set; }

        /// <summary>True when the title screen opens by itself at start: a built player not run with --probe.</summary>
        public static bool TitleAtStart => !Application.isEditor && !Probe.Requested;

        // PRD 7.2: a warm sun through the window. Bloom catches only what is brighter than 1: the threshold is in
        // gamma space, 1.25 is 1.63 in linear. A sunlit white trim peaks near 1.45 linear, the window pane (Unlit,
        // 1.6 x its color) near 2.6, so only the pane glows.
        private const float SunIntensity = Tuning.LookSunIntensity;
        private const float BloomThreshold = Tuning.LookBloomThreshold;
        private const float BloomIntensity = Tuning.LookBloomIntensity;

        private void Awake()
        {
            Instance = this;
            // The product owner's request: silent while tests run (AudioMute: batch mode, --probe, -mute).
            AudioListener.volume = AudioMute.Apply(AudioListener.volume);
            StartFullScreen();
            // M3: the pause flags are static and outlive a scene reload (tests reload Boot for every case).
            GamePause.IsPaused = false;
            AudioListener.pause = false;
            Run("time", () => Time.fixedDeltaTime = Tuning.FixedStep);
            // M5 (CONTRACT_M5_v3 15.7): the editor, --probe and --look use a test save deleted here; then the load.
            Run("save", SaveStore.Boot);
            Run("layers", Layers.Resolve);
            // The chair and the inhabitant never push each other: a still chair must never be displaced
            // (PRD 3.2 M1 note) and a chair leaving an overlap must not jump. Vision uses Occluder only.
            Run("physics", () => Physics.IgnoreLayerCollision(Layers.Player, Layers.Inhabitant, true));
            Run("lighting", BuildLighting);
            Run("camera", BuildCamera);
            Run("post processing", BuildVolume);
            Run("event system", BuildEventSystem);
            Run("sfx", BuildSfx);
            Run("music", BuildMusic);
            Run("hud", BuildHud);
            Run("game", BuildGame);
            Run("menu", BuildMenu);
            Run("probe", BuildProbe);
        }

        private void Start()
        {
            Run("level", () => Game.Begin());
            if (TitleAtStart)
            {
                // The title frees the cursor; Play captures it.
                Run("title", () => Menu.ShowTitle());
            }
            string look = Probe.ArgValue("--look");
            if (!Application.isEditor && !string.IsNullOrEmpty(look))
            {
                StartCoroutine(LookShots.Run(this, look));
            }
        }

        /// <summary>
        /// M3: what is wrong with the look (tests and --look): the x-ray and the SSAO on the renderer, bloom
        /// thresholded above 1, Neutral tonemapping, exactly one shadowed light and it is the directional sun.
        /// </summary>
        public List<string> LookProblems()
        {
            List<string> problems = XRay.Problems();
            VolumeProfile profile = PostProcessing != null ? PostProcessing.sharedProfile : null;
            if (profile == null)
            {
                problems.Add("no post processing profile");
            }
            else
            {
                if (!profile.TryGet(out Bloom bloom) || !bloom.active || !bloom.threshold.overrideState || bloom.threshold.value <= 1f
                    || bloom.intensity.value <= 0f)
                {
                    problems.Add("bloom is missing, off, or thresholded at or below 1");
                }
                if (!profile.TryGet(out Tonemapping tonemapping) || !tonemapping.active || tonemapping.mode.value != TonemappingMode.Neutral)
                {
                    problems.Add("tonemapping is not Neutral");
                }
            }
            int shadowed = 0;
            foreach (Light light in FindObjectsByType<Light>(FindObjectsSortMode.None))
            {
                if (light.enabled && light.shadows != LightShadows.None)
                {
                    shadowed++;
                }
            }
            if (shadowed != 1 || Sun == null || Sun.type != LightType.Directional || Sun.shadows == LightShadows.None)
            {
                problems.Add($"{shadowed} shadowed light(s); expected exactly one, the directional sun");
            }
            return problems;
        }

        /// <summary>
        /// M7 (ProbeTestsM7Look.Step60a_): true while the Volume carries an active tonemapper (any mode but
        /// None) and an active, thresholded bloom. The Tests.PlayMode assembly has no reference to the
        /// Universal Render Pipeline runtime (its asmdef), so the check lives here instead of in the test.
        /// </summary>
        public bool VolumeHasTonemapperAndBloom()
        {
            VolumeProfile profile = PostProcessing != null ? PostProcessing.sharedProfile : null;
            if (profile == null)
            {
                return false;
            }
            bool tonemap = profile.TryGet(out Tonemapping tonemapping) && tonemapping.active && tonemapping.mode.overrideState
                && tonemapping.mode.value != TonemappingMode.None;
            bool bloom = profile.TryGet(out Bloom bloomOverride) && bloomOverride.active && bloomOverride.intensity.overrideState
                && bloomOverride.intensity.value > 0f && bloomOverride.threshold.overrideState && bloomOverride.threshold.value > 1f;
            return tonemap && bloom;
        }

        private void OnDestroy()
        {
            if (Instance == this)
            {
                Instance = null;
            }
        }

        private void Update()
        {
            if (InputReader.ReleaseCursorPressed())
            {
                Cursor.lockState = CursorLockMode.None;
            }
            else if (InputReader.CaptureCursorPressed() && Cursor.lockState != CursorLockMode.Locked && (Menu == null || !Menu.WantsCursor))
            {
                // A click on a menu button must not capture the cursor it needs.
                Cursor.lockState = CursorLockMode.Locked;
            }
            if (FullScreenTogglePressed())
            {
                ToggleFullScreen();
            }
        }

        /// <summary>
        /// The product owner's request (2026-11-18): every launch starts in borderless full screen at the display
        /// resolution, even when the last session ended in a window (Unity restores the last window mode otherwise).
        /// Not in batch mode, the probe's runs (they set their own resolution) or with an explicit -screen-fullscreen.
        /// </summary>
        private static void StartFullScreen()
        {
            if (Application.isBatchMode || Application.isEditor || Application.isMobilePlatform)
            {
                return;
            }
            string[] args = Environment.GetCommandLineArgs();
            foreach (string a in args)
            {
                if (a == "-screen-fullscreen" || a == "--probe" || a == "--look" || a == "--titletour")
                {
                    return;
                }
            }
            Resolution d = Screen.currentResolution;
            Screen.SetResolution(d.width, d.height, FullScreenMode.FullScreenWindow);
        }

        /// <summary>Ctrl+F or F11 (the product owner's request; Alt+Enter is Unity's own standalone toggle).</summary>
        private static bool FullScreenTogglePressed()
        {
            Keyboard k = Keyboard.current;
            if (k == null)
            {
                return false;
            }
            bool ctrl = k.leftCtrlKey.isPressed || k.rightCtrlKey.isPressed;
            return (ctrl && k.fKey.wasPressedThisFrame) || k.f11Key.wasPressedThisFrame;
        }

        /// <summary>Borderless full screen at the display resolution, or a window of at most 1600 x 900.</summary>
        public static void ToggleFullScreen()
        {
            if (Screen.fullScreenMode == FullScreenMode.Windowed)
            {
                Resolution d = Screen.currentResolution;
                Screen.SetResolution(d.width, d.height, FullScreenMode.FullScreenWindow);
            }
            else
            {
                Resolution d = Screen.currentResolution;
                int w = Mathf.Min(1600, d.width * 3 / 4);
                int h = Mathf.Min(900, d.height * 3 / 4);
                Screen.SetResolution(w, h, FullScreenMode.Windowed);
            }
        }

        private void Run(string step, Action action)
        {
            try
            {
                action();
            }
            catch (Exception e)
            {
                FailedSteps++;
                Debug.LogError($"[Main] build step '{step}' failed: {e}");
            }
        }

        private GameObject Child(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(transform, false);
            return go;
        }

        private void BuildLighting()
        {
            // PRD 7.2: a warm directional light through the window (on the -z wall), soft shadows. The only
            // shadowed light; resolution, distance and cascades come from the URP asset (PRD 8.4).
            // M7 lighting (CONTRACT_M7 1.1, polish round 2): warmer and a little lower, for longer, more
            // readable soft shadows; the sky side of the ambient trilight pushed cooler against it.
            GameObject go = Child("Sun");
            Sun = go.AddComponent<Light>();
            Sun.type = LightType.Directional;
            Sun.color = DaySunColour;
            Sun.intensity = SunIntensity;
            Sun.shadows = LightShadows.Soft; // MUTATION:SUN_SOFT_SHADOWS
            Sun.shadowStrength = DaySunShadowStrength;
            go.transform.rotation = Quaternion.Euler(DaySunPitch, SunYaw, 0f);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = DayAmbientSky;
            RenderSettings.ambientEquatorColor = DayAmbientEquator;
            RenderSettings.ambientGroundColor = DayAmbientGround;
            RenderSettings.skybox = null;
            RenderSettings.fog = false;
            // A scene reload starts from the day look (the flag is static and outlives the previous Boot).
            AppliedLighting = LevelDef.LightingDay;
        }

        // ----- Levels v2 (D25, C10): the night lighting preset, visual only -----

        // The day look as BuildLighting and BuildVolume set it (the night preset puts exactly these back).
        private static readonly Color DaySunColour = new Color(1f, 0.87f, 0.67f);
        private const float DaySunShadowStrength = 0.78f;
        private const float DaySunPitch = 44f;
        private const float SunYaw = 32f;
        private static readonly Color DayAmbientSky = new Color(0.58f, 0.63f, 0.73f);
        private static readonly Color DayAmbientEquator = new Color(0.52f, 0.47f, 0.42f);
        private static readonly Color DayAmbientGround = new Color(0.28f, 0.23f, 0.19f);
        private const float DayTemperature = 9f;
        private const float DayVignette = 0.22f;

        // Night (presentation only, so not in Tuning; no rule reads any of it, PRD 4.7 unchanged): a low, cool moon as
        // the one shadowed key light (the same yaw as the sun, so the sky picture's glow and every cached sky mesh keep
        // their place), the ambient trilight at about NightAmbientFactor of the day's and pushed toward blue, a cool
        // grade and a deeper vignette. The room lights carry the warm pools (RoomLights.NightAllowance, NightPool), the
        // player's floor lamp shines brighter and further (LampLight.NightIntensity), the windows and the garden go dark
        // blue (WindowImage.NightColour, GardenBackdrop.NightTint).
        // NIGHT pass (2026-11-22, first look at it in real captures): the first values (moon 0.5, ambient 0.35) read as a
        // blue dusk, the light walls still pale and the pools faint. The moon and the ambient now go lower, so walls and
        // floors read dark and the warm pools carry the rooms; the cones (unlit shader) and the HUD (overlay) do not
        // depend on any of it.
        private static readonly Color NightMoonColour = new Color(0.6f, 0.71f, 1f);
        private const float NightMoonIntensity = 0.3f;
        private const float NightMoonShadowStrength = 0.55f;
        private const float NightMoonPitch = 27f;

        /// <summary>The night ambient trilight over the day's (each colour, before <see cref="NightAmbientTint"/>).</summary>
        public const float NightAmbientFactor = 0.24f;

        // Its luminance (Rec. 709 weights) is about 1 (0.97), so the factor above stays the ambient's brightness ratio.
        private static readonly Color NightAmbientTint = new Color(0.86f, 0.97f, 1.32f);
        private const float NightTemperature = -12f;
        // A deeper vignette frames the lit middle of the view (the HUD is an overlay: never darkened by it).
        private const float NightVignette = 0.3f;

        /// <summary>The preset applied last (<see cref="LevelDef.LightingDay"/> or <see cref="LevelDef.LightingNight"/>).</summary>
        public static string AppliedLighting { get; private set; } = LevelDef.LightingDay;

        /// <summary>True while the night preset is applied (WindowImage and GardenBackdrop read it as they build).</summary>
        public static bool Night => AppliedLighting == LevelDef.LightingNight;

        /// <summary>True when <paramref name="def"/> asks for the night preset ("lighting": "night"); null or "day" is day.</summary>
        public static bool IsNight(LevelDef def)
        {
            return def != null && def.Lighting == LevelDef.LightingNight;
        }

        private WhiteBalance whiteBalance;
        private Vignette vignette;

        /// <summary>
        /// Levels v2 (D25, C10): applies the lighting preset of <paramref name="def"/> (GardenBackdrop.Build calls it, the
        /// first level build step that sees the level, before any window reads <see cref="WindowImage.Colour"/>). Day puts
        /// back exactly the look of BuildLighting and BuildVolume; night dims and cools the sun into a moon, the ambient and
        /// the grade, and turns the camera's clear colour to the night sky. Without a Main (edit mode tools) only the flag
        /// the windows and the backdrop read changes. Visual only: no rule, no vision and no audit reads it.
        /// </summary>
        public static void ApplyLighting(LevelDef def)
        {
            bool night = IsNight(def);
            AppliedLighting = night ? LevelDef.LightingNight : LevelDef.LightingDay;
            Main main = Instance;
            if (main == null)
            {
                return;
            }
            if (main.Sun != null)
            {
                main.Sun.color = night ? NightMoonColour : DaySunColour; // MUTATION:NIGHT_MOON
                main.Sun.intensity = night ? NightMoonIntensity : SunIntensity;
                main.Sun.shadowStrength = night ? NightMoonShadowStrength : DaySunShadowStrength;
                main.Sun.transform.rotation = Quaternion.Euler(night ? NightMoonPitch : DaySunPitch, SunYaw, 0f);
            }
            RenderSettings.ambientSkyColor = night ? NightAmbient(DayAmbientSky) : DayAmbientSky;
            RenderSettings.ambientEquatorColor = night ? NightAmbient(DayAmbientEquator) : DayAmbientEquator;
            RenderSettings.ambientGroundColor = night ? NightAmbient(DayAmbientGround) : DayAmbientGround;
            DynamicGI.UpdateEnvironment();
            if (main.whiteBalance != null)
            {
                main.whiteBalance.temperature.Override(night ? NightTemperature : DayTemperature);
            }
            if (main.vignette != null)
            {
                main.vignette.intensity.Override(night ? NightVignette : DayVignette);
            }
            if (main.Camera != null)
            {
                main.Camera.backgroundColor = GardenBackdrop.ClearColour;
            }
        }

        private static Color NightAmbient(Color day)
        {
            return new Color(day.r * NightAmbientFactor * NightAmbientTint.r, day.g * NightAmbientFactor * NightAmbientTint.g,
                day.b * NightAmbientFactor * NightAmbientTint.b, 1f);
        }

        private void BuildCamera()
        {
            GameObject go = Child("Camera");
            go.tag = "MainCamera";
            Camera = go.AddComponent<Camera>();
            Camera.clearFlags = CameraClearFlags.SolidColor;
            // Garden backdrop (2026-11-19): the sky above the ring around the house continues its picture's top sky.
            Camera.backgroundColor = GardenBackdrop.ClearColour;
            Camera.fieldOfView = 55f;
            Camera.nearClipPlane = 0.05f;
            Camera.farClipPlane = 80f;
            go.AddComponent<AudioListener>();
            UniversalAdditionalCameraData data = Camera.GetUniversalAdditionalCameraData();
            data.renderPostProcessing = true;
            data.antialiasing = AntialiasingMode.None; // MSAA 4 comes from PC_RPAsset
            OrbitCamera = go.AddComponent<OrbitCamera>();
        }

        /// <summary>
        /// The global volume. PRD 8.4: Neutral tonemapping, not ACES, which washes out a flat palette. M3: bloom
        /// thresholded above 1 so only emissive surfaces (the window pane, a lit lamp) glow, never a sunlit wall;
        /// a light grade (a touch warmer, a little contrast and saturation); a soft vignette that frames the room.
        /// M7 (CONTRACT_M7 1.1, polish round 2): the bloom reaches a little further and the grade is a touch
        /// warmer, for a softer, more readable house; the tonemapper stays Neutral (still PRD 8.4's reason).
        /// </summary>
        private void BuildVolume()
        {
            GameObject go = Child("PostProcessing");
            var volume = go.AddComponent<Volume>();
            volume.isGlobal = true;
            volume.priority = 10f;
            VolumeProfile profile = ScriptableObject.CreateInstance<VolumeProfile>();
            profile.name = "OutOfSight Runtime Profile";
            Tonemapping tonemapping = profile.Add<Tonemapping>(true);
            tonemapping.mode.Override(TonemappingMode.Neutral); // MUTATION:TONEMAP_NEUTRAL
            Bloom bloom = profile.Add<Bloom>(true);
            bloom.threshold.Override(BloomThreshold);
            bloom.intensity.Override(BloomIntensity); // MUTATION:BLOOM_ON
            bloom.scatter.Override(0.68f);
            bloom.tint.Override(new Color(1f, 0.93f, 0.8f));
            bloom.highQualityFiltering.Override(false);
            ColorAdjustments color = profile.Add<ColorAdjustments>(true);
            color.postExposure.Override(0.08f);
            color.saturation.Override(11f);
            color.contrast.Override(10f);
            WhiteBalance white = profile.Add<WhiteBalance>(true);
            white.temperature.Override(DayTemperature);
            whiteBalance = white;
            white.tint.Override(0f);
            Vignette frame = profile.Add<Vignette>(true);
            frame.intensity.Override(DayVignette);
            frame.smoothness.Override(0.45f);
            vignette = frame;
            volume.sharedProfile = profile;
            PostProcessing = volume;
        }

        private void BuildEventSystem()
        {
            // PRD 8.4: InputSystemUIInputModule, never StandaloneInputModule (it throws with this input handler).
            GameObject go = Child("EventSystem");
            go.AddComponent<EventSystem>();
            go.AddComponent<InputSystemUIInputModule>();
        }

        private void BuildSfx()
        {
            Sfx = Child("Sfx").AddComponent<Sfx>();
            Sfx.Init();
        }

        /// <summary>The music on its own child: its two sources ignore the listener pause, unlike every effect of Sfx.</summary>
        private void BuildMusic()
        {
            Music = Child("Music").AddComponent<MusicPlayer>();
            Music.Init(AudioLibrary.Load());
        }

        private void BuildHud()
        {
            GameObject go = Child("Hud");
            go.AddComponent<RectTransform>();
            Hud = go.AddComponent<Hud>();
            Hud.Init();
        }

        private void BuildGame()
        {
            Game = Child("Game").AddComponent<GameState>();
            Game.Hud = Hud;
            Game.Sfx = Sfx;
            Game.Camera = OrbitCamera;
            // M2.1 (docs/CONTRACT_M2.md 11.6): the ghost of the remembered pose, built once, kept across levels.
            Game.Ghost = Child("Ghost").AddComponent<GhostView>();
            Game.Ghost.Init();
            // M2: "--level <id>" starts on another level of Resources/Levels (built player and playtests).
            string level = Probe.ArgValue("--level");
            if (!string.IsNullOrEmpty(level))
            {
                Game.LevelId = level;
            }
            if (Hud != null)
            {
                // M3: the HUD keeps the world markers below its gauges.
                Hud.View = Camera;
                Hud.Game = Game;
            }
        }

        private void BuildMenu()
        {
            GameObject go = Child("Menu");
            go.AddComponent<RectTransform>();
            Menu = go.AddComponent<Menu>();
            Menu.Init(Game, Hud, OrbitCamera, Sfx);
            Game.Menu = Menu;
        }

        private void BuildProbe()
        {
            Probe probe = Child("Probe").AddComponent<Probe>();
            probe.Game = Game;
            probe.Hud = Hud;
        }
    }
}
