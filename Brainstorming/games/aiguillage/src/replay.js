/**
 * AIGUILLAGE - slow motion collision replay.
 *
 * Purely a camera dramatisation: the simulation itself keeps running (at a
 * caller supplied time scale, typically 0.2x) so trains not involved in the
 * crash keep drifting; this module only pulls the camera's orbit target
 * toward the impact point over a fixed real-world duration.
 */

const DURATION = 2.6; // real seconds, not simulated seconds

export function createReplay() {
  let active = false;
  let elapsed = 0;
  let focus = null;

  return {
    get active() {
      return active;
    },

    start(worldPos) {
      active = true;
      elapsed = 0;
      focus = worldPos;
    },

    /** `dt` here is real (unscaled) time. Returns true while still playing. */
    update(dt, cameraRig) {
      if (!active) return false;
      elapsed += dt;
      if (focus && cameraRig) {
        cameraRig.target.lerp(focus, Math.min(1, dt * 1.4));
      }
      if (elapsed >= DURATION) {
        active = false;
        return false;
      }
      return true;
    },

    dispose() {
      active = false;
    },
  };
}
