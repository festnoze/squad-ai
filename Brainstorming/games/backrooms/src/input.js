/** "char:z" for a key that types z, null for anything longer than one glyph (AZERTY/QWERTY safe). */
function charOf(e) {
  return e.key && e.key.length === 1 ? 'char:' + e.key.toLowerCase() : null;
}

const NAV_KEYS = ['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Tab'];

/** Keyboard, mouse and pointer-lock state, plus a drag-to-look fallback for when lock fails. */
export class Input {
  constructor(domElement) {
    this.dom = domElement;
    this.keys = new Set();
    this.mouseDX = 0;
    this.mouseDY = 0;
    this.dragDX = 0;
    this.dragDY = 0;
    // code/char -> ms timestamp it was pressed. A Map (not a Set) so a press can
    // outlive the single frame it happened on: an entry guard (intro/pause/level
    // -complete overlay) reads no keys at all, and if we wiped this every frame
    // regardless of whether anything consumed it, a key pressed the instant
    // before/while such a guard is up would be silently dropped forever the
    // moment play resumes. Instead it stays valid for `pressedBufferMs` so the
    // resuming frame still sees it, and callers that act on it call consume()
    // to clear it immediately so it cannot also re-fire on the next frame.
    this.pressedThisFrame = new Map();
    this.pressedBufferMs = 350;
    this.locked = false;
    this.fallbackLook = false; // pointer lock refused by the browser/embedder
    this.dragging = false;
    this._lastClientX = 0;
    this._lastClientY = 0;
    this.sensitivity = 0.0026;
    this.invertY = false;
    this.onLockChange = null;
    this.enabled = true;

    this._onKeyDown = (e) => {
      if (!this.enabled) return;
      const code = e.code;
      if (!this.keys.has(code)) this.pressedThisFrame.set(code, performance.now());
      this.keys.add(code);
      const ch = charOf(e);
      if (ch) {
        if (!this.keys.has(ch)) this.pressedThisFrame.set(ch, performance.now());
        this.keys.add(ch);
      }
      if (NAV_KEYS.includes(code)) e.preventDefault();
    };
    this._onKeyUp = (e) => {
      this.keys.delete(e.code);
      const ch = charOf(e);
      if (ch) this.keys.delete(ch);
    };
    this._onMouseMove = (e) => {
      if (this.locked) {
        this.mouseDX += e.movementX || 0;
        this.mouseDY += e.movementY || 0;
      } else if (this.dragging) {
        this.dragDX += e.clientX - this._lastClientX;
        this.dragDY += e.clientY - this._lastClientY;
        this._lastClientX = e.clientX;
        this._lastClientY = e.clientY;
      }
    };
    this._onMouseDown = (e) => {
      if (!this.enabled || e.button !== 0) return;
      if (!this.locked) {
        this.dragging = true;
        this._lastClientX = e.clientX;
        this._lastClientY = e.clientY;
      }
    };
    this._onMouseUp = () => { this.dragging = false; };
    this._onContext = (e) => e.preventDefault();
    this._onBlur = () => { this.keys.clear(); this.dragging = false; };
    this._onLockChange = () => {
      this.locked = document.pointerLockElement === this.dom;
      if (!this.locked) this.keys.clear();
      if (this.onLockChange) this.onLockChange(this.locked);
    };
    this._onLockError = () => { this.fallbackLook = true; };

    window.addEventListener('keydown', this._onKeyDown);
    window.addEventListener('keyup', this._onKeyUp);
    window.addEventListener('mousemove', this._onMouseMove);
    window.addEventListener('mousedown', this._onMouseDown);
    window.addEventListener('mouseup', this._onMouseUp);
    window.addEventListener('blur', this._onBlur);
    document.addEventListener('pointerlockchange', this._onLockChange);
    document.addEventListener('pointerlockerror', this._onLockError);
    this.dom.addEventListener('contextmenu', this._onContext);
  }

  requestLock() {
    if (this.locked || !this.dom.requestPointerLock) return;
    try {
      const p = this.dom.requestPointerLock();
      if (p && typeof p.catch === 'function') p.catch(() => this._onLockError());
    } catch (err) {
      this._onLockError();
    }
  }

  releaseLock() {
    if (this.locked && document.exitPointerLock) document.exitPointerLock();
  }

  down(code) { return this.keys.has(code); }
  /** True while the key's press is still inside its short buffer window. */
  pressed(code) {
    const t = this.pressedThisFrame.get(code);
    return t !== undefined && (performance.now() - t) <= this.pressedBufferMs;
  }
  pressedAny(...names) {
    for (const n of names) if (this.pressed(n)) return true;
    return false;
  }
  /** Call once a buffered one-shot press has been acted on, so it does not fire again. */
  consume(...names) {
    for (const n of names) this.pressedThisFrame.delete(n);
  }
  any(...names) {
    for (const n of names) if (this.keys.has(n)) return true;
    return false;
  }

  /** Movement intent in local space: x = strafe, z = forward. QWERTY/AZERTY + arrows. */
  moveAxis() {
    let x = 0, z = 0;
    if (this.any('KeyW', 'KeyZ', 'char:w', 'char:z', 'ArrowUp')) z += 1;
    if (this.any('KeyS', 'char:s', 'ArrowDown')) z -= 1;
    if (this.any('KeyD', 'char:d', 'ArrowRight')) x += 1;
    if (this.any('KeyA', 'KeyQ', 'char:a', 'char:q', 'ArrowLeft')) x -= 1;
    const len = Math.hypot(x, z);
    if (len > 1) { x /= len; z /= len; }
    return { x, z };
  }

  /** Dedicated keyboard look, independent of movement keys: J/L yaw, I/K pitch. */
  lookAxis() {
    return {
      left: this.any('KeyJ', 'char:j'),
      right: this.any('KeyL', 'char:l'),
      up: this.any('KeyI', 'char:i'),
      down: this.any('KeyK', 'char:k'),
    };
  }

  /**
   * Call once at the end of every frame. Continuous deltas (mouse/drag) always
   * reset so time spent in a menu doesn't cause a jump on resume. Buffered
   * one-shot presses are left alone here - they expire on their own via
   * pressedBufferMs (see pressed()) or are removed explicitly via consume();
   * only stale entries are pruned so the map cannot grow unbounded.
   */
  endFrame() {
    if (this.pressedThisFrame.size) {
      const now = performance.now();
      for (const [k, t] of this.pressedThisFrame) {
        if (now - t > this.pressedBufferMs) this.pressedThisFrame.delete(k);
      }
    }
    this.mouseDX = 0;
    this.mouseDY = 0;
    this.dragDX = 0;
    this.dragDY = 0;
  }

  dispose() {
    window.removeEventListener('keydown', this._onKeyDown);
    window.removeEventListener('keyup', this._onKeyUp);
    window.removeEventListener('mousemove', this._onMouseMove);
    window.removeEventListener('mousedown', this._onMouseDown);
    window.removeEventListener('mouseup', this._onMouseUp);
    window.removeEventListener('blur', this._onBlur);
    document.removeEventListener('pointerlockchange', this._onLockChange);
    document.removeEventListener('pointerlockerror', this._onLockError);
    this.dom.removeEventListener('contextmenu', this._onContext);
  }
}
