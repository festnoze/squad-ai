// Level data: one entry per Niveau. Pure data plus a thin cache around
// maze.generateMaze so the same seed always produces the same layout.
import { generateMaze } from './maze.js';

/**
 * Visual/audio theme metadata, shared by render/maze.js, audio.js and hud.js.
 * Colors are plain hex numbers (three.Color-compatible) but this file stays
 * three-free so it can be imported from the Node validation script.
 */
export const THEMES = {
  yellow: {
    label: 'Salles jaunes',
    wall: 0xb7a349,
    wallDark: 0x8f7a2e,
    floor: 0x8a6a2b,
    ceiling: 0xcbb96a,
    tube: 0xfff3c4,
    fog: 0x6b5a22,
    ambient: 0x9c8a3f,
    ambientIntensity: 1.6,
    ceilHeight: 2.7,
    surface: 'carpet',
    fogDensity: 0.028,
  },
  warehouse: {
    label: 'Entrepot',
    wall: 0x6a6a63,
    wallDark: 0x45443f,
    floor: 0x3c3b37,
    ceiling: 0x2c2b28,
    tube: 0xffb35c,
    // Fog colour/density are the dominant factor at typical room distances, not
    // ambientIntensity: a near-black fog colour crushes the far side of every
    // room to near-zero luminance no matter how well the nearby wall is lit
    // (measured mean screen luminance 2.8/255 at the original 0x38352c/0.02,
    // barely moved by ambientIntensity alone; the values below fixed it).
    fog: 0x565143,
    ambient: 0x6b6558,
    ambientIntensity: 2.0,
    ceilHeight: 5.2,
    surface: 'concrete',
    fogDensity: 0.013,
  },
  pipes: {
    label: 'Tuyaux et tunnels',
    wall: 0x585048,
    wallDark: 0x342e29,
    floor: 0x2e2b28,
    ceiling: 0x201d1a,
    tube: 0xff4530,
    // See the warehouse theme's comment: fog, not light, was crushing this one
    // (measured 1.9/255, unmoved by tripling ambientIntensity to 1.6).
    fog: 0x3a3128,
    ambient: 0x4a2f22,
    ambientIntensity: 1.6,
    ceilHeight: 2.4,
    surface: 'metal',
    fogDensity: 0.028,
  },
  electrical: {
    label: 'Sous-sol electrique',
    wall: 0x2c333d,
    wallDark: 0x181c22,
    floor: 0x14171c,
    ceiling: 0x0e1013,
    tube: 0x8fd8ff,
    // See the warehouse theme's comment: fog, not light, was crushing this one
    // (measured 1.4/255, unmoved by more than tripling ambientIntensity to 1.5).
    fog: 0x1e2a38,
    ambient: 0x2b3d52,
    ambientIntensity: 1.5,
    ceilHeight: 2.5,
    surface: 'metal',
    fogDensity: 0.03,
  },
  kitchen: {
    label: 'Cuisine industrielle',
    wall: 0xd7ded9,
    wallDark: 0x9fb0a8,
    floor: 0xb9c6c1,
    ceiling: 0xe9efec,
    tube: 0xdfffe8,
    fog: 0x8ea89e,
    ambient: 0xaebdb6,
    ambientIntensity: 1.8,
    ceilHeight: 2.9,
    surface: 'tile',
    fogDensity: 0.024,
  },
  dark: {
    label: 'Noir absolu',
    wall: 0x201f1d,
    wallDark: 0x121110,
    floor: 0x141312,
    ceiling: 0x0a0908,
    tube: 0x000000,
    fog: 0x050505,
    ambient: 0x0c0b0a,
    ambientIntensity: 0.05,
    ceilHeight: 2.6,
    surface: 'carpet',
    fogDensity: 0.09,
  },
  poolrooms: {
    label: 'Poolrooms',
    wall: 0xdbe9ee,
    wallDark: 0xa9c2cb,
    floor: 0xcfe6ec,
    ceiling: 0xf3fbfd,
    tube: 0xeafcff,
    fog: 0xa9cdd6,
    ambient: 0xbfe0e6,
    ambientIntensity: 2.0,
    ceilHeight: 4.4,
    surface: 'tile',
    fogDensity: 0.016,
    water: true,
  },
  offices: {
    label: 'Bureaux abandonnes',
    wall: 0x7d7a70,
    wallDark: 0x504e47,
    floor: 0x6a655a,
    ceiling: 0x8c8a80,
    tube: 0xeceadf,
    fog: 0x4d4a41,
    ambient: 0x716c5f,
    // See the warehouse theme's comment: measured near-black (8.6/255) at 0.9.
    ambientIntensity: 1.9,
    ceilHeight: 2.5,
    surface: 'carpet',
    fogDensity: 0.03,
  },
  final: {
    label: 'Descente finale',
    wall: 0x585240,
    wallDark: 0x353022,
    floor: 0x403a26,
    ceiling: 0x2c2818,
    tube: 0xfff3c4,
    // See the warehouse theme's comment: fog, not light, was crushing this one
    // (measured 5.0/255, completely unmoved by more than tripling ambientIntensity).
    fog: 0x3d3720,
    ambient: 0x4a4326,
    ambientIntensity: 1.6,
    ceilHeight: 2.6,
    surface: 'metal',
    fogDensity: 0.028,
    // gradient target: colours lerp toward the yellow theme as the player advances
    gradientTo: 'yellow',
  },
};

function entityDef(count, opts = {}) {
  return {
    count,
    speed: opts.speed ?? 2.3,
    patrolSpeed: opts.patrolSpeed ?? 1.5,
    sightRange: opts.sightRange ?? 9,
    hearRangeBase: opts.hearRangeBase ?? 5,
    loseTime: opts.loseTime ?? 6,
    searchTime: opts.searchTime ?? 5,
  };
}

export const LEVELS = [
  {
    id: 0,
    name: 'Niveau 0 - Reveil',
    theme: 'yellow',
    seed: 100001,
    width: 26, height: 26, roomCount: 6, minRoomSize: 4, maxRoomSize: 7, loopChance: 0.1,
    entity: null,
    itemCount: 1, itemType: 'notebook',
    goldSeconds: 90,
    encounterLimit: 0,
    intro: 'Le papier peint suinte une lumiere jaune sale. Aucun bruit, aucune sortie visible. Marchez jusqu a la trouver.',
  },
  {
    id: 1,
    name: 'Niveau 0 - Couloirs sans fin',
    theme: 'yellow',
    seed: 100002,
    width: 30, height: 30, roomCount: 8, minRoomSize: 4, maxRoomSize: 7, loopChance: 0.14,
    entity: entityDef(1, { speed: 1.9, patrolSpeed: 1.2, sightRange: 7, hearRangeBase: 4 }),
    itemCount: 1, itemType: 'notebook',
    goldSeconds: 120,
    encounterLimit: 3,
    intro: 'Quelque chose d autre respire ici. Restez silencieux, marchez, ne courez qu en cas de necessite absolue.',
  },
  {
    id: 2,
    name: 'Niveau 1 - Entrepot',
    theme: 'warehouse',
    seed: 200001,
    width: 34, height: 34, roomCount: 9, minRoomSize: 5, maxRoomSize: 9, loopChance: 0.15,
    entity: entityDef(1, { speed: 2.2, patrolSpeed: 1.5, sightRange: 10, hearRangeBase: 5 }),
    itemCount: 1, itemType: 'notebook',
    goldSeconds: 140,
    encounterLimit: 3,
    intro: 'Des palettes empilees jusqu au plafond. Les allees sont larges, la visibilite aussi: pour vous comme pour elle.',
  },
  {
    id: 3,
    name: 'Niveau 2 - Tuyaux et tunnels',
    theme: 'pipes',
    seed: 300001,
    width: 30, height: 30, roomCount: 10, minRoomSize: 3, maxRoomSize: 5, loopChance: 0.16,
    entity: entityDef(1, { speed: 2.4, patrolSpeed: 1.6, sightRange: 8, hearRangeBase: 6.5 }),
    itemCount: 1, itemType: 'notebook',
    goldSeconds: 150,
    encounterLimit: 3,
    intro: 'Le sol metallique resonne sous chaque pas. Ici, courir revient a hurler votre position.',
  },
  {
    id: 4,
    name: 'Niveau 3 - Sous-sol electrique',
    theme: 'electrical',
    seed: 400001,
    width: 28, height: 28, roomCount: 9, minRoomSize: 3, maxRoomSize: 6, loopChance: 0.14,
    entity: entityDef(1, { speed: 2.3, patrolSpeed: 1.5, sightRange: 8, hearRangeBase: 5.5 }),
    itemCount: 2, itemType: 'notebook',
    goldSeconds: 150,
    encounterLimit: 3,
    intro: 'Des cables denudes courent au sol. Des etincelles trahissent parfois une silhouette dans le noir.',
    sparks: true,
  },
  {
    id: 5,
    name: 'Niveau 4 - Cuisine industrielle',
    theme: 'kitchen',
    seed: 500001,
    width: 32, height: 32, roomCount: 10, minRoomSize: 4, maxRoomSize: 7, loopChance: 0.15,
    entity: entityDef(1, { speed: 2.5, patrolSpeed: 1.7, sightRange: 10, hearRangeBase: 5 }),
    itemCount: 1, itemType: 'notebook',
    goldSeconds: 150,
    encounterLimit: 3,
    intro: 'Inox et carrelage blanc a perte de vue. Les plans de travail se ressemblent tous, la sortie ne ressemblera a rien d autre.',
  },
  {
    id: 6,
    name: 'Niveau 0 - Rappel',
    theme: 'yellow',
    seed: 100003,
    width: 38, height: 38, roomCount: 13, minRoomSize: 4, maxRoomSize: 8, loopChance: 0.16,
    entity: entityDef(1, { speed: 2.6, patrolSpeed: 1.7, sightRange: 9, hearRangeBase: 5.5 }),
    itemCount: 2, itemType: 'notebook',
    goldSeconds: 180,
    encounterLimit: 3,
    intro: 'Le jaune moisi revient, mais le dedale a grandi. Vous reconnaissez l odeur, pas le chemin.',
  },
  {
    id: 7,
    name: 'Niveau 6 - Noir absolu',
    theme: 'dark',
    seed: 600001,
    width: 30, height: 30, roomCount: 10, minRoomSize: 3, maxRoomSize: 6, loopChance: 0.14,
    entity: entityDef(1, { speed: 2.2, patrolSpeed: 1.4, sightRange: 12, hearRangeBase: 6 }),
    itemCount: 3, itemType: 'battery',
    goldSeconds: 170,
    encounterLimit: 4,
    flashlight: true,
    intro: 'Aucune lumiere ici hors la votre. Les piles sont rares: eteignez la lampe des que vous le pouvez.',
  },
  {
    id: 8,
    name: 'Niveau 7 - Poolrooms',
    theme: 'poolrooms',
    seed: 700001,
    width: 36, height: 36, roomCount: 11, minRoomSize: 5, maxRoomSize: 9, loopChance: 0.2,
    entity: entityDef(1, { speed: 2.4, patrolSpeed: 1.6, sightRange: 11, hearRangeBase: 7 }),
    itemCount: 2, itemType: 'notebook',
    goldSeconds: 190,
    encounterLimit: 4,
    intro: 'De l eau immobile a perte de vue, un carrelage qui se repete a l infini. Le son porte loin, tres loin.',
  },
  {
    id: 9,
    name: 'Niveau 1 - Entrepot avance',
    theme: 'warehouse',
    seed: 200002,
    width: 38, height: 38, roomCount: 12, minRoomSize: 5, maxRoomSize: 9, loopChance: 0.16,
    entity: entityDef(1, { speed: 2.9, patrolSpeed: 1.9, sightRange: 11, hearRangeBase: 6 }),
    itemCount: 2, itemType: 'notebook',
    goldSeconds: 190,
    encounterLimit: 3,
    intro: 'Le meme entrepot, mais quelque chose de plus rapide y patrouille desormais.',
  },
  {
    id: 10,
    name: 'Niveau 9 - Bureaux abandonnes',
    theme: 'offices',
    seed: 900001,
    width: 40, height: 40, roomCount: 14, minRoomSize: 3, maxRoomSize: 6, loopChance: 0.18,
    entity: entityDef(2, { speed: 2.4, patrolSpeed: 1.6, sightRange: 9, hearRangeBase: 5.5 }),
    itemCount: 2, itemType: 'notebook',
    goldSeconds: 210,
    encounterLimit: 5,
    intro: 'Des cubicles bas a perte de vue, des papiers au sol. Deux silhouettes s y croisent desormais.',
  },
  {
    id: 11,
    name: 'Niveau Final - Descente',
    theme: 'final',
    seed: 1100001,
    width: 42, height: 42, roomCount: 15, minRoomSize: 4, maxRoomSize: 7, loopChance: 0.15,
    entity: entityDef(1, { speed: 3.3, patrolSpeed: 2.1, sightRange: 10, hearRangeBase: 7 }),
    itemCount: 1, itemType: 'notebook',
    goldSeconds: 220,
    encounterLimit: 4,
    intro: 'Les murs changent de couleur a mesure que vous avancez. Le jaune du debut revient vous chercher. Suivez le bruit, pas la vue.',
    finalLevel: true,
  },
];

const mazeCache = new Map();

/** Lazily build (and cache) the maze for a level index. Deterministic per seed. */
export function getLevelMaze(levelIndex) {
  const def = LEVELS[levelIndex];
  if (!def) throw new Error(`Unknown level index ${levelIndex}`);
  if (mazeCache.has(levelIndex)) return mazeCache.get(levelIndex);
  const maze = generateMaze({
    seed: def.seed,
    width: def.width,
    height: def.height,
    roomCount: def.roomCount,
    minRoomSize: def.minRoomSize,
    maxRoomSize: def.maxRoomSize,
    loopChance: def.loopChance,
    patrolPoints: def.entity ? Math.min(8, def.roomCount - 1) : 0,
    itemCount: def.itemCount,
    itemType: def.itemType,
  });
  mazeCache.set(levelIndex, maze);
  return maze;
}

export function getLevelDef(levelIndex) {
  return LEVELS[levelIndex];
}

export const LEVEL_COUNT = LEVELS.length;
