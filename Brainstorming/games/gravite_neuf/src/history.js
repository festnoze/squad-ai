/**
 * GRAVITE NEUF - undo stack.
 *
 * The grid is tiny (a few hundred cells and under a dozen movables), so an undo
 * entry is a full clone of the world. No diffing, no replay, no edge case: the
 * player can go back to the very first move of the level at any time.
 */

import { cloneState, copyInto } from './world.js';

export function createHistory() {
  const stack = [];

  return {
    get depth() {
      return stack.length;
    },
    /** Records the world as it stands before a move is applied. */
    push(state) {
      stack.push(cloneState(state));
    },
    /** Restores the previous world into `state`. Returns false when empty. */
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
