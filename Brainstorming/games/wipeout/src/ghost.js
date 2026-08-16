/**
 * VELOCITRON - best lap ghost.
 *
 * WHY TRACK SPACE
 * A ghost recorded as world matrices is a stream of 16 floats per sample that
 * only replays correctly against the exact geometry it was captured on: retune
 * the track, move the start line, change the hover height, and the old ghost
 * flies through walls. The craft state is already (s, x, h, yaw) plus two
 * cosmetic angles, so a sample here is seven floats and stays valid for as long
 * as the circuit keeps its shape. Replaying it means asking the track for the
 * frame at that abscissa, which is the same call the live craft makes: the
 * ghost lands on the road by construction, banking included.
 *
 * STORAGE FORMAT (localStorage, one entry per track key)
 *   { v: 1, lap: <ms, integer>, dt: <sample interval ms>, n: <sample count>,
 *     d: [ t, s, x, h, yaw, roll, pitch, ... ] }
 * `d` is flat and rounded (centimetres for the metric fields, a thousandth of a
 * radian for the angles): a 40 s lap is about 1000 samples, roughly 40 KB of
 * JSON, written once when a record falls. Any entry that fails a single
 * validation step is dropped and the key is cleared, never thrown: storage can
 * be disabled, full, or hold a payload from an older build.
 *
 * Nothing in sample / update / deltaMs allocates. Both buffers are sized once
 * at construction and the lookups are binary searches over flat Float32Arrays.
 */

import * as THREE from 'three';
import { PALETTE, SHIP } from './config.js';
import { createShipMesh } from './ship.js';

// ---------------------------------------------------------------------------
// Recording layout
// ---------------------------------------------------------------------------

const STRIDE = 7;
const O_T = 0;
const O_S = 1;
const O_X = 2;
const O_H = 3;
const O_YAW = 4;
const O_ROLL = 5;
const O_PITCH = 6;

// 40 ms is about 6 m of track at racing speed, well inside the radius the
// interpolation has to cover, and it keeps a lap under a thousand samples.
const SAMPLE_MS = 40;
// Hard cap: 4096 samples is 164 s of recording. A lap that long is not a lap,
// so the recording is flagged and refused at commit time instead of growing.
const MAX_SAMPLES = 4096;
const MIN_SAMPLES = 12;

const STORAGE_VERSION = 1;
const DEFAULT_KEY = 'velocitron.ghost.akari.v1';

// A lap must cover the circuit before it is worth keeping or replaying.
const MIN_LAP_COVERAGE = 0.9;
// Beyond this many metres past the end of the recording the delta is meaningless.
const DELTA_RANGE_SLACK = 60;
const DELTA_CLAMP_MS = 99999;
// Fixed blend applied to the returned delta so the HUD digit does not flicker
// on the sample boundaries.
const DELTA_SMOOTH = 0.3;

// ---------------------------------------------------------------------------
// Scratch, module level. This module never nests with itself, so a single set
// is safe here.
// ---------------------------------------------------------------------------

const WORLD_UP = new THREE.Vector3(0, 1, 0);
const _fwd = new THREE.Vector3();
const _rgt = new THREE.Vector3();
const _up = new THREE.Vector3();
const _back = new THREE.Vector3();
const _basis = new THREE.Matrix4();
const _qRoll = new THREE.Quaternion();
const _qPitch = new THREE.Quaternion();

function clamp(v, lo, hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

function finite(v, fallback) {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}

function round2(v) {
  return Math.round(v * 100) / 100;
}

function round3(v) {
  return Math.round(v * 1000) / 1000;
}

/**
 * Last index whose column value is <= target, in [0, count - 1].
 * The column must be ascending, which both the time column and the derived
 * progress table are by construction.
 */
function lastAtMost(arr, offset, stride, count, target) {
  let lo = 0;
  let hi = count - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (arr[offset + mid * stride] <= target) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

// ---------------------------------------------------------------------------
// Ghost
// ---------------------------------------------------------------------------

/**
 * Creates the ghost craft. opts = { track, textures, scene, color, storageKey }.
 * The mesh is built and added to the scene here, hidden until a record exists.
 */
export function createGhost(opts) {
  const o = opts || {};
  const track = o.track || null;
  const color = o.color === undefined ? PALETTE.white : o.color;
  const storageKey = typeof o.storageKey === 'string' && o.storageKey
    ? o.storageKey
    : DEFAULT_KEY;
  const trackLength = track && Number.isFinite(track.length) && track.length > 0
    ? track.length
    : 0;

  // -- mesh ---------------------------------------------------------------
  const mesh = createShipMesh(o.textures, color);
  mesh.name = 'ghost';
  mesh.visible = false;
  makeGhostly(mesh, color);
  if (o.scene && typeof o.scene.add === 'function') o.scene.add(mesh);

  // -- buffers ------------------------------------------------------------
  // Recording in progress and committed playback are two separate buffers:
  // starting the next lap must not touch the ghost currently on screen.
  const recBuf = new Float32Array(MAX_SAMPLES * STRIDE);
  const plyBuf = new Float32Array(MAX_SAMPLES * STRIDE);
  // Unwrapped distance travelled since the first sample, derived once per
  // committed lap so the abscissa lookup can binary search a monotonic column.
  const progBuf = new Float32Array(MAX_SAMPLES);

  let recCount = 0;
  let recording = false;
  let recOverflow = false;
  let nextSampleT = 0;

  let plyCount = 0;
  let plyLength = 0; // metres covered by the committed lap
  let wantVisible = false;
  let deltaSmoothed = null;

  const frame = track && typeof track.makeFrame === 'function' ? track.makeFrame() : null;
  const worldPos = new THREE.Vector3();
  const quat = new THREE.Quaternion();

  const ghost = {
    mesh,
    hasRecord: false,
    recordMs: null,
    sampleInterval: SAMPLE_MS,
  };

  // -- storage ------------------------------------------------------------
  // Every single access is guarded: reading window.localStorage itself throws
  // in a sandboxed frame, and setItem throws when the quota is full.
  function storage() {
    try {
      const s = window.localStorage;
      return s && typeof s.getItem === 'function' ? s : null;
    } catch (err) {
      return null;
    }
  }

  function removeEntry() {
    const s = storage();
    if (!s) return;
    try {
      s.removeItem(storageKey);
    } catch (err) {
      /* storage disabled mid session, nothing to do */
    }
  }

  function persist() {
    const s = storage();
    if (!s || plyCount < MIN_SAMPLES) return;
    try {
      const d = new Array(plyCount * STRIDE);
      for (let i = 0; i < plyCount; i++) {
        const b = i * STRIDE;
        d[b + O_T] = Math.round(plyBuf[b + O_T]);
        d[b + O_S] = round2(plyBuf[b + O_S]);
        d[b + O_X] = round2(plyBuf[b + O_X]);
        d[b + O_H] = round2(plyBuf[b + O_H]);
        d[b + O_YAW] = round3(plyBuf[b + O_YAW]);
        d[b + O_ROLL] = round3(plyBuf[b + O_ROLL]);
        d[b + O_PITCH] = round3(plyBuf[b + O_PITCH]);
      }
      s.setItem(storageKey, JSON.stringify({
        v: STORAGE_VERSION,
        lap: Math.round(ghost.recordMs),
        dt: SAMPLE_MS,
        n: plyCount,
        d,
      }));
    } catch (err) {
      /* quota exceeded or serialisation refused: the session ghost still works */
    }
  }

  /**
   * Fills progBuf with the unwrapped distance covered by `count` samples of
   * `buf` and returns the total. progBuf is scratch shared by the recording and
   * the committed lap, so whoever overwrites it puts the right table back.
   */
  function fillProgress(buf, count) {
    if (count <= 0) return 0;
    progBuf[0] = 0;
    for (let i = 1; i < count; i++) {
      const prev = buf[(i - 1) * STRIDE + O_S];
      const cur = buf[i * STRIDE + O_S];
      let step = trackLength > 0 && typeof track.deltaS === 'function'
        ? track.deltaS(prev, cur)
        : cur - prev;
      if (!Number.isFinite(step) || step < 0) step = 0; // keep the column ascending
      progBuf[i] = progBuf[i - 1] + step;
    }
    return progBuf[count - 1];
  }

  function load() {
    const s = storage();
    if (!s) return;
    let raw = null;
    try {
      raw = s.getItem(storageKey);
    } catch (err) {
      return;
    }
    if (!raw) return;

    let data = null;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      removeEntry();
      return;
    }
    if (!data || typeof data !== 'object' || data.v !== STORAGE_VERSION) {
      removeEntry();
      return;
    }
    const lap = finite(data.lap, 0);
    const n = data.n | 0;
    const d = data.d;
    if (lap <= 0 || n < MIN_SAMPLES || n > MAX_SAMPLES
      || !Array.isArray(d) || d.length !== n * STRIDE) {
      removeEntry();
      return;
    }
    for (let i = 0; i < d.length; i++) {
      if (typeof d[i] !== 'number' || !Number.isFinite(d[i])) {
        removeEntry();
        return;
      }
    }
    // Times must be strictly ascending or the replay lookup is meaningless.
    for (let i = 1; i < n; i++) {
      if (d[i * STRIDE + O_T] <= d[(i - 1) * STRIDE + O_T]) {
        removeEntry();
        return;
      }
    }

    for (let i = 0; i < d.length; i++) plyBuf[i] = d[i];
    plyCount = n;
    plyLength = fillProgress(plyBuf, plyCount);
    if (trackLength > 0 && plyLength < trackLength * MIN_LAP_COVERAGE) {
      // Recorded on another layout, or truncated. Useless as a ghost.
      plyCount = 0;
      plyLength = 0;
      removeEntry();
      return;
    }
    ghost.recordMs = lap;
    ghost.hasRecord = true;
  }

  // -- recording ----------------------------------------------------------

  ghost.startLap = function startLap() {
    recCount = 0;
    recording = true;
    recOverflow = false;
    nextSampleT = 0;
    deltaSmoothed = null;
  };

  ghost.abortLap = function abortLap() {
    recCount = 0;
    recording = false;
    recOverflow = false;
    nextSampleT = 0;
    deltaSmoothed = null;
  };

  ghost.sample = function sample(ship, lapTimeMs) {
    if (!recording || !ship || recOverflow) return;
    const t = finite(lapTimeMs, -1);
    if (t < 0) return;
    if (recCount > 0) {
      if (t < nextSampleT) return;
      if (t <= recBuf[(recCount - 1) * STRIDE + O_T]) return;
    }
    if (recCount >= MAX_SAMPLES) {
      recOverflow = true;
      return;
    }
    const b = recCount * STRIDE;
    recBuf[b + O_T] = t;
    recBuf[b + O_S] = finite(ship.s, 0);
    recBuf[b + O_X] = finite(ship.x, 0);
    recBuf[b + O_H] = finite(ship.h, 0);
    recBuf[b + O_YAW] = finite(ship.yaw, 0);
    recBuf[b + O_ROLL] = finite(ship.roll, 0);
    recBuf[b + O_PITCH] = finite(ship.pitch, 0);
    recCount++;
    // Rebase after a frame hitch instead of firing a burst of catch-up samples.
    nextSampleT += SAMPLE_MS;
    if (nextSampleT <= t) nextSampleT = t + SAMPLE_MS;
  };

  ghost.commitLap = function commitLap(lapMs) {
    const lap = finite(lapMs, 0);
    const usable = recording && !recOverflow && recCount >= MIN_SAMPLES && lap > 0
      && (ghost.recordMs === null || lap < ghost.recordMs);
    recording = false;
    nextSampleT = 0;
    if (!usable) {
      recCount = 0;
      return false;
    }

    // Prove the recording covers the circuit before touching the ghost that is
    // already on screen: a lap validated by race.js can still be missing its
    // samples (a race started mid lap, a tab that was in the background).
    const cover = fillProgress(recBuf, recCount);
    if (trackLength > 0 && cover < trackLength * MIN_LAP_COVERAGE) {
      recCount = 0;
      fillProgress(plyBuf, plyCount); // put the kept ghost lookup table back
      return false;
    }

    plyBuf.set(recBuf.subarray(0, recCount * STRIDE), 0);
    plyCount = recCount;
    plyLength = cover; // progBuf already holds this recording's table
    recCount = 0;

    ghost.recordMs = lap;
    ghost.hasRecord = true;
    deltaSmoothed = null;
    persist();
    return true;
  };

  // -- replay -------------------------------------------------------------

  ghost.update = function update(dt, lapTimeMs) {
    if (!track || !frame || plyCount < 2) return;
    const t = clamp(finite(lapTimeMs, 0), plyBuf[O_T], plyBuf[(plyCount - 1) * STRIDE + O_T]);
    let i = lastAtMost(plyBuf, O_T, STRIDE, plyCount, t);
    if (i > plyCount - 2) i = plyCount - 2;
    const a = i * STRIDE;
    const b = a + STRIDE;
    const span = plyBuf[b + O_T] - plyBuf[a + O_T];
    const k = span > 0 ? clamp((t - plyBuf[a + O_T]) / span, 0, 1) : 0;

    // The abscissa wraps at the finish line: interpolating the raw values would
    // send the ghost backwards across the whole circuit on that one pair.
    const sA = plyBuf[a + O_S];
    const s = track.wrapS(sA + track.deltaS(sA, plyBuf[b + O_S]) * k);
    const x = plyBuf[a + O_X] + (plyBuf[b + O_X] - plyBuf[a + O_X]) * k;
    const h = plyBuf[a + O_H] + (plyBuf[b + O_H] - plyBuf[a + O_H]) * k;
    const yaw = plyBuf[a + O_YAW] + (plyBuf[b + O_YAW] - plyBuf[a + O_YAW]) * k;
    const roll = plyBuf[a + O_ROLL] + (plyBuf[b + O_ROLL] - plyBuf[a + O_ROLL]) * k;
    const pitch = plyBuf[a + O_PITCH] + (plyBuf[b + O_PITCH] - plyBuf[a + O_PITCH]) * k;

    applyGhostTransform(s, x, h, yaw, roll, pitch);
  };

  /** Same basis convention as ship.js applyTransform. Do not fork it. */
  function applyGhostTransform(s, x, h, yaw, roll, pitch) {
    const f = track.at(s, frame);
    track.toWorld(s, x, h, worldPos);

    const cy = Math.cos(yaw);
    const sy = Math.sin(yaw);
    _fwd.copy(f.tangent).multiplyScalar(cy).addScaledVector(f.right, sy);
    if (_fwd.lengthSq() < 1e-8) _fwd.set(0, 0, -1);
    _fwd.normalize();

    _rgt.crossVectors(_fwd, f.up);
    if (_rgt.lengthSq() < 1e-8) _rgt.crossVectors(_fwd, WORLD_UP);
    _rgt.normalize();

    _back.copy(_fwd).negate();
    _up.crossVectors(_back, _rgt).normalize();

    _basis.makeBasis(_rgt, _up, _back);
    quat.setFromRotationMatrix(_basis);
    _qRoll.setFromAxisAngle(_fwd, roll);
    _qPitch.setFromAxisAngle(_rgt, pitch);
    quat.premultiply(_qRoll).premultiply(_qPitch);

    mesh.position.copy(worldPos);
    mesh.quaternion.copy(quat);
  }

  // -- delta --------------------------------------------------------------

  ghost.deltaMs = function deltaMs(ship, lapTimeMs) {
    if (!ghost.hasRecord || plyCount < MIN_SAMPLES || !ship || trackLength <= 0) return null;
    const t = finite(lapTimeMs, -1);
    if (t < 0) return null;

    // Player progress inside the lap, measured from the abscissa the record
    // started at. Just after the line the craft can still read as being a few
    // metres before it, which wraps to a full lap of progress.
    let p = track.wrapS(finite(ship.s, 0) - plyBuf[O_S]);
    if (t < 2000 && p > trackLength * 0.5) p = 0;
    if (p > plyLength) {
      if (p - plyLength > DELTA_RANGE_SLACK) return null;
      p = plyLength;
    }

    let i = lastAtMost(progBuf, 0, 1, plyCount, p);
    if (i > plyCount - 2) i = plyCount - 2;
    const span = progBuf[i + 1] - progBuf[i];
    const k = span > 1e-4 ? clamp((p - progBuf[i]) / span, 0, 1) : 0;
    const tA = plyBuf[i * STRIDE + O_T];
    const tB = plyBuf[(i + 1) * STRIDE + O_T];
    const ghostTime = tA + (tB - tA) * k;

    const raw = clamp(t - ghostTime, -DELTA_CLAMP_MS, DELTA_CLAMP_MS);
    deltaSmoothed = deltaSmoothed === null
      ? raw
      : deltaSmoothed + (raw - deltaSmoothed) * DELTA_SMOOTH;
    return deltaSmoothed;
  };

  // -- lifecycle ----------------------------------------------------------

  ghost.setVisible = function setVisible(v) {
    wantVisible = !!v;
    mesh.visible = wantVisible && plyCount >= 2;
  };

  ghost.reset = function reset() {
    recCount = 0;
    recording = false;
    recOverflow = false;
    nextSampleT = 0;
    deltaSmoothed = null;
    wantVisible = false;
    mesh.visible = false;
  };

  ghost.clearRecord = function clearRecord() {
    ghost.reset();
    plyCount = 0;
    plyLength = 0;
    ghost.hasRecord = false;
    ghost.recordMs = null;
    removeEntry();
  };

  ghost.dispose = function dispose() {
    mesh.visible = false;
    if (mesh.parent) mesh.parent.remove(mesh);
    disposeGhostMesh(mesh);
  };

  load();
  if (ghost.hasRecord && track && frame) {
    // Park the ghost on its own start sample so the first frame it is shown on
    // is already in place.
    applyGhostTransform(
      plyBuf[O_S], plyBuf[O_X], plyBuf[O_H],
      plyBuf[O_YAW], plyBuf[O_ROLL], plyBuf[O_PITCH],
    );
  } else if (track && frame) {
    applyGhostTransform(finite(track.startS, 0), 0, SHIP.hoverHeight, 0, 0, 0);
  }

  return ghost;
}

// ---------------------------------------------------------------------------
// Ghost look
// ---------------------------------------------------------------------------

/**
 * Turns a freshly built racer into a hologram: cloned materials only, stripped
 * of their maps so the whole craft reads as one flat livery colour, translucent
 * and non writing to the depth buffer, and casting nothing.
 * The source materials belong to nobody else here, so they are disposed on the
 * spot; the materials of the real craft are never touched.
 */
function makeGhostly(mesh, color) {
  const livery = new THREE.Color(color === undefined ? PALETTE.white : color);
  const body = livery.clone().multiplyScalar(0.22);
  const seen = new Map();

  mesh.traverse((node) => {
    if (!node.isMesh) return;
    node.castShadow = false;
    node.receiveShadow = false;
    const src = node.material;
    if (!src) return;
    let ghostMat = seen.get(src);
    if (!ghostMat) {
      ghostMat = src.clone();
      ghostMat.name = 'ghost-' + (src.name || 'mat');
      // Flat livery: no albedo, no normal, no emissive texture.
      if ('map' in ghostMat) ghostMat.map = null;
      if ('normalMap' in ghostMat) ghostMat.normalMap = null;
      if ('emissiveMap' in ghostMat) ghostMat.emissiveMap = null;
      if ('roughnessMap' in ghostMat) ghostMat.roughnessMap = null;
      if ('metalnessMap' in ghostMat) ghostMat.metalnessMap = null;
      if (ghostMat.color) ghostMat.color.copy(body);
      if (ghostMat.emissive) ghostMat.emissive.copy(livery);
      if ('emissiveIntensity' in ghostMat) ghostMat.emissiveIntensity = 0.85;
      if ('metalness' in ghostMat) ghostMat.metalness = 0.1;
      if ('roughness' in ghostMat) ghostMat.roughness = 0.65;
      if ('envMapIntensity' in ghostMat) ghostMat.envMapIntensity = 0.5;
      ghostMat.transparent = true;
      ghostMat.opacity = 0.34;
      ghostMat.depthWrite = false;
      ghostMat.fog = true;
      seen.set(src, ghostMat);
      src.dispose();
    }
    node.material = ghostMat;
    node.renderOrder = 2;
  });

  // The build time materials this mesh advertised are gone: point the hook at
  // the clones so nothing can pulse a disposed material.
  mesh.userData.glowMaterials = Array.from(seen.values());
  mesh.userData.isGhost = true;
}

/** Frees the geometries and the cloned materials of the ghost mesh. */
function disposeGhostMesh(mesh) {
  if (!mesh) return;
  const done = new Set();
  mesh.traverse((node) => {
    if (!node.isMesh) return;
    if (node.geometry) node.geometry.dispose();
    const mat = node.material;
    if (mat && !done.has(mat)) {
      done.add(mat);
      mat.dispose();
    }
  });
}
