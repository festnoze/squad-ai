/**
 * Persistent user preferences.
 *
 * A small key/value store over localStorage, deliberately kept under a different key from
 * the save game: deleting your progress should not also reset your quality preset, and a
 * corrupt save should not take your preferences down with it.
 *
 * The store is read *synchronously at module load*, which is the whole point of it living
 * here rather than being handed out by the pause menu. Two preferences have to be known
 * before anything is built: the quality preset decides which post-processing stages exist
 * (PostFX builds its node graph once, in its constructor) and the resolution scale decides
 * how big the swap chain is. Applying either after the first frame means rebuilding the
 * pipeline in front of the player.
 *
 * Values are plain JSON, not four named fields, so the key-binding map and the locale can
 * live here too without touching this file.
 */

const KEY = 'liberty-horizon:settings:v1';
const VERSION = 1;
/**
 * Writes are coalesced: dragging a range input emits an `input` event per frame, and each
 * one would otherwise be a synchronous localStorage write on the main thread. The debounce
 * is only about write rate - `pagehide` flushes, so the last value of a drag never gets
 * lost to a reload.
 */
const FLUSH_DELAY_MS = 250;

export class SettingsStore {
  /** @param {Storage|null} storage */
  constructor(storage) {
    this._storage = storage;
    this._timer = 0;
    /** @type {Record<string, any>} */
    this.values = {};
    /** False once a write has failed, so we stop retrying on every slider tick. */
    this.enabled = !!storage;
    this._read();

    if (typeof window !== 'undefined') {
      window.addEventListener('pagehide', () => this.flush());
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) this.flush();
      });
    }
  }

  _read() {
    try {
      const raw = this._storage?.getItem(KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      // A store from another version is ignored rather than migrated field by field:
      // defaults are always a working game, half-applied preferences may not be.
      if (!data || data.version !== VERSION || typeof data.values !== 'object') return;
      this.values = data.values ?? {};
    } catch (err) {
      console.warn('[Settings] preferences unreadable, using defaults:', err.message);
    }
  }

  has(key) { return Object.prototype.hasOwnProperty.call(this.values, key); }

  /** @returns {any} the stored value, or `fallback` when nothing is stored. */
  get(key, fallback = null) { return this.has(key) ? this.values[key] : fallback; }

  /*
   * Typed accessors. Everything read at boot goes through one of these, because a store
   * hand-edited in devtools (or written by an older build) must not be able to brick the
   * game: a quality of "banana" or a resolution scale of -3 falls back instead.
   */

  number(key, fallback, min = -Infinity, max = Infinity) {
    const raw = this.get(key, undefined);
    if (typeof raw !== 'number' || !Number.isFinite(raw)) return fallback;
    return Math.min(max, Math.max(min, raw));
  }

  bool(key, fallback) {
    const raw = this.get(key, undefined);
    return typeof raw === 'boolean' ? raw : fallback;
  }

  /** @param {readonly any[]} allowed */
  choice(key, fallback, allowed) {
    const raw = this.get(key, undefined);
    return allowed.includes(raw) ? raw : fallback;
  }

  set(key, value) {
    this.values[key] = value;
    this._schedule();
    return value;
  }

  /** @param {Record<string, any>} entries */
  setMany(entries) {
    for (const [key, value] of Object.entries(entries)) this.values[key] = value;
    this._schedule();
  }

  remove(key) {
    if (!this.has(key)) return;
    delete this.values[key];
    this._schedule();
  }

  /** Back to defaults. Writes immediately - a reset the player asked for should stick. */
  clear() {
    this.values = {};
    this.flush();
  }

  /** A copy, so callers cannot mutate the store behind its own back. */
  all() { return { ...this.values }; }

  _schedule() {
    if (this._timer || !this.enabled) return;
    this._timer = setTimeout(() => { this._timer = 0; this.flush(); }, FLUSH_DELAY_MS);
  }

  /** Write now. Safe to call at any time; returns false if storage refused. */
  flush() {
    if (this._timer) { clearTimeout(this._timer); this._timer = 0; }
    if (!this.enabled || !this._storage) return false;
    try {
      this._storage.setItem(KEY, JSON.stringify({
        version: VERSION, savedAt: new Date().toISOString(), values: this.values,
      }));
      return true;
    } catch (err) {
      // Private browsing and full quotas both throw here. Preferences are a convenience;
      // losing them must never cost the player the game.
      console.warn('[Settings] could not write preferences:', err.message);
      this.enabled = false;
      return false;
    }
  }
}

/** localStorage access itself throws in some privacy modes, so even the lookup is guarded. */
function localStore() {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null;
  } catch {
    return null;
  }
}

export const SETTINGS_KEY = KEY;
export const settings = new SettingsStore(localStore());
