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

import { Mesh, Vector3, MeshBasicMaterial } from 'three/webgpu';
import { GeometryBuilder, colliderYaw } from './GeometryBuilder.js';
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

  _trafficLights() {
    const net = this.city.network;
    const m = this.builders.metal;
    const glow = this.builders.glow;

    for (const node of net.nodes) {
      if (node.edges.length < 3) continue;
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
         * Three lenses, one lit. Which one is baked in per approach axis rather than
         * cycled at runtime: crossing streets then show red against green, which is what
         * makes a junction read correctly, and it costs nothing per frame. Unlit lenses
         * keep a trace of colour so the head does not read as a black box.
         */
        const axis = Math.abs(ux) > Math.abs(uz) ? 0 : 1;
        const litIndex = axis === 0 ? 2 : 0;
        const lensStart = glow._v;
        const colours = [0xff2a20, 0xffb020, 0x30d060];
        for (let i = 0; i < 3; i++) {
          glow.setColor(colours[i], i === litIndex ? GLOW_LENS : 0.04);
          const cy = headY - 0.16 - i * 0.24;
          glow.box(
            new Vector3(bx - 0.11, cy - 0.09, bz - 0.2),
            new Vector3(bx + 0.11, cy + 0.09, bz - 0.16), 1,
          );
        }
        glow.resetColor();
        this.signals.push({ x, z, vertexStart: lensStart, vertexEnd: glow._v, axis, litIndex });
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

  /**
   * Drive the glow mesh brightness and cycle the traffic signals.
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
