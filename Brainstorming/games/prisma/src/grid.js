/**
 * PRISMA - board model.
 *
 * Pure data, no three.js: the renderer reads this, never the other way round.
 * A cell is a small mutable record; the whole board is one flat array indexed
 * by `row * width + col`.
 */

import { COLOR_R, COLOR_G, COLOR_B, COLOR_WHITE, ROTATIONS } from './levels.js';

export const CELL = {
  EMPTY: 0,
  WALL: 1,
  EMITTER: 2,
  TARGET: 3,
  MIRROR: 4,
  PRISM: 5,
  FILTER: 6,
  COMBINER: 7,
  SPLITTER: 8,
  PORTAL: 9,
};

export const KIND_TO_CELL = {
  mirror: CELL.MIRROR,
  prism: CELL.PRISM,
  filter: CELL.FILTER,
  combiner: CELL.COMBINER,
  splitter: CELL.SPLITTER,
};

export const CELL_TO_KIND = {
  [CELL.MIRROR]: 'mirror',
  [CELL.PRISM]: 'prism',
  [CELL.FILTER]: 'filter',
  [CELL.COMBINER]: 'combiner',
  [CELL.SPLITTER]: 'splitter',
};

/** East, South, West, North. Row indices grow southwards. */
export const DX = [1, 0, -1, 0];
export const DY = [0, 1, 0, -1];

const EMITTER_CHARS = { '>': 0, v: 1, '<': 2, '^': 3 };
const TARGET_CHARS = {
  R: COLOR_R,
  G: COLOR_G,
  B: COLOR_B,
  Y: COLOR_R | COLOR_G,
  C: COLOR_G | COLOR_B,
  M: COLOR_R | COLOR_B,
  W: COLOR_WHITE,
};

export const COLOR_NAMES = {
  0: 'rien',
  1: 'rouge',
  2: 'vert',
  3: 'jaune',
  4: 'bleu',
  5: 'magenta',
  6: 'cyan',
  7: 'blanc',
};

function makeCell() {
  return { type: CELL.EMPTY, rot: 0, mask: 0, dir: 0, fixed: false, link: -1 };
}

/**
 * Builds the board from a level record. Throws on a malformed grid so a typo
 * surfaces as an error screen instead of an unplayable puzzle.
 */
export function createGrid(level) {
  const rows = level.rows;
  const h = rows.length;
  const w = rows[0].length;
  for (let y = 0; y < h; y++) {
    if (rows[y].length !== w) {
      throw new Error(`Niveau ${level.id}: la ligne ${y} fait ${rows[y].length} cases au lieu de ${w}.`);
    }
  }

  const cells = new Array(w * h);
  for (let i = 0; i < w * h; i++) cells[i] = makeCell();

  const emitters = [];
  const targets = [];
  const portals = [];

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const ch = rows[y][x];
      const cell = cells[y * w + x];
      if (ch === '.') continue;
      if (ch === '#') {
        cell.type = CELL.WALL;
        cell.fixed = true;
      } else if (ch in EMITTER_CHARS) {
        cell.type = CELL.EMITTER;
        cell.fixed = true;
        cell.dir = EMITTER_CHARS[ch];
        cell.mask = COLOR_WHITE;
        emitters.push({ x, y, dir: cell.dir, mask: COLOR_WHITE });
      } else if (ch in TARGET_CHARS) {
        cell.type = CELL.TARGET;
        cell.fixed = true;
        cell.mask = TARGET_CHARS[ch];
        targets.push({ x, y, mask: cell.mask, index: targets.length });
      } else if (ch >= '0' && ch <= '3') {
        cell.type = CELL.MIRROR;
        cell.fixed = true;
        cell.rot = Number(ch);
      } else if (ch === 'p') {
        cell.type = CELL.PORTAL;
        cell.fixed = true;
        portals.push(y * w + x);
      } else {
        throw new Error(`Niveau ${level.id}: caractere inconnu "${ch}" en (${x}, ${y}).`);
      }
    }
  }

  if (portals.length % 2 !== 0) {
    throw new Error(`Niveau ${level.id}: ${portals.length} portails, il en faut un nombre pair.`);
  }
  for (let i = 0; i < portals.length; i += 2) {
    cells[portals[i]].link = portals[i + 1];
    cells[portals[i + 1]].link = portals[i];
  }
  if (emitters.length === 0) throw new Error(`Niveau ${level.id}: aucun emetteur.`);
  if (targets.length === 0) throw new Error(`Niveau ${level.id}: aucune cible.`);

  return {
    level,
    w,
    h,
    cells,
    emitters,
    targets,
    inventory: { ...level.inventory },
    idx: (x, y) => y * w + x,
  };
}

export function inBounds(grid, x, y) {
  return x >= 0 && y >= 0 && x < grid.w && y < grid.h;
}

export function cellAt(grid, x, y) {
  return grid.cells[y * grid.w + x];
}

/** A cell can host a component only if it is bare floor. */
export function isFree(grid, x, y) {
  if (!inBounds(grid, x, y)) return false;
  return grid.cells[y * grid.w + x].type === CELL.EMPTY;
}

export function isPlaced(grid, x, y) {
  if (!inBounds(grid, x, y)) return false;
  const cell = grid.cells[y * grid.w + x];
  return !cell.fixed && cell.type !== CELL.EMPTY;
}

export function countPlaced(grid, kind) {
  const type = KIND_TO_CELL[kind];
  let n = 0;
  for (let i = 0; i < grid.cells.length; i++) {
    const c = grid.cells[i];
    if (!c.fixed && c.type === type) n++;
  }
  return n;
}

export function totalPlaced(grid) {
  let n = 0;
  for (let i = 0; i < grid.cells.length; i++) {
    const c = grid.cells[i];
    if (!c.fixed && c.type !== CELL.EMPTY) n++;
  }
  return n;
}

export function remaining(grid, kind) {
  return (grid.inventory[kind] || 0) - countPlaced(grid, kind);
}

/** Returns 'ok' or a short French reason the placement was refused. */
export function canPlace(grid, x, y, kind) {
  if (!inBounds(grid, x, y)) return 'hors du plateau';
  if (!KIND_TO_CELL[kind]) return 'composant inconnu';
  if (!isFree(grid, x, y)) return 'case occupee';
  if (remaining(grid, kind) <= 0) return 'stock epuise';
  return 'ok';
}

export function place(grid, x, y, kind, rot = 0) {
  if (canPlace(grid, x, y, kind) !== 'ok') return false;
  const cell = grid.cells[y * grid.w + x];
  cell.type = KIND_TO_CELL[kind];
  cell.rot = rot % ROTATIONS[kind];
  cell.fixed = false;
  cell.mask = 0;
  return true;
}

export function remove(grid, x, y) {
  if (!isPlaced(grid, x, y)) return false;
  const cell = grid.cells[y * grid.w + x];
  cell.type = CELL.EMPTY;
  cell.rot = 0;
  return true;
}

export function rotate(grid, x, y, step = 1) {
  if (!isPlaced(grid, x, y)) return false;
  const cell = grid.cells[y * grid.w + x];
  const kind = CELL_TO_KIND[cell.type];
  const n = ROTATIONS[kind];
  cell.rot = (cell.rot + step + n * 2) % n;
  return true;
}

/** Compact snapshot of the placed components only: what undo stores. */
export function snapshot(grid) {
  const out = [];
  for (let i = 0; i < grid.cells.length; i++) {
    const c = grid.cells[i];
    if (!c.fixed && c.type !== CELL.EMPTY) out.push(i, c.type, c.rot);
  }
  return out;
}

export function restore(grid, snap) {
  for (let i = 0; i < grid.cells.length; i++) {
    const c = grid.cells[i];
    if (!c.fixed && c.type !== CELL.EMPTY) {
      c.type = CELL.EMPTY;
      c.rot = 0;
    }
  }
  for (let i = 0; i < snap.length; i += 3) {
    const c = grid.cells[snap[i]];
    c.type = snap[i + 1];
    c.rot = snap[i + 2];
    c.fixed = false;
  }
}

export function sameSnapshot(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

export function clearPlaced(grid) {
  restore(grid, []);
}

/** World position of a cell centre, board centred on the origin. */
export function cellToWorldX(grid, x) {
  return (x - (grid.w - 1) / 2);
}

export function cellToWorldZ(grid, y) {
  return (y - (grid.h - 1) / 2);
}

export function worldToCellX(grid, wx) {
  return Math.round(wx + (grid.w - 1) / 2);
}

export function worldToCellY(grid, wz) {
  return Math.round(wz + (grid.h - 1) / 2);
}
