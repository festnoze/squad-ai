/**
 * RESONANCE - pure 2D wave simulation.
 *
 * No three.js, no DOM: this module runs as-is under Node, which is how
 * tools/validate_levels.mjs proves every level against its reference solution.
 *
 * Three independent scalar fields (one per frequency band) advance with the
 * classic finite difference wave equation on flat Float32Arrays. Two buffers
 * per field are swapped in place: the "prev" array receives the next state,
 * then the roles flip. Nothing is allocated after createWave().
 *
 * Determinism: the only clock is the integer step counter. Sources are forced
 * to sin(2*pi*t/period + phase*pi/2), so a given layout always produces the
 * exact same interference pattern regardless of the render frame rate.
 */

export const SIM_N = 96;               // cells per side
export const BANDS = 3;                // 0 grave, 1 medium, 2 aigu
export const PERIODS = [32, 22, 16];   // steps per oscillation, per band
export const STEP_DT = 1 / 60;         // simulated seconds per step
// Global energy leak. 0.99 settles the cavity in under two seconds: echoes
// still take part in the pattern but the field reaches a readable steady
// state instead of sloshing resonant modes around for tens of seconds.
export const BASE_DAMP = 0.99;
export const FOAM_DAMP = 0.72;         // absorbing foam kills a wave in a few cells

// courant^2: must stay below 0.5 for stability on a 2D 5-point stencil.
// c = sqrt(C2) = 0.5 cell per step, so wavelength = period / 2 cells.
const C2 = 0.25;
export const WAVE_SPEED = 0.5;         // cells per step, derived from C2

const TAU = Math.PI * 2;

export function createWave() {
  const n = SIM_N;
  const cells = n * n;

  const fields = [];
  for (let b = 0; b < BANDS; b++) {
    fields.push({ prev: new Float32Array(cells), cur: new Float32Array(cells) });
  }

  const damp = new Float32Array(cells).fill(BASE_DAMP);
  const wall = new Uint8Array(cells);

  // The outer ring is a permanent wall: the Neumann substitution below turns
  // it into a mirror, so border echoes take part in the interference.
  for (let i = 0; i < n; i++) {
    wall[i] = 1;
    wall[(n - 1) * n + i] = 1;
    wall[i * n] = 1;
    wall[i * n + n - 1] = 1;
  }

  let sources = [];    // {idx, band, amp, phase} - phase in quarter periods (0..3)
  let resonators = []; // {idx, from, to, gain}
  const probes = [];   // {idx, band, ema, k}
  let t = 0;

  function idx(x, y) { return y * n + x; }

  function setWall(x, y, on) { wall[idx(x, y)] = on ? 1 : 0; }
  function setFoam(x, y, on) { damp[idx(x, y)] = on ? FOAM_DAMP : BASE_DAMP; }

  function clearLayout() {
    wall.fill(0);
    for (let i = 0; i < n; i++) {
      wall[i] = 1; wall[(n - 1) * n + i] = 1; wall[i * n] = 1; wall[i * n + n - 1] = 1;
    }
    damp.fill(BASE_DAMP);
    resonators = [];
    sources = [];
    probes.length = 0;
  }

  function setSources(list) { sources = list; }
  function addResonator(x, y, from, to, gain) { resonators.push({ idx: idx(x, y), from, to, gain }); }

  function addProbe(x, y, band) {
    // EMA over roughly one oscillation: a steady sine of amplitude A settles
    // the ema of u^2 at A^2/2, so level = sqrt(2*ema) reads as that amplitude.
    const p = { idx: idx(x, y), band, ema: 0, k: 1 / PERIODS[band] };
    probes.push(p);
    return p;
  }

  function probeLevel(p) { return Math.sqrt(2 * p.ema); }

  function reset() {
    for (let b = 0; b < BANDS; b++) { fields[b].prev.fill(0); fields[b].cur.fill(0); }
    for (let i = 0; i < probes.length; i++) probes[i].ema = 0;
    t = 0;
  }

  function step() {
    t++;
    for (let b = 0; b < BANDS; b++) {
      const f = fields[b];
      const prev = f.prev;
      const cur = f.cur;
      for (let y = 1; y < n - 1; y++) {
        const row = y * n;
        for (let x = 1; x < n - 1; x++) {
          const i = row + x;
          if (wall[i]) { prev[i] = 0; continue; }
          const c = cur[i];
          // Neumann walls: a wall neighbour mirrors the centre value, which
          // reflects the wave instead of absorbing it.
          const l = wall[i - 1] ? c : cur[i - 1];
          const r = wall[i + 1] ? c : cur[i + 1];
          const u = wall[i - n] ? c : cur[i - n];
          const d = wall[i + n] ? c : cur[i + n];
          prev[i] = (2 * c - prev[i] + C2 * (l + r + u + d - 4 * c)) * damp[i];
        }
      }
      f.prev = cur;
      f.cur = prev;
    }

    // Passive resonators: read band "from" locally, re-emit into band "to".
    // This is the only coupling between fields.
    for (let i = 0; i < resonators.length; i++) {
      const rs = resonators[i];
      fields[rs.to].cur[rs.idx] += rs.gain * fields[rs.from].cur[rs.idx];
    }

    // Hard sources: the fork cell is forced, which makes its amplitude
    // independent of whatever waves pass through it.
    for (let i = 0; i < sources.length; i++) {
      const s = sources[i];
      fields[s.band].cur[s.idx] = s.amp * Math.sin(TAU * (t / PERIODS[s.band]) + s.phase * Math.PI * 0.5);
    }

    for (let i = 0; i < probes.length; i++) {
      const p = probes[i];
      const u = fields[p.band].cur[p.idx];
      p.ema += p.k * (u * u - p.ema);
    }
  }

  return {
    n,
    fields,
    wall,
    damp,
    setWall,
    setFoam,
    clearLayout,
    setSources,
    addResonator,
    addProbe,
    probeLevel,
    reset,
    step,
    idx,
    get t() { return t; },
  };
}
