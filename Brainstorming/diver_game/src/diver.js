/**
 * ABYSSE - the player.
 *
 * Owns the swim and walk physics, the camera rig, the vitals, the three
 * weapons, the collection net and the first person view model. It deliberately
 * knows nothing about the fauna: firing calls out through `hooks` and main.js
 * resolves the hit. That keeps this module free of any gameplay import.
 *
 * Axes: the diver is a free 6DOF swimmer, so forward follows the pitch of the
 * camera. Space and Ctrl add a world space vertical component on top, which is
 * how real divers trim with a buoyancy vest.
 */

import * as THREE from 'three';
import {
  DIVER,
  CAMERA,
  WEAPONS,
  WORLD,
  PALETTE,
  SKINS,
  clamp,
  clamp01,
  lerp,
  springK,
  oxygenDrain,
} from './config.js';

// Scratch objects, never allocated per frame.
const _v1 = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _v3 = new THREE.Vector3();
const _fwd = new THREE.Vector3();
const _right = new THREE.Vector3();
const _euler = new THREE.Euler(0, 0, 0, 'YXZ');
const _quat = new THREE.Quaternion();
const _color = new THREE.Color();

const SKIN_BY_ID = SKINS.reduce((acc, s) => {
  acc[s.id] = s;
  return acc;
}, {});

// ---------------------------------------------------------------------------
// View model construction
// ---------------------------------------------------------------------------

function makeMetal(color, rough, metal) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: rough === undefined ? 0.42 : rough,
    metalness: metal === undefined ? 0.85 : metal,
  });
}

/**
 * Speargun: a stock, a rail, a thick rubber band pair and a loaded spear.
 * The spear child is hidden while the shot is in flight.
 */
function buildHarpoon(mats) {
  const g = new THREE.Group();

  const stock = new THREE.Mesh(new THREE.BoxGeometry(0.075, 0.075, 0.62), mats.gunBody);
  stock.position.set(0, 0, -0.16);
  g.add(stock);

  const grip = new THREE.Mesh(new THREE.BoxGeometry(0.062, 0.19, 0.085), mats.grip);
  grip.position.set(0, -0.115, 0.1);
  grip.rotation.x = -0.22;
  g.add(grip);

  const rail = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.022, 0.66), mats.gunDark);
  rail.position.set(0, 0.05, -0.2);
  g.add(rail);

  const muzzle = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.09, 12), mats.gunDark);
  muzzle.rotation.x = Math.PI / 2;
  muzzle.position.set(0, 0.012, -0.5);
  g.add(muzzle);

  for (let i = 0; i < 2; i++) {
    const band = new THREE.Mesh(new THREE.TorusGeometry(0.055, 0.011, 6, 14), mats.rubber);
    band.position.set(i ? 0.05 : -0.05, 0.03, -0.47);
    band.rotation.y = Math.PI / 2;
    g.add(band);
  }

  const reel = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.045, 14), mats.gunDark);
  reel.rotation.z = Math.PI / 2;
  reel.position.set(0, -0.045, -0.02);
  g.add(reel);

  const spear = new THREE.Group();
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.011, 0.95, 8), mats.steel);
  shaft.rotation.x = Math.PI / 2;
  shaft.position.z = -0.34;
  spear.add(shaft);
  const tip = new THREE.Mesh(new THREE.ConeGeometry(0.024, 0.1, 8), mats.steel);
  tip.rotation.x = -Math.PI / 2;
  tip.position.z = -0.86;
  spear.add(tip);
  // Barbs, so the head reads as a spear and not a nail.
  for (let i = 0; i < 2; i++) {
    const barb = new THREE.Mesh(new THREE.ConeGeometry(0.014, 0.07, 5), mats.steel);
    barb.position.set(i ? 0.016 : -0.016, 0, -0.78);
    barb.rotation.set(-Math.PI / 2, 0, i ? -0.9 : 0.9);
    spear.add(barb);
  }
  spear.name = 'spear';
  g.add(spear);

  g.userData.spear = spear;
  g.userData.muzzle = new THREE.Vector3(0, 0.012, -0.55);
  return g;
}

/** Needle rifle: a compact pressurised carbine with a cylinder magazine. */
function buildNeedler(mats) {
  const g = new THREE.Group();

  const body = new THREE.Mesh(new THREE.BoxGeometry(0.085, 0.1, 0.44), mats.gunBody);
  body.position.set(0, 0, -0.1);
  g.add(body);

  const barrel = new THREE.Mesh(new THREE.CylinderGeometry(0.021, 0.021, 0.4, 12), mats.gunDark);
  barrel.rotation.x = Math.PI / 2;
  barrel.position.set(0, 0.018, -0.42);
  g.add(barrel);

  const tank = new THREE.Mesh(new THREE.CylinderGeometry(0.046, 0.046, 0.3, 14), mats.tank);
  tank.rotation.x = Math.PI / 2;
  tank.position.set(0, -0.062, -0.06);
  g.add(tank);

  const gauge = new THREE.Mesh(new THREE.CircleGeometry(0.025, 12), mats.glow);
  gauge.position.set(0.046, -0.062, -0.2);
  gauge.rotation.y = Math.PI / 2;
  g.add(gauge);

  const grip = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.2, 0.08), mats.grip);
  grip.position.set(0, -0.13, 0.09);
  grip.rotation.x = -0.2;
  g.add(grip);

  const mag = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.15, 0.06), mats.gunDark);
  mag.position.set(0, -0.11, -0.14);
  g.add(mag);
  g.userData.mag = mag;

  const sight = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.035, 0.02), mats.gunDark);
  sight.position.set(0, 0.07, -0.28);
  g.add(sight);

  g.userData.muzzle = new THREE.Vector3(0, 0.018, -0.6);
  return g;
}

/** Shock stick: an insulated handle with two electrodes and an arc effect. */
function buildShocker(mats) {
  const g = new THREE.Group();

  const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.038, 0.3, 12), mats.grip);
  handle.rotation.x = Math.PI / 2 - 0.12;
  handle.position.set(0, -0.03, 0.02);
  g.add(handle);

  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.026, 0.52, 12), mats.steel);
  shaft.rotation.x = Math.PI / 2 - 0.12;
  shaft.position.set(0, 0.02, -0.36);
  g.add(shaft);

  const collar = new THREE.Mesh(new THREE.CylinderGeometry(0.038, 0.038, 0.05, 12), mats.gunBody);
  collar.rotation.x = Math.PI / 2 - 0.12;
  collar.position.set(0, 0.048, -0.58);
  g.add(collar);

  const arcGroup = new THREE.Group();
  for (let i = 0; i < 2; i++) {
    const prong = new THREE.Mesh(new THREE.CylinderGeometry(0.007, 0.005, 0.12, 6), mats.steel);
    prong.position.set(i ? 0.022 : -0.022, 0.062, -0.66);
    prong.rotation.x = Math.PI / 2 - 0.12;
    arcGroup.add(prong);
  }
  const arc = new THREE.Mesh(new THREE.SphereGeometry(0.035, 10, 8), mats.arc);
  arc.position.set(0, 0.07, -0.72);
  arc.visible = false;
  arcGroup.add(arc);
  g.add(arcGroup);
  g.userData.arc = arc;

  const cell = new THREE.Mesh(new THREE.BoxGeometry(0.055, 0.055, 0.1), mats.glow);
  cell.position.set(0, -0.05, 0.12);
  g.add(cell);

  g.userData.muzzle = new THREE.Vector3(0, 0.07, -0.74);
  return g;
}

/**
 * The player's own limbs. Two forearms with gloves, plus a pair of legs and
 * fins that come into view when you look down. Their materials carry the
 * wetsuit skin, which is the only place the player ever sees it.
 */
function buildBody(mats) {
  const g = new THREE.Group();

  function arm(side) {
    const a = new THREE.Group();
    const upper = new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.2, 4, 10), mats.suit);
    upper.rotation.x = Math.PI / 2;
    upper.position.set(0, 0, 0.16);
    a.add(upper);
    const fore = new THREE.Mesh(new THREE.CapsuleGeometry(0.048, 0.19, 4, 10), mats.suit);
    fore.rotation.x = Math.PI / 2;
    fore.position.set(0, 0.01, -0.1);
    a.add(fore);
    const cuff = new THREE.Mesh(new THREE.CylinderGeometry(0.052, 0.052, 0.035, 10), mats.trim);
    cuff.rotation.x = Math.PI / 2;
    cuff.position.set(0, 0.012, -0.2);
    a.add(cuff);
    const glove = new THREE.Mesh(new THREE.BoxGeometry(0.075, 0.05, 0.12), mats.glove);
    glove.position.set(0, 0.012, -0.27);
    a.add(glove);
    const thumb = new THREE.Mesh(new THREE.BoxGeometry(0.028, 0.04, 0.06), mats.glove);
    thumb.position.set(side * 0.04, 0.014, -0.25);
    a.add(thumb);
    return a;
  }

  const rightArm = arm(1);
  rightArm.position.set(0.24, -0.2, -0.28);
  rightArm.rotation.set(0.16, -0.1, 0.06);
  g.add(rightArm);

  const leftArm = arm(-1);
  leftArm.position.set(-0.26, -0.24, -0.22);
  leftArm.rotation.set(0.25, 0.22, -0.1);
  g.add(leftArm);

  // Legs and fins, only visible when the camera pitches down.
  const legs = new THREE.Group();
  for (let i = 0; i < 2; i++) {
    const s = i ? 1 : -1;
    const leg = new THREE.Group();
    const thigh = new THREE.Mesh(new THREE.CapsuleGeometry(0.085, 0.34, 4, 10), mats.suit);
    thigh.rotation.x = Math.PI / 2;
    thigh.position.set(0, 0, 0.24);
    leg.add(thigh);
    const shin = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.36, 4, 10), mats.suit);
    shin.rotation.x = Math.PI / 2;
    shin.position.set(0, -0.02, 0.66);
    leg.add(shin);
    const stripe = new THREE.Mesh(new THREE.CylinderGeometry(0.073, 0.073, 0.05, 10), mats.accent);
    stripe.rotation.x = Math.PI / 2;
    stripe.position.set(0, -0.02, 0.52);
    leg.add(stripe);
    // Fin blade, a long flattened wedge.
    const fin = new THREE.Mesh(new THREE.BoxGeometry(0.19, 0.028, 0.46), mats.trim);
    fin.position.set(0, -0.03, 1.05);
    leg.add(fin);
    const finTip = new THREE.Mesh(new THREE.BoxGeometry(0.145, 0.02, 0.14), mats.trim);
    finTip.position.set(0, -0.03, 1.33);
    leg.add(finTip);

    leg.position.set(s * 0.14, -0.62, 0.1);
    leg.userData.side = s;
    legs.add(leg);
  }
  g.add(legs);
  g.userData.legs = legs;
  g.userData.rightArm = rightArm;
  g.userData.leftArm = leftArm;

  return g;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createDiver(scene, camera, world, textures) {
  // ------------------------------------------------------------ materials
  const mats = {
    suit: new THREE.MeshStandardMaterial({ color: 0x1c3f6e, roughness: 0.72, metalness: 0.05 }),
    trim: new THREE.MeshStandardMaterial({ color: 0xf0a132, roughness: 0.6, metalness: 0.08 }),
    accent: new THREE.MeshStandardMaterial({
      color: 0x9fe8ff,
      roughness: 0.4,
      metalness: 0.1,
      emissive: 0x000000,
    }),
    glove: new THREE.MeshStandardMaterial({ color: 0x14243a, roughness: 0.85, metalness: 0.02 }),
    gunBody: makeMetal(0x3b4249, 0.5, 0.7),
    gunDark: makeMetal(0x20262b, 0.44, 0.85),
    steel: makeMetal(0xb9c4cc, 0.28, 0.95),
    grip: new THREE.MeshStandardMaterial({ color: 0x181c20, roughness: 0.95, metalness: 0.02 }),
    rubber: new THREE.MeshStandardMaterial({ color: 0x2a1f1f, roughness: 0.98, metalness: 0 }),
    tank: makeMetal(0xd8b23a, 0.35, 0.8),
    glow: new THREE.MeshStandardMaterial({
      color: 0x0a2028,
      emissive: new THREE.Color(PALETTE.ui),
      emissiveIntensity: 1.6,
      roughness: 0.3,
    }),
    arc: new THREE.MeshBasicMaterial({
      color: 0xbdf0ff,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  };

  // ---------------------------------------------------------------- rig
  // The camera hangs off a rig so the view model can inherit the head sway
  // without inheriting the raw mouse jitter.
  const rig = new THREE.Group();
  rig.add(camera);
  scene.add(rig);

  const viewRoot = new THREE.Group();
  // Rendered on top of the world so the gun never clips into a rock.
  viewRoot.renderOrder = 20;
  camera.add(viewRoot);

  const body = buildBody(mats);
  viewRoot.add(body);

  const weaponRoot = new THREE.Group();
  weaponRoot.position.set(0.24, -0.21, -0.3);
  viewRoot.add(weaponRoot);

  const models = {
    harpoon: buildHarpoon(mats),
    needler: buildNeedler(mats),
    shocker: buildShocker(mats),
  };
  for (const key of Object.keys(models)) {
    models[key].visible = false;
    weaponRoot.add(models[key]);
  }
  // Push the view model into a shallow depth range so it renders in front.
  viewRoot.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = false;
      o.receiveShadow = false;
      o.frustumCulled = false;
    }
  });

  // ------------------------------------------------------------- dive lamp
  const lamp = new THREE.SpotLight(
    0xdcf4ff,
    DIVER.lampIntensity,
    DIVER.lampRange,
    DIVER.lampAngle,
    0.55,
    1.1
  );
  lamp.position.set(0.2, -0.12, 0);
  lamp.target.position.set(0.2, -0.12, -1);
  camera.add(lamp);
  camera.add(lamp.target);
  lamp.visible = false;

  // A weak fill so the diver's own hands never sit in pure black.
  const fill = new THREE.PointLight(0x9fd8ff, 0.55, 4.2, 1.6);
  fill.position.set(0, 0.1, 0.2);
  camera.add(fill);

  // ------------------------------------------------------------ projectiles
  const spearGeo = new THREE.CylinderGeometry(0.012, 0.012, 1.0, 8);
  spearGeo.rotateX(Math.PI / 2);
  const spearTipGeo = new THREE.ConeGeometry(0.026, 0.11, 8);
  spearTipGeo.rotateX(-Math.PI / 2);

  const lineMat = new THREE.LineBasicMaterial({ color: 0xd8e6ee, transparent: true, opacity: 0.55 });
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
  const spearLine = new THREE.Line(lineGeo, lineMat);
  spearLine.frustumCulled = false;
  spearLine.visible = false;
  scene.add(spearLine);

  const projectiles = [];

  function acquireProjectile() {
    for (let i = 0; i < projectiles.length; i++) {
      if (!projectiles[i].active) return projectiles[i];
    }
    const g = new THREE.Group();
    const shaft = new THREE.Mesh(spearGeo, mats.steel);
    shaft.position.z = -0.4;
    g.add(shaft);
    const tip = new THREE.Mesh(spearTipGeo, mats.steel);
    tip.position.z = -0.94;
    g.add(tip);
    g.visible = false;
    g.frustumCulled = false;
    scene.add(g);
    const p = {
      object: g,
      position: g.position,
      velocity: new THREE.Vector3(),
      life: 0,
      active: false,
      weapon: null,
      returning: false,
    };
    projectiles.push(p);
    return p;
  }

  // --------------------------------------------------------------- state

  const weapons = WEAPONS.map((def) => ({
    def,
    mag: def.magazine,
    reserve: def.reserve,
    reloading: false,
    reloadT: 0,
    cooldown: 0,
  }));

  const self = {
    // Transform
    position: new THREE.Vector3(WORLD.subAnchor.x + 6, WORLD.subAnchor.y + 1, WORLD.subAnchor.z + 6),
    velocity: new THREE.Vector3(),
    yaw: 0,
    pitch: 0,

    // Modes: 'swim' free underwater, 'walk' on the island, 'ride' inside the
    // submarine, 'frozen' during a cinematic.
    mode: 'swim',
    grounded: false,
    autoMode: true,

    // Vitals
    oxygen: DIVER.maxOxygen,
    health: DIVER.maxHealth,
    stamina: DIVER.maxStamina,
    alive: true,
    lastHurtAt: -999,
    bleeding: 0,
    noise: 0,
    sprinting: false,

    // Kit
    weapons,
    weaponIndex: 0,
    lampOn: false,
    net: [],

    // Read only conveniences kept in sync each frame
    depth: 0,
    aboveWater: false,
    speed: 0,
    headBob: 0,

    rig,
    camera,
    viewRoot,
    lamp,

    hooks: {
      /** (origin, dir, weapon) => void, resolve an instant shot. */
      onHitscan: null,
      /** (origin, dir, weapon) => void, resolve a melee sweep. */
      onMelee: null,
      /**
       * (from, to, weapon) => { point, stop } | null
       * Called every step of a spear's flight so main can resolve the hit.
       */
      onProjectileStep: null,
      /** (position, count, spread) => void */
      onBubbles: null,
      /** (name, opts) => void */
      onSound: null,
      /** (kind) => void, called when the diver takes damage. */
      onHurt: null,
    },
  };

  // ------------------------------------------------------------------ skin

  function setSkin(skinId) {
    const skin = SKIN_BY_ID[skinId] || SKIN_BY_ID.standard;
    mats.suit.color.setHex(skin.suit);
    mats.trim.color.setHex(skin.trim);
    mats.accent.color.setHex(skin.accent);
    // Glove is a darker take on the suit colour so the two always agree.
    _color.setHex(skin.suit).multiplyScalar(0.62);
    mats.glove.color.copy(_color);
    // The abyss suit is the only one that actually emits light.
    const glowing = skinId === 'abyss';
    mats.accent.emissive.setHex(glowing ? skin.accent : 0x000000);
    mats.accent.emissiveIntensity = glowing ? 1.8 : 0;
    self.skinId = skin.id;
  }
  setSkin('standard');

  // -------------------------------------------------------------- weapons

  function currentWeapon() {
    return weapons[self.weaponIndex];
  }

  function selectWeapon(index) {
    if (index === self.weaponIndex || index < 0 || index >= weapons.length) return;
    const prev = weapons[self.weaponIndex];
    prev.reloading = false;
    prev.reloadT = 0;
    self.weaponIndex = index;
    models[weapons[index].def.id].visible = true;
    for (let i = 0; i < weapons.length; i++) {
      if (i !== index) models[weapons[i].def.id].visible = false;
    }
    weaponSwapT = 0.32;
    sound('reload', { volume: 0.35 });
  }

  function startReload() {
    const w = currentWeapon();
    if (w.reloading || w.mag >= w.def.magazine || w.reserve <= 0) return;
    w.reloading = true;
    w.reloadT = 0;
    sound('reload');
  }

  function finishReload() {
    const w = currentWeapon();
    const need = w.def.magazine - w.mag;
    const take = Math.min(need, w.reserve);
    w.mag += take;
    w.reserve -= take;
    w.reloading = false;
    w.reloadT = 0;
  }

  function sound(name, opts) {
    if (self.hooks.onSound) self.hooks.onSound(name, opts);
  }

  function bubbles(pos, count, spread) {
    if (self.hooks.onBubbles) self.hooks.onBubbles(pos, count, spread);
  }

  /** Muzzle position of the active weapon in world space. */
  function getMuzzle(out) {
    const model = models[currentWeapon().def.id];
    out.copy(model.userData.muzzle);
    model.localToWorld(out);
    return out;
  }

  function getAim(out) {
    camera.getWorldDirection(out);
    return out;
  }

  let recoil = 0;
  let recoilKick = 0;
  let weaponSwapT = 0;
  let arcTimer = 0;

  function fire() {
    const w = currentWeapon();
    if (w.cooldown > 0 || w.reloading || self.mode === 'ride' || !self.alive) return;
    if (w.mag <= 0) {
      sound('dryfire');
      w.cooldown = 0.35;
      if (w.reserve > 0) startReload();
      return;
    }

    w.mag -= 1;
    w.cooldown = w.def.fireDelay;
    self.noise = Math.min(1, self.noise + w.def.noise);
    recoil = 1;
    recoilKick = 1;

    const origin = getMuzzle(_v1);
    const dir = getAim(_v2).clone();
    // Spread, applied as a small random cone.
    if (w.def.spread > 0) {
      dir.x += (Math.random() - 0.5) * w.def.spread * 2;
      dir.y += (Math.random() - 0.5) * w.def.spread * 2;
      dir.z += (Math.random() - 0.5) * w.def.spread * 2;
      dir.normalize();
    }

    if (w.def.kind === 'projectile') {
      const p = acquireProjectile();
      p.active = true;
      p.returning = false;
      p.life = 0;
      p.weapon = w.def;
      p.object.visible = true;
      p.position.copy(origin);
      p.velocity.copy(dir).multiplyScalar(w.def.speed);
      // Inherit a little of the diver's own motion so shots feel attached.
      p.velocity.addScaledVector(self.velocity, 0.4);
      p.object.quaternion.copy(camera.quaternion);
      models[w.def.id].userData.spear.visible = false;
      spearLine.visible = true;
      sound('harpoon');
      bubbles(origin, 10, 0.28);
    } else if (w.def.kind === 'hitscan') {
      if (self.hooks.onHitscan) self.hooks.onHitscan(origin, dir, w.def);
      sound('needle', { rate: 0.94 + Math.random() * 0.14 });
      bubbles(origin, 3, 0.16);
    } else {
      if (self.hooks.onMelee) self.hooks.onMelee(origin, dir, w.def);
      sound('shock');
      arcTimer = 0.22;
      bubbles(origin, 14, 0.4);
    }

    if (w.mag <= 0 && w.reserve > 0) startReload();
  }

  // ------------------------------------------------------------------- net

  function netFull() {
    return self.net.length >= DIVER.netCapacity;
  }

  function addSpecimen(entry) {
    if (netFull()) return false;
    self.net.push(entry);
    return true;
  }

  function clearNet() {
    const taken = self.net.slice();
    self.net.length = 0;
    return taken;
  }

  // ---------------------------------------------------------------- damage

  function applyDamage(amount, fromPos, kind) {
    if (!self.alive || amount <= 0) return;
    self.health = Math.max(0, self.health - amount);
    self.lastHurtAt = 0;
    self.bleeding = Math.min(1, self.bleeding + amount / 60);
    if (self.hooks.onHurt) {
      let angle = null;
      if (fromPos) {
        _v1.copy(fromPos).sub(self.position);
        // Angle relative to where the diver is looking, 0 is straight ahead.
        const rel = Math.atan2(_v1.x, _v1.z) - (self.yaw + Math.PI);
        angle = Math.atan2(Math.sin(rel), Math.cos(rel));
      }
      self.hooks.onHurt(kind || 'hit', amount, angle);
    }
    if (self.health <= 0) {
      self.alive = false;
    }
  }

  function heal(amount) {
    self.health = Math.min(DIVER.maxHealth, self.health + amount);
  }

  function refillOxygen(amount) {
    self.oxygen = Math.min(DIVER.maxOxygen, self.oxygen + amount);
  }

  function refillAmmo() {
    for (let i = 0; i < weapons.length; i++) {
      const w = weapons[i];
      w.reserve = w.def.reserve;
      w.mag = w.def.magazine;
      w.reloading = false;
      w.reloadT = 0;
    }
  }

  function revive(position) {
    self.alive = true;
    self.health = DIVER.maxHealth;
    self.oxygen = DIVER.maxOxygen;
    self.stamina = DIVER.maxStamina;
    self.bleeding = 0;
    self.velocity.set(0, 0, 0);
    refillAmmo();
    if (position) self.position.copy(position);
  }

  function teleport(position, yaw) {
    self.position.copy(position);
    self.velocity.set(0, 0, 0);
    if (yaw !== undefined) self.yaw = yaw;
  }

  // --------------------------------------------------------------- physics

  function resolveMode() {
    if (!self.autoMode) return;
    if (self.mode === 'ride' || self.mode === 'frozen') return;
    const ground = world.heightAt(self.position.x, self.position.z);
    const feet = self.position.y - DIVER.eyeHeight;
    // Walk only where the terrain actually breaks the surface and the diver is
    // close enough to it to be standing.
    if (ground > 0.15 && feet <= ground + 0.6 && self.position.y > -0.4) {
      self.mode = 'walk';
    } else if (self.mode === 'walk' && (ground <= 0.05 || feet > ground + 1.6)) {
      self.mode = 'swim';
    } else if (self.mode !== 'walk') {
      self.mode = 'swim';
    }
  }

  function updateSwim(dt, input) {
    const move = input.moveAxes(_v3);
    const vertical = input.verticalAxis();
    const wantsSprint = input.sprinting() && (move.x !== 0 || move.z !== 0) && self.stamina > 1;
    self.sprinting = wantsSprint;

    // Camera space basis. Forward follows pitch so you dive where you look.
    _euler.set(self.pitch, self.yaw, 0, 'YXZ');
    _quat.setFromEuler(_euler);
    _fwd.set(0, 0, -1).applyQuaternion(_quat);
    _right.set(1, 0, 0).applyQuaternion(_quat);

    const boost = wantsSprint ? DIVER.sprintMultiplier : 1;
    const accel = DIVER.swimAccel * boost;

    _v1.set(0, 0, 0);
    _v1.addScaledVector(_fwd, move.z * accel);
    _v1.addScaledVector(_right, move.x * accel);
    _v1.y += vertical * DIVER.verticalAccel;

    // Buoyancy: a gentle upward pull that gets stronger near the surface, so
    // stopping always drifts you up rather than leaving you hanging.
    const surfacePull = clamp01((self.position.y + 30) / 30);
    _v1.y += DIVER.buoyancy * (0.5 + surfacePull * 0.9);

    self.velocity.addScaledVector(_v1, dt);

    // Drag, applied as an exponential decay so it is frame rate independent.
    const drag = Math.exp(-DIVER.waterDrag * dt);
    self.velocity.multiplyScalar(drag);

    // Speed caps, horizontal and vertical handled separately.
    const maxH = DIVER.swimMaxSpeed * boost;
    const hx = self.velocity.x;
    const hz = self.velocity.z;
    const h = Math.hypot(hx, hz);
    if (h > maxH) {
      const k = maxH / h;
      self.velocity.x *= k;
      self.velocity.z *= k;
    }
    const maxV = DIVER.verticalMaxSpeed * boost;
    if (Math.abs(self.velocity.y) > maxV) {
      self.velocity.y = Math.sign(self.velocity.y) * maxV;
    }

    // Stamina drives the sprint.
    if (wantsSprint) self.stamina = Math.max(0, self.stamina - DIVER.staminaDrain * dt);
    else self.stamina = Math.min(DIVER.maxStamina, self.stamina + DIVER.staminaRegen * dt);

    self.position.addScaledVector(self.velocity, dt);

    // The surface is a soft ceiling: you can break through it to breathe, but
    // you cannot swim into the sky.
    if (self.position.y > -0.15) {
      const overshoot = self.position.y + 0.15;
      self.position.y = -0.15 + overshoot * 0.35;
      if (self.velocity.y > 0) self.velocity.y *= 0.35;
      if (self.position.y > 0.55) self.position.y = 0.55;
    }
  }

  function updateWalk(dt, input) {
    const move = input.moveAxes(_v3);
    const wantsSprint = input.sprinting() && (move.x !== 0 || move.z !== 0) && self.stamina > 1;
    self.sprinting = wantsSprint;

    // On land only the yaw matters for movement.
    _fwd.set(-Math.sin(self.yaw), 0, -Math.cos(self.yaw));
    _right.set(Math.cos(self.yaw), 0, -Math.sin(self.yaw));

    const speed = DIVER.walkSpeed * (wantsSprint ? 1.55 : 1);
    _v1.set(0, 0, 0);
    _v1.addScaledVector(_fwd, move.z * DIVER.walkAccel);
    _v1.addScaledVector(_right, move.x * DIVER.walkAccel);

    self.velocity.x += _v1.x * dt;
    self.velocity.z += _v1.z * dt;

    const drag = Math.exp(-DIVER.walkDrag * dt);
    self.velocity.x *= drag;
    self.velocity.z *= drag;

    const h = Math.hypot(self.velocity.x, self.velocity.z);
    if (h > speed) {
      const k = speed / h;
      self.velocity.x *= k;
      self.velocity.z *= k;
    }

    self.velocity.y -= DIVER.gravity * dt;

    if (wantsSprint) self.stamina = Math.max(0, self.stamina - DIVER.staminaDrain * 0.6 * dt);
    else self.stamina = Math.min(DIVER.maxStamina, self.stamina + DIVER.staminaRegen * dt);

    self.position.addScaledVector(self.velocity, dt);

    const ground = world.heightAt(self.position.x, self.position.z);
    const feetTarget = ground + DIVER.eyeHeight;
    if (self.position.y <= feetTarget) {
      self.position.y = feetTarget;
      if (self.velocity.y < 0) self.velocity.y = 0;
      if (!self.grounded && self.velocity.y < -3) sound('footstep', { volume: 0.6 });
      self.grounded = true;
      if (input.down('Space')) {
        self.velocity.y = DIVER.jumpSpeed;
        self.grounded = false;
      }
    } else {
      self.grounded = false;
    }

    // Walking into the sea puts you back in the water.
    if (ground < 0.05 && self.position.y < 0.4) self.mode = 'swim';
  }

  // --------------------------------------------------------------- update

  let breathTimer = 0;
  let stepTimer = 0;
  let bobPhase = 0;
  let fovCurrent = CAMERA.fov;
  const sway = { x: 0, y: 0 };

  function updateProjectiles(dt) {
    let anyActive = false;
    for (let i = 0; i < projectiles.length; i++) {
      const p = projectiles[i];
      if (!p.active) continue;
      anyActive = true;
      p.life += dt;

      if (p.returning) {
        // Reel the spear back to the gun, then reload it visually.
        getMuzzle(_v1);
        _v2.copy(_v1).sub(p.position);
        const d = _v2.length();
        if (d < 0.6) {
          p.active = false;
          p.object.visible = false;
          models.harpoon.userData.spear.visible = true;
          continue;
        }
        _v2.multiplyScalar(1 / Math.max(d, 0.001));
        p.position.addScaledVector(_v2, Math.max(14, d * 4.5) * dt);
        p.object.lookAt(_v1);
        continue;
      }

      _v1.copy(p.position);
      p.velocity.y -= p.weapon.gravity * dt;
      // Water drag on the spear, so range is finite and the arc reads well.
      p.velocity.multiplyScalar(Math.exp(-0.55 * dt));
      p.position.addScaledVector(p.velocity, dt);

      // Orient along the flight path.
      _v2.copy(p.position).sub(_v1);
      if (_v2.lengthSq() > 1e-6) {
        _v3.copy(p.position).add(_v2);
        p.object.lookAt(_v3);
      }

      let stop = false;
      if (self.hooks.onProjectileStep) {
        const hit = self.hooks.onProjectileStep(_v1, p.position, p.weapon);
        if (hit) {
          if (hit.point) p.position.copy(hit.point);
          stop = !!hit.stop;
        }
      }

      // Seabed and range limits.
      const ground = world.heightAt(p.position.x, p.position.z);
      if (p.position.y <= ground + 0.05) {
        p.position.y = ground + 0.05;
        stop = true;
      }
      if (p.life > 2.4) stop = true;

      if (stop) {
        p.returning = true;
        p.life = 0;
      }
    }

    // The line runs from the muzzle to whichever spear is out.
    if (anyActive) {
      const p = projectiles.find((q) => q.active);
      if (p) {
        getMuzzle(_v1);
        const arr = lineGeo.attributes.position.array;
        arr[0] = _v1.x;
        arr[1] = _v1.y;
        arr[2] = _v1.z;
        arr[3] = p.position.x;
        arr[4] = p.position.y;
        arr[5] = p.position.z;
        lineGeo.attributes.position.needsUpdate = true;
        spearLine.visible = true;
      }
    } else if (spearLine.visible) {
      spearLine.visible = false;
    }
  }

  function updateViewModel(dt, input) {
    // Sway lags the mouse, which sells the weight of the gear.
    const targetX = clamp(-input.state.lookX * 0.0016, -0.06, 0.06);
    const targetY = clamp(-input.state.lookY * 0.0016, -0.05, 0.05);
    const k = springK(9, dt);
    sway.x += (targetX - sway.x) * k;
    sway.y += (targetY - sway.y) * k;

    recoil = Math.max(0, recoil - dt * 4.2);
    recoilKick = Math.max(0, recoilKick - dt * 8);
    weaponSwapT = Math.max(0, weaponSwapT - dt);

    const w = currentWeapon();
    const reloadPhase = w.reloading ? w.reloadT / w.def.reloadTime : 0;

    const bobX = Math.cos(bobPhase) * CAMERA.bobAmplitude * 0.5;
    const bobY = Math.sin(bobPhase * 2) * CAMERA.bobAmplitude * 0.35;

    weaponRoot.position.set(
      0.24 + sway.x + bobX,
      -0.21 + sway.y + bobY - Math.sin(reloadPhase * Math.PI) * 0.16 - weaponSwapT * 0.4,
      -0.3 + recoilKick * 0.09
    );
    weaponRoot.rotation.set(
      sway.y * 1.6 + recoil * 0.14 + Math.sin(reloadPhase * Math.PI) * 0.5,
      -sway.x * 2.2 + weaponSwapT * 0.9,
      -sway.x * 1.4 + Math.sin(reloadPhase * Math.PI * 2) * 0.22
    );

    // Arms follow the weapon, legs kick when swimming.
    body.userData.rightArm.position.set(0.24 + sway.x * 0.7, -0.2 + sway.y * 0.7, -0.28);
    body.userData.leftArm.position.set(-0.26 + sway.x * 0.9, -0.24 + sway.y * 0.9, -0.22);

    const legs = body.userData.legs;
    const kick = self.mode === 'swim' ? Math.min(1, self.speed / 4) : 0;
    for (let i = 0; i < legs.children.length; i++) {
      const leg = legs.children[i];
      const phase = bobPhase * 0.9 + (i ? Math.PI : 0);
      leg.rotation.x = Math.sin(phase) * 0.42 * kick;
      leg.rotation.z = Math.sin(phase * 0.5) * 0.06 * kick;
    }
    // On land the legs would poke through the camera, so tuck them away.
    legs.visible = self.mode === 'swim';

    // Shock arc flicker.
    arcTimer = Math.max(0, arcTimer - dt);
    const arc = models.shocker.userData.arc;
    if (arc) {
      arc.visible = arcTimer > 0;
      if (arc.visible) {
        const s = 0.7 + Math.random() * 0.9;
        arc.scale.setScalar(s);
        arc.material.opacity = 0.4 + Math.random() * 0.6;
      }
    }
  }

  function update(dt, input, ctx) {
    const modal = ctx && ctx.modal;

    // -------------------------------------------------------------- look
    if (!modal && input.state.locked && self.mode !== 'frozen') {
      self.yaw -= input.state.lookX * DIVER.lookSensitivity;
      self.pitch -= input.state.lookY * DIVER.lookSensitivity;
      self.pitch = clamp(self.pitch, -DIVER.pitchLimit, DIVER.pitchLimit);
      // Keep yaw in a sane range so the compass maths never drifts.
      if (self.yaw > Math.PI) self.yaw -= Math.PI * 2;
      else if (self.yaw < -Math.PI) self.yaw += Math.PI * 2;
    }

    // ------------------------------------------------------------ actions
    if (!modal && self.alive && self.mode !== 'ride' && self.mode !== 'frozen') {
      if (input.pressed('Digit1')) selectWeapon(0);
      if (input.pressed('Digit2')) selectWeapon(1);
      if (input.pressed('Digit3')) selectWeapon(2);
      if (input.state.wheel !== 0) {
        const n = weapons.length;
        selectWeapon((self.weaponIndex + input.state.wheel + n) % n);
      }
      if (input.pressed('KeyR')) startReload();
      if (input.pressed('KeyF')) {
        self.lampOn = !self.lampOn;
        sound('ui');
      }

      const w = currentWeapon();
      const auto = w.def.kind === 'hitscan';
      if ((auto && input.state.fire) || (!auto && input.state.firePressed)) fire();
    }

    // ------------------------------------------------------------ weapons
    for (let i = 0; i < weapons.length; i++) {
      const w = weapons[i];
      if (w.cooldown > 0) w.cooldown = Math.max(0, w.cooldown - dt);
      if (w.reloading) {
        w.reloadT += dt;
        if (w.reloadT >= w.def.reloadTime) finishReload();
      }
    }

    // ------------------------------------------------------------ physics
    resolveMode();
    if (self.alive && !modal) {
      if (self.mode === 'swim') updateSwim(dt, input);
      else if (self.mode === 'walk') updateWalk(dt, input);
    } else if (self.mode === 'swim') {
      // Dead or paused divers still sink gently and keep their momentum.
      self.velocity.multiplyScalar(Math.exp(-1.6 * dt));
      if (!self.alive) self.velocity.y += (DIVER.buoyancy * 0.4 - 0.9) * dt;
      self.position.addScaledVector(self.velocity, dt);
    }

    // ---------------------------------------------------------- collision
    if (self.mode !== 'ride' && self.mode !== 'frozen') {
      const push = world.collide(self.position, DIVER.radius);
      if (push) {
        self.position.add(push);
        // Kill the velocity component going into the surface.
        const n = _v1.copy(push).normalize();
        const into = self.velocity.dot(n);
        if (into < 0) self.velocity.addScaledVector(n, -into);
      }
      // Seabed floor, always enforced even where there is no prop.
      const ground = world.heightAt(self.position.x, self.position.z);
      const minY = ground + (self.mode === 'walk' ? DIVER.eyeHeight : DIVER.radius + 0.35);
      if (self.position.y < minY) {
        self.position.y = minY;
        if (self.velocity.y < 0) self.velocity.y = 0;
      }
      // Soft world boundary, a circular wall centred on the origin.
      const distFromCentre = Math.hypot(self.position.x, self.position.z);
      if (distFromCentre > WORLD.boundsRadius) {
        const over = distFromCentre - WORLD.boundsRadius;
        const k = over / distFromCentre;
        self.position.x -= self.position.x * k;
        self.position.z -= self.position.z * k;
        self.velocity.x *= 0.4;
        self.velocity.z *= 0.4;
      }
    }

    // ------------------------------------------------------------- vitals
    self.depth = Math.max(0, -self.position.y);
    self.aboveWater = self.position.y > 0.05;
    self.speed = self.velocity.length();

    const breathing = self.mode !== 'ride';
    if (self.alive && breathing) {
      if (self.aboveWater || self.mode === 'walk') {
        // Free air, the tank refills.
        self.oxygen = Math.min(DIVER.maxOxygen, self.oxygen + 22 * dt);
      } else {
        self.oxygen -= oxygenDrain(self.depth, self.sprinting) * dt;
        if (self.oxygen <= 0) {
          self.oxygen = 0;
          applyDamage(DIVER.drownDamage * dt, null, 'drown');
        }
      }
    }

    self.lastHurtAt += dt;
    if (self.alive && self.lastHurtAt > DIVER.healthRegenDelay) {
      self.health = Math.min(DIVER.maxHealth, self.health + DIVER.healthRegen * dt);
    }
    self.bleeding = Math.max(0, self.bleeding - dt * 0.16);
    self.noise = Math.max(0, self.noise - dt * 0.55);
    if (self.sprinting) self.noise = Math.min(1, self.noise + dt * 0.5);

    // ------------------------------------------------------------ breathing
    if (self.alive && self.mode === 'swim' && !self.aboveWater) {
      const rate = self.sprinting ? 1.9 : 3.6;
      breathTimer += dt;
      if (breathTimer > rate) {
        breathTimer = 0;
        _v1.copy(self.position);
        _v1.y += 0.25;
        camera.getWorldDirection(_v2);
        _v1.addScaledVector(_v2, 0.35);
        bubbles(_v1, 9, 0.22);
      }
    }
    if (self.mode === 'walk' && self.grounded) {
      stepTimer += self.speed * dt;
      if (stepTimer > 1.8) {
        stepTimer = 0;
        sound('footstep', { volume: 0.5 + Math.random() * 0.2 });
      }
    }

    // --------------------------------------------------------------- camera
    const moving = self.speed > 0.4;
    bobPhase += dt * CAMERA.bobFrequency * (moving ? clamp(self.speed / 4, 0.5, 1.8) : 0.35);
    self.headBob = Math.sin(bobPhase) * CAMERA.bobAmplitude * (moving ? 1 : 0.35);

    rig.position.copy(self.position);
    camera.position.set(0, self.headBob, 0);
    _euler.set(self.pitch, self.yaw, 0, 'YXZ');
    camera.quaternion.setFromEuler(_euler);
    // A slight roll into the turn while swimming.
    if (self.mode === 'swim') {
      camera.rotateZ(clamp(-input.state.lookX * 0.0009, -0.05, 0.05));
    }

    const targetFov = CAMERA.fov + (self.sprinting ? CAMERA.sprintFov : 0);
    fovCurrent += (targetFov - fovCurrent) * springK(4.5, dt);
    if (Math.abs(camera.fov - fovCurrent) > 0.01) {
      camera.fov = fovCurrent;
      camera.updateProjectionMatrix();
    }

    lamp.visible = self.lampOn;
    fill.intensity = self.lampOn ? 0.85 : 0.45;

    updateProjectiles(dt);
    updateViewModel(dt, input);
  }

  function dispose() {
    scene.remove(rig);
    scene.remove(spearLine);
    for (let i = 0; i < projectiles.length; i++) scene.remove(projectiles[i].object);
    lineGeo.dispose();
    lineMat.dispose();
    spearGeo.dispose();
    spearTipGeo.dispose();
    for (const key of Object.keys(mats)) mats[key].dispose();
  }

  // Start with the harpoon visible.
  models.harpoon.visible = true;

  Object.assign(self, {
    update,
    dispose,
    setSkin,
    selectWeapon,
    startReload,
    currentWeapon,
    getMuzzle,
    getAim,
    applyDamage,
    heal,
    refillOxygen,
    refillAmmo,
    revive,
    teleport,
    addSpecimen,
    clearNet,
    netFull,
  });

  return self;
}
