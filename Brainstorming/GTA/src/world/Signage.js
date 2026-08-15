/**
 * Billboards and signage.
 *
 * Every sign in the city shares one texture atlas and therefore one draw call. A billboard
 * picks a tile by offsetting its UVs into the atlas, which is what lets thousands of
 * distinct-looking panels merge into a single mesh - the alternative, a material per
 * design, would cost a draw call each.
 *
 * The artwork is drawn on a canvas at load time: bold blocks, stripes and type, which is
 * what advertising reads as at a distance and which no amount of noise can fake.
 */

import { Mesh, CanvasTexture, MeshStandardMaterial, Vector3, SRGBColorSpace } from 'three/webgpu';
import { GeometryBuilder, colliderYaw } from './GeometryBuilder.js';
import { getMaterial } from '../render/Materials.js';
import { GROUP } from '../physics/Physics.js';
import { makeRng } from '../core/Noise.js';

const ATLAS_COLS = 4;
const ATLAS_ROWS = 2;
const TILE = 256;

/** Ad copy, deliberately generic - it is set dressing, not a joke. */
const ADS = [
  { top: 'LIBERTY', bottom: 'HORIZON', bg: '#1d3557', fg: '#f1faee', accent: '#e63946' },
  { top: 'DRIVE', bottom: 'FASTER', bg: '#e63946', fg: '#fff8f0', accent: '#ffd166' },
  { top: 'HARBOUR', bottom: 'MARINA', bg: '#0d3b4f', fg: '#a8dadc', accent: '#f4a261' },
  { top: 'OPEN', bottom: '24 / 7', bg: '#faf3dd', fg: '#22223b', accent: '#e07a5f' },
  { top: 'THE', bottom: 'TOWERS', bg: '#2b2d42', fg: '#edf2f4', accent: '#8d99ae' },
  { top: 'ISLAND', bottom: 'RADIO', bg: '#3d405b', fg: '#f2cc8f', accent: '#81b29a' },
  { top: 'FRESH', bottom: 'DAILY', bg: '#588157', fg: '#f6fff8', accent: '#dad7cd' },
  { top: 'CITY', bottom: 'TRANSIT', bg: '#ffb703', fg: '#023047', accent: '#fb8500' },
];

/** Draw all the ad designs into one atlas. */
function makeAdAtlas() {
  const canvas = document.createElement('canvas');
  canvas.width = TILE * ATLAS_COLS;
  canvas.height = TILE * ATLAS_ROWS;
  const ctx = canvas.getContext('2d');

  ADS.forEach((ad, i) => {
    const cx = (i % ATLAS_COLS) * TILE;
    const cy = Math.floor(i / ATLAS_COLS) * TILE;
    ctx.save();
    ctx.translate(cx, cy);

    ctx.fillStyle = ad.bg;
    ctx.fillRect(0, 0, TILE, TILE);

    // A diagonal accent band, the single most common billboard device.
    ctx.fillStyle = ad.accent;
    ctx.beginPath();
    ctx.moveTo(0, TILE * 0.72);
    ctx.lineTo(TILE, TILE * 0.52);
    ctx.lineTo(TILE, TILE * 0.68);
    ctx.lineTo(0, TILE * 0.88);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = ad.fg;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `900 ${TILE * 0.2}px "Segoe UI", Arial, sans-serif`;
    ctx.fillText(ad.top, TILE / 2, TILE * 0.3);
    ctx.font = `900 ${TILE * 0.26}px "Segoe UI", Arial, sans-serif`;
    ctx.fillText(ad.bottom, TILE / 2, TILE * 0.53);

    // Border, so panels read as framed objects rather than floating colour.
    ctx.strokeStyle = 'rgba(0,0,0,0.35)';
    ctx.lineWidth = TILE * 0.03;
    ctx.strokeRect(0, 0, TILE, TILE);
    ctx.restore();
  });

  const tex = new CanvasTexture(canvas);
  tex.colorSpace = SRGBColorSpace;
  tex.anisotropy = 8;
  tex.needsUpdate = true;
  return tex;
}

export class Signage {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {import('./City.js').City} city
   */
  constructor(physics, city, { seed = 8080 } = {}) {
    this.physics = physics;
    this.city = city;
    this.rng = makeRng(seed);

    this.panels = new GeometryBuilder();
    this.frames = new GeometryBuilder();
    this.count = 0;

    this._rooftopBillboards();
    this._wallSigns();

    this.meshes = [];
    if (!this.panels.isEmpty) {
      const atlas = makeAdAtlas();
      // Slight emissive so signs stay legible at dusk without needing their own lights.
      const material = new MeshStandardMaterial({
        map: atlas,
        emissiveMap: atlas,
        emissive: 0xffffff,
        emissiveIntensity: 0.12,
        roughness: 0.72,
        metalness: 0.0,
        vertexColors: true,
      });
      this.material = material;
      const mesh = new Mesh(this.panels.build(), material);
      mesh.name = 'signPanels';
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      this.meshes.push(mesh);
    }
    if (!this.frames.isEmpty) {
      const mesh = new Mesh(this.frames.build(), getMaterial('metal'));
      mesh.name = 'signFrames';
      mesh.castShadow = true;
      this.meshes.push(mesh);
    }
    this.panels = null;
    this.frames = null;
  }

  /** UV rect for an atlas tile. */
  _tileUV(index) {
    const i = index % ADS.length;
    const col = i % ATLAS_COLS;
    const row = Math.floor(i / ATLAS_COLS);
    const u0 = col / ATLAS_COLS, u1 = (col + 1) / ATLAS_COLS;
    // Canvas rows run top-down, texture V runs bottom-up.
    const v1 = 1 - row / ATLAS_ROWS, v0 = 1 - (row + 1) / ATLAS_ROWS;
    return [u0, v0, u1, v1];
  }

  /**
   * A flat, double-sided panel standing in the XY plane, rotated about Y by `yaw`.
   * UVs come from the atlas tile so every panel can share one material.
   */
  _panel(cx, cy, cz, halfW, halfH, yaw, tileIndex) {
    const [u0, v0, u1, v1] = this._tileUV(tileIndex);
    const cos = Math.cos(yaw), sin = Math.sin(yaw);
    const p = (lx, ly) => new Vector3(cx + lx * cos, cy + ly, cz + lx * sin);
    const n = new Vector3(-sin, 0, cos);

    const a = p(-halfW, -halfH), b = p(halfW, -halfH);
    const c = p(halfW, halfH), d = p(-halfW, halfH);
    this.panels.quad(a, b, c, d, [u0, v0], [u1, v0], [u1, v1], [u0, v1], n);
    // Back face, so the sign is not invisible from behind.
    const back = n.clone().negate();
    this.panels.quad(b, a, d, c, [u0, v0], [u1, v0], [u1, v1], [u0, v1], back);
    this.count++;
  }

  /** Billboards on the roofs of mid-rise buildings, facing the city centre. */
  _rooftopBillboards() {
    const candidates = this.city.buildingBoxes.filter(
      (b) => b.height > 14 && b.height < 70 && (b.x1 - b.x0) > 14 && (b.z1 - b.z0) > 14,
    );
    for (const b of candidates) {
      if (this.rng() > 0.09) continue;
      const cx = (b.x0 + b.x1) / 2, cz = (b.z0 + b.z1) / 2;
      // Face the city centre: that is where the player spends most of their time.
      const yaw = Math.atan2(-cx, -cz) + Math.PI / 2;
      const halfW = Math.min((b.x1 - b.x0), (b.z1 - b.z0)) * 0.38;
      if (halfW < 4) continue;
      const halfH = halfW * 0.52;
      const baseY = b.height + 0.4;
      const cyPanel = baseY + halfH + 1.6;

      this._panel(cx, cyPanel, cz, halfW, halfH, yaw, Math.floor(this.rng() * ADS.length));

      // Support legs and a top rail, in the shared metal material.
      const cos = Math.cos(yaw), sin = Math.sin(yaw);
      this.frames.setColor(0x555b61, 1.0);
      for (const s of [-0.72, 0.72]) {
        const lx = halfW * s;
        this.frames.cylinder(cx + lx * cos, baseY, cz + lx * sin, 0.16, halfH + 1.6, 6, 2, false);
      }
      this.frames.rotatedBox(cx, cyPanel + halfH + 0.18, cz, halfW + 0.3, 0.12, 0.18, -yaw, 2);
      this.frames.resetColor();
    }
  }

  /** Smaller signs mounted flat against building walls at street level. */
  _wallSigns() {
    const net = this.city.network;
    for (const b of this.city.buildingBoxes) {
      if (b.height < 8) continue;
      if (this.rng() > 0.05) continue;
      // Only worth placing where a road can see it.
      const cx = (b.x0 + b.x1) / 2, cz = (b.z0 + b.z1) / 2;
      const near = net.nearestOnRoad(cx, cz);
      if (!near || near.distance > 40) continue;

      // Mount on the wall facing the nearest road.
      const dx = near.x - cx, dz = near.z - cz;
      const alongX = Math.abs(dx) > Math.abs(dz);
      const yaw = alongX ? (dx > 0 ? Math.PI / 2 : -Math.PI / 2) : (dz > 0 ? 0 : Math.PI);
      const px = alongX ? (dx > 0 ? b.x1 + 0.18 : b.x0 - 0.18) : cx;
      const pz = alongX ? cz : (dz > 0 ? b.z1 + 0.18 : b.z0 - 0.18);

      const halfW = 2.2 + this.rng() * 1.6;
      const halfH = halfW * 0.42;
      const y = 5.5 + this.rng() * 3;
      this._panel(px, y, pz, halfW, halfH, yaw, Math.floor(this.rng() * ADS.length));
    }
  }

  /**
   * Signs pick up a little glow after dark, in the same way the lamp heads do.
   * @param {number} nightFactor
   */
  update(nightFactor) {
    if (this.material) this.material.emissiveIntensity = 0.1 + nightFactor * 0.75;
  }
}

export { colliderYaw, GROUP };
