import * as THREE from 'three';

/** Stats for every gun that can end up in the escapee's hands. */
export const WEAPONS = {
  pistol: {
    id: 'pistol', name: 'PISTOLET 9mm', magSize: 12, reserveMax: 90,
    damage: 34, pellets: 1, rpm: 340, auto: false, spread: 0.006, sprintSpread: 0.05,
    reloadTime: 1.35, recoil: 0.028, range: 90, noise: 34, sound: 'pistol',
  },
  shotgun: {
    id: 'shotgun', name: 'FUSIL A POMPE', magSize: 6, reserveMax: 48,
    damage: 13, pellets: 9, rpm: 78, auto: false, spread: 0.055, sprintSpread: 0.11,
    reloadTime: 2.4, recoil: 0.075, range: 32, noise: 46, sound: 'shotgun',
  },
  rifle: {
    id: 'rifle', name: 'FUSIL D\'ASSAUT', magSize: 30, reserveMax: 210,
    damage: 24, pellets: 1, rpm: 640, auto: true, spread: 0.010, sprintSpread: 0.07,
    reloadTime: 1.9, recoil: 0.020, range: 110, noise: 40, sound: 'rifle',
  },
};

const _v = new THREE.Vector3();
const _right = new THREE.Vector3();
const _up = new THREE.Vector3();

/**
 * Everything the player's hands do: which guns are owned, ammo bookkeeping,
 * fire timing, reloads, recoil, and the first-person view model.
 */
export class Arsenal {
  constructor(camera, audio, fx) {
    this.camera = camera;
    this.audio = audio;
    this.fx = fx;

    this.owned = new Set();
    this.mag = {};
    this.reserve = {};
    for (const k of Object.keys(WEAPONS)) {
      this.mag[k] = 0;
      this.reserve[k] = 0;
    }

    this.current = null;
    this.cooldown = 0;
    this.reloading = 0;
    this.swapping = 0;
    /** Melee: a bare-knuckle swing, always available, gun or not. */
    this.meleeCooldown = 0;
    this.meleeAnim = 0;

    this.viewGroup = new THREE.Group();
    this.viewGroup.renderOrder = 10;
    camera.add(this.viewGroup);
    this.models = {};
    for (const k of [...Object.keys(WEAPONS), 'fists']) {
      const m = buildViewModel(k);
      m.visible = k === 'fists';
      this.viewGroup.add(m);
      this.models[k] = m;
    }
    // Where each model rests on screen. Fists sit lower and further out so
    // the knuckles read rather than the forearm.
    this._bases = {
      pistol: new THREE.Vector3(0.26, -0.23, -0.66),
      shotgun: new THREE.Vector3(0.26, -0.24, -0.74),
      rifle: new THREE.Vector3(0.26, -0.24, -0.72),
      fists: new THREE.Vector3(0.30, -0.34, -0.86),
    };
    this._sway = new THREE.Vector2();
    this._recoilZ = 0;
    this._recoilPitch = 0;
    this._bob = 0;
  }

  reset() {
    this.owned.clear();
    for (const k of Object.keys(WEAPONS)) {
      this.mag[k] = 0;
      this.reserve[k] = 0;
    }
    this.current = null;
    this.cooldown = 0;
    this.reloading = 0;
    this.meleeCooldown = 0;
    this.meleeAnim = 0;
    for (const k of Object.keys(this.models)) this.models[k].visible = k === 'fists';
  }

  /**
   * Swings. Always allowed, armed or not - with a gun in hand it reads as a
   * pistol-whip. Returns true when the swing actually started, so the caller
   * can look for something to hit.
   */
  tryMelee(player) {
    if (this.meleeCooldown > 0 || this.reloading > 0 || this.swapping > 0) return false;
    this.meleeCooldown = 0.62;
    this.meleeAnim = 0.62;
    this.audio.punchSwing();
    // A swing is quiet, but not silent.
    player.noiseSpike = Math.max(player.noiseSpike, 6);
    return true;
  }

  get weapon() {
    return this.current ? WEAPONS[this.current] : null;
  }

  get hasGun() {
    return this.current !== null;
  }

  /** Picks up a gun. Returns a short line for the HUD, or null if nothing changed. */
  give(kind, ammo = null) {
    const w = WEAPONS[kind];
    if (!w) return null;
    const first = !this.owned.has(kind);
    if (first) {
      this.owned.add(kind);
      this.mag[kind] = w.magSize;
      this.reserve[kind] = Math.min(w.reserveMax, ammo ?? w.magSize * 2);
      this.select(kind);
      return `${w.name} RECUPERE`;
    }
    const before = this.reserve[kind];
    this.reserve[kind] = Math.min(w.reserveMax, before + (ammo ?? w.magSize));
    if (this.reserve[kind] === before) return null;
    return `+${this.reserve[kind] - before} MUNITIONS`;
  }

  /** Ammo crate: tops up whatever the player is carrying. */
  giveAmmo(amount) {
    if (this.owned.size === 0) return null;
    let added = 0;
    for (const kind of this.owned) {
      const w = WEAPONS[kind];
      const before = this.reserve[kind];
      this.reserve[kind] = Math.min(w.reserveMax, before + Math.round(amount * (w.magSize / 12)));
      added += this.reserve[kind] - before;
    }
    return added > 0 ? `+${added} MUNITIONS` : null;
  }

  select(kind) {
    if (!this.owned.has(kind) || this.current === kind) return;
    if (this.current) this.models[this.current].visible = false;
    this.models.fists.visible = false;
    this.current = kind;
    this.models[kind].visible = true;
    this.reloading = 0;
    this.swapping = 0.35;
    this.cooldown = Math.max(this.cooldown, 0.3);
  }

  cycle(dir) {
    const list = Object.keys(WEAPONS).filter((k) => this.owned.has(k));
    if (list.length < 2) return;
    const i = list.indexOf(this.current);
    this.select(list[(i + dir + list.length) % list.length]);
  }

  startReload() {
    const w = this.weapon;
    if (!w || this.reloading > 0) return;
    if (this.mag[w.id] >= w.magSize || this.reserve[w.id] <= 0) return;
    this.reloading = w.reloadTime;
    this.audio.reloadStart();
  }

  /**
   * Attempts to fire. `onRay(origin, dir, damage)` is called once per pellet.
   * Returns true when a round actually left the barrel.
   */
  tryFire(player, held, justPressed, onRay) {
    const w = this.weapon;
    if (!w) return false;
    if (this.reloading > 0 || this.swapping > 0 || this.cooldown > 0) return false;
    if (w.auto ? !held : !justPressed) return false;

    if (this.mag[w.id] <= 0) {
      if (justPressed) {
        this.audio.dryFire();
        this.cooldown = 0.25;
        this.startReload();
      }
      return false;
    }

    this.mag[w.id]--;
    this.cooldown = 60 / w.rpm;

    const origin = player.eye;
    const dir = player.lookDir();
    _right.set(dir.z, 0, -dir.x).normalize();
    _up.crossVectors(_right, dir).normalize();

    const spread = player.sprinting ? w.sprintSpread : (player.crouching ? w.spread * 0.6 : w.spread);
    for (let i = 0; i < w.pellets; i++) {
      _v.copy(dir);
      const a = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.random()) * spread;
      _v.addScaledVector(_right, Math.cos(a) * r);
      _v.addScaledVector(_up, Math.sin(a) * r);
      _v.normalize();
      onRay(origin, _v.clone(), w.damage, w);
    }

    // feedback
    const muzzle = origin.clone().addScaledVector(dir, 0.6);
    this.fx.muzzleFlash(muzzle, w.pellets > 1 ? 1.7 : 1);
    this.audio.shot(w.sound, 0);
    player.addKick(w.recoil * (0.7 + Math.random() * 0.6), (Math.random() - 0.5) * w.recoil * 0.5);
    player.noiseSpike = Math.max(player.noiseSpike, w.noise);
    this._recoilZ = Math.min(0.12, this._recoilZ + w.recoil * 1.9);
    this._recoilPitch = Math.min(0.4, this._recoilPitch + w.recoil * 4.5);
    return true;
  }

  update(dt, player) {
    if (this.cooldown > 0) this.cooldown -= dt;
    if (this.swapping > 0) this.swapping -= dt;
    if (this.meleeCooldown > 0) this.meleeCooldown -= dt;
    if (this.meleeAnim > 0) this.meleeAnim = Math.max(0, this.meleeAnim - dt);
    if (this.reloading > 0) {
      this.reloading -= dt;
      if (this.reloading <= 0) {
        const w = this.weapon;
        const need = w.magSize - this.mag[w.id];
        const take = Math.min(need, this.reserve[w.id]);
        this.mag[w.id] += take;
        this.reserve[w.id] -= take;
        this.audio.reloadEnd();
      }
    }

    // ---- view model animation: sway from mouse, bob from walking, recoil ----
    this._sway.x += (-player.viewKick.y * 0.4 - this._sway.x) * Math.min(1, dt * 8);
    this._sway.y += (player.viewKick.x * 0.4 - this._sway.y) * Math.min(1, dt * 8);
    this._recoilZ *= Math.pow(0.0009, dt);
    this._recoilPitch *= Math.pow(0.0012, dt);

    const planar = Math.hypot(player.velocity.x, player.velocity.z);
    this._bob += dt * (player.sprinting ? 13 : 9) * Math.min(1, planar / 4);
    const bobAmt = Math.min(1, planar / 5) * (player.sprinting ? 0.035 : 0.018);

    const kind = this.current ?? 'fists';
    const model = this.models[kind];
    const base = this._bases[kind];
    if (!model) return;

    const lower = player.sprinting ? 1 : 0;
    const reloadT = this.reloading > 0 && this.weapon
      ? Math.sin(Math.PI * (1 - this.reloading / this.weapon.reloadTime))
      : 0;
    // Punch: a quick thrust forward, then a slower pull back.
    const mt = this.meleeAnim / 0.62;
    const punch = mt > 0 ? Math.sin(Math.PI * Math.min(1, (1 - mt) * 2.4)) : 0;

    model.position.set(
      base.x + this._sway.x + Math.cos(this._bob) * bobAmt - punch * 0.16,
      base.y + this._sway.y + Math.abs(Math.sin(this._bob)) * bobAmt
        - lower * 0.09 - reloadT * 0.14 + punch * 0.08,
      base.z + this._recoilZ + this.swapping * 0.5 - punch * 0.42
    );
    model.rotation.set(
      this._recoilPitch * 0.9 - reloadT * 0.7 - punch * 0.35,
      lower * 0.5 + this._sway.x * 1.2 + punch * 0.30,
      -lower * 0.25 - reloadT * 0.35 - punch * 0.5
    );
  }
}

/**
 * Guns are built from boxes at load time. Deliberately chunky and low-poly so
 * they sit in the same visual language as the intro cinematic.
 */
function buildViewModel(kind) {
  const g = new THREE.Group();
  const steel = new THREE.MeshLambertMaterial({ color: 0x30353a });
  const dark = new THREE.MeshLambertMaterial({ color: 0x1b1e21 });
  const grip = new THREE.MeshLambertMaterial({ color: 0x2b2118 });
  const accent = new THREE.MeshLambertMaterial({ color: 0x5a6167 });

  const box = (w, h, d, mat, x, y, z, rx = 0) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    if (rx) m.rotation.x = rx;
    g.add(m);
    return m;
  };

  if (kind === 'fists') {
    // Bare knuckles: forearm, fist, and the wrap the inmate made from a sheet.
    // Sized and placed like the guns so it sits at the same depth on screen.
    const skin = new THREE.MeshLambertMaterial({ color: 0xbb8f6e });
    const wrap = new THREE.MeshLambertMaterial({ color: 0xcfc8b8 });
    box(0.080, 0.080, 0.20, skin, 0, -0.015, 0.06);      // forearm
    box(0.105, 0.095, 0.13, skin, 0, -0.010, -0.09);     // fist
    box(0.110, 0.100, 0.07, wrap, 0, -0.010, -0.10);     // knuckle wrap
    box(0.110, 0.032, 0.08, wrap, 0, -0.048, -0.05);     // thumb wrap
    g.scale.setScalar(0.72);
    return g;
  }

  if (kind === 'pistol') {
    box(0.075, 0.075, 0.30, steel, 0, 0.015, -0.10);      // slide
    box(0.060, 0.045, 0.20, dark, 0, -0.035, -0.06);      // frame
    box(0.055, 0.14, 0.075, grip, 0, -0.115, 0.025, 0.22); // grip
    box(0.020, 0.020, 0.05, accent, 0, 0.055, -0.24);     // front sight block
    box(0.030, 0.030, 0.04, dark, 0, -0.005, -0.27);      // muzzle
  } else if (kind === 'shotgun') {
    box(0.085, 0.085, 0.62, steel, 0, 0.01, -0.22);       // receiver + barrel
    box(0.070, 0.070, 0.34, dark, 0, -0.075, -0.30);      // tube magazine
    box(0.090, 0.075, 0.16, accent, 0, -0.075, -0.15);    // pump
    box(0.065, 0.13, 0.10, grip, 0, -0.10, 0.04, 0.18);   // grip
    box(0.075, 0.075, 0.22, grip, 0, -0.035, 0.16, -0.10); // stock
    box(0.045, 0.045, 0.05, dark, 0, 0.01, -0.55);        // muzzle
  } else {
    box(0.075, 0.085, 0.40, steel, 0, 0.01, -0.16);       // receiver
    box(0.045, 0.045, 0.40, dark, 0, 0.02, -0.46);        // barrel
    box(0.055, 0.16, 0.09, dark, 0, -0.11, -0.05, 0.10);  // magazine
    box(0.055, 0.12, 0.08, grip, 0, -0.10, 0.06, 0.20);   // grip
    box(0.080, 0.085, 0.20, accent, 0, -0.005, 0.18);     // stock
    box(0.055, 0.045, 0.14, accent, 0, -0.055, -0.34);    // handguard
    box(0.018, 0.045, 0.02, dark, 0, 0.07, -0.62);        // front post
    box(0.050, 0.030, 0.09, dark, 0, 0.075, -0.10);       // optic
  }

  // Perspective at the edge of a wide FOV enlarges anything this close, so the
  // models are built slightly under scale.
  g.scale.setScalar(0.88);
  return g;
}
