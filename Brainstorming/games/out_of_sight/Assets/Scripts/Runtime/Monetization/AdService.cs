using System;
using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): the provider-agnostic ad layer. Main boots it after the save (the No ads
    /// purchase lives there): it reads Resources/Config/ads.json over the code defaults (<see cref="AdConfig"/>), picks the
    /// provider (<see cref="AdConfig.ResolveProvider"/>: Android only, "none" on Windows and in the editor unless the config
    /// forces the Simulated one, and never in batch mode or under the probe or the look agent), creates it from
    /// <see cref="AdProviderRegistry"/> and initializes it. <see cref="AdDirector"/> asks <see cref="EvaluateLevelEnd"/> at
    /// every win or fail (<see cref="AdPolicy"/>), then <see cref="aShowAd"/> shows the ad with the game and every sound
    /// paused for its length. A remote config can later call <see cref="ApplyRemoteConfig"/>.
    /// </summary>
    public static class AdService
    {
        /// <summary>The config's Resources path (Assets/Resources/Config/ads.json): readable synchronously on every platform.</summary>
        public const string ConfigResource = "Config/ads";

        public static AdConfig Config { get; private set; } = AdConfig.Defaults();
        public static IAdProvider Provider { get; private set; } = new NoAdProvider();
        public static AdPolicyState Policy { get; private set; } = new AdPolicyState();

        /// <summary>An ad is on screen (the game and the sounds are paused under it).</summary>
        public static bool Showing { get; private set; }

        /// <summary>The last level end's decision (tests, logs).</summary>
        public static AdDecision LastDecision { get; private set; } = AdDecision.Disabled;

        /// <summary>Raised when an ad starts (true) and ends (false).</summary>
        public static event Action<bool> ShowingChanged;

        /// <summary>The provider is a real one (or the Simulated one): level ends are worth evaluating.</summary>
        public static bool Active => Provider != null && Provider.Name != AdConfig.ProviderNone;

        /// <summary>The Simulated provider is in use.</summary>
        public static bool Simulated => Provider != null && Provider.Name == AdConfig.ProviderSimulated;

        /// <summary>
        /// ADSEVERY: the Simulated provider is in use and ads.json asks for an ad at every level end
        /// (<see cref="AdConfig.SimulatedEveryLevelEnd"/>): no frequency rule, no finale exception. False with a real provider.
        /// </summary>
        public static bool EveryLevelEnd => Config.EveryLevelEnd(Simulated);

        /// <summary>Ads may run in this process at all: not batch mode (the test suites), the probe or the look agent.</summary>
        public static bool RuntimeAllowed => !Application.isBatchMode && !Probe.Requested && !SaveStore.LookRequested;

        /// <summary>The ad clock: real seconds since the app started (the policy's "now").</summary>
        public static float Now => Time.realtimeSinceStartup;

        /// <summary>The No ads item is owned.</summary>
        public static bool NoAdsOwned => SaveStore.HasEntitlement(Entitlements.NoAds);

        /// <summary>Main, at boot: config, provider, policy session. Never throws.</summary>
        public static void Boot()
        {
            try
            {
                Config = LoadConfig();
                Policy = new AdPolicyState { SessionStart = Now };
                LastDecision = AdDecision.Disabled;
                UseProvider(Config.ResolveProvider(Application.platform == RuntimePlatform.Android, RuntimeAllowed));
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Ads] boot failed, no ads this session: " + e.Message);
                Provider = new NoAdProvider();
            }
        }

        /// <summary>Resources/Config/ads.json over the code defaults; the defaults alone (no ads) when it is missing or broken.</summary>
        public static AdConfig LoadConfig()
        {
            TextAsset asset = Resources.Load<TextAsset>(ConfigResource);
            if (asset == null)
            {
                Debug.LogWarning($"[Ads] Resources/{ConfigResource}.json is missing: code defaults (provider none)");
                return AdConfig.Defaults();
            }
            AdConfig config = AdConfig.Parse(asset.text, AdConfig.Defaults(), out string problem);
            if (problem != null)
            {
                Debug.LogWarning($"[Ads] Resources/{ConfigResource}.json: {problem}; code defaults kept");
            }
            return config;
        }

        /// <summary>
        /// The remote config hook: overlays <paramref name="json"/> (the same keys as ads.json, any subset) on the current
        /// config, and switches provider when the resolved one changed. Call it once the remote values arrived (Unity
        /// Remote Config, Firebase Remote Config, a plain HTTPS JSON). Never throws.
        /// </summary>
        public static void ApplyRemoteConfig(string json)
        {
            try
            {
                AdConfig next = AdConfig.Parse(json, Config, out string problem);
                if (problem != null)
                {
                    Debug.LogWarning("[Ads] remote config ignored: " + problem);
                    return;
                }
                Config = next;
                string name = Config.ResolveProvider(Application.platform == RuntimePlatform.Android, RuntimeAllowed);
                if (Provider == null || Provider.Name != name)
                {
                    UseProvider(name);
                }
                Debug.Log("[Ads] remote config applied");
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Ads] remote config failed: " + e.Message);
            }
        }

        private static void UseProvider(string name)
        {
            IAdProvider provider = AdProviderRegistry.Create(name);
            if (provider == null)
            {
                Debug.LogWarning($"[Ads] no adapter registered for '{name}' (SDK not installed, or its scripting define symbol "
                    + "missing): no ads this session");
                provider = new NoAdProvider();
            }
            Provider = provider;
            Debug.Log($"[Ads] provider {provider.Name} (configured '{Config.Provider}', enabled {Config.Enabled}, platform {Application.platform})"
                + (EveryLevelEnd ? ": simulation, an ad at every level end" : string.Empty));
            if (provider.Name != AdConfig.ProviderNone)
            {
                aInitializeProvider(provider);
            }
        }

        private static async void aInitializeProvider(IAdProvider provider)
        {
            try
            {
                bool ok = await provider.aInitialize(Config);
                Debug.Log($"[Ads] {provider.Name} initialized: {ok}");
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[Ads] {provider.Name} failed to initialize: {e.Message}");
            }
        }

        /// <summary>
        /// A level end (AdDirector): the policy's decision, which counts the end toward "every N" when it passes the level
        /// rules. "Disabled" when no provider is active. ADSEVERY: with the Simulated provider and
        /// <see cref="AdConfig.SimulatedEveryLevelEnd"/>, the policy runs on <see cref="AdConfig.PolicyFor"/>'s copy with
        /// every frequency rule off (the master switch and No ads still apply). Never throws.
        /// </summary>
        public static AdDecision EvaluateLevelEnd(AdLevelEnd end)
        {
            try
            {
                LastDecision = Active ? AdPolicy.Decide(Config.PolicyFor(Simulated), Policy, end, Now, NoAdsOwned) : AdDecision.Disabled;
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Ads] policy failed: " + e.Message);
                LastDecision = AdDecision.Disabled;
            }
            return LastDecision;
        }

        /// <summary>The format the automatic end-of-level ad uses with the current provider.</summary>
        public static AdFormat AutomaticFormat => Config.AutomaticFormat(Simulated);

        /// <summary>
        /// Shows an ad now, with the game paused and every sound silenced for its length (the music ignores the listener
        /// pause, so the listener volume goes to 0 as well); restores both after. A shown ad starts the policy's cooldown
        /// and every-N count again. NotReady when another ad shows or none is loaded. Never throws.
        /// </summary>
        public static async Task<AdShowResult> aShowAd(AdFormat format, string placement)
        {
            IAdProvider provider = Provider;
            if (Showing || provider == null || !provider.Initialized || !provider.IsReady(format))
            {
                return AdShowResult.Of(AdOutcome.NotReady);
            }
            AdShowResult result;
            Showing = true;
            BeginAdPause();
            RaiseShowing(true);
            try
            {
                result = await provider.aShow(format, placement);
            }
            catch (Exception e)
            {
                result = AdShowResult.Of(AdOutcome.Failed, e.Message);
            }
            finally
            {
                EndAdPause();
                Showing = false;
                RaiseShowing(false);
            }
            if (result.Shown)
            {
                Policy.RecordShown(Now);
            }
            Debug.Log($"[Ads] {format} at {placement}: {result}");
            return result;
        }

        /// <summary>
        /// An opt-in rewarded ad (a future "watch an ad to..." button): allowed even with No ads owned, since the player
        /// asked for it. True when the reward was earned.
        /// </summary>
        public static async Task<bool> aShowRewardedAd(string placement)
        {
            AdShowResult result = await aShowAd(AdFormat.Rewarded, placement);
            return result.Rewarded;
        }

        /// <summary>The provider can open its privacy options form (GDPR users must be able to change their consent).</summary>
        public static bool PrivacyOptionsAvailable => Provider != null && Provider.SupportsPrivacyOptions;

        /// <summary>Opens the provider's privacy options form, the sounds paused meanwhile. True when it showed. Never throws.</summary>
        public static async Task<bool> aShowPrivacyOptions()
        {
            IAdProvider provider = Provider;
            if (Showing || provider == null || !provider.SupportsPrivacyOptions)
            {
                return false;
            }
            Showing = true;
            BeginAdPause();
            try
            {
                return await provider.aShowPrivacyOptions();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Ads] privacy options failed: " + e.Message);
                return false;
            }
            finally
            {
                EndAdPause();
                Showing = false;
            }
        }

        private static void RaiseShowing(bool showing)
        {
            try
            {
                ShowingChanged?.Invoke(showing);
            }
            catch (Exception e)
            {
                Debug.LogException(e);
            }
        }

        // ----- The pause under an ad -----

        /// <summary>The game paused (no rule runs, no gameplay press is read) and every sound silenced.</summary>
        private static void BeginAdPause()
        {
            GameState game = Main.Instance != null ? Main.Instance.Game : null;
            if (game != null)
            {
                game.Paused = true;
            }
            else
            {
                GamePause.IsPaused = true;
                AudioListener.pause = true;
            }
            AudioListener.volume = 0f;
        }

        /// <summary>
        /// ADSEVERY: while an ad (or the privacy notice) shows, puts the pause and the silence back when something lifted
        /// them under the overlay: Escape, gamepad Start or the Android back key toggle the pause menu behind it, and
        /// closing that menu unpauses the game (Menu.Apply), which would let R restart the level under the ad.
        /// AdDirector calls it every LateUpdate, so the next frame's GameState.Update sees the pause again. Never throws.
        /// </summary>
        public static void KeepAdPause()
        {
            if (!Showing)
            {
                return;
            }
            GameState game = Main.Instance != null ? Main.Instance.Game : null;
            if (game != null && !game.Paused)
            {
                game.Paused = true;
            }
            if (AudioListener.volume != 0f)
            {
                AudioListener.volume = 0f;
            }
        }

        /// <summary>Back to what the menus want (paused only under an open menu) and the options' volume.</summary>
        private static void EndAdPause()
        {
            Main main = Main.Instance;
            bool menuOpen = main != null && main.Menu != null && main.Menu.IsOpen;
            if (main != null && main.Game != null)
            {
                main.Game.Paused = menuOpen;
            }
            else
            {
                GamePause.IsPaused = menuOpen;
                AudioListener.pause = menuOpen;
            }
            AudioListener.volume = AudioMute.Apply(SaveStore.AppliedVolume);
        }
    }
}
