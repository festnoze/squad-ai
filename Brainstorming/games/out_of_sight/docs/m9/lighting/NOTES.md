# Room lighting on Haut (2026-11-20)

Product owner request: on the "Haut" quality tier only, a more dynamic room lighting, with the corners at the floor and
at the ceiling less lit. Bas and Moyen (Mobile_RPAsset and Mobile_Renderer, the Android default is Moyen) are unchanged.

## How the tiers are wired

- QualitySettings: Bas and Moyen use `Mobile_RPAsset` (renderer `Mobile_Renderer`, Forward, no SSAO), Haut uses
  `PC_RPAsset` (renderer `PC_Renderer`, Forward+, soft shadows, MSAA 4, SSAO). Defaults: Android and iOS Moyen,
  everything else Haut (ProjectSetup.EnsureQualityLevels). QualityTier applies the choice at run time.
- So anything on `PC_Renderer` is Haut only by construction.

## Candidates tried (A/B shots of the same game camera views)

Look tool: PlayMode `ProbeTestsLightingShots.Lighting_z_Shots` (explicit), driven by `TestResults/lighting/config.txt`
(candidates as SSAO settings, ambient, sun and room light factors, title ceiling shade), so no recompilation per round.
Views: the start and two rooms of level4, level12 and level16 (and level21 in the final pass), four points of the
title tour. Four rounds, 29 candidates in all.

| Candidate | Result |
|---|---|
| SSAO as it was (0.6 intensity, 0.3 m radius, 0.25 direct) | barely visible: only a line under the furniture |
| Larger radius 0.9 to 1.2 m, intensity 1.5 to 1.8 | real depth from the high game camera, but black noisy blotches in corners and beside the fridge at the title's close eye level camera |
| SSAO after opaque | black halos round the furniture: rejected |
| Lower ambient (x0.85 to 0.9) and a brighter sun (x1.05 to 1.08) | more contrast but darker shadows everywhere (cones and inhabitants less readable), and the ambient is shared with the floor lamp's dimming (LampLight saves and restores it): rejected |
| Brighter secondary room lights (x1.4) | hardly visible next to the SSAO change: rejected |
| Gaussian blur | smoother but still grainy with blue noise |
| Interleaved gradient noise, 12 samples, radius 0.5 to 0.7 m | smooth at every distance: kept |
| Downsampled SSAO | same look, softer edges; not needed on the PC tier |
| Per-vertex AO in the wall and floor meshes | not built: a floor is one quad per room and a wall face one quad, so a junction gradient needs new vertex rows and a new vertex attribute in the room surface shader (edited at the same time for the floor dust); the SSAO already gives it on Haut, and the floor dust map adds grime along the walls |

## What ships

1. `PC_Renderer` SSAO (ProjectSetup.SsaoIntensity and the rest): intensity 1.6, radius 0.7 m, direct lighting
   strength 0.6, interleaved gradient noise, 12 samples, bilateral blur, full resolution, depth normals, in the
   lighting (not after opaque). Junctions, wall corners and furniture contact darken over a hand's breadth.
   About 12 depth samples per pixel plus the blur, full resolution, on the PC tier only.
2. Title house ceiling (TitleCameraTour, Haut only): the ceiling is unlit, so SSAO never shades it. On Haut its
   underside is a quad with a small linear shade texture (16 texels per metre, built once): in each room the product over
   its four wall faces of `1 - 0.45 * exp(-d / 0.4 m)`, so it darkens along the walls and more in the corners. Bas and
   Moyen keep the plain box. It follows the Qualite option at once (a string compare per frame).

Checks: EditMode `LightingHighTests` (the SSAO settings on PC_Renderer, none on Mobile_Renderer, the ceiling shade
profile), PlayMode `ProbeTestsLightingShots.Lighting_a_` (the ceiling shaded on Haut only, following the tier).
