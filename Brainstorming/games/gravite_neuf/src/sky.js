/**
 * GRAVITE NEUF - sky dome and star field.
 *
 * The dome stays fixed in screen space while the structure rolls, so its
 * gradient is a permanent "this way is down" reference. Its hue is bound to the
 * current gravity axis: six directions, six skies, which is the cheapest and
 * most readable orientation cue available.
 */

import * as THREE from 'three';

// Bottom / top colours per gravity direction, in the DIRS order of world.js.
const SKIES = [
  ['#17544f', '#0d2338'], // +X teal
  ['#38215a', '#160f30'], // -X violet
  ['#53214a', '#1f1029'], // +Y rose
  ['#1d3a6b', '#0a1330'], // -Y deep blue (default)
  ['#55391a', '#1f172e'], // +Z amber
  ['#17492a', '#0b1c2a'], // -Z green
];

const VERT = `
varying vec3 vDir;
void main() {
  vDir = normalize(position);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FRAG = `
uniform vec3 uBottom;
uniform vec3 uTop;
varying vec3 vDir;
void main() {
  float h = smoothstep(-0.45, 0.85, vDir.y);
  vec3 col = mix(uBottom, uTop, h);
  // Soft warm band right on the horizon, keeps the lower half from going flat.
  float band = exp(-abs(vDir.y) * 9.0);
  col += uBottom * band * 0.55;
  gl_FragColor = vec4(col, 1.0);
  // The renderer tone maps and encodes every built in material. A custom
  // ShaderMaterial gets neither unless it asks, and without these two chunks the
  // dome came out darker and flatter than the cubes lit in front of it.
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

function mulberry32(seed) {
  let a = seed >>> 0;
  return function random() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createSky(scene) {
  const geom = new THREE.SphereGeometry(400, 24, 16);
  const material = new THREE.ShaderMaterial({
    uniforms: {
      uBottom: { value: new THREE.Color(SKIES[3][0]) },
      uTop: { value: new THREE.Color(SKIES[3][1]) },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
  });
  const dome = new THREE.Mesh(geom, material);
  dome.frustumCulled = false;
  dome.renderOrder = -10;
  scene.add(dome);

  // Star field: one Points, no texture, additive so it never darkens the dome.
  const rnd = mulberry32(1337);
  const count = 700;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const u = rnd() * 2 - 1;
    const a = rnd() * Math.PI * 2;
    const r = Math.sqrt(1 - u * u);
    positions[i * 3] = Math.cos(a) * r * 320;
    positions[i * 3 + 1] = u * 320;
    positions[i * 3 + 2] = Math.sin(a) * r * 320;
  }
  const starGeom = new THREE.BufferGeometry();
  starGeom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const starMat = new THREE.PointsMaterial({
    color: 0xbcd4ff,
    size: 1.6,
    sizeAttenuation: false,
    transparent: true,
    opacity: 0.75,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const stars = new THREE.Points(starGeom, starMat);
  stars.frustumCulled = false;
  stars.renderOrder = -9;
  scene.add(stars);

  const fromBottom = new THREE.Color(SKIES[3][0]);
  const fromTop = new THREE.Color(SKIES[3][1]);
  const toBottom = new THREE.Color(SKIES[3][0]);
  const toTop = new THREE.Color(SKIES[3][1]);
  let blend = 1;

  return {
    dome,
    setDirection(dirIndex, immediate) {
      const pair = SKIES[dirIndex] || SKIES[3];
      fromBottom.copy(material.uniforms.uBottom.value);
      fromTop.copy(material.uniforms.uTop.value);
      toBottom.set(pair[0]);
      toTop.set(pair[1]);
      blend = immediate ? 1 : 0;
      if (immediate) {
        material.uniforms.uBottom.value.copy(toBottom);
        material.uniforms.uTop.value.copy(toTop);
      }
    },
    update(dt, elapsed) {
      if (blend < 1) {
        blend = Math.min(1, blend + dt / 0.45);
        const e = blend * blend * (3 - 2 * blend);
        material.uniforms.uBottom.value.copy(fromBottom).lerp(toBottom, e);
        material.uniforms.uTop.value.copy(fromTop).lerp(toTop, e);
      }
      stars.rotation.y = elapsed * 0.004;
    },
    dispose() {
      scene.remove(dome);
      scene.remove(stars);
      geom.dispose();
      material.dispose();
      starGeom.dispose();
      starMat.dispose();
    },
  };
}
