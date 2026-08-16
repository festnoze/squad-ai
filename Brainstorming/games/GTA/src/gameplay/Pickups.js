/**
 * World pickups: health, armour, ammo and weapons.
 *
 * Pickups are scattered on pavements, in car parks and in alleys at load time and then
 * respawn on a timer, so the map stays stocked without an infinite supply at any one
 * spot. Collection is a plain radius test against the player - a sensor collider per
 * pickup would be dozens of extra physics bodies for something a distance check answers
 * exactly as well.
 */

import {
  Group, Mesh, BoxGeometry, CylinderGeometry, TorusGeometry, MeshStandardMaterial,
  MeshBasicMaterial, Color, Vector3, AdditiveBlending, DoubleSide,
} from 'three/webgpu';
import { makeRng } from '../core/Noise.js';

const PICKUP_RADIUS = 1.8;
const RESPAWN_SECONDS = 45;

export const PICKUP_TYPES = {
  health: { colour: 0x57cc99, label: 'Health', amount: 25 },
  armour: { colour: 0x4cc9f0, label: 'Armour', amount: 50 },
  pistol: { colour: 0xffb703, label: 'Pistol', weapon: 'pistol', ammo: 48 },
  smg: { colour: 0xff8c42, label: 'SMG', weapon: 'smg', ammo: 120 },
  shotgun: { colour: 0xe5383b, label: 'Shotgun', weapon: 'shotgun', ammo: 32 },
  rifle: { colour: 0xb388ff, label: 'Rifle', weapon: 'rifle', ammo: 120 },
  ammo: { colour: 0xd8d2c0, label: 'Ammo', ammoOnly: 60 },
};

/* --------------------------------------------------------------------- models */

const geo = {
  cross: new BoxGeometry(0.7, 0.22, 0.22),
  crossB: new BoxGeometry(0.22, 0.7, 0.22),
  vest: new BoxGeometry(0.5, 0.62, 0.28),
  crate: new BoxGeometry(0.6, 0.4, 0.42),
  barrel: new CylinderGeometry(0.22, 0.22, 0.5, 10),
  ring: new TorusGeometry(0.85, 0.05, 6, 24),
};
geo.ring.rotateX(-Math.PI / 2);

function buildIcon(type) {
  const spec = PICKUP_TYPES[type];
  const g = new Group();
  const mat = new MeshStandardMaterial({
    color: new Color(spec.colour),
    emissive: new Color(spec.colour),
    emissiveIntensity: 0.55,
    roughness: 0.4,
    metalness: 0.2,
  });

  if (type === 'health') {
    g.add(new Mesh(geo.cross, mat), new Mesh(geo.crossB, mat));
  } else if (type === 'armour') {
    g.add(new Mesh(geo.vest, mat));
  } else if (type === 'ammo') {
    g.add(new Mesh(geo.crate, mat));
  } else {
    // Weapon pickups: a crate with a barrel across it, tinted per weapon.
    const crate = new Mesh(geo.crate, mat);
    const barrel = new Mesh(geo.barrel, mat);
    barrel.rotation.z = Math.PI / 2;
    barrel.position.y = 0.3;
    g.add(crate, barrel);
  }

  // Ground ring so the pickup reads from a distance.
  const ring = new Mesh(geo.ring, new MeshBasicMaterial({
    color: new Color(spec.colour), transparent: true, opacity: 0.5,
    blending: AdditiveBlending, depthWrite: false, side: DoubleSide,
  }));
  ring.position.y = -0.5;
  g.add(ring);
  g.userData.ring = ring;
  return g;
}

/* -------------------------------------------------------------------- manager */

export class PickupManager {
  /**
   * @param {object} deps `{ scene, city, player, weapons, hud, audio }`
   */
  constructor({ scene, city, player, weapons, hud, audio }, { seed = 777 } = {}) {
    this.scene = scene;
    this.city = city;
    this.player = player;
    this.weapons = weapons;
    this.hud = hud;
    this.audio = audio;
    this.rng = makeRng(seed);

    this.group = new Group();
    this.group.name = 'pickups';
    scene.add(this.group);

    /** @type {Array<object>} */
    this.items = [];
    this.collected = 0;
    this.time = 0;

    this._scatter();
  }

  /** Distribute pickups over the map, weighted so weapons are rarer than health. */
  _scatter() {
    const weights = {
      health: 26, armour: 16, ammo: 20, pistol: 8, smg: 10, shotgun: 10, rifle: 6,
    };
    const bag = [];
    for (const [key, w] of Object.entries(weights)) for (let i = 0; i < w; i++) bag.push(key);

    const blocks = this.city.network.blocks;
    const target = 68;
    let placed = 0, attempts = 0;
    while (placed < target && attempts < target * 30) {
      attempts++;
      const block = blocks[Math.floor(this.rng() * blocks.length)];
      // Tuck them against the block edge, on the pavement.
      const side = Math.floor(this.rng() * 4);
      const t = 0.15 + this.rng() * 0.7;
      let x, z;
      const inset = 1.9;
      if (side === 0) { x = block.x0 + (block.x1 - block.x0) * t; z = block.z0 - inset; }
      else if (side === 1) { x = block.x0 + (block.x1 - block.x0) * t; z = block.z1 + inset; }
      else if (side === 2) { x = block.x0 - inset; z = block.z0 + (block.z1 - block.z0) * t; }
      else { x = block.x1 + inset; z = block.z0 + (block.z1 - block.z0) * t; }

      if (!this.city.isSpawnClear(x, z, 1.0)) continue;
      if (this.items.some((p) => (p.x - x) ** 2 + (p.z - z) ** 2 < 40 * 40)) continue;

      this._add(bag[Math.floor(this.rng() * bag.length)], x, z);
      placed++;
    }
  }

  _add(type, x, z) {
    const mesh = buildIcon(type);
    mesh.position.set(x, 1.15, z);
    this.group.add(mesh);
    this.items.push({ type, x, z, mesh, taken: false, respawn: 0 });
  }

  /**
   * @param {number} dt
   * @param {Vector3} playerPosition
   */
  update(dt, playerPosition) {
    this.time += dt;
    for (const item of this.items) {
      if (item.taken) {
        item.respawn -= dt;
        if (item.respawn <= 0) {
          item.taken = false;
          item.mesh.visible = true;
        }
        continue;
      }

      // Spin and bob. Cheap, and it is what makes a pickup read as collectable.
      item.mesh.rotation.y = this.time * 1.6;
      item.mesh.position.y = 1.15 + Math.sin(this.time * 2.2 + item.x) * 0.12;

      const dx = playerPosition.x - item.x;
      const dz = playerPosition.z - item.z;
      if (dx * dx + dz * dz > PICKUP_RADIUS * PICKUP_RADIUS) continue;
      if (Math.abs(playerPosition.y - 0.2) > 3) continue;
      this._collect(item);
    }
  }

  _collect(item) {
    const spec = PICKUP_TYPES[item.type];
    let took = false;

    if (spec.amount && item.type === 'health') {
      if (this.player.health < 100) { this.player.heal(spec.amount); took = true; }
    } else if (spec.amount && item.type === 'armour') {
      if (this.player.armour < 100) {
        this.player.armour = Math.min(100, this.player.armour + spec.amount);
        took = true;
      }
    } else if (spec.weapon) {
      // A weapon you already own still yields its ammo.
      if (!this.weapons.owned.has(spec.weapon)) this.weapons.give(spec.weapon, spec.ammo);
      else this.weapons.ammo[spec.weapon].reserve += spec.ammo;
      took = true;
    } else if (spec.ammoOnly) {
      const current = this.weapons.current;
      if (current !== 'unarmed') {
        this.weapons.ammo[current].reserve += spec.ammoOnly;
        took = true;
      }
    }

    if (!took) return;
    this.collected++;
    item.taken = true;
    item.respawn = RESPAWN_SECONDS;
    item.mesh.visible = false;
    this.audio?.pickup();
    this.hud.say(spec.label, 1.6);
  }

  /** Radar blips for nearby pickups. */
  blips(focus, radius = 160) {
    const out = [];
    for (const item of this.items) {
      if (item.taken) continue;
      if (Math.abs(item.x - focus.x) > radius || Math.abs(item.z - focus.z) > radius) continue;
      out.push({ x: item.x, z: item.z, kind: 'pickup', size: 2 });
    }
    return out;
  }

  get available() { return this.items.filter((i) => !i.taken).length; }
}
