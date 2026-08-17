/**
 * MAREE - water planes, ice planes and the wood crates that ride them.
 *
 * Every basin gets one rippling, semi-transparent plane sized to its own
 * column footprint; height follows `basin.visual`, the smoothed value
 * water.js animates toward the logical level, so a raise or lower always
 * reads as a steady half-second rise rather than a snap. Ice planes are
 * created once, the moment a level actually freezes, and are never removed.
 */

import * as THREE from 'three';
import { CELL, PALETTE } from '../config.js';
import { colIndex, NO_BASIN } from '../world.js';

const VERT = `
uniform float uTime;
varying vec2 vUv;
varying float vRipple;
void main() {
  vUv = uv;
  vec3 p = position;
  float r = sin((position.x + uTime * 1.3) * 1.6) * 0.03 + cos((position.z - uTime * 1.1) * 1.9) * 0.03;
  p.y += r;
  vRipple = r;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}
`;

const FRAG = `
uniform vec3 uShallow;
uniform vec3 uDeep;
uniform float uOpacity;
varying vec2 vUv;
varying float vRipple;
void main() {
  float d = clamp(length(vUv - 0.5) * 1.4, 0.0, 1.0);
  vec3 col = mix(uShallow, uDeep, d);
  col += vRipple * 0.8;
  gl_FragColor = vec4(col, uOpacity);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

export function createWaterObjects(textures) {
  const group = new THREE.Group();
  const iceGroup = new THREE.Group();
  const woodGroup = new THREE.Group();
  group.add(iceGroup, woodGroup);

  let basinMeshes = [];
  let woodMeshes = [];
  let renderedIce = [];
  const owned = [];
  let planeGeom = null;

  function clear() {
    while (group.children.length) group.remove(group.children[0]);
    group.add(iceGroup, woodGroup);
    while (iceGroup.children.length) iceGroup.remove(iceGroup.children[0]);
    while (woodGroup.children.length) woodGroup.remove(woodGroup.children[0]);
    for (const o of owned) {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    }
    owned.length = 0;
    basinMeshes = [];
    woodMeshes = [];
    renderedIce = [];
  }

  function footprint(state, basinIndex) {
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    for (let z = 0; z < state.d; z++) {
      for (let x = 0; x < state.w; x++) {
        if (state.basinOf[colIndex(state, x, z)] === basinIndex) {
          minX = Math.min(minX, x);
          maxX = Math.max(maxX, x);
          minZ = Math.min(minZ, z);
          maxZ = Math.max(maxZ, z);
        }
      }
    }
    return { minX, maxX, minZ, maxZ };
  }

  function worldOf(state, x, z) {
    return {
      x: (x - (state.w - 1) / 2) * CELL,
      z: (z - (state.d - 1) / 2) * CELL,
    };
  }

  function build(state) {
    clear();
    planeGeom = new THREE.PlaneGeometry(1, 1, 12, 12);
    planeGeom.rotateX(-Math.PI / 2);
    owned.push(planeGeom);

    for (let i = 0; i < state.basins.length; i++) {
      const fp = footprint(state, i);
      if (!isFinite(fp.minX)) {
        basinMeshes.push(null);
        renderedIce.push(new Set());
        continue;
      }
      const w = (fp.maxX - fp.minX + 1) * CELL;
      const d = (fp.maxZ - fp.minZ + 1) * CELL;
      const c0 = worldOf(state, fp.minX, fp.minZ);
      const c1 = worldOf(state, fp.maxX, fp.maxZ);
      const cx = (c0.x + c1.x) / 2;
      const cz = (c0.z + c1.z) / 2;

      const mat = new THREE.ShaderMaterial({
        uniforms: {
          uTime: { value: 0 },
          uShallow: { value: new THREE.Color(PALETTE.waterShallow) },
          uDeep: { value: new THREE.Color(PALETTE.waterDeep) },
          uOpacity: { value: 0.78 },
        },
        vertexShader: VERT,
        fragmentShader: FRAG,
        transparent: true,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      owned.push(mat);
      const mesh = new THREE.Mesh(planeGeom, mat);
      mesh.scale.set(w * 0.98, 1, d * 0.98);
      mesh.position.set(cx, 0, cz);
      mesh.userData = { type: 'water', basin: i };
      mesh.visible = state.basins[i].level >= 0;
      group.add(mesh);
      basinMeshes.push(mesh);
      renderedIce.push(new Set());
    }

    const woodGeom = new THREE.BoxGeometry(CELL * 0.82, CELL * 0.62, CELL * 0.82);
    owned.push(woodGeom);
    for (const w of state.wood) {
      const mat = new THREE.MeshStandardMaterial({ map: textures.wood, roughness: 0.85 });
      owned.push(mat);
      const mesh = new THREE.Mesh(woodGeom, mat);
      const p = worldOf(state, w.x, w.z);
      mesh.position.set(p.x, 0, p.z);
      mesh.castShadow = true;
      woodGroup.add(mesh);
      woodMeshes.push({ mesh, def: w });
    }

    return { basinMeshes };
  }

  function addIcePlane(state, basinIndex, level) {
    const fp = footprint(state, basinIndex);
    if (!isFinite(fp.minX)) return;
    const w = (fp.maxX - fp.minX + 1) * CELL;
    const d = (fp.maxZ - fp.minZ + 1) * CELL;
    const c0 = worldOf(state, fp.minX, fp.minZ);
    const c1 = worldOf(state, fp.maxX, fp.maxZ);
    const geom = new THREE.PlaneGeometry(w * 0.98, d * 0.98);
    geom.rotateX(-Math.PI / 2);
    const mat = new THREE.MeshStandardMaterial({
      color: PALETTE.ice,
      transparent: true,
      opacity: 0.82,
      roughness: 0.25,
      metalness: 0.05,
    });
    owned.push(geom, mat);
    const mesh = new THREE.Mesh(geom, mat);
    mesh.position.set((c0.x + c1.x) / 2, level * CELL + 0.03 * CELL, (c0.z + c1.z) / 2);
    mesh.receiveShadow = true;
    iceGroup.add(mesh);
  }

  function update(state, dt, elapsed) {
    for (let i = 0; i < basinMeshes.length; i++) {
      const mesh = basinMeshes[i];
      if (!mesh) continue;
      const basin = state.basins[i];
      mesh.visible = basin.visual >= -0.4;
      mesh.position.y = basin.visual * CELL + 0.06 * CELL;
      mesh.material.uniforms.uTime.value = elapsed;

      for (const lvl of basin.iceLevels) {
        if (!renderedIce[i].has(lvl)) {
          renderedIce[i].add(lvl);
          addIcePlane(state, i, lvl);
        }
      }
    }
  }

  function updateWood(state) {
    for (const entry of woodMeshes) {
      // Wood always tracks the smoothed visual level of its own basin.
      const i = entry.basinIndex;
      const basin = state.basins[i];
      const y = Math.max(entry.def.homeFloor, basin.visual);
      entry.mesh.position.y = y * CELL;
    }
  }

  return {
    group,
    build(state) {
      const result = build(state);
      for (const entry of woodMeshes) {
        entry.basinIndex = state.basinOf[colIndex(state, entry.def.x, entry.def.z)];
      }
      return result;
    },
    update(state, dt, elapsed) {
      update(state, dt, elapsed);
      updateWood(state);
    },
    dispose() {
      clear();
    },
  };
}
