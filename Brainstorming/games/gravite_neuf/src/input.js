/**
 * GRAVITE NEUF - keyboard and pointer input.
 *
 * The six gravity keys are emitted as *screen relative* actions (forward, back,
 * left, right, up, down). Turning them into a world axis is the camera's job:
 * doing it here would break the moment the player orbits the structure.
 *
 * Letters are read from `event.key` rather than `event.code` so an AZERTY
 * keyboard gets ZQSD and A / E exactly as the interface promises.
 */

const TILT_KEYS = {
  arrowup: 'forward',
  z: 'forward',
  w: 'forward',
  arrowdown: 'back',
  s: 'back',
  arrowleft: 'left',
  q: 'left',
  arrowright: 'right',
  d: 'right',
  a: 'up',
  ' ': 'up',
  e: 'down',
  shift: 'down',
};

const COMMAND_KEYS = {
  r: 'restart',
  n: 'next',
  p: 'prev',
  m: 'mute',
  u: 'undo',
  backspace: 'undo',
  escape: 'pause',
};

// Still accepted while tilting is disabled (a screen is up).
const ALWAYS_KEYS = new Set(['escape', 'm']);

const PREVENT = new Set([
  'arrowup',
  'arrowdown',
  'arrowleft',
  'arrowright',
  ' ',
  'backspace',
  'shift',
]);

export function createInput(canvas) {
  const listeners = { tilt: [], command: [] };
  let enabled = true;

  let dragging = false;
  let pointerId = -1;
  let lastX = 0;
  let lastY = 0;
  let moved = 0;
  const orbitHandlers = [];
  const zoomHandlers = [];

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

    const tilt = TILT_KEYS[key];
    if (tilt) {
      emit('tilt', tilt);
      return;
    }
    const command = COMMAND_KEYS[key];
    if (command) emit('command', command);
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
      // Pointer already released by the browser, nothing to clean up.
    }
    pointerId = -1;
  }

  function onWheel(event) {
    event.preventDefault();
    for (let i = 0; i < zoomHandlers.length; i++) zoomHandlers[i](event.deltaY);
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
    onTilt(cb) {
      listeners.tilt.push(cb);
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
