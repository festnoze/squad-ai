/**
 * VELOCITRON - procedural texture factory.
 *
 * Every pixel of the game is painted here on a 2D canvas: there is not a single
 * binary asset in the project. All randomness goes through a seeded mulberry32
 * PRNG so two runs produce exactly the same images.
 *
 * Conventions:
 *  - albedo / emissive / decal canvases are tagged THREE.SRGBColorSpace,
 *  - normal, roughness and noise canvases stay in THREE.NoColorSpace,
 *  - tiling maps wrap in both directions and are built to be seamless,
 *  - normal maps are a sobel of the very height field used for the albedo
 *    grain, never a second unrelated noise.
 *
 * Background rule, learned the hard way in this repository: the night city is
 * a backdrop, never a light source. The track neon emits above 1.0 in linear
 * space and is the only thing the bloom is allowed to catch, so every
 * background map (sky, facades, ground plan, clouds, moon, glow) is built for
 * CONTRAST INSIDE THE DARK RANGE, not for average brightness. The sky dome is
 * hard clamped, hue preserving, to SKY_MAX_* and the city maps are painted so
 * their brightest pixel lands around 70-90 out of 255. Raising the overall
 * level instead of the local contrast produces a grey-violet haze that eats
 * the circuit: do not do it.
 *
 * Content, in build order: road, walls, track dressing, hull, cockpit, three
 * skyscraper facades (windows / windowsWarm / windowsSlim), rooftop deck,
 * vertical facade sign, top down city block plan, stratified rock, low cloud
 * deck, moon, horizon glow, three advert panels, the sky dome and the particle
 * sprites. Everything is registered in a single `owned` list, so `dispose()`
 * covers new maps automatically.
 *
 * The whole build stays under the 700 ms budget: heavy work is done with
 * native canvas operations (patterns, gradients) and the few per-pixel passes
 * run once, on ImageData, over small surfaces. The nebula of the sky is
 * computed at a fraction of the dome resolution and scaled up, which is the
 * only reason the 2048x1024 map stays cheap.
 */

import * as THREE from 'three';
import { PALETTE } from './config.js';

// ---------------------------------------------------------------------------
// Deterministic random
// ---------------------------------------------------------------------------

/** Classic mulberry32: fast, seedable, good enough for texture noise. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Tileable value noise on a nx by ny lattice. Returned sampler takes (u, v) in
 * [0,1) and wraps, so any texture built from it is seamless.
 */
function valueNoise(rand, nx, ny) {
  const g = new Float32Array(nx * ny);
  for (let i = 0; i < g.length; i++) g[i] = rand();
  // u and v are always fed in [0,1) here, so the wrap is one conditional
  // subtraction rather than four modulos: this sampler runs a few hundred
  // thousand times per texture.
  return function sample(u, v) {
    const fx = u * nx;
    const fy = v * ny;
    const ix = Math.floor(fx);
    const iy = Math.floor(fy);
    const tx = fx - ix;
    const ty = fy - iy;
    const x0 = ix >= nx ? ix % nx : ix < 0 ? ((ix % nx) + nx) % nx : ix;
    const y0 = iy >= ny ? iy % ny : iy < 0 ? ((iy % ny) + ny) % ny : iy;
    const x1 = x0 + 1 === nx ? 0 : x0 + 1;
    const y1 = y0 + 1 === ny ? 0 : y0 + 1;
    const sx = tx * tx * (3 - 2 * tx);
    const sy = ty * ty * (3 - 2 * ty);
    const r0 = y0 * nx;
    const r1 = y1 * nx;
    const a = g[r0 + x0];
    const b = g[r0 + x1];
    const c = g[r1 + x0];
    const e = g[r1 + x1];
    const top = a + (b - a) * sx;
    const bot = c + (e - c) * sx;
    return top + (bot - top) * sy;
  };
}

/**
 * Sums octaves of tileable value noise, each octave doubling the lattice, so
 * the result still wraps. This is what gives the nebulae, the rock strata and
 * the cloud deck their internal filaments instead of a soft blob.
 */
function fbmSampler(rand, nx, ny, octaves) {
  const grids = [];
  const gw = new Int32Array(octaves);
  const gh = new Int32Array(octaves);
  const amps = new Float32Array(octaves);
  let amp = 1;
  let total = 0;
  for (let o = 0; o < octaves; o++) {
    const w = nx << o;
    const h = ny << o;
    const g = new Float32Array(w * h);
    for (let i = 0; i < g.length; i++) g[i] = rand();
    grids.push(g);
    gw[o] = w;
    gh[o] = h;
    amps[o] = amp;
    total += amp;
    amp *= 0.5;
  }
  const inv = 1 / total;
  // The lattice lookup is inlined rather than delegated to valueNoise: this
  // sampler is called a few million times per build and the extra call per
  // octave was one of the two hot spots of the whole factory.
  return function sample(u, v) {
    let sum = 0;
    for (let o = 0; o < octaves; o++) {
      const w = gw[o];
      const h = gh[o];
      const g = grids[o];
      const fx = u * w;
      const fy = v * h;
      let ix = fx | 0;
      let iy = fy | 0;
      const tx = fx - ix;
      const ty = fy - iy;
      if (ix >= w) ix -= w;
      if (iy >= h) iy -= h;
      const x1 = ix + 1 === w ? 0 : ix + 1;
      const y1 = iy + 1 === h ? 0 : iy + 1;
      const r0 = iy * w;
      const r1 = y1 * w;
      const a = g[r0 + ix];
      const b = g[r0 + x1];
      const c = g[r1 + ix];
      const e = g[r1 + x1];
      const sx = tx * tx * (3 - 2 * tx);
      const sy = ty * ty * (3 - 2 * ty);
      const top = a + (b - a) * sx;
      const bot = c + (e - c) * sx;
      sum += (top + (bot - top) * sy) * amps[o];
    }
    return sum * inv;
  };
}

/** Hermite ramp, clamped. Used everywhere a soft edge is needed. */
function smoothStep(edge0, edge1, x) {
  let t = (x - edge0) / (edge1 - edge0);
  if (t < 0) t = 0;
  else if (t > 1) t = 1;
  return t * t * (3 - 2 * t);
}

// ---------------------------------------------------------------------------
// Canvas helpers
// ---------------------------------------------------------------------------

function makeCanvas(w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  return canvas;
}

function ctxOf(canvas) {
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  return ctx;
}

function rgbOf(hex) {
  return [(hex >> 16) & 255, (hex >> 8) & 255, hex & 255];
}

function cssOf(hex, alpha) {
  const c = rgbOf(hex);
  if (alpha === undefined) return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
  return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + alpha + ')';
}

function cssMix(hexA, hexB, t, alpha) {
  const a = rgbOf(hexA);
  const b = rgbOf(hexB);
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  if (alpha === undefined) return 'rgb(' + r + ',' + g + ',' + bl + ')';
  return 'rgba(' + r + ',' + g + ',' + bl + ',' + alpha + ')';
}

function cssGray(v, alpha) {
  const g = Math.max(0, Math.min(255, Math.round(v)));
  if (alpha === undefined) return 'rgb(' + g + ',' + g + ',' + g + ')';
  return 'rgba(' + g + ',' + g + ',' + g + ',' + alpha + ')';
}

/** Small opaque grayscale noise tile, used as a repeat pattern. */
function noiseTile(rand, size, lo, hi) {
  const canvas = makeCanvas(size, size);
  const ctx = ctxOf(canvas);
  const img = ctx.createImageData(size, size);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const v = lo + rand() * (hi - lo);
    d[i] = v;
    d[i + 1] = v;
    d[i + 2] = v;
    d[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

/** Brushed metal tile: constant value per row plus a light along-row jitter. */
function brushTile(rand, size, lo, hi) {
  const canvas = makeCanvas(size, size);
  const ctx = ctxOf(canvas);
  const img = ctx.createImageData(size, size);
  const d = img.data;
  for (let y = 0; y < size; y++) {
    const row = lo + rand() * (hi - lo);
    for (let x = 0; x < size; x++) {
      const v = row + (rand() - 0.5) * 14;
      const i = (y * size + x) * 4;
      d[i] = v;
      d[i + 1] = v;
      d[i + 2] = v;
      d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

function patternFill(ctx, tile, w, h, alpha, mode) {
  const pattern = ctx.createPattern(tile, 'repeat');
  ctx.save();
  ctx.globalAlpha = alpha;
  if (mode) ctx.globalCompositeOperation = mode;
  ctx.fillStyle = pattern;
  ctx.fillRect(0, 0, w, h);
  ctx.restore();
}

/** Runs a draw callback nine times so anything it paints wraps at the borders. */
function wrapDraw(ctx, w, h, cb) {
  for (let oy = -1; oy <= 1; oy++) {
    for (let ox = -1; ox <= 1; ox++) {
      ctx.save();
      ctx.translate(ox * w, oy * h);
      cb(ctx);
      ctx.restore();
    }
  }
}

/** Vertical band centred on cx, duplicated so it survives the horizontal wrap. */
function vBand(ctx, w, h, cx, halfW) {
  ctx.fillRect(cx - halfW, 0, halfW * 2, h);
  if (cx - halfW < 0) ctx.fillRect(cx - halfW + w, 0, halfW * 2, h);
  if (cx + halfW > w) ctx.fillRect(cx - halfW - w, 0, halfW * 2, h);
}

/** Manual letter spacing: ctx.letterSpacing is not available everywhere. */
function spacedText(ctx, text, x, y, spacing, align) {
  let total = 0;
  for (let i = 0; i < text.length; i++) {
    total += ctx.measureText(text[i]).width;
    if (i < text.length - 1) total += spacing;
  }
  let cx = x;
  if (align === 'center') cx = x - total * 0.5;
  else if (align === 'right') cx = x - total;
  const prev = ctx.textAlign;
  ctx.textAlign = 'left';
  for (let i = 0; i < text.length; i++) {
    ctx.fillText(text[i], cx, y);
    cx += ctx.measureText(text[i]).width + spacing;
  }
  ctx.textAlign = prev;
  return total;
}

function roundedRectPath(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

/** Corner cut panel outline, the recurring shape of the whole UI/decor. */
function cutRectPath(ctx, x, y, w, h, cut) {
  ctx.beginPath();
  ctx.moveTo(x + cut, y);
  ctx.lineTo(x + w, y);
  ctx.lineTo(x + w, y + h - cut);
  ctx.lineTo(x + w - cut, y + h);
  ctx.lineTo(x, y + h);
  ctx.lineTo(x, y + cut);
  ctx.closePath();
}

/**
 * Sobel of a grayscale height canvas into a tangent space normal map.
 * Wrapping is taken into account so the normal map tiles like its source.
 * Green is up (OpenGL convention, what three.js expects).
 */
function heightToNormal(src, strength, srcData) {
  const w = src.width;
  const h = src.height;
  // srcData lets a caller that just wrote the height field hand its pixels
  // over directly, skipping a canvas readback.
  const sd = srcData || ctxOf(src).getImageData(0, 0, w, h).data;
  const out = makeCanvas(w, h);
  const octx = ctxOf(out);
  const oimg = octx.createImageData(w, h);
  const od = oimg.data;
  // Neighbour columns are precomputed: this runs over more than 1.8 M pixels
  // across the whole build, and the two modulos per pixel were measurable.
  const xmT = new Int32Array(w);
  const xpT = new Int32Array(w);
  for (let x = 0; x < w; x++) {
    xmT[x] = (x - 1 + w) % w;
    xpT[x] = (x + 1) % w;
  }
  for (let y = 0; y < h; y++) {
    const ym = (y - 1 + h) % h;
    const yp = (y + 1) % h;
    const rowM = ym * w;
    const row0 = y * w;
    const rowP = yp * w;
    for (let x = 0; x < w; x++) {
      const xm = xmT[x];
      const xp = xpT[x];
      const tl = sd[(rowM + xm) * 4];
      const tc = sd[(rowM + x) * 4];
      const tr = sd[(rowM + xp) * 4];
      const ml = sd[(row0 + xm) * 4];
      const mr = sd[(row0 + xp) * 4];
      const bl = sd[(rowP + xm) * 4];
      const bc = sd[(rowP + x) * 4];
      const br = sd[(rowP + xp) * 4];
      const gx = tr + 2 * mr + br - (tl + 2 * ml + bl);
      const gy = bl + 2 * bc + br - (tl + 2 * tc + tr);
      const nx = -gx * strength;
      const ny = gy * strength;
      const inv = 127 / Math.sqrt(nx * nx + ny * ny + 1);
      const i = (row0 + x) * 4;
      od[i] = 128 + nx * inv;
      od[i + 1] = 128 + ny * inv;
      od[i + 2] = 128 + inv;
      od[i + 3] = 255;
    }
  }
  octx.putImageData(oimg, 0, 0);
  return out;
}

/**
 * Turns a white on transparent sprite into a grayscale ramp whose alpha equals
 * its luminance. It then reads correctly whether fx.js blends it additively or
 * with a regular alpha blend, and never shows a hard square.
 */
function rampFromAlpha(canvas) {
  const ctx = ctxOf(canvas);
  const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const a = d[i + 3];
    d[i] = (d[i] * a) / 255;
    d[i + 1] = (d[i + 1] * a) / 255;
    d[i + 2] = (d[i + 2] * a) / 255;
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

// ---------------------------------------------------------------------------
// Road: 8 m across by 32 m along, 32 pixels per metre.
// ---------------------------------------------------------------------------

const ROAD_W = 256;
const ROAD_H = 1024;
const ROAD_JOINTS = 4; // cast-in expansion joints per tile, one every 8 m
const POLISH_A = ROAD_W * 0.28; // tyre polish lines, 3.5 m apart like a wheelbase
const POLISH_B = ROAD_W * 0.72;
const POLISH_HALF = 26;

/**
 * Box blur along Y only, wrapped, done with successive averaging draws.
 *
 * Y is the direction of travel on the road tile, so smearing along it turns the
 * isotropic aggregate grain into fine longitudinal grooves. The surface then
 * reads as smooth polished tarmac, and once the craft is moving the grooves
 * stretch into speed lines instead of boiling as noise.
 */
function blurY(source, w, h, radius, taps) {
  const out = makeCanvas(w, h);
  const oc = ctxOf(out);
  const n = Math.max(2, taps | 0);
  for (let i = 0; i < n; i++) {
    // Running average: drawing sample i at alpha 1/(i+1) leaves the exact mean.
    const t = n === 1 ? 0 : (i / (n - 1)) * 2 - 1; // -1 .. 1
    const dy = t * radius;
    oc.globalAlpha = 1 / (i + 1);
    // Three passes cover the wrap; only one of them can touch a given pixel.
    oc.drawImage(source, 0, dy);
    oc.drawImage(source, 0, dy - h);
    oc.drawImage(source, 0, dy + h);
  }
  oc.globalAlpha = 1;
  return out;
}

function buildRoad(rand) {
  // --- height field, shared by the albedo grain, the normal and the roughness
  const height = makeCanvas(ROAD_W, ROAD_H);
  const hc = ctxOf(height);
  const patches = valueNoise(rand, 8, 32); // ~1 m cells, resurfaced areas
  const grit = valueNoise(rand, 32, 128); // ~0.25 m cells, aggregate clusters
  const himg = hc.createImageData(ROAD_W, ROAD_H);
  const hd = himg.data;
  for (let y = 0; y < ROAD_H; y++) {
    const v = y / ROAD_H;
    for (let x = 0; x < ROAD_W; x++) {
      const u = x / ROAD_W;
      let g = 0.5;
      g += (patches(u, v) - 0.5) * 0.3;
      g += (grit(u, v) - 0.5) * 0.28;
      g += (rand() - 0.5) * 0.34;
      const val = g * 255;
      const i = (y * ROAD_W + x) * 4;
      const c = val < 0 ? 0 : val > 255 ? 255 : val;
      hd[i] = c;
      hd[i + 1] = c;
      hd[i + 2] = c;
      hd[i + 3] = 255;
    }
  }
  hc.putImageData(himg, 0, 0);

  // Smear the aggregate along the direction of travel before anything crisp is
  // drawn on top, so the joints and the paint stay sharp. What is left is a
  // brushed, grooved surface rather than a field of dots.
  const smeared = blurY(height, ROAD_W, ROAD_H, 9, 9);
  hc.clearRect(0, 0, ROAD_W, ROAD_H);
  hc.drawImage(smeared, 0, 0);

  // Long faint grooves, full tile height so they never break at the seam. These
  // are what actually stretch into speed lines once the craft is moving.
  hc.save();
  for (let i = 0; i < 150; i++) {
    const x = rand() * ROAD_W;
    const wgroove = 1 + rand() * 2.5;
    hc.globalAlpha = 0.05 + rand() * 0.1;
    hc.fillStyle = rand() < 0.5 ? cssGray(255) : cssGray(0);
    hc.fillRect(x, 0, wgroove, ROAD_H);
  }
  hc.restore();

  // Expansion joints: a recessed slot with a slightly proud lip on each side.
  for (let k = 0; k <= ROAD_JOINTS; k++) {
    const y = (k * ROAD_H) / ROAD_JOINTS;
    hc.fillStyle = cssGray(96);
    hc.fillRect(0, y - 3, ROAD_W, 6);
    hc.fillStyle = cssGray(168);
    hc.fillRect(0, y - 5, ROAD_W, 2);
    hc.fillRect(0, y + 3, ROAD_W, 2);
  }
  // Painted edging sits on top of the asphalt, so it is a touch proud.
  hc.fillStyle = cssGray(150);
  vBand(hc, ROAD_W, ROAD_H, 0, 6);
  hc.fillStyle = cssGray(142);
  vBand(hc, ROAD_W, ROAD_H, 18, 2);
  vBand(hc, ROAD_W, ROAD_H, ROAD_W - 18, 2);

  // --- albedo
  const albedo = makeCanvas(ROAD_W, ROAD_H);
  const ac = ctxOf(albedo);
  ac.fillStyle = cssOf(PALETTE.asphalt);
  ac.fillRect(0, 0, ROAD_W, ROAD_H);
  ac.save();
  ac.globalCompositeOperation = 'overlay';
  ac.globalAlpha = 0.85;
  ac.drawImage(height, 0, 0);
  ac.restore();

  // Large soft patches: old repairs, dust, oil. Drawn wrapped to stay seamless.
  const patchList = [];
  for (let i = 0; i < 7; i++) {
    patchList.push({
      x: rand() * ROAD_W,
      y: rand() * ROAD_H,
      r: 70 + rand() * 190,
      light: rand() < 0.45,
      a: 0.05 + rand() * 0.07,
    });
  }
  wrapDraw(ac, ROAD_W, ROAD_H, (c) => {
    for (let i = 0; i < patchList.length; i++) {
      const p = patchList[i];
      const grad = c.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
      grad.addColorStop(0, p.light ? cssOf(PALETTE.asphaltEdge, p.a) : cssGray(0, p.a));
      grad.addColorStop(1, p.light ? cssOf(PALETTE.asphaltEdge, 0) : cssGray(0, 0));
      c.fillStyle = grad;
      c.fillRect(p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);
    }
  });

  // Tyre polish: rubber laid down over the racing line, darker and glossier.
  for (const cx of [POLISH_A, POLISH_B]) {
    const grad = ac.createLinearGradient(cx - POLISH_HALF, 0, cx + POLISH_HALF, 0);
    grad.addColorStop(0, cssGray(0, 0));
    grad.addColorStop(0.5, cssGray(0, 0.34));
    grad.addColorStop(1, cssGray(0, 0));
    ac.fillStyle = grad;
    ac.fillRect(cx - POLISH_HALF, 0, POLISH_HALF * 2, ROAD_H);
  }
  // A few smeared streaks inside the polish bands break the vertical banding.
  ac.save();
  ac.globalAlpha = 0.16;
  for (let i = 0; i < 26; i++) {
    const cx = (rand() < 0.5 ? POLISH_A : POLISH_B) + (rand() - 0.5) * 40;
    const y = rand() * ROAD_H;
    const len = 60 + rand() * 220;
    ac.fillStyle = rand() < 0.5 ? cssGray(0) : cssOf(PALETTE.asphaltEdge);
    ac.fillRect(cx, y, 1 + rand() * 3, len);
  }
  ac.restore();

  // Full height brushing across the whole width. Subtle on its own, but it is
  // the layer that turns into speed streaks under motion and it cannot break at
  // the tile seam because every stroke spans the tile.
  ac.save();
  for (let i = 0; i < 120; i++) {
    ac.globalAlpha = 0.03 + rand() * 0.07;
    ac.fillStyle = rand() < 0.55 ? cssOf(PALETTE.asphaltEdge) : cssGray(24);
    ac.fillRect(rand() * ROAD_W, 0, 1 + rand() * 3, ROAD_H);
  }
  ac.restore();

  // Joints, painted after the patches so they stay readable.
  for (let k = 0; k <= ROAD_JOINTS; k++) {
    const y = (k * ROAD_H) / ROAD_JOINTS;
    ac.fillStyle = cssGray(0, 0.62);
    ac.fillRect(0, y - 3, ROAD_W, 6);
    ac.fillStyle = cssOf(PALETTE.asphaltEdge, 0.5);
    ac.fillRect(0, y - 5, ROAD_W, 2);
    ac.fillRect(0, y + 3, ROAD_W, 2);
  }

  // Painted lane edging, worn white plus a thin companion line either side.
  ac.fillStyle = 'rgba(196,204,214,0.86)';
  vBand(ac, ROAD_W, ROAD_H, 0, 6);
  ac.fillStyle = 'rgba(150,160,172,0.55)';
  vBand(ac, ROAD_W, ROAD_H, 18, 2);
  vBand(ac, ROAD_W, ROAD_H, ROAD_W - 18, 2);
  // Wear: chew small holes out of the paint so it does not read as a decal.
  ac.save();
  ac.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < 90; i++) {
    const onSeam = rand() < 0.7;
    const x = onSeam ? (rand() < 0.5 ? rand() * 7 : ROAD_W - rand() * 7) : 17 + rand() * 3;
    ac.globalAlpha = 0.1 + rand() * 0.25;
    ac.fillStyle = '#000';
    ac.fillRect(x, rand() * ROAD_H, 1 + rand() * 3, 2 + rand() * 10);
  }
  ac.restore();
  // Fill the holes back with asphalt so the alpha channel stays opaque.
  ac.save();
  ac.globalCompositeOperation = 'destination-over';
  ac.fillStyle = cssOf(PALETTE.asphalt);
  ac.fillRect(0, 0, ROAD_W, ROAD_H);
  ac.restore();

  // --- roughness pack: R = ambient occlusion, G = roughness, B = metalness
  const rough = makeCanvas(ROAD_W, ROAD_H);
  const rc = ctxOf(rough);
  rc.fillStyle = 'rgb(255,226,0)';
  rc.fillRect(0, 0, ROAD_W, ROAD_H);
  rc.save();
  rc.globalCompositeOperation = 'overlay';
  rc.globalAlpha = 0.4;
  rc.drawImage(height, 0, 0);
  rc.restore();
  for (const cx of [POLISH_A, POLISH_B]) {
    const grad = rc.createLinearGradient(cx - POLISH_HALF, 0, cx + POLISH_HALF, 0);
    grad.addColorStop(0, 'rgba(255,96,0,0)');
    grad.addColorStop(0.5, 'rgba(255,96,0,0.85)');
    grad.addColorStop(1, 'rgba(255,96,0,0)');
    rc.fillStyle = grad;
    rc.fillRect(cx - POLISH_HALF, 0, POLISH_HALF * 2, ROAD_H);
  }
  for (let k = 0; k <= ROAD_JOINTS; k++) {
    const y = (k * ROAD_H) / ROAD_JOINTS;
    rc.fillStyle = 'rgb(150,250,0)';
    rc.fillRect(0, y - 3, ROAD_W, 6);
  }
  rc.fillStyle = 'rgb(255,168,0)';
  vBand(rc, ROAD_W, ROAD_H, 0, 6);
  vBand(rc, ROAD_W, ROAD_H, 18, 2);
  vBand(rc, ROAD_W, ROAD_H, ROAD_W - 18, 2);

  return { albedo, height, rough };
}

/**
 * Road decals, packed as a 2x2 atlas so track.js can pick a quadrant:
 *   (0,0) forward chevrons   (1,0) sector 1
 *   (0,1) sector 2           (1,1) sector 3
 * Transparent background, clamped wrapping.
 */
function buildRoadDetail() {
  const S = 512;
  const H = S / 2;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  ctx.clearRect(0, 0, S, S);

  // Chevron quadrant, pointing along the direction of travel.
  ctx.save();
  ctx.lineCap = 'butt';
  ctx.lineJoin = 'miter';
  for (let i = 0; i < 3; i++) {
    const y = 44 + i * 62;
    ctx.strokeStyle = cssOf(PALETTE.white, 0.95 - i * 0.2);
    ctx.lineWidth = 16;
    ctx.beginPath();
    ctx.moveTo(34, y + 44);
    ctx.lineTo(H * 0.5, y);
    ctx.lineTo(H - 34, y + 44);
    ctx.stroke();
  }
  ctx.restore();

  // Sector quadrants.
  const sectors = ['1', '2', '3'];
  const cells = [
    [H, 0],
    [0, H],
    [H, H],
  ];
  for (let i = 0; i < 3; i++) {
    const ox = cells[i][0];
    const oy = cells[i][1];
    ctx.save();
    ctx.translate(ox, oy);
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'center';
    ctx.font = 'bold 40px "Arial Narrow", Arial, sans-serif';
    ctx.fillStyle = cssOf(PALETTE.white, 0.72);
    spacedText(ctx, 'SECTEUR', H * 0.5, 52, 7, 'center');
    ctx.font = 'bold 150px "Arial Narrow", Arial, sans-serif';
    ctx.fillStyle = cssOf(PALETTE.white, 0.92);
    ctx.fillText(sectors[i], H * 0.5, 150);
    ctx.strokeStyle = cssOf(PALETTE.white, 0.5);
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.moveTo(46, 208);
    ctx.lineTo(H - 46, 208);
    ctx.stroke();
    ctx.restore();
  }
  return canvas;
}

// ---------------------------------------------------------------------------
// Walls: 8 m by 4 m, 128 pixels per metre.
// ---------------------------------------------------------------------------

const WALL_W = 1024;
const WALL_H = 512;
const NEON_TOP = 206;
const NEON_BOT = 242;

function buildWall(rand) {
  const albedo = makeCanvas(WALL_W, WALL_H);
  const ac = ctxOf(albedo);
  const height = makeCanvas(WALL_W, WALL_H);
  const hc = ctxOf(height);
  const emissive = makeCanvas(WALL_W, WALL_H);
  const ec = ctxOf(emissive);

  ac.fillStyle = cssOf(PALETTE.wall);
  ac.fillRect(0, 0, WALL_W, WALL_H);
  hc.fillStyle = cssGray(120);
  hc.fillRect(0, 0, WALL_W, WALL_H);
  ec.fillStyle = '#000';
  ec.fillRect(0, 0, WALL_W, WALL_H);

  // Structural bands, top to bottom.
  const bands = [
    { y: 0, h: 18, tone: 0.55, hgt: 176 }, // capping rail
    { y: 18, h: 16, tone: -0.5, hgt: 74 }, // recessed vent channel
    { y: 196, h: 10, tone: 0.3, hgt: 158 }, // neon lip
    { y: NEON_TOP, h: NEON_BOT - NEON_TOP, tone: -1, hgt: 48 }, // neon recess
    { y: NEON_BOT, h: 10, tone: 0.3, hgt: 158 },
    { y: 396, h: 8, tone: -0.5, hgt: 78 },
    { y: 456, h: 10, tone: 0.2, hgt: 150 },
  ];
  for (const b of bands) {
    ac.fillStyle =
      b.tone >= 0 ? cssMix(PALETTE.wall, PALETTE.wallTrim, b.tone) : cssGray(0, -b.tone * 0.75);
    ac.fillRect(0, b.y, WALL_W, b.h);
    hc.fillStyle = cssGray(b.hgt);
    hc.fillRect(0, b.y, WALL_W, b.h);
  }

  // Panel rows: 4 wide up top, 4 offset by half a panel below the neon.
  const drawPanels = (top, bottom, count, offset) => {
    const pw = WALL_W / count;
    for (let i = 0; i < count; i++) {
      const x = i * pw + offset;
      const tone = 0.12 + rand() * 0.3;
      ac.save();
      ac.beginPath();
      ac.rect(0, top, WALL_W, bottom - top);
      ac.clip();
      for (const ox of [-WALL_W, 0, WALL_W]) {
        ac.fillStyle = cssMix(PALETTE.wall, PALETTE.wallTrim, tone * 0.5);
        cutRectPath(ac, x + ox + 5, top + 6, pw - 10, bottom - top - 12, 16);
        ac.fill();
        // Recessed inner channel that catches a grazing light.
        ac.fillStyle = cssGray(0, 0.35);
        ac.fillRect(x + ox + 5, top + 6, pw - 10, 4);
        ac.fillStyle = cssMix(PALETTE.wall, PALETTE.wallTrim, 0.75, 0.5);
        ac.fillRect(x + ox + 5, bottom - 12, pw - 10, 3);
      }
      ac.restore();
      hc.save();
      hc.beginPath();
      hc.rect(0, top, WALL_W, bottom - top);
      hc.clip();
      for (const ox of [-WALL_W, 0, WALL_W]) {
        hc.fillStyle = cssGray(150);
        cutRectPath(hc, x + ox + 5, top + 6, pw - 10, bottom - top - 12, 16);
        hc.fill();
        hc.fillStyle = cssGray(76);
        hc.fillRect(x + ox + 5, top + 6, pw - 10, 4);
      }
      hc.restore();
      // Bolts around the panel border.
      const bolts = [];
      for (let k = 0; k < 5; k++) {
        const bx = x + 24 + (k * (pw - 48)) / 4;
        bolts.push([bx, top + 20], [bx, bottom - 22]);
      }
      bolts.push([x + 20, (top + bottom) * 0.5], [x + pw - 20, (top + bottom) * 0.5]);
      for (const b of bolts) {
        for (const ox of [-WALL_W, 0, WALL_W]) {
          ac.beginPath();
          ac.arc(b[0] + ox, b[1], 4, 0, Math.PI * 2);
          ac.fillStyle = cssMix(PALETTE.wall, PALETTE.wallTrim, 0.9);
          ac.fill();
          ac.beginPath();
          ac.arc(b[0] + ox - 1, b[1] - 1, 1.6, 0, Math.PI * 2);
          ac.fillStyle = cssGray(120, 0.5);
          ac.fill();
          hc.beginPath();
          hc.arc(b[0] + ox, b[1], 4, 0, Math.PI * 2);
          hc.fillStyle = cssGray(196);
          hc.fill();
        }
      }
    }
  };
  drawPanels(34, 196, 4, 0);
  drawPanels(252, 396, 4, WALL_W / 8);

  // Hazard chevrons: 45 degree stripes, period divides the width so it wraps.
  const hazTop = 404;
  const hazH = 52;
  ac.save();
  ac.beginPath();
  ac.rect(0, hazTop, WALL_W, hazH);
  ac.clip();
  ac.fillStyle = cssGray(8);
  ac.fillRect(0, hazTop, WALL_W, hazH);
  ac.fillStyle = cssOf(PALETTE.amber, 0.62);
  for (let x = -hazH; x < WALL_W + 64; x += 64) {
    ac.beginPath();
    ac.moveTo(x, hazTop + hazH);
    ac.lineTo(x + hazH, hazTop);
    ac.lineTo(x + hazH + 32, hazTop);
    ac.lineTo(x + 32, hazTop + hazH);
    ac.closePath();
    ac.fill();
  }
  ac.restore();
  hc.fillStyle = cssGray(134);
  hc.fillRect(0, hazTop, WALL_W, hazH);

  // Base skirt: grime rising from the ground.
  const skirt = ac.createLinearGradient(0, WALL_H - 70, 0, WALL_H);
  skirt.addColorStop(0, cssGray(0, 0));
  skirt.addColorStop(1, cssGray(0, 0.7));
  ac.fillStyle = skirt;
  ac.fillRect(0, WALL_H - 70, WALL_W, 70);

  // The neon channel is pure black in the albedo, the light lives in emissive.
  ac.fillStyle = '#000';
  ac.fillRect(0, NEON_TOP, WALL_W, NEON_BOT - NEON_TOP);

  // Surface grain, shared between albedo and height.
  const grain = noiseTile(rand, 256, 96, 160);
  patternFill(ac, grain, WALL_W, WALL_H, 0.16, 'overlay');
  patternFill(hc, grain, WALL_W, WALL_H, 0.3, 'overlay');

  // --- emissive: one cyan channel, plus small service indicators
  const neonY = (NEON_TOP + NEON_BOT) * 0.5;
  const glow = ec.createLinearGradient(0, NEON_TOP - 6, 0, NEON_BOT + 6);
  glow.addColorStop(0, cssOf(PALETTE.cyan, 0));
  glow.addColorStop(0.5, cssOf(PALETTE.cyan, 0.55));
  glow.addColorStop(1, cssOf(PALETTE.cyan, 0));
  ec.fillStyle = glow;
  ec.fillRect(0, NEON_TOP - 6, WALL_W, NEON_BOT - NEON_TOP + 12);
  ec.fillStyle = cssOf(PALETTE.cyan);
  ec.fillRect(0, neonY - 7, WALL_W, 14);
  ec.fillStyle = cssOf(PALETTE.white);
  ec.fillRect(0, neonY - 3, WALL_W, 6);
  // Segment breaks so the strip reads as a run of tubes.
  ec.fillStyle = '#000';
  for (let x = 0; x < WALL_W; x += 128) ec.fillRect(x - 3, NEON_TOP, 6, NEON_BOT - NEON_TOP);
  // Indicator dots on the capping rail and above the hazard band.
  for (let x = 64; x < WALL_W; x += 128) {
    ec.fillStyle = cssOf(PALETTE.magenta, 0.9);
    ec.beginPath();
    ec.arc(x, 9, 4, 0, Math.PI * 2);
    ec.fill();
    ec.fillStyle = cssOf(PALETTE.amber, 0.8);
    ec.fillRect(x - 22, 398, 44, 4);
  }

  return { albedo, height, emissive };
}

// ---------------------------------------------------------------------------
// Edge strip, boost pad, checker, grid
// ---------------------------------------------------------------------------

function buildEdgeStrip() {
  const W = 32;
  const H = 256;
  const canvas = makeCanvas(W, H);
  const ctx = ctxOf(canvas);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, W, H);
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0.0, cssGray(0));
  grad.addColorStop(0.18, cssOf(PALETTE.cyan, 0.25));
  grad.addColorStop(0.4, cssOf(PALETTE.cyan, 0.9));
  grad.addColorStop(0.5, cssOf(PALETTE.white));
  grad.addColorStop(0.6, cssOf(PALETTE.cyan, 0.9));
  grad.addColorStop(0.82, cssOf(PALETTE.cyan, 0.25));
  grad.addColorStop(1.0, cssGray(0));
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, H);
  return canvas;
}

function buildBoostPad() {
  const W = 256;
  const H = 768; // 9 m by 26 m plate
  const canvas = makeCanvas(W, H);
  const ctx = ctxOf(canvas);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, W, H);

  // Base plate wash so the whole pad glows a little.
  const wash = ctx.createLinearGradient(0, 0, 0, H);
  wash.addColorStop(0, cssOf(PALETTE.cyan, 0.0));
  wash.addColorStop(0.5, cssOf(PALETTE.cyan, 0.22));
  wash.addColorStop(1, cssOf(PALETTE.cyan, 0.0));
  ctx.fillStyle = wash;
  ctx.fillRect(0, 0, W, H);

  // Stacked forward chevrons, brighter towards the exit of the pad.
  ctx.lineCap = 'butt';
  ctx.lineJoin = 'miter';
  const count = 6;
  for (let i = 0; i < count; i++) {
    const t = i / (count - 1);
    const y = 90 + i * 108;
    ctx.strokeStyle = cssMix(PALETTE.cyan, PALETTE.white, 0.35 + t * 0.65, 0.35 + t * 0.65);
    ctx.lineWidth = 26;
    ctx.beginPath();
    ctx.moveTo(34, y + 62);
    ctx.lineTo(W * 0.5, y);
    ctx.lineTo(W - 34, y + 62);
    ctx.stroke();
    ctx.strokeStyle = cssOf(PALETTE.white, 0.28 + t * 0.6);
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.moveTo(34, y + 62);
    ctx.lineTo(W * 0.5, y);
    ctx.lineTo(W - 34, y + 62);
    ctx.stroke();
  }

  // Rails along the long edges.
  ctx.fillStyle = cssOf(PALETTE.cyan, 0.85);
  ctx.fillRect(8, 24, 7, H - 48);
  ctx.fillRect(W - 15, 24, 7, H - 48);

  // Soft falloff so the plate melts into the asphalt instead of cutting out.
  ctx.save();
  ctx.globalCompositeOperation = 'multiply';
  const fadeY = ctx.createLinearGradient(0, 0, 0, H);
  fadeY.addColorStop(0, '#000');
  fadeY.addColorStop(0.09, '#fff');
  fadeY.addColorStop(0.91, '#fff');
  fadeY.addColorStop(1, '#000');
  ctx.fillStyle = fadeY;
  ctx.fillRect(0, 0, W, H);
  const fadeX = ctx.createLinearGradient(0, 0, W, 0);
  fadeX.addColorStop(0, '#000');
  fadeX.addColorStop(0.07, '#fff');
  fadeX.addColorStop(0.93, '#fff');
  fadeX.addColorStop(1, '#000');
  ctx.fillStyle = fadeX;
  ctx.fillRect(0, 0, W, H);
  ctx.restore();
  return canvas;
}

function buildChecker() {
  const S = 256;
  const cells = 8;
  const cell = S / cells;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, S, S);
  ctx.fillStyle = '#ffffff';
  for (let y = 0; y < cells; y++) {
    for (let x = 0; x < cells; x++) {
      if ((x + y) % 2 === 0) ctx.fillRect(x * cell, y * cell, cell, cell);
    }
  }
  return canvas;
}

function buildGrid() {
  const S = 512;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  ctx.fillStyle = cssOf(PALETTE.ground);
  ctx.fillRect(0, 0, S, S);

  // Faint subdivisions first, main lines on top.
  ctx.strokeStyle = cssOf(PALETTE.cyan, 0.1);
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 1; i < 4; i++) {
    const p = (i * S) / 4;
    ctx.moveTo(p, 0);
    ctx.lineTo(p, S);
    ctx.moveTo(0, p);
    ctx.lineTo(S, p);
  }
  ctx.stroke();

  ctx.save();
  ctx.shadowColor = cssOf(PALETTE.cyan, 0.9);
  ctx.shadowBlur = 14;
  ctx.strokeStyle = cssOf(PALETTE.cyan, 0.85);
  ctx.lineWidth = 3;
  ctx.beginPath();
  for (const p of [0.5, S - 0.5]) {
    ctx.moveTo(p, 0);
    ctx.lineTo(p, S);
    ctx.moveTo(0, p);
    ctx.lineTo(S, p);
  }
  ctx.stroke();
  ctx.restore();

  // Node markers where lines cross.
  ctx.fillStyle = cssOf(PALETTE.white, 0.7);
  for (const x of [0, S]) {
    for (const y of [0, S]) ctx.fillRect(x - 4, y - 4, 8, 8);
  }
  return canvas;
}

// ---------------------------------------------------------------------------
// Ship hull: 1024 square, 4x4 plate cells so the layout wraps.
// ---------------------------------------------------------------------------

const HULL_S = 1024;
const HULL_CELLS = 4;

function buildHull(rand) {
  const cell = HULL_S / HULL_CELLS;
  const albedo = makeCanvas(HULL_S, HULL_S);
  const ac = ctxOf(albedo);
  const height = makeCanvas(HULL_S, HULL_S);
  const hc = ctxOf(height);
  const emissive = makeCanvas(HULL_S, HULL_S);
  const ec = ctxOf(emissive);

  ac.fillStyle = 'rgb(74,80,92)';
  ac.fillRect(0, 0, HULL_S, HULL_S);
  hc.fillStyle = cssGray(112);
  hc.fillRect(0, 0, HULL_S, HULL_S);
  ec.fillStyle = '#000';
  ec.fillRect(0, 0, HULL_S, HULL_S);

  // Brushed metal, applied to both albedo and height so they agree.
  const brushed = brushTile(rand, 512, 104, 152);
  patternFill(ac, brushed, HULL_S, HULL_S, 0.55, 'overlay');
  patternFill(hc, brushed, HULL_S, HULL_S, 0.22, 'overlay');

  // Plates: one per cell, inset so the groove between them wraps cleanly.
  for (let cy = 0; cy < HULL_CELLS; cy++) {
    for (let cx = 0; cx < HULL_CELLS; cx++) {
      const x = cx * cell;
      const y = cy * cell;
      const inset = 7;
      const tone = 0.86 + rand() * 0.3;
      ac.save();
      ac.globalAlpha = 0.5;
      ac.fillStyle = 'rgb(' + Math.round(74 * tone) + ',' + Math.round(80 * tone) + ',' + Math.round(92 * tone) + ')';
      cutRectPath(ac, x + inset, y + inset, cell - inset * 2, cell - inset * 2, 26);
      ac.fill();
      ac.restore();
      // Groove and its lit lip.
      ac.strokeStyle = 'rgba(12,14,20,0.85)';
      ac.lineWidth = 3;
      cutRectPath(ac, x + inset, y + inset, cell - inset * 2, cell - inset * 2, 26);
      ac.stroke();
      ac.strokeStyle = 'rgba(180,192,210,0.22)';
      ac.lineWidth = 1.5;
      cutRectPath(ac, x + inset + 2.5, y + inset + 2.5, cell - inset * 2 - 5, cell - inset * 2 - 5, 24);
      ac.stroke();

      hc.fillStyle = cssGray(146);
      cutRectPath(hc, x + inset, y + inset, cell - inset * 2, cell - inset * 2, 26);
      hc.fill();
      hc.strokeStyle = cssGray(58);
      hc.lineWidth = 4;
      cutRectPath(hc, x + inset, y + inset, cell - inset * 2, cell - inset * 2, 26);
      hc.stroke();

      // One internal split line per plate, kept inside the cell.
      if (rand() < 0.6) {
        const split = y + inset + 30 + rand() * (cell - inset * 2 - 60);
        ac.strokeStyle = 'rgba(14,16,22,0.7)';
        ac.lineWidth = 2;
        ac.beginPath();
        ac.moveTo(x + inset + 14, split);
        ac.lineTo(x + cell - inset - 14, split);
        ac.stroke();
        hc.strokeStyle = cssGray(84);
        hc.lineWidth = 3;
        hc.beginPath();
        hc.moveTo(x + inset + 14, split);
        hc.lineTo(x + cell - inset - 14, split);
        hc.stroke();
      }

      // Rivets along the plate border.
      const steps = 7;
      for (let k = 0; k < steps; k++) {
        const t = (k + 0.5) / steps;
        const px = x + inset + 16 + t * (cell - inset * 2 - 32);
        const py = y + inset + 16 + t * (cell - inset * 2 - 32);
        const spots = [
          [px, y + inset + 14],
          [px, y + cell - inset - 14],
          [x + inset + 14, py],
          [x + cell - inset - 14, py],
        ];
        for (const s of spots) {
          ac.beginPath();
          ac.arc(s[0], s[1], 3.2, 0, Math.PI * 2);
          ac.fillStyle = 'rgba(150,160,178,0.55)';
          ac.fill();
          ac.beginPath();
          ac.arc(s[0] + 1, s[1] + 1, 3.2, 0, Math.PI * 2);
          ac.fillStyle = 'rgba(10,12,18,0.4)';
          ac.fill();
          hc.beginPath();
          hc.arc(s[0], s[1], 3.4, 0, Math.PI * 2);
          hc.fillStyle = cssGray(190);
          hc.fill();
        }
      }
    }
  }

  // Stencilled markings. French, no accents so the canvas font never fails.
  const marks = [
    { t: 'V-07', s: 62, cx: 0, cy: 0, c: 'rgba(210,220,236,0.62)', sp: 3 },
    { t: 'DANGER', s: 40, cx: 1, cy: 0, c: 'rgba(255,176,32,0.6)', sp: 5 },
    { t: 'REACTEUR', s: 30, cx: 2, cy: 0, c: 'rgba(200,212,230,0.45)', sp: 4 },
    { t: '228', s: 74, cx: 3, cy: 1, c: 'rgba(210,220,236,0.5)', sp: 4 },
    { t: 'NE PAS TOUCHER', s: 24, cx: 1, cy: 2, c: 'rgba(255,59,48,0.55)', sp: 3 },
    { t: 'CARBURANT', s: 28, cx: 3, cy: 2, c: 'rgba(200,212,230,0.4)', sp: 4 },
    { t: 'AKARI', s: 44, cx: 0, cy: 3, c: 'rgba(200,212,230,0.5)', sp: 6 },
    { t: 'PRESSION 4.2', s: 22, cx: 2, cy: 3, c: 'rgba(200,212,230,0.38)', sp: 2 },
  ];
  ac.textBaseline = 'middle';
  for (const m of marks) {
    ac.font = 'bold ' + m.s + 'px "Arial Narrow", Arial, sans-serif';
    ac.fillStyle = m.c;
    spacedText(ac, m.t, m.cx * cell + cell * 0.5, m.cy * cell + cell * 0.5, m.sp, 'center');
    hc.font = ac.font;
    hc.fillStyle = cssGray(132);
    spacedText(hc, m.t, m.cx * cell + cell * 0.5, m.cy * cell + cell * 0.5, m.sp, 'center');
  }

  // Grime in the grooves.
  const dirt = noiseTile(rand, 256, 110, 146);
  patternFill(ac, dirt, HULL_S, HULL_S, 0.12, 'overlay');

  // --- emissive: white stripes and glyphs, tinted per livery by ship.js
  ec.fillStyle = '#ffffff';
  ec.fillRect(0, cell * 1.86, HULL_S, 26);
  ec.fillRect(0, cell * 1.86 + 36, HULL_S, 9);
  ec.fillStyle = 'rgba(255,255,255,0.55)';
  ec.fillRect(0, cell * 0.44, HULL_S, 6);
  ec.fillRect(0, cell * 3.52, HULL_S, 10);
  // Lit vents down each plate column boundary.
  ec.fillStyle = 'rgba(255,255,255,0.75)';
  for (let cx = 0; cx < HULL_CELLS; cx++) {
    for (let k = 0; k < 4; k++) {
      ec.fillRect(cx * cell + 40 + k * 22, cell * 2.62, 9, 58);
    }
  }
  // Chevron logo, repeated once per column so it wraps.
  ec.strokeStyle = 'rgba(255,255,255,0.9)';
  ec.lineWidth = 10;
  ec.lineJoin = 'miter';
  for (let cx = 0; cx < HULL_CELLS; cx++) {
    const bx = cx * cell + cell * 0.5;
    ec.beginPath();
    ec.moveTo(bx - 52, cell * 3.16);
    ec.lineTo(bx, cell * 3.16 + 42);
    ec.lineTo(bx + 52, cell * 3.16);
    ec.stroke();
  }

  return { albedo, height, emissive };
}

function buildCockpit(rand) {
  const S = 512;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);

  // Smoked glass base, darker at the top where it sees the night sky.
  const base = ctx.createLinearGradient(0, 0, 0, S);
  base.addColorStop(0, 'rgb(6,8,14)');
  base.addColorStop(0.55, 'rgb(12,16,26)');
  base.addColorStop(1, 'rgb(4,5,9)');
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, S, S);

  // Broad diagonal reflections of the city lights.
  ctx.save();
  ctx.translate(S * 0.5, S * 0.5);
  ctx.rotate(-0.55);
  for (let i = 0; i < 4; i++) {
    const w = 26 + rand() * 90;
    const x = -S * 0.7 + i * (S * 0.42) + rand() * 40;
    const grad = ctx.createLinearGradient(x - w, 0, x + w, 0);
    grad.addColorStop(0, cssOf(PALETTE.cyan, 0));
    grad.addColorStop(0.5, cssOf(PALETTE.white, 0.055 + rand() * 0.07));
    grad.addColorStop(1, cssOf(PALETTE.cyan, 0));
    ctx.fillStyle = grad;
    ctx.fillRect(x - w, -S, w * 2, S * 2);
  }
  ctx.restore();

  // Soft sheen in the upper left, the usual canopy highlight.
  const sheen = ctx.createRadialGradient(S * 0.32, S * 0.24, 0, S * 0.32, S * 0.24, S * 0.6);
  sheen.addColorStop(0, cssOf(PALETTE.white, 0.11));
  sheen.addColorStop(1, cssOf(PALETTE.white, 0));
  ctx.fillStyle = sheen;
  ctx.fillRect(0, 0, S, S);

  // Frame darkening around the edges plus a thin tint band at the top.
  const edge = ctx.createRadialGradient(S * 0.5, S * 0.5, S * 0.3, S * 0.5, S * 0.5, S * 0.72);
  edge.addColorStop(0, 'rgba(0,0,0,0)');
  edge.addColorStop(1, 'rgba(0,0,0,0.75)');
  ctx.fillStyle = edge;
  ctx.fillRect(0, 0, S, S);
  const tint = ctx.createLinearGradient(0, 0, 0, S * 0.22);
  tint.addColorStop(0, cssOf(PALETTE.violet, 0.22));
  tint.addColorStop(1, cssOf(PALETTE.violet, 0));
  ctx.fillStyle = tint;
  ctx.fillRect(0, 0, S, S * 0.22);

  // Fine horizontal scan reflections.
  ctx.fillStyle = cssOf(PALETTE.white, 0.025);
  for (let y = 0; y < S; y += 6) ctx.fillRect(0, y, S, 1);
  return canvas;
}

// ---------------------------------------------------------------------------
// City facade and billboards
// ---------------------------------------------------------------------------

/**
 * Facade tint pools. The first entries repeat on purpose: a facade reads as
 * "an office tower" or "a housing block" because one tint dominates, with the
 * other two only sprinkled in.
 */
const FACADE_TINTS = {
  office: [
    PALETTE.cityCold,
    PALETTE.cityCold,
    0x8fc4ff,
    0xd8ecff,
    PALETTE.cityGreen,
    PALETTE.cityWarm,
  ],
  warm: [
    PALETTE.cityWarm,
    PALETTE.cityWarm,
    0xffd39a,
    0xff9a5a,
    PALETTE.cityGreen,
    PALETTE.cityCold,
  ],
  slim: [
    PALETTE.cityCold,
    0xbfe6ff,
    PALETTE.cityCold,
    0x7fb4ff,
    PALETTE.cityGreen,
    PALETTE.cityWarm,
  ],
};

/**
 * Paints one 512 square skyscraper facade, albedo plus emissive.
 *
 * cfg fields:
 *   cols, rows      window grid pitch, both must divide 512 evenly
 *   style           'grid' punched openings, 'balcony' flats with ledges,
 *                   'ribbon' continuous glazing cut by thin mullions
 *   tints           tint pool, dominant colour first
 *   lit             probability that a single window is on
 *   fullFloors      how many floors are lit end to end (lobbies, plant rooms)
 *   base, trim      concrete tones of the structure
 *   glass           unlit pane colour
 *
 * The three variants must stay clearly different at distance, otherwise the
 * instanced city reads as one building copied hundreds of times: that is why
 * the pitch, the lit density and the dominant tint all change together.
 */
function buildFacade(rand, cfg) {
  const S = 512;
  const cols = cfg.cols;
  const rows = cfg.rows;
  const cw = S / cols;
  const rh = S / rows;
  const albedo = makeCanvas(S, S);
  const ac = ctxOf(albedo);
  const emissive = makeCanvas(S, S);
  const ec = ctxOf(emissive);

  ac.fillStyle = cssOf(cfg.base);
  ac.fillRect(0, 0, S, S);
  ec.fillStyle = '#000';
  ec.fillRect(0, 0, S, S);

  // Spandrel panels: the opaque strip of wall between two glazing rows. Two
  // alternating tones, a lit top lip and a cast shadow underneath give the
  // facade relief even on the floors where nothing is switched on.
  const spandrel = Math.max(3, Math.round(rh * 0.17));
  for (let r = 0; r < rows; r++) {
    const y = r * rh;
    ac.fillStyle = cssMix(cfg.base, cfg.trim, r % 2 === 0 ? 0.62 : 0.34);
    ac.fillRect(0, y, S, spandrel);
    ac.fillStyle = cssGray(255, 0.055);
    ac.fillRect(0, y, S, 1);
    ac.fillStyle = cssGray(0, 0.42);
    ac.fillRect(0, y + spandrel, S, 2);
  }

  // Service core: one blind column, no glazing, vents and an access ladder.
  const core = 1 + ((rand() * (cols - 2)) | 0);
  const coreX = core * cw;
  ac.fillStyle = cssMix(cfg.base, cfg.trim, 0.5);
  ac.fillRect(coreX, 0, cw, S);
  ac.fillStyle = cssGray(0, 0.3);
  ac.fillRect(coreX, 0, 3, S);
  ac.fillRect(coreX + cw - 3, 0, 3, S);
  for (let y = 6; y < S; y += 9) {
    ac.fillStyle = cssGray(0, 0.34);
    ac.fillRect(coreX + 5, y, cw - 10, 3);
  }
  ac.fillStyle = cssGray(200, 0.1);
  ac.fillRect(coreX + cw * 0.5 - 1, 0, 2, S);

  // Floors that are lit end to end. Picked before the loop so the whole row
  // agrees with itself.
  const fullFloors = [];
  for (let i = 0; i < cfg.fullFloors; i++) fullFloors.push((rand() * rows) | 0);

  const insetX = cfg.style === 'ribbon' ? 1.5 : Math.max(3, cw * 0.13);
  const winTop = spandrel + Math.max(2, rh * 0.08);
  const winH = Math.max(4, rh - winTop - Math.max(2, rh * 0.1));

  for (let r = 0; r < rows; r++) {
    const full = fullFloors.indexOf(r) >= 0;
    for (let c = 0; c < cols; c++) {
      if (c === core) continue;
      const x = c * cw + insetX;
      const y = r * rh + winTop;
      const w = cw - insetX * 2;
      const h = winH;

      // Unlit glass: a dark pane with a faint sky reflection along its top.
      ac.fillStyle = cssOf(cfg.glass);
      ac.fillRect(x, y, w, h);
      ac.fillStyle = 'rgba(44,58,96,0.32)';
      ac.fillRect(x, y, w, Math.max(2, h * 0.3));
      ac.fillStyle = cssGray(0, 0.4);
      ac.fillRect(x, y + h - 2, w, 2);

      // Balcony variant: a ledge under every opening plus a railing.
      if (cfg.style === 'balcony') {
        ac.fillStyle = cssMix(cfg.base, cfg.trim, 0.8);
        ac.fillRect(c * cw + 1, y + h, cw - 2, 3);
        ac.fillStyle = cssGray(0, 0.5);
        ac.fillRect(c * cw + 1, y + h + 3, cw - 2, 2);
        ac.fillStyle = cssGray(190, 0.14);
        ac.fillRect(c * cw + 2, y + h - 4, cw - 4, 1);
      }

      const lit = full || rand() < cfg.lit;
      if (!lit) continue;

      const tint = cfg.tints[(rand() * cfg.tints.length) | 0];
      // Deliberately moderate: density goes up, per window output does not,
      // so the skyline gains detail without gaining brightness.
      const level = 0.3 + rand() * 0.5;
      // Some rooms are only half lit, which reads far better from a distance.
      const hh = !full && rand() < 0.28 ? h * (0.4 + rand() * 0.35) : h;
      const yy = y + (h - hh);

      ac.fillStyle = cssOf(tint, 0.34 * level);
      ac.fillRect(x, yy, w, hh);
      ec.fillStyle = cssOf(tint, level);
      ec.fillRect(x, yy, w, hh);
      // A pane divider or two: a lit window is never a flat rectangle.
      if (w > 12) {
        ec.fillStyle = cssGray(0, 0.4);
        ec.fillRect(x + w * 0.5 - 1, yy, 2, hh);
        ac.fillStyle = cssGray(0, 0.45);
        ac.fillRect(x + w * 0.5 - 1, yy, 2, hh);
      }
      // Slight bleed so the bloom has something soft to grab.
      ec.save();
      ec.globalAlpha = 0.3 * level;
      ec.fillStyle = cssOf(tint);
      ec.fillRect(x - 2, yy - 2, w + 4, hh + 4);
      ec.restore();
    }
  }

  // Vertical mullions. Drawn at c = 0 and c = cols so the pair straddles the
  // horizontal seam and forms one continuous member once the tile wraps.
  const mullion = cfg.style === 'ribbon' ? 3 : 4;
  ac.fillStyle = cssMix(cfg.base, cfg.trim, 0.22, 0.92);
  for (let c = 0; c <= cols; c++) ac.fillRect(c * cw - mullion * 0.5, 0, mullion, S);
  ec.fillStyle = 'rgba(0,0,0,0.85)';
  for (let c = 0; c <= cols; c++) ec.fillRect(c * cw - mullion * 0.5, 0, mullion, S);
  if (cfg.style === 'ribbon') {
    // Ribbon glazing gets extra hairline mullions inside every bay.
    ac.fillStyle = cssGray(0, 0.55);
    ec.fillStyle = 'rgba(0,0,0,0.7)';
    for (let c = 0; c < cols; c++) {
      const x = c * cw + cw * 0.5;
      ac.fillRect(x, 0, 1, S);
      ec.fillRect(x, 0, 1, S);
    }
  }

  // Vertical grime: rain washing down the concrete, strongest under the
  // spandrels. Kept off the seams so the tile stays clean at the border.
  ac.save();
  for (let i = 0; i < 26; i++) {
    const x = 6 + rand() * (S - 12);
    const w = 2 + rand() * 7;
    const top = rand() * S;
    const len = 40 + rand() * 190;
    const g = ac.createLinearGradient(0, top, 0, top + len);
    g.addColorStop(0, cssGray(0, 0.22));
    g.addColorStop(1, cssGray(0, 0));
    ac.fillStyle = g;
    ac.fillRect(x, top, w, len);
  }
  ac.restore();
  // Overall soot gradient, dirtier at the base of the tower.
  const soot = ac.createLinearGradient(0, 0, 0, S);
  soot.addColorStop(0, cssGray(0, 0));
  soot.addColorStop(0.72, cssGray(0, 0.1));
  soot.addColorStop(1, cssGray(0, 0.28));
  ac.fillStyle = soot;
  ac.fillRect(0, 0, S, S);

  const grime = noiseTile(rand, 128, 100, 156);
  patternFill(ac, grime, S, S, 0.16, 'overlay');
  return { albedo, emissive };
}

/**
 * Rooftop deck seen from a craft flying above: vents, water tanks, a helipad,
 * antenna bases and a parapet that survives the wrap because both borders of
 * the tile carry the same rail.
 */
function buildRooftop(rand) {
  const S = 512;
  const albedo = makeCanvas(S, S);
  const ac = ctxOf(albedo);
  const emissive = makeCanvas(S, S);
  const ec = ctxOf(emissive);

  ac.fillStyle = 'rgb(23,24,32)';
  ac.fillRect(0, 0, S, S);
  ec.fillStyle = '#000';
  ec.fillRect(0, 0, S, S);

  // Weathering: pools of dried grime over the membrane.
  const stains = [];
  for (let i = 0; i < 9; i++) {
    stains.push({ x: rand() * S, y: rand() * S, r: 50 + rand() * 120, a: 0.06 + rand() * 0.1 });
  }
  wrapDraw(ac, S, S, (c) => {
    for (const p of stains) {
      const g = c.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r);
      g.addColorStop(0, rand() < 0.5 ? cssGray(0, p.a) : cssGray(90, p.a));
      g.addColorStop(1, cssGray(0, 0));
      c.fillStyle = g;
      c.fillRect(p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);
    }
  });

  // Expansion seams of the deck.
  ac.strokeStyle = cssGray(0, 0.35);
  ac.lineWidth = 2;
  ac.beginPath();
  for (let i = 1; i < 4; i++) {
    ac.moveTo((i * S) / 4, 0);
    ac.lineTo((i * S) / 4, S);
    ac.moveTo(0, (i * S) / 4);
    ac.lineTo(S, (i * S) / 4);
  }
  ac.stroke();

  // Helipad: painted circle with a big H, worn at the edges.
  const hx = 168;
  const hy = 344;
  const hr = 96;
  ac.fillStyle = 'rgb(17,18,25)';
  ac.beginPath();
  ac.arc(hx, hy, hr, 0, Math.PI * 2);
  ac.fill();
  ac.strokeStyle = 'rgba(214,222,236,0.5)';
  ac.lineWidth = 8;
  ac.beginPath();
  ac.arc(hx, hy, hr - 12, 0, Math.PI * 2);
  ac.stroke();
  ac.fillStyle = 'rgba(214,222,236,0.55)';
  ac.fillRect(hx - 38, hy - 44, 15, 88);
  ac.fillRect(hx + 23, hy - 44, 15, 88);
  ac.fillRect(hx - 38, hy - 8, 76, 16);

  // Water tanks: squat cylinders with a lit top and a cast shadow.
  for (let i = 0; i < 3; i++) {
    const cx = 300 + i * 68 + rand() * 12;
    const cy = 120 + rand() * 60;
    const r = 26 + rand() * 10;
    ac.fillStyle = cssGray(0, 0.45);
    ac.beginPath();
    ac.ellipse(cx + 7, cy + 8, r, r * 0.9, 0, 0, Math.PI * 2);
    ac.fill();
    const g = ac.createRadialGradient(cx - r * 0.4, cy - r * 0.4, 2, cx, cy, r);
    g.addColorStop(0, 'rgb(62,64,76)');
    g.addColorStop(1, 'rgb(28,29,38)');
    ac.fillStyle = g;
    ac.beginPath();
    ac.arc(cx, cy, r, 0, Math.PI * 2);
    ac.fill();
    ac.strokeStyle = cssGray(0, 0.5);
    ac.lineWidth = 2;
    ac.beginPath();
    ac.arc(cx, cy, r * 0.55, 0, Math.PI * 2);
    ac.stroke();
  }

  // Air handling units: boxes with slatted tops.
  for (let i = 0; i < 5; i++) {
    const x = 20 + rand() * (S - 140);
    const y = 20 + rand() * (S - 140);
    const w = 42 + rand() * 56;
    const h = 30 + rand() * 40;
    ac.fillStyle = cssGray(0, 0.5);
    ac.fillRect(x + 6, y + 7, w, h);
    ac.fillStyle = 'rgb(40,42,52)';
    ac.fillRect(x, y, w, h);
    ac.fillStyle = 'rgb(52,55,66)';
    ac.fillRect(x, y, w, 3);
    ac.fillStyle = cssGray(0, 0.4);
    for (let k = 6; k < h - 4; k += 6) ac.fillRect(x + 4, y + k, w - 8, 3);
  }

  // Antenna bases: a small plinth with four guy wires.
  const masts = [];
  for (let i = 0; i < 4; i++) {
    const x = 40 + rand() * (S - 80);
    const y = 40 + rand() * (S - 80);
    masts.push([x, y]);
    ac.strokeStyle = cssGray(150, 0.16);
    ac.lineWidth = 1;
    ac.beginPath();
    for (let k = 0; k < 4; k++) {
      const a = (k / 4) * Math.PI * 2 + 0.4;
      ac.moveTo(x, y);
      ac.lineTo(x + Math.cos(a) * 34, y + Math.sin(a) * 34);
    }
    ac.stroke();
    ac.fillStyle = 'rgb(48,50,60)';
    ac.fillRect(x - 8, y - 8, 16, 16);
    ac.fillStyle = cssGray(0, 0.55);
    ac.fillRect(x - 4, y - 4, 8, 8);
  }

  // Parapet, drawn last: both borders carry the same rail, so it tiles.
  const rail = 16;
  ac.fillStyle = 'rgb(36,38,48)';
  ac.fillRect(0, 0, S, rail);
  ac.fillRect(0, S - rail, S, rail);
  ac.fillRect(0, 0, rail, S);
  ac.fillRect(S - rail, 0, rail, S);
  ac.fillStyle = cssGray(120, 0.16);
  ac.fillRect(0, 0, S, 2);
  ac.fillRect(0, S - 2, S, 2);
  ac.fillRect(0, 0, 2, S);
  ac.fillRect(S - 2, 0, 2, S);
  ac.fillStyle = cssGray(0, 0.5);
  ac.fillRect(0, rail, S, 3);
  ac.fillRect(0, S - rail - 3, S, 3);

  const grit = noiseTile(rand, 128, 104, 152);
  patternFill(ac, grit, S, S, 0.2, 'overlay');

  // --- emissive: only the few things that are genuinely powered at night.
  ec.strokeStyle = cssOf(PALETTE.amber, 0.5);
  ec.lineWidth = 5;
  ec.beginPath();
  ec.arc(hx, hy, hr - 12, 0, Math.PI * 2);
  ec.stroke();
  ec.fillStyle = cssOf(PALETTE.white, 0.28);
  ec.fillRect(hx - 38, hy - 44, 15, 88);
  ec.fillRect(hx + 23, hy - 44, 15, 88);
  ec.fillRect(hx - 38, hy - 8, 76, 16);
  // Approach lamps around the pad.
  for (let k = 0; k < 8; k++) {
    const a = (k / 8) * Math.PI * 2;
    const x = hx + Math.cos(a) * (hr + 10);
    const y = hy + Math.sin(a) * (hr + 10);
    ec.fillStyle = cssOf(PALETTE.amber, 0.85);
    ec.beginPath();
    ec.arc(x, y, 3, 0, Math.PI * 2);
    ec.fill();
  }
  // Red obstruction lights on the masts and at the parapet corners.
  const lamps = masts.concat([[rail, rail], [S - rail, rail], [rail, S - rail], [S - rail, S - rail]]);
  for (const p of lamps) {
    const g = ec.createRadialGradient(p[0], p[1], 0, p[0], p[1], 12);
    g.addColorStop(0, cssOf(PALETTE.red, 0.9));
    g.addColorStop(0.35, cssOf(PALETTE.red, 0.35));
    g.addColorStop(1, cssOf(PALETTE.red, 0));
    ec.fillStyle = g;
    ec.fillRect(p[0] - 12, p[1] - 12, 24, 24);
  }
  // A pair of green service lamps by the deck hatch.
  ec.fillStyle = cssOf(PALETTE.cityGreen, 0.7);
  ec.fillRect(430, 430, 6, 6);
  ec.fillRect(452, 430, 6, 6);

  return { albedo, emissive };
}

/**
 * Tall vertical neon sign bolted to a facade. Transparent background, clamped
 * wrapping, big readable type. In world French, without accents.
 */
function buildFacadeSign(rand) {
  const W = 256;
  const H = 1024;
  const canvas = makeCanvas(W, H);
  const ctx = ctxOf(canvas);
  ctx.clearRect(0, 0, W, H);

  // Backing box, barely visible, so the letters are not floating in the void.
  ctx.fillStyle = 'rgba(8,6,18,0.72)';
  roundedRectPath(ctx, 40, 24, W - 80, H - 48, 22);
  ctx.fill();

  // Neon tube outline, twice: a wide soft pass then a tight bright core.
  ctx.save();
  ctx.shadowColor = cssOf(PALETTE.citySign, 0.9);
  ctx.shadowBlur = 30;
  ctx.strokeStyle = cssOf(PALETTE.citySign, 0.85);
  ctx.lineWidth = 7;
  roundedRectPath(ctx, 52, 36, W - 104, H - 72, 18);
  ctx.stroke();
  ctx.shadowBlur = 10;
  ctx.strokeStyle = cssOf(PALETTE.white, 0.75);
  ctx.lineWidth = 2;
  roundedRectPath(ctx, 52, 36, W - 104, H - 72, 18);
  ctx.stroke();
  ctx.restore();

  // Stacked letters of the brand.
  const word = 'SAKURA';
  const step = (H - 260) / word.length;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.save();
  ctx.shadowColor = cssOf(PALETTE.citySign, 0.95);
  ctx.shadowBlur = 26;
  ctx.font = 'bold 104px "Arial Narrow", Arial, sans-serif';
  for (let i = 0; i < word.length; i++) {
    const y = 128 + step * (i + 0.5);
    ctx.fillStyle = cssOf(PALETTE.white, 0.92);
    ctx.fillText(word[i], W * 0.5, y);
    ctx.fillStyle = cssOf(PALETTE.citySign, 0.45);
    ctx.fillText(word[i], W * 0.5, y + 3);
  }
  ctx.restore();

  // Footer plate and a top lamp.
  ctx.save();
  ctx.shadowColor = cssOf(PALETTE.cyan, 0.9);
  ctx.shadowBlur = 18;
  ctx.fillStyle = cssOf(PALETTE.cyan, 0.9);
  ctx.font = 'bold 40px "Arial Narrow", Arial, sans-serif';
  spacedText(ctx, 'NUIT 24H', W * 0.5, H - 96, 5, 'center');
  ctx.fillStyle = cssOf(PALETTE.cyan, 0.75);
  ctx.fillRect(70, H - 66, W - 140, 4);
  ctx.beginPath();
  ctx.arc(W * 0.5, 78, 9, 0, Math.PI * 2);
  ctx.fillStyle = cssOf(PALETTE.amber, 0.9);
  ctx.fill();
  ctx.restore();

  // Dead tube segments: a real sign is never perfectly maintained.
  ctx.save();
  ctx.globalCompositeOperation = 'destination-out';
  for (let i = 0; i < 5; i++) {
    ctx.fillStyle = 'rgba(0,0,0,' + (0.25 + rand() * 0.4) + ')';
    ctx.fillRect(52, 60 + rand() * (H - 160), W - 104, 3 + rand() * 6);
  }
  ctx.restore();
  return canvas;
}

/**
 * Top down city block plan, seen from a craft. Irregular avenue spacing and
 * unequal parcels keep the repeat from reading as a checkerboard over the
 * hundreds of metres this tile covers.
 */
function buildCityGround(rand) {
  const S = 512;
  const albedo = makeCanvas(S, S);
  const ac = ctxOf(albedo);
  const emissive = makeCanvas(S, S);
  const ec = ctxOf(emissive);

  ac.fillStyle = cssOf(PALETTE.ground);
  ac.fillRect(0, 0, S, S);
  ec.fillStyle = '#000';
  ec.fillRect(0, 0, S, S);

  // Draws a rect at three horizontal and vertical offsets so anything that
  // straddles a border of the tile comes back on the other side.
  const wrapRect = (c, x, y, w, h) => {
    for (const ox of [-S, 0, S]) {
      for (const oy of [-S, 0, S]) {
        if (x + ox > S || x + ox + w < 0 || y + oy > S || y + oy + h < 0) continue;
        c.fillRect(x + ox, y + oy, w, h);
      }
    }
  };

  // Avenue centres, deliberately uneven.
  const avX = [[6, 26], [138, 15], [252, 21], [376, 13]];
  const avY = [[18, 24], [112, 14], [238, 20], [352, 15], [446, 12]];

  // Parcels between the avenues, each one a block of buildings.
  const parcels = [];
  for (let i = 0; i < avX.length; i++) {
    const a = avX[i];
    const b = avX[(i + 1) % avX.length];
    const x0 = a[0] + a[1] * 0.5;
    let x1 = b[0] - b[1] * 0.5;
    if (x1 <= x0) x1 += S;
    for (let j = 0; j < avY.length; j++) {
      const c = avY[j];
      const d = avY[(j + 1) % avY.length];
      const y0 = c[0] + c[1] * 0.5;
      let y1 = d[0] - d[1] * 0.5;
      if (y1 <= y0) y1 += S;
      parcels.push([x0, y0, x1 - x0, y1 - y0]);
    }
  }

  for (const p of parcels) {
    // Base slab of the block, each one a slightly different darkness.
    const tone = 0.5 + rand() * 0.8;
    ac.fillStyle = cssMix(PALETTE.ground, PALETTE.street, tone * 0.5);
    wrapRect(ac, p[0], p[1], p[2], p[3]);
    // Minor streets carving the block into 2 or 3 strips.
    const cuts = 1 + ((rand() * 2) | 0);
    ac.fillStyle = cssOf(PALETTE.street, 0.9);
    for (let k = 1; k <= cuts; k++) {
      const t = k / (cuts + 1) + (rand() - 0.5) * 0.14;
      if (p[2] > p[3]) wrapRect(ac, p[0] + p[2] * t - 3, p[1], 6, p[3]);
      else wrapRect(ac, p[0], p[1] + p[3] * t - 3, p[2], 6);
    }
    // Rooftops: small darker and lighter pads inside the parcel.
    const roofs = 5 + ((rand() * 7) | 0);
    for (let k = 0; k < roofs; k++) {
      const w = 8 + rand() * Math.max(10, p[2] * 0.3);
      const h = 8 + rand() * Math.max(10, p[3] * 0.3);
      const x = p[0] + 4 + rand() * Math.max(1, p[2] - w - 8);
      const y = p[1] + 4 + rand() * Math.max(1, p[3] - h - 8);
      ac.fillStyle = rand() < 0.5 ? cssGray(0, 0.3) : cssMix(PALETTE.ground, PALETTE.wallTrim, 0.35);
      wrapRect(ac, x, y, w, h);
      // Every few roofs, a lit stairwell box.
      if (rand() < 0.22) {
        ec.fillStyle = cssOf(PALETTE.cityWarm, 0.22 + rand() * 0.2);
        wrapRect(ec, x + w * 0.3, y + h * 0.3, Math.max(2, w * 0.3), Math.max(2, h * 0.3));
      }
    }
  }

  // Avenues on top of the parcels, with their lit centre line.
  for (const a of avX) {
    ac.fillStyle = cssOf(PALETTE.street);
    wrapRect(ac, a[0] - a[1] * 0.5, 0, a[1], S);
    ac.fillStyle = cssGray(0, 0.35);
    wrapRect(ac, a[0] - a[1] * 0.5, 0, 2, S);
    wrapRect(ac, a[0] + a[1] * 0.5 - 2, 0, 2, S);
    ec.fillStyle = cssOf(PALETTE.streetLight, 0.3);
    wrapRect(ec, a[0] - 1, 0, 2, S);
    for (let y = 0; y < S; y += 22) {
      ec.fillStyle = cssOf(PALETTE.streetLight, 0.55);
      wrapRect(ec, a[0] - a[1] * 0.5 + 2, y, 3, 3);
      wrapRect(ec, a[0] + a[1] * 0.5 - 5, y + 11, 3, 3);
    }
  }
  for (const a of avY) {
    ac.fillStyle = cssOf(PALETTE.street);
    wrapRect(ac, 0, a[0] - a[1] * 0.5, S, a[1]);
    ac.fillStyle = cssGray(0, 0.35);
    wrapRect(ac, 0, a[0] - a[1] * 0.5, S, 2);
    wrapRect(ac, 0, a[0] + a[1] * 0.5 - 2, S, 2);
    ec.fillStyle = cssOf(PALETTE.streetLight, 0.3);
    wrapRect(ec, 0, a[0] - 1, S, 2);
    for (let x = 0; x < S; x += 22) {
      ec.fillStyle = cssOf(PALETTE.streetLight, 0.55);
      wrapRect(ec, x, a[0] - a[1] * 0.5 + 2, 3, 3);
      wrapRect(ec, x + 11, a[0] + a[1] * 0.5 - 5, 3, 3);
    }
  }

  // Two lit plazas: the only large bright shapes of the plan.
  const plazas = [
    [70, 150, 54, 44, PALETTE.streetLight],
    [292, 388, 60, 38, PALETTE.cityCold],
  ];
  for (const p of plazas) {
    ac.fillStyle = cssMix(PALETTE.street, PALETTE.wallTrim, 0.5);
    wrapRect(ac, p[0], p[1], p[2], p[3]);
    ec.fillStyle = cssOf(p[4], 0.3);
    wrapRect(ec, p[0], p[1], p[2], p[3]);
    ec.fillStyle = cssOf(p[4], 0.6);
    wrapRect(ec, p[0] + 4, p[1] + 4, p[2] - 8, 2);
    wrapRect(ec, p[0] + 4, p[1] + p[3] - 6, p[2] - 8, 2);
  }

  // Scattered vehicle lights along the avenues.
  for (let i = 0; i < 90; i++) {
    const onX = rand() < 0.5;
    const a = onX ? avX[(rand() * avX.length) | 0] : avY[(rand() * avY.length) | 0];
    const t = rand() * S;
    ec.fillStyle = cssOf(rand() < 0.6 ? PALETTE.streetLight : PALETTE.red, 0.5 + rand() * 0.35);
    if (onX) wrapRect(ec, a[0] + (rand() - 0.5) * (a[1] - 6), t, 2, 4);
    else wrapRect(ec, t, a[0] + (rand() - 0.5) * (a[1] - 6), 4, 2);
  }

  const grit = noiseTile(rand, 128, 108, 148);
  patternFill(ac, grit, S, S, 0.18, 'overlay');
  return { albedo, emissive };
}

/**
 * Stratified rock for the mesas and the cliffs. Albedo and height are produced
 * by the same pass, so the normal map agrees with what is painted. The strata
 * are a wrapped sawtooth of v warped by tileable noise, which makes the tile
 * seamless in both directions.
 */
function buildRock(rand) {
  const S = 256; // repeated over a whole cliff face, 256 is plenty with mips
  const warp = fbmSampler(rand, 4, 4, 2);
  const grain = fbmSampler(rand, 16, 16, 3);
  const strata = 9;
  const base = rgbOf(PALETTE.rock);

  const albedo = makeCanvas(S, S);
  const ac = ctxOf(albedo);
  const height = makeCanvas(S, S);
  const hc = ctxOf(height);
  const aimg = ac.createImageData(S, S);
  const himg = hc.createImageData(S, S);
  const ad = aimg.data;
  const hd = himg.data;

  for (let y = 0; y < S; y++) {
    const v = y / S;
    for (let x = 0; x < S; x++) {
      const u = x / S;
      const w = (warp(u, v) - 0.5) * 0.16;
      const s = (v + w) * strata;
      const layer = Math.floor(s);
      const f = s - layer;
      // Bedding plane: a dark recessed line at the bottom of every layer,
      // then a slow lightening towards its top.
      let shade = 0.55 + f * 0.5;
      if (f < 0.12) shade = 0.28 + f * 1.4;
      // Alternate harder and softer beds so the cliff is not a stack of clones.
      const kind = ((layer % 3) + 3) % 3;
      shade *= kind === 0 ? 1.14 : kind === 1 ? 0.86 : 1.0;
      const g = grain(u, v);
      shade *= 0.72 + g * 0.56;
      // Fractures: the same grain read at a hard threshold, which costs no
      // extra sampler and still cuts across the bedding.
      if (g > 0.66) shade *= 1 - (g - 0.66) * 1.6;

      let r = base[0] * shade * 1.35;
      let gg = base[1] * shade * 1.28;
      let b = base[2] * shade * 1.2;
      // Warm dust settled in the bedding planes catches the city glow.
      if (f < 0.2) {
        const t = (0.2 - f) * 1.6;
        r += 16 * t;
        gg += 10 * t;
        b += 6 * t;
      }
      const i = (y * S + x) * 4;
      ad[i] = r > 255 ? 255 : r;
      ad[i + 1] = gg > 255 ? 255 : gg;
      ad[i + 2] = b > 255 ? 255 : b;
      ad[i + 3] = 255;
      const hv = 40 + shade * 150 + (g - 0.5) * 40;
      const hcl = hv < 0 ? 0 : hv > 255 ? 255 : hv;
      hd[i] = hcl;
      hd[i + 1] = hcl;
      hd[i + 2] = hcl;
      hd[i + 3] = 255;
    }
  }
  ac.putImageData(aimg, 0, 0);
  hc.putImageData(himg, 0, 0);
  return { albedo, height, heightData: hd };
}

/**
 * Wide low cloud deck for the horizontal haze planes. Horizontal band
 * structure with torn edges, alpha zero at the top of the tile and at every
 * border, underside tinted by the haze plus a hint of city glow.
 */
function buildClouds(rand) {
  const S = 256; // a soft deck on a big plane: extra resolution buys nothing
  const shape = fbmSampler(rand, 6, 2, 3);
  const tear = fbmSampler(rand, 12, 6, 2);
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  const img = ctx.createImageData(S, S);
  const d = img.data;
  const haze = rgbOf(PALETTE.haze);
  const glow = rgbOf(PALETTE.streetLight);

  for (let y = 0; y < S; y++) {
    const v = y / S;
    // Two soft decks stacked in the tile, plus the fade that guarantees the
    // top of the tile and both horizontal borders are fully transparent.
    const deck =
      Math.exp(-Math.pow((v - 0.42) / 0.16, 2)) * 0.9 +
      Math.exp(-Math.pow((v - 0.74) / 0.11, 2)) * 0.7;
    const fadeV = smoothStep(0.04, 0.34, v) * smoothStep(1.0, 0.86, v);
    for (let x = 0; x < S; x++) {
      const u = x / S;
      const n = shape(u, v);
      const t = tear(u, v);
      let a = (n * 1.8 - 0.72) * deck * fadeV;
      a -= Math.max(0, t - 0.55) * 1.1;
      if (a <= 0) {
        const i0 = (y * S + x) * 4;
        d[i0 + 3] = 0;
        continue;
      }
      a *= smoothStep(0, 0.1, u) * smoothStep(1, 0.9, u);
      if (a > 1) a = 1;
      // Underside is warmer and brighter: it is the city lighting it.
      const lit = smoothStep(0.3, 0.85, v) * (0.35 + n * 0.5);
      const i = (y * S + x) * 4;
      d[i] = haze[0] * 0.85 + glow[0] * 0.22 * lit;
      d[i + 1] = haze[1] * 0.85 + glow[1] * 0.16 * lit;
      d[i + 2] = haze[2] * 0.9 + glow[2] * 0.1 * lit;
      d[i + 3] = a * 235;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

/**
 * Moon disc with maria and a soft limb. Kept dim on purpose: it is the
 * brightest single object of the backdrop and still has to sit under the
 * circuit neon.
 */
function buildMoon(rand) {
  const S = 512;
  const c = S * 0.5;
  const r = S * 0.34;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  ctx.clearRect(0, 0, S, S);

  // Faint halo around the disc.
  const halo = ctx.createRadialGradient(c, c, r * 0.9, c, c, S * 0.5);
  halo.addColorStop(0, 'rgba(96,106,132,0.3)');
  halo.addColorStop(0.4, 'rgba(70,80,104,0.1)');
  halo.addColorStop(1, 'rgba(60,70,96,0)');
  ctx.fillStyle = halo;
  ctx.fillRect(0, 0, S, S);

  // Disc, lit from the upper left, with limb darkening on the far side.
  const disc = ctx.createRadialGradient(c - r * 0.3, c - r * 0.32, r * 0.05, c, c, r);
  disc.addColorStop(0, 'rgb(78,83,97)');
  disc.addColorStop(0.55, 'rgb(63,67,81)');
  disc.addColorStop(0.9, 'rgb(45,49,62)');
  disc.addColorStop(1, 'rgb(33,37,50)');
  ctx.save();
  ctx.beginPath();
  ctx.arc(c, c, r, 0, Math.PI * 2);
  ctx.clip();
  ctx.fillStyle = disc;
  ctx.fillRect(0, 0, S, S);

  // Maria: broad dark basalt plains.
  for (let i = 0; i < 7; i++) {
    const a = rand() * Math.PI * 2;
    const dist = rand() * r * 0.7;
    const mx = c + Math.cos(a) * dist;
    const my = c + Math.sin(a) * dist;
    const mr = r * (0.16 + rand() * 0.26);
    const g = ctx.createRadialGradient(mx, my, 0, mx, my, mr);
    g.addColorStop(0, 'rgba(24,27,38,0.55)');
    g.addColorStop(0.7, 'rgba(28,31,42,0.3)');
    g.addColorStop(1, 'rgba(30,34,46,0)');
    ctx.fillStyle = g;
    ctx.fillRect(mx - mr, my - mr, mr * 2, mr * 2);
  }
  // Craters: a bright rim with a darker floor.
  for (let i = 0; i < 26; i++) {
    const a = rand() * Math.PI * 2;
    const dist = Math.sqrt(rand()) * r * 0.92;
    const mx = c + Math.cos(a) * dist;
    const my = c + Math.sin(a) * dist;
    const mr = 3 + rand() * 14;
    ctx.strokeStyle = 'rgba(104,110,128,0.22)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(mx, my, mr, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = 'rgba(26,29,40,0.3)';
    ctx.beginPath();
    ctx.arc(mx + 0.8, my + 0.8, mr * 0.8, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();

  // Soft limb: feather the very edge of the disc so it never shows a staircase.
  ctx.save();
  ctx.globalCompositeOperation = 'destination-in';
  const mask = ctx.createRadialGradient(c, c, 0, c, c, S * 0.5);
  mask.addColorStop(0, 'rgba(255,255,255,1)');
  mask.addColorStop(r / (S * 0.5) - 0.012, 'rgba(255,255,255,1)');
  mask.addColorStop(r / (S * 0.5) + 0.006, 'rgba(255,255,255,0.5)');
  mask.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = mask;
  ctx.fillRect(0, 0, S, S);
  ctx.restore();
  return canvas;
}

/**
 * Horizon light dome, meant for a big cylinder around the scene: transparent
 * at the top, warm and slightly banded at the base. This is what lifts the
 * skyline silhouette off the sky without brightening the whole background.
 */
function buildSkyGlow(rand) {
  const W = 256; // mostly a vertical ramp: width only carries the hot districts
  const H = 512;
  const canvas = makeCanvas(W, H);
  const ctx = ctxOf(canvas);
  ctx.clearRect(0, 0, W, H);

  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0.0, 'rgba(40,34,80,0)');
  g.addColorStop(0.42, 'rgba(48,38,86,0.1)');
  g.addColorStop(0.68, 'rgba(70,48,90,0.26)');
  g.addColorStop(0.86, 'rgba(104,62,74,0.46)');
  g.addColorStop(0.97, 'rgba(126,76,58,0.6)');
  g.addColorStop(1.0, 'rgba(92,58,52,0.5)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  // Thin inversion bands near the base, the usual look of city light trapped
  // under a temperature inversion.
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (let i = 0; i < 7; i++) {
    const y = H * (0.7 + i * 0.042);
    const h = 3 + rand() * 9;
    ctx.fillStyle = 'rgba(120,74,58,' + (0.05 + rand() * 0.07) + ')';
    ctx.fillRect(0, y, W, h);
  }
  // A few broad hot districts, so the glow is not perfectly uniform.
  for (let i = 0; i < 6; i++) {
    const cx = rand() * W;
    const r = 70 + rand() * 130;
    for (const ox of [-W, 0, W]) {
      const rg = ctx.createRadialGradient(cx + ox, H, 0, cx + ox, H, r);
      rg.addColorStop(0, 'rgba(140,86,58,0.16)');
      rg.addColorStop(1, 'rgba(140,86,58,0)');
      ctx.fillStyle = rg;
      ctx.fillRect(cx + ox - r, H - r, r * 2, r * 2);
    }
  }
  ctx.restore();

  // Ceiling on what this layer can actually put on screen. 'lighter' adds up
  // the alphas as well as the colours, so the base of the dome can end near
  // opaque: without this pass the glow becomes the brightest thing in the
  // frame, which is exactly the mistake this backdrop must not repeat. The
  // limit is applied to the premultiplied value, hue preserving, colour only.
  const CAP_R = 88;
  const CAP_G = 60;
  const CAP_B = 50;
  const img = ctx.getImageData(0, 0, W, H);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const a = d[i + 3] / 255;
    if (a <= 0) continue;
    const pr = (d[i] * a) / CAP_R;
    const pg = (d[i + 1] * a) / CAP_G;
    const pb = (d[i + 2] * a) / CAP_B;
    const over = pr > pg ? (pr > pb ? pr : pb) : pg > pb ? pg : pb;
    if (over <= 1) continue;
    const k = 1 / over;
    d[i] *= k;
    d[i + 1] *= k;
    d[i + 2] *= k;
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

/**
 * Holographic advert panel. One builder, three dressings, so the circuit is
 * lined with different brands instead of the same board every 200 metres.
 * cfg: { title, sub, foot, backA, backB, frame, titleGlow, subColor, footColor }
 */
function buildAdPanel(rand, cfg) {
  const W = 512;
  const H = 256;
  const canvas = makeCanvas(W, H);
  const ctx = ctxOf(canvas);
  ctx.fillStyle = 'rgb(6,4,16)';
  ctx.fillRect(0, 0, W, H);

  // Backing glow of the hologram.
  const back = ctx.createRadialGradient(W * 0.5, H * 0.5, 10, W * 0.5, H * 0.5, W * 0.6);
  back.addColorStop(0, cssOf(cfg.backA, 0.35));
  back.addColorStop(0.55, cssOf(cfg.backB, 0.16));
  back.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = back;
  ctx.fillRect(0, 0, W, H);

  // Frame with cut corners.
  ctx.strokeStyle = cssOf(cfg.frame, 0.85);
  ctx.lineWidth = 4;
  cutRectPath(ctx, 10, 10, W - 20, H - 20, 26);
  ctx.stroke();
  ctx.strokeStyle = cssOf(cfg.frame, 0.25);
  ctx.lineWidth = 1.5;
  cutRectPath(ctx, 20, 20, W - 40, H - 40, 20);
  ctx.stroke();

  ctx.textBaseline = 'middle';
  ctx.save();
  ctx.shadowColor = cssOf(cfg.titleGlow, 0.9);
  ctx.shadowBlur = 26;
  ctx.font = 'bold 82px "Arial Narrow", Arial, sans-serif';
  ctx.fillStyle = cssOf(PALETTE.white);
  spacedText(ctx, cfg.title, W * 0.5, 82, 10, 'center');
  ctx.shadowColor = cssOf(cfg.subColor, 0.9);
  ctx.font = 'bold 62px "Arial Narrow", Arial, sans-serif';
  ctx.fillStyle = cssOf(cfg.subColor);
  spacedText(ctx, cfg.sub, W * 0.5, 152, 12, 'center');
  ctx.restore();

  ctx.font = 'bold 24px "Arial Narrow", Arial, sans-serif';
  ctx.fillStyle = cssOf(cfg.footColor, 0.95);
  spacedText(ctx, cfg.foot, W * 0.5, 206, 4, 'center');

  // Interlace lines and a couple of glitch offsets.
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  for (let y = 0; y < H; y += 4) ctx.fillRect(0, y, W, 2);
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (let i = 0; i < 3; i++) {
    const y = 30 + rand() * (H - 60);
    const h = 3 + rand() * 7;
    ctx.fillStyle = cssOf(cfg.frame, 0.12);
    ctx.fillRect(-4 + rand() * 8, y, W, h);
  }
  ctx.restore();
  return canvas;
}

/** The three advert dressings. French, no accents, invented brands. */
const AD_PANELS = [
  {
    title: 'TURBO',
    sub: 'PLASMA',
    foot: 'ENERGIE PURE - NEO KYOTO',
    backA: PALETTE.magenta,
    backB: PALETTE.violet,
    frame: PALETTE.cyan,
    titleGlow: PALETTE.magenta,
    subColor: PALETTE.cyan,
    footColor: PALETTE.amber,
  },
  {
    title: 'KOSMA',
    sub: 'ORBITALE',
    foot: 'NAVETTES TOUTES LES 9 MINUTES',
    backA: PALETTE.lime,
    backB: 0x1e88a8,
    frame: PALETTE.lime,
    titleGlow: PALETTE.lime,
    subColor: PALETTE.amber,
    footColor: PALETTE.cyan,
  },
  {
    title: 'MIRAI',
    sub: 'CREDIT',
    foot: 'VOTRE VAISSEAU DES CE SOIR',
    backA: PALETTE.violet,
    backB: PALETTE.magenta,
    frame: PALETTE.amber,
    titleGlow: PALETTE.violet,
    subColor: PALETTE.magenta,
    footColor: PALETTE.white,
  },
];

// ---------------------------------------------------------------------------
// Sky: 2048x1024 equirectangular night dome.
//
// It must stay dark: the neon of the circuit has to be the brightest thing on
// screen. The dome therefore gets STRUCTURE (nebula filaments, star clusters,
// high cloud streaks, a warm horizon dome) rather than exposure, and the whole
// map ends on a hue preserving clamp to SKY_MAX_*, applied after every layer
// including the stars. A brighter sky than the subject was tried here once and
// swallowed the track.
// ---------------------------------------------------------------------------

const SKY_W = 2048;
const SKY_H = 1024;
const SKY_MAX_R = 70;
const SKY_MAX_G = 78;
const SKY_MAX_B = 110;
// The nebula is computed small and scaled up: the filaments survive the
// upscale as soft strands, and a full resolution fbm pass over the dome would
// eat the whole texture budget on its own.
const NEB_W = 384;
const NEB_H = 192;

/**
 * Nebula layer: three warped bands, each modulated by its own fbm so it shows
 * internal filaments instead of a soft radial blob. Returned opaque, meant to
 * be scaled up and added with 'lighter'.
 */
function buildNebula(rand) {
  const canvas = makeCanvas(NEB_W, NEB_H);
  const ctx = ctxOf(canvas);
  const img = ctx.createImageData(NEB_W, NEB_H);
  const d = img.data;
  const density = fbmSampler(rand, 3, 2, 2);
  const bands = [
    { v: 0.24, th: 0.1, warp: 0.1, col: rgbOf(PALETTE.violet), amp: 0.2, fil: fbmSampler(rand, 18, 7, 2) },
    { v: 0.36, th: 0.07, warp: 0.13, col: rgbOf(0x2a58c8), amp: 0.18, fil: fbmSampler(rand, 24, 9, 2) },
    { v: 0.45, th: 0.06, warp: 0.08, col: rgbOf(0x1e88a8), amp: 0.14, fil: fbmSampler(rand, 30, 12, 2) },
    { v: 0.15, th: 0.05, warp: 0.11, col: rgbOf(PALETTE.magenta), amp: 0.11, fil: fbmSampler(rand, 20, 8, 2) },
  ];
  const warp = fbmSampler(rand, 5, 3, 2);

  for (let y = 0; y < NEB_H; y++) {
    const v = y / NEB_H;
    for (let x = 0; x < NEB_W; x++) {
      const u = x / NEB_W;
      const w = (warp(u, v) - 0.5);
      let r = 0;
      let g = 0;
      let b = 0;
      for (let k = 0; k < bands.length; k++) {
        const band = bands[k];
        const dv = (v - band.v + w * band.warp) / band.th;
        if (dv < -2.6 || dv > 2.6) continue;
        let m = Math.exp(-dv * dv);
        if (m < 0.02) continue;
        // Contrast on the filaments: the low end is pushed to nothing so the
        // band breaks into strands rather than reading as a wash. The curve is
        // capped, otherwise the tail of the fbm blows a hole in the clamp and
        // the nebula turns back into the grey-violet haze we are avoiding.
        const f = band.fil(u, v);
        let fc = f * 1.7 - 0.5;
        if (fc < 0) fc = 0;
        else if (fc > 1) fc = 1;
        m *= 0.1 + 0.5 * fc * fc;
        m *= band.amp * (0.3 + density(u, v) * 1.1);
        r += band.col[0] * m;
        g += band.col[1] * m;
        b += band.col[2] * m;
      }
      const i = (y * NEB_W + x) * 4;
      d[i] = r > 255 ? 255 : r;
      d[i + 1] = g > 255 ? 255 : g;
      d[i + 2] = b > 255 ? 255 : b;
      d[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

function buildSky(rand) {
  const canvas = makeCanvas(SKY_W, SKY_H);
  const ctx = ctxOf(canvas);
  const horizon = SKY_H * 0.5;

  // Vertical gradient, zenith at the top row. Deep indigo rather than black:
  // a pure black zenith gives the stars nothing to sit on.
  const grad = ctx.createLinearGradient(0, 0, 0, SKY_H);
  grad.addColorStop(0.0, 'rgb(13,11,32)');
  grad.addColorStop(0.18, 'rgb(11,10,29)');
  grad.addColorStop(0.34, 'rgb(9,9,25)');
  grad.addColorStop(0.46, 'rgb(13,11,30)');
  grad.addColorStop(0.5, 'rgb(17,14,34)');
  grad.addColorStop(0.56, 'rgb(9,8,18)');
  grad.addColorStop(0.74, 'rgb(4,4,10)');
  grad.addColorStop(1.0, 'rgb(2,2,6)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, SKY_W, SKY_H);

  // Nebulae, computed small and scaled up: the filaments survive the upscale,
  // and the dome costs a fraction of a full resolution pass.
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.drawImage(buildNebula(rand), 0, 0, SKY_W, SKY_H);
  ctx.restore();

  // Thin high altitude cloud streaks, drawn as chains of soft puffs so their
  // edges tear instead of ending on a clean ellipse. The wrap copies are only
  // painted when the puff actually straddles a border: at this resolution the
  // three blind copies would cost more than the rest of the dome.
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (let i = 0; i < 11; i++) {
    const y0 = SKY_H * (0.16 + rand() * 0.3);
    const len = 260 + rand() * 700;
    const x0 = rand() * SKY_W;
    const tilt = (rand() - 0.5) * 90;
    const thick = 6 + rand() * 12;
    const level = 0.016 + rand() * 0.028;
    const warm = rand() < 0.4;
    const col = warm ? 0xa07a90 : 0x6a76b0;
    const puffs = 22 + ((rand() * 12) | 0);
    for (let k = 0; k < puffs; k++) {
      const t = k / (puffs - 1);
      const px = x0 + t * len;
      const py = y0 + tilt * t + Math.sin(t * 7 + i) * thick * 0.6;
      const pr = thick * (0.4 + Math.sin(t * Math.PI) * 1.3) * (0.7 + rand() * 0.6);
      const rr = pr * 3.4;
      for (const ox of [-SKY_W, 0, SKY_W]) {
        if (px + ox + rr < 0 || px + ox - rr > SKY_W) continue;
        // Squashed hard: a round puff reads as a polka dot, a flat one reads
        // as a torn strip of high cloud.
        ctx.save();
        ctx.translate(px + ox, py);
        ctx.scale(1, 0.28);
        const g = ctx.createRadialGradient(0, 0, 0, 0, 0, rr);
        g.addColorStop(0, cssOf(col, level));
        g.addColorStop(0.5, cssOf(col, level * 0.35));
        g.addColorStop(1, cssOf(col, 0));
        ctx.fillStyle = g;
        ctx.fillRect(-rr, -rr, rr * 2, rr * 2);
        ctx.restore();
      }
    }
  }
  ctx.restore();

  // Warm light dome over the city. This is the important layer: it is what
  // separates the black skyline silhouette from the black sky.
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  // Clipped to the horizon band: the wide hot spot gradients would otherwise
  // spill deep into the lower hemisphere, wasting fill and lifting a region
  // that ends up hidden behind the terrain anyway.
  ctx.beginPath();
  ctx.rect(0, horizon - 330, SKY_W, 390);
  ctx.clip();
  const glow = ctx.createLinearGradient(0, horizon - 300, 0, horizon + 60);
  // Peak values are kept under the ceiling on purpose: if the dome saturates
  // the clamp, the horizon flattens into one solid band and the structure the
  // whole layer exists for is lost. The ramp also returns to zero before the
  // clip, otherwise the layer ends on a straight line across the sky.
  glow.addColorStop(0.0, 'rgba(70,50,120,0)');
  glow.addColorStop(0.4, 'rgba(84,56,124,0.1)');
  glow.addColorStop(0.66, 'rgba(140,84,110,0.2)');
  glow.addColorStop(0.8, 'rgba(190,120,82,0.24)');
  glow.addColorStop(0.87, 'rgba(150,94,74,0.15)');
  glow.addColorStop(1.0, 'rgba(120,76,64,0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, horizon - 300, SKY_W, 360);
  // Hot districts along the dome, plus the light shafts they throw upwards.
  for (let i = 0; i < 11; i++) {
    const cx = rand() * SKY_W;
    const r = 130 + rand() * 300;
    const color = rand() < 0.55 ? 0xff9a50 : 0x9a68ff;
    for (const ox of [-SKY_W, 0, SKY_W]) {
      if (cx + ox + r < 0 || cx + ox - r > SKY_W) continue;
      // Squashed flat so the district glow dies out well before the clip line
      // and hugs the horizon the way a real city dome does.
      ctx.save();
      ctx.translate(cx + ox, horizon + 4);
      ctx.scale(1, 0.22);
      const g = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
      g.addColorStop(0, cssOf(color, 0.16));
      g.addColorStop(0.5, cssOf(color, 0.05));
      g.addColorStop(1, cssOf(color, 0));
      ctx.fillStyle = g;
      ctx.fillRect(-r, -r, r * 2, r * 2);
      ctx.restore();
    }
    if (rand() < 0.5) {
      // Light shaft rising off a district. Drawn as a squashed radial so it
      // fades on all sides: a plain rectangle leaves two hard vertical edges
      // in the middle of the sky, which is instantly readable as a mistake.
      const h = 120 + rand() * 220;
      const sw = 40 + rand() * 90;
      for (const ox of [-SKY_W, 0, SKY_W]) {
        if (cx + ox + sw < 0 || cx + ox - sw > SKY_W) continue;
        ctx.save();
        ctx.translate(cx + ox, horizon);
        ctx.scale(sw / h, 1);
        const sg = ctx.createRadialGradient(0, 0, 0, 0, 0, h);
        sg.addColorStop(0, cssOf(color, 0.14));
        sg.addColorStop(0.45, cssOf(color, 0.05));
        sg.addColorStop(1, cssOf(color, 0));
        ctx.fillStyle = sg;
        ctx.fillRect(-h, -h, h * 2, h);
        ctx.restore();
      }
    }
  }
  ctx.restore();

  // Star field. Density follows a couple of Milky Way clusters so the sky is
  // not an even sprinkle of dots.
  const starTints = [0xffffff, 0xdfe8ff, 0xfff0d8, 0xcfe0ff, 0xffd9c0];
  const clusters = [];
  for (let i = 0; i < 3; i++) {
    clusters.push({ x: rand() * SKY_W, y: SKY_H * (0.08 + rand() * 0.3), r: 130 + rand() * 190 });
  }
  const placeStar = (x, y, v, boost) => {
    const b = rand();
    const level = 40 + b * b * b * 190 * boost;
    const fade = 1 - Math.min(1, Math.max(0, (v - 0.36) / 0.16));
    const tint = starTints[(rand() * starTints.length) | 0];
    ctx.fillStyle = cssOf(tint, (level / 255) * (0.3 + fade * 0.7));
    const size = b > 0.93 ? 2 : 1;
    ctx.fillRect(x, y, size, size);
    if (b > 0.978) {
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      const g = ctx.createRadialGradient(x, y, 0, x, y, 9);
      g.addColorStop(0, cssOf(tint, 0.4));
      g.addColorStop(1, cssOf(tint, 0));
      ctx.fillStyle = g;
      ctx.fillRect(x - 9, y - 9, 18, 18);
      ctx.restore();
    }
  };
  for (let i = 0; i < 2100; i++) {
    const u = rand();
    const t = rand();
    const v = Math.acos(1 - 2 * t) / Math.PI; // uniform over the sphere
    if (v > 0.52) continue; // nothing below the horizon
    placeStar(u * SKY_W, v * SKY_H, v, 1);
  }
  for (const c of clusters) {
    for (let i = 0; i < 200; i++) {
      const a = rand() * Math.PI * 2;
      const d = Math.pow(rand(), 1.7) * c.r;
      const x = c.x + Math.cos(a) * d;
      const y = c.y + Math.sin(a) * d * 0.6;
      if (y < 0 || y > SKY_H * 0.52) continue;
      placeStar((x + SKY_W) % SKY_W, y, y / SKY_H, 0.7);
    }
  }

  // Distant skyline: tiny lit windows and a few beacons right on the horizon.
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (let i = 0; i < 1200; i++) {
    const x = rand() * SKY_W;
    const y = horizon - rand() * rand() * 34;
    const warm = rand() < 0.6;
    const color = warm ? 0xffb070 : 0x80d0ff;
    ctx.fillStyle = cssOf(color, 0.12 + rand() * 0.26);
    ctx.fillRect(x, y, 1, 1 + (rand() < 0.2 ? 1 : 0));
  }
  for (let i = 0; i < 34; i++) {
    const x = rand() * SKY_W;
    const h = 24 + rand() * 78;
    const g = ctx.createLinearGradient(0, horizon, 0, horizon - h);
    const color = rand() < 0.5 ? PALETTE.cyan : PALETTE.magenta;
    g.addColorStop(0, cssOf(color, 0.16));
    g.addColorStop(1, cssOf(color, 0));
    ctx.fillStyle = g;
    ctx.fillRect(x, horizon - h, 1 + rand() * 2, h);
  }
  ctx.restore();

  // Hue preserving ceiling, stars included: scaling the triplet instead of
  // clamping each channel keeps a white star white. Only the top 56 % of the
  // map is scanned: every additive layer above is bounded by the horizon band
  // clip at horizon + 60, and below that row the base gradient alone remains,
  // peaking at rgb(9,8,18).
  const clampH = Math.round(SKY_H * 0.56);
  const img = ctx.getImageData(0, 0, SKY_W, clampH);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    // Fast path: most of the dome sits far below the ceiling, so the division
    // only runs on the handful of pixels that actually need rescaling.
    if (d[i] <= SKY_MAX_R && d[i + 1] <= SKY_MAX_G && d[i + 2] <= SKY_MAX_B) continue;
    const r = d[i] / SKY_MAX_R;
    const g = d[i + 1] / SKY_MAX_G;
    const b = d[i + 2] / SKY_MAX_B;
    const over = r > g ? (r > b ? r : b) : g > b ? g : b;
    const k = 1 / over;
    d[i] *= k;
    d[i + 1] *= k;
    d[i + 2] *= k;
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

// ---------------------------------------------------------------------------
// Particle sprites. All are soft radial ramps: colour equals alpha so they
// look right under additive as well as regular alpha blending.
// ---------------------------------------------------------------------------

function buildSpark() {
  const S = 128;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  const c = S * 0.5;
  const g = ctx.createRadialGradient(c, c, 0, c, c, c);
  g.addColorStop(0.0, 'rgba(255,255,255,1)');
  g.addColorStop(0.14, 'rgba(255,255,255,0.92)');
  g.addColorStop(0.34, 'rgba(255,255,255,0.34)');
  g.addColorStop(0.62, 'rgba(255,255,255,0.08)');
  g.addColorStop(1.0, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  return rampFromAlpha(canvas);
}

function buildSmoke(rand) {
  const S = 128;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  const c = S * 0.5;
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  for (let i = 0; i < 9; i++) {
    const a = rand() * Math.PI * 2;
    const d = rand() * S * 0.16;
    const x = c + Math.cos(a) * d;
    const y = c + Math.sin(a) * d;
    const r = S * (0.22 + rand() * 0.2);
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, 'rgba(255,255,255,0.3)');
    g.addColorStop(0.5, 'rgba(255,255,255,0.13)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  }
  ctx.restore();
  // Guarantee a perfectly soft circular border.
  ctx.globalCompositeOperation = 'destination-in';
  const mask = ctx.createRadialGradient(c, c, 0, c, c, c);
  mask.addColorStop(0, 'rgba(255,255,255,1)');
  mask.addColorStop(0.55, 'rgba(255,255,255,0.85)');
  mask.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = mask;
  ctx.fillRect(0, 0, S, S);
  ctx.globalCompositeOperation = 'source-over';
  return rampFromAlpha(canvas);
}

function buildFlare() {
  const S = 256;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  const c = S * 0.5;
  const halo = ctx.createRadialGradient(c, c, 0, c, c, c);
  halo.addColorStop(0.0, 'rgba(255,255,255,0.75)');
  halo.addColorStop(0.18, 'rgba(255,255,255,0.3)');
  halo.addColorStop(0.45, 'rgba(255,255,255,0.09)');
  halo.addColorStop(1.0, 'rgba(255,255,255,0)');
  ctx.fillStyle = halo;
  ctx.fillRect(0, 0, S, S);
  const core = ctx.createRadialGradient(c, c, 0, c, c, S * 0.16);
  core.addColorStop(0.0, 'rgba(255,255,255,1)');
  core.addColorStop(0.5, 'rgba(255,255,255,0.6)');
  core.addColorStop(1.0, 'rgba(255,255,255,0)');
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.fillStyle = core;
  ctx.fillRect(0, 0, S, S);
  ctx.restore();
  return rampFromAlpha(canvas);
}

function buildRing() {
  const S = 256;
  const canvas = makeCanvas(S, S);
  const ctx = ctxOf(canvas);
  const c = S * 0.5;
  const g = ctx.createRadialGradient(c, c, 0, c, c, c);
  g.addColorStop(0.0, 'rgba(255,255,255,0)');
  g.addColorStop(0.5, 'rgba(255,255,255,0.02)');
  g.addColorStop(0.72, 'rgba(255,255,255,0.22)');
  g.addColorStop(0.86, 'rgba(255,255,255,1)');
  g.addColorStop(0.93, 'rgba(255,255,255,0.4)');
  g.addColorStop(1.0, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  return rampFromAlpha(canvas);
}

// ---------------------------------------------------------------------------
// Public factory
// ---------------------------------------------------------------------------

/**
 * Builds every texture of the game.
 * @param {THREE.WebGLRenderer} renderer only read for the max anisotropy.
 * @returns {object} the Textures object described in CONTRACTS.md section 3.
 */
export function createTextures(renderer) {
  const maxAniso =
    renderer && renderer.capabilities && renderer.capabilities.getMaxAnisotropy
      ? renderer.capabilities.getMaxAnisotropy()
      : 1;
  const owned = [];

  /**
   * Wraps a canvas into a texture with the right colour space and filtering.
   * opts: { srgb, aniso, wrapS, wrapT, mips }
   */
  function tex(canvas, opts) {
    const o = opts || {};
    const t = new THREE.CanvasTexture(canvas);
    t.colorSpace = o.srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    t.wrapS = o.wrapS || THREE.RepeatWrapping;
    t.wrapT = o.wrapT || THREE.RepeatWrapping;
    t.generateMipmaps = o.mips === false ? false : true;
    t.minFilter = t.generateMipmaps ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter;
    t.magFilter = THREE.LinearFilter;
    t.anisotropy = Math.min(maxAniso, o.aniso === undefined ? 4 : o.aniso);
    t.needsUpdate = true;
    owned.push(t);
    return t;
  }

  // --- road
  const roadParts = buildRoad(mulberry32(0x1a2b3c4d));
  const road = tex(roadParts.albedo, { srgb: true, aniso: maxAniso });
  const roadNormal = tex(heightToNormal(roadParts.height, 0.016), { aniso: maxAniso });
  const roadRough = tex(roadParts.rough, { aniso: maxAniso });
  const roadDetail = tex(buildRoadDetail(), {
    srgb: true,
    aniso: maxAniso,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });

  // --- walls
  const wallParts = buildWall(mulberry32(0x2b3c4d5e));
  const wall = tex(wallParts.albedo, { srgb: true, aniso: maxAniso });
  const wallNormal = tex(heightToNormal(wallParts.height, 0.02), { aniso: maxAniso });
  const wallEmissive = tex(wallParts.emissive, { srgb: true, aniso: maxAniso });

  // --- track dressing
  const edgeStrip = tex(buildEdgeStrip(), { srgb: true, wrapT: THREE.ClampToEdgeWrapping });
  // The plate fades to black on all four sides, so it reads correctly whether
  // it is mapped one to one on a quad or repeated.
  const boostPad = tex(buildBoostPad(), { srgb: true, aniso: maxAniso });
  const checker = tex(buildChecker(), { srgb: true, aniso: maxAniso });
  const grid = tex(buildGrid(), { srgb: true, aniso: maxAniso });

  // --- craft
  const hullParts = buildHull(mulberry32(0x3c4d5e6f));
  const hull = tex(hullParts.albedo, { srgb: true, aniso: maxAniso });
  const hullNormal = tex(heightToNormal(hullParts.height, 0.014), { aniso: maxAniso });
  const hullEmissive = tex(hullParts.emissive, { srgb: true, aniso: maxAniso });
  const cockpit = tex(buildCockpit(mulberry32(0x4d5e6f70)), { srgb: true, aniso: maxAniso });

  // --- city facades. Three profiles: cold office tower, warm housing block,
  // slim ribbon glazing. Different pitch, density and dominant tint, so an
  // instanced skyline does not read as one building repeated.
  const windowParts = buildFacade(mulberry32(0x5e6f7081), {
    cols: 8,
    rows: 14,
    style: 'grid',
    tints: FACADE_TINTS.office,
    lit: 0.46,
    fullFloors: 2,
    base: 0x0d0e15,
    trim: 0x252838,
    glass: 0x080a12,
  });
  const windows = tex(windowParts.albedo, { srgb: true, aniso: maxAniso });
  const windowsEmissive = tex(windowParts.emissive, { srgb: true, aniso: maxAniso });

  const warmParts = buildFacade(mulberry32(0x5e6f7082), {
    cols: 16,
    rows: 16,
    style: 'balcony',
    tints: FACADE_TINTS.warm,
    lit: 0.62,
    fullFloors: 1,
    base: 0x14110f,
    trim: 0x2e2a26,
    glass: 0x0a0a10,
  });
  const windowsWarm = tex(warmParts.albedo, { srgb: true, aniso: maxAniso });
  const windowsWarmEmissive = tex(warmParts.emissive, { srgb: true, aniso: maxAniso });

  const slimParts = buildFacade(mulberry32(0x5e6f7083), {
    cols: 8,
    rows: 32,
    style: 'ribbon',
    tints: FACADE_TINTS.slim,
    lit: 0.4,
    fullFloors: 3,
    base: 0x0a0d16,
    trim: 0x1e2740,
    glass: 0x060911,
  });
  const windowsSlim = tex(slimParts.albedo, { srgb: true, aniso: maxAniso });
  const windowsSlimEmissive = tex(slimParts.emissive, { srgb: true, aniso: maxAniso });

  const rooftopParts = buildRooftop(mulberry32(0x5e6f7084));
  const rooftop = tex(rooftopParts.albedo, { srgb: true, aniso: maxAniso });
  const rooftopEmissive = tex(rooftopParts.emissive, { srgb: true, aniso: maxAniso });

  const facadeSign = tex(buildFacadeSign(mulberry32(0x5e6f7085)), {
    srgb: true,
    aniso: maxAniso,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });

  const groundParts = buildCityGround(mulberry32(0x5e6f7086));
  const cityGround = tex(groundParts.albedo, { srgb: true, aniso: maxAniso });
  const cityGroundEmissive = tex(groundParts.emissive, { srgb: true, aniso: maxAniso });

  // --- terrain and atmosphere
  const rockParts = buildRock(mulberry32(0x5e6f7087));
  const rock = tex(rockParts.albedo, { srgb: true, aniso: maxAniso });
  const rockNormal = tex(heightToNormal(rockParts.height, 0.018, rockParts.heightData), {
    aniso: maxAniso,
  });
  const clouds = tex(buildClouds(mulberry32(0x5e6f7088)), { srgb: true, aniso: maxAniso });
  const moon = tex(buildMoon(mulberry32(0x5e6f7089)), {
    srgb: true,
    aniso: maxAniso,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });
  const skyGlow = tex(buildSkyGlow(mulberry32(0x5e6f708a)), {
    srgb: true,
    aniso: maxAniso,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });

  // --- advert panels
  const billboard = tex(buildAdPanel(mulberry32(0x6f708192), AD_PANELS[0]), {
    srgb: true,
    aniso: maxAniso,
  });
  const hologramB = tex(buildAdPanel(mulberry32(0x6f708193), AD_PANELS[1]), {
    srgb: true,
    aniso: maxAniso,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });
  const hologramC = tex(buildAdPanel(mulberry32(0x6f708194), AD_PANELS[2]), {
    srgb: true,
    aniso: maxAniso,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });

  const skyTexture = tex(buildSky(mulberry32(0x708192a3)), {
    srgb: true,
    aniso: 1,
    wrapT: THREE.ClampToEdgeWrapping,
  });
  skyTexture.mapping = THREE.EquirectangularReflectionMapping;

  // --- particles
  const spark = tex(buildSpark(), {
    srgb: true,
    aniso: 1,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });
  const smoke = tex(buildSmoke(mulberry32(0x8192a3b4)), {
    srgb: true,
    aniso: 1,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });
  const flare = tex(buildFlare(), {
    srgb: true,
    aniso: 1,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });
  const ring = tex(buildRing(), {
    srgb: true,
    aniso: 1,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
  });

  // --- data noise, four independent channels for the shaders
  const NS = 256;
  const noiseRand = mulberry32(0x92a3b4c5);
  const noiseData = new Uint8Array(NS * NS * 4);
  const smoothA = valueNoise(noiseRand, 16, 16);
  const smoothB = valueNoise(noiseRand, 64, 64);
  for (let y = 0; y < NS; y++) {
    const v = y / NS;
    for (let x = 0; x < NS; x++) {
      const i = (y * NS + x) * 4;
      const u = x / NS;
      noiseData[i] = noiseRand() * 255;
      noiseData[i + 1] = noiseRand() * 255;
      noiseData[i + 2] = smoothA(u, v) * 255;
      noiseData[i + 3] = smoothB(u, v) * 255;
    }
  }
  const noise = new THREE.DataTexture(noiseData, NS, NS, THREE.RGBAFormat, THREE.UnsignedByteType);
  noise.colorSpace = THREE.NoColorSpace;
  noise.wrapS = THREE.RepeatWrapping;
  noise.wrapT = THREE.RepeatWrapping;
  noise.minFilter = THREE.LinearMipmapLinearFilter;
  noise.magFilter = THREE.LinearFilter;
  noise.generateMipmaps = true;
  noise.needsUpdate = true;
  owned.push(noise);

  return {
    road,
    roadNormal,
    roadRough,
    roadDetail,
    wall,
    wallNormal,
    wallEmissive,
    edgeStrip,
    boostPad,
    checker,
    hull,
    hullNormal,
    hullEmissive,
    cockpit,
    windows,
    windowsEmissive,
    windowsWarm,
    windowsWarmEmissive,
    windowsSlim,
    windowsSlimEmissive,
    rooftop,
    rooftopEmissive,
    facadeSign,
    cityGround,
    cityGroundEmissive,
    rock,
    rockNormal,
    clouds,
    moon,
    skyGlow,
    billboard,
    hologramB,
    hologramC,
    sky: skyTexture,
    grid,
    spark,
    smoke,
    flare,
    ring,
    noise,
    /**
     * Releases every GPU texture built here. New maps need no extra line: they
     * are registered in `owned` by the local tex() helper, and the DataTexture
     * of the noise is pushed there too.
     */
    dispose() {
      for (let i = 0; i < owned.length; i++) owned[i].dispose();
      owned.length = 0;
    },
  };
}
