/**
 * CONTREPOIDS - procedural canvas textures.
 *
 * Zero binary asset: every surface is painted into a 2D canvas at boot. A
 * deterministic PRNG (mulberry32) keeps every repaint identical, which matters
 * for InstancedMesh surfaces that must look the same every time the game
 * reloads a level.
 */

import * as THREE from 'three';

const SIZE = 128;

function makeCanvas(size) {
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
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

function speckle(ctx, size, seed, amount, alpha) {
  const rnd = mulberry32(seed);
  for (let i = 0; i < amount; i++) {
    const x = Math.floor(rnd() * size);
    const y = Math.floor(rnd() * size);
    const v = rnd();
    ctx.fillStyle = v > 0.5 ? 'rgba(255,255,255,' + alpha + ')' : 'rgba(0,0,0,' + alpha + ')';
    ctx.fillRect(x, y, 2, 2);
  }
}

function bevel(ctx, size, width, light, dark) {
  ctx.fillStyle = light;
  ctx.fillRect(0, 0, size, width);
  ctx.fillRect(0, 0, width, size);
  ctx.fillStyle = dark;
  ctx.fillRect(0, size - width, size, width);
  ctx.fillRect(size - width, 0, width, size);
}

function outline(ctx, size, width, color) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.strokeRect(width * 0.5, width * 0.5, size - width, size - width);
}

/** Rough-cut rock wall: the mine shaft's permanent lining. */
function rockWall() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, 0, SIZE);
  g.addColorStop(0, '#4a4038');
  g.addColorStop(1, '#332a24');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);

  const rnd = mulberry32(101);
  for (let i = 0; i < 22; i++) {
    const x = rnd() * SIZE;
    const y = rnd() * SIZE;
    const r = 6 + rnd() * 16;
    ctx.fillStyle = 'rgba(' + (20 + rnd() * 30 | 0) + ',' + (16 + rnd() * 24 | 0) + ',' + (12 + rnd() * 18 | 0) + ',0.5)';
    ctx.beginPath();
    ctx.ellipse(x, y, r, r * (0.6 + rnd() * 0.5), rnd() * Math.PI, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.strokeStyle = 'rgba(10,8,6,0.55)';
  ctx.lineWidth = 2;
  for (let i = 0; i < 10; i++) {
    ctx.beginPath();
    const y = rnd() * SIZE;
    ctx.moveTo(0, y);
    ctx.bezierCurveTo(SIZE * 0.3, y + (rnd() - 0.5) * 20, SIZE * 0.7, y + (rnd() - 0.5) * 20, SIZE, y + (rnd() - 0.5) * 10);
    ctx.stroke();
  }
  speckle(ctx, SIZE, 55, 600, 0.05);
  return c;
}

/** Worn wooden planks for platform tops. */
function woodPlanks() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#7a5636';
  ctx.fillRect(0, 0, SIZE, SIZE);
  const plankH = SIZE / 5;
  const rnd = mulberry32(9);
  for (let i = 0; i < 5; i++) {
    const y = i * plankH;
    const shade = 0.85 + rnd() * 0.25;
    ctx.fillStyle = 'rgb(' + (122 * shade | 0) + ',' + (86 * shade | 0) + ',' + (54 * shade | 0) + ')';
    ctx.fillRect(0, y + 1, SIZE, plankH - 2);
    ctx.strokeStyle = 'rgba(35,20,8,0.7)';
    ctx.lineWidth = 2;
    ctx.strokeRect(0, y, SIZE, plankH);
    // Grain streaks.
    ctx.strokeStyle = 'rgba(50,30,12,0.35)';
    ctx.lineWidth = 1;
    for (let g = 0; g < 3; g++) {
      const gy = y + 3 + rnd() * (plankH - 6);
      ctx.beginPath();
      ctx.moveTo(0, gy);
      ctx.lineTo(SIZE, gy + (rnd() - 0.5) * 4);
      ctx.stroke();
    }
    // Bolt heads at plank ends.
    ctx.fillStyle = 'rgba(20,20,22,0.8)';
    ctx.beginPath();
    ctx.arc(8, y + plankH / 2, 2.6, 0, Math.PI * 2);
    ctx.arc(SIZE - 8, y + plankH / 2, 2.6, 0, Math.PI * 2);
    ctx.fill();
  }
  bevel(ctx, SIZE, 4, 'rgba(255,220,180,0.18)', 'rgba(20,10,4,0.4)');
  return c;
}

/** Riveted iron band, used for rims, pulleys and the enclume. */
function ironBand() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, SIZE, SIZE);
  g.addColorStop(0, '#6a6f78');
  g.addColorStop(0.5, '#454a52');
  g.addColorStop(1, '#2c2f34');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);
  speckle(ctx, SIZE, 31, 500, 0.06);
  ctx.fillStyle = 'rgba(230,230,235,0.45)';
  const pad = 10;
  for (let i = 0; i < 4; i++) {
    for (let j = 0; j < 4; j++) {
      const x = pad + i * (SIZE - pad * 2) / 3;
      const y = pad + j * (SIZE - pad * 2) / 3;
      ctx.beginPath();
      ctx.arc(x, y, 2.4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  bevel(ctx, SIZE, 5, 'rgba(210,215,225,0.4)', 'rgba(8,9,11,0.6)');
  outline(ctx, SIZE, 2, 'rgba(8,9,11,0.7)');
  return c;
}

/** Rounded stone for the pierre. */
function stoneSurface() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(SIZE * 0.35, SIZE * 0.3, 4, SIZE * 0.5, SIZE * 0.5, SIZE * 0.75);
  g.addColorStop(0, '#9a978f');
  g.addColorStop(1, '#5a5850');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);
  speckle(ctx, SIZE, 41, 900, 0.06);
  ctx.strokeStyle = 'rgba(30,28,24,0.4)';
  ctx.lineWidth = 2;
  const rnd = mulberry32(42);
  for (let i = 0; i < 6; i++) {
    ctx.beginPath();
    ctx.arc(rnd() * SIZE, rnd() * SIZE, 4 + rnd() * 10, 0, Math.PI * 2);
    ctx.stroke();
  }
  return c;
}

/** Taut fabric skin for the ballon. */
function balloonSkin() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(SIZE * 0.35, SIZE * 0.3, 6, SIZE * 0.5, SIZE * 0.5, SIZE * 0.75);
  g.addColorStop(0, '#ffe27a');
  g.addColorStop(0.55, '#ff9f43');
  g.addColorStop(1, '#c96a1e');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.strokeStyle = 'rgba(120,50,4,0.35)';
  ctx.lineWidth = 3;
  for (let i = 0; i < 6; i++) {
    ctx.beginPath();
    ctx.moveTo(SIZE / 2, SIZE / 2);
    const a = (i / 6) * Math.PI * 2;
    ctx.lineTo(SIZE / 2 + Math.cos(a) * SIZE * 0.6, SIZE / 2 + Math.sin(a) * SIZE * 0.6);
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(255,255,255,0.4)';
  ctx.beginPath();
  ctx.ellipse(SIZE * 0.36, SIZE * 0.3, SIZE * 0.12, SIZE * 0.07, -0.5, 0, Math.PI * 2);
  ctx.fill();
  return c;
}

/** Rope fibre, tiled vertically along cable cylinders. */
function ropeFibre() {
  const c = makeCanvas(32);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#8a7048';
  ctx.fillRect(0, 0, 32, 32);
  ctx.strokeStyle = 'rgba(50,36,16,0.6)';
  ctx.lineWidth = 2;
  for (let i = -2; i < 5; i++) {
    ctx.beginPath();
    ctx.moveTo(i * 8, 0);
    ctx.lineTo(i * 8 + 32, 32);
    ctx.stroke();
  }
  return c;
}

/** Skin tone canvas for the miner character. */
function skinTone() {
  const c = makeCanvas(32);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#d8a878';
  ctx.fillRect(0, 0, 32, 32);
  speckle(ctx, 32, 3, 60, 0.05);
  return c;
}

/** Canvas overlay drawing an arrow, used on the exit ledge marker. */
function exitGlow() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#0b2a22';
  ctx.fillRect(0, 0, SIZE, SIZE);
  const mid = SIZE / 2;
  const g = ctx.createRadialGradient(mid, mid, 4, mid, mid, mid);
  g.addColorStop(0, '#daffef');
  g.addColorStop(0.4, '#4ce8b8');
  g.addColorStop(1, 'rgba(6,50,42,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.strokeStyle = 'rgba(210,255,240,0.85)';
  ctx.lineWidth = 4;
  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.arc(mid, mid, 16 + i * 15, 0, Math.PI * 2);
    ctx.stroke();
  }
  outline(ctx, SIZE, 5, 'rgba(150,255,220,0.8)');
  return c;
}

export function createTextures(renderer) {
  const aniso = renderer ? renderer.capabilities.getMaxAnisotropy() : 1;
  const made = [];

  function tex(canvas, opts) {
    const t = new THREE.CanvasTexture(canvas);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = aniso;
    t.wrapS = THREE.RepeatWrapping;
    t.wrapT = THREE.RepeatWrapping;
    if (opts && opts.repeat) t.repeat.set(opts.repeat[0], opts.repeat[1]);
    t.needsUpdate = true;
    made.push(t);
    return t;
  }

  const textures = {
    rock: tex(rockWall(), { repeat: [3, 3] }),
    wood: tex(woodPlanks()),
    iron: tex(ironBand()),
    stone: tex(stoneSurface()),
    balloon: tex(balloonSkin()),
    rope: tex(ropeFibre(), { repeat: [1, 4] }),
    skin: tex(skinTone()),
    exit: tex(exitGlow()),
    dispose() {
      for (let i = 0; i < made.length; i++) made[i].dispose();
      made.length = 0;
    },
  };

  return textures;
}
