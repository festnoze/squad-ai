# Linen (Fabric036)

What I saw: on 08_level6 and 21_alert the bed mattress (cream, ~1.4 m wide) shows the
weave fine but legible, three to four repeats, not noisy. On the lamp shade (red,
~0.3 m, curved, one repeat or less of the tile) the fine threads mip away at play
distance and all that is left is a flat, blotchy cone with almost no relief catching
the light, which wastes the normal map on the one object where the stylized look
should read best (small, lit from above, close to camera in several shots).

What I changed: `NormalScaleLinen` 0.6 -> 0.85 in Core/Tuning.cs. Left
`DetailTileLinen` at 0.45 (3-4 repeats on a bed, under 1 repeat on clothes/lampshade):
the grain on the mattress already read well at that scale, no sign of moire or of the
Step22d noise cap being threatened, so only the amplitude needed raising, not the
frequency. Did not touch the source PNGs: Fabric036's own grain and contrast were
fine, the problem was amplitude at distance, not the source.

What to check in the next shots: the lamp shade in 08_level6/18_level16 should now
show a faint directional sheen instead of a flat blotch, and the beds in 21_alert/
08_level6 should keep their calm, readable weave (not turn noisy). If the lampshade
still looks flat, the next step is less tiling (lower DetailTileLinen) rather than more
normal scale, since the object may be too small for the current repeat to carry any
mid-frequency detail through the mip chain at all.
