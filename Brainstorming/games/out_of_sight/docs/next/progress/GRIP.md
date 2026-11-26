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

## TITLESCALE (2026-11-23): the title's dog and human 1.5 times bigger

Product owner: the dog and the human of the title loops 1.5 times bigger. `TitleLogoDogScale` 0.8 -> 1.2,
`TitleLogoHumanScale` 0.6 -> 0.9. The chair's size and place on screen, the letters and the menu are unchanged.

- The fit. At 0.9 the man (1.49 m) is taller than the room between the title's letters (glyph top 346.7) and the top
  of a 20:9 phone (483): his head reaches 525.3. Lowering him would put his feet on the letters, and the chair cannot
  move. So the logo's frame grows upward to 540, the top of a 16:9 screen, where he shows whole (15 units of margin).
  On a 20:9 phone the screen's own top edge crops his top 42 units (head and shoulders, 27 % of his height): a straight
  cut at the screen's border, which reads as a close camera, never a cut inside the picture. The frame's own top is
  never reached (test: his top under the frame's, and under 538).
- The frame (same 110.4 units per metre, the chair's foot still at x 221.6, y 368): `TitleLogoWidth` x `Height` 438 x
  290 -> 533 x 388 pixels, `TitleLogoFrameWidth` 2.3 -> 2.8 m, `TitleLogoChairInset` 1.02 -> 1.52 (0.5 m more floor on
  the left for the dog's rump and the man's back while they hold the chair), `TitleLogoFootHeight` 0.315 -> 0.2352 (the
  same 91 pixels), UI 254 x 168 at 109, 399 -> 309.2 x 225 at 53.8, 427.5 (bottom still at 315).
- The dog: `TitleLogoDogGrip` -0.67 -> -0.808, so its lowered snout lands on the same spot of the chair's left back leg
  as the 0.8 dog's (0.274 m left of the chair's foot, 0.300 m up; neck 52 deg, was 27.5). Stride 0.29 -> 0.435, bob
  0.01 -> 0.015, the release step 0.05 -> 0.075.
- The human: `TitleLogoHumanReach` 0.30 -> 0.32 (the 0.6 man reached up to a rail above his shoulders, his left hand
  0.072 m short; at 0.9 the rail is 0.29 m under his 1.22 m shoulders): both hands exactly on their rail targets (0.000
  m), the elbows bent, the backrest a hand ahead of the belly. Bob 0.006 -> 0.009, release step 0.06 -> 0.09, the pull's
  short steps 0.1 -> 0.15 m. His walk frames swap every half of his (scaled) stride.
- The fade at the frame's left edge, `TitleLogoDogFade` 0.35 -> 0.55 (both carriers): the bigger pictures reach about
  0.49 m behind their feet, so they turn opaque only once wholly inside the frame. Checked offline first (a Python copy
  of `Sample` and the test's choreography checks, scratchpad sim2.py), which reproduced both failures below: 0.35 left
  the human 0.1 % visible at the loop's end (his walk out is 0.5 m longer in the same time), and with a 0.3 m wider
  frame a 0.55 fade left the dog not quite opaque where it backs off the chair.
- The bake: 20 render targets of 1066 x 776 (was 876 x 580), about 1.6 times the memory for the bake's few frames.

Unity runs (4, `--filter Step74b`, TestResults/titlescale.xml, shots in Build/shots/grip):
1. Failed: the human's alpha 0.001 at the loop's end (fade 0.35, frame 2.6 m). Fade raised.
2. Failed: the dog not opaque while it backs off (fade 0.55, frame 2.6 m). Frame 2.7 m, fade 0.45.
3. Failed: the opaque dog 2.6 units past the frame's left edge (its rump), and the log measured its snout 0.018 m right
   of the old spot. Frame 2.8 m, dog grip -0.808, fade 0.55 (simulated first).
4. PASSED. Chair 351.8 to 479.3 (unchanged); dog 351.8 to 434.1, opaque from x -771.7 (frame -777.6); human 352.7 to
   525.3, opaque from -766.1; frame top 540. Looked at: `title_chair_dog_close.png` (the big dog's lowered head round
   the back left leg under the seat), `title_chair_human_close.png` (both hands on the top rail, leaning into the
   pull), the loop sheet (walk in, grab, pull, release, walk out, both loops), `title_chair_human_1920x1080.png` (whole,
   head just under the top) and `title_chair_human_2400x1080.png` (cut at the chest by the phone's top edge).

Not run: Step74a (the pool's checks: its edge fades inside the larger frame, its soft share threshold scales with the
frame's area), GripTests (EditMode: no title value checked beyond the alternation, unchanged).

## TITLEMOVE (2026-11-23): the chair goes twice as far, the carriers pull it home twice as fast

Product owner: the chair's hops to the right cover twice the distance; the dog and the human pull it back at twice
their speed (so in about the same time), their walk matching the speed, the bite and the hands locked on the chair.

- The hops: `TitleLogoChairHopStride` 0.13 -> 0.26 m, still 3 hops at the same pitch (0.75 s) and height (0.045 m):
  the chair ends 0.78 m right of its mark (was 0.39), 86.5 units on screen (was 44.3).
- The frame: unchanged. At 0.78 m the chair's right edge (its layer, margins included) stays 19.6 units inside the
  frame's right edge (-488.0 against -468.4 in the test's canvas), the pair (human and chair) likewise; the chair never
  gets lower than its line (bottom 351.8, letters 346.7) nor higher (top 479.3, the startle, phone top 483). Only
  sideways motion changed, so phone 20:9 and PC 16:9 fit as before (shots below).
- The pull: same window (DragStart 6.30 s to DragEnd 9.10 s, a smoothstep) over twice the floor, so twice the speed:
  peak 0.418 m/s (was 0.209), 2.80 s per loop (both measured by the test).
- The walks: frames swap by the floor covered, so the steps keep pace with any speed. The dog's drag frames swap every
  half of its real stride (0.2175 m): its steps come twice as quick. The human's pull steps (`HumanPullStep`) 0.15 ->
  0.21 m: 1.4 times longer and 1.4 times quicker (the square root of 2 each, as a person speeds up), 3.7 swaps over
  the pull (was 2.6).
- Locked on the chair: the human holds it through the pair's picture, drawn exactly over the chair's layer (unchanged).
  The dog's picture used to bob with its walk while the chair had its tug lift, so its snout moved a few units on the
  leg (worse at twice the cadence): during the drag its picture now follows the chair's lift, blended in and out by
  the drag's envelope so the bob never jumps (test: mid drag, DogHop equals Hop).
- Timing kept: spot away, hops, the light back (3.10 to 3.80 s), the startle, the walk in and out, the release, the
  15 s hold, the alternation. Two adjustments for the longer way, both checked first in a Python copy of `Sample`
  (scratchpad sim.py): the spot's way back is now 1.23 m, and its cubic ease in would land at 5.3 m/s (0.0226 m per
  test sample, over the 0.02 continuity limit), so it is a square (3.5 m/s, the cube's old 3.6); and the walk in now
  starts at 4.45 s (was 4.70) so the dog and the human cover the longer way at about their old speed (peaks 1.54 and
  1.81 m/s, were 1.38 and 1.74; without the change 1.86 and 2.18).
- Test `Step74b`: the chair 0.78 m away (+-0.005), the pull's peak 2 x 0.209 m/s (+-0.02), its length 2.8 s (+-0.1),
  the chair's right edge inside the frame's, the dog's bob in the continuity check, the bite locked mid drag.

Unity runs (2, `--filter Step74b|MenuCam_`, shots in Build/shots/grip and Build/shots/menucam):
1. TestResults/titlemove.xml: both PASSED (the bite lock not yet in). Farthest 0.780 m, pull peak 0.418 m/s over 2.80
   s per loop, largest step 0.0151 m (limit 0.02), light 0.0138; chair 351.8 to 479.3, travels 86.5 units, right edge
   19.6 units inside the frame; dog opaque from -771.7 to -551.1, human -766.6 to -488.4 (frame -777.6 to -468.4).
   Looked at: the loop sheet (hops in the dark well to the right, the light lands on it, the dog and the man bring it
   home, both loops), `title_chair_away_2400x1080.png` (the phone: the chair in the dark at the right of its frame,
   above "Out of", nothing cut), `title_chair_dog_close.png` (the lowered head on the back left leg),
   `title_chair_human_close.png` (both hands on the top rail). The dog's walk bob against the chair's lift seen in the
   numbers (frame 8: chair lift 0.012, dog bob 0.015): fixed as above.
2. TestResults/titlemove2.xml: both PASSED with the bite lock (frame 8: lift 0.012, bob 0.012; frame 9: 0.018, 0.018);
   every other number unchanged. MenuCam_a at the coordinator's 0.55 m / 4 deg: closest 0.40 m (limit 0.25, at
   (4.45, 0.55, 3.25), the bureau-salon doorway, as before), 0 of 10080 rays outside; its sheets show no clipping.

Builds: Windows `Build/Play/OutOfSight.exe` (Build/pc.log, no game process was running) and Android
`Build/Android/OutOfSight.apk` (55.7 MB, Build/apk.log), both succeeded.

Not run: GripTests (EditMode; its title check compares the two loops before TrotStart, which moved earlier: still the
same hops and light in both loops), Step74a (pool only, unchanged).

## TITLEMOVE2 (2026-11-24): the chair twice as far again, and the carriers turn round instead of flipping

Product owner: the chair's move to the right twice as long again (TITLEMOVE's 0.78 m to about 1.56 m), the carriers'
pull at TITLEMOVE's speed; and the dog's turn after it lets go (an instant mirror of its picture) made a natural turn,
the human's too.

The move (TitleLogo.Sample, Tuning):
- The hops: 4 of 0.39 m (`TitleLogoChairHops` 3 -> 4, `TitleLogoChairHopStride` 0.26 -> 0.39), same pitch (0.75 s),
  a little higher (`TitleLogoChairHopHeight` 0.045 -> 0.05; the startle, 0.065, stays the highest jump): the chair ends
  1.560 m right of its mark, 172.6 units on screen. Three hops of 0.52 m under the same low lift would read as a skid.
- The frame grows 0.75 m on the RIGHT, as TITLESCALE grew it on the left (its left edge, the chair's foot, the height,
  the scale and so the chair, the letters and the menu unchanged): `TitleLogoFrameWidth` 2.8 -> 3.55 m,
  `TitleLogoWidth` 533 -> 676 pixels, `TitleLogoUiWidth` 309.2 -> 392 (110.4 units per metre kept). The chair's right
  edge at its farthest is 16.4 units inside the frame's (-402.0 against -385.6). Nothing changes vertically: the chair
  between y 351.8 and 479.3 (letters 346.7, phone top 483) as before; on a 20:9 phone it ends above "of", clear of the
  letters and of the buttons below the title.
- The timeline (act 11 -> 16.2 s, `TitleLogoCycleSeconds` 26 -> 31.2, still 15 s, `TitleLogoStartPhase` 12.5/31.2):
  hops end at 3.45 s (the fourth adds 0.75 s); the spot's way back (now 2.01 m) 3.85 to 4.85 s (1.0 s, was 0.7: the
  square ease would land at 5.7 m/s, over the per sample limit; now 4.0 m/s); startle 5.00 to 5.40; walk in 5.50 to
  7.60 (2.1 s, was 1.45: peaks 1.62 m/s for the dog, 1.81 for the human, as before); grab to 8.00; the pull 8.00 to 13.60
  (5.6 s, was 2.8, at the same peak 0.418 m/s); release to 13.90; wag (the human stands) to 14.50; the turn round to
  15.20 (new, 0.7 s); walk out to 16.2. Checked first in a Python copy of `Sample` (scratchpad sim3.py).
- The test's sample step is now fixed at 26/6000 s (it was 12000 samples over two loops of 26 s), so its per sample
  limits stay the same speeds with the longer loop.

The turn (TitleLogo, bake and runtime):
- Each carrier has baked frames facing LEFT now (walk 4 and 5, yaw 360 - its right yaw: 250 for the dog, 275 for the
  human), rendered and lit for real, and turn frames between: 6 for the dog (110 to 250 degrees, 20 apart), 7 for the
  human (85 to 275, 23.75 apart), the yaw passing through 180 (facing the camera). The pictures are never mirrored any
  more (the layers' scale stays 1); `Pose.DogTurn` / `HumanTurn` go 0 to 1 (a smoothstep) over the 0.7 s and
  `FrameOf` picks the nearest baked frame.
- Each turn frame, from the real model: the walk clip stepped on through one cycle from the frame the carrier stands on
  (`DogStandFrame`, `HumanStandFrame`, so the steps start and end on its legs), blended toward the Idle pose to
  `TitleLogoTurnStride` 0.45 of the stride at the middle (short steps on the spot, not a walk in place); the body arcs
  with `sin(pi s)`: the dog's spine (Torso, Torso2, Torso3) bends `TitleLogoDogTurnBend` 36 degrees toward the turn, its
  neck 24 more (`TitleLogoDogTurnHead`), the hips lagging half the bend behind the frame's yaw; the human's spine 26, his
  head 18. So the head leads and the rump follows. The ears hang in the head's frame, the tail in the hips'. Every bone
  is put back to its rest before each frame (a `PoseSnapshot`), so no frame inherits another's pose.
- Facing the camera, a body reaches further toward it, so lower on screen: each frame facing left or turning steps back
  into the depth just enough that its lowest point never shows below the walking frames' (measured on the baked
  vertices). Logged: the dog 0.015 m facing left, 0 to 0.183 m through the turn; the human 0.057 m facing left, 0 to
  0.143 m through the turn (his top rises to 534.8, limit 538). It reads as a small step back into the room while turning.
- The bake: 52 body crops now (25 frames and their shadows, 2 pairs). Rendering them all at once would have needed 54
  targets of 1352 x 776 (about 450 MB), so the bodies render 4 frames at a time into a pool of targets (12 targets in
  all, about 100 MB, fewer than the 20 before), are read back, then cropped on worker threads while the next 4 render;
  only the crops are kept. The atlas shelves grow to 2048 wide. A body with a missing crop is left out whole.

Tests (`ProbeTestsTitleChair.Step74b`): the chair 1.56 m away (+-0.005), the pull's peak 2 x 0.209 m/s (+-0.02), its
length 5.6 s (+-0.1), the act 15 to 17.5 s; per sample: the turn's step under 0.03; the carrier turns fully shown,
neither moving, biting nor holding, and faces left only once turned; on screen, the dog's and the human's layers never
mirrored (scale 1 at every step of both acts); through the turn, pinned 400 times, the yaw of the frame shown never goes
back, never jumps more than 30 degrees, ends at the mirror yaw and shows every turn frame. New shots: the turn strips
`title_chair_dog_turn_strip.png`, `title_chair_human_turn_strip.png` (each turn frame, plus before and after) and the
doubled middle frames `title_chair_dog_turn_mid.png`, `title_chair_human_turn_mid.png`.

Unity runs (`--filter Step74|MenuCam_`, TestResults/titlemove3.xml; shots written to Build/shots/titlechair, copied to
Build/shots/grip):
1. Did not compile: the test declared a local `right` inside a loop under the method's own `right` (CS0136; the .NET 9
   Roslyn static check let it pass). Renamed.
2. PASSED: Step74a, Step74b, MenuCam_a. Farthest 1.560 m, largest step 0.0173 m (limit 0.02), light 0.0138, pull peak
   0.418 m/s over 5.60 s, turn step 0.0093; chair 351.8 to 479.3, travels 172.6 units, right edge 16.4 inside the frame;
   dog 351.9 to 437.1, opaque from -777.3 to -465.0; human 352.7 to 534.8, opaque from -764.8 to -402.4 (frame -777.6 to
   -385.6, top 540); the dog turns 110 to 250 through 8 yaws (at most 20 degrees a frame), the human 85 to 275 through
   9 (23.8). Pool (Step74a): drawn top 471. Looked at: the turn strips (the dog swings its head round toward the camera,
   the body following, short steps, then walks off facing left; the man turns his head and chest first, faces the
   camera, then walks off), the loop sheet (4 hops in the dark to above "of", the light lands, dog and man bring it home,
   turn, leave), `title_chair_away_2400x1080.png` (the phone: the chair at its farthest above "of", nothing cut).

2 of 4 Unity runs used. Not run: GripTests (EditMode; its title check uses TrotStart and the alternation, unchanged in
meaning).

A VERIFIER
1. The dog's middle turn frames (facing the camera): the spine bend and the short steps give a hunched, foreshortened
   dog with its front legs apart; if it reads odd, lower `TitleLogoDogTurnBend` (36) or raise `TitleLogoTurnStride`.
2. The 0.18 m step back into the depth mid turn (the dog) shows as a small rise of the picture, then back down.
3. The bake renders 25 body frames now (was 14), in 7 rounds of 4: check the title page's first appearance time on
   Android.
