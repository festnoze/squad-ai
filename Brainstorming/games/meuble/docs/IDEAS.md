# Out of Sight: Don't Get Caught Moving - improvement ideas

Date: 2026-11-19. Scope: every area of the game, from the core rules to the store page. Unity was not run for this
review: it rests on the PRD (v1.10), the M2 to M7 contracts, docs/m7/design.md, docs/m8/ROOMS_PLAN.md,
docs/m9/FLOORS_WALLS.md, docs/audio/AUDIO_REPORT.md, a read of the runtime code (Assets/Scripts/Core and Runtime,
Assets/Editor/Builder.cs, ProjectSettings) and about twenty screenshots (docs/m7, docs/m8/levels, docs/m9/floors,
docs/m9/handles, TestResults/shots).

How to read an entry: **ID - title** [Impact, Effort], then why and what. Impact is High, Medium or Low. Effort is
S (a day or less of agent work, a few files), M (a few days, several systems, new tests or audit runs) or L (a
milestone of its own). Quick wins (High impact, S effort) are gathered first. Every other idea sits in its area. The
bugs and inconsistencies found while reading are listed at the end, with file and line.

---

## 1. Quick wins (High impact, S effort)

- **QW1 - Pause when the game loses focus** [High, S] (UI/UX, mobile). No `OnApplicationFocus` or
  `OnApplicationPause` exists in Assets/Scripts, and `runInBackground: 1` (ProjectSettings.asset:89): an alt-tab on PC
  keeps routines walking and the creak gauge filling, and a phone call on Android drops the player back mid-stealth.
  Open the pause menu on focus loss and on app pause.
- **QW2 - Prompts that match the device in use** [High, S] (controls). The fail and win lines have keyboard and touch
  variants but no gamepad one ("Press R" to a pad player, Hud.cs:1220, 1247, 1251); the careful, lamp and door hints are
  keyboard only (Hud.cs:511-520); six level hints hard-code Shift or E. Resolve `{action}` and `{careful}` tokens from
  `InputReader.LastInputWasGamepad` and `TouchUIActive`, as the wardrobe prompt already does for the pad.
- **QW3 - First language from the system** [High, S] (localization). `Strings.Language` starts in English and a save
  without a language stays English (Strings.cs:19, 25), so a French phone, the first audience, opens in English. Use
  `Application.systemLanguage` when the save has no language yet.
- **QW4 - Start the level on the first input** [High, S] (UI/UX). The clock and every routine run from the build
  (GameState.cs:1733) while the intro card covers the screen centre for 5 s (Hud.cs:1365): records include reading
  time and the house is already moving before the player looks. Hold the rules until the first move or key, then
  start the clock and the creak start delay.
- **QW5 - Game speed assist (90, 80, 70 %)** [High, S] (accessibility). The catch grace is 0.2 s and the README's bot
  with a human reaction time was seen moving for 0.18 s of it. Scaling `Time.timeScale` keeps every rule identical in
  game time (they all run in fixed steps). File these records apart, as the difficulty already does.
- **QW6 - Let a stuck player move on** [High, S] (progression). 24 levels unlock strictly in order
  (`SaveStore.IsUnlocked`). Offer "skip this level" after 5 failures, or an "unlock every level" option; a skipped
  level stays unwon on its card.
- **QW7 - A rug without red or coral** [High, S] (art). `rug_modern_inset_border.png` carries two large coral discs,
  and level 9 starts the red chair right on one (docs/m8/levels/level9.png), against PRD 7.2 and ROOMS_PLAN 4 ("no red
  or orange"). Recolour it to blue, green and ochre; later add two more designs, since every rug of the game is this one.
- **QW8 - Zoom on gamepad and touch** [High, S] (controls, camera). `ZoomNotches` reads the mouse wheel only
  (InputReader.cs:126-136, OrbitCamera.cs:159), so pad and phone players cannot pull back in the 6 to 8 room houses.
  Bind the bumpers (or right stick click plus stick) and a two finger pinch.
- **QW9 - An exit marker that shows through walls** [High, S] (UI/UX). The exit is a green doormat, invisible in the
  start views of the large houses (docs/m9/floors/level19_start.jpg, level24_start.jpg). Draw a door icon over
  everything at the exit, like the gaze arrowheads, fading near it.
- **QW10 - Near-miss feedback** [High, S] (feedback). When `seenMoving` rose above zero and fell back without a catch,
  play a short relief beat (a 0.2 s slow-down, a sigh, "Ouf !"). It turns the grace into a felt reward and teaches it
  without a tutorial line.
- **QW11 - Measure on a real Android phone now** [High, S] (performance). The M7 gate (30 fps on a mid range phone) is
  still "pending, product owner" (docs/m7/android.json); the 24 levels, up to 156 draw calls, were never run on a
  device. One evening with adb and the probe answers it before any more mobile work.
- **QW12 - Put the effect WAVs under version control** [High, S] (tech debt). `*.wav` is ignored at the repository
  root: 0 of the 33 WAVs in Assets/ThirdParty/Audio are tracked (AUDIO_REPORT 8), so a clean clone ships fallbacks or
  silence. Add a gitignore exception or Git LFS for that folder.
- **QW13 - A store-ready Android build** [High, S] (build). `Builder.BuildAndroid` forces an APK
  (Builder.cs:63) with debug signing, and the versions are fixed at 0.1.0 and versionCode 1 (ProjectSettings.asset:150,
  182). Google Play needs an AAB, an upload key and a rising versionCode; pin the target API as well.
- **QW14 - Check the name before the store page** [High, S] (marketing). To my knowledge a 2025 commercial game is
  already called "Out of Sight" (to be checked on Steam and the stores). Keep "Don't Get Caught Moving" as the unique
  handle, or pick a distinctive title before buying any capsule art or trailer work.
- **QW15 - Decide the business model early** [High, S] (monetization). Premium on PC (Steam and itch, 5 to 8 EUR) with a
  free demo of levels 1 to 7 fits a short, polished, ad-free stealth comedy; deciding now shapes the demo cut, the
  store page and the Android plan (MO1).

## 2. Bigger bets (the five with the most leverage)

1. **PR1 - Three stars per level, par from the audit**: replay value from data the pipeline already computes.
2. **LD1 + LD2 - Retune the curve and measure human feasibility**: the product owner's "everything is easy" is still
   unanswered.
3. **NA1 - Speech bubbles and personality reactions**: the comedy pillar is mostly silent today.
4. **UX4 + FX2 - The catch as a comic, readable moment**: a double take, then a short replay from the watcher's cone.
5. **GP4 - Hop into a decoy**: a signature twist that fits the existing decoy and memory rules.

---

## 3. Core gameplay and mechanics

- **GP1 - A deliberate knock (voluntary creak)** [High, M]. PRD open question 6 was never decided, and pillar 3 ("the
  player can always create their own window") rests on a passive gauge. The action key with nothing in reach knocks:
  an early creak at the furniture that resets the gauge, with a cooldown. It only helps, so every audited schedule
  stays valid.
- **GP2 - A lure at a distance** [High, M]. Let the furniture bump a light prop (vase, books) off a table: a crash where it
  lands, and an inhabitant walks there to put it away. It reuses the fallen-load clue (GameState StepClue and
  StepPutAway, GameState.cs:1519, 1561) and gives a lure that is not at the player's own spot.
- **GP3 - Household appliances as cover noise** [High, M]. A TV, a washing machine, a kettle switched on by routines
  that mask hops like the robot does (`HumMasks`, GameState.cs:1322). Timed windows that come from the household's
  life rather than from glances.
- **GP4 - Hop into a decoy** [High, L]. Unseen and touching a decoy of its own kind, the player swaps bodies; the old
  body stays where it stands as a decoy. It fits the decoy rule ("une chaise parmi d'autres") and the memory rule, and
  makes a strong mid-game twist; the audit must model the swap.
- **GP5 - Two new bodies with one rule each** [Medium, M]. A pouf (silent on every floor, too low to see over
  anything, cannot open doors) and a bar cart (rolls like the office chair, its bottles rattle as noise). Fresh
  combinations for houses after level 18 without new systems.

## 4. Level design and difficulty curve

- **LD1 - Apply the retune plan** [High, M]. The product owner finished 18 levels in 8 to 34 s; docs/m7/design.md
  section 3 lists a lever per level (margins 15 down to 4 to 6, exits 10 s up to 45 to 60 s) but no level file was
  changed. Include level 10, whose rock lesson is only advisory (CONTRACT_M6 5), and check 19 to 24 against the same
  curve.
- **LD2 - A human-feasibility score per level** [High, M]. The audit proves a schedule exists, not that a human can
  play it. Generalize the README's step 11 bot (0.24 s reaction, reads only the telegraph and the cone) to all 24
  levels at both difficulties and report a win rate and the closest call.
- **LD3 - Acts with breathers** [Medium, S]. Present the 24 levels as three acts (learn 1 to 7, combine 8 to 18, houses
  19 to 24) in the level select, and check that 19 to 24, appended after the M7 curve, respect "never easier than two
  levels before".
- **LD4 - Remix levels** [High, M]. Data-only variants of the early houses with new routines tuned for Difficile, run
  through the existing audit and route writer. The cheapest way to double the content.
- **LD5 - Fill the bare houses** [Medium, M]. Level 21 (the office) and others show wide empty floors with little cover
  (docs/m8/levels/level21.png). More mid-height cover and decoys create real route choices in the big houses.

## 5. AI and inhabitants

- **AI1 - React to a chair in the way** [Medium, M]. The Player and Inhabitant layers ignore each other (Main.cs:69),
  so people walk straight through the furniture. Let them bump, frown and step around it; a bump on a chair out of
  place can count as a discovery, which is also funny.
- **AI2 - Walk to an unexplained noise, then stay alert** [Medium, M]. An Alerted watcher only looks for 2 s. Walking
  to the source when nothing is seen, then a short phase of extra glances, gives lures and mistakes a real cost and
  a real use.
- **AI3 - Personality readable at a glance** [High, M]. Personalities appear only on the intro card. Give each a prop
  and an idle: the teen's phone glow on his face, granny's knitting or cane, the neat freak's feather duster, the
  rusher on a call. The player then reads range and habits from the model.
- **AI4 - Routine preview assist** [Medium, M]. An optional faint path to the next station and a countdown ring before
  the next glance (on by default in Facile), for players who struggle to read the 0.6 s telegraph.
- **AI5 - New watchers: the child and the cat** [Medium, M]. A child who picks up furniture and moves it for fun
  (chaos and comedy, a new kind of setback), and a cat that naps on the player (a pin like a sitter) and sees high
  where the dog sees low.

## 6. Controls (PC, gamepad, touch)

QW2 (device-aware prompts) and QW8 (zoom on gamepad and touch) belong here.

- **CT1 - Key rebinding** [Medium, M]. Keys are hard-coded by physical position (InputReader.cs:33-36, Shift in
  `CarefulHeld`). An Input System rebinding page saved with the options also helps one-handed players.
- **CT2 - Careful mode as hold or toggle** [Medium, S]. Keyboard and pad players must hold Shift or LT through whole
  levels such as 11 and 13; touch already toggles it. Make it an option for every device.
- **CT3 - Touch layout pass** [Medium, S]. Buttons use fixed offsets (TouchControls.cs:243-250) and no
  `Screen.safeArea`, so notches and punch holes can cover them; the action button always says "Action". Respect the
  safe area, show the context icon (door, lamp, wardrobe) and dim the button when nothing is in reach.
- **CT4 - Controller glyphs and a Steam Deck pass** [Medium, M]. Prompts name letters (X, Y, Start); show Xbox or
  PlayStation glyphs by device and check the layout at 1280 x 800.

## 7. Camera

- **CA1 - Plan view** [High, M]. Hold Tab (or a pad and touch button) for a top-down view of the whole house with
  watchers and cones. `LevelMiniature` already draws each level from above for the level select.
- **CA2 - Level opening glide** [High, M]. A 2 s skippable camera move from the exit to the player at the start (with
  QW4 holding the rules meanwhile), so the goal is known before the first step.
- **CA3 - Off-screen watcher indicators** [High, M]. M3.1 dropped the marker clamp. A watcher out of frame whose cone
  covers the furniture, or who is about to turn toward it, should show an arrow at the screen edge with its eye state.
- **CA4 - 90 degree snap rotation** [Medium, S]. Bumpers or Q/E rotate the dollhouse by 90 degrees: easier than free
  orbit on pad and touch, and it keeps walls aligned with the screen.

## 8. UI, UX and onboarding

QW1 (pause on focus loss), QW4 (start on the first input) and QW9 (exit marker) belong here.

- **UX1 - Hint and people in the pause menu** [Medium, S]. The hint shows for 5 s (Hud.cs:1365) and carries the key
  instructions (level 22: the wardrobe and the doors). Repeat it in the pause menu with the people list.
- **UX2 - Contextual first-time tips** [High, M]. Level 1 already shows the Creak and Suspicion gauges with no word
  about them (TestResults/shots/02_caught.png). Explain each gauge, the eye, the memory ghost and the action key the
  first time each one matters, with a short pause.
- **UX3 - Move the intro card off the furniture** [Medium, S]. Title and hint sit at the screen centre, over the player
  (docs/m7/after_level16.png, after_level17.png). Put them in a top band and wrap long hints: level 22's runs from edge
  to edge at 1280 x 720 (TestResults/shots/24_level22.png).
- **UX4 - "Who saw you" replay** [High, M]. On a catch, replay the last 3 s from the watcher's side with its cone; the
  poses are already published every fixed step (`GameState.FixedStepped`). Each catch becomes a lesson (pillar 2).
- **UX5 - End-of-level summary** [Medium, M]. Time, best, discoveries, creaks, restarts and star objectives on the win
  panel, instead of the time alone.

## 9. Feedback and juice

QW10 (near-miss feedback) belongs here.

- **FX1 - Hop dust and squash** [Medium, S]. Dust puffs on hard floors and none on rugs (the silent zone becomes
  visible), a small squash on each landing, skid marks after an office chair glide.
- **FX2 - A comic double take on a catch** [High, M]. Freeze 0.3 s, cut to the watcher's startled face, a record
  scratch, then the panel (UX4 can follow). Today the panel covers the scene at once.
- **FX3 - A win moment** [Medium, M]. The furniture hops out into the garden and the door closes behind it before the
  panel; a short beat that rewards the escape the title promises.
- **FX4 - Haptics** [Medium, S]. Pad rumble and phone vibration on seen-moving, the creak warning and the catch;
  nothing vibrates today.

## 10. Art direction and readability

QW7 (the rug) belongs here.

- **ART1 - Night levels that look like night** [High, M]. Level 16 "La nuit" averages a luminance of 0.446 in its start
  view, the same as the day levels (docs/m7/player_final.txt), with sunlight through the windows; level 20 "Fringale de
  minuit" too. A moon key light, a dark ambient and room lights on, keeping the HUD contrast and probe checks.
- **ART2 - A garden worth looking at** [Medium, M]. Start views are 30 to 50 % flat lawn (docs/m9/floors/level19_start.jpg,
  docs/m8/levels/level21.png). Hedges, a fence, a path, the street and a moving van at the exit frame the escape and
  improve every store shot.
- **ART3 - Calmer x-ray and see-through walls** [Medium, S]. Through walls the cones turn into jagged violet sheets over
  the wall tops (docs/m9/floors/level24_start.jpg), and a translucent band plus floating light strips cross several
  views (docs/m8/levels/level9.png, level12.png). An outline or hatching at low alpha reads cleaner.
- **ART4 - Eyes on the furniture** [High, M]. Small cartoon eyes on the player furniture that look around while unseen
  and squeeze shut when seen: a second, non-colour channel for the seen state, and the mascot the marketing needs.
- **ART5 - Detail on box props** [Low, M]. Sideboards, commodes and counters are bare boxes in several levels
  (docs/m9/handles/level19_wardrobe_ArmoireMilieu_game.png); drawers and handles as the M9 handles pass did elsewhere.
- **ART6 - Lighting and post nits** [Low, S]. Window panes blow out to pure white in every view; a sky gradient or
  curtains, and a slightly lower bloom on panes, keep the red furniture the brightest saturated thing.

## 11. Audio and music

- **AU1 - Adaptive music** [High, M]. One 40 s level loop plays under all 24 levels (AUDIO_REPORT 5). Add a tension stem
  driven by `seenMoving`, suspicion and the creak warning, a calm stem, a night variant, and one more track per act.
- **AU2 - Floor-aware footsteps and room ambience** [Medium, M]. Footsteps ignore the floor (FootstepAudio.cs reads no
  floor) and every room has the same air vent. Carpet, tile and marble steps plus per-room beds (fridge hum, clock,
  TV) tell where people are without looking; pairs with GP3.
- **AU3 - Personality voices** [Medium, M]. "hm ?" and "hein ?" are one synthesized cue for everyone. Short CC0 or
  generated grunts per personality (granny's sigh, the teen's "pff", the neat freak's tut).
- **AU4 - A separate effects slider** [Medium, S]. Options hold Volume (master) and Music only; effects were cut 4 dB by
  default (AUDIO_REPORT 9.2) and players cannot rebalance them.
- **AU5 - Finish the listening pass** [Medium, S]. Still open: the win jingle, the wardrobe pair, the door, crash versus
  topple; the dog bark is still synthesized (AUDIO_REPORT 8).

## 12. Progression and replayability

QW6 (move on when stuck) belongs here.

- **PR1 - Three stars per level** [High, M]. Escape, escape with no discovery, escape under par, where par comes from
  the audit (the last `at` of `designerRoute`, 10.3 s on level 1) plus a margin. Stars unlock red finishes for the
  furniture (lacquer, velvet, chrome), never another colour.
- **PR2 - Collectibles** [Medium, M]. One lost sock or coin per level off the safe path: an optional detour that forces
  a new route through known routines.
- **PR3 - Modifiers and a daily challenge** [Medium, M]. No careful mode, no cones, a mirrored house, Difficile with a
  shorter grace; a seeded daily pick of level and modifier with its own record.
- **PR4 - Ghost of your best run** [Medium, M]. Record the furniture pose on each fixed step of a record and replay it
  translucent; with a full-game timer it also serves speedrunners.
- **PR5 - Achievements** [Medium, S]. Steam and Play Games: sat on 10 times, a pratfall, freed from the dog, every star.
- **PR6 - Level editor, in two steps** [Medium, L]. First load user JSON from a mods folder, checked by `LevelValidator`
  (Core, available in the player); then an in-game editor. The audit stays in the editor, so mark such levels
  "unverified".

## 13. Narrative and humour

- **NA1 - Speech bubbles** [High, M]. One-line world bubbles per personality on a discovery, a carry back, a pratfall,
  the dog's hold ("J'aurais juré qu'elle était près de la fenêtre..."), and when two people meet over a moved chair.
  Pillar 4 (comedy) is mostly silent today; the "?" and "!" markers already give the anchor.
- **NA2 - Name the characters on the intro card** [Medium, S]. Hints name Lea, Rex, Hugo, Odile, Dad, Mum, the butler and
  the countess (Strings.cs:148-159) but the card lists only "The Suspicious One, The Rusher, Granny"
  (TestResults/shots/24_level22.png). Show "Lea, the Suspicious One".
- **NA3 - Pools of fail lines** [Medium, S]. One fixed body per lose reason (Strings.cs:74, 81). Ten jokes per reason,
  some tied to the personality who caught you, keep the hundredth catch funny.
- **NA4 - A thin story** [Medium, M]. Why escape and where to: three act cards and an epilogue (the garage sale, the
  van, the other furniture waiting in the garden) instead of "Every room is behind you".

## 14. Accessibility

QW5 (game speed assist) belongs here.

- **AX1 - Reduce flashing** [Medium, S]. The creak warning flashes at 6 Hz (Hud.cs:1325) and the red edge pulse runs near
  3 Hz (Hud.cs:1330). Cap both under 3 Hz and add a "reduce flashing" toggle.
- **AX2 - Text and HUD size** [Medium, M]. All uGUI sizes are fixed and the HUD labels are small at 720p; one option that
  scales the HUD and menu canvases.
- **AX3 - Colour options** [Medium, M]. A red player and a green exit are a red-green pair. Offer player colour presets
  (yellow, magenta, cyan) with the exit icon of QW9, keeping the eye shapes of M6.
- **AX4 - Sound captions** [Medium, M]. Off-screen footsteps, a bark, a door, a crash become short edge captions with a
  direction, for deaf and hard of hearing players.

## 15. Performance and mobile

QW11 (measure on a real phone) belongs here.

- **PF1 - Bake the NavMesh per level** [Medium, M]. Each first load builds a NavMesh at runtime with 0.05 m voxels
  (NavPlanner.cs:82-101). Bake it at import and ship it as an asset for shorter loads on phones.
- **PF2 - Cheap menus** [Medium, S]. `NeverSleep` is set whenever a tier is applied (QualityTier.cs:120), title
  included, and the title's 3D camera tour runs at the play frame rate. Use 30 fps and the normal sleep timeout outside
  play.
- **PF3 - Automatic quality on first launch** [Medium, M]. Every Android device starts on Moyen; pick Bas, Moyen or Haut
  from `SystemInfo` or a 3 s benchmark on the title.
- **PF4 - Shader warm-up** [Medium, M]. Materials are created at runtime and compile their variants on first use; a
  ShaderVariantCollection warmed during the title avoids hitches on Vulkan phones.
- **PF5 - Cone mesh cost** [Low, S]. Each cone casts 40 rays and rebuilds its mesh every rendered frame, even with cones
  hidden by the option (VisionConeView.cs:358-372); skip hidden or off-screen cones, rebuild on the fixed step.

## 16. Monetization and store options

QW15 (decide the model) belongs here.

- **MO1 - Mobile: a free first act and one unlock** [Medium, M]. One non-consumable purchase for the full house (Unity
  IAP), no ads and no energy. If ads ever come, only an opt-in reward that shows the designer route, a data every
  level already holds.

## 17. Store page, marketing, trailer and screenshots

QW14 (the name check) belongs here.

- **MK1 - A trailer and GIF capture tool** [High, M]. Designer routes replay deterministically (RouteReplayer, a test
  helper today) and the title camera tour exists; script cinematic cameras over them to export clean clips at will.
- **MK2 - Better store screenshots** [Medium, S]. The probe shots are high, with half the frame lawn. Shoot at eye level
  (the title tour), closer, on comic beats: the carry back, the pratfall, the dog's hold.
- **MK3 - Hook and demo plan** [Medium, M]. "Red light, green light, but you are the furniture." A Steam page early for
  wishlists, an act 1 demo for Next Fest, a short press kit.

## 18. Localization

QW3 (system language) belongs here.

- **LO1 - Strings in a data table** [Medium, M]. 180 lines of C# dictionary (Strings.cs:44-223); a CSV or JSON table
  lets translators work, then Spanish, German, Italian and Brazilian Portuguese (Latin glyphs work with the legacy font).
- **LO2 - Text expansion safety** [Medium, S]. A pseudo-locale with +40 % length finds overflow in the options rows, the
  hints and the two-line level card names before a real translation does.

## 19. Analytics and telemetry

- **AN1 - Local run log and heatmap** [High, M]. Per attempt: level, difficulty, lose reason, catch position, watcher,
  time; `GameState.Restarts` exists (GameState.cs:101) but is never kept. A JSON log plus an editor overlay on the
  level miniature turns every playtest into tuning data for LD1.
- **AN2 - Opt-in remote telemetry** [Medium, M]. After release, with GDPR consent, the same events to a small endpoint
  (or Unity Analytics), never before consent.

## 20. Technical debt

QW12 (WAVs in git) belongs here.

- **TD1 - One way to copy the options** [Medium, S]. `SaveOptions` is rebuilt field by field in nine places
  (Menu.cs:152, 164, 177, 189, 199, 207, 220, 232, 244); a new field forgotten in one silently resets that option.
  A clone-with helper removes the trap.
- **TD2 - Split GameState** [Medium, L]. 2,862 lines run every mechanic (dog hold, robots, rock, load, wardrobe, doors)
  in one FixedUpdate. Per-mechanic systems called in a fixed order; LevelAudit.cs (7,868 lines) next.
- **TD3 - No runtime writes to project assets** [Medium, S]. `QualityTier` sets `renderScale` on the shared
  Mobile_RPAsset (QualityTier.cs:113); in the editor this dirties a tracked asset that can be saved at 0.75.

## 21. Testing, CI and build pipeline

QW13 (store-ready Android build) belongs here.

- **QA1 - Nightly verify on a runner** [Medium, M]. `verify.sh` runs by hand under the `tools/unity.sh` lock; a
  self-hosted runner on the development PC nightly, and the full `mutation.sh` before a release (skipped in M6 for
  credits).
- **QA2 - Golden-image diff** [Medium, M]. The probe shots are "meant to be looked at"; a perceptual diff against
  approved shots would have flagged the floating light strips and the night level automatically.
- **QA3 - Android smoke test over adb** [Medium, M]. Install, launch with `--probe`, pull report.json and the player log:
  PRD 10.4 on a device.

---

## 22. Bugs and inconsistencies noticed while reading

1. Main.cs:69 - `IgnoreLayerCollision(Player, Inhabitant)`: inhabitants walk through the player furniture (visible
   clipping). PRD 3.2 left "reacting to furniture in the way" to M2; it never came.
2. Hud.cs:1160, 1220, 1247, 1251 - the fail and win action lines switch between keyboard and touch only: a gamepad
   player reads "Press R" and "Press Enter".
3. Hud.cs:511-512 and 520 with Strings.cs:62-63 and 67 - the careful, lamp and door hints are keyboard only; the
   wardrobe hint has a pad variant (GameState.cs:1844-1845) but no touch one.
4. Strings.cs:109, 113, 118, 126, 132, 146 - level hints 4, 6, 8, 11, 13 and 18 name Shift and E on every device.
5. InputReader.cs:126-136 and OrbitCamera.cs:159 - zoom reads only the mouse wheel; no zoom on gamepad or touch.
6. ProjectSettings.asset:89 `runInBackground: 1` and no `OnApplicationFocus` or `OnApplicationPause` in Assets/Scripts:
   the level keeps running when the window loses focus.
7. GameState.cs:1733-1734 with Hud.cs:1365 - the record clock and the routines start at the build, during the 5 s
   intro card.
8. Menu.cs:809 - `OptionsArrows` draws left and right chevrons on every Options row, but the rows only cycle forward on
   submit (Menu.cs:144-250); left and right only move the selection (Menu.cs:1122-1137).
9. Hud.cs:1325 - the creak warning flashes at 6 Hz, above the usual 3 flashes per second limit.
10. QualityTier.cs:113 - a project asset (`Mobile_RPAsset.renderScale`) is modified at runtime.
11. Strings.cs:155, 157, 184 - French switches to "vous" (Passez, Laissez, "Vous, au départ") while every other French
    line uses "tu".
12. Strings.cs:64 and 100 - English and French differ in content ("Stay strong." and "Freedom smells of fresh air."
    exist only in English).
13. Strings.cs:50 - the French column of `title.credits` is the English text.
14. Strings.cs:148-159 against the intro card - hints name Dad, Mum, the butler, the countess, Hugo, Odile, Rex and Lea,
    but the card shows only personality labels.
15. Strings.cs:129 - the English level 12 hint "Catch his eye moving and he pins you" reads backwards (the dog catches
    you moving).
16. Assets/Art/Environment/rug_modern_inset_border.png - coral and red shapes under the red player
    (docs/m8/levels/level9.png), against PRD 7.2 and ROOMS_PLAN.md section 4.
17. docs/m7/player_final.txt - level 16 "La nuit" has a start view luminance of 0.446, the same as the day levels.
18. docs/m8/levels/level9.png and level12.png - a white wall light strip floats mid-room over the see-through near
    wall, although ROOMS_PLAN.md section 5 says a lowered wall never leaves a fixture floating; a translucent
    horizontal band crosses the frame in the same shots and in level16.png and level21.png.
19. docs/m9/floors/level19_start.jpg - the grasscloth wall finish reads as stretched streaks at play distance.
20. LevelSelect.cs:65-78 - the default selection is the first unlocked card (level 1 forever), while Play starts the
    first unwon level.
21. VisionConeView.cs:358-372 - `Rebuild()` runs even when the option hides the cones.
22. Builder.cs:63 - APK only with debug signing; ProjectSettings.asset:150 and 182 keep version 0.1.0 and versionCode 1.
23. Repository .gitignore (`*.wav`) - none of the 33 effect WAVs is tracked (AUDIO_REPORT.md section 8).
24. Assets/Resources/Levels/test_*.json - about sixty test fixtures (and test_rooms, test_lights) ship in every build,
    since everything under Resources is packed.
25. docs/PRD.md:96-97 and README.md:4-5 say every player string is French, but English is the default (Strings.cs:19);
    PRD 8.1 names the folder games/OutOfSight; the README stops at the M6 gate, still says "you are a chair" and
    "probe steps 01 to 35".
26. docs/audio/AUDIO_REPORT.md section 7 - `ProbeTestsM5Ui.Step41b_PlayStartsTheFirstUnwonLevel` was reported failing on
    its premise after the title house arrived and "left as is"; confirm it was fixed or rewritten.
27. docs/m7/design.md section 2 - the retune "after" table is the baseline: no level file changed, so the flat curve
    the product owner reported (margins 15+ on levels 6, 8, 11, 12 and 16) is still there.
28. Strings.cs:291-360 - named members exist for levels 1 to 18 only; levels 19 to 24 are reached by key, in a
    scrambled table order (Strings.cs:148-159). Cosmetic, but a sign the per-level strings belong in the level JSON.

## 23. Count per area

| Area | Ideas | Of which quick wins |
|---|---|---|
| Core gameplay and mechanics | 5 | 0 |
| Level design and difficulty | 5 | 0 |
| AI and inhabitants | 5 | 0 |
| Controls | 6 | 2 (QW2, QW8) |
| Camera | 4 | 0 |
| UI, UX and onboarding | 8 | 3 (QW1, QW4, QW9) |
| Feedback and juice | 5 | 1 (QW10) |
| Art direction and readability | 7 | 1 (QW7) |
| Audio and music | 5 | 0 |
| Progression and replayability | 7 | 1 (QW6) |
| Narrative and humour | 4 | 0 |
| Accessibility | 5 | 1 (QW5) |
| Performance and mobile | 6 | 1 (QW11) |
| Monetization | 2 | 1 (QW15) |
| Store and marketing | 4 | 1 (QW14) |
| Localization | 3 | 1 (QW3) |
| Analytics and telemetry | 2 | 0 |
| Technical debt | 4 | 1 (QW12) |
| Testing, CI and build | 4 | 1 (QW13) |
| **Total** | **91** | **15** |

Plus 28 bugs and inconsistencies in section 22.
