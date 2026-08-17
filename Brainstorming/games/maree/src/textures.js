/**
 * MAREE - procedural textures. Every surface in the game is painted here on a
 * 2D canvas; there is not one binary image in the project. A seeded PRNG keeps
 * a given texture identical between two runs.
 *
 * No text is ever drawn on these canvases: canvas font rendering of accented
 * French is unreliable, so any label lives in the DOM instead (see hud.js).
 */

import * as THREE from 'three';

function mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
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
  return c;
}

function ctxOf(canvas) {
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  return ctx;
}

function rgbOf(hex) {
  return [(hex >> 16) & 255, (hex >> 8) & 255, hex & 255];
}

function cssOf(hex, alpha) {
  const c = rgbOf(hex);
  return alpha === undefined ? 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')' : 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + alpha + ')';
}

function cssGray(v, alpha) {
  const g = Math.max(0, Math.min(255, Math.round(v)));
  return alpha === undefined ? 'rgb(' + g + ',' + g + ',' + g + ')' : 'rgba(' + g + ',' + g + ',' + g + ',' + alpha + ')';
}

/** Speckled grain, the base of every stone/rock surface in the game. */
function grainTile(rand, size, lo, hi, count) {
  const canvas = makeCanvas(size, size);
  const ctx = ctxOf(canvas);
  ctx.fillStyle = cssGray((lo + hi) / 2);
  ctx.fillRect(0, 0, size, size);
  for (let i = 0; i < count; i++) {
    const v = lo + rand() * (hi - lo);
    const r = 0.5 + rand() * 2.2;
    ctx.fillStyle = cssGray(v, 0.5 + rand() * 0.4);
    ctx.beginPath();
    ctx.arc(rand() * size, rand() * size, r, 0, Math.PI * 2);
    ctx.fill();
  }
  return canvas;
}

function makeTexture(canvas, colorSpace) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = colorSpace || THREE.SRGBColorSpace;
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.needsUpdate = true;
  return tex;
}

function buildRock(rand) {
  const c = grainTile(rand, 256, 60, 130, 2600);
  const ctx = ctxOf(c);
  // A few darker cracks so a flat rock face still reads as rock up close.
  ctx.strokeStyle = 'rgba(30,26,20,0.35)';
  ctx.lineWidth = 1.4;
  for (let i = 0; i < 10; i++) {
    ctx.beginPath();
    let x = rand() * 256;
    let y = rand() * 256;
    ctx.moveTo(x, y);
    for (let k = 0; k < 4; k++) {
      x += (rand() - 0.5) * 60;
      y += (rand() - 0.5) * 60;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  return c;
}

function buildShore(rand) {
  const c = grainTile(rand, 256, 90, 160, 2200);
  const ctx = ctxOf(c);
  ctx.strokeStyle = 'rgba(60,50,34,0.3)';
  ctx.lineWidth = 1.2;
  for (let i = 0; i < 8; i++) {
    ctx.beginPath();
    let x = rand() * 256;
    let y = rand() * 256;
    ctx.moveTo(x, y);
    for (let k = 0; k < 3; k++) {
      x += (rand() - 0.5) * 50;
      y += (rand() - 0.5) * 50;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  return c;
}

function buildWood(rand) {
  const size = 256;
  const c = makeCanvas(size, size);
  const ctx = ctxOf(c);
  ctx.fillStyle = '#a9784a';
  ctx.fillRect(0, 0, size, size);
  const planks = 4;
  for (let p = 0; p < planks; p++) {
    const y = (p * size) / planks;
    const h = size / planks;
    const tone = 0.85 + rand() * 0.3;
    ctx.fillStyle = 'rgb(' + Math.round(169 * tone) + ',' + Math.round(120 * tone) + ',' + Math.round(74 * tone) + ')';
    ctx.fillRect(0, y, size, h);
    ctx.strokeStyle = 'rgba(50,32,16,0.5)';
    ctx.lineWidth = 2;
    ctx.strokeRect(0, y, size, h);
    // Grain lines along the plank.
    ctx.strokeStyle = 'rgba(70,44,20,0.25)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i++) {
      const gy = y + 4 + rand() * (h - 8);
      ctx.beginPath();
      ctx.moveTo(0, gy);
      for (let x = 0; x <= size; x += 24) ctx.lineTo(x, gy + (rand() - 0.5) * 4);
      ctx.stroke();
    }
    // A couple of iron nail heads per plank.
    for (let n = 0; n < 2; n++) {
      const nx = size * 0.15 + n * size * 0.7;
      ctx.beginPath();
      ctx.arc(nx, y + h * 0.5, 3, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(30,26,24,0.7)';
      ctx.fill();
    }
  }
  return c;
}

function buildStone(rand) {
  const c = grainTile(rand, 256, 45, 100, 3000);
  const ctx = ctxOf(c);
  ctx.strokeStyle = 'rgba(10,10,12,0.4)';
  ctx.lineWidth = 2;
  for (let i = 0; i < 6; i++) {
    ctx.beginPath();
    let x = rand() * 256;
    let y = rand() * 256;
    ctx.moveTo(x, y);
    for (let k = 0; k < 3; k++) {
      x += (rand() - 0.5) * 70;
      y += (rand() - 0.5) * 70;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  return c;
}

function buildIce(rand) {
  const size = 256;
  const c = makeCanvas(size, size);
  const ctx = ctxOf(c);
  const grad = ctx.createLinearGradient(0, 0, size, size);
  grad.addColorStop(0, '#dff5f7');
  grad.addColorStop(1, '#a9dde2');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = 'rgba(255,255,255,0.6)';
  ctx.lineWidth = 1.5;
  for (let i = 0; i < 14; i++) {
    ctx.beginPath();
    let x = rand() * size;
    let y = rand() * size;
    ctx.moveTo(x, y);
    for (let k = 0; k < 3; k++) {
      x += (rand() - 0.5) * 60;
      y += (rand() - 0.5) * 60;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  return c;
}

function buildSuit(rand) {
  const size = 128;
  const c = makeCanvas(size, size);
  const ctx = ctxOf(c);
  ctx.fillStyle = '#2a6f8f';
  ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = '#e8a23a';
  for (let y = 0; y < size; y += 24) ctx.fillRect(0, y, size, 6);
  for (let i = 0; i < 400; i++) {
    ctx.fillStyle = 'rgba(0,0,0,' + (0.03 + rand() * 0.05) + ')';
    ctx.fillRect(rand() * size, rand() * size, 2, 2);
  }
  return c;
}

export function createTextures() {
  const rand = mulberry32(20260816);
  const rock = makeTexture(buildRock(rand));
  const shore = makeTexture(buildShore(rand));
  const wood = makeTexture(buildWood(rand));
  const stone = makeTexture(buildStone(rand));
  const ice = makeTexture(buildIce(rand));
  const suit = makeTexture(buildSuit(rand));
  const owned = [rock, shore, wood, stone, ice, suit];

  return {
    rock,
    shore,
    wood,
    stone,
    ice,
    suit,
    dispose() {
      for (const t of owned) t.dispose();
    },
  };
}
