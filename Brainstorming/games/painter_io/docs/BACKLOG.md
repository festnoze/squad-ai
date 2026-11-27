# Painter.io - Backlog (ideas for later, not scheduled)

## Future biomes (designer note, 2026-11-26)
Two possible extensions on top of Liquide / Feu / Électricité. Each would be a new BiomeTheme (composite, bead and overlay graphs, FX,
clip set) plus a default trait set in BiomeTraitTable (see docs/BIOME_TRAITS.md); the rules stay shared.
- **Air**: the pawn is a soap bubble instead of a drop (iridescent thin-film sheen, wobbly round silhouette, transparency). Ideas to explore:
  airy territories (clouds or bubble foam), a trail of small bubbles, a cut that pops the trail bubble by bubble. Possible traits: drift
  (inertia), a lighter pawn pushed by "wind" zones.
- **Cancer**: the pawn is a virus with sharp spiky asperities instead of a drop (crisp spikes, organic membrane). Ideas to explore:
  territories as spreading cellular tissue (cells dividing at the edge), a trail like a filament, a cut that makes the filament wither;
  Propagation fits naturally. Mind the tone and the store guidelines: a stylized "infection / cells" look rather than a medical one, and
  check the name of the biome for sensitivity (for example "Virus" or "Cellules" as the player-facing name).

## Arena variants (to decide)
Today every biome uses the same rounded-square arena; only the ground changes. Possible per-biome arenas and decor: see the proposal in the
conversation of 2026-11-26 (shape per biome, background decor outside the arena, optional obstacles). Technical note: obstacles must be a new
"blocked" cell type (not Void): Void cells are "outside" for the enclosure flood, so a lake made of Void would stop every capture around it.

## Deferred items from wave C (docs/waveC/fix_plan.json "deferred")
rules-03 (doomed pocket presentation once the lasso is back on), feel-01 (longer slow motion and "cut right behind you" line), feel-11
(final standings list), feel-08 (home edge indicator), feel-13 (predefined haptic effects), perf-03 (persisted tier), shader warm-up,
perf-04 (smaller bolt quads), liquid per-pixel cost (perf-06).
