// Offline solver for CONTREPOIDS levels.
//
// Exhaustive breadth-first search over the pure model in src/shaft.js (no
// three.js, no DOM: this script runs under plain Node). For every level it
// finds the shortest sequence of actions to victory and asserts the result
// against the `par` declared in src/levels.js, so a level's medal thresholds
// can never silently drift from what is actually reachable.
//
// Usage: node tools/solve.mjs
import { createState, cloneState, hashState, moveTo, jumpTo, takeItem, dropItem, pushAnvil } from '../src/shaft.js';
import { LEVELS } from '../src/levels.js';

function actionsList() {
  const acts = [];
  for (let d = 0; d < 4; d++) acts.push(['move', d]);
  for (let d = 0; d < 4; d++) acts.push(['jump', d]);
  acts.push(['take', 0]);
  acts.push(['drop', 0]);
  for (let d = 0; d < 4; d++) acts.push(['push', d]);
  return acts;
}
const ACTIONS = actionsList();

function apply(kind, dir, state) {
  if (kind === 'move') return moveTo(state, dir);
  if (kind === 'jump') return jumpTo(state, dir);
  if (kind === 'take') return takeItem(state);
  if (kind === 'drop') return dropItem(state);
  if (kind === 'push') return pushAnvil(state, dir);
  throw new Error('unknown action ' + kind);
}

/** Returns { par, visited, path } or { par: -1, ... } if unsolved within maxDepth. */
function solve(level, maxDepth) {
  const start = createState(level);
  const startHash = hashState(start);
  const visited = new Map([[startHash, null]]);
  let frontier = [{ state: start, hash: startHash }];
  let depth = 0;
  if (start.status === 'won') return { par: 0, visited: 1, path: [] };
  while (frontier.length && depth < maxDepth) {
    depth++;
    const next = [];
    for (const { state: st, hash: stHash } of frontier) {
      for (const [kind, dir] of ACTIONS) {
        const trial = cloneState(st);
        const res = apply(kind, dir, trial);
        if (!res.ok) continue;
        const h = hashState(trial);
        if (visited.has(h)) continue;
        visited.set(h, { parent: stHash, kind, dir });
        if (trial.status === 'won') {
          const path = [];
          let cur = h;
          while (cur !== startHash) {
            const rec = visited.get(cur);
            path.unshift(rec.kind + (rec.kind === 'take' || rec.kind === 'drop' ? '' : ':' + rec.dir));
            cur = rec.parent;
          }
          return { par: depth, visited: visited.size, path };
        }
        next.push({ state: trial, hash: h });
      }
    }
    frontier = next;
    if (frontier.length === 0) break;
  }
  return { par: -1, visited: visited.size, path: null };
}

let allOk = true;
for (let i = 0; i < LEVELS.length; i++) {
  const lvl = LEVELS[i];
  let res;
  try {
    res = solve(lvl, 24);
  } catch (e) {
    console.log(String(i + 1).padStart(2, ' '), lvl.name, 'ERREUR:', e.message);
    allOk = false;
    continue;
  }
  const mismatch = res.par < 0 || (lvl.par !== undefined && lvl.par !== res.par);
  const status = res.par >= 0 ? 'OK par=' + res.par + ' (declare ' + lvl.par + ')' : 'INSOLVABLE dans la limite';
  if (mismatch) allOk = false;
  console.log(String(i + 1).padStart(2, ' '), lvl.name.padEnd(28, ' '), status, ' states=' + res.visited);
  if (res.path) console.log('     ' + res.path.join(' '));
}
console.log(allOk ? 'TOUT VALIDE' : 'A CORRIGER');
process.exit(allOk ? 0 : 1);
