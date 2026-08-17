/**
 * AIGUILLAGE - renderer, scene, night sky and lights.
 *
 * Kept deliberately simple: no post processing pipeline, no HDR render
 * target. Built-in materials only (MeshStandardMaterial, MeshBasicMaterial,
 * PointsMaterial) so tonemapping and colour space conversion are handled by
 * three itself; nothing here needs the ShaderMaterial tonemapping/colorspace
 * chunks because nothing here is a custom ShaderMaterial.
 */

import * as THREE from 'three';

const STAR_COUNT = 900;

function buildSkyDome() {
  const geo = new THREE.SphereGeometry(900, 24, 16, 0, Math.PI * 2, 0, Math.PI * 0.62);
  const colors = new Float32Array(geo.attributes.position.count * 3);
  const top = new THREE.Color(0x0a0e1c);
  const horizon = new THREE.Color(0x2a2440);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i) / 900; // 0 at horizon-ish, up to ~1 at zenith
    const t = THREE.MathUtils.clamp(y * 1.4, 0, 1);
    const c = horizon.clone().lerp(top, t);
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  const mat = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide, fog: false });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.renderOrder = -10;
  return mesh;
}

function buildStars(textures) {
  const positions = new Float32Array(STAR_COUNT * 3);
  // Deterministic placement (no Math.random) so the sky is stable frame to frame.
  let seed = 0x9e3779b9;
  function rnd() {
    seed = (seed + 0x6d2b79f5) >>> 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  for (let i = 0; i < STAR_COUNT; i++) {
    const theta = rnd() * Math.PI * 2;
    const phi = rnd() * Math.PI * 0.55; // upper dome only
    const r = 850;
    positions[i * 3] = Math.cos(theta) * Math.sin(phi) * r;
    positions[i * 3 + 1] = Math.cos(phi) * r;
    positions[i * 3 + 2] = Math.sin(theta) * Math.sin(phi) * r;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const mat = new THREE.PointsMaterial({
    map: textures.spark,
    size: 3.2,
    sizeAttenuation: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    color: 0xdfe6ff,
  });
  const pts = new THREE.Points(geo, mat);
  pts.renderOrder = -9;
  return pts;
}

export function createSceneRig(canvas, textures) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new THREE.Scene();
  // Never pure black: a deep desaturated indigo, matched by the sky dome base.
  scene.background = new THREE.Color(0x0c1020);
  scene.fog = new THREE.FogExp2(0x141a2c, 0.0032);

  const hemi = new THREE.HemisphereLight(0x3a4a75, 0x0c0d10, 0.55);
  scene.add(hemi);

  const moon = new THREE.DirectionalLight(0x9fb4ff, 1.1);
  moon.position.set(-120, 180, 90);
  scene.add(moon);
  scene.add(moon.target);

  const fill = new THREE.DirectionalLight(0x5b6ea8, 0.28);
  fill.position.set(140, 90, -140);
  scene.add(fill);

  const sky = buildSkyDome();
  scene.add(sky);
  const stars = buildStars(textures);
  scene.add(stars);

  function resize(w, h) {
    renderer.setSize(w, h, false);
  }

  return {
    renderer,
    scene,
    moon,
    resize,
    render(camera) {
      renderer.render(scene, camera);
    },
    dispose() {
      sky.geometry.dispose();
      sky.material.dispose();
      stars.geometry.dispose();
      stars.material.dispose();
      renderer.dispose();
    },
  };
}
