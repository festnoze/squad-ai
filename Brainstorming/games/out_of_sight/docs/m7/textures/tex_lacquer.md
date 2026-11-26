# tex_lacquer (PaintedWood006C, player furniture)

What I saw: in 01_start, 07_level5 and 20_level18 the red player furniture already reads as the clearest
thing in frame. A close crop of the armchair in 07_level5 shows readable vertical wood-grain streaks
through the red tint, at a tiling scale (DetailTileLacquer = 1.0 m/repeat) that gives 2-3 repeats across
the chair back, proportionate and not noisy. No blown-out white specular glints found in any crop
(channel max stayed red-dominant, e.g. R221/G150/B158).

What I checked: detail_lacquer_PaintedWood006C.png's contrast (mean 240, std 17.4) is in line with the
other shipped detail maps (parquet mean 240/std 12, metal mean 240/std 15.4), so the grain source itself
is not the problem and needed no re-derive. But normal_lacquer_PaintedWood006C.png has a low average
relief (xy deviation mean ~6 of 127) with a few sharp plank-seam spikes (max ~121), the highest spike of
any surface at the old baseline scale. Combined with LacquerSmoothness = 0.9 (a tight specular lobe), that
is a specular-noise risk on the one object the PRD requires to stay the clearest.

What I changed: Core/Tuning.cs, NormalScaleLacquer 1.0 -> 0.8 (one value, with a comment explaining why).
Left DetailTileLacquer (1.0) and LacquerSmoothness (0.9) untouched: both already look right in the crops.
Did not touch any PNG, any other surface's constants, or any .cs file besides Tuning.cs.

Next shots: re-check 07_level5 and 20_level18 up close for the armchair and stool, confirm the seam
highlights no longer pop as bright pinpoints under direct light, and that the grain is still visible (not
flattened) at play distance.
