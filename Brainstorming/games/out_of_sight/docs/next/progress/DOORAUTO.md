# DOORAUTO progress (doors and wardrobes open by pushing toward them)

## The request (product owner, 2026-11-21)
Replace E for doors by simply moving toward the door, for all doors including the wardrobe's (hide = push into its
front, leave = push out of it). Remove the action button on Android, now useless.

## How it works
- Push target: `GameState.DoorPushDirection` (also `FurnitureController.DoorPushTarget`), a planar unit direction or
  null, with the same priority as the old E hook:
  - hidden: out of the wardrobe's front (`WardrobeRule.Front`);
  - else the nearest closed leaf in reach that the player may open: its wall's normal, from the furniture's side into
    the wall (`GameState.DoorPushToward`). Not toward the doorway centre, so a push along the wall never opens it;
  - else a wardrobe in front that the body fits in: into its front;
  - a playerLocked leaf is never a target: the existing "Locked" hint (hud.door.locked) shows, and a push simply drives
    into the closed leaf.
- Push (`FurnitureController.StepDoorPush`, every step that takes input, upright, not pinned, not carried, no action,
  hidden included): the wish must be at least `Tuning.PushMinInput` (0.3) strong and within `Tuning.PushConeDegrees`
  (45) of the target.
  - It starts only if the furniture is still, or pressed against the door: it pushed toward it on the last step too
    yet did not travel toward it (standing against the closed leaf or the wardrobe, maybe sliding along it).
  - A furniture travelling toward the door drives on into the leaf, stops there, and the push starts then. So a route
    leg heading for a door cell never opens it on the way.
  - Once started, the push holds the furniture still (`DoorPushHolding`, a release for the body: no travel, no turn).
  - After `Tuning.PushConfirmTime` (0.16 s = 8 fixed steps, `FurnitureController.DoorPushConfirmSteps`), on the next
    step where the furniture is still, the push is confirmed and handed to `GameState.ClaimDoorPush`. That is the old
    `ClaimActionKey`, unchanged: the same `BeginExternalAction(DoorOpenTime)` or `(WardrobeActionTime)`, the same
    leaf swing, counters, sounds, door memory events and wardrobe stages.
  - The confirm step is the first step of the action, exactly as the E press step was, so the audit's model of an
    action (LevelAudit.cs, untouched) stays valid: the furniture is still before the action in both cases.
  - Leaving the cone, an action, a teleport, a pin or a carry resets the push.
- E / gamepad X: only the floor lamp now (`FurnitureController.Step`: the door push branch comes first, then the lamp,
  then the hold). E near a door with the lamp body switches the lamp (it used to open the door). E and X still release
  a held start (STARTFIX unchanged), and a move still releases it too.
- Touch: the action button is gone (`TouchControls.ActionButton` removed, `Tuning.TouchActionSize` removed). The lamp
  is switched by a tap on the player lamp itself: a short tap (the STARTFIX tap: lifted within 0.35 s, travelled at
  most 20 px) whose origin falls in `TouchControls.PlayerLampScreenRect` (the player furniture's box projected by
  Main.Camera, grown by `Tuning.TouchLampTapMargin` = 60 px of a 1080 px screen, only for a lamp body under
  GameRules.Lamp, not hidden) calls `InputReader.PressTouchAction` (the E key); any other tap stays the start press.
  Marker `// MUTATION:TOUCH_LAMP_TAP`.
- Grep of the action API: `InputReader.ActionPressed` has one reader (FurnitureController.Step: lamp, previously also
  the door hook); `InjectAction` is used by tests and RouteReplayer ("toggle"); `PressTouchAction` by TouchControls
  (now the lamp tap). No other use.
- New test hook: `InputReader.InjectDoorPush` (a push already held for its confirm time, handed to the game on the
  next step, no direction needed), the door and wardrobe equivalent of the old `InjectAction`.

## RouteReplayer
"open", "hide" and "leave" no longer press E.
- At "at" minus `PushSteps * FixedStep` (0.16 s), once the furniture is still, the replayer pushes along
  `GameState.DoorPushDirection` (ScriptedDirection). The action therefore begins on the step after "at", the step the
  E press made it begin.
- The direction is cleared on the step the action starts.
- A push that started nothing after its 8 confirm steps plus `PressWaitSteps` (2) is pushed again, at most
  `MaxOpenPresses` (5) pushes, then the step is given up (`OpenFailures`).
- With no target (no door in reach) the push is waited out with no input, which keeps Step45f's semantics.
- `OpenPresses` now counts pushes. "toggle" keeps `InputReader.InjectAction` (the lamp).

## Strings (Strings.cs, FR and EN; re-read right before editing)
- hud.door: "Push toward the door to open it" / "Pousse vers la porte pour l'ouvrir".
- hud.hide: "Push into the wardrobe to hide" / "Pousse vers l'armoire pour te cacher".
- hud.leave: "Push away to come out" / "Pousse vers l'extérieur pour sortir".
- hud.hidePad and hud.leavePad removed (the push names no key, one sentence for every device).
- hud.lampPad (new): "X: lights off / on" / "X : éteindre / allumer".
- hud.lampTouch (new): "Tap the lamp: off / on" / "Touche la lampe : éteindre / allumer". The lamp hint now follows
  the device (Hud.SetLampHintText, on device change and Relocalize); hud.lamp (E) unchanged.
- hud.controlsTouch: "Action: act" removed.
- touch.action replaced by touch.lamp ("tap the lamp" / "touche la lampe"), the touch name of {action}.
  `Hud.ActionLabel` now reads the lamp hints: E, X, "tap the lamp".
- level18.hint: no {action} any more ("push into it to hide inside, push away to come back out" / "pousse vers elle
  pour t'y cacher, pousse dans l'autre sens pour en sortir").
- level6.hint keeps {action} (the lamp).
- No tip (tips.*) named the action: unchanged.
- README.md controls: X is the lamp, plus the door and wardrobe push and the touch lamp tap.
- Hud: the door and wardrobe hint plates widened to 780 px (the push sentences are longer than "E: ...").

## Files
- Runtime: FurnitureController.cs, GameState.cs, InputReader.cs, TouchControls.cs, Hud.cs, WardrobeDoors.cs (comment).
- Core: Tuning.cs (PushConfirmTime, PushConeDegrees, PushMinInput, TouchLampTapMargin; TouchActionSize removed),
  Strings.cs.
- README.md, this file.
- LevelAudit.cs untouched (its comments still name GameState.ClaimActionKey, now ClaimDoorPush; not a cref).

## Tests (static edits only, not run; T1 owns these files)
- RouteReplayer.cs: push instead of E for open, hide and leave (see above).
- ProbeTestsM5Bodies.cs:
  - TearDown clears DoorPushClaimed and DoorPushTarget.
  - Step36j rewritten on the push hook: no target means a drive; E never reaches the hook; asked once after the
    confirm steps, the lamp held still; asked again one confirm later; the claim step is the first opening step.
- ProbeTestsM5Game.cs:
  - Door E presses become `InjectDoorPush`.
  - Step36c: E with the lamp in reach now switches the lamp and leaves the door closed.
  - New Step36c2: a real push opens after exactly 8 held steps, still and unturned; 90 and 60 degrees off never
    open; a short push opens nothing.
- ProbeTestsM6Gameplay.cs:
  - Wardrobe and door E presses become `InjectDoorPush`.
  - The hidden stool's held input in Step53a is now sideways (Vector3.back was a push out of the wardrobe).
  - New Step53a2: a real push into the front hides after 8 still steps, a sideways one never does; hidden, a push
    into the wardrobe never leaves, a push out leaves on step 9.
- ProbeTestsHeldStart.cs: HeldStart03 also injects door pushes at the playerLocked leaf and checks it offers no push
  direction. HeldStart01 still starts with E (a start input).
- ProbeTestsM7Touch.cs: Step63a taps the player lamp (and a tap away does nothing); Step63b checks the action button is
  gone and the careful button sits at the bottom.
- ProbeTestsHudV2.cs: {action} on touch is touch.lamp.
- ProbeTestsBars.cs: the touch overlay reference moved from ActionButton to CarefulButton.
- ProbeTestsTips.cs: nothing to change (no tip names the action).

## mutation.sh rows
- e_claim: the marked line changed. New marked text:
  `bool claimed = DoorPushClaimed != null && DoorPushClaimed(); // MUTATION:E_CLAIM`,
  replacement `bool claimed = false; // MUTATION:E_CLAIM`, still PlayMode `Step36j_`.
- New marker, suggested row:
  `touch_lamp_tap|Assets/Scripts/Runtime/TouchControls.cs|return PlayerLampScreenRect(out Rect rect) && rect.Contains(screen); // MUTATION:TOUCH_LAMP_TAP|return false; // MUTATION:TOUCH_LAMP_TAP|PlayMode|Step63a_TouchButtonsActionCarefulPause`.
- Every other marker is unchanged in text (TOUCH_TAP_START, START_PRESS, LOCKED_LEAF, LOCKED_HINT, HINT_TOKENS,
  EXTERNAL_STILL, TOUCH_UI_GATE, PUSH_*).

## Compile
One Unity run (tools/unity.ps1, agent DOORAUTO, queued behind LEVELS6's lock):
`OutOfSight.Editor.Builder.SetupAndCompile`, exit 0, 0 `error CS` in Build/DOORAUTO.log. The runtime, editor and both
test assemblies (OutOfSight.Tests.PlayMode, OutOfSight.Tests.EditMode) compiled. No test was run.

## A VERIFIER
1. Replay timing when the furniture reaches the door cell late. The replayer starts its push at "at" - 0.16 s only if
   the furniture is already still. If the leg arrives after that, the action begins up to 0.16 s later than with E.
   The audit's fidelity replay (LevelAudit.KinematicReplay, untouched) does not model that. Check the designer route
   replays of the door and wardrobe levels (level8, level18 to level24, Step45 and the playthrough) with LEVELS6's
   routes.
2. A real player walking into a door at an angle slides along the leaf and wall. The push starts once it presses
   against them (no travel toward the door), but an office chair then glides along the wall first. Feel test on PC and
   phone.
3. A stool pressed against a door while sliding fast along it is released by the hold: it may tip (the usual release
   rule). Feel test level 18.
4. The runtime probe bot (Probe.cs) and any scripted drive that stops still in reach of a closed door and keeps
   pushing toward it now opens it after 0.16 s (before, it stayed blocked). Check the probe's verify run.
5. Touch lamp tap: the tap rectangle (lamp box + 60 px) on a real phone, and a tap meant as a start press that lands
   on the lamp (it switches the lamp and starts the level).
6. The lamp hint "Touche la lampe : éteindre / allumer" overflows its 380 px label to the left at 30 px: check it
   does not overlap the controls line on a 20:9 phone.
7. The door and wardrobe hint plates (780 px) on the narrowest supported screen.
8. HeldStart02 (hold on vs off must win on the same step): the push is symmetrical, but run it.
9. LevelAudit.cs comments still mention E and ClaimActionKey; update them when LEVELS6 releases the file.
