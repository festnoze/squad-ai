/**
 * PONTS DE FORTUNE - convoy meshes.
 *
 * Simple boxes, but proportioned so a truck reads as a truck at a glance: the
 * player has to recognise the load before deciding whether the bridge can take
 * it. Wheels spin with the distance travelled and the body follows the deck
 * slope and twist.
 */

import * as THREE from 'three';
import { VEHICLES } from '../config.js';

const WHEEL_R = 0.55;

function box(w, h, d, color, rough, metal) {
  const g = new THREE.BoxGeometry(w, h, d);
  const m = new THREE.MeshStandardMaterial({
    color, roughness: rough === undefined ? 0.6 : rough, metalness: metal === undefined ? 0.25 : metal,
  });
  const mesh = new THREE.Mesh(g, m);
  mesh.castShadow = true;
  return mesh;
}

function buildCar(def) {
  const g = new THREE.Group();
  const body = box(def.length, 0.85, def.width, def.color, 0.45, 0.35);
  body.position.y = WHEEL_R + 0.45;
  g.add(body);
  const cabin = box(def.length * 0.5, 0.62, def.width * 0.9, def.accent, 0.28, 0.1);
  cabin.position.set(-0.2, WHEEL_R + 1.15, 0);
  g.add(cabin);
  const glass = box(def.length * 0.46, 0.4, def.width * 0.94, 0x9fd4e8, 0.15, 0.05);
  glass.position.set(-0.2, WHEEL_R + 1.2, 0);
  g.add(glass);
  const lamp = box(0.2, 0.24, def.width * 0.7, 0xfff2c0, 0.3, 0);
  lamp.material.emissive = new THREE.Color(0xffe9a8);
  lamp.material.emissiveIntensity = 0.9;
  lamp.position.set(def.length * 0.5 - 0.1, WHEEL_R + 0.5, 0);
  g.add(lamp);
  return { group: g, wheelRows: [[def.length * 0.32, def.width * 0.52], [-def.length * 0.32, def.width * 0.52]] };
}

function buildTruck(def) {
  const g = new THREE.Group();
  const cab = box(def.length * 0.3, 1.9, def.width, def.color, 0.45, 0.3);
  cab.position.set(def.length * 0.33, WHEEL_R + 1.15, 0);
  g.add(cab);
  const glass = box(0.18, 0.7, def.width * 0.88, 0x8fc8de, 0.15, 0.05);
  glass.position.set(def.length * 0.48, WHEEL_R + 1.65, 0);
  g.add(glass);
  const chassis = box(def.length * 0.94, 0.32, def.width * 0.82, 0x33383e, 0.7, 0.3);
  chassis.position.set(-0.2, WHEEL_R + 0.28, 0);
  g.add(chassis);
  const load = box(def.length * 0.62, def.height - 1.3, def.width, def.accent, 0.75, 0.12);
  load.position.set(-def.length * 0.2, WHEEL_R + 0.45 + (def.height - 1.3) * 0.5, 0);
  g.add(load);
  const stripe = box(def.length * 0.63, 0.22, def.width + 0.06, 0xe8e2cf, 0.6, 0.05);
  stripe.position.set(-def.length * 0.2, WHEEL_R + 1.4, 0);
  g.add(stripe);
  const beacon = box(0.4, 0.22, 0.4, 0xffb020, 0.4, 0);
  beacon.material.emissive = new THREE.Color(0xffa000);
  beacon.material.emissiveIntensity = 1.4;
  beacon.position.set(def.length * 0.33, WHEEL_R + 2.2, 0);
  g.add(beacon);
  return {
    group: g,
    wheelRows: [
      [def.length * 0.34, def.width * 0.5],
      [-def.length * 0.18, def.width * 0.5],
      [-def.length * 0.36, def.width * 0.5],
    ],
    beacon,
  };
}

export function createVehicleView(scene) {
  const group = new THREE.Group();
  scene.add(group);
  const built = [];
  const wheelGeo = new THREE.CylinderGeometry(WHEEL_R, WHEEL_R, 0.36, 12);
  wheelGeo.rotateX(Math.PI / 2);
  const wheelMat = new THREE.MeshStandardMaterial({ color: 0x1e2126, roughness: 0.85, metalness: 0.1 });
  // Shared, built once, never disposed until the view itself goes away. The
  // per vehicle boxes are the opposite: a new set on every convoy, so they have
  // to be released on the way out or a long session leaks a mesh per test run.
  const shared = [wheelGeo, wheelMat];

  function clear() {
    for (let i = 0; i < built.length; i++) {
      const made = built[i];
      group.remove(made.group);
      for (let k = 0; k < made.owned.length; k++) made.owned[k].dispose();
      made.owned.length = 0;
    }
    built.length = 0;
  }

  function setConvoy(vehicles) {
    clear();
    for (let i = 0; i < vehicles.length; i++) {
      const def = VEHICLES[vehicles[i].key] || VEHICLES.car;
      const made = def.key === 'truck' ? buildTruck(def) : buildCar(def);
      const wheels = [];
      for (const row of made.wheelRows) {
        for (const sz of [-1, 1]) {
          const w = new THREE.Mesh(wheelGeo, wheelMat);
          w.position.set(row[0], WHEEL_R, sz * row[1]);
          w.castShadow = true;
          made.group.add(w);
          wheels.push(w);
        }
      }
      made.wheels = wheels;
      const owned = [];
      made.group.traverse((o) => {
        if (!o.isMesh) return;
        if (o.geometry && shared.indexOf(o.geometry) < 0 && owned.indexOf(o.geometry) < 0) owned.push(o.geometry);
        if (o.material && shared.indexOf(o.material) < 0 && owned.indexOf(o.material) < 0) owned.push(o.material);
      });
      made.owned = owned;
      group.add(made.group);
      built.push(made);
    }
  }

  function sync(vehicles) {
    for (let i = 0; i < built.length && i < vehicles.length; i++) {
      const v = vehicles[i];
      const m = built[i];
      m.group.position.set(v.x, v.y + 0.21, v.z);
      m.group.rotation.set(v.roll, 0, v.pitch);
      for (let k = 0; k < m.wheels.length; k++) m.wheels[k].rotation.z = -v.wheelSpin / WHEEL_R;
      if (m.beacon) {
        m.beacon.material.emissiveIntensity = 0.6 + Math.abs(Math.sin(v.wheelSpin * 0.9)) * 1.6;
      }
      m.group.visible = true;
    }
  }

  function setVisible(v) { group.visible = v; }

  function dispose() {
    clear();
    scene.remove(group);
    for (let i = 0; i < shared.length; i++) shared[i].dispose();
    shared.length = 0;
  }

  return { setConvoy, sync, setVisible, dispose, group };
}
