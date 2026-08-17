// FPS look: mouse (pointer lock) as the primary path, with a keyboard turn
// fallback (J/L/I/K) and a click-drag fallback for when pointer lock is
// unavailable. Runs once per rendered frame (not the fixed step): look is
// direct player input, not part of the deterministic simulation.
import * as THREE from 'three';

const KEY_TURN_RATE = 1.9; // rad/s while a look key is held
const PITCH_LIMIT = Math.PI / 2 - 0.04;

export function createLook() {
  return { yaw: 0, pitch: 0 };
}

export function updateLook(look, dt, input, settings) {
  const sens = settings.sensitivity;
  const invert = settings.invertY ? -1 : 1;

  if (input.locked) {
    look.yaw -= input.mouseDX * sens;
    look.pitch -= invert * input.mouseDY * sens;
  } else if (input.dragging) {
    look.yaw -= input.dragDX * sens;
    look.pitch -= invert * input.dragDY * sens;
  }

  const k = input.lookAxis();
  if (k.left) look.yaw += KEY_TURN_RATE * dt;
  if (k.right) look.yaw -= KEY_TURN_RATE * dt;
  if (k.up) look.pitch += invert * KEY_TURN_RATE * dt;
  if (k.down) look.pitch -= invert * KEY_TURN_RATE * dt;

  look.pitch = Math.max(-PITCH_LIMIT, Math.min(PITCH_LIMIT, look.pitch));
}

/** Push the look angles and an eye-space world position into a three.js camera. */
export function applyLook(look, camera, eyeX, eyeY, eyeZ) {
  camera.position.set(eyeX, eyeY, eyeZ);
  camera.rotation.set(look.pitch, look.yaw, 0, 'YXZ');
}

export function forwardVector(look, out = new THREE.Vector3()) {
  return out.set(-Math.sin(look.yaw), 0, -Math.cos(look.yaw));
}
