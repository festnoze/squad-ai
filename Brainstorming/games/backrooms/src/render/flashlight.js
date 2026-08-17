// The player's flashlight: the single dynamic light this game ever uses
// (budget rule: at most one SpotLight, everything else is ambient or emissive
// planes). Parented to the camera so it always points where the player looks.
import * as THREE from 'three';

export function createFlashlight(camera) {
  const spot = new THREE.SpotLight(0xfff3d6, 0, 15, 0.46, 0.45, 1.6);
  spot.position.set(0, 0, 0);
  const target = new THREE.Object3D();
  target.position.set(0, 0, -1);
  camera.add(target);
  spot.target = target;
  camera.add(spot);

  let flicker = 0;

  return {
    spot,
    target,
    update(dt, on, baseIntensity = 5.2) {
      spot.visible = on;
      if (!on) return;
      flicker += dt;
      // tiny handheld wobble, never enough to look like a strobing bulb
      const wobble = 1 + Math.sin(flicker * 9) * 0.02 + Math.sin(flicker * 23.1) * 0.01;
      spot.intensity = baseIntensity * wobble;
    },
    dispose() {
      camera.remove(spot);
      camera.remove(target);
    },
  };
}
