/**
 * CONTREPOIDS - keyboard and pointer input.
 *
 * Movement keys are emitted as *screen relative* actions (forward, back, left,
 * right): turning them into a grid direction is the camera's job, so orbiting
 * never breaks which key means what. Letters are read from `event.key` so an
 * AZERTY keyboard gets ZQSD exactly as the interface promises.
 *
 * Orbit input follows three independent paths, as required: mouse drag (using
 * clientX/Y deltas, never movementX/Y), mouse wheel for zoom, keyboard I/J/K/L
 * for orbiting without a pointer, and a trackpad two-finger swipe detected
 * from a wheel event whose deltaX dominates deltaY (only the dominant axis is
 * honoured so a diagonal swipe never zooms and rotates at once).
 */

const MOVE_KEYS = {
  arrowup: 'forward',
  z: 'forward',
  w: 'forward',
  arrowdown: 'back',
  s: 'back',
  arrowleft: 'left',
  q: 'left',
  a: 'left',
  arrowright: 'right',
  d: 'right',
};

const ORBIT_KEYS = {
  j: [-1, 0],
  l: [1, 0],
  i: [0, -1],
  k: [0, 1],
};

const COMMAND_KEYS = {
  r: 'restart',
  m: 'mute',
  escape: 'pause',
  e: 'action',
  ' ': 'jump',
};

// Still accepted while gameplay input is disabled (a screen is up).
const ALWAYS_KEYS = new Set(['escape', 'm']);

const PREVENT = new Set(['arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' ', 'backspace']);

export function createInput(canvas) {
  const listeners = { move: [], command: [] };
  let enabled = true;

  let dragging = false;
  let pointerId = -1;
  let lastX = 0;
  let lastY = 0;
  const orbitHandlers = [];
  const zoomHandlers = [];
  const KEY_ORBIT_SPEED = 1.6;

  function emit(bucket, value) {
    const list = listeners[bucket];
    for (let i = 0; i < list.length; i++) list[i](value);
  }

  function onKeyDown(event) {
    if (event.repeat) return;
    const key = String(event.key || '').toLowerCase();

    if ((event.ctrlKey || event.metaKey) && key === 'z') {
      event.preventDefault();
      if (enabled) emit('command', 'undo');
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    if (PREVENT.has(key)) event.preventDefault();
    if (!enabled) {
      if (ALWAYS_KEYS.has(key)) emit('command', COMMAND_KEYS[key]);
      return;
    }

    const orbitKey = ORBIT_KEYS[key];
    if (orbitKey) {
      for (let i = 0; i < orbitHandlers.length; i++) orbitHandlers[i](orbitKey[0] * KEY_ORBIT_SPEED * 0.02, orbitKey[1] * KEY_ORBIT_SPEED * 0.02);
      return;
    }

    const move = MOVE_KEYS[key];
    if (move) {
      emit('move', move);
      return;
    }
    const command = COMMAND_KEYS[key];
    if (command) emit('command', command);
  }

  function onPointerDown(event) {
    if (event.button !== 0 && event.button !== 2) return;
    dragging = true;
    pointerId = event.pointerId;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.setPointerCapture(pointerId);
    canvas.classList.add('grabbing');
  }

  function onPointerMove(event) {
    if (!dragging || event.pointerId !== pointerId) return;
    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    for (let i = 0; i < orbitHandlers.length; i++) orbitHandlers[i](dx * 0.0075, dy * 0.006);
  }

  function onPointerUp(event) {
    if (event.pointerId !== pointerId) return;
    dragging = false;
    canvas.classList.remove('grabbing');
    try {
      canvas.releasePointerCapture(pointerId);
    } catch (e) {
      // Pointer already released by the browser, nothing to clean up.
    }
    pointerId = -1;
  }

  function onWheel(event) {
    event.preventDefault();
    if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      // Two-finger trackpad swipe: only the dominant axis acts, and it rotates.
      for (let i = 0; i < orbitHandlers.length; i++) orbitHandlers[i](event.deltaX * 0.003, 0);
    } else {
      for (let i = 0; i < zoomHandlers.length; i++) zoomHandlers[i](event.deltaY);
    }
  }

  function onContextMenu(event) {
    event.preventDefault();
  }

  window.addEventListener('keydown', onKeyDown);
  canvas.addEventListener('pointerdown', onPointerDown);
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);
  window.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', onContextMenu);

  return {
    onMove(cb) {
      listeners.move.push(cb);
    },
    onCommand(cb) {
      listeners.command.push(cb);
    },
    onOrbit(cb) {
      orbitHandlers.push(cb);
    },
    onZoom(cb) {
      zoomHandlers.push(cb);
    },
    setEnabled(value) {
      enabled = value;
    },
    dispose() {
      window.removeEventListener('keydown', onKeyDown);
      canvas.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('contextmenu', onContextMenu);
    },
  };
}
