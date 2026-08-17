/**
 * CONTREPOIDS - the miner character.
 *
 * A small blocky figure built entirely from primitives (no external model).
 * `main.js` owns the actual world position/animation timing; this module only
 * knows how to pose itself given a position, a facing angle and whether it is
 * currently walking, and how to show whatever is currently held in its hand.
 */

import * as THREE from 'three';
import { OBJ } from '../shaft.js';

export function createPlayer(textures) {
  const group = new THREE.Group();

  const suitMat = new THREE.MeshStandardMaterial({ color: 0xd8862c, roughness: 0.75, metalness: 0.05 });
  const skinMat = new THREE.MeshStandardMaterial({ map: textures.skin, roughness: 0.8, metalness: 0 });
  const bootMat = new THREE.MeshStandardMaterial({ color: 0x2a231c, roughness: 0.9, metalness: 0.05 });
  const lampMat = new THREE.MeshStandardMaterial({ color: 0xfff2b0, emissive: 0xffd77a, emissiveIntensity: 2.2, roughness: 0.4 });

  const body = new THREE.Group();
  group.add(body);

  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.42, 0.22), suitMat);
  torso.position.y = 0.62;
  torso.castShadow = true;
  body.add(torso);

  const head = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.26, 0.26), skinMat);
  head.position.y = 0.98;
  head.castShadow = true;
  body.add(head);

  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 8), lampMat);
  lamp.position.set(0, 1.03, 0.14);
  body.add(lamp);
  const lampLight = new THREE.PointLight(0xffd79a, 1.4, 5, 2);
  lampLight.position.copy(lamp.position);
  body.add(lampLight);

  const legGeom = new THREE.BoxGeometry(0.12, 0.36, 0.14);
  const legL = new THREE.Mesh(legGeom, bootMat);
  legL.position.set(-0.09, 0.18, 0);
  legL.castShadow = true;
  const legR = new THREE.Mesh(legGeom, bootMat);
  legR.position.set(0.09, 0.18, 0);
  legR.castShadow = true;
  body.add(legL, legR);

  const armGeom = new THREE.BoxGeometry(0.1, 0.3, 0.12);
  const armPivotL = new THREE.Group();
  armPivotL.position.set(-0.23, 0.78, 0);
  const armL = new THREE.Mesh(armGeom, suitMat);
  armL.position.y = -0.14;
  armL.castShadow = true;
  armPivotL.add(armL);
  const armPivotR = new THREE.Group();
  armPivotR.position.set(0.23, 0.78, 0);
  const armR = new THREE.Mesh(armGeom, suitMat);
  armR.position.y = -0.14;
  armR.castShadow = true;
  armPivotR.add(armR);
  body.add(armPivotL, armPivotR);

  const handAnchor = new THREE.Group();
  handAnchor.position.set(0.3, 0.5, 0.22);
  body.add(handAnchor);
  let heldMesh = null;
  let heldKind = null;

  const pierreGeom = new THREE.IcosahedronGeometry(0.16, 0);
  const pierreMat = new THREE.MeshStandardMaterial({ map: textures.stone, roughness: 0.9 });
  const ballonGeom = new THREE.SphereGeometry(0.18, 12, 10);
  const ballonMat = new THREE.MeshStandardMaterial({ map: textures.balloon, roughness: 0.35 });

  function setCarrying(kind) {
    if (kind === heldKind) return;
    heldKind = kind;
    if (heldMesh) {
      handAnchor.remove(heldMesh);
      heldMesh = null;
    }
    if (kind === OBJ.PIERRE) heldMesh = new THREE.Mesh(pierreGeom, pierreMat);
    else if (kind === OBJ.BALLON) heldMesh = new THREE.Mesh(ballonGeom, ballonMat);
    if (heldMesh) {
      heldMesh.castShadow = true;
      handAnchor.add(heldMesh);
    }
  }

  let walkPhase = 0;
  let facing = 0;
  let facingTarget = 0;

  const api = { group, handAnchor };

  api.setPosition = function setPosition(x, y, z) {
    group.position.set(x, y, z);
  };

  api.setFacing = function setFacing(angle) {
    facingTarget = angle;
  };

  api.setCarrying = setCarrying;

  api.update = function update(dt, moving) {
    let delta = facingTarget - facing;
    while (delta > Math.PI) delta -= Math.PI * 2;
    while (delta < -Math.PI) delta += Math.PI * 2;
    facing += delta * Math.min(1, dt * 10);
    group.rotation.y = facing;

    if (moving) {
      walkPhase += dt * 9;
      const swing = Math.sin(walkPhase) * 0.55;
      legL.rotation.x = swing;
      legR.rotation.x = -swing;
      armPivotL.rotation.x = -swing * 0.8;
      armPivotR.rotation.x = swing * 0.8;
      body.position.y = Math.abs(Math.sin(walkPhase)) * 0.03;
    } else {
      walkPhase *= 0.85;
      legL.rotation.x *= 0.8;
      legR.rotation.x *= 0.8;
      armPivotL.rotation.x *= 0.8;
      armPivotR.rotation.x *= 0.8;
      body.position.y *= 0.8;
    }
  };

  api.dispose = function dispose() {
    suitMat.dispose();
    skinMat.dispose();
    bootMat.dispose();
    lampMat.dispose();
    legGeom.dispose();
    armGeom.dispose();
    pierreGeom.dispose();
    pierreMat.dispose();
    ballonGeom.dispose();
    ballonMat.dispose();
    torso.geometry.dispose();
    head.geometry.dispose();
    lamp.geometry.dispose();
  };

  return api;
}
