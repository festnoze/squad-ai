# Out of Sight - in-game work needed before a monetized store release

Date: 2026-11-20. Scope: what the game itself must contain to ship free with ads plus a "Remove ads" purchase on
Android and iOS, in France and the rest of the EEA. Store account setup, tax status and marketing are out of scope,
except the few external items the in-game work depends on (section 12).

Assumed model: Unity LevelPlay mediation (Unity Ads + AdMob), one non-consumable purchase, audience declared 13+.
SDK names, quotas and policy details below come from memory and were not rechecked on the date above: confirm each
one against the vendor documentation when the item is implemented.

Priority: **P0** blocks the release (legal or store rejection), **P1** is expected for launch, **P2** can follow.

---

## 1. Consent and privacy (P0)

Nothing in section 2 or 7 may initialize before this flow has resolved.

- [ ] **Consent form at first launch.** Google UMP (an IAB TCF certified CMP) shown before any ad or analytics SDK
      starts. Without a certified CMP, ad networks serve almost nothing in the EEA.
- [ ] **Four outcomes handled**: granted, denied, not required (player outside the EEA), unknown (offline or form
      failed to load). Unknown means no ads this session and a retry at the next launch.
- [ ] **No consent wall.** A player who refuses plays the full game; ads fall back to non-personalized or limited ads.
- [ ] **Consent forwarded** to LevelPlay and to every network adapter before their initialization.
- [ ] **iOS tracking prompt (ATT)** shown after the consent form and only if consent was given, with a usage
      description string in English and French.
- [ ] **Withdrawal as easy as acceptance**: a "Privacy settings" row in the Options panel (`Menu.BuildOptions`) that
      reopens the consent form at any time.
- [ ] **"Privacy policy" row** in Options and in Credits, opening the hosted policy URL in the browser.
- [ ] **Consent state is owned by the CMP SDK.** Do not copy it into `SaveData`; read it from the SDK at each launch.
- [ ] **Startup order written down and tested**: consent form, then ATT (iOS), then ads init, then analytics init,
      then the title screen stays interactive throughout (no blocking spinner if the network is slow).

## 2. Ads (P0 for the model, P1 for the polish)

- [ ] **`IAdService` abstraction.** Interface and pure rules in `OutOfSight.Core`, SDK implementation in Runtime, and
      a no-op implementation for PC, the editor and every test, so the probe tests stay deterministic.
- [ ] **Interstitial placement**: after the win panel, when the player asks for the next level (`GameState.Win` then
      `Menu.OnWinScreen`). Never during a level, never on a fail or a retry (the quick retry is the core loop).
- [ ] **Interstitial pacing rule** as `Tuning` constants, pure and unit tested: none before level 3 is won, at most
      one every 2 wins, and a minimum delay between two ads (for example 120 s).
- [ ] **Rewarded video offer**, always optional and player initiated. Candidates: "skip this level" after N fails,
      or an extra hint. The reward is granted only on the SDK's completion callback, never on open or on close.
- [ ] **Skipped levels tracked apart from won levels** (a `skipped` list), so best times and completion stay honest
      while the next level still unlocks.
- [ ] **Rewarded button state**: hidden or disabled when no ad is loaded; no dead tap, no endless spinner.
- [ ] **Preloading**: the next interstitial and rewarded ad are requested after init and after each display.
- [ ] **Failure path**: no fill, timeout or offline continues the flow at once, with no error shown to the player.
- [ ] **Pause and mute while an ad is on screen**: game time stopped (`GamePause`), audio muted (`AudioMute`), both
      restored on close. Requires the focus-loss pause that IDEAS.md QW1 reports missing (`OnApplicationPause`).
- [ ] **Input guard on return**: the tap that closes the ad must not trigger a game action.
- [ ] **No banner**: it pays little and covers the play area.
- [ ] **Test mode**: development builds use test ad units and registered test devices only. Clicking live ads in
      your own app gets the account suspended.
- [ ] **Ad unit ids per platform** in one config asset, not scattered in code.

## 3. "Remove ads" purchase (P1)

- [ ] **One non-consumable product** (`remove_ads`) through Unity IAP.
- [ ] **Entry points**: a row in Options, and a discreet button on the win panel.
- [ ] **Price read from the store** (localized string from the SDK), never hard-coded in `Strings`.
- [ ] **"Restore purchases" button** in Options. Mandatory on iOS; on Android the entitlement is re-read at launch.
- [ ] **Entitlement source of truth is the store.** A cached `noAds` flag in the save only avoids an ad flash while
      the store answers at startup.
- [ ] **Every purchase state handled**: success, cancelled, failed, pending or deferred (parental approval), already
      owned.
- [ ] **Effect defined**: interstitials removed for good; rewarded offers grant their reward directly, with no video.
- [ ] **A reset of progress never clears the entitlement.**
- [ ] **Confirmation feedback** after a successful purchase or restore.

## 4. Review prompt (P1)

- [ ] **Native review card only**: Google Play In-App Review on Android, the system review request on iOS.
- [ ] **Trigger rule, pure and unit tested**: right after a win, never after a fail, never in the first session,
      never just before or after an ad. Suggested points: level 5 won, then level 12 won, then the last level.
- [ ] **No custom "Do you like the game?" gate** in front of the card and no reward for rating: both stores forbid
      or discourage it.
- [ ] **The API returns no result**: the OS decides whether the card appears (quotas apply), so no logic may depend
      on it having been shown.
- [ ] **At most one request per app version**, tracked in the save.
- [ ] **Permanent "Rate the game" row** in Options or Credits, opening the store page directly.

## 5. Notifications (P2)

A 24 level game has little to announce: local reminders only, no push server.

- [ ] **Local notifications** through the Unity Mobile Notifications package.
- [ ] **Permission asked in context**, never at first launch: a soft in-game question after an early win ("Want a
      reminder to come back?"), then the system prompt (Android 13+ runtime permission, iOS authorization).
- [ ] **Options toggle**, off until the player accepts, switchable at any time (the opt out).
- [ ] **Schedule**: reminders at day 1, 3 and 7 while levels remain unfinished, cancelled and rescheduled at every
      app start, none once every level is won.
- [ ] **Limits**: at most one per day, delivered in the early evening local time, never at night.
- [ ] **Localized text** (English and French) following the game's language option.
- [ ] **Android notification channel and small icon**; a tap opens the game on the level select.
- [ ] **No advertising content** in a notification.

## 6. Sharing and store links (P2)

- [ ] **Share button on the win panel**: native share sheet with the level, the time and the store link.
- [ ] **Store URLs per platform** in one place, used by sharing, "Rate the game" and the end screen.
- [ ] **End screen after the last level**: thanks, "Rate the game", share, and the "Remove ads" offer if not owned.

## 7. Analytics and crash reports (P1)

Needed to measure retention and to know whether marketing works.

- [ ] **One analytics SDK** (Unity Analytics or Firebase), started only after the consent flow.
- [ ] **Opt-out toggle** in Options, or coverage by the consent form's analytics purpose.
- [ ] **Minimal event set**: level start, win (time, difficulty), fail (reason), skip, ad shown, reward granted,
      purchase, review requested, notification opt-in.
- [ ] **No personal data** in event parameters.
- [ ] **Crash reporting** enabled for release builds.

## 8. Save data additions

Same convention as `SaveOptions`: new keys, version stays 1, a missing key means the default.

- [ ] `noAds` (bool, cache of the entitlement).
- [ ] `skipped` (list of level ids).
- [ ] `review` (last app version a review was requested for).
- [ ] `notifications` (bool, the Options toggle).
- [ ] `analyticsOptOut` (bool), if the toggle exists.
- [ ] Ad pacing counters (wins since the last interstitial); the last ad time can stay in memory.
- [ ] `SaveData.Parse` stays defensive: a malformed new field falls back to its default and never fails the load.

## 9. Menus and strings

- [ ] **Options panel**: Privacy settings, Privacy policy, Remove ads, Restore purchases, Notifications, Rate the
      game. Check that the panel still fits a phone screen and stays reachable by gamepad and keyboard.
- [ ] **Win panel**: rewarded and share buttons, without pushing "Next level" out of thumb reach.
- [ ] **Every new string in `Strings`** in English and French.
- [ ] **The consent form and the ATT prompt follow the device language**, not the game's language option: accept it
      or document it.
- [ ] **Credits and `docs/LICENSES.md`** updated with the added SDKs.

## 10. Platform configuration (P0)

- [ ] **Android manifest**: internet, advertising id and notification permissions; AdMob app id.
- [ ] **iOS Info.plist**: tracking usage description, SKAdNetwork ids of every network, AdMob app id.
- [ ] **iOS privacy manifest** covering the game and each SDK.
- [ ] **Store declarations match the code**: Google Play Data safety form and App Store privacy labels list exactly
      what the SDKs collect.
- [ ] **Stripping check in a built player**: ads, purchase and consent verified on a real device, not only in the
      editor (IL2CPP stripping can remove SDK code silently).

## 11. Tests

- [ ] **Pure rules in Core with EditMode tests and mutation markers**: interstitial pacing, review trigger,
      notification schedule, entitlement effect on ads.
- [ ] **Fake `IAdService`** for PlayMode probes: ad shown, ad failed, reward granted, reward abandoned.
- [ ] **Save round trip** for every new key, including an old save without them.
- [ ] **Device checklist per release**: first launch inside the EEA, consent refused, offline launch, purchase,
      restore on a fresh install, interruption by a phone call during an ad.

## 12. External items the game depends on

- [ ] Hosted privacy policy page (its URL is used in section 1 and by both stores).
- [ ] `app-ads.txt` on the developer website (ad revenue drops without it).
- [ ] Ad unit ids, the `remove_ads` product and the store page URLs created in the consoles.

---

## Suggested order

1. Sections 1 and 10, with the `IAdService` no-op (the game ships unchanged, the consent flow is proven).
2. Section 2 interstitial, then rewarded.
3. Sections 3 and 4.
4. Sections 7, 6 and 5.
