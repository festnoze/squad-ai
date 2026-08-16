/**
 * PONTS DE FORTUNE - the convoy.
 *
 * Vehicles do not live in world X but in a continuous column coordinate `u`.
 * That matters: when the deck sags or stretches, world X stops being monotonic
 * and a vehicle driven in X can jump backwards or tunnel through a hole. In
 * column space the run is always well ordered, and the world position is simply
 * read back from the deformed roadway.
 *
 * Weight is applied as two axle loads, each split between the two trusses and
 * shared between the ends of the roadway cell it stands on. Loads are extra
 * kilograms on the nodes rather than forces: position based dynamics resolves
 * mass ratios far more gracefully than large impulses.
 */

import { GRID, DECK_Y, VEHICLES, CONVOY } from './config.js';
import { colToX } from './levels.js';

const STATE_WAIT = 'wait';
const STATE_RUN = 'run';
const STATE_FALL = 'fall';
const STATE_DONE = 'done';

export function createConvoy(level, plan, spec) {
  const cells = new Map();
  for (let i = 0; i < plan.deck.length; i++) cells.set(plan.deck[i].col, plan.deck[i]);

  const exitU = level.right + 5;
  const vehicles = [];
  for (let i = 0; i < spec.length; i++) {
    const def = VEHICLES[spec[i]] || VEHICLES.car;
    const halfCols = def.length * 0.5 / GRID;
    vehicles.push({
      def,
      key: def.key,
      mass: def.mass,
      halfCols,
      axle: halfCols * 0.62,
      u: level.left - 4 - i * (CONVOY.spacing / GRID) - halfCols,
      x: 0, y: DECK_Y, z: 0,
      pitch: 0, roll: 0,
      vy: 0, vx: 0,
      state: STATE_WAIT,
      onBridge: false,
      wheelSpin: 0,
    });
  }

  let timer = 0;
  let released = false;
  let maxLoad = 0;
  let failed = false;
  let failReason = '';

  /** Keeps a sample inside the span: the approaches are solid rock anyway. */
  function clampU(u) {
    if (u < level.left) return level.left;
    if (u > level.right - 1e-4) return level.right - 1e-4;
    return u;
  }

  /** Deck point under a column coordinate, or null over a hole. */
  function sample(u, out) {
    const col = Math.floor(clampU(u));
    const cell = cells.get(col);
    if (!cell) return null;
    // A cell whose two roadway members are both gone is a hole, not a road.
    const links = plan.sim.links;
    if (links[cell.links[0]].broken && links[cell.links[1]].broken) return null;
    const nodes = plan.sim.nodes;
    const a0 = nodes[cell.n0[0]];
    const a1 = nodes[cell.n0[1]];
    const b0 = nodes[cell.n1[0]];
    const b1 = nodes[cell.n1[1]];
    const t = clampU(u) - col;
    out.x = (a0.x + a1.x) * 0.5 * (1 - t) + (b0.x + b1.x) * 0.5 * t;
    out.y = (a0.y + a1.y) * 0.5 * (1 - t) + (b0.y + b1.y) * 0.5 * t;
    out.z = (a0.z + a1.z) * 0.5 * (1 - t) + (b0.z + b1.z) * 0.5 * t;
    out.tilt = ((a1.y - a0.y) * (1 - t) + (b1.y - b0.y) * t) / (2 * Math.abs(a1.z - a0.z) + 1e-6);
    out.cell = cell;
    out.t = t;
    return out;
  }

  const probe = { x: 0, y: 0, z: 0, tilt: 0, cell: null, t: 0 };
  const probeB = { x: 0, y: 0, z: 0, tilt: 0, cell: null, t: 0 };

  /** Called before every solver substep: puts the axle weights on the nodes. */
  function applyLoads() {
    let onBridge = 0;
    for (let i = 0; i < vehicles.length; i++) {
      const v = vehicles[i];
      if (v.state !== STATE_RUN) continue;
      if (v.u <= level.left || v.u >= level.right) continue;
      let carried = 0;
      for (let s = -1; s <= 1; s += 2) {
        const ua = clampU(v.u + s * v.axle);
        const col = Math.floor(ua);
        const cell = cells.get(col);
        if (!cell) continue;
        const t = ua - col;
        const quarter = v.mass * 0.25; // half the vehicle, halved again per truss
        plan.sim.addLoad(cell.n0[0], quarter * (1 - t));
        plan.sim.addLoad(cell.n0[1], quarter * (1 - t));
        plan.sim.addLoad(cell.n1[0], quarter * t);
        plan.sim.addLoad(cell.n1[1], quarter * t);
        carried += v.mass * 0.5;
      }
      onBridge += carried;
    }
    if (onBridge > maxLoad) maxLoad = onBridge;
  }

  /** Called after every solver substep: moves the vehicles and reads the deck. */
  function advance(dt) {
    timer += dt;
    if (!released && timer >= CONVOY.settleTime) released = true;

    for (let i = 0; i < vehicles.length; i++) {
      const v = vehicles[i];

      if (v.state === STATE_FALL) {
        v.vy -= 9.81 * dt;
        v.y += v.vy * dt;
        v.x += v.vx * dt;
        v.pitch += dt * 1.6;
        v.roll += dt * 0.9;
        if (v.y < DECK_Y - CONVOY.fallDepth && !failed) {
          failed = true;
          failReason = v.def.name + ' EST TOMBE DANS LE RAVIN';
        }
        continue;
      }
      if (v.state === STATE_DONE) continue;

      if (released) {
        v.state = STATE_RUN;
        v.u += (v.def.speed / GRID) * dt;
        v.wheelSpin += v.def.speed * dt;
      } else {
        v.state = STATE_WAIT;
      }

      if (v.u >= exitU) { v.state = STATE_DONE; }

      const overGap = v.u > level.left && v.u < level.right;
      v.onBridge = overGap;

      if (!overGap) {
        // Solid ground on either approach.
        v.x = colToX(level, v.u);
        v.y = DECK_Y;
        v.z = 0;
        v.pitch = 0;
        v.roll = 0;
        continue;
      }

      const a = sample(v.u - v.axle, probe);
      const b = sample(v.u + v.axle, probeB);
      if (!a && !b) {
        // Nothing under either axle: the roadway is gone here.
        v.state = STATE_FALL;
        v.vx = v.def.speed;
        v.vy = -1;
        continue;
      }
      const pa = a || b;
      const pb = b || a;
      v.x = (pa.x + pb.x) * 0.5;
      v.y = (pa.y + pb.y) * 0.5;
      v.z = (pa.z + pb.z) * 0.5;
      const dx = pb.x - pa.x;
      const dy = pb.y - pa.y;
      v.pitch = Math.atan2(dy, Math.abs(dx) + 1e-4);
      v.roll = Math.atan(((pa.tilt + pb.tilt) * 0.5));
      if (v.y < DECK_Y - CONVOY.fallDepth * 0.55) {
        v.state = STATE_FALL;
        v.vx = v.def.speed * 0.4;
        v.vy = -2;
      }
    }

    if (!failed && timer > CONVOY.timeout) {
      failed = true;
      failReason = 'LE CONVOI N A PAS TRAVERSE A TEMPS';
    }
  }

  function allDone() {
    for (let i = 0; i < vehicles.length; i++) if (vehicles[i].state !== STATE_DONE) return false;
    return true;
  }

  function leader() {
    let best = vehicles[0];
    for (let i = 1; i < vehicles.length; i++) if (vehicles[i].u > best.u) best = vehicles[i];
    return best;
  }

  return {
    vehicles,
    applyLoads,
    advance,
    allDone,
    leader,
    get time() { return timer; },
    get started() { return released; },
    get maxLoad() { return maxLoad; },
    get failed() { return failed; },
    get failReason() { return failReason; },
  };
}
