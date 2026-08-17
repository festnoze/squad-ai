// Builds the visible geometry for one level's maze: walls, floor, ceiling,
// fluorescent tubes, doors, the exit sign and pickable items. Pure three.js,
// consumes the plain-data maze produced by src/maze.js.
import * as THREE from 'three';
import { TILE, TILE_SIZE, tileToWorldCenter } from '../maze.js';
import { lerpColor } from '../textures.js';
import { THEMES } from '../levels.js';

const _dummy = new THREE.Object3D();
const _v = new THREE.Vector3();

function isWalkableStatic(t) {
  return t === TILE.FLOOR || t === TILE.DOOR || t === TILE.EXIT;
}

function keyOf(x, y) { return `${x},${y}`; }

export function buildMazeScene(scene, maze, levelDef, theme, shared) {
  const group = new THREE.Group();
  group.name = `level-${levelDef.id}`;
  scene.add(group);

  const wallHeight = theme.ceilHeight;
  const tex = shared.themes[levelDef.theme];

  const wallMat = new THREE.MeshStandardMaterial({ map: tex.wall, color: 0xffffff, roughness: 0.92, metalness: 0.02 });
  const floorMat = new THREE.MeshStandardMaterial({ map: tex.floor, color: 0xffffff, roughness: 0.95, metalness: 0.0 });
  const ceilMat = new THREE.MeshStandardMaterial({ map: tex.ceiling, color: 0xffffff, roughness: 1, metalness: 0 });

  // ---- collect visible walls + floor/ceiling tiles ----
  const wallCells = [];
  const floorCells = [];
  for (let y = 0; y < maze.height; y++) {
    for (let x = 0; x < maze.width; x++) {
      const t = maze.tiles[y * maze.width + x];
      if (t === TILE.WALL) {
        const n = isWalkableStatic(maze.tiles[y * maze.width + Math.max(0, x - 1)]) ||
          isWalkableStatic(maze.tiles[y * maze.width + Math.min(maze.width - 1, x + 1)]) ||
          (y > 0 && isWalkableStatic(maze.tiles[(y - 1) * maze.width + x])) ||
          (y < maze.height - 1 && isWalkableStatic(maze.tiles[(y + 1) * maze.width + x]));
        if (n) wallCells.push({ x, y });
      } else {
        floorCells.push({ x, y, t });
      }
    }
  }

  const wallGeo = new THREE.BoxGeometry(TILE_SIZE, wallHeight, TILE_SIZE);
  const wallMesh = new THREE.InstancedMesh(wallGeo, wallMat, Math.max(1, wallCells.length));
  wallCells.forEach((c, i) => {
    const w = tileToWorldCenter(c.x, c.y);
    _dummy.position.set(w.x, wallHeight / 2, w.z);
    _dummy.rotation.set(0, 0, 0);
    _dummy.updateMatrix();
    wallMesh.setMatrixAt(i, _dummy.matrix);
  });
  wallMesh.instanceMatrix.needsUpdate = true;
  wallMesh.count = wallCells.length;
  group.add(wallMesh);

  const floorGeo = new THREE.PlaneGeometry(TILE_SIZE, TILE_SIZE);
  floorGeo.rotateX(-Math.PI / 2);
  const floorMesh = new THREE.InstancedMesh(floorGeo, floorMat, Math.max(1, floorCells.length));
  const ceilGeo = new THREE.PlaneGeometry(TILE_SIZE, TILE_SIZE);
  ceilGeo.rotateX(Math.PI / 2);
  const ceilMesh = new THREE.InstancedMesh(ceilGeo, ceilMat, Math.max(1, floorCells.length));
  floorCells.forEach((c, i) => {
    const w = tileToWorldCenter(c.x, c.y);
    _dummy.position.set(w.x, 0, w.z);
    _dummy.rotation.set(0, 0, 0);
    _dummy.updateMatrix();
    floorMesh.setMatrixAt(i, _dummy.matrix);
    _dummy.position.set(w.x, wallHeight, w.z);
    _dummy.updateMatrix();
    ceilMesh.setMatrixAt(i, _dummy.matrix);
  });
  floorMesh.instanceMatrix.needsUpdate = true;
  ceilMesh.instanceMatrix.needsUpdate = true;
  group.add(floorMesh);
  group.add(ceilMesh);

  // ---- optional still-water plane for poolrooms ----
  let waterMesh = null;
  if (theme.water) {
    const w = maze.width * TILE_SIZE;
    const h = maze.height * TILE_SIZE;
    const waterMat = new THREE.MeshStandardMaterial({
      map: shared.water, color: 0xbfe4ec, roughness: 0.12, metalness: 0.05,
      transparent: true, opacity: 0.55, depthWrite: false,
    });
    waterMesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), waterMat);
    waterMesh.rotation.x = -Math.PI / 2;
    waterMesh.position.set(w / 2, 0.03, h / 2);
    group.add(waterMesh);
  }

  // ---- fluorescent tubes: one per room, plain emissive-look plane (no per-tube light) ----
  const tubeTex = levelDef.theme === 'pipes' ? shared.tubeRed : levelDef.theme === 'electrical' ? shared.tubeBlue : shared.tube;
  const tubeMat = new THREE.MeshBasicMaterial({ map: tubeTex, transparent: true, depthWrite: false });
  const tubes = [];
  if (levelDef.theme !== 'dark') {
    for (const r of maze.rooms) {
      const long = r.w >= r.h;
      const len = (long ? r.w : r.h) * TILE_SIZE * 0.6;
      const geo = new THREE.PlaneGeometry(len, 0.5);
      geo.rotateX(Math.PI / 2);
      if (!long) geo.rotateY(Math.PI / 2);
      const mesh = new THREE.Mesh(geo, tubeMat.clone());
      const w = tileToWorldCenter(r.cx, r.cy);
      mesh.position.set(w.x, wallHeight - 0.05, w.z);
      group.add(mesh);
      tubes.push({ mesh, timer: 0.5 + Math.random() * 6, flickering: false, flickerT: 0 });
    }
  }

  // ---- doors: individually pivoted so they can swing open ----
  const doors = [];
  const openDoors = new Set();
  for (const d of maze.doors) {
    const pivot = new THREE.Group();
    const w = tileToWorldCenter(d.x, d.y);
    // hinge sits at one edge of the tile; orientation follows whichever axis the corridor runs.
    // A PlaneGeometry faces +Z unrotated, which blocks travel along Z: that is exactly the
    // leaf a NON-horizontal (north/south) passage needs, so horizontalPassage (an east/west
    // passage, blocked along X) is the one that needs the +90 degree turn.
    const horizontalPassage = isWalkableStatic(maze.tiles[d.y * maze.width + Math.max(0, d.x - 1)]) ||
      isWalkableStatic(maze.tiles[d.y * maze.width + Math.min(maze.width - 1, d.x + 1)]);
    pivot.position.set(w.x, 0, w.z);
    pivot.rotation.y = horizontalPassage ? Math.PI / 2 : 0;

    const leafGeo = new THREE.PlaneGeometry(TILE_SIZE * 0.85, wallHeight * 0.92);
    const leafMat = new THREE.MeshStandardMaterial({ map: shared.door, roughness: 0.8, metalness: 0.15, side: THREE.DoubleSide });
    const leaf = new THREE.Mesh(leafGeo, leafMat);
    leaf.position.set(TILE_SIZE * 0.42, wallHeight * 0.46, 0); // hinge at local origin, leaf offset to the side
    pivot.add(leaf);
    group.add(pivot);
    doors.push({ x: d.x, y: d.y, pivot, openAngle: 0, targetAngle: 0, horizontalPassage });
  }

  // ---- exit sign: a bright vertical plane, unmistakably different from decor ----
  const exitWorld = tileToWorldCenter(maze.exitPos.x, maze.exitPos.y);
  const exitMat = new THREE.MeshBasicMaterial({ map: shared.exit, transparent: true });
  const exitSign = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 1.1), exitMat);
  exitSign.position.set(exitWorld.x, 1.7, exitWorld.z);
  group.add(exitSign);

  // ---- items ----
  const items = maze.items.map((it) => {
    const w = tileToWorldCenter(it.x, it.y);
    let mesh;
    if (it.type === 'battery') {
      mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.28, 10), new THREE.MeshStandardMaterial({ color: 0xffd23c, roughness: 0.4, metalness: 0.3 }));
      mesh.position.set(w.x, 0.3, w.z);
    } else {
      mesh = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.03, 0.32), new THREE.MeshStandardMaterial({ color: 0xd8cfa0, roughness: 0.9 }));
      mesh.position.set(w.x, 0.12, w.z);
    }
    group.add(mesh);
    return { x: it.x, y: it.y, type: it.type, taken: false, mesh, baseY: mesh.position.y, spin: Math.random() * Math.PI * 2 };
  });

  // Colour target for the final level's gradient: the numeric palette (not the canvas texture set).
  const gradientBase = theme.gradientTo ? THEMES[theme.gradientTo] : null;

  return {
    group, wallMesh, floorMesh, ceilMesh, waterMesh, doors, tubes, items,
    openDoors,
    exitWorld,
    startWorld: tileToWorldCenter(maze.startPos.x, maze.startPos.y),

    /**
     * Opens the closest door within `range` of (px,pz), if any. Returns true iff a
     * door existed there. Corridors are one tile wide, so a player blocked by a
     * closed door is always stopped half a tile (1.5m) plus their own collision
     * radius (0.36m) from the door's tile centre: about 1.86m, dead on. The range
     * default has to clear that with margin (players approaching from an angled
     * room entrance, not a straight corridor, land a little further out still),
     * or a closed door becomes permanently out of interact reach the instant it
     * actually blocks you (the exact bug this comment is here to prevent regressing).
     */
    tryOpenDoor(px, pz, range = 2.3) {
      let best = null;
      let bestD = range * range;
      for (const d of this.doors) {
        const w = tileToWorldCenter(d.x, d.y);
        const dd = (w.x - px) ** 2 + (w.z - pz) ** 2;
        if (dd < bestD) { bestD = dd; best = d; }
      }
      if (!best) return false;
      best.targetAngle = best.targetAngle > 0.1 ? 0 : Math.PI * 0.62;
      if (best.targetAngle > 0.1) this.openDoors.add(keyOf(best.x, best.y));
      else this.openDoors.delete(keyOf(best.x, best.y));
      return true;
    },

    /** Picks up the closest un-taken item within range, returns it (or null). */
    tryPickup(px, pz, range = 1.4) {
      for (const it of this.items) {
        if (it.taken) continue;
        const w = tileToWorldCenter(it.x, it.y);
        if ((w.x - px) ** 2 + (w.z - pz) ** 2 < range * range) {
          it.taken = true;
          it.mesh.visible = false;
          return it;
        }
      }
      return null;
    },

    update(dt, progress01) {
      for (const t of this.tubes) {
        if (t.flickering) {
          t.flickerT -= dt;
          t.mesh.material.opacity = 0.15 + Math.random() * 0.15;
          if (t.flickerT <= 0) { t.flickering = false; t.mesh.material.opacity = 1; }
        } else {
          t.timer -= dt;
          if (t.timer <= 0) { t.flickering = true; t.flickerT = 0.12 + Math.random() * 0.18; t.timer = 5 + Math.random() * 9; }
        }
      }
      for (const d of this.doors) {
        if (Math.abs(d.openAngle - d.targetAngle) > 0.01) {
          d.openAngle += Math.sign(d.targetAngle - d.openAngle) * Math.min(Math.abs(d.targetAngle - d.openAngle), dt * 2.6);
          d.pivot.rotation.y = (d.horizontalPassage ? Math.PI / 2 : 0) + d.openAngle;
        }
      }
      for (const it of this.items) {
        if (it.taken) continue;
        it.spin += dt * 1.4;
        it.mesh.rotation.y = it.spin;
        it.mesh.position.y = it.baseY + Math.sin(it.spin * 1.7) * 0.05;
      }
      if (this.waterMesh) this.waterMesh.material.map.offset.y = (this.waterMesh.material.map.offset.y + dt * 0.004) % 1;

      if (gradientBase && progress01 !== undefined) {
        wallMat.color.setHex(lerpColor(theme.wall, gradientBase.wall, progress01));
        floorMat.color.setHex(lerpColor(theme.floor, gradientBase.floor, progress01));
        ceilMat.color.setHex(lerpColor(theme.ceiling, gradientBase.ceiling, progress01));
      }
    },

    dispose() {
      group.traverse((o) => {
        if (o.isMesh && o.material && o.material !== wallMat && o.material !== floorMat && o.material !== ceilMat) {
          if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose());
          else o.material.dispose();
        }
      });
      wallGeo.dispose(); floorGeo.dispose(); ceilGeo.dispose();
      wallMat.dispose(); floorMat.dispose(); ceilMat.dispose();
      scene.remove(group);
    },
  };
}
