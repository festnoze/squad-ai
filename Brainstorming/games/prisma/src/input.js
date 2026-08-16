/**
 * PRISMA - raw input to intents.
 *
 * This module never decides what a click means: it reports where the pointer is
 * and which button was used without dragging. main.js owns the meaning, which
 * keeps the "drag to orbit, click to place" split in one readable place.
 */

const DRAG_THRESHOLD = 5;

export function createInput(element) {
  const listeners = new Map();
  let dragging = false;
  let moved = 0;
  let button = -1;
  let lastX = 0;
  let lastY = 0;
  let enabled = true;

  function emit(name, a, b) {
    const fns = listeners.get(name);
    if (!fns) return;
    for (const fn of fns) fn(a, b);
  }

  function ndc(event) {
    const rect = element.getBoundingClientRect();
    return [
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    ];
  }

  function onPointerDown(event) {
    if (!enabled) return;
    try {
      element.setPointerCapture(event.pointerId);
    } catch {
      // Capture is a convenience for dragging outside the canvas; a pointer the
      // browser no longer tracks must not break placing a component.
    }
    dragging = true;
    moved = 0;
    button = event.button;
    lastX = event.clientX;
    lastY = event.clientY;
  }

  function onPointerMove(event) {
    if (!enabled) return;
    const [x, y] = ndc(event);
    if (dragging) {
      const dx = event.clientX - lastX;
      const dy = event.clientY - lastY;
      moved += Math.abs(dx) + Math.abs(dy);
      lastX = event.clientX;
      lastY = event.clientY;
      if (moved > DRAG_THRESHOLD) {
        emit('orbit', dx, dy);
        return;
      }
    }
    emit('hover', x, y);
  }

  function onPointerUp(event) {
    if (!enabled) return;
    if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
    const wasDrag = moved > DRAG_THRESHOLD;
    const btn = button;
    dragging = false;
    button = -1;
    if (wasDrag) return;
    const [x, y] = ndc(event);
    emit('hover', x, y);
    if (btn === 0) emit('primary');
    else if (btn === 2) emit('secondary');
    else if (btn === 1) emit('tertiary');
  }

  function onPointerLeave() {
    if (!dragging) emit('hover', null, null);
  }

  function onWheel(event) {
    if (!enabled) return;
    event.preventDefault();
    emit('wheel', event.deltaY);
  }

  function onContextMenu(event) {
    event.preventDefault();
  }

  function onKeyDown(event) {
    if (event.repeat && event.code !== 'KeyZ') return;
    const code = event.code;

    if ((event.ctrlKey || event.metaKey) && code === 'KeyZ') {
      event.preventDefault();
      emit('undo');
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;

    const digit = /^(Digit|Numpad)([1-5])$/.exec(code);
    if (digit) {
      event.preventDefault();
      emit('kind', Number(digit[2]) - 1);
      return;
    }

    switch (code) {
      case 'Escape':
        event.preventDefault();
        emit('pause');
        break;
      case 'KeyR':
        event.preventDefault();
        emit('restart');
        break;
      case 'KeyM':
        emit('mute');
        break;
      case 'KeyH':
        emit('help');
        break;
      case 'KeyC':
        emit('recenter');
        break;
      case 'Delete':
      case 'Backspace':
        event.preventDefault();
        emit('delete');
        break;
      case 'Space':
        event.preventDefault();
        emit('secondary');
        break;
      default:
        break;
    }
  }

  element.addEventListener('pointerdown', onPointerDown);
  element.addEventListener('pointermove', onPointerMove);
  element.addEventListener('pointerup', onPointerUp);
  element.addEventListener('pointercancel', onPointerUp);
  element.addEventListener('pointerleave', onPointerLeave);
  element.addEventListener('wheel', onWheel, { passive: false });
  element.addEventListener('contextmenu', onContextMenu);
  window.addEventListener('keydown', onKeyDown);

  return {
    on(name, fn) {
      if (!listeners.has(name)) listeners.set(name, []);
      listeners.get(name).push(fn);
    },
    setEnabled(v) {
      enabled = v;
      if (!v) {
        dragging = false;
        button = -1;
      }
    },
    dispose() {
      element.removeEventListener('pointerdown', onPointerDown);
      element.removeEventListener('pointermove', onPointerMove);
      element.removeEventListener('pointerup', onPointerUp);
      element.removeEventListener('pointercancel', onPointerUp);
      element.removeEventListener('pointerleave', onPointerLeave);
      element.removeEventListener('wheel', onWheel);
      element.removeEventListener('contextmenu', onContextMenu);
      window.removeEventListener('keydown', onKeyDown);
      listeners.clear();
    },
  };
}
