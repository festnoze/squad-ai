// Pure tile-grid maze generation and graph queries. No three.js here so this
// module can be unit-tested from plain Node (see tools/validate_levels.mjs).

export const TILE_SIZE = 3; // metres per tile edge

export const TILE = Object.freeze({
  WALL: 0,
  FLOOR: 1,
  DOOR: 2,
  EXIT: 3,
});

/** Deterministic PRNG (mulberry32). Same seed -> same sequence, always. */
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function rng() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function idx(width, x, y) {
  return y * width + x;
}

function distSq(a, b) {
  const dx = a.cx - b.cx;
  const dy = a.cy - b.cy;
  return dx * dx + dy * dy;
}

function insideAnyRoom(rooms, x, y) {
  for (let i = 0; i < rooms.length; i++) {
    const r = rooms[i];
    if (x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h) return true;
  }
  return false;
}

/** Place non-overlapping rectangular rooms (with a one-tile margin) via rejection sampling. */
function placeRooms(rng, width, height, roomCount, minSize, maxSize) {
  const rooms = [];
  let attempts = 0;
  const maxAttempts = roomCount * 60;
  while (rooms.length < roomCount && attempts < maxAttempts) {
    attempts++;
    const w = minSize + Math.floor(rng() * (maxSize - minSize + 1));
    const h = minSize + Math.floor(rng() * (maxSize - minSize + 1));
    const x = 2 + Math.floor(rng() * Math.max(1, width - w - 4));
    const y = 2 + Math.floor(rng() * Math.max(1, height - h - 4));
    let overlap = false;
    for (const r of rooms) {
      if (
        x - 2 < r.x + r.w + 2 &&
        x + w + 2 > r.x - 2 &&
        y - 2 < r.y + r.h + 2 &&
        y + h + 2 > r.y - 2
      ) {
        overlap = true;
        break;
      }
    }
    if (overlap) continue;
    rooms.push({ x, y, w, h, cx: x + (w >> 1), cy: y + (h >> 1) });
  }
  return rooms;
}

/** Carve a single-tile-wide L-shaped corridor of FLOOR between two room centres. */
function carveCorridor(tiles, width, height, a, b, rng) {
  let x = a.cx;
  let y = a.cy;
  const tx = b.cx;
  const ty = b.cy;
  const horizFirst = rng() < 0.5;
  const path = [];
  if (horizFirst) {
    while (x !== tx) { x += Math.sign(tx - x); path.push([x, y]); }
    while (y !== ty) { y += Math.sign(ty - y); path.push([x, y]); }
  } else {
    while (y !== ty) { y += Math.sign(ty - y); path.push([x, y]); }
    while (x !== tx) { x += Math.sign(tx - x); path.push([x, y]); }
  }
  for (const [px, py] of path) {
    if (px < 1 || py < 1 || px >= width - 1 || py >= height - 1) continue;
    const i = idx(width, px, py);
    if (tiles[i] === TILE.WALL) tiles[i] = TILE.FLOOR;
  }
}

function isWalkableTile(t) {
  return t === TILE.FLOOR || t === TILE.DOOR || t === TILE.EXIT;
}

/** BFS over the walkable tile graph, returns Int32Array of distances (-1 = unreachable). */
export function bfsDistances(tiles, width, height, sx, sy) {
  const dist = new Int32Array(width * height).fill(-1);
  const startI = idx(width, sx, sy);
  if (!isWalkableTile(tiles[startI])) return dist;
  dist[startI] = 0;
  const queue = [startI];
  let head = 0;
  while (head < queue.length) {
    const cur = queue[head++];
    const cx = cur % width;
    const cy = (cur / width) | 0;
    const d = dist[cur];
    const neighbors = [
      [cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1],
    ];
    for (const [nx, ny] of neighbors) {
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const ni = idx(width, nx, ny);
      if (dist[ni] !== -1 || !isWalkableTile(tiles[ni])) continue;
      dist[ni] = d + 1;
      queue.push(ni);
    }
  }
  return dist;
}

/** Nearest-neighbour tour over a subset of rooms, used as the entity patrol loop. */
function buildPatrolLoop(rooms, startRoom, rng, maxPoints) {
  if (maxPoints <= 0) return [];
  const pool = rooms.filter((r) => r !== startRoom);
  if (pool.length === 0) return [];
  const wanted = Math.min(maxPoints, pool.length);
  // Pick a spread-out subset: sort by distance from start, then stride through it.
  const sorted = pool.slice().sort((a, b) => distSq(a, startRoom) - distSq(b, startRoom));
  const chosen = [];
  const stride = Math.max(1, Math.floor(sorted.length / wanted));
  for (let i = 0; i < sorted.length && chosen.length < wanted; i += stride) chosen.push(sorted[i]);

  const loop = [];
  const remaining = chosen.slice();
  let cur = remaining.shift();
  loop.push({ x: cur.cx, y: cur.cy });
  while (remaining.length) {
    let bestI = 0;
    let bestD = Infinity;
    for (let i = 0; i < remaining.length; i++) {
      const d = distSq(cur, remaining[i]);
      if (d < bestD) { bestD = d; bestI = i; }
    }
    cur = remaining.splice(bestI, 1)[0];
    loop.push({ x: cur.cx, y: cur.cy });
  }
  // small deterministic shuffle of the starting phase so levels feel less mechanical
  const offset = Math.floor(rng() * loop.length);
  return loop.slice(offset).concat(loop.slice(0, offset));
}

/** Scatter pickable items (battery / notebook) on floor tiles away from the start. */
function placeItems(rng, tiles, width, height, startPos, count, type) {
  const items = [];
  let attempts = 0;
  const maxAttempts = count * 200;
  while (items.length < count && attempts < maxAttempts) {
    attempts++;
    const x = 2 + Math.floor(rng() * (width - 4));
    const y = 2 + Math.floor(rng() * (height - 4));
    const t = tiles[idx(width, x, y)];
    if (t !== TILE.FLOOR) continue;
    const dx = x - startPos.x;
    const dy = y - startPos.y;
    if (dx * dx + dy * dy < 16) continue;
    if (items.some((it) => it.x === x && it.y === y)) continue;
    items.push({ x, y, type });
  }
  return items;
}

/**
 * Build a full maze from a deterministic config. Returns a plain-data Maze:
 * { width, height, tiles(Uint8Array), rooms, doors, startPos, exitPos, patrolPoints, items }
 */
export function generateMaze(cfg) {
  const {
    seed, width, height, roomCount, minRoomSize, maxRoomSize,
    loopChance = 0.12, patrolPoints: patrolCount = 6,
    itemCount = 0, itemType = 'notebook',
  } = cfg;

  const rng = mulberry32(seed);
  const tiles = new Uint8Array(width * height).fill(TILE.WALL);

  const rooms = placeRooms(rng, width, height, roomCount, minRoomSize, maxRoomSize);
  for (const r of rooms) {
    for (let y = r.y; y < r.y + r.h; y++) {
      for (let x = r.x; x < r.x + r.w; x++) tiles[idx(width, x, y)] = TILE.FLOOR;
    }
  }

  // Spanning tree: each room connects to its nearest already-placed predecessor.
  const edges = [];
  for (let i = 1; i < rooms.length; i++) {
    let best = 0;
    let bestD = Infinity;
    for (let j = 0; j < i; j++) {
      const d = distSq(rooms[i], rooms[j]);
      if (d < bestD) { bestD = d; best = j; }
    }
    edges.push([i, best]);
  }
  // Extra edges between nearby rooms create loops so the entity cannot trivially wall the player in.
  const loopRange = (Math.max(width, height) * 0.55) ** 2;
  for (let i = 0; i < rooms.length; i++) {
    for (let j = i + 1; j < rooms.length; j++) {
      if (rng() < loopChance && distSq(rooms[i], rooms[j]) < loopRange) edges.push([i, j]);
    }
  }
  for (const [a, b] of edges) carveCorridor(tiles, width, height, rooms[a], rooms[b], rng);

  // Doorways: corridor tiles that touch a room's interior become DOOR tiles.
  const doorIdx = new Set();
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const i = idx(width, x, y);
      if (tiles[i] !== TILE.FLOOR || insideAnyRoom(rooms, x, y)) continue;
      const touchesRoom =
        insideAnyRoom(rooms, x + 1, y) || insideAnyRoom(rooms, x - 1, y) ||
        insideAnyRoom(rooms, x, y + 1) || insideAnyRoom(rooms, x, y - 1);
      if (touchesRoom) doorIdx.add(i);
    }
  }
  const doors = [];
  for (const i of doorIdx) {
    tiles[i] = TILE.DOOR;
    doors.push({ x: i % width, y: (i / width) | 0 });
  }

  const startRoom = rooms[0];
  const startPos = { x: startRoom.cx, y: startRoom.cy };
  const dist = bfsDistances(tiles, width, height, startPos.x, startPos.y);

  let exitRoomIdx = 0;
  let exitDist = -1;
  for (let i = 1; i < rooms.length; i++) {
    const d = dist[idx(width, rooms[i].cx, rooms[i].cy)];
    if (d > exitDist) { exitDist = d; exitRoomIdx = i; }
  }
  const exitRoom = rooms[exitRoomIdx];
  tiles[idx(width, exitRoom.cx, exitRoom.cy)] = TILE.EXIT;
  const exitPos = { x: exitRoom.cx, y: exitRoom.cy };

  const patrolPoints = buildPatrolLoop(rooms, startRoom, rng, patrolCount);
  const items = placeItems(rng, tiles, width, height, startPos, itemCount, itemType);

  return { width, height, tiles, rooms, doors, startPos, exitPos, patrolPoints, items, seed };
}

export function tileAt(maze, x, y) {
  if (x < 0 || y < 0 || x >= maze.width || y >= maze.height) return TILE.WALL;
  return maze.tiles[idx(maze.width, x, y)];
}

/** Walkability that accounts for runtime door state (a Set of "x,y" keys that are open). */
export function isWalkableAt(maze, x, y, openDoors) {
  const t = tileAt(maze, x, y);
  if (t === TILE.WALL) return false;
  if (t === TILE.DOOR) return openDoors ? openDoors.has(`${x},${y}`) : false;
  return true;
}

/** Simple grid line-of-sight: walk the line in tile steps, blocked by any WALL or closed DOOR. */
export function hasLineOfSight(maze, x0, y0, x1, y1, openDoors) {
  const dx = x1 - x0;
  const dy = y1 - y0;
  const steps = Math.max(Math.abs(dx), Math.abs(dy), 1) * 2;
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const x = Math.round(x0 + dx * t);
    const y = Math.round(y0 + dy * t);
    if (!isWalkableAt(maze, x, y, openDoors)) return false;
  }
  return true;
}

export function worldToTile(wx, wz) {
  return { x: Math.floor(wx / TILE_SIZE), y: Math.floor(wz / TILE_SIZE) };
}

export function tileToWorldCenter(x, y) {
  return { x: x * TILE_SIZE + TILE_SIZE / 2, z: y * TILE_SIZE + TILE_SIZE / 2 };
}

/** True if a circle of radius r centred at (cx,cz) world-space overlaps no wall/closed door. */
export function circleFree(maze, openDoors, cx, cz, r) {
  const corners = [
    [cx - r, cz - r], [cx + r, cz - r], [cx - r, cz + r], [cx + r, cz + r],
  ];
  for (const [wx, wz] of corners) {
    const t = worldToTile(wx, wz);
    if (!isWalkableAt(maze, t.x, t.y, openDoors)) return false;
  }
  return true;
}

/**
 * Axis-separated circle-vs-grid slide used by both the player and the entity,
 * so a body sliding along a wall does not get snagged on grid corners.
 * Returns a new {x, z}; never allocates beyond that one result object.
 */
export function moveCircle(maze, openDoors, x, z, dx, dz, radius) {
  let nx = x + dx;
  if (circleFree(maze, openDoors, nx, z, radius)) x = nx;
  let nz = z + dz;
  if (circleFree(maze, openDoors, x, nz, radius)) z = nz;
  return { x, z };
}
