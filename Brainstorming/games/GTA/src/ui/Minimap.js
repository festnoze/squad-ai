/**
 * Radar and world map.
 *
 * The street map is baked once into an offscreen canvas from the same data the 3D world
 * was generated from - the island field, the road graph, block footprints and parks - so
 * the map can never drift out of sync with the city. Per frame we only blit a rotated
 * crop of that bitmap plus a handful of blips, which costs nothing.
 *
 * `M` opens the full map over the whole screen.
 */

const COLOURS = {
  sea: '#12303f',
  land: '#2e3a30',
  beach: '#7d6f4f',
  block: '#3b4048',
  park: '#2f4a30',
  street: '#5c626b',
  avenue: '#7c828b',
  streetEdge: '#2a2e34',
  highway: '#c9a227',
  highwayEdge: '#4a3d12',
  player: '#ffe066',
  vehicle: '#9aa4b2',
  boat: '#63b3d6',
  mission: '#ffb703',
  wanted: '#e5383b',
  ped: '#c9cdd4',
  pickup: '#57cc99',
  waypoint: '#4cc9f0',
  bridge: '#b7a68b',
  bridgeEdge: '#4a4238',
};

export class Minimap {
  /**
   * @param {HTMLCanvasElement} canvas the small radar canvas in the HUD
   * @param {object} world `{ island, city, ocean }`
   */
  constructor(canvas, { island, city, highway = null, bridges = null }) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.island = island;
    this.city = city;
    this.highway = highway;
    this.bridges = bridges;

    /** World-space extent covered by the baked bitmap. */
    this.extent = 1750;
    this.bakeSize = 2048;
    /** Metres visible across the radar. Smaller = more zoomed in. */
    this.radarSpan = 260;
    this.rotate = true;

    this.blips = [];
    this.baked = null;
    this._bake();

    this.fullOpen = false;
    this._buildFullMap();
  }

  /** World metres -> baked bitmap pixels. */
  _toMap(x, z) {
    const s = this.bakeSize / (this.extent * 2);
    return [(x + this.extent) * s, (z + this.extent) * s];
  }

  _bake() {
    const size = this.bakeSize;
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext('2d');
    const scale = size / (this.extent * 2);

    ctx.fillStyle = COLOURS.sea;
    ctx.fillRect(0, 0, size, size);

    /* ------------------------------------------------------------ land mass */
    // Scan-convert the island field. A coarse grid is plenty at map resolution and it
    // guarantees the coastline drawn here is the coastline the player walks on.
    const step = 6;
    const cells = Math.ceil((this.extent * 2) / step);
    for (let j = 0; j < cells; j++) {
      const z = -this.extent + j * step;
      for (let i = 0; i < cells; i++) {
        const x = -this.extent + i * step;
        const f = this.island ? this.island.landField(x, z) : 1;
        if (f <= 0) continue;
        ctx.fillStyle = f < 46 ? COLOURS.beach : COLOURS.land;
        const [px, pz] = this._toMap(x, z);
        ctx.fillRect(px, pz, step * scale + 1, step * scale + 1);
      }
    }

    /* --------------------------------------------------------------- blocks */
    ctx.fillStyle = COLOURS.block;
    for (const b of this.city.network.blocks) {
      const [x0, z0] = this._toMap(b.x0, b.z0);
      const [x1, z1] = this._toMap(b.x1, b.z1);
      ctx.fillRect(x0, z0, x1 - x0, z1 - z0);
    }

    ctx.fillStyle = COLOURS.park;
    for (const p of this.city.parks) {
      const [x0, z0] = this._toMap(p.x0, p.z0);
      const [x1, z1] = this._toMap(p.x1, p.z1);
      ctx.fillRect(x0, z0, x1 - x0, z1 - z0);
    }

    /* ---------------------------------------------------------------- roads */
    // Two passes: a dark casing under a lighter carriageway, which is what makes a road
    // network legible at a glance rather than a grey mesh.
    for (const pass of ['edge', 'fill']) {
      for (const e of this.city.network.edges) {
        const a = this.city.network.nodes[e.a];
        const b = this.city.network.nodes[e.b];
        const [ax, az] = this._toMap(a.x, a.z);
        const [bx, bz] = this._toMap(b.x, b.z);
        const w = e.type.width * scale;
        ctx.strokeStyle = pass === 'edge' ? COLOURS.streetEdge
          : (e.type.width > 15 ? COLOURS.avenue : COLOURS.street);
        ctx.lineWidth = pass === 'edge' ? w + 2 : w;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(ax, az);
        ctx.lineTo(bx, bz);
        ctx.stroke();
      }
    }

    /* -------------------------------------------------------------- highway */
    // Drawn last and in its own colour: an elevated road is a different navigational
    // thing from a street, and burying it in the same grey makes the map unreadable.
    if (this.highway && this.highway.ringPoints.length) {
      const pts = this.highway.ringPoints;
      for (const pass of ['edge', 'fill']) {
        ctx.strokeStyle = pass === 'edge' ? COLOURS.highwayEdge : COLOURS.highway;
        ctx.lineWidth = (pass === 'edge' ? 26 : 20) * scale;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        pts.forEach((wp, i) => {
          const [px, pz] = this._toMap(wp.x, wp.z);
          if (i === 0) ctx.moveTo(px, pz);
          else ctx.lineTo(px, pz);
        });
        ctx.closePath();
        ctx.stroke();
      }
    }

    /* -------------------------------------------------------------- bridges */
    // Drawn over the highway: a bridge is the one crossing on the map that decides a
    // route, so it has to survive being covered by whatever else runs near the shore.
    if (this.bridges) {
      for (const span of this.bridges.spans) {
        const [ax, az] = this._toMap(span.a.x, span.a.z);
        const [bx, bz] = this._toMap(span.b.x, span.b.z);
        for (const pass of ['edge', 'fill']) {
          ctx.strokeStyle = pass === 'edge' ? COLOURS.bridgeEdge : COLOURS.bridge;
          ctx.lineWidth = (pass === 'edge' ? 24 : 17) * scale;
          ctx.lineCap = 'butt';
          ctx.beginPath();
          ctx.moveTo(ax, az);
          ctx.lineTo(bx, bz);
          ctx.stroke();
        }
      }
    }

    this.baked = canvas;
  }

  _buildFullMap() {
    const el = document.createElement('div');
    el.id = 'worldmap';
    el.hidden = true;
    el.innerHTML = '<canvas id="worldmap-canvas"></canvas><div class="legend">M to close</div>';
    document.body.appendChild(el);
    this.fullEl = el;
    this.fullCanvas = el.querySelector('canvas');
    this.fullCtx = this.fullCanvas.getContext('2d');
  }

  toggleFull() {
    this.fullOpen = !this.fullOpen;
    this.fullEl.hidden = !this.fullOpen;
    return this.fullOpen;
  }

  /** Replace the blip list for this frame. */
  setBlips(blips) { this.blips = blips; }

  /**
   * @param {{x:number,z:number}} focus world position at the centre of the radar
   * @param {number} heading radians; the radar rotates so this points up
   */
  draw(focus, heading) {
    const ctx = this.ctx;
    const size = this.canvas.width;
    const half = size / 2;
    const scale = this.bakeSize / (this.extent * 2);
    const pxPerMetre = size / this.radarSpan;

    ctx.save();
    ctx.clearRect(0, 0, size, size);
    // Circular mask.
    ctx.beginPath();
    ctx.arc(half, half, half, 0, Math.PI * 2);
    ctx.clip();
    ctx.fillStyle = COLOURS.sea;
    ctx.fillRect(0, 0, size, size);

    ctx.translate(half, half);
    if (this.rotate) ctx.rotate(heading);
    ctx.scale(pxPerMetre / scale, pxPerMetre / scale);
    const [fx, fz] = this._toMap(focus.x, focus.z);
    ctx.drawImage(this.baked, -fx, -fz);
    ctx.restore();

    /* ---------------------------------------------------------------- blips */
    ctx.save();
    ctx.translate(half, half);
    if (this.rotate) ctx.rotate(heading);
    for (const b of this.blips) {
      const dx = (b.x - focus.x) * pxPerMetre;
      const dz = (b.z - focus.z) * pxPerMetre;
      if (Math.hypot(dx, dz) > half - 4) {
        // Clamp off-screen mission blips to the rim so objectives stay findable.
        if (!b.pin) continue;
        const a = Math.atan2(dz, dx);
        ctx.fillStyle = COLOURS[b.kind] ?? '#fff';
        ctx.beginPath();
        ctx.arc(Math.cos(a) * (half - 6), Math.sin(a) * (half - 6), 3.5, 0, Math.PI * 2);
        ctx.fill();
        continue;
      }
      ctx.fillStyle = COLOURS[b.kind] ?? '#fff';
      ctx.beginPath();
      ctx.arc(dx, dz, b.size ?? 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    // Player arrow, always centred and pointing up.
    ctx.save();
    ctx.translate(half, half);
    ctx.fillStyle = COLOURS.player;
    ctx.beginPath();
    ctx.moveTo(0, -7);
    ctx.lineTo(5, 6);
    ctx.lineTo(0, 3);
    ctx.lineTo(-5, 6);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  /** Full-screen map. */
  drawFull(focus) {
    if (!this.fullOpen) return;
    const w = window.innerWidth, h = window.innerHeight;
    if (this.fullCanvas.width !== w || this.fullCanvas.height !== h) {
      this.fullCanvas.width = w;
      this.fullCanvas.height = h;
    }
    const ctx = this.fullCtx;
    ctx.fillStyle = 'rgba(6,9,14,0.92)';
    ctx.fillRect(0, 0, w, h);

    const side = Math.min(w, h) * 0.86;
    const ox = (w - side) / 2, oy = (h - side) / 2;
    ctx.drawImage(this.baked, ox, oy, side, side);
    ctx.strokeStyle = 'rgba(255,255,255,.25)';
    ctx.strokeRect(ox, oy, side, side);

    const worldToScreen = (x, z) => {
      const s = side / (this.extent * 2);
      return [ox + (x + this.extent) * s, oy + (z + this.extent) * s];
    };

    for (const b of this.blips) {
      const [px, pz] = worldToScreen(b.x, b.z);
      ctx.fillStyle = COLOURS[b.kind] ?? '#fff';
      ctx.beginPath();
      ctx.arc(px, pz, b.kind === 'mission' ? 6 : 2.5, 0, Math.PI * 2);
      ctx.fill();
    }

    const [px, pz] = worldToScreen(focus.x, focus.z);
    ctx.fillStyle = COLOURS.player;
    ctx.beginPath();
    ctx.arc(px, pz, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#0b0e13';
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}
