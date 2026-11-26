# DOGCARRY: the dog brings the furniture back itself

Product owner: "quand il t'attrape, il te ramene comme un humain le ferait". When the dog catches the player furniture, the
dog itself drags it back to its place, the way a human would, instead of calling a human.

## How it works

The M5 hold is unchanged up to the pin: the dog barks, runs to the furniture, pins it (hold line, "WOUF !" bubble, bark
loop). Then, in `GameState.StepDogHold`:

1. Grip beat: `Tuning.DogGripTime` (0.6 s) of the pin, so the catch reads before anything moves.
2. `GameState.BeginDogDrag` picks the owner: the nearest human with a memory (the one the old hold would have called,
   wherever it is; it does not walk). The owner's memory decides everything, as the called human's did on arrival:
   - in place for its memory: nothing to bring back, the hold ends at no cost (old Step38i outcome);
   - out of place: the dog must have a path to the owner's slot (`InhabitantRoutine.CanPlanCarry`, the humans' planner
     `InvestigatePlanner`, same goal math as `BeginCarry`). With one, the dog starts the HUMAN carry
     (`InhabitantRoutine.BeginCarry(memories[owner].PlayerSlot)`): same pick up, same path planning, same put down, same
     return position and yaw. GameState makes the dog the `carrier`, so the existing carry code of `StepInvestigations`
     attaches the furniture (`FurnitureController.FollowCarrier`: controller disabled, so no collider or physics fights the
     drag), follows `CarryAnchor` every step (step 1: the input is not read while `Carried`, the player has no control),
     releases it on the slot and sets every memory's slot to it. The camera follows the furniture visual as during a
     human carry.
   - The owner makes the discovery its arrival would have made, at the grip: `DiscoveryCount`, `DogHoldDiscoveryCount`,
     `meters[owner].AddDiscovery()` (suspicion 1 loses as usual), the "hein" sound toward it.
3. The drag: the dog walks forward at `Tuning.DogDragSpeed` (0.8 m/s, a bit slower than a human's 1.0) with the furniture
   ahead of it, its near edge at the snout (the body's `CarryForward` already reaches the edge, as a human's hands do),
   lifted only `Tuning.DogDragLift` (0.06 m, instead of `CarryHeight` 0.30) with a deterministic tug wobble
   (`DogDragWobbleDegrees` 6 deg yaw, `DogDragBob` 0.03 m, 2.5 Hz) that fades in over the pick up and out over the put
   down, so the return pose stays exact. A bubble from the new `ReactionKind.DogDrag` lines shows at the grip.
4. Drop: the put down is the human one. The dog then barks once ("WOUF !" bubble + bark sound, no noise event), wags
   (`InhabitantRoutine.IsWagging`, a `Tuning.DogWagTime` 0.8 s Look beat queued after the put down; `Inhabitant.ApplyRig`
   wiggles the body visual, the head keeps the routine's gaze) and resumes its routine.
5. Interrupted drag (a pin or startle of the dog): the carry code drops the furniture where it is, the hold ends.

No human is called for a dog catch any more. The human put back for human catches is untouched (the carry block only
skips the human `PutBack` bubble when the carrier has no memory, i.e. the dog).

Walking backward was not chosen: the carry goal and anchor math puts the furniture ahead of the body; a backward dog
would need a visual offset from its rule position (vision cone origin) that would clip into walls next to the slot.

## Fallback

When `CanPlanCarry` fails (the dog has no path to the slot where the humans' planner would need a straight-line
fallback), the hold falls back on the old M5 behaviour: the nearest free human is called (`DogCall` bubble), finds it,
discovery and carry back. It is logged (`[GameState] DOGCARRY: the dog has no path ...`) and counted
(`GameState.DogDragFallbackCount`). With no human with a memory at all, the dog waits `DogHoldMaxWait` and gives up, as
before.

## New public API

- `GameState.DraggedByDog`, `GameState.DogDragCount`, `GameState.DogDragFallbackCount`.
- `InhabitantRoutine.CanPlanCarry(FurniturePose)`, `InhabitantRoutine.IsWagging`.
- `BeginCarry` now clears `Running` (a bark during the drag or the wag starts no new run).
- Tuning: `DogGripTime`, `DogDragSpeed`, `DogDragLift`, `DogDragWobbleDegrees`, `DogDragBob`, `DogDragWobbleHz`, `DogWagTime`.

## Strings

- New `react.dogDrag.dog.1..4`: "Mmmf! Mmmf!" / "Mmmf ! Mmmf !", "Grmf... heavy..." / "Grmf... lourd...",
  "Bad! Back home!" / "Vilain ! Au panier !", "Wuff... hnngh!" / "Wouf... hnngh !".
- `hud.dogHold` no longer promises a human: "The dog has you! Back to your place..." / "Le chien te tient ! Retour à
  ta place...".
- `react.dogCall.*` kept (fallback only).

## Files

- Assets/Scripts/Core/Tuning.cs (dog drag constants)
- Assets/Scripts/Core/InhabitantRoutine.cs (dog carry speed and lift, CanPlanCarry, IsWagging, wag beat, Running reset)
- Assets/Scripts/Runtime/GameState.cs (StepDogHold drag branch and grip, BeginDogDrag, carry wobble, PutBack bubble
  skipped for the dog, counters, docs)
- Assets/Scripts/Core/Reactions.cs (`ReactionKind.DogDrag`, appended last), Assets/Scripts/Core/Strings.cs
- Assets/Scripts/Runtime/Inhabitant.cs (wag, render only)
- Tests (static, not run): ProbeTestsM5Game Step38h renamed `Step38h_DogPinsTheChairAndDragsItBackItself` (drag,
  carrier, no human sent, chair follows the mouth, low lift, discovery, slot and yaw, wag then routine), Step38i (in
  place: no drag, nobody called, no cost); ProbeTestsBubbles Step80a/80b (dog's own drag lines, a human has none).
- mutation.sh: rows `dog_call` and `dog_call_finds` parked (commented, with the reason): their markers now mark the
  fallback only, which no fixture reaches. New rows `dog_drag` (`MUTATION:DOG_DRAG`, Step38h_) and `dog_drag_finds`
  (`MUTATION:DOG_DRAG_FINDS`, Step38i_). Every existing marker is kept in the code.

## Level files (not edited): concerns

- No level file names a human route to the dog spot; nothing in the data assumes the called human. The behaviour change
  is dynamic: before, a dog catch pulled the nearest human off its route (a long walk, sometimes across the house);
  now the humans never leave their routes. Designer routes (designerRoute / designerRouteHard) of 12, 15, 16, 17, 20,
  23, 24 that relied on the human's detour after a bark would differ; the routes are meant to avoid the dog anyway.
- Doors: 17 (porte_bureau), 20 (porte_cuisine), 23 (porte_couloir), 24 (porte_cuisine) have `openedByInhabitants`
  leaves: the dragging dog opens them on its way (StepHouseholdDoors is generic), and on the door memory levels 20, 23,
  24 every door memory then remembers them open. Before, the called human did the same on his walk.
- Player-only closed leaves (16 porte_salon, 17/20 porte_entree, 23/24 porte_chambre): if the slot is behind one still
  closed, the planner has no path: the fallback calls a human, who has no path either (same as before).
- Platforms and ramps (17, 23, 24): the dog drags the furniture up or down a ramp at 0.06 m over the floor under the dog;
  the furniture's far end may clip into the slope.
- 24: Rex walks the landing while the humans are downstairs: a catch on the landing is now resolved by the dog alone
  and fast; before, the player stayed pinned until a human climbed up.
- test_m5_audit_pet, test_m5_watchers_dog, test_pet: no human, so no owner: the dog waits and gives up (unchanged).

## Compile

See the end of this file.

## A VERIFIER

1. Run Step38h_ and Step38i_ (ProbeTestsM5Game) and Step80a/80b (ProbeTestsBubbles); then `./mutation.sh dog_drag`.
2. Feel test level 12 and 24: the drag speed (0.8 m/s), the 0.6 s grip, the wobble amount, the wag (12 deg at 22 rad/s)
   and whether the dog walking forward with the furniture in its mouth reads as "dragging" (the PO may want the backward
   walk: it needs a visual offset, see above).
3. Visual: the furniture's near edge vs the Shiba's snout for each body (CarryForward 0.40 to 0.65): the armchair
   and sofa bodies may hang in front of the snout or overlap its head.
4. Owner choice: the nearest human with a memory, whatever its mode (frozen, investigating, far away). The old call took
   the nearest calm free human. Check this is the wanted suspicion target (e.g. a frozen sentinel gets the discovery).
5. Discovery timing: at the grip (as on the called human's arrival). A suspicion loss now happens at the grip, before
   the drag shows; check the fail panel reads well (the dog's drag bubble and the catch line on the same step).
6. Fallback never reached by a fixture: build a no-path dog fixture (e.g. a slot behind a closed player-only leaf),
   then restore the parked mutation rows `dog_call` and `dog_call_finds`.
7. Ramps (17, 23, 24): the low drag over a slope, and a slot on the platform.
8. LevelAudit / designer route replays with a dog (the audit does not model the hold; check it never assumed a human
   detour).

## Compile result

One run, `OutOfSight.Editor.Builder.SetupAndCompile` via tools/unity.ps1 (after DOORAUTO's compile passed, exit 0):
exit 0, 0 `error CS` in Build/DOGCARRY.log (CompileScripts 3.8 s, runtime, editor and both test assemblies). No test was run.
