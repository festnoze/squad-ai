/**
 * PONTS DE FORTUNE - pointer editing and camera control.
 *
 * Editing happens in the plane z = 0. Screen points are projected onto that
 * plane and snapped to the grid, which is why the default side on camera makes
 * the plan feel like a 2D editor while the scene stays in three dimensions.
 *
 * Left drag draws, right click removes, right drag orbits, middle drag pans,
 * wheel zooms. The right button does two jobs, separated by a movement
 * threshold: a click that never moved is a removal, anything else is an orbit.
 */

import * as THREE from 'three';
import { MATERIALS } from './config.js';
import { xToCol, yToRow, colToX, rowToY, canPlaceNode } from './levels.js';

const DRAG_THRESHOLD = 6; // pixels before a right press becomes an orbit
const SNAP = 0.52; // fraction of a grid cell that still snaps to a joint
const PICK_RADIUS = 1.25; // metres around a member for the right click test

const hit = new THREE.Vector3();

function distToSegment(px, py, ax, ay, bx, by) {
  const vx = bx - ax;
  const vy = by - ay;
  const len2 = vx * vx + vy * vy;
  let t = len2 > 1e-6 ? ((px - ax) * vx + (py - ay) * vy) / len2 : 0;
  t = Math.max(0, Math.min(1, t));
  const dx = px - (ax + vx * t);
  const dy = py - (ay + vy * t);
  return Math.sqrt(dx * dx + dy * dy);
}

export function createEditor(opts) {
  const { canvas, stage, view, audio, hud } = opts;
  let level = null;
  let bridge = null;
  let material = 'wood';
  let enabled = true;

  let drawing = false;
  const startPoint = [0, 0];
  const cursorPoint = [0, 0];

  let orbiting = false;
  let panning = false;
  let rightDown = false;
  let rightMoved = 0;
  let lastX = 0;
  let lastY = 0;

  function setLevel(lv, br) {
    level = lv;
    bridge = br;
    drawing = false;
    view.setPreview(null, null, null, false);
    if (level && level.allow.indexOf(material) < 0) material = level.allow[0];
  }

  function setMaterial(key) {
    if (!level || level.allow.indexOf(key) < 0) {
      audio.deny();
      hud.toast('MATERIAU INDISPONIBLE SUR CE CHANTIER', 'bad');
      return false;
    }
    material = key;
    audio.click();
    if (opts.onMaterial) opts.onMaterial(material);
    return true;
  }

  /** Nearest grid joint to a screen point, or null when nothing is close. */
  function pickJoint(clientX, clientY, out) {
    if (!stage.planePoint(clientX, clientY, hit)) return null;
    const cf = xToCol(level, hit.x);
    const rf = yToRow(hit.y);
    const col = Math.round(cf);
    const row = Math.round(rf);
    if (Math.abs(cf - col) > SNAP || Math.abs(rf - row) > SNAP) return null;
    if (!canPlaceNode(level, col, row)) return null;
    out[0] = col;
    out[1] = row;
    return out;
  }

  function pickElement(clientX, clientY) {
    if (!stage.planePoint(clientX, clientY, hit)) return -1;
    const els = bridge.elements;
    let best = -1;
    let bestD = PICK_RADIUS;
    for (let i = 0; i < els.length; i++) {
      const e = els[i];
      const d = distToSegment(
        hit.x, hit.y,
        colToX(level, e.ca), rowToY(e.ra),
        colToX(level, e.cb), rowToY(e.rb),
      );
      if (d < bestD) { bestD = d; best = i; }
    }
    return best;
  }

  function refreshPreview(clientX, clientY) {
    if (!drawing) return;
    const target = pickJoint(clientX, clientY, cursorPoint);
    if (!target || (target[0] === startPoint[0] && target[1] === startPoint[1])) {
      view.setPreview(null, null, null, false);
      hud.setCursor(null);
      return;
    }
    const check = bridge.evaluate(startPoint[0], startPoint[1], target[0], target[1], material);
    view.setPreview(startPoint, target, material, check.ok);
    hud.setCursor(
      check.cost + ' CR  (' + check.len.toFixed(1) + ' m)',
      check.ok ? MATERIALS[material].name : check.reason,
      check.ok,
    );
  }

  function commit(clientX, clientY) {
    const target = pickJoint(clientX, clientY, cursorPoint);
    drawing = false;
    view.setPreview(null, null, null, false);
    hud.setCursor(null);
    if (!target) return;
    if (target[0] === startPoint[0] && target[1] === startPoint[1]) return;
    const res = bridge.add(startPoint[0], startPoint[1], target[0], target[1], material);
    if (res.ok) {
      audio.place(material);
      if (opts.onChange) opts.onChange();
    } else {
      audio.deny();
      hud.toast(res.reason.toUpperCase(), 'bad');
    }
  }

  function onPointerDown(e) {
    if (!enabled || !level) return;
    canvas.setPointerCapture(e.pointerId);
    lastX = e.clientX;
    lastY = e.clientY;

    if (e.button === 1) {
      panning = true;
      e.preventDefault();
      return;
    }
    if (e.button === 2) {
      rightDown = true;
      rightMoved = 0;
      return;
    }
    if (e.button !== 0) return;

    if (opts.getMode() !== 'build') {
      orbiting = true;
      document.body.classList.add('dragging');
      return;
    }
    const joint = pickJoint(e.clientX, e.clientY, startPoint);
    if (joint) {
      drawing = true;
    } else {
      orbiting = true;
      document.body.classList.add('dragging');
    }
  }

  function onPointerMove(e) {
    if (!enabled || !level) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;

    if (rightDown) rightMoved += Math.abs(dx) + Math.abs(dy);

    if (panning) {
      const scale = (2 * stage.rig.dist * Math.tan((stage.camera.fov * Math.PI) / 360)) / canvas.clientHeight;
      stage.pan(-dx * scale, dy * scale);
      return;
    }
    if (orbiting || (rightDown && rightMoved > DRAG_THRESHOLD)) {
      stage.orbit(dx * 0.0055, dy * 0.0045);
      return;
    }
    if (drawing) {
      refreshPreview(e.clientX, e.clientY);
      return;
    }
    if (opts.getMode() === 'build') {
      const idx = pickElement(e.clientX, e.clientY);
      view.setHover(idx);
      if (idx >= 0) {
        const el = bridge.elements[idx];
        hud.setCursor(el.cost + ' CR', 'CLIC DROIT POUR RETIRER', true);
      } else {
        const joint = pickJoint(e.clientX, e.clientY, cursorPoint);
        if (joint) {
          hud.setCursor(MATERIALS[material].name, 'GLISSER VERS UN AUTRE NOEUD', true);
        } else {
          hud.setCursor(null);
        }
      }
    }
  }

  function onPointerUp(e) {
    if (!enabled || !level) return;
    if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
    document.body.classList.remove('dragging');

    if (e.button === 1) { panning = false; return; }
    if (e.button === 2) {
      const wasClick = rightMoved <= DRAG_THRESHOLD;
      rightDown = false;
      if (wasClick && opts.getMode() === 'build') {
        const idx = pickElement(e.clientX, e.clientY);
        if (idx >= 0) {
          bridge.removeAt(idx);
          view.setHover(-1);
          audio.remove();
          if (opts.onChange) opts.onChange();
        } else {
          audio.deny();
        }
      }
      return;
    }
    if (e.button !== 0) return;
    if (orbiting) { orbiting = false; return; }
    if (drawing) commit(e.clientX, e.clientY);
  }

  function onWheel(e) {
    if (!enabled) return;
    e.preventDefault();
    stage.zoom(e.deltaY > 0 ? 1 : -1);
  }

  function onContextMenu(e) { e.preventDefault(); }

  function onPointerLeave() {
    if (drawing) {
      drawing = false;
      view.setPreview(null, null, null, false);
    }
    hud.setCursor(null);
    view.setHover(-1);
  }

  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('pointerleave', onPointerLeave);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', onContextMenu);

  function dispose() {
    canvas.removeEventListener('pointerdown', onPointerDown);
    canvas.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('pointerup', onPointerUp);
    canvas.removeEventListener('pointercancel', onPointerUp);
    canvas.removeEventListener('pointerleave', onPointerLeave);
    canvas.removeEventListener('wheel', onWheel);
    canvas.removeEventListener('contextmenu', onContextMenu);
  }

  return {
    setLevel, setMaterial, dispose,
    get material() { return material; },
    set enabled(v) {
      enabled = v;
      if (!v) {
        drawing = false;
        orbiting = false;
        panning = false;
        rightDown = false;
        view.setPreview(null, null, null, false);
        view.setHover(-1);
        hud.setCursor(null);
      }
    },
    get enabled() { return enabled; },
    get drawing() { return drawing; },
  };
}
