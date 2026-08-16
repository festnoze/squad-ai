/**
 * PARADOXE - deterministic fixed step simulation.
 *
 * This module never imports three and never touches the DOM: it is the single
 * source of truth that both the live run and every clone replay go through.
 * Correctness of the whole game rests on one rule: the same sequence of input
 * bytes fed to a fresh sim produces the exact same trajectory, forever. So:
 *
 *  - no Math.random, no Date, no dt from the wall clock (SIM.dt is a constant),
 *  - the camera yaw is quantised to a byte before it can influence movement,
 *  - nothing is allocated per tick except the rare event object,
 *  - and, the subtle one, bodies are stepped and iterated in *age* order
 *    (oldest clone first, live player last). A clone recorded as "the newest
 *    actor" keeps every older actor in front of it on replay, so the relative
 *    resolution order of any pair is the same in every run. Ordering by array
 *    index instead would flip pairs between runs and invent paradoxes.
 *
 * Actors also start mutually intangible: every run begins with all of them
 * stacked on the same spawn tile, and a pair only becomes solid once its boxes
 * have separated. Without that rule the very first clone would be shoved out
 * of the spawn on tick one and diverge instantly.
 */

import { SIM, PLAYER, CRATE, WORLD, BIT } from './config.js';

const DT = SIM.dt;
const EPS = 1e-4;
/** Penetration beyond which a vertical hit is treated as a side hit instead. */
const LEDGE = 0.45;
/**
 * Same idea for landings on another body, but much more generous: landing on a
 * clone's head is a core move and the target is only 0.66 wide, so the window
 * where a descent still snaps onto it has to be wide enough to aim at. It stays
 * below the 0.9 body height, so walking into a clone's side never pops you up.
 */
const BODY_LEDGE = 0.62;
const TAU = Math.PI * 2;

/** Walls are 3.6 tall: out of reach even jumping off the tallest block (3.31). */
function cellTop(h) {
  return h === 3 ? WORLD.wallHeight : h;
}

function makeActor(index) {
  return {
    kind: 'actor',
    index,
    active: false,
    isPlayer: false,
    /** Age rank: 0 is the oldest clone, -1 marks the live player. */
    age: -1,
    x: 0,
    y: 0,
    z: 0,
    vx: 0,
    vy: 0,
    vz: 0,
    hw: PLAYER.halfWidth,
    hd: PLAYER.halfWidth,
    hh: PLAYER.height,
    grounded: false,
    groundBody: -1,
    lastDx: 0,
    lastDz: 0,
    faceX: 0,
    faceZ: -1,
    yawAngle: 0,
    coyote: 0,
    jumpBuffer: 0,
    prevBits: 0,
    bits: 0,
    teleCd: 0,
    carrying: -1,
    buttonMask: 0,
    solidMask: 0,
    fallen: false,
    frozen: false,
  };
}

function makeCrate(index) {
  return {
    kind: 'crate',
    index,
    active: false,
    x: 0,
    y: 0,
    z: 0,
    vx: 0,
    vy: 0,
    vz: 0,
    hw: CRATE.half,
    hd: CRATE.half,
    hh: CRATE.size,
    grounded: false,
    groundBody: -1,
    lastDx: 0,
    lastDz: 0,
    carriedBy: -1,
  };
}

export function createSim(level) {
  const w = level.w;
  const h = level.h;

  const actors = [];
  for (let i = 0; i < SIM.maxActors; i++) actors.push(makeActor(i));
  const crates = [];
  for (let i = 0; i < SIM.maxCrates; i++) crates.push(makeCrate(SIM.maxActors + i));

  /** Index addressable body table: body.index is always its slot here. */
  const bodies = actors.concat(crates);

  /** Canonical iteration order: oldest clone, ..., newest clone, player, crates. */
  const iterBodies = [];
  for (let i = 1; i < SIM.maxActors; i++) iterBodies.push(actors[i]);
  iterBodies.push(actors[0]);
  for (let i = 0; i < crates.length; i++) iterBodies.push(crates[i]);

  const heightNow = new Int8Array(w * h);
  const fragileTimer = new Int16Array(w * h);
  const fragileCells = [];
  for (let i = 0; i < w * h; i++) if (level.fragile[i]) fragileCells.push(i);

  const doorOpen = new Uint8Array(level.doors.length);
  const groupCount = new Int8Array(8);
  const groupOn = new Uint8Array(8);
  const buttonOn = new Uint8Array(level.buttons.length);
  const plateOn = new Uint8Array(level.plates.length);

  const traceStride = (SIM.maxActors + SIM.maxCrates) * 3;
  const maxTicks = level.ticks + 4;
  const trace = new Float32Array(maxTicks * traceStride);

  const sim = {
    level,
    actors,
    crates,
    bodies,
    heightNow,
    fragileTimer,
    doorOpen,
    groupOn,
    groupCount,
    buttonOn,
    plateOn,
    trace,
    traceStride,
    maxTicks,
    tick: 0,
    actorCount: 1,
    status: 'run',
    reason: '',
    /** Events emitted during the last step(). Cleared at the start of each step. */
    frameEvents: [],
    recordings: null,
  };

  const exitTop = Math.max(0, cellTop(level.height[level.exit.z * w + level.exit.x]));
  sim.exitTop = exitTop;

  function heightAt(cx, cz) {
    if (cx < 0 || cz < 0 || cx >= w || cz >= h) return 3;
    return heightNow[cz * w + cx];
  }

  function emit(actorIndex, key) {
    sim.frameEvents.push({ actor: actorIndex, key, tick: sim.tick });
  }

  /** Two actors ignore each other until their boxes have separated once. */
  function pairIgnored(b, o) {
    if (b.kind !== 'actor' || o.kind !== 'actor') return false;
    return (b.solidMask & (1 << o.index)) === 0;
  }

  function skipBody(b, o) {
    if (o === b || !o.active) return true;
    if (o.kind === 'crate' && o.carriedBy >= 0) return true;
    if (b.kind === 'actor' && b.carrying >= 0 && b.carrying + SIM.maxActors === o.index) return true;
    if (pairIgnored(b, o)) return true;
    return false;
  }

  // -------------------------------------------------------------------------
  // Collision primitives, all on axis aligned boxes
  //   [x-hw, x+hw] x [y, y+hh] x [z-hd, z+hd]
  // -------------------------------------------------------------------------

  /** True when body `b` currently intersects anything solid. Used to test moves. */
  function blocked(b, ignoreIndex) {
    const minX = b.x - b.hw;
    const maxX = b.x + b.hw;
    const minY = b.y;
    const maxY = b.y + b.hh;
    const minZ = b.z - b.hd;
    const maxZ = b.z + b.hd;
    const cx0 = Math.floor(minX + EPS);
    const cx1 = Math.floor(maxX - EPS);
    const cz0 = Math.floor(minZ + EPS);
    const cz1 = Math.floor(maxZ - EPS);
    for (let cz = cz0; cz <= cz1; cz++) {
      for (let cx = cx0; cx <= cx1; cx++) {
        const hv = heightAt(cx, cz);
        if (hv < 0) continue;
        const boxMin = hv === 0 ? -1.2 : 0;
        const boxMax = hv === 0 ? 0 : cellTop(hv);
        if (minY < boxMax - EPS && maxY > boxMin + EPS) return true;
      }
    }
    for (let i = 0; i < level.doors.length; i++) {
      if (doorOpen[i]) continue;
      const d = level.doors[i];
      if (maxX <= d.x + EPS || minX >= d.x + 1 - EPS) continue;
      if (maxZ <= d.z + EPS || minZ >= d.z + 1 - EPS) continue;
      if (minY < WORLD.doorHeight - EPS && maxY > EPS) return true;
    }
    for (let k = 0; k < iterBodies.length; k++) {
      const o = iterBodies[k];
      if (skipBody(b, o) || o.index === ignoreIndex) continue;
      if (maxX <= o.x - o.hw + EPS || minX >= o.x + o.hw - EPS) continue;
      if (maxZ <= o.z - o.hd + EPS || minZ >= o.z + o.hd - EPS) continue;
      if (maxY <= o.y + EPS || minY >= o.y + o.hh - EPS) continue;
      return true;
    }
    return false;
  }

  function moveY(b) {
    b.y += b.vy * DT;
    b.grounded = false;
    b.groundBody = -1;
    const minX = b.x - b.hw;
    const maxX = b.x + b.hw;
    const minZ = b.z - b.hd;
    const maxZ = b.z + b.hd;
    const cx0 = Math.floor(minX + EPS);
    const cx1 = Math.floor(maxX - EPS);
    const cz0 = Math.floor(minZ + EPS);
    const cz1 = Math.floor(maxZ - EPS);
    for (let cz = cz0; cz <= cz1; cz++) {
      for (let cx = cx0; cx <= cx1; cx++) {
        const hv = heightAt(cx, cz);
        if (hv < 0) continue;
        const boxMin = hv === 0 ? -1.2 : 0;
        const boxMax = hv === 0 ? 0 : cellTop(hv);
        if (b.y >= boxMax - EPS || b.y + b.hh <= boxMin + EPS) continue;
        if (b.vy <= 0) {
          // Only land when we came from above: a side penetration must be
          // resolved horizontally, otherwise a body pops to the top of a wall.
          if (b.y < boxMax - LEDGE) continue;
          b.y = boxMax;
          b.vy = 0;
          b.grounded = true;
        } else {
          if (b.y + b.hh > boxMin + LEDGE) continue;
          b.y = boxMin - b.hh;
          b.vy = 0;
        }
      }
    }
    for (let i = 0; i < level.doors.length; i++) {
      if (doorOpen[i]) continue;
      const d = level.doors[i];
      if (maxX <= d.x + EPS || minX >= d.x + 1 - EPS) continue;
      if (maxZ <= d.z + EPS || minZ >= d.z + 1 - EPS) continue;
      if (b.y >= WORLD.doorHeight - EPS || b.y + b.hh <= EPS) continue;
      if (b.vy <= 0 && b.y >= WORLD.doorHeight - LEDGE) {
        b.y = WORLD.doorHeight;
        b.vy = 0;
        b.grounded = true;
      }
    }
    for (let k = 0; k < iterBodies.length; k++) {
      const o = iterBodies[k];
      if (skipBody(b, o)) continue;
      if (maxX <= o.x - o.hw + EPS || minX >= o.x + o.hw - EPS) continue;
      if (maxZ <= o.z - o.hd + EPS || minZ >= o.z + o.hd - EPS) continue;
      const boxMin = o.y;
      const boxMax = o.y + o.hh;
      if (b.y >= boxMax - EPS || b.y + b.hh <= boxMin + EPS) continue;
      if (b.vy <= 0) {
        if (b.y < boxMax - BODY_LEDGE) continue;
        b.y = boxMax;
        b.vy = 0;
        b.grounded = true;
        b.groundBody = o.index;
      } else {
        if (b.y + b.hh > boxMin + LEDGE) continue;
        b.y = boxMin - b.hh;
        b.vy = 0;
      }
    }
  }

  /**
   * Horizontal move on one axis (ax 0 = x, 2 = z). Actors push crates: the
   * crate is offered the same penetration and, if it fits, both advance.
   */
  function moveH(b, ax, delta) {
    if (delta === 0) return;
    if (ax === 0) b.x += delta;
    else b.z += delta;
    const minY = b.y;
    const maxY = b.y + b.hh;
    let minX = b.x - b.hw;
    let maxX = b.x + b.hw;
    let minZ = b.z - b.hd;
    let maxZ = b.z + b.hd;

    const cx0 = Math.floor(minX + EPS);
    const cx1 = Math.floor(maxX - EPS);
    const cz0 = Math.floor(minZ + EPS);
    const cz1 = Math.floor(maxZ - EPS);
    for (let cz = cz0; cz <= cz1; cz++) {
      for (let cx = cx0; cx <= cx1; cx++) {
        const hv = heightAt(cx, cz);
        if (hv < 0) continue;
        const boxMin = hv === 0 ? -1.2 : 0;
        const boxMax = hv === 0 ? 0 : cellTop(hv);
        if (minY >= boxMax - EPS || maxY <= boxMin + EPS) continue;
        if (ax === 0) {
          if (maxX <= cx + EPS || minX >= cx + 1 - EPS) continue;
          b.x = delta > 0 ? cx - b.hw : cx + 1 + b.hw;
          b.vx = 0;
          minX = b.x - b.hw;
          maxX = b.x + b.hw;
        } else {
          if (maxZ <= cz + EPS || minZ >= cz + 1 - EPS) continue;
          b.z = delta > 0 ? cz - b.hd : cz + 1 + b.hd;
          b.vz = 0;
          minZ = b.z - b.hd;
          maxZ = b.z + b.hd;
        }
      }
    }

    for (let i = 0; i < level.doors.length; i++) {
      if (doorOpen[i]) continue;
      const d = level.doors[i];
      if (minY >= WORLD.doorHeight - EPS || maxY <= EPS) continue;
      if (maxX <= d.x + EPS || minX >= d.x + 1 - EPS) continue;
      if (maxZ <= d.z + EPS || minZ >= d.z + 1 - EPS) continue;
      if (ax === 0) {
        b.x = delta > 0 ? d.x - b.hw : d.x + 1 + b.hw;
        b.vx = 0;
        minX = b.x - b.hw;
        maxX = b.x + b.hw;
      } else {
        b.z = delta > 0 ? d.z - b.hd : d.z + 1 + b.hd;
        b.vz = 0;
        minZ = b.z - b.hd;
        maxZ = b.z + b.hd;
      }
    }

    for (let k = 0; k < iterBodies.length; k++) {
      const o = iterBodies[k];
      if (skipBody(b, o)) continue;
      if (minY >= o.y + o.hh - EPS || maxY <= o.y + EPS) continue;
      if (maxX <= o.x - o.hw + EPS || minX >= o.x + o.hw - EPS) continue;
      if (maxZ <= o.z - o.hd + EPS || minZ >= o.z + o.hd - EPS) continue;

      let pushed = false;
      if (b.kind === 'actor' && o.kind === 'crate') {
        const amount =
          ax === 0
            ? delta > 0
              ? maxX - (o.x - o.hw)
              : minX - (o.x + o.hw)
            : delta > 0
              ? maxZ - (o.z - o.hd)
              : minZ - (o.z + o.hd);
        const oldX = o.x;
        const oldZ = o.z;
        if (ax === 0) o.x += amount;
        else o.z += amount;
        if (blocked(o, b.index)) {
          o.x = oldX;
          o.z = oldZ;
        } else {
          pushed = true;
        }
      }
      if (pushed) continue;

      if (ax === 0) {
        b.x = delta > 0 ? o.x - o.hw - b.hw : o.x + o.hw + b.hw;
        b.vx = 0;
        minX = b.x - b.hw;
        maxX = b.x + b.hw;
      } else {
        b.z = delta > 0 ? o.z - o.hd - b.hd : o.z + o.hd + b.hd;
        b.vz = 0;
        minZ = b.z - b.hd;
        maxZ = b.z + b.hd;
      }
    }
  }

  // -------------------------------------------------------------------------
  // Actor logic
  // -------------------------------------------------------------------------

  function stepActor(a, bits, yawByte) {
    a.bits = bits;
    if (a.fallen) return;

    // Ride whatever we stood on last tick (one tick of lag, invisible at 60 Hz).
    if (a.groundBody >= 0) {
      const g = bodies[a.groundBody];
      a.x += g.lastDx;
      a.z += g.lastDz;
    }
    const startX = a.x;
    const startZ = a.z;

    const yaw = (yawByte / 256) * TAU;
    a.yawAngle = yaw;
    const fx = -Math.sin(yaw);
    const fz = -Math.cos(yaw);
    const rx = Math.cos(yaw);
    const rz = -Math.sin(yaw);

    const iz = (bits & BIT.forward ? 1 : 0) - (bits & BIT.back ? 1 : 0);
    const ix = (bits & BIT.right ? 1 : 0) - (bits & BIT.left ? 1 : 0);
    let dx = rx * ix + fx * iz;
    let dz = rz * ix + fz * iz;
    const len = Math.sqrt(dx * dx + dz * dz);
    if (len > 1e-6) {
      dx /= len;
      dz /= len;
      a.faceX = dx;
      a.faceZ = dz;
    } else {
      dx = 0;
      dz = 0;
    }

    // Jump: buffered on the rising edge, allowed for a few coyote ticks.
    const jumpEdge = (bits & BIT.jump) !== 0 && (a.prevBits & BIT.jump) === 0;
    if (jumpEdge) a.jumpBuffer = PLAYER.jumpBufferTicks;
    if (a.grounded) a.coyote = PLAYER.coyoteTicks;
    else if (a.coyote > 0) a.coyote--;
    if (a.jumpBuffer > 0 && a.coyote > 0) {
      a.vy = PLAYER.jumpSpeed;
      a.jumpBuffer = 0;
      a.coyote = 0;
      a.grounded = false;
      emit(a.index, 'jump');
    } else if (a.jumpBuffer > 0) {
      a.jumpBuffer--;
    }

    a.vy -= PLAYER.gravity * DT;
    if (a.vy < -26) a.vy = -26;
    moveY(a);

    const rate = (a.grounded ? PLAYER.accel : PLAYER.airAccel) * DT;
    if (dx === 0 && dz === 0) {
      const fr = (a.grounded ? PLAYER.groundFriction : PLAYER.airFriction) * DT;
      const sp = Math.sqrt(a.vx * a.vx + a.vz * a.vz);
      if (sp <= fr) {
        a.vx = 0;
        a.vz = 0;
      } else {
        const k = (sp - fr) / sp;
        a.vx *= k;
        a.vz *= k;
      }
    } else {
      const ddx = dx * PLAYER.maxSpeed - a.vx;
      const ddz = dz * PLAYER.maxSpeed - a.vz;
      const dd = Math.sqrt(ddx * ddx + ddz * ddz);
      if (dd <= rate) {
        a.vx = dx * PLAYER.maxSpeed;
        a.vz = dz * PLAYER.maxSpeed;
      } else {
        a.vx += (ddx / dd) * rate;
        a.vz += (ddz / dd) * rate;
      }
    }

    moveH(a, 0, a.vx * DT);
    moveH(a, 2, a.vz * DT);
    a.lastDx = a.x - startX;
    a.lastDz = a.z - startZ;

    const interactEdge = (bits & BIT.interact) !== 0 && (a.prevBits & BIT.interact) === 0;
    if (interactEdge) doInteract(a);

    if (a.carrying >= 0) {
      const c = crates[a.carrying];
      c.x = a.x;
      c.z = a.z;
      c.y = a.y + PLAYER.carryHeight;
      c.vx = 0;
      c.vy = 0;
      c.vz = 0;
      c.grounded = false;
      c.groundBody = -1;
      c.lastDx = 0;
      c.lastDz = 0;
    }

    if (a.teleCd > 0) a.teleCd--;
    else tryTeleport(a);

    updateButtonMask(a);

    if (a.y < SIM.killY) {
      a.fallen = true;
      if (a.carrying >= 0) {
        crates[a.carrying].carriedBy = -1;
        a.carrying = -1;
      }
      emit(a.index, 'fall');
    }

    a.prevBits = bits;
  }

  function doInteract(a) {
    if (a.carrying >= 0) {
      const c = crates[a.carrying];
      const oldX = c.x;
      const oldY = c.y;
      const oldZ = c.z;
      for (let k = 0; k < 2; k++) {
        c.x = k === 0 ? a.x + a.faceX * 0.82 : a.x;
        c.z = k === 0 ? a.z + a.faceZ * 0.82 : a.z;
        c.y = a.y + 0.02;
        c.carriedBy = -1;
        if (!blocked(c, a.index)) {
          a.carrying = -1;
          c.vy = 0;
          emit(a.index, 'drop:' + c.index);
          return;
        }
      }
      c.x = oldX;
      c.y = oldY;
      c.z = oldZ;
      c.carriedBy = a.index;
      emit(a.index, 'refuse');
      return;
    }
    let best = -1;
    let bestD = PLAYER.grabRange * PLAYER.grabRange;
    for (let i = 0; i < crates.length; i++) {
      const c = crates[i];
      if (!c.active || c.carriedBy >= 0) continue;
      if (Math.abs(c.y - a.y) > 1.15) continue;
      const ddx = c.x - a.x;
      const ddz = c.z - a.z;
      const d = ddx * ddx + ddz * ddz;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    if (best < 0) {
      emit(a.index, 'refuse');
      return;
    }
    const c = crates[best];
    c.carriedBy = a.index;
    a.carrying = best;
    emit(a.index, 'grab:' + c.index);
  }

  function tryTeleport(a) {
    if (level.teleports.length === 0) return;
    if (a.y > 0.6 || a.y < -0.4) return;
    const cx = Math.floor(a.x);
    const cz = Math.floor(a.z);
    for (let i = 0; i < level.teleports.length; i++) {
      const t = level.teleports[i];
      if (t.x !== cx || t.z !== cz) continue;
      a.x = t.tx + 0.5;
      a.z = t.tz + 0.5;
      a.y = 0.02;
      a.vx = 0;
      a.vz = 0;
      a.vy = 0;
      a.teleCd = WORLD.teleportCooldown;
      a.lastDx = 0;
      a.lastDz = 0;
      emit(a.index, 'tp:' + i);
      return;
    }
  }

  function updateButtonMask(a) {
    let mask = 0;
    if (!a.fallen && a.y > -0.4 && a.y < 0.5) {
      const cx = Math.floor(a.x);
      const cz = Math.floor(a.z);
      for (let i = 0; i < level.buttons.length; i++) {
        const b = level.buttons[i];
        if (b.x === cx && b.z === cz) mask |= 1 << i;
      }
    }
    if (mask !== a.buttonMask) {
      for (let i = 0; i < level.buttons.length; i++) {
        const bit = 1 << i;
        if (mask & bit) {
          if (!(a.buttonMask & bit)) emit(a.index, 'b+' + i);
        } else if (a.buttonMask & bit) {
          emit(a.index, 'b-' + i);
        }
      }
      a.buttonMask = mask;
    }
  }

  function stepCrate(c) {
    if (!c.active || c.carriedBy >= 0) return;
    if (c.groundBody >= 0) {
      const g = bodies[c.groundBody];
      c.x += g.lastDx;
      c.z += g.lastDz;
    }
    const startX = c.x;
    const startZ = c.z;
    c.vy -= CRATE.gravity * DT;
    if (c.vy < -26) c.vy = -26;
    moveY(c);
    c.lastDx = c.x - startX;
    c.lastDz = c.z - startZ;
    if (c.y < SIM.killY) c.active = false;
  }

  /** Once two actors have separated they stay solid to each other for good. */
  function updateSolidPairs() {
    for (let i = 0; i < sim.actorCount; i++) {
      const a = actors[i];
      if (!a.active) continue;
      for (let j = i + 1; j < sim.actorCount; j++) {
        const b = actors[j];
        if (!b.active) continue;
        if (a.solidMask & (1 << b.index)) continue;
        const sep =
          Math.abs(a.x - b.x) >= a.hw + b.hw - EPS ||
          Math.abs(a.z - b.z) >= a.hd + b.hd - EPS ||
          a.y >= b.y + b.hh - EPS ||
          b.y >= a.y + a.hh - EPS;
        if (sep) {
          a.solidMask |= 1 << b.index;
          b.solidMask |= 1 << a.index;
        }
      }
    }
  }

  // -------------------------------------------------------------------------
  // Triggers
  // -------------------------------------------------------------------------

  function updateTriggers() {
    groupCount.fill(0);
    for (let i = 0; i < level.buttons.length; i++) {
      const b = level.buttons[i];
      let on = 0;
      for (let k = 0; k < actors.length && !on; k++) {
        const a = actors[k];
        if (!a.active || a.fallen) continue;
        if (a.y > 0.5 || a.y < -0.4) continue;
        if (Math.floor(a.x) === b.x && Math.floor(a.z) === b.z) on = 1;
      }
      for (let k = 0; k < crates.length && !on; k++) {
        const c = crates[k];
        if (!c.active || c.carriedBy >= 0) continue;
        if (c.y > 0.5 || c.y < -0.4) continue;
        if (Math.floor(c.x) === b.x && Math.floor(c.z) === b.z) on = 1;
      }
      buttonOn[i] = on;
      if (on) groupCount[b.group]++;
    }
    for (let i = 0; i < level.plates.length; i++) {
      const p = level.plates[i];
      let on = 0;
      for (let k = 0; k < crates.length && !on; k++) {
        const c = crates[k];
        if (!c.active || c.carriedBy >= 0) continue;
        if (c.y > 0.4 || c.y < -0.4) continue;
        if (Math.floor(c.x) === p.x && Math.floor(c.z) === p.z) on = 1;
      }
      plateOn[i] = on;
      if (on) groupCount[p.group]++;
    }
    for (let g = 1; g < 8; g++) groupOn[g] = groupCount[g] >= level.require[g] ? 1 : 0;
    groupOn[0] = 0;
    for (let i = 0; i < level.doors.length; i++) doorOpen[i] = groupOn[level.doors[i].group];
  }

  function updateFragile() {
    for (let k = 0; k < fragileCells.length; k++) {
      const idx = fragileCells[k];
      if (heightNow[idx] < 0) continue;
      const cx = idx % w;
      const cz = (idx / w) | 0;
      if (fragileTimer[idx] === 0) {
        let touched = false;
        for (let i = 0; i < iterBodies.length && !touched; i++) {
          const b = iterBodies[i];
          if (!b.active || !b.grounded) continue;
          if (b.kind === 'crate' && b.carriedBy >= 0) continue;
          if (b.y > 0.3 || b.y < -0.3) continue;
          if (Math.floor(b.x) === cx && Math.floor(b.z) === cz) touched = true;
        }
        if (touched) {
          fragileTimer[idx] = WORLD.fragileTicks;
          emit(-1, 'crack');
        }
      } else if (fragileTimer[idx] > 1) {
        fragileTimer[idx]--;
      } else if (fragileTimer[idx] === 1) {
        fragileTimer[idx] = -1;
        heightNow[idx] = -1;
        emit(-1, 'collapse');
      }
    }
  }

  function checkExit() {
    const p = actors[0];
    if (!p.active || p.fallen || sim.status !== 'run') return;
    if (!p.grounded) return;
    if (Math.abs(p.y - exitTop) > 0.4) return;
    if (Math.floor(p.x) !== level.exit.x || Math.floor(p.z) !== level.exit.z) return;
    sim.status = 'win';
    emit(0, 'exit');
  }

  function writeTrace() {
    if (sim.tick >= sim.maxTicks) return;
    const base = sim.tick * traceStride;
    for (let i = 0; i < bodies.length; i++) {
      const b = bodies[i];
      const o = base + i * 3;
      trace[o] = b.x;
      trace[o + 1] = b.active ? b.y : NaN;
      trace[o + 2] = b.z;
    }
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /**
   * Rebuild the arena and place the player plus one clone per recording.
   * @param {Array} recordings clone recordings, oldest first
   */
  sim.reset = function reset(recordings) {
    sim.recordings = recordings;
    sim.tick = 0;
    sim.status = 'run';
    sim.reason = '';
    sim.frameEvents.length = 0;
    heightNow.set(level.height);
    fragileTimer.fill(0);
    doorOpen.fill(0);
    groupOn.fill(0);
    buttonOn.fill(0);
    plateOn.fill(0);

    sim.actorCount = Math.min(1 + recordings.length, SIM.maxActors);
    for (let i = 0; i < actors.length; i++) {
      const a = actors[i];
      a.active = i < sim.actorCount;
      a.isPlayer = i === 0;
      a.age = i === 0 ? -1 : i - 1;
      a.x = level.spawn.x + 0.5;
      a.z = level.spawn.z + 0.5;
      a.y = 0.02;
      a.vx = 0;
      a.vy = 0;
      a.vz = 0;
      a.grounded = false;
      a.groundBody = -1;
      a.lastDx = 0;
      a.lastDz = 0;
      a.faceX = 0;
      a.faceZ = -1;
      a.yawAngle = 0;
      a.coyote = 0;
      a.jumpBuffer = 0;
      a.prevBits = 0;
      a.bits = 0;
      a.teleCd = 0;
      a.carrying = -1;
      a.buttonMask = 0;
      a.solidMask = 0;
      a.fallen = false;
      a.frozen = false;
    }
    for (let i = 0; i < crates.length; i++) {
      const c = crates[i];
      const spec = level.crateSpawns[i];
      c.active = !!spec;
      c.x = spec ? spec.x + 0.5 : 0;
      c.z = spec ? spec.z + 0.5 : 0;
      c.y = spec ? 0.02 : 0;
      c.vx = 0;
      c.vy = 0;
      c.vz = 0;
      c.grounded = false;
      c.groundBody = -1;
      c.lastDx = 0;
      c.lastDz = 0;
      c.carriedBy = -1;
    }
    updateTriggers();
    writeTrace();
  };

  /**
   * Advance exactly one tick. `bits` / `yawByte` are the live player input;
   * clones read their own tape at the same tick index. Clones move first
   * (oldest to newest), the player last.
   */
  sim.step = function step(bits, yawByte) {
    sim.frameEvents.length = 0;
    if (sim.status !== 'run') return;
    sim.tick++;
    const t = sim.tick - 1;

    for (let i = 1; i < sim.actorCount; i++) {
      const rec = sim.recordings[i - 1];
      const a = actors[i];
      let cb = 0;
      let cy = 0;
      if (rec && t < rec.ticks) {
        cb = rec.bits[t];
        cy = rec.yaw[t];
      } else if (rec && rec.ticks > 0) {
        // Past the end of its tape a clone holds still, which turns an early
        // rewind into a deliberate "leave a statue right here" move.
        cy = rec.yaw[rec.ticks - 1];
      }
      a.frozen = !(rec && t < rec.ticks);
      stepActor(a, cb, cy);
    }
    stepActor(actors[0], bits, yawByte);

    for (let i = 0; i < crates.length; i++) stepCrate(crates[i]);

    updateSolidPairs();
    updateTriggers();
    updateFragile();
    checkExit();
    writeTrace();

    if (actors[0].fallen && sim.status === 'run') {
      sim.status = 'fell';
      sim.reason = 'Chute dans le vide';
    }
    if (sim.tick >= level.ticks && sim.status === 'run') sim.status = 'timeout';
  };

  /** Read a body position out of the trace (used by the rewind effect). */
  sim.traceAt = function traceAt(tick, bodyIndex, out) {
    const t = tick < 0 ? 0 : tick >= sim.maxTicks ? sim.maxTicks - 1 : tick;
    const o = t * traceStride + bodyIndex * 3;
    out.x = trace[o];
    out.y = trace[o + 1];
    out.z = trace[o + 2];
    return out;
  };

  sim.heightAt = heightAt;

  return sim;
}
