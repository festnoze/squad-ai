/**
 * AIGUILLAGE - train meshes, synced every frame from the pure simulation.
 *
 * One pooled THREE.Group per live train id (created lazily, disposed when
 * the train is delivered). A coupled train additionally shows a trailing
 * car derived the same way trains.js derives it: sAbs - dir * coupleGap on
 * the same segment.
 */

import * as THREE from 'three';

const bodyGeo = new THREE.BoxGeometry(3.4, 1.5, 1.7);
const cabGeo = new THREE.BoxGeometry(1.0, 0.55, 1.5);
const wheelGeo = new THREE.CylinderGeometry(0.42, 0.42, 1.8, 10);
wheelGeo.rotateZ(Math.PI / 2);

const scratchPos = new THREE.Vector3();
const scratchAim = new THREE.Vector3();
const scratchFrame = { pos: new THREE.Vector3(), tangent: new THREE.Vector3() };

function makeCarVisual(color, textures) {
  const group = new THREE.Group();
  const bodyMat = new THREE.MeshStandardMaterial({ color, roughness: 0.5, metalness: 0.25 });
  const body = new THREE.Mesh(bodyGeo, bodyMat);
  body.position.y = 1.05;
  group.add(body);

  const cabMat = new THREE.MeshStandardMaterial({ color: 0x1a1d24, roughness: 0.4, metalness: 0.3 });
  const cab = new THREE.Mesh(cabGeo, cabMat);
  cab.position.set(-1.35, 1.68, 0);
  group.add(cab);

  const wheelMat = new THREE.MeshStandardMaterial({ color: 0x14161a, roughness: 0.6, metalness: 0.4 });
  const wA = new THREE.Mesh(wheelGeo, wheelMat);
  wA.position.set(1.0, 0.42, 0);
  const wB = new THREE.Mesh(wheelGeo, wheelMat);
  wB.position.set(-1.0, 0.42, 0);
  group.add(wA, wB);

  const headlight = new THREE.Sprite(new THREE.SpriteMaterial({
    map: textures.glow,
    color: 0xfff2d0,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  }));
  headlight.scale.setScalar(1.1);
  headlight.position.set(-1.85, 1.05, 0);
  group.add(headlight);

  return { group, bodyMat };
}

export function createTrainRender(textures) {
  const group = new THREE.Group();
  const pool = new Map(); // trainId -> { group, bodyMat, rear:{group,bodyMat}|null }

  function ensureEntry(train) {
    let entry = pool.get(train.id);
    if (!entry) {
      const front = makeCarVisual(train.color, textures);
      group.add(front.group);
      entry = { front, rear: null };
      pool.set(train.id, entry);
    }
    return entry;
  }

  function placeCar(carGroup, spline, sAbs, dir) {
    spline.at(sAbs, scratchFrame);
    scratchPos.copy(scratchFrame.pos).setY(0.05);
    carGroup.position.copy(scratchPos);
    const heading = dir >= 0 ? scratchFrame.tangent : scratchAim.copy(scratchFrame.tangent).negate();
    scratchAim.copy(scratchPos).add(heading);
    carGroup.lookAt(scratchAim);
  }

  const trainRender = {
    group,

    sync(simTrains, trackRender, coupleGap) {
      const seen = new Set();
      for (const train of simTrains) {
        if (train.state === 'delivered') continue;
        seen.add(train.id);
        const spline = trackRender.getSpline(train.segmentId);
        if (!spline) continue;
        const entry = ensureEntry(train);
        entry.front.group.visible = true;
        placeCar(entry.front.group, spline, train.sAbs, train.dir);

        if (train.state === 'crashed') {
          const pulse = 0.55 + 0.45 * Math.sin(performance.now() * 0.02);
          entry.front.bodyMat.emissive.setRGB(pulse * 0.6, 0.02, 0.02);
        } else if (entry.front.bodyMat.emissive.r !== 0) {
          entry.front.bodyMat.emissive.setRGB(0, 0, 0);
        }

        if (train.coupledSecondColor) {
          if (!entry.rear) {
            entry.rear = makeCarVisual(train.coupledSecondColor, textures);
            group.add(entry.rear.group);
          }
          const rearSAbs = train.sAbs - train.dir * coupleGap;
          const clamped = Math.max(0, Math.min(spline.length, rearSAbs));
          entry.rear.group.visible = rearSAbs >= 0 && rearSAbs <= spline.length;
          placeCar(entry.rear.group, spline, clamped, train.dir);
        } else if (entry.rear) {
          entry.rear.group.visible = false;
        }
      }

      for (const [id, entry] of pool) {
        if (seen.has(id)) continue;
        group.remove(entry.front.group);
        entry.front.group.traverse((o) => {
          if (o.geometry && o.geometry !== bodyGeo && o.geometry !== cabGeo && o.geometry !== wheelGeo) o.geometry.dispose();
        });
        entry.front.bodyMat.dispose();
        if (entry.rear) {
          group.remove(entry.rear.group);
          entry.rear.bodyMat.dispose();
        }
        pool.delete(id);
      }
    },

    dispose() {
      for (const [, entry] of pool) {
        group.remove(entry.front.group);
        entry.front.bodyMat.dispose();
        if (entry.rear) {
          group.remove(entry.rear.group);
          entry.rear.bodyMat.dispose();
        }
      }
      pool.clear();
      bodyGeo.dispose();
      cabGeo.dispose();
      wheelGeo.dispose();
    },
  };

  return trainRender;
}
