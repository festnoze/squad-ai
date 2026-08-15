/** "char:z" for a key that types z, null for anything longer than one glyph. */
function charOf(e) {
  return e.key && e.key.length === 1 ? 'char:' + e.key.toLowerCase() : null;
}

/** Keyboard, mouse and pointer-lock state. */
export class Input {
  constructor(domElement) {
    this.dom = domElement;
    this.keys = new Set();
    this.mouseDX = 0;
    this.mouseDY = 0;
    this.buttons = [false, false, false];
    this.pressedThisFrame = new Set();
    this.clickedThisFrame = [false, false, false];
    this.locked = false;
    // Some contexts (sandboxed iframes, automation, a few embedded browsers)
    // refuse pointer lock. We fall back to raw mousemove look so the game
    // stays playable instead of freezing the camera.
    this.fallbackLook = false;
    this.sensitivity = 0.0022;
    this.invertY = false;
    this.onLockChange = null;
    this.onLockError = null;
    this.enabled = true;

    this._onKeyDown = (e) => {
      if (!this.enabled) return;
      const code = e.code;
      if (!this.keys.has(code)) this.pressedThisFrame.add(code);
      this.keys.add(code);
      // Track the produced character too, so AZERTY (ZQSD) and QWERTY (WASD)
      // both work whatever the browser reports.
      const ch = charOf(e);
      if (ch) {
        if (!this.keys.has(ch)) this.pressedThisFrame.add(ch);
        this.keys.add(ch);
      }
      // stop the browser scrolling / quick-finding while playing
      if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Tab', 'Slash'].includes(code)) {
        e.preventDefault();
      }
    };
    this._onKeyUp = (e) => {
      this.keys.delete(e.code);
      const ch = charOf(e);
      if (ch) this.keys.delete(ch);
    };
    this._onMouseMove = (e) => {
      if (!this.active) return;
      this.mouseDX += e.movementX || 0;
      this.mouseDY += e.movementY || 0;
    };
    this._onMouseDown = (e) => {
      if (!this.active) return;
      if (e.button < 3) {
        this.buttons[e.button] = true;
        this.clickedThisFrame[e.button] = true;
      }
      e.preventDefault();
    };
    this._onMouseUp = (e) => {
      if (e.button < 3) this.buttons[e.button] = false;
    };
    this._onContext = (e) => e.preventDefault();
    this._onBlur = () => {
      this.keys.clear();
      this.buttons = [false, false, false];
    };
    this._onLockChange = () => {
      this.locked = document.pointerLockElement === this.dom;
      if (!this.locked) {
        this.keys.clear();
        this.buttons = [false, false, false];
      }
      if (this.onLockChange) this.onLockChange(this.locked);
    };

    this._onLockError = () => {
      this.fallbackLook = true;
      if (this.onLockError) this.onLockError();
    };

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

  /** True when look and shoot input should be read. */
  get active() {
    return this.locked || this.fallbackLook;
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
  pressed(code) { return this.pressedThisFrame.has(code); }

  /** Edge-triggered version of any(). */
  pressedAny(...names) {
    for (const n of names) if (this.pressedThisFrame.has(n)) return true;
    return false;
  }
  clicked(button) { return this.clickedThisFrame[button]; }

  /** True if any of the given codes / "char:x" entries is held. */
  any(...names) {
    for (const n of names) if (this.keys.has(n)) return true;
    return false;
  }

  /**
   * Movement intent in local space: x = strafe, z = forward.
   * Accepts QWERTY (WASD), AZERTY (ZQSD) and the arrow keys.
   */
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

  /** Consume per-frame edge state. Call once at the end of every frame. */
  endFrame() {
    this.pressedThisFrame.clear();
    this.clickedThisFrame[0] = this.clickedThisFrame[1] = this.clickedThisFrame[2] = false;
    this.mouseDX = 0;
    this.mouseDY = 0;
  }
}
