/**
 * CONTREPOIDS - level data.
 *
 * A level is an ASCII grid (`grid[z]` is one row along +X, rows run along +Z),
 * '.' meaning void (no column, cannot be entered). Every other character is a
 * column letter resolved through `columns`. `ropes` links two letters into one
 * simple pair. `items` places initial cargo on a letter. `start`/`exit` name
 * the player's spawn column and the goal column.
 *
 * `par` is the shortest solution length (number of actions), computed offline
 * by tools/solve.mjs and asserted by it against this file.
 */

export const LEGEND = [
  ['ground', 'Sol fixe, ne bouge jamais'],
  ['platform', 'Plateforme suspendue, monte et descend entre ses deux butees'],
  ['pierre', 'Objet de poids 1, se porte'],
  ['enclume', 'Objet de poids 3, se pousse seulement, jamais porte'],
  ['ballon', 'Objet de poids -1, se porte'],
];

export const LEVELS = [
  // -------------------------------------------------------------------------
  // 1) Poser un objet fait descendre sa plateforme et monter sa jumelle.
  // -------------------------------------------------------------------------
  {
    name: 'Premier contrepoids',
    hint: 'Une pierre posee alourdit sa plateforme : elle descend, sa jumelle monte.',
    par: 4,
    grid: ['EAX', '.B.'],
    columns: {
      E: { kind: 'ground', h: 4 },
      A: { kind: 'platform', min: 0, max: 4, h: 4 },
      X: { kind: 'ground', h: 0 },
      B: { kind: 'platform', min: 0, max: 4, h: 0 },
    },
    ropes: [['A', 'B']],
    items: { E: 'pierre' },
    start: 'E',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 2) Le personnage lui-meme est un poids de 2.
  // -------------------------------------------------------------------------
  {
    name: 'Le poids du corps',
    hint: 'Vous pesez 2 des que vous montez sur une plateforme. Votre jumelle le sent aussitot.',
    par: 2,
    grid: ['EAX', '.B.'],
    columns: {
      E: { kind: 'ground', h: 1 },
      A: { kind: 'platform', min: 0, max: 2, h: 1 },
      X: { kind: 'ground', h: 0 },
      B: { kind: 'platform', min: 0, max: 2, h: 1 },
    },
    ropes: [['A', 'B']],
    items: {},
    start: 'E',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 3) Pousser une enclume d'une plateforme a l'autre, a niveau egal.
  // -------------------------------------------------------------------------
  {
    name: "L'enclume",
    hint: 'Une enclume ne se porte jamais : elle se pousse, seulement a niveau egal. Poussez-en deux pour monter.',
    par: 4,
    grid: ['.X..', 'EGMF', '.N..', '.H..'],
    columns: {
      X: { kind: 'ground', h: 3 },
      E: { kind: 'ground', h: 0 },
      G: { kind: 'platform', min: 0, max: 5, h: 0 },
      M: { kind: 'ground', h: 0 },
      F: { kind: 'platform', min: -5, max: 0, h: 0 },
      N: { kind: 'ground', h: 1 },
      H: { kind: 'platform', min: -5, max: 1, h: 1 },
    },
    ropes: [
      ['F', 'G'],
      ['H', 'G'],
    ],
    items: { M: 'enclume', N: 'enclume' },
    start: 'E',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 4) Le ballon retire du poids : sa plateforme descend moins loin.
  // -------------------------------------------------------------------------
  {
    name: 'Le ballon',
    hint: 'Un ballon pese -1 : il allege la plateforme qui le porte.',
    par: 4,
    grid: ['EAX', '.B.'],
    columns: {
      E: { kind: 'ground', h: 4 },
      A: { kind: 'platform', min: 0, max: 4, h: 4 },
      X: { kind: 'ground', h: 0 },
      B: { kind: 'platform', min: 0, max: 4, h: 0 },
    },
    ropes: [['A', 'B']],
    items: { E: 'ballon' },
    start: 'E',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 5) Chaine simple : une plateforme centrale relie deux paires distinctes.
  // -------------------------------------------------------------------------
  {
    name: 'La chaine',
    hint: 'Cette plateforme tire deux cordes a la fois : une pierre posee dessus tire les deux jumelles.',
    par: 4,
    grid: ['EGX', '.F.', '.H.'],
    columns: {
      E: { kind: 'ground', h: 12 },
      G: { kind: 'platform', min: 0, max: 20, h: 12 },
      X: { kind: 'ground', h: 2 },
      F: { kind: 'platform', min: 0, max: 20, h: 0 },
      H: { kind: 'platform', min: 0, max: 20, h: 0 },
    },
    ropes: [
      ['G', 'F'],
      ['G', 'H'],
    ],
    items: { E: 'pierre' },
    start: 'E',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 6) Le saut : grimper un cran demande Espace, descendre se fait en marchant.
  // -------------------------------------------------------------------------
  {
    name: 'Le saut',
    hint: 'Descendre d\'un cran se marche. Monter d\'un cran se saute.',
    par: 3,
    grid: ['EABX'],
    columns: {
      E: { kind: 'ground', h: 0 },
      A: { kind: 'platform', min: 0, max: 3, h: 1 },
      B: { kind: 'platform', min: 0, max: 3, h: 2 },
      X: { kind: 'ground', h: 3 },
    },
    ropes: [],
    items: {},
    start: 'E',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 7) L'enclume voyageuse : deux poussees successives, portees par une corde.
  // -------------------------------------------------------------------------
  {
    name: 'Enclume voyageuse',
    hint: 'La corde est loin de vous : marchez jusqu\'a elle, puis poussez les deux enclumes pour monter.',
    par: 5,
    grid: ['..X..', 'TUGMF', '..N..', '..H..'],
    columns: {
      X: { kind: 'ground', h: 3 },
      T: { kind: 'ground', h: 0 },
      U: { kind: 'ground', h: 0 },
      G: { kind: 'platform', min: 0, max: 5, h: 0 },
      M: { kind: 'ground', h: 0 },
      F: { kind: 'platform', min: -5, max: 0, h: 0 },
      N: { kind: 'ground', h: 1 },
      H: { kind: 'platform', min: -5, max: 1, h: 1 },
    },
    ropes: [
      ['F', 'G'],
      ['H', 'G'],
    ],
    items: { M: 'enclume', N: 'enclume' },
    start: 'T',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 8) Deux poulies independantes a franchir dans le bon ordre.
  // -------------------------------------------------------------------------
  {
    name: 'Deux poulies',
    hint: 'Deux cordes independantes, deux pierres : la seconde chute ne ressemble pas a la premiere.',
    par: 8,
    grid: ['EAXCZ', '.B..D'],
    columns: {
      E: { kind: 'ground', h: 4 },
      A: { kind: 'platform', min: 0, max: 4, h: 4 },
      X: { kind: 'ground', h: 0 },
      C: { kind: 'platform', min: -4, max: 0, h: 0 },
      Z: { kind: 'ground', h: -4 },
      B: { kind: 'platform', min: 0, max: 4, h: 0 },
      D: { kind: 'platform', min: -4, max: 0, h: -4 },
    },
    ropes: [
      ['A', 'B'],
      ['C', 'D'],
    ],
    items: { E: 'pierre', X: 'pierre' },
    start: 'E',
    exit: 'Z',
  },

  // -------------------------------------------------------------------------
  // 9) Reglage fin : une pierre et un ballon pour tomber pile sur la sortie.
  // -------------------------------------------------------------------------
  {
    name: 'Reglage fin',
    hint: 'Une pierre tombe loin, un ballon retient la chute suivante : la meme recette, un poids different.',
    par: 8,
    grid: ['EAXCZ', '.B..D'],
    columns: {
      E: { kind: 'ground', h: 4 },
      A: { kind: 'platform', min: 0, max: 4, h: 4 },
      X: { kind: 'ground', h: 0 },
      C: { kind: 'platform', min: -4, max: 0, h: 0 },
      Z: { kind: 'ground', h: -4 },
      B: { kind: 'platform', min: 0, max: 4, h: 0 },
      D: { kind: 'platform', min: -4, max: 0, h: -4 },
    },
    ropes: [
      ['A', 'B'],
      ['C', 'D'],
    ],
    items: { E: 'pierre', X: 'ballon' },
    start: 'E',
    exit: 'Z',
  },

  // -------------------------------------------------------------------------
  // 10) Longue chaine de quatre plateformes.
  // -------------------------------------------------------------------------
  {
    name: 'La longue chaine',
    hint: 'Trois cordes tirees a la fois par la meme plateforme : la chute se creuse plus profond qu\'on ne croit.',
    par: 4,
    grid: ['EGX', '.F.', '.H.', '.K.'],
    columns: {
      E: { kind: 'ground', h: 24 },
      G: { kind: 'platform', min: 0, max: 40, h: 24 },
      X: { kind: 'ground', h: 9 },
      F: { kind: 'platform', min: 0, max: 40, h: 0 },
      H: { kind: 'platform', min: 0, max: 40, h: 0 },
      K: { kind: 'platform', min: 0, max: 40, h: 0 },
    },
    ropes: [
      ['G', 'F'],
      ['G', 'H'],
      ['G', 'K'],
    ],
    items: { E: 'pierre' },
    start: 'E',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 11) Le puits profond : enclume et pierre combinees sur une longue descente.
  // -------------------------------------------------------------------------
  {
    name: 'Le puits profond',
    hint: 'Une pierre pour descendre, deux enclumes pour remonter ailleurs : deux cordes, deux techniques.',
    par: 8,
    grid: ['...X..', 'EAYGMF', '.B.N..', '...H..'],
    columns: {
      X: { kind: 'ground', h: 3 },
      E: { kind: 'ground', h: 4 },
      A: { kind: 'platform', min: 0, max: 4, h: 4 },
      Y: { kind: 'ground', h: 0 },
      G: { kind: 'platform', min: 0, max: 5, h: 0 },
      M: { kind: 'ground', h: 0 },
      F: { kind: 'platform', min: -5, max: 0, h: 0 },
      B: { kind: 'platform', min: 0, max: 4, h: 0 },
      N: { kind: 'ground', h: 1 },
      H: { kind: 'platform', min: -5, max: 1, h: 1 },
    },
    ropes: [
      ['A', 'B'],
      ['F', 'G'],
      ['H', 'G'],
    ],
    items: { E: 'pierre', M: 'enclume', N: 'enclume' },
    start: 'E',
    exit: 'X',
  },

  // -------------------------------------------------------------------------
  // 12) Le grand puits : chaine, enclume et ballon dans la meme traversee.
  // -------------------------------------------------------------------------
  {
    name: 'Le grand puits',
    hint: 'Tout ce que vous avez appris, une seule fois, dans le bon ordre : pierre, enclumes, ballon.',
    par: 12,
    grid: ['..XCD..', '...Q...', 'EAYGMF.', '.B.N...', '...H...'],
    columns: {
      X: { kind: 'ground', h: -1 },
      C: { kind: 'platform', min: 0, max: 3, h: 3 },
      D: { kind: 'platform', min: 0, max: 3, h: 0 },
      Q: { kind: 'ground', h: 3 },
      E: { kind: 'ground', h: 4 },
      A: { kind: 'platform', min: 0, max: 4, h: 4 },
      Y: { kind: 'ground', h: 0 },
      G: { kind: 'platform', min: 0, max: 5, h: 0 },
      M: { kind: 'ground', h: 0 },
      F: { kind: 'platform', min: -5, max: 0, h: 0 },
      B: { kind: 'platform', min: 0, max: 4, h: 0 },
      N: { kind: 'ground', h: 1 },
      H: { kind: 'platform', min: -5, max: 1, h: 1 },
    },
    ropes: [
      ['C', 'D'],
      ['A', 'B'],
      ['F', 'G'],
      ['H', 'G'],
    ],
    items: { Q: 'ballon', E: 'pierre', M: 'enclume', N: 'enclume' },
    start: 'E',
    exit: 'X',
  },
];
