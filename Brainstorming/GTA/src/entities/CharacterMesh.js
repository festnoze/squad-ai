/**
 * Procedural humanoid: a jointed rig of boxes with hand-authored locomotion.
 *
 * There is no skinned-mesh asset pipeline here, so the rig is built from nested Groups
 * and animated by rotating joints directly. It reads as a stylised low-poly character,
 * which suits the art direction, and it costs nothing to spawn hundreds of them for the
 * pedestrian crowd.
 */

import { Group, Mesh, BoxGeometry, CapsuleGeometry, SphereGeometry, MeshStandardMaterial, Color, MathUtils } from 'three/webgpu';

const geo = {
  torso: new BoxGeometry(0.42, 0.56, 0.24),
  hips: new BoxGeometry(0.38, 0.2, 0.24),
  head: new SphereGeometry(0.135, 16, 12),
  neck: new CapsuleGeometry(0.055, 0.06, 4, 8),
  upperArm: new CapsuleGeometry(0.058, 0.2, 4, 8),
  lowerArm: new CapsuleGeometry(0.05, 0.2, 4, 8),
  hand: new SphereGeometry(0.06, 10, 8),
  thigh: new CapsuleGeometry(0.085, 0.26, 4, 8),
  shin: new CapsuleGeometry(0.07, 0.26, 4, 8),
  foot: new BoxGeometry(0.11, 0.07, 0.26),
};

for (const g of Object.values(geo)) g.computeBoundingSphere();

const SKIN_TONES = [0xf0c8a0, 0xd9a878, 0xa8703f, 0x74492a, 0x4a2f1c, 0xf7d7bd];
const SHIRT_COLOURS = [0x2f6f8f, 0x8f3f3f, 0x3f7f4f, 0xd9d2c5, 0x2b2f3a, 0x8a6f3f, 0x6b4f8f, 0xc9803f];
const TROUSER_COLOURS = [0x2a3242, 0x3a3a3a, 0x1f2530, 0x5a4a3a, 0x24405a];

/** Pick deterministic-ish outfit colours. */
function outfit(rand = Math.random) {
  return {
    skin: SKIN_TONES[Math.floor(rand() * SKIN_TONES.length)],
    shirt: SHIRT_COLOURS[Math.floor(rand() * SHIRT_COLOURS.length)],
    trousers: TROUSER_COLOURS[Math.floor(rand() * TROUSER_COLOURS.length)],
    shoes: 0x14161a,
  };
}

function part(geometry, material, x = 0, y = 0, z = 0) {
  const m = new Mesh(geometry, material);
  m.position.set(x, y, z);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

export class CharacterMesh {
  /**
   * @param {object} [opts]
   * @param {() => number} [opts.rand] RNG for outfit selection
   * @param {number} [opts.scale] height multiplier
   */
  constructor({ rand = Math.random, scale = 1 } = {}) {
    const colours = outfit(rand);
    const mat = {
      skin: new MeshStandardMaterial({ color: new Color(colours.skin), roughness: 0.72, metalness: 0.0 }),
      shirt: new MeshStandardMaterial({ color: new Color(colours.shirt), roughness: 0.82, metalness: 0.0 }),
      trousers: new MeshStandardMaterial({ color: new Color(colours.trousers), roughness: 0.86, metalness: 0.0 }),
      shoes: new MeshStandardMaterial({ color: new Color(colours.shoes), roughness: 0.5, metalness: 0.1 }),
    };
    this.materials = mat;

    // Root sits at the feet, so world position == ground contact point.
    this.root = new Group();
    this.root.scale.setScalar(scale);

    this.hips = new Group();
    this.hips.position.y = 0.92;
    this.root.add(this.hips);
    this.hips.add(part(geo.hips, mat.trousers));

    this.spine = new Group();
    this.spine.position.y = 0.1;
    this.hips.add(this.spine);
    this.spine.add(part(geo.torso, mat.shirt, 0, 0.28, 0));

    this.neck = new Group();
    this.neck.position.y = 0.58;
    this.spine.add(this.neck);
    this.neck.add(part(geo.neck, mat.skin));
    this.head = new Group();
    this.head.position.y = 0.12;
    this.neck.add(this.head);
    this.head.add(part(geo.head, mat.skin));
    // A slightly darker cap of hair so the head has a facing direction.
    const hair = part(geo.head, new MeshStandardMaterial({ color: 0x241a14, roughness: 0.9 }), 0, 0.028, -0.012);
    hair.scale.set(1.03, 0.82, 1.03);
    this.head.add(hair);

    this.arms = { left: this._arm(mat, -1), right: this._arm(mat, 1) };
    this.spine.add(this.arms.left.shoulder, this.arms.right.shoulder);

    this.legs = { left: this._leg(mat, -1), right: this._leg(mat, 1) };
    this.hips.add(this.legs.left.hip, this.legs.right.hip);

    this.phase = 0;
    this.lean = 0;
    this.detail = 0;
    // Cached for LOD toggling; a humanoid is ~15 separate meshes, and a crowd of them
    // dominates the draw-call budget if every one of them is drawn in full.
    this._meshes = [];
    this.root.traverse((o) => { if (o.isMesh) this._meshes.push(o); });
  }

  /**
   * Detail tier from camera distance.
   * 0 = full with shadows, 1 = full without shadows, 2 = hidden.
   *
   * Shadow casting is dropped first because each caster is a second draw call for
   * something that, at forty metres, contributes a few pixels of shadow.
   */
  setDetail(level) {
    if (level === this.detail) return;
    this.detail = level;
    this.root.visible = level < 2;
    const shadows = level === 0;
    for (const m of this._meshes) m.castShadow = shadows;
  }

  _arm(mat, side) {
    const shoulder = new Group();
    shoulder.position.set(0.26 * side, 0.5, 0);
    const upper = part(geo.upperArm, mat.shirt, 0, -0.13, 0);
    shoulder.add(upper);
    const elbow = new Group();
    elbow.position.y = -0.26;
    shoulder.add(elbow);
    elbow.add(part(geo.lowerArm, mat.skin, 0, -0.13, 0));
    const hand = new Group();
    hand.position.y = -0.27;
    elbow.add(hand);
    hand.add(part(geo.hand, mat.skin));
    return { shoulder, elbow, hand, side };
  }

  _leg(mat, side) {
    const hip = new Group();
    hip.position.set(0.11 * side, -0.08, 0);
    hip.add(part(geo.thigh, mat.trousers, 0, -0.2, 0));
    const knee = new Group();
    knee.position.y = -0.4;
    hip.add(knee);
    knee.add(part(geo.shin, mat.trousers, 0, -0.19, 0));
    const ankle = new Group();
    ankle.position.y = -0.38;
    knee.add(ankle);
    ankle.add(part(geo.foot, mat.shoes, 0, -0.035, 0.06));
    return { hip, knee, ankle, side };
  }

  /**
   * Drive the rig.
   * @param {number} dt seconds
   * @param {object} s state
   * @param {number} s.speed horizontal speed in m/s
   * @param {boolean} s.grounded
   * @param {number} [s.turnRate] rad/s, drives body lean
   * @param {'idle'|'walk'|'run'|'jump'|'fall'|'drive'|'swim'} s.mode
   */
  update(dt, s) {
    const { speed = 0, grounded = true, turnRate = 0, mode = 'idle' } = s;

    if (mode === 'drive') return this._poseDriving(dt);
    if (mode === 'swim') return this._poseSwimming(dt);
    if (!grounded) return this._poseAirborne(dt, mode === 'jump');

    // Stride frequency scales with speed; 1.85 Hz at a walk, ~3.2 Hz at a sprint.
    const stride = MathUtils.clamp(speed / 1.6, 0, 3.4);
    this.phase += dt * (1.9 + stride * 1.5) * Math.PI * (speed > 0.15 ? 1 : 0);
    const swing = MathUtils.clamp(speed / 5.2, 0, 1);

    const p = this.phase;
    const legAmp = 0.42 + swing * 0.55;
    const armAmp = 0.3 + swing * 0.62;

    this.legs.left.hip.rotation.x = Math.sin(p) * legAmp;
    this.legs.right.hip.rotation.x = Math.sin(p + Math.PI) * legAmp;
    // Knees only bend one way; a rectified sine keeps them from inverting.
    this.legs.left.knee.rotation.x = -Math.max(0, Math.sin(p - 0.6)) * (0.5 + swing * 0.75);
    this.legs.right.knee.rotation.x = -Math.max(0, Math.sin(p + Math.PI - 0.6)) * (0.5 + swing * 0.75);
    this.legs.left.ankle.rotation.x = Math.sin(p + 0.5) * 0.22;
    this.legs.right.ankle.rotation.x = Math.sin(p + Math.PI + 0.5) * 0.22;

    this.arms.left.shoulder.rotation.x = Math.sin(p + Math.PI) * armAmp;
    this.arms.right.shoulder.rotation.x = Math.sin(p) * armAmp;
    this.arms.left.shoulder.rotation.z = 0.09 + swing * 0.1;
    this.arms.right.shoulder.rotation.z = -(0.09 + swing * 0.1);
    this.arms.left.elbow.rotation.x = -(0.22 + swing * 0.7 + Math.max(0, Math.sin(p + Math.PI)) * 0.35);
    this.arms.right.elbow.rotation.x = -(0.22 + swing * 0.7 + Math.max(0, Math.sin(p)) * 0.35);

    // Bob, counter-rotate the shoulders against the hips, and lean into turns.
    this.hips.position.y = 0.92 - Math.abs(Math.sin(p)) * (0.015 + swing * 0.035);
    this.hips.rotation.y = Math.sin(p) * 0.06 * swing;
    this.spine.rotation.y = -Math.sin(p) * 0.13 * swing;
    this.spine.rotation.x = swing * 0.19;
    this.lean = MathUtils.lerp(this.lean, MathUtils.clamp(-turnRate * 0.22, -0.28, 0.28), dt * 6);
    this.spine.rotation.z = this.lean;
    this.head.rotation.x = -swing * 0.1;

    // Idle: settle into a breathing pose.
    if (speed < 0.15) {
      const breathe = Math.sin(performance.now() * 0.0016) * 0.02;
      for (const l of [this.legs.left, this.legs.right]) {
        l.hip.rotation.x = MathUtils.lerp(l.hip.rotation.x, 0, dt * 8);
        l.knee.rotation.x = MathUtils.lerp(l.knee.rotation.x, -0.04, dt * 8);
      }
      for (const a of [this.arms.left, this.arms.right]) {
        a.shoulder.rotation.x = MathUtils.lerp(a.shoulder.rotation.x, 0.03, dt * 8);
        a.elbow.rotation.x = MathUtils.lerp(a.elbow.rotation.x, -0.2, dt * 8);
      }
      this.spine.rotation.x = breathe;
      this.spine.rotation.y = 0;
      this.hips.position.y = 0.92 + breathe * 0.3;
    }
  }

  _poseAirborne(dt, rising) {
    const t = dt * 9;
    const tuck = rising ? 0.7 : 0.32;
    this.legs.left.hip.rotation.x = MathUtils.lerp(this.legs.left.hip.rotation.x, tuck, t);
    this.legs.right.hip.rotation.x = MathUtils.lerp(this.legs.right.hip.rotation.x, tuck * 0.45, t);
    this.legs.left.knee.rotation.x = MathUtils.lerp(this.legs.left.knee.rotation.x, -1.1, t);
    this.legs.right.knee.rotation.x = MathUtils.lerp(this.legs.right.knee.rotation.x, -0.5, t);
    for (const a of [this.arms.left, this.arms.right]) {
      a.shoulder.rotation.x = MathUtils.lerp(a.shoulder.rotation.x, rising ? -1.5 : -0.7, t);
      a.elbow.rotation.x = MathUtils.lerp(a.elbow.rotation.x, -0.5, t);
    }
    this.spine.rotation.x = MathUtils.lerp(this.spine.rotation.x, rising ? -0.12 : 0.18, t);
  }

  _poseDriving(dt) {
    const t = dt * 10;
    for (const l of [this.legs.left, this.legs.right]) {
      l.hip.rotation.x = MathUtils.lerp(l.hip.rotation.x, 1.35, t);
      l.knee.rotation.x = MathUtils.lerp(l.knee.rotation.x, -1.4, t);
      l.hip.rotation.z = MathUtils.lerp(l.hip.rotation.z, -0.12 * l.side, t);
    }
    for (const a of [this.arms.left, this.arms.right]) {
      a.shoulder.rotation.x = MathUtils.lerp(a.shoulder.rotation.x, -0.95, t);
      a.shoulder.rotation.z = MathUtils.lerp(a.shoulder.rotation.z, 0.3 * -a.side, t);
      a.elbow.rotation.x = MathUtils.lerp(a.elbow.rotation.x, -0.55, t);
    }
    this.spine.rotation.set(0.08, 0, 0);
    this.hips.position.y = 0.92;
  }

  _poseSwimming(dt) {
    this.phase += dt * 5;
    const p = this.phase;
    this.spine.rotation.x = 1.15;
    for (const [i, a] of [this.arms.left, this.arms.right].entries()) {
      a.shoulder.rotation.x = -1.2 + Math.sin(p + i * Math.PI) * 1.5;
      a.elbow.rotation.x = -0.4;
    }
    this.legs.left.hip.rotation.x = Math.sin(p * 1.4) * 0.35 - 1.0;
    this.legs.right.hip.rotation.x = Math.sin(p * 1.4 + Math.PI) * 0.35 - 1.0;
    this.legs.left.knee.rotation.x = -0.35;
    this.legs.right.knee.rotation.x = -0.35;
  }

  /** Point the head towards a yaw offset from the body, for aiming/looking around. */
  lookYaw(yaw, pitch = 0) {
    this.neck.rotation.y = MathUtils.clamp(yaw, -1.1, 1.1);
    this.head.rotation.x = MathUtils.clamp(pitch, -0.7, 0.7);
  }

  dispose() {
    for (const m of Object.values(this.materials)) m.dispose();
  }
}

/** Shared geometry is module-level; call only on full teardown. */
export function disposeCharacterGeometry() {
  for (const g of Object.values(geo)) g.dispose();
}
