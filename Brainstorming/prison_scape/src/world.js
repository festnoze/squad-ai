import * as THREE from 'three';
import { Colliders } from './collision.js';
import { getTexture, getTextureXY } from './textures.js';
import {
  TILE, GRID_W, GRID_D, tileX, tileZ,
  AREAS, DOOR_DEFS, CAMERA_DEFS, GUARD_DEFS, PICKUP_DEFS,
  PLAYER_SPAWN, EXIT_TILE, WALL_H, HALL_H, BACK_H,
} from './layout.js';

export {
  TILE, GRID_W, GRID_D, tileX, tileZ,
  PLAYER_SPAWN, EXIT_TILE,
} from './layout.js';

/** World-space centre of a tile column, as a vector. */
export function tileVec(ix, iz, y = 0) { return new THREE.Vector3(tileX(ix), y, tileZ(iz)); }

/**
 * Builds the whole prison: geometry, colliders, doors, camera mounts, props
 * and the light rig. Everything lives under `this.group` in the scene.
 */
export class World {
  constructor(scene) {
    this.scene = scene;
    this.group = new THREE.Group();
    scene.add(this.group);
    this.colliders = new Colliders(TILE * 2);
    this.doors = [];
    this.cellGates = [];
    this.lightSpots = [];
    this.areaByTile = new Map();
    this.cameraDefs = CAMERA_DEFS;
    this.guardDefs = GUARD_DEFS;
    this.pickupDefs = PICKUP_DEFS;

    this._buildGrid();
    this._buildFloorsAndCeilings();
    this._buildWalls();
    this._buildDoors();
    this._propBatches = new Map();
    this._buildSecretDoors();
    this._buildProps();
    this._flushProps();
    this._buildLightRig();
  }

  // ------------------------------------------------------------------ grid
  _buildGrid() {
    this.open = [];
    this.area = [];
    for (let z = 0; z < GRID_D; z++) {
      this.open.push(new Array(GRID_W).fill(false));
      this.area.push(new Array(GRID_W).fill(null));
    }
    for (const a of AREAS) {
      for (let z = a.z0; z <= a.z1; z++) {
        for (let x = a.x0; x <= a.x1; x++) {
          if (x < 0 || z < 0 || x >= GRID_W || z >= GRID_D) continue;
          this.open[z][x] = true;
          this.area[z][x] = a;
        }
      }
    }
    this.areas = AREAS;
  }

  isOpen(x, z) {
    if (x < 0 || z < 0 || x >= GRID_W || z >= GRID_D) return false;
    return this.open[z][x];
  }

  areaAt(pos) {
    const x = Math.floor(pos.x / TILE);
    const z = Math.floor(pos.z / TILE);
    if (x < 0 || z < 0 || x >= GRID_W || z >= GRID_D) return null;
    return this.area[z][x];
  }

  /** True when the point sits under open sky (used for lighting and rain). */
  isOutdoor(pos) {
    const a = this.areaAt(pos);
    return !!(a && a.outdoor);
  }

  // ---------------------------------------------------- floors and ceilings
  /**
   * Floors and ceilings, merged into one mesh per texture. Seventy areas with
   * a plane each is seventy draw calls before a single wall is drawn, so the
   * quads are welded together and their UVs baked from world coordinates.
   */
  _buildFloorsAndCeilings() {
    const slabs = new Map();   // texture name -> list of quads

    const quad = (tex, x0, z0, x1, z1, y, up, uvScale) => {
      if (!slabs.has(tex)) slabs.set(tex, []);
      slabs.get(tex).push({ x0, z0, x1, z1, y, up, uvScale });
    };

    for (const a of AREAS) {
      const x0 = a.x0 * TILE, x1 = (a.x1 + 1) * TILE;
      const z0 = a.z0 * TILE, z1 = (a.z1 + 1) * TILE;
      quad(a.floor, x0, z0, x1, z1, 0, true, 1 / 4);
      if (!a.outdoor) quad(a.ceil ?? 'ceiling', x0, z0, x1, z1, a.h, false, 1 / 8);
    }

    for (const [texName, quads] of slabs) {
      const n = quads.length;
      const pos = new Float32Array(n * 4 * 3);
      const nor = new Float32Array(n * 4 * 3);
      const uv = new Float32Array(n * 4 * 2);
      const idx = new Uint32Array(n * 6);

      quads.forEach((q, i) => {
        const v = i * 4;
        // corners, anticlockwise seen from above
        const corners = [[q.x0, q.z0], [q.x1, q.z0], [q.x1, q.z1], [q.x0, q.z1]];
        corners.forEach(([px, pz], c) => {
          const o = (v + c) * 3;
          pos[o] = px; pos[o + 1] = q.y; pos[o + 2] = pz;
          nor[o] = 0; nor[o + 1] = q.up ? 1 : -1; nor[o + 2] = 0;
          const u = (v + c) * 2;
          uv[u] = px * q.uvScale;
          uv[u + 1] = pz * q.uvScale;
        });
        const t = i * 6;
        if (q.up) {
          idx[t] = v; idx[t + 1] = v + 2; idx[t + 2] = v + 1;
          idx[t + 3] = v; idx[t + 4] = v + 3; idx[t + 5] = v + 2;
        } else {
          idx[t] = v; idx[t + 1] = v + 1; idx[t + 2] = v + 2;
          idx[t + 3] = v; idx[t + 4] = v + 2; idx[t + 5] = v + 3;
        }
      });

      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
      geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
      geo.setIndex(new THREE.BufferAttribute(idx, 1));
      geo.computeBoundingSphere();

      const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({
        map: getTexture(texName, 1),
      }));
      mesh.frustumCulled = false;
      this.group.add(mesh);
    }
    // The floor plane is not a collider: a single ground box under everything
    // is cheaper and stops the player falling through area seams.
    this.colliders.add(
      new THREE.Vector3(-40, -6, -40),
      new THREE.Vector3(GRID_W * TILE + 40, 0, GRID_D * TILE + 40),
      { tag: 'ground' }
    );
  }

  // ----------------------------------------------------------------- walls
  _buildWalls() {
    const byStyle = new Map();
    const NB = [[1, 0], [-1, 0], [0, 1], [0, -1]];

    for (let z = 0; z < GRID_D; z++) {
      for (let x = 0; x < GRID_W; x++) {
        if (this.open[z][x]) continue;
        let style = null;
        let height = 0;
        for (const [dx, dz] of NB) {
          const nx = x + dx, nz = z + dz;
          if (!this.isOpen(nx, nz)) continue;
          const a = this.area[nz][nx];
          if (!style) style = a.wall;
          height = Math.max(height, a.h);
        }
        if (!style) continue;
        if (!byStyle.has(style)) byStyle.set(style, []);
        byStyle.get(style).push({ x, z, h: height });
      }
    }

    const geo = new THREE.BoxGeometry(TILE, 1, TILE);
    for (const [style, cells] of byStyle) {
      const mat = new THREE.MeshLambertMaterial({ map: getTexture(style, 1) });
      const mesh = new THREE.InstancedMesh(geo, mat, cells.length);
      mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
      const m = new THREE.Matrix4();
      cells.forEach((c, i) => {
        m.makeScale(1, c.h, 1);
        m.setPosition(tileX(c.x), c.h / 2, tileZ(c.z));
        mesh.setMatrixAt(i, m);
        this.colliders.add(
          new THREE.Vector3(c.x * TILE, 0, c.z * TILE),
          new THREE.Vector3((c.x + 1) * TILE, c.h, (c.z + 1) * TILE),
          { tag: 'wall' }
        );
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.frustumCulled = false;
      this.group.add(mesh);
    }
  }

  // ----------------------------------------------------------------- doors
  _buildDoors() {
    for (const def of DOOR_DEFS) {
      const a = AREAS.find((r) => r.id === def.area);
      const rect = def.rect || [a.x0, a.z0, a.x1, a.z1];
      const [x0, z0, x1, z1] = rect;
      const w = (x1 - x0 + 1) * TILE;
      const d = (z1 - z0 + 1) * TILE;
      const cx = (x0 * TILE + (x1 + 1) * TILE) / 2;
      const cz = (z0 * TILE + (z1 + 1) * TILE) / 2;
      const h = a.h - 0.4;

      const thickness = 0.5;
      const sizeX = def.axis === 'z' ? thickness : w;
      const sizeZ = def.axis === 'z' ? d : thickness;
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(sizeX, h, sizeZ),
        new THREE.MeshLambertMaterial({ map: getTexture('doorLocked', 1) })
      );
      mesh.position.set(cx, h / 2, cz);
      this.group.add(mesh);

      // Status light above the door, red while locked.
      const lamp = new THREE.Mesh(
        new THREE.SphereGeometry(0.22, 10, 8),
        new THREE.MeshBasicMaterial({ color: 0xff2a2a })
      );
      lamp.position.set(cx, h - 0.1, cz);
      this.group.add(lamp);

      const box = this.colliders.add(
        new THREE.Vector3(cx - sizeX / 2, 0, cz - sizeZ / 2),
        new THREE.Vector3(cx + sizeX / 2, h, cz + sizeZ / 2),
        { tag: 'door' }
      );

      const tiles = [];
      for (let z = z0; z <= z1; z++) for (let x = x0; x <= x1; x++) tiles.push([x, z]);

      this.doors.push({
        id: def.id,
        label: def.label,
        cameras: Array.isArray(def.camera) ? def.camera : [def.camera],
        mesh, lamp, box, tiles,
        closedY: h / 2,
        openY: h / 2 - h - 0.5,
        locked: true,
        opening: false,
        t: 0,
        position: new THREE.Vector3(cx, 1.5, cz),
      });
    }
  }

  // --------------------------------------------------------- navigation
  /**
   * Flow field over the walkable tiles, pointing at `(tx, tz)`. Guards read the
   * next step out of it instead of walking blindly into walls. One BFS serves
   * every guard heading for the same tile, and the result is cached until the
   * target or the door state changes.
   */
  flowField(tx, tz) {
    const key = `${tx},${tz}|${this._doorStamp ?? 0}`;
    if (this._flowKey === key) return this._flowField;

    const n = GRID_W * GRID_D;
    const next = new Int32Array(n).fill(-1);
    const dist = new Int32Array(n).fill(-1);
    const blocked = this._blockedTiles();

    const start = tz * GRID_W + tx;
    if (tx < 0 || tz < 0 || tx >= GRID_W || tz >= GRID_D || !this.open[tz][tx] || blocked.has(start)) {
      this._flowKey = key;
      this._flowField = { next, dist };
      return this._flowField;
    }

    dist[start] = 0;
    const queue = [start];
    for (let head = 0; head < queue.length; head++) {
      const cur = queue[head];
      const cx = cur % GRID_W;
      const cz = (cur - cx) / GRID_W;
      for (let i = 0; i < 4; i++) {
        const nx = cx + (i === 0 ? 1 : i === 1 ? -1 : 0);
        const nz = cz + (i === 2 ? 1 : i === 3 ? -1 : 0);
        if (nx < 0 || nz < 0 || nx >= GRID_W || nz >= GRID_D) continue;
        if (!this.open[nz][nx]) continue;
        const idx = nz * GRID_W + nx;
        if (blocked.has(idx) || dist[idx] !== -1) continue;
        dist[idx] = dist[cur] + 1;
        next[idx] = cur;          // step toward the target
        queue.push(idx);
      }
    }

    this._flowKey = key;
    this._flowField = { next, dist };
    return this._flowField;
  }

  /** Tiles a still-locked security door seals off. */
  _blockedTiles() {
    if (this._blockedCache && this._blockedStamp === (this._doorStamp ?? 0)) {
      return this._blockedCache;
    }
    const set = new Set();
    for (const door of this.doors) {
      if (!door.locked) continue;
      for (const [x, z] of door.tiles) set.add(z * GRID_W + x);
    }
    // Guards do not go off-plan. Whatever is back there, it is the player's
    // problem alone.
    for (const a of this.areas) {
      if (a.nav !== false) continue;
      for (let z = a.z0; z <= a.z1; z++) {
        for (let x = a.x0; x <= a.x1; x++) set.add(z * GRID_W + x);
      }
    }
    this._blockedCache = set;
    this._blockedStamp = this._doorStamp ?? 0;
    return set;
  }

  /** The tile a walker at `position` should step to next on the way to a field's target. */
  nextStep(field, position) {
    const x = Math.floor(position.x / TILE);
    const z = Math.floor(position.z / TILE);
    if (x < 0 || z < 0 || x >= GRID_W || z >= GRID_D) return null;
    const idx = z * GRID_W + x;
    const step = field.next[idx];
    if (step < 0) return null;
    const sx = step % GRID_W;
    const sz = (step - sx) / GRID_W;
    return { x: tileX(sx), z: tileZ(sz), tile: [sx, sz], dist: field.dist[idx] };
  }

  /** Called when a camera dies: releases any door whose cameras are all down. */
  releaseDoors(deadCameraIds) {
    const opened = [];
    for (const door of this.doors) {
      if (!door.locked) continue;
      if (door.cameras.every((c) => deadCameraIds.has(c))) {
        door.locked = false;
        door.opening = true;
        door.lamp.material.color.setHex(0x35ff6a);
        // Sink the collider out of the way; the mesh animates down to match.
        door.box.min.y = -200;
        door.box.max.y = -190;
        opened.push(door);
      }
    }
    // Invalidate the navigation caches: a new route just opened up.
    if (opened.length) this._doorStamp = (this._doorStamp ?? 0) + 1;
    return opened;
  }

  updateDoors(dt) {
    for (const door of this.doors) {
      if (!door.opening) continue;
      door.t = Math.min(1, door.t + dt / 2.2);
      const e = 1 - Math.pow(1 - door.t, 3);
      door.mesh.position.y = door.closedY + (door.openY - door.closedY) * e;
      if (door.t >= 1) door.opening = false;
    }
  }

  /**
   * The two ways off-plan, both sealed until the player works them loose: a
   * loose tile panel at the back of the last toilet stall, and a rusted vent
   * grille behind the pallets at the bottom of the yard. Without the second
   * one the backrooms would simply be an open corridor off the yard, which
   * rather defeats the point of hiding them.
   */
  _buildSecretDoors() {
    this.secretDoors = [];

    const add = (cfg) => {
      const { cx, cz, w, d, h, tex, label, tipAxis } = cfg;
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(w, h, d),
        new THREE.MeshLambertMaterial({ map: getTexture(tex, 1) })
      );
      mesh.position.set(cx, h / 2, cz);
      this.group.add(mesh);

      // A hairline of yellow light around the edge: the only tell.
      const seam = new THREE.Mesh(
        new THREE.PlaneGeometry(tipAxis === 'z' ? w - 0.1 : d - 0.1, h - 0.15),
        new THREE.MeshBasicMaterial({
          color: 0xffe07a, transparent: true, opacity: 0.14,
          blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
        })
      );
      seam.position.set(cx, h / 2, cz);
      if (tipAxis === 'x') seam.rotation.y = Math.PI / 2;
      this.group.add(seam);

      const box = this.colliders.add(
        new THREE.Vector3(cx - w / 2, 0, cz - d / 2),
        new THREE.Vector3(cx + w / 2, h, cz + d / 2),
        { tag: 'secret' }
      );

      this.secretDoors.push({
        mesh, seam, box, label, tipAxis, h,
        home: new THREE.Vector3(cx, h / 2, cz),
        position: new THREE.Vector3(cx, 1.4, cz),
        open: false,
        t: 0,
      });
    };

    // 1. The stall panel, on the seam between the toilets and the throat.
    add({
      cx: tileX(4), cz: tileZ(32) + TILE / 2,
      w: TILE - 0.2, d: 0.34, h: 2.6,
      tex: 'tileWhite', label: 'DESCELLER LE PANNEAU', tipAxis: 'z',
    });

    // 2. The vent grille, on the seam between the back corridor and the yard.
    add({
      cx: tileX(23) + TILE / 2, cz: tileZ(39) + TILE / 2,
      w: 0.34, d: TILE * 2 - 0.2, h: 2.6,
      tex: 'metal', label: 'FORCER LA GRILLE', tipAxis: 'x',
    });
  }

  /** The sealed way the player is standing next to, or null. */
  secretDoorNear(position, radius = 2.8) {
    for (const p of this.secretDoors) {
      if (p.open) continue;
      if (p.position.distanceTo(position) < radius) return p;
    }
    return null;
  }

  /** Works one loose. Returns false if it was already open. */
  openSecretDoor(p) {
    if (!p || p.open) return false;
    p.open = true;
    p.box.min.y = -200;
    p.box.max.y = -190;
    return true;
  }

  updateSecretDoors(dt) {
    for (const p of this.secretDoors) {
      if (!p.open || p.t >= 1) continue;
      p.t = Math.min(1, p.t + dt * 1.6);
      const e = 1 - Math.pow(1 - p.t, 3);
      // Tips out of the wall and falls flat.
      if (p.tipAxis === 'z') {
        p.mesh.rotation.x = e * -1.45;
        p.mesh.position.z = p.home.z - e * 1.1;
      } else {
        p.mesh.rotation.z = e * 1.45;
        p.mesh.position.x = p.home.x + e * 1.1;
      }
      p.mesh.position.y = p.home.y - e * (p.h / 2 - 0.15);
      p.seam.material.opacity = 0.14 + e * 0.5;
    }
  }

  resetSecretDoors() {
    for (const p of this.secretDoors) {
      p.open = false;
      p.t = 0;
      p.mesh.rotation.set(0, 0, 0);
      p.mesh.position.copy(p.home);
      p.seam.material.opacity = 0.14;
      p.box.min.y = 0;
      p.box.max.y = p.h;
    }
  }

  // ----------------------------------------------------------------- props
  /**
   * Queues a box-shaped prop. Nothing is built yet: props are collected by
   * material and flushed into one InstancedMesh each, because a room full of
   * individually meshed bunks and lockers costs one draw call apiece and that
   * alone halved the frame rate.
   */
  _addBox(cx, cy, cz, sx, sy, sz, color, opts = {}) {
    const key = [
      opts.map ?? '', opts.repeat ?? 1, color ?? 0,
      opts.emissive ?? 0, opts.transparent ? 1 : 0, opts.opacity ?? 1,
    ].join('|');
    let batch = this._propBatches.get(key);
    if (!batch) {
      batch = { color, opts, items: [] };
      this._propBatches.set(key, batch);
    }
    batch.items.push({ cx, cy, cz, sx, sy, sz, rotY: opts.rotY || 0 });

    if (opts.solid !== false) {
      this.colliders.add(
        new THREE.Vector3(cx - sx / 2, cy - sy / 2, cz - sz / 2),
        new THREE.Vector3(cx + sx / 2, cy + sy / 2, cz + sz / 2),
        { tag: opts.tag || 'prop' }
      );
    }
  }

  /** Builds one InstancedMesh per prop material and drops the queue. */
  _flushProps() {
    const unit = new THREE.BoxGeometry(1, 1, 1);
    const m = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const axis = new THREE.Vector3(0, 1, 0);
    const pos = new THREE.Vector3();
    const scl = new THREE.Vector3();

    for (const batch of this._propBatches.values()) {
      const o = batch.opts;
      const mat = o.map
        ? new THREE.MeshLambertMaterial({ map: getTexture(o.map, o.repeat || 1) })
        : new THREE.MeshLambertMaterial({ color: batch.color, emissive: o.emissive || 0x000000 });
      if (o.transparent) {
        mat.transparent = true;
        mat.opacity = o.opacity ?? 1;
        mat.side = THREE.DoubleSide;
        mat.depthWrite = (o.opacity ?? 1) > 0.8;
      }

      const mesh = new THREE.InstancedMesh(unit, mat, batch.items.length);
      mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
      batch.items.forEach((it, i) => {
        q.setFromAxisAngle(axis, it.rotY);
        pos.set(it.cx, it.cy, it.cz);
        scl.set(it.sx, it.sy, it.sz);
        m.compose(pos, q, scl);
        mesh.setMatrixAt(i, m);
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.frustumCulled = false;   // one call each; culling would gain nothing
      this.group.add(mesh);
    }
    this._propBatches.clear();
  }

  _buildProps() {
    // ------------------------------------------------------------- cells
    for (let i = 0; i < 6; i++) {
      const x0 = 2 + i * 3;
      for (const [z0, side] of [[3, 'N'], [10, 'S']]) {
        const bx = tileX(x0) - 1.0;
        const bz = tileZ(z0) + (side === 'N' ? -0.4 : 0.4);
        // bunk bed: frame + two mattresses
        this._addBox(bx, 0.42, bz, 1.9, 0.12, 3.0, 0x5b6167);
        this._addBox(bx, 0.52, bz, 1.8, 0.16, 2.9, 0x8a8272, { solid: false });
        this._addBox(bx, 1.62, bz, 1.9, 0.12, 3.0, 0x5b6167);
        this._addBox(bx, 1.72, bz, 1.8, 0.16, 2.9, 0x8a8272, { solid: false });
        this._addBox(bx - 0.9, 1.0, bz - 1.4, 0.12, 2.0, 0.12, 0x4a5055);
        this._addBox(bx - 0.9, 1.0, bz + 1.4, 0.12, 2.0, 0.12, 0x4a5055);
        // toilet + sink against the far wall
        const tz = side === 'N' ? tileZ(z0) - 1.4 : tileZ(z0 + 2) + 1.4;
        this._addBox(tileX(x0 + 1) + 0.9, 0.32, tz, 0.7, 0.64, 0.6, 0xb9bec0);
        this._addBox(tileX(x0 + 1) + 0.9, 1.05, tz + (side === 'N' ? -0.1 : 0.1), 0.66, 0.16, 0.55, 0x9aa0a2, { solid: false });
      }
      // Barred gates on each cell doorway. They hold everyone in until the
      // blackout that starts the run drops the locks.
      for (const z of [6, 9]) {
        const h = WALL_H - 0.4;
        const bars = new THREE.Mesh(
          new THREE.PlaneGeometry(TILE, h),
          new THREE.MeshLambertMaterial({
            map: getTexture('bars', 1), transparent: true, alphaTest: 0.45, side: THREE.DoubleSide,
          })
        );
        bars.position.set(tileX(x0), h / 2, tileZ(z));
        this.group.add(bars);
        const box = this.colliders.add(
          new THREE.Vector3(x0 * TILE, 0, tileZ(z) - 0.2),
          new THREE.Vector3((x0 + 1) * TILE, h, tileZ(z) + 0.2),
          { tag: 'cellgate' }
        );
        this.cellGates.push({ mesh: bars, box, opening: false, y0: h / 2, top: h });
      }
    }

    // ---------------------------------------------------- central rotunda
    // A raised control desk in the middle, with pillars and benches to break
    // the sightlines of CAM-2 and give the player something to hide behind.
    this._addBox(tileX(25) + 2, 0.55, tileZ(8) + 2, 6.0, 1.1, 4.0, 0x3f464d, { map: 'metal' });
    this._addBox(tileX(25) + 2, 1.18, tileZ(8) + 2, 6.4, 0.16, 4.4, 0x596066);
    for (let i = 0; i < 3; i++) {
      this._addBox(tileX(24) + 1 + i * 1.6, 1.75, tileZ(8) + 0.4, 1.3, 0.85, 0.12,
        0x101214, { emissive: 0x0a2418, solid: false });
    }
    // Kept off tile (23,5): that is CAM-2's mount, and a pillar there would
    // block every shot the player takes at it.
    for (const [px, pz] of [[24, 6], [28, 6], [24, 12], [28, 12]]) {
      this._addBox(tileX(px), HALL_H / 2, tileZ(pz), 1.2, HALL_H, 1.2, 0x5c6268, { map: 'wall' });
    }
    for (const [bx, bz] of [[24, 10], [27, 6]]) {
      this._addBox(tileX(bx), 0.45, tileZ(bz), 3.4, 0.16, 0.9, 0x6b5f4a);
      this._addBox(tileX(bx) - 1.4, 0.22, tileZ(bz), 0.2, 0.45, 0.8, 0x50565a);
      this._addBox(tileX(bx) + 1.4, 0.22, tileZ(bz), 0.2, 0.45, 0.8, 0x50565a);
    }

    // ------------------------------------------------------- guard post
    this._addBox(tileX(33), 0.85, tileZ(8) + 0.6, 5.0, 0.14, 1.6, 0x6b5b45);
    for (const dx of [-2.2, 2.2]) {
      this._addBox(tileX(33) + dx, 0.42, tileZ(8) + 0.6, 0.14, 0.85, 1.5, 0x51462f);
    }
    // wall of monitors
    for (let i = 0; i < 4; i++) {
      const mx = tileX(31) - 1.2 + i * 1.35;
      this._addBox(mx, 2.4, tileZ(7) - 1.85, 1.15, 0.75, 0.12, 0x101214, { emissive: 0x0a2a1a, solid: false });
    }
    // lockers, kept clear of the x37 wall column
    for (let i = 0; i < 4; i++) {
      this._addBox(tileX(36) + 0.9, 1.05, tileZ(9) + i * 1.0 - 1.5, 1.1, 2.1, 0.95, 0x3f4a52, { map: 'metal' });
    }
    this._addBox(tileX(35), 0.45, tileZ(11), 1.0, 0.9, 1.0, 0x4d5358); // filing cabinet

    // --------------------------------------------------------- armoury
    for (let i = 0; i < 3; i++) {
      this._addBox(tileX(41) + i * 1.6, 1.1, tileZ(8) - 1.6, 1.2, 2.2, 0.5, 0x3a3f43, { map: 'metal' });
    }
    for (let i = 0; i < 4; i++) {
      this._addBox(tileX(43) + (i % 2) * 1.4 - 0.7, 0.4 + Math.floor(i / 2) * 0.8, tileZ(12) + (i % 2) * 0.3, 1.3, 0.8, 1.3, 0x4a5138);
    }

    // -------------------------------------------------------- refectoire
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 2; c++) {
        const cx = tileX(33) + c * 6.5;
        const cz = tileZ(19) + r * 5.0;
        this._addBox(cx, 0.78, cz, 4.6, 0.12, 1.1, 0x8c7a55);
        this._addBox(cx, 0.39, cz, 0.2, 0.78, 0.9, 0x565b5e);
        for (const dz of [-1.0, 1.0]) {
          this._addBox(cx, 0.45, cz + dz, 4.4, 0.1, 0.55, 0x6e6047);
        }
      }
    }
    // serving counter
    this._addBox(tileX(42), 0.55, tileZ(21), 1.2, 1.1, 8.0, 0x9aa0a2, { map: 'metal' });

    // --------------------------------------------------------- buanderie
    for (let i = 0; i < 5; i++) {
      this._addBox(tileX(4) + i * 1.6, 0.9, tileZ(19) - 1.4, 1.4, 1.8, 1.3, 0x7d8386, { map: 'metal' });
    }
    for (let i = 0; i < 3; i++) {
      this._addBox(tileX(5) + i * 2.4, 0.6, tileZ(22), 1.6, 1.2, 1.6, 0x6b5f4a); // laundry carts
    }

    // ---------------------------------------------------- local technique
    for (let i = 0; i < 3; i++) {
      this._addBox(tileX(14) + i * 2.2, 1.2, tileZ(19), 1.6, 2.4, 1.6, 0x4a5a52); // generators
    }
    for (let i = 0; i < 4; i++) {
      this._addBox(tileX(15) + i * 1.2, 0.7, tileZ(22), 1.0, 1.4, 1.0, 0x5b4a3a); // crates
    }
    // overhead pipe runs, purely decorative
    for (let i = 0; i < 3; i++) {
      const pipe = new THREE.Mesh(
        new THREE.CylinderGeometry(0.16, 0.16, 26, 8),
        new THREE.MeshLambertMaterial({ color: 0x555f5a })
      );
      pipe.rotation.z = Math.PI / 2;
      pipe.position.set(tileX(10), WALL_H - 0.55 - i * 0.42, tileZ(15) + 0.5 + i * 0.6);
      this.group.add(pipe);
    }

    // ----------------------------------------------------------- douches
    // Open shower bay: heads on the wall, half-height dividers, drains, bench.
    for (let i = 0; i < 6; i++) {
      const sx = tileX(22) + 1.4 + i * 2.0;
      this._addBox(sx, 2.35, tileZ(18) - 1.75, 0.16, 0.16, 0.55, 0x9aa0a2, { solid: false });
      this._addBox(sx, 2.05, tileZ(18) - 1.5, 0.34, 0.12, 0.34, 0xb4babc, { solid: false });
      if (i < 5) this._addBox(sx + 1.0, 1.0, tileZ(18) - 0.6, 0.12, 2.0, 2.2, 0xa8b0ae);
      // floor drain
      this._addBox(sx, 0.02, tileZ(18) - 0.4, 0.5, 0.04, 0.5, 0x4a5052, { solid: false });
    }
    this._addBox(tileX(27), 0.5, tileZ(23), 4.0, 1.0, 0.4, 0x7f8588); // bench
    for (let i = 0; i < 3; i++) {
      this._addBox(tileX(23) + i * 1.2, 1.05, tileZ(23) + 1.4, 1.1, 2.1, 0.9, 0x54606a, { map: 'metal' });
    }

    // --------------------------------------------------------- sanitaires
    this._buildToilets();
    this._buildInfirmary();
    this._buildVisitRoom();
    this._buildKitchen();
    this._buildWorkshop();
    this._buildSolitary();
    this._buildBackrooms();

    // ------------------------------------------------------------- yard
    this._buildYard();

    // ------------------------------------------------------ wall clutter
    this._addBox(tileX(25), 3.2, tileZ(4) - 1.9, 6.0, 2.4, 0.2, 0x2a2f33, { solid: false, emissive: 0x0e1a12 });
  }

  /** Sanitary block: a row of stalls, urinals, a trough sink and mirrors. */
  _buildToilets() {
    const white = 0xc6cdca;
    // Stalls down the west wall, dividers and doors. The last one backs onto
    // the loose panel.
    for (let i = 0; i < 4; i++) {
      const sz = tileZ(28) + 1.2 + i * 2.6;
      this._addBox(tileX(2) + 1.5, 1.15, sz + 1.3, 3.0, 2.3, 0.1, 0xb0b8b5);   // divider
      this._addBox(tileX(2) + 0.6, 0.32, sz, 0.7, 0.64, 0.6, white);           // pan
      this._addBox(tileX(2) + 0.6, 0.78, sz - 0.35, 0.66, 0.3, 0.24, white, { solid: false });
      this._addBox(tileX(2) + 0.6, 1.55, sz - 0.4, 0.5, 0.7, 0.22, 0xa8b0ad, { solid: false }); // cistern
    }
    // Urinals on the east wall.
    for (let i = 0; i < 3; i++) {
      const uz = tileZ(29) + i * 1.6;
      this._addBox(tileX(7) + 1.5, 1.0, uz, 0.5, 0.9, 0.55, white, { solid: false });
      this._addBox(tileX(7) + 1.4, 1.7, uz, 0.7, 1.6, 0.9, 0xb8c0bd);         // privacy fin
    }
    // Trough sink and the mirror strip above it.
    this._addBox(tileX(5), 0.85, tileZ(32) + 1.4, 5.0, 0.25, 0.7, white);
    this._addBox(tileX(5), 0.45, tileZ(32) + 1.4, 4.8, 0.6, 0.5, 0x9aa2a0, { solid: false });
    this._addBox(tileX(5), 1.75, tileZ(32) + 1.75, 5.0, 1.3, 0.06, 0x6f8a92,
      { solid: false, emissive: 0x16242a });
    for (let i = 0; i < 3; i++) {
      this._addBox(tileX(4) + i * 1.6, 1.15, tileZ(32) + 1.6, 0.14, 0.3, 0.3, 0xb4bcb9, { solid: false });
    }
    // A mop bucket, because someone has to clean this.
    this._addBox(tileX(6) + 1.0, 0.35, tileZ(30), 0.7, 0.7, 0.7, 0x3f5f4a);
  }

  /** Infirmary: beds behind curtain rails, cabinets, a treatment trolley. */
  _buildInfirmary() {
    for (let i = 0; i < 3; i++) {
      const bz = tileZ(28) + 0.8 + i * 3.2;
      const bx = tileX(9) + 1.6;
      this._addBox(bx, 0.55, bz, 2.0, 0.14, 3.0, 0xb9c2c4);          // frame
      this._addBox(bx, 0.66, bz, 1.9, 0.18, 2.9, 0xe4e7e2, { solid: false });  // mattress
      this._addBox(bx, 0.86, bz - 1.1, 1.7, 0.16, 0.6, 0xf0f2ee, { solid: false }); // pillow
      this._addBox(bx, 0.95, bz + 1.5, 2.0, 0.7, 0.08, 0xa4adb0, { solid: false }); // foot board
      // curtain rail and a half-drawn curtain
      this._addBox(bx + 1.3, 2.3, bz, 0.08, 0.08, 3.0, 0x9aa2a4, { solid: false });
      this._addBox(bx + 1.3, 1.5, bz - 0.7, 0.1, 1.6, 1.5, 0x76a8b4,
        { solid: false, transparent: true, opacity: 0.75 });
      // bedside monitor
      this._addBox(bx + 1.5, 1.25, bz + 1.2, 0.5, 0.4, 0.4, 0x22282c, { emissive: 0x0d2a1e });
    }
    // Drug cabinet and desk along the east wall.
    for (let i = 0; i < 2; i++) {
      this._addBox(tileX(14) + 1.4, 1.15, tileZ(29) + i * 2.4, 1.0, 2.3, 1.8, 0xe8ebe6);
      this._addBox(tileX(14) + 0.85, 1.5, tileZ(29) + i * 2.4, 0.1, 1.1, 1.5, 0x8fb6c0,
        { solid: false, transparent: true, opacity: 0.55 });
    }
    this._addBox(tileX(12), 0.8, tileZ(32) + 1.3, 2.6, 0.12, 1.1, 0xdfe3de);
    this._addBox(tileX(11), 0.5, tileZ(31), 0.8, 1.0, 0.8, 0xcfd6d2);   // trolley
    // Red cross on the back wall.
    this._addBox(tileX(11), 2.9, tileZ(28) - 1.9, 1.6, 0.4, 0.1, 0xd4302f, { solid: false });
    this._addBox(tileX(11), 2.9, tileZ(28) - 1.9, 0.4, 1.6, 0.1, 0xd4302f, { solid: false });
  }

  /** Visiting room: booths split by glass, stools and handsets. */
  _buildVisitRoom() {
    const cz = tileZ(30);
    // The long counter and the glass partition running down the middle.
    this._addBox(tileX(17) + 1, 0.5, cz, 11.5, 1.0, 1.2, 0x6b5f4a);
    this._addBox(tileX(17) + 1, 1.9, cz, 11.5, 1.8, 0.12, 0x9fd0e0,
      { solid: false, transparent: true, opacity: 0.28 });
    for (let i = 0; i < 4; i++) {
      const bx = tileX(15) + 1.2 + i * 2.9;
      // booth dividers on both sides
      this._addBox(bx + 1.45, 1.4, cz, 0.12, 2.8, 3.4, 0x8a9095);
      // stools
      this._addBox(bx, 0.4, cz - 1.5, 0.5, 0.8, 0.5, 0x50565a);
      this._addBox(bx, 0.4, cz + 1.5, 0.5, 0.8, 0.5, 0x50565a);
      // handsets either side of the glass
      this._addBox(bx - 1.0, 1.35, cz - 0.35, 0.16, 0.5, 0.16, 0x1c2024, { solid: false });
      this._addBox(bx - 1.0, 1.35, cz + 0.35, 0.16, 0.5, 0.16, 0x1c2024, { solid: false });
    }
  }

  /** Kitchen: ranges, extraction hoods, prep counters and a walk-in. */
  _buildKitchen() {
    // Cooking line along the east wall.
    for (let i = 0; i < 3; i++) {
      const kz = tileZ(19) + i * 2.2;
      this._addBox(tileX(47) + 0.8, 0.5, kz, 1.6, 1.0, 2.0, 0x8d9498, { map: 'metal' });
      for (const dz of [-0.5, 0.5]) {
        this._addBox(tileX(47) + 0.8, 1.02, kz + dz, 0.6, 0.06, 0.6, 0x2a2f33, { solid: false });
      }
      this._addBox(tileX(47) + 0.8, 2.6, kz, 2.0, 0.7, 2.2, 0x767d81, { solid: false, map: 'metal' });
    }
    // Central prep island with pots.
    this._addBox(tileX(46), 0.5, tileZ(21), 1.6, 1.0, 5.0, 0x9aa2a6, { map: 'metal' });
    for (let i = 0; i < 3; i++) {
      this._addBox(tileX(46), 1.2, tileZ(20) + i * 1.6, 0.7, 0.4, 0.7, 0x5b6266, { solid: false });
    }
    // Walk-in fridge at the north end.
    this._addBox(tileX(46), 1.3, tileZ(18) - 1.0, 3.2, 2.6, 1.4, 0xb0b8ba, { map: 'metal' });
    this._addBox(tileX(46), 1.3, tileZ(18) - 0.3, 1.2, 2.2, 0.12, 0x7f878a, { solid: false });
    // Knife rack: the one thing in here worth noticing.
    this._addBox(tileX(45) - 0.9, 1.9, tileZ(23), 0.1, 0.5, 1.6, 0x3a4045, { solid: false });
  }

  /** Workshop: benches, vices, a pillar drill and stacked timber. */
  _buildWorkshop() {
    for (let i = 0; i < 4; i++) {
      const bx = tileX(29) + 1.5 + i * 2.6;
      this._addBox(bx, 0.85, tileZ(1) + 0.5, 2.2, 0.16, 1.2, 0x7a6448);
      this._addBox(bx, 0.42, tileZ(1) + 0.5, 2.0, 0.7, 1.0, 0x5b4a33, { solid: false });
      this._addBox(bx - 0.7, 1.05, tileZ(1) + 0.5, 0.3, 0.3, 0.3, 0x3f4a52, { solid: false }); // vice
      // tool board on the wall
      this._addBox(bx, 2.3, tileZ(1) - 1.9, 2.0, 1.4, 0.08, 0x4a3f2f, { solid: false });
    }
    // Pillar drill and a timber stack.
    this._addBox(tileX(37), 0.9, tileZ(2), 0.7, 1.8, 0.7, 0x3a4248);
    this._addBox(tileX(37), 1.9, tileZ(2) - 0.2, 0.4, 0.5, 1.0, 0x2f363b, { solid: false });
    for (let i = 0; i < 3; i++) {
      this._addBox(tileX(30), 0.3 + i * 0.45, tileZ(2) + 0.6, 1.4, 0.4, 3.0, 0x6b5636);
    }
  }

  /** Solitary: two bare isolation cells, one tile wide, in the wall slot. */
  _buildSolitary() {
    const cx = tileX(38);
    // Dividing wall across the middle of the slot, with a gap to squeeze past.
    this._addBox(cx - 1.1, 1.7, tileZ(9) + 2, 1.8, 3.4, 0.4, 0x6a7268);
    for (let i = 0; i < 2; i++) {
      // The divider sits at z=40; the two cells centre either side of it.
      const cz = tileZ(8) + i * 12.0;
      // slab bunk and a bucket. That is the whole inventory.
      this._addBox(cx - 1.1, 0.4, cz, 1.6, 0.35, 2.4, 0x707870);
      this._addBox(cx + 1.3, 0.25, cz + 1.0, 0.5, 0.5, 0.5, 0x3f5f4a);
      // observation slot in the east wall, glowing faintly from the far side
      this._addBox(cx + 1.9, 1.6, cz, 0.12, 0.28, 0.9, 0x1a1e20,
        { solid: false, emissive: 0x2a2410 });
    }
  }

  /**
   * The backrooms. Regular pillars, wallpaper that never changes, and a strip
   * light every few metres whether it helps or not.
   */
  _buildBackrooms() {
    const bays = [
      [1, 35, 20, 36], [1, 39, 20, 40],
      [2, 37, 3, 38], [8, 37, 9, 38], [14, 37, 15, 38], [19, 37, 20, 38],
      [21, 39, 23, 40], [4, 33, 4, 34],
    ];
    // Skirting board around every bay: the detail that sells an interior.
    for (const [x0, z0, x1, z1] of bays) {
      const cx = (x0 * TILE + (x1 + 1) * TILE) / 2;
      const cz = (z0 * TILE + (z1 + 1) * TILE) / 2;
      const w = (x1 - x0 + 1) * TILE;
      const d = (z1 - z0 + 1) * TILE;
      this._addBox(cx, 0.09, cz - d / 2 + 0.06, w, 0.18, 0.12, 0x8a7a34, { solid: false });
      this._addBox(cx, 0.09, cz + d / 2 - 0.06, w, 0.18, 0.12, 0x8a7a34, { solid: false });
    }

    // Fluorescent strips, thick on the ground and slightly too bright.
    const strips = [];
    const put = (x, z) => {
      strips.push([tileX(x), BACK_H - 0.09, tileZ(z)]);
      this.lightSpots.push({
        pos: new THREE.Vector3(tileX(x), BACK_H - 0.45, tileZ(z)),
        color: 0xfff0b0, intensity: 2.6, distance: 15,
      });
    };
    for (let x = 2; x <= 19; x += 3) { put(x, 35); put(x, 40); }
    put(3, 37); put(9, 37); put(15, 37); put(20, 37); put(22, 40);

    const tubes = new THREE.InstancedMesh(
      new THREE.BoxGeometry(3.2, 0.08, 0.5),
      new THREE.MeshBasicMaterial({ color: 0xfff6d0 }),
      strips.length
    );
    const m = new THREE.Matrix4();
    strips.forEach((p, i) => {
      m.makeTranslation(p[0], p[1], p[2]);
      tubes.setMatrixAt(i, m);
    });
    tubes.instanceMatrix.needsUpdate = true;
    tubes.frustumCulled = false;
    this.group.add(tubes);

    // A folding chair, sitting in the middle of nowhere in particular.
    this._addBox(tileX(11) + 1.2, 0.42, tileZ(35) + 1.0, 0.5, 0.06, 0.5, 0x6d5f2c);
    this._addBox(tileX(11) + 1.2, 0.75, tileZ(35) + 1.2, 0.5, 0.7, 0.06, 0x6d5f2c, { solid: false });
  }

  _buildYard() {
    // Perimeter razor-wire fence, inside the concrete wall.
    const fenceMat = new THREE.MeshLambertMaterial({
      map: getTextureXY('fence', 12, 2), transparent: true, alphaTest: 0.35, side: THREE.DoubleSide,
    });
    const fz0 = tileZ(27) - 1.0;
    const fence = new THREE.Mesh(new THREE.PlaneGeometry((45 - 24 + 1) * TILE, 5.0), fenceMat);
    fence.position.set((24 * TILE + 46 * TILE) / 2, 2.5, fz0);
    this.group.add(fence);

    // Two watchtowers - the mounts for CAM-4 and CAM-5.
    for (const [tx, tz] of [[27, 30], [43, 36]]) {
      const bx = tileX(tx), bz = tileZ(tz);
      for (const [dx, dz] of [[-1.4, -1.4], [1.4, -1.4], [-1.4, 1.4], [1.4, 1.4]]) {
        this._addBox(bx + dx, 3.0, bz + dz, 0.4, 6.0, 0.4, 0x4b5155);
      }
      this._addBox(bx, 6.15, bz, 4.0, 0.3, 4.0, 0x5a6165, { map: 'metal' });
      this._addBox(bx, 6.9, bz, 4.2, 1.2, 0.25, 0x4b5155, { solid: false });
      this._addBox(bx, 6.9, bz - 2.0, 4.2, 1.2, 0.25, 0x4b5155, { solid: false });
      // floodlight head
      const head = new THREE.Mesh(
        new THREE.BoxGeometry(0.9, 0.7, 0.5),
        new THREE.MeshBasicMaterial({ color: 0xfff2c8 })
      );
      head.position.set(bx + 1.6, 7.4, bz);
      this.group.add(head);
      this.lightSpots.push({ pos: new THREE.Vector3(bx, 7.0, bz), color: 0xfff0cc, intensity: 6.0, distance: 46 });
    }

    // Floodlights along the perimeter wall so the yard is lit like a yard.
    for (const [fx, fz] of [[25, 28], [35, 28], [44, 28], [25, 38], [35, 39], [44, 38]]) {
      const head = new THREE.Mesh(
        new THREE.BoxGeometry(1.1, 0.8, 0.6),
        new THREE.MeshBasicMaterial({ color: 0xfff2c8 })
      );
      head.position.set(tileX(fx), 7.6, tileZ(fz));
      this.group.add(head);
      this._addBox(tileX(fx), 3.8, tileZ(fz), 0.3, 7.6, 0.3, 0x4b5155, { solid: false });
      this.lightSpots.push({
        pos: new THREE.Vector3(tileX(fx), 7.2, tileZ(fz)),
        color: 0xfff0cc, intensity: 5.0, distance: 40,
      });
    }

    // Basketball hoop and a few benches, so the yard reads as a real place.
    this._addBox(tileX(33), 2.0, tileZ(29), 0.3, 4.0, 0.3, 0x6a7075);
    this._addBox(tileX(33), 3.9, tileZ(29) + 0.7, 2.2, 1.4, 0.12, 0xb9bec0, { solid: false });
    for (const [bx, bz] of [[30, 34], [37, 33], [40, 38]]) {
      this._addBox(tileX(bx), 0.45, tileZ(bz), 3.2, 0.16, 0.8, 0x6b5f4a);
      this._addBox(tileX(bx) - 1.3, 0.22, tileZ(bz), 0.2, 0.45, 0.7, 0x50565a);
      this._addBox(tileX(bx) + 1.3, 0.22, tileZ(bz), 0.2, 0.45, 0.7, 0x50565a);
    }
    // Stacked pallets for cover near the gate.
    for (let i = 0; i < 4; i++) {
      this._addBox(tileX(44) - (i % 2) * 1.6, 0.5 + Math.floor(i / 2) * 1.0, tileZ(30) + (i % 2) * 1.4, 1.5, 1.0, 1.5, 0x5b4a33);
    }
  }

  // ------------------------------------------------------------- lighting
  _buildLightRig() {
    // Fixtures are collected first and drawn as a single instanced batch.
    const fixtures = [];
    for (const a of this.areas) {
      if (a.outdoor) continue;
      if (a.back) continue;   // the backrooms bring their own strip lights
      const stepX = Math.max(1, Math.round((a.x1 - a.x0 + 1) / 3));
      const stepZ = Math.max(1, Math.round((a.z1 - a.z0 + 1) / 3));
      for (let z = a.z0 + Math.floor(stepZ / 2); z <= a.z1; z += Math.max(2, stepZ)) {
        for (let x = a.x0 + Math.floor(stepX / 2); x <= a.x1; x += Math.max(2, stepX)) {
          fixtures.push([tileX(x), a.h - 0.12, tileZ(z)]);
          this.lightSpots.push({
            pos: new THREE.Vector3(tileX(x), a.h - 0.4, tileZ(z)),
            color: a.floor === 'metal' ? 0xd8ecff : 0xffeccb,
            intensity: a.h > 5 ? 3.4 : 2.4,
            distance: a.h > 5 ? 22 : 17,
          });
        }
      }
    }
    if (fixtures.length) {
      const bulbs = new THREE.InstancedMesh(
        new THREE.BoxGeometry(1.6, 0.12, 0.34),
        new THREE.MeshBasicMaterial({ color: 0xdfe6ee }),
        fixtures.length
      );
      const m = new THREE.Matrix4();
      fixtures.forEach((p, i) => {
        m.makeTranslation(p[0], p[1], p[2]);
        bulbs.setMatrixAt(i, m);
      });
      bulbs.instanceMatrix.needsUpdate = true;
      bulbs.frustumCulled = false;
      this.group.add(bulbs);
    }

    // A small pool of real point lights, re-assigned every frame to whichever
    // fixtures are closest to the camera. Keeps the draw calls cheap.
    this.livePool = [];
    for (let i = 0; i < 10; i++) {
      const l = new THREE.PointLight(0xffeccb, 0, 16, 2);
      this.scene.add(l);
      this.livePool.push(l);
    }
    this._lightTimer = 0;
  }

  updateLights(cameraPos, dt) {
    this._lightTimer -= dt;
    if (this._lightTimer > 0) return;
    this._lightTimer = 0.25;
    const scored = [];
    for (const s of this.lightSpots) {
      const d = s.pos.distanceToSquared(cameraPos);
      if (d < 1600) scored.push({ s, d });
    }
    scored.sort((a, b) => a.d - b.d);
    for (let i = 0; i < this.livePool.length; i++) {
      const l = this.livePool[i];
      const hit = scored[i];
      if (!hit) {
        l.intensity = 0;
        continue;
      }
      l.position.copy(hit.s.pos);
      l.color.setHex(hit.s.color);
      l.intensity = hit.s.intensity;
      l.distance = hit.s.distance;
    }
  }

  /** Puts every door, cell gate and secret way back to its closed state. */
  resetSecurity() {
    this.resetSecretDoors();
    this._doorStamp = (this._doorStamp ?? 0) + 1;
    this._flowKey = null;
    for (const door of this.doors) {
      door.locked = true;
      door.opening = false;
      door.t = 0;
      door.mesh.position.y = door.closedY;
      door.lamp.material.color.setHex(0xff2a2a);
      door.box.min.y = 0;
      door.box.max.y = door.closedY * 2;
    }
    for (const gate of this.cellGates) {
      gate.opening = false;
      gate.mesh.visible = true;
      gate.mesh.position.y = gate.y0;
      gate.box.min.y = 0;
      gate.box.max.y = gate.top;
    }
  }

  /** Slide every cell gate up into the ceiling: the blackout that starts the run. */
  openCellGates() {
    for (const gate of this.cellGates) {
      if (gate.opening || !gate.mesh.visible) continue;
      gate.opening = true;
      gate.box.min.y = -200;
      gate.box.max.y = -190;
    }
  }

  updateCellGates(dt) {
    for (const gate of this.cellGates) {
      if (!gate.opening) continue;
      gate.mesh.position.y += dt * 1.6;
      if (gate.mesh.position.y > WALL_H + 2) {
        gate.opening = false;
        gate.mesh.visible = false;
      }
    }
  }
}
