// Rig de camera. Trois modes : poursuite, cockpit, orbite.
//
// La camera travaille en ESPACE VUE : main.js garantit
// `viewOrigin === ship.state.position`, donc le vaisseau est a l'origine.
// On ne fait donc que positionner et orienter la camera AUTOUR de l'origine,
// avec une amplitude bornee (~90 unites) pour rester loin des problemes de
// precision.
//
// Aucune allocation par frame : tous les temporaires vivent dans la closure.

import * as THREE from 'three';
import { SHIP } from '../core/settings.js';
import { clamp, damp, saturate } from '../core/math.js';
import { turbulence } from '../world/physics.js';

const MODES = ['chase', 'cockpit', 'orbit'];
const MAX_RADIUS = 90;
// Part du roulis du vaisseau conservee en mode poursuite : plus lisible.
const CHASE_ROLL = 0.35;

const DEFAULT_UP = new THREE.Vector3(0, 1, 0);

export function createCameraRig({ camera }) {
  const baseFov = camera ? camera.fov : 72;

  let mode = 'chase';
  let shakeLevel = 0;
  let time = 0;
  let orbitAngle = 0;
  let orbitHeight = 6;
  let snap = true;
  let currentFov = baseFov;

  const camPos = new THREE.Vector3(0, 3, 14);
  const qSmooth = new THREE.Quaternion();

  const _fwd = new THREE.Vector3();
  const _up = new THREE.Vector3(0, 1, 0);
  const _shipUp = new THREE.Vector3();
  const _right = new THREE.Vector3();
  const _desUp = new THREE.Vector3();
  const _cross = new THREE.Vector3();
  const _tanA = new THREE.Vector3();
  const _tanB = new THREE.Vector3();
  const _ref = new THREE.Vector3();
  const _desired = new THREE.Vector3();
  const _target = new THREE.Vector3();
  const _shake = new THREE.Vector3();
  const _qTarget = new THREE.Quaternion();
  const _qLook = new THREE.Quaternion();
  const _qc = new THREE.Quaternion();
  const _dq = new THREE.Quaternion();
  const _euler = new THREE.Euler(0, 0, 0, 'XYZ');
  const _m4 = new THREE.Matrix4();

  /** Amortissement exponentiel composante par composante. */
  function dampTo(vec, target, lambda, dt) {
    vec.x = damp(vec.x, target.x, lambda, dt);
    vec.y = damp(vec.y, target.y, lambda, dt);
    vec.z = damp(vec.z, target.z, lambda, dt);
  }

  /**
   * Retire une fraction `amount` du roulis de `q` par rapport a `upRef`.
   * amount = 1 -> parfaitement a plat, amount = 0 -> inchange.
   */
  function reduceRoll(q, upRef, amount) {
    _fwd.set(0, 0, -1).applyQuaternion(q);
    if (Math.abs(_fwd.dot(upRef)) > 0.985) return q;
    _right.crossVectors(_fwd, upRef);
    if (_right.lengthSq() < 1e-8) return q;
    _right.normalize();
    _desUp.crossVectors(_right, _fwd).normalize();
    _shipUp.set(0, 1, 0).applyQuaternion(q);
    const d = clamp(_shipUp.dot(_desUp), -1, 1);
    _cross.crossVectors(_shipUp, _desUp);
    const angle = Math.atan2(_cross.dot(_fwd), d);
    if (Math.abs(angle) < 1e-4) return q;
    _qc.setFromAxisAngle(_fwd, angle * amount);
    return q.premultiply(_qc).normalize();
  }

  function setFov(target, dt) {
    currentFov = snap ? target : damp(currentFov, target, 5, dt);
    if (Math.abs(currentFov - camera.fov) > 0.02) {
      camera.fov = currentFov;
      camera.updateProjectionMatrix();
    }
  }

  function update(dt, ctx) {
    if (!camera || !ctx || !ctx.ship) return;
    if (!(dt > 0)) dt = ctx.dt > 0 ? ctx.dt : 1 / 60;
    if (dt > 1 / 15) dt = 1 / 15;
    time += dt;

    const ship = ctx.ship;
    const st = ship.state;
    const tel = ship.telemetry || null;
    const env = ctx.env || null;
    const input = ctx.input || null;

    const speed = tel ? tel.speed : st.velocity.length();
    const pulse = tel && tel.pulse !== undefined ? tel.pulse : 0;
    const boost = st.boost || 0;
    const density = env && env.density ? saturate(env.density) : 0;

    if (env && env.up && env.up.isVector3 && env.up.lengthSq() > 1e-8) _up.copy(env.up).normalize();
    else _up.copy(DEFAULT_UP);

    // Secousses declenchees par le vaisseau (impact, rentree, turbulences).
    if (tel && tel.impact > 0) shakeLevel = Math.max(shakeLevel, tel.impact);
    if (env && env.insideGas) shakeLevel = Math.max(shakeLevel, saturate(env.insideGas) * 0.45);

    const speedNorm = saturate(speed / (SHIP.atmoMaxSpeed * 1.4));

    if (mode === 'cockpit') {
      // Dans la verriere, juste devant le pare-brise.
      _desired.set(0, 0.46, -1.15).applyQuaternion(st.quaternion);
      dampTo(camPos, _desired, snap ? 1e6 : 26, dt);
      camera.position.copy(camPos);
      camera.quaternion.slerp(st.quaternion, snap ? 1 : 1 - Math.exp(-24 * dt));
      setFov(baseFov + 4 * boost + 6 * pulse, dt);
    } else if (mode === 'orbit') {
      // Rotation lente autour du vaisseau, pilotable a la souris.
      let spin = 0.28;
      if (input && input.mouse) {
        spin += input.mouse.dx * 0.02;
        orbitHeight = clamp(orbitHeight - input.mouse.dy * 0.06, -14, 20);
      }
      orbitAngle += spin * dt;
      // Base tangente stable autour de la verticale locale.
      _ref.set(0, 0, 1);
      if (Math.abs(_up.z) > 0.9) _ref.set(1, 0, 0);
      _tanA.crossVectors(_ref, _up).normalize();
      _tanB.crossVectors(_up, _tanA).normalize();
      const r = 18 + speedNorm * 10;
      _desired
        .set(0, 0, 0)
        .addScaledVector(_tanA, Math.cos(orbitAngle) * r)
        .addScaledVector(_tanB, Math.sin(orbitAngle) * r)
        .addScaledVector(_up, orbitHeight);
      dampTo(camPos, _desired, snap ? 1e6 : 4, dt);
      camera.position.copy(camPos);
      _target.set(0, 0, 0);
      _m4.lookAt(camPos, _target, _up);
      _qLook.setFromRotationMatrix(_m4);
      camera.quaternion.slerp(_qLook, snap ? 1 : 1 - Math.exp(-8 * dt));
      setFov(baseFov, dt);
    } else {
      // --- Poursuite (mode par defaut) -----------------------------------
      _qTarget.copy(st.quaternion);
      // Roulis partiel : on n'en garde qu'une fraction, l'horizon reste lisible.
      reduceRoll(_qTarget, _up, 1 - CHASE_ROLL);
      const lambdaRot = 5.5 + speedNorm * 4 + density * 1.5;
      if (snap) qSmooth.copy(_qTarget);
      else qSmooth.slerp(_qTarget, 1 - Math.exp(-lambdaRot * dt));

      // Recul qui s'ouvre avec la vitesse, le boost et le pulse.
      const back = 11 + speedNorm * 9 + boost * 4 + pulse * 9;
      const lift = 2.7 + speedNorm * 1.3;
      _desired.set(0, lift, back).applyQuaternion(qSmooth);
      dampTo(camPos, _desired, snap ? 1e6 : 6.5 + speedNorm * 5, dt);
      camera.position.copy(camPos);

      // On vise un point devant le nez : la trajectoire reste lisible.
      _fwd.set(0, 0, -1).applyQuaternion(st.quaternion);
      _target.copy(_fwd).multiplyScalar(16 + speedNorm * 45);
      // Le "haut" de la camera vient du quaternion lisse : le roulis partiel
      // est deja encode dedans.
      _shipUp.set(0, 1, 0).applyQuaternion(qSmooth);
      _m4.lookAt(camPos, _target, _shipUp);
      _qLook.setFromRotationMatrix(_m4);
      camera.quaternion.slerp(_qLook, snap ? 1 : 1 - Math.exp(-11 * dt));

      setFov(baseFov + 7 * boost + 9 * pulse, dt);
    }

    // --- Secousse (tous modes) --------------------------------------------
    shakeLevel *= Math.exp(-3.2 * dt);
    if (shakeLevel > 0.002) {
      turbulence(time * 7.7, shakeLevel * 1.1, _shake);
      camera.position.add(_shake);
      turbulence(time * 5.3 + 41.7, shakeLevel * 0.055, _shake);
      _euler.set(_shake.x, _shake.y, _shake.z);
      _dq.setFromEuler(_euler);
      camera.quaternion.multiply(_dq).normalize();
    } else {
      shakeLevel = 0;
    }

    // Garde-fou d'amplitude : la camera ne s'eloigne jamais du vaisseau.
    if (camera.position.lengthSq() > MAX_RADIUS * MAX_RADIUS) {
      camera.position.setLength(MAX_RADIUS);
    }

    snap = false;
  }

  return {
    update,

    setMode(m) {
      if (MODES.indexOf(m) === -1) return;
      if (m === mode) return;
      mode = m;
      snap = true; // pas de long travelling en changeant de mode
    },

    get mode() {
      return mode;
    },

    /** Secousse decroissante, cumulative et bornee. */
    shake(amount) {
      const a = Number.isFinite(amount) ? Math.max(0, amount) : 0;
      shakeLevel = Math.min(1.6, shakeLevel + a);
    },

    dispose() {
      if (camera && camera.fov !== baseFov) {
        camera.fov = baseFov;
        camera.updateProjectionMatrix();
      }
    },
  };
}
