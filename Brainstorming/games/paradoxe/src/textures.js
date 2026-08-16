/**
 * PARADOXE - procedural textures.
 *
 * Zero binary assets: every surface is drawn once into a 2D canvas at boot.
 * The PRNG is seeded so two sessions look identical, which matters here because
 * the game is about repeating the same run and any visual drift reads as a bug.
 */

import * as THREE from 'three';
import { PALETTE } from './config.js';

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
  c.height = h || w;
  return c;
}

function hex(n) {
  return '#' + n.toString(16).padStart(6, '0');
}

function grain(ctx, w, h, rnd, amount, alpha) {
  for (let i = 0; i < amount; i++) {
    const x = rnd() * w;
    const y = rnd() * h;
    const s = 1 + rnd() * 2;
    ctx.fillStyle = rnd() > 0.5 ? 'rgba(255,255,255,' + alpha + ')' : 'rgba(0,0,0,' + alpha + ')';
    ctx.fillRect(x, y, s, s);
  }
}

function toTexture(canvas, repeat, srgb, aniso) {
  const t = new THREE.CanvasTexture(canvas);
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = srgb === false ? THREE.NoColorSpace : THREE.SRGBColorSpace;
  t.anisotropy = aniso || 1;
  if (repeat) t.repeat.set(repeat, repeat);
  t.needsUpdate = true;
  return t;
}

function drawFloor(rnd) {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, S, S);
  g.addColorStop(0, '#2c4759');
  g.addColorStop(0.5, '#345365');
  g.addColorStop(1, '#294152');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);

  // Fine inner hatch so a large floor never reads as flat paint.
  ctx.strokeStyle = 'rgba(120,190,220,0.055)';
  ctx.lineWidth = 1;
  for (let i = 0; i < S; i += 16) {
    ctx.beginPath();
    ctx.moveTo(i + 0.5, 0);
    ctx.lineTo(i + 0.5, S);
    ctx.moveTo(0, i + 0.5);
    ctx.lineTo(S, i + 0.5);
    ctx.stroke();
  }
  // Tile border.
  ctx.strokeStyle = 'rgba(90,220,255,0.22)';
  ctx.lineWidth = 4;
  ctx.strokeRect(2, 2, S - 4, S - 4);
  ctx.strokeStyle = 'rgba(10,20,28,0.55)';
  ctx.lineWidth = 2;
  ctx.strokeRect(7, 7, S - 14, S - 14);

  // Corner brackets.
  ctx.strokeStyle = 'rgba(120,230,255,0.30)';
  ctx.lineWidth = 3;
  const m = 22;
  const l = 34;
  const corners = [
    [m, m, 1, 1],
    [S - m, m, -1, 1],
    [m, S - m, 1, -1],
    [S - m, S - m, -1, -1],
  ];
  for (const [x, y, sx, sy] of corners) {
    ctx.beginPath();
    ctx.moveTo(x + sx * l, y);
    ctx.lineTo(x, y);
    ctx.lineTo(x, y + sy * l);
    ctx.stroke();
  }
  grain(ctx, S, S, rnd, 900, 0.045);
  return c;
}

function drawBlock(rnd) {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#2c4a5c';
  ctx.fillRect(0, 0, S, S);
  ctx.fillStyle = 'rgba(255,255,255,0.04)';
  for (let y = 0; y < S; y += 64) {
    for (let x = 0; x < S; x += 64) {
      if (((x + y) / 64) % 2 === 0) ctx.fillRect(x, y, 64, 64);
    }
  }
  ctx.strokeStyle = 'rgba(8,16,22,0.6)';
  ctx.lineWidth = 3;
  for (let i = 0; i <= S; i += 64) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i, S);
    ctx.moveTo(0, i);
    ctx.lineTo(S, i);
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(120,230,255,0.5)';
  for (let y = 32; y < S; y += 64) {
    for (let x = 32; x < S; x += 64) {
      ctx.fillRect(x - 3, y - 3, 6, 6);
    }
  }
  grain(ctx, S, S, rnd, 700, 0.05);
  return c;
}

function drawWall(rnd) {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  // Walls face away from the sun and cover a lot of screen from a high camera:
  // too dark a base and half the arena reads as a hole in the floor.
  ctx.fillStyle = '#2b4655';
  ctx.fillRect(0, 0, S, S);
  ctx.fillStyle = 'rgba(255,255,255,0.05)';
  for (let x = 0; x < S; x += 32) if ((x / 32) % 2 === 0) ctx.fillRect(x, 0, 32, S);
  ctx.strokeStyle = 'rgba(10,20,26,0.7)';
  ctx.lineWidth = 2;
  for (let x = 0; x <= S; x += 32) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, S);
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(130,220,250,0.26)';
  ctx.lineWidth = 2;
  for (let y = 24; y < S; y += 84) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(S, y);
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(140,225,255,0.34)';
  for (let i = 0; i < 22; i++) {
    const x = Math.floor(rnd() * 8) * 32 + 12;
    const y = rnd() * S;
    ctx.fillRect(x, y, 8, 3);
  }
  grain(ctx, S, S, rnd, 600, 0.05);
  return c;
}

function drawCrate(rnd) {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#7a5326';
  ctx.fillRect(0, 0, S, S);
  ctx.fillStyle = 'rgba(0,0,0,0.16)';
  for (let y = 0; y < S; y += 26) if ((y / 26) % 2 === 0) ctx.fillRect(0, y, S, 26);
  ctx.strokeStyle = '#c99a4e';
  ctx.lineWidth = 14;
  ctx.strokeRect(7, 7, S - 14, S - 14);
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.moveTo(16, 16);
  ctx.lineTo(S - 16, S - 16);
  ctx.moveTo(S - 16, 16);
  ctx.lineTo(16, S - 16);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(0,0,0,0.35)';
  ctx.lineWidth = 2;
  ctx.strokeRect(14, 14, S - 28, S - 28);
  grain(ctx, S, S, rnd, 1200, 0.07);
  return c;
}

function drawButton() {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#101d26';
  ctx.fillRect(0, 0, S, S);
  ctx.translate(S / 2, S / 2);
  ctx.strokeStyle = hex(PALETTE.accentWarm);
  ctx.lineWidth = 8;
  ctx.beginPath();
  ctx.arc(0, 0, 92, 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = 4;
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(Math.cos(a) * 68, Math.sin(a) * 68);
    ctx.lineTo(Math.cos(a) * 84, Math.sin(a) * 84);
    ctx.stroke();
  }
  const g = ctx.createRadialGradient(0, 0, 6, 0, 0, 62);
  g.addColorStop(0, 'rgba(255,220,150,0.95)');
  g.addColorStop(1, 'rgba(255,150,60,0.10)');
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(0, 0, 62, 0, Math.PI * 2);
  ctx.fill();
  return c;
}

function drawPlate() {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#171226';
  ctx.fillRect(0, 0, S, S);
  ctx.strokeStyle = hex(PALETTE.plate);
  ctx.lineWidth = 8;
  ctx.strokeRect(20, 20, S - 40, S - 40);
  ctx.lineWidth = 3;
  ctx.globalAlpha = 0.55;
  for (let i = -S; i < S * 2; i += 22) {
    ctx.beginPath();
    ctx.moveTo(i, 20);
    ctx.lineTo(i - S + 40, S - 20);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 6;
  ctx.strokeRect(20, 20, S - 40, S - 40);
  return c;
}

function drawFragile(rnd) {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#3c4a54';
  ctx.fillRect(0, 0, S, S);
  ctx.strokeStyle = 'rgba(220,240,255,0.32)';
  ctx.lineWidth = 3;
  for (let i = 0; i < 16; i++) {
    ctx.beginPath();
    let x = rnd() * S;
    let y = rnd() * S;
    ctx.moveTo(x, y);
    for (let k = 0; k < 4; k++) {
      x += (rnd() - 0.5) * 90;
      y += (rnd() - 0.5) * 90;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(255,255,255,0.18)';
  ctx.lineWidth = 6;
  ctx.strokeRect(4, 4, S - 8, S - 8);
  grain(ctx, S, S, rnd, 800, 0.07);
  return c;
}

function drawExit() {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#04120c';
  ctx.fillRect(0, 0, S, S);
  ctx.translate(S / 2, S / 2);
  for (let r = 108; r > 12; r -= 22) {
    ctx.strokeStyle = 'rgba(125,255,158,' + (0.10 + (1 - r / 108) * 0.55).toFixed(3) + ')';
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.stroke();
  }
  const g = ctx.createRadialGradient(0, 0, 2, 0, 0, 70);
  g.addColorStop(0, 'rgba(230,255,240,0.95)');
  g.addColorStop(1, 'rgba(125,255,158,0)');
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(0, 0, 70, 0, Math.PI * 2);
  ctx.fill();
  return c;
}

function drawTele() {
  const S = 256;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#0a1626';
  ctx.fillRect(0, 0, S, S);
  ctx.translate(S / 2, S / 2);
  ctx.strokeStyle = 'rgba(80,220,255,0.85)';
  ctx.lineWidth = 5;
  for (let k = 0; k < 3; k++) {
    ctx.beginPath();
    for (let i = 0; i <= 120; i++) {
      const t = i / 120;
      const a = t * Math.PI * 3 + (k / 3) * Math.PI * 2;
      const r = 12 + t * 100;
      const x = Math.cos(a) * r;
      const y = Math.sin(a) * r;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(180,240,255,0.55)';
  ctx.lineWidth = 7;
  ctx.beginPath();
  ctx.arc(0, 0, 116, 0, Math.PI * 2);
  ctx.stroke();
  return c;
}

function drawSky() {
  const W = 1024;
  const H = 512;
  const c = makeCanvas(W, H);
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#050a12');
  g.addColorStop(0.55, '#0a1a28');
  g.addColorStop(0.78, '#123049');
  g.addColorStop(1, '#071019');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  const rnd = mulberry32(20260816);
  // Soft nebula bands, kept dim: the arena neon has to stay the brightest thing.
  for (let i = 0; i < 18; i++) {
    const x = rnd() * W;
    const y = H * (0.4 + rnd() * 0.45);
    const r = 140 + rnd() * 260;
    const rg = ctx.createRadialGradient(x, y, 0, x, y, r);
    const tint = rnd() > 0.5 ? '80,150,210' : '120,100,200';
    rg.addColorStop(0, 'rgba(' + tint + ',0.055)');
    rg.addColorStop(1, 'rgba(' + tint + ',0)');
    ctx.fillStyle = rg;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  for (let i = 0; i < 1100; i++) {
    const x = rnd() * W;
    const y = rnd() * H * 0.85;
    const a = 0.1 + rnd() * 0.45;
    ctx.fillStyle = 'rgba(200,225,250,' + a.toFixed(2) + ')';
    ctx.fillRect(x, y, 1, 1);
  }
  return c;
}

function drawGlow() {
  const S = 128;
  const c = makeCanvas(S);
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.35, 'rgba(255,255,255,0.35)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  return c;
}

export function createTextures(renderer) {
  const aniso = renderer && renderer.capabilities ? renderer.capabilities.getMaxAnisotropy() : 1;
  const rnd = mulberry32(0x50415241);

  const tex = {
    floor: toTexture(drawFloor(rnd), 1, true, aniso),
    block: toTexture(drawBlock(rnd), 1, true, aniso),
    wall: toTexture(drawWall(rnd), 1, true, aniso),
    crate: toTexture(drawCrate(rnd), 1, true, aniso),
    button: toTexture(drawButton(), 1, true, aniso),
    plate: toTexture(drawPlate(), 1, true, aniso),
    fragile: toTexture(drawFragile(rnd), 1, true, aniso),
    exit: toTexture(drawExit(), 1, true, aniso),
    tele: toTexture(drawTele(), 1, true, aniso),
    glow: toTexture(drawGlow(), 1, true, 1),
    sky: null,
  };

  const sky = new THREE.CanvasTexture(drawSky());
  sky.mapping = THREE.EquirectangularReflectionMapping;
  sky.colorSpace = THREE.SRGBColorSpace;
  sky.needsUpdate = true;
  tex.sky = sky;

  tex.dispose = function dispose() {
    for (const key of Object.keys(tex)) {
      const t = tex[key];
      if (t && t.isTexture) t.dispose();
    }
  };

  return tex;
}
