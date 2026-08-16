import * as THREE from 'three';

const _v = new THREE.Vector3();
const _muzzleWorld = new THREE.Vector3();
const _dir = new THREE.Vector3();
const _right = new THREE.Vector3();
const _up = new THREE.Vector3();

export const RIFLE_STATS = {
  name: 'AR-7 "SCAVENGER"',
  magSize: 30,
  reserveMax: 270,
  rpm: 620,
  damage: 27,
  headMultiplier: 2.7,
  falloffStart: 45,
  falloffEnd: 110,
  falloffFloor: 0.55,
  range: 240,
  reloadTime: 2.15,
  reloadTimeEmpty: 2.75,
};

/**
 * The one and only weapon: a scavenged 5.56 carbine.
 * Owns its viewmodel (rendered in an overlay scene so it never clips walls),
 * hitscan ballistics, recoil, spread, ADS and reload state.
 */
export class Rifle {
  constructor(ctx) {
    this.camera = ctx.camera;
    this.viewScene = ctx.viewScene;
    this.colliders = ctx.colliders;
    this.effects = ctx.effects;
    this.audio = ctx.audio;
    this.player = ctx.player;
    this.enemies = ctx.enemies;

    this.ammo = RIFLE_STATS.magSize;
    this.reserve = 120;
    this.fireInterval = 60 / RIFLE_STATS.rpm;
    this.cooldown = 0;
    this.reloading = false;
    this.reloadTimer = 0;
    this.reloadDuration = 0;
    this.aiming = false;
    this.adsAmount = 0;

    this.bloom = 0;          // accumulated recoil spread
    this.kick = 0;           // viewmodel kickback
    this.kickRot = 0;
    this.swayX = 0;
    this.swayY = 0;
    this.bobT = 0;
    this.shotsFired = 0;
    this.shotsHit = 0;
    this.lastHitWasKill = false;

    this.onHitmarker = null; // (isHeadshot, isKill) => void
    this.onAmmoChange = null;

    this.group = new THREE.Group();
    this.viewScene.add(this.group);
    this.muzzleLocal = new THREE.Vector3();
    this._build();

    // Distances are tuned against the 58 degree view camera: the rifle reads
    // about half the screen width at the hip and centres its optic when aiming.
    this.restPos = new THREE.Vector3(0.30, -0.235, -0.78);
    this.adsPos = new THREE.Vector3(0, 0, -0.62);
    this.sprintPos = new THREE.Vector3(0.36, -0.30, -0.70);
    this.group.position.copy(this.restPos);
  }

  _build() {
    const gun = new THREE.Group();
    this.gun = gun;
    this.group.add(gun);

    // Keep metalness low: without a strong environment map, metallic surfaces
    // render almost black.
    const dark = new THREE.MeshStandardMaterial({ color: 0x3c4046, roughness: 0.5, metalness: 0.32 });
    const body = new THREE.MeshStandardMaterial({ color: 0x46443b, roughness: 0.66, metalness: 0.22 });
    const worn = new THREE.MeshStandardMaterial({ color: 0x574a3a, roughness: 0.85, metalness: 0.12 });
    const tape = new THREE.MeshStandardMaterial({ color: 0x3a3831, roughness: 1, metalness: 0 });
    const glow = new THREE.MeshBasicMaterial({ color: 0xff3b30 });
    this.matDark = dark;

    const box = new THREE.BoxGeometry(1, 1, 1);
    const cyl = new THREE.CylinderGeometry(0.5, 0.5, 1, 12);

    const add = (geo, mat, x, y, z, sx, sy, sz, rx = 0, ry = 0, rz = 0) => {
      const m = new THREE.Mesh(geo, mat);
      m.position.set(x, y, z);
      m.scale.set(sx, sy, sz);
      m.rotation.set(rx, ry, rz);
      gun.add(m);
      return m;
    };

    // Local frame: the optic sits at (0, 0.075, 0) so ADS can centre it exactly.
    // -Z points down range.
    const OY = 0.075;

    // upper receiver
    add(box, body, 0, -OY + 0.048, 0.02, 0.056, 0.062, 0.30);
    // lower receiver + magwell
    add(box, body, 0, -OY + 0.008, 0.06, 0.05, 0.05, 0.14);
    // magazine, slightly curved look via two segments
    add(box, worn, 0, -OY - 0.048, 0.075, 0.042, 0.10, 0.075, 0.18);
    add(box, worn, 0, -OY - 0.105, 0.093, 0.040, 0.045, 0.07, 0.34);
    // pistol grip
    add(box, dark, 0, -OY - 0.055, 0.145, 0.04, 0.10, 0.05, 0.35);
    // trigger guard
    add(box, dark, 0, -OY - 0.018, 0.113, 0.03, 0.012, 0.05);
    // stock
    add(box, worn, 0, -OY + 0.036, 0.20, 0.045, 0.052, 0.10);
    add(box, dark, 0, -OY + 0.026, 0.265, 0.052, 0.075, 0.045);
    // handguard with rails
    add(box, dark, 0, -OY + 0.046, -0.155, 0.052, 0.056, 0.24);
    for (const s of [-1, 1]) {
      add(box, dark, s * 0.030, -OY + 0.046, -0.155, 0.006, 0.040, 0.235);
    }
    // taped-on grip under the handguard
    add(box, tape, 0, -OY + 0.006, -0.14, 0.030, 0.040, 0.055, 0.25);
    // barrel + muzzle brake
    add(cyl, dark, 0, -OY + 0.046, -0.30, 0.017, 0.14, 0.017, Math.PI / 2);
    const brake = add(cyl, dark, 0, -OY + 0.046, -0.385, 0.026, 0.05, 0.026, Math.PI / 2);
    brake.name = 'brake';
    // top rail
    add(box, dark, 0, -OY + 0.082, 0.0, 0.032, 0.012, 0.40);
    // optic body sitting on the rail, its glass centred at local (0, OY-ish)
    add(box, dark, 0, 0.0, 0.0, 0.040, 0.052, 0.085);
    const lens = add(cyl, new THREE.MeshStandardMaterial({ color: 0x0d1a16, roughness: 0.25, metalness: 0.8 }),
      0, 0.0, -0.045, 0.031, 0.006, 0.031, Math.PI / 2);
    lens.name = 'lens';
    // red dot
    const dot = new THREE.Mesh(new THREE.CircleGeometry(0.0035, 12), glow);
    dot.position.set(0, 0, -0.05);
    gun.add(dot);
    this.dot = dot;
    // charging handle + ejection port
    add(box, dark, 0.036, -OY + 0.062, 0.12, 0.022, 0.02, 0.05);
    add(box, dark, 0, -OY + 0.075, 0.155, 0.03, 0.014, 0.07);
    // sling loop, purely cosmetic
    add(box, tape, -0.03, -OY + 0.02, -0.05, 0.008, 0.03, 0.008);

    // left hand on the handguard, right hand on the grip
    const skin = new THREE.MeshStandardMaterial({ color: 0x8a6647, roughness: 0.95 });
    const glove = new THREE.MeshStandardMaterial({ color: 0x554a3d, roughness: 1 });
    const lh = new THREE.Group();
    lh.position.set(0.0, -OY - 0.015, -0.155);
    const palm = new THREE.Mesh(box, glove);
    palm.scale.set(0.055, 0.055, 0.09);
    lh.add(palm);
    const thumb = new THREE.Mesh(box, skin);
    thumb.position.set(0.012, 0.028, -0.02);
    thumb.scale.set(0.022, 0.022, 0.06);
    thumb.rotation.x = 0.3;
    lh.add(thumb);
    const forearmL = new THREE.Mesh(box, glove);
    forearmL.position.set(0.05, -0.055, 0.06);
    forearmL.scale.set(0.06, 0.06, 0.22);
    forearmL.rotation.set(-0.5, -0.45, 0);
    lh.add(forearmL);
    gun.add(lh);
    this.leftHand = lh;

    const rh = new THREE.Group();
    rh.position.set(0.008, -OY - 0.045, 0.15);
    const palmR = new THREE.Mesh(box, glove);
    palmR.scale.set(0.05, 0.075, 0.055);
    rh.add(palmR);
    const forearmR = new THREE.Mesh(box, glove);
    forearmR.position.set(0.03, -0.03, 0.13);
    forearmR.scale.set(0.062, 0.062, 0.2);
    forearmR.rotation.set(0.25, -0.2, 0);
    rh.add(forearmR);
    gun.add(rh);

    // muzzle flash sprite, hidden until a shot goes off
    const flashMat = new THREE.SpriteMaterial({
      color: 0xffc46a, transparent: true, opacity: 0,
      blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false,
    });
    const flash = new THREE.Sprite(flashMat);
    flash.position.set(0, -OY + 0.046, -0.42);
    flash.scale.set(0.28, 0.28, 0.28);
    gun.add(flash);
    this.flashSprite = flash;

    // a second, thinner flare across the brake
    const flare = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.06),
      new THREE.MeshBasicMaterial({ color: 0xffd9a0, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false }));
    flare.position.copy(flash.position);
    gun.add(flare);
    this.flashFlare = flare;

    this.muzzleLocal.set(0, -OY + 0.046, -0.42);
  }

  get canFire() {
    return !this.reloading && this.ammo > 0 && this.cooldown <= 0;
  }

  get spread() {
    const p = this.player;
    let s = 0.0075;
    if (this.adsAmount > 0.5) s = 0.0016;
    if (p) {
      if (p.crouching) s *= 0.72;
      if (!p.grounded) s *= 2.6;
      s += Math.min(0.02, p.speed2D * 0.0022);
    }
    return s + this.bloom;
  }

  /** 0..1, drives the HUD crosshair gap. */
  get spreadNorm() {
    return Math.min(1, this.spread / 0.055);
  }

  addAmmo(rounds) {
    const before = this.reserve;
    this.reserve = Math.min(RIFLE_STATS.reserveMax, this.reserve + rounds);
    if (this.onAmmoChange) this.onAmmoChange();
    return this.reserve - before;
  }

  refill() {
    this.ammo = RIFLE_STATS.magSize;
    this.reserve = 120;
    this.reloading = false;
    this.reloadTimer = 0;
    this.cooldown = 0;
    this.bloom = 0;
    this.kick = 0;
    this.kickRot = 0;
    this.shotsFired = 0;
    this.shotsHit = 0;
    if (this.onAmmoChange) this.onAmmoChange();
  }

  startReload() {
    if (this.reloading || this.ammo >= RIFLE_STATS.magSize || this.reserve <= 0) return;
    this.reloading = true;
    this.reloadDuration = this.ammo === 0 ? RIFLE_STATS.reloadTimeEmpty : RIFLE_STATS.reloadTime;
    this.reloadTimer = this.reloadDuration;
    this.audio.reloadStart();
  }

  _finishReload() {
    const need = RIFLE_STATS.magSize - this.ammo;
    const take = Math.min(need, this.reserve);
    this.ammo += take;
    this.reserve -= take;
    this.reloading = false;
    this.audio.reloadEnd();
    if (this.onAmmoChange) this.onAmmoChange();
  }

  fire() {
    if (this.reloading) return false;
    if (this.ammo <= 0) {
      if (this.cooldown <= 0) {
        this.audio.dryFire();
        this.cooldown = 0.25;
      }
      return false;
    }
    if (this.cooldown > 0) return false;

    this.ammo--;
    this.shotsFired++;
    // Add the interval rather than assigning it, so the leftover from a long
    // frame carries over and the real rate matches the rpm at any frame rate.
    this.cooldown += this.fireInterval;
    this.audio.shot();
    if (this.onAmmoChange) this.onAmmoChange();

    // --- build the shot ray from the camera, offset by current spread ---
    const cam = this.camera;
    cam.getWorldDirection(_dir);
    _right.set(1, 0, 0).applyQuaternion(cam.quaternion);
    _up.set(0, 1, 0).applyQuaternion(cam.quaternion);
    const s = this.spread;
    const a = Math.random() * Math.PI * 2;
    const r = Math.sqrt(Math.random()) * s;
    _dir.addScaledVector(_right, Math.cos(a) * r).addScaledVector(_up, Math.sin(a) * r).normalize();

    const origin = cam.getWorldPosition(_v).clone();
    const worldHit = this.colliders.raycast(origin, _dir, RIFLE_STATS.range);
    const enemyHit = this.enemies ? this.enemies.raycast(origin, _dir, RIFLE_STATS.range) : null;

    let end;
    if (enemyHit && (!worldHit || enemyHit.distance < worldHit.distance)) {
      end = enemyHit.point;
      const falloff = this._falloff(enemyHit.distance);
      let dmg = RIFLE_STATS.damage * falloff;
      if (enemyHit.part === 'head') dmg *= RIFLE_STATS.headMultiplier;
      else if (enemyHit.part === 'limb') dmg *= 0.75;
      const killed = enemyHit.enemy.hit(dmg, _dir, enemyHit.point, enemyHit.part);
      this.shotsHit++;
      this.effects.impact(enemyHit.point, _dir.clone().negate(), 'flesh');
      if (enemyHit.part === 'head') this.audio.headshot(); else this.audio.flesh();
      if (this.onHitmarker) this.onHitmarker(enemyHit.part === 'head', killed);
    } else if (worldHit) {
      end = worldHit.point;
      const kind = worldHit.box.tag === 'prop' ? 'metal' : 'concrete';
      this.effects.impact(worldHit.point, worldHit.normal, kind);
      this.audio.impact(kind === 'metal');
    } else {
      end = origin.clone().addScaledVector(_dir, RIFLE_STATS.range);
    }

    // --- visuals ---
    this.camera.localToWorld(_muzzleWorld.copy(this.muzzleLocal));
    this.effects.tracer(_muzzleWorld, end);
    this.effects.pointFlash(_muzzleWorld.clone(), 9);
    this.effects.sparks.emit(
      _muzzleWorld.clone().addScaledVector(_right, 0.12),
      _right.clone().multiplyScalar(0.8).setY(0.5),
      { count: 2, speed: 2.6, spread: 0.5, life: 0.5, size: 0.035 }
    );
    this.effects.smoke(_muzzleWorld.clone().addScaledVector(_dir, 0.25), _dir.clone(), 2);
    this.flashSprite.material.opacity = 1;
    this.flashSprite.material.rotation = Math.random() * Math.PI * 2;
    this.flashSprite.scale.setScalar(0.22 + Math.random() * 0.12);
    this.flashFlare.material.opacity = 0.85;
    this.flashFlare.rotation.z = Math.random() * Math.PI;

    // --- recoil ---
    const vertical = 0.0125 + Math.random() * 0.006;
    const horizontal = (Math.random() - 0.5) * 0.010;
    const scale = this.adsAmount > 0.5 ? 0.62 : 1;
    this.player.applyRecoil(vertical * scale, horizontal * scale);
    this.kick = Math.min(0.06, this.kick + 0.030);
    this.kickRot = Math.min(0.30, this.kickRot + 0.16);
    this.bloom = Math.min(0.045, this.bloom + (this.adsAmount > 0.5 ? 0.0032 : 0.0055));
    return true;
  }

  _falloff(distance) {
    const { falloffStart, falloffEnd, falloffFloor } = RIFLE_STATS;
    if (distance <= falloffStart) return 1;
    if (distance >= falloffEnd) return falloffFloor;
    const t = (distance - falloffStart) / (falloffEnd - falloffStart);
    return 1 - t * (1 - falloffFloor);
  }

  update(dt, input, opts = {}) {
    const active = opts.active !== false;
    const triggerHeld = active && input.buttons[0] && !this.reloading;
    // While the trigger is down the cooldown may run negative, so the leftover
    // from a long frame carries into the next shot and the rate matches the rpm
    // whatever the frame rate. Off the trigger it floors at zero, otherwise idle
    // time would bank credit and the first shots of a burst would double up.
    this.cooldown -= dt;
    const floor = triggerHeld ? -this.fireInterval : 0;
    if (this.cooldown < floor) this.cooldown = floor;
    this.bloom = Math.max(0, this.bloom - dt * 0.075);

    if (active) {
      this.aiming = input.buttons[2] && !this.reloading && !this.player.sprinting;
      if (input.pressedAny('KeyR', 'char:r')) this.startReload();
      if (input.buttons[0]) this.fire();
      if (this.ammo === 0 && !this.reloading && this.reserve > 0) this.startReload();
    } else {
      this.aiming = false;
    }

    if (this.reloading) {
      this.reloadTimer -= dt;
      if (this.reloadTimer <= 0) this._finishReload();
    }

    const adsTarget = this.aiming ? 1 : 0;
    this.adsAmount += (adsTarget - this.adsAmount) * Math.min(1, 14 * dt);

    // ---- viewmodel placement ----
    const sprintAmount = this.player.sprinting && this.player.speed2D > 4 ? 1 : 0;
    this._sprintLerp = (this._sprintLerp ?? 0) + (sprintAmount - (this._sprintLerp ?? 0)) * Math.min(1, 9 * dt);

    _v.copy(this.restPos).lerp(this.sprintPos, this._sprintLerp).lerp(this.adsPos, this.adsAmount);

    // sway lags the mouse
    const swayTargetX = THREE.MathUtils.clamp(-input.mouseDX * 0.0006, -0.035, 0.035);
    const swayTargetY = THREE.MathUtils.clamp(input.mouseDY * 0.0006, -0.035, 0.035);
    const swayK = Math.min(1, 10 * dt);
    this.swayX += (swayTargetX * (1 - this.adsAmount * 0.75) - this.swayX) * swayK;
    this.swayY += (swayTargetY * (1 - this.adsAmount * 0.75) - this.swayY) * swayK;

    // walk bob
    const p = this.player;
    if (p.grounded && p.speed2D > 0.6) {
      this.bobT += dt * (p.sprinting ? 12 : 8.5);
    }
    const bobScale = (1 - this.adsAmount * 0.8) * Math.min(1, p.speed2D / 5);
    const bobX = Math.cos(this.bobT) * 0.011 * bobScale;
    const bobY = Math.abs(Math.sin(this.bobT)) * 0.009 * bobScale;

    // reload animation: dip down and roll the weapon over
    let reloadDip = 0, reloadRoll = 0, reloadYaw = 0;
    if (this.reloading) {
      const t = 1 - this.reloadTimer / this.reloadDuration;
      const curve = Math.sin(Math.min(1, t * 1.15) * Math.PI);
      reloadDip = curve * 0.10;
      reloadRoll = curve * 0.5;
      reloadYaw = curve * 0.22;
    }

    this.group.position.set(
      _v.x + this.swayX + bobX,
      _v.y + this.swayY - bobY - reloadDip,
      _v.z + this.kick
    );
    this.group.rotation.set(
      this.kickRot * 0.35 + reloadRoll * 0.25 + this.swayY * 1.2,
      reloadYaw + this.swayX * 1.6 - this._sprintLerp * 0.5,
      reloadRoll + this._sprintLerp * 0.35
    );

    this.kick *= Math.exp(-14 * dt);
    this.kickRot *= Math.exp(-13 * dt);

    // flash decay
    if (this.flashSprite.material.opacity > 0) {
      this.flashSprite.material.opacity = Math.max(0, this.flashSprite.material.opacity - dt * 26);
      this.flashFlare.material.opacity = Math.max(0, this.flashFlare.material.opacity - dt * 24);
    }
    this.dot.material.color.setHex(this.adsAmount > 0.4 ? 0xff5040 : 0xff3b30);
  }
}
