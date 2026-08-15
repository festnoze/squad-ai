import * as THREE from 'three';
import { tileX, tileZ } from './world.js';

const PICKUP_RADIUS = 1.5;

const COLORS = {
  pistol: 0xffc45a,
  shotgun: 0xff8a3a,
  rifle: 0x7fd4ff,
  ammo: 0xd8e24a,
  medkit: 0x4aff7f,
};

/**
 * Weapons, ammo boxes and medkits lying around the prison. Each one bobs and
 * spins over a coloured glow ring so it reads from across a dark corridor.
 */
export class Pickups {
  constructor(scene, world, audio) {
    this.scene = scene;
    this.world = world;
    this.audio = audio;
    this.items = [];
    this.group = new THREE.Group();
    scene.add(this.group);
    this._build();
  }

  _build() {
    for (const def of this.world.pickupDefs) {
      const root = new THREE.Group();
      root.position.set(tileX(def.tile[0]), 0.75, tileZ(def.tile[1]));
      this.group.add(root);

      const model = buildPickupModel(def.kind);
      root.add(model);

      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.42, 0.62, 20),
        new THREE.MeshBasicMaterial({
          color: COLORS[def.kind], transparent: true, opacity: 0.5,
          side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
        })
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = -0.72;
      root.add(ring);

      // A short pillar of light, so pickups are visible from a distance.
      const beam = new THREE.Mesh(
        new THREE.CylinderGeometry(0.24, 0.34, 2.2, 10, 1, true),
        new THREE.MeshBasicMaterial({
          color: COLORS[def.kind], transparent: true, opacity: 0.10,
          side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
        })
      );
      beam.position.y = 0.35;
      root.add(beam);

      this.items.push({
        kind: def.kind,
        amount: def.amount ?? null,
        root, model, ring, beam,
        position: root.position.clone(),
        taken: false,
        phase: Math.random() * Math.PI * 2,
      });
    }
  }

  update(dt, time) {
    for (const it of this.items) {
      if (it.taken) continue;
      it.model.rotation.y += dt * 1.4;
      const bob = Math.sin(time * 2 + it.phase) * 0.09;
      it.model.position.y = bob;
      it.ring.material.opacity = 0.35 + Math.sin(time * 3 + it.phase) * 0.18;
      it.ring.scale.setScalar(1 + Math.sin(time * 3 + it.phase) * 0.08);
    }
  }

  /**
   * Anything the player is standing on. `apply` receives the item and returns
   * a HUD message, or null if the pickup should be left where it is.
   */
  collect(playerPos, apply) {
    const messages = [];
    for (const it of this.items) {
      if (it.taken) continue;
      const dx = it.position.x - playerPos.x;
      const dz = it.position.z - playerPos.z;
      const dy = it.position.y - playerPos.y;
      if (dx * dx + dz * dz > PICKUP_RADIUS * PICKUP_RADIUS) continue;
      if (Math.abs(dy) > 2.2) continue;
      const msg = apply(it);
      if (!msg) continue;
      it.taken = true;
      it.root.visible = false;
      this.audio.pickup();
      messages.push(msg);
    }
    return messages;
  }

  reset() {
    for (const it of this.items) {
      it.taken = false;
      it.root.visible = true;
    }
  }
}

function buildPickupModel(kind) {
  const g = new THREE.Group();
  const steel = new THREE.MeshLambertMaterial({ color: 0x3c4247 });
  const dark = new THREE.MeshLambertMaterial({ color: 0x1e2225 });

  const box = (w, h, d, mat, x, y, z) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    g.add(m);
    return m;
  };

  if (kind === 'pistol') {
    box(0.14, 0.14, 0.52, steel, 0, 0.06, 0);
    box(0.11, 0.26, 0.15, dark, 0, -0.12, 0.12);
  } else if (kind === 'shotgun') {
    box(0.14, 0.14, 1.05, steel, 0, 0.04, 0);
    box(0.12, 0.12, 0.28, dark, 0, -0.10, -0.10);
    box(0.14, 0.20, 0.30, dark, 0, -0.06, 0.42);
  } else if (kind === 'rifle') {
    box(0.14, 0.16, 0.80, steel, 0, 0.04, 0);
    box(0.09, 0.09, 0.55, dark, 0, 0.06, -0.60);
    box(0.10, 0.28, 0.14, dark, 0, -0.16, 0.06);
    box(0.15, 0.16, 0.32, dark, 0, -0.02, 0.48);
  } else if (kind === 'ammo') {
    box(0.55, 0.32, 0.36, new THREE.MeshLambertMaterial({ color: 0x4a5138 }), 0, 0, 0);
    box(0.58, 0.06, 0.39, dark, 0, 0.17, 0);
    box(0.14, 0.05, 0.14, dark, 0, 0.22, 0);
  } else {
    box(0.46, 0.34, 0.36, new THREE.MeshLambertMaterial({ color: 0xe8e4dc }), 0, 0, 0);
    box(0.30, 0.10, 0.38, new THREE.MeshLambertMaterial({ color: 0xd4302f }), 0, 0.02, 0);
    box(0.10, 0.28, 0.38, new THREE.MeshLambertMaterial({ color: 0xd4302f }), 0, 0.02, 0);
  }
  return g;
}
