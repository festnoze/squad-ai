/**
 * AIGUILLAGE - track, ballast, sleepers, switch lamps, sidings, crossings.
 *
 * One spline per segment (src/spline.js), sampled once at build time into
 * static geometry: nothing here is rebuilt per frame. `update()` only
 * touches the handful of things that actually change: switch lamps and
 * level crossing barriers/lights.
 */

import * as THREE from 'three';
import { createSpline } from '../spline.js';

const GAUGE = 0.9; // metres between the two rail centrelines
const BALLAST_HALF_WIDTH = 2.1;
const SLEEPER_SPACING = 2.2;
const RAIL_RADIUS = 0.065;

const upVec = new THREE.Vector3(0, 1, 0);

function computeFrame(spline, s, out) {
  spline.at(s, out);
  out.right.crossVectors(out.tangent, upVec).normalize();
  return out;
}

function buildRibbonGeometry(spline, halfWidth, tileLength) {
  const count = Math.max(2, Math.round(spline.length / 1.6) + 1);
  const positions = new Float32Array(count * 2 * 3);
  const uvs = new Float32Array(count * 2 * 2);
  const normals = new Float32Array(count * 2 * 3);
  const frame = { pos: new THREE.Vector3(), tangent: new THREE.Vector3(), right: new THREE.Vector3() };
  let dist = 0;
  let prevPos = null;
  for (let i = 0; i < count; i++) {
    const s = (i / (count - 1)) * spline.length;
    computeFrame(spline, s, frame);
    if (prevPos) dist += frame.pos.distanceTo(prevPos);
    else prevPos = new THREE.Vector3();
    prevPos.copy(frame.pos);
    const v = dist / tileLength;
    const li = i * 2;
    const lx = frame.pos.x - frame.right.x * halfWidth;
    const lz = frame.pos.z - frame.right.z * halfWidth;
    const rx = frame.pos.x + frame.right.x * halfWidth;
    const rz = frame.pos.z + frame.right.z * halfWidth;
    positions[li * 3] = lx;
    positions[li * 3 + 1] = frame.pos.y;
    positions[li * 3 + 2] = lz;
    positions[(li + 1) * 3] = rx;
    positions[(li + 1) * 3 + 1] = frame.pos.y;
    positions[(li + 1) * 3 + 2] = rz;
    normals[li * 3 + 1] = 1;
    normals[(li + 1) * 3 + 1] = 1;
    uvs[li * 2] = 0;
    uvs[li * 2 + 1] = v;
    uvs[(li + 1) * 2] = 1;
    uvs[(li + 1) * 2 + 1] = v;
  }
  const indices = [];
  for (let i = 0; i < count - 1; i++) {
    const a = i * 2;
    const b = a + 1;
    const c = a + 2;
    const d = a + 3;
    indices.push(a, c, b, b, c, d);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
  geo.setIndex(indices);
  return geo;
}

function buildRailGeometry(spline, side) {
  const count = Math.max(4, Math.round(spline.length / 1.4) + 1);
  const pts = [];
  const frame = { pos: new THREE.Vector3(), tangent: new THREE.Vector3(), right: new THREE.Vector3() };
  for (let i = 0; i < count; i++) {
    const s = (i / (count - 1)) * spline.length;
    computeFrame(spline, s, frame);
    pts.push(
      new THREE.Vector3(
        frame.pos.x + frame.right.x * side * (GAUGE / 2),
        frame.pos.y + 0.09,
        frame.pos.z + frame.right.z * side * (GAUGE / 2),
      ),
    );
  }
  const curve = new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.4);
  const tubular = Math.max(6, Math.round(spline.length / 2));
  return new THREE.TubeGeometry(curve, tubular, RAIL_RADIUS, 6, false);
}

function branchAwayDirection(spline, seg, nodeId) {
  const frame = { pos: new THREE.Vector3(), tangent: new THREE.Vector3(), right: new THREE.Vector3() };
  if (seg.a === nodeId) {
    computeFrame(spline, 0, frame);
    return frame.tangent.clone();
  }
  computeFrame(spline, spline.length, frame);
  return frame.tangent.clone().negate();
}

export function createTrackRender(network, textures) {
  const group = new THREE.Group();
  const splines = new Map();

  const railMat = new THREE.MeshStandardMaterial({ color: 0xb9c2cc, metalness: 0.45, roughness: 0.42 });
  const ballastMat = new THREE.MeshStandardMaterial({ map: textures.ballast, roughness: 0.95, metalness: 0 });
  const sleeperMat = new THREE.MeshStandardMaterial({ map: textures.sleeper, roughness: 0.92, metalness: 0 });
  const groundMat = new THREE.MeshStandardMaterial({ map: textures.ground, roughness: 1, metalness: 0 });

  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (const n of network.nodes.values()) {
    minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x);
    minZ = Math.min(minZ, n.z); maxZ = Math.max(maxZ, n.z);
  }
  const cx = (minX + maxX) / 2;
  const cz = (minZ + maxZ) / 2;
  const spanX = Math.max(160, maxX - minX + 240);
  const spanZ = Math.max(160, maxZ - minZ + 240);

  const groundGeo = new THREE.PlaneGeometry(spanX, spanZ, 1, 1);
  groundGeo.rotateX(-Math.PI / 2);
  groundGeo.attributes.uv.array.forEach((v, i) => {
    groundGeo.attributes.uv.array[i] = v * (spanX / 24);
  });
  const ground = new THREE.Mesh(groundGeo, groundMat);
  ground.position.set(cx, -0.06, cz);
  group.add(ground);

  // ---- per segment: spline, ballast ribbon, two rails --------------------
  const sleeperMatrices = [];
  const tmpMat = new THREE.Matrix4();
  const tmpQuat = new THREE.Quaternion();
  const tmpFrame = { pos: new THREE.Vector3(), tangent: new THREE.Vector3(), right: new THREE.Vector3() };

  for (const seg of network.segments.values()) {
    const points3 = seg.points.map((p) => ({ x: p.x, y: 0, z: p.z }));
    const spline = createSpline(points3);
    splines.set(seg.id, spline);

    const ballastGeo = buildRibbonGeometry(spline, BALLAST_HALF_WIDTH, 6);
    group.add(new THREE.Mesh(ballastGeo, ballastMat));

    group.add(new THREE.Mesh(buildRailGeometry(spline, -1), railMat));
    group.add(new THREE.Mesh(buildRailGeometry(spline, 1), railMat));

    const sleeperCount = Math.max(1, Math.floor(spline.length / SLEEPER_SPACING));
    for (let i = 0; i <= sleeperCount; i++) {
      const s = (i / sleeperCount) * spline.length;
      computeFrame(spline, s, tmpFrame);
      tmpQuat.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tmpFrame.tangent);
      tmpMat.compose(
        new THREE.Vector3(tmpFrame.pos.x, 0.03, tmpFrame.pos.z),
        tmpQuat,
        new THREE.Vector3(1, 1, 1),
      );
      sleeperMatrices.push(tmpMat.clone());
    }
  }

  const sleeperGeo = new THREE.BoxGeometry(1.9, 0.08, 0.32);
  const sleepers = new THREE.InstancedMesh(sleeperGeo, sleeperMat, sleeperMatrices.length);
  for (let i = 0; i < sleeperMatrices.length; i++) sleepers.setMatrixAt(i, sleeperMatrices[i]);
  sleepers.instanceMatrix.needsUpdate = true;
  group.add(sleepers);

  // ---- nodes: spawns, exits, sidings, switches ----------------------------
  const switchPickables = [];
  const sidingPickables = [];
  const switchLamps = new Map(); // switchId -> {a: Mesh, b: Mesh}
  const crossingRigs = new Map(); // segmentId -> {arm, lightA, lightB}

  const gateMat = new THREE.MeshStandardMaterial({ color: 0x556074, roughness: 0.7, metalness: 0.2 });
  const postGeo = new THREE.CylinderGeometry(0.14, 0.16, 2.6, 8);

  for (const node of network.nodes.values()) {
    const pos = new THREE.Vector3(node.x, 0, node.z);
    if (node.kind === 'spawn') {
      const post = new THREE.Mesh(postGeo, gateMat);
      post.position.copy(pos).setY(1.3);
      group.add(post);
      const sign = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.9, 0.08), gateMat);
      sign.position.copy(pos).setY(2.5);
      group.add(sign);
    } else if (node.kind === 'exit') {
      const ringGeo = new THREE.RingGeometry(1.6, 2.1, 24);
      ringGeo.rotateX(-Math.PI / 2);
      const ringMat = new THREE.MeshBasicMaterial({ color: node.color, transparent: true, opacity: 0.85 });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.position.copy(pos).setY(0.04);
      group.add(ring);
      const post = new THREE.Mesh(postGeo, gateMat);
      post.position.copy(pos).setY(1.3);
      group.add(post);
      const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.32, 10, 8), new THREE.MeshBasicMaterial({ color: node.color }));
      lamp.position.copy(pos).setY(2.7);
      group.add(lamp);
    } else if (node.kind === 'siding') {
      const bufferGeo = new THREE.BoxGeometry(0.5, 0.6, 2.6);
      const bufferMat = new THREE.MeshStandardMaterial({ map: textures.barrier, roughness: 0.6 });
      const buffer = new THREE.Mesh(bufferGeo, bufferMat);
      buffer.position.copy(pos).setY(0.3);
      group.add(buffer);
      sidingPickables.push({ nodeId: node.id, mesh: buffer, pos: pos.clone() });
    }
  }

  for (const sw of network.switches.values()) {
    const node = network.nodes.get(sw.nodeId);
    const pos = new THREE.Vector3(node.x, 0, node.z);
    const post = new THREE.Mesh(postGeo, gateMat);
    post.position.copy(pos).setY(1.3);
    group.add(post);

    const segA = network.segments.get(sw.branches[0]);
    const segB = network.segments.get(sw.branches[1]);
    const splineA = splines.get(segA.id);
    const splineB = splines.get(segB.id);
    const dirA = branchAwayDirection(splineA, segA, sw.nodeId);
    const dirB = branchAwayDirection(splineB, segB, sw.nodeId);

    const lampGeo = new THREE.SphereGeometry(0.4, 10, 8);
    const lampA = new THREE.Mesh(lampGeo, new THREE.MeshBasicMaterial({ color: 0xfff2c8 }));
    lampA.position.copy(pos).addScaledVector(dirA, 5.5).setY(2.9);
    const lampB = new THREE.Mesh(lampGeo, new THREE.MeshBasicMaterial({ color: 0xfff2c8 }));
    lampB.position.copy(pos).addScaledVector(dirB, 5.5).setY(2.9);
    group.add(lampA, lampB);
    switchLamps.set(sw.id, { a: lampA, b: lampB });

    const hitGeo = new THREE.CylinderGeometry(2.4, 2.4, 3.2, 10);
    const hitMesh = new THREE.Mesh(hitGeo, new THREE.MeshBasicMaterial({ visible: false }));
    hitMesh.position.copy(pos).setY(1.4);
    group.add(hitMesh);
    switchPickables.push({ switchId: sw.id, mesh: hitMesh, pos: pos.clone() });
  }

  // ---- level crossings -----------------------------------------------------
  for (const seg of network.segments.values()) {
    if (!seg.crossing) continue;
    const spline = splines.get(seg.id);
    const frame = spline.makeFrame();
    frame.right = new THREE.Vector3();
    spline.at(seg.crossing.sAt, frame);
    frame.right.crossVectors(frame.tangent, upVec).normalize();

    const rig = new THREE.Group();
    rig.position.copy(frame.pos);
    rig.lookAt(frame.pos.clone().add(frame.right));

    const postL = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.14, 2.1, 8), gateMat);
    postL.position.set(0, 1.05, -BALLAST_HALF_WIDTH - 0.6);
    rig.add(postL);
    const armPivot = new THREE.Group();
    armPivot.position.set(0, 1.9, -BALLAST_HALF_WIDTH - 0.6);
    rig.add(armPivot);
    const arm = new THREE.Mesh(new THREE.BoxGeometry(BALLAST_HALF_WIDTH * 2 + 1.4, 0.14, 0.14), new THREE.MeshStandardMaterial({ map: textures.barrier }));
    arm.position.set((BALLAST_HALF_WIDTH * 2 + 1.4) / 2, 0, 0);
    armPivot.add(arm);

    const lightGeo = new THREE.SphereGeometry(0.16, 8, 6);
    const lightA = new THREE.Mesh(lightGeo, new THREE.MeshBasicMaterial({ color: 0x400000 }));
    lightA.position.set(0, 2.15, -BALLAST_HALF_WIDTH - 0.6);
    const lightB = lightA.clone();
    lightB.material = lightA.material.clone();
    lightB.position.z = BALLAST_HALF_WIDTH + 0.6;
    rig.add(lightA, lightB);

    group.add(rig);
    crossingRigs.set(seg.id, { armPivot, lightA, lightB, blink: 0 });
  }

  const trackRender = {
    group,
    switchPickables,
    sidingPickables,

    getSpline(segmentId) {
      return splines.get(segmentId);
    },

    nodeWorldPos(nodeId) {
      const n = network.nodes.get(nodeId);
      return new THREE.Vector3(n.x, 0, n.z);
    },

    update(dt, simTime) {
      for (const sw of network.switches.values()) {
        const lamps = switchLamps.get(sw.id);
        if (!lamps) continue;
        const activeA = sw.state === 0;
        lamps.a.material.color.setHex(activeA ? 0xfff2c8 : 0x453c2c);
        lamps.b.material.color.setHex(activeA ? 0x453c2c : 0xfff2c8);
      }
      for (const [segId, rig] of crossingRigs) {
        const closed = network.isCrossingClosed(segId, simTime);
        const targetAngle = closed ? Math.PI / 2 : 0;
        const current = rig.armPivot.rotation.y;
        rig.armPivot.rotation.y += (targetAngle - current) * Math.min(1, dt * 4);
        rig.blink += dt;
        const on = closed && Math.floor(rig.blink * 3) % 2 === 0;
        rig.lightA.material.color.setHex(on ? 0xff2a2a : 0x400000);
        rig.lightB.material.color.setHex(on ? 0xff2a2a : 0x400000);
      }
    },

    dispose() {
      group.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
          if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
          else obj.material.dispose();
        }
      });
    },
  };

  return trackRender;
}
