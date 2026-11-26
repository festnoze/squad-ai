# Grass (ambientCG Grass001)

What I saw: in 01_start.png the lawn fills a large part of the frame at play distance and, zoomed in,
read as fine salt-and-pepper noise rather than readable grain; the broader light/dark blotches (the
actual "grass" read) were fine, but a layer of per-texel speckle sat on top of them. 06_level4 and
20_level18 show little to no grass, so they did not change my read.

What I changed: softened `Assets/ThirdParty/Textures/ambientCG/detail_grass_Grass001.png` in place with
a periodic (wrap-around, still tiles) Gaussian blur, sigma 1.6px, then re-centred the mean back to
240/255 and kept the same darkest texel (0.706). Stats went from mean 0.941 / std 0.058 (min 0.706,
max 1.0) to mean 0.941 / std 0.035 (min 0.718, max 0.9999): same overall brightness and range, about
40% less high-frequency variance, so the fine noise is gone but the blotchy grain still reads.

Left unchanged: `DetailTileGrass` (2.0 m/repeat, same order as Plaster's walls, reads fine at lawn
scale), `NormalScaleGrass` (0.6, already modest, in line with Carpet/Linen), `GrassSmoothness` (0.2,
matte). No LICENSES.md change (same source material, not re-cropped, no new material).

Next: re-check 01_start.png (lawn fills ~40% of frame) for calm grain without noise at play distance,
and any other exterior shot with a visible garden, to confirm the blotches still read as grass and not
as a flat wash.
