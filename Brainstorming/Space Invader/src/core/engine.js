// Moteur de rendu : renderer, scene, camera, post-traitement, boucle de frame.
//
// Rendu relatif camera : la camera reste au voisinage de l'origine et tout le
// monde est place a `absolutePosition - viewOrigin`. Cela supprime d'un coup
// tous les problemes de precision float32 a plusieurs millions d'unites.

import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { getQuality } from './settings.js';
import { SCALE } from './settings.js';

export function createEngine({ canvas }) {
  const quality = getQuality();

  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: !quality.bloom, // avec bloom, le SMAA du composer prend le relais
    powerPreference: 'high-performance',
    logarithmicDepthBuffer: true,
    stencil: false,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, quality.pixelRatio));
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.autoClear = true;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(
    72,
    window.innerWidth / window.innerHeight,
    SCALE.CAM_NEAR,
    SCALE.CAM_FAR,
  );
  scene.add(camera);

  let composer = null;
  let bloomPass = null;
  if (quality.bloom > 0) {
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    bloomPass = new UnrealBloomPass(
      new THREE.Vector2(window.innerWidth, window.innerHeight),
      quality.bloom,
      0.7,
      0.82,
    );
    composer.addPass(bloomPass);
    composer.addPass(new OutputPass());
    composer.setPixelRatio(renderer.getPixelRatio());
    composer.setSize(window.innerWidth, window.innerHeight);
  }

  // Horloge maison : THREE.Clock est deprecie en 0.185 et THREE.Timer n'apporte
  // rien ici. performance.now() suffit et ne coute aucune dependance.
  const clock = {
    _last: 0,
    _elapsed: 0,
    getDelta() {
      const now = performance.now();
      if (this._last === 0) this._last = now;
      const dt = (now - this._last) / 1000;
      this._last = now;
      this._elapsed += dt;
      return dt;
    },
    getElapsedTime() {
      return this._elapsed;
    },
  };
  const viewOrigin = new THREE.Vector3();
  const callbacks = new Set();
  let running = false;
  let rafId = 0;
  let elapsed = 0;

  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
    if (composer) composer.setSize(w, h);
  }
  window.addEventListener('resize', resize);

  function loop() {
    if (!running) return;
    rafId = requestAnimationFrame(loop);
    // Un dt borne evite les explosions numeriques apres un onglet en arriere-plan.
    const dt = Math.min(clock.getDelta(), 1 / 20);
    elapsed += dt;
    for (const cb of callbacks) cb(dt, elapsed);
    if (composer) composer.render(dt);
    else renderer.render(scene, camera);
  }

  const api = {
    renderer,
    scene,
    camera,
    composer,
    clock,
    viewOrigin,

    /** Convertit une position absolue en position d'espace vue. */
    toView(abs, out) {
      return out.copy(abs).sub(viewOrigin);
    },

    onFrame(cb) {
      callbacks.add(cb);
      return () => callbacks.delete(cb);
    },

    start() {
      if (running) return;
      running = true;
      clock.getDelta();
      rafId = requestAnimationFrame(loop);
    },

    stop() {
      running = false;
      cancelAnimationFrame(rafId);
    },

    setBloom(strength) {
      if (bloomPass) bloomPass.strength = strength;
    },

    setExposure(e) {
      renderer.toneMappingExposure = e;
    },

    resize,

    dispose() {
      api.stop();
      window.removeEventListener('resize', resize);
      callbacks.clear();
      if (composer) composer.dispose();
      renderer.dispose();
    },
  };

  return api;
}
