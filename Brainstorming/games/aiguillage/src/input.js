/**
 * AIGUILLAGE - pointer, keyboard and trackpad input.
 *
 * A left click that barely moves is a "pick" (toggle a switch, recall a
 * siding train); a left or middle drag orbits the camera instead. Mouse
 * drag uses clientX/clientY deltas (never movementX/Y, which some browsers
 * throttle oddly under high DPI scaling). A wheel event whose deltaX
 * dominates deltaY (two finger trackpad swipe) orbits instead of zooming.
 */

const CLICK_MOVE_THRESHOLD = 6; // pixels

const ORBIT_KEYS = {
  i: 'pitchUp',
  j: 'yawLeft',
  k: 'pitchDown',
  l: 'yawRight',
};

const COMMAND_KEYS = {
  escape: 'pause',
  m: 'mute',
  r: 'restart',
  ' ': 'pause-tactical',
};

export function createInput(canvas) {
  const listeners = { orbit: [], zoom: [], pick: [], command: [], orbitKey: [] };
  let enabled = true;

  let dragging = false;
  let pointerId = -1;
  let dragButton = -1;
  let lastX = 0;
  let lastY = 0;
  let moved = 0;

  const keysDown = new Set();

  function emit(bucket, ...args) {
    const list = listeners[bucket];
    for (let i = 0; i < list.length; i++) list[i](...args);
  }

  function onPointerDown(event) {
    if (!enabled) return;
    if (event.button !== 0 && event.button !== 1) return;
    dragging = true;
    dragButton = event.button;
    moved = 0;
    pointerId = event.pointerId;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.setPointerCapture(pointerId);
  }

  function onPointerMove(event) {
    if (!dragging || event.pointerId !== pointerId) return;
    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    moved += Math.abs(dx) + Math.abs(dy);
    emit('orbit', dx * 0.0055, -dy * 0.0045);
  }

  function onPointerUp(event) {
    if (event.pointerId !== pointerId) return;
    const wasClick = dragging && moved < CLICK_MOVE_THRESHOLD && dragButton === 0;
    dragging = false;
    try {
      canvas.releasePointerCapture(pointerId);
    } catch (err) {
      // Already released by the browser: nothing to clean up.
    }
    pointerId = -1;
    if (wasClick && enabled) {
      const rect = canvas.getBoundingClientRect();
      const ndcX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      const ndcY = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      emit('pick', ndcX, ndcY);
    }
  }

  function onWheel(event) {
    event.preventDefault();
    if (!enabled) return;
    if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      emit('orbit', event.deltaX * 0.0028, 0);
    } else {
      emit('zoom', event.deltaY);
    }
  }

  function onContextMenu(event) {
    event.preventDefault();
  }

  function onKeyDown(event) {
    const key = String(event.key || '').toLowerCase();
    if (key === ' ' || key === 'arrowup' || key === 'arrowdown' || key === 'arrowleft' || key === 'arrowright') {
      event.preventDefault();
    }
    if (event.repeat) {
      if (ORBIT_KEYS[key]) keysDown.add(key);
      return;
    }
    if (ORBIT_KEYS[key]) {
      keysDown.add(key);
      return;
    }
    const command = COMMAND_KEYS[key];
    if (command) emit('command', command);
  }

  function onKeyUp(event) {
    const key = String(event.key || '').toLowerCase();
    keysDown.delete(key);
  }

  function onBlur() {
    keysDown.clear();
    dragging = false;
  }

  canvas.addEventListener('pointerdown', onPointerDown);
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);
  window.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', onContextMenu);
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  window.addEventListener('blur', onBlur);

  return {
    onOrbit(cb) { listeners.orbit.push(cb); },
    onZoom(cb) { listeners.zoom.push(cb); },
    onPick(cb) { listeners.pick.push(cb); },
    onCommand(cb) { listeners.command.push(cb); },

    /** Called once per frame by main.js to turn held IJKL into orbit rates. */
    pollKeyboardOrbit(dt, orbitRateFn) {
      let yawRate = 0;
      let pitchRate = 0;
      if (keysDown.has('j')) yawRate -= 1;
      if (keysDown.has('l')) yawRate += 1;
      if (keysDown.has('i')) pitchRate += 1;
      if (keysDown.has('k')) pitchRate -= 1;
      if (yawRate !== 0 || pitchRate !== 0) orbitRateFn(yawRate * 1.6, pitchRate * 1.1, dt);
    },

    setEnabled(value) {
      enabled = value;
      if (!value) {
        dragging = false;
        keysDown.clear();
      }
    },

    dispose() {
      canvas.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
      canvas.removeEventListener('wheel', onWheel);
      canvas.removeEventListener('contextmenu', onContextMenu);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', onBlur);
    },
  };
}
