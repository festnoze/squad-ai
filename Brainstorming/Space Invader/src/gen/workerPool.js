// Pool de workers de terrain.
//
// Regles :
// - chaque requete recoit un id entier croissant (ou son id explicite si
//   l'appelant en fournit un) ; la promesse est resolue a la reception du
//   message portant le meme id, rejetee sur { type: 'error' },
// - au plus MAX_IN_FLIGHT requetes en vol par worker : le reste attend dans la
//   file, ce qui permet d'annuler ce qui n'est pas encore parti,
// - cancel(id) retire de la file et resout avec null,
// - dispose() resout tout ce qui reste avec null (jamais de rejet orphelin).

const MAX_IN_FLIGHT = 2;

export class WorkerPool {
  constructor({ size = 2, factory } = {}) {
    if (typeof factory !== 'function') throw new Error('WorkerPool: factory manquante');
    this.size = Math.max(1, size | 0);
    this.factory = factory;
    this.spec = null;

    this._slots = []; // { worker, inFlight: Set<number> }
    this._pending = new Map(); // id -> { resolve, reject, slot }
    this._queue = []; // { id, msg, resolve, reject }
    this._nextId = 1;
    this._ready = false;
    this._disposed = false;

    for (let i = 0; i < this.size; i++) this._spawn();
  }

  // -- cycle de vie -------------------------------------------------------

  _spawn() {
    const slot = { worker: this.factory(), inFlight: new Set() };
    slot.worker.onmessage = (event) => this._onMessage(slot, event.data);
    slot.worker.onerror = (event) => {
      this._failSlot(slot, (event && event.message) || 'erreur de worker');
    };
    slot.worker.onmessageerror = () => {
      this._failSlot(slot, 'message de worker non deserialisable');
    };
    this._slots.push(slot);
    return slot;
  }

  /** Envoie le spec a tous les workers et attend leur 'ready'. */
  async init(spec) {
    if (this._disposed) throw new Error('WorkerPool: pool libere');
    this.spec = spec;
    await Promise.all(
      this._slots.map(
        (slot) =>
          new Promise((resolve, reject) => {
            const id = this._nextId++;
            this._pending.set(id, { resolve, reject, slot });
            slot.inFlight.add(id);
            slot.worker.postMessage({ type: 'init', id, spec });
          }),
      ),
    );
    this._ready = true;
    this._pump();
  }

  // -- requetes -----------------------------------------------------------

  /**
   * @param {object} msg { type, ... } ; msg.id est ajoute s'il est absent.
   * @returns {Promise<object>} la promesse porte aussi `.id` (pour cancel).
   */
  request(msg) {
    if (this._disposed) return Promise.resolve(null);
    let id;
    if (typeof msg.id === 'number' && Number.isFinite(msg.id)) {
      id = msg.id | 0;
      if (id >= this._nextId) this._nextId = id + 1;
    } else {
      id = this._nextId++;
    }
    const outgoing = { ...msg, id };
    const promise = new Promise((resolve, reject) => {
      this._queue.push({ id, msg: outgoing, resolve, reject });
      this._pump();
    });
    promise.id = id;
    return promise;
  }

  /** Annule une requete si elle n'est pas encore partie ; resout avec null. */
  cancel(id) {
    for (let i = 0; i < this._queue.length; i++) {
      if (this._queue[i].id === id) {
        const job = this._queue[i];
        this._queue.splice(i, 1);
        job.resolve(null);
        return;
      }
    }
    // Deja en vol : on laisse la reponse arriver normalement.
  }

  get pending() {
    return this._pending.size;
  }

  get queued() {
    return this._queue.length;
  }

  /** Nombre de workers vivants. */
  get workerCount() {
    return this._slots.length;
  }

  // -- interne ------------------------------------------------------------

  _pickSlot() {
    let best = null;
    for (const slot of this._slots) {
      if (slot.inFlight.size >= MAX_IN_FLIGHT) continue;
      if (!best || slot.inFlight.size < best.inFlight.size) best = slot;
    }
    return best;
  }

  _pump() {
    if (!this._ready || this._disposed) return;
    while (this._queue.length > 0) {
      const slot = this._pickSlot();
      if (!slot) break;
      const job = this._queue.shift();
      this._pending.set(job.id, { resolve: job.resolve, reject: job.reject, slot });
      slot.inFlight.add(job.id);
      slot.worker.postMessage(job.msg);
    }
  }

  _onMessage(slot, data) {
    if (!data || typeof data.id !== 'number') return;
    const entry = this._pending.get(data.id);
    slot.inFlight.delete(data.id);
    if (entry) {
      this._pending.delete(data.id);
      if (data.type === 'error') entry.reject(new Error(data.message || 'erreur de worker'));
      else entry.resolve(data);
    }
    this._pump();
  }

  /** Un worker est mort ou a plante : on rejette tout ce qu'il portait. */
  _failSlot(slot, message) {
    for (const id of Array.from(slot.inFlight)) {
      const entry = this._pending.get(id);
      slot.inFlight.delete(id);
      if (entry) {
        this._pending.delete(id);
        entry.reject(new Error(message));
      }
    }
    this._pump();
  }

  dispose() {
    if (this._disposed) return;
    this._disposed = true;
    this._ready = false;
    for (const job of this._queue) job.resolve(null);
    this._queue.length = 0;
    for (const entry of this._pending.values()) entry.resolve(null);
    this._pending.clear();
    for (const slot of this._slots) {
      slot.worker.onmessage = null;
      slot.worker.onerror = null;
      slot.worker.onmessageerror = null;
      slot.inFlight.clear();
      slot.worker.terminate();
    }
    this._slots.length = 0;
  }
}

/** Cree un pool de workers de terrain deja initialise avec le spec. */
export async function createTerrainPool(spec, size = 3) {
  const pool = new WorkerPool({
    size,
    factory: () => new Worker(new URL('./terrainWorker.js', import.meta.url), { type: 'module' }),
  });
  await pool.init(spec);
  return pool;
}
