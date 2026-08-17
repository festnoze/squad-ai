// Pure state machine for the black entity: patrol / chase / search. No three.js
// dependency so behaviour can be reasoned about (and unit-tested) in isolation.
import { worldToTile, hasLineOfSight, tileToWorldCenter, moveCircle, TILE_SIZE } from './maze.js';

const RADIUS = 0.42;
const IDLE_MAX = 3.5; // lesson: never stay frozen more than a few seconds

function stepToward(entity, tx, tz, speed, dt, maze, openDoors) {
  const dx = tx - entity.x;
  const dz = tz - entity.z;
  const dist = Math.hypot(dx, dz);
  if (dist < 1e-4) return dist;
  const step = Math.min(dist, speed * dt);
  const moved = moveCircle(maze, openDoors, entity.x, entity.z, (dx / dist) * step, (dz / dist) * step, RADIUS);
  entity.x = moved.x;
  entity.z = moved.z;
  entity.facing = Math.atan2(dx, dz);
  return dist;
}

/**
 * Creates one entity, spawned on one of the maze's patrol waypoints so several
 * entities on the same level do not stack on top of each other.
 */
export function createEntity(def, maze, index) {
  const patrol = maze.patrolPoints.length ? maze.patrolPoints : [maze.startPos];
  const spawnPt = patrol[index % patrol.length];
  const world = tileToWorldCenter(spawnPt.x, spawnPt.y);
  return {
    index,
    x: world.x,
    z: world.z,
    prevX: world.x,
    prevZ: world.z,
    facing: 0,
    state: 'patrol',
    patrolIndex: index % patrol.length,
    lastKnownX: 0,
    lastKnownZ: 0,
    loseTimer: 0,
    searchTimer: 0,
    idleTimer: 0,
    chaseSideFlip: false,
    speed: def.speed,
    patrolSpeed: def.patrolSpeed,
    sightRange: def.sightRange,
    hearRangeBase: def.hearRangeBase,
    loseTime: def.loseTime,
    searchTime: def.searchTime,
    patrol,
    detectedNow: false,
  };
}

/** Called after the player is teleported back to a checkpoint: the entity loses the trail. */
export function breakTrail(entity) {
  entity.state = 'search';
  entity.searchTimer = 0;
  entity.lastKnownX = entity.x;
  entity.lastKnownZ = entity.z;
}

/**
 * ctx = { maze, openDoors, playerX, playerZ, noise01 }
 * noise01 in [0,1]: how loud the player currently is (sprint > walk > crouch).
 */
export function updateEntity(entity, dt, ctx) {
  entity.prevX = entity.x;
  entity.prevZ = entity.z;
  const { maze, openDoors, playerX, playerZ, noise01 } = ctx;
  const pt = worldToTile(playerX, playerZ);
  const et = worldToTile(entity.x, entity.z);
  const dist = Math.hypot(playerX - entity.x, playerZ - entity.z);

  const sees = dist <= entity.sightRange && hasLineOfSight(maze, et.x, et.y, pt.x, pt.y, openDoors);
  const hearRange = entity.hearRangeBase * (0.35 + noise01 * 1.65);
  const hears = dist <= hearRange;
  entity.detectedNow = sees || hears;

  if (entity.detectedNow) {
    entity.state = 'chase';
    entity.lastKnownX = playerX;
    entity.lastKnownZ = playerZ;
    entity.loseTimer = 0;
  } else if (entity.state === 'chase') {
    entity.loseTimer += dt;
    if (entity.loseTimer >= entity.loseTime) {
      entity.state = 'search';
      entity.searchTimer = 0;
    }
  }

  if (entity.state === 'patrol') {
    const target = entity.patrol[entity.patrolIndex];
    const w = tileToWorldCenter(target.x, target.y);
    const remaining = stepToward(entity, w.x, w.z, entity.patrolSpeed, dt, maze, openDoors);
    entity.idleTimer = remaining < 0.4 ? entity.idleTimer + dt : 0;
    if (remaining < 0.3 || entity.idleTimer > IDLE_MAX) {
      entity.patrolIndex = (entity.patrolIndex + 1) % entity.patrol.length;
      entity.idleTimer = 0;
    }
  } else if (entity.state === 'chase') {
    const remaining = stepToward(entity, entity.lastKnownX, entity.lastKnownZ, entity.speed, dt, maze, openDoors);
    // `hears` (unlike `sees`) has no line-of-sight requirement, so an entity can
    // keep re-detecting a player through a wall and never fall through to the
    // loseTimer branch above, even while pinned against that wall with near-zero
    // net progress. Same anti-freeze idea as patrol/search: once stuck for too
    // long, sidestep perpendicular to the blocked direction to break out
    // (lesson: never stay frozen more than a few seconds).
    entity.idleTimer = remaining < 0.4 ? entity.idleTimer + dt : 0;
    if (entity.idleTimer > IDLE_MAX) {
      const dx = entity.lastKnownX - entity.x;
      const dz = entity.lastKnownZ - entity.z;
      const len = Math.hypot(dx, dz) || 1;
      entity.chaseSideFlip = !entity.chaseSideFlip;
      const side = entity.chaseSideFlip ? 1 : -1;
      const sideX = entity.x + (-dz / len) * side * TILE_SIZE;
      const sideZ = entity.z + (dx / len) * side * TILE_SIZE;
      stepToward(entity, sideX, sideZ, entity.speed, dt, maze, openDoors);
      entity.idleTimer = 0;
    }
  } else if (entity.state === 'search') {
    entity.searchTimer += dt;
    // Circle around the last known position while the search window lasts,
    // so the entity keeps moving instead of freezing over a doorway.
    const angle = entity.searchTimer * 1.1;
    const radius = TILE_SIZE * 0.9;
    const tx = entity.lastKnownX + Math.cos(angle) * radius;
    const tz = entity.lastKnownZ + Math.sin(angle) * radius;
    const remaining = stepToward(entity, tx, tz, entity.patrolSpeed, dt, maze, openDoors);
    entity.idleTimer = remaining < 0.4 ? entity.idleTimer + dt : 0;
    if (entity.idleTimer > IDLE_MAX) {
      // stuck against a wall while circling: nudge back toward the anchor point directly
      stepToward(entity, entity.lastKnownX, entity.lastKnownZ, entity.patrolSpeed, dt, maze, openDoors);
    }
    if (entity.searchTimer >= entity.searchTime) {
      entity.state = 'patrol';
      // resume patrol from whichever waypoint is nearest, so it does not walk back across the map
      let bestI = 0;
      let bestD = Infinity;
      for (let i = 0; i < entity.patrol.length; i++) {
        const w = tileToWorldCenter(entity.patrol[i].x, entity.patrol[i].y);
        const d = (w.x - entity.x) ** 2 + (w.z - entity.z) ** 2;
        if (d < bestD) { bestD = d; bestI = i; }
      }
      entity.patrolIndex = bestI;
    }
  }
}

export const ENTITY_RADIUS = RADIUS;
