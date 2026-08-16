/**
 * Island shape and coastline geometry.
 *
 * The map is an island so the world has a real edge: the city grid stops at the shore
 * instead of fading into an infinite grey plane. The shape is one analytic function -
 * `isLand(x, z)` - which the road network, the terrain mesh, the beach ring and the
 * spawn logic all consult, so the coastline is consistent everywhere by construction.
 *
 * A bay is subtracted from the south-east so boats have somewhere to launch from that is
 * within reach of downtown, and so the docks district has a waterfront.
 */

import { Mesh, Vector3 } from 'three/webgpu';
import { GeometryBuilder, colliderYaw } from './GeometryBuilder.js';
import { getMaterial, getFlat } from '../render/Materials.js';
import { fbm2, smoothstep } from '../core/Noise.js';

export const SEA_LEVEL = -2.4;
/**
 * The visual terrain is drawn a few centimetres below its collision height. The city's
 * road surface also sits at y=0, and two coplanar meshes z-fight - which shows up as
 * grass bleeding through the carriageway. The offset is far too small to feel underfoot,
 * and physics still uses the true height.
 */
const VISUAL_DROP = 0.06;
/** Land sits at y=0; the beach ramps from SEA_LEVEL up to 0 across this width. */
export const BEACH_WIDTH = 46;

export class Island {
  /**
   * @param {object} opts
   * @param {number} opts.radius mean coastline radius
   * @param {number} opts.seed
   */
  constructor({ radius = 1320, seed = 20260814 } = {}) {
    this.radius = radius;
    this.seed = seed;

    /** Bay carved out of the coast, giving the docks a sheltered harbour. */
    this.bay = { x: 980, z: -900, radius: 430 };
    /** A second, smaller inlet on the north-west shore - the marina. */
    this.marina = { x: -1010, z: 760, radius: 250 };
  }

  /**
   * Signed distance-ish field: positive inland, negative at sea. Zero is the shoreline.
   * Everything else in the game derives from this.
   */
  landField(x, z) {
    const r = Math.hypot(x, z) || 1e-6;
    const angle = Math.atan2(z, x);
    // Wobble the coastline with low-frequency noise sampled around the compass, so the
    // island is not a circle. Sampling on a circle keeps it seamless at +/-pi.
    const nx = Math.cos(angle) * 2.2, nz = Math.sin(angle) * 2.2;
    const wobble = fbm2(nx + 8, nz + 8, { octaves: 4, period: 6, seed: this.seed & 0xffff });
    const coast = this.radius * (0.9 + wobble * 0.24);
    let field = coast - r;

    // Subtract the harbour and marina inlets.
    for (const inlet of [this.bay, this.marina]) {
      const d = Math.hypot(x - inlet.x, z - inlet.z);
      const cut = inlet.radius - d;
      if (cut > 0) field = Math.min(field, -cut * 0.9);
    }
    return field;
  }

  isLand(x, z) { return this.landField(x, z) > 0; }

  /** True where the ground should be sand rather than city surface. */
  isBeach(x, z) {
    const f = this.landField(x, z);
    return f > 0 && f < BEACH_WIDTH;
  }

  /**
   * Terrain height. Land is flat at 0 except for the beach, which ramps down to the
   * sea floor so the shoreline is walkable rather than a cliff.
   */
  heightAt(x, z) {
    const f = this.landField(x, z);
    if (f >= BEACH_WIDTH) return 0;
    if (f <= -BEACH_WIDTH) return SEA_LEVEL - 3;
    // Smooth S-curve from sea floor up to land level across the beach band.
    const t = smoothstep(-BEACH_WIDTH, BEACH_WIDTH, f);
    return (SEA_LEVEL - 3) + t * (0 - (SEA_LEVEL - 3));
  }

  /**
   * Build the land + beach mesh. Cells are emitted only where they are at least partly
   * land, so the mesh has a real coastline silhouette rather than a square edge.
   *
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {number} cell grid resolution in metres
   */
  buildTerrain(physics, { cell = 24, extent = 1700 } = {}) {
    const land = new GeometryBuilder();
    const beach = new GeometryBuilder();
    const meshes = [];

    const n = Math.ceil((extent * 2) / cell);
    const h = (x, z) => this.heightAt(x, z) - VISUAL_DROP;

    for (let j = 0; j < n; j++) {
      for (let i = 0; i < n; i++) {
        const x0 = -extent + i * cell, x1 = x0 + cell;
        const z0 = -extent + j * cell, z1 = z0 + cell;
        // Skip cells that are entirely below the beach band - the ocean covers them.
        const corners = [
          this.landField(x0, z0), this.landField(x1, z0),
          this.landField(x0, z1), this.landField(x1, z1),
        ];
        if (Math.max(...corners) < -BEACH_WIDTH) continue;

        const minField = Math.min(...corners);
        const b = minField < BEACH_WIDTH ? beach : land;
        // No per-cell tint here: vertex colours are constant across a cell, so any
        // variation shows up as visible flat-shaded blocks on open ground. The texture
        // already carries the large-scale variation.

        const A = new Vector3(x0, h(x0, z0), z0);
        const B = new Vector3(x0, h(x0, z1), z1);
        const C = new Vector3(x1, h(x1, z1), z1);
        const D = new Vector3(x1, h(x1, z0), z0);
        const tile = 8;
        const uv = (p) => [p.x / tile, p.z / tile];
        // Split the quad so the two triangles follow the slope rather than warping.
        b.tri(A, B, C, uv(A), uv(B), uv(C));
        b.tri(A, C, D, uv(A), uv(C), uv(D));
      }
    }

    if (!land.isEmpty) {
      const m = new Mesh(land.build(), getMaterial('grass'));
      m.name = 'islandLand';
      m.receiveShadow = true;
      meshes.push(m);
    }
    if (!beach.isEmpty) {
      const m = new Mesh(beach.build(), getMaterial('sand'));
      m.name = 'islandBeach';
      m.receiveShadow = true;
      meshes.push(m);
    }

    /*
     * Collision is a heightfield sampled from the same `heightAt` the visual mesh uses,
     * so the ground follows the beach down to the sea floor. A flat plane would extend
     * under the ocean and boats would rest on it instead of floating.
     */
    physics.addHeightfieldFromFunction(
      (x, z) => this.heightAt(x, z),
      Math.round((extent * 2) / cell) + 1,
      extent * 2,
    );

    return meshes;
  }

  /**
   * Sea wall along the developed waterfront, so cars stop at the quayside instead of
   * driving into the harbour.
   */
  buildSeaWall(physics, network) {
    const b = new GeometryBuilder();
    const placed = [];
    // Walk the coast at a fixed angular step and drop a wall segment wherever the
    // shoreline is close to a road.
    const steps = 460;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * Math.PI * 2;
      // March outward to find the shoreline along this bearing.
      let r = this.radius * 0.5;
      let found = -1;
      for (let k = 0; k < 260; k++) {
        const x = Math.cos(angle) * r, z = Math.sin(angle) * r;
        if (!this.isLand(x, z)) { found = r; break; }
        r += 8;
      }
      if (found < 0) continue;
      const wallR = found - 3;
      const x = Math.cos(angle) * wallR, z = Math.sin(angle) * wallR;
      const near = network.nearestOnRoad(x, z);
      if (!near || near.distance > 60) continue;

      const yaw = angle + Math.PI / 2;
      b.setColor(0xffffff, 0.8);
      b.rotatedBox(x, 0.55, z, 5.0, 0.55, 0.6, yaw, 3);
      b.resetColor();
      placed.push({ x, z, yaw });
    }
    if (b.isEmpty) return null;
    const mesh = new Mesh(b.build(), getMaterial('concrete'));
    mesh.name = 'seaWall';
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    for (const p of placed) {
      physics.addStaticBox(new Vector3(p.x, 0.55, p.z), new Vector3(5.0, 0.55, 0.6), colliderYaw(p.yaw));
    }
    return mesh;
  }

  /**
   * Timber jetties in the harbour and marina - somewhere to moor the boats and to walk
   * out over the water.
   * @returns {{mesh: Mesh, moorings: Array<{x:number,z:number,heading:number}>}}
   */
  buildDocks(physics) {
    const b = new GeometryBuilder();
    const moorings = [];
    const deckY = 0.9;

    for (const inlet of [this.bay, this.marina]) {
      // Find a shoreline point on the inlet facing the open water, and run piers out.
      const toCentre = Math.atan2(-inlet.z, -inlet.x);
      const pierCount = 3;
      for (let p = 0; p < pierCount; p++) {
        const spread = (p - (pierCount - 1) / 2) * 0.42;
        const angle = toCentre + spread;
        // Start on land and extend into the inlet.
        let r = inlet.radius + 30;
        let startX = inlet.x + Math.cos(angle) * r;
        let startZ = inlet.z + Math.sin(angle) * r;
        // Walk back until we are on land.
        let guard = 0;
        while (!this.isLand(startX, startZ) && guard++ < 60) {
          r += 8;
          startX = inlet.x + Math.cos(angle) * r;
          startZ = inlet.z + Math.sin(angle) * r;
        }
        if (guard >= 60) continue;

        const length = 64;
        const dirX = -Math.cos(angle), dirZ = -Math.sin(angle);
        const cx = startX + dirX * length * 0.5;
        const cz = startZ + dirZ * length * 0.5;
        const yaw = Math.atan2(dirX, dirZ);

        b.setColor(0xffffff, 0.85 + (p % 2) * 0.2);
        b.rotatedBox(cx, deckY - 0.15, cz, 3.2, 0.15, length / 2, -yaw, 2.4);
        // Piles.
        for (let s = -1; s <= 1; s += 2) {
          for (let t = 0; t <= 4; t++) {
            const along = (t / 4 - 0.5) * length;
            const px = cx + dirX * along - dirZ * 3.0 * s;
            const pz = cz + dirZ * along + dirX * 3.0 * s;
            b.cylinder(px, SEA_LEVEL - 2, pz, 0.22, deckY - SEA_LEVEL + 2, 6, 2, false);
          }
        }
        b.resetColor();

        physics.addStaticBox(
          new Vector3(cx, deckY - 0.15, cz), new Vector3(3.2, 0.15, length / 2), colliderYaw(-yaw),
        );

        /*
         * Moor alongside the seaward end of the pier - but only once the sea floor is
         * genuinely below the waterline. The beach ramps gradually, so a berth placed by
         * distance alone lands on the sand and the boat sits aground instead of afloat.
         */
        let along = length * 0.3;
        let mx = 0, mz = 0;
        for (let step = 0; step < 40; step++) {
          mx = cx + dirX * along - dirZ * 5.4;
          mz = cz + dirZ * along + dirX * 5.4;
          if (this.heightAt(mx, mz) < SEA_LEVEL - 1.5) break;
          along += 6;
        }
        if (this.heightAt(mx, mz) >= SEA_LEVEL - 1.5) continue;   // no deep water here
        moorings.push({ x: mx, z: mz, heading: yaw });
      }
    }

    if (b.isEmpty) return { mesh: null, moorings };
    const mesh = new Mesh(b.build(), getMaterial('wood'));
    mesh.name = 'docks';
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    return { mesh, moorings };
  }

  /** Nearest open-water point to a position, for boat spawning and mission markers. */
  nearestWater(x, z, maxSearch = 900) {
    if (!this.isLand(x, z)) return { x, z };
    for (let r = 20; r < maxSearch; r += 20) {
      for (let a = 0; a < 16; a++) {
        const angle = (a / 16) * Math.PI * 2;
        const px = x + Math.cos(angle) * r, pz = z + Math.sin(angle) * r;
        if (!this.isLand(px, pz)) return { x: px, z: pz };
      }
    }
    return null;
  }
}

export { getFlat };
