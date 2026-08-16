/**
 * OVERCLOCK - persistence.
 *
 * The arcade console serves every game from the same origin, so every key is
 * prefixed. Storage can be disabled, full or hold garbage from an older build:
 * every access is guarded and a failure simply means "no save".
 */

const PREFIX = 'overclock.';
const VERSION = 1;

function read(key, fallback) {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (!raw) return fallback;
    const data = JSON.parse(raw);
    if (!data || data.v !== VERSION) return fallback;
    return data.d;
  } catch (e) {
    return fallback;
  }
}

function write(key, value) {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify({ v: VERSION, d: value }));
    return true;
  } catch (e) {
    return false;
  }
}

export function createStorage() {
  let progress = read('progress', null);
  if (!progress || typeof progress !== 'object') progress = { maxIndex: 0, best: {} };
  if (typeof progress.maxIndex !== 'number') progress.maxIndex = 0;
  if (!progress.best || typeof progress.best !== 'object') progress.best = {};

  let programs = read('programs', null);
  if (!programs || typeof programs !== 'object') programs = {};

  return {
    get maxIndex() {
      return progress.maxIndex;
    },

    bestFor(levelId) {
      const v = progress.best[levelId];
      return typeof v === 'number' ? v : null;
    },

    /** Records a win. Returns true when it beat the previous personal best. */
    recordWin(levelId, index, used) {
      const prev = progress.best[levelId];
      const better = typeof prev !== 'number' || used < prev;
      if (better) progress.best[levelId] = used;
      if (index + 1 > progress.maxIndex) progress.maxIndex = index + 1;
      write('progress', progress);
      return better;
    },

    programFor(levelId) {
      const p = programs[levelId];
      return Array.isArray(p) ? p : null;
    },

    saveProgram(levelId, data) {
      programs[levelId] = data;
      write('programs', programs);
    },

    wipe() {
      progress = { maxIndex: 0, best: {} };
      programs = {};
      write('progress', progress);
      write('programs', programs);
    },
  };
}
