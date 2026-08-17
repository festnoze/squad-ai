/**
 * Playable championships. Track control points are [x, y, z, width, bank, tag].
 * Akari intentionally omits them: track.js keeps its original authored layout.
 */

const COAST_CONTROL = [
  [-760, 18, 350, 14, 0, 'start'],
  [-520, 18, 350, 14, 0, ''],
  [-260, 20, 342, 13, -4, ''],
  [20, 26, 300, 12, -14, ''],
  [270, 38, 190, 12, -28, ''],
  [430, 52, 10, 11, -38, ''],
  [470, 58, -230, 10, -34, ''],
  [360, 54, -450, 11, -22, ''],
  [120, 44, -560, 12, -8, ''],
  [-150, 30, -550, 13, 6, ''],
  [-390, 14, -455, 12, 24, ''],
  [-550, 8, -300, 11, 34, ''],
  [-610, 10, -100, 10, 28, ''],
  [-560, 16, 80, 11, 14, ''],
  [-700, 18, 210, 13, -5, ''],
];

const PRISM_CONTROL = [
  [-620, 0, 300, 14, 0, 'start'],
  [-350, 8, 330, 13, -8, ''],
  [-100, 35, 270, 11, -25, ''],
  [80, 70, 100, 9, -42, ''],
  [260, 38, -80, 10, 35, ''],
  [520, 5, -40, 13, 18, ''],
  [650, 30, 180, 11, -30, ''],
  [540, 82, 410, 9, -45, ''],
  [280, 110, 500, 10, -24, ''],
  [40, 70, 430, 12, 18, ''],
  [-120, 20, 180, 9, 43, ''],
  [-250, 65, -100, 10, 38, ''],
  [-500, 95, -250, 11, 25, ''],
  [-720, 45, -150, 12, 8, ''],
  [-770, 8, 80, 13, -12, ''],
];

export const LEVELS = [
  {
    id: 'akari',
    number: '01',
    name: 'NEO KYOTO / CIRCUIT AKARI',
    shortName: 'CIRCUIT AKARI',
    location: 'NEO KYOTO',
    theme: 'city',
    difficulty: 'INTERMEDIAIRE',
    distance: '4.0 KM',
    description: 'Neons, viaducs vertigineux et virages releves au-dessus de la megapole.',
    accent: '#22e0ff',
    track: {
      surface: {
        color: 0xdce4f0,
        roughness: 0.82,
        metalness: 0.16,
        normalScale: 1.08,
        tileLength: 26,
      },
      wallSurface: { roughness: 0.56, metalness: 0.62, normalScale: 1.2 },
    },
  },
  {
    id: 'azur',
    number: '02',
    name: 'COTE D AZUR / HORIZON MARIN',
    shortName: 'HORIZON MARIN',
    location: 'COTE D AZUR',
    theme: 'coast',
    difficulty: 'RAPIDE',
    distance: '3.8 KM',
    description: 'Un ruban solaire entre falaises blanches, plages et pleine mer.',
    accent: '#40e8ff',
    track: {
      control: COAST_CONTROL,
      centre: [80, 0],
      pads: [
        { at: 0.13, x: 1.5 }, { at: 0.36, x: -2 }, { at: 0.58, x: 0 },
        { at: 0.79, x: 2 }, { at: 0.94, x: 0 },
      ],
      primary: 0x39e7ff,
      secondary: 0xffc85b,
      wall: 0x172735,
      wallTrim: 0x47758a,
      surface: {
        color: 0xd3d8d0,
        roughness: 0.72,
        metalness: 0.08,
        normalScale: 0.92,
        tileLength: 22,
      },
      wallSurface: { roughness: 0.68, metalness: 0.32, normalScale: 0.86 },
    },
  },
  {
    id: 'prism',
    number: '03',
    name: 'FAILLE PRISMATIQUE / KALEIDOSCOPE',
    shortName: 'KALEIDOSCOPE',
    location: 'FAILLE PRISMATIQUE',
    theme: 'psychedelic',
    difficulty: 'EXPERT',
    distance: '4.3 KM',
    description: 'Relief impossible, portails mouvants et couleurs psychedeliques en fusion.',
    accent: '#ff4df0',
    track: {
      control: PRISM_CONTROL,
      centre: [20, -100],
      pads: [
        { at: 0.1, x: 0 }, { at: 0.31, x: 2.5 }, { at: 0.49, x: -2.5 },
        { at: 0.71, x: 0 }, { at: 0.9, x: 1 },
      ],
      primary: 0xff38df,
      secondary: 0x74ff37,
      wall: 0x18052c,
      wallTrim: 0x5b1a88,
      surface: {
        color: 0xc5d2bd,
        roughness: 0.58,
        metalness: 0.24,
        normalScale: 1.25,
        tileLength: 18,
      },
      wallSurface: { roughness: 0.38, metalness: 0.72, normalScale: 1.32 },
    },
  },
];

export function getLevel(id) {
  return LEVELS.find((level) => level.id === id) || LEVELS[0];
}
