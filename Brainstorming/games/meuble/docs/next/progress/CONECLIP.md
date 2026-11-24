# CONECLIP - the floor cone ignored low covers (level4 salon buffet)

## Report

Level 4, salon: the inhabitant seated on the sofa (eye 1.15 m) looks toward the buffet (counter, 0.9 m, occluder). The
stool (top samples at 0.52 m) hidden behind the buffet is not seen by the vision test, yet the drawn fan runs over the
buffet and on to the stool and the wall behind it.

## Cause

Not a gameplay bug, and not a collider or layer problem: the buffet is on the Occluder layer and both the vision test and
the fan raycast against the same `Layers.OccluderMask` colliders. The mismatch is in how the fan picks its sight line.

- Vision (`Vision.Test`): one ray from the eye to each of the 5 sample points of the furniture (4 top corners at
  `size.y - SampleInset`, the centre at half height). A top 0.5 m behind the buffet lies on a steep line that the 0.9 m
  buffet stops.
- Fan (`VisionConeView.RayReach`): ONE ray per fan direction, aimed at the furniture top at the FAR end of the range
  (10 m). That line descends slowly (1.15 m to 0.52 m over 10 m), passes ABOVE the 0.9 m buffet (about 1.0 m there), and
  is only stopped by the wall behind. The fan was then filled from the eye up to the wall. Every nearer top lies on a
  steeper line that the buffet blocks: the whole strip between the buffet and the wall is safe but drawn as watched.
- The class comment claimed "a prop lower than the furniture never shortens the fan" and "every nearer top lies on a
  lower sight line": true, but it only proves that what lies BEYOND the first hit is hidden. It never checked the part
  between a low cover and that hit. A cover is "low" here when it is higher than the furniture top but lower than the
  eye: it hides a shadow behind it of planar length far x (eye - top) / (eye - cover).

## Fix (presentation only, gameplay unchanged)

`VisionConeView.ShadowReach` (flat floors, eye above the furniture top, i.e. humans):

1. one horizontal cast at the furniture top's height along the ray finds every occluder higher than the top (near face);
   one cast back finds its far face; covers whose collider does not stand on the floor are ignored (what is under a
   lintel or shelf may be seen);
2. the shadow of each cover is [near, far x (eye - top) / (eye - cover) - TargetRadius] (to the end of the ray when the
   cover reaches the eye); `TargetRadius` (new, `LevelBuilder.ConeTargetRadius`) is the planar half diagonal of the
   top samples, so a furniture whose far corner pokes out of the shadow stays under the fan;
   each claimed shadow is then checked with two true sight lines (`Vision.Occluded`, the vision test's own raycast) at its middle and its end; a cover that fails (not an upright box, grazing hit) casts no shadow;
3. a shadow that runs to the end of the ray cuts the ray at the cover's near face (the outline and the rim line follow);
4. a shadow in the middle of a ray (the ray goes on through a doorway and sees again further) is cut out of the fill:
   the fan switches to radial samples (every `Tuning.ConeRadialStep`) and marks hidden samples in UV2.x; the shader
   (`Assets/Settings/VisionCone.shader`, both the fill and the x-ray hatching) multiplies its alpha by `1 - UV2.x`. A
   sample is cut only when its neighbours along the ray and on both side rays are hidden too, so the interpolated fade
   stays inside the shadow.

The fan stays a superset of what the vision test sees (it may still warn about a safe spot, never hide a watched one).
`VisionConeView.ClipShadows` (static, default true) exists only for the look tool's before/after.

Files: `Assets/Scripts/Runtime/VisionConeView.cs`, `Assets/Settings/VisionCone.shader`,
`Assets/Scripts/Runtime/LevelBuilder.cs` (TargetRadius), `Assets/Editor/ConeClipShots.cs` (look tool + audit).

## Shots

`-executeMethod OutOfSight.Editor.ConeClipShots.Shoot` writes `Build/shots/coneclip/salon_orbit_{before,after}.png` and
`salon_above_{before,after}.png`, and logs the per-level audit.

## Results (2 Unity runs, no test run)

- level4, eye 1.15 m on the sofa, stool at (-0.4, -1.05) behind the buffet: vision test `seen False, samples 00000`.
  Rays 23 to 28 drop from 3.3-5.2 m (wall or door) to 2.4-2.9 m (the buffet's near face). The strip behind the buffet and
  the wedge through the salon door are no longer drawn.
- Audit (every flat level, every human station, 72 directions): the same mismatch exists, mostly small, behind
  level2 Shoes, level3 Sideboard, level4 Buffet and Table, level9 MeubleChaussures, level11 Coiffeuse, level12 Plan,
  TableCuisine, Television, level18 Plan and Buffet, level19 EtagereMaman, MeubleTV, Cuisiniere, Evier, TableCuisine,
  level22 Comptoir, Console5, TableSalon, Lit, level24 Evier. Largest cuts: level4 station 0 (2.9 m), level18 (1.7 m),
  level12 and level19 (about 1 m). All fixed by the same code (no level data change).

## A VERIFIER

- Run the cone and vision tests (filters in the final report): the flat-level `Radial == 1` assertion of
  Step37w holds only while no ray has a middle shadow (the fan goes radial when one appears).
- In game, level 4 salon: the fan stops at the buffet; through the salon door the strip behind the buffet is clear.
- Non-flat levels (14, 17, 21, 23, 24): not clipped (old fan, a superset).
- The dog (eye under the furniture top) is unchanged (M5B m20 rule).
- A shadow's side edges: the fan's 40 rays are 2.8 degrees apart; a furniture right at a cover's side may show a corner.
