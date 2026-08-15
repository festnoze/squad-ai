import * as THREE from 'three';
import { moveAABB, rayBox } from './collision.js';
import { tileX, tileZ, TILE } from './world.js';

const GUARD_HP = 100;
const VIEW_RANGE = 24;
const VIEW_FOV = Math.cos(THREE.MathUtils.degToRad(105) / 2);
const DISGUISE_RANGE = 9;      // beyond this a uniform is good enough
/** How much lockdown progress a punch in the face knocks off the call. */
export const PUNCH_RADIO_SETBACK = 2.0;
const SPOT_BASE = 0.85;        // seconds to fully identify you at point blank
const HALF = new THREE.Vector3(0.42, 0.9, 0.42);

const STATE = { PATROL: 0, INVESTIGATE: 1, ALERT: 2, DEAD: 3 };

const _v = new THREE.Vector3();
const _dir = new THREE.Vector3();
const _delta = new THREE.Vector3();
// Scratch vectors owned solely by _steer. Callers pass their target in using
// the shared _v, so _steer must never touch it.
const _steerEye = new THREE.Vector3();
const _steerAim = new THREE.Vector3();

/**
 * The prison staff. They walk routes, hear you run, and if one of them gets a
 * clean look at you he starts shooting and calling the lockdown in on his
 * radio. Let that call finish and the run is over - so either stay unseen, or
 * put him down before he finishes talking.
 */
export class Guards {
  constructor(scene, world, audio, fx) {
    this.scene = scene;
    this.world = world;
    this.audio = audio;
    this.fx = fx;
    this.list = [];
    this.group = new THREE.Group();
    scene.add(this.group);
    this.uniformTaken = false;
    this._build();
  }

  _build() {
    for (const def of this.world.guardDefs) {
      const model = buildGuard();
      this.group.add(model.root);
      const start = new THREE.Vector3(tileX(def.route[0][0]), 0.92, tileZ(def.route[0][1]));
      model.root.position.copy(start);

      this.list.push({
        id: def.id,
        def,
        model,
        root: model.root,
        position: start.clone(),
        velocity: new THREE.Vector3(),
        yaw: 0,
        targetYaw: 0,
        hp: GUARD_HP,
        alive: true,
        state: STATE.PATROL,
        waypoint: 1,
        pauseTimer: 0,
        awareness: 0,
        calling: false,
        radioChirp: 0,
        shootCooldown: 1.2,
        staggered: 0,
        investigateAt: new THREE.Vector3(),
        investigateTimer: 0,
        lookAroundPhase: 0,
        weapon: def.weapon,
        speed: def.speed,
        stepPhase: Math.random() * 10,
        looted: false,
        deathT: 0,
        alertedOnce: false,
      });
    }
  }

  get aliveCount() {
    return this.list.filter((g) => g.alive).length;
  }

  // ------------------------------------------------------------------ senses
  _canSee(g, player) {
    if (!player.alive) return 0;
    const eye = new THREE.Vector3(g.position.x, g.position.y + 0.72, g.position.z);
    const target = player.chest;
    _dir.copy(target).sub(eye);
    const dist = _dir.length();
    if (dist > VIEW_RANGE) return 0;
    if (player.disguised && dist > DISGUISE_RANGE) return 0;
    _dir.multiplyScalar(1 / dist);
    const fwd = _v.set(-Math.sin(g.yaw), 0, -Math.cos(g.yaw));
    const flat = Math.hypot(_dir.x, _dir.z) || 1e-6;
    const dot = (fwd.x * _dir.x + fwd.z * _dir.z) / flat;
    if (dot < VIEW_FOV) return 0;
    if (!this.world.colliders.lineOfSight(eye, target)) return 0;

    // Rate falls off with distance; crouching and a stolen uniform both help.
    let rate = 1 - Math.min(0.75, dist / VIEW_RANGE);
    if (player.crouching) rate *= 0.55;
    if (player.disguised) rate *= 0.18;
    if (g.state === STATE.INVESTIGATE) rate *= 1.6;
    return Math.max(0.05, rate);
  }

  _canHear(g, player) {
    if (player.noiseRadius <= 0) return false;
    const d = g.position.distanceTo(player.position);
    return d < player.noiseRadius;
  }

  // ------------------------------------------------------------------ update
  /**
   * Steps every guard. Returns `callers`: how many are on the radio right now,
   * which the caller feeds into the prison's single shared lockdown clock.
   */
  update(dt, player, gameActive) {
    let anyAlert = false;
    let highestAwareness = 0;
    let callers = 0;

    for (const g of this.list) {
      if (!g.alive) {
        this._updateCorpse(g, dt);
        continue;
      }

      if (gameActive) {
        const sight = this._canSee(g, player);
        if (sight > 0) {
          g.awareness = Math.min(1, g.awareness + (dt / SPOT_BASE) * sight);
          g.lastSeen = player.position.clone();
          if (g.awareness > 0.3 && g.state === STATE.PATROL) {
            g.state = STATE.INVESTIGATE;
            g.investigateAt.copy(player.position);
            g.investigateTimer = 6;
            this.audio.suspicion();
          }
          if (g.awareness >= 1 && g.state !== STATE.ALERT) {
            this._raiseAlert(g, player);
          }
        } else {
          g.awareness = Math.max(0, g.awareness - dt * 0.4);
          if (this._canHear(g, player) && g.state === STATE.PATROL) {
            g.state = STATE.INVESTIGATE;
            g.investigateAt.copy(player.position);
            g.investigateTimer = 7;
          }
        }
      }

      g.calling = false;
      if (g.staggered > 0) {
        // Reeling from a punch: no steering, no shooting, no radio. This is
        // the window the unarmed player buys with their fists.
        g.staggered -= dt;
        g.velocity.x *= Math.pow(0.02, dt);
        g.velocity.z *= Math.pow(0.02, dt);
        if (g.state === STATE.ALERT) anyAlert = true;
      } else {
        switch (g.state) {
          case STATE.PATROL: this._patrol(g, dt); break;
          case STATE.INVESTIGATE: this._investigate(g, dt); break;
          case STATE.ALERT: {
            anyAlert = true;
            this._alert(g, dt, player);
            g.calling = true;
            callers++;
            break;
          }
        }
      }

      this._applyMotion(g, dt);
      this._animate(g, dt);
      highestAwareness = Math.max(highestAwareness, g.awareness);
    }

    return { anyAlert, awareness: highestAwareness, callers };
  }

  _raiseAlert(g, player) {
    g.state = STATE.ALERT;
    g.awareness = 1;
    g.calling = true;
    g.radioChirp = 0;
    g.shootCooldown = 0.8;
    g.lastSeen = player.position.clone();
    if (!g.alertedOnce) {
      g.alertedOnce = true;
      this.audio.guardShout(g.position.distanceTo(player.position));
    }
    // Everyone within earshot converges on the sighting.
    for (const other of this.list) {
      if (other === g || !other.alive || other.state === STATE.ALERT) continue;
      if (other.position.distanceTo(g.position) < 30) {
        other.state = STATE.INVESTIGATE;
        other.investigateAt.copy(player.position);
        other.investigateTimer = 12;
        other.awareness = Math.max(other.awareness, 0.5);
      }
    }
  }

  /**
   * A gunshot anywhere nearby pulls guards toward the noise. Returns how many
   * were drawn, so the HUD can say so - these are existing patrols walking
   * over, never new arrivals. The roster is the ten built at load and nothing
   * ever replaces one that goes down.
   */
  hearGunshot(position, radius = 45) {
    let drawn = 0;
    for (const g of this.list) {
      if (!g.alive || g.state === STATE.ALERT) continue;
      if (g.position.distanceTo(position) > radius) continue;
      if (g.state !== STATE.INVESTIGATE) drawn++;
      g.state = STATE.INVESTIGATE;
      g.investigateAt.copy(position);
      g.investigateTimer = 14;
      g.awareness = Math.max(g.awareness, 0.45);
    }
    return drawn;
  }

  _patrol(g, dt) {
    const route = g.def.route;
    const wp = route[g.waypoint % route.length];
    const target = _v.set(tileX(wp[0]), g.position.y, tileZ(wp[1]));
    const dist = Math.hypot(target.x - g.position.x, target.z - g.position.z);
    if (dist < 1.2) {
      g.waypoint = (g.waypoint + 1) % route.length;
      g.pauseTimer = 0.6 + Math.random() * 1.4;
      return;
    }
    if (g.pauseTimer > 0) {
      g.pauseTimer -= dt;
      g.velocity.set(0, g.velocity.y, 0);
      return;
    }
    this._steer(g, target, g.speed);
  }

  _investigate(g, dt) {
    g.investigateTimer -= dt;
    if (g.investigateTimer <= 0) {
      g.state = STATE.PATROL;
      g.awareness = Math.min(g.awareness, 0.25);
      return;
    }
    const dist = Math.hypot(g.investigateAt.x - g.position.x, g.investigateAt.z - g.position.z);
    if (dist > 1.6) {
      this._steer(g, g.investigateAt, g.speed * 1.25);
    } else {
      // Arrived: sweep the area with a slow head turn.
      g.velocity.set(0, g.velocity.y, 0);
      g.lookAroundPhase += dt * 1.4;
      g.targetYaw = g.yaw + Math.sin(g.lookAroundPhase) * 0.05;
      g.yaw += Math.sin(g.lookAroundPhase * 0.9) * dt * 1.6;
    }
  }

  /**
   * On the radio and shooting. The countdown itself is not kept here: the
   * prison has one lockdown clock, fed by however many officers and cameras
   * are calling it in (see Game._updateLockdown). Independent per-guard timers
   * meant a second officer who spotted you a moment later had a clock the
   * player could neither see nor stop in time.
   */
  _alert(g, dt, player) {
    const eye = new THREE.Vector3(g.position.x, g.position.y + 0.72, g.position.z);
    const visible = this.world.colliders.lineOfSight(eye, player.chest) && player.alive;
    if (visible) g.lastSeen = player.position.clone();

    const target = g.lastSeen || player.position;
    const dist = Math.hypot(target.x - g.position.x, target.z - g.position.z);

    // Keep at a firing distance: close in when far, back off when too close.
    if (dist > 12) this._steer(g, target, g.speed * 1.35);
    else if (dist < 4.5 && visible) {
      _v.copy(g.position).sub(target).setY(0).normalize().multiplyScalar(4);
      this._steer(g, _v.add(g.position), g.speed);
    } else {
      g.velocity.set(0, g.velocity.y, 0);
      this._face(g, target);
    }

    // Radio chatter, so a caller is audible even when out of sight.
    g.radioChirp -= dt;
    if (g.radioChirp <= 0) {
      g.radioChirp = 0.55;
      this.audio.radio(g.position.distanceTo(player.position));
    }

    g.shootCooldown -= dt;
    if (visible && g.shootCooldown <= 0 && dist < 30) {
      this._shoot(g, player, dist);
    }
  }

  _shoot(g, player, dist) {
    const profile = g.weapon === 'shotgun'
      ? { cd: 1.4, dmg: 16, spread: 0.10, shots: 5 }
      : g.weapon === 'rifle'
        ? { cd: 0.9, dmg: 9, spread: 0.045, shots: 3 }
        : { cd: 1.1, dmg: 12, spread: 0.05, shots: 1 };
    g.shootCooldown = profile.cd + Math.random() * 0.4;

    const from = new THREE.Vector3(g.position.x, g.position.y + 0.55, g.position.z);
    const to = player.chest;
    const base = to.clone().sub(from).normalize();
    this.fx.muzzleFlash(from.clone().addScaledVector(base, 0.5), 0.7);
    this.audio.shot(g.weapon, g.position.distanceTo(player.position));

    // Accuracy degrades with distance and improves the longer they have been
    // shooting at you, so peeking from cover is survivable but greedy.
    const acc = profile.spread * (0.6 + dist / 22);
    let hits = 0;
    for (let i = 0; i < profile.shots; i++) {
      const d = base.clone();
      d.x += (Math.random() - 0.5) * acc * 2;
      d.y += (Math.random() - 0.5) * acc * 2;
      d.z += (Math.random() - 0.5) * acc * 2;
      d.normalize();
      const wall = this.world.colliders.raycast(from, d, dist + 2);
      const hitPlayer = !wall || wall.distance > dist - 0.6;
      const end = hitPlayer ? to.clone() : wall.point;
      this.fx.tracer(from, end);
      if (hitPlayer) hits++;
      else {
        this.fx.sparks(wall.point, wall.normal, 4);
        this.fx.decal(wall.point, wall.normal, 0.2);
      }
    }
    if (hits > 0) player.damage(profile.dmg * hits);
  }

  _face(g, target) {
    g.targetYaw = Math.atan2(-(target.x - g.position.x), -(target.z - g.position.z));
  }

  /** Straight-line steering. Only safe when nothing is in the way. */
  _steerDirect(g, target, speed) {
    _dir.set(target.x - g.position.x, 0, target.z - g.position.z);
    const len = _dir.length();
    if (len < 0.01) return;
    _dir.multiplyScalar(speed / len);
    g.velocity.x = _dir.x;
    g.velocity.z = _dir.z;
    this._face(g, target);
  }

  /**
   * Walks toward `target`, going around the building rather than into it. Uses
   * a straight line while the way is clear, and the world's flow field the
   * moment a wall gets between the guard and where he wants to be. Without
   * this, a guard pressed against a wall used to grind sideways until he
   * squeezed through it and popped out inside a sealed room.
   */
  _steer(g, target, speed) {
    // Snapshot the target first: it is often the shared scratch vector.
    const tgx = target.x;
    const tgz = target.z;
    const eye = _steerEye.set(g.position.x, g.position.y + 0.4, g.position.z);
    const aim = _steerAim.set(tgx, g.position.y + 0.4, tgz);
    if (this.world.colliders.lineOfSight(eye, aim)) {
      this._steerDirect(g, aim, speed);
      return;
    }

    const tx = Math.floor(tgx / TILE);
    const tz = Math.floor(tgz / TILE);
    const field = this.world.flowField(tx, tz);
    const step = this.world.nextStep(field, g.position);
    if (!step) {
      // Unreachable (locked door, or the target is inside geometry): hold
      // position and look toward it rather than shoving into the wall.
      g.velocity.x = 0;
      g.velocity.z = 0;
      this._face(g, _steerAim.set(tgx, g.position.y, tgz));
      return;
    }
    this._steerDirect(g, _steerAim.set(step.x, g.position.y, step.z), speed);
  }

  _applyMotion(g, dt) {
    // face the direction of travel smoothly
    let diff = g.targetYaw - g.yaw;
    while (diff > Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    g.yaw += diff * Math.min(1, dt * 7);

    g.velocity.y -= 22 * dt;
    _delta.set(g.velocity.x * dt, g.velocity.y * dt, g.velocity.z * dt);
    const res = moveAABB(this.world.colliders, g.position, HALF, _delta, 0.5);
    if (res.grounded) g.velocity.y = 0;
    if (res.hitWall) {
      // Slide along the wall to get around a corner - but through the collision
      // solver, never as a raw displacement. Adding it directly used to walk
      // guards clean through walls over a few frames.
      _delta.set(-g.velocity.z, 0, g.velocity.x);
      const len = Math.hypot(_delta.x, _delta.z);
      if (len > 0.001) {
        _delta.multiplyScalar(0.9 * dt / len);
        _delta.y = 0;
        moveAABB(this.world.colliders, g.position, HALF, _delta, 0.5);
      }
    }

    // Belt and braces: a guard must never be standing inside the building. If
    // one somehow is, put him back where he last stood legitimately.
    if (this._insideGeometry(g)) {
      if (g.lastSafe) g.position.copy(g.lastSafe);
      g.velocity.x = 0;
      g.velocity.z = 0;
    } else {
      (g.lastSafe ??= new THREE.Vector3()).copy(g.position);
    }

    g.root.position.copy(g.position);
    g.root.position.y = g.position.y - HALF.y;
    g.root.rotation.y = g.yaw;
  }

  /** True when the guard's body overlaps a wall, a door or a prop. */
  _insideGeometry(g) {
    return this.world.colliders.overlaps(
      g.position.x, g.position.y, g.position.z,
      HALF.x - 0.06, HALF.y - 0.12, HALF.z - 0.06
    );
  }

  _animate(g, dt) {
    const planar = Math.hypot(g.velocity.x, g.velocity.z);
    g.stepPhase += dt * (2.4 + planar * 1.5);
    const swing = Math.min(1, planar / 2.5);
    const s = Math.sin(g.stepPhase * 2.2) * 0.62 * swing;
    g.model.legL.rotation.x = s;
    g.model.legR.rotation.x = -s;
    g.model.armL.rotation.x = -s * 0.55;
    g.model.armR.rotation.x = g.state === STATE.ALERT ? -1.35 : s * 0.55;
    g.model.root.position.y = g.position.y - HALF.y + Math.abs(Math.sin(g.stepPhase * 2.2)) * 0.045 * swing;

    // Awareness marker floating over the head.
    const mark = g.model.mark;
    if (g.state === STATE.ALERT) {
      mark.visible = true;
      mark.material.color.setHex(0xff2b2b);
      mark.scale.setScalar(0.9 + Math.sin(performance.now() / 90) * 0.18);
    } else if (g.awareness > 0.08) {
      mark.visible = true;
      mark.material.color.setHex(g.awareness > 0.6 ? 0xff8a2b : 0xffd447);
      mark.scale.setScalar(0.45 + g.awareness * 0.6);
    } else {
      mark.visible = false;
    }

    // Ground-projected vision cone: the stealth read the player needs.
    const fan = g.model.fan;
    fan.rotation.y = 0;
    fan.material.opacity = g.state === STATE.ALERT ? 0.20 : 0.085 + g.awareness * 0.12;
    fan.material.color.setHex(g.state === STATE.ALERT ? 0xff3b3b : (g.awareness > 0.3 ? 0xffb03a : 0x7fd4ff));
  }

  _updateCorpse(g, dt) {
    if (g.deathT >= 1) return;
    g.deathT = Math.min(1, g.deathT + dt * 2.4);
    const e = 1 - Math.pow(1 - g.deathT, 3);
    g.root.rotation.z = e * (Math.PI / 2) * g.fallDir;
    g.root.position.y = (g.position.y - HALF.y) - e * 0.35;
  }

  // ------------------------------------------------------------------ combat
  /** Closest guard hit by a ray, as { guard, distance, point, head }. */
  raycast(origin, dir, maxDist) {
    let best = null;
    for (const g of this.list) {
      if (!g.alive) continue;
      const body = { min: new THREE.Vector3(), max: new THREE.Vector3() };
      body.min.set(g.position.x - 0.42, g.position.y - 0.9, g.position.z - 0.42);
      body.max.set(g.position.x + 0.42, g.position.y + 0.62, g.position.z + 0.42);
      const tBody = rayBox(origin, dir, body.min, body.max, maxDist);

      const head = { min: new THREE.Vector3(), max: new THREE.Vector3() };
      head.min.set(g.position.x - 0.20, g.position.y + 0.60, g.position.z - 0.20);
      head.max.set(g.position.x + 0.20, g.position.y + 0.98, g.position.z + 0.20);
      const tHead = rayBox(origin, dir, head.min, head.max, maxDist);

      let t = -1, isHead = false;
      if (tHead >= 0 && (tBody < 0 || tHead <= tBody)) { t = tHead; isHead = true; }
      else if (tBody >= 0) { t = tBody; }
      if (t < 0) continue;
      if (!best || t < best.distance) {
        best = { guard: g, distance: t, point: origin.clone().addScaledVector(dir, t), head: isHead };
      }
    }
    return best;
  }

  /** Returns true when the guard went down from this hit. */
  damage(g, amount, point, dir, headshot) {
    if (!g.alive) return false;
    g.hp -= headshot ? amount * 2.6 : amount;
    this.fx.blood(point, dir, headshot ? 26 : 14);
    this.audio.flesh();
    if (g.state === STATE.PATROL) {
      g.state = STATE.INVESTIGATE;
      g.investigateTimer = 12;
      g.awareness = 0.9;
    }
    if (g.hp > 0) return false;
    this._kill(g);
    return true;
  }

  _kill(g) {
    g.alive = false;
    g.state = STATE.DEAD;
    g.calling = false;
    g.awareness = 0;
    g.fallDir = Math.random() > 0.5 ? 1 : -1;
    g.deathT = 0;
    g.model.mark.visible = false;
    g.model.fan.visible = false;
    this.audio.guardDeath();
  }

  /**
   * The guard a punch would land on: alive, within `range`, and inside a
   * generous cone in front of the player. Returns null when the swing whiffs.
   */
  meleeTarget(origin, dir, range = 2.6) {
    let best = null;
    let bestD = range;
    for (const g of this.list) {
      if (!g.alive) continue;
      _dir.set(g.position.x - origin.x, 0, g.position.z - origin.z);
      const d = _dir.length();
      if (d > bestD) continue;
      if (Math.abs(g.position.y - origin.y) > 2.0) continue;
      _dir.multiplyScalar(1 / Math.max(0.001, d));
      const flat = Math.hypot(dir.x, dir.z) || 1e-6;
      if ((dir.x * _dir.x + dir.z * _dir.z) / flat < 0.55) continue;   // ~57 deg cone
      bestD = d;
      best = g;
    }
    return best;
  }

  /** True when the player is behind the guard's shoulders. */
  isBehind(g, position) {
    const fwd = _v.set(-Math.sin(g.yaw), 0, -Math.cos(g.yaw));
    _dir.set(position.x - g.position.x, 0, position.z - g.position.z).normalize();
    return fwd.x * _dir.x + fwd.z * _dir.z < -0.15;
  }

  /**
   * Lands a punch. From behind it is a silent takedown. From the front it
   * hurts, staggers, and - the point of the whole move - knocks the radio out
   * of his hand, buying the player time to run or to keep swinging.
   *
   * Returns { killed, behind, staggered }.
   */
  punch(g, position) {
    const behind = this.isBehind(g, position);
    const dir = _v.set(g.position.x - position.x, 0, g.position.z - position.z).normalize();
    const point = new THREE.Vector3(g.position.x, g.position.y + 0.5, g.position.z);

    if (behind) {
      this.fx.blood(point, dir, 8);
      this.audio.knockout();
      this._kill(g);
      return { killed: true, behind: true, staggered: false };
    }

    g.hp -= 42;
    this.fx.blood(point, dir, 6);
    this.audio.punchHit();
    if (g.hp <= 0) {
      this.audio.knockout();
      this._kill(g);
      return { killed: true, behind: false, staggered: false };
    }

    // Stagger: pushed back, cannot shoot, and the radio drops out of his hand.
    // He stops counting as a caller for as long as he is reeling.
    g.staggered = 1.5;
    g.calling = false;
    g.shootCooldown = Math.max(g.shootCooldown, 1.6);
    g.velocity.x = dir.x * 5.5;
    g.velocity.z = dir.z * 5.5;
    if (g.state !== STATE.ALERT) {
      g.state = STATE.ALERT;
      g.awareness = 1;
      this.audio.guardShout(0);
    }
    return { killed: false, behind: false, staggered: true };
  }

  /** The nearest lootable corpse within reach, or null. */
  lootableNear(position, radius = 2.6) {
    let best = null;
    let bestD = radius;
    for (const g of this.list) {
      if (g.alive || g.looted) continue;
      const d = g.position.distanceTo(position);
      if (d < bestD) {
        bestD = d;
        best = g;
      }
    }
    return best;
  }

  loot(g) {
    g.looted = true;
    // The stripped guard loses his uniform colours.
    for (const part of g.model.uniform) part.material = STRIPPED_MAT;
  }

  reset() {
    for (const g of this.list) {
      g.hp = GUARD_HP;
      g.alive = true;
      g.state = STATE.PATROL;
      g.waypoint = 1;
      g.awareness = 0;
      g.calling = false;
      g.radioChirp = 0;
      g.staggered = 0;
      g.looted = false;
      g.deathT = 0;
      g.alertedOnce = false;
      g.lastSeen = null;
      g.lastSafe = null;
      g.velocity.set(0, 0, 0);
      g.position.set(tileX(g.def.route[0][0]), 0.92, tileZ(g.def.route[0][1]));
      // Face the next waypoint, and keep yaw and the mesh in agreement.
      const next = g.def.route[1 % g.def.route.length];
      g.yaw = Math.atan2(-(tileX(next[0]) - g.position.x), -(tileZ(next[1]) - g.position.z));
      g.targetYaw = g.yaw;
      g.root.position.copy(g.position);
      g.root.rotation.set(0, g.yaw, 0);
      g.model.fan.visible = true;
      g.model.mark.visible = false;
      g.model.uniform.forEach((p, i) => { p.material = g.model.uniformMats[i]; });
    }
  }
}

export { STATE as GUARD_STATE };

const STRIPPED_MAT = new THREE.MeshLambertMaterial({ color: 0xb9b0a2 });

/**
 * A guard: chunky low-poly figure in navy blues, with a peaked cap, a duty
 * belt, an awareness marker and a vision fan painted on the floor.
 */
function buildGuard() {
  const root = new THREE.Group();
  const navy = new THREE.MeshLambertMaterial({ color: 0x232b45 });
  const navyDark = new THREE.MeshLambertMaterial({ color: 0x1a2036 });
  const skin = new THREE.MeshLambertMaterial({ color: 0xc79a7a });
  const belt = new THREE.MeshLambertMaterial({ color: 0x14161c });
  const badge = new THREE.MeshLambertMaterial({ color: 0xd8c25a });

  const part = (w, h, d, mat, x, y, z, parent = root) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    parent.add(m);
    return m;
  };

  const torso = part(0.62, 0.72, 0.36, navy, 0, 1.22, 0);
  part(0.64, 0.10, 0.38, belt, 0, 0.90, 0);
  part(0.10, 0.10, 0.03, badge, -0.18, 1.40, 0.19);
  const head = part(0.30, 0.30, 0.30, skin, 0, 1.72, 0);
  const cap = part(0.36, 0.10, 0.36, navyDark, 0, 1.90, 0);
  part(0.34, 0.04, 0.14, navyDark, 0, 1.85, -0.20);   // peak

  // Arms and legs pivot from the shoulder / hip, so they swing properly.
  const armL = new THREE.Group();
  armL.position.set(-0.40, 1.52, 0);
  root.add(armL);
  const armLMesh = part(0.18, 0.62, 0.20, navy, 0, -0.31, 0, armL);

  const armR = new THREE.Group();
  armR.position.set(0.40, 1.52, 0);
  root.add(armR);
  const armRMesh = part(0.18, 0.62, 0.20, navy, 0, -0.31, 0, armR);
  // sidearm in the right hand
  part(0.10, 0.10, 0.34, belt, 0, -0.60, -0.16, armR);

  const legL = new THREE.Group();
  legL.position.set(-0.17, 0.88, 0);
  root.add(legL);
  const legLMesh = part(0.24, 0.88, 0.26, navyDark, 0, -0.44, 0, legL);

  const legR = new THREE.Group();
  legR.position.set(0.17, 0.88, 0);
  root.add(legR);
  const legRMesh = part(0.24, 0.88, 0.26, navyDark, 0, -0.44, 0, legR);

  // Floating awareness marker.
  const mark = new THREE.Mesh(
    new THREE.ConeGeometry(0.16, 0.34, 4),
    new THREE.MeshBasicMaterial({ color: 0xffd447, depthTest: false, transparent: true, opacity: 0.95 })
  );
  mark.rotation.x = Math.PI;
  mark.position.y = 2.30;
  mark.renderOrder = 6;
  mark.visible = false;
  root.add(mark);

  // Vision fan on the floor.
  // Centred on the guard's local -Z once laid flat, matching VIEW_FOV.
  const fanGeo = new THREE.CircleGeometry(VIEW_RANGE * 0.55, 24, Math.PI / 2 - 0.92, 1.84);
  fanGeo.rotateX(-Math.PI / 2);
  const fan = new THREE.Mesh(fanGeo, new THREE.MeshBasicMaterial({
    color: 0x7fd4ff, transparent: true, opacity: 0.09, side: THREE.DoubleSide,
    depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  fan.position.y = 0.04;
  fan.renderOrder = 1;
  root.add(fan);

  const uniform = [torso, armLMesh, armRMesh, legLMesh, legRMesh, cap];
  return {
    root, head, armL, armR, legL, legR, mark, fan,
    uniform,
    uniformMats: uniform.map((m) => m.material),
  };
}
