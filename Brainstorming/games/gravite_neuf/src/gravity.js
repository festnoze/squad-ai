/**
 * GRAVITE NEUF - fall resolution.
 *
 * One tilt of gravity is resolved by repeated single cell iterations. Inside an
 * iteration the movables are processed from the one closest to the new floor to
 * the one furthest from it, so a stack collapses column by column and nothing
 * can tunnel through anything. The loop is bounded twice (nothing moved, and a
 * hard iteration cap) so a malformed level can never freeze the page.
 *
 * No three.js here: the offline solver imports this file as is.
 */

import {
  S,
  MV,
  DIRS,
  staticBlocks,
  rebuildOcc,
  switchOn,
  snapshot,
  inside,
} from './world.js';

const MAX_ITERATIONS = 512;

/** Kill / stick / void reasons carried by the state after a tilt. */
export const REASON = {
  VOID: 'void',
  SPIKE: 'spike',
  GLUE: 'glue',
};

const sortScratch = [];

/**
 * Advances every movable by at most one cell along `d`.
 * Returns true when the world changed (a move, a death or a stick).
 */
function settleStep(state, d, events) {
  const { W, D, statics, occ, movables } = state;
  rebuildOcc(state);
  const gateAOpen = switchOn(state, S.SWITCH_A);
  const gateBOpen = switchOn(state, S.SWITCH_B);

  sortScratch.length = 0;
  for (let i = 0; i < movables.length; i++) {
    const m = movables[i];
    m.blockedBy = -1;
    if (m.alive) sortScratch.push(i);
  }
  // Closest to the new floor first: that cell is the one that can free up.
  sortScratch.sort((ia, ib) => {
    const a = movables[ia];
    const b = movables[ib];
    const pa = a.x * d[0] + a.y * d[1] + a.z * d[2];
    const pb = b.x * d[0] + b.y * d[1] + b.z * d[2];
    return pb - pa;
  });

  let changed = false;

  for (let k = 0; k < sortScratch.length; k++) {
    const i = sortScratch[k];
    const m = movables[i];
    if (m.stuck) continue;
    const nx = m.x + d[0];
    const ny = m.y + d[1];
    const nz = m.z + d[2];

    if (!inside(state, nx, ny, nz)) {
      occ[(m.y * D + m.z) * W + m.x] = -1;
      m.x = nx;
      m.y = ny;
      m.z = nz;
      m.alive = false;
      m.voided = true;
      m.killed = REASON.VOID;
      events.push({ type: 'void', index: i, kind: m.kind });
      changed = true;
      continue;
    }

    const c = (ny * D + nz) * W + nx;
    const kind = statics[c];
    if (staticBlocks(kind, gateAOpen, gateBOpen)) {
      m.blockedBy = kind;
      continue;
    }
    if (occ[c] !== -1) {
      m.blockedBy = -1;
      continue;
    }
    occ[(m.y * D + m.z) * W + m.x] = -1;
    m.x = nx;
    m.y = ny;
    m.z = nz;
    occ[c] = i;
    m.blockedBy = -1;
    changed = true;
  }

  // Contact effects are applied after the whole pass: an object that landed on
  // a spike this very iteration must die now, not on the next one.
  for (let k = 0; k < sortScratch.length; k++) {
    const i = sortScratch[k];
    const m = movables[i];
    if (!m.alive || m.stuck) continue;
    if (m.blockedBy === S.SPIKE) {
      m.alive = false;
      m.killed = REASON.SPIKE;
      events.push({ type: 'spike', index: i, kind: m.kind, x: m.x, y: m.y, z: m.z });
      changed = true;
    } else if (m.blockedBy === S.GLUE) {
      m.stuck = true;
      events.push({ type: 'glue', index: i, kind: m.kind, x: m.x, y: m.y, z: m.z });
      changed = true;
    }
  }

  return changed;
}

/** Keys are picked up when they come to rest against the player cube. */
function collectKeys(state, events) {
  const player = state.movables[state.playerIndex];
  if (!player.alive) return 0;
  let taken = 0;
  for (let i = 0; i < state.movables.length; i++) {
    const m = state.movables[i];
    if (!m.alive || m.kind !== MV.KEY) continue;
    const dx = Math.abs(m.x - player.x);
    const dy = Math.abs(m.y - player.y);
    const dz = Math.abs(m.z - player.z);
    if (dx + dy + dz !== 1) continue;
    m.alive = false;
    m.killed = 'taken';
    state.keysTaken++;
    taken++;
    events.push({ type: 'key', index: i, x: m.x, y: m.y, z: m.z });
  }
  return taken;
}

function finalize(state) {
  const player = state.movables[state.playerIndex];
  const statics = state.statics;

  for (let i = 0; i < state.movables.length; i++) {
    const m = state.movables[i];
    if (m.kind === MV.CRATE && !m.alive) state.crateLost = true;
  }

  if (!player.alive) {
    state.status = 'lost';
    state.reason =
      player.killed === REASON.SPIKE
        ? 'Le cube joueur a fini sur les piques.'
        : 'Le cube joueur est tombe dans le vide.';
    return;
  }

  const cell = (player.y * state.D + player.z) * state.W + player.x;
  const onExit = statics[cell] === S.EXIT;

  if (onExit && state.keysTaken === state.keysTotal) {
    state.status = 'won';
    state.reason = '';
    return;
  }

  for (let i = 0; i < state.movables.length; i++) {
    const m = state.movables[i];
    if (m.kind !== MV.KEY || m.alive || m.killed === 'taken') continue;
    state.status = 'lost';
    state.reason =
      m.killed === REASON.SPIKE ? 'Une cle a ete detruite par les piques.' : 'Une cle est tombee dans le vide.';
    return;
  }

  if (player.stuck) {
    state.status = 'lost';
    state.reason = 'Le cube joueur est colle a la glu, il ne bougera plus.';
    return;
  }

  state.status = 'play';
  state.reason = '';
}

/**
 * Applies one gravity tilt in place.
 * Returns { moved, steps, events }. `steps` always starts with the world as it
 * was before the tilt, so the renderer can animate straight from it.
 */
export function applyGravity(state, dirIndex) {
  const d = DIRS[dirIndex];
  const events = [];
  const steps = [snapshot(state)];
  state.gravity = dirIndex;

  let moved = false;
  let guard = 0;

  for (;;) {
    if (++guard > MAX_ITERATIONS) break;
    if (settleStep(state, d, events)) {
      moved = true;
      steps.push(snapshot(state));
      continue;
    }
    if (collectKeys(state, events) > 0) {
      moved = true;
      steps.push(snapshot(state));
      continue;
    }
    break;
  }

  finalize(state);
  return { moved, steps, events };
}

/** Settles a freshly loaded level without counting it as a player move. */
export function settleInitial(state) {
  const res = applyGravity(state, state.gravity);
  res.steps = [snapshot(state)];
  res.moved = false;
  return res;
}
