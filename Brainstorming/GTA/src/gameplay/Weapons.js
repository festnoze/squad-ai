/**
 * Weapons and shooting.
 *
 * Hitscan: every shot is a ray from the camera through the crosshair, resolved against
 * the physics world. Whatever the ray hits is looked up in the collider-owner registry,
 * so the same code path handles pedestrians, vehicles, police and scenery without any
 * per-target special casing at the call site.
 *
 * Visual feedback (muzzle flash, tracer, impact spark) comes from small fixed pools that
 * are recycled rather than allocated per shot - a fully automatic weapon would otherwise
 * churn hundreds of objects a second.
 */

import {
  Group, Mesh, BoxGeometry, CylinderGeometry, SphereGeometry, MeshBasicMaterial,
  MeshStandardMaterial, Color, Vector3, AdditiveBlending, MathUtils,
} from 'three/webgpu';
import { GROUP, groups } from '../physics/Physics.js';
import { CRIME } from './Wanted.js';

export const WEAPONS = {
  unarmed: {
    label: 'Unarmed', damage: 0, rpm: 0, magazine: 0, auto: false, range: 0,
  },
  pistol: {
    label: 'Pistol',
    damage: 26,
    rpm: 320,
    spread: 0.012,
    range: 140,
    magazine: 12,
    reserve: 96,
    reloadTime: 1.35,
    pellets: 1,
    auto: false,
    recoil: 0.022,
    heat: CRIME.PED_KILL,
  },
  smg: {
    label: 'SMG',
    damage: 17,
    rpm: 780,
    spread: 0.034,
    range: 110,
    magazine: 30,
    reserve: 210,
    reloadTime: 1.8,
    pellets: 1,
    auto: true,
    recoil: 0.016,
    heat: CRIME.PED_KILL,
  },
  shotgun: {
    label: 'Shotgun',
    damage: 13,
    rpm: 75,
    spread: 0.075,
    range: 45,
    magazine: 8,
    reserve: 48,
    reloadTime: 2.6,
    pellets: 8,
    auto: false,
    recoil: 0.09,
    heat: CRIME.PED_KILL,
  },
  rifle: {
    label: 'Rifle',
    damage: 32,
    rpm: 560,
    spread: 0.019,
    range: 220,
    magazine: 30,
    reserve: 180,
    reloadTime: 2.1,
    pellets: 1,
    auto: true,
    recoil: 0.028,
    heat: CRIME.PED_KILL,
  },
};

export const WEAPON_ORDER = ['unarmed', 'pistol', 'smg', 'shotgun', 'rifle'];

/* --------------------------------------------------------------- weapon models */

const gunMetal = new MeshStandardMaterial({ color: 0x22262c, roughness: 0.42, metalness: 0.85 });
const gunGrip = new MeshStandardMaterial({ color: 0x14161a, roughness: 0.85, metalness: 0.1 });

/** Blocky but readable weapon models, held in the player's right hand. */
function buildWeaponMesh(kind) {
  const g = new Group();
  const add = (w, h, d, x, y, z, mat = gunMetal) => {
    const m = new Mesh(new BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    m.castShadow = true;
    g.add(m);
    return m;
  };

  switch (kind) {
    case 'pistol':
      add(0.05, 0.09, 0.2, 0, 0, 0.06);           // slide
      add(0.045, 0.12, 0.06, 0, -0.1, -0.01, gunGrip);
      break;
    case 'smg':
      add(0.05, 0.08, 0.3, 0, 0, 0.1);
      add(0.04, 0.16, 0.05, 0, -0.11, 0.0, gunGrip);
      add(0.035, 0.13, 0.04, 0, -0.09, 0.09, gunGrip);   // magazine
      add(0.03, 0.05, 0.16, 0, 0.02, -0.12);             // stock
      break;
    case 'shotgun':
      add(0.05, 0.07, 0.5, 0, 0, 0.18);
      add(0.045, 0.05, 0.18, 0, -0.06, 0.14);            // pump
      add(0.04, 0.13, 0.06, 0, -0.09, -0.04, gunGrip);
      add(0.04, 0.08, 0.2, 0, -0.02, -0.16, gunGrip);
      break;
    case 'rifle':
      add(0.05, 0.09, 0.42, 0, 0, 0.16);
      add(0.04, 0.17, 0.05, 0, -0.12, 0.02, gunGrip);
      add(0.04, 0.14, 0.05, 0, -0.1, 0.11, gunGrip);
      add(0.035, 0.07, 0.22, 0, 0.0, -0.16, gunGrip);
      add(0.02, 0.03, 0.1, 0, 0.06, 0.05);               // sight
      break;
    default:
      return null;
  }
  return g;
}

/* --------------------------------------------------------------------- effects */

const tracerGeo = new CylinderGeometry(0.022, 0.022, 1, 5, 1, true);
tracerGeo.rotateX(Math.PI / 2);   // align with +Z so we can lookAt the impact point
const flashGeo = new SphereGeometry(0.11, 8, 6);
const sparkGeo = new SphereGeometry(0.05, 6, 4);

class EffectPool {
  constructor(scene, size, geometry, colour, blending = AdditiveBlending) {
    this.items = [];
    for (let i = 0; i < size; i++) {
      const mesh = new Mesh(geometry, new MeshBasicMaterial({
        color: new Color(colour), transparent: true, opacity: 0,
        blending, depthWrite: false,
      }));
      mesh.visible = false;
      mesh.frustumCulled = false;
      scene.add(mesh);
      this.items.push({ mesh, life: 0, maxLife: 1 });
    }
    this.cursor = 0;
  }

  /** Grab the least-recently-used slot; oldest effect is recycled when saturated. */
  take() {
    const item = this.items[this.cursor];
    this.cursor = (this.cursor + 1) % this.items.length;
    return item;
  }

  update(dt) {
    for (const item of this.items) {
      if (item.life <= 0) continue;
      item.life -= dt;
      const t = Math.max(0, item.life / item.maxLife);
      item.mesh.material.opacity = t;
      if (item.life <= 0) item.mesh.visible = false;
    }
  }
}

/* ---------------------------------------------------------------------- system */

export class WeaponSystem {
  /**
   * @param {object} deps `{ scene, physics, player, peds, traffic, wanted, hud, cameraRig }`
   */
  constructor({ scene, physics, player, peds, traffic, wanted, hud, cameraRig }) {
    this.scene = scene;
    this.physics = physics;
    this.player = player;
    this.peds = peds;
    this.traffic = traffic;
    this.wanted = wanted;
    this.hud = hud;
    this.cameraRig = cameraRig;

    this.current = 'unarmed';
    /** Per-weapon ammo state, so switching does not reset a magazine. */
    this.ammo = {};
    for (const key of WEAPON_ORDER) {
      const spec = WEAPONS[key];
      this.ammo[key] = { magazine: spec.magazine ?? 0, reserve: spec.reserve ?? 0 };
    }
    // The player starts with a pistol; the rest are picked up.
    this.owned = new Set(['unarmed', 'pistol']);

    this.cooldown = 0;
    this.reloading = 0;
    this.kills = 0;
    this.shotsFired = 0;

    // Weapon meshes live in the character's right hand.
    this.meshes = {};
    this.hand = player.character.arms.right.hand;
    for (const key of WEAPON_ORDER) {
      const mesh = buildWeaponMesh(key);
      if (!mesh) continue;
      mesh.visible = false;
      mesh.position.set(0, -0.06, 0.04);
      this.hand.add(mesh);
      this.meshes[key] = mesh;
    }

    this.tracers = new EffectPool(scene, 24, tracerGeo, 0xffd9a0);
    this.flashes = new EffectPool(scene, 8, flashGeo, 0xfff0c0);
    this.sparks = new EffectPool(scene, 16, sparkGeo, 0xffc070);

    this._origin = new Vector3();
    this._dir = new Vector3();
    this._spread = new Vector3();
    this._mid = new Vector3();
    this._filter = groups(
      GROUP.BULLET,
      GROUP.PED | GROUP.VEHICLE | GROUP.BUILDING | GROUP.STATIC | GROUP.TERRAIN | GROUP.PROP,
    );
  }

  get spec() { return WEAPONS[this.current]; }
  get isArmed() { return this.current !== 'unarmed'; }
  get magazine() { return this.ammo[this.current]?.magazine ?? 0; }
  get reserve() { return this.ammo[this.current]?.reserve ?? 0; }

  /** Give the player a weapon (and ammo), e.g. from a pickup. */
  give(kind, ammo = 0) {
    if (!WEAPONS[kind]) return false;
    this.owned.add(kind);
    this.ammo[kind].reserve += ammo || WEAPONS[kind].reserve || 0;
    this.hud.say(`${WEAPONS[kind].label} acquired`, 2.5);
    return true;
  }

  /** Cycle to the next owned weapon. */
  next() {
    const owned = WEAPON_ORDER.filter((k) => this.owned.has(k));
    const i = owned.indexOf(this.current);
    this.select(owned[(i + 1) % owned.length]);
  }

  select(kind) {
    if (!this.owned.has(kind)) return;
    this.current = kind;
    this.reloading = 0;
    for (const [key, mesh] of Object.entries(this.meshes)) mesh.visible = key === kind;
  }

  reload() {
    const spec = this.spec;
    if (!this.isArmed || this.reloading > 0) return;
    const state = this.ammo[this.current];
    if (state.magazine >= spec.magazine || state.reserve <= 0) return;
    this.reloading = spec.reloadTime;
  }

  /**
   * @param {number} dt
   * @param {object} input `{ firing, aiming }`
   */
  update(dt, input) {
    this.cooldown = Math.max(0, this.cooldown - dt);
    this.tracers.update(dt);
    this.flashes.update(dt);
    this.sparks.update(dt);

    if (this.reloading > 0) {
      this.reloading -= dt;
      if (this.reloading <= 0) this._finishReload();
      return;
    }

    if (!this.isArmed || !input.firing) return;
    // Semi-automatic weapons need the trigger released between shots.
    if (!this.spec.auto && !input.firePressed) return;
    if (this.cooldown > 0) return;

    const state = this.ammo[this.current];
    if (state.magazine <= 0) {
      this.reload();
      return;
    }
    this._fire();
  }

  _finishReload() {
    const spec = this.spec;
    const state = this.ammo[this.current];
    const needed = spec.magazine - state.magazine;
    const taken = Math.min(needed, state.reserve);
    state.magazine += taken;
    state.reserve -= taken;
  }

  _fire() {
    const spec = this.spec;
    const state = this.ammo[this.current];
    state.magazine--;
    this.cooldown = 60 / spec.rpm;
    this.shotsFired++;

    const camera = this.cameraRig.camera;
    camera.getWorldPosition(this._origin);
    camera.getWorldDirection(this._dir);

    /*
     * Slide the ray origin forward along the aim line until it is level with the player.
     * In third person the camera sits several metres behind them and is regularly inside
     * a wall, a hedge or a tree; a ray started there reports a hit at distance zero and
     * every shot silently lands on whatever the camera is buried in.
     */
    const chestY = this.player.position.y + 1.4;
    const dx = this.player.position.x - this._origin.x;
    const dy = chestY - this._origin.y;
    const dz = this.player.position.z - this._origin.z;
    const skip = Math.max(0, dx * this._dir.x + dy * this._dir.y + dz * this._dir.z);
    this._origin.addScaledVector(this._dir, skip);

    // Muzzle flash at the gun, tracer from the gun - but the ray comes from the camera,
    // so what the crosshair covers is what gets hit.
    const mesh = this.meshes[this.current];
    const muzzle = this._mid.set(0, 0, 0.28);
    if (mesh) mesh.localToWorld(muzzle);
    const flash = this.flashes.take();
    flash.mesh.position.copy(muzzle);
    flash.mesh.visible = true;
    flash.mesh.material.opacity = 1;
    flash.life = flash.maxLife = 0.05;

    for (let p = 0; p < (spec.pellets ?? 1); p++) {
      this._spread.set(
        (Math.random() - 0.5) * spec.spread,
        (Math.random() - 0.5) * spec.spread,
        (Math.random() - 0.5) * spec.spread,
      );
      const dir = this._dir.clone().add(this._spread).normalize();
      const hit = this.physics.raycast(this._origin, dir, spec.range, this._filter, this.player.collider);
      const end = hit ? hit.point : this._origin.clone().addScaledVector(dir, spec.range);
      this._spawnTracer(muzzle, end);
      if (hit) this._resolveHit(hit, spec, dir);
    }

    // Recoil kicks the camera up and slightly sideways.
    this.cameraRig.pitch = MathUtils.clamp(
      this.cameraRig.pitch + spec.recoil, -1.15, 0.95,
    );
    this.cameraRig.yaw += (Math.random() - 0.5) * spec.recoil * 0.7;
    this.cameraRig.shake(spec.recoil * 2.4, 0.12);
    this.onShot?.(this.current);
  }

  _spawnTracer(from, to) {
    const item = this.tracers.take();
    const length = from.distanceTo(to);
    if (length < 0.2) return;
    item.mesh.position.copy(from).lerp(to, 0.5);
    item.mesh.lookAt(to);
    item.mesh.scale.set(1, 1, length);
    item.mesh.visible = true;
    item.mesh.material.opacity = 1;
    item.life = item.maxLife = 0.06;
  }

  _resolveHit(hit, spec, dir) {
    // Impact spark wherever the round lands.
    const spark = this.sparks.take();
    spark.mesh.position.copy(hit.point);
    spark.mesh.visible = true;
    spark.mesh.material.opacity = 1;
    spark.life = spark.maxLife = 0.16;

    const owner = hit.owner;
    if (!owner) return;

    if (owner.isPedestrian) {
      // One clean hit puts a ped down; the crime is reported either way.
      const killed = this.peds.knockDown(owner, dir);
      if (killed) {
        this.kills++;
        this.peds.scatter(owner.position, 26);
        this.wanted.report(spec.heat ?? CRIME.PED_KILL, 'shooting');
      }
      return;
    }

    if (owner.applyDamage) {
      const destroyed = owner.applyDamage(spec.damage * 0.6);
      // Shooting at police escalates fast.
      if (owner.livery === 'police') this.wanted.report(CRIME.POLICE_RAM, 'shooting at police');
      else this.wanted.report(CRIME.VEHICLE_RAM * 0.5, 'vandalism');
      if (destroyed) this.wanted.report(CRIME.PED_KILL, 'destroyed a vehicle');
    }
  }

  /** HUD line: "Pistol  9 / 96", or null when unarmed. */
  get statusLine() {
    if (!this.isArmed) return null;
    if (this.reloading > 0) return `${this.spec.label}  reloading`;
    return `${this.spec.label}  ${this.magazine} / ${this.reserve}`;
  }
}
