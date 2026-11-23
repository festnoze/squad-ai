# GRIP: where carriers hold the furniture (humans' hands, the dog's bite), and the title's dog and human loops

Product owner feedback (two screenshots, 2026-11-22):
1. The black Labrador grabs the red STOOL with its snout at the top of the seat: too high. It should bite where a dog
   would (a leg or the low rung, near the floor), the head-roll bite pose kept.
2. A man carrying the red CHAIR stands inside its back, his hands sunk into it. His hands must rest ON the chair (top of
   the backrest and/or the seat's edge), his body at a believable distance behind it.
3. Every carryable body, for humans and the dog. Then the title screen: a human comes from the left, grabs the chair with
   the new grip and pulls it home (the rest of the loop kept).
4. Coordinator's change (same day): do NOT remove the title dog: the loops ALTERNATE, one with the dog (with the new low
   snout grip), the next with the human, and so on.

## Diagnosis

- The carry anchor is gameplay (`InhabitantRoutine.CarryAnchor`: `CarryForward` ahead of the carrier, `CarryHeight` 0.30
  up for a human, `DogDragLift` 0.06 for the dog). The chair's backrest (its near side, the carried furniture takes the
  carrier's yaw) is only 0.225 m ahead of the man's feet; his belly reaches 0.13 to 0.15 m (more in the walk clip).
- The human's carry arms were fixed angles (`RigCarryUpperArmPitch` 50, `RigCarryLowerArmPitch` 15): the hands ended
  about 0.5 m ahead at 1.06 m high, i.e. inside the chair (its backrest spans 0.225 to 0.27 m ahead, its seat beyond).
- The dog's snout stayed at its own height (about 0.50 m), stepped back to the near edge (DOGBIG): on the stool that is
  the seat's cushion (0.45 to 0.55 m, plus the 0.06 lift).

## What changed (presentation only: the rules, the anchor and the routine never move)

- New `Assets/Scripts/Core/GripDef.cs`:
  - `GripDef.For(kind)`: per body, in the furniture's frame (carrier on -z): the human's two wrist targets and finger
    directions, `HumanStand` (how far behind the furniture's centre his body stands) and `HumanLean`, and the dog's
    `Snout` point. Measured on the fitted models (scratchpad `furn.py` on the Kenney GLBs; FurnitureKit for the
    procedural office and rocking chairs):

| Body | Hands (wrists) | Human stands (hold back) | Dog bites |
|---|---|---|---|
| chair | top rail of the backrest (y 0.935, z -0.245, x +-0.15), fingers over it | 0.56 m (0.11 m behind the rule position) | left back leg, 0.26 m up |
| stool | sides of the seat (y 0.53, x +-0.20), lean 14 deg | 0.42 m (0.03 m ahead) | near left leg, 0.28 m up (MUTATION:GRIP_STOOL_LOW) |
| armchair | top of the backrest (y 1.08, x +-0.24) | 0.75 m (0.10 behind) | low back, 0.28 m up |
| floor lamp | round the pole, right hand higher (0.80 / 1.00) | 0.40 m (0) | the pole above the foot, 0.34 m |
| office chair | top of the backrest (y 1.03, x +-0.17) | 0.68 m (0.03 behind) | the seat's rear rim, 0.42 m |
| rocking chair | tops of the back posts (y 1.07, x +-0.22) | 0.72 m (0.07 behind) | the seat's rear rim between the runners, 0.42 m |

  - `GripMath`: the dog's neck bend (degrees, bisection) that brings its snout tip down to a height: the neck chain's
    segments turn a third, two thirds and all of the bend, the head follows (`Tuning.DogGripHeadFollow` 1).
- `Inhabitant` (render only): `Grip` and `GripFurniture` (set by `GameState.WireRoutines` for the level's furniture).
  The hold step (DOGBIG's hold back) is now a 2D step in the body's frame (`ShownHold`: sideways, back), eased at
  `DogHoldBackRate`:
  - a carrying human: back by `HumanStand - CarryForward`, while his hands rest on the carried furniture;
  - the biting dog, from the pin to the drop: the bite point in its body frame, the rig solves the neck bend for its
    height (`InhabitantRig.SolveBite`), the step puts the snout tip on it (sideways up to 0.3 m, toward the furniture
    still on the floor up to `Tuning.DogGripReachIn` 0.35 m); the wag keeps the last step. Without grip data: DOGBIG's
    near edge.
  - the human's wrist targets are taken from the furniture as it is drawn this frame (`FurnitureController.InterpolatedBase`,
    no LateUpdate order dependency) and handed to the rig with the grip's weight (`HandGripRate` 6/s).
- `InhabitantRig`: after the old carry pose, a two bone IK per arm (`SolveArm`, swing only, the elbow out, down and back),
  the palm aimed along the fingers (`AimBone`); the stool's lean on the spine (never on top of the pick up's bend);
  Palm.L/R found (`PalmLeft`, `PalmRight`) and reset each frame with the other driven bones. For the dog: the neck chain
  (Neck1..3) measured in Idle, bent nose down by `GripNeck * Bite` before the head, then the head pitched by the same
  angle after the absolute head line (MUTATION:HEAD untouched), then PetPose's roll, dip and jaw as before (PetPose not
  edited: DOGFACE owns the jaw and face).
- Tuning: `DogSnoutDrop`, `DogGripHeadFollow`, `DogGripReachIn`; title: `TitleLogoDogBiteHeight`, `TitleLogoHuman*`.

## Title logo (TitleLogo.cs): alternating loops

- `Sample(phase)` now covers two loops (`Phase` in [0, 2)): even loops the dog, odd loops the human; the spot, the hops,
  the return and the startle are identical; both start and end on `Rest`; 15 s still in each.
- The dog's loop: frames 2 and 3 are new bite frames (the same strides with PetPose's bite and the neck bent by
  GripMath until the snout is at `TitleLogoDogBiteHeight` 0.30 m, the chair's left back leg), shown from the grab to the
  end of the drag (`Pose.DogBite`). A bite frame takes its walk stride's scale factor (its lowered head would trip the
  height guard).
- The human's loop: the level 1 man (`quaternius.man`, dressed by the game's own rig and CharacterLook, then the rig is
  switched off) at `TitleLogoHumanScale` 0.6, yaw 85, standing at `HumanRoot` (0.30 m behind the middle of his hands,
  which rest on the backrest's top rail: GripDef's chair wrists at x 0.17 and 0.03 across the rail). Four static copies:
  walk 0 and 1, then the same strides with the arms IK'd onto the rail (the game's `SolveArm` and `AimBone`). Bake passes:
  each copy alone (colour and shadow), and each holding copy with the chair (the pair). The pair's picture keeps, per
  sample, the human where it matches the human alone better than the chair alone, else the chair (with the chair
  layer's gamma curve); it is drawn exactly over the chair's layer while he holds it (no lift, no tilt then), so his
  hands lie on the rail and the backrest hides what it should. Timeline: walks in from the left edge (4.70 to 5.90 s),
  grabs (to 6.30), pulls home backwards with short steps (to 9.10, frames swap every 0.1 m), lets go and backs off
  0.06 m, stands, turns and walks out through the left edge.
- Margins: the frame has 1.04 m of floor above the chair's foot; at 0.6 the human's head is planned about 5 units under
  the 20:9 top (481 limit). The frame and the chair's size are unchanged.

## Tests (static, see the Unity runs below)

- New EditMode `Assets/Tests/EditMode/GripTests.cs`: every kind has its grip; hands on the furniture, within the arm's
  reach (Quaternius man measured: shoulder 1.357 m, arm 0.559 m), the body clear of it; the chair's carrier stepped back
  and his hands on the top rail; the dog bites the stool by a leg below its seat (mutation row `grip_stool_low`); the dog
  never bites above 0.45 m nor on the far side; the neck solve reaches every bite's height; `Down`; the title loops
  alternate.
- New PlayMode look test `Assets/Tests/PlayMode/ProbeTestsGripLook.cs` (real levels: 1, 4, 5, 6, 7, 10 for the humans,
  12 and 17 for the dog): shots to Build/shots/grip, logs of the hands' miss, the body gap, the neck bend.
- `ProbeTestsTitleChair.Step74b` renamed `Step74b_TitleChairHopsAndTheDogOrAHumanBringsItBack` and rewritten for the two
  loops (continuity over both, the chair comes home only in the dog's bite or the human's hands, the pair on the chair,
  the human's margins and frame), shots `title_chair_dog_*`, `title_chair_human_*`, close crops.
- mutation.sh: new row `grip_stool_low`. Every existing marker kept.

## Unity runs

- Static check first (no Unity, the lock was held for hours by LEVELS6 and HUMANAUDIT): the four assemblies (Core,
  Runtime, EditMode tests, PlayMode tests) compiled with the .NET 9 Roslyn compiler against the Unity 6.3 managed DLLs and
  the project's csproj references: 0 errors. A first SetupAndCompile through tools/unity.ps1 waited on the lock and was
  stopped; no Unity run spent.
1. `test . --mode PlayMode --filter GripLook_|Step74b_` (TestResults/grip1.xml, compiled every assembly, 0 error):
   - `GripLook_DogBitesTheStoolAndTheChairLow` passed. Level 12 stool: grip neck 66 deg (the stool still on the floor,
     the dog 0.20 m forward), drag neck 43 deg, hold back 0.15 m, sideways 0.07 m, bite point 0.37 m over the floor.
     Level 17 chair: drag neck 48 deg, hold back 0.22 m, sideways 0.21 m. Looked at (Build/shots/grip/dog_*): the head
     lowered and rolled, the open mouth round the stool's near leg below the seat; on the chair, round the back left
     leg below the seat. No longer at the seat's top.
   - `GripLook_HumansCarry...` failed on the test, not the game: the hands' "miss" (0.4 to 0.9 m) was read from a
     coroutine, after the rig's Update put the driven bones back to rest; level 1 found no free spot (0.7 m clearance);
     level 7 was measured during the put down. The shots (front and back cameras) show the hands ON the armchair's
     backrest top, the stool seat's sides (body leaning, the seat clear of the belly), round the lamp's pole, on the
     rocking chair's post tops, each body a forearm behind. The side cameras stood behind walls (rooms are small).
   - Step74b failed: "the title logo was never baked": the bake (12 targets now) outlasted the test's 300 frame wait. Its
     logs: the human 0.996 m tall (expected 1.038), hands on the rail 0.000 and 0.072 m from their targets; the title dog's
     neck 27.5 deg, snout at 0.300 m. The choreography half of the test (both loops, sampled) passed its checks.
   - Fixes (tests only): measured in a RigWatcher LateUpdate, spots up to 2.6 m with 0.5 m clearance, a 0.35 s settle,
     closer side cameras; the title test waits up to 30 s of real time for the bake.
2. `test . --mode PlayMode --filter GripLook_HumansCarry|Step74b_` (TestResults/grip2.xml):
   - Step74b PASSED. Chair between y 351.7 and 479.2 (unchanged), dog 357.0 to 412.3, human 352.7 to 475.0 (glyphs top
     346.7, phone top 483: 8 units of margin), the opaque human between x -717.4 and -531.4 inside the frame (-722.4 to
     -468.4). Looked at `title_chair_dog_close.png` (the dog's lowered head biting the chair's left back leg, under the
     seat) and `title_chair_human_close.png` (the man behind the chair, both hands on the top rail of the backrest,
     leaning into the pull), `title_chair_human_walkin_close.png`, the loop sheet: nothing clipped, clear of the letters.
   - Humans: hands 0.014 to 0.018 m from their targets on the stool, armchair, floor lamp, office chair and rocking
     chair; the near face of the furniture 0.22 (lamp, stool) to 0.40 m ahead of the spine; bodies exactly at their
     grip distance. Level 1 still found no free spot (its room is small): widened the search (all turns, 0.35 m clearance).
3. `--filter GripLook_HumansCarry` (grip3.xml): the widened search put the furniture where the humans of levels 1 and 7
   did not see it (no carry); level 10 again 0.014 m. Reverted the search; level 1 now uses Step24's known setup (the man
   at the window, the chair at -3.2, -0.8).
4. --filter GripLook_HumansCarry (grip4.xml): PASSED. Hands 0.014 to 0.018 m from their targets on all six bodies;
   level 1 chair: the body 0.557 m behind the chair's centre (0.11 m behind the rule position), the backrest 0.33 m ahead
   of the spine. Looked at human_chair_side.png: both hands resting on the top rail, forearms over it, the torso clear
   of the backrest; the stool held by its seat's sides, body leaning; armchair, office and rocking chairs by the top of
   the backrest; the lamp by its pole, right hand higher.

4 of 4 Unity runs used. Not run: GripTests (EditMode, statically compiled), ProbeTestsM3Rig Step24, ProbeTestsDogLook,
ProbeTestsM5Game Step38h_/38i_, mutation row grip_stool_low.

## A VERIFIER

1. Run GripTests (EditMode), ProbeTestsM3Rig Step24 (carry hands: now 0.32 m or more ahead of the stepped back visual),
   ProbeTestsDogLook, ProbeTestsM5Game Step38h_/38i_, then ./mutation.sh grip_stool_low.
2. Feel in play: the human's step back (0.11 m on the chair) slides in with the carry (0.25 s) and out after the put down;
   the elbows on the armchair, whose top is near shoulder height (hands raised).
3. The dog's lowered head while it walks: the neck bend is solved on the Idle chain (drag 43 to 48 deg); the walk clip's
   bob moves the snout a few cm. At the grip (stool still on the floor) the bend reaches 66 deg and the dog steps 0.20 m
   forward: check the neck mesh there.
4. The dog's sideways step onto a leg (stool 0.07 m, chair 0.21 m), most visible when the furniture is turned at the pin.
5. Title: the human at 0.6 of his size (1.0 m) reads small next to the chair; his hands rest above shoulder height on
   the 0.9 m rail. TitleLogoFrameWidth 2.6 (chair 12 % smaller) would allow about 0.68. Human top 475.0 (limit 481).
6. Title human's left hand ends 0.072 m from its target (the right one 0.000): the rail's far part is at the arm's reach;
   TitleLogoHumanReach 0.27 or TitleLogoHumanLeftX 0.06 would close it.
7. Ramps (levels 17, 23, 24): the hands and the snout follow the furniture's interpolated base, not its slope tilt.
8. The title bake renders 14 targets now (was 6): check the title page's first appearance time on Android.