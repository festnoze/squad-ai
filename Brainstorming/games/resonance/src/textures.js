/**
 * RESONANCE - procedural canvas textures. No binary asset anywhere: every
 * texture is drawn once at boot into a 2D canvas. Text drawn here must stay
 * accent-free (canvas font rendering of accents is unreliable in this repo).
 */

import * as THREE from 'three';

function canvas(size) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  return c;
}

function makeRock() {
  const c = canvas(256);
  const g = c.getContext('2d');
  g.fillStyle = '#3a3350';
  g.fillRect(0, 0, 256, 256);
  // Layered speckle passes read as mineral grain from a distance.
  for (let pass = 0; pass < 3; pass++) {
    const alpha = [0.22, 0.12, 0.08][pass];
    const size = [3, 7, 14][pass];
    for (let i = 0; i < 260; i++) {
      const v = Math.random();
      g.fillStyle = v > 0.5
        ? `rgba(104, 94, 138, ${alpha})`
        : `rgba(28, 22, 44, ${alpha})`;
      g.fillRect(Math.random() * 256, Math.random() * 256, size * (0.5 + Math.random()), size * (0.5 + Math.random()));
    }
  }
  // A few pale veins.
  g.strokeStyle = 'rgba(150, 138, 196, 0.14)';
  g.lineWidth = 2;
  for (let i = 0; i < 10; i++) {
    g.beginPath();
    let x = Math.random() * 256; let y = Math.random() * 256;
    g.moveTo(x, y);
    for (let s = 0; s < 6; s++) { x += (Math.random() - 0.5) * 80; y += (Math.random() - 0.5) * 80; g.lineTo(x, y); }
    g.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function makeHalo() {
  const c = canvas(128);
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(64, 64, 4, 64, 64, 62);
  grad.addColorStop(0, 'rgba(255,255,255,0.9)');
  grad.addColorStop(0.35, 'rgba(255,255,255,0.28)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function makeWarn() {
  const c = canvas(128);
  const g = c.getContext('2d');
  g.clearRect(0, 0, 128, 128);
  g.strokeStyle = 'rgba(255,70,80,0.95)';
  g.lineWidth = 7;
  g.beginPath();
  g.arc(64, 64, 46, 0, Math.PI * 2);
  g.stroke();
  g.beginPath();
  g.moveTo(32, 96);
  g.lineTo(96, 32);
  g.stroke();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function makeFrame() {
  const c = canvas(128);
  const g = c.getContext('2d');
  g.clearRect(0, 0, 128, 128);
  g.strokeStyle = 'rgba(255,255,255,0.95)';
  g.lineWidth = 6;
  const k = 30;
  for (const [x0, y0, dx, dy] of [[6, 6, 1, 1], [122, 6, -1, 1], [122, 122, -1, -1], [6, 122, 1, -1]]) {
    g.beginPath();
    g.moveTo(x0 + dx * k, y0);
    g.lineTo(x0, y0);
    g.lineTo(x0, y0 + dy * k);
    g.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function makeFoam() {
  const c = canvas(128);
  const g = c.getContext('2d');
  g.fillStyle = '#141220';
  g.fillRect(0, 0, 128, 128);
  // Anechoic wedge look: rows of dark pyramids.
  for (let y = 0; y < 4; y++) {
    for (let x = 0; x < 4; x++) {
      const cx = x * 32; const cy = y * 32;
      const grad = g.createRadialGradient(cx + 16, cy + 16, 2, cx + 16, cy + 16, 20);
      grad.addColorStop(0, 'rgba(60,54,88,0.55)');
      grad.addColorStop(1, 'rgba(8,6,16,0.9)');
      g.fillStyle = grad;
      g.fillRect(cx + 2, cy + 2, 28, 28);
    }
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export function createTextures() {
  const rock = makeRock();
  const halo = makeHalo();
  const warn = makeWarn();
  const frame = makeFrame();
  const foam = makeFoam();
  function dispose() {
    rock.dispose(); halo.dispose(); warn.dispose(); frame.dispose(); foam.dispose();
  }
  return { rock, halo, warn, frame, foam, dispose };
}
