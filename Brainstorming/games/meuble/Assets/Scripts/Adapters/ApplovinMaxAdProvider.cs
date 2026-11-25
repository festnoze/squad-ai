// ADSSHOP (docs/next/progress/ADSSHOP.md): the AppLovin MAX adapter, compiled only with the scripting define symbol
// OOS_ADS_APPLOVIN_MAX (Player Settings > Android > Scripting Define Symbols) once the MAX Unity plugin is installed.
// Without the symbol this file is empty and the project compiles without the SDK. It lives outside the game's asmdefs
// (Assembly-CSharp), which references every auto-referenced assembly, the MAX plugin's included, and the game's own.
// Written against the MAX Unity plugin 8.x documentation (support.applovin.com/en/max/unity); not compiled here, since
// the SDK is not installed yet: check the first build with the symbol for API drift.
#if OOS_ADS_APPLOVIN_MAX
using System;
using System.Threading;
using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight.Adapters
{
    /// <summary>
    /// ADSSHOP: <see cref="IAdProvider"/> over AppLovin MAX (mediation: AppLovin, Google bidding, Unity Ads, Meta... as
    /// set up in the MAX dashboard and the Integration Manager). The SDK key, the Terms and Privacy Policy flow (Google
    /// UMP for GDPR users) and the network adapters are set in AppLovin > Integration Manager, not in code. The ad unit
    /// ids come from ads.json: providers.applovin_max.interstitialAdUnitId and rewardedAdUnitId.
    /// MAX may raise its callbacks off the Unity main thread, so every callback is posted to the main thread first.
    /// </summary>
    public sealed class ApplovinMaxAdProvider : IAdProvider
    {
        private const int InitTimeoutMs = 30000;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void Register()
        {
            AdProviderRegistry.Register(AdConfig.ProviderApplovinMax, () => new ApplovinMaxAdProvider());
        }

        private SynchronizationContext mainThread;
        private string interstitialId;
        private string rewardedId;
        private int interstitialAttempts;
        private int rewardedAttempts;
        private TaskCompletionSource<AdShowResult> showing;
        private bool rewardEarned;

        public string Name => AdConfig.ProviderApplovinMax;
        public bool Initialized { get; private set; }

        public bool SupportsPrivacyOptions
        {
            get
            {
                if (!Initialized)
                {
                    return false;
                }
                try
                {
                    return MaxSdk.GetSdkConfiguration().ConsentFlowUserGeography == MaxSdkBase.ConsentFlowUserGeography.Gdpr;
                }
                catch (Exception)
                {
                    return false;
                }
            }
        }

        public async Task<bool> aInitialize(AdConfig config)
        {
            mainThread = SynchronizationContext.Current;
            interstitialId = config.ProviderSetting(Name, "interstitialAdUnitId");
            rewardedId = config.ProviderSetting(Name, "rewardedAdUnitId");
            if (string.IsNullOrEmpty(interstitialId) || interstitialId.StartsWith("REPLACE", StringComparison.Ordinal))
            {
                Debug.LogWarning("[Ads] applovin_max: providers.applovin_max.interstitialAdUnitId is not set in ads.json");
            }
            var ready = new TaskCompletionSource<bool>();
            try
            {
                MaxSdkCallbacks.OnSdkInitializedEvent += configuration => Post(() => ready.TrySetResult(true));

                MaxSdkCallbacks.Interstitial.OnAdLoadedEvent += (unit, info) => Post(() => interstitialAttempts = 0);
                MaxSdkCallbacks.Interstitial.OnAdLoadFailedEvent += (unit, error) => Post(() => aRetryLoad(AdFormat.Interstitial));
                MaxSdkCallbacks.Interstitial.OnAdDisplayFailedEvent += (unit, error, info) => Post(() =>
                {
                    Complete(AdShowResult.Of(AdOutcome.Failed, error != null ? error.Message : "display failed"));
                    Load(AdFormat.Interstitial);
                });
                MaxSdkCallbacks.Interstitial.OnAdHiddenEvent += (unit, info) => Post(() =>
                {
                    Complete(AdShowResult.Of(AdOutcome.Completed));
                    Load(AdFormat.Interstitial);
                });

                MaxSdkCallbacks.Rewarded.OnAdLoadedEvent += (unit, info) => Post(() => rewardedAttempts = 0);
                MaxSdkCallbacks.Rewarded.OnAdLoadFailedEvent += (unit, error) => Post(() => aRetryLoad(AdFormat.Rewarded));
                MaxSdkCallbacks.Rewarded.OnAdReceivedRewardEvent += (unit, reward, info) => Post(() => rewardEarned = true);
                MaxSdkCallbacks.Rewarded.OnAdDisplayFailedEvent += (unit, error, info) => Post(() =>
                {
                    Complete(AdShowResult.Of(AdOutcome.Failed, error != null ? error.Message : "display failed"));
                    Load(AdFormat.Rewarded);
                });
                MaxSdkCallbacks.Rewarded.OnAdHiddenEvent += (unit, info) => Post(() =>
                {
                    Complete(new AdShowResult { Outcome = rewardEarned ? AdOutcome.Completed : AdOutcome.Skipped, Rewarded = rewardEarned });
                    Load(AdFormat.Rewarded);
                });

                // The Terms and Privacy Policy flow (Integration Manager) runs inside InitializeSdk for GDPR users.
                MaxSdk.InitializeSdk();
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Ads] applovin_max: initialization failed: " + e.Message);
                return false;
            }
            Task finished = await Task.WhenAny(ready.Task, Task.Delay(InitTimeoutMs));
            if (finished != ready.Task)
            {
                Debug.LogWarning("[Ads] applovin_max: no initialization callback after 30 s");
                return false;
            }
            Initialized = true;
            if (config.ShowMediationDebugger)
            {
                MaxSdk.ShowMediationDebugger();
            }
            Load(AdFormat.Interstitial);
            Load(AdFormat.Rewarded);
            return true;
        }

        public bool IsReady(AdFormat format)
        {
            string unit = UnitOf(format);
            if (!Initialized || string.IsNullOrEmpty(unit))
            {
                return false;
            }
            try
            {
                return format == AdFormat.Rewarded ? MaxSdk.IsRewardedAdReady(unit) : MaxSdk.IsInterstitialReady(unit);
            }
            catch (Exception)
            {
                return false;
            }
        }

        public Task<AdShowResult> aShow(AdFormat format, string placement)
        {
            if (!IsReady(format) || showing != null)
            {
                return Task.FromResult(AdShowResult.Of(AdOutcome.NotReady));
            }
            showing = new TaskCompletionSource<AdShowResult>();
            rewardEarned = false;
            try
            {
                if (format == AdFormat.Rewarded)
                {
                    MaxSdk.ShowRewardedAd(rewardedId, placement);
                }
                else
                {
                    MaxSdk.ShowInterstitial(interstitialId, placement);
                }
            }
            catch (Exception e)
            {
                Complete(AdShowResult.Of(AdOutcome.Failed, e.Message));
            }
            return showing != null ? showing.Task : Task.FromResult(AdShowResult.Of(AdOutcome.Failed));
        }

        public Task<bool> aShowPrivacyOptions()
        {
            var shown = new TaskCompletionSource<bool>();
            try
            {
                MaxSdk.CmpService.ShowCmpForExistingUser(error => Post(() => shown.TrySetResult(error == null)));
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Ads] applovin_max: privacy options failed: " + e.Message);
                shown.TrySetResult(false);
            }
            return shown.Task;
        }

        private string UnitOf(AdFormat format) => format == AdFormat.Rewarded ? rewardedId : interstitialId;

        private void Load(AdFormat format)
        {
            string unit = UnitOf(format);
            if (string.IsNullOrEmpty(unit))
            {
                return;
            }
            try
            {
                if (format == AdFormat.Rewarded)
                {
                    MaxSdk.LoadRewardedAd(unit);
                }
                else
                {
                    MaxSdk.LoadInterstitial(unit);
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Ads] applovin_max: load failed: " + e.Message);
            }
        }

        /// <summary>AppLovin's recommended retry: an exponential backoff, 2^n seconds capped at 64.</summary>
        private async void aRetryLoad(AdFormat format)
        {
            int attempt = format == AdFormat.Rewarded ? ++rewardedAttempts : ++interstitialAttempts;
            double seconds = Math.Pow(2, Math.Min(6, attempt));
            await Task.Delay(TimeSpan.FromSeconds(seconds));
            Load(format);
        }

        private void Complete(AdShowResult result)
        {
            TaskCompletionSource<AdShowResult> pending = showing;
            showing = null;
            pending?.TrySetResult(result);
        }

        /// <summary>Runs <paramref name="action"/> on the Unity main thread (the SynchronizationContext captured at init).</summary>
        private void Post(Action action)
        {
            if (mainThread == null || SynchronizationContext.Current == mainThread)
            {
                action();
            }
            else
            {
                mainThread.Post(_ => action(), null);
            }
        }
    }
}
#endif
