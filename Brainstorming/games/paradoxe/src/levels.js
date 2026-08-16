/**
 * PARADOXE - level data.
 *
 * Every arena is two ASCII grids of identical dimensions:
 *
 *   heights   ' ' vide (trou)   '0' sol   '1' bloc de 1   '2' bloc de 2   '#' mur
 *   marks     '.' rien          'S' depart               'X' sortie
 *             'K' caisse        'T'/'t' paire de teleporteurs
 *             '1'..'6' bouton a maintenir du groupe n
 *             'a'..'f' plaque a poids du groupe 1..6
 *             'A'..'F' porte du groupe 1..6
 *             '~' sol fragile (s'effondre apres le passage)
 *
 * A group opens when `require[group]` of its triggers are active at once
 * (default 1). Mark rows may be shorter than the grid: they are padded.
 */

const PIT = -1;

const HEIGHT_CHARS = { ' ': PIT, '.': 0, '0': 0, '1': 1, '2': 2, '#': 3 };

/** Raw definitions, in play order. */
export const LEVEL_DEFS = [
  {
    name: 'Se tenir la porte',
    hint: 'Un bouton ouvre la porte tant qu on le maintient. Personne ne peut etre a deux endroits... sauf toi.',
    seconds: 12,
    maxClones: 3,
    medalClones: 1,
    heights: [
      '#############',
      '#00000#00000#',
      '#00000000000#',
      '#00000#00000#',
      '#00000#00000#',
      '#00000#00000#',
      '#############',
    ],
    marks: [
      '',
      '',
      '..S...A....X.',
      '',
      '..1',
    ],
  },
  {
    name: 'Marchepied',
    hint: 'Un clone est solide. On peut lui monter sur la tete.',
    seconds: 14,
    maxClones: 3,
    medalClones: 1,
    heights: [
      '###############',
      '#0000000000000#',
      '#0000000000000#',
      '#0000000022220#',
      '#0000000022220#',
      '#0000000022220#',
      '#0000000000000#',
      '#0000000000000#',
      '###############',
    ],
    marks: [
      '',
      '',
      '..S',
      '',
      '..........X',
    ],
  },
  {
    name: 'Relais de caisse',
    hint: 'E prend et pose une caisse. Une plaque reste enfoncee sous une caisse, pas sous un corps.',
    seconds: 16,
    maxClones: 3,
    medalClones: 1,
    heights: [
      '###############',
      '#00000#00000#0#',
      '#00000#00000#0#',
      '#00000000000#0#',
      '#0000000000000#',
      '#00000#00000#0#',
      '#00000#00000#0#',
      '#00000#00000#0#',
      '###############',
    ],
    marks: [
      '',
      '.......K',
      '',
      '..S...A',
      '..1.........BX',
      '',
      '..........b',
    ],
  },
  {
    name: 'Double garde',
    hint: 'Deux portes en serie: il faut deux mains, donc deux passes.',
    seconds: 15,
    maxClones: 4,
    medalClones: 2,
    heights: [
      '#################',
      '#00000#00000#000#',
      '#00000#00000#000#',
      '#00000000000#000#',
      '#00000#00000#000#',
      '#00000#000000000#',
      '#00000#00000#000#',
      '#00000#00000#000#',
      '#################',
    ],
    marks: [
      '',
      '',
      '..S...........X',
      '......A',
      '',
      '............B',
      '',
      '..1.....2',
    ],
  },
  {
    name: 'Deux poids',
    hint: 'Deux caisses, deux plaques, un seul chronometre.',
    seconds: 14,
    maxClones: 4,
    medalClones: 1,
    heights: [
      '#################',
      '#000000000000000#',
      '#000000000000000#',
      '#000000000000000#',
      '########0########',
      '#000000000000000#',
      '########0########',
      '#000000000000000#',
      '#000000000000000#',
      '#000000000000000#',
      '#################',
    ],
    marks: [
      '',
      '.......X',
      '',
      '',
      '........A',
      '',
      '........B',
      '..K..........K',
      '.......S',
      '.....a.....b',
    ],
  },
  {
    name: 'Passage instantane',
    hint: 'Les teleporteurs relient deux dalles. Ils ne se soucient pas du temps.',
    seconds: 14,
    maxClones: 3,
    medalClones: 1,
    heights: [
      '#################',
      '#00000#000000000#',
      '#00000#000000000#',
      '#00000#000000000#',
      '#00000#0000######',
      '#00000#0000#0000#',
      '#00000#000000000#',
      '#00000#0000#0000#',
      '#00000#0000#0000#',
      '#00000#0000#0000#',
      '#################',
    ],
    marks: [
      '',
      '',
      '..S......t',
      '....T',
      '',
      '',
      '...........A',
      '',
      '..1...........X',
    ],
  },
  {
    name: 'Le pont qui s efface',
    hint: 'Les dalles claires cedent apres le passage. Chaque passe use son pont.',
    seconds: 15,
    maxClones: 3,
    medalClones: 1,
    heights: [
      '#################',
      '#00000000000#000#',
      '#00000000000#000#',
      '#000000000000000#',
      '#00000000000#000#',
      '#00000000000#000#',
      '#    0    0     #',
      '#    0    0     #',
      '#    0    0     #',
      '#000000000000000#',
      '#000000000000000#',
      '#000000000000000#',
      '#################',
    ],
    marks: [
      '',
      '',
      '..1',
      '............A',
      '..............X',
      '',
      '.....~....~',
      '.....~....~',
      '.....~....~',
      '',
      '..S',
    ],
  },
  {
    name: 'Aiguillage',
    hint: 'Trois salles, trois boutons, une seule sortie.',
    seconds: 15,
    maxClones: 5,
    medalClones: 3,
    heights: [
      '#################',
      '#00000#00000#000#',
      '#00000#00000#000#',
      '#00000000000#000#',
      '#00000#00000#000#',
      '#00000#00000##0##',
      '#00000#00000#000#',
      '#00000#000000000#',
      '#00000#00000#000#',
      '#00000#00000#000#',
      '#00000#00000#000#',
      '#00000#00000#000#',
      '#################',
    ],
    marks: [
      '',
      '..S...........X',
      '',
      '......A',
      '',
      '..............C',
      '',
      '............B',
      '',
      '..............3',
      '..1.....2',
    ],
  },
  {
    name: 'Echafaudage',
    hint: 'Une passe tient la porte, une autre sert de marche.',
    seconds: 16,
    maxClones: 4,
    medalClones: 2,
    heights: [
      '#################',
      '#00000#000000000#',
      '#00000#000000000#',
      '#00000#002222000#',
      '#00000#002222000#',
      '#000000000000000#',
      '#00000#000000000#',
      '#00000#000000000#',
      '#00000#000000000#',
      '#00000#000000000#',
      '#################',
    ],
    marks: [
      '',
      '',
      '..S',
      '..........X',
      '',
      '......A',
      '',
      '',
      '..1',
    ],
  },
  {
    name: 'Triple appui',
    hint: 'Cette porte demande trois appuis simultanes.',
    seconds: 13,
    maxClones: 5,
    medalClones: 3,
    require: { 1: 3 },
    heights: [
      '#################',
      '#000000000000#00#',
      '#000000000000#00#',
      '#000000000000000#',
      '#000000000000#00#',
      '#000000000000#00#',
      '#000000000000#00#',
      '#000000000000#00#',
      '#000000000000#00#',
      '#000000000000#00#',
      '#################',
    ],
    marks: [
      '',
      '',
      '..1',
      '.............A',
      '',
      '.......1......X',
      '',
      '',
      '..S.......1',
    ],
  },
  {
    name: 'Navette',
    hint: 'Une caisse traverse le teleporteur avec celui qui la porte.',
    seconds: 18,
    maxClones: 4,
    medalClones: 1,
    heights: [
      '#################',
      '#0000000#0000000#',
      '#0000000#0000000#',
      '#0000000#0000000#',
      '###0#######0#####',
      '#0000000#0000000#',
      '#0000000#0000000#',
      '#0000000#0000000#',
      '#0000000#0000000#',
      '#0000000#0000000#',
      '#################',
    ],
    marks: [
      '',
      '.....X.......K',
      '',
      '',
      '...B.......A',
      '',
      '',
      '.....b.......1',
      '...T........t',
      '..S',
    ],
  },
  {
    name: 'Deux mains, une caisse',
    hint: 'Maintenir a deux, porter a trois.',
    seconds: 18,
    maxClones: 4,
    medalClones: 2,
    require: { 1: 2 },
    heights: [
      '#################',
      '#00000000#000000#',
      '#00000000#000000#',
      '####0#####000000#',
      '#00000000#000000#',
      '#00000000#000000#',
      '#000000000000000#',
      '#00000000#000000#',
      '#00000000#000000#',
      '#00000000#000000#',
      '#################',
    ],
    marks: [
      '',
      '....X........K',
      '',
      '....B',
      '',
      '..1.....1',
      '.........A',
      '',
      '.....b',
      '..S',
    ],
  },
  {
    name: 'Trois ponts',
    hint: 'Trois ponts fragiles, deux appuis a tenir de l autre cote.',
    seconds: 16,
    maxClones: 4,
    medalClones: 2,
    require: { 1: 2 },
    heights: [
      '#################',
      '#000000000000#00#',
      '#000000000000#00#',
      '#000000000000000#',
      '#000000000000#00#',
      '#000000000000#00#',
      '#   0   0   0   #',
      '#   0   0   0   #',
      '#   0   0   0   #',
      '#000000000000000#',
      '#000000000000000#',
      '#000000000000000#',
      '#################',
    ],
    marks: [
      '',
      '',
      '..1......1',
      '.............A',
      '..............X',
      '',
      '....~...~...~',
      '....~...~...~',
      '....~...~...~',
      '',
      '........S',
    ],
  },
  {
    name: 'Paradoxe final',
    hint: 'Tenir, porter, poser, grimper. Quatre passes, une seule ligne de temps.',
    seconds: 20,
    maxClones: 5,
    medalClones: 3,
    heights: [
      '#################',
      '#00000#000000000#',
      '#00000#022220000#',
      '#00000#022220000#',
      '#000000000000000#',
      '#00000#000000000#',
      '#00000#####0#####',
      '#00000#000000000#',
      '###0###000000000#',
      '#00000#000000000#',
      '#00000#000000000#',
      '#00000#000000000#',
      '#################',
    ],
    marks: [
      '',
      '',
      '.........X',
      '..T',
      '',
      '',
      '...........B',
      '',
      '...A',
      '.............K',
      '..1.......b...t',
      '..S',
    ],
  },
];

function padRow(row, w) {
  const s = row || '';
  return s.length >= w ? s.slice(0, w) : s + '.'.repeat(w - s.length);
}

/**
 * Turn a raw definition into the typed structures the simulation reads.
 * Throws with a precise message when the grids are malformed: a silent size
 * mismatch would produce an unsolvable arena.
 */
export function parseLevel(def, index) {
  const rows = def.heights;
  const h = rows.length;
  const w = rows[0].length;
  for (let z = 0; z < h; z++) {
    if (rows[z].length !== w) {
      throw new Error(
        'Niveau ' + (index + 1) + ' (' + def.name + '): ligne ' + z + ' fait ' + rows[z].length + ' au lieu de ' + w,
      );
    }
  }

  const height = new Int8Array(w * h);
  const fragile = new Uint8Array(w * h);
  const level = {
    index,
    name: def.name,
    hint: def.hint,
    w,
    h,
    height,
    fragile,
    spawn: null,
    exit: null,
    buttons: [],
    plates: [],
    doors: [],
    crateSpawns: [],
    teleports: [],
    require: new Int8Array(8).fill(1),
    seconds: def.seconds,
    ticks: Math.round(def.seconds * 60),
    maxClones: def.maxClones,
    medalClones: def.medalClones,
  };

  if (def.require) {
    for (const key of Object.keys(def.require)) level.require[Number(key)] = def.require[key];
  }

  for (let z = 0; z < h; z++) {
    for (let x = 0; x < w; x++) {
      const c = rows[z][x];
      const v = HEIGHT_CHARS[c];
      if (v === undefined) {
        throw new Error('Niveau ' + (index + 1) + ': caractere de hauteur inconnu "' + c + '" en ' + x + ',' + z);
      }
      height[z * w + x] = v;
    }
  }

  let teleA = null;
  let teleB = null;
  const marks = [];
  for (let z = 0; z < h; z++) marks.push(padRow(def.marks[z], w));

  for (let z = 0; z < h; z++) {
    for (let x = 0; x < w; x++) {
      const c = marks[z][x];
      if (c === '.' || c === ' ') continue;
      if (c === 'S') level.spawn = { x, z };
      else if (c === 'X') level.exit = { x, z };
      else if (c === 'K') level.crateSpawns.push({ x, z });
      else if (c === 'T') teleA = { x, z };
      else if (c === 't') teleB = { x, z };
      else if (c === '~') fragile[z * w + x] = 1;
      else if (c >= '1' && c <= '6') level.buttons.push({ x, z, group: c.charCodeAt(0) - 48 });
      else if (c >= 'a' && c <= 'f') level.plates.push({ x, z, group: c.charCodeAt(0) - 96 });
      else if (c >= 'A' && c <= 'F') level.doors.push({ x, z, group: c.charCodeAt(0) - 64 });
      else throw new Error('Niveau ' + (index + 1) + ': marque inconnue "' + c + '" en ' + x + ',' + z);
    }
  }

  if (teleA && teleB) {
    level.teleports.push({ x: teleA.x, z: teleA.z, tx: teleB.x, tz: teleB.z });
    level.teleports.push({ x: teleB.x, z: teleB.z, tx: teleA.x, tz: teleA.z });
  }

  if (!level.spawn) throw new Error('Niveau ' + (index + 1) + ': pas de depart "S"');
  if (!level.exit) throw new Error('Niveau ' + (index + 1) + ': pas de sortie "X"');
  if (level.crateSpawns.length > 8) throw new Error('Niveau ' + (index + 1) + ': trop de caisses');

  return level;
}

/** All levels, parsed once at module load so authoring mistakes fail loudly. */
export const LEVELS = LEVEL_DEFS.map(parseLevel);

export const LEVEL_COUNT = LEVELS.length;
