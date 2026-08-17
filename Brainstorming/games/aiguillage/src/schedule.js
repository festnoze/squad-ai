/**
 * AIGUILLAGE - deterministic spawn scheduler.
 *
 * Pure data walker: consumes a level's spawn table (already sorted by time,
 * never randomised) and hands back the entries that are due, in order,
 * exactly once each. main.js drives it with the simulation clock so a
 * tactical pause (which freezes trains but not the level clock, per the
 * design brief) still lets the schedule progress if it was already due.
 */

export function createScheduler(spawnList) {
  const list = spawnList.slice().sort((a, b) => a.t - b.t);
  let cursor = 0;

  return {
    get total() {
      return list.length;
    },
    get done() {
      return cursor >= list.length;
    },
    get remaining() {
      return list.length - cursor;
    },
    /** Returns (and consumes) every entry whose time has come. */
    pending(simTime) {
      const due = [];
      while (cursor < list.length && list[cursor].t <= simTime) {
        due.push(list[cursor]);
        cursor++;
      }
      return due;
    },
    reset() {
      cursor = 0;
    },
  };
}
