/**
 * RESONANCE - input layer. Raw DOM events become semantic calls on the
 * handler object; no game state lives here.
 *
 * Camera paths (all three, deliberately): mouse drag orbits using client
 * deltas (never movementX outside pointer lock), wheel zooms, I/J/K/L orbit
 * from the keyboard (physical codes: stable spot on AZERTY and QWERTY).
 * Trackpads: a wheel event dominated by |deltaX| orbits instead of zooming,
 * and only the dominant axis is kept.
 */

export function createInput(canvas, handlers) {
  let down = false;
  let moved = false;
  let lastX = 0;
  let lastY = 0;
  let downX = 0;
  let downY = 0;
  let downButton = 0;
  const held = new Set();

  function ndc(e) {
    const r = canvas.getBoundingClientRect();
    return [
      ((e.clientX - r.left) / r.width) * 2 - 1,
      -(((e.clientY - r.top) / r.height) * 2 - 1),
    ];
  }

  function onPointerDown(e) {
    e.preventDefault(); // middle click must remove a fork, never autoscroll
    handlers.gesture();
    down = true;
    moved = false;
    lastX = downX = e.clientX;
    lastY = downY = e.clientY;
    downButton = e.button;
    canvas.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e) {
    const [nx, ny] = ndc(e);
    handlers.hover(nx, ny);
    if (!down) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    if (Math.abs(e.clientX - downX) + Math.abs(e.clientY - downY) > 6) moved = true;
    if (moved && downButton === 0) handlers.orbit(dx, dy);
  }

  function onPointerUp(e) {
    if (!down) return;
    down = false;
    if (!moved) {
      const [nx, ny] = ndc(e);
      handlers.click(nx, ny, e.button);
    }
  }

  function onWheel(e) {
    e.preventDefault();
    handlers.gesture();
    // Trackpad horizontal pan: orbit with the dominant axis only.
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      handlers.orbit(e.deltaX * 1.6, 0);
      return;
    }
    const [nx, ny] = ndc(e);
    handlers.wheel(nx, ny, Math.sign(e.deltaY) * Math.min(Math.abs(e.deltaY), 120));
  }

  function onKeyDown(e) {
    if (e.repeat && !['KeyI', 'KeyJ', 'KeyK', 'KeyL'].includes(e.code)) return;
    handlers.gesture();
    if (['KeyI', 'KeyJ', 'KeyK', 'KeyL'].includes(e.code)) {
      held.add(e.code);
      e.preventDefault();
      return;
    }
    const k = e.key.toLowerCase();
    if (e.ctrlKey && k === 'z') { e.preventDefault(); handlers.action('undo'); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    switch (e.code) {
      case 'Digit1': case 'Numpad1': handlers.action('band0'); return;
      case 'Digit2': case 'Numpad2': handlers.action('band1'); return;
      case 'Digit3': case 'Numpad3': handlers.action('band2'); return;
      default: break;
    }
    switch (k) {
      case 'f': handlers.action('freq'); break;
      case 'g': handlers.action('phase'); break;
      case 'r': handlers.action('restart'); break;
      case 'n': handlers.action('next'); break;
      case 'p': handlers.action('prev'); break;
      case 'm': handlers.action('mute'); break;
      case 'delete': case 'backspace': handlers.action('delete'); break;
      case 'escape': handlers.action('pause'); break;
      case 'enter': case ' ': handlers.action('confirm'); break;
      default: break;
    }
  }

  function onKeyUp(e) { held.delete(e.code); }

  function onContext(e) { e.preventDefault(); }

  /** Keyboard orbit, applied continuously while I/J/K/L are held. */
  function update(dt) {
    if (held.size === 0) return;
    const speed = 420 * dt;
    let dx = 0;
    let dy = 0;
    if (held.has('KeyJ')) dx -= speed;
    if (held.has('KeyL')) dx += speed;
    if (held.has('KeyI')) dy -= speed;
    if (held.has('KeyK')) dy += speed;
    if (dx || dy) handlers.orbit(dx, dy);
  }

  canvas.addEventListener('pointerdown', onPointerDown);
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  canvas.addEventListener('contextmenu', onContext);

  function dispose() {
    canvas.removeEventListener('pointerdown', onPointerDown);
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    canvas.removeEventListener('wheel', onWheel);
    window.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('keyup', onKeyUp);
    canvas.removeEventListener('contextmenu', onContext);
  }

  return { update, dispose };
}
