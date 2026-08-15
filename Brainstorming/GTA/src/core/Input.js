/**
 * Keyboard / mouse / gamepad input.
 *
 * Actions are polled (`down`, `pressed`) rather than event-driven so the fixed-step
 * simulation reads a stable snapshot. Call `endFrame()` once per frame after the
 * simulation has consumed `pressed`.
 *
 * Bindings are on `KeyboardEvent.code`, which identifies the *physical* key and ignores
 * the OS layout. `KeyW/KeyA/KeyS/KeyD` are therefore the same four physical keys on every
 * layout - the ones labelled W A S D on QWERTY and Z Q S D on AZERTY. That is what we
 * want: the movement cluster stays under the same fingers. Only the on-screen labels need
 * to change per layout, which `keyLabel()` handles via the Keyboard Map API.
 */

const DEFAULT_BINDINGS = {
  forward: ['KeyW', 'ArrowUp'],
  back: ['KeyS', 'ArrowDown'],
  left: ['KeyA', 'ArrowLeft'],
  right: ['KeyD', 'ArrowRight'],
  jump: ['Space'],
  sprint: ['ShiftLeft', 'ShiftRight'],
  handbrake: ['Space'],
  interact: ['KeyF'],
  fire: ['Mouse0'],
  aim: ['Mouse2'],
  reload: ['KeyR'],
  camera: ['KeyV'],
  horn: ['KeyH'],
  lights: ['KeyL'],
  map: ['KeyM'],
  pause: ['Escape'],
  respawn: ['KeyK'],
  debug: ['F3'],
  nextRadio: ['BracketRight'],
  freeCam: ['KeyP'],
  phone: ['KeyT'],
  camUp: ['Space'],
  camDown: ['ControlLeft'],
};

export class Input {
  constructor(target = window) {
    this.bindings = { ...DEFAULT_BINDINGS };
    /** code -> printed label for the user's actual layout, filled by `loadLayout()`. */
    this.layout = new Map();
    this.codes = new Set();
    this.justPressed = new Set();
    this.justReleased = new Set();
    this.mouse = { dx: 0, dy: 0, wheel: 0, locked: false };
    this.gamepadIndex = null;
    this.axes = { moveX: 0, moveY: 0, lookX: 0, lookY: 0, throttle: 0, brake: 0 };
    this._target = target;
    this._install();
  }

  _install() {
    const t = this._target;

    this._onKeyDown = (e) => {
      // Let the browser keep F5/F12/devtools shortcuts.
      if (e.code === 'F5' || e.code === 'F12') return;
      if (e.repeat) return;
      if (!this.codes.has(e.code)) this.justPressed.add(e.code);
      this.codes.add(e.code);
      if (e.code === 'Tab' || e.code === 'Space' || e.code.startsWith('Arrow')) e.preventDefault();
    };
    this._onKeyUp = (e) => {
      this.codes.delete(e.code);
      this.justReleased.add(e.code);
    };
    this._onBlur = () => { this.codes.clear(); };

    this._onMouseDown = (e) => {
      const code = `Mouse${e.button}`;
      if (!this.codes.has(code)) this.justPressed.add(code);
      this.codes.add(code);
    };
    this._onMouseUp = (e) => {
      const code = `Mouse${e.button}`;
      this.codes.delete(code);
      this.justReleased.add(code);
    };
    this._onMouseMove = (e) => {
      if (!this.mouse.locked) return;
      this.mouse.dx += e.movementX;
      this.mouse.dy += e.movementY;
    };
    this._onWheel = (e) => { this.mouse.wheel += Math.sign(e.deltaY); e.preventDefault(); };
    this._onContext = (e) => e.preventDefault();
    this._onLockChange = () => {
      this.mouse.locked = document.pointerLockElement !== null;
      if (!this.mouse.locked) this.codes.clear();
    };
    this._onPadConnect = (e) => { this.gamepadIndex = e.gamepad.index; };
    this._onPadDisconnect = () => { this.gamepadIndex = null; };

    t.addEventListener('keydown', this._onKeyDown);
    t.addEventListener('keyup', this._onKeyUp);
    t.addEventListener('blur', this._onBlur);
    t.addEventListener('mousedown', this._onMouseDown);
    t.addEventListener('mouseup', this._onMouseUp);
    t.addEventListener('mousemove', this._onMouseMove);
    t.addEventListener('wheel', this._onWheel, { passive: false });
    t.addEventListener('contextmenu', this._onContext);
    document.addEventListener('pointerlockchange', this._onLockChange);
    t.addEventListener('gamepadconnected', this._onPadConnect);
    t.addEventListener('gamepaddisconnected', this._onPadDisconnect);
  }

  /**
   * Resolve physical key codes to the characters actually printed on the user's
   * keyboard, so an AZERTY player is told "ZQSD" and a QWERTY player "WASD".
   * Falls back to the QWERTY-ish code name when the Keyboard Map API is unavailable.
   */
  async loadLayout() {
    try {
      const map = await navigator.keyboard?.getLayoutMap?.();
      if (map) for (const [code, key] of map) this.layout.set(code, key.toUpperCase());
    } catch {
      // Firefox/Safari have no Keyboard Map API; labels stay at their defaults.
    }
    return this.layout;
  }

  /** Printed label for a physical key code, e.g. `KeyW` -> "Z" on AZERTY. */
  keyLabel(code) {
    if (this.layout.has(code)) return this.layout.get(code);
    if (code.startsWith('Key')) return code.slice(3);
    if (code.startsWith('Digit')) return code.slice(5);
    return code;
  }

  /** Label for the first key bound to an action, e.g. `interact` -> "F". */
  actionLabel(action) {
    const code = this.bindings[action]?.[0];
    return code ? this.keyLabel(code) : '?';
  }

  /** The movement cluster as printed, e.g. "WASD" or "ZQSD". */
  get moveKeysLabel() {
    return ['forward', 'left', 'back', 'right']
      .map((a) => this.actionLabel(a)).join('');
  }

  requestLock(element) {
    if (document.pointerLockElement === element) return;
    const p = element.requestPointerLock?.({ unadjustedMovement: true });
    // Some platforms reject unadjustedMovement; retry plain.
    if (p && typeof p.catch === 'function') p.catch(() => element.requestPointerLock());
  }

  releaseLock() { document.exitPointerLock?.(); }

  /** Is any key bound to `action` currently held? */
  down(action) {
    const keys = this.bindings[action];
    if (!keys) return false;
    for (const k of keys) if (this.codes.has(k)) return true;
    return false;
  }

  /** Did `action` transition to held this frame? */
  pressed(action) {
    const keys = this.bindings[action];
    if (!keys) return false;
    for (const k of keys) if (this.justPressed.has(k)) return true;
    return false;
  }

  released(action) {
    const keys = this.bindings[action];
    if (!keys) return false;
    for (const k of keys) if (this.justReleased.has(k)) return true;
    return false;
  }

  /** Analog value in [-1,1] combining keyboard digital input and gamepad sticks. */
  moveVector(out) {
    let x = (this.down('right') ? 1 : 0) - (this.down('left') ? 1 : 0);
    let y = (this.down('forward') ? 1 : 0) - (this.down('back') ? 1 : 0);
    if (Math.abs(this.axes.moveX) > 0.02) x = this.axes.moveX;
    if (Math.abs(this.axes.moveY) > 0.02) y = -this.axes.moveY;
    const len = Math.hypot(x, y);
    if (len > 1) { x /= len; y /= len; }
    out.x = x; out.y = y;
    return out;
  }

  /** Poll gamepad; call once per frame before reading axes. */
  pollGamepad() {
    if (this.gamepadIndex === null || !navigator.getGamepads) return;
    const pad = navigator.getGamepads()[this.gamepadIndex];
    if (!pad) return;
    const dz = (v) => (Math.abs(v) < 0.14 ? 0 : v);
    this.axes.moveX = dz(pad.axes[0] ?? 0);
    this.axes.moveY = dz(pad.axes[1] ?? 0);
    this.axes.lookX = dz(pad.axes[2] ?? 0);
    this.axes.lookY = dz(pad.axes[3] ?? 0);
    this.axes.throttle = pad.buttons[7]?.value ?? 0;
    this.axes.brake = pad.buttons[6]?.value ?? 0;
    // Map the important face buttons onto the keyboard action set.
    const map = { 0: 'Space', 1: 'KeyF', 2: 'KeyR', 3: 'KeyV', 9: 'Escape', 10: 'ShiftLeft' };
    for (const [i, code] of Object.entries(map)) {
      const pressedNow = pad.buttons[i]?.pressed;
      if (pressedNow && !this.codes.has(code)) { this.codes.add(code); this.justPressed.add(code); }
      else if (!pressedNow && this.codes.has(code)) { this.codes.delete(code); this.justReleased.add(code); }
    }
  }

  /** Consume per-frame deltas. */
  endFrame() {
    this.justPressed.clear();
    this.justReleased.clear();
    this.mouse.dx = 0;
    this.mouse.dy = 0;
    this.mouse.wheel = 0;
  }

  dispose() {
    const t = this._target;
    t.removeEventListener('keydown', this._onKeyDown);
    t.removeEventListener('keyup', this._onKeyUp);
    t.removeEventListener('blur', this._onBlur);
    t.removeEventListener('mousedown', this._onMouseDown);
    t.removeEventListener('mouseup', this._onMouseUp);
    t.removeEventListener('mousemove', this._onMouseMove);
    t.removeEventListener('wheel', this._onWheel);
    t.removeEventListener('contextmenu', this._onContext);
    document.removeEventListener('pointerlockchange', this._onLockChange);
    t.removeEventListener('gamepadconnected', this._onPadConnect);
    t.removeEventListener('gamepaddisconnected', this._onPadDisconnect);
  }
}
