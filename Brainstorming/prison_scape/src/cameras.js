import * as THREE from 'three';
import { tileX, tileZ } from './world.js';

const SPOT_TIME = 1.25;  // seconds of clean view before the camera calls it in
const DECAY = 0.28;      // how fast the meter falls once you break the view
const CAM_HP = 40;
const CAM_PITCH = -0.20; // cameras look slightly down at the floor

/**
 * Above this much suspicion the camera stops sweeping and turns to follow you.
 * Without it, a sweeping camera loses you every couple of seconds and the meter
 * drains as fast as it fills, so cameras were effectively harmless.
 */
const TRACK_AT = 0.10;
const TRACK_RATE = 1.9;               // radians per second while tracking
const TRACK_MARGIN = Math.PI / 10;    // how far past its patrol arc it can turn

/** Shortest signed angle between two headings. */
function wrapPi(a) {
  while (a > Math.PI) a -= Math.PI * 2;
  while (a < -Math.PI) a += Math.PI * 2;
  return a;
}

const _toPlayer = new THREE.Vector3();
const _fwd = new THREE.Vector3();

/**
 * Wall-mounted security cameras. Each one sweeps a cone, fills a detection
 * meter while it has a clean line to the player, and dies to a couple of
 * bullets. Killing the right camera unlocks the door it was wired to.
 */
export class SecurityCameras {
  constructor(scene, world, audio, fx) {
    this.scene = scene;
    this.world = world;
    this.audio = audio;
    this.fx = fx;
    this.cameras = [];
    this.dead = new Set();
    this.group = new THREE.Group();
    scene.add(this.group);
    this._build();
  }

  _build() {
    const bodyMat = new THREE.MeshLambertMaterial({ color: 0x3a4045 });
    const armMat = new THREE.MeshLambertMaterial({ color: 0x2b3034 });

    for (const def of this.world.cameraDefs) {
      const root = new THREE.Group();
      const off = def.offset ?? [0, 0];
      const pos = new THREE.Vector3(tileX(def.tile[0]) + off[0], def.y, tileZ(def.tile[1]) + off[1]);
      root.position.copy(pos);
      this.group.add(root);

      // mount arm going up to the ceiling / tower deck
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.7, 0.14), armMat);
      arm.position.y = 0.42;
      root.add(arm);

      // yoke turns with the sweep
      const yoke = new THREE.Group();
      yoke.rotation.order = 'YXZ';
      root.add(yoke);
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.30, 0.62), bodyMat);
      body.position.z = -0.12;
      yoke.add(body);
      const hood = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.10, 0.40), armMat);
      hood.position.set(0, 0.19, -0.22);
      yoke.add(hood);
      const lens = new THREE.Mesh(
        new THREE.CylinderGeometry(0.11, 0.11, 0.10, 12),
        new THREE.MeshBasicMaterial({ color: 0x101418 })
      );
      lens.rotation.x = Math.PI / 2;
      lens.position.z = -0.44;
      yoke.add(lens);
      const led = new THREE.Mesh(
        new THREE.SphereGeometry(0.05, 8, 6),
        new THREE.MeshBasicMaterial({ color: 0x22ff55 })
      );
      led.position.set(0.12, 0.13, -0.36);
      yoke.add(led);

      // The vision cone is drawn so the player can read and dodge it.
      // The drawn cone is shorter than the real detection range: at full length
      // the long-range yard cameras fill half the screen.
      const half = THREE.MathUtils.degToRad(def.fov) / 2;
      const shown = def.range * 0.72;
      const radius = Math.tan(half) * shown;
      const coneGeo = new THREE.ConeGeometry(radius, shown, 20, 1, true);
      // Apex at the lens, opening away down the camera's local -Z.
      coneGeo.translate(0, -shown / 2, 0);
      coneGeo.rotateX(Math.PI / 2);
      const coneMat = new THREE.MeshBasicMaterial({
        color: 0x39d6ff, transparent: true, opacity: 0.045,
        side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending,
      });
      const cone = new THREE.Mesh(coneGeo, coneMat);
      cone.renderOrder = 1;
      yoke.add(cone);

      this.cameras.push({
        id: def.id,
        def,
        root, yoke, led, cone, lens,
        position: pos.clone(),
        baseYaw: THREE.MathUtils.degToRad(def.yaw),
        sweep: THREE.MathUtils.degToRad(def.sweep),
        period: def.period,
        range: def.range,
        cosHalfFov: Math.cos(half),
        hp: CAM_HP,
        alive: true,
        yaw: 0,
        phase: Math.random() * Math.PI * 2,
        meter: 0,
        seeing: false,
        tracking: false,
        reporting: false,
        lastKnown: null,
      });
    }
  }

  /** World-space direction the camera is currently pointing (yaw + fixed downward tilt). */
  _forward(cam, out) {
    const cp = Math.cos(CAM_PITCH);
    return out.set(
      -Math.sin(cam.yaw) * cp,
      Math.sin(CAM_PITCH),
      -Math.cos(cam.yaw) * cp
    );
  }

  /**
   * Advances every camera. Returns the highest detection meter (0..1) and
   * whether one of them completed a detection this frame.
   */
  update(dt, player, gameActive) {
    let worst = 0;
    let reporters = 0;
    let justReported = null;

    for (const cam of this.cameras) {
      if (!cam.alive) continue;

      // ------------------------------------------------- aim: sweep or track
      if (cam.tracking && cam.lastKnown) {
        // Turn toward where the player was last seen, but only within the arc
        // the mount physically allows.
        const want = Math.atan2(
          -(cam.lastKnown.x - cam.position.x),
          -(cam.lastKnown.z - cam.position.z)
        );
        const limit = cam.sweep + TRACK_MARGIN;
        const off = THREE.MathUtils.clamp(wrapPi(want - cam.baseYaw), -limit, limit);
        const targetYaw = cam.baseYaw + off;
        const step = THREE.MathUtils.clamp(
          wrapPi(targetYaw - cam.yaw), -TRACK_RATE * dt, TRACK_RATE * dt
        );
        cam.yaw += step;
      } else {
        cam.phase += (dt / cam.period) * Math.PI * 2;
        cam.yaw = cam.baseYaw + Math.sin(cam.phase) * cam.sweep;
      }
      cam.yoke.rotation.y = cam.yaw;
      cam.yoke.rotation.x = CAM_PITCH;

      let sees = false;
      if (gameActive && player.alive && !player.disguised) {
        const eye = player.chest;
        _toPlayer.copy(eye).sub(cam.position);
        const dist = _toPlayer.length();
        if (dist < cam.range && dist > 0.2) {
          _toPlayer.multiplyScalar(1 / dist);
          this._forward(cam, _fwd);
          if (_fwd.dot(_toPlayer) > cam.cosHalfFov) {
            sees = this.world.colliders.lineOfSight(cam.position, eye);
          }
        }
      }

      cam.seeing = sees;
      if (sees) {
        (cam.lastKnown ??= new THREE.Vector3()).copy(player.position);
        // Closer is quicker to resolve; crouching in a cone only slows the
        // camera down, it does not hide you from it.
        const d = cam.position.distanceTo(player.chest);
        let rate = 1.15 - 0.55 * Math.min(1, d / cam.range);
        if (player.crouching) rate *= 0.7;
        const before = cam.meter;
        cam.meter = Math.min(1, cam.meter + (dt / SPOT_TIME) * rate);
        if (before < TRACK_AT && cam.meter >= TRACK_AT) {
          this.audio.suspicion();
          cam.tracking = true;      // stop sweeping, lock on
        }
        // A full meter means the control room has you on screen. Same as a
        // guard on his radio, it feeds the lockdown clock rather than ending
        // the run outright - shoot the camera out and it stops calling.
        if (before < 1 && cam.meter >= 1) {
          cam.reporting = true;
          justReported = cam;
        }
      } else {
        cam.meter = Math.max(0, cam.meter - dt * DECAY);
        if (cam.meter <= 0 && cam.tracking) {
          // Lost you for good: resume the patrol sweep from where it is aimed.
          cam.tracking = false;
          cam.lastKnown = null;
          cam.phase = Math.asin(
            THREE.MathUtils.clamp((cam.yaw - cam.baseYaw) / (cam.sweep || 1), -1, 1)
          );
        }
      }

      // LED and cone colour track the meter: green -> amber -> red.
      const m = cam.meter;
      const col = m <= 0 ? 0x22ff55 : (m < 0.6 ? 0xffc23a : 0xff2b2b);
      cam.led.material.color.setHex(col);
      cam.cone.material.color.setHex(m > 0.05 ? (m < 0.6 ? 0xffc23a : 0xff3b3b) : 0x39d6ff);
      // Kept low: standing inside a cone means looking through the whole
      // volume, and at high opacity the red wash swallowed the corridor.
      cam.cone.material.opacity = 0.035 + m * 0.055 + (sees ? 0.02 : 0);
      if (m > 0.6) {
        cam.led.visible = Math.sin(cam.phase * 24) > -0.2;
      } else {
        cam.led.visible = true;
      }

      // It keeps calling you in until it loses you completely, or is wrecked.
      if (cam.meter < 1) cam.reporting = false;
      if (cam.reporting) reporters++;

      worst = Math.max(worst, cam.meter);
    }

    return { worst, reporters, justReported };
  }

  /**
   * Ray/camera intersection for the player's shots. Returns the closest hit
   * as { cam, distance, point } or null.
   */
  raycast(origin, dir, maxDist) {
    let best = null;
    for (const cam of this.cameras) {
      if (!cam.alive) continue;
      const t = raySphere(origin, dir, cam.position, 0.55, maxDist);
      if (t < 0) continue;
      if (!best || t < best.distance) {
        best = {
          cam,
          distance: t,
          point: origin.clone().addScaledVector(dir, t),
        };
      }
    }
    return best;
  }

  /** Returns true when the shot finished the camera off. */
  damage(cam, amount, point) {
    if (!cam.alive) return false;
    cam.hp -= amount;
    this.fx.sparks(point, new THREE.Vector3(0, 1, 0), 8, [1.0, 0.9, 0.5]);
    if (cam.hp > 0) {
      this.audio.impact(true);
      return false;
    }
    this._kill(cam);
    return true;
  }

  _kill(cam) {
    cam.alive = false;
    cam.meter = 0;
    cam.tracking = false;
    cam.reporting = false;
    cam.lastKnown = null;
    cam.cone.visible = false;
    cam.led.visible = false;
    cam.lens.material.color.setHex(0x000000);
    cam.yoke.rotation.z = 0.7;
    cam.yoke.rotation.x = 0.9;
    cam.yoke.position.y -= 0.12;
    this.dead.add(cam.id);
    this.audio.cameraBreak();
    this.fx.glass(cam.position, 24);
    this.fx.smoke(cam.position, 8);
    cam.smokeTimer = 0;
  }

  /** Lingering smoke from every wrecked camera. */
  updateWrecks(dt) {
    for (const cam of this.cameras) {
      if (cam.alive) continue;
      cam.smokeTimer = (cam.smokeTimer ?? 0) - dt;
      if (cam.smokeTimer <= 0) {
        cam.smokeTimer = 0.5 + Math.random() * 0.6;
        this.fx.smoke(cam.position, 1);
      }
    }
  }

  get aliveCount() {
    return this.cameras.filter((c) => c.alive).length;
  }

  /** Cameras still watching the route to a given door. */
  camerasFor(ids) {
    return this.cameras.filter((c) => ids.includes(c.id));
  }

  reset() {
    for (const cam of this.cameras) {
      cam.alive = true;
      cam.hp = CAM_HP;
      cam.meter = 0;
      cam.tracking = false;
      cam.reporting = false;
      cam.lastKnown = null;
      cam.cone.visible = true;
      cam.led.visible = true;
      cam.lens.material.color.setHex(0x101418);
      cam.yoke.rotation.set(0, 0, 0);
      cam.yoke.position.y = 0;
    }
    this.dead.clear();
  }
}

/** Ray/sphere entry distance, or -1. */
function raySphere(origin, dir, center, radius, maxDist) {
  const ox = origin.x - center.x;
  const oy = origin.y - center.y;
  const oz = origin.z - center.z;
  const b = ox * dir.x + oy * dir.y + oz * dir.z;
  const c = ox * ox + oy * oy + oz * oz - radius * radius;
  if (c > 0 && b > 0) return -1;
  const disc = b * b - c;
  if (disc < 0) return -1;
  const t = -b - Math.sqrt(disc);
  if (t < 0 || t > maxDist) return -1;
  return t;
}
