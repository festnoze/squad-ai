// All materials are procedural canvas textures. No binary assets anywhere.
import * as THREE from 'three';
import { mulberry32 } from './maze.js';

function makeCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

function toTexture(canvas, renderer, repeat = 1) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  const maxAniso = renderer?.capabilities?.getMaxAnisotropy?.() ?? 4;
  tex.anisotropy = maxAniso;
  tex.repeat.set(repeat, repeat);
  tex.needsUpdate = true;
  return tex;
}

function hex(c) {
  return `#${c.toString(16).padStart(6, '0')}`;
}

function lerpColor(a, b, t) {
  const ar = (a >> 16) & 255, ag = (a >> 8) & 255, ab = a & 255;
  const br = (b >> 16) & 255, bg = (b >> 8) & 255, bb = b & 255;
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bch = Math.round(ab + (bb - ab) * t);
  return (r << 16) | (g << 8) | bch;
}

/** Even grime: a base fill plus a handful of soft, irregular darker/lighter blotches. */
function paintStains(ctx, w, h, rng, base, dark, light, count) {
  ctx.fillStyle = hex(base);
  ctx.fillRect(0, 0, w, h);
  for (let i = 0; i < count; i++) {
    const x = rng() * w;
    const y = rng() * h;
    const r = 6 + rng() * Math.min(w, h) * 0.22;
    const useDark = rng() < 0.65;
    const c = useDark ? dark : light;
    const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
    grad.addColorStop(0, hex(c) + '55');
    grad.addColorStop(1, hex(c) + '00');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** Fine per-cell grain via a downsampled ImageData pass; cheap and always tileable. */
function paintGrain(ctx, w, h, rng, amount) {
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const n = (rng() - 0.5) * amount * 255;
    d[i] = Math.max(0, Math.min(255, d[i] + n));
    d[i + 1] = Math.max(0, Math.min(255, d[i + 1] + n));
    d[i + 2] = Math.max(0, Math.min(255, d[i + 2] + n));
  }
  ctx.putImageData(img, 0, 0);
}

function paintGrid(ctx, w, h, cell, color, lineW) {
  ctx.strokeStyle = hex(color);
  ctx.lineWidth = lineW;
  for (let x = 0; x <= w; x += cell) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  for (let y = 0; y <= h; y += cell) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }
}

// ---------------------------------------------------------------- yellow
function yellowWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(1);
  paintStains(ctx, 256, 256, rng, 0xb7a349, 0x6d5c22, 0xd8c56a, 26);
  // faint wallpaper seams
  ctx.strokeStyle = '#8f7a2e55';
  ctx.lineWidth = 1;
  for (let x = 0; x < 256; x += 64) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 256); ctx.stroke(); }
  paintGrain(ctx, 256, 256, rng, 0.05);
  return toTexture(c, renderer, 3);
}
function yellowFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(2);
  paintStains(ctx, 256, 256, rng, 0x8a6a2b, 0x4f3c18, 0xa9873c, 34);
  paintGrain(ctx, 256, 256, rng, 0.08);
  return toTexture(c, renderer, 5);
}

// -------------------------------------------------------------- warehouse
function warehouseWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(11);
  paintStains(ctx, 256, 256, rng, 0x6a6a63, 0x37362f, 0x82817a, 20);
  ctx.strokeStyle = '#00000040';
  for (let i = 0; i < 14; i++) {
    ctx.beginPath();
    ctx.moveTo(rng() * 256, rng() * 256);
    ctx.lineTo(rng() * 256, rng() * 256);
    ctx.lineWidth = 0.6 + rng();
    ctx.stroke();
  }
  paintGrain(ctx, 256, 256, rng, 0.05);
  return toTexture(c, renderer, 4);
}
function warehouseFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(12);
  paintStains(ctx, 256, 256, rng, 0x3c3b37, 0x1e1d1a, 0x54534c, 22);
  paintGrid(ctx, 256, 256, 128, 0x000000, 2);
  paintGrain(ctx, 256, 256, rng, 0.06);
  return toTexture(c, renderer, 6);
}

// ------------------------------------------------------------------ pipes
function pipesWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(21);
  ctx.fillStyle = '#585048';
  ctx.fillRect(0, 0, 256, 256);
  for (let y = 0; y < 256; y += 8) {
    ctx.fillStyle = (y / 8) % 2 === 0 ? '#5c5449' : '#4a433a';
    ctx.fillRect(0, y, 256, 8);
  }
  paintStains(ctx, 256, 256, rng, 0x000000, 0x804a2a, 0x8a6a3a, 10);
  paintGrain(ctx, 256, 256, rng, 0.07);
  return toTexture(c, renderer, 4);
}
function pipesFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(22);
  ctx.fillStyle = '#2e2b28';
  ctx.fillRect(0, 0, 256, 256);
  ctx.fillStyle = '#43403a';
  for (let y = 8; y < 256; y += 20) {
    for (let x = (y / 20) % 2 === 0 ? 0 : 10; x < 256; x += 20) {
      ctx.beginPath();
      ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  paintGrain(ctx, 256, 256, rng, 0.05);
  return toTexture(c, renderer, 6);
}

// ------------------------------------------------------------- electrical
function electricalWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(31);
  paintStains(ctx, 256, 256, rng, 0x2c333d, 0x11151a, 0x3d4855, 18);
  ctx.strokeStyle = '#000000aa';
  ctx.lineWidth = 1;
  for (let i = 0; i < 20; i++) {
    ctx.fillStyle = '#000000cc';
    ctx.fillRect(rng() * 250, rng() * 250, 3, 3);
  }
  // stray cable doodles
  for (let i = 0; i < 5; i++) {
    ctx.beginPath();
    ctx.strokeStyle = i % 2 === 0 ? '#1a1a1a' : '#5a3a1a';
    ctx.lineWidth = 2;
    ctx.moveTo(rng() * 256, rng() * 256);
    ctx.bezierCurveTo(rng() * 256, rng() * 256, rng() * 256, rng() * 256, rng() * 256, rng() * 256);
    ctx.stroke();
  }
  paintGrain(ctx, 256, 256, rng, 0.06);
  return toTexture(c, renderer, 4);
}
function electricalFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(32);
  ctx.fillStyle = '#14171c';
  ctx.fillRect(0, 0, 256, 256);
  ctx.fillStyle = '#20242b';
  for (let y = 4; y < 256; y += 16) {
    for (let x = (y / 16) % 2 === 0 ? 4 : 12; x < 256; x += 16) {
      ctx.fillRect(x, y, 6, 6);
    }
  }
  paintGrain(ctx, 256, 256, rng, 0.05);
  return toTexture(c, renderer, 6);
}

// ---------------------------------------------------------------- kitchen
function kitchenWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(41);
  ctx.fillStyle = '#d7ded9';
  ctx.fillRect(0, 0, 256, 256);
  paintGrid(ctx, 256, 256, 32, 0x9fb0a8, 2);
  paintStains(ctx, 256, 256, rng, 0xffffff, 0xb8c4bd, 0xffffff, 6);
  paintGrain(ctx, 256, 256, rng, 0.03);
  return toTexture(c, renderer, 4);
}
function kitchenFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(42);
  ctx.fillStyle = '#b9c6c1';
  ctx.fillRect(0, 0, 256, 256);
  paintGrid(ctx, 256, 256, 32, 0x7f948b, 2);
  paintGrain(ctx, 256, 256, rng, 0.04);
  return toTexture(c, renderer, 6);
}

// ------------------------------------------------------------------- dark
function darkWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(51);
  paintStains(ctx, 256, 256, rng, 0x201f1d, 0x0c0b0a, 0x2c2b28, 12);
  paintGrain(ctx, 256, 256, rng, 0.05);
  return toTexture(c, renderer, 4);
}
function darkFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(52);
  paintStains(ctx, 256, 256, rng, 0x141312, 0x080706, 0x1c1b18, 14);
  paintGrain(ctx, 256, 256, rng, 0.06);
  return toTexture(c, renderer, 6);
}

// -------------------------------------------------------------- poolrooms
function poolWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(61);
  ctx.fillStyle = '#dbe9ee';
  ctx.fillRect(0, 0, 256, 256);
  paintGrid(ctx, 256, 256, 42, 0xa9c2cb, 2);
  paintStains(ctx, 256, 256, rng, 0xffffff, 0xc3dee6, 0xffffff, 5);
  paintGrain(ctx, 256, 256, rng, 0.02);
  return toTexture(c, renderer, 3);
}
function poolFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(62);
  ctx.fillStyle = '#cfe6ec';
  ctx.fillRect(0, 0, 256, 256);
  paintGrid(ctx, 256, 256, 42, 0x8fb3bd, 2);
  paintGrain(ctx, 256, 256, rng, 0.02);
  return toTexture(c, renderer, 5);
}

// --------------------------------------------------------------- offices
function officesWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(71);
  paintStains(ctx, 256, 256, rng, 0x7d7a70, 0x4a483f, 0x928f83, 20);
  paintGrain(ctx, 256, 256, rng, 0.07);
  return toTexture(c, renderer, 4);
}
function officesFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(72);
  paintStains(ctx, 256, 256, rng, 0x6a655a, 0x403c33, 0x817b6c, 26);
  // scattered paper flecks
  for (let i = 0; i < 14; i++) {
    ctx.fillStyle = '#e9e6da';
    ctx.save();
    ctx.translate(rng() * 256, rng() * 256);
    ctx.rotate(rng() * Math.PI);
    ctx.fillRect(-4, -3, 8, 6);
    ctx.restore();
  }
  paintGrain(ctx, 256, 256, rng, 0.05);
  return toTexture(c, renderer, 6);
}

// ----------------------------------------------------------------- final
function finalWall(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(81);
  paintStains(ctx, 256, 256, rng, 0x585240, 0x2a2718, 0x726b4d, 24);
  paintGrain(ctx, 256, 256, rng, 0.06);
  return toTexture(c, renderer, 4);
}
function finalFloor(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(82);
  paintStains(ctx, 256, 256, rng, 0x403a26, 0x201c11, 0x574f33, 26);
  paintGrain(ctx, 256, 256, rng, 0.07);
  return toTexture(c, renderer, 6);
}

// ----------------------------------------------------------- shared bits
function ceilingTiles(renderer, base, line) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(base + 9000);
  ctx.fillStyle = hex(base);
  ctx.fillRect(0, 0, 256, 256);
  paintGrid(ctx, 256, 256, 64, line, 3);
  paintGrain(ctx, 256, 256, rng, 0.03);
  return toTexture(c, renderer, 4);
}

function tubeTexture(renderer, glow) {
  const c = makeCanvas(128, 32);
  const ctx = c.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, 0, 32);
  grad.addColorStop(0, '#00000000');
  grad.addColorStop(0.5, hex(glow));
  grad.addColorStop(1, '#00000000');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 32);
  ctx.fillStyle = hex(glow);
  ctx.fillRect(4, 12, 120, 8);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  return tex;
}

function doorTexture(renderer) {
  const c = makeCanvas(128, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(999);
  ctx.fillStyle = '#5a5348';
  ctx.fillRect(0, 0, 128, 256);
  ctx.strokeStyle = '#2c281f';
  ctx.lineWidth = 4;
  ctx.strokeRect(10, 10, 108, 236);
  ctx.strokeRect(20, 20, 88, 100);
  ctx.strokeRect(20, 136, 88, 100);
  ctx.fillStyle = '#8a8578';
  ctx.fillRect(14, 128, 10, 6);
  paintGrain(ctx, 128, 256, rng, 0.05);
  return toTexture(c, renderer, 1);
}

function exitTexture(renderer) {
  const c = makeCanvas(256, 128);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#062b12';
  ctx.fillRect(0, 0, 256, 128);
  ctx.strokeStyle = '#39ff8a';
  ctx.lineWidth = 6;
  ctx.strokeRect(6, 6, 244, 116);
  ctx.fillStyle = '#39ff8a';
  ctx.font = 'bold 46px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('SORTIE', 128, 64); // no accent needed, safe in 3D text
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  return tex;
}

function waterTexture(renderer) {
  const c = makeCanvas(256, 256);
  const ctx = c.getContext('2d');
  const rng = mulberry32(555);
  ctx.fillStyle = '#bfe4ec';
  ctx.fillRect(0, 0, 256, 256);
  ctx.strokeStyle = '#ffffff55';
  for (let i = 0; i < 40; i++) {
    ctx.beginPath();
    ctx.lineWidth = 1 + rng();
    const y = rng() * 256;
    ctx.moveTo(0, y);
    ctx.bezierCurveTo(64, y + rng() * 12 - 6, 192, y - rng() * 12 + 6, 256, y);
    ctx.stroke();
  }
  return toTexture(c, renderer, 4);
}

export function createTextures(renderer) {
  const themes = {
    yellow: { wall: yellowWall(renderer), floor: yellowFloor(renderer), ceiling: ceilingTiles(renderer, 0xcbb96a, 0x9c8a3f) },
    warehouse: { wall: warehouseWall(renderer), floor: warehouseFloor(renderer), ceiling: ceilingTiles(renderer, 0x2c2b28, 0x161512) },
    pipes: { wall: pipesWall(renderer), floor: pipesFloor(renderer), ceiling: ceilingTiles(renderer, 0x201d1a, 0x100e0c) },
    electrical: { wall: electricalWall(renderer), floor: electricalFloor(renderer), ceiling: ceilingTiles(renderer, 0x0e1013, 0x050607) },
    kitchen: { wall: kitchenWall(renderer), floor: kitchenFloor(renderer), ceiling: ceilingTiles(renderer, 0xe9efec, 0xb9c6c1) },
    dark: { wall: darkWall(renderer), floor: darkFloor(renderer), ceiling: ceilingTiles(renderer, 0x0a0908, 0x030302) },
    poolrooms: { wall: poolWall(renderer), floor: poolFloor(renderer), ceiling: ceilingTiles(renderer, 0xf3fbfd, 0xcfe6ec) },
    offices: { wall: officesWall(renderer), floor: officesFloor(renderer), ceiling: ceilingTiles(renderer, 0x8c8a80, 0x504e47) },
    final: { wall: finalWall(renderer), floor: finalFloor(renderer), ceiling: ceilingTiles(renderer, 0x2c2818, 0x161408) },
  };

  const tube = tubeTexture(renderer, 0xfffbe6);
  const tubeRed = tubeTexture(renderer, 0xff5533);
  const tubeBlue = tubeTexture(renderer, 0x9fe0ff);
  const door = doorTexture(renderer);
  const exit = exitTexture(renderer);
  const water = waterTexture(renderer);

  return {
    themes,
    tube,
    tubeRed,
    tubeBlue,
    door,
    exit,
    water,
    dispose() {
      for (const t of Object.values(themes)) { t.wall.dispose(); t.floor.dispose(); t.ceiling.dispose(); }
      tube.dispose(); tubeRed.dispose(); tubeBlue.dispose();
      door.dispose(); exit.dispose(); water.dispose();
    },
  };
}

export { lerpColor };
