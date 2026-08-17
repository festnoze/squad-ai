/**
 * MAREE - explorer pathfinding. Pure BFS over standing nodes, no three.js.
 *
 * A node is (x, z, h): a column plus one of its currently usable standing
 * heights (ground, a floating wood crate, or a formed ice plane). Nodes whose
 * water classifies as "drown" (fully over the head) are never offered to the
 * planner, so the explorer never chooses to walk into deep water - except his
 * own current position, which is always accepted as a start even if the world
 * just turned it dangerous out from under him, so he can still scramble to
 * safety if any route exists.
 */

import { inBounds, isVoid, standableHeights, classify } from './world.js';

const NEI = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
];

function nodeKey(x, z, h) {
  return x + ',' + z + ',' + h;
}

/** Lists the safe (non-drowning) nodes of a column, tagged with their swim state. */
function safeNodes(state, x, z) {
  const out = [];
  for (const n of standableHeights(state, x, z)) {
    const level = n.basin === -1 ? -1 : state.basins[n.basin].level;
    const cls = classify(n.h, level);
    if (cls === 'drown') continue;
    out.push({ x, z, h: n.h, swim: cls === 'swim' });
  }
  return out;
}

/**
 * BFS from `start` (forced into the graph regardless of its own safety) to any
 * safe node standing on the exit column. Returns an array of nodes from start
 * to goal (start included), or null when no route exists right now.
 */
export function findPath(state, start, exit) {
  const startKey = nodeKey(start.x, start.z, start.h);
  const cameFrom = new Map();
  const visited = new Set([startKey]);
  const queue = [start];
  let qi = 0;
  let goalNode = null;

  while (qi < queue.length && !goalNode) {
    const cur = queue[qi++];
    if (cur.x === exit.x && cur.z === exit.z) {
      goalNode = cur;
      break;
    }
    for (const [dx, dz] of NEI) {
      const nx = cur.x + dx;
      const nz = cur.z + dz;
      if (!inBounds(state, nx, nz) || isVoid(state, nx, nz)) continue;
      for (const cand of safeNodes(state, nx, nz)) {
        if (Math.abs(cand.h - cur.h) > 1) continue;
        const key = nodeKey(cand.x, cand.z, cand.h);
        if (visited.has(key)) continue;
        visited.add(key);
        cameFrom.set(key, cur);
        queue.push(cand);
      }
    }
  }

  if (!goalNode) return null;
  const path = [goalNode];
  let k = nodeKey(goalNode.x, goalNode.z, goalNode.h);
  while (k !== startKey) {
    const prev = cameFrom.get(k);
    path.push(prev);
    k = nodeKey(prev.x, prev.z, prev.h);
  }
  path.reverse();
  return path;
}
