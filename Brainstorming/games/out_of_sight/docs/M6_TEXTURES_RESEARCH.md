# M6 Texture pass 2 - ambientCG candidates

Checked on ambientCG (https://ambientcg.com, CC0 1.0): each item page (`/a/<id>`) returns 200 after
redirect, and each `get?file=<id>_1K-JPG.zip` link 302-redirects to a real `application/zip` file
(verified with `curl -IL`, no full download). Resolutions below are 1K/2K/4K/8K, each in JPG and PNG,
unless noted. Maps are read from ambientCG's own preview-link metadata (`texture_name=...`).

| # | Surface | Primary id | Fallback id | Resolutions | Maps (primary) | Smoothness | Metallic |
|---|---|---|---|---|---|---|---|
| 1 | Grass (garden ground) | Grass001 | Grass004 | 1K-8K JPG/PNG | Color, Displacement, Normal, Roughness, AO | 0.15-0.25 | 0.0 |
| 2 | Lacquer/painted chair | PaintedWood006C | PaintedWood008A | 1K-8K JPG/PNG | Color, Displacement, Normal, Roughness, AO | 0.75-0.85 | 0.0 |
| 3 | Brushed metal | Metal009 | Metal011 | 1K-8K JPG/PNG | Color, Displacement, Normal, Roughness, Metalness | 0.45-0.55 | 0.9-1.0 |
| 4 | Plastic (vacuum) | Plastic006 | Plastic011 | 1K-8K JPG/PNG | Color, Displacement, Normal, Roughness | 0.5-0.6 | 0.0 |
| 5 | Leaves/foliage | Moss002 | Leaf001 | 1K-8K JPG/PNG | Color, Displacement, Normal, Roughness, AO | 0.2-0.3 | 0.0 |
| 6 | Soil/potting earth | Ground104 | Ground048 | 1K-8K JPG/PNG | Color, Displacement, Normal, Roughness, AO | 0.05-0.1 | 0.0 |
| 7 | Glass (window pane) | none (no texture) | - | - | - | 0.95-1.0 | 0.0 |
| 8 | Wardrobe wood | Wood049 (reuse) | - | 1K-8K JPG/PNG | Color, Displacement, Normal, Roughness | 0.3-0.4 | 0.0 |

## Notes

- Grass001/004 are tagged Dense/Soft/Lush/Short, 1.4 m tile: fine grain, low contrast, matches the
  "garden ground at 8-16 m" brief; the same high-pass + wrap-around seamless derivation already used
  for the other six materials will hide any repeat at that tile size.
- PaintedWood006C/008A are the "clean" variants (no old/rough/scratched tag): grain stays visible but
  even in tone, matching Q28's default (glossy lacquer, strong highlights, wood grain visible under it).
  Skip the scratched variants (007B/008B/009B): their visible feature is bare-wood-vs-paint hue contrast
  at similar luminance, so they would read badly once flattened to grayscale.
- Metal009/Metal011 both carry the "brushed" tag and ship a Metalness map, unlike the other 5 picks.
  Caveat: the directional "brushed" sheen is partly an anisotropic-highlight effect; a flat
  smoothness/metallic URP Lit will keep the striation (from the grayscale detail) but not the moving
  anisotropic gleam.
- Leaf001 is a single-leaf cutout (has an Opacity map, not a seamless tile) : usable only if cropped to
  a card, not as a drop-in multiply-detail like the other materials. Moss002 is the safer generic
  seamless organic-noise primary; swap ranks if the plants get an actual leaf-shaped card.
- Glass: ambientCG's "glass" query only returns building Facade materials (glass + mullions baked
  together), nothing usable as a standalone pane detail. Recommend no texture: URP Lit, Transparent
  surface, smoothness 0.95-1.0, metallic 0.0, as the PRD itself suggests.
- Wood049 reuse for the wardrobe is fine: same material, same licence entry already in LICENSES.md,
  no new asset needed.
