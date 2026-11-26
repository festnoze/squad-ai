using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// START SPLASH (docs/next/progress/SPLASH.md, user request 2026-11-27): on every launch of a built player, Windows and
    /// Android, the poster Assets/Art/UI/out-of-sight-affiche-fr.png (<see cref="SplashArt"/>) from the first rendered frame,
    /// whole (aspect ratio kept, fitted inside the screen, so it fills the height on any landscape screen) and centred on
    /// black, for at least <see cref="HoldSeconds"/> of real time while the game builds behind it, then a
    /// <see cref="FadeSeconds"/> fade into the title.
    /// <list type="bullet">
    /// <item>Main.Awake shows it before anything else and defers its whole build by two frames, so the poster is on screen
    /// before the heavy part (every subsystem, the first level, the title house) runs; Main then calls
    /// <see cref="BootDone"/>. The splash lifts once both the hold time is over and the boot is done (plus two frames), or
    /// after <see cref="MaxHoldSeconds"/> whatever happens.</item>
    /// <item>Its own clear-only camera (culling mask 0, lowest depth) clears the screen to black and makes sure the overlay
    /// is drawn before the game camera exists; it goes as soon as Main built the game camera.</item>
    /// <item>Input: the EventSystem's input module is switched off until the splash is gone, and a full screen raycast
    /// target covers the menus, so no click, tap, key or pad press reaches a title button. TouchControls ignores every
    /// finger that landed on it; Main never captures the cursor under it.</item>
    /// <item>The title music (MusicPlayer) and the title logo (TitleLogo) wait while it holds (<see cref="Holding"/>) and
    /// start as it fades.</item>
    /// <item>Once per process: nothing shows it again on a return to the title or a level load.</item>
    /// <item>Skipped (<see cref="SkipReason"/>): in the editor (so every EditMode and PlayMode test), in batch mode, with any
    /// "--" option of the game's tools (--level, --probe, --look, --shot, --feet, --titletour, --levelshot,
    /// --optionsshot, --charshots, ...), with -autoShot, or with <see cref="NoSplashFlag"/>. -touch, -mute and Unity's own
    /// single-dash options keep it (a -touch launch plays like a phone launch).</item>
    /// </list>
    /// </summary>
    [DefaultExecutionOrder(-2000)]
    public sealed class StartSplash : MonoBehaviour
    {
        /// <summary>The least time the poster stays fully up, in real seconds from the first frame it was presented.</summary>
        public const float HoldSeconds = 3f;

        /// <summary>The fade out into the title, in real seconds.</summary>
        public const float FadeSeconds = 0.3f;

        /// <summary>Safety: the splash lifts after this many real seconds even if the boot never reported.</summary>
        public const float MaxHoldSeconds = 12f;

        /// <summary>Above every other overlay canvas (the menus 50, the simulated ad 200).</summary>
        public const int SortingOrder = 32000;

        /// <summary>The command line flag that skips the splash on a normal launch (any case).</summary>
        public const string NoSplashFlag = "-nosplash";

        /// <summary>LEVELNUM's single-dash screenshot option (Menu.AutoShot), which skips the splash too.</summary>
        public const string AutoShotFlag = "-autoShot";

        /// <summary>The splash on screen, or null (never shown, or gone).</summary>
        public static StartSplash Current { get; private set; }

        /// <summary>True from the splash's creation until it is gone (input is blocked, touches are ignored).</summary>
        public static bool Active => Current != null;

        /// <summary>True while the poster is fully up (the title music and logo wait); false from the fade on.</summary>
        public static bool Holding => Current != null && !Current.fading;

        /// <summary>The poster image (its texture is released when the splash is gone).</summary>
        public RawImage Poster { get; private set; }

        /// <summary>The canvas group the fade drives.</summary>
        public CanvasGroup Group { get; private set; }

        private Texture2D texture;
        private Camera clearCamera;
        private BaseInputModule blockedModule;
        private int createdFrame;
        private double createdAt;
        private double shownAt = -1d;
        private bool bootDone;
        private int bootFrame;
        private bool fading;
        private double fadeStart;
        private bool cleaned;

        /// <summary>
        /// Why a launch skips the splash, or null when it shows: "editor", "batch mode", or the first command line argument
        /// that asks for it (any "--" option of the game's test and screenshot tools, -autoShot, -nosplash). Pure, so a
        /// test can call it with any arguments.
        /// </summary>
        public static string SkipReason(string[] args, bool editor, bool batchMode)
        {
            if (editor)
            {
                return "editor";
            }
            if (batchMode)
            {
                return "batch mode";
            }
            if (args == null)
            {
                return null;
            }
            foreach (string a in args)
            {
                if (string.IsNullOrEmpty(a))
                {
                    continue;
                }
                if (a.StartsWith("--", StringComparison.Ordinal)
                    || string.Equals(a, NoSplashFlag, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(a, AutoShotFlag, StringComparison.OrdinalIgnoreCase))
                {
                    return a;
                }
            }
            return null;
        }

        /// <summary>True when this launch shows the splash (<see cref="SkipReason"/> is null).</summary>
        public static bool Wanted => SkipReason(Environment.GetCommandLineArgs(), Application.isEditor, Application.isBatchMode) == null;

        /// <summary>
        /// Puts the poster up (once per process) and returns the splash, or null when the poster does not ship (a warning;
        /// the game then starts as before).
        /// </summary>
        public static StartSplash Show()
        {
            if (Current != null)
            {
                return Current;
            }
            SplashArt art = Resources.Load<SplashArt>(SplashArt.ResourcePath);
            Texture2D poster = art != null ? art.poster : null;
            if (poster == null)
            {
                Debug.LogWarning($"[StartSplash] No poster in Resources/{SplashArt.ResourcePath}: the game starts without the splash.");
                return null;
            }
            var go = new GameObject("StartSplash");
            StartSplash splash = go.AddComponent<StartSplash>();
            splash.Build(poster);
            return splash;
        }

        /// <summary>
        /// Main's build behind the poster is over (called even when a step failed). The input module Main just created is
        /// switched off at once (before the EventSystem's first update), and the clear camera goes once the game camera
        /// exists. The splash then lifts when its hold time is over.
        /// </summary>
        public static void BootDone()
        {
            StartSplash splash = Current;
            if (splash == null)
            {
                return;
            }
            splash.bootDone = true;
            splash.bootFrame = Time.frameCount;
            splash.BlockInput();
            Main main = Main.Instance;
            if (splash.clearCamera != null && main != null && main.Camera != null)
            {
                Destroy(splash.clearCamera.gameObject);
                splash.clearCamera = null;
            }
        }

        private void Build(Texture2D poster)
        {
            Current = this;
            texture = poster;
            createdFrame = Time.frameCount;
            createdAt = Time.realtimeSinceStartupAsDouble;

            // Black under the overlay, and an overlay drawn even before the game camera exists. Lowest depth: once the game
            // camera renders, it draws over this clear (only until BootDone removes it).
            var cameraObject = new GameObject("SplashCamera");
            cameraObject.transform.SetParent(transform, false);
            clearCamera = cameraObject.AddComponent<Camera>();
            clearCamera.clearFlags = CameraClearFlags.SolidColor;
            clearCamera.backgroundColor = Color.black;
            clearCamera.cullingMask = 0;
            clearCamera.depth = -100f;
            clearCamera.allowHDR = false;
            clearCamera.allowMSAA = false;
            clearCamera.useOcclusionCulling = false;
            UniversalAdditionalCameraData data = clearCamera.GetUniversalAdditionalCameraData();
            data.renderPostProcessing = false;
            data.renderShadows = false;
            data.antialiasing = AntialiasingMode.None;
            data.requiresDepthOption = CameraOverrideOption.Off;
            data.requiresColorOption = CameraOverrideOption.Off;

            var canvasObject = new GameObject("SplashCanvas", typeof(RectTransform));
            canvasObject.transform.SetParent(transform, false);
            var canvas = canvasObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = SortingOrder;
            canvasObject.AddComponent<GraphicRaycaster>();
            Group = canvasObject.AddComponent<CanvasGroup>();
            Group.alpha = 1f;
            Group.blocksRaycasts = true;
            Group.interactable = false;

            // The black backdrop, a raycast target over the whole screen: no pointer reaches the menus under it.
            var backdropObject = new GameObject("Black", typeof(RectTransform));
            backdropObject.transform.SetParent(canvasObject.transform, false);
            var backdrop = backdropObject.AddComponent<Image>();
            backdrop.color = Color.black;
            backdrop.raycastTarget = true;
            RectTransform b = backdrop.rectTransform;
            b.anchorMin = Vector2.zero;
            b.anchorMax = Vector2.one;
            b.offsetMin = Vector2.zero;
            b.offsetMax = Vector2.zero;

            // The poster, fitted inside the screen with its own aspect ratio, centred. A landscape screen (16:9, 20:9, 4:3)
            // is wider than the 2:3 poster, so it fills the height with black on both sides; the phones' cutouts sit on those
            // sides in landscape, so no safe area is needed.
            var posterObject = new GameObject("Poster", typeof(RectTransform));
            posterObject.transform.SetParent(canvasObject.transform, false);
            Poster = posterObject.AddComponent<RawImage>();
            Poster.texture = poster;
            Poster.raycastTarget = false;
            var fitter = posterObject.AddComponent<AspectRatioFitter>();
            fitter.aspectRatio = poster.width / (float)Mathf.Max(1, poster.height);
            fitter.aspectMode = AspectRatioFitter.AspectMode.FitInParent;

            Debug.Log($"[StartSplash] Poster {poster.width} x {poster.height} up at frame {createdFrame}, "
                + $"{createdAt:0.000} s after start (hold {HoldSeconds} s, fade {FadeSeconds} s).");
        }

        private void Update()
        {
            double now = Time.realtimeSinceStartupAsDouble;
            if (shownAt < 0d && Time.frameCount > createdFrame)
            {
                // The frame the splash was built in has been presented: the poster is on screen from here.
                shownAt = now;
            }
            BlockInput();
            if (!fading)
            {
                bool held = shownAt >= 0d && now - shownAt >= HoldSeconds;
                bool ready = bootDone && Time.frameCount >= bootFrame + 2;
                bool timedOut = now - createdAt >= MaxHoldSeconds;
                if ((held && ready) || timedOut)
                {
                    if (timedOut && !(held && ready))
                    {
                        Debug.LogWarning($"[StartSplash] Lifted after {MaxHoldSeconds} s (boot reported: {bootDone}).");
                    }
                    fading = true;
                    fadeStart = now;
                }
                return;
            }
            float t = FadeSeconds > 0f ? (float)((now - fadeStart) / FadeSeconds) : 1f;
            Group.alpha = 1f - Mathf.SmoothStep(0f, 1f, t);
            if (t >= 1f)
            {
                Debug.Log($"[StartSplash] Gone at frame {Time.frameCount}: poster shown {now - shownAt:0.00} s "
                    + $"({now:0.00} s after start).");
                Cleanup();
                Destroy(gameObject);
            }
        }

        /// <summary>Switches off the EventSystem's input module (once it exists) until the splash is gone.</summary>
        private void BlockInput()
        {
            if (blockedModule != null || cleaned)
            {
                return;
            }
            EventSystem events = EventSystem.current;
            if (events == null)
            {
                return;
            }
            BaseInputModule module = events.GetComponent<BaseInputModule>();
            if (module != null && module.enabled)
            {
                module.enabled = false;
                blockedModule = module;
            }
        }

        /// <summary>Gives the input back and releases the poster's texture. Idempotent (the fade's end, or OnDestroy).</summary>
        private void Cleanup()
        {
            if (cleaned)
            {
                return;
            }
            cleaned = true;
            if (blockedModule != null)
            {
                blockedModule.enabled = true;
                blockedModule = null;
            }
            if (Poster != null)
            {
                Poster.texture = null;
            }
            if (texture != null)
            {
                Resources.UnloadAsset(texture);
                texture = null;
            }
            if (Current == this)
            {
                Current = null;
            }
        }

        private void OnDestroy()
        {
            Cleanup();
        }
    }
}
