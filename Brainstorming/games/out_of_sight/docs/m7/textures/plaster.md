# Plaster (ambientCG Plaster001) - walls, wall caps, vase, pot

What I saw: in 01_start, 16_level14 and 19_level17 the walls and the sloped wall caps render
completely flat, no plaster grain readable at all, even up close behind the bookshelf. Checked
`Assets/ThirdParty/Textures/ambientCG/detail_plaster_Plaster001.png`: its relative std was 0.0274,
far below every other material (wood 0.100, carpet 0.090, linen 0.080, upholstery 0.140) - the
contrast was simply below the floor of visibility at play distance, not a tiling or relief problem.

What I changed: boosted the contrast of `detail_plaster_Plaster001.png` only, re-applying the same
mean-preserving normalization as `tools/assets/derive_textures.py` (MEAN = 240/255, highlight capped
at 1.0, darkest = MEAN * 0.88), with a 1.55x gain on the deviation from MEAN. Old std = 0.0274, new
std = 0.0385 - still the calmest detail map of the six materials (well under carpet/linen/
upholstery/wood), to respect the Step22d wall-calm cap. Could not reach the raw ambientCG
`Plaster001_1K-JPG_Color.jpg` (not in `tools/assets/raw` nor the m7 scratch `raw` folder, only
NormalGL was there), so I edited the already-derived PNG directly instead of rerunning the full
pipeline; math is equivalent since plaster has no extra map and no rotation.

Left `Core/Tuning.cs` untouched: `DetailTilePlaster = 2.0f` (2 m per repeat already reads at a
sensible scale on walls/caps in the shots) and `NormalScalePlaster = 1.0f` (baseline; the normal map
already shows believable trowel strokes, the flatness was the detail map's contrast, not relief).

Next shots to check: 01_start, 16_level14, 19_level17 - walls and the sloped cap should now show a
faint cloudy plaster weave under the directional light, not noise, and should not trip Step22d. If
it still reads flat, the single knob is `GAIN` in my `boost_contrast.py` (currently 1.55). If Step22d
flags walls as too noisy, lower that gain. The vase and pot in 19_level17 are small against a 2 m
tile, so they mostly show a smooth local shade rather than visible weave - worth a look but probably
fine as-is.
