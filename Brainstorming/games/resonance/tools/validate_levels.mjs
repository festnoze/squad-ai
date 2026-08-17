/**
 * RESONANCE - level validator.
 *
 * Replays every level's reference solution in the real simulation (the same
 * wave.js and board.js the game runs) and asserts:
 *   - each placement of the solution is legal (free slot, stock available),
 *   - every target crystal shatters within the time budget,
 *   - no forbidden crystal ever shatters,
 *   - par matches the solution's fork count.
 *
 * Usage:
 *   node tools/validate_levels.mjs            strict pass/fail, exit code 0/1
 *   node tools/validate_levels.mjs --report   also prints per-crystal levels
 *   node tools/validate_levels.mjs --report 4 report a single level (index)
 */

import { createWave } from '../src/wave.js';
import { createBoard, BAND_NAMES } from '../src/board.js';
import { LEVELS } from '../src/levels.js';

const REPORT = process.argv.includes('--report');
const onlyArg = process.argv.find((a) => /^\d+$/.test(a));
const only = onlyArg === undefined ? -1 : Number(onlyArg);

const BUDGET_STEPS = 30 * 60; // 30 simulated seconds

let failures = 0;

LEVELS.forEach((level, li) => {
  if (only >= 0 && li !== only) return;

  const wave = createWave();
  const board = createBoard(level, wave);
  const problems = [];

  if (level.par !== level.solution.length) {
    problems.push(`par=${level.par} but the solution has ${level.solution.length} forks`);
  }

  for (const s of level.solution) {
    const r = board.place(s.x, s.y, s.band, s.phase);
    if (!r.ok) problems.push(`illegal solution placement at (${s.x},${s.y}): ${r.reason}`);
  }

  const stats = board.crystals.map(() => ({ min: Infinity, max: 0 }));
  let wonAt = -1;

  for (let step = 0; step < BUDGET_STEPS; step++) {
    wave.step();
    board.tick();
    board.crystals.forEach((c, i) => {
      // Track the settled range (skip the first 3 s of transient).
      if (step > 180) {
        stats[i].min = Math.min(stats[i].min, c.level);
        stats[i].max = Math.max(stats[i].max, c.level);
      }
    });
    const st = board.status();
    if (st.failed) { problems.push(`forbidden crystal shattered at step ${step}`); break; }
    if (st.won && wonAt < 0) wonAt = step;
  }

  if (wonAt < 0 && !problems.some((p) => p.startsWith('forbidden'))) {
    const left = board.crystals.filter((c) => !c.forbidden && !c.shattered)
      .map((c) => `(${c.x},${c.y})`).join(' ');
    problems.push(`targets still standing after ${BUDGET_STEPS} steps: ${left}`);
  }

  const tag = problems.length ? 'ECHEC' : 'ok   ';
  console.log(`${tag} ${String(li).padStart(2)} ${level.name}` +
    (wonAt >= 0 ? ` (resolu a ${(wonAt / 60).toFixed(1)} s)` : ''));
  for (const p of problems) console.log(`        - ${p}`);

  if (REPORT) {
    board.crystals.forEach((c, i) => {
      const kind = c.forbidden ? 'INTERDIT' : 'cible   ';
      console.log(`        ${kind} (${String(c.x).padStart(2)},${String(c.y).padStart(2)}) ` +
        `${BAND_NAMES[c.band].padEnd(6)} seuil=${c.threshold.toFixed(2)} ` +
        `niveau=[${stats[i].min === Infinity ? '-' : stats[i].min.toFixed(3)} .. ${stats[i].max.toFixed(3)}] ` +
        (c.shattered ? `BRISE a ${(c.shatterStep / 60).toFixed(1)} s` : `charge=${c.charge.toFixed(2)}`));
    });
  }

  if (problems.length) failures++;
});

if (only < 0) {
  console.log(failures === 0
    ? `\n${LEVELS.length} niveaux valides.`
    : `\n${failures} niveau(x) en echec.`);
}
process.exit(failures === 0 ? 0 : 1);
