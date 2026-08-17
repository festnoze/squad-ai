/**
 * RESONANCE - board/world coordinate helpers.
 *
 * The surface plane has SIM_N vertices over SIM_N - 1 segments, so texel i
 * sits at world -HALF + SPAN * i / (SIM_N - 1). Every mesh that must sit on a
 * simulation cell (forks, crystals, walls) goes through these helpers; using
 * a naive cell * cellSize mapping would drift up to a quarter slot at the
 * edges and clicks would select the wrong cell (interaction range lesson:
 * derive from real geometry, never eyeball).
 */

import { SIM_N } from './wave.js';
import { BOARD_N, SLOT } from './board.js';

const SPAN = BOARD_N;          // world units
const HALF = SPAN / 2;
const K = SPAN / (SIM_N - 1);  // world units per texel step

export function cellToWorldX(cx) { return -HALF + cx * K; }
export function cellToWorldZ(cy) { return HALF - cy * K; }

export function slotToWorldX(sx) { return cellToWorldX(sx * SLOT + (SLOT >> 1)); }
export function slotToWorldZ(sy) { return cellToWorldZ(sy * SLOT + (SLOT >> 1)); }

/** World point to board slot; returns false when outside the board. */
export function worldToSlot(wx, wz, out) {
  const cx = Math.round((wx + HALF) / K);
  const cy = Math.round((HALF - wz) / K);
  if (cx < 0 || cy < 0 || cx >= SIM_N || cy >= SIM_N) return false;
  out.x = Math.min(BOARD_N - 1, Math.floor(cx / SLOT));
  out.y = Math.min(BOARD_N - 1, Math.floor(cy / SLOT));
  return true;
}
