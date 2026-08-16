/**
 * PRISMA - every texture is drawn into a 2D canvas at boot.
 *
 * No image file, no fetch. The PRNG is seeded so a given build always produces
 * the same speckle, which makes visual regressions obvious.
 */

import * as THREE from 'three';

function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function random() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function canvasTexture(canvas, { srgb = true, repeat = false } = {}) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  if (repeat) {
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
  }
  tex.needsUpdate = true;
  return tex;
}

/** Floor tile: dark plate, inset border, corner ticks. Kept mid grey so the
 *  per instance colour of the board can tint it without going black. */
function drawTile(rand) {
  const s = 128;
  const c = makeCanvas(s, s);
  const g = c.getContext('2d');
  g.fillStyle = '#8d93a8';
  g.fillRect(0, 0, s, s);

  for (let i = 0; i < 1400; i++) {
    const v = 128 + Math.floor(rand() * 40);
    g.fillStyle = `rgba(${v},${v},${v + 8},0.16)`;
    g.fillRect(Math.floor(rand() * s), Math.floor(rand() * s), 1, 1);
  }

  g.strokeStyle = 'rgba(20,24,38,0.75)';
  g.lineWidth = 6;
  g.strokeRect(3, 3, s - 6, s - 6);
  g.strokeStyle = 'rgba(210,220,255,0.32)';
  g.lineWidth = 2;
  g.strokeRect(12, 12, s - 24, s - 24);

  g.fillStyle = 'rgba(215,225,255,0.5)';
  const t = 10;
  for (const [x, y] of [
    [12, 12],
    [s - 12 - t, 12],
    [12, s - 12 - t],
    [s - 12 - t, s - 12 - t],
  ]) {
    g.fillRect(x, y, t, 2);
    g.fillRect(x, y, 2, t);
  }
  return c;
}

/** Wall panel: vertical ribs plus a bright cap line at the top. */
function drawPanel(rand) {
  const w = 128;
  const h = 128;
  const c = makeCanvas(w, h);
  const g = c.getContext('2d');
  g.fillStyle = '#4a5068';
  g.fillRect(0, 0, w, h);
  for (let x = 0; x < w; x += 16) {
    g.fillStyle = 'rgba(24,28,44,0.55)';
    g.fillRect(x, 0, 3, h);
    g.fillStyle = 'rgba(190,205,255,0.13)';
    g.fillRect(x + 3, 0, 1, h);
  }
  for (let i = 0; i < 900; i++) {
    const v = Math.floor(rand() * 30);
    g.fillStyle = `rgba(${v},${v},${v + 10},0.2)`;
    g.fillRect(Math.floor(rand() * w), Math.floor(rand() * h), 1, 1);
  }
  g.fillStyle = 'rgba(220,230,255,0.4)';
  g.fillRect(0, 0, w, 4);
  g.fillStyle = 'rgba(10,12,22,0.6)';
  g.fillRect(0, h - 8, w, 8);
  return c;
}

/** Soft round sprite, used for dust motes and every flare. */
function drawGlow() {
  const s = 64;
  const c = makeCanvas(s, s);
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.28, 'rgba(255,255,255,0.55)');
  grad.addColorStop(0.65, 'rgba(255,255,255,0.12)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, s, s);
  return c;
}

/** Target face: concentric rings with a bright rim, alpha cut. */
function drawRing() {
  const s = 256;
  const c = makeCanvas(s, s);
  const g = c.getContext('2d');
  g.clearRect(0, 0, s, s);
  const cx = s / 2;
  g.strokeStyle = 'rgba(255,255,255,0.95)';
  g.lineWidth = 14;
  g.beginPath();
  g.arc(cx, cx, s * 0.40, 0, Math.PI * 2);
  g.stroke();
  g.strokeStyle = 'rgba(255,255,255,0.55)';
  g.lineWidth = 5;
  g.beginPath();
  g.arc(cx, cx, s * 0.27, 0, Math.PI * 2);
  g.stroke();
  g.fillStyle = 'rgba(255,255,255,0.85)';
  g.beginPath();
  g.arc(cx, cx, s * 0.11, 0, Math.PI * 2);
  g.fill();
  g.strokeStyle = 'rgba(255,255,255,0.7)';
  g.lineWidth = 6;
  for (let i = 0; i < 4; i++) {
    const a = (i / 4) * Math.PI * 2 + Math.PI / 4;
    g.beginPath();
    g.moveTo(cx + Math.cos(a) * s * 0.44, cx + Math.sin(a) * s * 0.44);
    g.lineTo(cx + Math.cos(a) * s * 0.5, cx + Math.sin(a) * s * 0.5);
    g.stroke();
  }
  return c;
}

/** Portal face: a spiral of dashes, spun by the renderer. */
function drawPortal() {
  const s = 256;
  const c = makeCanvas(s, s);
  const g = c.getContext('2d');
  const cx = s / 2;
  for (let ring = 0; ring < 4; ring++) {
    const r = s * (0.18 + ring * 0.08);
    const segs = 10 + ring * 4;
    g.strokeStyle = `rgba(255,255,255,${0.85 - ring * 0.14})`;
    g.lineWidth = 8 - ring;
    for (let i = 0; i < segs; i++) {
      const a0 = (i / segs) * Math.PI * 2 + ring * 0.4;
      g.beginPath();
      g.arc(cx, cx, r, a0, a0 + (Math.PI * 2) / segs / 1.9);
      g.stroke();
    }
  }
  return c;
}

/** Equirectangular room light probe. Metal in this game is lit almost entirely
 *  by this, so it must keep some bright spots or every mirror renders matte
 *  black (a trap this repository has hit before). */
function drawEnv() {
  const w = 256;
  const h = 128;
  const c = makeCanvas(w, h);
  const g = c.getContext('2d');
  const sky = g.createLinearGradient(0, 0, 0, h);
  sky.addColorStop(0, '#3a2a63');
  sky.addColorStop(0.42, '#2a2450');
  sky.addColorStop(0.52, '#6c3fa8');
  sky.addColorStop(0.62, '#1b2038');
  sky.addColorStop(1, '#0c0e1a');
  g.fillStyle = sky;
  g.fillRect(0, 0, w, h);

  for (const [x, y, r, col] of [
    [40, 30, 34, 'rgba(255,255,255,0.85)'],
    [160, 22, 26, 'rgba(150,220,255,0.7)'],
    [220, 46, 30, 'rgba(255,140,220,0.6)'],
    [100, 66, 40, 'rgba(120,90,255,0.45)'],
  ]) {
    const grad = g.createRadialGradient(x, y, 0, x, y, r);
    grad.addColorStop(0, col);
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grad;
    g.fillRect(x - r, y - r, r * 2, r * 2);
  }
  return c;
}

/**
 * Inventory icons, returned as data URLs so the HUD can use them as CSS
 * backgrounds without shipping a single image file.
 */
function drawIcons() {
  const size = 72;
  const out = {};

  function base() {
    const c = makeCanvas(size, size);
    const g = c.getContext('2d');
    g.clearRect(0, 0, size, size);
    g.lineCap = 'round';
    g.lineJoin = 'round';
    return { c, g };
  }

  {
    const { c, g } = base();
    g.strokeStyle = '#eaf2ff';
    g.lineWidth = 8;
    g.beginPath();
    g.moveTo(16, 56);
    g.lineTo(56, 16);
    g.stroke();
    g.strokeStyle = 'rgba(120,132,160,0.9)';
    g.lineWidth = 5;
    g.beginPath();
    g.moveTo(22, 62);
    g.lineTo(62, 22);
    g.stroke();
    out.mirror = c.toDataURL();
  }
  {
    const { c, g } = base();
    g.strokeStyle = '#d9b6ff';
    g.lineWidth = 6;
    g.beginPath();
    g.moveTo(36, 12);
    g.lineTo(60, 56);
    g.lineTo(12, 56);
    g.closePath();
    g.stroke();
    g.fillStyle = 'rgba(190,140,255,0.28)';
    g.fill();
    out.prism = c.toDataURL();
  }
  {
    const { c, g } = base();
    g.strokeStyle = '#ff7a7a';
    g.lineWidth = 6;
    g.strokeRect(14, 14, 44, 44);
    g.fillStyle = 'rgba(255,90,90,0.3)';
    g.fillRect(14, 14, 44, 44);
    g.strokeStyle = '#ffe08a';
    g.lineWidth = 5;
    g.beginPath();
    g.moveTo(4, 36);
    g.lineTo(20, 36);
    g.stroke();
    g.strokeStyle = '#ff7a7a';
    g.beginPath();
    g.moveTo(52, 36);
    g.lineTo(68, 36);
    g.stroke();
    out.filter = c.toDataURL();
  }
  {
    const { c, g } = base();
    g.strokeStyle = '#ffcc66';
    g.lineWidth = 6;
    g.beginPath();
    g.arc(32, 36, 18, 0, Math.PI * 2);
    g.stroke();
    g.beginPath();
    g.moveTo(4, 20);
    g.lineTo(18, 30);
    g.moveTo(4, 52);
    g.lineTo(18, 42);
    g.stroke();
    g.beginPath();
    g.moveTo(50, 36);
    g.lineTo(68, 36);
    g.moveTo(60, 29);
    g.lineTo(68, 36);
    g.lineTo(60, 43);
    g.stroke();
    out.combiner = c.toDataURL();
  }
  {
    const { c, g } = base();
    g.strokeStyle = 'rgba(160,230,255,0.95)';
    g.lineWidth = 7;
    g.beginPath();
    g.moveTo(18, 54);
    g.lineTo(54, 18);
    g.stroke();
    g.strokeStyle = '#eaf6ff';
    g.lineWidth = 4;
    g.beginPath();
    g.moveTo(4, 36);
    g.lineTo(68, 36);
    g.moveTo(36, 36);
    g.lineTo(36, 4);
    g.stroke();
    out.splitter = c.toDataURL();
  }
  return out;
}

export function createTextures(renderer) {
  const rand = mulberry32(0x9e3779b9);
  const maxAniso = renderer ? renderer.capabilities.getMaxAnisotropy() : 1;

  const tile = canvasTexture(drawTile(rand), { repeat: true });
  tile.anisotropy = maxAniso;
  const panel = canvasTexture(drawPanel(rand), { repeat: true });
  panel.anisotropy = maxAniso;
  const glow = canvasTexture(drawGlow());
  const ring = canvasTexture(drawRing());
  const portal = canvasTexture(drawPortal());
  const env = canvasTexture(drawEnv());
  env.mapping = THREE.EquirectangularReflectionMapping;

  const list = [tile, panel, glow, ring, portal, env];

  return {
    tile,
    panel,
    glow,
    ring,
    portal,
    env,
    icons: drawIcons(),
    dispose() {
      for (const t of list) t.dispose();
    },
  };
}
