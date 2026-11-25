using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace OutOfSight.Core
{
    /// <summary>ADSSHOP: the ad formats a provider may show. Interstitial is the automatic end-of-level ad.</summary>
    public enum AdFormat
    {
        Interstitial,
        Rewarded,
    }

    /// <summary>ADSSHOP: which level ends may show the automatic ad.</summary>
    public enum AdPlacement
    {
        Win,
        Fail,
        Both,
    }

    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): the ads configuration, read from Resources/Config/ads.json over the code
    /// defaults below (<see cref="Parse"/>), and overlaid again later by a remote config if one is wired
    /// (Runtime AdService.ApplyRemoteConfig). Every field is clamped to a sane range; a malformed field keeps its previous
    /// value, a malformed file keeps the whole base config. Pure data and rules: nothing here touches Unity.
    /// Ads run on Android only: on Windows and in the editor the provider resolves to "none" unless
    /// <see cref="ForceSimulated"/> asks for the fake ad (testing). Batch mode, the probe and the look agent never show ads.
    /// </summary>
    public sealed class AdConfig
    {
        public const string ProviderNone = "none";
        public const string ProviderSimulated = "simulated";
        public const string ProviderApplovinMax = "applovin_max";

        /// <summary>Master switch: false never shows an ad, whatever else the config says.</summary>
        public bool Enabled = true;

        /// <summary>The provider to use on Android ("none", "simulated", "applovin_max", or any registered adapter name).</summary>
        public string Provider = ProviderNone;

        /// <summary>Testing only: the Simulated provider on every platform (editor, Windows), whatever <see cref="Provider"/> says.</summary>
        public bool ForceSimulated;

        /// <summary>
        /// The automatic end-of-level ad's format. Networks require rewarded ads to be opt-in, so a real provider shows the
        /// automatic placement as an interstitial even when this says rewarded (<see cref="AutomaticFormat"/>).
        /// </summary>
        public AdFormat Format = AdFormat.Interstitial;

        public AdPlacement Placement = AdPlacement.Both;

        /// <summary>The first level (1-based, in play order) whose end may show an ad: never on the first levels.</summary>
        public int FirstEligibleLevel = 4;

        /// <summary>An ad at most once every N eligible level ends (1: every eligible end).</summary>
        public int EveryNLevelEnds = 2;

        /// <summary>The cooldown: seconds between two ads.</summary>
        public float MinSecondsBetweenAds = 120f;

        /// <summary>No ad during the first seconds of a session (the launch, or the first minutes of play).</summary>
        public float MinSecondsAfterLaunch = 90f;

        /// <summary>A level that ended faster than this (a quick fail, a quick retry) never shows an ad and is not counted.</summary>
        public float MinSecondsInLevel = 20f;

        /// <summary>At most this many ads per session; 0 is unlimited.</summary>
        public int MaxAdsPerSession;

        /// <summary>Seconds the win or fail panel shows before the ad (the result and its jingle stay readable).</summary>
        public float ShowDelaySeconds = 1.2f;

        /// <summary>
        /// The wished-for ad length. Only the Simulated provider honours it: real networks pick the creative, the duration
        /// and the skip delay server-side (docs/next/ADS_STUDY.md, "Durée des pubs").
        /// </summary>
        public int PreferredMaxDurationSeconds = 15;

        /// <summary>When the skip button unlocks (Simulated provider only, like <see cref="PreferredMaxDurationSeconds"/>).</summary>
        public int SkippableAfterSeconds = 5;

        /// <summary>
        /// ADVIDEO (2026-11-25): the Simulated provider's ad video, a VideoClip path under Resources (no extension). Empty:
        /// the text card. The video's own length then replaces <see cref="PreferredMaxDurationSeconds"/>.
        /// </summary>
        public string SimulatedVideo = "Ads/out_of_sight_ad";

        /// <summary>
        /// ADSEVERY (2026-11-25): simulation override. With the Simulated provider active, an ad at EVERY level end, win and
        /// fail, from the first level: <see cref="PolicyFor"/> drops the frequency rules (first level, placement, level
        /// lists, quick end, launch grace, cooldown, every N, session cap) and the director drops the finale exception.
        /// The master switch and the No ads entitlement still apply. Never changes what a real provider does.
        /// </summary>
        public bool SimulatedEveryLevelEnd;

        /// <summary>When not empty, only these level ids may show an ad.</summary>
        public List<string> OnlyLevels = new List<string>();

        /// <summary>These level ids never show an ad.</summary>
        public List<string> ExcludedLevels = new List<string>();

        /// <summary>Development only: opens the network's own debugger once initialized (when the adapter has one).</summary>
        public bool ShowMediationDebugger;

        /// <summary>Per provider settings (ad unit ids, app ids), provider name to key to value; strings only.</summary>
        public Dictionary<string, Dictionary<string, string>> Providers = new Dictionary<string, Dictionary<string, string>>();

        public static AdConfig Defaults() => new AdConfig();

        /// <summary>A provider's setting, or null when missing or empty.</summary>
        public string ProviderSetting(string provider, string key)
        {
            if (provider == null || key == null || Providers == null)
            {
                return null;
            }
            if (Providers.TryGetValue(provider, out Dictionary<string, string> settings) && settings != null
                && settings.TryGetValue(key, out string value) && !string.IsNullOrWhiteSpace(value))
            {
                return value.Trim();
            }
            return null;
        }

        /// <summary>
        /// The provider this run uses: "none" when ads may not run here (batch mode, the probe; <paramref name="runtimeAllowed"/>
        /// false) or are switched off; "simulated" when <see cref="ForceSimulated"/>; otherwise <see cref="Provider"/> on
        /// Android only, "none" on any other platform.
        /// </summary>
        public string ResolveProvider(bool android, bool runtimeAllowed)
        {
            if (!runtimeAllowed || !Enabled)
            {
                return ProviderNone;
            }
            if (ForceSimulated) // MUTATION:ADS_FORCE_SIMULATED
            {
                return ProviderSimulated;
            }
            if (!android)
            {
                return ProviderNone;
            }
            string name = NormalizeName(Provider);
            return string.IsNullOrEmpty(name) ? ProviderNone : name;
        }

        /// <summary>
        /// The format of the automatic end-of-level ad: <see cref="Format"/>, except that a real network gets an
        /// interstitial instead of a rewarded ad (rewarded ads must be opt-in under AdMob and AppLovin policies).
        /// </summary>
        public AdFormat AutomaticFormat(bool simulatedProvider)
        {
            return Format == AdFormat.Rewarded && simulatedProvider ? AdFormat.Rewarded : AdFormat.Interstitial;
        }

        /// <summary>
        /// ADSEVERY: true when the automatic ad shows at every level end with this provider: the Simulated provider and
        /// <see cref="SimulatedEveryLevelEnd"/> both.
        /// </summary>
        public bool EveryLevelEnd(bool simulatedProvider) => simulatedProvider && SimulatedEveryLevelEnd; // MUTATION:ADS_SIMULATED_EVERY_END

        /// <summary>
        /// ADSEVERY: the rules <see cref="AdPolicy.Decide"/> applies with the active provider. A real provider (or the
        /// Simulated one without <see cref="SimulatedEveryLevelEnd"/>) gets this config untouched. The Simulated provider with
        /// the override gets a copy with every frequency rule off: first level 1, both outcomes, no level lists, no quick
        /// end, no launch grace, no cooldown, every end, no session cap. <see cref="Enabled"/> stays, and the No ads
        /// entitlement is checked by the policy before any of these. This config is never modified.
        /// </summary>
        public AdConfig PolicyFor(bool simulatedProvider)
        {
            if (!EveryLevelEnd(simulatedProvider))
            {
                return this;
            }
            AdConfig every = Clone();
            every.Placement = AdPlacement.Both;
            every.FirstEligibleLevel = 1;
            every.OnlyLevels.Clear();
            every.ExcludedLevels.Clear();
            every.MinSecondsInLevel = 0f;
            every.MinSecondsAfterLaunch = 0f;
            every.MinSecondsBetweenAds = 0f;
            every.EveryNLevelEnds = 1;
            every.MaxAdsPerSession = 0;
            return every;
        }

        /// <summary>Lower case, trimmed; null stays null.</summary>
        public static string NormalizeName(string name) => name?.Trim().ToLowerInvariant();

        public AdConfig Clone()
        {
            var copy = (AdConfig)MemberwiseClone();
            copy.OnlyLevels = new List<string>(OnlyLevels ?? new List<string>());
            copy.ExcludedLevels = new List<string>(ExcludedLevels ?? new List<string>());
            copy.Providers = new Dictionary<string, Dictionary<string, string>>();
            if (Providers != null)
            {
                foreach (KeyValuePair<string, Dictionary<string, string>> p in Providers)
                {
                    copy.Providers[p.Key] = p.Value != null ? new Dictionary<string, string>(p.Value) : new Dictionary<string, string>();
                }
            }
            return copy;
        }

        /// <summary>Every field inside its range (in place); returns this config.</summary>
        public AdConfig Clamp()
        {
            Provider = string.IsNullOrWhiteSpace(Provider) ? ProviderNone : NormalizeName(Provider);
            FirstEligibleLevel = Math.Max(1, FirstEligibleLevel);
            EveryNLevelEnds = Math.Max(1, EveryNLevelEnds);
            MinSecondsBetweenAds = Finite(MinSecondsBetweenAds, 0f, 3600f);
            MinSecondsAfterLaunch = Finite(MinSecondsAfterLaunch, 0f, 3600f);
            MinSecondsInLevel = Finite(MinSecondsInLevel, 0f, 600f);
            MaxAdsPerSession = Math.Max(0, MaxAdsPerSession);
            ShowDelaySeconds = Finite(ShowDelaySeconds, 0f, 10f);
            PreferredMaxDurationSeconds = Math.Max(1, Math.Min(60, PreferredMaxDurationSeconds));
            SkippableAfterSeconds = Math.Max(0, Math.Min(PreferredMaxDurationSeconds, SkippableAfterSeconds));
            OnlyLevels = OnlyLevels ?? new List<string>();
            ExcludedLevels = ExcludedLevels ?? new List<string>();
            Providers = Providers ?? new Dictionary<string, Dictionary<string, string>>();
            return this;
        }

        private static float Finite(float value, float min, float max)
        {
            if (float.IsNaN(value) || float.IsInfinity(value))
            {
                return min;
            }
            return Math.Max(min, Math.Min(max, value));
        }

        /// <summary>
        /// A copy of <paramref name="baseConfig"/> (the defaults when null) with every field present in
        /// <paramref name="json"/> applied, then clamped. A field of the wrong type keeps the base value. Never throws:
        /// not JSON or not an object returns the base copy with <paramref name="problem"/> set.
        /// </summary>
        public static AdConfig Parse(string json, AdConfig baseConfig, out string problem)
        {
            problem = null;
            AdConfig config = (baseConfig ?? Defaults()).Clone();
            try
            {
                if (string.IsNullOrWhiteSpace(json))
                {
                    problem = "empty";
                    return config.Clamp();
                }
                if (!(JToken.Parse(json) is JObject root))
                {
                    problem = "not a JSON object";
                    return config.Clamp();
                }
                config.Overlay(root);
            }
            catch (Exception e)
            {
                problem = e.GetType().Name + ": " + e.Message;
                return (baseConfig ?? Defaults()).Clone().Clamp();
            }
            return config.Clamp();
        }

        /// <summary>Applies every known key of <paramref name="root"/> that has the right type (in place, not clamped).</summary>
        private void Overlay(JObject root)
        {
            Enabled = Bool(root["enabled"], Enabled);
            Provider = Str(root["provider"], Provider);
            ForceSimulated = Bool(root["forceSimulated"], ForceSimulated);
            string format = NormalizeName(Str(root["format"], null));
            if (format == "interstitial")
            {
                Format = AdFormat.Interstitial;
            }
            else if (format == "rewarded")
            {
                Format = AdFormat.Rewarded;
            }
            string placement = NormalizeName(Str(root["placement"], null));
            if (placement == "win")
            {
                Placement = AdPlacement.Win;
            }
            else if (placement == "fail")
            {
                Placement = AdPlacement.Fail;
            }
            else if (placement == "both")
            {
                Placement = AdPlacement.Both;
            }
            FirstEligibleLevel = Int(root["firstEligibleLevel"], FirstEligibleLevel);
            EveryNLevelEnds = Int(root["everyNLevelEnds"], EveryNLevelEnds);
            MinSecondsBetweenAds = Num(root["minSecondsBetweenAds"], MinSecondsBetweenAds);
            MinSecondsAfterLaunch = Num(root["minSecondsAfterLaunch"], MinSecondsAfterLaunch);
            MinSecondsInLevel = Num(root["minSecondsInLevel"], MinSecondsInLevel);
            MaxAdsPerSession = Int(root["maxAdsPerSession"], MaxAdsPerSession);
            ShowDelaySeconds = Num(root["showDelaySeconds"], ShowDelaySeconds);
            PreferredMaxDurationSeconds = Int(root["preferredMaxDurationSeconds"], PreferredMaxDurationSeconds);
            SkippableAfterSeconds = Int(root["skippableAfterSeconds"], SkippableAfterSeconds);
            SimulatedVideo = Str(root["simulatedVideo"], SimulatedVideo);
            SimulatedEveryLevelEnd = Bool(root["simulatedEveryLevelEnd"], SimulatedEveryLevelEnd);
            OnlyLevels = StrList(root["onlyLevels"], OnlyLevels);
            ExcludedLevels = StrList(root["excludedLevels"], ExcludedLevels);
            ShowMediationDebugger = Bool(root["showMediationDebugger"], ShowMediationDebugger);
            if (root["providers"] is JObject providers)
            {
                foreach (JProperty provider in providers.Properties())
                {
                    if (!(provider.Value is JObject settings))
                    {
                        continue;
                    }
                    string name = NormalizeName(provider.Name);
                    if (string.IsNullOrEmpty(name))
                    {
                        continue;
                    }
                    if (!Providers.TryGetValue(name, out Dictionary<string, string> into) || into == null)
                    {
                        into = new Dictionary<string, string>();
                        Providers[name] = into;
                    }
                    foreach (JProperty setting in settings.Properties())
                    {
                        if (setting.Value.Type == JTokenType.String)
                        {
                            into[setting.Name] = setting.Value.Value<string>();
                        }
                    }
                }
            }
        }

        // ----- Tolerant readers: the right type or the fallback. -----

        internal static bool Bool(JToken token, bool fallback)
        {
            return token != null && token.Type == JTokenType.Boolean ? token.Value<bool>() : fallback;
        }

        internal static string Str(JToken token, string fallback)
        {
            return token != null && token.Type == JTokenType.String ? token.Value<string>() : fallback;
        }

        internal static int Int(JToken token, int fallback)
        {
            if (token == null || (token.Type != JTokenType.Integer && token.Type != JTokenType.Float))
            {
                return fallback;
            }
            double value = token.Value<double>();
            if (double.IsNaN(value) || double.IsInfinity(value) || value > int.MaxValue || value < int.MinValue)
            {
                return fallback;
            }
            return (int)Math.Round(value);
        }

        internal static float Num(JToken token, float fallback)
        {
            if (token == null || (token.Type != JTokenType.Integer && token.Type != JTokenType.Float))
            {
                return fallback;
            }
            double value = token.Value<double>();
            return double.IsNaN(value) || double.IsInfinity(value) ? fallback : (float)value;
        }

        internal static List<string> StrList(JToken token, List<string> fallback)
        {
            if (!(token is JArray array))
            {
                return fallback;
            }
            var list = new List<string>();
            foreach (JToken item in array)
            {
                string s = item.Type == JTokenType.String ? item.Value<string>()?.Trim() : null;
                if (!string.IsNullOrEmpty(s) && !list.Contains(s))
                {
                    list.Add(s);
                }
            }
            return list;
        }
    }
}
