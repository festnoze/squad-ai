# Metal (Metal009) - M7 texture pass

What I saw: in 08_level6 (lamp), 09_level7 (office chairs) and 11_level9 (robot) the metal parts read as
flat, slightly glossy grey/red with almost no relief. The detail PNG itself has good brushed-streak
contrast (mean 0.94, std 0.06), but the source ambientCG NormalGL for Metal009 is nearly flat (xy std only
~0.005/0.012 out of 1.0: real brushed metal is optically flat, its look comes from specular anisotropy more
than geometry), so even the existing 2x `_BumpScale` barely moved it, which is why the robot body and the
lamp pole showed no catch-light relief at play distance.

What I changed:
- Re-derived `normal_metal_Metal009.png` with a copy of `derive_m7.py` (`tex_metal/derive_metal_gain.py`)
  that applies a 3x gain on the source NormalGL's xy before the wrap-around resize and renormalize (same
  tiling method, no shape change). New xy std ~0.013/0.036, z stays high (min 0.99): more visible streaks,
  still flat enough not to read as noise.
- `NormalScaleMetal`: 2.0 -> 1.5 (Core/Tuning.cs), since the source itself is now stronger; combined relief
  is roughly 2x the old 2.0x1.0 baseline rather than 6x, to stay short of noisy on the robot's body (the
  largest metal surface).
- Left `DetailTileMetal` (0.3 m), `MetalSmoothness` (0.5) and `MetalMetallic` (0.9) unchanged: the grain
  scale and finish already read fine on the thin chair legs and lamp pole.

Next shots: check 11_level9 (robot body, largest flat metal area) for any noise creeping in, and
08_level6 / 09_level7 for whether the brushed streaks now catch a visible highlight on the lamp pole and
chair frames without looking busy.
