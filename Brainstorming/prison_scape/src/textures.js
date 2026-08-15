import * as THREE from 'three';

/**
 * Every surface is painted into a 2D canvas at boot, so there are no image
 * downloads. Textures are cached by name and reused across the whole prison.
 */
const cache = new Map();

function canvas(size = 256) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  return c;
}

function finish(c, repeat = 1) {
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(repeat, repeat);
  tex.anisotropy = 4;
  return tex;
}

/** Deterministic-ish speckle used by most of the concrete surfaces. */
function speckle(ctx, size, count, colors, minR, maxR, alpha = 1) {
  ctx.globalAlpha = alpha;
  for (let i = 0; i < count; i++) {
    ctx.fillStyle = colors[(Math.random() * colors.length) | 0];
    const r = minR + Math.random() * (maxR - minR);
    ctx.beginPath();
    ctx.arc(Math.random() * size, Math.random() * size, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function grime(ctx, size, strength = 0.25) {
  const g = ctx.createLinearGradient(0, 0, 0, size);
  g.addColorStop(0, `rgba(0,0,0,${strength})`);
  g.addColorStop(0.45, 'rgba(0,0,0,0)');
  g.addColorStop(1, `rgba(0,0,0,${strength * 1.6})`);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
}

const builders = {
  /** Painted breeze-block: the default interior wall of the whole facility. */
  wall() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#6a6f6d';
    ctx.fillRect(0, 0, size, size);
    speckle(ctx, size, 2600, ['#757a77', '#5f6462', '#70756f', '#666b68'], 0.6, 2.2, 0.55);
    // block courses, offset every other row
    const bh = 32, bw = 64;
    ctx.strokeStyle = 'rgba(35,38,37,0.75)';
    ctx.lineWidth = 2;
    for (let row = 0; row * bh < size; row++) {
      const y = row * bh;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(size, y);
      ctx.stroke();
      const off = row % 2 ? bw / 2 : 0;
      for (let x = off; x < size + bw; x += bw) {
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x, y + bh);
        ctx.stroke();
      }
    }
    // damp stains
    ctx.globalAlpha = 0.16;
    for (let i = 0; i < 8; i++) {
      ctx.fillStyle = '#3d4442';
      ctx.beginPath();
      ctx.ellipse(Math.random() * size, Math.random() * size, 12 + Math.random() * 34, 20 + Math.random() * 50, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    grime(ctx, size, 0.22);
    return finish(c, 1);
  },

  /** Same block, painted the pale institutional green of the cell wing. */
  wallCell() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#7c8578';
    ctx.fillRect(0, 0, size, size);
    speckle(ctx, size, 2200, ['#89927f', '#6f776b', '#818a76'], 0.6, 2.0, 0.5);
    ctx.strokeStyle = 'rgba(48,53,46,0.6)';
    ctx.lineWidth = 2;
    for (let row = 0; row * 32 < size; row++) {
      const y = row * 32;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(size, y); ctx.stroke();
      const off = row % 2 ? 32 : 0;
      for (let x = off; x < size + 64; x += 64) {
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + 32); ctx.stroke();
      }
    }
    // scratched tally marks - somebody counted the days here
    ctx.strokeStyle = 'rgba(230,230,220,0.30)';
    ctx.lineWidth = 1.6;
    for (let g = 0; g < 3; g++) {
      const bx = 40 + Math.random() * 150;
      const by = 60 + Math.random() * 140;
      for (let i = 0; i < 4; i++) {
        ctx.beginPath(); ctx.moveTo(bx + i * 6, by); ctx.lineTo(bx + i * 6 + 2, by + 18); ctx.stroke();
      }
      ctx.beginPath(); ctx.moveTo(bx - 3, by + 16); ctx.lineTo(bx + 24, by + 2); ctx.stroke();
    }
    grime(ctx, size, 0.26);
    return finish(c, 1);
  },

  /** Poured concrete floor, wet-looking and worn along the middle. */
  floor() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#4a4d4e';
    ctx.fillRect(0, 0, size, size);
    speckle(ctx, size, 4200, ['#54585a', '#414445', '#5b5f60', '#3b3e3f'], 0.5, 2.6, 0.6);
    // expansion joints
    ctx.strokeStyle = 'rgba(24,26,27,0.8)';
    ctx.lineWidth = 3;
    ctx.strokeRect(0, 0, size, size);
    ctx.beginPath(); ctx.moveTo(size / 2, 0); ctx.lineTo(size / 2, size); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, size / 2); ctx.lineTo(size, size / 2); ctx.stroke();
    // cracks
    ctx.strokeStyle = 'rgba(20,22,23,0.55)';
    ctx.lineWidth = 1.4;
    for (let i = 0; i < 5; i++) {
      let x = Math.random() * size, y = Math.random() * size;
      ctx.beginPath();
      ctx.moveTo(x, y);
      for (let s = 0; s < 7; s++) {
        x += (Math.random() - 0.5) * 40;
        y += (Math.random() - 0.5) * 40;
        ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    return finish(c, 1);
  },

  /** Glossy checkerboard tiles: canteen, showers, infirmary. */
  tile() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    const cell = 32;
    for (let y = 0; y < size / cell; y++) {
      for (let x = 0; x < size / cell; x++) {
        ctx.fillStyle = (x + y) % 2 ? '#8d9092' : '#6c7072';
        ctx.fillRect(x * cell, y * cell, cell, cell);
      }
    }
    speckle(ctx, size, 1800, ['#9aa0a2', '#5f6365'], 0.4, 1.4, 0.3);
    ctx.strokeStyle = 'rgba(40,44,46,0.6)';
    ctx.lineWidth = 2;
    for (let i = 0; i <= size / cell; i++) {
      ctx.beginPath(); ctx.moveTo(i * cell, 0); ctx.lineTo(i * cell, size); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, i * cell); ctx.lineTo(size, i * cell); ctx.stroke();
    }
    grime(ctx, size, 0.18);
    return finish(c, 1);
  },

  /** Brushed steel for doors, lockers and the armoury. */
  metal() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#585d61';
    ctx.fillRect(0, 0, size, size);
    ctx.globalAlpha = 0.25;
    for (let y = 0; y < size; y += 2) {
      ctx.fillStyle = Math.random() > 0.5 ? '#6b7176' : '#4a4f53';
      ctx.fillRect(0, y, size, 1);
    }
    ctx.globalAlpha = 1;
    // rivets around the border
    ctx.fillStyle = '#767c80';
    for (let i = 12; i < size; i += 40) {
      for (const [x, y] of [[i, 10], [i, size - 10], [10, i], [size - 10, i]]) {
        ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
      }
    }
    // rust bleed
    ctx.globalAlpha = 0.2;
    for (let i = 0; i < 5; i++) {
      ctx.fillStyle = '#7a4a24';
      ctx.beginPath();
      ctx.ellipse(Math.random() * size, Math.random() * size, 6 + Math.random() * 14, 14 + Math.random() * 30, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    return finish(c, 1);
  },

  /** Locked security door: steel with hazard chevrons and a red band. */
  doorLocked() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#4d5256';
    ctx.fillRect(0, 0, size, size);
    ctx.globalAlpha = 0.2;
    for (let y = 0; y < size; y += 3) {
      ctx.fillStyle = Math.random() > 0.5 ? '#5f6569' : '#41464a';
      ctx.fillRect(0, y, size, 1);
    }
    ctx.globalAlpha = 1;
    // hazard chevrons top and bottom
    for (const y0 of [8, size - 40]) {
      ctx.save();
      ctx.beginPath(); ctx.rect(0, y0, size, 32); ctx.clip();
      for (let x = -64; x < size + 64; x += 32) {
        ctx.fillStyle = ((x / 32) | 0) % 2 ? '#d8b32a' : '#242628';
        ctx.beginPath();
        ctx.moveTo(x, y0); ctx.lineTo(x + 16, y0);
        ctx.lineTo(x + 48, y0 + 32); ctx.lineTo(x + 32, y0 + 32);
        ctx.closePath(); ctx.fill();
      }
      ctx.restore();
    }
    ctx.fillStyle = '#8e2020';
    ctx.fillRect(0, 112, size, 32);
    ctx.fillStyle = '#f0d8d8';
    ctx.font = 'bold 26px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('VERROUILLE', size / 2, 136);
    return finish(c, 1);
  },

  /** Ceiling: dirty acoustic panels with a grid of struts. */
  ceiling() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#3b3e40';
    ctx.fillRect(0, 0, size, size);
    speckle(ctx, size, 1600, ['#444749', '#333638'], 0.6, 2.0, 0.6);
    ctx.strokeStyle = 'rgba(90,95,98,0.5)';
    ctx.lineWidth = 4;
    for (let i = 0; i <= 4; i++) {
      ctx.beginPath(); ctx.moveTo(i * 64, 0); ctx.lineTo(i * 64, size); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, i * 64); ctx.lineTo(size, i * 64); ctx.stroke();
    }
    return finish(c, 1);
  },

  /** Cracked asphalt for the exercise yard. */
  yard() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#333638';
    ctx.fillRect(0, 0, size, size);
    speckle(ctx, size, 5000, ['#3c3f41', '#2b2e30', '#45484a'], 0.5, 2.4, 0.7);
    ctx.strokeStyle = 'rgba(18,20,21,0.6)';
    for (let i = 0; i < 12; i++) {
      let x = Math.random() * size, y = Math.random() * size;
      ctx.lineWidth = 0.8 + Math.random() * 1.6;
      ctx.beginPath();
      ctx.moveTo(x, y);
      for (let s = 0; s < 6; s++) {
        x += (Math.random() - 0.5) * 60;
        y += (Math.random() - 0.5) * 60;
        ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    // faded court line
    ctx.strokeStyle = 'rgba(200,190,170,0.18)';
    ctx.lineWidth = 5;
    ctx.strokeRect(20, 20, size - 40, size - 40);
    return finish(c, 1);
  },

  /** Chain-link fence, drawn with transparency so it reads as mesh. */
  fence() {
    const size = 128;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, size, size);
    ctx.strokeStyle = 'rgba(168,176,180,0.95)';
    ctx.lineWidth = 3;
    const step = 16;
    for (let i = -size; i < size * 2; i += step) {
      ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + size, size); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(i + size, 0); ctx.lineTo(i, size); ctx.stroke();
    }
    return finish(c, 1);
  },

  /** Clinical white wall tiles: sanitary block, infirmary, kitchen. */
  tileWhite() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#cfd6d4';
    ctx.fillRect(0, 0, size, size);
    const w = 64, h = 32;
    for (let row = 0; row * h < size; row++) {
      for (let x = 0; x < size; x += w) {
        const off = row % 2 ? w / 2 : 0;
        ctx.fillStyle = ['#d9e0dd', '#cdd5d2', '#d3dad7'][(row + x / w) % 3];
        ctx.fillRect(x + off - w, row * h + 1, w - 2, h - 2);
      }
    }
    speckle(ctx, size, 900, ['#c3cbc8', '#dee5e2'], 0.4, 1.4, 0.35);
    // limescale runs and mould in the grout
    ctx.globalAlpha = 0.22;
    for (let i = 0; i < 14; i++) {
      ctx.fillStyle = Math.random() > 0.5 ? '#8a9a80' : '#a89a74';
      ctx.fillRect(Math.random() * size, Math.random() * size, 1.5 + Math.random() * 3, 8 + Math.random() * 40);
    }
    ctx.globalAlpha = 1;
    grime(ctx, size, 0.2);
    return finish(c, 1);
  },

  /** The backrooms: mono-yellow damp wallpaper. */
  wallpaperYellow() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#c8b558';
    ctx.fillRect(0, 0, size, size);
    // faint vertical stripe, the way old wallpaper prints
    for (let x = 0; x < size; x += 16) {
      ctx.fillStyle = (x / 16) % 2 ? 'rgba(210,192,100,0.5)' : 'rgba(185,167,78,0.5)';
      ctx.fillRect(x, 0, 16, size);
    }
    speckle(ctx, size, 2600, ['#d4c169', '#b9a74e', '#c2b055'], 0.6, 2.2, 0.4);
    // damp patches bleeding from the top
    ctx.globalAlpha = 0.18;
    for (let i = 0; i < 10; i++) {
      ctx.fillStyle = '#8a7736';
      ctx.beginPath();
      ctx.ellipse(Math.random() * size, Math.random() * size, 10 + Math.random() * 40, 16 + Math.random() * 55, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    // seams between wallpaper drops
    ctx.strokeStyle = 'rgba(140,124,58,0.45)';
    ctx.lineWidth = 1.5;
    for (let x = 0; x <= size; x += 64) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, size); ctx.stroke();
    }
    grime(ctx, size, 0.16);
    return finish(c, 1);
  },

  /** The backrooms: damp mustard carpet. */
  carpetYellow() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#a8933f';
    ctx.fillRect(0, 0, size, size);
    // dense fibre noise
    for (let i = 0; i < 14000; i++) {
      const v = Math.random();
      ctx.fillStyle = v > 0.66 ? '#b8a34c' : v > 0.33 ? '#96822f' : '#a89237';
      ctx.fillRect(Math.random() * size, Math.random() * size, 1.6, 1.6);
    }
    // wet patches
    ctx.globalAlpha = 0.2;
    for (let i = 0; i < 9; i++) {
      ctx.fillStyle = '#6f5f22';
      ctx.beginPath();
      ctx.ellipse(Math.random() * size, Math.random() * size, 14 + Math.random() * 40, 12 + Math.random() * 36, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    return finish(c, 1);
  },

  /** Drop-ceiling panels with the fluorescent grid, for the backrooms. */
  ceilingPanel() {
    const size = 256;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#d8d2b4';
    ctx.fillRect(0, 0, size, size);
    speckle(ctx, size, 3000, ['#e2dcbe', '#cec8aa'], 0.5, 1.8, 0.5);
    ctx.strokeStyle = 'rgba(120,114,92,0.6)';
    ctx.lineWidth = 3;
    for (let i = 0; i <= 2; i++) {
      ctx.beginPath(); ctx.moveTo(i * 128, 0); ctx.lineTo(i * 128, size); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, i * 128); ctx.lineTo(size, i * 128); ctx.stroke();
    }
    ctx.globalAlpha = 0.15;
    for (let i = 0; i < 6; i++) {
      ctx.fillStyle = '#9a8f5e';
      ctx.beginPath();
      ctx.ellipse(Math.random() * size, Math.random() * size, 10 + Math.random() * 26, 10 + Math.random() * 26, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    return finish(c, 1);
  },

  /** Vertical cell bars, transparent between the bars. */
  bars() {
    const size = 128;
    const c = canvas(size);
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, size, size);
    for (let x = 8; x < size; x += 22) {
      const g = ctx.createLinearGradient(x, 0, x + 9, 0);
      g.addColorStop(0, '#3c4145');
      g.addColorStop(0.4, '#8b9297');
      g.addColorStop(1, '#42474b');
      ctx.fillStyle = g;
      ctx.fillRect(x, 0, 9, size);
    }
    // horizontal rails
    ctx.fillStyle = '#575e63';
    ctx.fillRect(0, 12, size, 8);
    ctx.fillRect(0, size - 22, size, 8);
    return finish(c, 1);
  },
};

/** Texture by name, built on first use. `repeat` scales the UV tiling. */
export function getTexture(name, repeat = 1) {
  const key = `${name}@${repeat}`;
  if (cache.has(key)) return cache.get(key);
  const build = builders[name];
  if (!build) throw new Error(`unknown texture: ${name}`);
  const base = build();
  const tex = repeat === 1 ? base : base.clone();
  if (repeat !== 1) {
    tex.needsUpdate = true;
    tex.repeat.set(repeat, repeat);
  }
  cache.set(key, tex);
  return tex;
}

/** Non-square tiling, for long walls and floors. */
export function getTextureXY(name, rx, ry) {
  const key = `${name}@${rx}x${ry}`;
  if (cache.has(key)) return cache.get(key);
  const tex = builders[name]().clone();
  tex.needsUpdate = true;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(rx, ry);
  cache.set(key, tex);
  return tex;
}

export function disposeTextures() {
  for (const tex of cache.values()) tex.dispose();
  cache.clear();
}
