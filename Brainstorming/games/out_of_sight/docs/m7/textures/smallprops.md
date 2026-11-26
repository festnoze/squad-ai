# smallprops (Plastic006, Moss002, Ground104)

What I saw: in the raw detail PNGs and in the level shots (11_level9, 13_level11, 17_level15),
the robot bumper, potted-plant leaves and soil discs are all small props (leaf sprigs 2.6 cm wide,
foliage balls 7-14 cm, soil discs 9-23 cm). `DetailTileFoliage` (0.35 m) and `DetailTileSoil`
(0.25 m) were bigger than the props themselves, so each one showed well under one texture repeat:
a flat tinted blob with no visible moss crack or soil grain, even though the source PNGs do carry
grain. The plastic bumper is a long curved strip (about 59 cm around at `DetailTilePlastic` 0.2 m,
so ~3 repeats along its length) and already reads fine, so I left it and the three smoothness
values (Plastic 0.55, Foliage 0.25, Soil 0.08) unchanged; they already fit a semi-gloss plastic,
a matte leaf and a matte dirt.

Changed in `Core/Tuning.cs`: `DetailTileFoliage` 0.35 -> 0.08, `DetailTileSoil` 0.25 -> 0.09. This
puts 2-3 repeats across a leaf/foliage ball and across the soil discs, so Moss002's crack pattern
and Ground104's grit read as fine grain instead of a flat gradient, without raising per-texel
contrast (kept calm, no PNG changes needed).

Next shots: look at the potted plant leaves and soil on any level with the vase/plant load clue
(13_level11 and any level with a knocked-over plant) for a mottled green/brown instead of a flat
tint, and at a robot close-up to confirm the bumper still reads as calm, not noisy.
