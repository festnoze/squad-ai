/**
 * MAREE - water level resolution: raising/lowering a basin, opening and
 * closing vannes, and forming ice. Pure state mutation, no three.js.
 *
 * Lesson learned from a sibling puzzle game in this repository: a request the
 * player is allowed to make must always execute, at its normal cost, even
 * when nothing visibly moves. The only free, cost-less case handled here is
 * asking for the exact level the basin is already at (a genuinely identical
 * request), never "nothing moved this time".
 */

import { rebuildGroups } from './world.js';
import { FREEZE_HOLD_TIME, WATER_VISUAL_SPEED } from './config.js';

/**
 * Requests a one-cran change on the basin `basinId` (and, since a shared gate
 * group always carries one common level, on every basin currently joined to
 * it). Returns { changed } so the caller can skip the move counter and the
 * history push on the one legal no-op: re-requesting the level already active.
 */
export function requestLevelChange(state, basinId, delta) {
  const group = state.groups[state.groupOf[basinId]];
  const current = state.basins[basinId].level;
  const target = Math.max(state.basins[basinId].min, Math.min(state.basins[basinId].max, current + delta));
  if (target === current) return { changed: false };
  for (const i of group) {
    const b = state.basins[i];
    b.level = target;
    b.stableAt = target;
    b.stableTime = 0;
  }
  return { changed: true, group };
}

/**
 * Flips one gate. Opening always merges its two basins to the lower of their
 * two levels (water finds the lower shelf); closing simply lets the two
 * groups drift apart from the level they already share. A toggle always
 * changes the gate's own open/closed flag, so it always costs a move.
 */
export function toggleGate(state, gateIndex) {
  const gate = state.gates[gateIndex];
  gate.open = !gate.open;
  rebuildGroups(state);
  if (gate.open) {
    const group = state.groups[state.groupOf[gate.a]];
    let target = state.basins[group[0]].level;
    for (const i of group) target = Math.min(target, state.basins[i].level);
    for (const i of group) {
      const b = state.basins[i];
      b.level = target;
      b.stableAt = target;
      b.stableTime = 0;
    }
  }
  return { changed: true };
}

/** Advances the smooth visual level that render/water.js and render/explorer.js read. */
export function updateVisualLevels(state, dt) {
  const step = WATER_VISUAL_SPEED * dt;
  for (const b of state.basins) {
    const diff = b.level - b.visual;
    if (Math.abs(diff) <= step) b.visual = b.level;
    else b.visual += Math.sign(diff) * step;
  }
}

/**
 * Ice forms wherever a freeze-capable basin has held one exact level for
 * FREEZE_HOLD_TIME seconds of simulation. Once formed a level never leaves
 * `iceLevels`: undo is the only way to remove it (history.js restores the
 * whole array), matching "un plancher de glace ne disparait jamais".
 */
export function updateFreeze(state, dt) {
  for (const b of state.basins) {
    if (!b.freeze || b.level < 0) continue;
    if (b.level !== b.stableAt) {
      b.stableAt = b.level;
      b.stableTime = 0;
      continue;
    }
    if (b.iceLevels.indexOf(b.level) !== -1) continue;
    b.stableTime += dt;
    if (b.stableTime >= FREEZE_HOLD_TIME) b.iceLevels.push(b.level);
  }
}
