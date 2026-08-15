/**
 * Neon and shop-window spill.
 *
 * Ground-floor lighting is what separates a city that happens to be dark from a city that
 * is *at night*. Street lamps light the road; neon lights the buildings, and the spill
 * pools on the pavement in front of shopfronts.
 *
 * Everything here is unlit geometry in one merged mesh whose brightness is driven by the
 * time of day, exactly like the lamp heads in `StreetProps`. Authored above 1.0 so the
 * bloom threshold catches it - a neon tube that does not bloom reads as painted plastic.
 */

import { Mesh, MeshBasicMaterial, Vector3, DoubleSide, AdditiveBlending } from 'three/webgpu';
import { GeometryBuilder, colliderYaw } from './GeometryBuilder.js';
import { makeRng } from '../core/Noise.js';
import { DISTRICT, districtAt } from './City.js';

/** Saturated tube colours. Deliberately few - real signage streets repeat a palette. */
const NEON_COLOURS = [
  0xff2d6f, 0x2de1ff, 0xffd12d, 0x8f2dff, 0x2dff8f, 0xff6a2d, 0xffffff, 0xff2d2d,
];

const TUBE_GLOW = 3.4;
const SPILL_GLOW = 1.5;
const SIDEWALK_HEIGHT = 0.17;

export class Neon {
  /**
   * @param {import('./City.js').City} city
   */
  constructor(city, { seed = 6161 } = {}) {
    this.city = city;
    this.rng = makeRng(seed);

    this.tubes = new GeometryBuilder();
    this.spill = new GeometryBuilder();
    this.count = 0;

    this._build();

    this.meshes = [];
    // Tubes glow; additive blending is what makes them read as light rather than paint.
    this.tubeMaterial = new MeshBasicMaterial({
      vertexColors: true, toneMapped: true, side: DoubleSide,
      transparent: true, opacity: 1, blending: AdditiveBlending, depthWrite: false,
    });
    // Spill is a soft pool on the ground; normal blending so it tints rather than adds.
    this.spillMaterial = new MeshBasicMaterial({
      vertexColors: true, toneMapped: true, transparent: true, opacity: 0.5,
      depthWrite: false, blending: AdditiveBlending,
    });

    if (!this.tubes.isEmpty) {
      const m = new Mesh(this.tubes.build(), this.tubeMaterial);
      m.name = 'neonTubes';
      m.renderOrder = 6;
      this.meshes.push(m);
    }
    if (!this.spill.isEmpty) {
      const m = new Mesh(this.spill.build(), this.spillMaterial);
      m.name = 'neonSpill';
      m.renderOrder = 5;
      this.meshes.push(m);
    }
    this.tubes = null;
    this.spill = null;
  }

  _pick() { return NEON_COLOURS[Math.floor(this.rng() * NEON_COLOURS.length)]; }

  _build() {
    const net = this.city.network;

    for (const b of this.city.buildingBoxes) {
      const district = b.district ?? districtAt((b.x0 + b.x1) / 2, (b.z0 + b.z1) / 2);
      // Neon belongs on commercial frontage, not on suburban houses or warehouses.
      const chance = district === DISTRICT.DOWNTOWN ? 0.5
        : district === DISTRICT.MIDTOWN ? 0.42 : 0.05;
      if (this.rng() > chance) continue;
      if (b.height < 7) continue;

      const cx = (b.x0 + b.x1) / 2, cz = (b.z0 + b.z1) / 2;
      const near = net.nearestOnRoad(cx, cz);
      if (!near || near.distance > 42) continue;

      // Face the nearest road, on whichever wall points at it.
      const dx = near.x - cx, dz = near.z - cz;
      const alongX = Math.abs(dx) > Math.abs(dz);
      const outX = alongX ? Math.sign(dx) : 0;
      const outZ = alongX ? 0 : Math.sign(dz);
      const wallX = alongX ? (dx > 0 ? b.x1 : b.x0) : cx;
      const wallZ = alongX ? cz : (dz > 0 ? b.z1 : b.z0);
      const halfSpan = alongX ? (b.z1 - b.z0) / 2 : (b.x1 - b.x0) / 2;
      if (halfSpan < 3) continue;

      this._frontage(wallX, wallZ, outX, outZ, halfSpan, alongX);
    }
  }

  /**
   * One shopfront: a horizontal tube above the door line, a vertical blade sign, and a
   * pool of spill on the pavement.
   */
  _frontage(wallX, wallZ, outX, outZ, halfSpan, alongX) {
    const colour = this._pick();
    const push = 0.16;
    const x = wallX + outX * push;
    const z = wallZ + outZ * push;
    const bandY = 3.6 + this.rng() * 1.4;
    const span = Math.min(halfSpan * 0.85, 7);

    const t = this.tubes;
    t.setColor(colour, TUBE_GLOW);
    // Horizontal band. Thin in the wall normal, long across the frontage.
    if (alongX) {
      t.box(
        new Vector3(x - 0.06, bandY, z - span),
        new Vector3(x + 0.06, bandY + 0.22, z + span), 1,
      );
    } else {
      t.box(
        new Vector3(x - span, bandY, z - 0.06),
        new Vector3(x + span, bandY + 0.22, z + 0.06), 1,
      );
    }

    // Vertical blade sign projecting from the wall, on some frontages.
    if (this.rng() < 0.45) {
      const bladeColour = this._pick();
      const top = bandY + 1.0 + this.rng() * 3.5;
      const bottom = bandY + 0.5;
      t.setColor(bladeColour, TUBE_GLOW);
      const out = 0.55;
      if (alongX) {
        t.box(
          new Vector3(x, bottom, z - 0.35),
          new Vector3(x + outX * out, top, z + 0.35), 1,
        );
      } else {
        t.box(
          new Vector3(x - 0.35, bottom, z),
          new Vector3(x + 0.35, top, z + outZ * out), 1,
        );
      }
    }
    t.resetColor();

    /*
     * Spill on the pavement. A flat quad just above the slab rather than a real light:
     * a hundred shopfronts cannot each afford a point light, and at ground level a
     * soft pool of the sign's own colour reads as the light it casts.
     */
    const s = this.spill;
    const depth = 3.4;
    const y = SIDEWALK_HEIGHT + 0.03;
    // Emitted as concentric bands of falling intensity rather than one flat quad: light
    // falls off with distance, and a hard-edged rectangle on the pavement reads as a
    // painted marking rather than as a glow.
    const bands = 3;
    for (let i = 0; i < bands; i++) {
      const near = (i / bands) * depth;
      const far = ((i + 1) / bands) * depth;
      s.setColor(colour, SPILL_GLOW * (1 - i / bands) ** 1.6);
      if (alongX) {
        const a = x + outX * near, b2 = x + outX * far;
        s.ground(Math.min(a, b2), z - span, Math.max(a, b2), z + span, y, 6);
      } else {
        const a = z + outZ * near, b2 = z + outZ * far;
        s.ground(x - span, Math.min(a, b2), x + span, Math.max(a, b2), y, 6);
      }
    }
    s.resetColor();
    this.count++;
  }

  /**
   * Neon is off in daylight and full after dark. Also flickers a little - a perfectly
   * steady tube looks like a lightbox.
   * @param {number} nightFactor
   * @param {number} time seconds
   */
  update(nightFactor, time) {
    const flicker = 0.96 + Math.sin(time * 11.3) * 0.02 + Math.sin(time * 27.7) * 0.02;
    const level = nightFactor * flicker;
    this.tubeMaterial.color.setScalar(level);
    this.spillMaterial.color.setScalar(level);
    // Hide entirely by day so additive blending does not wash out the facades.
    for (const m of this.meshes) m.visible = nightFactor > 0.02;
  }
}

export { colliderYaw };
