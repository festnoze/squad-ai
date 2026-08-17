// Renderer + camera + base scene bootstrap. Shared by every level.
import * as THREE from 'three';

export function createScene(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new THREE.Scene();
  // Never pure black: keeps the anti-black-screen safety net meaningful even
  // in the "noir absolu" level.
  scene.background = new THREE.Color(0x030303);

  const camera = new THREE.PerspectiveCamera(78, window.innerWidth / window.innerHeight, 0.08, 90);

  function setSize(w, h) {
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  setSize(window.innerWidth, window.innerHeight);

  return { renderer, scene, camera, setSize };
}
