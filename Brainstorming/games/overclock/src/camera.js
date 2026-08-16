/**
 * OVERCLOCK - orbit rig.
 *
 * Default angles are chosen so a level is readable without touching anything:
 * a three quarter view high enough to show the relief, low enough to keep the
 * painted floor visible.
 */

import * as THREE from 'three';

const MIN_EL = 0.2;
const MAX_EL = 1.45;

export function createCameraRig(camera, dom) {
  const target = new THREE.Vector3();
  const state = {
    az: -0.55,
    el: 0.74,
    dist: 12,
    azTo: -0.55,
    elTo: 0.74,
    distTo: 12,
    minDist: 4,
    maxDist: 40,
  };

  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  let pointerId = -1;

  function onDown(e) {
    if (e.button !== 0 && e.button !== 2) return;
    dragging = true;
    pointerId = e.pointerId;
    lastX = e.clientX;
    lastY = e.clientY;
    dom.setPointerCapture(e.pointerId);
  }

  function onMove(e) {
    if (!dragging || e.pointerId !== pointerId) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    state.azTo -= dx * 0.007;
    state.elTo = Math.max(MIN_EL, Math.min(MAX_EL, state.elTo + dy * 0.006));
  }

  function onUp(e) {
    if (e.pointerId !== pointerId) return;
    dragging = false;
    pointerId = -1;
    if (dom.hasPointerCapture(e.pointerId)) dom.releasePointerCapture(e.pointerId);
  }

  function onWheel(e) {
    e.preventDefault();
    const k = Math.exp(e.deltaY * 0.0012);
    state.distTo = Math.max(state.minDist, Math.min(state.maxDist, state.distTo * k));
  }

  function onContext(e) {
    e.preventDefault();
  }

  dom.addEventListener('pointerdown', onDown);
  dom.addEventListener('pointermove', onMove);
  dom.addEventListener('pointerup', onUp);
  dom.addEventListener('pointercancel', onUp);
  dom.addEventListener('wheel', onWheel, { passive: false });
  dom.addEventListener('contextmenu', onContext);

  const rig = {
    target,

    /** Frames a level: radius in world units, centre height in world units. */
    frame(radius, centerY) {
      target.set(0, centerY, 0);
      const fov = (camera.fov * Math.PI) / 180;
      const d = (radius / Math.tan(fov / 2)) * 1.05;
      state.dist = state.distTo = d;
      state.minDist = d * 0.35;
      state.maxDist = d * 2.8;
      state.az = state.azTo = -0.55;
      state.el = state.elTo = 0.74;
      rig.update(1);
    },

    reset() {
      state.azTo = -0.55;
      state.elTo = 0.74;
    },

    update(dt) {
      const k = Math.min(1, dt * 12);
      state.az += (state.azTo - state.az) * k;
      state.el += (state.elTo - state.el) * k;
      state.dist += (state.distTo - state.dist) * k;

      const ce = Math.cos(state.el);
      camera.position.set(
        target.x + state.dist * ce * Math.sin(state.az),
        target.y + state.dist * Math.sin(state.el),
        target.z + state.dist * ce * Math.cos(state.az)
      );
      camera.lookAt(target);
    },

    dispose() {
      dom.removeEventListener('pointerdown', onDown);
      dom.removeEventListener('pointermove', onMove);
      dom.removeEventListener('pointerup', onUp);
      dom.removeEventListener('pointercancel', onUp);
      dom.removeEventListener('wheel', onWheel);
      dom.removeEventListener('contextmenu', onContext);
    },
  };

  return rig;
}
