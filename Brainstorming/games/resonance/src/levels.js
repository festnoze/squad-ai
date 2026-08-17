/**
 * RESONANCE - level data.
 *
 * Pure data, importable under Node. Every level carries its reference
 * solution; tools/validate_levels.mjs replays it in the real simulation and
 * asserts that it shatters every target and spares every forbidden crystal.
 * `par` is the fork count of the reference solution and drives the medals.
 *
 * Bands: 0 grave, 1 medium, 2 aigu. Phases are quarter periods (0..3).
 * Coordinates are board slots (0..23). Thresholds are amplitude levels (a
 * fork forces amplitude 1.0 at its own cell); with the current damping a
 * lone fork reads about 0.32 one slot away, 0.21 at two, 0.15 at four.
 * Every threshold below was tuned against tools/rms_map.mjs measurements,
 * never guessed.
 */

export const LEVELS = [
  {
    id: 'premier-eclat',
    name: 'Premier eclat',
    hint: 'Posez un diapason grave (touche 1, puis clic) pres du cristal : l onde le fera vibrer jusqu a la rupture.',
    stock: [1, 0, 0],
    crystals: [
      { x: 12, y: 12, band: 0 },
    ],
    solution: [{ x: 12, y: 10, band: 0, phase: 0 }],
    par: 1,
  },
  {
    id: 'accord-parfait',
    name: 'Accord parfait',
    hint: 'Ce cristal est trop dur pour un seul diapason. Deux ondes EN PHASE, a egale distance, s additionnent.',
    stock: [2, 0, 0],
    crystals: [
      { x: 12, y: 12, band: 0, threshold: 0.42 },
    ],
    solution: [
      { x: 11, y: 12, band: 0, phase: 0 },
      { x: 13, y: 12, band: 0, phase: 0 },
    ],
    par: 2,
  },
  {
    id: 'zone-de-silence',
    name: 'Zone de silence',
    hint: 'Le cristal rouge est interdit. Deux diapasons en OPPOSITION de phase (G) s annulent a egale distance : creusez le silence sur lui.',
    stock: [2, 0, 0],
    crystals: [
      { x: 16, y: 12, band: 0, forbidden: true, threshold: 0.13 },
      { x: 17, y: 12, band: 0, threshold: 0.2 },
    ],
    solution: [
      { x: 13, y: 12, band: 0, phase: 0 },
      { x: 19, y: 12, band: 0, phase: 2 },
    ],
    par: 2,
  },
  {
    id: 'l-echo',
    name: 'L echo',
    hint: 'Un cristal endurci au fond d un couloir. Les parois renvoient l onde : posez le diapason DANS le couloir et laissez l echo s additionner.',
    stock: [1, 0, 0],
    walls: [
      { x: 12, y: 11, w: 5, h: 1 },
      { x: 12, y: 13, w: 5, h: 1 },
      { x: 17, y: 12 },
    ],
    crystals: [
      { x: 16, y: 12, band: 0, threshold: 0.42 },
    ],
    solution: [{ x: 15, y: 12, band: 0, phase: 0 }],
    par: 1,
  },
  {
    id: 'la-mousse',
    name: 'La mousse',
    hint: 'La mousse absorbe les ondes. Le cristal interdit est a l abri derriere elle... tant que vous restez du bon cote.',
    stock: [1, 0, 0],
    foams: [{ x: 11, y: 6, w: 1, h: 12 }],
    crystals: [
      { x: 8, y: 12, band: 0, forbidden: true },
      { x: 16, y: 12, band: 0 },
    ],
    solution: [{ x: 18, y: 12, band: 0, phase: 0 }],
    par: 1,
  },
  {
    id: 'entre-deux-feux',
    name: 'Entre deux feux',
    hint: 'Deux cibles, un interdit au centre, a egale distance de tout. En phase vos ondes s additionnent sur lui ; en opposition elles s y annulent.',
    stock: [2, 0, 0],
    crystals: [
      { x: 12, y: 12, band: 0, forbidden: true, threshold: 0.13 },
      { x: 7, y: 12, band: 0 },
      { x: 17, y: 12, band: 0 },
    ],
    solution: [
      { x: 5, y: 12, band: 0, phase: 0 },
      { x: 19, y: 12, band: 0, phase: 2 },
    ],
    par: 2,
  },
  {
    id: 'le-resonateur',
    name: 'Le resonateur',
    hint: 'Aucun diapason aigu en stock. Le resonateur ecoute le medium et re-emet en aigu : servez-vous en de relais.',
    stock: [0, 1, 0],
    resonators: [{ x: 14, y: 12, from: 1, to: 2, gain: 2.0 }],
    crystals: [
      { x: 16, y: 12, band: 2, threshold: 0.1 },
    ],
    solution: [{ x: 12, y: 12, band: 1, phase: 0 }],
    par: 1,
  },
  {
    id: 'les-colonnes',
    name: 'Les colonnes',
    hint: 'Les colonnes diffractent l onde. Derriere elles, franges brillantes et franges calmes alternent : visez la bonne.',
    stock: [0, 1, 0],
    walls: [
      { x: 12, y: 7 }, { x: 12, y: 10 }, { x: 12, y: 13 }, { x: 12, y: 16 },
    ],
    crystals: [
      { x: 14, y: 9, band: 1 },
      { x: 14, y: 12, band: 1, forbidden: true },
    ],
    solution: [{ x: 11, y: 12, band: 1, phase: 0 }],
    par: 1,
  },
  {
    id: 'triptyque',
    name: 'Triptyque',
    hint: 'Trois frequences, trois cibles, un interdit medium qui traine au milieu. Chaque diapason compte.',
    stock: [1, 1, 1],
    crystals: [
      { x: 6, y: 6, band: 0 },
      { x: 18, y: 6, band: 1 },
      { x: 12, y: 18, band: 2 },
      { x: 10, y: 12, band: 1, forbidden: true },
    ],
    solution: [
      { x: 6, y: 8, band: 0, phase: 0 },
      { x: 18, y: 8, band: 1, phase: 0 },
      { x: 12, y: 16, band: 2, phase: 0 },
    ],
    par: 3,
  },
  {
    id: 'chambre-sourde',
    name: 'La chambre sourde',
    hint: 'Un cristal endurci au nord, un interdit au sud. La mousse etouffe ce qui descend : accordez votre paire au nord.',
    stock: [2, 0, 0],
    foams: [{ x: 9, y: 8, w: 7, h: 1 }],
    crystals: [
      { x: 12, y: 5, band: 0, threshold: 0.5 },
      { x: 12, y: 12, band: 0, forbidden: true },
    ],
    solution: [
      { x: 11, y: 5, band: 0, phase: 0 },
      { x: 13, y: 5, band: 0, phase: 0 },
    ],
    par: 2,
  },
  {
    id: 'cascade',
    name: 'Cascade harmonique',
    hint: 'Un seul diapason grave, une cible aigue et fragile. Deux resonateurs en chaine : grave vers medium, medium vers aigu.',
    stock: [1, 0, 0],
    resonators: [
      { x: 10, y: 12, from: 0, to: 1, gain: 1.5 },
      { x: 14, y: 12, from: 1, to: 2, gain: 2.0 },
    ],
    crystals: [
      { x: 16, y: 12, band: 2, threshold: 0.05 },
      { x: 6, y: 18, band: 1, forbidden: true },
    ],
    solution: [{ x: 8, y: 12, band: 0, phase: 0 }],
    par: 1,
  },
  {
    id: 'grande-finale',
    name: 'Grande finale',
    hint: 'Tout a la fois : une paire accordee au sud, un relais resonateur au nord, et un interdit qui ecoute chaque note grave.',
    stock: [2, 1, 0],
    foams: [{ x: 9, y: 10, w: 2, h: 5 }],
    resonators: [{ x: 16, y: 6, from: 1, to: 2, gain: 2.0 }],
    crystals: [
      { x: 6, y: 18, band: 0, threshold: 0.4 },
      { x: 18, y: 6, band: 2, threshold: 0.1 },
      { x: 12, y: 12, band: 0, forbidden: true },
    ],
    solution: [
      { x: 5, y: 17, band: 0, phase: 0 },
      { x: 7, y: 17, band: 0, phase: 0 },
      { x: 14, y: 6, band: 1, phase: 0 },
    ],
    par: 3,
  },
];
