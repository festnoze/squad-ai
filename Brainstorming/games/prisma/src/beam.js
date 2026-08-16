/**
 * PRISMA - beam propagation.
 *
 * The beam walks the board cell by cell in the four cardinal directions. Every
 * travelling packet carries an RGB mask (three bits) and an intensity.
 *
 * Two safety nets, both mandatory:
 *   - a visited table keyed by (cell, direction, mask) cuts any mirror loop the
 *     first time it repeats, otherwise a ring of mirrors freezes the tab;
 *   - a hard segment budget stops runaway splitter cascades.
 *
 * Combiners need a beam that does not exist yet when they are first reached, so
 * the whole propagation is run again until the set of combiner inputs stops
 * growing. The inputs only ever gain bits, so this always converges (Kleene
 * iteration on a monotone operator), in practice in two or three passes.
 */

import { CELL, DX, DY } from './grid.js';
import { COLOR_R, COLOR_G, COLOR_B } from './levels.js';

const MAX_SEGMENTS = 2400;
const MAX_PASSES = 12;
const MIN_INTENSITY = 0.045;
const SPLIT_LOSS = 0.5;

/** [left, straight, right] colour for each prism rotation. */
const PRISM_PERM = [
  [COLOR_R, COLOR_G, COLOR_B],
  [COLOR_G, COLOR_B, COLOR_R],
  [COLOR_B, COLOR_R, COLOR_G],
];

const FILTER_MASK = [COLOR_R, COLOR_G, COLOR_B];

function popcount(m) {
  return (m & 1) + ((m >> 1) & 1) + ((m >> 2) & 1);
}

export function createSolver(grid) {
  const w = grid.w;
  const h = grid.h;
  const cellCount = w * h;
  const cap = MAX_SEGMENTS;

  // Segment stream: a segment always spans one cell step, from (x, y) towards
  // dir. Flat typed arrays so a solve allocates nothing.
  const segX = new Int16Array(cap);
  const segY = new Int16Array(cap);
  const segDir = new Uint8Array(cap);
  const segMask = new Uint8Array(cap);
  const segInt = new Float32Array(cap);

  const qX = new Int16Array(cap);
  const qY = new Int16Array(cap);
  const qDir = new Uint8Array(cap);
  const qMask = new Uint8Array(cap);
  const qInt = new Float32Array(cap);

  const visited = new Uint8Array(cellCount * 32); // (cell * 4 + dir) * 8 + mask
  const combMask = new Uint8Array(cellCount);
  const combInt = new Float32Array(cellCount);
  const pendMask = new Uint8Array(cellCount);
  const pendInt = new Float32Array(cellCount);

  const targetGot = new Uint8Array(grid.targets.length);
  const targetLit = new Uint8Array(grid.targets.length);
  const targetExact = new Uint8Array(grid.targets.length);
  const cellEnergy = new Float32Array(cellCount * 4); // r, g, b, intensity per cell

  let segCount = 0;
  let head = 0;
  let tail = 0;
  let truncated = false;

  const result = {
    segX,
    segY,
    segDir,
    segMask,
    segInt,
    count: 0,
    targetGot,
    targetLit,
    litCount: 0,
    totalTargets: grid.targets.length,
    cellEnergy,
    truncated: false,
    solved: false,
  };

  function push(x, y, dir, mask, intensity) {
    if (mask === 0 || intensity < MIN_INTENSITY) return;
    if (tail >= cap) {
      truncated = true;
      return;
    }
    qX[tail] = x;
    qY[tail] = y;
    qDir[tail] = dir;
    qMask[tail] = mask;
    qInt[tail] = intensity;
    tail++;
  }

  function paint(index, mask, intensity) {
    const o = index * 4;
    if (mask & COLOR_R) cellEnergy[o] = Math.max(cellEnergy[o], intensity);
    if (mask & COLOR_G) cellEnergy[o + 1] = Math.max(cellEnergy[o + 1], intensity);
    if (mask & COLOR_B) cellEnergy[o + 2] = Math.max(cellEnergy[o + 2], intensity);
    cellEnergy[o + 3] = Math.max(cellEnergy[o + 3], intensity);
  }

  function runPass() {
    visited.fill(0);
    pendMask.fill(0);
    pendInt.fill(0);
    targetGot.fill(0);
    targetExact.fill(0);
    cellEnergy.fill(0);
    segCount = 0;
    head = 0;
    tail = 0;

    for (let i = 0; i < grid.emitters.length; i++) {
      const e = grid.emitters[i];
      push(e.x, e.y, e.dir, e.mask, 1);
      paint(e.y * w + e.x, e.mask, 1);
    }
    // Combiner outputs come from the previous pass: seeding them here is what
    // lets a merged beam travel on this pass.
    for (let i = 0; i < cellCount; i++) {
      if (combMask[i] === 0) continue;
      const cell = grid.cells[i];
      if (cell.type !== CELL.COMBINER) continue;
      push(i % w, (i / w) | 0, cell.rot, combMask[i], combInt[i]);
    }

    while (head < tail) {
      const x = qX[head];
      const y = qY[head];
      const dir = qDir[head];
      const mask = qMask[head];
      const intensity = qInt[head];
      head++;

      const nx = x + DX[dir];
      const ny = y + DY[dir];
      const inside = nx >= 0 && ny >= 0 && nx < w && ny < h;
      let index = -1;

      if (inside) {
        index = ny * w + nx;
        const key = (index * 4 + dir) * 8 + mask;
        if (visited[key]) continue;
        visited[key] = 1;
      }

      if (segCount >= cap) {
        truncated = true;
        break;
      }
      segX[segCount] = x;
      segY[segCount] = y;
      segDir[segCount] = dir;
      segMask[segCount] = mask;
      segInt[segCount] = intensity;
      segCount++;

      if (!inside) continue;
      paint(index, mask, intensity);

      const cell = grid.cells[index];
      const entry = (dir + 2) & 3;

      switch (cell.type) {
        case CELL.EMPTY:
          push(nx, ny, dir, mask, intensity);
          break;

        case CELL.WALL:
        case CELL.EMITTER:
          break;

        case CELL.TARGET: {
          // A target is lit by ONE beam of exactly the right colour. Two beams
          // of different colours landing on it do not add up: that is the whole
          // reason the combiner exists.
          const ti = cellTargetIndex(index);
          if (ti >= 0) {
            if (popcount(mask) > popcount(targetGot[ti])) targetGot[ti] = mask;
            if (mask === grid.targets[ti].mask) targetExact[ti] = 1;
          }
          break;
        }

        case CELL.PORTAL: {
          const twin = cell.link;
          if (twin >= 0) push(twin % w, (twin / w) | 0, dir, mask, intensity);
          break;
        }

        case CELL.MIRROR: {
          const a = cell.rot;
          const b = (cell.rot + 1) & 3;
          if (entry === a) push(nx, ny, b, mask, intensity);
          else if (entry === b) push(nx, ny, a, mask, intensity);
          break;
        }

        case CELL.SPLITTER: {
          const a = cell.rot;
          const b = (cell.rot + 1) & 3;
          if (entry === a) {
            push(nx, ny, b, mask, intensity * SPLIT_LOSS);
            push(nx, ny, dir, mask, intensity * SPLIT_LOSS);
          } else if (entry === b) {
            push(nx, ny, a, mask, intensity * SPLIT_LOSS);
            push(nx, ny, dir, mask, intensity * SPLIT_LOSS);
          } else {
            // Back of the plate: plain glass, the beam simply goes through.
            push(nx, ny, dir, mask, intensity);
          }
          break;
        }

        case CELL.FILTER: {
          const kept = mask & FILTER_MASK[cell.rot];
          if (kept) push(nx, ny, dir, kept, intensity);
          break;
        }

        case CELL.PRISM: {
          const perm = PRISM_PERM[cell.rot];
          if (mask & perm[0]) push(nx, ny, (dir + 3) & 3, perm[0], intensity);
          if (mask & perm[1]) push(nx, ny, dir, perm[1], intensity);
          if (mask & perm[2]) push(nx, ny, (dir + 1) & 3, perm[2], intensity);
          break;
        }

        case CELL.COMBINER: {
          // Entering through the output face means running into the emitter
          // mouth: absorbed, and that is what makes the arrow meaningful.
          if (entry === cell.rot) break;
          pendMask[index] |= mask;
          if (intensity > pendInt[index]) pendInt[index] = intensity;
          break;
        }

        default:
          break;
      }
    }
  }

  // Target lookup by cell index, built once: the board never changes shape.
  const targetIndexByCell = new Int16Array(cellCount).fill(-1);
  for (let i = 0; i < grid.targets.length; i++) {
    const t = grid.targets[i];
    targetIndexByCell[t.y * w + t.x] = i;
  }
  function cellTargetIndex(index) {
    return targetIndexByCell[index];
  }

  function solve() {
    combMask.fill(0);
    combInt.fill(0);
    truncated = false;

    for (let pass = 0; pass < MAX_PASSES; pass++) {
      runPass();
      let changed = false;
      for (let i = 0; i < cellCount; i++) {
        if (pendMask[i] === 0) continue;
        const merged = combMask[i] | pendMask[i];
        if (merged !== combMask[i]) {
          combMask[i] = merged;
          changed = true;
        }
        if (pendInt[i] > combInt[i] + 1e-4) {
          combInt[i] = pendInt[i];
          changed = true;
        }
      }
      if (!changed) break;
    }

    let lit = 0;
    for (let i = 0; i < grid.targets.length; i++) {
      const ok = targetExact[i];
      targetLit[i] = ok;
      lit += ok;
    }

    result.count = segCount;
    result.litCount = lit;
    result.truncated = truncated;
    result.solved = lit === grid.targets.length;
    return result;
  }

  return { solve, result };
}
