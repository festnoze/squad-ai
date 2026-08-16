/**
 * OVERCLOCK - procedural textures.
 *
 * Every pixel is drawn in a 2D canvas at boot: the game ships no binary asset.
 * A seeded PRNG keeps the result identical from one run to the next, which
 * matters when comparing screenshots.
 */

import * as THREE from 'three';

function mulberry32(seed) {
  let a = seed >>> 0;
  return function rand() {
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

function toTexture(canvas, opts) {
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = opts && opts.data ? THREE.NoColorSpace : THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = opts && opts.clamp ? THREE.ClampToEdgeWrapping : THREE.RepeatWrapping;
  t.anisotropy = (opts && opts.aniso) || 1;
  t.needsUpdate = true;
  return t;
}

/** Fine grain over the whole canvas, the cheapest way to kill flat plastic. */
function grain(ctx, w, h, rand, amount) {
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const n = (rand() - 0.5) * amount;
    d[i] = Math.max(0, Math.min(255, d[i] + n));
    d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + n));
    d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + n));
  }
  ctx.putImageData(img, 0, 0);
}

function slabTexture(rand) {
  const S = 128;
  const { canvas, ctx } = makeCanvas(S, S);
  ctx.fillStyle = '#8e9ea4';
  ctx.fillRect(0, 0, S, S);

  // brushed diagonal streaks
  ctx.globalAlpha = 0.09;
  for (let i = 0; i < 90; i++) {
    ctx.strokeStyle = rand() > 0.5 ? '#ffffff' : '#40525a';
    ctx.lineWidth = 1;
    const y = rand() * S;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(S, y + (rand() - 0.5) * 10);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  // inner panel with a bevel, so tile edges read at any camera angle
  ctx.strokeStyle = 'rgba(30, 44, 50, 0.8)';
  ctx.lineWidth = 5;
  ctx.strokeRect(2.5, 2.5, S - 5, S - 5);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.28)';
  ctx.lineWidth = 2;
  ctx.strokeRect(8, 8, S - 16, S - 16);
  ctx.strokeStyle = 'rgba(30, 44, 50, 0.45)';
  ctx.lineWidth = 1;
  ctx.strokeRect(20, 20, S - 40, S - 40);

  // bolts
  for (const [bx, by] of [[16, 16], [S - 16, 16], [16, S - 16], [S - 16, S - 16]]) {
    ctx.fillStyle = 'rgba(40, 54, 60, 0.85)';
    ctx.beginPath();
    ctx.arc(bx, by, 3.4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
    ctx.beginPath();
    ctx.arc(bx - 0.9, by - 0.9, 1.5, 0, Math.PI * 2);
    ctx.fill();
  }

  // hazard hatch in one corner, purely to break the symmetry
  ctx.save();
  ctx.beginPath();
  ctx.rect(24, S - 44, 40, 20);
  ctx.clip();
  ctx.globalAlpha = 0.16;
  for (let i = -20; i < 60; i += 8) {
    ctx.strokeStyle = '#1d2b31';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(24 + i, S - 24);
    ctx.lineTo(24 + i + 20, S - 44);
    ctx.stroke();
  }
  ctx.restore();
  ctx.globalAlpha = 1;

  grain(ctx, S, S, rand, 16);
  return canvas;
}

function crateTexture(rand) {
  const S = 128;
  const { canvas, ctx } = makeCanvas(S, S);
  ctx.fillStyle = '#b98a45';
  ctx.fillRect(0, 0, S, S);
  ctx.fillStyle = 'rgba(90, 60, 24, 0.5)';
  for (let y = 0; y < S; y += 16) ctx.fillRect(0, y, S, 2);

  ctx.strokeStyle = '#6d4c1e';
  ctx.lineWidth = 9;
  ctx.strokeRect(4.5, 4.5, S - 9, S - 9);
  ctx.lineWidth = 7;
  ctx.beginPath();
  ctx.moveTo(8, 8);
  ctx.lineTo(S - 8, S - 8);
  ctx.moveTo(S - 8, 8);
  ctx.lineTo(8, S - 8);
  ctx.stroke();

  ctx.fillStyle = 'rgba(255, 236, 190, 0.75)';
  ctx.fillRect(S / 2 - 16, S / 2 - 7, 32, 14);
  ctx.fillStyle = '#4a3212';
  ctx.fillRect(S / 2 - 12, S / 2 - 3, 24, 2);
  ctx.fillRect(S / 2 - 12, S / 2 + 1, 16, 2);

  grain(ctx, S, S, rand, 22);
  return canvas;
}

/** Ring plus inner rosette, alpha only: tinted per instance at render time. */
function targetTexture() {
  const S = 128;
  const { canvas, ctx } = makeCanvas(S, S);
  const c = S / 2;
  ctx.clearRect(0, 0, S, S);

  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.arc(c, c, 46, 0, Math.PI * 2);
  ctx.stroke();

  ctx.lineWidth = 3;
  ctx.globalAlpha = 0.75;
  ctx.beginPath();
  ctx.arc(c, c, 34, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = 1;

  // four ticks
  for (let i = 0; i < 4; i++) {
    const a = (i / 4) * Math.PI * 2 + Math.PI / 4;
    ctx.lineWidth = 7;
    ctx.beginPath();
    ctx.moveTo(c + Math.cos(a) * 50, c + Math.sin(a) * 50);
    ctx.lineTo(c + Math.cos(a) * 60, c + Math.sin(a) * 60);
    ctx.stroke();
  }

  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.arc(c, c, 13, 0, Math.PI * 2);
  ctx.fill();
  return canvas;
}

function haloTexture() {
  const S = 128;
  const { canvas, ctx } = makeCanvas(S, S);
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  g.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
  g.addColorStop(0.35, 'rgba(255, 255, 255, 0.4)');
  g.addColorStop(0.72, 'rgba(255, 255, 255, 0.1)');
  g.addColorStop(1, 'rgba(255, 255, 255, 0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  return canvas;
}

function sparkTexture() {
  const S = 64;
  const { canvas, ctx } = makeCanvas(S, S);
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  g.addColorStop(0, 'rgba(255, 255, 255, 1)');
  g.addColorStop(0.45, 'rgba(255, 255, 255, 0.35)');
  g.addColorStop(1, 'rgba(255, 255, 255, 0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  return canvas;
}

function hullTexture(rand) {
  const S = 128;
  const { canvas, ctx } = makeCanvas(S, S);
  ctx.fillStyle = '#546e79';
  ctx.fillRect(0, 0, S, S);
  ctx.fillStyle = '#63808c';
  ctx.fillRect(0, 0, S, S * 0.42);

  ctx.strokeStyle = 'rgba(20, 34, 40, 0.3)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 10; i++) {
    const y = 10 + rand() * (S - 20);
    ctx.beginPath();
    ctx.moveTo(6, y);
    ctx.lineTo(S - 6, y);
    ctx.stroke();
  }

  ctx.fillStyle = 'rgba(33, 227, 154, 0.85)';
  ctx.fillRect(0, S * 0.56, S, 6);
  ctx.fillStyle = 'rgba(33, 227, 154, 0.3)';
  ctx.fillRect(0, S * 0.66, S, 2);

  ctx.fillStyle = 'rgba(10, 16, 18, 0.7)';
  ctx.fillRect(S * 0.1, S * 0.78, S * 0.34, S * 0.12);
  ctx.fillRect(S * 0.56, S * 0.78, S * 0.2, S * 0.12);

  grain(ctx, S, S, rand, 14);
  return canvas;
}

function groundTexture(rand) {
  const S = 256;
  const { canvas, ctx } = makeCanvas(S, S);
  ctx.fillStyle = '#0c1a1e';
  ctx.fillRect(0, 0, S, S);
  ctx.strokeStyle = 'rgba(33, 227, 154, 0.16)';
  ctx.lineWidth = 2;
  ctx.strokeRect(0, 0, S, S);
  ctx.strokeStyle = 'rgba(33, 227, 154, 0.07)';
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    const p = (i / 4) * S;
    ctx.beginPath();
    ctx.moveTo(p, 0);
    ctx.lineTo(p, S);
    ctx.moveTo(0, p);
    ctx.lineTo(S, p);
    ctx.stroke();
  }
  grain(ctx, S, S, rand, 8);
  return canvas;
}

export function createTextures(renderer) {
  const aniso = renderer ? renderer.capabilities.getMaxAnisotropy() : 1;

  const tex = {
    slab: toTexture(slabTexture(mulberry32(11)), { aniso, clamp: true }),
    crate: toTexture(crateTexture(mulberry32(29)), { aniso, clamp: true }),
    target: toTexture(targetTexture(), { clamp: true, aniso }),
    halo: toTexture(haloTexture(), { clamp: true }),
    spark: toTexture(sparkTexture(), { clamp: true }),
    hull: toTexture(hullTexture(mulberry32(53)), { aniso, clamp: true }),
    ground: toTexture(groundTexture(mulberry32(71)), { aniso }),

    dispose() {
      for (const k of Object.keys(tex)) {
        const v = tex[k];
        if (v && v.isTexture) v.dispose();
      }
    },
  };

  tex.ground.repeat.set(24, 24);
  return tex;
}
