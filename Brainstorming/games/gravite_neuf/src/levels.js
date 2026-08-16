/**
 * GRAVITE NEUF - level data.
 *
 * A level is a stack of horizontal slices, bottom first. `layers[y][z]` is one
 * ASCII row running along +X, and consecutive rows run along +Z. Every slice of
 * a level must be a rectangle of the same size; `createState` enforces it.
 *
 * Legend
 *   .   vide
 *   #   mur fixe
 *   X   sortie (traversable)
 *   G   glu (bloc fixe, colle ce qui se pose contre lui)
 *   ^   piques (bloc fixe, detruit ce qui tombe dessus)
 *   a b plaques de pression (traversables)
 *   A B grilles colorees (ouvertes tant que leur plaque est enfoncee)
 *   @   cube joueur
 *   o   caisse
 *   *   cle
 *
 * `par` is the shortest solution length, computed offline by tools/solve.mjs.
 */

export const LEGEND = [
  ['#', 'Mur fixe'],
  ['X', 'Sortie'],
  ['G', 'Glu (fige ce qui se pose contre elle)'],
  ['^', 'Piques (detruisent ce qui tombe dessus)'],
  ['a', 'Plaque de pression'],
  ['A', 'Grille (ouverte quand la plaque est chargee)'],
  ['@', 'Cube joueur'],
  ['o', 'Caisse'],
  ['*', 'Cle'],
];

export const LEVELS = [
  {
    name: 'Premier basculement',
    hint: 'Vous ne deplacez pas le cube : vous choisissez ou est le bas.',
    par: 1,
    layers: [
      ['#####', '#####', '#####', '#####', '#####'],
      ['#####', '#...#', '#@.X#', '#...#', '#####'],
    ],
  },
  {
    name: 'La caisse',
    hint: 'Les caisses tombent aussi. Une caisse bien placee vous arrete au bon endroit.',
    par: 2,
    layers: [
      ['######', '######', '######', '######', '######', '######'],
      ['######', '##..##', '#@.X.#', '#....#', '#...o#', '######'],
    ],
  },
  {
    name: 'La glu',
    hint: 'La glu fige definitivement ce qui vient s y poser. Un support qui ne bouge plus.',
    par: 4,
    layers: [
      ['######', '######', '######', '######', '######', '######'],
      ['######', '#....#', '#....#', '#@.o.#', '##.G.#', '######'],
      ['......', '......', '......', '...X..', '......', '......'],
      ['......', '......', '......', '....#.', '......', '......'],
      ['......', '......', '......', '.#....', '......', '......'],
    ],
  },
  {
    name: 'La cle',
    hint: 'Une cle se ramasse quand le cube s immobilise juste a cote. Sans toutes les cles, pas de sortie.',
    par: 3,
    layers: [
      ['######', '######', '######', '######', '######', '######'],
      ['######', '#@...#', '#.#..#', '#..#.#', '#X#.*#', '######'],
    ],
  },
  {
    name: 'Les piques',
    hint: 'Ce qui vient buter contre les piques est detruit. Y compris vous.',
    par: 4,
    layers: [
      ['######', '######', '######', '######', '######', '######'],
      ['######', '#@..##', '#.^.^#', '##...#', '#..#X#', '######'],
    ],
  },
  {
    name: 'La plaque',
    hint: 'Une plaque chargee ouvre la grille de sa couleur. Une caisse fait un bon presse-papier.',
    par: 3,
    layers: [
      ['######', '######', '######', '######', '######', '######'],
      ['######', '#o.@.#', '#.##.#', '#a#.A#', '##..X#', '######'],
    ],
  },
  {
    name: 'Le puits',
    hint: 'La gravite monte aussi. Cherchez la trouee dans le plancher du dessus.',
    par: 4,
    layers: [
      ['######', '######', '######', '######', '######'],
      ['######', '#....#', '#....#', '#..@.#', '######'],
      ['......', '..###.', '.####.', '.####.', '......'],
      ['######', '#..X##', '#....#', '#....#', '######'],
      ['......', '.#....', '......', '......', '......'],
    ],
  },
  {
    name: 'Monter la caisse',
    hint: 'Envoyez la caisse a l etage avant vous : elle vous servira de butoir la-haut.',
    par: 4,
    layers: [
      ['######', '######', '######', '######', '######'],
      ['######', '#@.o.#', '#....#', '#....#', '######'],
      ['......', '.##.#.', '.####.', '..###.', '......'],
      ['######', '#....#', '#....#', '#.X.##', '######'],
      ['......', '...#..', '......', '.#.#..', '......'],
    ],
  },
  {
    name: 'Plateforme collee',
    hint: 'Une caisse collee en plein air reste en plein air.',
    par: 3,
    layers: [
      ['######', '######', '######', '######', '######'],
      ['######', '#@...#', '#...o#', '##..##', '######'],
      ['......', '......', '...X..', '.#....', '......'],
      ['......', '.#....', '.#..G.', '......', '......'],
    ],
  },
  {
    name: 'La cle sous grille',
    hint: 'Chargez la plaque, puis laissez la cle vous ouvrir la voie.',
    par: 3,
    layers: [
      ['######', '######', '######', '######', '######', '######'],
      ['######', '#o.@.#', '#.##.#', '#a#.A#', '##*.X#', '######'],
    ],
  },
  {
    name: 'Deux cles',
    hint: 'Une cle ramassee libere la case : le cube repart aussitot dans le meme mouvement.',
    par: 5,
    layers: [
      ['######', '######', '######', '######', '######'],
      ['######', '#@..*#', '#....#', '#....#', '######'],
      ['......', '.###..', '.####.', '.####.', '......'],
      ['######', '#.#*.#', '#....#', '#X..##', '######'],
      ['......', '...##.', '......', '......', '......'],
    ],
  },
  {
    name: 'Colle sur la plaque',
    hint: 'Une caisse collee sur une plaque, c est une grille ouverte pour toujours.',
    par: 5,
    layers: [
      ['######', '######', '######', '######', '######'],
      ['######', '#....#', '#@...#', '#o.aG#', '######'],
      ['......', '.###..', '.####.', '.####.', '......'],
      ['######', '#....#', '#A...#', '#X...#', '######'],
      ['......', '....#.', '......', '......', '......'],
    ],
  },
  {
    name: 'Piques a l etage',
    hint: 'Le chemin court passe sur les piques. Le bon chemin fait le tour.',
    par: 5,
    layers: [
      ['######', '######', '######', '######', '######'],
      ['######', '#..^.#', '#@...#', '#o.aG#', '######'],
      ['......', '.###..', '.####.', '.####.', '......'],
      ['######', '#..*.#', '#A...#', '#X...#', '######'],
      ['......', '...##.', '......', '......', '......'],
    ],
  },
  {
    name: 'Gravite neuf',
    hint: 'Tout ce que la structure sait faire, dans le bon ordre.',
    par: 5,
    layers: [
      ['#######', '#######', '#######', '#######', '#######'],
      ['#######', '#@....#', '#...^*#', '#o.aG.#', '#######'],
      ['.......', '.####..', '.#####.', '.#####.', '.......'],
      ['#######', '#.#.*.#', '#A....#', '#X#..##', '#######'],
      ['.......', '....##.', '.......', '.......', '.......'],
    ],
  },
];

export const LEVEL_COUNT = LEVELS.length;
