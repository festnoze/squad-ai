/**
 * Level integrity check. Runs in plain Node against src/layout.js - no browser,
 * no GPU, no three.js.
 *
 *   node tools/check-level.mjs
 *
 * It exists because a room added in the wrong place silently deleted the wall
 * that kept the armoury behind CAM-2's door, and the whole progression came
 * apart without anything visibly breaking. Geometry is data; data can be
 * asserted. Run this after touching the layout.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import {
  AREAS, DOOR_DEFS, CAMERA_DEFS, GUARD_DEFS, PICKUP_DEFS,
  PLAYER_SPAWN, EXIT_TILE, GRID_W, GRID_D,
} from '../src/layout.js';

const here = dirname(fileURLToPath(import.meta.url));

let failures = 0;
const ok = (name) => console.log(`  ok    ${name}`);
const fail = (name, detail) => {
  failures++;
  console.log(`  FAIL  ${name}${detail ? `\n          ${detail}` : ''}`);
};
const check = (name, cond, detail) => (cond ? ok(name) : fail(name, detail));
const section = (t) => console.log(`\n${t}`);

// ---------------------------------------------------------------- the grid
const open = Array.from({ length: GRID_D }, () => new Array(GRID_W).fill(false));
const owner = new Map();
const areaById = new Map(AREAS.map((a) => [a.id, a]));

section('Geometry');
{
  let overlaps = [];
  let oob = [];
  for (const a of AREAS) {
    if (a.x1 < a.x0 || a.z1 < a.z0) fail('rect is not inverted', a.id);
    // Row/column 0 and the last row/column must stay solid, or the level has
    // no outer wall and you can see out of it.
    if (a.x0 < 1 || a.z0 < 1 || a.x1 > GRID_W - 2 || a.z1 > GRID_D - 2) oob.push(a.id);
    for (let z = a.z0; z <= a.z1; z++) {
      for (let x = a.x0; x <= a.x1; x++) {
        const k = `${x},${z}`;
        if (owner.has(k)) overlaps.push(`${k}: ${owner.get(k)} <-> ${a.id}`);
        else owner.set(k, a.id);
        open[z][x] = true;
      }
    }
  }
  check('every area is inside the outer wall', oob.length === 0, oob.join(', '));
  check('no two areas claim the same tile', overlaps.length === 0, overlaps.slice(0, 5).join('\n          '));
}

// ------------------------------------------------------------- the textures
section('Textures');
{
  const tex = readFileSync(join(here, '../src/textures.js'), 'utf8');
  const defined = new Set([...tex.matchAll(/^ {2}(\w+)\(\) \{/gm)].map((m) => m[1]));
  const missing = new Set();
  for (const a of AREAS) {
    for (const t of [a.wall, a.floor, a.ceil]) {
      if (t && !defined.has(t)) missing.add(t);
    }
  }
  check('every area texture exists', missing.size === 0, [...missing].join(', '));
}

// ------------------------------------------------------------- entity tiles
section('Entity placement');
{
  const isOpen = (x, z) => x >= 0 && z >= 0 && x < GRID_W && z < GRID_D && open[z][x];
  const bad = [];
  if (!isOpen(...PLAYER_SPAWN.tile)) bad.push(`player spawn ${PLAYER_SPAWN.tile}`);
  if (!isOpen(...EXIT_TILE)) bad.push(`exit ${EXIT_TILE}`);
  for (const p of PICKUP_DEFS) if (!isOpen(...p.tile)) bad.push(`pickup ${p.kind} ${p.tile}`);
  for (const c of CAMERA_DEFS) if (!isOpen(...c.tile)) bad.push(`camera ${c.id} ${c.tile}`);
  for (const g of GUARD_DEFS) {
    for (const wp of g.route) if (!isOpen(...wp)) bad.push(`guard ${g.id} waypoint ${wp}`);
  }
  for (const d of DOOR_DEFS) {
    const a = areaById.get(d.area);
    if (!a) { bad.push(`door ${d.id} references unknown area ${d.area}`); continue; }
    const [x0, z0, x1, z1] = d.rect || [a.x0, a.z0, a.x1, a.z1];
    for (let z = z0; z <= z1; z++) {
      for (let x = x0; x <= x1; x++) if (!isOpen(x, z)) bad.push(`door ${d.id} tile ${x},${z}`);
    }
  }
  check('nothing is placed inside a wall', bad.length === 0, bad.join('\n          '));
}

// ------------------------------------------------------------ reachability
/**
 * Flood fill from the spawn. `opened` lists door ids that are unlocked; the two
 * secret ways are named 'PANEL' (toilets) and 'GRATE' (yard end).
 */
const SECRET_SEAMS = {
  PANEL: [[4, 32, 4, 33]],
  GRATE: [[23, 39, 24, 39], [23, 40, 24, 40]],
};

function reach(opened = []) {
  const blockedTiles = new Set();
  for (const d of DOOR_DEFS) {
    if (opened.includes(d.id)) continue;
    const a = areaById.get(d.area);
    const [x0, z0, x1, z1] = d.rect || [a.x0, a.z0, a.x1, a.z1];
    for (let z = z0; z <= z1; z++) for (let x = x0; x <= x1; x++) blockedTiles.add(`${x},${z}`);
  }
  const blockedSeams = new Set();
  for (const [name, seams] of Object.entries(SECRET_SEAMS)) {
    if (opened.includes(name)) continue;
    for (const [ax, az, bx, bz] of seams) {
      blockedSeams.add(`${ax},${az}|${bx},${bz}`);
      blockedSeams.add(`${bx},${bz}|${ax},${az}`);
    }
  }

  const start = PLAYER_SPAWN.tile.join(',');
  const seen = new Set([start]);
  const queue = [PLAYER_SPAWN.tile];
  while (queue.length) {
    const [x, z] = queue.shift();
    for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = x + dx, nz = z + dz;
      const k = `${nx},${nz}`;
      if (seen.has(k)) continue;
      if (nx < 0 || nz < 0 || nx >= GRID_W || nz >= GRID_D || !open[nz][nx]) continue;
      if (blockedTiles.has(k)) continue;
      if (blockedSeams.has(`${x},${z}|${nx},${nz}`)) continue;
      seen.add(k);
      queue.push([nx, nz]);
    }
  }
  return seen;
}

const at = (set, x, z) => set.has(`${x},${z}`);

section('Progression gating');
{
  const locked = reach([]);
  const d2 = reach(['D2']);
  const d3 = reach(['D3']);
  const d34 = reach(['D3', 'D4']);
  const secret = reach(['PANEL', 'GRATE']);

  // Landmarks: [label, tile]
  const ARMOURY = [42, 9];
  const YARD = [30, 33];
  const EXIT = EXIT_TILE;
  const BACKROOMS = [10, 35];

  check('armoury is sealed until CAM-2 opens D2', !at(locked, ...ARMOURY),
    'a room was placed in the wall column that gates it');
  check('armoury opens once D2 is released', at(d2, ...ARMOURY));

  check('yard is sealed until CAM-3 opens D3', !at(locked, ...YARD));
  check('yard opens once D3 is released', at(d3, ...YARD));

  check('exit is sealed until CAM-4 and CAM-5 open D4', !at(d3, ...EXIT));
  check('exit opens once D4 is released', at(d34, ...EXIT));

  check('backrooms are sealed from the prison', !at(locked, ...BACKROOMS));
  check('backrooms are sealed from the yard', !at(d34, ...BACKROOMS));
  check('backrooms open once both secret ways are worked loose', at(secret, ...BACKROOMS));
  check('the back way reaches the yard without D3', at(secret, ...YARD));
}

section('Room reachability (all doors locked)');
{
  const locked = reach([]);
  // Every named room except the ones that are meant to be gated.
  const GATED = new Set(['Armurerie', 'Cour de promenade', 'Porte principale', 'Sas de la cour', 'Hors-plan', 'Cuisine']);
  const unreachable = [];
  const byName = new Map();
  for (const a of AREAS) {
    if (!byName.has(a.name)) byName.set(a.name, []);
    byName.get(a.name).push(a);
  }
  for (const [name, list] of byName) {
    if (GATED.has(name)) continue;
    const anyReached = list.some((a) => {
      for (let z = a.z0; z <= a.z1; z++) {
        for (let x = a.x0; x <= a.x1; x++) if (at(locked, x, z)) return true;
      }
      return false;
    });
    if (!anyReached) unreachable.push(name);
  }
  check('every ungated room can be walked to', unreachable.length === 0, unreachable.join(', '));
  console.log(`  info  ${byName.size} named rooms, ${owner.size} walkable tiles`);
}

// ---------------------------------------------------------------------- end
console.log(`\n${failures === 0 ? 'PASS' : `${failures} FAILURE(S)`}\n`);
process.exit(failures === 0 ? 0 : 1);
