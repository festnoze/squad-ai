# Carpet (ambientCG Carpet012)

What I saw: in 07_level5 and 13_level11 the blue rug reads as two flat colour bands (light
centre, dark border) with no visible pile or weave at all, even though the wood floor next to it
shows clear grain. The source detail/normal pair is very fine, high frequency pile noise with no
mid scale structure, so at play distance and the old tile size it was aliasing down to a flat wash
instead of reading as carpet.

What I changed in Core/Tuning.cs:
- `DetailTileCarpet`: 0.7 -> 1.1 (metres per repeat). A coarser world scale repeat means fewer
  texels per screen pixel at play distance, so the pile reads as grain instead of blurring flat.
  1.1 sits between Wood (1.0) and the old fabric scale fabrics (Upholstery 0.55, Linen 0.45),
  since a floor rug is viewed wider than a cushion.
- `NormalScaleCarpet`: 0.5 -> 0.75. The coarser tile above already lowers aliasing risk, so a
  slightly stronger bump (just above Upholstery/Linen's 0.6) can catch light on the pile without
  adding more screen noise than before.

Did not touch the PNGs: the grain itself is fine but coherent (real carpet pile has no macro
pattern), the problem was purely scale, not source quality.

Next shots to check: 07_level5 and 13_level11 (the blue rug under the armchair/table) for visible
pile texture and a highlight catching the weave without it reading as noisy static; also confirm
the rug still looks calmer than the player furniture in the same frame.
