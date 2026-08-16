/**
 * OVERCLOCK - warehouse rendering.
 *
 * Everything repeated is instanced: one draw call for the slabs, one for the
 * crates, one for the target rings. A level never exceeds a few dozen tiles so
 * the whole warehouse costs about six draw calls.
 */

import * as THREE from 'three';

export const TILE = 1.0;
export const STEP = 0.45;
const SLAB = 0.94;
const BOTTOM = -1.6;

const COLOR_BY_PAINT = {
  n: new THREE.Color(0.86, 0.94, 0.97),
  r: new THREE.Color(1.0, 0.34, 0.4),
  g: new THREE.Color(0.36, 1.0, 0.52),
  b: new THREE.Color(0.34, 0.66, 1.0),
};

const LIT_COLOR = new THREE.Color(0.16, 1.0, 0.62);
const UNLIT_COLOR = new THREE.Color(0.9, 0.62, 0.14);

// Module scratch. Never shared between two functions that can nest.
const mat4 = new THREE.Matrix4();
const scratchPos = new THREE.Vector3();
const scratchScale = new THREE.Vector3();
const scratchQuat = new THREE.Quaternion();
const scratchColor = new THREE.Color();

export function createScene(renderer, textures) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a171c);
  scene.fog = new THREE.FogExp2(0x0a171c, 0.024);

  const root = new THREE.Group();
  scene.add(root);

  // ---- lights -----------------------------------------------------------
  const hemi = new THREE.HemisphereLight(0x8fd0dc, 0x16262c, 1.9);
  scene.add(hemi);

  const key = new THREE.DirectionalLight(0xe8fdf5, 2.6);
  key.position.set(6.5, 11, 5);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.near = 1;
  key.shadow.camera.far = 40;
  key.shadow.bias = -0.0016;
  key.shadow.normalBias = 0.03;
  scene.add(key);
  scene.add(key.target);

  const fill = new THREE.DirectionalLight(0x3ae0ad, 0.8);
  fill.position.set(-7, 5, -6);
  scene.add(fill);

  if (renderer) {
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  }

  // ---- static ground ----------------------------------------------------
  const groundMat = new THREE.MeshStandardMaterial({
    map: textures.ground,
    color: 0x28414a,
    roughness: 0.95,
    metalness: 0.0,
  });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), groundMat);
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = BOTTOM - 0.6;
  ground.receiveShadow = false;
  scene.add(ground);

  // ---- reusable geometry / materials ------------------------------------
  const slabGeo = new THREE.BoxGeometry(SLAB, 1, SLAB);
  const slabMat = new THREE.MeshStandardMaterial({
    map: textures.slab,
    roughness: 0.82,
    metalness: 0.05,
  });

  const crateGeo = new THREE.BoxGeometry(SLAB * 0.78, STEP * 0.94, SLAB * 0.78);
  const crateMat = new THREE.MeshStandardMaterial({
    map: textures.crate,
    roughness: 0.9,
    metalness: 0.0,
  });

  const ringGeo = new THREE.PlaneGeometry(SLAB * 0.86, SLAB * 0.86);
  ringGeo.rotateX(-Math.PI / 2);
  const ringMat = new THREE.MeshBasicMaterial({
    map: textures.target,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
  });

  let slabs = null;
  let crates = null;
  let rings = null;
  let edges = null;

  let wh = null;
  let slabTiles = [];
  let crateTiles = [];
  let ringTiles = [];
  let crateCapacity = 1;
  let pulse = 0;

  const api = {
    scene,
    root,
    center: new THREE.Vector3(),
    radius: 4,

    /** Grid cell -> world position of the slab centre (top surface excluded). */
    cellX(x) {
      return (x - (wh.cols - 1) / 2) * TILE;
    },
    cellZ(z) {
      return (z - (wh.rows - 1) / 2) * TILE;
    },
    topY(top) {
      return top * STEP;
    },

    build(warehouse) {
      api.clearMeshes();
      wh = warehouse;

      slabTiles = wh.tiles.filter((t) => t.h >= 0);
      ringTiles = wh.tiles.filter((t) => t.target);
      crateTiles = wh.tiles.slice();

      crateCapacity = Math.max(1, wh.tiles.filter((t) => t.crate).length);

      slabs = new THREE.InstancedMesh(slabGeo, slabMat, Math.max(1, slabTiles.length));
      slabs.castShadow = true;
      slabs.receiveShadow = true;
      slabs.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      root.add(slabs);

      crates = new THREE.InstancedMesh(crateGeo, crateMat, crateCapacity);
      crates.castShadow = true;
      crates.receiveShadow = true;
      crates.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      root.add(crates);

      rings = new THREE.InstancedMesh(ringGeo, ringMat, Math.max(1, ringTiles.length));
      rings.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      rings.frustumCulled = false;
      root.add(rings);

      // thin outline under the whole zone, gives the floating slabs a floor
      const w = wh.cols * TILE + 0.6;
      const d = wh.rows * TILE + 0.6;
      const outline = new THREE.BufferGeometry();
      const hw = w / 2;
      const hd = d / 2;
      outline.setAttribute(
        'position',
        new THREE.Float32BufferAttribute(
          [-hw, 0, -hd, hw, 0, -hd, hw, 0, -hd, hw, 0, hd, hw, 0, hd, -hw, 0, hd, -hw, 0, hd, -hw, 0, -hd],
          3
        )
      );
      edges = new THREE.LineSegments(
        outline,
        new THREE.LineBasicMaterial({ color: 0x21e39a, transparent: true, opacity: 0.3, toneMapped: false })
      );
      edges.position.y = BOTTOM + 0.02;
      root.add(edges);

      // Frame on the diagonal: a one row level would otherwise sit far away
      // just because its long side is short.
      api.center.set(0, (maxTop(wh) * STEP) / 2, 0);
      api.radius = 0.5 * Math.hypot(wh.cols * TILE, wh.rows * TILE) + 1.2;

      // shadow frustum tight around the zone
      const r = Math.max(wh.cols, wh.rows) * TILE * 0.8 + 2.5;
      key.shadow.camera.left = -r;
      key.shadow.camera.right = r;
      key.shadow.camera.top = r;
      key.shadow.camera.bottom = -r;
      key.shadow.camera.updateProjectionMatrix();
      key.position.set(r * 0.7, r * 1.5 + 4, r * 0.6);
      key.target.position.set(0, 0, 0);
      key.target.updateMatrixWorld();

      api.sync();
      return api;
    },

    /** Pushes model state (paint, crates, lit targets) into the instances. */
    sync() {
      if (!wh || !slabs) return;

      for (let i = 0; i < slabTiles.length; i++) {
        const t = slabTiles[i];
        const top = t.h * STEP;
        const height = top - BOTTOM;
        scratchPos.set(api.cellX(t.x), BOTTOM + height / 2, api.cellZ(t.z));
        scratchScale.set(1, height, 1);
        scratchQuat.identity();
        mat4.compose(scratchPos, scratchQuat, scratchScale);
        slabs.setMatrixAt(i, mat4);

        const base = COLOR_BY_PAINT[t.color] || COLOR_BY_PAINT.n;
        // higher slabs get a touch more light so the relief reads from above,
        // and a target slab is darkened into a pad so its additive ring pops
        const lift = (1 + Math.min(0.22, t.h * 0.07)) * (t.target ? 0.5 : 1);
        scratchColor.copy(base).multiplyScalar(lift);
        slabs.setColorAt(i, scratchColor);
      }
      slabs.count = slabTiles.length;
      slabs.instanceMatrix.needsUpdate = true;
      if (slabs.instanceColor) slabs.instanceColor.needsUpdate = true;

      let ci = 0;
      for (const t of crateTiles) {
        if (!t.crate || ci >= crateCapacity) continue;
        const restY = (t.h < 0 ? -1 : t.h) * STEP + (STEP * 0.94) / 2;
        scratchPos.set(api.cellX(t.x), restY, api.cellZ(t.z));
        scratchScale.set(1, 1, 1);
        scratchQuat.identity();
        mat4.compose(scratchPos, scratchQuat, scratchScale);
        crates.setMatrixAt(ci, mat4);
        ci++;
      }
      crates.count = ci;
      crates.instanceMatrix.needsUpdate = true;

      for (let i = 0; i < ringTiles.length; i++) {
        const t = ringTiles[i];
        const top = wh.topOf(t);
        scratchPos.set(api.cellX(t.x), (top === null ? t.h : top) * STEP + 0.012, api.cellZ(t.z));
        scratchScale.set(1, 1, 1);
        scratchQuat.identity();
        mat4.compose(scratchPos, scratchQuat, scratchScale);
        rings.setMatrixAt(i, mat4);
      }
      rings.count = ringTiles.length;
      rings.instanceMatrix.needsUpdate = true;
      api.updatePulse(0);
    },

    /** Unlit targets breathe, lit ones hold steady. Colours only, no matrices. */
    updatePulse(dt) {
      if (!rings || !ringTiles.length) return;
      pulse += dt;
      const wave = 0.55 + 0.45 * Math.sin(pulse * 3.1);
      for (let i = 0; i < ringTiles.length; i++) {
        const t = ringTiles[i];
        if (t.lit) scratchColor.copy(LIT_COLOR).multiplyScalar(1.35);
        else scratchColor.copy(UNLIT_COLOR).multiplyScalar(0.35 + wave * 0.75);
        rings.setColorAt(i, scratchColor);
      }
      if (rings.instanceColor) rings.instanceColor.needsUpdate = true;
    },

    update(dt) {
      api.updatePulse(dt);
    },

    clearMeshes() {
      // Shared geometry and materials live for the whole session; only the
      // instanced wrappers and the per level outline are thrown away here.
      for (const m of [slabs, crates, rings]) {
        if (!m) continue;
        root.remove(m);
        m.dispose();
      }
      if (edges) {
        root.remove(edges);
        edges.geometry.dispose();
        edges.material.dispose();
      }
      slabs = crates = rings = edges = null;
    },

    dispose() {
      api.clearMeshes();
      slabGeo.dispose();
      crateGeo.dispose();
      ringGeo.dispose();
      slabMat.dispose();
      crateMat.dispose();
      ringMat.dispose();
      ground.geometry.dispose();
      groundMat.dispose();
      scene.clear();
    },
  };

  return api;
}

function maxTop(wh) {
  let m = 0;
  for (const t of wh.tiles) if (t.h > m) m = t.h;
  return m;
}
