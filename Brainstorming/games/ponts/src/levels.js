/**
 * PONTS DE FORTUNE - level data.
 *
 * A level is pure data: the geometry of the ravine in grid coordinates, what
 * may be built where, how many credits, and what has to cross. Nothing here
 * knows about three.js or about the solver.
 *
 * Grid coordinates: `col` runs left to right, `row` 0 is the roadway level and
 * positive rows are above it. World conversion lives in the two helpers below.
 */

import { GRID, DECK_Y } from './config.js';

/**
 * @typedef Level
 * @property {string} key           storage key, stable forever
 * @property {string} name
 * @property {string} brief         one line of framing, shown on the level card
 * @property {string} hint          the idea the level is about
 * @property {number} left          column of the left cliff edge (anchored)
 * @property {number} right         column of the right cliff edge (anchored)
 * @property {number} cols          last column of the world strip
 * @property {number} rowMin
 * @property {number} rowMax
 * @property {number|null} ceilRow  nothing may be built above this row
 * @property {Array<[number,number]>} anchors extra fixed points
 * @property {Array<[number,number]>} piers   anchors resting on a stone pier
 * @property {Array<[number,number]>} masts   anchors on top of a steel mast
 * @property {number} budget
 * @property {string[]} convoy      vehicle keys, in order
 * @property {string[]} allow       material keys usable here
 */

const ALL = ['wood', 'steel', 'cable', 'road'];

/** Approach columns kept on each side of the gap so the convoy has a run up. */
const APPROACH = 7;

function level(spec) {
  const left = APPROACH;
  const right = APPROACH + spec.span;
  return {
    key: spec.key,
    name: spec.name,
    brief: spec.brief,
    hint: spec.hint,
    left,
    right,
    cols: right + APPROACH,
    rowMin: spec.rowMin !== undefined ? spec.rowMin : -6,
    rowMax: spec.rowMax !== undefined ? spec.rowMax : 6,
    ceilRow: spec.ceilRow !== undefined ? spec.ceilRow : null,
    anchors: (spec.anchors || []).map((a) => [left + a[0], a[1]]),
    piers: (spec.piers || []).map((a) => [left + a[0], a[1]]),
    masts: (spec.masts || []).map((a) => [left + a[0], a[1]]),
    budget: spec.budget,
    convoy: spec.convoy,
    allow: spec.allow || ALL,
    span: spec.span,
  };
}

export const LEVELS = [
  level({
    key: 'p01', name: 'LE PREMIER FRANCHISSEMENT', span: 3,
    brief: 'Douze metres de vide, une voiture, du bois et de la route.',
    hint: 'La route porte les roues, elle ne se porte pas elle meme.',
    budget: 240, convoy: ['car'], allow: ['wood', 'road'],
    rowMin: -4, rowMax: 4,
  }),
  level({
    key: 'p02', name: 'LE TRIANGLE', span: 4,
    brief: 'Un metre de plus et le tablier plie. Rigidifiez-le.',
    hint: 'Un carre se deforme, un triangle non. Croisez vos poutres.',
    budget: 360, convoy: ['car'], allow: ['wood', 'road'],
    rowMin: -4, rowMax: 4,
  }),
  level({
    key: 'p03', name: 'LA CORDE RAIDE', span: 5,
    brief: 'Deux pylones sur les rives. Le cable coute presque rien.',
    hint: 'Un cable tire, il ne pousse jamais. Suspendez le tablier.',
    budget: 235, convoy: ['car'], allow: ['wood', 'cable', 'road'],
    anchors: [[0, 3], [5, 3]], masts: [[0, 3], [5, 3]],
    rowMin: -4, rowMax: 5,
  }),
  level({
    key: 'p04', name: 'POIDS LOURD', span: 4,
    brief: 'Cinq tonnes. Le bois va crier avant de rompre.',
    hint: 'L acier coute trois fois plus et tient quatre fois plus.',
    budget: 520, convoy: ['truck'],
    rowMin: -5, rowMax: 5,
  }),
  level({
    key: 'p05', name: 'LE PILIER', span: 8,
    brief: 'Trente-deux metres, mais un pilier de pierre au milieu.',
    hint: 'Un appui central coupe la portee en deux. Servez-vous en.',
    budget: 740, convoy: ['car', 'truck'],
    anchors: [[4, 0]], piers: [[4, 0]],
    rowMin: -6, rowMax: 5,
  }),
  level({
    key: 'p06', name: 'SOUS LE TUNNEL', span: 5,
    brief: 'Le rocher descend juste au dessus du tablier.',
    hint: 'Rien au dessus de la route: toute la structure passe dessous.',
    budget: 560, convoy: ['truck'], ceilRow: 0,
    rowMin: -6, rowMax: 0,
  }),
  level({
    key: 'p07', name: 'DEUX TRAVEES', span: 10,
    brief: 'Deux piliers, quarante metres, un convoi mixte.',
    hint: 'Chaque travee est un pont a part entiere.',
    budget: 900, convoy: ['truck', 'car'],
    anchors: [[3, 0], [7, 0]], piers: [[3, 0], [7, 0]],
    rowMin: -6, rowMax: 5,
  }),
  level({
    key: 'p08', name: 'LE CONVOI', span: 6,
    brief: 'Trois vehicules a la file. La charge s additionne.',
    hint: 'Dimensionnez pour le pire instant, pas pour le premier.',
    budget: 700, convoy: ['truck', 'truck', 'car'],
    rowMin: -6, rowMax: 5,
  }),
  level({
    key: 'p09', name: 'LE GRAND VIDE', span: 8,
    brief: 'Trente-deux metres sans le moindre appui.',
    hint: 'Une poutre longue flambe. Fractionnez la compression.',
    budget: 880, convoy: ['car', 'truck'],
    rowMin: -6, rowMax: 6,
  }),
  level({
    key: 'p10', name: 'SUSPENDU', span: 9,
    brief: 'Deux pylones de vingt metres. A vous de tendre la toile.',
    hint: 'Cables en chaine entre les pylones, suspentes verticales dessous.',
    budget: 840, convoy: ['truck'],
    anchors: [[0, 5], [9, 5]], masts: [[0, 5], [9, 5]],
    rowMin: -5, rowMax: 6,
  }),
  level({
    key: 'p11', name: 'LE DEFILE', span: 7,
    brief: 'Une corniche au dessus, le vide juste en dessous.',
    hint: 'Peu de place en hauteur comme en profondeur: soyez compact.',
    budget: 720, convoy: ['truck', 'truck'], ceilRow: 2,
    rowMin: -4, rowMax: 2,
  }),
  level({
    key: 'p12', name: 'LA GRANDE TRAVERSEE', span: 11,
    brief: 'Quarante-quatre metres, un pilier, et pas un credit de trop.',
    hint: 'Deux travees de six cases, chacune impeccable.',
    budget: 1100, convoy: ['truck', 'truck', 'car'],
    anchors: [[5, 0]], piers: [[5, 0]],
    rowMin: -6, rowMax: 6,
  }),
  level({
    key: 'p13', name: 'VERTIGE', span: 10,
    brief: 'Quarante metres, un plafond bas, deux camions.',
    hint: 'Sous le tablier, la compression devient votre seul allie.',
    budget: 1040, convoy: ['truck', 'car', 'truck'], ceilRow: 1,
    rowMin: -7, rowMax: 1,
  }),
  level({
    key: 'p14', name: 'LE DERNIER PONT', span: 13,
    brief: 'Cinquante-deux metres. Tout ce que vous avez appris, en une fois.',
    hint: 'Suspension pour la portee, treillis pour la rigidite.',
    budget: 1300, convoy: ['truck', 'truck', 'truck'],
    anchors: [[0, 6], [13, 6]], masts: [[0, 6], [13, 6]],
    rowMin: -6, rowMax: 7,
  }),
];

export function levelByKey(key) {
  for (let i = 0; i < LEVELS.length; i++) if (LEVELS[i].key === key) return LEVELS[i];
  return null;
}

/** World X of a grid column. The gap is centred on the origin. */
export function colToX(level, col) {
  return (col - level.cols * 0.5) * GRID;
}

export function rowToY(row) {
  return DECK_Y + row * GRID;
}

export function xToCol(level, x) {
  return x / GRID + level.cols * 0.5;
}

export function yToRow(y) {
  return (y - DECK_Y) / GRID;
}

/** True when a joint may exist at this grid point. */
export function canPlaceNode(level, col, row) {
  if (col < level.left || col > level.right) return false;
  if (row < level.rowMin || row > level.rowMax) return false;
  if (level.ceilRow !== null && row > level.ceilRow) return false;
  return true;
}

/** All fixed points of a level, deck edges included. */
export function anchorPoints(level) {
  const out = [[level.left, 0], [level.right, 0]];
  for (let i = 0; i < level.anchors.length; i++) {
    const a = level.anchors[i];
    let dup = false;
    for (let j = 0; j < out.length; j++) if (out[j][0] === a[0] && out[j][1] === a[1]) dup = true;
    if (!dup) out.push([a[0], a[1]]);
  }
  return out;
}
