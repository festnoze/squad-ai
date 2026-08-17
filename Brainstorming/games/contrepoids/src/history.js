/**
 * CONTREPOIDS - undo stack.
 *
 * A level never holds more than a couple dozen columns, so an undo entry is a
 * full clone of the world. No diffing, no replay: the player can step back to
 * the very first action of the level at any time, with no limit.
 */

import { cloneState, copyInto } from './shaft.js';

export function createHistory() {
  const stack = [];

  return {
    get depth() {
      return stack.length;
    },
    /** Records the world as it stands right before an action is applied. */
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
