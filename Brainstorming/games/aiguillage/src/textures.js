/**
 * AIGUILLAGE - procedural canvas textures.
 *
 * Every texture is drawn in a 2D canvas at build time (no binary assets).
 * A local deterministic PRNG (mulberry32) is used everywhere instead of
 * Math.random so two runs of the game produce pixel identical textures.
 */

import * as THREE from 'three';

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
  return c;
}

function finish(canvas, renderer, opts) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.anisotropy = renderer ? renderer.capabilities.getMaxAnisotropy() : 4;
  tex.needsUpdate = true;
  if (opts && opts.colorSpace) tex.colorSpace = opts.colorSpace;
  else tex.colorSpace = THREE.SRGBColorSpace;
  if (opts && opts.noRepeat) {
    tex.wrapS = THREE.ClampToEdgeWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
  }
  return tex;
}

function drawBallast(ctx, w, h, rnd) {
  ctx.fillStyle = '#33302c';
  ctx.fillRect(0, 0, w, h);
  const stones = 900;
  for (let i = 0; i < stones; i++) {
    const x = rnd() * w;
    const y = rnd() * h;
    const r = 1.2 + rnd() * 2.6;
    const tone = 30 + rnd() * 55;
    ctx.fillStyle = `rgb(${tone + 20},${tone + 14},${tone + 8})`;
    ctx.beginPath();
    ctx.ellipse(x, y, r, r * (0.7 + rnd() * 0.4), rnd() * Math.PI, 0, Math.PI * 2);
    ctx.fill();
  }
  // faint diagonal shading so the tile does not read as pure noise
  ctx.globalAlpha = 0.08;
  ctx.fillStyle = '#000000';
  for (let i = 0; i < 10; i++) {
    ctx.fillRect(0, (i / 10) * h, w, h / 30);
  }
  ctx.globalAlpha = 1;
}

function drawGround(ctx, w, h, rnd) {
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, '#20241f');
  grad.addColorStop(1, '#161a15');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
  ctx.globalAlpha = 0.5;
  for (let i = 0; i < 500; i++) {
    const x = rnd() * w;
    const y = rnd() * h;
    const r = 2 + rnd() * 5;
    ctx.fillStyle = rnd() > 0.5 ? '#272c22' : '#191d16';
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  // sparse painted yard markings (worn yellow)
  ctx.strokeStyle = 'rgba(210,180,60,0.18)';
  ctx.lineWidth = 3;
  for (let i = 0; i < 6; i++) {
    const y = (i / 6) * h + 12;
    ctx.setLineDash([18, 14]);
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  ctx.setLineDash([]);
}

function drawSleeper(ctx, w, h, rnd) {
  ctx.fillStyle = '#3c2a1e';
  ctx.fillRect(0, 0, w, h);
  for (let i = 0; i < 220; i++) {
    const x = rnd() * w;
    const y = rnd() * h;
    ctx.strokeStyle = `rgba(20,12,8,${0.15 + rnd() * 0.2})`;
    ctx.lineWidth = 1 + rnd();
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x + (rnd() - 0.5) * 6, h);
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(0,0,0,0.35)';
  ctx.lineWidth = 3;
  ctx.strokeRect(2, 2, w - 4, h - 4);
}

function drawPanel(ctx, w, h, rnd) {
  ctx.fillStyle = '#4a5058';
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(0,0,0,0.35)';
  ctx.lineWidth = 2;
  const cols = 5;
  const rows = 8;
  for (let i = 0; i <= cols; i++) {
    const x = (i / cols) * w;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  for (let j = 0; j <= rows; j++) {
    const y = (j / rows) * h;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  for (let i = 0; i < 260; i++) {
    ctx.fillStyle = `rgba(0,0,0,${rnd() * 0.08})`;
    ctx.fillRect(rnd() * w, rnd() * h, 6, 6);
  }
}

function drawWindows(ctx, w, h, rnd) {
  ctx.clearRect(0, 0, w, h);
  const cols = 6;
  const rows = 10;
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      if (rnd() > 0.4) continue;
      const x = (i / cols) * w + w / cols * 0.18;
      const y = (j / rows) * h + h / rows * 0.18;
      const ww = w / cols * 0.64;
      const hh = h / rows * 0.64;
      const warm = rnd() > 0.5;
      ctx.fillStyle = warm ? 'rgba(255,200,120,0.95)' : 'rgba(170,210,255,0.85)';
      ctx.fillRect(x, y, ww, hh);
    }
  }
}

function drawGlow(ctx, w, h) {
  const cx = w / 2;
  const cy = h / 2;
  const r = w / 2;
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.35, 'rgba(255,255,255,0.55)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
}

function drawSpark(ctx, w, h) {
  const cx = w / 2;
  const cy = h / 2;
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, w / 2);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.5, 'rgba(255,255,255,0.35)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
}

function drawBarrier(ctx, w, h) {
  ctx.fillStyle = '#d8d3c8';
  ctx.fillRect(0, 0, w, h);
  const stripes = 6;
  ctx.fillStyle = '#c23b2e';
  for (let i = 0; i < stripes; i++) {
    if (i % 2 === 0) continue;
    ctx.fillRect((i / stripes) * w, 0, w / stripes, h);
  }
}

export function createTextures(renderer) {
  const rnd1 = mulberry32(0xba11a57);
  const rnd2 = mulberry32(0x7ed17ac);
  const rnd3 = mulberry32(0x51ee9e2);
  const rnd4 = mulberry32(0x0ff1ce1);
  const rnd5 = mulberry32(0xca11d0f);

  const cBallast = makeCanvas(256, 256);
  drawBallast(cBallast.getContext('2d'), 256, 256, rnd1);

  const cGround = makeCanvas(256, 256);
  drawGround(cGround.getContext('2d'), 256, 256, rnd2);

  const cSleeper = makeCanvas(64, 32);
  drawSleeper(cSleeper.getContext('2d'), 64, 32, rnd3);

  const cPanel = makeCanvas(128, 128);
  drawPanel(cPanel.getContext('2d'), 128, 128, rnd4);

  const cWindows = makeCanvas(128, 192);
  drawWindows(cWindows.getContext('2d'), 128, 192, rnd5);

  const cGlow = makeCanvas(64, 64);
  drawGlow(cGlow.getContext('2d'), 64, 64);

  const cSpark = makeCanvas(32, 32);
  drawSpark(cSpark.getContext('2d'), 32, 32);

  const cBarrier = makeCanvas(64, 16);
  drawBarrier(cBarrier.getContext('2d'), 64, 16);

  const textures = {
    ballast: finish(cBallast, renderer),
    ground: finish(cGround, renderer),
    sleeper: finish(cSleeper, renderer),
    panel: finish(cPanel, renderer),
    windows: finish(cWindows, renderer, { noRepeat: true }),
    glow: finish(cGlow, renderer, { noRepeat: true }),
    spark: finish(cSpark, renderer, { noRepeat: true }),
    barrier: finish(cBarrier, renderer),
    dispose() {
      this.ballast.dispose();
      this.ground.dispose();
      this.sleeper.dispose();
      this.panel.dispose();
      this.windows.dispose();
      this.glow.dispose();
      this.spark.dispose();
      this.barrier.dispose();
    },
  };
  return textures;
}
