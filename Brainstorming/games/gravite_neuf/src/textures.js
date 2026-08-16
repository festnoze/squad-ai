/**
 * GRAVITE NEUF - procedural canvas textures.
 *
 * Zero binary asset: every surface is painted into a 2D canvas at boot. Each
 * cube face texture bakes its own bevelled border, which is what lets a whole
 * wall drawn as a single InstancedMesh still read as individual cubes without
 * paying for one LineSegments per block.
 */

import * as THREE from 'three';

export const PALETTE = {
  wall: '#59637a',
  wallDark: '#2b3244',
  glue: '#e8a33d',
  glueDark: '#7a4f14',
  spike: '#8c3b46',
  spikeDark: '#3a1a22',
  exit: '#3ce8b4',
  plateA: '#b47cff',
  plateB: '#4fd0ff',
  player: '#ffc94a',
  crate: '#c98a45',
  key: '#fff0a8',
};

const SIZE = 128;

function makeCanvas(size) {
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
  return c;
}

/** Deterministic PRNG so two boots paint exactly the same speckle. */
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

/** Bevelled frame: bright on the top and left, dark on the bottom and right. */
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

function wallFace() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, SIZE, SIZE);
  g.addColorStop(0, '#5d6880');
  g.addColorStop(1, '#3d4559');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);

  ctx.fillStyle = 'rgba(20,24,36,0.35)';
  ctx.fillRect(16, 16, SIZE - 32, SIZE - 32);
  ctx.strokeStyle = 'rgba(150,168,200,0.30)';
  ctx.lineWidth = 2;
  ctx.strokeRect(16, 16, SIZE - 32, SIZE - 32);

  ctx.fillStyle = 'rgba(160,178,210,0.42)';
  const r = 4;
  const pads = [
    [26, 26],
    [SIZE - 26, 26],
    [26, SIZE - 26],
    [SIZE - 26, SIZE - 26],
  ];
  for (let i = 0; i < pads.length; i++) {
    ctx.beginPath();
    ctx.arc(pads[i][0], pads[i][1], r, 0, Math.PI * 2);
    ctx.fill();
  }

  speckle(ctx, SIZE, 7, 900, 0.055);
  bevel(ctx, SIZE, 6, 'rgba(190,206,236,0.55)', 'rgba(12,15,24,0.62)');
  outline(ctx, SIZE, 3, 'rgba(10,13,22,0.85)');
  return c;
}

function glueFace() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, 0, SIZE);
  g.addColorStop(0, '#f0b757');
  g.addColorStop(1, '#a86c1c');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);

  // Sticky blobs, drawn from a fixed seed so the pattern is stable.
  const rnd = mulberry32(21);
  for (let i = 0; i < 16; i++) {
    const x = rnd() * SIZE;
    const y = rnd() * SIZE;
    const rr = 6 + rnd() * 16;
    const grad = ctx.createRadialGradient(x, y, 0, x, y, rr);
    grad.addColorStop(0, 'rgba(255,226,150,0.75)');
    grad.addColorStop(1, 'rgba(255,226,150,0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(x, y, rr, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.strokeStyle = 'rgba(90,54,8,0.55)';
  ctx.lineWidth = 3;
  for (let i = 0; i < 5; i++) {
    const x = 12 + i * 26;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x + 6, 22 + ((i * 13) % 26));
    ctx.stroke();
  }
  bevel(ctx, SIZE, 6, 'rgba(255,238,190,0.60)', 'rgba(70,40,4,0.60)');
  outline(ctx, SIZE, 3, 'rgba(56,32,4,0.9)');
  return c;
}

function spikeFace() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#2f1a20';
  ctx.fillRect(0, 0, SIZE, SIZE);
  speckle(ctx, SIZE, 3, 700, 0.08);

  // Four blades pointing outward from the centre of the face.
  const mid = SIZE / 2;
  const half = 22;
  const tips = [
    [mid, 8, half, 0],
    [SIZE - 8, mid, 0, half],
    [mid, SIZE - 8, half, 0],
    [8, mid, 0, half],
  ];
  for (let i = 0; i < tips.length; i++) {
    const [tx, ty, ox, oy] = tips[i];
    const g = ctx.createLinearGradient(mid, mid, tx, ty);
    g.addColorStop(0, '#6d2c37');
    g.addColorStop(0.7, '#c85a64');
    g.addColorStop(1, '#ffd9d0');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(tx, ty);
    ctx.lineTo(mid - ox, mid - oy);
    ctx.lineTo(mid + ox, mid + oy);
    ctx.closePath();
    ctx.fill();
  }
  ctx.fillStyle = 'rgba(20,10,14,0.9)';
  ctx.beginPath();
  ctx.arc(mid, mid, 12, 0, Math.PI * 2);
  ctx.fill();
  bevel(ctx, SIZE, 6, 'rgba(220,150,150,0.30)', 'rgba(0,0,0,0.7)');
  outline(ctx, SIZE, 3, 'rgba(0,0,0,0.9)');
  return c;
}

function exitFace() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#052b24';
  ctx.fillRect(0, 0, SIZE, SIZE);
  const mid = SIZE / 2;
  const g = ctx.createRadialGradient(mid, mid, 4, mid, mid, mid);
  g.addColorStop(0, '#d8fff2');
  g.addColorStop(0.35, PALETTE.exit);
  g.addColorStop(1, 'rgba(6,60,50,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);

  ctx.strokeStyle = 'rgba(220,255,244,0.9)';
  ctx.lineWidth = 4;
  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.arc(mid, mid, 18 + i * 16, 0, Math.PI * 2);
    ctx.stroke();
  }
  outline(ctx, SIZE, 5, 'rgba(120,255,220,0.85)');
  return c;
}

function plateFace(color) {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.fillStyle = 'rgba(14,18,28,1)';
  ctx.fillRect(0, 0, SIZE, SIZE);
  const mid = SIZE / 2;
  ctx.strokeStyle = color;
  ctx.lineWidth = 8;
  ctx.strokeRect(20, 20, SIZE - 40, SIZE - 40);
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(mid, 30);
  ctx.lineTo(mid, SIZE - 30);
  ctx.moveTo(30, mid);
  ctx.lineTo(SIZE - 30, mid);
  ctx.stroke();
  outline(ctx, SIZE, 4, color);
  return c;
}

function gateFace(color) {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, SIZE, SIZE);
  ctx.fillStyle = 'rgba(10,14,24,0.55)';
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.strokeStyle = color;
  ctx.lineWidth = 6;
  for (let i = 1; i < 4; i++) {
    ctx.beginPath();
    ctx.moveTo((i * SIZE) / 4, 0);
    ctx.lineTo((i * SIZE) / 4, SIZE);
    ctx.stroke();
  }
  ctx.lineWidth = 10;
  ctx.strokeRect(5, 5, SIZE - 10, SIZE - 10);
  return c;
}

function playerFace() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, SIZE, SIZE);
  g.addColorStop(0, '#ffe08a');
  g.addColorStop(1, '#e08c14');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.fillStyle = 'rgba(60,32,0,0.28)';
  ctx.fillRect(22, 22, SIZE - 44, SIZE - 44);
  ctx.strokeStyle = 'rgba(255,250,220,0.95)';
  ctx.lineWidth = 5;
  ctx.strokeRect(22, 22, SIZE - 44, SIZE - 44);
  const mid = SIZE / 2;
  ctx.fillStyle = 'rgba(255,252,235,0.95)';
  ctx.beginPath();
  ctx.arc(mid, mid, 11, 0, Math.PI * 2);
  ctx.fill();
  speckle(ctx, SIZE, 11, 400, 0.05);
  bevel(ctx, SIZE, 6, 'rgba(255,255,230,0.7)', 'rgba(90,50,0,0.55)');
  outline(ctx, SIZE, 3, 'rgba(70,38,0,0.9)');
  return c;
}

function crateFace() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#7b5228';
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.fillStyle = '#96652f';
  for (let i = 0; i < 4; i++) ctx.fillRect(0, i * 32 + 3, SIZE, 26);
  ctx.strokeStyle = 'rgba(40,24,8,0.6)';
  ctx.lineWidth = 3;
  for (let i = 0; i < 4; i++) {
    ctx.beginPath();
    ctx.moveTo(0, i * 32 + 32);
    ctx.lineTo(SIZE, i * 32 + 32);
    ctx.stroke();
  }
  ctx.fillStyle = '#c9903f';
  ctx.fillRect(0, 0, SIZE, 14);
  ctx.fillRect(0, SIZE - 14, SIZE, 14);
  ctx.fillRect(0, 0, 14, SIZE);
  ctx.fillRect(SIZE - 14, 0, 14, SIZE);
  ctx.fillStyle = 'rgba(255,222,160,0.55)';
  for (let i = 0; i < 4; i++) {
    const p = [
      [8, 8],
      [SIZE - 12, 8],
      [8, SIZE - 12],
      [SIZE - 12, SIZE - 12],
    ][i];
    ctx.fillRect(p[0] - 1, p[1] - 1, 6, 6);
  }
  speckle(ctx, SIZE, 5, 700, 0.07);
  bevel(ctx, SIZE, 5, 'rgba(255,225,170,0.42)', 'rgba(30,16,4,0.55)');
  outline(ctx, SIZE, 3, 'rgba(30,16,4,0.9)');
  return c;
}

function keyFace() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#4a3a06';
  ctx.fillRect(0, 0, SIZE, SIZE);
  const mid = SIZE / 2;
  const g = ctx.createRadialGradient(mid, mid, 2, mid, mid, mid * 0.95);
  g.addColorStop(0, '#ffffff');
  g.addColorStop(0.4, PALETTE.key);
  g.addColorStop(1, 'rgba(120,90,0,0.2)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SIZE, SIZE);
  return c;
}

function gridTile() {
  const c = makeCanvas(SIZE);
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, SIZE, SIZE);
  ctx.strokeStyle = 'rgba(150,190,240,0.30)';
  ctx.lineWidth = 3;
  ctx.strokeRect(1.5, 1.5, SIZE - 3, SIZE - 3);
  ctx.strokeStyle = 'rgba(150,190,240,0.10)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(SIZE / 2, 0);
  ctx.lineTo(SIZE / 2, SIZE);
  ctx.moveTo(0, SIZE / 2);
  ctx.lineTo(SIZE, SIZE / 2);
  ctx.stroke();
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
    wall: tex(wallFace()),
    glue: tex(glueFace()),
    spike: tex(spikeFace()),
    exit: tex(exitFace()),
    plateA: tex(plateFace(PALETTE.plateA)),
    plateB: tex(plateFace(PALETTE.plateB)),
    gateA: tex(gateFace(PALETTE.plateA)),
    gateB: tex(gateFace(PALETTE.plateB)),
    player: tex(playerFace()),
    crate: tex(crateFace()),
    key: tex(keyFace()),
    grid: tex(gridTile()),
    dispose() {
      for (let i = 0; i < made.length; i++) made[i].dispose();
      made.length = 0;
    },
  };

  return textures;
}
