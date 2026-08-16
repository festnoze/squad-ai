/**
 * VELOCITRON - keyboard input.
 *
 * Turns raw KeyboardEvent.code values (mapped by KEYS in config.js) into the
 * reusable `controls` object consumed by ship.js, plus edge triggered actions
 * for one shot commands (boost, pause, camera, mute, respawn).
 *
 * Design notes:
 * - `controls` is allocated once and mutated in place: zero allocation per frame.
 * - `pressed(action)` returns a rising edge and consumes it, so an action can
 *   never be handled twice.
 * - Every mapped key calls preventDefault (Space scrolls the page, the arrows
 *   scroll and move focus), except when the event targets a form control so the
 *   pause screen volume slider stays usable.
 * - Losing focus releases everything: a key held while alt-tabbing would
 *   otherwise stay down forever.
 */

import { KEYS, SHIP } from './config.js';

const ACTIONS = Object.keys(KEYS);

// code -> [action, ...]. A single physical key may drive several actions if the
// mapping ever overlaps, so the value is always a list.
const CODE_TO_ACTIONS = (() => {
  const map = new Map();
  for (let i = 0; i < ACTIONS.length; i++) {
    const action = ACTIONS[i];
    const codes = KEYS[action];
    for (let k = 0; k < codes.length; k++) {
      const code = codes[k];
      let list = map.get(code);
      if (!list) {
        list = [];
        map.set(code, list);
      }
      list.push(action);
    }
  }
  return map;
})();

// Actions that must keep working even when a form control has focus.
const UI_ACTIONS = new Set(['pause', 'mute']);

function isUiAction(action) {
  return UI_ACTIONS.has(action);
}

function isFormTarget(node) {
  if (!node || !node.tagName) return false;
  const tag = node.tagName;
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    tag === 'BUTTON' ||
    node.isContentEditable === true
  );
}

/**
 * @param {EventTarget} [target] element receiving the key events (window by default)
 * @returns {object} Input
 */
export function createInput(target) {
  const el = target || window;

  /** @type {Record<string, boolean>} held state per action */
  const down = Object.create(null);
  /** @type {Record<string, boolean>} unconsumed rising edge per action */
  const edge = Object.create(null);
  /** @type {Record<string, Function[]>} */
  const listeners = Object.create(null);

  for (let i = 0; i < ACTIONS.length; i++) {
    down[ACTIONS[i]] = false;
    edge[ACTIONS[i]] = false;
    listeners[ACTIONS[i]] = [];
  }

  // The single controls object handed to ship.js / race.js every frame.
  const controls = {
    thrust: 0,
    brake: 0,
    steer: 0,
    airLeft: 0,
    airRight: 0,
    boost: false,
  };

  function fire(action) {
    const cbs = listeners[action];
    for (let i = 0; i < cbs.length; i++) cbs[i]();
  }

  function onKeyDown(e) {
    const actions = CODE_TO_ACTIONS.get(e.code);
    if (!actions) return;
    // The pause screen volume slider keeps focus after being dragged, and it is
    // a form control: without this exemption Escape never reaches togglePause
    // and the player is stuck on the pause screen without a mouse.
    const form = isFormTarget(e.target);
    if (form && !actions.some(isUiAction)) return;
    e.preventDefault();
    if (e.repeat) return;
    for (let i = 0; i < actions.length; i++) {
      const action = actions[i];
      if (form && !UI_ACTIONS.has(action)) continue;
      if (down[action]) continue;
      down[action] = true;
      edge[action] = true;
      fire(action);
    }
  }

  function onKeyUp(e) {
    const actions = CODE_TO_ACTIONS.get(e.code);
    if (!actions) return;
    const form = isFormTarget(e.target);
    if (form && !actions.some(isUiAction)) return;
    e.preventDefault();
    for (let i = 0; i < actions.length; i++) down[actions[i]] = false;
  }

  function releaseAll() {
    for (let i = 0; i < ACTIONS.length; i++) {
      down[ACTIONS[i]] = false;
      edge[ACTIONS[i]] = false;
    }
    controls.thrust = 0;
    controls.brake = 0;
    controls.steer = 0;
    controls.airLeft = 0;
    controls.airRight = 0;
    controls.boost = false;
  }

  function onBlur() {
    releaseAll();
  }

  el.addEventListener('keydown', onKeyDown, { passive: false });
  el.addEventListener('keyup', onKeyUp, { passive: false });
  window.addEventListener('blur', onBlur);

  const input = {
    controls,
    enabled: true,

    /**
     * Recompute `controls` from the current keyboard state. `dt` is optional
     * and only used to ramp the steering axis.
     */
    update(dt) {
      if (!input.enabled) {
        controls.thrust = 0;
        controls.brake = 0;
        controls.steer = 0;
        controls.airLeft = 0;
        controls.airRight = 0;
        controls.boost = false;
        return controls;
      }
      controls.thrust = down.thrust ? 1 : 0;
      controls.brake = down.brake ? 1 : 0;
      // A key is digital but the rudder is not: snapping to full lock makes
      // every tap a swerve. Ramp toward the target instead, and snap back to
      // centre fast so releasing the key still feels immediate.
      const target = (down.right ? 1 : 0) - (down.left ? 1 : 0);
      const step = Number.isFinite(dt) && dt > 0 ? Math.min(dt, 1 / 20) : 1 / 60;
      const rate = target === 0 ? SHIP.steerRamp * 2.2 : SHIP.steerRamp;
      const delta = target - controls.steer;
      const move = rate * step;
      controls.steer += Math.abs(delta) <= move ? delta : Math.sign(delta) * move;
      controls.airLeft = down.airbrakeLeft ? 1 : 0;
      controls.airRight = down.airbrakeRight ? 1 : 0;
      // Boost is a one shot trigger: holding Space must not drain the tank.
      controls.boost = input.pressed('boost');
      return controls;
    },

    /** Rising edge, consumed on read. */
    pressed(action) {
      if (!input.enabled) return false;
      const value = edge[action] === true;
      edge[action] = false;
      return value;
    },

    isDown(action) {
      return down[action] === true;
    },

    /** Register a callback fired once per key press of `action`. */
    onAction(action, cb) {
      const list = listeners[action];
      if (!list || typeof cb !== 'function') return () => {};
      list.push(cb);
      return () => {
        const i = list.indexOf(cb);
        if (i >= 0) list.splice(i, 1);
      };
    },

    /** Force every key up (used on pause / focus loss). */
    releaseAll,

    dispose() {
      el.removeEventListener('keydown', onKeyDown);
      el.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('blur', onBlur);
      releaseAll();
      for (let i = 0; i < ACTIONS.length; i++) listeners[ACTIONS[i]].length = 0;
    },
  };

  return input;
}
