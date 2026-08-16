/**
 * Street furniture: lamp posts, traffic lights, hydrants, benches, bins, bus shelters.
 *
 * All of it is merged into a handful of meshes keyed by material, so the entire city's
 * furniture costs about five draw calls. Lamp heads and traffic-light lenses go into a
 * separate *unlit* mesh whose brightness is driven by time of day - that one mesh is what
 * makes the city read as lit at night, without needing hundreds of real lights.
 *
 * Lamp positions are also exported so `NightLights` can attach a small pool of real
 * point lights to whichever posts are nearest the camera.
 */

import {
  Mesh, Vector3, MeshBasicMaterial, Color, SRGBColorSpace, DynamicDrawUsage,
} from 'three/webgpu';
import { GeometryBuilder, colliderYaw } from './GeometryBuilder.js';
import { ROAD } from './RoadNetwork.js';
import { getMaterial, getFlat } from '../render/Materials.js';
import { GROUP } from '../physics/Physics.js';
import { makeRng } from '../core/Noise.js';

const LAMP_SPACING = 30;
const LAMP_HEIGHT = 7.4;
const SIDEWALK_HEIGHT = 0.17;

/**
 * Emissive brightness authored above 1.0 so the bloom threshold catches lamp heads at
 * night. `GeometryBuilder.setColor`'s scale multiplies after the sRGB decode, so values
 * greater than one are legal and land in HDR range.
 */
const GLOW_LAMP = 2.6;
const GLOW_LENS = 3.2;
const GLOW_LENS_DARK = 0.04;

/*
 * Signal timing, in *simulation* seconds. One clock for the whole city: every junction
 * changes together. That is a real pattern (a synchronised grid) and it costs one modulo
 * per query instead of a per-junction phase table.
 *
 * The durations are constrained from below by the traffic AI, not by taste.
 * `VehicleManager` treats twelve seconds below walking pace as a dead queue and teleports
 * the car forward. A driver arriving one tick after its light drops waits
 * GREEN + AMBER + CLEAR = 8 s, which leaves margin before that recovery path would haul a
 * legitimately queued car through a red. The AI freezes its dead-queue timer while it is
 * held at a signal as well, but the two guards are deliberately independent - relying on
 * the freeze alone would mean a car genuinely wedged at a stop line never got recovered.
 */
const SIGNAL_GREEN = 6;
const SIGNAL_AMBER = 1;
const SIGNAL_CLEAR = 1;    // all-red, so anything that entered on amber is out of the box
const SIGNAL_HALF = SIGNAL_GREEN + SIGNAL_AMBER + SIGNAL_CLEAR;
export const SIGNAL_PERIOD = SIGNAL_HALF * 2;

/**
 * Lens colours, red-amber-green from the top. The index of a lens is also its phase
 * number, which is what lets `signalPhase` return a value the painter can use directly.
 */
const LENS_COLOURS = [0xff2a20, 0xffb020, 0x30d060];
const _lensColor = new Color();
const lensRGB = (hex, scale) => {
  _lensColor.setHex(hex, SRGBColorSpace);
  return [_lensColor.r * scale, _lensColor.g * scale, _lensColor.b * scale];
};
const LENS_LIT = LENS_COLOURS.map((c) => lensRGB(c, GLOW_LENS));
const LENS_DIM = LENS_COLOURS.map((c) => lensRGB(c, GLOW_LENS_DARK));

export class StreetProps {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {import('./City.js').City} city
   */
  constructor(physics, city, { seed = 5150 } = {}) {
    this.physics = physics;
    this.city = city;
    this.rng = makeRng(seed);

    /** @type {Array<{x:number,y:number,z:number}>} lamp head positions for real lights */
    this.lamps = [];
    /** @type {Array<object>} traffic light groups, for signal cycling */
    this.signals = [];
    /** @type {Set<number>} road-graph node ids that carry signal heads */
    this.signalNodes = new Set();
    /** Simulation seconds since the cycle started. Advanced from the fixed step. */
    this.signalTime = 0;
    this._paintedPhase = -1;
    /** @type {import('three/webgpu').BufferAttribute|null} glow mesh vertex colours */
    this.lensColours = null;

    this.builders = {
      metal: new GeometryBuilder(),
      concrete: new GeometryBuilder(),
      wood: new GeometryBuilder(),
      glow: new GeometryBuilder(),
    };

    this._lampPosts();
    this._trafficLights();
    this._streetFurniture();

    this.meshes = [];
    this.glowMaterial = new MeshBasicMaterial({ vertexColors: true, toneMapped: true });
    for (const [key, b] of Object.entries(this.builders)) {
      if (b.isEmpty) continue;
      const material = key === 'glow' ? this.glowMaterial : getMaterial(key);
      const mesh = new Mesh(b.build(), material);
      if (key === 'glow') {
        // Signal lenses are repainted in place when the phase changes. They are the only
        // part of this buffer that ever moves, and they are contiguous - `_lampPosts` runs
        // to completion before `_trafficLights` starts - so the upload stays one range.
        this.lensColours = mesh.geometry.getAttribute('color');
        this.lensColours.setUsage(DynamicDrawUsage);
      }
      mesh.name = `props_${key}`;
      mesh.castShadow = key !== 'glow';
      mesh.receiveShadow = key !== 'glow';
      this.meshes.push(mesh);
    }
    this.builders = null;
  }

  /* ----------------------------------------------------------------- lamp posts */

  _lampPosts() {
    const net = this.city.network;
    const m = this.builders.metal;
    const glow = this.builders.glow;

    for (const e of net.edges) {
      const a = net.nodes[e.a];
      const count = Math.floor(e.length / LAMP_SPACING);
      if (count < 1) continue;
      const ux = e.dirX, uz = e.dirZ;
      const rx = -uz, rz = ux;
      /*
       * Blocks start exactly at the kerb line (RoadNetwork insets them by the road's
       * half-width), and the pavement slab runs *inward* from there towards the
       * carriageway. So the pavement occupies [halfWidth - 3.2, halfWidth] measured from
       * the road centreline - anything beyond halfWidth is inside a building, which is
       * why an outward offset had most lamp posts rejected as blocked.
       */
      const offset = e.type.width / 2 - 1.3;
      const yaw = Math.atan2(ux, uz);

      for (let i = 0; i < count; i++) {
        // Alternate sides so the street is lit evenly from both kerbs.
        const side = i % 2 === 0 ? 1 : -1;
        const t = (i + 0.5) / count;
        const along = t * e.length;
        const x = a.x + ux * along + rx * offset * side;
        const z = a.z + uz * along + rz * offset * side;
        if (this.city.island && !this.city.island.isLand(x, z)) continue;
        if (!this.city.isSpawnClear(x, z, 0.6)) continue;

        const y = SIDEWALK_HEIGHT;
        m.setColor(0x4a5058, 1.0);
        m.cylinder(x, y, z, 0.11, LAMP_HEIGHT, 7, 2, false, 0.08);
        // Arm reaching out over the carriageway.
        const armLen = 1.7;
        m.rotatedBox(
          x - rx * armLen * 0.5 * side, y + LAMP_HEIGHT - 0.15, z - rz * armLen * 0.5 * side,
          armLen * 0.5, 0.07, 0.07, -yaw + Math.PI / 2, 1,
        );
        m.resetColor();

        const hx = x - rx * armLen * side;
        const hz = z - rz * armLen * side;
        // Lamp head: a shallow box, glowing side down.
        glow.setColor(0xffe4b0, GLOW_LAMP);
        glow.box(
          new Vector3(hx - 0.24, y + LAMP_HEIGHT - 0.34, hz - 0.42),
          new Vector3(hx + 0.24, y + LAMP_HEIGHT - 0.22, hz + 0.42),
          1,
        );
        glow.resetColor();

        this.lamps.push({ x: hx, y: y + LAMP_HEIGHT - 0.3, z: hz });
        this.physics.addStaticBox(
          new Vector3(x, y + LAMP_HEIGHT / 2, z),
          new Vector3(0.14, LAMP_HEIGHT / 2, 0.14), 0, GROUP.PROP,
        );
        this.city.props.push({ x, z, radius: 0.3 });
      }
    }
  }

  /* ------------------------------------------------------------- traffic lights */

  /**
   * True where an avenue crosses an avenue - the arterial crossroads, and the only
   * junctions that get signals.
   *
   * This is a traffic decision as much as a dressing one. Signals on all 534 junctions of
   * the grid were built and measured: AI obedience was textbook (64% of red-approach
   * samples at a standstill, zero cars crossing a red at speed) but city flow collapsed
   * from 25.7 of 28 cars moving to 19.2, junction throughput halved, and stuck-recovery
   * teleports went from 22 to 58 over the same 120 s. Two axes sharing a junction means
   * each one is stopped for most of the cycle, and a grid where every corner does that is
   * a grid that spends its time waiting. Restricting signals to the 36 avenue crossings
   * (of 534) puts them where an arterial actually needs priority, roughly every 300 m
   * downtown, and leaves the minor corners as they were.
   *
   * Read off the edge types rather than recomputed from the grid line indices, which is
   * where the road types are decided - deriving the same fact twice by two routes is how
   * the heads would end up somewhere the cars do not expect them.
   */
  _isArterialCrossing(net, node) {
    let avenueX = false, avenueZ = false;
    for (const eid of node.edges) {
      const e = net.edges[eid];
      if (e.type !== ROAD.AVENUE) continue;
      if (e.axis === 'x') avenueX = true; else avenueZ = true;
    }
    return avenueX && avenueZ;
  }

  _trafficLights() {
    const net = this.city.network;
    const m = this.builders.metal;
    const glow = this.builders.glow;

    for (const node of net.nodes) {
      if (node.edges.length < 3) continue;
      if (!this._isArterialCrossing(net, node)) continue;
      // One signal head per approach, set back from the junction on the near-side kerb.
      for (const eid of node.edges) {
        const e = net.edges[eid];
        const other = net.nodes[net.otherEnd(e, node.id)];
        const dx = other.x - node.x, dz = other.z - node.z;
        const len = Math.hypot(dx, dz) || 1;
        const ux = dx / len, uz = dz / len;
        const rx = -uz, rz = ux;
        const back = e.type.width / 2 + 2.2;
        // Same pavement geometry as the lamp posts: inset from the kerb, not beyond it.
        const lateral = e.type.width / 2 - 1.4;
        const x = node.x + ux * back + rx * lateral;
        const z = node.z + uz * back + rz * lateral;
        if (this.city.island && !this.city.island.isLand(x, z)) continue;

        const y = SIDEWALK_HEIGHT;
        const poleH = 4.2;
        m.setColor(0x3a4046, 1.0);
        m.cylinder(x, y, z, 0.09, poleH, 6, 2, false);
        m.resetColor();

        // Signal box facing back down the approach.
        const bx = x, bz = z;
        const headY = y + poleH - 0.1;
        this.builders.metal.setColor(0x24282e, 1.0);
        this.builders.metal.box(
          new Vector3(bx - 0.18, headY - 0.75, bz - 0.18),
          new Vector3(bx + 0.18, headY, bz + 0.18), 1,
        );
        this.builders.metal.resetColor();

        /*
         * Three lenses, one lit. Which one is lit comes from the approach axis and the
         * shared cycle clock, so crossing streets always show red against green. The
         * geometry is baked at t=0 (axis 0 green) and only repainted when the phase
         * actually changes - four writes per sixteen seconds, not one per frame. Unlit
         * lenses keep a trace of colour so the head does not read as a black box.
         *
         * The axis is read off the edge rather than recomputed from the direction vector:
         * `VehicleManager` asks for a phase using the same field, and deriving it twice by
         * two different routes is how the lights and the cars would eventually disagree.
         */
        const axis = e.axis === 'x' ? 0 : 1;
        const litIndex = axis === 0 ? 2 : 0;
        const lensStart = glow._v;
        for (let i = 0; i < 3; i++) {
          glow.setColor(LENS_COLOURS[i], i === litIndex ? GLOW_LENS : GLOW_LENS_DARK);
          const cy = headY - 0.16 - i * 0.24;
          glow.box(
            new Vector3(bx - 0.11, cy - 0.09, bz - 0.2),
            new Vector3(bx + 0.11, cy + 0.09, bz - 0.16), 1,
          );
        }
        glow.resetColor();
        this.signals.push({
          x, z, node: node.id, vertexStart: lensStart, vertexEnd: glow._v, axis, litIndex,
        });
        this.signalNodes.add(node.id);
      }
    }
  }

  /* ------------------------------------------------------------------ furniture */

  _streetFurniture() {
    const c = this.builders.concrete;
    const m = this.builders.metal;
    const w = this.builders.wood;
    const blocks = this.city.network.blocks;

    for (const block of blocks) {
      const perimeter = 2 * ((block.x1 - block.x0) + (block.z1 - block.z0));
      const items = Math.floor(perimeter / 60);
      for (let i = 0; i < items; i++) {
        const side = Math.floor(this.rng() * 4);
        const t = 0.15 + this.rng() * 0.7;
        const inset = 2.1;
        let x, z, yaw;
        if (side === 0) { x = block.x0 + (block.x1 - block.x0) * t; z = block.z0 - inset; yaw = 0; }
        else if (side === 1) { x = block.x0 + (block.x1 - block.x0) * t; z = block.z1 + inset; yaw = Math.PI; }
        else if (side === 2) { x = block.x0 - inset; z = block.z0 + (block.z1 - block.z0) * t; yaw = Math.PI / 2; }
        else { x = block.x1 + inset; z = block.z0 + (block.z1 - block.z0) * t; yaw = -Math.PI / 2; }
        if (!this.city.isSpawnClear(x, z, 0.9)) continue;

        const roll = this.rng();
        const y = SIDEWALK_HEIGHT;
        if (roll < 0.3) {
          // Hydrant.
          m.setColor(0xc0392b, 1.0);
          m.cylinder(x, y, z, 0.13, 0.62, 8, 1, true);
          m.box(new Vector3(x - 0.22, y + 0.3, z - 0.07), new Vector3(x + 0.22, y + 0.42, z + 0.07), 1);
          m.resetColor();
          this.city.props.push({ x, z, radius: 0.35 });
        } else if (roll < 0.55) {
          // Bench: timber slats on concrete legs.
          w.setColor(0x8a6a44, 0.9 + this.rng() * 0.2);
          w.rotatedBox(x, y + 0.44, z, 0.9, 0.05, 0.28, yaw, 1);
          w.rotatedBox(x, y + 0.66, z - 0.22, 0.9, 0.22, 0.05, yaw, 1);
          w.resetColor();
          c.setColor(0xffffff, 0.7);
          c.rotatedBox(x - 0.75, y + 0.22, z, 0.08, 0.22, 0.26, yaw, 1);
          c.rotatedBox(x + 0.75, y + 0.22, z, 0.08, 0.22, 0.26, yaw, 1);
          c.resetColor();
          this.city.props.push({ x, z, radius: 1.0 });
        } else if (roll < 0.78) {
          // Litter bin.
          m.setColor(0x3f4a44, 1.0);
          m.cylinder(x, y, z, 0.28, 0.85, 9, 1.2, true, 0.3);
          m.resetColor();
          this.city.props.push({ x, z, radius: 0.4 });
        } else {
          // Bus shelter: posts, roof, glass-free for cheapness.
          m.setColor(0x51585f, 1.0);
          for (const s of [-1, 1]) {
            m.cylinder(x + Math.cos(yaw) * 1.5 * s, y, z + Math.sin(yaw) * 1.5 * s, 0.07, 2.5, 6, 1, false);
          }
          m.rotatedBox(x, y + 2.55, z, 1.7, 0.06, 0.7, yaw, 1.5);
          m.resetColor();
          this.physics.addStaticBox(
            new Vector3(x, y + 1.2, z), new Vector3(1.7, 1.2, 0.12), colliderYaw(yaw), GROUP.PROP,
          );
          this.city.props.push({ x, z, radius: 1.8 });
        }
      }
    }
  }

  /* --------------------------------------------------------------- signal cycle */

  /**
   * Signal state for one approach axis, right now.
   *
   * The returned number is also the index of the lit lens (0 red, 1 amber, 2 green),
   * which is the whole reason the lenses are authored red-amber-green top to bottom.
   *
   * @param {0|1} axis 0 for a road running along x, 1 for one running along z
   * @returns {0|1|2}
   */
  signalPhase(axis) {
    // Axis 1 is offset by half a period, so it is red for exactly as long as axis 0 is
    // not, with the amber and all-red intervals falling inside the other axis's red.
    const local = (this.signalTime + (axis ? SIGNAL_HALF : 0)) % SIGNAL_PERIOD;
    if (local < SIGNAL_GREEN) return 2;
    if (local < SIGNAL_GREEN + SIGNAL_AMBER) return 1;
    return 0;
  }

  /** True when this road-graph node carries signal heads. */
  isSignalled(nodeId) { return this.signalNodes.has(nodeId); }

  /**
   * Advance the cycle. Driven from the fixed step, not from `update`, because the two
   * clocks genuinely differ: the fixed loop caps at five steps a frame and discards the
   * remainder, so under load (or in the headless harness) wall time runs several times
   * faster than simulation time. Traffic decides whether to stop from simulation time, so
   * the lenses have to be painted from the same clock or the picture contradicts the cars.
   */
  advanceSignals(dt) {
    this.signalTime = (this.signalTime + dt) % SIGNAL_PERIOD;
    const phase = this.signalPhase(0) * 3 + this.signalPhase(1);
    if (phase !== this._paintedPhase) {
      this._paintedPhase = phase;
      this._paintLenses();
    }
  }

  /** Rewrite the lens vertex colours for the current phase. */
  _paintLenses() {
    const attr = this.lensColours;
    if (!attr) return;
    const arr = attr.array;
    const lit = [this.signalPhase(0), this.signalPhase(1)];
    for (const s of this.signals) {
      const on = lit[s.axis];
      if (s.litIndex === on) continue;
      s.litIndex = on;
      // Three lenses share the range evenly; derived rather than hardcoded so a change to
      // the lens primitive cannot silently paint the wrong vertices.
      const per = (s.vertexEnd - s.vertexStart) / 3;
      for (let i = 0; i < 3; i++) {
        const c = i === on ? LENS_LIT[i] : LENS_DIM[i];
        const end = s.vertexStart + (i + 1) * per;
        for (let v = s.vertexStart + i * per; v < end; v++) {
          arr[v * 3] = c[0]; arr[v * 3 + 1] = c[1]; arr[v * 3 + 2] = c[2];
        }
      }
    }
    attr.needsUpdate = true;
  }

  /**
   * Drive the glow mesh brightness. The signal cycle is deliberately not here: it runs off
   * the fixed step in `advanceSignals`, because traffic decides whether to stop from
   * simulation time and the two clocks diverge whenever the fixed loop drops steps.
   * @param {number} nightFactor 0 = full day, 1 = night
   */
  update(nightFactor, time) {
    // Lamp heads and lenses are unlit geometry; scaling the material colour is what turns
    // the street lighting on and off across the whole city in one uniform write.
    this.glowMaterial.color.setScalar(0.06 + nightFactor * 0.94);
    void time;
  }
}

export { getFlat };
