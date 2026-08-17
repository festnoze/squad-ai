/**
 * MAREE - keyboard, pointer and wheel input.
 *
 * Orbit camera lesson learned in a sibling project: dragging with the mouse
 * cannot be the only way to turn the camera, or the game is unplayable with
 * one hand on the keyboard and a trackpad under the other. So every orbit
 * path is offered here: mouse drag, I/J/K/L keys, and a two-finger trackpad
 * swipe (a wheel event whose deltaX dominates). Pointer deltas are taken from
 * clientX/clientY, not movementX/Y, which some trackpad drivers never fill in
 * outside of pointer lock.
 *
 * Plain vertical wheel is reserved for this game's own primary action (raise
 * or lower the selected basin, same as the up/down arrows) rather than zoom,
 * since that is what the design calls for; zoom still lives on the wheel, one
 * modifier away (Shift+wheel), so the mandatory zoom path is never dropped.
 */

const COMMAND_KEYS = {
  r: 'restart',
  n: 'next',
  p: 'prev',
  m: 'mute',
  escape: 'pause',
  '1': 'basin1',
  '2': 'basin2',
  '3': 'basin3',
  '4': 'basin4',
};

const LEVEL_KEYS = { arrowup: 1, arrowdown: -1 };
const ORBIT_KEYS = { i: [0, -1], k: [0, 1], j: [-1, 0], l: [1, 0] };

const PREVENT = new Set(['arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' ']);

export function createInput(canvas) {
  const listeners = { command: [], level: [] };
  const orbitHandlers = [];
  const zoomHandlers = [];
  const clickHandlers = [];
  let enabled = true;
  const orbitKeyState = { i: false, k: false, j: false, l: false };

  let dragging = false;
  let pointerId = -1;
  let lastX = 0;
  let lastY = 0;
  let moved = 0;

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

    if (key in ORBIT_KEYS) orbitKeyState[key] = true;

    if (!enabled) {
      if (key === 'escape' || key === 'm') emit('command', COMMAND_KEYS[key]);
      return;
    }
    if (key in LEVEL_KEYS) {
      emit('level', LEVEL_KEYS[key]);
      return;
    }
    const command = COMMAND_KEYS[key];
    if (command) emit('command', command);
  }

  function onKeyUp(event) {
    const key = String(event.key || '').toLowerCase();
    if (key in ORBIT_KEYS) orbitKeyState[key] = false;
  }

  function onPointerDown(event) {
    if (event.button !== 0 && event.button !== 2) return;
    dragging = true;
    moved = 0;
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
    moved += Math.abs(dx) + Math.abs(dy);
    for (let i = 0; i < orbitHandlers.length; i++) orbitHandlers[i](dx * 0.0075, dy * 0.006);
  }

  function onPointerUp(event) {
    if (event.pointerId !== pointerId) return;
    dragging = false;
    canvas.classList.remove('grabbing');
    try {
      canvas.releasePointerCapture(pointerId);
    } catch (e) {
      // Already released by the browser.
    }
    pointerId = -1;
    if (moved < 6 && event.button === 0) {
      for (let i = 0; i < clickHandlers.length; i++) clickHandlers[i](event.clientX, event.clientY);
    }
  }

  function onWheel(event) {
    event.preventDefault();
    // A trackpad two-finger swipe reports mostly deltaX; only the dominant
    // axis acts, so a slightly diagonal swipe never orbits and raises water
    // at once. Shift turns a plain vertical wheel into the camera zoom.
    if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      for (let i = 0; i < orbitHandlers.length; i++) orbitHandlers[i](event.deltaX * 0.0026, 0);
    } else if (event.shiftKey) {
      for (let i = 0; i < zoomHandlers.length; i++) zoomHandlers[i](event.deltaY);
    } else if (enabled) {
      emit('level', event.deltaY < 0 ? 1 : -1);
    }
  }

  function onContextMenu(event) {
    event.preventDefault();
  }

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  canvas.addEventListener('pointerdown', onPointerDown);
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);
  window.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', onContextMenu);

  return {
    onCommand(cb) {
      listeners.command.push(cb);
    },
    onLevel(cb) {
      listeners.level.push(cb);
    },
    onOrbit(cb) {
      orbitHandlers.push(cb);
    },
    onZoom(cb) {
      zoomHandlers.push(cb);
    },
    onClick(cb) {
      clickHandlers.push(cb);
    },
    /** Continuous keyboard orbit (I/J/K/L), called once per frame with dt. */
    applyKeyOrbit(dt) {
      let dx = 0;
      let dy = 0;
      if (orbitKeyState.j) dx -= 1;
      if (orbitKeyState.l) dx += 1;
      if (orbitKeyState.i) dy -= 1;
      if (orbitKeyState.k) dy += 1;
      if (dx || dy) {
        for (let i = 0; i < orbitHandlers.length; i++) orbitHandlers[i](dx * dt * 1.6, dy * dt * 1.2);
      }
    },
    setEnabled(value) {
      enabled = value;
    },
    dispose() {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      canvas.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('contextmenu', onContextMenu);
    },
  };
}
