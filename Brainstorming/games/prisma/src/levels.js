/**
 * PRISMA - level data.
 *
 * A level is an array of equal length ASCII rows. Row 0 is the north edge,
 * column 0 the west edge. Everything the simulation needs lives here, so the
 * rules module never has to know about a specific puzzle.
 *
 * Legend
 *   .          free floor (a component can be dropped here)
 *   #          opaque wall, absorbs any beam
 *   > < ^ v    white emitter facing east / west / north / south
 *   R G B      target waiting for red / green / blue
 *   Y C M      target waiting for yellow (R+G) / cyan (G+B) / magenta (R+B)
 *   W          target waiting for white (R+G+B)
 *   0 1 2 3    fixed mirror, already oriented (same rotation table as a placed one)
 *   p          portal, paired with the next `p` in reading order
 *
 * `solution` is a reference layout replayed through the real solver during
 * verification: it proves the level is solvable and pins `optimum` to a
 * disposition that actually lights every target.
 */

export const COLOR_R = 1;
export const COLOR_G = 2;
export const COLOR_B = 4;
export const COLOR_WHITE = 7;

/** Piece kinds a player can place. Order drives the 1..5 hotkeys. */
export const PIECE_KINDS = ['mirror', 'prism', 'filter', 'combiner', 'splitter'];

/** How many distinct rotations each kind exposes. */
export const ROTATIONS = {
  mirror: 4,
  prism: 3,
  filter: 3,
  combiner: 4,
  splitter: 4,
};

export const PIECE_LABEL = {
  mirror: 'Miroir',
  prism: 'Prisme',
  filter: 'Filtre',
  combiner: 'Combinateur',
  splitter: 'Splitter',
};

export const PIECE_HELP = {
  mirror: 'Devie de 90 degres. Une seule face reflechit, le dos absorbe.',
  prism: 'Separe le faisceau en rouge, vert et bleu sur trois directions.',
  filter: 'Ne laisse passer qu une composante de couleur.',
  combiner: 'Additionne tous les faisceaux entrants et ressort par sa fleche.',
  splitter: 'Moitie tout droit, moitie a 90 degres.',
};

export const LEVELS = [
  {
    id: 'l01',
    name: 'Premier reflet',
    hint: 'Le miroir ne reflechit que du cote poli. Clic droit pour le tourner.',
    inventory: { mirror: 2 },
    optimum: 1,
    rows: [
      '......',
      '>....#',
      '......',
      '......',
      '....W.',
      '......',
    ],
    solution: [[4, 1, 'mirror', 1]],
  },
  {
    id: 'l02',
    name: 'Teinte imposee',
    hint: 'Le filtre ne garde qu une couleur. Tourne-le pour choisir laquelle.',
    inventory: { mirror: 3, filter: 2 },
    optimum: 3,
    rows: [
      '#......',
      '>.....#',
      '......#',
      '.#....#',
      '......#',
      '.R.....',
      '.......',
    ],
    solution: [
      [5, 1, 'mirror', 1],
      [5, 5, 'mirror', 2],
      [3, 5, 'filter', 0],
    ],
  },
  {
    id: 'l03',
    name: 'Trois couleurs',
    hint: 'Le prisme eclate le blanc: gauche, tout droit, droite.',
    inventory: { prism: 1, mirror: 2 },
    optimum: 1,
    rows: [
      '...R...',
      '.......',
      '.......',
      '>.....G',
      '.......',
      '.......',
      '...B...',
    ],
    solution: [[3, 3, 'prism', 0]],
  },
  {
    id: 'l04',
    name: 'Demi-teinte',
    hint: 'Le splitter garde la moitie du faisceau tout droit.',
    inventory: { splitter: 1, mirror: 2 },
    optimum: 2,
    rows: [
      '........',
      '.##..##.',
      '.#....#.',
      '>......W',
      '.#....#.',
      '.##..##.',
      '........',
      'W.......',
    ],
    solution: [
      [4, 3, 'splitter', 1],
      [4, 7, 'mirror', 2],
    ],
  },
  {
    id: 'l05',
    name: 'Addition',
    hint: 'Le combinateur additionne ce qui entre. Rouge plus bleu donne magenta.',
    inventory: { prism: 1, combiner: 1 },
    optimum: 2,
    rows: [
      '........',
      '...0..1.',
      '........',
      '>....#.M',
      '........',
      '...3..2.',
      '........',
      '........',
    ],
    solution: [
      [3, 3, 'prism', 0],
      [6, 3, 'combiner', 0],
    ],
  },
  {
    id: 'l06',
    name: 'Passage',
    hint: 'Les portails se repondent et conservent la direction du faisceau.',
    inventory: { splitter: 1, filter: 2, mirror: 1 },
    optimum: 3,
    rows: [
      '........',
      '>......G',
      '........',
      '....#p..',
      '........',
      '........',
      '..p.....',
      '..R.....',
    ],
    solution: [
      [5, 1, 'splitter', 1],
      [5, 2, 'filter', 0],
      [6, 1, 'filter', 1],
    ],
  },
  {
    id: 'l07',
    name: 'Ricochet',
    hint: 'Deux murs, deux ouvertures. Le trajet est force, l orientation non.',
    inventory: { mirror: 5 },
    optimum: 4,
    rows: [
      '.........',
      '>........',
      '#######.#',
      '.........',
      '.........',
      '#.#######',
      '.........',
      '......W..',
      '.........',
    ],
    solution: [
      [7, 1, 'mirror', 1],
      [7, 3, 'mirror', 2],
      [1, 3, 'mirror', 0],
      [1, 7, 'mirror', 3],
    ],
  },
  {
    id: 'l08',
    name: 'Jaune',
    hint: 'Le jaune n existe pas dans le prisme: il faut le reconstruire.',
    inventory: { prism: 1, mirror: 3, combiner: 1, filter: 2 },
    optimum: 4,
    rows: [
      '.........',
      '.........',
      '.........',
      '.........',
      '>.......Y',
      '.........',
      '..#......',
      '.........',
      '.........',
    ],
    solution: [
      [2, 4, 'prism', 0],
      [2, 0, 'mirror', 0],
      [6, 0, 'mirror', 1],
      [6, 4, 'combiner', 0],
    ],
  },
  {
    id: 'l09',
    name: 'Deux sources',
    hint: 'Deux emetteurs, une seule cible. Chaque branche apporte sa couleur.',
    inventory: { mirror: 3, filter: 3, combiner: 1 },
    optimum: 5,
    rows: [
      '..........',
      '..........',
      '>.........',
      '....##....',
      '.........C',
      '....##....',
      '..........',
      '>.........',
      '..........',
      '..........',
    ],
    solution: [
      [3, 2, 'filter', 1],
      [6, 2, 'mirror', 1],
      [3, 7, 'filter', 2],
      [6, 7, 'mirror', 2],
      [6, 4, 'combiner', 0],
    ],
  },
  {
    id: 'l10',
    name: 'Cascade',
    hint: 'Chaque splitter divise encore. Cinq cibles, un seul faisceau.',
    inventory: { splitter: 3, mirror: 3 },
    optimum: 5,
    rows: [
      'W......W..',
      '..........',
      '..........',
      '..........',
      '>........W',
      '..........',
      '..........',
      '..........',
      '..........',
      '.........W',
    ],
    solution: [
      [2, 4, 'splitter', 2],
      [5, 4, 'splitter', 1],
      [7, 4, 'splitter', 2],
      [2, 0, 'mirror', 1],
      [5, 9, 'mirror', 3],
    ],
  },
  {
    id: 'l11',
    name: 'Aller-retour',
    hint: 'Le portail avale la moitie du faisceau. L autre moitie doit descendre.',
    inventory: { splitter: 2, mirror: 3, filter: 2 },
    optimum: 4,
    rows: [
      '..........',
      '..........',
      '>.....p..G',
      '..........',
      '....####..',
      '..........',
      '..........',
      '..p.......',
      '....#.....',
      '....W.....',
    ],
    solution: [
      [3, 2, 'splitter', 1],
      [3, 9, 'mirror', 3],
      [7, 7, 'filter', 1],
      [9, 7, 'mirror', 2],
    ],
  },
  {
    id: 'l12',
    name: 'Chromatique',
    hint: 'Chaque couleur sert deux fois: une cible pure, une part au melange.',
    inventory: { prism: 1, splitter: 2, mirror: 3, combiner: 1, filter: 2 },
    optimum: 6,
    rows: [
      '..R........',
      '...........',
      '...........',
      '...........',
      '...........',
      '>....G....M',
      '...........',
      '...........',
      '...........',
      '...........',
      '..B........',
    ],
    solution: [
      [2, 5, 'prism', 0],
      [2, 3, 'splitter', 0],
      [2, 7, 'splitter', 3],
      [8, 3, 'mirror', 1],
      [8, 7, 'mirror', 2],
      [8, 5, 'combiner', 0],
    ],
  },
  {
    id: 'l13',
    name: 'Croisement',
    hint: 'Un seul prisme pour deux melanges. Le vert doit partir des deux cotes.',
    inventory: { prism: 1, splitter: 2, mirror: 4, combiner: 2, filter: 2 },
    optimum: 7,
    rows: [
      '##........Y',
      '...........',
      '.#.......#.',
      '...........',
      '...........',
      '>..........',
      '...........',
      '...........',
      '.#.......#.',
      '...........',
      '##........C',
    ],
    solution: [
      [3, 5, 'prism', 0],
      [5, 5, 'splitter', 2],
      [3, 0, 'mirror', 0],
      [5, 0, 'combiner', 0],
      [7, 5, 'mirror', 1],
      [3, 10, 'mirror', 3],
      [7, 10, 'combiner', 0],
    ],
  },
  {
    id: 'l14',
    name: 'PRISMA',
    hint: 'Separer, prelever, puis tout recomposer en blanc.',
    inventory: { prism: 2, splitter: 3, mirror: 4, combiner: 2, filter: 3 },
    optimum: 7,
    rows: [
      '..R.........',
      '............',
      '............',
      '.....p##p...',
      '............',
      '............',
      '>..........W',
      '............',
      '............',
      '............',
      '............',
      '..B..G......',
    ],
    solution: [
      [2, 6, 'prism', 0],
      [2, 3, 'splitter', 0],
      [2, 9, 'splitter', 3],
      [5, 6, 'splitter', 1],
      [9, 3, 'mirror', 1],
      [9, 9, 'mirror', 2],
      [9, 6, 'combiner', 0],
    ],
  },
];

export function levelCount() {
  return LEVELS.length;
}

export function inventoryTotal(level) {
  let total = 0;
  for (const kind of PIECE_KINDS) total += level.inventory[kind] || 0;
  return total;
}
