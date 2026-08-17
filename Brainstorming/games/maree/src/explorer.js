/**
 * MAREE - the autonomous explorer: replans on every node he reaches, walks or
 * swims one step at a time, waits patiently when no route exists, and drowns
 * only after a full submersion held for DROWN_TIME seconds. No three.js here;
 * the render layer only reads the plain numbers this module maintains.
 *
 * Replanning at every arrival (rather than only when explicitly told the
 * world changed) is deliberate: this grid is a few hundred nodes at most, so
 * the BFS is effectively free, and it is the only way to guarantee the
 * explorer notices a shortcut that opens up mid-walk - ice finishing while he
 * is already committed to the long way round a room, for instance.
 *
 * Lesson learned from a sibling game in this repository: a transition already
 * in flight must never be cut short by new input. Replanning only happens
 * when `stepT` reaches 1 (at rest on a node), never mid-step, so the walk
 * animation itself is never torn apart by the water changing again a moment
 * later.
 */

import { classify, groundNode, standableHeights } from './world.js';
import { findPath } from './pathing.js';
import { WALK_STEP_TIME, SWIM_STEP_TIME, DROWN_TIME } from './config.js';

/** Places the explorer on its authored start column, resting on dry ground. */
export function initExplorer(state) {
  const e = state.explorer;
  const node = groundNode(state, state.start.x, state.start.z);
  e.x = e.fromX = state.start.x;
  e.z = e.fromZ = state.start.z;
  e.h = e.fromH = node ? node.h : 0;
  e.swimming = false;
  e.stepT = 1;
  e.stepDur = 0.001;
  e.path = null;
  e.pathIndex = 0;
  e.submerged = 0;
  e.status = 'alive';
}

/**
 * Historically a signal for "the world changed, replan soon". Kept as a
 * no-op entry point (main.js calls it after every action) since tickExplorer
 * now replans from scratch at every node arrival regardless - cheaper to
 * always recompute on this grid size than to track what might be stale.
 */
export function requestRepath(state) {
  // Intentionally a no-op; see the module doc comment above.
}

function currentClassification(state) {
  const e = state.explorer;
  const nodes = standableHeights(state, e.x, e.z);
  for (const n of nodes) {
    if (n.h !== e.h) continue;
    const level = n.basin === -1 ? -1 : state.basins[n.basin].level;
    return classify(n.h, level);
  }
  // The column no longer offers this exact height (a crate moved on): treat as
  // the deepest risk so the drowning clock starts rather than silently idling.
  return 'drown';
}

/** Recomputes the plan from the explorer's current resting node. */
function tryRepath(state) {
  const e = state.explorer;
  if (e.x === state.exit.x && e.z === state.exit.z) {
    e.status = 'won';
    return;
  }
  e.path = findPath(state, { x: e.x, z: e.z, h: e.h }, state.exit);
  e.pathIndex = 0;
}

/** Advances the simulation by dt seconds of simulation time. */
export function tickExplorer(state, dt) {
  const e = state.explorer;
  if (e.status !== 'alive') return;

  if (e.stepT < 1) {
    // Mid-step: finish the current move before anything else can happen.
    e.stepT = Math.min(1, e.stepT + dt / e.stepDur);
    if (e.stepT >= 1) {
      e.x = e.path[e.pathIndex].x;
      e.z = e.path[e.pathIndex].z;
      e.h = e.path[e.pathIndex].h;
      if (e.x === state.exit.x && e.z === state.exit.z) {
        e.status = 'won';
        return;
      }
    }
  }

  if (e.stepT >= 1) {
    // At rest: always re-derive the plan fresh, so path[0] is always exactly
    // where the explorer is standing right now (never a stale index).
    tryRepath(state);
    if (e.status !== 'alive') return;

    if (e.path && e.path.length > 1) {
      const next = e.path[1];
      e.fromX = e.x;
      e.fromZ = e.z;
      e.fromH = e.h;
      e.pathIndex = 1;
      e.swimming = next.swim;
      e.stepDur = next.swim ? SWIM_STEP_TIME : WALK_STEP_TIME;
      e.stepT = 0;
    } else {
      // No plan, or already standing on the only safe node: watch for danger.
      const cls = currentClassification(state);
      if (cls === 'drown') {
        e.submerged += dt;
        if (e.submerged >= DROWN_TIME) e.status = 'drowned';
      } else {
        e.submerged = 0;
      }
    }
  }
}
