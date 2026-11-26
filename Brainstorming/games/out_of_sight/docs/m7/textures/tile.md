# Tile (Tiles049, kitchen and bathroom floors)

What I saw: none of the 11 levels with `"floorFinish": "tile"` (level3, 8-12, 14-18) have a
screenshot that actually frames the kitchen or bathroom; `TestResults/shots/` has one shot per
level taken at spawn, and spawn is always a bedroom/living room/dining room with a wood floor
(checked 7 shots: level3, 8, 9, 10, 11, 12, 15, 17). So I judged the source instead: pixel stats
of `detail_tile_Tiles049.png` (mean 0.941, std 0.0424, min 0.765) show it is already the calmest
floor detail of the three (Wood std 0.0588, Parquet std 0.0472), consistent with the "floors fill
the frame, keep them calm" rule, and `NormalScaleTile = 1.0f` already matches the documented
Wood/Parquet precedent (floor surfaces keep the modest scale even for their own grout/seams).

What I changed: only `DetailTileTile`, from `0.5f` to `0.6f` (Core/Tuning.cs). The Tiles049
source is a "crazy paving" mosaic with ~6 internal rows of irregular rectangles per repeat; at
0.5 m that is a lot of thin grout lines packed into a small kitchen/bathroom (level10's cuisine
is only 4.4 x 5.9 m), even though each line's contrast is low. Nudging the repeat to 0.6 m cuts
the line density by about a fifth while staying far smaller-scaled than Parquet's 1.8 m planks,
which fits small ceramic/mosaic tile better than a bigger repeat would.

Left unchanged: `TileSmoothness` (0.5, already commented as "glazed ceramic, smoother than
Parquet's 0.35") and `NormalScaleTile` (1.0, matches the Wood/Parquet floor-surface precedent).

Next shots: please get an actual kitchen or bathroom tile floor in frame (e.g. level10's
"cuisine" room, or level8/9/11's tile rooms) so the repeat density and grout contrast can be
checked directly instead of from pixel stats alone.
