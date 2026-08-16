/**
 * OVERCLOCK - the drone.
 *
 * Built entirely from primitives. Four rotors in one InstancedMesh, a ventral
 * halo faked with an additive disc (a real spot light with a shadow map would
 * cost more than the rest of the scene), and a short additive particle trail.
 */

import * as THREE from 'three';
import { STEP } from './scene.js';

const TRAIL = 84;
const ACCENT = new THREE.Color(0x21e39a);
const REFUSE = new THREE.Color(0xff5566);

// Module scratch, never shared across nested calls.
const rotorMat4 = new THREE.Matrix4();
const rotorPos = new THREE.Vector3();
const rotorQuat = new THREE.Quaternion();
const rotorScale = new THREE.Vector3(1, 1, 1);
const rotorAxis = new THREE.Vector3(0, 1, 0);

export function createDrone(textures) {
  const group = new THREE.Group();

  const hullMat = new THREE.MeshStandardMaterial({
    map: textures.hull,
    color: 0xc8d8dc,
    roughness: 0.55,
    metalness: 0.08,
  });
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x16232a, roughness: 0.45, metalness: 0.05 });
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0x8ff0d0,
    roughness: 0.15,
    metalness: 0.0,
    transparent: true,
    opacity: 0.55,
    emissive: 0x0d5a44,
    emissiveIntensity: 0.9,
  });
  const glowMat = new THREE.MeshBasicMaterial({ color: ACCENT.clone(), toneMapped: false });

  const body = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.11, 0.42), hullMat);
  body.castShadow = true;
  group.add(body);

  const belly = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.06, 0.26), darkMat);
  belly.position.y = -0.075;
  group.add(belly);

  const canopy = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.09, 0.2), glassMat);
  canopy.position.set(0, 0.075, 0.07);
  group.add(canopy);

  const beacon = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.03, 0.06), glowMat);
  beacon.position.set(0, 0.015, 0.235);
  group.add(beacon);

  // two crossed arms carrying the four rotors
  const armGeo = new THREE.BoxGeometry(0.62, 0.035, 0.055);
  for (const a of [Math.PI / 4, -Math.PI / 4]) {
    const arm = new THREE.Mesh(armGeo, darkMat);
    arm.rotation.y = a;
    arm.castShadow = true;
    group.add(arm);
  }

  const hubGeo = new THREE.CylinderGeometry(0.045, 0.055, 0.05, 10);
  const rotorOffsets = [];
  for (let i = 0; i < 4; i++) {
    const a = Math.PI / 4 + (i * Math.PI) / 2;
    const p = new THREE.Vector3(Math.cos(a) * 0.22, 0.03, Math.sin(a) * 0.22);
    rotorOffsets.push(p);
    const hub = new THREE.Mesh(hubGeo, darkMat);
    hub.position.copy(p);
    group.add(hub);
  }

  const bladeGeo = new THREE.RingGeometry(0.05, 0.125, 18, 1);
  bladeGeo.rotateX(-Math.PI / 2);
  const bladeMat = new THREE.MeshBasicMaterial({
    color: 0x9ff5d8,
    transparent: true,
    opacity: 0.22,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
    toneMapped: false,
  });
  const rotors = new THREE.InstancedMesh(bladeGeo, bladeMat, 4);
  rotors.frustumCulled = false;
  group.add(rotors);

  // ventral cone, cheap volumetric hint
  const coneGeo = new THREE.ConeGeometry(0.26, 0.55, 14, 1, true);
  const coneMat = new THREE.MeshBasicMaterial({
    color: 0x21e39a,
    transparent: true,
    opacity: 0.12,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
    toneMapped: false,
  });
  const cone = new THREE.Mesh(coneGeo, coneMat);
  cone.position.y = -0.36;
  cone.rotation.x = Math.PI;
  group.add(cone);

  // carried crate, drawn only when the drone holds one
  const carried = new THREE.Mesh(
    new THREE.BoxGeometry(0.42, STEP * 0.78, 0.42),
    new THREE.MeshStandardMaterial({ map: textures.crate, roughness: 0.9, metalness: 0 })
  );
  carried.position.y = -0.28;
  carried.castShadow = true;
  carried.visible = false;
  group.add(carried);

  // ---- halo on the floor, independent of the drone tilt -----------------
  const haloMat = new THREE.MeshBasicMaterial({
    map: textures.halo,
    color: 0x21e39a,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
    opacity: 0.75,
  });
  const haloGeo = new THREE.PlaneGeometry(1.5, 1.5);
  haloGeo.rotateX(-Math.PI / 2);
  const halo = new THREE.Mesh(haloGeo, haloMat);

  // ---- trail ------------------------------------------------------------
  const tPos = new Float32Array(TRAIL * 3);
  const tCol = new Float32Array(TRAIL * 3);
  const tLife = new Float32Array(TRAIL);
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute('position', new THREE.BufferAttribute(tPos, 3));
  trailGeo.setAttribute('color', new THREE.BufferAttribute(tCol, 3));
  const trailMat = new THREE.PointsMaterial({
    size: 0.11,
    map: textures.spark,
    vertexColors: true,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
    toneMapped: false,
  });
  const trail = new THREE.Points(trailGeo, trailMat);
  trail.frustumCulled = false;

  let head = 0;
  let emitTimer = 0;
  let spin = 0;
  let flashTimer = 0;
  let lastX = 0;
  let lastY = 0;
  let lastZ = 0;
  let bob = 0;

  const drone = {
    group,
    halo,
    trail,

    setPose(x, y, z, yaw, tiltX, tiltZ) {
      group.position.set(x, y, z);
      group.rotation.set(tiltX || 0, yaw, tiltZ || 0, 'YXZ');
    },

    setCarrying(v) {
      carried.visible = !!v;
    },

    /** Ground height the halo is projected onto, in world units. */
    setGroundY(y) {
      halo.position.set(group.position.x, y + 0.02, group.position.z);
      const d = Math.max(0.15, group.position.y - y);
      const s = 0.7 + d * 0.55;
      halo.scale.set(s, 1, s);
      haloMat.opacity = Math.max(0.12, 0.85 - d * 0.28);
      cone.scale.set(1, Math.max(0.3, d / 0.55), 1);
      cone.position.y = -0.09 - (d * 0.5);
    },

    /** Red pulse when an instruction is refused: readable without reading. */
    refuse() {
      flashTimer = 0.45;
    },

    update(dt, moving) {
      spin += dt * (moving ? 34 : 20);
      for (let i = 0; i < 4; i++) {
        rotorPos.copy(rotorOffsets[i]);
        rotorPos.y += 0.045;
        rotorQuat.setFromAxisAngle(rotorAxis, spin * (i % 2 === 0 ? 1 : -1));
        rotorMat4.compose(rotorPos, rotorQuat, rotorScale);
        rotors.setMatrixAt(i, rotorMat4);
      }
      rotors.instanceMatrix.needsUpdate = true;

      bob += dt;

      if (flashTimer > 0) {
        flashTimer = Math.max(0, flashTimer - dt);
        const k = flashTimer / 0.45;
        glowMat.color.copy(ACCENT).lerp(REFUSE, k);
        haloMat.color.copy(ACCENT).lerp(REFUSE, k);
      }

      // trail
      emitTimer -= dt;
      const dx = group.position.x - lastX;
      const dy = group.position.y - lastY;
      const dz = group.position.z - lastZ;
      const dist2 = dx * dx + dy * dy + dz * dz;
      if (emitTimer <= 0 && dist2 > 0.00002) {
        emitTimer = 0.024;
        const i3 = head * 3;
        tPos[i3] = group.position.x;
        tPos[i3 + 1] = group.position.y - 0.1;
        tPos[i3 + 2] = group.position.z;
        tLife[head] = 1;
        head = (head + 1) % TRAIL;
      }
      lastX = group.position.x;
      lastY = group.position.y;
      lastZ = group.position.z;

      for (let i = 0; i < TRAIL; i++) {
        if (tLife[i] <= 0) {
          tCol[i * 3] = tCol[i * 3 + 1] = tCol[i * 3 + 2] = 0;
          continue;
        }
        tLife[i] = Math.max(0, tLife[i] - dt * 1.8);
        const l = tLife[i] * tLife[i];
        tCol[i * 3] = 0.13 * l;
        tCol[i * 3 + 1] = 0.89 * l;
        tCol[i * 3 + 2] = 0.62 * l;
      }
      trailGeo.attributes.color.needsUpdate = true;
      trailGeo.attributes.position.needsUpdate = true;
    },

    /** Small vertical float, added by main.js on top of the logical height. */
    bobOffset() {
      return Math.sin(bob * 2.4) * 0.028;
    },

    resetTrail() {
      for (let i = 0; i < TRAIL; i++) tLife[i] = 0;
      for (let i = 0; i < TRAIL * 3; i++) tCol[i] = 0;
      trailGeo.attributes.color.needsUpdate = true;
    },

    dispose() {
      body.geometry.dispose();
      belly.geometry.dispose();
      canopy.geometry.dispose();
      beacon.geometry.dispose();
      armGeo.dispose();
      hubGeo.dispose();
      bladeGeo.dispose();
      coneGeo.dispose();
      haloGeo.dispose();
      trailGeo.dispose();
      carried.geometry.dispose();
      carried.material.dispose();
      hullMat.dispose();
      darkMat.dispose();
      glassMat.dispose();
      glowMat.dispose();
      bladeMat.dispose();
      coneMat.dispose();
      haloMat.dispose();
      trailMat.dispose();
      rotors.dispose();
    },
  };

  return drone;
}
