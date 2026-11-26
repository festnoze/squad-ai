using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using OutOfSight.Core;
using UnityEngine;

namespace OutOfSight
{
    /// <summary>ADSSHOP: how a shown (or refused) ad ended.</summary>
    public enum AdOutcome
    {
        /// <summary>Watched to the end (or closed once it allowed it).</summary>
        Completed,
        /// <summary>Skipped or closed early.</summary>
        Skipped,
        /// <summary>No ad loaded yet, or the provider is not initialized: nothing showed.</summary>
        NotReady,
        /// <summary>The network failed to show it: nothing (or almost nothing) showed.</summary>
        Failed,
    }

    /// <summary>ADSSHOP: the result of <see cref="IAdProvider.aShow"/>.</summary>
    public struct AdShowResult
    {
        public AdOutcome Outcome;
        /// <summary>A rewarded ad earned its reward.</summary>
        public bool Rewarded;
        public string Error;

        /// <summary>The ad took the screen (completed or skipped).</summary>
        public bool Shown => Outcome == AdOutcome.Completed || Outcome == AdOutcome.Skipped;

        public static AdShowResult Of(AdOutcome outcome, string error = null)
        {
            return new AdShowResult { Outcome = outcome, Error = error };
        }

        public override string ToString() => Outcome + (Rewarded ? " (rewarded)" : string.Empty) + (Error != null ? ": " + Error : string.Empty);
    }

    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): one ad network (or mediation) behind <see cref="AdService"/>. To plug a new
    /// network: write one class implementing this interface (preloading its ads after initialization, raising nothing
    /// off the main thread), register it under a name with <see cref="AdProviderRegistry.Register"/> from a
    /// [RuntimeInitializeOnLoadMethod], and set "provider" in Resources/Config/ads.json to that name. Adapters that need
    /// an SDK live in Assets/Scripts/Adapters behind a scripting define symbol, so the project compiles without the SDK.
    /// </summary>
    public interface IAdProvider
    {
        /// <summary>The registry name ("none", "simulated", "applovin_max"...).</summary>
        string Name { get; }

        bool Initialized { get; }

        /// <summary>Starts the SDK (consent flow included, when the network runs one) and begins loading ads. True when ready to load.</summary>
        Task<bool> aInitialize(AdConfig config);

        /// <summary>An ad of <paramref name="format"/> is loaded and can show at once.</summary>
        bool IsReady(AdFormat format);

        /// <summary>Shows an ad full screen and completes when it closed. Never throws.</summary>
        Task<AdShowResult> aShow(AdFormat format, string placement);

        /// <summary>The network offers a privacy options form (GDPR: the user must be able to change their consent).</summary>
        bool SupportsPrivacyOptions { get; }

        /// <summary>Opens the privacy options form; true when it showed. Never throws.</summary>
        Task<bool> aShowPrivacyOptions();
    }

    /// <summary>ADSSHOP: the provider names <see cref="AdService"/> can create. "none" and "simulated" are built in.</summary>
    public static class AdProviderRegistry
    {
        private static readonly Dictionary<string, Func<IAdProvider>> Factories = new Dictionary<string, Func<IAdProvider>>
        {
            { AdConfig.ProviderNone, () => new NoAdProvider() },
            { AdConfig.ProviderSimulated, () => new SimulatedAdProvider() },
        };

        /// <summary>Registers (or replaces) the factory of <paramref name="name"/> (an adapter calls it at load).</summary>
        public static void Register(string name, Func<IAdProvider> factory)
        {
            string key = AdConfig.NormalizeName(name);
            if (string.IsNullOrEmpty(key) || factory == null)
            {
                return;
            }
            Factories[key] = factory;
        }

        public static bool Has(string name)
        {
            string key = AdConfig.NormalizeName(name);
            return key != null && Factories.ContainsKey(key);
        }

        /// <summary>A new provider of that name, or null when none is registered (its SDK or define symbol is missing).</summary>
        public static IAdProvider Create(string name)
        {
            string key = AdConfig.NormalizeName(name);
            if (key == null || !Factories.TryGetValue(key, out Func<IAdProvider> factory))
            {
                return null;
            }
            try
            {
                return factory();
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[Ads] cannot create the provider '{key}': {e.Message}");
                return null;
            }
        }
    }

    /// <summary>ADSSHOP: no ads at all (Windows, the editor, the master switch off, an unknown provider).</summary>
    public sealed class NoAdProvider : IAdProvider
    {
        public string Name => AdConfig.ProviderNone;
        public bool Initialized => true;
        public bool SupportsPrivacyOptions => false;
        public Task<bool> aInitialize(AdConfig config) => Task.FromResult(true);
        public bool IsReady(AdFormat format) => false;
        public Task<AdShowResult> aShow(AdFormat format, string placement) => Task.FromResult(AdShowResult.Of(AdOutcome.NotReady));
        public Task<bool> aShowPrivacyOptions() => Task.FromResult(false);
    }
}
