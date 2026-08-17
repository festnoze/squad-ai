// First-person controller: fixed-step movement, circle-vs-grid collision,
// stamina-limited sprint, crouch, and the noise value the entity "hears".
// Deliberately three-free: main.js/camera.js turn (x, eyeY, z) into a camera pose.
import { moveCircle, TILE_SIZE } from './maze.js';

const RADIUS = 0.36;
const EYE_STAND = 1.6;
const EYE_CROUCH = 1.05;
const SPEED_WALK = 3.1;
const SPEED_SPRINT = 5.4;
const SPEED_CROUCH = 1.6;
const ACCEL = 16;
const STAMINA_DRAIN = 0.35; // per second while sprinting
const STAMINA_REGEN = 0.22; // per second while not sprinting
const STAMINA_REGEN_STILL = 0.4; // bonus regen while fully stopped

const SURFACE_NOISE = { carpet: 0.75, tile: 1.0, metal: 1.35, concrete: 1.1 };
const SURFACE_STEP_INTERVAL = { carpet: 0.62, tile: 0.5, metal: 0.42, concrete: 0.55 };

export function createPlayer(startX, startZ) {
  return {
    x: startX, z: startZ,
    prevX: startX, prevZ: startZ,
    vx: 0, vz: 0,
    yaw: 0,
    crouching: false,
    sprinting: false,
    moving: false,
    stamina: 1,
    noise01: 0,
    speed2D: 0,
    stepAccum: 0,
    stepEvent: false,
    checkpointX: startX,
    checkpointZ: startZ,
    encounters: 0,
    flashlightOn: false,
    batteryLife: 0, // seconds remaining, set by level setup when a flashlight level starts
    hasFlashlight: false,
  };
}

export function respawnPlayer(player, x, z) {
  player.x = x; player.z = z;
  player.prevX = x; player.prevZ = z;
  player.vx = 0; player.vz = 0;
  player.stamina = 1;
  player.stepAccum = 0;
}

export function setCheckpoint(player, x, z) {
  player.checkpointX = x;
  player.checkpointZ = z;
}

export function eyeHeight(player) {
  return player.crouching ? EYE_CROUCH : EYE_STAND;
}

/**
 * Fixed-step update. `input` exposes moveAxis()/any() like src/input.js.
 * `surface` is the theme's floor material key, used for noise + footstep pacing.
 */
export function updatePlayer(player, dt, input, maze, openDoors, surface, canMove) {
  player.prevX = player.x;
  player.prevZ = player.z;
  player.stepEvent = false;

  const wantCrouch = canMove && input.any('ControlLeft', 'ControlRight', 'char:c');
  player.crouching = wantCrouch;

  const axis = canMove ? input.moveAxis() : { x: 0, z: 0 };
  player.moving = axis.x !== 0 || axis.z !== 0;
  player.sprinting = canMove && player.moving && !player.crouching &&
    (input.down('ShiftLeft') || input.down('ShiftRight')) && player.stamina > 0.02;

  let maxSpeed = SPEED_WALK;
  if (player.crouching) maxSpeed = SPEED_CROUCH;
  else if (player.sprinting) maxSpeed = SPEED_SPRINT;

  const yaw = player.yaw;
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  const wishX = (axis.x * cy - axis.z * sy) * maxSpeed;
  const wishZ = -(axis.x * sy + axis.z * cy) * maxSpeed;

  const dvx = wishX - player.vx;
  const dvz = wishZ - player.vz;
  const dlen = Math.hypot(dvx, dvz);
  if (dlen > 1e-5) {
    const step = Math.min(dlen, ACCEL * dt);
    player.vx += (dvx / dlen) * step;
    player.vz += (dvz / dlen) * step;
  }

  const moved = moveCircle(maze, openDoors, player.x, player.z, player.vx * dt, player.vz * dt, RADIUS);
  player.x = moved.x;
  player.z = moved.z;
  player.speed2D = Math.hypot(player.vx, player.vz);

  // stamina
  if (player.sprinting) player.stamina = Math.max(0, player.stamina - STAMINA_DRAIN * dt);
  else if (!player.moving) player.stamina = Math.min(1, player.stamina + STAMINA_REGEN_STILL * dt);
  else player.stamina = Math.min(1, player.stamina + STAMINA_REGEN * dt);

  // noise: base speed ratio scaled by surface, crouch always quiet regardless of surface
  const surfMul = SURFACE_NOISE[surface] ?? 1;
  let noiseTarget = 0;
  if (player.crouching && player.moving) noiseTarget = 0.12;
  else if (player.sprinting) noiseTarget = 1.0 * surfMul;
  else if (player.moving) noiseTarget = 0.42 * surfMul;
  player.noise01 = Math.min(1.4, player.noise01 + (noiseTarget - player.noise01) * Math.min(1, 10 * dt));

  // footsteps: distance accumulator so pace matches actual travel, not wall-clock time
  if (player.moving && player.speed2D > 0.15) {
    const interval = (SURFACE_STEP_INTERVAL[surface] ?? 0.55) * (player.sprinting ? 0.7 : player.crouching ? 1.3 : 1);
    player.stepAccum += player.speed2D * dt;
    if (player.stepAccum > interval * SPEED_WALK) {
      player.stepAccum = 0;
      player.stepEvent = true;
    }
  } else {
    player.stepAccum = 0;
  }

  // flashlight battery drain
  if (player.hasFlashlight && player.flashlightOn) {
    player.batteryLife = Math.max(0, player.batteryLife - dt);
    if (player.batteryLife <= 0) player.flashlightOn = false;
  }
}

/** Interaction always succeeds when physically possible (lesson B): never a silent no-op. */
export function toggleFlashlight(player) {
  if (!player.hasFlashlight) return false;
  if (!player.flashlightOn && player.batteryLife <= 0) return false;
  player.flashlightOn = !player.flashlightOn;
  return true;
}

export function addBattery(player, seconds) {
  player.hasFlashlight = true;
  player.batteryLife += seconds;
}

export const PLAYER_RADIUS = RADIUS;
export const TILE = TILE_SIZE;
