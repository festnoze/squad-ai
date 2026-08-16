/**
 * ABYSSE - procedural texture factory.
 *
 * Every texture is painted on a 2D canvas at boot time. No binary asset, no
 * external URL. The generators are seeded with makeRandom() from config.js so
 * the game always boots with the exact same set of textures.
 *
 * Layout of this file:
 *   1. canvas and pixel helpers
 *   2. seeded noise toolbox (value noise, fbm, tileable Worley)
 *   3. colour helpers and normal map builder
 *   4. one builder function per texture family
 *   5. createTextures() which assembles the flat contract object
 */

import * as THREE from 'three';
import { PALETTE, makeRandom, clamp01 } from './config.js';

// ---------------------------------------------------------------------------
// 1. Canvas and pixel helpers
// ---------------------------------------------------------------------------

function makeCanvas(w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h === undefined ? w : h;
  return canvas;
}

/**
 * Runs fn(u, v, out, x, y) for every pixel, out = [r, g, b, a] bytes.
 * u and v are in [0, 1), which keeps every generator resolution independent.
 */
function fillPixels(w, h, fn) {
  const canvas = makeCanvas(w, h);
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(w, h);
  const data = img.data;
  const out = [0, 0, 0, 255];
  for (let y = 0; y < h; y++) {
    const v = y / h;
    for (let x = 0; x < w; x++) {
      out[0] = 0; out[1] = 0; out[2] = 0; out[3] = 255;
      fn(x / w, v, out, x, y);
      const i = (y * w + x) * 4;
      data[i] = out[0] | 0;
      data[i + 1] = out[1] | 0;
      data[i + 2] = out[2] | 0;
      data[i + 3] = out[3] | 0;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

function clampByte(v) {
  return v < 0 ? 0 : v > 255 ? 255 : v;
}

function smoothstep(a, b, x) {
  const t = clamp01((x - a) / (b - a));
  return t * t * (3 - 2 * t);
}

/** Scatter small dots on an existing canvas, duplicated across edges so the
 *  result stays tileable. */
function drawSpecks(canvas, rng, count, color, maxR, alpha) {
  const ctx = canvas.getContext('2d');
  const s = canvas.width;
  ctx.fillStyle = color;
  ctx.globalAlpha = alpha;
  for (let i = 0; i < count; i++) {
    const x = rng() * s;
    const y = rng() * s;
    const r = 0.5 + rng() * maxR;
    for (let ox = -1; ox <= 1; ox++) {
      for (let oy = -1; oy <= 1; oy++) {
        ctx.beginPath();
        ctx.arc(x + ox * s, y + oy * s, r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }
  ctx.globalAlpha = 1;
}

// ---------------------------------------------------------------------------
// 2. Seeded noise toolbox (everything tiles by construction)
// ---------------------------------------------------------------------------

/** Lattice value noise with independent wrap periods on each axis. */
function makeValueNoise(rng, px, py) {
  py = py || px;
  const grid = new Float32Array(px * py);
  for (let i = 0; i < grid.length; i++) grid[i] = rng();
  return function noise(x, y) {
    let xi = Math.floor(x);
    let yi = Math.floor(y);
    const xf = x - xi;
    const yf = y - yi;
    const u = xf * xf * (3 - 2 * xf);
    const v = yf * yf * (3 - 2 * yf);
    xi = ((xi % px) + px) % px;
    yi = ((yi % py) + py) % py;
    const x1 = (xi + 1) % px;
    const y1 = (yi + 1) % py;
    const a = grid[yi * px + xi];
    const b = grid[yi * px + x1];
    const c = grid[y1 * px + xi];
    const d = grid[y1 * px + x1];
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  };
}

/**
 * Tileable gradient (Perlin) noise with independent wrap periods.
 *
 * Value noise interpolates random *values* sitting on the lattice, so every
 * extremum lands on a lattice point and the result reads as blobs lined up on
 * a grid. Gradient noise interpolates random *directions* instead: extrema
 * fall between lattice points and features cross the grid at any angle, which
 * is what makes sand ripples and rock strata look eroded rather than knitted.
 */
function makeGradientNoise(rng, px, py) {
  py = py || px;
  const gx = new Float32Array(px * py);
  const gy = new Float32Array(px * py);
  for (let i = 0; i < px * py; i++) {
    const a = rng() * Math.PI * 2;
    gx[i] = Math.cos(a);
    gy[i] = Math.sin(a);
  }
  return function noise(x, y) {
    const xi = Math.floor(x);
    const yi = Math.floor(y);
    const xf = x - xi;
    const yf = y - yi;
    // Quintic fade: its second derivative vanishes at the lattice, so no
    // crease shows along the grid lines the way smoothstep leaves one.
    const u = xf * xf * xf * (xf * (xf * 6 - 15) + 10);
    const v = yf * yf * yf * (yf * (yf * 6 - 15) + 10);
    const x0 = ((xi % px) + px) % px;
    const y0 = ((yi % py) + py) % py;
    const x1 = (x0 + 1) % px;
    const y1 = (y0 + 1) % py;
    const i00 = y0 * px + x0;
    const i10 = y0 * px + x1;
    const i01 = y1 * px + x0;
    const i11 = y1 * px + x1;
    const n00 = gx[i00] * xf + gy[i00] * yf;
    const n10 = gx[i10] * (xf - 1) + gy[i10] * yf;
    const n01 = gx[i01] * xf + gy[i01] * (yf - 1);
    const n11 = gx[i11] * (xf - 1) + gy[i11] * (yf - 1);
    const a = n00 + (n10 - n00) * u;
    const b = n01 + (n11 - n01) * u;
    // 2D gradient noise spans about [-sqrt(2)/2, sqrt(2)/2]; remap to [0, 1].
    return (a + (b - a) * v) * 0.7071 + 0.5;
  };
}

/** Fractional Brownian motion built from stacked tileable gradient noises.
 *  fx and fy are the base frequencies (integer, so the result tiles). */
function makeFbm(rng, fx, fy, octaves) {
  const layers = [];
  for (let o = 0; o < octaves; o++) {
    layers.push(makeGradientNoise(rng, fx << o, fy << o));
  }
  return function fbm(u, v) {
    let sum = 0;
    let amp = 0.5;
    let tot = 0;
    for (let o = 0; o < octaves; o++) {
      sum += layers[o](u * (fx << o), v * (fy << o)) * amp;
      tot += amp;
      amp *= 0.5;
    }
    return sum / tot;
  };
}

// Worley writes its results into module scratch to avoid per-pixel objects.
let _wf1 = 0;
let _wf2 = 0;
let _wid = 0;

/** Tileable cellular noise. Call the returned sampler then read _wf1 (nearest
 *  distance), _wf2 (second nearest) and _wid (nearest cell id). */
function makeWorley(rng, count) {
  const px = new Float32Array(count);
  const py = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    px[i] = rng();
    py[i] = rng();
  }
  return function worley(u, v) {
    let f1 = 9;
    let f2 = 9;
    let id = 0;
    for (let i = 0; i < count; i++) {
      let dx = Math.abs(u - px[i]);
      if (dx > 0.5) dx = 1 - dx;
      let dy = Math.abs(v - py[i]);
      if (dy > 0.5) dy = 1 - dy;
      const d = dx * dx + dy * dy;
      if (d < f1) {
        f2 = f1;
        f1 = d;
        id = i;
      } else if (d < f2) {
        f2 = d;
      }
    }
    _wf1 = Math.sqrt(f1);
    _wf2 = Math.sqrt(f2);
    _wid = id;
  };
}

// ---------------------------------------------------------------------------
// 3. Colour helpers and normal map builder
// ---------------------------------------------------------------------------

function hexToRgb(hex) {
  return [(hex >> 16) & 255, (hex >> 8) & 255, hex & 255];
}

function mixInto(out, a, b, t) {
  out[0] = a[0] + (b[0] - a[0]) * t;
  out[1] = a[1] + (b[1] - a[1]) * t;
  out[2] = a[2] + (b[2] - a[2]) * t;
}

/**
 * Greyscale roughness map from the same height field that fed the normal map.
 * Crests are scoured smooth and troughs collect loose sediment, so tying
 * roughness to height makes the ripples catch the light instead of leaving the
 * whole ground under one flat roughness constant.
 */
function roughnessCanvas(size, height, lo, hi) {
  return fillPixels(size, size, (u, v, out, x, y) => {
    // three.js samples roughness from the green channel; grey keeps it obvious.
    const g = clampByte((lo + (hi - lo) * height[y * size + x]) * 255);
    out[0] = g;
    out[1] = g;
    out[2] = g;
  });
}

/** Sobel-ish normal map derived from a wrapped height field (0..1 values). */
function normalCanvas(size, height, strength) {
  return fillPixels(size, size, (u, v, out, x, y) => {
    const xl = height[y * size + (x + size - 1) % size];
    const xr = height[y * size + (x + 1) % size];
    const yu = height[((y + size - 1) % size) * size + x];
    const yd = height[((y + 1) % size) * size + x];
    const nx = (xl - xr) * strength;
    const ny = (yd - yu) * strength;
    const inv = 1 / Math.sqrt(nx * nx + ny * ny + 1);
    out[0] = clampByte((nx * inv * 0.5 + 0.5) * 255);
    out[1] = clampByte((ny * inv * 0.5 + 0.5) * 255);
    out[2] = clampByte((inv * 0.5 + 0.5) * 255);
  });
}

// ---------------------------------------------------------------------------
// 4. Texture builders
// ---------------------------------------------------------------------------

/** Sandy ground: warm grain, soft ripple bands, scattered darker specks.
 *  Returns the canvas plus the height field so the normal map can match. */
function buildSand(rng, size, baseHex, rippleAmp, grainAmp, speckColor) {
  const warp = makeFbm(rng, 4, 4, 3);
  const grain = makeFbm(rng, 24, 24, 4);
  const fine = makeFbm(rng, 48, 48, 2);
  const height = new Float32Array(size * size);
  const base = hexToRgb(baseHex);
  const canvas = fillPixels(size, size, (u, v, out, x, y) => {
    const w = warp(u, v);
    // Two ripple trains at different scales and angles. A single sine reads as
    // corduroy as soon as the texture repeats; crossing trains read as sand.
    const main = Math.sin((v * 6 + u * 1.5 + w * 1.7) * Math.PI * 2);
    const cross = Math.sin((v * 11 - u * 4 + w * 2.6) * Math.PI * 2);
    // Real ripples are asymmetric: a sharp crest above a long flat trough. The
    // gamma below spends most of the range low, which gives that profile.
    const shaped = Math.pow(main * 0.5 + 0.5, 1.8) * 2 - 1;
    const band = shaped * 0.82 + cross * 0.18;
    const g = grain(u, v) - 0.5;
    const f = fine(u, v) - 0.5;
    height[y * size + x] = clamp01(0.5 + band * 0.28 + g * 0.55 + f * 0.26);
    const light =
      1 + band * rippleAmp + g * grainAmp + f * grainAmp * 0.55 + (w - 0.5) * 0.1;
    out[0] = clampByte(base[0] * light);
    out[1] = clampByte(base[1] * light);
    out[2] = clampByte(base[2] * light);
  });
  // Many small specks rather than few big ones: a handful of large blobs are
  // landmarks, and landmarks are exactly what makes a repeat visible.
  drawSpecks(canvas, rng, 520, speckColor, 0.65, 0.22);
  return { canvas, height };
}

/** Layered strata with cracks, cool grey. */
function buildRock(rng, size) {
  const warp = makeFbm(rng, 5, 5, 4);
  const detail = makeFbm(rng, 18, 18, 4);
  const cracks = makeWorley(rng, 20);
  const dark = hexToRgb(PALETTE.darkRock);
  const light = hexToRgb(PALETTE.rock);
  const height = new Float32Array(size * size);
  const rgb = [0, 0, 0];
  const canvas = fillPixels(size, size, (u, v, out, x, y) => {
    const w = warp(u, v);
    const strata = Math.sin((v * 5 + w * 2.4) * Math.PI * 2) * 0.5 + 0.5;
    cracks(u, v);
    const crack = 1 - smoothstep(0, 0.05, _wf2 - _wf1);
    const d = detail(u, v);
    let h = 0.35 + strata * 0.32 + (d - 0.5) * 0.5 - crack * 0.55;
    h = clamp01(h);
    height[y * size + x] = h;
    mixInto(rgb, dark, light, h);
    out[0] = clampByte(rgb[0] * 0.94);
    out[1] = clampByte(rgb[1] * 0.99);
    out[2] = clampByte(rgb[2] * 1.06);
  });
  return { canvas, height };
}

/** Coral crust: Worley cells tinted from the coral palette, dark crevices. */
function buildCoral(rng, size) {
  const cellCount = 26;
  const cells = makeWorley(rng, cellCount);
  const bump = makeFbm(rng, 20, 20, 3);
  const paletteHex = [
    PALETTE.coralPink, PALETTE.coralOrange, PALETTE.coralPurple,
    0x2fd6a8, PALETTE.coralPink, PALETTE.coralOrange,
  ];
  const cellColors = [];
  for (let i = 0; i < cellCount; i++) {
    const c = hexToRgb(paletteHex[Math.floor(rng() * paletteHex.length)]);
    const shade = 0.72 + rng() * 0.45;
    cellColors.push([c[0] * shade, c[1] * shade, c[2] * shade]);
  }
  const height = new Float32Array(size * size);
  const canvas = fillPixels(size, size, (u, v, out, x, y) => {
    cells(u, v);
    const col = cellColors[_wid];
    const crevice = 0.3 + 0.7 * smoothstep(0.008, 0.06, _wf2 - _wf1);
    const b = 0.85 + (bump(u, v) - 0.5) * 0.55;
    // Each polyp is a rounded lobe: full height at the cell centre, cut down
    // sharply in the crevice between cells.
    height[y * size + x] = clamp01(crevice * 0.75 + (b - 0.6) * 0.5);
    out[0] = clampByte(col[0] * crevice * b);
    out[1] = clampByte(col[1] * crevice * b);
    out[2] = clampByte(col[2] * crevice * b);
  });
  return { canvas, height };
}

/** Bright thin Worley filaments on black. Two overlapping scales so the
 *  pattern reads as refracted light rather than a plain cell diagram. */
function buildCaustics(rng, size) {
  const wideCells = makeWorley(rng, 14);
  const fineCells = makeWorley(rng, 30);
  const shimmer = makeFbm(rng, 6, 6, 3);
  return fillPixels(size, size, (u, v, out) => {
    wideCells(u, v);
    const a = Math.pow(clamp01(1 - (_wf2 - _wf1) * 9), 3.4);
    fineCells(u, v);
    const b = Math.pow(clamp01(1 - (_wf2 - _wf1) * 12), 3.8);
    const mod = 0.72 + shimmer(u, v) * 0.55;
    const val = clamp01((a * 0.9 + b * 0.65) * mod);
    const byte = clampByte(val * 255);
    out[0] = byte;
    out[1] = byte;
    out[2] = clampByte(byte * 1.04);
  });
}

/** Generic tileable grey fbm. */
function buildNoise(rng, size) {
  const fbm = makeFbm(rng, 8, 8, 5);
  return fillPixels(size, size, (u, v, out) => {
    const byte = clampByte(fbm(u, v) * 255);
    out[0] = byte;
    out[1] = byte;
    out[2] = byte;
  });
}

/** Overlapping rows of scale arcs with a mild iridescent sheen. */
function buildFishScale(rng, size) {
  const canvas = makeCanvas(size);
  const ctx = canvas.getContext('2d');
  const cols = 8;
  const w = size / cols;
  const rows = 12; // even so the half-offset rows tile vertically
  const rowH = size / rows;
  ctx.fillStyle = '#7fa8b8';
  ctx.fillRect(0, 0, size, size);
  for (let row = -1; row <= rows; row++) {
    const off = (((row % 2) + 2) % 2) * w * 0.5;
    for (let col = -1; col <= cols; col++) {
      const cx = col * w + off + w * 0.5;
      const cy = row * rowH;
      const hue = 190 + Math.sin((row * 7 + col * 13) * 0.7) * 26;
      const lig = 58 + Math.sin((row * 3 + col * 5) * 1.3) * 8;
      const grad = ctx.createRadialGradient(cx, cy - w * 0.2, w * 0.08, cx, cy, w * 0.68);
      grad.addColorStop(0, 'hsl(' + hue + ', 32%, ' + (lig + 14) + '%)');
      grad.addColorStop(1, 'hsl(' + hue + ', 38%, ' + (lig - 8) + '%)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx, cy, w * 0.62, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(20, 45, 60, 0.5)';
      ctx.lineWidth = 1.4;
      ctx.stroke();
    }
  }
  // Iridescent sheen: cyan to pink and back so the gradient tiles.
  const sheen = ctx.createLinearGradient(0, 0, size, 0);
  sheen.addColorStop(0, 'rgba(110, 235, 255, 0.16)');
  sheen.addColorStop(0.5, 'rgba(255, 150, 220, 0.16)');
  sheen.addColorStop(1, 'rgba(110, 235, 255, 0.16)');
  ctx.fillStyle = sheen;
  ctx.fillRect(0, 0, size, size);
  return canvas;
}

/** Matte grey skin with tiny light denticle dashes. */
function buildSharkSkin(rng, size) {
  const fbm = makeFbm(rng, 10, 10, 4);
  const canvas = fillPixels(size, size, (u, v, out) => {
    const g = 105 + (fbm(u, v) - 0.5) * 46;
    out[0] = clampByte(g);
    out[1] = clampByte(g * 1.03);
    out[2] = clampByte(g * 1.08);
  });
  const ctx = canvas.getContext('2d');
  for (let i = 0; i < 900; i++) {
    const x = rng() * size;
    const y = rng() * size;
    ctx.fillStyle = rng() < 0.5 ? 'rgba(220, 230, 238, 0.14)' : 'rgba(30, 38, 46, 0.14)';
    for (let ox = -1; ox <= 1; ox++) {
      ctx.fillRect(x + ox * size, y, 2.5, 1);
    }
  }
  return canvas;
}

/** Steel panels with seams, bevels and rivets. */
function buildHullPanel(rng, size) {
  const fbm = makeFbm(rng, 12, 12, 3);
  const panels = 4;
  const canvas = fillPixels(size, size, (u, v, out) => {
    const pu = (u * panels) % 1;
    const pv = (v * panels) % 1;
    const edge = Math.min(pu, 1 - pu, pv, 1 - pv);
    let g = 150 + (fbm(u, v) - 0.5) * 26;
    if (edge < 0.015) g *= 0.45; // seam groove
    else if (edge < 0.05) g *= 1.12; // bevel highlight
    out[0] = clampByte(g * 0.96);
    out[1] = clampByte(g);
    out[2] = clampByte(g * 1.05);
  });
  const ctx = canvas.getContext('2d');
  const step = size / panels;
  for (let py = 0; py < panels; py++) {
    for (let px = 0; px < panels; px++) {
      for (let i = 0; i < 6; i++) {
        const t = (i + 0.5) / 6;
        dot(ctx, px * step + t * step, py * step + step * 0.08);
        dot(ctx, px * step + t * step, py * step + step * 0.92);
      }
    }
  }
  function dot(c, x, y) {
    c.fillStyle = 'rgba(28, 34, 40, 0.8)';
    c.beginPath();
    c.arc(x, y, 2.2, 0, Math.PI * 2);
    c.fill();
    c.fillStyle = 'rgba(230, 238, 244, 0.5)';
    c.beginPath();
    c.arc(x - 0.7, y - 0.7, 0.9, 0, Math.PI * 2);
    c.fill();
  }
  return canvas;
}

/** Corroded wreck plating: brown base, orange blooms, vertical run-off. */
function buildHullRust(rng, size) {
  const blotch = makeFbm(rng, 6, 6, 4);
  const streak = makeFbm(rng, 12, 3, 3);
  const pits = makeFbm(rng, 28, 28, 2);
  const base = hexToRgb(0x3d2a1f);
  const rust = hexToRgb(0xa4562a);
  const rgb = [0, 0, 0];
  return fillPixels(size, size, (u, v, out) => {
    const t = smoothstep(0.42, 0.72, blotch(u, v) * 0.72 + streak(u, v) * 0.28);
    mixInto(rgb, base, rust, t);
    const pit = pits(u, v) > 0.78 ? 0.55 : 1;
    out[0] = clampByte(rgb[0] * pit);
    out[1] = clampByte(rgb[1] * pit);
    out[2] = clampByte(rgb[2] * pit);
  });
}

/** Weathered dock planks with stretched grain. */
function buildPlank(rng, size) {
  const grain = makeFbm(rng, 3, 40, 4);
  const planks = 4;
  const shades = [];
  for (let i = 0; i < planks; i++) shades.push(0.82 + rng() * 0.32);
  const base = hexToRgb(0x8a6a44);
  const canvas = fillPixels(size, size, (u, v, out) => {
    const pi = Math.floor(u * planks) % planks;
    const pu = (u * planks) % 1;
    const g = grain(u, v + pi * 0.37);
    let light = shades[pi] * (0.78 + Math.pow(g, 1.4) * 0.5);
    if (pu < 0.03 || pu > 0.97) light *= 0.4; // gap between planks
    out[0] = clampByte(base[0] * light);
    out[1] = clampByte(base[1] * light);
    out[2] = clampByte(base[2] * light);
  });
  const ctx = canvas.getContext('2d');
  for (let i = 0; i < 5; i++) {
    const x = (i + 0.5) * (size / 5) + (rng() - 0.5) * 20;
    const y = rng() * size;
    ctx.fillStyle = 'rgba(45, 30, 16, 0.55)';
    ctx.beginPath();
    ctx.ellipse(x, y, 4.5, 6.5, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  return canvas;
}

/** Clean pale lab wall with faint panel seams. */
function buildLabWall(rng, size) {
  const fbm = makeFbm(rng, 9, 9, 3);
  const panels = 2;
  return fillPixels(size, size, (u, v, out) => {
    const pu = (u * panels) % 1;
    const pv = (v * panels) % 1;
    const edge = Math.min(pu, 1 - pu, pv, 1 - pv);
    let g = 224 + (fbm(u, v) - 0.5) * 14;
    if (edge < 0.01) g *= 0.82;
    if (v > 0.86) g *= 0.9; // darker skirting band, tiles vertically
    out[0] = clampByte(g * 0.985);
    out[1] = clampByte(g);
    out[2] = clampByte(g * 1.01);
  });
}

/** Lacey white surface foam with alpha holes. */
function buildSeaFoam(rng, size) {
  const cells = makeWorley(rng, 22);
  const mask = makeFbm(rng, 5, 5, 4);
  return fillPixels(size, size, (u, v, out) => {
    cells(u, v);
    const lace = Math.pow(clamp01(1 - (_wf2 - _wf1) * 7), 2.2);
    const patch = smoothstep(0.34, 0.62, mask(u, v));
    const a = clamp01(lace * 0.85 + patch * 0.25) * patch;
    out[0] = 240;
    out[1] = 250;
    out[2] = 255;
    out[3] = clampByte(a * 255);
  });
}

/** Two octaves of directional waves plus fbm chop, encoded as a normal map. */
function buildWaterNormal(rng, size) {
  const warp = makeFbm(rng, 4, 4, 3);
  const chop = makeFbm(rng, 12, 12, 3);
  const height = new Float32Array(size * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = x / size;
      const v = y / size;
      const w = warp(u, v);
      const wave1 = Math.sin((3 * u + 1 * v) * Math.PI * 2 + w * 2.4) * 0.5;
      const wave2 = Math.sin((-2 * u + 5 * v) * Math.PI * 2 + w * 3.1) * 0.28;
      const c = (chop(u, v) - 0.5) * 0.6;
      height[y * size + x] = clamp01(0.5 + wave1 * 0.4 + wave2 * 0.4 + c);
    }
  }
  return normalCanvas(size, height, 2.0);
}

/** Single kelp blade with alpha, veins and colour drift along its length. */
function buildKelp(rng) {
  const w = 128;
  const h = 512;
  const canvas = makeCanvas(w, h);
  const ctx = canvas.getContext('2d');
  const steps = 40;
  const cx = w * 0.5;
  const left = [];
  const right = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const y = 8 + t * (h - 16);
    const sway = Math.sin(t * 9 + 1.3) * w * 0.07;
    const width = w * 0.36 * Math.max(0.06, Math.sin(Math.PI * Math.min(1, t * 1.12)))
      * (0.82 + 0.18 * Math.sin(t * 23 + 1.7));
    left.push([cx + sway - width, y]);
    right.push([cx + sway + width, y]);
  }
  ctx.beginPath();
  ctx.moveTo(left[0][0], left[0][1]);
  for (let i = 1; i <= steps; i++) ctx.lineTo(left[i][0], left[i][1]);
  for (let i = steps; i >= 0; i--) ctx.lineTo(right[i][0], right[i][1]);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, '#5c9a48');
  grad.addColorStop(0.3, '#3f7a34');
  grad.addColorStop(0.55, '#4d8a3e');
  grad.addColorStop(0.8, '#2f5a28');
  grad.addColorStop(1, '#24491f');
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.strokeStyle = 'rgba(18, 40, 14, 0.7)';
  ctx.lineWidth = 2;
  ctx.stroke();
  // Midrib plus side veins.
  ctx.strokeStyle = 'rgba(150, 190, 100, 0.5)';
  ctx.lineWidth = 3;
  ctx.beginPath();
  for (let i = 0; i <= steps; i++) {
    const x = (left[i][0] + right[i][0]) * 0.5;
    if (i === 0) ctx.moveTo(x, left[i][1]);
    else ctx.lineTo(x, left[i][1]);
  }
  ctx.stroke();
  ctx.lineWidth = 1;
  ctx.strokeStyle = 'rgba(24, 52, 18, 0.45)';
  for (let i = 4; i < steps; i += 4) {
    const midX = (left[i][0] + right[i][0]) * 0.5;
    ctx.beginPath();
    ctx.moveTo(midX, left[i][1]);
    ctx.lineTo(left[i][0] + 4, left[i][1] + 14);
    ctx.moveTo(midX, right[i][1]);
    ctx.lineTo(right[i][0] - 4, right[i][1] + 14);
    ctx.stroke();
  }
  return canvas;
}

/** Horizontal palm frond: curved rachis, tapering leaflets on both sides. */
function buildPalmLeaf(rng) {
  const w = 512;
  const h = 256;
  const canvas = makeCanvas(w, h);
  const ctx = canvas.getContext('2d');
  const baseY = h * 0.52;
  const rachis = (t) => baseY + Math.sin(t * Math.PI) * -18 + t * 26;
  const n = 30;
  for (let side = -1; side <= 1; side += 2) {
    for (let i = 0; i < n; i++) {
      const t = (i + 0.5) / n;
      const x = 14 + t * (w - 40);
      const y = rachis(t);
      const len = (h * 0.42) * (1 - t * 0.72) * (0.68 + rng() * 0.4);
      const ang = side * (0.9 + t * 0.55) + (rng() - 0.5) * 0.16;
      const tipX = x + Math.sin(ang) * len * 0.55 + len * 0.5;
      const tipY = y + Math.cos(ang) * len * side * -1;
      const g = 92 + rng() * 60;
      ctx.fillStyle = 'rgb(' + Math.round(g * 0.42) + ',' + Math.round(g) + ',' + Math.round(g * 0.38) + ')';
      ctx.beginPath();
      ctx.moveTo(x, y - side * 2);
      ctx.quadraticCurveTo(x + len * 0.3, (y + tipY) * 0.5 - side * 6, tipX, tipY);
      ctx.quadraticCurveTo(x + len * 0.34, (y + tipY) * 0.5 + side * 2, x + 7, y);
      ctx.closePath();
      ctx.fill();
    }
  }
  ctx.strokeStyle = '#6b5a30';
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.moveTo(10, rachis(0));
  for (let i = 1; i <= 24; i++) {
    const t = i / 24;
    ctx.lineTo(14 + t * (w - 40), rachis(t));
  }
  ctx.stroke();
  return canvas;
}

/** Bushy island foliage: a rosette of pointed leaves with veins. */
function buildFoliage(rng) {
  const s = 256;
  const canvas = makeCanvas(s);
  const ctx = canvas.getContext('2d');
  const greens = ['#2f5a2a', '#3f7a34', '#558a3c', '#6fa04a', '#47823a'];
  const cx = s * 0.5;
  const cy = s * 0.62;
  for (let i = 0; i < 16; i++) {
    const ang = (i / 16) * Math.PI * 2 + rng() * 0.4;
    const len = s * (0.22 + rng() * 0.24);
    const wid = len * (0.3 + rng() * 0.18);
    const tipX = cx + Math.cos(ang) * len;
    const tipY = cy + Math.sin(ang) * len * 0.86 - len * 0.18;
    const midX = cx + Math.cos(ang) * len * 0.5;
    const midY = cy + Math.sin(ang) * len * 0.5 * 0.86;
    const px = Math.cos(ang + Math.PI * 0.5) * wid * 0.5;
    const py = Math.sin(ang + Math.PI * 0.5) * wid * 0.5;
    ctx.fillStyle = greens[Math.floor(rng() * greens.length)];
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.quadraticCurveTo(midX + px, midY + py, tipX, tipY);
    ctx.quadraticCurveTo(midX - px, midY - py, cx, cy);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = 'rgba(20, 42, 16, 0.55)';
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(tipX, tipY);
    ctx.stroke();
  }
  return canvas;
}

/** Radial bubble sprite: bright rim, faint fill, offset highlight. */
function buildBubble(size) {
  return fillPixels(size, size, (u, v, out) => {
    const dx = (u - 0.5) * 2;
    const dy = (v - 0.5) * 2;
    const r = Math.sqrt(dx * dx + dy * dy);
    const rim = Math.exp(-Math.pow((r - 0.74) * 8.5, 2));
    const inner = 0.1 * smoothstep(1, 0.15, r);
    const hx = dx + 0.28;
    const hy = dy + 0.3;
    const hl = Math.exp(-(hx * hx + hy * hy) * 26);
    const a = clamp01(rim * 0.95 + inner + hl * 0.85) * smoothstep(1, 0.94, r);
    out[0] = 218;
    out[1] = 240;
    out[2] = 255;
    out[3] = clampByte(a * 255);
  });
}

/** Tiny soft dot for marine snow. */
function buildMote(size) {
  return fillPixels(size, size, (u, v, out) => {
    const dx = (u - 0.5) * 2;
    const dy = (v - 0.5) * 2;
    const a = Math.exp(-(dx * dx + dy * dy) * 6.5);
    out[0] = 255;
    out[1] = 255;
    out[2] = 255;
    out[3] = clampByte(a * 255);
  });
}

/** Generic radial glow for bioluminescence, lamps and blood clouds. */
function buildGlow(size) {
  return fillPixels(size, size, (u, v, out) => {
    const dx = (u - 0.5) * 2;
    const dy = (v - 0.5) * 2;
    const r = Math.sqrt(dx * dx + dy * dy);
    const a = clamp01(Math.pow(Math.max(0, 1 - r), 2.1) + Math.exp(-r * 7) * 0.4);
    out[0] = 255;
    out[1] = 255;
    out[2] = 255;
    out[3] = clampByte(a * 255);
  });
}

/** Vertical light shaft: soft horizontal band, alpha fading at both ends. */
function buildGodray(rng, w, h) {
  const streak = makeValueNoise(rng, 24, 1);
  return fillPixels(w, h, (u, v, out) => {
    const xb = Math.exp(-Math.pow((u - 0.5) / 0.2, 2));
    const yb = smoothstep(0, 0.2, v) * smoothstep(1, 0.55, v);
    const s = 0.78 + streak(u * 24, 0) * 0.22;
    const a = clamp01(xb * yb * s);
    out[0] = 232;
    out[1] = 246;
    out[2] = 255;
    out[3] = clampByte(a * 255);
  });
}

/** Sun halo seen from under the surface: hot core, wide halo, faint rays. */
function buildFlare(size) {
  return fillPixels(size, size, (u, v, out) => {
    const dx = (u - 0.5) * 2;
    const dy = (v - 0.5) * 2;
    const r = Math.sqrt(dx * dx + dy * dy);
    const ang = Math.atan2(dy, dx);
    const core = Math.exp(-r * 10);
    const halo = Math.exp(-r * 3.2) * 0.55;
    const rays = Math.pow(Math.abs(Math.cos(ang * 5)), 10) * Math.exp(-r * 4) * 0.5;
    const ring = Math.exp(-Math.pow((r - 0.55) * 8, 2)) * 0.1;
    const val = clamp01(core + halo + rays + ring);
    out[0] = clampByte(val * 255);
    out[1] = clampByte(val * 250);
    out[2] = clampByte(val * 238 + val * val * 30);
    out[3] = clampByte(val * 255);
  });
}

// ---------------------------------------------------------------------------
// 5. Assembly
// ---------------------------------------------------------------------------

// Set once from the renderer in createTextures(). The seabed is almost always
// seen at a grazing angle, which is exactly the case anisotropic filtering
// exists for: at 4 the sand smears into mush a few metres ahead of the diver.
let _anisotropy = 4;

function toTexture(canvas, opts) {
  opts = opts || {};
  const tex = new THREE.CanvasTexture(canvas);
  if (opts.repeat) {
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
  }
  if (opts.srgb) tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = _anisotropy;
  return tex;
}

/** `renderer` is optional: without it the filtering falls back to the old
 *  fixed value, so the texture set still builds in a headless test. */
export function createTextures(renderer) {
  _anisotropy = renderer ? renderer.capabilities.getMaxAnisotropy() : 4;
  const rng = makeRandom(48151623);

  const sandBuild = buildSand(rng, 256, PALETTE.sand, 0.09, 0.24, 'rgba(96, 78, 52, 1)');
  const beachBuild = buildSand(rng, 256, 0xe8dcb8, 0.06, 0.17, 'rgba(180, 150, 110, 1)');
  const rockBuild = buildRock(rng, 256);
  const coralBuild = buildCoral(rng, 256);

  const textures = {
    // Ground and structures
    sand: toTexture(sandBuild.canvas, { repeat: true, srgb: true }),
    sandNormal: toTexture(normalCanvas(256, sandBuild.height, 2.8), { repeat: true }),
    sandRough: toTexture(roughnessCanvas(256, sandBuild.height, 0.72, 1.0), { repeat: true }),
    rock: toTexture(rockBuild.canvas, { repeat: true, srgb: true }),
    rockNormal: toTexture(normalCanvas(256, rockBuild.height, 3.4), { repeat: true }),
    rockRough: toTexture(roughnessCanvas(256, rockBuild.height, 0.66, 1.0), { repeat: true }),
    coral: toTexture(coralBuild.canvas, { repeat: true, srgb: true }),
    coralNormal: toTexture(normalCanvas(256, coralBuild.height, 2.4), { repeat: true }),
    beachSand: toTexture(beachBuild.canvas, { repeat: true, srgb: true }),
    beachNormal: toTexture(normalCanvas(256, beachBuild.height, 2.2), { repeat: true }),
    plank: toTexture(buildPlank(rng, 256), { repeat: true, srgb: true }),
    labWall: toTexture(buildLabWall(rng, 256), { repeat: true, srgb: true }),
    hullPanel: toTexture(buildHullPanel(rng, 256), { repeat: true, srgb: true }),
    hullRust: toTexture(buildHullRust(rng, 256), { repeat: true, srgb: true }),

    // Vegetation (alpha cutouts, not tileable)
    kelp: toTexture(buildKelp(rng), { srgb: true }),
    foliage: toTexture(buildFoliage(rng), { srgb: true }),
    palmLeaf: toTexture(buildPalmLeaf(rng), { srgb: true }),

    // Creatures
    fishScale: toTexture(buildFishScale(rng, 256), { repeat: true, srgb: true }),
    sharkSkin: toTexture(buildSharkSkin(rng, 256), { repeat: true, srgb: true }),

    // Light and water (kept linear: they are light or data maps)
    caustics: toTexture(buildCaustics(rng, 512), { repeat: true }),
    noise: toTexture(buildNoise(rng, 256), { repeat: true }),
    waterNormal: toTexture(buildWaterNormal(rng, 256), { repeat: true }),
    seaFoam: toTexture(buildSeaFoam(rng, 256), { repeat: true, srgb: true }),

    // Sprites
    bubble: toTexture(buildBubble(128), { srgb: true }),
    mote: toTexture(buildMote(64), { srgb: true }),
    glow: toTexture(buildGlow(128), { srgb: true }),
    godray: toTexture(buildGodray(rng, 128, 512), { srgb: true }),
    flare: toTexture(buildFlare(256), { srgb: true }),

    dispose() {
      for (const key of Object.keys(textures)) {
        const t = textures[key];
        if (t && t.isTexture) t.dispose();
      }
    },
  };

  return textures;
}
