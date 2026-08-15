/**
 * ABYSSE - the research submersible.
 *
 * The sub is both the player's safe house (oxygen, ammo, repairs) and the
 * vehicle that carries specimens up to the island laboratory. It never moves
 * under player control: it sits at its anchor point, and once you decide to
 * surface it follows a fixed path up to the dock with the diver riding inside.
 *
 * States:
 *   'deep'      parked on the reef, the diver can dock and unload
 *   'ascending' running the path from the anchor to the island dock
 *   'surface'   moored at the dock, the diver can climb out onto the island
 *   'descending' running the path back down
 */

import * as THREE from 'three';
import { SUB, WORLD, PALETTE, clamp01, springK } from './config.js';

const _v1 = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _q1 = new THREE.Quaternion();
const _m1 = new THREE.Matrix4();
const _up = new THREE.Vector3(0, 1, 0);

// ---------------------------------------------------------------------------
// Mesh
// ---------------------------------------------------------------------------

function buildSub(textures) {
  const group = new THREE.Group();

  const hullMat = new THREE.MeshStandardMaterial({
    color: PALETTE.hull,
    roughness: 0.55,
    metalness: 0.55,
    map: textures.hullPanel || null,
  });
  const darkMat = new THREE.MeshStandardMaterial({
    color: PALETTE.hullDark,
    roughness: 0.6,
    metalness: 0.7,
  });
  const steelMat = new THREE.MeshStandardMaterial({ color: 0x9aa6ae, roughness: 0.35, metalness: 0.9 });
  const glassMat = new THREE.MeshStandardMaterial({
    color: PALETTE.glass,
    roughness: 0.05,
    metalness: 0.1,
    transparent: true,
    opacity: 0.42,
    envMapIntensity: 1.4,
  });
  const emissiveMat = new THREE.MeshBasicMaterial({ color: 0xfff2c4 });
  const beaconMat = new THREE.MeshBasicMaterial({ color: 0xff4d5e });

  const L = SUB.hullLength;
  const R = SUB.hullRadius;

  // Main pressure hull: a capsule with a tapered nose.
  const hull = new THREE.Mesh(new THREE.CapsuleGeometry(R, L - R * 2, 8, 20), hullMat);
  hull.rotation.x = Math.PI / 2;
  group.add(hull);

  // A yellow band and a dark keel strip give the hull some read at distance.
  const band = new THREE.Mesh(new THREE.CylinderGeometry(R * 1.02, R * 1.02, 1.4, 20, 1, true), darkMat);
  band.rotation.x = Math.PI / 2;
  band.position.z = 1.2;
  group.add(band);

  // Nose cone with the observation dome.
  const nose = new THREE.Mesh(new THREE.ConeGeometry(R, 3.4, 20), hullMat);
  nose.rotation.x = -Math.PI / 2;
  nose.position.z = -L / 2 - 1.1;
  group.add(nose);

  const dome = new THREE.Mesh(new THREE.SphereGeometry(R * 0.78, 20, 16), glassMat);
  dome.position.z = -L / 2 - 0.2;
  dome.scale.z = 1.25;
  group.add(dome);

  const domeRing = new THREE.Mesh(new THREE.TorusGeometry(R * 0.78, 0.14, 8, 24), steelMat);
  domeRing.position.z = -L / 2 + 0.4;
  group.add(domeRing);

  // Conning tower with a hatch.
  const tower = new THREE.Mesh(new THREE.BoxGeometry(2.4, 2.6, 4.2), hullMat);
  tower.position.set(0, R + 0.9, 0.6);
  group.add(tower);
  const towerTop = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.1, 0.5, 14), darkMat);
  towerTop.position.set(0, R + 2.3, 0.6);
  group.add(towerTop);
  const periscope = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 2.6, 8), steelMat);
  periscope.position.set(0.45, R + 3.4, 0.2);
  group.add(periscope);
  const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 3.4, 6), steelMat);
  antenna.position.set(-0.5, R + 3.8, 1.4);
  group.add(antenna);

  // Side windows along the hull.
  for (let i = 0; i < 4; i++) {
    for (let s = -1; s <= 1; s += 2) {
      const port = new THREE.Mesh(new THREE.CircleGeometry(0.42, 14), glassMat);
      port.position.set(s * (R - 0.05), 0.5, -3.5 + i * 2.4);
      port.rotation.y = (s * Math.PI) / 2;
      group.add(port);
      const rim = new THREE.Mesh(new THREE.TorusGeometry(0.44, 0.06, 6, 16), steelMat);
      rim.position.copy(port.position);
      rim.rotation.y = (s * Math.PI) / 2;
      group.add(rim);
    }
  }

  // Ballast tanks on the flanks.
  for (let s = -1; s <= 1; s += 2) {
    const tank = new THREE.Mesh(new THREE.CapsuleGeometry(0.85, 8.5, 6, 12), darkMat);
    tank.rotation.x = Math.PI / 2;
    tank.position.set(s * (R + 0.5), -1.1, 0.5);
    group.add(tank);
  }

  // Stern: shroud, propeller and dive planes.
  const shroud = new THREE.Mesh(new THREE.CylinderGeometry(2.0, 2.0, 1.6, 18, 1, true), darkMat);
  shroud.rotation.x = Math.PI / 2;
  shroud.position.z = L / 2 + 1.2;
  shroud.material.side = THREE.DoubleSide;
  group.add(shroud);

  const propeller = new THREE.Group();
  const hubGeo = new THREE.CylinderGeometry(0.32, 0.32, 0.6, 10);
  const hub = new THREE.Mesh(hubGeo, steelMat);
  hub.rotation.x = Math.PI / 2;
  propeller.add(hub);
  for (let i = 0; i < 5; i++) {
    const blade = new THREE.Mesh(new THREE.BoxGeometry(0.14, 1.5, 0.5), steelMat);
    blade.position.set(0, 0.85, 0);
    blade.rotation.set(0.5, 0, 0);
    const arm = new THREE.Group();
    arm.add(blade);
    arm.rotation.z = (i / 5) * Math.PI * 2;
    propeller.add(arm);
  }
  propeller.position.z = L / 2 + 1.2;
  group.add(propeller);

  for (let i = 0; i < 4; i++) {
    const fin = new THREE.Mesh(new THREE.BoxGeometry(0.18, 3.2, 1.5), hullMat);
    fin.position.z = L / 2 - 0.4;
    const arm = new THREE.Group();
    arm.add(fin);
    arm.rotation.z = (i / 4) * Math.PI * 2 + Math.PI / 4;
    group.add(arm);
  }

  // Headlights on a rail above the dome.
  const lightRail = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.3, 0.4), darkMat);
  lightRail.position.set(0, R * 0.6, -L / 2 - 0.6);
  group.add(lightRail);

  const lamps = [];
  for (let s = -1; s <= 1; s += 2) {
    const housing = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.38, 0.5, 12), darkMat);
    housing.rotation.x = Math.PI / 2;
    housing.position.set(s * 1.8, R * 0.6, -L / 2 - 0.9);
    group.add(housing);
    const lens = new THREE.Mesh(new THREE.CircleGeometry(0.3, 12), emissiveMat);
    lens.position.set(s * 1.8, R * 0.6, -L / 2 - 1.16);
    group.add(lens);

    const spot = new THREE.SpotLight(0xfff0cc, 5.5, 95, 0.5, 0.5, 1.2);
    spot.position.set(s * 1.8, R * 0.6, -L / 2 - 1.2);
    spot.target.position.set(s * 2.6, -2, -L / 2 - 40);
    group.add(spot);
    group.add(spot.target);
    lamps.push({ spot, lens });
  }

  // Cargo bay: an open hatch on the back with a lit interior, the drop point.
  const bay = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.4, 3.6), darkMat);
  bay.position.set(0, R - 0.3, 4.6);
  group.add(bay);
  const bayGlow = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 3.2), new THREE.MeshBasicMaterial({
    color: 0x64f0a8,
    transparent: true,
    opacity: 0.45,
    side: THREE.DoubleSide,
    depthWrite: false,
  }));
  bayGlow.rotation.x = -Math.PI / 2;
  bayGlow.position.set(0, R - 0.05, 4.6);
  group.add(bayGlow);
  const bayLight = new THREE.PointLight(0x64f0a8, 3.5, 16, 1.6);
  bayLight.position.set(0, R + 1.2, 4.6);
  group.add(bayLight);

  // Docking beacon, blinks so you can find the sub in murky water.
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.3, 10, 8), beaconMat);
  beacon.position.set(0, R + 2.7, 0.6);
  group.add(beacon);
  const beaconLight = new THREE.PointLight(0xff4d5e, 4, 60, 1.4);
  beaconLight.position.copy(beacon.position);
  group.add(beaconLight);

  // Manipulator arm, folded against the hull.
  const armBase = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.45, 0.6, 10), steelMat);
  armBase.position.set(-R * 0.7, -R * 0.6, -4.5);
  armBase.rotation.z = Math.PI / 2;
  group.add(armBase);
  const armSeg = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.22, 3.2, 8), steelMat);
  armSeg.position.set(-R * 0.9, -R * 0.9, -5.6);
  armSeg.rotation.set(0.7, 0, 0.4);
  group.add(armSeg);

  return {
    group,
    propeller,
    lamps,
    beacon,
    beaconLight,
    bayGlow,
    bayLight,
    materials: [hullMat, darkMat, steelMat, glassMat, emissiveMat, beaconMat],
    // Where the diver sits during a transit, in local space.
    seatLocal: new THREE.Vector3(0, R * 0.35, -L / 2 + 1.6),
    // Where the docking prompt triggers, in local space.
    dockLocal: new THREE.Vector3(0, R - 0.2, 4.6),
  };
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createSub(scene, world, textures) {
  const built = buildSub(textures);
  const group = built.group;
  scene.add(group);

  const anchor = new THREE.Vector3(WORLD.subAnchor.x, WORLD.subAnchor.y, WORLD.subAnchor.z);
  const dock = new THREE.Vector3(WORLD.subDock.x, WORLD.subDock.y, WORLD.subDock.z);

  // Keep the anchor clear of the seabed even if the terrain generator moved.
  const anchorGround = world.heightAt(anchor.x, anchor.z);
  anchor.y = Math.max(anchor.y, anchorGround + SUB.hullRadius + 3.5);

  group.position.copy(anchor);
  group.rotation.y = Math.PI * 0.15;

  /**
   * Path from the reef anchor up to the island dock. The sub climbs almost
   * vertically first, so the ascent reads as a real decompression run, then
   * cruises north just under the surface before mooring.
   */
  const midA = new THREE.Vector3(anchor.x + 20, anchor.y * 0.45, anchor.z - 60);
  const midB = new THREE.Vector3(anchor.x * 0.4 - 10, -6.5, (anchor.z + dock.z) * 0.5);
  const midC = new THREE.Vector3(dock.x + 14, -2.4, dock.z + 70);
  const path = new THREE.CatmullRomCurve3([anchor.clone(), midA, midB, midC, dock.clone()], false, 'catmullrom', 0.3);

  const self = {
    group,
    position: group.position,
    state: 'deep',
    transitT: 0,
    // Filled by main.js so the HUD can show what is stowed.
    cargo: [],
    lightsOn: true,
    seat: new THREE.Vector3(),
    dockPoint: new THREE.Vector3(),
    anchor,
    dock,
    onArrive: null,
  };

  let beaconPhase = 0;
  let propSpin = 0;
  let bubbleTimer = 0;

  /** World space point where the diver docks to unload. */
  function updatePoints() {
    self.dockPoint.copy(built.dockLocal);
    group.localToWorld(self.dockPoint);
    self.seat.copy(built.seatLocal);
    group.localToWorld(self.seat);
  }
  updatePoints();

  function distanceTo(pos) {
    return pos.distanceTo(self.dockPoint);
  }

  function isNear(pos) {
    return self.state !== 'ascending' && self.state !== 'descending' && distanceTo(pos) < SUB.interactRadius;
  }

  /** Begin the trip to the island. */
  function ascend() {
    if (self.state !== 'deep') return false;
    self.state = 'ascending';
    self.transitT = 0;
    return true;
  }

  /** Begin the trip back to the reef. */
  function descend() {
    if (self.state !== 'surface') return false;
    self.state = 'descending';
    self.transitT = 0;
    return true;
  }

  function update(dt, ctx) {
    const time = ctx && ctx.time ? ctx.time : 0;

    // ------------------------------------------------------------- transit
    if (self.state === 'ascending' || self.state === 'descending') {
      self.transitT = Math.min(1, self.transitT + dt / SUB.transitTime);
      // Ease in and out so the sub does not snap into motion.
      const e = self.transitT * self.transitT * (3 - 2 * self.transitT);
      const t = self.state === 'ascending' ? e : 1 - e;
      path.getPointAt(t, _v1);
      group.position.copy(_v1);

      // Face along the direction of travel.
      path.getTangentAt(t, _v2);
      if (self.state === 'descending') _v2.negate();
      if (_v2.lengthSq() > 1e-5) {
        _v1.copy(group.position).add(_v2);
        _m1.lookAt(group.position, _v1, _up);
        _q1.setFromRotationMatrix(_m1);
        // The mesh points down -Z, which is what lookAt gives us.
        group.quaternion.slerp(_q1, springK(4, dt));
      }
      // Bank slightly into the climb.
      group.rotation.z = Math.sin(self.transitT * Math.PI) * 0.12 * (self.state === 'ascending' ? 1 : -1);

      propSpin += dt * 26;

      if (self.transitT >= 1) {
        self.state = self.state === 'ascending' ? 'surface' : 'deep';
        self.transitT = 0;
        if (self.state === 'surface') {
          group.position.copy(dock);
          group.rotation.set(0, Math.PI * 0.5, 0);
        } else {
          group.position.copy(anchor);
          group.rotation.set(0, Math.PI * 0.15, 0);
        }
        if (typeof self.onArrive === 'function') self.onArrive(self.state);
      }
    } else {
      // Idle drift, a slow bob on the mooring.
      const bobY = Math.sin(time * 0.55) * 0.22;
      const rollZ = Math.sin(time * 0.42) * 0.02;
      const base = self.state === 'surface' ? dock : anchor;
      group.position.y = base.y + bobY;
      group.rotation.z = rollZ;
      group.rotation.x = Math.sin(time * 0.33) * 0.015;
      propSpin += dt * 1.6;
    }

    built.propeller.rotation.z = propSpin;
    updatePoints();

    // -------------------------------------------------------------- lights
    beaconPhase += dt;
    const blink = beaconPhase % 1.6 < 0.22 ? 1 : 0.06;
    built.beacon.material.color.setRGB(blink, blink * 0.18, blink * 0.22);
    built.beaconLight.intensity = 1.2 + blink * 5;

    const underwater = group.position.y < -2;
    const lampsOn = self.lightsOn && underwater;
    for (let i = 0; i < built.lamps.length; i++) {
      built.lamps[i].spot.intensity = lampsOn ? 5.5 : 0.2;
      built.lamps[i].lens.material.color.setScalar(lampsOn ? 1 : 0.25);
    }
    built.bayLight.intensity = 2.2 + Math.sin(time * 2.4) * 0.5;
    built.bayGlow.material.opacity = 0.32 + Math.sin(time * 2.4) * 0.1;

    // -------------------------------------------------------------- bubbles
    if (ctx && ctx.onBubbles && underwater) {
      bubbleTimer -= dt;
      if (bubbleTimer <= 0) {
        bubbleTimer = self.state === 'ascending' || self.state === 'descending' ? 0.06 : 1.4;
        _v1.set(0, -SUB.hullRadius * 0.4, SUB.hullLength / 2 + 1.4);
        group.localToWorld(_v1);
        ctx.onBubbles(_v1, self.state === 'deep' ? 3 : 12, 1.1);
      }
    }
  }

  function dispose() {
    scene.remove(group);
    for (let i = 0; i < built.materials.length; i++) built.materials[i].dispose();
    group.traverse((o) => {
      if (o.isMesh && o.geometry) o.geometry.dispose();
    });
  }

  Object.assign(self, { update, dispose, isNear, distanceTo, ascend, descend, path });
  return self;
}
