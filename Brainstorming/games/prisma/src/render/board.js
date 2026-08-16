/**
 * PRISMA - the room, the floor grid and every cell visual.
 *
 * The board owns the scene graph for one level: it diffs the model against the
 * meshes already in the scene and only rebuilds what actually changed, so
 * dropping or rotating a component never touches the other cells.
 */

import * as THREE from 'three';
import { CELL, cellToWorldX, cellToWorldZ } from '../grid.js';

const TILE_FREE = 0x828cc6;
const TILE_BLOCKED = 0x3a3f5e;
const TILE_CHECKER = 0.7;
const ROOM_TINT = 0x0d0b1c;

const _q = new THREE.Quaternion();
const _c = new THREE.Color();
const _m = new THREE.Matrix4();
const _v = new THREE.Vector3();

export function createBoard(scene, renderer, textures, factory) {
  scene.background = new THREE.Color(ROOM_TINT);
  scene.fog = new THREE.FogExp2(ROOM_TINT, 0.03);

  // Metal is lit almost entirely by this probe: without it every mirror renders
  // matte black, a trap this repository has already fallen into twice.
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envRT = pmrem.fromEquirectangular(textures.env);
  scene.environment = envRT.texture;
  pmrem.dispose();
  factory.setEnvironment(envRT.texture);

  const lights = new THREE.Group();
  const hemi = new THREE.HemisphereLight(0x8f7dff, 0x14112a, 1.0);
  const key = new THREE.DirectionalLight(0xdfe4ff, 1.5);
  key.position.set(6, 12, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.near = 1;
  key.shadow.camera.far = 40;
  key.shadow.camera.left = -10;
  key.shadow.camera.right = 10;
  key.shadow.camera.top = 10;
  key.shadow.camera.bottom = -10;
  key.shadow.bias = -0.0012;
  const fillA = new THREE.PointLight(0xff5ce0, 14, 26, 2);
  fillA.position.set(-8, 4, -7);
  const fillB = new THREE.PointLight(0x4cc4ff, 14, 26, 2);
  fillB.position.set(8, 4, 7);
  lights.add(hemi, key, fillA, fillB);
  scene.add(lights);

  const root = new THREE.Group();
  scene.add(root);

  // ---- floor ---------------------------------------------------------------
  const tileGeo = new THREE.BoxGeometry(0.96, 0.12, 0.96);
  const tileMat = new THREE.MeshStandardMaterial({
    map: textures.tile,
    metalness: 0.25,
    roughness: 0.72,
  });
  let tiles = null;

  const roomGeo = new THREE.PlaneGeometry(1, 1);
  // Own copy of the panel texture: the floor stretches it over the whole room
  // and mutating `repeat` on the shared one would shred the wall panels too.
  const roomTex = textures.panel.clone();
  roomTex.needsUpdate = true;
  const roomMat = new THREE.MeshStandardMaterial({
    color: 0x1b1a33,
    map: roomTex,
    metalness: 0.2,
    roughness: 0.9,
  });
  const room = new THREE.Mesh(roomGeo, roomMat);
  room.rotation.x = -Math.PI / 2;
  room.position.y = -0.14;
  room.receiveShadow = true;
  root.add(room);

  // ---- highlights ----------------------------------------------------------
  const hlGeo = new THREE.PlaneGeometry(0.98, 0.98);
  const hlMat = new THREE.MeshBasicMaterial({
    color: 0x66f0ff,
    transparent: true,
    opacity: 0.35,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
  });
  const hover = new THREE.Mesh(hlGeo, hlMat);
  hover.rotation.x = -Math.PI / 2;
  hover.position.y = 0.075;
  hover.visible = false;
  hover.renderOrder = 2;
  root.add(hover);

  const selGeo = new THREE.TorusGeometry(0.46, 0.03, 8, 28);
  const selMat = new THREE.MeshBasicMaterial({
    color: 0xffd36b,
    transparent: true,
    opacity: 0.9,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
  });
  const selection = new THREE.Mesh(selGeo, selMat);
  selection.rotation.x = -Math.PI / 2;
  selection.position.y = 0.09;
  selection.visible = false;
  selection.renderOrder = 2;
  root.add(selection);

  const ghostHolder = new THREE.Group();
  ghostHolder.visible = false;
  root.add(ghostHolder);
  let ghostKey = '';

  // ---- per cell visuals ----------------------------------------------------
  const visuals = new Map(); // cell index -> { obj, sig }
  const spinners = [];
  const billboards = [];
  const targetVisuals = [];

  let grid = null;
  let selectedObj = null;

  function clearVisuals() {
    selectedObj = null;
    for (const entry of visuals.values()) root.remove(entry.obj);
    visuals.clear();
    spinners.length = 0;
    billboards.length = 0;
    targetVisuals.length = 0;
  }

  function registerAnimated(obj) {
    if (obj.userData.spin) spinners.push(obj.userData.spin);
    if (obj.userData.billboards) billboards.push(...obj.userData.billboards);
  }

  function signature(cell) {
    return `${cell.type}:${cell.rot}:${cell.mask}:${cell.dir}`;
  }

  function buildCellVisual(index) {
    const cell = grid.cells[index];
    const x = index % grid.w;
    const y = (index / grid.w) | 0;
    const obj = factory.build(cell);
    if (!obj) return;
    obj.position.set(cellToWorldX(grid, x), 0, cellToWorldZ(grid, y));
    root.add(obj);
    visuals.set(index, { obj, sig: signature(cell) });
    registerAnimated(obj);
    trackTarget(index, obj);
  }

  /** Targets keep their model index so lighting them up never searches. */
  function trackTarget(index, obj) {
    if (grid.cells[index].type !== CELL.TARGET) return;
    const x = index % grid.w;
    const y = (index / grid.w) | 0;
    const model = grid.targets.find((t) => t.x === x && t.y === y);
    if (model) targetVisuals.push({ obj, index: model.index });
  }

  function setGrid(nextGrid) {
    grid = nextGrid;
    clearVisuals();

    if (tiles) {
      root.remove(tiles);
      tiles.dispose();
    }
    const count = grid.w * grid.h;
    tiles = new THREE.InstancedMesh(tileGeo, tileMat, count);
    tiles.receiveShadow = true;
    tiles.frustumCulled = false;
    for (let y = 0; y < grid.h; y++) {
      for (let x = 0; x < grid.w; x++) {
        const i = y * grid.w + x;
        _v.set(cellToWorldX(grid, x), 0, cellToWorldZ(grid, y));
        _m.makeTranslation(_v.x, _v.y, _v.z);
        tiles.setMatrixAt(i, _m);
        const blocked = grid.cells[i].type !== CELL.EMPTY;
        _c.setHex(blocked ? TILE_BLOCKED : TILE_FREE);
        // A faint checker keeps the grid readable from a shallow camera angle.
        if ((x + y) % 2 === 0) _c.multiplyScalar(TILE_CHECKER);
        tiles.setColorAt(i, _c);
      }
    }
    tiles.instanceMatrix.needsUpdate = true;
    if (tiles.instanceColor) tiles.instanceColor.needsUpdate = true;
    root.add(tiles);

    room.scale.set(grid.w + 26, grid.h + 26, 1);
    roomTex.repeat.set((grid.w + 26) / 3, (grid.h + 26) / 3);

    for (let i = 0; i < count; i++) buildCellVisual(i);

    const span = Math.max(grid.w, grid.h);
    key.shadow.camera.left = -span;
    key.shadow.camera.right = span;
    key.shadow.camera.top = span;
    key.shadow.camera.bottom = -span;
    key.shadow.camera.updateProjectionMatrix();
    fillA.position.set(-grid.w * 0.7, 4.5, -grid.h * 0.7);
    fillB.position.set(grid.w * 0.7, 4.5, grid.h * 0.7);
  }

  /** Rebuilds only the cells whose model record changed. */
  function refresh() {
    if (!grid) return;
    let structuralChange = false;
    for (let i = 0; i < grid.cells.length; i++) {
      const cell = grid.cells[i];
      const entry = visuals.get(i);
      const sig = signature(cell);
      if (entry && entry.sig === sig) continue;
      if (entry) {
        if (entry.obj === selectedObj) selectedObj = null;
        root.remove(entry.obj);
        visuals.delete(i);
        structuralChange = true;
      }
      if (cell.type !== CELL.EMPTY) {
        buildCellVisual(i);
        structuralChange = true;
      }
      if (tiles) {
        _c.setHex(cell.type !== CELL.EMPTY ? TILE_BLOCKED : TILE_FREE);
        const x = i % grid.w;
        const y = (i / grid.w) | 0;
        if ((x + y) % 2 === 0) _c.multiplyScalar(TILE_CHECKER);
        tiles.setColorAt(i, _c);
      }
    }
    if (structuralChange) {
      // The animated lists reference objects that may have just been removed.
      spinners.length = 0;
      billboards.length = 0;
      targetVisuals.length = 0;
      for (const [index, entry] of visuals) {
        registerAnimated(entry.obj);
        trackTarget(index, entry.obj);
      }
    }
    if (tiles && tiles.instanceColor) tiles.instanceColor.needsUpdate = true;
  }

  /** Switches target lenses on or off from a solver result. */
  function setTargetStates(res) {
    if (!grid) return;
    for (const t of targetVisuals) {
      const lit = res.targetLit[t.index] === 1;
      const data = t.obj.userData;
      data.litTarget = lit;
      if (data.lens) data.lens.material = lit ? data.lensOn : data.lensOff;
    }
  }

  function setHover(x, y, valid) {
    if (x === null || !grid) {
      hover.visible = false;
      ghostHolder.visible = false;
      return;
    }
    hover.visible = true;
    hover.position.set(cellToWorldX(grid, x), 0.075, cellToWorldZ(grid, y));
    hlMat.color.setHex(valid ? 0x66f0ff : 0xff5a6a);
    ghostHolder.position.copy(hover.position).setY(0);
  }

  function setGhost(kind, rot, visible) {
    if (!visible || !kind) {
      ghostHolder.visible = false;
      return;
    }
    const wanted = `${kind}:${rot}`;
    if (wanted !== ghostKey) {
      ghostHolder.clear();
      const g = factory.buildKind(kind, rot, true);
      if (g) ghostHolder.add(g);
      ghostKey = wanted;
    }
    ghostHolder.visible = true;
  }

  function releaseSelected() {
    if (!selectedObj) return;
    selectedObj.position.y = 0;
    selectedObj.scale.setScalar(1);
    selectedObj = null;
  }

  function setSelection(x, y) {
    releaseSelected();
    if (x === null || !grid) {
      selection.visible = false;
      return;
    }
    selection.visible = true;
    selection.position.set(cellToWorldX(grid, x), 0.09, cellToWorldZ(grid, y));
    const entry = visuals.get(y * grid.w + x);
    if (entry && !grid.cells[y * grid.w + x].fixed) selectedObj = entry.obj;
  }

  function update(dt, camera, time) {
    for (const s of spinners) s.rotation.z += dt * 0.7;
    camera.getWorldQuaternion(_q);
    for (const b of billboards) b.quaternion.copy(_q);
    selection.rotation.z += dt * 1.6;
    hlMat.opacity = 0.24 + 0.12 * Math.sin(time * 4.5);
    if (selectedObj) {
      // A slow lift, never a spin: on a mirror the yaw carries the orientation
      // and turning it would lie about which face reflects.
      selectedObj.position.y = 0.055 + 0.025 * Math.sin(time * 3.2);
      selectedObj.scale.setScalar(1.05);
    }
    for (const t of targetVisuals) {
      const data = t.obj.userData;
      if (!data.flare) continue;
      const target = data.litTarget ? 1.5 + 0.22 * Math.sin(time * 5) : 0.25;
      const s = data.flare.scale.x + (target - data.flare.scale.x) * Math.min(1, dt * 7);
      data.flare.scale.setScalar(s);
    }
  }

  function dispose() {
    clearVisuals();
    if (tiles) {
      root.remove(tiles);
      tiles.dispose();
      tiles = null;
    }
    scene.remove(root, lights);
    tileGeo.dispose();
    tileMat.dispose();
    roomGeo.dispose();
    roomMat.dispose();
    roomTex.dispose();
    hlGeo.dispose();
    hlMat.dispose();
    selGeo.dispose();
    selMat.dispose();
    envRT.dispose();
    scene.environment = null;
  }

  return { setGrid, refresh, setTargetStates, setHover, setGhost, setSelection, update, dispose, root };
}
