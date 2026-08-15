import { TILE, GRID_W, GRID_D } from './world.js';
import { GUARD_STATE } from './guards.js';

/**
 * Fog-of-war floor plan. Rooms are drawn only once the player has set foot in
 * them, so the map doubles as a record of how much of the facility has been
 * explored. Small version sits in the corner; M blows it up to full screen.
 */
export class Minimap {
  constructor(world) {
    this.world = world;
    this.discovered = new Set();
    this.expanded = false;

    this.canvas = document.getElementById('minimap');
    this.ctx = this.canvas.getContext('2d');
    this.wrap = document.getElementById('minimap-wrap');
    this.counter = document.getElementById('minimap-count');
    this.title = document.getElementById('minimap-title');

    // Areas that make up one visual room, so the plan reads as rooms rather
    // than as the dozens of rectangles the level is actually carved from.
    this.roomOf = new Map();
    for (const a of world.areas) this.roomOf.set(a.id, a.name);

    this._pulse = 0;
    this._sized = null;
  }

  /** Marks whatever the player is standing in as seen. */
  observe(position) {
    const area = this.world.areaAt(position);
    if (area) this.discovered.add(area.id);
  }

  toggle() {
    this.expanded = !this.expanded;
    this.wrap.classList.toggle('expanded', this.expanded);
    this.title.textContent = this.expanded ? 'PLAN DU PENITENCIER' : 'PLAN';
  }

  reset() {
    this.discovered.clear();
    this.expanded = false;
    this.wrap.classList.remove('expanded');
    this.title.textContent = 'PLAN';
  }

  get roomsSeen() {
    const names = new Set();
    for (const id of this.discovered) {
      const n = this.roomOf.get(id);
      if (n) names.add(n);
    }
    return names.size;
  }

  get roomsTotal() {
    return new Set([...this.roomOf.values()]).size;
  }

  draw(dt, state) {
    const { player, cameras, guards, doors, marker } = state;
    this._pulse += dt;

    const size = this.expanded ? 720 : 250;
    if (this._sized !== size) {
      this._sized = size;
      const ratio = GRID_D / GRID_W;
      this.canvas.width = size;
      this.canvas.height = Math.round(size * ratio);
      this.canvas.style.width = `${size}px`;
      this.canvas.style.height = `${Math.round(size * ratio)}px`;
    }

    const ctx = this.ctx;
    const W = this.canvas.width;
    const H = this.canvas.height;
    const s = W / (GRID_W * TILE);              // pixels per world unit
    const px = (wx) => wx * s;
    const pz = (wz) => wz * s;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(8, 11, 15, 0.82)';
    ctx.fillRect(0, 0, W, H);

    // ---------------------------------------------------------- the rooms
    for (const a of this.world.areas) {
      if (!this.discovered.has(a.id)) continue;
      const x = px(a.x0 * TILE);
      const z = pz(a.z0 * TILE);
      const w = px((a.x1 - a.x0 + 1) * TILE);
      const h = pz((a.z1 - a.z0 + 1) * TILE);
      ctx.fillStyle = a.outdoor ? 'rgba(60, 72, 62, 0.95)' : 'rgba(58, 66, 74, 0.95)';
      ctx.fillRect(x, z, w, h);
    }

    // Outline only the outer edge of the discovered blob: any face that is not
    // shared with another discovered area reads as a wall.
    ctx.strokeStyle = 'rgba(168, 180, 190, 0.75)';
    ctx.lineWidth = this.expanded ? 2 : 1.2;
    for (const a of this.world.areas) {
      if (!this.discovered.has(a.id)) continue;
      for (let x = a.x0; x <= a.x1; x++) {
        for (let z = a.z0; z <= a.z1; z++) {
          for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
            const nb = this._areaAtTile(x + dx, z + dz);
            if (nb && this.discovered.has(nb.id)) continue;
            const x0 = px(x * TILE), z0 = pz(z * TILE);
            const x1 = px((x + 1) * TILE), z1 = pz((z + 1) * TILE);
            ctx.beginPath();
            if (dx === 1) { ctx.moveTo(x1, z0); ctx.lineTo(x1, z1); }
            else if (dx === -1) { ctx.moveTo(x0, z0); ctx.lineTo(x0, z1); }
            else if (dz === 1) { ctx.moveTo(x0, z1); ctx.lineTo(x1, z1); }
            else { ctx.moveTo(x0, z0); ctx.lineTo(x1, z0); }
            ctx.stroke();
          }
        }
      }
    }

    // --------------------------------------------------------- room labels
    if (this.expanded) {
      ctx.font = '10px Consolas, monospace';
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(214, 226, 234, 0.72)';
      const drawn = new Set();
      for (const a of this.world.areas) {
        if (!this.discovered.has(a.id) || drawn.has(a.name)) continue;
        const tiles = (a.x1 - a.x0 + 1) * (a.z1 - a.z0 + 1);
        if (tiles < 6) continue;
        drawn.add(a.name);
        const cx = px((a.x0 + (a.x1 - a.x0 + 1) / 2) * TILE);
        const cz = pz((a.z0 + (a.z1 - a.z0 + 1) / 2) * TILE);
        ctx.fillText(a.name.toUpperCase(), cx, cz);
      }
    }

    // --------------------------------------------------------------- doors
    for (const d of doors) {
      const area = this.world.areaAt(d.position);
      if (!area || !this.discovered.has(area.id)) continue;
      ctx.fillStyle = d.locked ? '#ff3b3b' : '#35ff8a';
      const r = this.expanded ? 5 : 3;
      ctx.fillRect(px(d.position.x) - r, pz(d.position.z) - r, r * 2, r * 2);
    }

    // ------------------------------------------------------------- cameras
    for (const cam of cameras) {
      const area = this.world.areaAt(cam.position);
      if (!area || !this.discovered.has(area.id)) continue;
      const cx = px(cam.position.x);
      const cz = pz(cam.position.z);
      if (cam.alive) {
        // Cone of view, so the plan shows where not to walk.
        const half = Math.acos(cam.cosHalfFov);
        const rad = px(cam.range * 0.8);
        ctx.beginPath();
        ctx.moveTo(cx, cz);
        // Screen +y is world +z, and the camera looks down its local -Z.
        ctx.arc(cx, cz, rad, -cam.yaw - Math.PI / 2 - half, -cam.yaw - Math.PI / 2 + half);
        ctx.closePath();
        ctx.fillStyle = cam.meter > 0.05 ? 'rgba(255, 120, 60, 0.20)' : 'rgba(90, 200, 255, 0.14)';
        ctx.fill();
      }
      ctx.beginPath();
      ctx.arc(cx, cz, this.expanded ? 5 : 3, 0, Math.PI * 2);
      ctx.fillStyle = cam.alive ? '#59c8ff' : '#5a3030';
      ctx.fill();
      if (this.expanded) {
        ctx.font = '9px Consolas, monospace';
        ctx.textAlign = 'left';
        ctx.fillStyle = cam.alive ? 'rgba(89, 200, 255, 0.9)' : 'rgba(140, 90, 90, 0.9)';
        ctx.fillText(cam.id, cx + 7, cz + 3);
      }
    }

    // Alerted guards only: knowing where every patrol is would kill the game.
    for (const g of guards) {
      if (!g.alive || g.state !== GUARD_STATE.ALERT) continue;
      const cx = px(g.position.x);
      const cz = pz(g.position.z);
      ctx.beginPath();
      ctx.arc(cx, cz, (this.expanded ? 6 : 4) * (1 + Math.sin(this._pulse * 8) * 0.15), 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 59, 59, 0.85)';
      ctx.fill();
    }

    // ------------------------------------------------------------ marker
    if (marker) {
      const cx = px(marker.x);
      const cz = pz(marker.z);
      const r = (this.expanded ? 7 : 5) + Math.sin(this._pulse * 4) * 1.5;
      ctx.beginPath();
      ctx.arc(cx, cz, r, 0, Math.PI * 2);
      ctx.strokeStyle = '#ffc23a';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cz, 1.6, 0, Math.PI * 2);
      ctx.fillStyle = '#ffc23a';
      ctx.fill();
    }

    // ------------------------------------------------------------- player
    const cx = px(player.position.x);
    const cz = pz(player.position.z);
    const size2 = this.expanded ? 9 : 6;
    ctx.save();
    ctx.translate(cx, cz);
    // World forward is (-sin yaw, -cos yaw); on the plan that is (-sin, -cos).
    ctx.rotate(-player.yaw);
    ctx.beginPath();
    ctx.moveTo(0, -size2);
    ctx.lineTo(size2 * 0.65, size2 * 0.7);
    ctx.lineTo(0, size2 * 0.35);
    ctx.lineTo(-size2 * 0.65, size2 * 0.7);
    ctx.closePath();
    ctx.fillStyle = player.disguised ? '#8fbaff' : '#ffffff';
    ctx.fill();
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();

    this.counter.textContent = `${this.roomsSeen}/${this.roomsTotal}`;
  }

  _areaAtTile(x, z) {
    if (x < 0 || z < 0 || x >= GRID_W || z >= GRID_D) return null;
    return this.world.area[z][x];
  }
}
