// Pure Node validation: for every level, confirm the maze generator produced
// a layout with a guaranteed path from start to exit, no isolated rooms, and
// entity patrol points that are all reachable. Run with: node tools/validate_levels.mjs
import { LEVELS, getLevelMaze } from '../src/levels.js';
import { bfsDistances, generateMaze } from '../src/maze.js';

function idx(w, x, y) { return y * w + x; }

let failures = 0;

for (let i = 0; i < LEVELS.length; i++) {
  const def = LEVELS[i];
  const maze = getLevelMaze(i);
  const problems = [];

  const dist = bfsDistances(maze.tiles, maze.width, maze.height, maze.startPos.x, maze.startPos.y);

  const exitDist = dist[idx(maze.width, maze.exitPos.x, maze.exitPos.y)];
  if (exitDist === -1) problems.push('exit unreachable from start');

  let isolatedRooms = 0;
  for (const r of maze.rooms) {
    if (dist[idx(maze.width, r.cx, r.cy)] === -1) isolatedRooms++;
  }
  if (isolatedRooms > 0) problems.push(`${isolatedRooms} isolated room(s)`);

  let unreachablePatrol = 0;
  for (const p of maze.patrolPoints) {
    if (dist[idx(maze.width, p.x, p.y)] === -1) unreachablePatrol++;
  }
  if (unreachablePatrol > 0) problems.push(`${unreachablePatrol} unreachable patrol point(s)`);

  let unreachableItems = 0;
  for (const it of maze.items) {
    if (dist[idx(maze.width, it.x, it.y)] === -1) unreachableItems++;
  }
  if (unreachableItems > 0) problems.push(`${unreachableItems} unreachable item(s)`);

  if (def.entity && maze.patrolPoints.length === 0) {
    problems.push('level has an entity but no patrol points were generated');
  }

  // Determinism check: regenerate from the same seed and confirm byte-identical tiles.
  const fresh = generateMaze({
    seed: def.seed, width: def.width, height: def.height, roomCount: def.roomCount,
    minRoomSize: def.minRoomSize, maxRoomSize: def.maxRoomSize, loopChance: def.loopChance,
    patrolPoints: def.entity ? Math.min(8, def.roomCount - 1) : 0,
    itemCount: def.itemCount, itemType: def.itemType,
  });
  const identical = fresh.tiles.length === maze.tiles.length &&
    fresh.tiles.every((v, i2) => v === maze.tiles[i2]);
  if (!identical) problems.push('regeneration from the same seed produced a different layout (non-deterministic)');

  const status = problems.length === 0 ? 'PASS' : 'FAIL';
  if (status === 'FAIL') failures++;
  console.log(
    `[${status}] Level ${i} "${def.name}" (${def.theme}, seed ${def.seed}) - ` +
    `rooms=${maze.rooms.length} doors=${maze.doors.length} exitDist=${exitDist} ` +
    `patrol=${maze.patrolPoints.length} items=${maze.items.length}` +
    (problems.length ? ` :: ${problems.join('; ')}` : '')
  );
}

console.log('');
if (failures > 0) {
  console.log(`VALIDATION FAILED: ${failures} / ${LEVELS.length} level(s) have a problem.`);
  process.exit(1);
} else {
  console.log(`VALIDATION OK: all ${LEVELS.length} levels have a guaranteed start-to-exit path.`);
  process.exit(0);
}
