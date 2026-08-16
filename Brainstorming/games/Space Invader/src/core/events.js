// Emetteur d'evenements minimal, sans dependance.

export class Emitter {
  constructor() {
    this._map = new Map();
  }

  /** Retourne une fonction de desabonnement. */
  on(name, cb) {
    let set = this._map.get(name);
    if (!set) {
      set = new Set();
      this._map.set(name, set);
    }
    set.add(cb);
    return () => this.off(name, cb);
  }

  off(name, cb) {
    const set = this._map.get(name);
    if (set) set.delete(cb);
  }

  emit(name, payload) {
    const set = this._map.get(name);
    if (!set) return;
    for (const cb of Array.from(set)) {
      try {
        cb(payload);
      } catch (err) {
        console.error(`[events] listener "${name}" a echoue`, err);
      }
    }
  }

  clear() {
    this._map.clear();
  }
}
