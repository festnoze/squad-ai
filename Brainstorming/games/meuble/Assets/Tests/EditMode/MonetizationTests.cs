using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using OutOfSight.Core;

namespace OutOfSight.Tests
{
    /// <summary>
    /// ADSSHOP (docs/next/progress/ADSSHOP.md): the pure logic of the ads and the shop. The ad config (code defaults are
    /// safe, the JSON overlays only well typed keys, never throws, clamps), the provider choice (Android only, Simulated
    /// only when forced, never in batch mode), the frequency policy (master switch, No ads, placement, first level, level
    /// lists, quick ends not counted, launch grace, cooldown, every N, session cap; ADSEVERY: the Simulated provider's
    /// "every level end" override, which leaves the real rules alone), the shop catalog (replaces the
    /// defaults, skips bad entries, platform visibility), the purchases in the save (granted once, consumables counted,
    /// covered by a bundle, never failing a load, round trip), the strings in both languages, and the shipped JSON files.
    /// Filter: MonetizationTests.
    /// </summary>
    public sealed class MonetizationTests
    {
        private const string AdsJson = "Assets/Resources/Config/ads.json";
        private const string ShopJson = "Assets/Resources/Config/shop.json";

        // ----- AdConfig -----

        [Test]
        public void AdConfig_Defaults_ShowNothingUntilConfigured()
        {
            AdConfig config = AdConfig.Defaults();
            Assert.IsTrue(config.Enabled);
            Assert.AreEqual(AdConfig.ProviderNone, config.Provider, "the code fallback never shows ads");
            Assert.AreEqual(AdFormat.Interstitial, config.Format);
            Assert.GreaterOrEqual(config.FirstEligibleLevel, 2, "never on the first level");
            Assert.Greater(config.MinSecondsBetweenAds, 0f, "a cooldown by default");
            Assert.Greater(config.MinSecondsInLevel, 0f, "no ad after a quick retry by default");
        }

        [Test]
        public void AdConfig_Parse_OverlaysWellTypedKeysOnly()
        {
            const string json = "{ \"enabled\": false, \"provider\": \" AppLovin_MAX \", \"format\": \"rewarded\", \"placement\": \"win\","
                + " \"firstEligibleLevel\": 6, \"everyNLevelEnds\": 3, \"minSecondsBetweenAds\": 45.5, \"minSecondsInLevel\": \"ten\","
                + " \"onlyLevels\": [\"level7\", 3, \"level7\", \"level9\"], \"providers\": { \"applovin_max\": { \"interstitialAdUnitId\": \"abc\", \"n\": 4 } } }";
            AdConfig config = AdConfig.Parse(json, AdConfig.Defaults(), out string problem);
            Assert.IsNull(problem, problem);
            Assert.IsFalse(config.Enabled);
            Assert.AreEqual(AdConfig.ProviderApplovinMax, config.Provider, "trimmed and lower cased");
            Assert.AreEqual(AdFormat.Rewarded, config.Format);
            Assert.AreEqual(AdPlacement.Win, config.Placement);
            Assert.AreEqual(6, config.FirstEligibleLevel);
            Assert.AreEqual(3, config.EveryNLevelEnds);
            Assert.AreEqual(45.5f, config.MinSecondsBetweenAds, 1e-4f);
            Assert.AreEqual(AdConfig.Defaults().MinSecondsInLevel, config.MinSecondsInLevel, "a string keeps the default");
            CollectionAssert.AreEqual(new[] { "level7", "level9" }, config.OnlyLevels, "strings only, once each");
            Assert.AreEqual("abc", config.ProviderSetting(AdConfig.ProviderApplovinMax, "interstitialAdUnitId"));
            Assert.IsNull(config.ProviderSetting(AdConfig.ProviderApplovinMax, "n"), "a number is not a setting");
            Assert.IsNull(config.ProviderSetting("admob", "appId"));
        }

        [Test]
        public void AdConfig_Parse_NeverThrows_AndKeepsTheBase()
        {
            AdConfig baseConfig = AdConfig.Defaults();
            baseConfig.FirstEligibleLevel = 7;
            foreach (string bad in new[] { null, "", "   ", "not json", "[1, 2]", "42", "{ \"enabled\": " })
            {
                AdConfig config = AdConfig.Parse(bad, baseConfig, out string problem);
                Assert.IsNotNull(config, $"'{bad}' returned null");
                Assert.IsNotNull(problem, $"'{bad}' raised no problem");
                Assert.AreEqual(7, config.FirstEligibleLevel, $"'{bad}' lost the base");
            }
            Assert.AreEqual(7, baseConfig.FirstEligibleLevel, "the base is never modified");
        }

        [Test]
        public void AdConfig_Parse_Clamps()
        {
            const string json = "{ \"firstEligibleLevel\": -3, \"everyNLevelEnds\": 0, \"minSecondsBetweenAds\": -1, \"maxAdsPerSession\": -2,"
                + " \"showDelaySeconds\": 99, \"preferredMaxDurationSeconds\": 0, \"skippableAfterSeconds\": 30, \"provider\": \"\" }";
            AdConfig config = AdConfig.Parse(json, null, out string problem);
            Assert.IsNull(problem, problem);
            Assert.AreEqual(1, config.FirstEligibleLevel);
            Assert.AreEqual(1, config.EveryNLevelEnds);
            Assert.AreEqual(0f, config.MinSecondsBetweenAds);
            Assert.AreEqual(0, config.MaxAdsPerSession);
            Assert.AreEqual(10f, config.ShowDelaySeconds);
            Assert.AreEqual(1, config.PreferredMaxDurationSeconds);
            Assert.AreEqual(1, config.SkippableAfterSeconds, "never after the end of the ad");
            Assert.AreEqual(AdConfig.ProviderNone, config.Provider);
        }

        [Test]
        public void AdConfig_ResolveProvider_AndroidOnly_SimulatedWhenForced_NeverInBatch()
        {
            AdConfig config = AdConfig.Defaults();
            config.Provider = AdConfig.ProviderApplovinMax;
            Assert.AreEqual(AdConfig.ProviderApplovinMax, config.ResolveProvider(true, true));
            Assert.AreEqual(AdConfig.ProviderNone, config.ResolveProvider(false, true), "never on Windows or in the editor");
            Assert.AreEqual(AdConfig.ProviderNone, config.ResolveProvider(true, false), "never in batch mode or the probe");
            config.ForceSimulated = true;
            Assert.AreEqual(AdConfig.ProviderSimulated, config.ResolveProvider(false, true), "forced on desktop (MUTATION:ADS_FORCE_SIMULATED)");
            Assert.AreEqual(AdConfig.ProviderSimulated, config.ResolveProvider(true, true));
            Assert.AreEqual(AdConfig.ProviderNone, config.ResolveProvider(false, false), "still never in batch mode");
            config.Enabled = false;
            Assert.AreEqual(AdConfig.ProviderNone, config.ResolveProvider(true, true), "the master switch wins");
        }

        [Test]
        public void AdConfig_AutomaticFormat_RewardedOnlyWithTheSimulatedProvider()
        {
            AdConfig config = AdConfig.Defaults();
            Assert.AreEqual(AdFormat.Interstitial, config.AutomaticFormat(true));
            config.Format = AdFormat.Rewarded;
            Assert.AreEqual(AdFormat.Rewarded, config.AutomaticFormat(true));
            Assert.AreEqual(AdFormat.Interstitial, config.AutomaticFormat(false), "a real network never forces a rewarded ad");
        }

        // ----- AdPolicy -----

        private static AdConfig Policy()
        {
            return new AdConfig
            {
                Enabled = true,
                Placement = AdPlacement.Both,
                FirstEligibleLevel = 4,
                EveryNLevelEnds = 2,
                MinSecondsBetweenAds = 100f,
                MinSecondsAfterLaunch = 60f,
                MinSecondsInLevel = 20f,
            };
        }

        private static AdLevelEnd End(int number, bool won = true, float seconds = 40f)
        {
            return new AdLevelEnd { Won = won, LevelId = "level" + number, LevelNumber = number, SecondsInLevel = seconds };
        }

        [Test]
        public void Policy_MasterSwitch_AndNoAds_ComeFirst()
        {
            AdConfig config = Policy();
            var state = new AdPolicyState();
            config.Enabled = false;
            Assert.AreEqual(AdDecision.Disabled, AdPolicy.Decide(config, state, End(9), 1000f, false), "MUTATION:ADS_MASTER_SWITCH");
            config.Enabled = true;
            Assert.AreEqual(AdDecision.NoAdsOwned, AdPolicy.Decide(config, state, End(9), 1000f, true), "MUTATION:ADS_NO_ADS_ENTITLEMENT");
            Assert.AreEqual(0, state.EndsSinceAd, "neither counts the end");
        }

        [Test]
        public void Policy_Placement()
        {
            AdConfig config = Policy();
            config.Placement = AdPlacement.Win;
            Assert.AreEqual(AdDecision.PlacementOff, AdPolicy.Decide(config, new AdPolicyState(), End(9, false), 1000f, false));
            config.Placement = AdPlacement.Fail;
            Assert.AreEqual(AdDecision.PlacementOff, AdPolicy.Decide(config, new AdPolicyState(), End(9, true), 1000f, false));
            Assert.IsTrue(AdPolicy.PlacementAllows(AdPlacement.Both, true));
            Assert.IsTrue(AdPolicy.PlacementAllows(AdPlacement.Both, false));
        }

        [Test]
        public void Policy_NeverOnTheFirstLevels_NorOutsideThePlayOrder()
        {
            AdConfig config = Policy();
            var state = new AdPolicyState();
            for (int n = 1; n < config.FirstEligibleLevel; n++)
            {
                Assert.AreEqual(AdDecision.TooEarlyLevel, AdPolicy.Decide(config, state, End(n), 1000f, false), $"level {n} (MUTATION:ADS_FIRST_LEVEL)");
            }
            Assert.AreEqual(AdDecision.TooEarlyLevel, AdPolicy.Decide(config, state, End(0), 1000f, false), "a level outside the order");
            Assert.AreEqual(0, state.EndsSinceAd, "the first levels never count");
            Assert.AreNotEqual(AdDecision.TooEarlyLevel, AdPolicy.Decide(config, state, End(config.FirstEligibleLevel), 1000f, false));
        }

        [Test]
        public void Policy_LevelLists()
        {
            AdConfig config = Policy();
            config.EveryNLevelEnds = 1;
            config.ExcludedLevels.Add("level8");
            Assert.AreEqual(AdDecision.LevelExcluded, AdPolicy.Decide(config, new AdPolicyState(), End(8), 1000f, false));
            Assert.AreEqual(AdDecision.Show, AdPolicy.Decide(config, new AdPolicyState(), End(9), 1000f, false));
            config.OnlyLevels.Add("level10");
            Assert.AreEqual(AdDecision.LevelExcluded, AdPolicy.Decide(config, new AdPolicyState(), End(9), 1000f, false));
            Assert.AreEqual(AdDecision.Show, AdPolicy.Decide(config, new AdPolicyState(), End(10), 1000f, false));
        }

        [Test]
        public void Policy_QuickEnd_NeverShows_AndIsNotCounted()
        {
            AdConfig config = Policy();
            var state = new AdPolicyState();
            for (int i = 0; i < 5; i++)
            {
                Assert.AreEqual(AdDecision.QuickEnd, AdPolicy.Decide(config, state, End(6, false, 5f), 1000f, false), "MUTATION:ADS_QUICK_END");
            }
            Assert.AreEqual(0, state.EndsSinceAd, "quick retries never add up to an ad");
        }

        [Test]
        public void Policy_LaunchGrace_Cooldown_EveryN()
        {
            AdConfig config = Policy();
            var state = new AdPolicyState { SessionStart = 0f };
            Assert.AreEqual(AdDecision.TooSoonAfterLaunch, AdPolicy.Decide(config, state, End(5), 30f, false));
            Assert.AreEqual(AdDecision.Show, AdPolicy.Decide(config, state, End(5), 70f, false), "the second counted end, after the grace");
            state.RecordShown(70f);
            Assert.AreEqual(0, state.EndsSinceAd);
            Assert.AreEqual(1, state.AdsThisSession);
            Assert.AreEqual(AdDecision.Cooldown, AdPolicy.Decide(config, state, End(6), 120f, false), "MUTATION:ADS_COOLDOWN");
            Assert.AreEqual(AdDecision.Cooldown, AdPolicy.Decide(config, state, End(7), 160f, false));
            Assert.AreEqual(AdDecision.Show, AdPolicy.Decide(config, state, End(8), 171f, false),
                "the ends held by the cooldown counted: the first end after it shows");
            state.RecordShown(171f);
            Assert.AreEqual(AdDecision.NotEveryLevel, AdPolicy.Decide(config, state, End(9), 400f, false), "MUTATION:ADS_EVERY_N");
            Assert.AreEqual(AdDecision.Show, AdPolicy.Decide(config, state, End(10), 410f, false));
        }

        [Test]
        public void Policy_SessionCap()
        {
            AdConfig config = Policy();
            config.EveryNLevelEnds = 1;
            config.MinSecondsBetweenAds = 0f;
            config.MaxAdsPerSession = 2;
            var state = new AdPolicyState();
            for (int i = 0; i < 2; i++)
            {
                Assert.AreEqual(AdDecision.Show, AdPolicy.Decide(config, state, End(5), 100f + i, false));
                state.RecordShown(100f + i);
            }
            Assert.AreEqual(AdDecision.SessionCap, AdPolicy.Decide(config, state, End(5), 500f, false));
        }

        // ----- ADSEVERY: the Simulated provider's "every level end" override -----

        [Test]
        public void AdConfig_Parse_ReadsSimulatedEveryLevelEnd_OffByDefault()
        {
            Assert.IsFalse(AdConfig.Defaults().SimulatedEveryLevelEnd, "the code fallback keeps the frequency rules");
            AdConfig config = AdConfig.Parse("{ \"simulatedEveryLevelEnd\": true }", AdConfig.Defaults(), out string problem);
            Assert.IsNull(problem, problem);
            Assert.IsTrue(config.SimulatedEveryLevelEnd);
            Assert.IsTrue(config.Clone().SimulatedEveryLevelEnd, "kept by a copy");
            Assert.IsTrue(AdConfig.Parse("{ \"simulatedEveryLevelEnd\": \"no\" }", config, out problem).SimulatedEveryLevelEnd,
                "a string keeps the base");
            Assert.IsTrue(config.EveryLevelEnd(true));
            Assert.IsFalse(config.EveryLevelEnd(false), "never with a real provider");
        }

        [Test]
        public void Policy_SimulatedEveryLevelEnd_ShowsAtEveryEnd_FromTheFirstLevel()
        {
            AdConfig config = Policy();
            config.SimulatedEveryLevelEnd = true;
            config.Placement = AdPlacement.Win;
            config.ExcludedLevels.Add("level2");
            config.MaxAdsPerSession = 1;
            AdConfig rules = config.PolicyFor(true);
            var state = new AdPolicyState { SessionStart = 0f };
            float now = 0.5f;
            for (int n = 1; n <= 6; n++)
            {
                foreach (bool won in new[] { true, false })
                {
                    // A 0.5 s level, half a second after the launch and after the previous ad, on a placement "win" config
                    // with level2 excluded and a cap of one ad: the override shows it anyway.
                    Assert.AreEqual(AdDecision.Show, AdPolicy.Decide(rules, state, End(n, won, 0.5f), now, false),
                        $"level {n} {(won ? "win" : "fail")} at {now} s (MUTATION:ADS_SIMULATED_EVERY_END)");
                    state.RecordShown(now);
                    now += 0.5f;
                }
            }
            Assert.AreEqual(12, state.AdsThisSession);
            Assert.AreEqual(AdDecision.NoAdsOwned, AdPolicy.Decide(rules, state, End(3), now, true), "a No ads purchase still wins");
            config.Enabled = false;
            Assert.AreEqual(AdDecision.Disabled, AdPolicy.Decide(config.PolicyFor(true), state, End(3), now, false),
                "the master switch still wins");
        }

        [Test]
        public void Policy_SimulatedEveryLevelEnd_LeavesTheRealRulesAlone()
        {
            AdConfig config = Policy();
            config.SimulatedEveryLevelEnd = true;
            config.ExcludedLevels.Add("level8");
            Assert.AreSame(config, config.PolicyFor(false), "a real provider gets the config untouched");
            Assert.AreEqual(AdDecision.TooEarlyLevel, AdPolicy.Decide(config.PolicyFor(false), new AdPolicyState(), End(1), 1000f, false));
            Assert.AreEqual(AdDecision.QuickEnd, AdPolicy.Decide(config.PolicyFor(false), new AdPolicyState(), End(6, false, 5f), 1000f, false));

            AdConfig copy = config.PolicyFor(true);
            Assert.AreNotSame(config, copy);
            Assert.AreEqual(4, config.FirstEligibleLevel, "the base is never modified");
            Assert.AreEqual(20f, config.MinSecondsInLevel);
            Assert.AreEqual(60f, config.MinSecondsAfterLaunch);
            Assert.AreEqual(100f, config.MinSecondsBetweenAds);
            Assert.AreEqual(2, config.EveryNLevelEnds);
            CollectionAssert.AreEqual(new[] { "level8" }, config.ExcludedLevels, "the base's lists are not cleared");

            config.SimulatedEveryLevelEnd = false;
            Assert.AreSame(config, config.PolicyFor(true), "the Simulated provider without the override keeps the rules");
            Assert.AreEqual(AdDecision.TooEarlyLevel, AdPolicy.Decide(config.PolicyFor(true), new AdPolicyState(), End(1), 1000f, false));
        }

        // ----- ShopConfig -----

        [Test]
        public void ShopConfig_Defaults_HoldNoAds_AndShowOnAndroidOnly()
        {
            ShopConfig config = ShopConfig.Defaults();
            Assert.AreEqual(ShopConfig.ProviderNone, config.Provider, "the code fallback has no store");
            ShopProduct noAds = config.Find("no_ads");
            Assert.IsNotNull(noAds);
            Assert.AreEqual(ProductKind.NonConsumable, noAds.Kind);
            CollectionAssert.Contains(noAds.Grants, Entitlements.NoAds);
            Assert.IsTrue(config.ShowsOn(true, false, false), "Android");
            Assert.IsFalse(config.ShowsOn(false, true, false), "Windows (MUTATION:SHOP_PLATFORM)");
            Assert.IsFalse(config.ShowsOn(true, false, true), "the editor wins over the platform");
            config.ShowOnWindows = true;
            Assert.IsTrue(config.ShowsOn(false, true, false));
            config.Enabled = false;
            Assert.IsFalse(config.ShowsOn(true, false, false), "the master switch");
        }

        [Test]
        public void ShopConfig_Parse_ReplacesTheCatalog_SkippingBadEntries()
        {
            const string json = "{ \"provider\": \"Unity_IAP\", \"showOnWindows\": true, \"products\": ["
                + " { \"id\": \"coins\", \"type\": \"consumable\", \"priceLabel\": \"1 €\", \"grants\": [] },"
                + " { \"id\": \"Bad Id\" }, { \"id\": \"coins\" }, 42, { \"type\": \"consumable\" },"
                + " { \"id\": \"vip\", \"storeId\": \"vip.google\", \"grants\": [\"no_ads\"], \"enabled\": false } ] }";
            ShopConfig config = ShopConfig.Parse(json, out string problem);
            Assert.IsNull(problem, problem);
            Assert.AreEqual(ShopConfig.ProviderUnityIap, config.Provider);
            Assert.IsTrue(config.ShowOnWindows);
            CollectionAssert.AreEqual(new[] { "coins", "vip" }, config.Products.Select(p => p.Id).ToList());
            Assert.IsTrue(config.Find("coins").Consumable);
            Assert.AreEqual("coins", config.Find("coins").StoreId, "the id when no storeId");
            Assert.AreEqual("vip", config.FindByStoreId("vip.google").Id);
            Assert.AreEqual("shop.coins.title", config.Find("coins").TitleKey, "a default key from the id");
            CollectionAssert.AreEqual(new[] { "coins" }, config.EnabledProducts().Select(p => p.Id).ToList());
            Assert.IsNull(config.Find("no_ads"), "the file's catalog replaced the defaults");
        }

        [Test]
        public void ShopConfig_Parse_NeverThrows()
        {
            foreach (string bad in new[] { null, "", "nope", "[]", "{ \"products\": " })
            {
                ShopConfig config = ShopConfig.Parse(bad, out string problem);
                Assert.IsNotNull(config, $"'{bad}'");
                Assert.IsNotNull(problem, $"'{bad}' raised no problem");
                Assert.IsNotNull(config.Find("no_ads"), $"'{bad}' lost the default catalog");
            }
        }

        // ----- SavePurchases -----

        [Test]
        public void Purchases_GrantOnce_CountConsumables_CoveredByABundle()
        {
            ShopConfig catalog = ShopConfig.Defaults();
            var purchases = new SavePurchases();
            Assert.IsFalse(purchases.CoveredBy(catalog.Find("no_ads")));
            Assert.IsTrue(purchases.Grant(catalog.Find("premium_pack")));
            Assert.IsFalse(purchases.Grant(catalog.Find("premium_pack")), "a restore changes nothing (MUTATION:PURCHASE_OWNED_ONCE)");
            Assert.IsTrue(purchases.Owns("premium_pack"));
            Assert.IsTrue(purchases.HasEntitlement(Entitlements.NoAds));
            Assert.IsTrue(purchases.HasEntitlement(Entitlements.AllLevels));
            Assert.IsTrue(purchases.CoveredBy(catalog.Find("no_ads")), "the bundle covers No ads");
            Assert.IsTrue(purchases.CoveredBy(catalog.Find("all_levels")));
            ShopProduct coffee = catalog.Find("tip_coffee");
            Assert.IsFalse(purchases.CoveredBy(coffee), "a consumable is never owned");
            Assert.IsTrue(purchases.Grant(coffee));
            Assert.IsTrue(purchases.Grant(coffee));
            Assert.AreEqual(2, purchases.ConsumedCount("tip_coffee"));
            Assert.IsFalse(purchases.Owns("tip_coffee"));
        }

        [Test]
        public void Purchases_InTheSave_RoundTrip_AndNeverFailALoad()
        {
            var save = new SaveData();
            save.Purchases.Grant(ShopConfig.Defaults().Find("no_ads"));
            save.Purchases.Grant(ShopConfig.Defaults().Find("tip_coffee"));
            SaveData back = SaveData.Parse(save.ToJson(), out string problem);
            Assert.IsNotNull(back, problem);
            Assert.IsTrue(back.Purchases.Owns("no_ads"));
            Assert.IsTrue(back.Purchases.HasEntitlement(Entitlements.NoAds));
            Assert.AreEqual(1, back.Purchases.ConsumedCount("tip_coffee"));

            SaveData old = SaveData.Parse("{ \"version\": 1, \"won\": [\"level1\"] }", out problem);
            Assert.IsNotNull(old, problem);
            Assert.IsNotNull(old.Purchases, "an older save reads as nothing bought");
            Assert.IsFalse(old.Purchases.HasEntitlement(Entitlements.NoAds));

            foreach (string purchases in new[] { "42", "\"x\"", "[]", "{ \"owned\": 3, \"entitlements\": [1, \"no_ads\"], \"consumed\": { \"a\": \"b\", \"c\": -1, \"d\": 2 } }" })
            {
                SaveData data = SaveData.Parse("{ \"version\": 1, \"won\": [\"level1\"], \"purchases\": " + purchases + " }", out problem);
                Assert.IsNotNull(data, $"purchases {purchases} failed the save: {problem}");
                CollectionAssert.AreEqual(new[] { "level1" }, data.Won, "the rest of the save is kept");
            }
            SaveData mixed = SaveData.Parse("{ \"version\": 1, \"purchases\": { \"entitlements\": [1, \"no_ads\"], \"consumed\": { \"a\": \"b\", \"c\": -1, \"d\": 2 } } }", out problem);
            CollectionAssert.AreEqual(new[] { "no_ads" }, mixed.Purchases.Entitlements);
            Assert.AreEqual(new Dictionary<string, int> { { "d", 2 } }, mixed.Purchases.Consumed);
        }

        // ----- Strings and the shipped files -----

        [Test]
        public void Strings_ShopAndAdKeys_HaveBothLanguages_AndNoEmDash()
        {
            var keys = Strings.Keys.Where(k => k.StartsWith("shop.") || k.StartsWith("ads.")).ToList();
            Assert.Greater(keys.Count, 20, "premise: the shop and ad strings");
            foreach (string key in keys)
            {
                string en = Strings.Get(key, Strings.English);
                string fr = Strings.Get(key, Strings.French);
                Assert.IsFalse(string.IsNullOrWhiteSpace(en), key + " has no English");
                Assert.IsFalse(string.IsNullOrWhiteSpace(fr), key + " has no French");
                Assert.IsFalse(en.Contains("\u2014") || fr.Contains("\u2014"), key + " holds an em dash");
            }
            foreach (ShopProduct p in ShopConfig.Defaults().Products)
            {
                CollectionAssert.Contains(Strings.Keys.ToList(), p.TitleKey, p.Id + " title");
                CollectionAssert.Contains(Strings.Keys.ToList(), p.DescriptionKey, p.Id + " description");
            }
        }

        [Test]
        public void ShippedConfigs_Parse_AndTheirKeysExist()
        {
            AdConfig ads = AdConfig.Parse(File.ReadAllText(AdsJson), AdConfig.Defaults(), out string problem);
            Assert.IsNull(problem, AdsJson + ": " + problem);
            Assert.GreaterOrEqual(ads.FirstEligibleLevel, 2, "the shipped config shows no ad on the first level");
            Assert.IsTrue(ads.SimulatedEveryLevelEnd, "ADSEVERY: the shipped simulation shows an ad at every level end");
            Assert.GreaterOrEqual(ads.PolicyFor(false).FirstEligibleLevel, 2, "ADSEVERY: a real provider keeps the first levels ad free");

            ShopConfig shop = ShopConfig.Parse(File.ReadAllText(ShopJson), out problem);
            Assert.IsNull(problem, ShopJson + ": " + problem);
            Assert.IsNotNull(shop.Find("no_ads"), "the shipped catalog sells No ads");
            Assert.IsFalse(shop.ShowOnWindows, "hidden on Windows by default");
            Assert.IsTrue(shop.ShowOnAndroid, "shown on Android by default");
            Assert.LessOrEqual(shop.EnabledProducts().Count, ShopConfig.MaxShownProducts, "the page has no scroll");
            var keys = Strings.Keys.ToList();
            foreach (ShopProduct p in shop.Products)
            {
                CollectionAssert.Contains(keys, p.TitleKey, p.Id + " title key");
                CollectionAssert.Contains(keys, p.DescriptionKey, p.Id + " description key");
                foreach (string grant in p.Grants)
                {
                    Assert.IsTrue(grant == Entitlements.NoAds || grant == Entitlements.AllLevels, $"{p.Id} grants an unknown '{grant}'");
                }
            }
        }
    }
}
