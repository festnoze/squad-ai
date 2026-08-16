import * as THREE from 'three';
import { moveAABB, rayBox } from './collision.js';

const _v = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _delta = new THREE.Vector3();
const _center = new THREE.Vector3();
const _half = new THREE.Vector3();
const _min = new THREE.Vector3();
const _max = new THREE.Vector3();

export const ENEMY_TYPES = {
  ghoul: {
    label: 'GHOUL',
    health: 95,
    speed: 3.6,
    chargeSpeed: 5.0,
    damage: 11,
    attackRange: 2.35,
    windup: 0.38,
    attackCooldown: 1.3,
    ranged: false,
    scale: 1,
    skin: 0xa8b894,
    cloth: 0x5b564a,
    skinTex: 'skinGhoul',
    clothTex: 'clothDark',
    score: 100,
  },
  raider: {
    label: 'RAIDER',
    health: 75,
    speed: 3.2,
    chargeSpeed: 4.4,
    damage: 9,
    attackRange: 26,
    preferredRange: 15,
    windup: 0.45,
    attackCooldown: 2.3,
    ranged: true,
    burst: 3,
    scale: 1,
    skin: 0x9c7c5e,
    cloth: 0x7d6446,
    skinTex: 'skinRaider',
    clothTex: 'clothBrown',
    score: 150,
  },
  brute: {
    label: 'BRUTE',
    health: 300,
    speed: 2.7,
    chargeSpeed: 3.6,
    damage: 32,
    attackRange: 3.0,
    windup: 0.55,
    attackCooldown: 1.6,
    ranged: false,
    scale: 1.45,
    skin: 0xa4756a,
    cloth: 0x4c4238,
    skinTex: 'skinBrute',
    clothTex: 'clothBlack',
    score: 400,
  },
};

const boxGeo = new THREE.BoxGeometry(1, 1, 1);

/** One hostile. Boxy humanoid, AABB physics, small state machine. */
class Enemy {
  constructor(manager, type) {
    this.manager = manager;
    this.type = type;
    this.def = ENEMY_TYPES[type];
    this.group = new THREE.Group();
    this.group.visible = false;
    manager.scene.add(this.group);

    this.position = new THREE.Vector3();
    this.velocity = new THREE.Vector3();
    this.yaw = 0;
    this.alive = false;
    this.health = 0;
    this.maxHealth = this.def.health;
    this.state = 'idle';
    this.stateTime = 0;
    this.attackTimer = 0;
    this.losTimer = 0;
    this.hasLOS = false;
    this.walkPhase = Math.random() * 6.28;
    this.flash = 0;
    this.deathTime = 0;
    this.strafeSide = Math.random() < 0.5 ? -1 : 1;
    this.avoidTimer = 0;
    this.burstLeft = 0;
    this.burstTimer = 0;
    this.growlTimer = Math.random() * 6;
    this.grounded = false;

    this.headBox = { min: new THREE.Vector3(), max: new THREE.Vector3() };
    this.bodyBox = { min: new THREE.Vector3(), max: new THREE.Vector3() };
    this.legBox = { min: new THREE.Vector3(), max: new THREE.Vector3() };

    this._build();
  }

  _build() {
    const d = this.def;
    const tex = this.manager.tex;
    // The texture already carries the colour, so the material tint stays near
    // white and only varies a little: enough that a pack does not read as one
    // model copied ten times, without crushing them to black.
    const jitter = (hue, spread) => {
      const c = new THREE.Color();
      c.setHSL(
        (hue + (Math.random() - 0.5) * spread + 1) % 1,
        0.05 + Math.random() * 0.12,
        0.62 + Math.random() * 0.22
      );
      return c;
    };
    const skinMat = new THREE.MeshStandardMaterial({
      map: tex ? tex[d.skinTex] : null,
      color: tex ? jitter(0.18, 0.12) : d.skin,
      roughness: 0.92,
    });
    const clothMat = new THREE.MeshStandardMaterial({
      map: tex ? tex[d.clothTex] : null,
      color: tex ? jitter(0.09, 0.16) : d.cloth,
      roughness: 1,
    });
    const darkMat = new THREE.MeshStandardMaterial({
      map: tex ? tex.clothBlack : null, color: 0x8c8478, roughness: 0.85, metalness: 0.2,
    });
    this.skinMat = skinMat;
    this.clothMat = clothMat;
    this.baseSkin = skinMat.color.clone();
    this.baseCloth = clothMat.color.clone();

    const S = d.scale;
    const body = new THREE.Group();
    body.scale.setScalar(S);
    this.group.add(body);
    this.body = body;

    const mk = (mat, x, y, z, sx, sy, sz, parent = body) => {
      const m = new THREE.Mesh(boxGeo, mat);
      m.position.set(x, y, z);
      m.scale.set(sx, sy, sz);
      m.castShadow = true;
      parent.add(m);
      return m;
    };

    // torso, hunched slightly forward
    this.torso = mk(clothMat, 0, 1.12, 0, 0.62, 0.72, 0.36);
    this.torso.rotation.x = 0.12;
    this.torso.userData.bigPart = true;
    mk(skinMat, 0, 1.46, 0.02, 0.44, 0.18, 0.30); // shoulders / neck base

    // head
    this.head = new THREE.Group();
    this.head.position.set(0, 1.62, 0.02);
    body.add(this.head);
    mk(skinMat, 0, 0, 0, 0.30, 0.32, 0.28, this.head).userData.bigPart = true;
    if (this.type === 'raider') {
      // gas mask with two glass lenses
      mk(darkMat, 0, -0.02, 0.14, 0.28, 0.24, 0.06, this.head);
      for (const s of [-1, 1]) {
        const lens = mk(new THREE.MeshStandardMaterial({ color: 0x2f4a3a, roughness: 0.3, metalness: 0.6 }),
          s * 0.075, 0.02, 0.175, 0.09, 0.09, 0.03, this.head);
        lens.name = 'lens';
      }
      mk(darkMat, 0, -0.10, 0.16, 0.12, 0.10, 0.10, this.head); // filter canister
      mk(clothMat, 0, 0.14, -0.02, 0.34, 0.10, 0.32, this.head); // hood rim
    } else {
      // sunken glowing eyes
      for (const s of [-1, 1]) {
        const eye = mk(new THREE.MeshBasicMaterial({ color: this.type === 'brute' ? 0xff5a2a : 0xd8ff6a }),
          s * 0.07, 0.03, 0.145, 0.05, 0.035, 0.02, this.head);
        eye.name = 'eye';
      }
      mk(darkMat, 0, -0.09, 0.14, 0.14, 0.06, 0.03, this.head); // maw
    }

    if (this.type === 'brute') {
      mk(darkMat, 0, 1.30, 0.19, 0.70, 0.42, 0.10); // chest plate
      for (const s of [-1, 1]) mk(darkMat, s * 0.36, 1.42, 0, 0.22, 0.18, 0.34); // pauldrons
    }

    // arms: pivot at the shoulder so they can swing
    this.arms = [];
    for (const s of [-1, 1]) {
      const pivot = new THREE.Group();
      pivot.position.set(s * 0.40, 1.40, 0);
      body.add(pivot);
      mk(clothMat, 0, -0.22, 0, 0.20, 0.46, 0.20, pivot).userData.bigPart = true;
      const hand = mk(skinMat, 0, -0.50, 0.02, 0.17, 0.20, 0.17, pivot);
      hand.name = 'hand';
      pivot.rotation.x = 0.2;
      this.arms.push(pivot);
    }

    // legs
    this.legs = [];
    for (const s of [-1, 1]) {
      const pivot = new THREE.Group();
      pivot.position.set(s * 0.17, 0.78, 0);
      body.add(pivot);
      mk(clothMat, 0, -0.28, 0, 0.24, 0.58, 0.24, pivot).userData.bigPart = true;
      mk(darkMat, 0, -0.58, 0.04, 0.26, 0.12, 0.32, pivot); // boot
      this.legs.push(pivot);
    }

    if (this.type === 'raider') {
      // a crude rifle held across the chest
      const gun = new THREE.Group();
      gun.position.set(0.30, 1.22, 0.26);
      gun.rotation.set(0, -0.25, 0);
      body.add(gun);
      mk(darkMat, 0, 0, 0, 0.07, 0.10, 0.62, gun);
      mk(darkMat, 0, -0.09, 0.06, 0.06, 0.14, 0.10, gun);
      mk(darkMat, 0, 0.02, -0.42, 0.045, 0.045, 0.28, gun);
      this.gun = gun;
      this.muzzleOffset = new THREE.Vector3(0.30, 1.22, -0.30);
    }

    // tattered coat flaps
    for (let i = 0; i < 3; i++) {
      const flap = mk(clothMat, (Math.random() - 0.5) * 0.4, 0.72 + Math.random() * 0.1, (Math.random() < 0.5 ? 0.2 : -0.2), 0.22, 0.34, 0.06);
      flap.rotation.z = (Math.random() - 0.5) * 0.6;
    }

    // Only the big masses cast shadows. The trinkets contribute nothing at this
    // silhouette size and would double the draw calls in the shadow pass.
    this.group.traverse((o) => {
      if (o.isMesh) o.castShadow = !!o.userData.bigPart;
    });
  }

  spawn(pos) {
    this.position.copy(pos);
    this.velocity.set(0, 0, 0);
    this.health = this.maxHealth;
    this.alive = true;
    this.state = 'chase';
    this.stateTime = 0;
    this.attackTimer = 0.4 + Math.random() * 0.6;
    this.deathTime = 0;
    this.flash = 0;
    this.group.visible = true;
    this.group.position.copy(pos);
    this.group.rotation.set(0, 0, 0);
    this.body.rotation.set(0, 0, 0);
    this.body.position.set(0, 0, 0);
    this.skinMat.color.copy(this.baseSkin);
    this.clothMat.color.copy(this.baseCloth);
    this.skinMat.opacity = 1;
    this.clothMat.opacity = 1;
    this.skinMat.transparent = false;
    this.clothMat.transparent = false;
    this.burstLeft = 0;
    this._updateHitboxes();
  }

  despawn() {
    this.alive = false;
    this.group.visible = false;
    this.state = 'idle';
  }

  get halfWidth() {
    return 0.34 * this.def.scale;
  }

  get standHeight() {
    return 1.78 * this.def.scale;
  }

  _updateHitboxes() {
    const S = this.def.scale;
    const x = this.position.x, y = this.position.y, z = this.position.z;
    const hw = 0.30 * S;
    this.headBox.min.set(x - 0.19 * S, y + 1.44 * S, z - 0.19 * S);
    this.headBox.max.set(x + 0.19 * S, y + 1.80 * S, z + 0.19 * S);
    this.bodyBox.min.set(x - hw - 0.06 * S, y + 0.74 * S, z - 0.24 * S);
    this.bodyBox.max.set(x + hw + 0.06 * S, y + 1.46 * S, z + 0.24 * S);
    this.legBox.min.set(x - hw, y, z - 0.22 * S);
    this.legBox.max.set(x + hw, y + 0.76 * S, z + 0.22 * S);
  }

  /** Returns true when this shot killed it. */
  hit(damage, dir, point, part) {
    if (!this.alive) return false;
    this.health -= damage;
    this.flash = 1;
    this.manager.effects.bloodBurst(point, dir.clone().multiplyScalar(0.6).setY(0.35), part === 'head');
    // knock the aim/pose around a little
    this.velocity.addScaledVector(dir, Math.min(3.2, damage * 0.045));
    if (this.health <= 0) {
      this.die(dir);
      return true;
    }
    if (this.state === 'chase' && Math.random() < 0.25) {
      this.state = 'stagger';
      this.stateTime = 0;
    }
    return false;
  }

  die(dir) {
    this.alive = false;
    this.state = 'dead';
    this.deathTime = 0;
    this.manager.onEnemyKilled(this, dir);
  }

  update(dt, player, colliders) {
    if (this.state === 'dead') {
      this.deathTime += dt;
      // topple over, then sink and fade away
      const t = Math.min(1, this.deathTime / 0.55);
      const ease = 1 - Math.pow(1 - t, 3);
      this.body.rotation.x = ease * (Math.PI / 2) * 0.95;
      this.body.position.y = -ease * 0.55 * this.def.scale;
      if (this.deathTime > 3.2) {
        const fade = Math.max(0, 1 - (this.deathTime - 3.2) / 1.4);
        this.skinMat.transparent = this.clothMat.transparent = true;
        this.skinMat.opacity = this.clothMat.opacity = fade;
        this.group.position.y = this.position.y - (1 - fade) * 0.8;
        if (fade <= 0) this.despawn();
      }
      if (this.flash > 0) this.flash = Math.max(0, this.flash - dt * 4);
      return;
    }
    if (!this.alive) return;

    this.stateTime += dt;
    this.attackTimer -= dt;
    this.losTimer -= dt;

    const eye = _v.set(this.position.x, this.position.y + 1.55 * this.def.scale, this.position.z);
    const playerEye = _v2.set(player.position.x, player.eyeY, player.position.z);
    const toPlayer = _delta.copy(playerEye).sub(eye);
    const dist = toPlayer.length();

    if (this.losTimer <= 0) {
      this.losTimer = 0.18 + Math.random() * 0.12;
      this.hasLOS = player.alive && colliders.lineOfSight(eye, playerEye);
    }

    // ambient growling when close
    this.growlTimer -= dt;
    if (this.growlTimer <= 0) {
      this.growlTimer = 4 + Math.random() * 7;
      if (dist < 26 && Math.random() < 0.5) this.manager.audio.growl();
    }

    // ---- decide ----
    const def = this.def;
    let moveDir = null;
    let speed = def.speed;

    if (!player.alive) {
      this.state = 'idle';
    } else if (this.state === 'stagger') {
      if (this.stateTime > 0.35) { this.state = 'chase'; this.stateTime = 0; }
    } else if (this.state === 'attack') {
      // committed to a swing / burst
      if (def.ranged) {
        if (this.stateTime >= def.windup) {
          if (this.burstLeft > 0) {
            this.burstTimer -= dt;
            if (this.burstTimer <= 0) {
              this.burstTimer = 0.11;
              this.burstLeft--;
              this._shoot(player, colliders);
            }
          } else {
            this.state = 'chase';
            this.stateTime = 0;
            this.attackTimer = def.attackCooldown * (0.75 + Math.random() * 0.6);
          }
        }
      } else if (this.stateTime >= def.windup) {
        // the swing lands now
        const d2 = this.position.distanceTo(player.position);
        if (d2 <= def.attackRange + 0.6 && this.hasLOS) {
          player.damage(def.damage, this.position);
          this.manager.audio.flesh();
          this.manager.onPlayerHit(this);
        }
        this.state = 'chase';
        this.stateTime = 0;
        this.attackTimer = def.attackCooldown * (0.8 + Math.random() * 0.5);
      }
    } else {
      // chase / reposition
      this.state = 'chase';
      const flatDist = Math.hypot(player.position.x - this.position.x, player.position.z - this.position.z);
      if (def.ranged) {
        const pref = def.preferredRange;
        if (this.hasLOS && flatDist < pref * 0.65) {
          moveDir = _v2.set(this.position.x - player.position.x, 0, this.position.z - player.position.z).normalize();
        } else if (!this.hasLOS || flatDist > pref * 1.25) {
          moveDir = _v2.set(player.position.x - this.position.x, 0, player.position.z - this.position.z).normalize();
        } else {
          // strafe to stay awkward to track
          const to = _v2.set(player.position.x - this.position.x, 0, player.position.z - this.position.z).normalize();
          moveDir = new THREE.Vector3(-to.z * this.strafeSide, 0, to.x * this.strafeSide);
          speed *= 0.8;
        }
        if (this.hasLOS && this.attackTimer <= 0 && flatDist < def.attackRange) {
          this.state = 'attack';
          this.stateTime = 0;
          this.burstLeft = def.burst;
          this.burstTimer = 0;
        }
      } else {
        moveDir = _v2.set(player.position.x - this.position.x, 0, player.position.z - this.position.z);
        const l = moveDir.length();
        if (l > 0.001) moveDir.multiplyScalar(1 / l);
        if (flatDist < 14) speed = def.chargeSpeed;
        if (flatDist <= def.attackRange && this.hasLOS && this.attackTimer <= 0) {
          this.state = 'attack';
          this.stateTime = 0;
          this.manager.audio.growl();
          moveDir = null;
        } else if (flatDist <= def.attackRange * 0.85) {
          moveDir = null; // already in range, wait out the cooldown
        }
      }
    }

    // ---- separation from the rest of the pack ----
    const sep = this.manager.separation(this, _v);
    if (moveDir && sep.lengthSq() > 0) {
      moveDir.add(sep.multiplyScalar(1.4));
      if (moveDir.lengthSq() > 0) moveDir.normalize();
    }

    // ---- move ----
    const targetVX = moveDir ? moveDir.x * speed : 0;
    const targetVZ = moveDir ? moveDir.z * speed : 0;
    const k = Math.min(1, 9 * dt);
    this.velocity.x += (targetVX - this.velocity.x) * k;
    this.velocity.z += (targetVZ - this.velocity.z) * k;
    this.velocity.y += -24 * dt;

    _delta.set(this.velocity.x * dt, this.velocity.y * dt, this.velocity.z * dt);
    _half.set(this.halfWidth, this.standHeight / 2, this.halfWidth);
    _center.set(this.position.x, this.position.y + this.standHeight / 2, this.position.z);
    const res = moveAABB(colliders, _center, _half, _delta, 0.62);
    this.position.set(_center.x, _center.y - this.standHeight / 2, _center.z);
    if (res.grounded) { this.velocity.y = 0; this.grounded = true; } else this.grounded = false;

    // The player is solid to enemies too. Without this the pack shoves one of
    // its own into the camera and you end up looking at the inside of a face.
    {
      const standoff = this.halfWidth + 0.36 + 0.45;
      let dx = this.position.x - player.position.x;
      let dz = this.position.z - player.position.z;
      let d = Math.hypot(dx, dz);
      if (d < standoff) {
        if (d < 1e-4) { dx = Math.sin(this.yaw); dz = Math.cos(this.yaw); d = 1; }
        const push = (standoff - d) / d;
        this.position.x += dx * push;
        this.position.z += dz * push;
        this.velocity.x *= 0.4;
        this.velocity.z *= 0.4;
      }
    }

    // stuck against a wall: slide along it for a moment
    this.avoidTimer -= dt;
    if (res.hitWall && moveDir) {
      if (this.avoidTimer <= 0) {
        this.strafeSide *= -1;
        this.avoidTimer = 0.7 + Math.random() * 0.5;
      }
      const perp = _v.set(-moveDir.z * this.strafeSide, 0, moveDir.x * this.strafeSide);
      this.velocity.x += perp.x * speed * 1.1 * dt * 8;
      this.velocity.z += perp.z * speed * 1.1 * dt * 8;
      // small hop to clear low rubble
      if (this.grounded && Math.random() < 0.02) this.velocity.y = 5.4;
    }

    // ---- face the player ----
    const desiredYaw = Math.atan2(player.position.x - this.position.x, player.position.z - this.position.z);
    let diff = desiredYaw - this.yaw;
    while (diff > Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    this.yaw += diff * Math.min(1, 8 * dt);

    // ---- animate ----
    const planarSpeed = Math.hypot(this.velocity.x, this.velocity.z);
    this.walkPhase += dt * (2.2 + planarSpeed * 1.9);
    const swing = Math.sin(this.walkPhase) * Math.min(1, planarSpeed / 3) * 0.8;
    this.legs[0].rotation.x = swing;
    this.legs[1].rotation.x = -swing;

    if (this.state === 'attack' && !def.ranged) {
      const t = Math.min(1, this.stateTime / def.windup);
      const lunge = Math.sin(t * Math.PI) * 1.5;
      this.arms[0].rotation.x = 0.2 - lunge;
      this.arms[1].rotation.x = 0.2 - lunge * 0.85;
      this.body.position.z = Math.sin(t * Math.PI) * 0.18;
    } else {
      this.arms[0].rotation.x = 0.2 - swing * 0.7;
      this.arms[1].rotation.x = 0.2 + swing * 0.7;
      this.body.position.z *= Math.exp(-8 * dt);
    }
    // ghouls reach forward when charging
    if (!def.ranged && planarSpeed > 3.6) {
      this.arms[0].rotation.x = -1.25 + Math.sin(this.walkPhase * 2) * 0.12;
      this.arms[1].rotation.x = -1.25 - Math.sin(this.walkPhase * 2) * 0.12;
    }
    this.body.rotation.z = Math.sin(this.walkPhase) * 0.05;

    this.group.position.copy(this.position);
    this.group.rotation.y = this.yaw;

    // hit flash
    if (this.flash > 0) {
      this.flash = Math.max(0, this.flash - dt * 5);
      const f = this.flash;
      this.skinMat.color.copy(this.baseSkin).lerp(_flashColor, f);
      this.clothMat.color.copy(this.baseCloth).lerp(_flashColor, f * 0.8);
    }

    this._updateHitboxes();
  }

  _shoot(player, colliders) {
    const muzzle = _v.set(this.position.x, this.position.y + 1.35 * this.def.scale, this.position.z);
    const fwd = _v2.set(Math.sin(this.yaw), 0, Math.cos(this.yaw));
    muzzle.addScaledVector(fwd, 0.45);
    const target = new THREE.Vector3(player.position.x, player.eyeY - 0.25, player.position.z);
    const dir = target.clone().sub(muzzle);
    const dist = dir.length();
    dir.multiplyScalar(1 / dist);

    // inaccuracy grows with range
    const spread = 0.022 + Math.min(0.05, dist * 0.0016);
    const a = Math.random() * Math.PI * 2;
    const r = Math.sqrt(Math.random()) * spread;
    const rightAxis = new THREE.Vector3(dir.z, 0, -dir.x).normalize();
    const upAxis = new THREE.Vector3().crossVectors(rightAxis, dir).normalize();
    dir.addScaledVector(rightAxis, Math.cos(a) * r).addScaledVector(upAxis, Math.sin(a) * r).normalize();

    this.manager.audio.enemyShot();
    this.manager.effects.pointFlash(muzzle.clone(), 6);

    const worldHit = colliders.raycast(muzzle, dir, dist);
    if (worldHit) {
      this.manager.effects.tracer(muzzle, worldHit.point);
      this.manager.effects.impact(worldHit.point, worldHit.normal, 'concrete');
      return;
    }
    const endPoint = muzzle.clone().addScaledVector(dir, dist);
    this.manager.effects.tracer(muzzle, endPoint);
    // did the round pass close enough to count as a hit?
    const miss = endPoint.distanceTo(target);
    if (miss < 0.55) {
      player.damage(this.def.damage, this.position);
      this.manager.onPlayerHit(this);
    } else {
      this.manager.onNearMiss(endPoint);
    }
  }
}

const _flashColor = new THREE.Color(0xff6b5a);

/** Spawns, updates and pools every enemy; owns the wave logic. */
export class EnemyManager {
  constructor(ctx) {
    this.scene = ctx.scene;
    this.colliders = ctx.colliders;
    this.effects = ctx.effects;
    this.audio = ctx.audio;
    this.tex = ctx.tex;
    this.spawnPoints = ctx.spawnPoints;
    this.pools = { ghoul: [], raider: [], brute: [] };
    this.active = [];
    this.onKill = null;       // (enemy) => void
    this.onPlayerHitCb = null;
    this.wave = 0;
    this.pending = [];        // queued spawns for the current wave
    this.spawnTimer = 0;
    this.waveActive = false;
    this.betweenWaves = 0;
    this.totalKills = 0;
    this.score = 0;
  }

  _obtain(type) {
    const pool = this.pools[type];
    for (let i = 0; i < pool.length; i++) {
      if (!pool[i].alive && pool[i].state !== 'dead') return pool[i];
    }
    const e = new Enemy(this, type);
    pool.push(e);
    return e;
  }

  get aliveCount() {
    let n = 0;
    for (const e of this.active) if (e.alive) n++;
    return n;
  }

  get remainingInWave() {
    return this.aliveCount + this.pending.length;
  }

  /** Composition scales up with the wave number. */
  planWave(n) {
    const list = [];
    const ghouls = 4 + Math.floor(n * 1.7);
    for (let i = 0; i < ghouls; i++) list.push('ghoul');
    const raiders = n >= 2 ? Math.floor((n - 1) * 1.1) : 0;
    for (let i = 0; i < raiders; i++) list.push('raider');
    const brutes = n >= 4 ? Math.floor((n - 2) / 3) : 0;
    for (let i = 0; i < brutes; i++) list.push('brute');
    // shuffle so the drip feed is mixed
    for (let i = list.length - 1; i > 0; i--) {
      const j = (Math.random() * (i + 1)) | 0;
      [list[i], list[j]] = [list[j], list[i]];
    }
    return list;
  }

  startWave(n, player) {
    this.wave = n;
    this.pending = this.planWave(n);
    this.spawnTimer = 0;
    this.waveActive = true;
    this.maxAlive = Math.min(16, 7 + n);
    this.player = player;
    this.audio.waveStart();
  }

  /** Pick a spawn point far from the player and ideally out of sight. */
  _pickSpawn(player) {
    const pts = this.spawnPoints;
    let best = null;
    let bestScore = -Infinity;
    for (let i = 0; i < 24; i++) {
      const p = pts[(Math.random() * pts.length) | 0];
      const d = p.distanceTo(player.position);
      if (d < 26) continue;
      const eye = _v.set(p.x, p.y + 1.5, p.z);
      const pe = _v2.set(player.position.x, player.eyeY, player.position.z);
      const visible = this.colliders.lineOfSight(eye, pe);
      // prefer 30-60m away and hidden
      const score = -Math.abs(d - 42) + (visible ? -35 : 0) + Math.random() * 6;
      if (score > bestScore) { bestScore = score; best = p; }
    }
    if (!best) best = pts[(Math.random() * pts.length) | 0];
    return best;
  }

  update(dt, player) {
    // drip-feed the wave in
    if (this.waveActive && this.pending.length > 0) {
      this.spawnTimer -= dt;
      if (this.spawnTimer <= 0 && this.aliveCount < this.maxAlive) {
        const type = this.pending.shift();
        const e = this._obtain(type);
        const p = this._pickSpawn(player);
        e.spawn(new THREE.Vector3(p.x, p.y + 0.05, p.z));
        if (!this.active.includes(e)) this.active.push(e);
        this.spawnTimer = 0.35 + Math.random() * 0.7;
      }
    }

    for (let i = 0; i < this.active.length; i++) {
      const e = this.active[i];
      if (!e.alive && e.state !== 'dead') continue;
      e.update(dt, player, this.colliders);
    }
    // drop fully despawned enemies from the active list
    this.active = this.active.filter((e) => e.alive || e.state === 'dead');

    if (this.waveActive && this.pending.length === 0 && this.aliveCount === 0) {
      this.waveActive = false;
    }
  }

  /** Gentle push so the pack does not stack into one body. */
  separation(self, out) {
    out.set(0, 0, 0);
    const r = 1.5 * self.def.scale;
    for (let i = 0; i < this.active.length; i++) {
      const o = this.active[i];
      if (o === self || !o.alive) continue;
      const dx = self.position.x - o.position.x;
      const dz = self.position.z - o.position.z;
      const d2 = dx * dx + dz * dz;
      if (d2 > r * r || d2 < 1e-6) continue;
      const d = Math.sqrt(d2);
      out.x += (dx / d) * (1 - d / r);
      out.z += (dz / d) * (1 - d / r);
    }
    return out;
  }

  /** Closest enemy hitbox along a ray. Returns null or {enemy, distance, point, part}. */
  raycast(origin, dir, maxDist) {
    let best = null;
    for (let i = 0; i < this.active.length; i++) {
      const e = this.active[i];
      if (!e.alive) continue;
      // cheap reject: skip enemies far off the ray
      _v.copy(e.position).sub(origin);
      const along = _v.dot(dir);
      if (along < -2 || along > maxDist + 2) continue;
      const perp2 = _v.lengthSq() - along * along;
      if (perp2 > 9) continue;

      const parts = [
        ['head', e.headBox],
        ['body', e.bodyBox],
        ['limb', e.legBox],
      ];
      for (const [part, bx] of parts) {
        const t = rayBox(origin, dir, bx.min, bx.max, maxDist);
        if (t >= 0 && (!best || t < best.distance)) {
          best = { enemy: e, distance: t, part, point: null };
        }
      }
    }
    if (best) {
      best.point = new THREE.Vector3(
        origin.x + dir.x * best.distance,
        origin.y + dir.y * best.distance,
        origin.z + dir.z * best.distance
      );
    }
    return best;
  }

  onEnemyKilled(enemy, dir) {
    this.totalKills++;
    this.score += enemy.def.score;
    this.audio.enemyDeath();
    this.effects.bloodBurst(
      _v.set(enemy.position.x, enemy.position.y + 1.1, enemy.position.z).clone(),
      dir ? dir.clone().setY(0.5).normalize() : new THREE.Vector3(0, 1, 0),
      true
    );
    if (this.onKill) this.onKill(enemy);
  }

  onPlayerHit(enemy) {
    if (this.onPlayerHitCb) this.onPlayerHitCb(enemy);
  }

  onNearMiss(point) {
    this.effects.smoke(point, new THREE.Vector3(0, 1, 0), 1);
  }

  reset() {
    for (const e of this.active) e.despawn();
    this.active.length = 0;
    this.pending.length = 0;
    this.wave = 0;
    this.waveActive = false;
    this.totalKills = 0;
    this.score = 0;
  }
}
