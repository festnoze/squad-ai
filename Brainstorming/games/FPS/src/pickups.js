import * as THREE from 'three';

const boxGeo = new THREE.BoxGeometry(1, 1, 1);

/** Ammo crates and medkits dropped by the dead. They bob, spin and glow. */
export class PickupManager {
  constructor(scene, audio) {
    this.scene = scene;
    this.audio = audio;
    this.items = [];
    this.pool = [];
    this.t = 0;

    this.mats = {
      ammoBody: new THREE.MeshStandardMaterial({ color: 0x3d4a2e, roughness: 0.85 }),
      ammoTrim: new THREE.MeshStandardMaterial({ color: 0xc9a227, roughness: 0.4, metalness: 0.7, emissive: 0x3a2c00 }),
      medBody: new THREE.MeshStandardMaterial({ color: 0xd8d3c6, roughness: 0.9 }),
      medTrim: new THREE.MeshStandardMaterial({ color: 0xc02a22, roughness: 0.6, emissive: 0x4a0a06 }),
    };
  }

  _build(type) {
    const g = new THREE.Group();
    if (type === 'ammo') {
      const body = new THREE.Mesh(boxGeo, this.mats.ammoBody);
      body.scale.set(0.44, 0.26, 0.30);
      body.castShadow = true;
      g.add(body);
      const lid = new THREE.Mesh(boxGeo, this.mats.ammoBody);
      lid.scale.set(0.46, 0.05, 0.32);
      lid.position.y = 0.15;
      g.add(lid);
      for (const s of [-1, 1]) {
        const round = new THREE.Mesh(boxGeo, this.mats.ammoTrim);
        round.scale.set(0.05, 0.14, 0.05);
        round.position.set(s * 0.10, 0.22, 0);
        g.add(round);
      }
      const light = new THREE.PointLight(0xffc453, 1.6, 3.5, 2);
      light.position.y = 0.3;
      g.add(light);
    } else {
      const body = new THREE.Mesh(boxGeo, this.mats.medBody);
      body.scale.set(0.36, 0.26, 0.26);
      body.castShadow = true;
      g.add(body);
      const cross1 = new THREE.Mesh(boxGeo, this.mats.medTrim);
      cross1.scale.set(0.22, 0.07, 0.28);
      cross1.position.y = 0.02;
      g.add(cross1);
      const cross2 = new THREE.Mesh(boxGeo, this.mats.medTrim);
      cross2.scale.set(0.07, 0.22, 0.28);
      cross2.position.y = 0.02;
      g.add(cross2);
      const light = new THREE.PointLight(0xff5a4a, 1.6, 3.5, 2);
      light.position.y = 0.3;
      g.add(light);
    }
    this.scene.add(g);
    return g;
  }

  spawn(type, position) {
    let item = this.pool.find((p) => !p.active && p.type === type);
    if (!item) {
      item = { type, group: this._build(type), active: false, life: 0, baseY: 0, phase: 0 };
      this.pool.push(item);
    }
    item.active = true;
    item.life = 45;
    item.baseY = position.y + 0.55;
    item.phase = Math.random() * 6.28;
    item.group.position.set(position.x, item.baseY, position.z);
    item.group.visible = true;
    if (!this.items.includes(item)) this.items.push(item);
    return item;
  }

  /** onCollect(type) should return true when the pickup is consumed. */
  update(dt, player, onCollect) {
    this.t += dt;
    for (let i = this.items.length - 1; i >= 0; i--) {
      const it = this.items[i];
      if (!it.active) { this.items.splice(i, 1); continue; }
      it.life -= dt;
      it.group.rotation.y += dt * 1.5;
      it.group.position.y = it.baseY + Math.sin(this.t * 2.2 + it.phase) * 0.09;

      // blink out in the last few seconds
      if (it.life < 5) it.group.visible = Math.sin(it.life * 14) > -0.35;

      if (it.life <= 0) {
        it.active = false;
        it.group.visible = false;
        this.items.splice(i, 1);
        continue;
      }
      const dx = it.group.position.x - player.position.x;
      const dz = it.group.position.z - player.position.z;
      const dy = it.group.position.y - (player.position.y + 0.9);
      if (dx * dx + dz * dz < 1.7 * 1.7 && Math.abs(dy) < 2) {
        if (onCollect(it.type)) {
          this.audio.pickup();
          it.active = false;
          it.group.visible = false;
          this.items.splice(i, 1);
        }
      }
    }
  }

  reset() {
    for (const it of this.pool) {
      it.active = false;
      it.group.visible = false;
    }
    this.items.length = 0;
  }
}
