# Painter IO - User feedback for wave D (normative)

Status: v1.0, 2026-11-26. The user played the Gate B build and asked for three changes, to be integrated in wave D together with
docs/BIOME_TRAITS.md. They are folded into docs/CONTRACT.md (section 28) after wave C-2. They override older text where they disagree.

## F1. A real logo for the game
User: "Je veux que tu crées un logo pour le jeu qui semble adapté."
- Wordmark "Painter IO" drawn as glossy liquid paint, consistent with the game: thick rounded letters (the OFL font in Resources/Fonts,
  Nunito Black or Fredoka, as the base outline), coral body with a soft specular highlight on the upper-left of each letter, a soft
  lower-right shadow, and one playful liquid idea that tells the game in one glance: for example the "O" is a pearl (the pawn head) whose
  thin teal thread loops back into the "I", or a drip / thread that leaves a letter and returns. Legible on the navy menu background and at
  small sizes. No em dash, no text other than the name.
- Variants from the same reproducible generator: liquid (primary), fire (ember / flame letters), electric (neon letters with small arcs).
  The menu shows the variant of the selected biome (swap with a short crossfade), with a gentle idle animation (slow shine sweep or wobble).
- App icon: a square mark derived from the logo (a coral pearl with its teal thread loop on a navy rounded square), exported for Android
  (adaptive icon foreground + background layers, and legacy icons) and for the Windows player icon, set by Builder in PlayerSettings.
- Production: a reproducible generator under tools/logo/ (Python + numpy + Pillow, or a Unity batch method that renders with the game's
  own shading functions), SDF based shading that matches PIO_ShadeLiquid (same key light from the upper left). Outputs committed under
  Assets/Resources/UI/ (logo_liquid.png, logo_fire.png, logo_electric.png with alpha, about 1600 x 640) and the icon set. The licence of the
  font is already alongside it (OFL). Look at every output with the Read tool and iterate until it looks like a professional mobile game logo.

## F2. The liquid must look more like a DROP
User: "Je veux que l'aspect liquide ressemble plus a une goutte."
- Today the puddles read as flat coins with a thin bevel. Target: every puddle reads as one big drop of liquid: a domed, thick body whose
  height keeps rising over about 1.5 to 2 u from the edge (not a flat top after 0.3 u), a broad soft highlight band on the upper-left plus a
  sharp specular hot spot, slightly richer color at the thick center and a lighter or more translucent look toward the thin edge (depth
  absorption), a crisp meniscus foot and a stronger, softer contact shadow on the lower right. The pearl reads as a drop too (a slight
  teardrop stretch along the motion), threads stay round tubes, and the fusion necks between pearl, thread and puddle stay smooth.
- Technique (suggested): a second, much wider territory field (for example 256 x 256, Gaussian sigma about 0.8 u, built in the same
  scissored command buffer as the existing blur) published as `_PIO_TerritoryDome`, combined with the existing narrow field so the edge stays
  sharp while the body domes; one extra bilinear fetch in the composite is allowed (update the 12.2 item 4 budget note).
- Acceptance: DevShot / probe screenshots before and after at 540 x 960 and 1080 x 2400, High and Medium, side by side with
  docs/reference_gouttes.png; V1-V8 must still pass; the electric and fire composites must not change (shared files keep their signatures).

## F3. Electric bases crackle with small arcs
User: "Je veux que la base en mode electrique soit parcourue de petits traits electriques comme c'est le cas du fil quand on est en train
de partir de la base."
- In the Electricite biome, the territory INTERIOR is crossed by many small jagged electric streaks of the same visual language as the live
  wire (thread): short arcs (about 0.3 to 0.8 u), thin white-hot core with the player's neon glow, jagged offset flickering at 12 to 20 Hz,
  drifting and re-spawning across the surface, a few more near the rim. Readable, lively, not noisy: moderate density, no full-screen strobe,
  home vs pocket vs rival territory still identifiable, the chase packet still the brightest moving thing.
- Procedural in ElectricComposite (no new texture), inside the fetch budget; Medium halves the density, Low keeps a few static-ish arcs.
- Acceptance: screenshots at several moments (the arcs must be visible in still frames) and a short frame sequence to judge the flicker.
