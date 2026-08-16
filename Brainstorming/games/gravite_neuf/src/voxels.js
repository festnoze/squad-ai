/**
 * GRAVITE NEUF - voxel renderer.
 *
 * The whole level lives inside a single Group whose quaternion is driven by the
 * camera module: when gravity tilts, the structure rolls and the new floor ends
 * up at the bottom of the screen. Static blocks are one InstancedMesh per kind
 * (a level is well under twenty draw calls); only the handful of movables get
 * their own mesh, since they are animated individually.
 */

import * as THREE from 'three';
import { S, MV, DIRS, switchOn } from './world.js';
import { PALETTE } from './textures.js';

const STEP_BASE = 0.115; // seconds for the very first cell of a fall
const STEP_MIN = 0.034;
const STEP_MAX = 0.17;

const tmpMatrix = new THREE.Matrix4();
const tmpPos = new THREE.Vector3();
const tmpQuat = new THREE.Quaternion();
const tmpScale = new THREE.Vector3(1, 1, 1);
const gridNormal = new THREE.Vector3();
const PLANE_FORWARD = new THREE.Vector3(0, 0, 1);

function stepDuration(k) {
  const d = STEP_BASE * (Math.sqrt(k + 1) - Math.sqrt(k));
  return d < STEP_MIN ? STEP_MIN : d > STEP_MAX ? STEP_MAX : d;
}

export function createVoxels(textures) {
  const group = new THREE.Group();
  const staticGroup = new THREE.Group();
  const movableGroup = new THREE.Group();
  group.add(staticGroup);
  group.add(movableGroup);

  const boxGeom = new THREE.BoxGeometry(1, 1, 1);
  const keyGeom = new THREE.OctahedronGeometry(0.36, 0);
  const planeGeom = new THREE.PlaneGeometry(1, 1);

  const owned = [];
  let W = 1;
  let H = 1;
  let D = 1;
  let offX = 0;
  let offY = 0;
  let offZ = 0;

  const staticMeshes = {};
  const movableViews = [];
  let cage = null;
  let grid = null;
  let gridMaterial = null;
  let exitMaterial = null;
  let plateMaterials = { a: null, b: null };
  let gateMaterials = { a: null, b: null };

  let anim = null;
  const api = {
    group,
    busy: false,
    radius: 6,
  };

  function track(x) {
    owned.push(x);
    return x;
  }

  function localX(x) {
    return x - offX;
  }
  function localY(y) {
    return y - offY;
  }
  function localZ(z) {
    return z - offZ;
  }

  function clearLevel() {
    for (let i = staticGroup.children.length - 1; i >= 0; i--) {
      const child = staticGroup.children[i];
      if (typeof child.dispose === 'function') child.dispose();
      staticGroup.remove(child);
    }
    for (let i = movableGroup.children.length - 1; i >= 0; i--) movableGroup.remove(movableGroup.children[i]);
    if (cage) {
      group.remove(cage);
      cage = null;
    }
    if (grid) {
      group.remove(grid);
      grid = null;
    }
    for (let i = 0; i < owned.length; i++) {
      const o = owned[i];
      if (o && typeof o.dispose === 'function') o.dispose();
    }
    owned.length = 0;
    movableViews.length = 0;
    for (const k in staticMeshes) delete staticMeshes[k];
  }

  function solidMaterial(map, extra) {
    const m = new THREE.MeshStandardMaterial({
      map,
      color: 0xffffff,
      roughness: 0.82,
      metalness: 0.0,
    });
    if (extra) Object.assign(m, extra);
    return track(m);
  }

  function addInstanced(key, positions, material, scale, castShadow, renderOrder) {
    if (!positions.length) return null;
    const mesh = new THREE.InstancedMesh(boxGeom, material, positions.length);
    mesh.castShadow = !!castShadow;
    mesh.receiveShadow = !!castShadow;
    if (renderOrder) mesh.renderOrder = renderOrder;
    tmpScale.set(scale, scale, scale);
    tmpQuat.identity();
    for (let i = 0; i < positions.length; i++) {
      const p = positions[i];
      tmpPos.set(localX(p[0]), localY(p[1]), localZ(p[2]));
      tmpMatrix.compose(tmpPos, tmpQuat, tmpScale);
      mesh.setMatrixAt(i, tmpMatrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    staticGroup.add(mesh);
    staticMeshes[key] = mesh;
    return mesh;
  }

  function buildMovableView(m) {
    const holder = new THREE.Group();
    let mesh;
    if (m.kind === MV.KEY) {
      const mat = track(
        new THREE.MeshStandardMaterial({
          map: textures.key,
          color: 0xffffff,
          emissive: new THREE.Color(PALETTE.key),
          emissiveIntensity: 0.9,
          roughness: 0.35,
          metalness: 0.0,
        })
      );
      mesh = new THREE.Mesh(keyGeom, mat);
    } else if (m.kind === MV.PLAYER) {
      const mat = solidMaterial(textures.player, {
        emissive: new THREE.Color(PALETTE.player),
        emissiveIntensity: 0.30,
        roughness: 0.55,
      });
      mesh = new THREE.Mesh(boxGeom, mat);
      mesh.scale.setScalar(0.88);
    } else {
      const mat = solidMaterial(textures.crate, { roughness: 0.9 });
      mesh = new THREE.Mesh(boxGeom, mat);
      mesh.scale.setScalar(0.92);
    }
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    holder.add(mesh);

    if (m.kind !== MV.KEY) {
      const edges = new THREE.LineSegments(
        track(new THREE.EdgesGeometry(boxGeom)),
        track(
          new THREE.LineBasicMaterial({
            color: m.kind === MV.PLAYER ? 0xfff4cf : 0x2a1a08,
            transparent: true,
            opacity: 0.85,
          })
        )
      );
      edges.scale.setScalar(m.kind === MV.PLAYER ? 0.9 : 0.94);
      holder.add(edges);
    }

    // X-ray silhouette. A voxel structure hides its own interior as soon as it
    // rolls, so everything the player must plan around keeps a faint outline
    // drawn on top of the scene.
    const xrayColor =
      m.kind === MV.PLAYER ? PALETTE.player : m.kind === MV.KEY ? PALETTE.key : PALETTE.crate;
    const xray = new THREE.LineSegments(
      track(new THREE.EdgesGeometry(m.kind === MV.KEY ? keyGeom : boxGeom)),
      track(
        new THREE.LineBasicMaterial({
          color: xrayColor,
          transparent: true,
          opacity: m.kind === MV.CRATE ? 0.28 : 0.5,
          depthTest: false,
          depthWrite: false,
        })
      )
    );
    xray.scale.setScalar(m.kind === MV.KEY ? 1 : 0.9);
    xray.renderOrder = 11;
    holder.add(xray);

    movableGroup.add(holder);
    return { holder, mesh, xray, kind: m.kind, stuckShown: false };
  }

  api.build = function build(state) {
    clearLevel();
    W = state.W;
    H = state.H;
    D = state.D;
    offX = (W - 1) / 2;
    offY = (H - 1) / 2;
    offZ = (D - 1) / 2;
    api.radius = 0.5 * Math.sqrt(W * W + H * H + D * D);

    const buckets = {};
    for (let y = 0; y < H; y++) {
      for (let z = 0; z < D; z++) {
        for (let x = 0; x < W; x++) {
          const k = state.statics[(y * D + z) * W + x];
          if (k === S.EMPTY) continue;
          if (!buckets[k]) buckets[k] = [];
          buckets[k].push([x, y, z]);
        }
      }
    }

    addInstanced('wall', buckets[S.WALL] || [], solidMaterial(textures.wall), 1.0, true);
    addInstanced(
      'glue',
      buckets[S.GLUE] || [],
      solidMaterial(textures.glue, {
        emissive: new THREE.Color(PALETTE.glue),
        emissiveIntensity: 0.22,
        roughness: 0.45,
      }),
      1.0,
      true
    );
    addInstanced(
      'spike',
      buckets[S.SPIKE] || [],
      solidMaterial(textures.spike, {
        emissive: new THREE.Color('#ff6a6a'),
        emissiveIntensity: 0.18,
        roughness: 0.6,
      }),
      1.0,
      true
    );

    exitMaterial = solidMaterial(textures.exit, {
      emissive: new THREE.Color(PALETTE.exit),
      emissiveIntensity: 1.0,
      transparent: true,
      opacity: 0.62,
      roughness: 0.3,
      depthWrite: false,
    });
    addInstanced('exit', buckets[S.EXIT] || [], exitMaterial, 0.99, false);

    // Small additive core drawn with depthTest off: the exit stays locatable
    // even when the structure has rolled and buried it behind three walls.
    addInstanced(
      'exitMark',
      buckets[S.EXIT] || [],
      track(
        new THREE.MeshBasicMaterial({
          color: new THREE.Color(PALETTE.exit),
          transparent: true,
          opacity: 0.30,
          depthTest: false,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        })
      ),
      0.34,
      false,
      12
    );

    plateMaterials.a = solidMaterial(textures.plateA, {
      emissive: new THREE.Color(PALETTE.plateA),
      emissiveIntensity: 0.35,
      transparent: true,
      opacity: 0.55,
      roughness: 0.4,
      depthWrite: false,
    });
    plateMaterials.b = solidMaterial(textures.plateB, {
      emissive: new THREE.Color(PALETTE.plateB),
      emissiveIntensity: 0.35,
      transparent: true,
      opacity: 0.55,
      roughness: 0.4,
      depthWrite: false,
    });
    addInstanced('plateA', buckets[S.SWITCH_A] || [], plateMaterials.a, 0.98, false);
    addInstanced('plateB', buckets[S.SWITCH_B] || [], plateMaterials.b, 0.98, false);

    gateMaterials.a = solidMaterial(textures.gateA, {
      emissive: new THREE.Color(PALETTE.plateA),
      emissiveIntensity: 0.8,
      transparent: true,
      opacity: 0.8,
      roughness: 0.35,
      depthWrite: false,
    });
    gateMaterials.b = solidMaterial(textures.gateB, {
      emissive: new THREE.Color(PALETTE.plateB),
      emissiveIntensity: 0.8,
      transparent: true,
      opacity: 0.8,
      roughness: 0.35,
      depthWrite: false,
    });
    addInstanced('gateA', buckets[S.GATE_A] || [], gateMaterials.a, 0.99, false);
    addInstanced('gateB', buckets[S.GATE_B] || [], gateMaterials.b, 0.99, false);

    for (let i = 0; i < state.movables.length; i++) {
      movableViews.push(buildMovableView(state.movables[i]));
    }

    // The box only exists to be turned into edges; dropping it on the floor
    // leaked one buffer geometry per level load over a whole session.
    const cageBox = new THREE.BoxGeometry(W, H, D);
    const cageGeom = track(new THREE.EdgesGeometry(cageBox));
    cageBox.dispose();
    cage = new THREE.LineSegments(
      cageGeom,
      track(new THREE.LineBasicMaterial({ color: 0x8fb4e8, transparent: true, opacity: 0.28 }))
    );
    group.add(cage);

    gridMaterial = track(
      new THREE.MeshBasicMaterial({
        map: textures.grid,
        transparent: true,
        opacity: 0.55,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
    );
    grid = new THREE.Mesh(planeGeom, gridMaterial);
    group.add(grid);

    api.setGravityFace(state.gravity);
    api.applyState(state);
    api.syncStatics(state);
    anim = null;
    api.busy = false;
  };


  /** Places the reference grid on the face of the world box gravity points at. */
  api.setGravityFace = function setGravityFace(dirIndex) {
    if (!grid) return;
    const d = DIRS[dirIndex];
    gridNormal.set(-d[0], -d[1], -d[2]);
    grid.quaternion.setFromUnitVectors(PLANE_FORWARD, gridNormal);
    const half = [W * 0.5, H * 0.5, D * 0.5];
    const axis = d[0] !== 0 ? 0 : d[1] !== 0 ? 1 : 2;
    const dist = half[axis] + 0.04;
    grid.position.set(d[0] * dist, d[1] * dist, d[2] * dist);
    const sizes = axis === 0 ? [D, H] : axis === 1 ? [W, D] : [W, H];
    grid.scale.set(sizes[0], sizes[1], 1);
    textures.grid.repeat.set(sizes[0], sizes[1]);
  };

  api.syncStatics = function syncStatics(st) {
    const gateA = switchOn(st, S.SWITCH_A);
    const gateB = switchOn(st, S.SWITCH_B);
    if (staticMeshes.gateA) {
      gateMaterials.a.opacity = gateA ? 0.14 : 0.82;
      gateMaterials.a.emissiveIntensity = gateA ? 0.25 : 0.9;
    }
    if (staticMeshes.gateB) {
      gateMaterials.b.opacity = gateB ? 0.14 : 0.82;
      gateMaterials.b.emissiveIntensity = gateB ? 0.25 : 0.9;
    }
    if (staticMeshes.plateA) plateMaterials.a.emissiveIntensity = gateA ? 1.4 : 0.3;
    if (staticMeshes.plateB) plateMaterials.b.emissiveIntensity = gateB ? 1.4 : 0.3;
  };

  function placeView(i, x, y, z, scale, visible) {
    const v = movableViews[i];
    if (!v) return;
    v.holder.visible = visible;
    if (!visible) return;
    v.holder.position.set(localX(x), localY(y), localZ(z));
    v.holder.scale.setScalar(scale);
  }

  function markStuck(i, stuck) {
    const v = movableViews[i];
    if (!v || v.stuckShown === stuck) return;
    v.stuckShown = stuck;
    const mat = v.mesh.material;
    if (stuck) {
      mat.emissive.set(PALETTE.glue);
      mat.emissiveIntensity = 0.65;
    } else if (v.kind === MV.PLAYER) {
      mat.emissive.set(PALETTE.player);
      mat.emissiveIntensity = 0.3;
    } else if (v.kind === MV.KEY) {
      mat.emissive.set(PALETTE.key);
      mat.emissiveIntensity = 0.9;
    } else {
      mat.emissive.set(0x000000);
      mat.emissiveIntensity = 0;
    }
  }

  /** Snaps every movable to the exact state, with no animation. */
  api.applyState = function applyState(st) {
    for (let i = 0; i < st.movables.length; i++) {
      const m = st.movables[i];
      placeView(i, m.x, m.y, m.z, 1, m.alive);
      markStuck(i, m.stuck);
    }
    anim = null;
    api.busy = false;
  };

  api.play = function play(steps) {
    if (!steps || steps.length < 2) {
      api.busy = false;
      return;
    }
    const times = new Float32Array(steps.length - 1);
    let total = 0;
    for (let k = 0; k < times.length; k++) {
      times[k] = stepDuration(k);
      total += times[k];
    }
    anim = { steps, times, total, t: 0 };
    api.busy = true;
  };

  api.update = function update(dt, elapsed) {
    if (exitMaterial) exitMaterial.emissiveIntensity = 0.75 + 0.45 * Math.sin(elapsed * 3.0);
    for (let i = 0; i < movableViews.length; i++) {
      const v = movableViews[i];
      if (v.kind === MV.KEY && v.holder.visible) {
        v.mesh.rotation.y = elapsed * 1.7;
        v.mesh.rotation.x = Math.sin(elapsed * 1.1) * 0.35;
        v.xray.rotation.copy(v.mesh.rotation);
      }
    }

    if (!anim) return;
    anim.t += dt;
    let t = anim.t;
    let k = 0;
    while (k < anim.times.length && t > anim.times[k]) {
      t -= anim.times[k];
      k++;
    }
    if (k >= anim.times.length) {
      const last = anim.steps[anim.steps.length - 1];
      for (let i = 0; i < last.alive.length; i++) {
        placeView(i, last.pos[i * 3], last.pos[i * 3 + 1], last.pos[i * 3 + 2], 1, last.alive[i] === 1);
        markStuck(i, last.stuck[i] === 1);
      }
      anim = null;
      api.busy = false;
      return;
    }

    const a = anim.steps[k];
    const b = anim.steps[k + 1];
    const u = anim.times[k] > 0 ? t / anim.times[k] : 1;
    for (let i = 0; i < a.alive.length; i++) {
      const aliveA = a.alive[i] === 1;
      const aliveB = b.alive[i] === 1;
      if (!aliveA && !aliveB) {
        placeView(i, 0, 0, 0, 1, false);
        continue;
      }
      const ax = a.pos[i * 3];
      const ay = a.pos[i * 3 + 1];
      const az = a.pos[i * 3 + 2];
      const bx = b.pos[i * 3];
      const by = b.pos[i * 3 + 1];
      const bz = b.pos[i * 3 + 2];
      const x = ax + (bx - ax) * u;
      const y = ay + (by - ay) * u;
      const z = az + (bz - az) * u;
      const scale = aliveA && !aliveB ? Math.max(0.02, 1 - u * 0.9) : 1;
      placeView(i, x, y, z, scale, true);
      markStuck(i, b.stuck[i] === 1 && u > 0.4);
    }
  };

  api.dispose = function dispose() {
    clearLevel();
    boxGeom.dispose();
    keyGeom.dispose();
    planeGeom.dispose();
  };

  return api;
}
