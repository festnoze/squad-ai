# ADSSHOP progress (end-of-level video ads on Android, and the Shop page)

Study and network choice (French): docs/next/ADS_STUDY.md. Recommended: AppLovin MAX as the mediation layer (plan B:
AdMob mediation). No SDK or package was added to Packages/manifest.json; both real adapters compile only behind a
scripting define symbol, so the project builds as before without them.

## Design
- **Provider-agnostic layers.** Ads: `IAdProvider` + `AdProviderRegistry` + `AdService` (static) + `AdDirector` (the
  end-of-level hook). Shop: `IStoreProvider` + `StoreProviderRegistry` + `StoreService` (static) + `ShopPage` (UI).
  Built-in providers: `none` and `simulated` for both. Real adapters: `applovin_max` (ads, `OOS_ADS_APPLOVIN_MAX`) and
  `unity_iap` (store, `OOS_IAP_UNITY`). An adapter registers itself by name from a `[RuntimeInitializeOnLoadMethod]`;
  the config's `provider` picks it. A name with no registered adapter falls back to `none` with a warning.
- **Pure rules in Core** (EditMode testable): `AdConfig` (parse, clamp, provider resolution), `AdPolicy` (frequency),
  `ShopConfig` (catalog), `SavePurchases` (owned products, entitlements, consumable counts).
- **Config in Resources** (`Resources.Load<TextAsset>`, synchronous on Android, unlike StreamingAssets here):
  `Assets/Resources/Config/ads.json` and `shop.json`, each over code defaults that show no ad and open no store when the
  file is missing or broken. Remote config hook: `AdService.ApplyRemoteConfig(json)` overlays any subset of ads.json keys.
- **End-of-level flow, gameplay untouched.** `AdDirector` (child "Ads" of Main) only listens to
  `GameState.StateChanged`. On a win (not the last level's end screen) or a fail it asks `AdPolicy`; on Show it waits
  `showDelaySeconds` with the panel up and shows the ad only if the player is still on that panel (a Retry, Next level
  or menu cancels it). During the ad: `GameState.Paused` is true (no rule runs, no gameplay press is read) and
  `AudioListener.volume` is 0 (the music ignores the listener pause); both are restored after (paused only under an
  open menu, the options' volume).
- **Platforms.** Ads: Android only. Windows and the editor resolve to `none` unless `forceSimulated` is true. Batch mode
  (the test suites), `--probe` and `--look` never show ads and never show the shop.
- **Rewarded.** Networks require rewarded ads to be opt-in, so a real provider always shows the automatic placement as an
  interstitial; `format: rewarded` only changes the Simulated ad. `AdService.aShowRewardedAd(placement)` is ready for a
  future opt-in button (allowed even with No ads owned).
- **Shop.** A Shop button at the top right of the title page (a column button, so the five-button column and its metrics
  stay as they were), only where `StoreService.ShopVisible`: Android yes, Windows and the editor no, by default. It joins
  the title's up/down cycle above Play (and Right from any column button). The page follows the Options and Credits
  style: one row per product (name and line from Strings, store price or the catalog's priceLabel, "Owned" once
  bought), Restore purchases, Ad privacy choices (only when the ad network offers a consent form: MAX for GDPR users,
  always with Simulated), Back, and a status line. Escape / gamepad B / Android back close it.
- **Purchases in the save.** `SaveData.purchases = { owned: [...], entitlements: [...], consumed: {...} }` (version stays
  1; a missing or malformed object reads as nothing bought, never failing the load). Entitlements are stored, not
  derived, so a product later disabled keeps what it granted. `no_ads` stops the automatic ads; `all_levels` makes
  `SaveStore.IsUnlocked` true for every level. A delivered purchase is saved before the store transaction is confirmed.
- **Catalog shipped**: `no_ads` (2,99 €), `premium_pack` (no ads + all levels, 3,99 €), `all_levels` (1,99 €),
  `tip_coffee` (consumable tip, 0,99 €). Prices are fallbacks: the store's localized price wins.

## Config reference
ads.json (every key optional; code defaults in `Core/Monetization/AdConfig.cs`):

| Key | Shipped | Meaning |
|---|---|---|
| enabled | true | Master switch: false never shows an ad. |
| provider | "simulated" | none / simulated / applovin_max (Android only). |
| forceSimulated | false | Testing: the Simulated ad on every platform, editor and Windows included. |
| format | "interstitial" | interstitial / rewarded (rewarded only with Simulated, see above). |
| placement | "both" | win / fail / both. |
| firstEligibleLevel | 4 | First level (1-based, play order) whose end may show an ad. |
| everyNLevelEnds | 2 | At most one ad every N eligible level ends. |
| minSecondsBetweenAds | 120 | Cooldown. |
| minSecondsAfterLaunch | 90 | No ad this early in a session. |
| minSecondsInLevel | 20 | A shorter level (quick fail or retry) shows nothing and is not counted. |
| maxAdsPerSession | 0 | 0 is unlimited. |
| showDelaySeconds | 1.2 | Panel time before the ad. |
| onlyLevels / excludedLevels | [] | Level id lists. |
| preferredMaxDurationSeconds / skippableAfterSeconds | 15 / 5 | Simulated ad only (real networks decide server-side). |
| simulatedVideo | "Ads/out_of_sight_ad" | Simulated ad only: a VideoClip under Resources. No clip ships since 2026-11-25, so the text card shows. |
| simulatedEveryLevelEnd | true | Simulated provider only: an ad at every level end (see the 2026-11-25 section). Code default false. |
| showMediationDebugger | false | Opens MAX's Mediation Debugger after init (development). |
| providers.applovin_max | placeholders | interstitialAdUnitId, rewardedAdUnitId (SDK key: Integration Manager). |
| providers.admob | Google TEST ids | Plan B, no adapter yet. |

shop.json: `enabled`, `provider` (none / simulated / unity_iap), `showOnAndroid` (true), `showOnWindows` (false),
`showInEditor` (false), `products[]` with `id`, `storeId` (Google Play product id, defaults to id), `type`
(nonconsumable / consumable), `priceLabel`, `titleKey`, `descriptionKey` (Strings keys), `grants` (no_ads, all_levels),
`enabled`. The page shows the first 5 enabled products. A products list in the file replaces the default catalog.

## How to
- **Disable ads**: ads.json `"enabled": false` (or `"provider": "none"`). Per level: `excludedLevels` / `onlyLevels`.
- **Switch ad network**: install its SDK, add its define symbol, set `"provider"` to its name and fill
  `providers.<name>`. A new network = one class implementing `IAdProvider` in `Assets/Scripts/Adapters/`, wrapped in
  `#if OOS_ADS_<NAME>`, registering itself with `AdProviderRegistry.Register("<name>", ...)`. Same for a store with
  `IStoreProvider` / `StoreProviderRegistry`.
- **Try the ads in the editor or on Windows**: ads.json `"forceSimulated": true`. With `simulatedEveryLevelEnd` (shipped
  true) every level end shows one; with it false, play past level 3 (or lower `firstEligibleLevel`,
  `minSecondsAfterLaunch`, `minSecondsBetweenAds` for a quick check). Logs: `[Ads] ...`.
- **Try the shop in the editor**: shop.json `"showInEditor": true` (provider simulated). Logs: `[Shop] ...`. The editor
  save is a temporary file wiped at every boot, so purchases do not persist there.
- **Remote config**: call `AdService.ApplyRemoteConfig(json)` once the values arrive (any subset of ads.json keys).

## Go live (details and order: docs/next/ADS_STUDY.md sections 7 and 8)
1. Ads: AppLovin + AdMob accounts, GDPR message published in AdMob, MAX ad units (interstitial, rewarded), MAX Unity
   plugin + Integration Manager (SDK key, network adapters, Terms and Privacy Policy flow with a privacy policy URL),
   define `OOS_ADS_APPLOVIN_MAX`, ads.json `"provider": "applovin_max"` with the real ad unit ids, app-ads.txt, Play
   Console "Contains ads" and Data safety.
2. Shop: Play Console merchant profile, a signed release AAB in internal testing, the four in-app products, Unity IAP 5
   package, define `OOS_IAP_UNITY` (and optionally `OOS_IAP_RECEIPT_VALIDATION` with the generated GooglePlayTangle),
   shop.json `"provider": "unity_iap"`, license testers.
3. The shipped JSONs use the Simulated providers (development): switch both before release (a player build logs a
   warning while a Simulated provider runs).
4. First build with each define symbol: fix any API drift in the two adapters (written from the docs, never compiled
   here since neither SDK is installed).

## Files
- New, Core: `Assets/Scripts/Core/Monetization/AdConfig.cs`, `AdPolicy.cs`, `ShopConfig.cs`, `SavePurchases.cs`.
- New, Runtime: `Assets/Scripts/Runtime/Monetization/IAdProvider.cs` (interface, registry, NoAdProvider),
  `SimulatedAdProvider.cs` (provider and its overlay), `AdService.cs`, `AdDirector.cs`, `IStoreProvider.cs` (interface,
  registry, NoStoreProvider, SimulatedStoreProvider), `StoreService.cs`, `ShopPage.cs`.
- New, adapters (Assembly-CSharp, empty without their symbol): `Assets/Scripts/Adapters/ApplovinMaxAdProvider.cs`,
  `UnityIapStoreProvider.cs`.
- New, config: `Assets/Resources/Config/ads.json`, `shop.json`.
- Changed: `Core/SaveData.cs` (purchases field and lenient parse), `Core/Strings.cs` (shop.* and ads.* keys, a few
  members), `Runtime/SaveStore.cs` (HasEntitlement, IsCovered, RecordPurchase, PurchasesChanged, all_levels in
  IsUnlocked), `Runtime/Menu.cs` (ShopOpen, OpenShop, CloseShop, BuildShop, guards, Back, Apply, DefaultButton,
  relocalize), `Runtime/Main.cs` (boot steps "store", "ads", "ad director").
- Tests (new, not run): `Assets/Tests/EditMode/MonetizationTests.cs`. Filter: `MonetizationTests`, e.g.
  `pwsh -NoProfile -File tools/unity.ps1 -Agent <name> -UnityArgs "test . --mode EditMode --filter MonetizationTests --report-format junit --output TestResults/adsshop.xml --timeout 1800"`.

## Notes and limits
- The save is a local file: a player who edits it can grant themselves No ads. Acceptable for a single-player game.
- A consumable delivered twice (a crash between the grant and the store confirmation) is counted twice: harmless.
- With the shop hidden on Android, no store connects, so pending purchases and the privacy choices button are
  unavailable: move the privacy button elsewhere (GDPR) if the shop is ever hidden there.
- Compile check (tools/unity.ps1 SetupAndCompile, Build/ADSSHOP.log): see the final report.

## 2026-11-25: ADSEVERY (an ad at every level end in simulation, no ad video in the build)

### An ad at every level end with the Simulated provider
- **Config, not weaker rules.** New ads.json key `"simulatedEveryLevelEnd": true` (code default false), parsed in
  `AdConfig`. `AdConfig.EveryLevelEnd(simulated)` is true only when the active provider is the Simulated one AND the key
  is on. `AdConfig.PolicyFor(simulated)` returns the config untouched for a real provider (or without the key), and for
  the Simulated provider a copy with every frequency rule off: placement both, first level 1, no level lists, no
  quick-end, launch, cooldown or every-N gate, no session cap. `AdPolicy` itself is unchanged; `AdService.EvaluateLevelEnd`
  passes it `Config.PolicyFor(Simulated)`. The real-provider path (`applovin_max`) keeps all the rules of the table above.
- **Still apply in simulation:** `enabled` (master switch), the No ads entitlement (checked by the policy before any
  rule, so `no_ads` and `premium_pack`, simulated purchases included, still stop every automatic ad), batch mode / the
  probe / the look agent (no provider), spectator runs (never end).
- **The finale too.** `AdDirector` skipped the last level's end screen; with `AdService.EveryLevelEnd` it shows an ad there
  too (a real provider still skips it). After the ad, Menu.Update reselects the end screen's button.
- **Level-end UI flow (checked in code, unchanged):** the panel shows first (GameState.Win/Lose call Hud.ShowWin/ShowFail
  before StateChanged); the director waits `showDelaySeconds` (1.2) and shows the ad only if the same panel is still up,
  so a Retry, Next level or menu during the delay cancels it. Only one overlay at a time: the director stops a pending
  coroutine before starting another, `AdService.aShowAd` refuses while `Showing`, and the Simulated provider is not ready
  while an overlay exists. The overlay (sorting order 200) swallows every pointer and keeps the UI selection on its Skip
  button, and GameState.Update reads no R or Enter while paused. When it closes, `EndAdPause` restores the pause (only
  under an open menu) and the options' volume; on the fail panel Menu.Update reselects Retry the next frame, on the win
  panel Enter and gamepad A load the next level as before (no button is selected there by design).
- **Pause guard (new).** Escape, gamepad Start or the Android back key still toggle the pause menu behind the overlay;
  closing that menu set `Game.Paused` false under the ad (R could restart the level under it). `AdService.KeepAdPause()`,
  called from `AdDirector.LateUpdate`, puts the pause and the 0 listener volume back while an ad shows.
- **Platforms (unchanged).** Ads resolve to a provider on Android only. On Windows (player) and in the editor the
  provider is `none` unless `"forceSimulated": true`, so the shipped config shows NO ad on PC; with `forceSimulated` the
  Simulated provider runs there and `simulatedEveryLevelEnd` applies as on Android.

### Simulated purchases: where they live and how to reset them
- They are in the save, `SaveData.purchases` (`owned`, `entitlements`, `consumed`), file `outofsight_save.json` in
  `Application.persistentDataPath`. Nothing in the game resets them.
- **Android:** usually `/storage/emulated/0/Android/data/com.outofsight.game/files/outofsight_save.json`. Reset:
  Settings > Apps > Out of Sight > Storage > Clear storage, or `adb shell pm clear com.outofsight.game` (both also wipe the
  level progress and the options), or `adb pull` the file, delete its `"purchases"` object, `adb push` it back.
- **Windows player:** `%USERPROFILE%\AppData\LocalLow\OutOfSight\Out of Sight\outofsight_save.json`: delete the
  `"purchases"` object (keep the JSON valid). Deleting the file alone is not enough: a missing save is restored from its
  `.tmp` or `.bak`, which hold the purchases too, so delete those as well.
- **Editor:** the save is a temporary file wiped at every boot: purchases never persist.

### No ad video in the build (Resources/Ads emptied and removed)
- Everything under a Resources folder ships in the APK (about 150 MB of clips here). The user wants no ad video in the
  APK (a streamed online source will be chosen later), so EVERY file of `Assets/Resources/Ads` moved to `ArtHandoff/Ads/`
  (outside Assets, 157 MB): `Out of Sight 2026-11-25 11-17-29.mp4`, `out_of_sight_ad_15s-wan_30.mp4`,
  `out_of_sight_ad_gemini-omni-1.2-flash-15s-horizontal.mp4`, `out_of_sight_ad_gemini-omni-1.2-flash-15s-vertical.mp4`,
  `out_of_sight_ad_google_omni.mp4`, `out_of_sight_ad_seedance_25.mp4`, `out_of_sight_ad_seedance_25_flash_30s.mp4`,
  `out-of-sight-affiche-fr.png`. The 8 `.meta` files Unity had created were deleted (the orphan
  `out_of_sight_ad.mp4.meta` was already gone), then the empty folder and `Assets/Resources/Ads.meta` (none of it was
  tracked by git, nothing referenced those GUIDs).
- `simulatedVideo` stays "Ads/out_of_sight_ad": `Resources.Load<VideoClip>` returns null and the Simulated ad shows its
  text card (15 s, skippable after 5 s); it now logs that once per session. A future streamed source can replace it.
- Best candidate to host later: `out_of_sight_ad_gemini-omni-1.2-flash-15s-horizontal.mp4` (15 s, 640x360, 3.2 MB,
  landscape like the game: defaultScreenOrientation 4 = auto rotation, landscape left/right only), not re-encoded here.
- `ArtHandoff/Ads/` holds a 93 MB capture: use Git LFS (or keep it out of git) before committing it.

### Files
- Changed: `Assets/Scripts/Core/Monetization/AdConfig.cs` (SimulatedEveryLevelEnd, EveryLevelEnd, PolicyFor, parse),
  `AdPolicy.cs` (doc only), `Assets/Scripts/Runtime/Monetization/AdService.cs` (EveryLevelEnd, PolicyFor in
  EvaluateLevelEnd, KeepAdPause, boot log), `AdDirector.cs` (finale in simulation, LateUpdate guard, log),
  `SimulatedAdProvider.cs` (one log when the clip is missing), `Assets/Resources/Config/ads.json` (the key and its
  comment), `Assets/Tests/EditMode/MonetizationTests.cs` (3 new tests, 2 assertions in ShippedConfigs).
- Tests (not run): filter `MonetizationTests`, or the new ones alone
  `AdConfig_Parse_ReadsSimulatedEveryLevelEnd_OffByDefault`, `Policy_SimulatedEveryLevelEnd_ShowsAtEveryEnd_FromTheFirstLevel`,
  `Policy_SimulatedEveryLevelEnd_LeavesTheRealRulesAlone`, plus `ShippedConfigs_Parse_AndTheirKeysExist`.
- Check by hand (Android, after an APK rebuild): fail level 1 at once and wait: the fail panel, then after 1.2 s the
  Simulated ad (text card, Skip after 5 s); skip it: Retry is selected and works. Win a level: the win panel, the ad, then
  Next level works. Retry within 1.2 s of a fail: no ad. Press back during the ad: the pause menu opens behind it, the game
  stays paused and silent. Buy No ads in the Shop: no more ads. Logcat: `adb logcat -s Unity | findstr "[Ads]"`.
- Compile check (tools/unity.ps1 SetupAndCompile, Build/adsevery.log): OK, "[Builder] Scripts compiled and project set
  up.", no `error CS`, no new warning, no import error (no video left to import). Unity warned that the drive has less
  than 1 GB free.
