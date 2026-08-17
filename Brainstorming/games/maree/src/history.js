/**
 * MAREE - undo stack.
 *
 * A level is a handful of basins, gates and one explorer: a full snapshot per
 * action is cheap enough that undo can go back to the very first move.
 */

import { cloneWorld, copyInto } from './world.js';

export function createHistory() {
  const stack = [];
  return {
    get depth() {
      return stack.length;
    },
    push(state) {
      stack.push(cloneWorld(state));
    },
    /** Records an already-taken snapshot (see main.js: taken before a mutation
     * whose no-op outcome is only known after the fact, and discarded then). */
    pushSnapshot(snapshot) {
      stack.push(snapshot);
    },
    undo(state) {
      const prev = stack.pop();
      if (!prev) return false;
      copyInto(state, prev);
      return true;
    },
    clear() {
      stack.length = 0;
    },
  };
}
