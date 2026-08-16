/**
 * PARADOXE - keyboard and mouse.
 *
 * The keyboard is reduced to a single byte (BIT in config.js) because that byte
 * is what gets recorded. Everything else (rewind, undo, pause) is an edge
 * triggered command that never enters the simulation.
 *
 * AZERTY and QWERTY share the same physical keys: KeyZ and KeyW both mean
 * forward, KeyQ and KeyA both mean left. Ctrl+Z is undo and must not also read
 * as "forward", so the modifier is checked first.
 */

import { BIT, CAMERA, KEYS } from './config.js';

const MOVE_CODES = new Map();
for (const code of KEYS.forward) MOVE_CODES.set(code, BIT.forward);
for (const code of KEYS.back) MOVE_CODES.set(code, BIT.back);
for (const code of KEYS.left) MOVE_CODES.set(code, BIT.left);
for (const code of KEYS.right) MOVE_CODES.set(code, BIT.right);
for (const code of KEYS.jump) MOVE_CODES.set(code, BIT.jump);
for (const code of KEYS.interact) MOVE_CODES.set(code, BIT.interact);

/** Camera orbit keys. Held, not edge triggered, and outside the recorded byte. */
const ROTATE_CODES = new Map();
for (const code of KEYS.camLeft) ROTATE_CODES.set(code, 'left');
for (const code of KEYS.camRight) ROTATE_CODES.set(code, 'right');
for (const code of KEYS.camUp) ROTATE_CODES.set(code, 'up');
for (const code of KEYS.camDown) ROTATE_CODES.set(code, 'down');

const COMMAND_CODES = new Map();
for (const code of KEYS.rewind) COMMAND_CODES.set(code, 'rewind');
for (const code of KEYS.restart) COMMAND_CODES.set(code, 'restart');
for (const code of KEYS.pause) COMMAND_CODES.set(code, 'pause');
for (const code of KEYS.mute) COMMAND_CODES.set(code, 'mute');

const PREVENT = new Set(['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown']);

function isFormTarget(node) {
  if (!node || !node.tagName) return false;
  const tag = node.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || node.isContentEditable === true;
}

export function createInput(canvas) {
  const held = new Map();
  const rotHeld = new Map();
  const edges = new Set();
  const listeners = new Map();

  const mouse = { dx: 0, dy: 0, wheel: 0, swipeX: 0, swipeY: 0, dragging: false };
  const camAxis = { yaw: 0, pitch: 0 };
  let dragX = 0;
  let dragY = 0;

  const input = {
    bits: 0,
    enabled: true,
    mouse,
  };

  function fire(name) {
    const list = listeners.get(name);
    if (list) for (let i = 0; i < list.length; i++) list[i]();
  }

  function recomputeBits() {
    let bits = 0;
    for (const [code, bit] of held) {
      void code;
      bits |= bit;
    }
    input.bits = input.enabled ? bits : 0;
  }

  /** Opposite keys cancel, so holding J and L leaves the camera still. */
  function recomputeCamAxis() {
    let yaw = 0;
    let pitch = 0;
    for (const dir of rotHeld.values()) {
      if (dir === 'left') yaw -= 1;
      else if (dir === 'right') yaw += 1;
      else if (dir === 'up') pitch += 1;
      else pitch -= 1;
    }
    camAxis.yaw = yaw < -1 ? -1 : yaw > 1 ? 1 : yaw;
    camAxis.pitch = pitch < -1 ? -1 : pitch > 1 ? 1 : pitch;
  }

  function onKeyDown(e) {
    if (isFormTarget(e.target)) return;
    if (PREVENT.has(e.code)) e.preventDefault();

    if (e.ctrlKey || e.metaKey) {
      if (e.code === 'KeyZ') {
        e.preventDefault();
        if (!e.repeat) {
          edges.add('undo');
          fire('undo');
        }
      }
      return;
    }

    const cmd = COMMAND_CODES.get(e.code);
    if (cmd && !e.repeat) {
      edges.add(cmd);
      fire(cmd);
    }

    const rot = ROTATE_CODES.get(e.code);
    if (rot !== undefined && !rotHeld.has(e.code)) {
      rotHeld.set(e.code, rot);
      recomputeCamAxis();
    }

    const bit = MOVE_CODES.get(e.code);
    if (bit !== undefined) {
      if (!held.has(e.code)) {
        held.set(e.code, bit);
        recomputeBits();
      }
    }
  }

  function onKeyUp(e) {
    if (rotHeld.has(e.code)) {
      rotHeld.delete(e.code);
      recomputeCamAxis();
    }
    if (held.has(e.code)) {
      held.delete(e.code);
      recomputeBits();
    }
  }

  function releaseAll() {
    held.clear();
    rotHeld.clear();
    edges.clear();
    input.bits = 0;
    camAxis.yaw = 0;
    camAxis.pitch = 0;
    mouse.dx = 0;
    mouse.dy = 0;
    mouse.wheel = 0;
    mouse.swipeX = 0;
    mouse.swipeY = 0;
    mouse.dragging = false;
  }

  function onBlur() {
    releaseAll();
  }

  function onPointerDown(e) {
    if (e.button !== 0 && e.button !== 2) return;
    mouse.dragging = true;
    dragX = e.clientX;
    dragY = e.clientY;
    if (canvas.setPointerCapture) {
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch (err) {
        void err;
      }
    }
  }

  function onPointerUp() {
    mouse.dragging = false;
  }

  function onPointerMove(e) {
    if (!mouse.dragging) return;
    // Client deltas, not movementX: the pointer is never locked here, and some
    // trackpad drivers report zero movement for a slow drag.
    mouse.dx += e.clientX - dragX;
    mouse.dy += e.clientY - dragY;
    dragX = e.clientX;
    dragY = e.clientY;
  }

  /**
   * A wheel zooms, a trackpad orbits. Horizontal scroll is only ever a two
   * finger swipe, so it maps to yaw; vertical scroll keeps its usual zoom role
   * unless Shift or Alt is held, which turns it into pitch. Only the dominant
   * axis is acted on, otherwise a slightly diagonal swipe turns and zooms at
   * once. Pinch to zoom arrives as Ctrl+wheel and falls through to the zoom.
   */
  function onWheel(e) {
    e.preventDefault();
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      mouse.swipeX += e.deltaX;
      return;
    }
    if (e.shiftKey || e.altKey) mouse.swipeY += e.deltaY;
    else mouse.wheel += e.deltaY;
  }

  function onContextMenu(e) {
    e.preventDefault();
  }

  window.addEventListener('keydown', onKeyDown, { passive: false });
  window.addEventListener('keyup', onKeyUp);
  window.addEventListener('blur', onBlur);
  canvas.addEventListener('pointerdown', onPointerDown);
  window.addEventListener('pointerup', onPointerUp);
  window.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', onContextMenu);

  /** Rising edge, consumed on read. */
  input.pressed = function pressed(name) {
    if (!edges.has(name)) return false;
    edges.delete(name);
    return true;
  };

  input.on = function on(name, cb) {
    let list = listeners.get(name);
    if (!list) {
      list = [];
      listeners.set(name, list);
    }
    list.push(cb);
  };

  /**
   * Drain every orbit source into one drag, expressed in mouse pixels: pointer
   * drag, trackpad swipe and held camera keys all end up on the same scale so
   * camera.js only has to know about one sensitivity.
   * @param {object} out reused output object
   * @param {number} dt seconds since the previous call, for the held keys
   */
  input.consumeMouse = function consumeMouse(out, dt) {
    const step = Number.isFinite(dt) && dt > 0 ? Math.min(dt, 0.1) : 0;
    out.dx = mouse.dx + mouse.swipeX * CAMERA.swipeToDrag + camAxis.yaw * CAMERA.keyRotate * step;
    // camUp raises the camera above the arena, which is a downward drag.
    out.dy = mouse.dy + mouse.swipeY * CAMERA.swipeToDrag + camAxis.pitch * CAMERA.keyRotate * step;
    out.wheel = mouse.wheel;
    mouse.dx = 0;
    mouse.dy = 0;
    mouse.wheel = 0;
    mouse.swipeX = 0;
    mouse.swipeY = 0;
    return out;
  };

  input.setEnabled = function setEnabled(v) {
    input.enabled = v;
    if (!v) releaseAll();
    else recomputeBits();
  };

  input.releaseAll = releaseAll;

  input.dispose = function dispose() {
    window.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('keyup', onKeyUp);
    window.removeEventListener('blur', onBlur);
    canvas.removeEventListener('pointerdown', onPointerDown);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('wheel', onWheel);
    canvas.removeEventListener('contextmenu', onContextMenu);
    releaseAll();
    listeners.clear();
  };

  return input;
}
