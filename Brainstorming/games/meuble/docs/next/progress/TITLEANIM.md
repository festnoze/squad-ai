# TITLEANIM progress (title chair: face right, hops, caught, the dog drags it home)

## Requests (product owner, 2026-11-21, three rounds merged)
1. The title chair faces RIGHT (yaw in the logo frame), shadow inside the pool, fit unchanged.
2. Longer loop: the light slides away LEFT and dims, the chair hops RIGHT.
3. Round 2 (dog): after the hops, the house dog comes in from the LEFT and drags the chair back, as the in-game dog
   now does (docs/next/progress/DOGCARRY.md); it lets go, wags and leaves left. Baked once, 2 or 3 walk frames or a
   bob, no per-frame allocation, the dog inside the frame where visible, never over the title letters.
4. Round 3 (refinements): hops too strong (vibrating, deformed): fewer, smoother, gentle lift and soft landing, the
   chair keeps its shape. New order: the light comes back ON THE CHAIR where it stands, the chair gives ONE startled
   jump, THEN the dog drags it home; the chair ends in full light on its mark. Hold the still pose 15 s after.

## Final timings (26 s loop)
- Still: 15 s (TitleLogoStillFraction 15/26), the first act 2.5 s after the logo appears (StartPhase 12.5/26).
- Act, 11 s:
  - 0.00 to 0.70 s: the spot slides left (0.45 m) and dims to 0.12;
  - 0.60 to 2.70 s: 3 gentle hops right (0.13 m each, 0.045 m lift on a squared sine, eased stride, 0.6 s flight
    then 0.15 s on the floor), no squash, no tilt;
  - 3.10 to 3.80 s: the spot returns ONTO the chair where it stands (cubic ease in, accelerating, lands at full light);
  - 3.95 to 4.35 s: one startled jump (0.065 m, up in 0.1 s, down in 0.3 s), on the spot;
  - 4.70 to 5.90 s: the dog trots in from the frame's left edge (fading in over 0.35 m) to the chair's left edge;
  - 5.90 to 6.30 s: the grab (the chair jolts 1.5 deg toward the dog);
  - 6.30 to 9.10 s: the drag home: the dog walks backwards facing the chair, the chair lifted 0.02 m with a 1.5 deg
    tug wobble at 2.5 Hz (the in-game rate), the spot follows the chair (full light all the way);
  - 9.10 to 9.40 s: the dog lets go and backs off 0.05 m; 9.40 to 10.00 s: a wag (6 deg at 6 Hz);
  - 10.00 to 11.00 s: it turns round (picture mirrored about its own centre) and trots out left, fading at the edge.

## What changed
- `Assets/Scripts/Core/Tuning.cs` (TitleLogo block only): `TitleLogoChairYaw` 220 -> 140 (exact mirror, same outline
  height), `TitleLogoFillIntensity` 0.5; loop `TitleLogoCycleSeconds` 26, `TitleLogoStillFraction` 15/26,
  `TitleLogoStartPhase` 12.5/26; `TitleLogoChairHops` 3, `TitleLogoChairHopStride` 0.13, `TitleLogoChairHopHeight`
  0.045, `TitleLogoChairStartle` 0.065; `TitleLogoDragWobble` 1.5, `TitleLogoDragLift` 0.02; dog: `TitleLogoDogGrip`
  -0.62 (its body from the chair's foot when holding it on its mark), `TitleLogoDogYaw` 110, `TitleLogoDogStride` 0.24,
  `TitleLogoDogBob` 0.01, `TitleLogoDogFade` 0.35, `TitleLogoDogWag` 6, `TitleLogoDogShadow` 0.7. Removed the old
  `TitleLogoChairSteps/Step/Lean` and the short-lived `TitleLogoChairSquash`.
- `Assets/Scripts/Runtime/TitleLogo.cs`:
  - `Pose`: Chair, Lean, Light, Spot, Hop + Dog, DogAlpha, DogFacing, DogFrame, DogHop, DogWag (no squash any more).
    `DogEdge` const (where the hidden dog waits, = Rest). Timeline constants public (fractions of the act).
  - `Sample` rewritten for the order above; pure, exact Rest at both ends.
  - Bake: the Shiba (ModelKit, in-game size and tint) stands at the grip spot; its Walk clip is sampled at two foot
    contacts (DogFootContactCycle and half a cycle later) and each pose is baked (`SkinnedMeshRenderer.BakeMesh`) into a
    static copy. After the chair's pass, each copy is shown alone for one more chair-camera + shadow-camera render
    request (same frame, same light): 4 more targets, read back with the others. Compose crops 2 dog frames + 2 dog
    shadows into a third atlas row. Dog shadow: soft ink at full pool light; at runtime its alpha is the pool's light
    where the dog stands (`PoolLightAt`, the bake's own falloff, now shared). If the dog cannot be built or the
    pipeline has no render requests, the logo goes without it (warning) and the chair still comes home.
  - Layers: Shadow, DogShadow, Chair, Dog (dog in front: its head overlaps the chair's left leg). The dog layer swaps
    uv/size/pivot only when its frame changes; its pivot is its picture's centre so the turn round stays in place.
  - `Apply`: chair lift only (no scale writes), dog position/scale/rotation/colour; struct writes only.
  - Rim light mirrored to the chair's back side; soft fill light in front of the chair.
- `Assets/Tests/PlayMode/ProbeTestsTitleChair.cs`: Step74b renamed `Step74b_TitleChairHopsAndTheDogDragsItBack` and
  rewritten: still >= 14.95 s, act 8 to 13 s, start = end, continuity (positions < 0.02 m, light and dog fade < 0.03,
  tilt and wag < 3 deg per 1/6000 loop), exactly 3 hops in the dark and 1 startle in the light before the dog, the
  startle higher than the hops, the chair moves right only with light < 0.5 and comes home only from the dog's mouth
  in the full light with the spot on it, no tilt without the dog, the dog only after the light is back and opaque only
  inside the frame; on screen: chair y = rest + lift, shadow on the floor line, scale always 1, chair and dog under the
  20:9 top - 2 and above the glyphs + 2, the opaque dog inside the frame, light back on the chair when caught, light
  following during the drag, dog gone at the loop's end. Sheet of 16 frames + away (1920, 2400), caught (1920), dog
  (1920, 2400) under Build/shots/titlechair.
- Python check of `Sample` (scratchpad sim2.py): still 15.0 s, act 11.0 s, 3 hops + 1 startle, farthest 0.39 m, max
  position step 0.0154 m, light step 0.016, the chair only moves home from the dog's mouth.

## Unity runs
- Round 1: two launches refused before Unity opened (LEVELS6 editors held the project), then 1 compile
  (Build/TITLEANIM_compile.log): my files clean; the PlayMode assembly failed on other agents' files (ProbeTestsHudV2,
  ProbeTestsM5Bodies, ProbeTestsM7Touch).
- Round 2 (dog + refinements), lock free:
  - 1 compile (SetupAndCompile, Build/TITLEANIM_compile2.log): exit 0, no error, no warning in my files (the other
    agents' test files compile again).
  - PlayMode run 1 (`--filter ProbeTestsTitleChair`, TestResults/titleanim.xml): 2/2 passed, but the frames showed
    the dog as a 5 cm speck: `BakeMesh(mesh, true)` applied the model's 0.13 fit a second time.
  - Fix: `BakeMesh(mesh, false)`, plus a guard that rescales a baked pose to the catalog height and grounds its feet.
  - PlayMode run 2 (TestResults/titleanim2.xml): 2/2 passed. Logged: still 15.0 s, act 11.0 s, 3 hops up to 0.045 m,
    1 startle 0.065 m; chair between y 351.7 and 479.2 (glyphs 346.7, limit 481); dog between y 358.5 and 409.8,
    opaque inside the frame (x -712.9 to -599.9, frame -722.4 to -468.4); ShadowInPool 0.68. Looked at the sheet and
    the dog shots: chair faces right, gentle hops in the dark, light back on it, startle, the Shiba trots in, holds the
    chair's left leg through the drag with the light following, lets go, turns and fades out at the left edge.

## A VERIFIER
- Top margin on 20:9 is tight: the startle peaks at 479.2 against the test limit 481 (phone top 483). If the chair
  model grows again, lower `TitleLogoChairStartle` (0.055).
- Dog colour: the in-game tint #4F6670 makes the Shiba grey-blue (same as in game); the PO may prefer the natural fur.
- Feel at real speed (the PO): hop softness, startle height, drag pace (0.14 m/s average), wag, the 1 s exit.
- Fill light 0.5 on the chair at yaw 140 looks right in the shots; adjust only if the PO finds it flat.
