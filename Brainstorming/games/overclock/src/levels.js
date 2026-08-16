/**
 * OVERCLOCK - level data.
 *
 * Everything about a level lives here, in data. No level logic anywhere else.
 *
 * `h` : one string per row (z), one char per column (x)
 *       '0'..'9' -> slab height in steps, '.' -> void (a crate dropped in it
 *       fills it back to height 0).
 * `m` : same shape, markers
 *       '.' nothing        '*' target
 *       'C' crate          'r' 'g' 'b' painted floor
 *       'R' 'G' 'B' painted floor that is also a target
 * `start` : { x, z, dir }, dir 0 = +x, 1 = +z, 2 = -x, 3 = -z
 * `procs` : slot budget of PRINCIPAL, P1, P2
 * `ops`   : instructions offered by the palette, in keyboard order (1..9)
 * `colors`: condition colours the player may attach to an instruction
 * `optimal`: instruction count of the reference solution (gold medal threshold)
 * `solution`: the reference program, kept in data so it can be replayed by the
 *       verification script. It is never shown to the player.
 */

const MOVE = ['FWD', 'LEFT', 'RIGHT', 'ACT'];

export const LEVELS = [
  {
    id: 'l01',
    name: 'PREMIER CONTACT',
    hint: 'Le drone execute les slots de gauche a droite, puis s arrete. Amenez le sur la cible et allumez la.',
    h: ['000', '..0', '..0'],
    m: ['...', '...', '..*'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [8],
    ops: MOVE,
    colors: [],
    optimal: 6,
    solution: [['FWD', 'FWD', 'RIGHT', 'FWD', 'FWD', 'ACT']],
  },
  {
    id: 'l02',
    name: 'BOUCLE',
    hint: 'Quatre slots pour six cibles. Une procedure qui s appelle elle meme recommence pour toujours : c est la boucle.',
    h: ['000000'],
    m: ['******'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [4],
    ops: [...MOVE, 'CALL0'],
    colors: [],
    optimal: 3,
    solution: [['ACT', 'FWD', 'CALL0']],
  },
  {
    id: 'l03',
    name: 'COULEUR',
    hint: 'Une instruction peut porter une condition de couleur : elle ne s execute que si la dalle sous le drone est de cette couleur. Le rouge marque les angles.',
    h: ['0000', '0..0', '0..0', '0000'],
    m: ['***R', '*..*', '*..*', 'R**R'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [5],
    ops: [...MOVE, 'CALL0'],
    colors: ['r'],
    optimal: 4,
    solution: [['ACT', 'RIGHT@r', 'FWD', 'CALL0']],
  },
  {
    id: 'l04',
    name: 'SOUS-PROGRAMME',
    hint: 'PRINCIPAL n a que trois slots. Rangez un quart de tour dans P1 et faites appeler P1 en boucle.',
    h: ['000', '0.0', '000'],
    m: ['***', '*.*', '***'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [3, 5],
    ops: [...MOVE, 'CALL0', 'CALL1'],
    colors: [],
    optimal: 7,
    solution: [['CALL1', 'CALL0'], ['ACT', 'FWD', 'ACT', 'FWD', 'RIGHT']],
  },
  {
    id: 'l05',
    name: 'RELIEF',
    hint: 'AVANCER exige une dalle a la meme hauteur. SAUT monte d une marche, descend de n importe quelle hauteur, et franchit un vide d une case.',
    h: ['012.210'],
    m: ['***.***'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [4],
    ops: [...MOVE, 'JUMP', 'CALL0'],
    colors: [],
    optimal: 3,
    solution: [['ACT', 'JUMP', 'CALL0']],
  },
  {
    id: 'l06',
    name: 'MEMOIRE FRAICHE',
    hint: 'Le drone ne voit rien devant lui. Peindre une dalle, c est se laisser un souvenir pour le tour suivant : au deuxieme passage l angle bleu se traverse tout droit.',
    h: ['0000', '0.0.', '000.'],
    m: ['R*R*', '*.*.', 'R*R.'],
    start: { x: 1, z: 0, dir: 0 },
    procs: [7],
    ops: [...MOVE, 'PAINT_B', 'CALL0'],
    colors: ['r', 'b'],
    optimal: 6,
    solution: [['ACT', 'FWD@b', 'RIGHT@r', 'PAINT_B@r', 'FWD', 'CALL0']],
  },
  {
    id: 'l07',
    name: 'CAISSES',
    hint: 'PRENDRE saisit la caisse posee juste devant, POSER la depose devant. Une caisse lachee dans un vide le comble.',
    h: ['00.00'],
    m: ['.C..*'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [8],
    ops: [...MOVE, 'GRAB', 'DROP'],
    colors: [],
    optimal: 7,
    solution: [['GRAB', 'FWD', 'DROP', 'FWD', 'FWD', 'FWD', 'ACT']],
  },
  {
    id: 'l08',
    name: 'ESCALADE',
    hint: 'SAUT ne monte que d une marche. Une caisse posee au bon endroit fait la marche qui manque.',
    h: ['002', '00.'],
    m: ['..*', 'C..'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [8],
    ops: [...MOVE, 'JUMP', 'GRAB', 'DROP'],
    colors: [],
    optimal: 7,
    solution: [['RIGHT', 'GRAB', 'LEFT', 'DROP', 'JUMP', 'JUMP', 'ACT']],
  },
  {
    id: 'l09',
    name: 'SERPENTIN',
    hint: 'Rouge tourne d un cote, bleu de l autre. Une seule boucle doit suffire pour balayer les vingt cinq dalles.',
    h: ['00000', '00000', '00000', '00000', '00000'],
    m: ['****R', 'B***R', 'B***R', 'B***R', 'B****'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [6],
    ops: [...MOVE, 'CALL0'],
    colors: ['r', 'b'],
    optimal: 5,
    solution: [['ACT', 'RIGHT@r', 'LEFT@b', 'FWD', 'CALL0']],
  },
  {
    id: 'l10',
    name: 'PALIERS',
    hint: 'Le motif se repete : deux dalles plates puis une marche. PRINCIPAL est trop court pour l ecrire, P1 ne l est pas.',
    h: ['000111222333'],
    m: ['************'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [3, 6],
    ops: [...MOVE, 'JUMP', 'CALL0', 'CALL1'],
    colors: [],
    optimal: 8,
    solution: [['CALL1', 'CALL0'], ['ACT', 'FWD', 'ACT', 'FWD', 'ACT', 'JUMP']],
  },
  {
    id: 'l11',
    name: 'CHAINE DE MONTAGE',
    hint: 'Trois vides, trois caisses, un seul motif. La boucle doit rester valable meme quand il n y a plus rien a prendre : une instruction qui echoue ne casse pas le programme.',
    h: ['00.0.0.0'],
    m: ['.C.C.C.*'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [7],
    ops: [...MOVE, 'GRAB', 'DROP', 'CALL0'],
    colors: [],
    optimal: 6,
    solution: [['ACT', 'GRAB', 'FWD', 'DROP', 'FWD', 'CALL0']],
  },
  {
    id: 'l12',
    name: 'TOLE ONDULEE',
    hint: 'Plus une seule dalle a la meme hauteur que sa voisine. AVANCER ne sert plus a rien ici.',
    h: ['010101', '101010', '010101', '101010'],
    m: ['*****R', 'B****R', 'B****R', '*****R'],
    start: { x: 0, z: 0, dir: 0 },
    procs: [6],
    ops: [...MOVE, 'JUMP', 'CALL0'],
    colors: ['r', 'b'],
    optimal: 5,
    solution: [['ACT', 'RIGHT@r', 'LEFT@b', 'JUMP', 'CALL0']],
  },
  {
    id: 'l13',
    name: 'DEUXIEME PASSAGE',
    hint: 'Un seul angle est vert. Marquez le au premier tour pour qu au second le drone file tout droit vers l antenne.',
    h: ['0000000', '0...0..', '0...0..', '0...0..', '00000..'],
    m: ['R***G.*', '*...*..', '*...*..', '*...*..', 'R***R..'],
    start: { x: 1, z: 0, dir: 0 },
    procs: [8],
    ops: [...MOVE, 'PAINT_B', 'CALL0'],
    colors: ['r', 'g', 'b'],
    optimal: 7,
    solution: [['ACT', 'FWD@b', 'RIGHT@r', 'RIGHT@g', 'PAINT_B@g', 'FWD', 'CALL0']],
  },
  {
    id: 'l14',
    name: 'SURCHARGE',
    hint: 'Trois anneaux, trois hauteurs, trois couleurs. Rouge tourne, bleu tourne dans l autre sens, vert tourne et monte. Une seule boucle.',
    h: ['00000', '01110', '01210', '01110', '00000'],
    m: ['R*G*R', '*.BR*', '*G***', '*R*R*', 'R***R'],
    start: { x: 3, z: 0, dir: 0 },
    procs: [8, 4, 4],
    ops: [...MOVE, 'JUMP', 'CALL0', 'CALL1', 'CALL2'],
    colors: ['r', 'g', 'b'],
    optimal: 7,
    solution: [['ACT', 'RIGHT@r', 'LEFT@b', 'RIGHT@g', 'JUMP@g', 'FWD', 'CALL0']],
  },
];

export function levelIndexById(id) {
  for (let i = 0; i < LEVELS.length; i++) if (LEVELS[i].id === id) return i;
  return -1;
}
