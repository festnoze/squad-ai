/**
 * ABYSSE - keyboard and mouse.
 *
 * Every key is read through `event.code`, which is the physical key position.
 * That way the ZQSD of an AZERTY keyboard and the WASD of a QWERTY one are the
 * same four keys without any layout detection.
 *
 * Mouse look only accumulates while the pointer is locked. `endFrame()` must be
 * called once per frame, after the game has read the state, so the edge
 * triggered values (`pressed`, `look`) reset properly.
 */

const MOVE_KEYS = {
  forward: ['KeyW', 'ArrowUp'],
  back: ['KeyS', 'ArrowDown'],
  left: ['KeyA', 'ArrowLeft'],
  right: ['KeyD', 'ArrowRight'],
};

// Keys we swallow so the browser does not scroll or open a quick find bar.
const SWALLOW = new Set([
  'Space',
  'Tab',
  'ArrowUp',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'KeyQ',
  'Slash',
  'Quote',
]);

export function createInput(canvas) {
  const held = new Set();
  const pressedThisFrame = new Set();
  const releasedThisFrame = new Set();

  const state = {
    locked: false,
    lookX: 0,
    lookY: 0,
    fire: false,
    firePressed: false,
    altFire: false,
    altFirePressed: false,
    wheel: 0,
    // Set by main.js. While true the input layer stops requesting the lock back
    // on click, which is what you want when a modal is open.
    suspended: false,
    onLockChange: null,
    onWheelWeapon: null,
  };

  // ------------------------------------------------------------------ keyboard

  function onKeyDown(e) {
    if (e.repeat) {
      if (SWALLOW.has(e.code)) e.preventDefault();
      return;
    }
    if (SWALLOW.has(e.code)) e.preventDefault();
    held.add(e.code);
    pressedThisFrame.add(e.code);
  }

  function onKeyUp(e) {
    held.delete(e.code);
    releasedThisFrame.add(e.code);
  }

  /** Alt tabbing away must not leave a key stuck down. */
  function onBlur() {
    held.clear();
    state.fire = false;
    state.altFire = false;
  }

  // --------------------------------------------------------------------- mouse

  function onMouseDown(e) {
    if (!state.locked) return;
    if (e.button === 0) {
      state.fire = true;
      state.firePressed = true;
    } else if (e.button === 2) {
      state.altFire = true;
      state.altFirePressed = true;
    }
  }

  function onMouseUp(e) {
    if (e.button === 0) state.fire = false;
    else if (e.button === 2) state.altFire = false;
  }

  function onMouseMove(e) {
    if (!state.locked) return;
    // Chrome can emit a single huge delta right after the lock is granted.
    const dx = e.movementX || 0;
    const dy = e.movementY || 0;
    if (Math.abs(dx) > 250 || Math.abs(dy) > 250) return;
    state.lookX += dx;
    state.lookY += dy;
  }

  function onWheel(e) {
    if (!state.locked) return;
    e.preventDefault();
    state.wheel += e.deltaY > 0 ? 1 : -1;
  }

  function onContextMenu(e) {
    e.preventDefault();
  }

  // ---------------------------------------------------------------- pointer lock

  function onLockChange() {
    const locked = document.pointerLockElement === canvas;
    if (locked === state.locked) return;
    state.locked = locked;
    if (!locked) {
      state.fire = false;
      state.altFire = false;
      held.clear();
    }
    if (typeof state.onLockChange === 'function') state.onLockChange(locked);
  }

  /**
   * Browsers fire this when the lock is refused, typically because it was
   * requested too soon after an exit. There was no transition out of a locked
   * state, so the listener must not be told the player just lost the pointer:
   * doing that would bounce the game straight into its pause menu, and the
   * resume button would request the lock again and bounce right back.
   */
  function onLockError() {
    const wasLocked = state.locked;
    state.locked = false;
    if (wasLocked && typeof state.onLockChange === 'function') state.onLockChange(false);
  }

  function requestLock() {
    if (state.locked) return;
    const p = canvas.requestPointerLock();
    // Chrome 113+ returns a promise that rejects if the document is not focused.
    if (p && typeof p.catch === 'function') p.catch(() => {});
  }

  function exitLock() {
    if (document.pointerLockElement === canvas) document.exitPointerLock();
  }

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  window.addEventListener('blur', onBlur);
  window.addEventListener('mousedown', onMouseDown);
  window.addEventListener('mouseup', onMouseUp);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', onContextMenu);
  document.addEventListener('pointerlockchange', onLockChange);
  document.addEventListener('pointerlockerror', onLockError);

  // -------------------------------------------------------------------- queries

  function down(code) {
    return held.has(code);
  }

  function pressed(code) {
    return pressedThisFrame.has(code);
  }

  function released(code) {
    return releasedThisFrame.has(code);
  }

  function anyDown(codes) {
    for (let i = 0; i < codes.length; i++) if (held.has(codes[i])) return true;
    return false;
  }

  /** Move axes in the range [-1, 1], already normalised on the diagonal. */
  function moveAxes(out) {
    let x = 0;
    let z = 0;
    if (anyDown(MOVE_KEYS.forward)) z += 1;
    if (anyDown(MOVE_KEYS.back)) z -= 1;
    if (anyDown(MOVE_KEYS.right)) x += 1;
    if (anyDown(MOVE_KEYS.left)) x -= 1;
    const len = Math.hypot(x, z);
    if (len > 1) {
      x /= len;
      z /= len;
    }
    out.x = x;
    out.z = z;
    return out;
  }

  function verticalAxis() {
    let v = 0;
    if (held.has('Space')) v += 1;
    if (held.has('ControlLeft') || held.has('ControlRight') || held.has('KeyC')) v -= 1;
    return v;
  }

  function sprinting() {
    return held.has('ShiftLeft') || held.has('ShiftRight');
  }

  function endFrame() {
    pressedThisFrame.clear();
    releasedThisFrame.clear();
    state.lookX = 0;
    state.lookY = 0;
    state.firePressed = false;
    state.altFirePressed = false;
    state.wheel = 0;
  }

  function dispose() {
    window.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('keyup', onKeyUp);
    window.removeEventListener('blur', onBlur);
    window.removeEventListener('mousedown', onMouseDown);
    window.removeEventListener('mouseup', onMouseUp);
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('wheel', onWheel);
    canvas.removeEventListener('contextmenu', onContextMenu);
    document.removeEventListener('pointerlockchange', onLockChange);
    document.removeEventListener('pointerlockerror', onLockError);
    exitLock();
  }

  return {
    state,
    down,
    pressed,
    released,
    moveAxes,
    verticalAxis,
    sprinting,
    requestLock,
    exitLock,
    endFrame,
    dispose,
  };
}
