# TIPS progress (idea 3: first-time tips for levels 1 to 3)

Agent TIPS, 2026-11-20 / 2026-11-21. Static work plus one compile-only Unity run (no tests, no player build: PO policy).

## Design

Six one-sentence tips (FR/EN, "tu" register, no em-dash), each shown once per save when its situation first happens,
with a small amber chevron bobbing over the related HUD element or world spot. One tip at a time, never blocking input.

| Key | Trigger (read after every fixed step, level started and playing) | Levels | Pointer |
|---|---|---|---|
| tips.freeze | the furniture moves and a human watcher's cone turns toward it (angle to the furniture within HalfAngle + 25 deg and shrinking since the previous step, within 1.25 x range), or the caught grace already runs (SeenMoving > 0) | 1, 2, 3 | eye |
| tips.creak | first creak warning (Creak.Warning rises) | 1, 2, 3 | creak gauge |
| tips.suspicion | first rise of the highest suspicion (MaxSuspicion > 0 and increasing, memory rule on) | 1, 2, 3 | suspicion gauge |
| tips.decoy | a decoy of the furniture's kind within 2 m (planar), memory rule on | 3 | world: top of that decoy |
| tips.rug | the furniture's centre stands on a rug (a soft room is not a rug) | 2, 3 | world: rug centre |
| tips.eye | the eye opens Calm (seen, still) while not moving | 1, 2, 3 | eye |

Precedence on the same step: the table order. The freeze tip replaces an uncommitted eye tip; any other request while a
tip is on screen is refused (the situation recurs and the tip fires then).

Tokens: `{move}` resolves per device (tips.move.keyboard "the keys", .gamepad "the stick", .touch "your thumb"; FR
"les touches" / "le stick" / "le pouce"), then `{action}` / `{careful}` through `Hud.ResolveHintTokens` like the hints.
Language and device changes re-resolve the shown sentence.

Lifetime: fade in, shown for `TipDef.ShowSeconds` (5 s unscaled, pauses excluded) or until a new press on any device after
`TipDef.MinSeconds` (1 s), read directly from the Input System devices (nothing consumed: InputReader's latches untouched).
Committed to the save (SaveData.Tips, SaveStore.Save) once shown for MinSeconds; a tip cut short before that (restart,
caught) is not saved and comes back. Hidden (clock stopped) while paused, under a menu (Hud.Visible false) or an end
panel; an end panel drops it. Never before the held start releases (no FixedStepped runs before it). A new level or a
restart (Hud.ShowLevel) clears the plate. "Par défaut" resets the options only: tips stay shown; a new save shows them again.

Off under --probe and --look (`Tips.DefaultEnabled`), so shots and probe steps are unchanged; tests set
`Tips.EnabledOverride = true`.

Layout (reference pixels): plate on a row at y 312 (above the sat-on row), centred under the anchor's x and clamped to the
screen; text 34 px, wraps at 1100; chevron 44 px turned to point down, 10 px above the element's top, bobbing 6 px. A world
spot projects through Hud.View; off screen or behind the camera the chevron hides and the plate sits centred on its row;
a spot low on screen pushes the plate above it so the plate never covers the spot.

## Files

- New `Assets/Scripts/Core/TipDef.cs`: keys, anchors, per-tip levels, thresholds (ShowSeconds, MinSeconds, ApproachMarginDegrees,
  ApproachRangeFactor, DecoyNearMetres), `ConeTurnsToward`, `MoveKey`.
- New `Assets/Scripts/Runtime/Tips.cs`: the MonoBehaviour (nested Canvas under the HUD) with the step rules, `Trigger(key, world)`,
  `Dismiss()`, `Clear()`, test accessors (ShownKey, ShownText, Visible, Committed, ShownSeconds, PointerScreen, PointerVisible,
  LastRefusal, CommittedCount).
- `Assets/Scripts/Runtime/Hud.cs`: `Tips` property, `EyeAnchor` / `CreakAnchor` / `SuspicionAnchor`, `Tips.Build(this)` at the
  end of Init, `Tips?.OnLevelShown()` in ShowLevel, `Tips?.Relocalize()` at the end of Relocalize. No MUTATION marker touched.
- `Assets/Scripts/Core/SaveData.cs`: field `Tips` (`"tips"`, list of keys) and its lenient parse (malformed ignored, never fails
  the save).
- `Assets/Scripts/Core/Strings.cs`: section "Onboarding tips" at the end of the table (tips.eye, tips.freeze, tips.creak,
  tips.suspicion, tips.rug, tips.decoy, tips.move.keyboard/gamepad/touch) and six named members (TipsEye ... TipsDecoy).
- `Assets/Scripts/Runtime/GameState.cs`: untouched (everything the rules need is already public: FixedStepped, EyeState,
  Creak, MaxSuspicion, SeenMoving, FurnitureMoving, Level.Inhabitants, Level.Decoys, Def.Rugs).
- New `Assets/Tests/PlayMode/ProbeTestsTips.cs` (static, never run): Tips_01 to Tips_05 on the Boot scene, Tips_06 plain test.

## Compile

Run 1 (2026-11-21, `Build/TIPS.log`): Core and Runtime assemblies compile with no error or warning in the TIPS files. The
test assembly fails on `Assets/Tests/PlayMode/ProbeTestsFocusPause.cs` (agent FOCUS): its `[assembly: TestRunCallback]`
duplicates the one of `ProbeTestsHeldStart.cs` (CS0579, not a TIPS file).
Retry (allowed once for a foreign error, after FOCUS removed its duplicate; `Build/TIPS_r1.log`): exit 0, no compile error,
no warning in the TIPS files; every assembly compiles (Core, Runtime, EditMode and PlayMode tests, ProbeTestsTips included).

## A VERIFIER

- PlayMode filter `ProbeTestsTips`: Tips_01 (level1 freeze/eye tip fires while driving forward: if the level1 watcher never
  turns within 25 s, drive toward the sofa instead), Tips_02 (gauge pointers: 60 px tolerance against CreakScreenRect /
  SuspicionScreenRect), Tips_03 (decoy pointer over the first decoy of level3; rug tip on level2), Tips_04 (pause, cut short,
  restart), Tips_05 (needs level1 to catch the chair driving straight: Inconclusive otherwise), Tips_06 (save round trip,
  strings).
- In game (new save, levels 1 to 3, keyboard then gamepad then touch): the freeze tip comes the first time the watcher turns
  while you move and not before; "{move}" reads "the keys" / "the stick" / "your thumb"; the chevron sits just above the eye,
  not over the sat-on row; the creak tip appears with the gauge's flashing; the suspicion tip appears on the first out-of-place
  discovery; level2: the rug tip on the first rug, chevron on the rug centre; level3: the decoy tip near a chair decoy, chevron
  on top of that chair; each tip once per save (quit and relaunch: none again; delete the save: all again).
- Pause (Esc) in the middle of a tip: plate gone, back on resume with its remaining time; options "Par défaut" leaves the tips
  shown.
- Being caught 0.5 s after a tip appears: the tip comes back on the retry (not committed under 1 s).
- A press dismisses only after 1 s; holding the move keys does not dismiss (anyKey.wasPressedThisFrame is a new press).
- Plate width and wrap at 16:10 and on a 20:9 phone (text 34 px, max 1100 reference px, two lines at most for the FR creak tip).
- Shots under --look and probes under --probe show no plate (DefaultEnabled false).
- CoreTests string checks: every tips.* key has both languages and no em-dash (Tips_06 covers it too).
