/**
 * PARADOXE - arena rendering.
 *
 * Builds the static geometry of one level with InstancedMesh (one draw call per
 * block class) and keeps the handful of animated props (doors, buttons, plates,
 * teleporters, exit, crates, collapsing tiles) as individual meshes.
 *
 * Readability rule: walls are drawn 2.2 tall while the simulation treats them
 * as 3.6. The extra 1.4 is invisible headroom that stops a player from landing
 * on top of a wall after a jump off a 2 high block; drawing it would only wall
 * the camera in for no gameplay gain.
 */

import * as THREE from 'three';
import { PALETTE, SIM, WORLD } from '../config.js';

const WALL_VISUAL = WORLD.wallVisual;

const boxGeo = new THREE.BoxGeometry(1, 1, 1);
const mat4 = new THREE.Matrix4();
const vec3 = new THREE.Vector3();
const quatId = new THREE.Quaternion();
const scaleTmp = new THREE.Vector3();

function tileUv(geo, times) {
  const uv = geo.attributes.uv;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * times, uv.getY(i) * times);
  uv.needsUpdate = true;
}

function countCells(level, predicate) {
  let n = 0;
  for (let i = 0; i < level.w * level.h; i++) if (predicate(level.height[i], i)) n++;
  return n;
}

export function createArena(level, textures, renderer) {
  const scene = new THREE.Scene();
  scene.background = textures.sky;
  scene.fog = new THREE.FogExp2(PALETTE.fog, 0.013);

  let envTexture = null;
  if (renderer) {
    const pmrem = new THREE.PMREMGenerator(renderer);
    pmrem.compileEquirectangularShader();
    envTexture = pmrem.fromEquirectangular(textures.sky).texture;
    scene.environment = envTexture;
    // Low on purpose: the sky is the brightest thing in the PMREM and a high
    // value flattens every surface into the same pale teal.
    scene.environmentIntensity = 0.18;
    pmrem.dispose();
  }

  const group = new THREE.Group();
  scene.add(group);

  const cx = level.w * 0.5;
  const cz = level.h * 0.5;

  // ---------------------------------------------------------------- lights
  const hemi = new THREE.HemisphereLight(0x6ea3c2, 0x101d26, 0.85);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xd6ecff, 2.1);
  sun.position.set(cx + 9, 20, cz + 7);
  sun.target.position.set(cx, 0, cz);
  sun.castShadow = true;
  const span = Math.max(level.w, level.h) * 0.72 + 3;
  sun.shadow.camera.left = -span;
  sun.shadow.camera.right = span;
  sun.shadow.camera.top = span;
  sun.shadow.camera.bottom = -span;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 60;
  sun.shadow.mapSize.set(1024, 1024);
  // normalBias is what stops a large flat floor from shadowing itself; a plain
  // depth bias big enough to do the same job detaches every shadow from its
  // caster instead.
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 0.04;
  scene.add(sun);
  scene.add(sun.target);

  const rim = new THREE.DirectionalLight(0x3f7ac0, 0.28);
  rim.position.set(cx - 10, 8, cz - 9);
  scene.add(rim);

  // ---------------------------------------------------------------- helpers
  const disposables = [];
  function track(obj) {
    disposables.push(obj);
    return obj;
  }

  function makeInstanced(geo, mat, count) {
    const m = new THREE.InstancedMesh(geo, mat, Math.max(count, 1));
    m.count = count;
    m.castShadow = true;
    m.receiveShadow = true;
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    track(geo);
    track(mat);
    return m;
  }

  function setInstance(mesh, i, x, y, z, sx, sy, sz) {
    vec3.set(x, y, z);
    scaleTmp.set(sx, sy, sz);
    mat4.compose(vec3, quatId, scaleTmp);
    mesh.setMatrixAt(i, mat4);
  }

  // ---------------------------------------------------------------- floors
  const floorGeo = boxGeo.clone();
  const floorMat = new THREE.MeshStandardMaterial({
    map: textures.floor,
    color: 0xffffff,
    roughness: 0.86,
    metalness: 0.04,
  });
  const isPlainFloor = (hv, i) => hv === 0 && !level.fragile[i];
  const floorMesh = makeInstanced(floorGeo, floorMat, countCells(level, isPlainFloor));
  floorMesh.castShadow = false;
  {
    let n = 0;
    for (let z = 0; z < level.h; z++) {
      for (let x = 0; x < level.w; x++) {
        const i = z * level.w + x;
        if (!isPlainFloor(level.height[i], i)) continue;
        setInstance(floorMesh, n++, x + 0.5, -0.13, z + 0.5, 1, 0.26, 1);
      }
    }
  }
  floorMesh.instanceMatrix.needsUpdate = true;
  group.add(floorMesh);

  // ---------------------------------------------------------------- blocks
  const blockMat = new THREE.MeshStandardMaterial({
    map: textures.block,
    color: 0xffffff,
    roughness: 0.72,
    metalness: 0.1,
  });
  const block1Geo = boxGeo.clone();
  const block1 = makeInstanced(block1Geo, blockMat, countCells(level, (hv) => hv === 1));
  const block2Geo = boxGeo.clone();
  tileUv(block2Geo, 2);
  const block2 = makeInstanced(block2Geo, blockMat, countCells(level, (hv) => hv === 2));
  {
    let n1 = 0;
    let n2 = 0;
    for (let z = 0; z < level.h; z++) {
      for (let x = 0; x < level.w; x++) {
        const hv = level.height[z * level.w + x];
        if (hv === 1) setInstance(block1, n1++, x + 0.5, 0.5, z + 0.5, 1, 1, 1);
        else if (hv === 2) setInstance(block2, n2++, x + 0.5, 1, z + 0.5, 1, 2, 1);
      }
    }
  }
  block1.instanceMatrix.needsUpdate = true;
  block2.instanceMatrix.needsUpdate = true;
  group.add(block1);
  group.add(block2);

  // ---------------------------------------------------------------- walls
  const wallGeo = boxGeo.clone();
  tileUv(wallGeo, 2);
  const wallMat = new THREE.MeshStandardMaterial({
    map: textures.wall,
    color: 0xffffff,
    roughness: 0.9,
    metalness: 0.06,
  });
  const wallMesh = makeInstanced(wallGeo, wallMat, countCells(level, (hv) => hv === 3));
  {
    let n = 0;
    for (let z = 0; z < level.h; z++) {
      for (let x = 0; x < level.w; x++) {
        if (level.height[z * level.w + x] !== 3) continue;
        setInstance(wallMesh, n++, x + 0.5, WALL_VISUAL * 0.5, z + 0.5, 1, WALL_VISUAL, 1);
      }
    }
  }
  wallMesh.instanceMatrix.needsUpdate = true;
  group.add(wallMesh);

  // Glowing cap so the top of a wall reads as "you cannot go there".
  const capGeo = new THREE.BoxGeometry(1.02, 0.07, 1.02);
  const capMat = new THREE.MeshBasicMaterial({ color: PALETTE.accent, transparent: true, opacity: 0.42 });
  const capMesh = makeInstanced(capGeo, capMat, wallMesh.count);
  capMesh.castShadow = false;
  capMesh.receiveShadow = false;
  {
    let n = 0;
    for (let z = 0; z < level.h; z++) {
      for (let x = 0; x < level.w; x++) {
        if (level.height[z * level.w + x] !== 3) continue;
        setInstance(capMesh, n++, x + 0.5, WALL_VISUAL + 0.02, z + 0.5, 1, 1, 1);
      }
    }
  }
  capMesh.instanceMatrix.needsUpdate = true;
  group.add(capMesh);

  // ---------------------------------------------------------------- fragile
  const fragileTiles = [];
  {
    const fmat = new THREE.MeshStandardMaterial({
      map: textures.fragile,
      color: 0xffffff,
      roughness: 0.95,
      metalness: 0,
      emissive: 0x223038,
      emissiveIntensity: 0.6,
    });
    track(fmat);
    for (let z = 0; z < level.h; z++) {
      for (let x = 0; x < level.w; x++) {
        const i = z * level.w + x;
        if (!level.fragile[i]) continue;
        const geo = boxGeo.clone();
        track(geo);
        const mesh = new THREE.Mesh(geo, fmat);
        mesh.scale.set(0.98, 0.26, 0.98);
        mesh.position.set(x + 0.5, -0.13, z + 0.5);
        mesh.receiveShadow = true;
        group.add(mesh);
        fragileTiles.push({ idx: i, mesh, fall: 0, baseY: -0.13 });
      }
    }
  }

  // ---------------------------------------------------------------- doors
  const doorMeshes = [];
  {
    const geo = new THREE.BoxGeometry(0.98, WORLD.doorHeight, 0.98);
    track(geo);
    for (let i = 0; i < level.doors.length; i++) {
      const d = level.doors[i];
      const mat = new THREE.MeshStandardMaterial({
        color: PALETTE.door,
        roughness: 0.35,
        metalness: 0.2,
        emissive: PALETTE.door,
        emissiveIntensity: 0.5,
        transparent: true,
        opacity: 0.82,
      });
      track(mat);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(d.x + 0.5, WORLD.doorHeight * 0.5, d.z + 0.5);
      mesh.castShadow = true;
      group.add(mesh);
      doorMeshes.push({ mesh, mat, open: 0 });
    }
  }

  // ---------------------------------------------------------------- buttons
  const buttonMeshes = [];
  {
    const padGeo = new THREE.CylinderGeometry(0.42, 0.46, 0.12, 20);
    track(padGeo);
    for (let i = 0; i < level.buttons.length; i++) {
      const b = level.buttons[i];
      const mat = new THREE.MeshStandardMaterial({
        map: textures.button,
        color: 0xffffff,
        roughness: 0.5,
        metalness: 0.15,
        emissive: PALETTE.accentWarm,
        emissiveIntensity: 0.35,
      });
      track(mat);
      const mesh = new THREE.Mesh(padGeo, mat);
      mesh.position.set(b.x + 0.5, 0.06, b.z + 0.5);
      mesh.receiveShadow = true;
      group.add(mesh);

      const halo = new THREE.Mesh(
        track(new THREE.RingGeometry(0.5, 0.66, 24)),
        track(
          new THREE.MeshBasicMaterial({
            color: PALETTE.accentWarm,
            transparent: true,
            opacity: 0.3,
            side: THREE.DoubleSide,
          }),
        ),
      );
      halo.rotation.x = -Math.PI / 2;
      halo.position.set(b.x + 0.5, 0.015, b.z + 0.5);
      group.add(halo);
      buttonMeshes.push({ mesh, mat, halo, group: b.group });
    }
  }

  // ---------------------------------------------------------------- plates
  const plateMeshes = [];
  {
    const geo = new THREE.BoxGeometry(0.9, 0.1, 0.9);
    track(geo);
    for (let i = 0; i < level.plates.length; i++) {
      const p = level.plates[i];
      const mat = new THREE.MeshStandardMaterial({
        map: textures.plate,
        color: 0xffffff,
        roughness: 0.6,
        metalness: 0.1,
        emissive: PALETTE.plate,
        emissiveIntensity: 0.3,
      });
      track(mat);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(p.x + 0.5, 0.05, p.z + 0.5);
      mesh.receiveShadow = true;
      group.add(mesh);
      plateMeshes.push({ mesh, mat });
    }
  }

  // ---------------------------------------------------------------- teleport
  const teleMeshes = [];
  {
    for (let i = 0; i < level.teleports.length; i++) {
      const t = level.teleports[i];
      const geo = track(new THREE.CircleGeometry(0.46, 28));
      const mat = track(
        new THREE.MeshBasicMaterial({ map: textures.tele, transparent: true, opacity: 0.9, depthWrite: false }),
      );
      const mesh = new THREE.Mesh(geo, mat);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.set(t.x + 0.5, 0.03, t.z + 0.5);
      group.add(mesh);

      const beamGeo = track(new THREE.CylinderGeometry(0.34, 0.44, 1.6, 18, 1, true));
      const beamMat = track(
        new THREE.MeshBasicMaterial({
          color: PALETTE.accent,
          transparent: true,
          opacity: 0.14,
          side: THREE.DoubleSide,
          depthWrite: false,
        }),
      );
      const beam = new THREE.Mesh(beamGeo, beamMat);
      beam.position.set(t.x + 0.5, 0.8, t.z + 0.5);
      group.add(beam);
      teleMeshes.push({ mesh, beam });
    }
  }

  // ---------------------------------------------------------------- exit
  const exitTop = Math.max(0, level.height[level.exit.z * level.w + level.exit.x]);
  const exitPad = new THREE.Mesh(
    track(new THREE.CircleGeometry(0.47, 30)),
    track(new THREE.MeshBasicMaterial({ map: textures.exit, transparent: true, depthWrite: false })),
  );
  exitPad.rotation.x = -Math.PI / 2;
  exitPad.position.set(level.exit.x + 0.5, exitTop + 0.03, level.exit.z + 0.5);
  group.add(exitPad);

  const exitBeam = new THREE.Mesh(
    track(new THREE.CylinderGeometry(0.3, 0.44, 2.6, 20, 1, true)),
    track(
      new THREE.MeshBasicMaterial({
        color: PALETTE.exit,
        transparent: true,
        opacity: 0.16,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    ),
  );
  exitBeam.position.set(level.exit.x + 0.5, exitTop + 1.3, level.exit.z + 0.5);
  group.add(exitBeam);

  const exitLight = new THREE.PointLight(PALETTE.exit, 2.2, 7, 2);
  exitLight.position.set(level.exit.x + 0.5, exitTop + 1.1, level.exit.z + 0.5);
  scene.add(exitLight);

  // ---------------------------------------------------------------- crates
  const crateMeshes = [];
  {
    const geo = track(new THREE.BoxGeometry(0.74, 0.74, 0.74));
    const mat = track(
      new THREE.MeshStandardMaterial({ map: textures.crate, color: 0xffffff, roughness: 0.78, metalness: 0.05 }),
    );
    for (let i = 0; i < 8; i++) {
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.visible = false;
      group.add(mesh);
      crateMeshes.push(mesh);
    }
  }

  // ---------------------------------------------------------------- update
  const arena = {
    scene,
    group,
    sun,
    exitTop,
    wallVisual: WALL_VISUAL,
  };

  /**
   * @param {object} sim simulation to read state from
   * @param {Float32Array} rpos interpolated positions, 3 floats per body index
   * @param {number} dt render delta in seconds
   * @param {number} elapsed total elapsed seconds (drives idle animation)
   */
  arena.update = function update(sim, rpos, dt, elapsed) {
    for (let i = 0; i < doorMeshes.length; i++) {
      const d = doorMeshes[i];
      const target = sim.doorOpen[i] ? 1 : 0;
      d.open += (target - d.open) * Math.min(1, dt * 11);
      const door = level.doors[i];
      d.mesh.position.y = WORLD.doorHeight * 0.5 - d.open * (WORLD.doorHeight - 0.12);
      d.mesh.visible = d.open < 0.985;
      d.mat.opacity = 0.86 - d.open * 0.45;
      void door;
    }
    for (let i = 0; i < buttonMeshes.length; i++) {
      const b = buttonMeshes[i];
      const on = sim.buttonOn[i];
      b.mesh.position.y = on ? 0.025 : 0.06;
      b.mat.emissiveIntensity = on ? 1.5 : 0.3 + Math.sin(elapsed * 2 + i) * 0.08;
      b.halo.material.opacity = on ? 0.62 : 0.22;
      b.halo.scale.setScalar(on ? 1.12 : 1);
    }
    for (let i = 0; i < plateMeshes.length; i++) {
      const p = plateMeshes[i];
      const on = sim.plateOn[i];
      p.mesh.position.y = on ? 0.02 : 0.05;
      p.mat.emissiveIntensity = on ? 1.3 : 0.28;
    }
    for (let i = 0; i < teleMeshes.length; i++) {
      teleMeshes[i].mesh.rotation.z = elapsed * (i % 2 === 0 ? 1.1 : -1.1);
      teleMeshes[i].beam.scale.y = 1 + Math.sin(elapsed * 2.4 + i) * 0.06;
    }
    exitPad.rotation.z = elapsed * 0.6;
    exitBeam.scale.y = 1 + Math.sin(elapsed * 1.8) * 0.05;
    exitLight.intensity = 1.8 + Math.sin(elapsed * 3) * 0.4;

    for (let i = 0; i < fragileTiles.length; i++) {
      const f = fragileTiles[i];
      const gone = sim.heightNow[f.idx] < 0;
      const timer = sim.fragileTimer[f.idx];
      if (gone) {
        if (f.fall < 1) f.fall = Math.min(1, f.fall + dt * 1.6);
        f.mesh.position.y = f.baseY - f.fall * f.fall * 8;
        f.mesh.visible = f.fall < 1;
        f.mesh.rotation.z = f.fall * 1.4;
      } else {
        f.fall = 0;
        f.mesh.visible = true;
        f.mesh.rotation.z = 0;
        const shake = timer > 0 ? Math.sin(elapsed * 46) * 0.022 : 0;
        f.mesh.position.y = f.baseY + shake;
        f.mesh.position.x = level.w ? (f.idx % level.w) + 0.5 + shake * 0.6 : 0;
      }
    }

    for (let i = 0; i < crateMeshes.length; i++) {
      const c = sim.crates[i];
      const mesh = crateMeshes[i];
      if (!c || !c.active) {
        mesh.visible = false;
        continue;
      }
      mesh.visible = true;
      const b = (SIM.maxActors + i) * 3;
      mesh.position.set(rpos[b], rpos[b + 1] + 0.37, rpos[b + 2]);
      mesh.rotation.y = c.carriedBy >= 0 ? elapsed * 1.4 : 0;
    }
  };

  arena.dispose = function dispose() {
    for (let i = 0; i < disposables.length; i++) {
      const d = disposables[i];
      if (d && typeof d.dispose === 'function') d.dispose();
    }
    disposables.length = 0;
    if (envTexture) envTexture.dispose();
    scene.clear();
  };

  return arena;
}
