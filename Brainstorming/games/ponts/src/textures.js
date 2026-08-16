/**
 * PONTS DE FORTUNE - procedural textures.
 *
 * Every surface in the game is drawn here into a 2D canvas: not one binary
 * asset is loaded. Member textures are deliberately near grey so the instance
 * colour (material tint blended with the stress reading) survives the multiply.
 */

import * as THREE from 'three';

/** Deterministic PRNG: the ravine looks the same on every machine. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function random() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return { canvas: c, ctx: c.getContext('2d') };
}

function toTexture(canvas, repeatX, repeatY, srgb) {
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeatX || 1, repeatY || 1);
  t.colorSpace = srgb === false ? THREE.NoColorSpace : THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

/** Value noise on a coarse lattice, smoothed. Cheap and good enough for rock. */
function valueNoise(rand, w, h, cell) {
  const gw = Math.ceil(w / cell) + 2;
  const gh = Math.ceil(h / cell) + 2;
  const g = new Float32Array(gw * gh);
  for (let i = 0; i < g.length; i++) g[i] = rand();
  return function at(x, y) {
    const fx = x / cell;
    const fy = y / cell;
    const ix = Math.floor(fx);
    const iy = Math.floor(fy);
    const tx = fx - ix;
    const ty = fy - iy;
    const sx = tx * tx * (3 - 2 * tx);
    const sy = ty * ty * (3 - 2 * ty);
    const i00 = g[(iy % gh) * gw + (ix % gw)];
    const i10 = g[(iy % gh) * gw + ((ix + 1) % gw)];
    const i01 = g[((iy + 1) % gh) * gw + (ix % gw)];
    const i11 = g[((iy + 1) % gh) * gw + ((ix + 1) % gw)];
    return (i00 * (1 - sx) + i10 * sx) * (1 - sy) + (i01 * (1 - sx) + i11 * sx) * sy;
  };
}

function woodCanvas(rand) {
  const { canvas, ctx } = makeCanvas(128, 128);
  ctx.fillStyle = '#d8d0c4';
  ctx.fillRect(0, 0, 128, 128);
  // Grain running along the member (U axis).
  for (let i = 0; i < 90; i++) {
    const y = rand() * 128;
    ctx.strokeStyle = 'rgba(120,100,78,' + (0.06 + rand() * 0.16).toFixed(3) + ')';
    ctx.lineWidth = 0.6 + rand() * 1.6;
    ctx.beginPath();
    ctx.moveTo(0, y);
    for (let x = 0; x <= 128; x += 16) ctx.lineTo(x, y + Math.sin((x + i * 30) * 0.05) * 2.2);
    ctx.stroke();
  }
  // Knots and end bands.
  for (let i = 0; i < 5; i++) {
    const x = rand() * 128;
    const y = rand() * 128;
    const r = 3 + rand() * 5;
    const grd = ctx.createRadialGradient(x, y, 0, x, y, r);
    grd.addColorStop(0, 'rgba(96,74,52,0.75)');
    grd.addColorStop(1, 'rgba(96,74,52,0)');
    ctx.fillStyle = grd;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = 'rgba(90,72,52,0.35)';
  ctx.fillRect(0, 0, 4, 128);
  ctx.fillRect(124, 0, 4, 128);
  return canvas;
}

function steelCanvas(rand) {
  const { canvas, ctx } = makeCanvas(128, 128);
  ctx.fillStyle = '#dfe4e9';
  ctx.fillRect(0, 0, 128, 128);
  for (let i = 0; i < 200; i++) {
    const y = rand() * 128;
    ctx.strokeStyle = 'rgba(120,130,142,' + (0.04 + rand() * 0.1).toFixed(3) + ')';
    ctx.lineWidth = 0.5 + rand();
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(128, y + (rand() - 0.5) * 2);
    ctx.stroke();
  }
  // Rivet rows near the ends.
  ctx.fillStyle = 'rgba(108,118,130,0.85)';
  for (const bx of [10, 118]) {
    for (let k = 0; k < 5; k++) {
      ctx.beginPath();
      ctx.arc(bx, 16 + k * 24, 2.6, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.strokeStyle = 'rgba(150,158,168,0.6)';
  ctx.lineWidth = 2;
  ctx.strokeRect(1, 1, 126, 126);
  return canvas;
}

function cableCanvas() {
  const { canvas, ctx } = makeCanvas(32, 32);
  ctx.fillStyle = '#cfc9b8';
  ctx.fillRect(0, 0, 32, 32);
  ctx.strokeStyle = 'rgba(110,104,88,0.7)';
  ctx.lineWidth = 2;
  for (let i = -32; i < 64; i += 7) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i + 12, 32);
    ctx.stroke();
  }
  return canvas;
}

function roadCanvas(rand) {
  const { canvas, ctx } = makeCanvas(128, 128);
  ctx.fillStyle = '#cdd2d6';
  ctx.fillRect(0, 0, 128, 128);
  for (let i = 0; i < 2600; i++) {
    const v = 150 + rand() * 90;
    ctx.fillStyle = 'rgba(' + (v | 0) + ',' + (v | 0) + ',' + ((v + 6) | 0) + ',0.4)';
    ctx.fillRect(rand() * 128, rand() * 128, 1.6, 1.6);
  }
  // Kerbs along the two long edges, dashes down the middle.
  ctx.fillStyle = 'rgba(96,102,110,0.75)';
  ctx.fillRect(0, 0, 128, 9);
  ctx.fillRect(0, 119, 128, 9);
  ctx.fillStyle = 'rgba(250,244,220,0.85)';
  for (let x = 8; x < 128; x += 40) ctx.fillRect(x, 61, 22, 6);
  return canvas;
}

function rockCanvas(rand) {
  const { canvas, ctx } = makeCanvas(256, 256);
  const noise = valueNoise(rand, 256, 256, 22);
  const fine = valueNoise(rand, 256, 256, 6);
  const img = ctx.createImageData(256, 256);
  for (let y = 0; y < 256; y++) {
    for (let x = 0; x < 256; x++) {
      // Strata: horizontal bands warped by the coarse noise.
      const band = Math.sin((y + noise(x, y) * 26) * 0.19);
      let v = 0.52 + band * 0.11 + (fine(x, y) - 0.5) * 0.20 + (noise(x, y) - 0.5) * 0.12;
      v = Math.max(0.16, Math.min(1, v));
      const i = (y * 256 + x) * 4;
      img.data[i] = (v * 148 + 86) | 0;
      img.data[i + 1] = (v * 136 + 76) | 0;
      img.data[i + 2] = (v * 118 + 62) | 0;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  // A few cracks.
  ctx.strokeStyle = 'rgba(58,48,38,0.42)';
  for (let i = 0; i < 26; i++) {
    ctx.lineWidth = 0.6 + rand() * 1.4;
    let x = rand() * 256;
    let y = rand() * 256;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let k = 0; k < 7; k++) {
      x += (rand() - 0.5) * 34;
      y += (rand() - 0.3) * 30;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  return canvas;
}

function grassCanvas(rand) {
  const { canvas, ctx } = makeCanvas(128, 128);
  const noise = valueNoise(rand, 128, 128, 14);
  const img = ctx.createImageData(128, 128);
  for (let y = 0; y < 128; y++) {
    for (let x = 0; x < 128; x++) {
      const v = 0.55 + (noise(x, y) - 0.5) * 0.45;
      const i = (y * 128 + x) * 4;
      img.data[i] = (v * 128 + 26) | 0;
      img.data[i + 1] = (v * 146 + 40) | 0;
      img.data[i + 2] = (v * 88 + 26) | 0;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  for (let i = 0; i < 500; i++) {
    ctx.strokeStyle = 'rgba(' + (70 + rand() * 50 | 0) + ',' + (96 + rand() * 60 | 0) + ',40,0.5)';
    const x = rand() * 128;
    const y = rand() * 128;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + (rand() - 0.5) * 3, y - 2 - rand() * 3);
    ctx.stroke();
  }
  return canvas;
}

function skyCanvas(rand) {
  const { canvas, ctx } = makeCanvas(1024, 512);
  const grd = ctx.createLinearGradient(0, 0, 0, 512);
  grd.addColorStop(0.0, '#1d3f6b');
  grd.addColorStop(0.34, '#4d7ba6');
  grd.addColorStop(0.52, '#9fbcd0');
  grd.addColorStop(0.62, '#d7d2c0');
  grd.addColorStop(1.0, '#6d7a72');
  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, 1024, 512);
  // Sun glow, upper left of the panorama.
  const sun = ctx.createRadialGradient(300, 150, 0, 300, 150, 260);
  sun.addColorStop(0, 'rgba(255,244,214,0.95)');
  sun.addColorStop(0.25, 'rgba(255,232,186,0.35)');
  sun.addColorStop(1, 'rgba(255,220,170,0)');
  ctx.fillStyle = sun;
  ctx.fillRect(0, 0, 1024, 512);
  // Soft cloud banks.
  for (let i = 0; i < 90; i++) {
    const x = rand() * 1024;
    const y = 90 + rand() * 200;
    const r = 30 + rand() * 110;
    const g2 = ctx.createRadialGradient(x, y, 0, x, y, r);
    const a = 0.05 + rand() * 0.16;
    g2.addColorStop(0, 'rgba(255,253,247,' + a.toFixed(3) + ')');
    g2.addColorStop(1, 'rgba(255,253,247,0)');
    ctx.fillStyle = g2;
    ctx.beginPath();
    ctx.ellipse(x, y, r, r * 0.42, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  // Distant ridge line so the horizon is not a bare gradient.
  ctx.fillStyle = 'rgba(96,110,116,0.55)';
  ctx.beginPath();
  ctx.moveTo(0, 512);
  for (let x = 0; x <= 1024; x += 16) {
    ctx.lineTo(x, 300 + Math.sin(x * 0.011) * 22 + Math.sin(x * 0.037) * 12 + rand() * 5);
  }
  ctx.lineTo(1024, 512);
  ctx.closePath();
  ctx.fill();
  return canvas;
}

function softCanvas() {
  const { canvas, ctx } = makeCanvas(64, 64);
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.45, 'rgba(255,255,255,0.45)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return canvas;
}

function mistCanvas(rand) {
  const { canvas, ctx } = makeCanvas(256, 128);
  ctx.clearRect(0, 0, 256, 128);
  for (let i = 0; i < 140; i++) {
    const x = rand() * 256;
    const y = 20 + rand() * 90;
    const r = 25 + rand() * 70;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    const a = 0.03 + rand() * 0.09;
    g.addColorStop(0, 'rgba(238,242,244,' + a.toFixed(3) + ')');
    g.addColorStop(1, 'rgba(238,242,244,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(x, y, r, r * 0.5, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  return canvas;
}

export function createTextures() {
  const rand = mulberry32(0x5eed17);
  const made = [];
  function keep(t) { made.push(t); return t; }

  const sky = new THREE.CanvasTexture(skyCanvas(rand));
  sky.mapping = THREE.EquirectangularReflectionMapping;
  sky.colorSpace = THREE.SRGBColorSpace;
  made.push(sky);

  const tex = {
    wood: keep(toTexture(woodCanvas(rand), 1, 1)),
    steel: keep(toTexture(steelCanvas(rand), 1, 1)),
    cable: keep(toTexture(cableCanvas(), 1, 6)),
    road: keep(toTexture(roadCanvas(rand), 1, 1)),
    rock: keep(toTexture(rockCanvas(rand), 3, 3)),
    grass: keep(toTexture(grassCanvas(rand), 12, 12)),
    soft: keep(toTexture(softCanvas(), 1, 1)),
    mist: keep(toTexture(mistCanvas(rand), 1, 1)),
    sky,
    dispose() {
      for (let i = 0; i < made.length; i++) made[i].dispose();
      made.length = 0;
    },
  };
  return tex;
}
