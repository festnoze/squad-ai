/**
 * PONTS DE FORTUNE - recording and replaying a collapse.
 *
 * The renderer never reads the solver directly: it reads a flat state buffer.
 * The live test fills that buffer from the solver, the replay fills it from a
 * ring of recorded frames. Same code path, so a slow motion collapse looks
 * exactly like the real thing, only slower.
 */

import { REPLAY } from './config.js';

/** Flat buffers the bridge view consumes. */
export function createState(plan) {
  const n = plan.sim.nodes.length;
  const l = plan.sim.links.length;
  return {
    pos: new Float32Array(n * 3),
    ratio: new Float32Array(l),
    sign: new Int8Array(l),
    broken: new Uint8Array(l),
  };
}

export function captureState(sim, state) {
  const nodes = sim.nodes;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    state.pos[i * 3] = n.x;
    state.pos[i * 3 + 1] = n.y;
    state.pos[i * 3 + 2] = n.z;
  }
  const links = sim.links;
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    state.ratio[i] = l.ratio;
    state.sign[i] = l.force >= 0 ? 1 : -1;
    state.broken[i] = l.broken ? 1 : 0;
  }
}

export function createRecorder(plan, vehicleCount) {
  const nodeCount = plan.sim.nodes.length;
  const linkCount = plan.sim.links.length;
  const perFrame = nodeCount * 3;
  // Keep the whole recording under roughly thirty megabytes. The links weigh as
  // much as the nodes here (six bytes each per frame), so a cable spammed
  // structure has to count in the budget too or the ring blows past its cap.
  const bytesPerFrame = perFrame * 4 + linkCount * 6 + Math.max(1, vehicleCount) * 24;
  const budget = Math.floor(30000000 / Math.max(1, bytesPerFrame));
  const max = Math.max(120, Math.min(REPLAY.maxFrames, budget));

  const pos = new Float32Array(max * perFrame);
  const ratio = new Float32Array(max * linkCount);
  const sign = new Int8Array(max * linkCount);
  const broken = new Uint8Array(max * linkCount);
  const veh = new Float32Array(max * vehicleCount * 6);

  let total = 0; // absolute number of frames pushed since reset
  const breakPoint = { x: 0, y: 0, z: 0, frame: -1, kind: '' };

  function reset() {
    total = 0;
    breakPoint.frame = -1;
  }

  function record(sim, vehicles) {
    const slot = total % max;
    const nodes = sim.nodes;
    const base = slot * perFrame;
    for (let i = 0; i < nodeCount; i++) {
      const n = nodes[i];
      pos[base + i * 3] = n.x;
      pos[base + i * 3 + 1] = n.y;
      pos[base + i * 3 + 2] = n.z;
    }
    const lbase = slot * linkCount;
    const links = sim.links;
    for (let i = 0; i < linkCount; i++) {
      const l = links[i];
      ratio[lbase + i] = l.ratio;
      sign[lbase + i] = l.force >= 0 ? 1 : -1;
      broken[lbase + i] = l.broken ? 1 : 0;
    }
    const vbase = slot * vehicleCount * 6;
    for (let i = 0; i < vehicleCount; i++) {
      const v = vehicles[i];
      veh[vbase + i * 6] = v.x;
      veh[vbase + i * 6 + 1] = v.y;
      veh[vbase + i * 6 + 2] = v.z;
      veh[vbase + i * 6 + 3] = v.pitch;
      veh[vbase + i * 6 + 4] = v.roll;
      veh[vbase + i * 6 + 5] = v.wheelSpin;
    }
    total += 1;
  }

  /** First rupture wins: that is where the replay camera looks. */
  function markBreak(x, y, z, kind) {
    if (breakPoint.frame >= 0) return;
    breakPoint.x = x;
    breakPoint.y = y;
    breakPoint.z = z;
    breakPoint.kind = kind;
    breakPoint.frame = total;
  }

  function firstFrame() {
    return Math.max(0, total - max);
  }

  function read(frame, state, vehicles) {
    const f = Math.max(firstFrame(), Math.min(total - 1, Math.round(frame)));
    if (f < 0) return;
    const slot = f % max;
    const base = slot * perFrame;
    state.pos.set(pos.subarray(base, base + perFrame));
    const lbase = slot * linkCount;
    state.ratio.set(ratio.subarray(lbase, lbase + linkCount));
    state.sign.set(sign.subarray(lbase, lbase + linkCount));
    state.broken.set(broken.subarray(lbase, lbase + linkCount));
    const vbase = slot * vehicleCount * 6;
    for (let i = 0; i < vehicleCount && i < vehicles.length; i++) {
      const v = vehicles[i];
      v.x = veh[vbase + i * 6];
      v.y = veh[vbase + i * 6 + 1];
      v.z = veh[vbase + i * 6 + 2];
      v.pitch = veh[vbase + i * 6 + 3];
      v.roll = veh[vbase + i * 6 + 4];
      v.wheelSpin = veh[vbase + i * 6 + 5];
    }
  }

  return {
    reset, record, markBreak, read, firstFrame, breakPoint,
    get total() { return total; },
    get capacity() { return max; },
  };
}
