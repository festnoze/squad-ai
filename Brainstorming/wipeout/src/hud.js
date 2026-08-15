/**
 * VELOCITRON - heads up display.
 *
 * Pure DOM plus two 2D canvases (#gauge and #minimap). No three.js, no import:
 * the HUD must keep working even while the rest of the game is being rewritten.
 *
 * Performance rules honoured here:
 *  - every element reference is resolved once at creation,
 *  - every field remembers the last value written and skips the DOM otherwise
 *    (this code runs 60 times per second),
 *  - the static parts of both canvases are baked into offscreen canvases and
 *    only blitted per frame,
 *  - no array/object allocation in the per-frame paths.
 *
 * Element ids are the ones declared in index.html. If one is missing (index.html
 * edited down), it is created here rather than crashing.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const NEON = {
  cyan: '#22e0ff',
  magenta: '#ff2bd6',
  red: '#ff3b30',
  amber: '#ffb020',
  white: '#dff6ff',
};

const DEG = Math.PI / 180;
const ARC_START = 150 * DEG; // canvas angles: 0 = +x, positive = clockwise
const ARC_SWEEP = 240 * DEG;
// Top of the dial, km/h. The needle and the graduations are both driven by
// kph / GAUGE_TOP_KPH, so a printed number always sits under the needle. The
// value is the boosted top speed (SHIP.boostMaxSpeed in m/s times 3.6, about
// 705 km/h) rounded up to the next hundred. It stays a literal because the HUD
// imports nothing by contract, and a fixed scale is what keeps the dial stable.
const GAUGE_TOP_KPH = 800;
// Speed at which the danger sector starts, km/h: 90 percent of the unboosted
// top speed (~533 km/h), which is where the readout used to turn red.
const RED_ZONE_KPH = 480;
const RED_ZONE = RED_ZONE_KPH / GAUGE_TOP_KPH; // same speed, new scale
// Ratio (speed / max speed, as fed to setSpeed) above which the digital
// readout turns hot. Unrelated to the dial scale.
const HOT_RATIO = 0.9;
const GAUGE_SEGMENTS = 72;
// Steps of needle travel worth a repaint. Below one step the dial is visually
// identical, so the whole canvas pass is skipped.
const GAUGE_QUANT = 200;
// Angular slack kept before the arc start so the baked round cap and its glow
// survive the reveal wedge.
const GAUGE_CLIP_PAD = 0.35;
const TOAST_LIFE = 2600; // ms
const TOAST_MAX = 4;
const NO_TIME = '--:--.---';
const NO_VALUE = -1; // cached "nothing written yet / no time" marker

// Gauge colour ramp: cyan -> magenta -> red, baked once as css colour strings.
const RAMP = buildRamp();

// ---------------------------------------------------------------------------
// Small helpers (module scope, allocation free at call time where it matters)
// ---------------------------------------------------------------------------
function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

function mixChannel(a, b, t) {
  return Math.round(a + (b - a) * t);
}

function rgbString(r, g, b) {
  return 'rgb(' + r + ',' + g + ',' + b + ')';
}

function buildRamp() {
  // cyan 34,224,255 -> magenta 255,43,214 -> red 255,59,48
  const out = new Array(GAUGE_SEGMENTS + 1);
  for (let i = 0; i <= GAUGE_SEGMENTS; i++) {
    const t = i / GAUGE_SEGMENTS;
    let r;
    let g;
    let b;
    if (t <= RED_ZONE) {
      const k = t / RED_ZONE;
      r = mixChannel(34, 255, k);
      g = mixChannel(224, 43, k);
      b = mixChannel(255, 214, k);
    } else {
      const k = (t - RED_ZONE) / (1 - RED_ZONE);
      r = 255;
      g = mixChannel(43, 59, k);
      b = mixChannel(214, 48, k);
    }
    out[i] = rgbString(r, g, b);
  }
  return out;
}

/** Accepts 0x22e0ff, '#22e0ff' or 'cyan'. Cached so per-frame calls are free. */
const colorCache = new Map();
function cssColor(value) {
  if (typeof value === 'string') return value;
  if (typeof value !== 'number' || !isFinite(value)) return NEON.cyan;
  const key = value | 0;
  let hit = colorCache.get(key);
  if (hit === undefined) {
    hit = '#' + (key >>> 0).toString(16).padStart(6, '0').slice(-6);
    colorCache.set(key, hit);
  }
  return hit;
}

function formatTime(ms) {
  if (ms === null || ms === undefined || typeof ms !== 'number' || !isFinite(ms)) return NO_TIME;
  let v = Math.max(0, Math.round(ms));
  const m = Math.floor(v / 60000);
  v -= m * 60000;
  const s = Math.floor(v / 1000);
  v -= s * 1000;
  return m + ':' + (s < 10 ? '0' : '') + s + '.' + (v < 10 ? '00' : v < 100 ? '0' : '') + v;
}

function formatDelta(ms) {
  const sign = ms >= 0 ? '+' : '-';
  const v = Math.abs(ms) / 1000;
  return sign + (v < 10 ? v.toFixed(3) : v.toFixed(2));
}

function formatGap(gap) {
  if (typeof gap === 'string') return gap;
  if (typeof gap !== 'number' || !isFinite(gap) || gap <= 0.001) return '--';
  return '+' + (gap < 10 ? gap.toFixed(2) : gap.toFixed(1));
}

/** Writes textContent only when it actually changed. */
function setText(node, cache, key, value) {
  if (cache[key] === value) return;
  cache[key] = value;
  node.textContent = value;
}

/** Restarts a css animation driven by a class. */
function retrigger(node, cls) {
  node.classList.remove(cls);
  void node.offsetWidth; // force reflow so the animation replays
  node.classList.add(cls);
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------
export function createHUD(track) {
  const app = document.getElementById('app') || document.body;
  const root = ensure('hud', 'div', app, 'hidden');

  const el = {
    vignette: ensure('fx-vignette', 'div', root),
    hit: ensure('fx-hit', 'div', root),
    boostFx: ensure('fx-boost', 'div', root),
    gauge: ensureCanvas('gauge', root, 260),
    speedValue: ensure('speed-value', 'span', root),
    shieldFill: ensure('shield-fill', 'div', root),
    shieldNum: ensure('shield-num', 'span', root),
    boostFill: ensure('boost-fill', 'div', root),
    boostNum: ensure('boost-num', 'span', root),
    boostReady: ensure('boost-ready', 'div', root),
    lapValue: ensure('lap-value', 'b', root),
    lapTotal: ensure('lap-total', 'span', root),
    posValue: ensure('pos-value', 'b', root),
    posTotal: ensure('pos-total', 'span', root),
    timeCurrent: ensure('time-current', 'b', root),
    timeLast: ensure('time-last', 'b', root),
    timeBest: ensure('time-best', 'b', root),
    timeDelta: ensure('time-delta', 'div', root),
    minimap: ensureCanvas('minimap', root, 220),
    standings: ensure('standings', 'ol', root),
    countdown: ensure('countdown', 'div', root),
    banner: ensure('banner', 'div', root),
    bannerTitle: ensure('banner-title', 'span', document.getElementById('banner') || root),
    bannerSub: ensure('banner-sub', 'span', document.getElementById('banner') || root),
    toasts: ensure('toasts', 'div', root),
    resultsBody: ensure('results-body', 'tbody', document.getElementById('results-table') || app),
    resultsTitle: document.getElementById('results-title'),
    resultsSub: document.getElementById('results-sub'),
  };

  const gaugeCtx = el.gauge.getContext('2d');
  const mapCtx = el.minimap.getContext('2d');
  const gaugeBase = document.createElement('canvas');
  const gaugeBaseCtx = gaugeBase.getContext('2d');
  const gaugeArc = document.createElement('canvas');
  const gaugeArcCtx = gaugeArc.getContext('2d');
  const mapBase = document.createElement('canvas');
  const mapBaseCtx = mapBase.getContext('2d');

  // Cached last written values, one entry per field.
  const cache = {
    speed: -1,
    shield: -1,
    shieldNum: -1,
    shieldState: '',
    boost: -1,
    boostNum: -1,
    boostReady: null,
    lap: '',
    lapTotal: '',
    pos: '',
    posTotal: '',
    posClass: '',
    // Lap times and delta are cached as numbers: the string is only built when
    // the value that is actually displayed moves.
    current: -2,
    last: -2,
    best: -2,
    delta: 'none',
    deltaClass: '',
    countdown: null,
    vignette: -1,
    vignetteHot: false,
  };

  // Gauge state.
  const gauge = {
    size: 0,
    dpr: 0,
    ratio: 0,
    target: 0,
    baseKey: '',
    arcKey: '',
    drawnQ: -1, // quantised ratio of the last painted frame
    dirty: true,
  };

  // Minimap state.
  const map = {
    size: 0,
    dpr: 0,
    ready: false,
  };

  const standingRows = [];
  const toastTimers = [];
  let bannerTimer = 0;

  // -------------------------------------------------------------------------
  // Canvas sizing
  // -------------------------------------------------------------------------
  function deviceRatio() {
    const dpr = window.devicePixelRatio || 1;
    return dpr > 2 ? 2 : dpr < 1 ? 1 : dpr;
  }

  function syncGauge() {
    const dpr = deviceRatio();
    const size = el.gauge.clientWidth || parseInt(el.gauge.getAttribute('width'), 10) || 260;
    if (size === gauge.size && dpr === gauge.dpr) return false;
    gauge.size = size;
    gauge.dpr = dpr;
    el.gauge.width = Math.round(size * dpr);
    el.gauge.height = Math.round(size * dpr);
    gaugeBase.width = el.gauge.width;
    gaugeBase.height = el.gauge.height;
    gaugeArc.width = el.gauge.width;
    gaugeArc.height = el.gauge.height;
    gauge.baseKey = '';
    gauge.arcKey = '';
    gauge.drawnQ = -1;
    gauge.dirty = true;
    return true;
  }

  function syncMap() {
    const dpr = deviceRatio();
    const size = el.minimap.clientWidth || parseInt(el.minimap.getAttribute('width'), 10) || 220;
    if (size === map.size && dpr === map.dpr) return false;
    map.size = size;
    map.dpr = dpr;
    el.minimap.width = Math.round(size * dpr);
    el.minimap.height = Math.round(size * dpr);
    mapBase.width = el.minimap.width;
    mapBase.height = el.minimap.height;
    buildMinimapBase();
    return true;
  }

  // -------------------------------------------------------------------------
  // Gauge
  // -------------------------------------------------------------------------
  function buildGaugeBase() {
    const key = gauge.size + '|' + gauge.dpr;
    if (key === gauge.baseKey) return;
    gauge.baseKey = key;

    const c = gaugeBaseCtx;
    const L = gauge.size;
    const cx = L * 0.5;
    const cy = L * 0.54;
    const rOuter = L * 0.44;
    const rTrack = L * 0.375;

    c.setTransform(gauge.dpr, 0, 0, gauge.dpr, 0, 0);
    c.clearRect(0, 0, L, L);
    c.lineCap = 'butt';

    // Dark backing disc so the readout stays legible over a bright scene.
    c.beginPath();
    c.arc(cx, cy, rOuter, 0, Math.PI * 2);
    c.fillStyle = 'rgba(3,5,12,0.72)';
    c.fill();

    // Outer hairline ring.
    c.beginPath();
    c.arc(cx, cy, rOuter - 1, ARC_START, ARC_START + ARC_SWEEP);
    c.strokeStyle = 'rgba(34,224,255,0.22)';
    c.lineWidth = 1;
    c.stroke();

    // Empty gauge channel.
    c.beginPath();
    c.arc(cx, cy, rTrack, ARC_START, ARC_START + ARC_SWEEP);
    c.strokeStyle = 'rgba(120,190,230,0.14)';
    c.lineWidth = L * 0.075;
    c.stroke();

    // Danger sector past 90 percent.
    c.beginPath();
    c.arc(cx, cy, rTrack, ARC_START + ARC_SWEEP * RED_ZONE, ARC_START + ARC_SWEEP);
    c.strokeStyle = 'rgba(255,59,48,0.3)';
    c.lineWidth = L * 0.075;
    c.stroke();

    // Ticks: minor every 20 kph, major every 100 kph with a label.
    const rInner = rTrack - L * 0.045;
    const rMajor = rTrack - L * 0.115;
    const rLabel = rTrack - L * 0.165;
    c.font = 'bold ' + Math.round(L * 0.062) + 'px "Arial Narrow", system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    for (let v = 0; v <= GAUGE_TOP_KPH; v += 20) {
      const t = v / GAUGE_TOP_KPH;
      const a = ARC_START + ARC_SWEEP * t;
      const cos = Math.cos(a);
      const sin = Math.sin(a);
      const major = v % 100 === 0;
      const r0 = major ? rMajor : rInner;
      const hot = t >= RED_ZONE;
      c.beginPath();
      c.moveTo(cx + cos * r0, cy + sin * r0);
      c.lineTo(cx + cos * (rTrack + L * 0.045), cy + sin * (rTrack + L * 0.045));
      c.strokeStyle = hot
        ? 'rgba(255,90,80,' + (major ? 0.95 : 0.5) + ')'
        : 'rgba(200,240,255,' + (major ? 0.85 : 0.32) + ')';
      c.lineWidth = major ? 2.2 : 1;
      c.stroke();
      if (major) {
        c.fillStyle = hot ? 'rgba(255,120,110,0.95)' : 'rgba(190,232,255,0.8)';
        c.fillText(String(v), cx + cos * rLabel, cy + sin * rLabel);
      }
    }

    // Inner hairline that frames the digital readout sitting in the opening.
    c.beginPath();
    c.arc(cx, cy, rLabel - L * 0.03, ARC_START, ARC_START + ARC_SWEEP);
    c.strokeStyle = 'rgba(34,224,255,0.16)';
    c.lineWidth = 1;
    c.stroke();
  }

  /**
   * Bakes the whole 240 degree ramp, glow included, into an offscreen canvas.
   * The per frame pass then only has to clip it to a wedge, which replaces a
   * shadow blurred stroke plus up to GAUGE_SEGMENTS individual arc strokes.
   */
  function buildGaugeArc() {
    const key = gauge.size + '|' + gauge.dpr;
    if (key === gauge.arcKey) return;
    gauge.arcKey = key;

    const L = gauge.size;
    const dpr = gauge.dpr;
    const cx = L * 0.5;
    const cy = L * 0.54;
    const rTrack = L * 0.375;
    const width = L * 0.062;
    const step = ARC_SWEEP / GAUGE_SEGMENTS;
    const arcEnd = ARC_START + ARC_SWEEP;

    // Crisp ramp, drawn once at full opacity in a scratch canvas: it doubles as
    // the sharp layer and as the source of the glow underneath it.
    const tmp = document.createElement('canvas');
    tmp.width = gaugeArc.width;
    tmp.height = gaugeArc.height;
    const t2 = tmp.getContext('2d');
    t2.setTransform(dpr, 0, 0, dpr, 0, 0);
    t2.lineWidth = width;
    t2.lineCap = 'butt';
    for (let i = 0; i < GAUGE_SEGMENTS; i++) {
      const a0 = ARC_START + step * i;
      const a1 = Math.min(arcEnd, a0 + step + 0.004);
      if (a1 <= a0) break;
      t2.beginPath();
      t2.arc(cx, cy, rTrack, a0, a1);
      t2.strokeStyle = RAMP[i];
      t2.stroke();
    }

    const c = gaugeArcCtx;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, gaugeArc.width, gaugeArc.height);

    // Canvas filter lengths ignore the transform, so the blur is in backing
    // store pixels. shadowBlur uses half that radius, hence the 0.055.
    let blurred = false;
    c.save();
    try {
      c.filter = 'blur(' + (L * 0.055 * dpr).toFixed(2) + 'px)';
      blurred = c.filter !== 'none';
    } catch (e) {
      blurred = false;
    }
    if (blurred) {
      c.globalAlpha = 0.55;
      c.drawImage(tmp, 0, 0);
    }
    c.restore();

    if (!blurred) {
      // No canvas filter: fall back to one shadowed stroke for the halo.
      c.save();
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      c.globalAlpha = 0.55;
      c.shadowColor = RAMP[GAUGE_SEGMENTS >> 1];
      c.shadowBlur = L * 0.11;
      c.strokeStyle = RAMP[GAUGE_SEGMENTS >> 1];
      c.lineWidth = width;
      c.lineCap = 'round';
      c.beginPath();
      c.arc(cx, cy, rTrack, ARC_START, arcEnd);
      c.stroke();
      c.restore();
      c.setTransform(1, 0, 0, 1, 0, 0);
    }

    c.drawImage(tmp, 0, 0);

    // Round cap at the low end, left behind by the old glow pass line cap.
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.save();
    c.globalAlpha = 0.55;
    c.strokeStyle = RAMP[0];
    c.lineWidth = width;
    c.lineCap = 'round';
    c.beginPath();
    c.arc(cx, cy, rTrack, ARC_START, ARC_START + 0.002);
    c.stroke();
    c.restore();
  }

  function drawGauge() {
    const c = gaugeCtx;
    const L = gauge.size;
    if (L <= 0) return;

    const t = clamp01(gauge.ratio);
    // Nothing the eye can see moved since the last paint: skip both canvases.
    const q = Math.round(t * GAUGE_QUANT);
    if (q === gauge.drawnQ) return;
    gauge.drawnQ = q;

    buildGaugeBase();
    buildGaugeArc();

    const dpr = gauge.dpr;
    const cx = L * 0.5;
    const cy = L * 0.54;
    const rTrack = L * 0.375;
    const end = ARC_START + ARC_SWEEP * t;

    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, el.gauge.width, el.gauge.height);
    c.drawImage(gaugeBase, 0, 0);

    if (t > 0.001) {
      // Reveal the baked ramp up to the needle with a single wedge clip.
      c.save();
      c.beginPath();
      c.moveTo(cx * dpr, cy * dpr);
      c.arc(cx * dpr, cy * dpr, L * dpr, ARC_START - GAUGE_CLIP_PAD, end);
      c.closePath();
      c.clip();
      c.drawImage(gaugeArc, 0, 0);
      c.restore();
    }

    c.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (t > 0.001) {
      // Round tip, the other half of the old glow pass line cap.
      c.save();
      c.globalAlpha = 0.55;
      c.strokeStyle = RAMP[Math.min(GAUGE_SEGMENTS, Math.round(t * GAUGE_SEGMENTS))];
      c.lineWidth = L * 0.062;
      c.lineCap = 'round';
      c.beginPath();
      c.arc(cx, cy, rTrack, end - 0.002, end);
      c.stroke();
      c.restore();
    }

    // Needle.
    const a = ARC_START + ARC_SWEEP * t;
    const cos = Math.cos(a);
    const sin = Math.sin(a);
    const rN = rTrack + L * 0.02;
    c.save();
    c.shadowColor = t > RED_ZONE ? NEON.red : NEON.white;
    c.shadowBlur = L * 0.06;
    c.strokeStyle = t > RED_ZONE ? '#ffd2ce' : '#eefaff';
    c.lineWidth = Math.max(2, L * 0.013);
    c.lineCap = 'round';
    c.beginPath();
    c.moveTo(cx - cos * L * 0.055, cy - sin * L * 0.055);
    c.lineTo(cx + cos * rN, cy + sin * rN);
    c.stroke();
    c.restore();

    // Hub.
    c.beginPath();
    c.arc(cx, cy, L * 0.035, 0, Math.PI * 2);
    c.fillStyle = '#070a14';
    c.fill();
    c.strokeStyle = 'rgba(34,224,255,0.7)';
    c.lineWidth = 1.5;
    c.stroke();
  }

  // -------------------------------------------------------------------------
  // Minimap
  // -------------------------------------------------------------------------
  function buildMinimapBase() {
    map.ready = false;
    const c = mapBaseCtx;
    const L = map.size;
    if (L <= 0) return;
    c.setTransform(map.dpr, 0, 0, map.dpr, 0, 0);
    c.clearRect(0, 0, L, L);

    // Darkened backing plus corner brackets, readable over a bright scene.
    c.fillStyle = 'rgba(3,5,12,0.62)';
    c.fillRect(0, 0, L, L);
    c.strokeStyle = 'rgba(34,224,255,0.3)';
    c.lineWidth = 1;
    const b = L * 0.14;
    const inset = 2;
    c.beginPath();
    c.moveTo(inset, b); c.lineTo(inset, inset); c.lineTo(b, inset);
    c.moveTo(L - b, inset); c.lineTo(L - inset, inset); c.lineTo(L - inset, b);
    c.moveTo(L - inset, L - b); c.lineTo(L - inset, L - inset); c.lineTo(L - b, L - inset);
    c.moveTo(b, L - inset); c.lineTo(inset, L - inset); c.lineTo(inset, L - b);
    c.stroke();

    const pts = track && Array.isArray(track.outlinePoints) ? track.outlinePoints : null;
    if (!pts || pts.length < 3) return;

    const pad = L * 0.14;
    const scale = (L - pad * 2) * 0.5;
    const cx = L * 0.5;
    const cy = L * 0.5;

    c.beginPath();
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      const px = cx + p.x * scale;
      const py = cy - p.y * scale;
      if (i === 0) c.moveTo(px, py);
      else c.lineTo(px, py);
    }
    c.closePath();

    c.lineJoin = 'round';
    c.lineCap = 'round';
    // Wide dark casing, then two glowing passes.
    c.strokeStyle = 'rgba(4,8,18,0.95)';
    c.lineWidth = Math.max(5, L * 0.045);
    c.stroke();
    c.save();
    c.shadowColor = NEON.cyan;
    c.shadowBlur = L * 0.05;
    c.strokeStyle = 'rgba(34,224,255,0.35)';
    c.lineWidth = Math.max(3, L * 0.028);
    c.stroke();
    c.strokeStyle = 'rgba(190,245,255,0.95)';
    c.lineWidth = Math.max(1.4, L * 0.012);
    c.stroke();
    c.restore();

    // Start line marker: a tick across the ribbon at track.startS.
    const n = pts.length;
    let idx = 0;
    if (track && isFinite(track.startS) && isFinite(track.length) && track.length > 0) {
      idx = Math.round((track.startS / track.length) * n) % n;
      if (idx < 0) idx += n;
    }
    const a = pts[idx];
    const bnext = pts[(idx + 1) % n];
    let dx = bnext.x - a.x;
    let dy = bnext.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    dx /= len;
    dy /= len;
    const mx = cx + a.x * scale;
    const my = cy - a.y * scale;
    const half = Math.max(4, L * 0.035);
    c.save();
    c.shadowColor = NEON.magenta;
    c.shadowBlur = L * 0.05;
    c.strokeStyle = NEON.magenta;
    c.lineWidth = Math.max(2, L * 0.016);
    c.beginPath();
    c.moveTo(mx + dy * half, my + dx * half);
    c.lineTo(mx - dy * half, my - dx * half);
    c.stroke();
    c.restore();

    map.ready = true;
  }

  // -------------------------------------------------------------------------
  // Standings rows (pooled)
  // -------------------------------------------------------------------------
  function standingRow() {
    const li = document.createElement('li');
    li.className = 'standing';
    const pos = document.createElement('span');
    pos.className = 'st-pos';
    const dot = document.createElement('i');
    dot.className = 'st-dot';
    const name = document.createElement('span');
    name.className = 'st-name';
    const gap = document.createElement('span');
    gap.className = 'st-gap';
    li.appendChild(pos);
    li.appendChild(dot);
    li.appendChild(name);
    li.appendChild(gap);
    li._pos = pos;
    li._dot = dot;
    li._name = name;
    li._gap = gap;
    li._cPos = '';
    li._cName = '';
    li._cGap = '';
    li._cColor = '';
    li._cPlayer = null;
    return li;
  }

  /**
   * Writes a lap time, formatting only when the displayed millisecond moved.
   * NO_VALUE stands for "no time yet", so the string is built at most once per
   * change instead of once per frame.
   */
  function writeTime(node, key, ms) {
    const v = ms === null || ms === undefined || typeof ms !== 'number' || !isFinite(ms)
      ? NO_VALUE
      : Math.max(0, Math.round(ms));
    if (cache[key] === v) return;
    cache[key] = v;
    node.textContent = v === NO_VALUE ? NO_TIME : formatTime(v);
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------
  const hud = {
    show() {
      root.classList.remove('hidden');
      syncGauge();
      syncMap();
      gauge.drawnQ = -1;
      gauge.dirty = true;
    },

    hide() {
      root.classList.add('hidden');
      hud.setCountdown(null);
      el.banner.classList.remove('show');
    },

    setSpeed(kph, ratio01) {
      const v = Math.max(0, Math.round(kph || 0));
      if (cache.speed !== v) {
        cache.speed = v;
        el.speedValue.textContent = String(v);
        el.speedValue.classList.toggle('hot', ratio01 > HOT_RATIO);
      }
      // The needle reads the same scale as the printed graduations: the dial
      // top is fixed, so the value under the needle is the value displayed.
      // ratio01 only drives the hot readout above.
      gauge.target = clamp01(v / GAUGE_TOP_KPH);
      const d = gauge.target - gauge.ratio;
      if (Math.abs(d) < 0.0006) {
        gauge.ratio = gauge.target;
        if (!gauge.dirty) return;
      } else {
        gauge.ratio += d * 0.35;
        gauge.dirty = true;
      }
      if (gauge.size === 0) syncGauge();
      drawGauge();
      gauge.dirty = Math.abs(gauge.target - gauge.ratio) > 0.0006;
    },

    setShield(ratio01) {
      const r = clamp01(ratio01 || 0);
      const pct = Math.round(r * 1000) / 10;
      if (cache.shield !== pct) {
        cache.shield = pct;
        el.shieldFill.style.width = pct + '%';
      }
      const num = Math.round(r * 100);
      if (cache.shieldNum !== num) {
        cache.shieldNum = num;
        el.shieldNum.textContent = String(num);
      }
      const state = r < 0.2 ? 'critical' : r < 0.45 ? 'warn' : '';
      if (cache.shieldState !== state) {
        el.shieldFill.classList.toggle('critical', state === 'critical');
        el.shieldFill.classList.toggle('warn', state === 'warn');
        cache.shieldState = state;
      }
    },

    setBoost(ratio01, ready) {
      const r = clamp01(ratio01 || 0);
      const pct = Math.round(r * 1000) / 10;
      if (cache.boost !== pct) {
        cache.boost = pct;
        el.boostFill.style.width = pct + '%';
      }
      const num = Math.round(r * 100);
      if (cache.boostNum !== num) {
        cache.boostNum = num;
        el.boostNum.textContent = String(num);
      }
      const on = !!ready;
      if (cache.boostReady !== on) {
        cache.boostReady = on;
        el.boostReady.classList.toggle('on', on);
      }
    },

    setLap(lap, total) {
      setText(el.lapValue, cache, 'lap', String(lap));
      setText(el.lapTotal, cache, 'lapTotal', String(total));
    },

    setPosition(pos, total) {
      setText(el.posValue, cache, 'pos', String(pos));
      setText(el.posTotal, cache, 'posTotal', String(total));
      const cls = pos === 1 ? 'lead' : pos === total ? 'last' : '';
      if (cache.posClass !== cls) {
        el.posValue.classList.toggle('lead', cls === 'lead');
        el.posValue.classList.toggle('last', cls === 'last');
        cache.posClass = cls;
      }
    },

    setTimes(times) {
      const t = times || null;
      writeTime(el.timeCurrent, 'current', t ? t.current : null);
      writeTime(el.timeLast, 'last', t ? t.last : null);
      writeTime(el.timeBest, 'best', t ? t.best : null);
    },

    setDelta(ms) {
      const valid = !(ms === null || ms === undefined || !isFinite(ms));
      // Quantised to the precision the formatter shows: 1 ms, or 10 ms past 10 s.
      const key = !valid ? null : Math.abs(ms) < 10000 ? Math.round(ms) : Math.round(ms / 10) * 10;
      if (cache.delta !== key) {
        cache.delta = key;
        el.timeDelta.textContent = valid ? formatDelta(ms) : '';
      }
      const cls = !valid ? '' : ms >= 0 ? 'slow' : 'fast';
      if (cache.deltaClass !== cls) {
        el.timeDelta.classList.toggle('slow', cls === 'slow');
        el.timeDelta.classList.toggle('fast', cls === 'fast');
        cache.deltaClass = cls;
      }
    },

    setStandings(rows) {
      const list = rows || [];
      while (standingRows.length > list.length) {
        const li = standingRows.pop();
        el.standings.removeChild(li);
      }
      while (standingRows.length < list.length) {
        const li = standingRow();
        standingRows.push(li);
        el.standings.appendChild(li);
      }
      for (let i = 0; i < list.length; i++) {
        const r = list[i];
        const li = standingRows[i];
        const pos = String(r.pos !== undefined ? r.pos : i + 1);
        if (li._cPos !== pos) {
          li._cPos = pos;
          li._pos.textContent = pos;
        }
        const name = String(r.name || '');
        if (li._cName !== name) {
          li._cName = name;
          li._name.textContent = name;
        }
        const gap = formatGap(r.gap);
        if (li._cGap !== gap) {
          li._cGap = gap;
          li._gap.textContent = gap;
        }
        const color = cssColor(r.color);
        if (li._cColor !== color) {
          li._cColor = color;
          li._dot.style.background = color;
          li._dot.style.boxShadow = '0 0 8px ' + color;
        }
        const player = !!r.isPlayer;
        if (li._cPlayer !== player) {
          li._cPlayer = player;
          li.classList.toggle('me', player);
        }
      }
    },

    setMinimap(dots) {
      const L = map.size || (syncMap(), map.size);
      if (L <= 0) return;
      const c = mapCtx;
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.clearRect(0, 0, el.minimap.width, el.minimap.height);
      c.drawImage(mapBase, 0, 0);
      if (!dots || dots.length === 0) return;
      c.setTransform(map.dpr, 0, 0, map.dpr, 0, 0);

      const pad = L * 0.14;
      const scale = (L - pad * 2) * 0.5;
      const cx = L * 0.5;
      const cy = L * 0.5;
      const pulse = 1 + 0.18 * Math.sin(performance.now() * 0.006);

      for (let i = 0; i < dots.length; i++) {
        const d = dots[i];
        const px = cx + (d.u || 0) * scale;
        const py = cy - (d.v || 0) * scale;
        const col = cssColor(d.color);
        const r = d.isPlayer ? L * 0.028 * pulse : L * 0.018;
        if (d.isPlayer) {
          c.beginPath();
          c.arc(px, py, r * 2.1, 0, Math.PI * 2);
          c.fillStyle = 'rgba(223,246,255,0.14)';
          c.fill();
        }
        c.save();
        c.shadowColor = col;
        c.shadowBlur = d.isPlayer ? L * 0.05 : L * 0.025;
        c.beginPath();
        c.arc(px, py, r, 0, Math.PI * 2);
        c.fillStyle = col;
        c.fill();
        c.restore();
        if (d.isPlayer) {
          c.beginPath();
          c.arc(px, py, r, 0, Math.PI * 2);
          c.strokeStyle = '#ffffff';
          c.lineWidth = 1.5;
          c.stroke();
        }
      }
    },

    setCountdown(text) {
      const value = text === null || text === undefined ? null : String(text);
      if (cache.countdown === value) return;
      cache.countdown = value;
      if (value === null) {
        el.countdown.classList.remove('show');
        el.countdown.textContent = '';
        return;
      }
      el.countdown.textContent = value;
      el.countdown.classList.toggle('go', value === 'GO');
      retrigger(el.countdown, 'show');
    },

    banner(title, sub, ms) {
      el.bannerTitle.textContent = title === undefined || title === null ? '' : String(title);
      el.bannerSub.textContent = sub === undefined || sub === null ? '' : String(sub);
      retrigger(el.banner, 'show');
      if (bannerTimer) clearTimeout(bannerTimer);
      bannerTimer = setTimeout(() => {
        el.banner.classList.remove('show');
        bannerTimer = 0;
      }, Math.max(200, ms || 2000));
    },

    toast(text) {
      const node = document.createElement('div');
      node.className = 'toast';
      node.textContent = String(text);
      el.toasts.appendChild(node);
      while (el.toasts.childElementCount > TOAST_MAX) {
        el.toasts.removeChild(el.toasts.firstElementChild);
        const dead = toastTimers.shift();
        if (dead) clearTimeout(dead);
      }
      const timer = setTimeout(() => {
        if (node.parentNode === el.toasts) el.toasts.removeChild(node);
        const at = toastTimers.indexOf(timer);
        if (at >= 0) toastTimers.splice(at, 1);
      }, TOAST_LIFE);
      toastTimers.push(timer);
    },

    hit(intensity01) {
      const i = clamp01(intensity01 === undefined ? 1 : intensity01);
      if (i <= 0.02) return;
      el.hit.style.setProperty('--hit', (0.25 + i * 0.75).toFixed(3));
      retrigger(el.hit, 'on');
    },

    boostFlash() {
      retrigger(el.boostFx, 'on');
    },

    speedFx(ratio01) {
      const r = clamp01(ratio01 || 0);
      const q = Math.round(r * 50) / 50;
      if (cache.vignette !== q) {
        cache.vignette = q;
        el.vignette.style.opacity = q.toFixed(2);
      }
      const hot = r > 0.78;
      if (cache.vignetteHot !== hot) {
        cache.vignetteHot = hot;
        el.vignette.classList.toggle('hot', hot);
      }
    },

    results(rows, title, sub) {
      if (title !== undefined && title !== null && el.resultsTitle) el.resultsTitle.textContent = String(title);
      if (sub !== undefined && sub !== null && el.resultsSub) el.resultsSub.textContent = String(sub);
      const body = el.resultsBody;
      while (body.firstChild) body.removeChild(body.firstChild);
      const list = rows || [];
      for (let i = 0; i < list.length; i++) {
        const r = list[i];
        const tr = document.createElement('tr');
        if (r.isPlayer) tr.className = 'me';
        const cPos = document.createElement('td');
        cPos.className = 'r-pos';
        cPos.textContent = String(r.pos !== undefined ? r.pos : i + 1);
        const cName = document.createElement('td');
        cName.className = 'r-name';
        const dot = document.createElement('i');
        dot.className = 'st-dot';
        const col = cssColor(r.color);
        dot.style.background = col;
        dot.style.boxShadow = '0 0 8px ' + col;
        cName.appendChild(dot);
        cName.appendChild(document.createTextNode(String(r.name || '')));
        const cTime = document.createElement('td');
        cTime.className = 'r-time';
        cTime.textContent = typeof r.time === 'string' ? r.time : formatTime(r.time);
        const cBest = document.createElement('td');
        cBest.className = 'r-best';
        cBest.textContent = typeof r.best === 'string' ? r.best : formatTime(r.best);
        tr.appendChild(cPos);
        tr.appendChild(cName);
        tr.appendChild(cTime);
        tr.appendChild(cBest);
        body.appendChild(tr);
      }
    },

    formatTime,

    /** Recomputes both canvas backing stores. Called on window resize. */
    resize() {
      syncGauge();
      syncMap();
      gauge.drawnQ = -1;
      gauge.dirty = true;
    },

    dispose() {
      window.removeEventListener('resize', onResize);
      if (bannerTimer) clearTimeout(bannerTimer);
      for (let i = 0; i < toastTimers.length; i++) clearTimeout(toastTimers[i]);
      toastTimers.length = 0;
      while (el.toasts.firstChild) el.toasts.removeChild(el.toasts.firstChild);
      while (el.standings.firstChild) el.standings.removeChild(el.standings.firstChild);
      standingRows.length = 0;
      root.classList.add('hidden');
    },
  };

  function onResize() {
    hud.resize();
  }
  window.addEventListener('resize', onResize);

  // First layout pass. The HUD may still be hidden here, in which case
  // clientWidth is 0 and the attribute size is used until show() runs.
  syncGauge();
  syncMap();
  drawGauge();
  hud.setMinimap(null);

  return hud;
}

// ---------------------------------------------------------------------------
// Element resolution: use index.html when present, build a stand-in otherwise.
// ---------------------------------------------------------------------------
function ensure(id, tag, parent, cls) {
  let node = document.getElementById(id);
  if (node) return node;
  node = document.createElement(tag);
  node.id = id;
  if (cls) node.className = cls;
  (parent || document.body).appendChild(node);
  return node;
}

function ensureCanvas(id, parent, size) {
  let node = document.getElementById(id);
  if (node && node.tagName === 'CANVAS') return node;
  node = document.createElement('canvas');
  node.id = id;
  node.width = size;
  node.height = size;
  (parent || document.body).appendChild(node);
  return node;
}
