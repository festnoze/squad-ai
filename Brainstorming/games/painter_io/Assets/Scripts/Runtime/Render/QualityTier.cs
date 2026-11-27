// Owned by B1. Contract 12.4: render quality tiers and the FPS watchdog.
// High (PC default): actor field scale 0.75, bicubic territory, central differences, shadows, both specular lobes, bloom
// allowed. Medium (Android default): scale 0.5, bilinear territory, shadows. Low: scale 0.35, no shadow taps, one lobe.
// SaveData.Quality forces a tier (0 Auto, 1 High, 2 Medium, 3 Low); Auto uses the platform default and the watchdog.
// The command line "-quality high|medium|low" forces a tier too (visual checks of a tier on PC).
// Wave C (infra-perf): each tier carries a render height cap (RenderScaleFor: Medium 1600 px, Low 1280 px, High none, 1920
// on Android as contract 11.1), applied to the URP render scale by LiquidRenderer. The watchdog drops outlier frames
// (longer than max(0.1 s, 4 frame budgets): a hitch, a suspended process) by restarting its window instead of averaging
// them in, and LiquidRenderer only feeds it the frames of real rounds in Playing.
using System;
using System.Globalization;
using System.Runtime.CompilerServices;
using UnityEngine;

[assembly: InternalsVisibleTo("PainterIO.Tests.EditMode")]

namespace PainterIO.Runtime
{
    /// <summary>The three render tiers; the values match SaveData.Quality (1 High, 2 Medium, 3 Low).</summary>
    public enum RenderTier { High = 1, Medium = 2, Low = 3 }

    public static class QualityTier
    {
        /// <summary>Seconds ignored after a session starts before the watchdog measures.</summary>
        public const float WatchdogWarmupSeconds = 5f;
        /// <summary>Length of the averaging window of the watchdog.</summary>
        public const float WatchdogWindowSeconds = 3f;
        /// <summary>The watchdog steps down when the window average is below this fraction of the target rate.</summary>
        public const float WatchdogRatio = 0.83f;
        /// <summary>A frame longer than max(this, WatchdogOutlierBudgets / target) is an outlier: it restarts the window.</summary>
        public const float WatchdogOutlierSeconds = 0.1f;
        /// <summary>Frame budgets (1 / target) beyond which a frame is an outlier (see WatchdogOutlierSeconds).</summary>
        public const float WatchdogOutlierBudgets = 4f;
        /// <summary>Render height cap of the Medium tier in pixels (RenderScaleFor).</summary>
        public const int MediumRenderHeight = 1600;
        /// <summary>Render height cap of the Low tier in pixels (RenderScaleFor).</summary>
        public const int LowRenderHeight = 1280;
        /// <summary>Render height cap of the High tier on Android (contract 11.1); High has no cap elsewhere.</summary>
        public const int AndroidHighRenderHeight = 1920;

        private static bool initialized;
        private static bool initializedOnce;
        private static RenderTier current = RenderTier.High;
        private static RenderTier autoTier;
        private static bool autoTierSet;
        private static bool steppedThisSession;
        private static float sessionClock;
        private static float windowTime;
        private static int windowFrames;

        /// <summary>Raised when Current changes (forced setting, command line or watchdog step).</summary>
        public static event Action Changed;

        /// <summary>The active tier.</summary>
        public static RenderTier Current
        {
            get
            {
                EnsureInitialized();
                return current;
            }
        }

        /// <summary>High on desktop, Medium on Android and other handhelds.</summary>
        public static RenderTier PlatformDefault => Application.isMobilePlatform ? RenderTier.Medium : RenderTier.High;

        /// <summary>True when neither SaveData.Quality nor the command line forces a tier (the watchdog may act).</summary>
        public static bool IsAuto => CommandLineTier() == null && ForcedSetting() == null;

        /// <summary>Times the watchdog stepped the tier down since the application started.</summary>
        public static int WatchdogSteps { get; private set; }

        /// <summary>Actor field resolution scale (RT size = view size x ppu x scale).</summary>
        public static float ActorFieldScale => ScaleOf(Current);

        public static bool Bicubic => Current == RenderTier.High;
        public static bool CentralDifferences => Current == RenderTier.High;
        public static bool Shadows => Current != RenderTier.Low;
        public static int SpecularLobes => Current == RenderTier.High ? 2 : 1;
        public static bool BloomAllowed => Current == RenderTier.High && !Application.isMobilePlatform;

        /// <summary>The _PIO_Quality global: (specular lobes, shadow taps, bicubic territory, central differences).</summary>
        public static Vector4 ShaderFlags => new Vector4(SpecularLobes, Shadows ? 1f : 0f, Bicubic ? 1f : 0f, CentralDifferences ? 1f : 0f);

        public static float ScaleOf(RenderTier tier)
        {
            switch (tier)
            {
                case RenderTier.High: return 0.75f;
                case RenderTier.Medium: return 0.5f;
                default: return 0.35f;
            }
        }

        /// <summary>
        /// The render height cap of a tier in pixels, 0 for none: Medium 1600, Low 1280, High 1920 on Android (contract
        /// 11.1) and none elsewhere.
        /// </summary>
        public static int RenderHeightCap(RenderTier tier, bool android)
        {
            switch (tier)
            {
                case RenderTier.Medium: return MediumRenderHeight;
                case RenderTier.Low: return LowRenderHeight;
                default: return android ? AndroidHighRenderHeight : 0;
            }
        }

        /// <summary>
        /// The URP render scale of a screen height on a tier: cap / screenHeight when the screen is taller than the tier's
        /// render height cap, else 1 (the composite is rendered at the capped height and upscaled bilinearly by URP; the
        /// overlay HUD stays native).
        /// </summary>
        public static float RenderScaleFor(int screenHeight, RenderTier tier, bool android)
        {
            int cap = RenderHeightCap(tier, android);
            return cap > 0 && screenHeight > cap ? cap / (float)screenHeight : 1f;
        }

        /// <summary>True when a frame of unscaledDeltaTime seconds is a watchdog outlier at the target rate.</summary>
        public static bool IsOutlierFrame(float unscaledDeltaTime, float target)
        {
            float budgets = target > 0f ? WatchdogOutlierBudgets / target : 0f;
            return unscaledDeltaTime > Mathf.Max(WatchdogOutlierSeconds, budgets);
        }

        /// <summary>Re-reads the forced setting (SaveData.Quality, command line) and raises Changed if the tier moved.</summary>
        public static void Refresh()
        {
            initialized = true;
            RenderTier next;
            RenderTier? cli = CommandLineTier();
            RenderTier? forced = ForcedSetting();
            if (cli.HasValue) next = cli.Value;
            else if (forced.HasValue) next = forced.Value;
            else
            {
                if (!autoTierSet)
                {
                    autoTier = PlatformDefault;
                    autoTierSet = true;
                }
                next = autoTier;
            }
            SetCurrent(next);
        }

        /// <summary>A session started: the watchdog ignores the next 5 s and may step down once in this session.</summary>
        public static void BeginSession()
        {
            EnsureInitialized();
            steppedThisSession = false;
            sessionClock = 0f;
            ResetWindow();
        }

        /// <summary>
        /// Called once per frame with the unscaled frame time. running = a real round is actually moving (not the attract,
        /// in Playing, not paused, not waiting for the human, not ended): frames of other states are not measured.
        /// </summary>
        public static void Tick(float unscaledDeltaTime, bool running)
        {
            EnsureInitialized();
            if (!IsAuto || steppedThisSession || current == RenderTier.Low) return;
            TickWatchdog(unscaledDeltaTime, running, TargetRate());
        }

        /// <summary>
        /// The watchdog proper, with the target rate given (Tick passes TargetRate(); the tests pass a fixed rate). Skips
        /// the auto check of Tick: the caller decides that the tier is automatic.
        /// </summary>
        internal static void TickWatchdog(float unscaledDeltaTime, bool running, float target)
        {
            EnsureInitialized();
            if (steppedThisSession || current == RenderTier.Low) return;
            if (!(unscaledDeltaTime > 0f) || float.IsInfinity(unscaledDeltaTime)) return;
            if (!running)
            {
                ResetWindow();
                return;
            }
            if (IsOutlierFrame(unscaledDeltaTime, target))
            {
                // A hitch (a GC pause, a shader warm-up, a suspended or dragged window) says nothing about the steady
                // rate: averaged in, one 1.5 s frame alone pulled a 60 fps window under the threshold.
                ResetWindow();
                return;
            }
            sessionClock += unscaledDeltaTime;
            if (sessionClock < WatchdogWarmupSeconds) return;
            if (target <= 30f) return;
            windowTime += unscaledDeltaTime;
            windowFrames++;
            if (windowTime < WatchdogWindowSeconds) return;
            float fps = windowFrames / windowTime;
            ResetWindow();
            if (fps >= WatchdogRatio * target) return;
            steppedThisSession = true;
            WatchdogSteps++;
            autoTier = current == RenderTier.High ? RenderTier.Medium : RenderTier.Low;
            autoTierSet = true;
            Debug.Log("[PainterIO] quality watchdog: " + fps.ToString("0.0", CultureInfo.InvariantCulture) + " fps < "
                      + (WatchdogRatio * target).ToString("0.0", CultureInfo.InvariantCulture) + ", tier " + current + " -> " + autoTier);
            SetCurrent(autoTier);
        }

        /// <summary>
        /// Tests only: puts the tier state back to a known start without raising Changed. With a tier, the state is
        /// initialized on that automatic tier with a fresh session; without one, it returns to the uninitialized state
        /// (the next read applies the forced setting or the platform default, and raises Changed).
        /// </summary>
        internal static void ResetForTests(RenderTier? start)
        {
            initialized = start.HasValue;
            initializedOnce = start.HasValue;
            current = start ?? RenderTier.High;
            autoTier = current;
            autoTierSet = start.HasValue;
            steppedThisSession = false;
            sessionClock = 0f;
            ResetWindow();
            WatchdogSteps = 0;
        }

        /// <summary>min(target frame rate (the refresh rate when it is -1), the display refresh rate).</summary>
        public static float TargetRate()
        {
            float refresh = 60f;
            try
            {
                double r = Screen.currentResolution.refreshRateRatio.value;
                if (r > 1.0 && !double.IsNaN(r) && !double.IsInfinity(r)) refresh = (float)r;
            }
            catch (Exception)
            {
                // Keep 60.
            }
            int target = Application.targetFrameRate;
            float t = target > 0 ? target : refresh;
            return Mathf.Min(t, refresh);
        }

        private static void ResetWindow()
        {
            windowTime = 0f;
            windowFrames = 0;
        }

        private static void EnsureInitialized()
        {
            if (!initialized) Refresh();
        }

        private static void SetCurrent(RenderTier next)
        {
            if (next == current && initializedOnce) return;
            initializedOnce = true;
            current = next;
            Action handler = Changed;
            if (handler == null) return;
            foreach (Delegate d in handler.GetInvocationList())
            {
                try
                {
                    ((Action)d)();
                }
                catch (Exception e)
                {
                    Debug.LogError("[PainterIO] QualityTier.Changed subscriber failed: " + e);
                }
            }
        }

        private static RenderTier? ForcedSetting()
        {
            int q;
            try
            {
                q = SaveData.Quality;
            }
            catch (Exception)
            {
                q = 0;
            }
            if (q == 1) return RenderTier.High;
            if (q == 2) return RenderTier.Medium;
            if (q == 3) return RenderTier.Low;
            return null;
        }

        private static RenderTier? CommandLineTier()
        {
            string v = LaunchArgs.Value("-quality");
            if (string.IsNullOrEmpty(v)) return null;
            switch (v.Trim().ToLowerInvariant())
            {
                case "high":
                case "1":
                    return RenderTier.High;
                case "medium":
                case "2":
                    return RenderTier.Medium;
                case "low":
                case "3":
                    return RenderTier.Low;
                default:
                    return null;
            }
        }
    }
}
