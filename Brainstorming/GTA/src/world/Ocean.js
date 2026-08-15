/**
 * Ocean.
 *
 * three ships a `WaterMesh` for WebGPU, but it is WebGPU-only and depends on a live
 * reflection render. This implementation runs identically on both backends: a flat plane
 * with two counter-scrolling normal maps, a deep-water base colour, and strong
 * environment reflection. Detail comes from the normals rather than from geometry.
 *
 * Wave *height* is a separate analytic function, `heightAt()`, shared by the buoyancy
 * solver so boats bob in sync with what the player sees. Amplitude is kept small (tens of
 * centimetres) precisely so a flat visual surface and a wavy physical one never visibly
 * disagree.
 */

import {
  Mesh, PlaneGeometry, MeshStandardMaterial, Color, Vector2, Vector3, RepeatWrapping,
} from 'three/webgpu';
import { makeWaterNormals } from '../render/TextureFactory.js';
import { SEA_LEVEL } from './Island.js';

/** Directional wave train: amplitude, wavelength, speed, direction. */
const WAVES = [
  { amp: 0.20, len: 34, speed: 5.2, dx: 1.00, dz: 0.12 },
  { amp: 0.13, len: 19, speed: 6.4, dx: 0.42, dz: 0.91 },
  { amp: 0.08, len: 11, speed: 7.8, dx: -0.72, dz: 0.69 },
  { amp: 0.04, len: 6.5, speed: 9.1, dx: 0.18, dz: -0.98 },
];

export class Ocean {
  constructor({ size = 9000, level = SEA_LEVEL } = {}) {
    this.level = level;
    this.time = 0;

    const normals = makeWaterNormals(512);
    normals.wrapS = normals.wrapT = RepeatWrapping;
    // Two independent samplers would be ideal; with one shared texture we get the same
    // read by scrolling the normal and roughness slots at different rates.
    this.normalMap = normals.clone();
    this.normalMap.wrapS = this.normalMap.wrapT = RepeatWrapping;
    this.normalMap.repeat.set(size / 26, size / 26);
    this.normalMap.needsUpdate = true;

    this.material = new MeshStandardMaterial({
      color: new Color(0x0d2a38),
      roughness: 0.055,
      metalness: 0.02,
      normalMap: this.normalMap,
      normalScale: new Vector2(0.55, 0.55),
      envMapIntensity: 1.6,
      transparent: true,
      // Nearly opaque. The sea bed underneath is lit and shadowed like any other terrain,
      // so a clearer surface shows the hard rectangular edge where the sun's shadow
      // frustum ends. A little transparency keeps the shallows readable without that.
      opacity: 0.965,
    });

    const geometry = new PlaneGeometry(size, size, 1, 1);
    geometry.rotateX(-Math.PI / 2);
    this.mesh = new Mesh(geometry, this.material);
    this.mesh.position.y = level;
    this.mesh.name = 'ocean';
    this.mesh.receiveShadow = false;
    this.mesh.frustumCulled = false;
    // Draw after opaque geometry so the transparent surface blends over the sea floor.
    this.mesh.renderOrder = 10;

    this._scroll = new Vector2();
  }

  /**
   * Surface height at a world position.
   * @param {number} x
   * @param {number} z
   * @param {number} [t] time in seconds; defaults to the ocean's own clock
   */
  heightAt(x, z, t = this.time) {
    let h = 0;
    for (const w of WAVES) {
      const k = (Math.PI * 2) / w.len;
      const phase = (x * w.dx + z * w.dz) * k + t * w.speed * k;
      h += Math.sin(phase) * w.amp;
    }
    return this.level + h;
  }

  /**
   * Surface normal, from the analytic derivative of `heightAt`. Used to orient boats
   * with the wave slope.
   */
  normalAt(x, z, out = new Vector3(), t = this.time) {
    let dx = 0, dz = 0;
    for (const w of WAVES) {
      const k = (Math.PI * 2) / w.len;
      const phase = (x * w.dx + z * w.dz) * k + t * w.speed * k;
      const c = Math.cos(phase) * w.amp * k;
      dx += c * w.dx;
      dz += c * w.dz;
    }
    return out.set(-dx, 1, -dz).normalize();
  }

  /** Depth of a point below the surface; negative when above water. */
  depthAt(x, y, z) { return this.heightAt(x, z) - y; }

  isUnderwater(x, y, z) { return y < this.heightAt(x, z); }

  /** Keep the plane centred on the viewer so it always reaches the horizon. */
  update(dt, focus) {
    this.time += dt;
    if (focus) this.mesh.position.set(focus.x, this.level, focus.z);
    // Scroll the normals; the offset drifts diagonally so the swell has a direction.
    this._scroll.x = (this.time * 0.0075) % 1;
    this._scroll.y = (this.time * 0.0042) % 1;
    this.normalMap.offset.copy(this._scroll);
  }

  dispose() {
    this.mesh.geometry.dispose();
    this.material.dispose();
    this.normalMap.dispose();
  }
}
