/**
 * RESONANCE - board state on top of the wave simulation.
 *
 * Pure module (no three, no DOM): the same code drives the game and the Node
 * level validator. The board owns forks, crystals, walls, foams, resonators
 * and the per-band inventory; the wave only sees cells, sources and probes.
 *
 * Coordinates: the board is BOARD_N x BOARD_N slots, each slot covering
 * SLOT x SLOT simulation cells. A slot maps to the cell at its centre.
 */

import { SIM_N, STEP_DT } from './wave.js';

export const BOARD_N = 24;
export const SLOT = SIM_N / BOARD_N; // 4 cells per slot
export const BAND_NAMES = ['grave', 'medium', 'aigu'];
export const CHARGE_TIME = 1.5;          // seconds above threshold before a crystal shatters
export const DEFAULT_THRESHOLD = 0.16;   // amplitude level (source amplitude is 1.0)
export const SOURCE_AMP = 1.0;

// Slot occupancy codes.
export const FREE = 0, WALL = 1, FOAM = 2, CRYSTAL = 3, RESON = 4, FORK = 5;

export function slotToCell(s) { return s * SLOT + (SLOT >> 1); }

export function createBoard(level, wave) {
  const occ = new Uint8Array(BOARD_N * BOARD_N);
  const forks = [];    // {x, y, band, phase}
  const crystals = []; // {x, y, band, forbidden, threshold, charge, level, shattered, shatterStep, probe}
  const stock = level.stock.slice();
  let poses = 0;       // total placements, for the curious counter

  wave.reset();
  wave.clearLayout();

  function occAt(x, y) { return occ[y * BOARD_N + x]; }
  function setOcc(x, y, v) { occ[y * BOARD_N + x] = v; }

  function fillRect(rect, code, cellFn) {
    for (let y = rect.y; y < rect.y + (rect.h || 1); y++) {
      for (let x = rect.x; x < rect.x + (rect.w || 1); x++) {
        setOcc(x, y, code);
        for (let cy = y * SLOT; cy < (y + 1) * SLOT; cy++) {
          for (let cx = x * SLOT; cx < (x + 1) * SLOT; cx++) cellFn(cx, cy);
        }
      }
    }
  }

  for (const r of level.walls || []) fillRect(r, WALL, (cx, cy) => wave.setWall(cx, cy, true));
  for (const r of level.foams || []) fillRect(r, FOAM, (cx, cy) => wave.setFoam(cx, cy, true));

  for (const r of level.resonators || []) {
    setOcc(r.x, r.y, RESON);
    wave.addResonator(slotToCell(r.x), slotToCell(r.y), r.from, r.to, r.gain);
  }

  for (const c of level.crystals || []) {
    setOcc(c.x, c.y, CRYSTAL);
    crystals.push({
      x: c.x, y: c.y, band: c.band,
      forbidden: !!c.forbidden,
      threshold: c.threshold !== undefined ? c.threshold : DEFAULT_THRESHOLD,
      charge: 0, level: 0,
      shattered: false, shatterStep: -1,
      probe: wave.addProbe(slotToCell(c.x), slotToCell(c.y), c.band),
    });
  }

  function syncSources() {
    wave.setSources(forks.map((f) => ({
      idx: wave.idx(slotToCell(f.x), slotToCell(f.y)),
      band: f.band, amp: SOURCE_AMP, phase: f.phase,
    })));
  }

  function inBounds(x, y) { return x >= 0 && y >= 0 && x < BOARD_N && y < BOARD_N; }

  function forkAt(x, y) {
    for (const f of forks) if (f.x === x && f.y === y) return f;
    return null;
  }

  function crystalAt(x, y) {
    for (const c of crystals) if (c.x === x && c.y === y) return c;
    return null;
  }

  /** Place a fork. Never refused for cosmetic reasons: only physics says no. */
  function place(x, y, band, phase = 0) {
    if (!inBounds(x, y)) return { ok: false, reason: 'hors du plateau' };
    if (occAt(x, y) !== FREE) return { ok: false, reason: 'case occupee' };
    if (stock[band] <= 0) return { ok: false, reason: 'stock epuise' };
    const fork = { x, y, band, phase: phase & 3 };
    forks.push(fork);
    stock[band]--;
    poses++;
    setOcc(x, y, FORK);
    syncSources();
    return { ok: true, fork };
  }

  function remove(fork) {
    const i = forks.indexOf(fork);
    if (i < 0) return { ok: false, reason: 'diapason absent' };
    forks.splice(i, 1);
    stock[fork.band]++;
    setOcc(fork.x, fork.y, FREE);
    syncSources();
    return { ok: true };
  }

  function setBand(fork, band) {
    if (band === fork.band) return { ok: true };
    if (stock[band] <= 0) return { ok: false, reason: 'stock epuise' };
    stock[fork.band]++;
    stock[band]--;
    fork.band = band;
    syncSources();
    return { ok: true };
  }

  function setPhase(fork, phase) {
    fork.phase = ((phase % 4) + 4) % 4;
    syncSources();
    return { ok: true };
  }

  /** Advance crystal charges by one simulation step. Call after wave.step(). */
  function tick() {
    let shatteredNow = null;
    for (const c of crystals) {
      if (c.shattered) continue;
      c.level = wave.probeLevel(c.probe);
      if (c.level > c.threshold) {
        c.charge += STEP_DT;
        if (c.charge >= CHARGE_TIME) {
          c.shattered = true;
          c.shatterStep = wave.t;
          shatteredNow = c;
        }
      } else {
        c.charge = Math.max(0, c.charge - STEP_DT * 1.5);
      }
    }
    return shatteredNow;
  }

  /** Undo support: bring back every crystal shattered at or after a step. */
  function restoreShatteredSince(step) {
    const restored = [];
    for (const c of crystals) {
      if (c.shattered && c.shatterStep >= step) {
        c.shattered = false;
        c.shatterStep = -1;
        c.charge = 0;
        c.probe.ema = 0;
        restored.push(c);
      }
    }
    return restored;
  }

  function status() {
    let targetsLeft = 0;
    let failed = false;
    let chargingForbidden = false;
    for (const c of crystals) {
      if (c.forbidden) {
        if (c.shattered) failed = true;
        else if (c.charge > 0) chargingForbidden = true;
      } else if (!c.shattered) targetsLeft++;
    }
    // No sneaking a win past a forbidden crystal mid-charge: victory waits
    // until every forbidden gauge is back to zero (or turns into a failure).
    return {
      targetsLeft, failed, chargingForbidden,
      won: targetsLeft === 0 && !failed && !chargingForbidden,
    };
  }

  return {
    level, occ, forks, crystals, stock,
    get poses() { return poses; },
    occAt, forkAt, crystalAt, inBounds,
    place, remove, setBand, setPhase,
    tick, restoreShatteredSince, status,
  };
}
