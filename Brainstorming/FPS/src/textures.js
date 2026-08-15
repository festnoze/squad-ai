import * as THREE from 'three';

/** Deterministic PRNG so the city looks the same every run. */
export function makeRNG(seed) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function newCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

function noiseOverlay(ctx, w, h, amount, alpha) {
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const n = (Math.random() - 0.5) * amount;
    d[i] = Math.min(255, Math.max(0, d[i] + n));
    d[i + 1] = Math.min(255, Math.max(0, d[i + 1] + n));
    d[i + 2] = Math.min(255, Math.max(0, d[i + 2] + n));
    d[i + 3] = Math.min(255, d[i + 3] * (alpha ?? 1));
  }
  ctx.putImageData(img, 0, 0);
}

function splotches(ctx, w, h, count, colors, rng, minR, maxR) {
  for (let i = 0; i < count; i++) {
    const x = rng() * w;
    const y = rng() * h;
    const r = minR + rng() * (maxR - minR);
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    const col = colors[(rng() * colors.length) | 0];
    g.addColorStop(0, col.replace('ALPHA', 0.5));
    g.addColorStop(1, col.replace('ALPHA', 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
}

function finish(canvas, repeatX, repeatY, srgb = true) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(repeatX, repeatY);
  tex.anisotropy = 8;
  if (srgb) tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Cracked, oil-stained asphalt for the streets. */
export function asphaltTexture(rng) {
  const S = 512;
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#413d38';
  ctx.fillRect(0, 0, S, S);
  splotches(ctx, S, S, 40, ['rgba(34,32,30,ALPHA)', 'rgba(96,90,80,ALPHA)', 'rgba(74,64,52,ALPHA)'], rng, 20, 90);

  // cracks
  ctx.strokeStyle = 'rgba(12,11,10,0.85)';
  for (let i = 0; i < 26; i++) {
    ctx.lineWidth = 0.6 + rng() * 1.8;
    let x = rng() * S;
    let y = rng() * S;
    let a = rng() * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(x, y);
    const segs = 4 + ((rng() * 8) | 0);
    for (let j = 0; j < segs; j++) {
      a += (rng() - 0.5) * 1.4;
      x += Math.cos(a) * (8 + rng() * 26);
      y += Math.sin(a) * (8 + rng() * 26);
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  // scattered gravel
  for (let i = 0; i < 900; i++) {
    ctx.fillStyle = `rgba(${90 + rng() * 60 | 0},${85 + rng() * 50 | 0},${75 + rng() * 40 | 0},${0.15 + rng() * 0.35})`;
    ctx.fillRect(rng() * S, rng() * S, 1 + rng() * 2, 1 + rng() * 2);
  }
  noiseOverlay(ctx, S, S, 26);
  // Repeat is 1 here: world geometry scales UVs itself so texel density stays
  // constant no matter how big the surface is.
  return finish(c, 1, 1);
}

/** Scorched concrete for building bodies and rubble. */
export function concreteTexture(rng, tint = '#6a6258') {
  const S = 512;
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = tint;
  ctx.fillRect(0, 0, S, S);
  splotches(ctx, S, S, 60, ['rgba(30,26,22,ALPHA)', 'rgba(120,110,96,ALPHA)', 'rgba(70,52,32,ALPHA)'], rng, 15, 120);
  // soot streaks running down
  for (let i = 0; i < 30; i++) {
    const x = rng() * S;
    const w = 4 + rng() * 26;
    const g = ctx.createLinearGradient(0, 0, 0, S);
    g.addColorStop(0, 'rgba(16,14,12,0.55)');
    g.addColorStop(0.6, 'rgba(16,14,12,0.15)');
    g.addColorStop(1, 'rgba(16,14,12,0)');
    ctx.fillStyle = g;
    ctx.fillRect(x, rng() * S * 0.4, w, S);
  }
  noiseOverlay(ctx, S, S, 30);
  return finish(c, 1, 1);
}

/**
 * Building facade, tileable in both axes: a grid of gutted windows separated
 * by floor slabs and pillars, over weathered concrete.
 * One tile is `cols` windows wide by `rows` floors tall.
 */
export function facadeTexture(rng, opts = {}) {
  const S = 512;
  const cols = opts.cols ?? 4;
  const rows = opts.rows ?? 4;
  const base = opts.base ?? '#5d564c';
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');

  ctx.fillStyle = base;
  ctx.fillRect(0, 0, S, S);
  splotches(ctx, S, S, 50, ['rgba(28,24,20,ALPHA)', 'rgba(120,110,96,ALPHA)', 'rgba(74,54,32,ALPHA)'], rng, 18, 120);

  const cw = S / cols;
  const ch = S / rows;

  // vertical pillars between window bays
  for (let k = 0; k < cols; k++) {
    const x = k * cw;
    const g = ctx.createLinearGradient(x, 0, x + cw * 0.2, 0);
    g.addColorStop(0, 'rgba(255,255,255,0.055)');
    g.addColorStop(1, 'rgba(0,0,0,0.10)');
    ctx.fillStyle = g;
    ctx.fillRect(x, 0, cw * 0.2, S);
  }

  for (let r = 0; r < rows; r++) {
    for (let k = 0; k < cols; k++) {
      const x = k * cw + cw * 0.24;
      const y = r * ch + ch * 0.22;
      const w = cw * 0.52;
      const h = ch * 0.46;
      const roll = rng();

      // recessed reveal around the opening
      ctx.fillStyle = 'rgba(0,0,0,0.30)';
      ctx.fillRect(x - 3, y - 3, w + 6, h + 6);

      if (roll < 0.14) {
        // boarded up with scavenged planks
        ctx.fillStyle = '#4a4137';
        ctx.fillRect(x, y, w, h);
        ctx.strokeStyle = 'rgba(58,44,30,0.9)';
        ctx.lineWidth = Math.max(2, h * 0.13);
        for (let p = 0; p < 3; p++) {
          const py = y + h * (0.22 + p * 0.28);
          ctx.beginPath();
          ctx.moveTo(x, py + (rng() - 0.5) * 4);
          ctx.lineTo(x + w, py + (rng() - 0.5) * 4);
          ctx.stroke();
        }
      } else {
        // gutted interior, darker toward the top of the opening
        const g = ctx.createLinearGradient(x, y, x, y + h);
        g.addColorStop(0, '#080706');
        g.addColorStop(0.7, '#0f0d0c');
        g.addColorStop(1, '#1a1613');
        ctx.fillStyle = g;
        ctx.fillRect(x, y, w, h);

        if (roll > 0.55) {
          // shards still hanging in the frame
          ctx.fillStyle = 'rgba(158,172,166,0.22)';
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x + w, y);
          ctx.lineTo(x + w * (0.25 + rng() * 0.5), y + h * (0.25 + rng() * 0.45));
          ctx.closePath();
          ctx.fill();
          ctx.beginPath();
          ctx.moveTo(x, y + h);
          ctx.lineTo(x + w * (0.2 + rng() * 0.3), y + h);
          ctx.lineTo(x, y + h * (0.55 + rng() * 0.3));
          ctx.closePath();
          ctx.fill();
        }
        if (roll > 0.90) {
          // a rare lamp still burning deep inside
          const lg = ctx.createRadialGradient(x + w / 2, y + h / 2, 0, x + w / 2, y + h / 2, w * 0.7);
          lg.addColorStop(0, 'rgba(255,176,84,0.42)');
          lg.addColorStop(1, 'rgba(255,150,60,0)');
          ctx.fillStyle = lg;
          ctx.fillRect(x, y, w, h);
        }
        if (roll > 0.72 && roll < 0.80) {
          // torn curtain / rag hanging out
          ctx.fillStyle = 'rgba(90,78,64,0.55)';
          ctx.fillRect(x + w * 0.55, y, w * 0.3, h * (0.5 + rng() * 0.5));
        }
      }

      // sill, and soot licking up the wall above the opening
      ctx.fillStyle = 'rgba(24,21,18,0.55)';
      ctx.fillRect(x - 4, y + h, w + 8, 4);
      ctx.fillStyle = 'rgba(210,200,182,0.10)';
      ctx.fillRect(x - 4, y + h, w + 8, 1.5);
      const sg = ctx.createLinearGradient(0, y, 0, y - ch * 0.5);
      sg.addColorStop(0, `rgba(12,10,9,${0.32 + rng() * 0.3})`);
      sg.addColorStop(1, 'rgba(12,10,9,0)');
      ctx.fillStyle = sg;
      ctx.fillRect(x - 2, y - ch * 0.5, w + 4, ch * 0.5);
    }

    // floor slab band across the whole tile
    const by = (r + 1) * ch - ch * 0.09;
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.fillRect(0, by, S, ch * 0.09);
    ctx.fillStyle = 'rgba(220,210,190,0.09)';
    ctx.fillRect(0, by, S, 2);
  }

  // long grime runs down the whole facade
  for (let i = 0; i < 22; i++) {
    const x = rng() * S;
    const w = 3 + rng() * 20;
    const g = ctx.createLinearGradient(0, 0, 0, S);
    g.addColorStop(0, 'rgba(18,15,12,0.30)');
    g.addColorStop(1, 'rgba(18,15,12,0.05)');
    ctx.fillStyle = g;
    ctx.fillRect(x, 0, w, S);
  }
  noiseOverlay(ctx, S, S, 24);
  return finish(c, opts.repeatX ?? 1, opts.repeatY ?? 1);
}

/** Tar-and-gravel rooftop with patches and puddle stains. */
export function roofTexture(rng) {
  const S = 256;
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#565049';
  ctx.fillRect(0, 0, S, S);
  splotches(ctx, S, S, 50, ['rgba(34,31,28,ALPHA)', 'rgba(108,100,90,ALPHA)', 'rgba(74,66,56,ALPHA)'], rng, 10, 70);
  // tar seams
  ctx.strokeStyle = 'rgba(16,14,12,0.7)';
  ctx.lineWidth = 3;
  for (let i = 0; i < 6; i++) {
    const y = (i / 6) * S + rng() * 8;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(S, y + (rng() - 0.5) * 6);
    ctx.stroke();
  }
  // gravel
  for (let i = 0; i < 1400; i++) {
    ctx.fillStyle = `rgba(${100 + rng() * 70 | 0},${94 + rng() * 60 | 0},${82 + rng() * 50 | 0},${0.1 + rng() * 0.4})`;
    ctx.fillRect(rng() * S, rng() * S, 1 + rng() * 2, 1 + rng() * 2);
  }
  noiseOverlay(ctx, S, S, 30);
  return finish(c, 1, 1);
}

/** Mottled, blotchy hide for the ghouls and brutes. */
export function skinTexture(rng, base = '#8d9b7a') {
  const S = 128;
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, S, S);
  splotches(ctx, S, S, 60, [
    'rgba(60,70,50,ALPHA)', 'rgba(150,150,120,ALPHA)',
    'rgba(90,60,55,ALPHA)', 'rgba(40,44,36,ALPHA)',
  ], rng, 4, 30);
  // veins and scarring
  ctx.strokeStyle = 'rgba(70,40,44,0.5)';
  for (let i = 0; i < 22; i++) {
    ctx.lineWidth = 0.6 + rng() * 1.4;
    let x = rng() * S, y = rng() * S, a = rng() * 6.28;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let j = 0; j < 4; j++) {
      a += (rng() - 0.5) * 1.6;
      x += Math.cos(a) * 8;
      y += Math.sin(a) * 8;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  noiseOverlay(ctx, S, S, 34);
  return finish(c, 1, 1);
}

/** Coarse woven cloth with patches and dirt, for rags and coats. */
export function clothTexture(rng, base = '#33302a') {
  const S = 128;
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, S, S);
  // weave
  ctx.strokeStyle = 'rgba(255,255,255,0.045)';
  ctx.lineWidth = 1;
  for (let i = 0; i < S; i += 3) {
    ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, S); ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(0,0,0,0.09)';
  for (let i = 0; i < S; i += 3) {
    ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(S, i); ctx.stroke();
  }
  splotches(ctx, S, S, 34, ['rgba(20,17,14,ALPHA)', 'rgba(84,74,58,ALPHA)', 'rgba(52,34,24,ALPHA)'], rng, 5, 34);
  // stitched patches
  for (let i = 0; i < 5; i++) {
    const x = rng() * S, y = rng() * S, w = 12 + rng() * 22, h = 10 + rng() * 18;
    ctx.fillStyle = `rgba(${40 + rng() * 50 | 0},${36 + rng() * 40 | 0},${28 + rng() * 30 | 0},0.6)`;
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = 'rgba(0,0,0,0.35)';
    ctx.setLineDash([2, 3]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
  }
  noiseOverlay(ctx, S, S, 26);
  return finish(c, 1, 1);
}

/** Faded dashed road marking on transparent background. */
export function roadLineTexture(rng) {
  const w = 32, h = 256;
  const c = newCanvas(w, h);
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = 'rgba(198,170,74,0.55)';
  // two dashes per tile, worn away in places
  for (const [y0, y1] of [[16, 104], [144, 232]]) {
    for (let y = y0; y < y1; y += 2) {
      if (rng() < 0.22) continue;
      ctx.globalAlpha = 0.25 + rng() * 0.5;
      ctx.fillRect(8 + (rng() - 0.5) * 2, y, 16, 2);
    }
  }
  ctx.globalAlpha = 1;
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

/** Rusted / burnt metal for cars, barrels, containers. */
export function rustTexture(rng, base = '#6b3a20') {
  const S = 256;
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, S, S);
  splotches(ctx, S, S, 70, ['rgba(120,58,24,ALPHA)', 'rgba(40,30,26,ALPHA)', 'rgba(160,96,40,ALPHA)', 'rgba(24,20,18,ALPHA)'], rng, 6, 48);
  noiseOverlay(ctx, S, S, 40);
  return finish(c, 2, 2);
}

/** Soft round blob used for ash motes, smoke puffs and muzzle flare. */
export function softDot(colorInner = 'rgba(255,255,255,1)', colorOuter = 'rgba(255,255,255,0)') {
  const S = 64;
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  g.addColorStop(0, colorInner);
  g.addColorStop(1, colorOuter);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Bullet hole decal (dark crater with a bright chipped rim). */
export function bulletHoleTexture() {
  const S = 64;
  const c = newCanvas(S, S);
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, S, S);
  const g = ctx.createRadialGradient(S / 2, S / 2, 1, S / 2, S / 2, S / 2);
  g.addColorStop(0, 'rgba(4,4,4,1)');
  g.addColorStop(0.35, 'rgba(10,10,10,0.95)');
  g.addColorStop(0.5, 'rgba(90,84,74,0.55)');
  g.addColorStop(1, 'rgba(120,112,100,0)');
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(S / 2, S / 2, S / 2, 0, Math.PI * 2);
  ctx.fill();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Every texture the game needs, built once at boot. */
export function buildTextureSet(seed = 1337) {
  const rng = makeRNG(seed);
  return {
    asphalt: asphaltTexture(rng),
    concrete: concreteTexture(rng, '#948b7d'),
    concreteDark: concreteTexture(rng, '#736c62'),
    rubble: concreteTexture(rng, '#867c68'),
    facadeA: facadeTexture(rng, { base: '#8b8274', cols: 4, rows: 4 }),
    facadeB: facadeTexture(rng, { base: '#9a8770', cols: 4, rows: 4 }),
    facadeC: facadeTexture(rng, { base: '#78746f', cols: 4, rows: 4 }),
    facadeD: facadeTexture(rng, { base: '#a38d6d', cols: 4, rows: 4 }),
    roof: roofTexture(rng),
    roadLine: roadLineTexture(rng),
    skinGhoul: skinTexture(rng, '#a9bd8c'),
    skinBrute: skinTexture(rng, '#b07d68'),
    skinRaider: skinTexture(rng, '#a8825f'),
    clothDark: clothTexture(rng, '#6b6455'),
    clothBrown: clothTexture(rng, '#8a6c46'),
    clothBlack: clothTexture(rng, '#514a40'),
    rust: rustTexture(rng, '#8a5330'),
    rustDark: rustTexture(rng, '#5b4738'),
    ash: softDot('rgba(214,206,190,0.9)', 'rgba(214,206,190,0)'),
    smoke: softDot('rgba(120,112,100,0.75)', 'rgba(120,112,100,0)'),
    flash: softDot('rgba(255,236,178,1)', 'rgba(255,140,30,0)'),
    blood: softDot('rgba(190,26,26,0.95)', 'rgba(90,10,10,0)'),
    hole: bulletHoleTexture(),
  };
}
