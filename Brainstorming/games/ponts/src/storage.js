/**
 * PONTS DE FORTUNE - persistence.
 *
 * Everything goes through try/catch: storage disabled, quota exceeded, corrupt
 * JSON or a payload from an older version must all degrade to "start fresh",
 * never to an exception. Keys are prefixed because the arcade console serves
 * every game from a single origin.
 */

import { STORE } from './config.js';

const VERSION = 1;

function blank() {
  return { version: VERSION, unlocked: 0, volume: 0.7, muted: false, levels: {} };
}

export function loadProgress() {
  try {
    const raw = window.localStorage.getItem(STORE.progress);
    if (!raw) return blank();
    const data = JSON.parse(raw);
    if (!data || data.version !== VERSION || typeof data.levels !== 'object') return blank();
    const out = blank();
    out.unlocked = Math.max(0, Math.min(200, data.unlocked | 0));
    out.volume = typeof data.volume === 'number' ? Math.max(0, Math.min(1, data.volume)) : 0.7;
    out.muted = !!data.muted;
    for (const key of Object.keys(data.levels)) {
      const rec = data.levels[key];
      if (!rec) continue;
      out.levels[key] = {
        done: !!rec.done,
        credits: rec.credits | 0,
        load: rec.load | 0,
        bridge: Array.isArray(rec.bridge) ? rec.bridge : null,
      };
    }
    return out;
  } catch (e) {
    return blank();
  }
}

export function saveProgress(progress) {
  try {
    window.localStorage.setItem(STORE.progress, JSON.stringify(progress));
    return true;
  } catch (e) {
    return false;
  }
}

export function recordFor(progress, key) {
  if (!progress.levels[key]) {
    progress.levels[key] = { done: false, credits: 0, load: 0, bridge: null };
  }
  return progress.levels[key];
}

export function countDone(progress) {
  let n = 0;
  for (const key of Object.keys(progress.levels)) if (progress.levels[key].done) n += 1;
  return n;
}
