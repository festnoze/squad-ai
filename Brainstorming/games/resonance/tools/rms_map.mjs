/**
 * RESONANCE - amplitude map, a level design aid.
 *
 * Prints, for one level with its reference solution applied, the settled
 * amplitude level of one band on every board slot. Used to place crystals on
 * measured bright or dark fringes instead of guessing (the cavity is modal:
 * border echoes make amplitude anything but monotonic with distance).
 *
 * Usage: node tools/rms_map.mjs <levelIndex> <band 0|1|2> [steps=1800]
 */

import { createWave } from '../src/wave.js';
import { createBoard, BOARD_N, slotToCell } from '../src/board.js';
import { LEVELS } from '../src/levels.js';

const li = Number(process.argv[2] ?? 0);
const band = Number(process.argv[3] ?? 0);
const steps = Number(process.argv[4] ?? 1800);

const level = LEVELS[li];
const wave = createWave();
const board = createBoard(level, wave);
for (const s of level.solution) {
  const r = board.place(s.x, s.y, s.band, s.phase);
  if (!r.ok) console.error(`placement refuse (${s.x},${s.y}): ${r.reason}`);
}

const probes = [];
for (let y = 0; y < BOARD_N; y++) {
  for (let x = 0; x < BOARD_N; x++) {
    probes.push(wave.addProbe(slotToCell(x), slotToCell(y), band));
  }
}

for (let i = 0; i < steps; i++) wave.step();

console.log(`${level.name} - band ${band} - level x100 per slot (col 0..23 left to right)`);
for (let y = 0; y < BOARD_N; y++) {
  let row = String(y).padStart(2) + ' ';
  for (let x = 0; x < BOARD_N; x++) {
    const v = Math.round(wave.probeLevel(probes[y * BOARD_N + x]) * 100);
    const occ = board.occAt(x, y);
    const mark = occ === 1 ? '##' : occ === 2 ? 'ff' : occ === 5 ? 'FF' : occ === 3 ? 'CC' : occ === 4 ? 'RR' : null;
    row += (mark ?? String(Math.min(99, v)).padStart(2)) + ' ';
  }
  console.log(row);
}
