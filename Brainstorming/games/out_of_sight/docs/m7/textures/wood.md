# Wood (Wood049) - M7 texture pass

What I saw: in 01_start, 06_level4, 12_level10 and 20_level18 the Surface.Wood pieces (bookshelf
frame, wardrobe, worktop/cabinet in the background rooms) read as flat solid colour at play
distance, no visible grain or relief. The player's own chair/stool/rocking chair are red and go
through Surface.Lacquer instead (ModelMath.IsRed in FurnitureKit.MainSurface), so they are out of
my scope; the plain-coloured furniture is what I tuned for.

What I changed (Core/Tuning.cs, both Surface.Wood only):
- `DetailTileWood`: 1.0m -> 0.6m. At 1.0m a chair seat or wardrobe door only showed a small, almost
  smooth crop of the grain bitmap. 0.6m is close to the other furniture-scale surfaces
  (Upholstery 0.55, Linen 0.45) and gives readable streaks on seats, tops and wardrobe doors without
  visibly repeating on the small pieces (legs, trim).
- `NormalScaleWood`: 1.0 -> 1.3. It was pinned equal to Parquet because of the Step22d noise cap on
  the floor, which fills far more of the frame than any one piece of furniture. Furniture can take a
  bit more relief before that cap matters, so I raised it to let the grain catch the light instead of
  reading as a flat tint.
- Did not touch the source PNGs (detail_wood_Wood049.png, normal_wood_Wood049.png): their contrast
  looked fine on inspection, the problem was scale, not the bitmap. Did not touch ModelSmoothness
  (it is shared by every ModelKit material, not wood-specific).

Next shots to check: 20_level18 (wardrobe doors, should now show vertical grain streaks and catch
a highlight), 12_level10 (bookshelf frame/back panel), 01_start (bookshelf again, different light
angle). Watch that the grain doesn't read as noise on the small trim pieces, and that the floor
(Parquet, not mine) still looks calm next to the now-slightly-stronger furniture relief.
