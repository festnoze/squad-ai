# Upholstery (ambientCG Fabric011)

What I saw: in `07_level5` the red armchair (and blue sofa) already show a readable, calm
fiber grain at play distance, picked up nicely by the light on the backrest and seat edges;
no visible noise or tiling seam. The sofa's flatter look at a distance is lighting/angle
(indirect light, facing away from the key light), not a texture problem.

Source check: `detail_upholstery_Fabric011.png` has mean 240.0 (exactly `Tuning.DetailMean`)
and std 15.67, in the same band as the other furniture-grade fabrics (carpet 15.66, linen
14.77, wood 15.0) and well above the flatter plaster/tile/plastic textures. So the PNG itself
is not the problem; no re-derive needed.

Constants checked: `DetailTileUpholstery = 0.55f` (repeat every 0.55 m, sits between Linen
0.45 and Carpet 0.7, sensible for cushion/seat-sized surfaces) and `NormalScaleUpholstery =
0.6f` (same as Linen, below Wood/Lacquer at 1.0). Both already match sibling soft-fabric
surfaces and produced the good result seen on the armchair, so I made **no changes** (values
kept as-is: 0.55 / 0.6).

Next shots to check: look closer at the office chair seat and any cushions in `14_level12`
and `19_level17` to confirm the same grain reads well on smaller/flatter upholstered parts,
and that it still stays calm once floors/walls are back in frame (Step22d).
