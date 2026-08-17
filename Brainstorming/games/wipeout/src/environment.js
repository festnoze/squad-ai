/**
 * Unified environment controller.
 *
 * Every level gets the same lifecycle (panorama, detail layer, weather,
 * speed-response and disposal), while its base world remains theme-specific.
 */
import * as THREE from 'three';
import { createWorld } from './world.js';
import { createThemedWorld } from './themed-world.js';

const BACKDROPS = {
  akari: new URL('../assets/backgrounds/neo-kyoto-panorama.png', import.meta.url).href,
  azur: new URL('../assets/backgrounds/azur-panorama.png', import.meta.url).href,
  prism: new URL('../assets/backgrounds/prism-panorama.png', import.meta.url).href,
};

const PROFILES = {
  city: {
    panoramaTint: 0x617a9d,
    panoramaOpacity: 0.76,
    panoramaRepeat: 1.35,
    panoramaY: 80,
    rotation: 0.18,
    wind: 0.45,
    hardware: [0x22e0ff, 0xff2bd6, 0x17223a],
  },
  coast: {
    panoramaTint: 0xb7d9da,
    panoramaOpacity: 0.86,
    panoramaRepeat: 2.15,
    panoramaY: 45,
    rotation: -0.42,
    wind: 1.15,
    hardware: [0x42eaff, 0xffc963, 0xe6e1cf],
  },
  psychedelic: {
    panoramaTint: 0x8b56a7,
    panoramaOpacity: 0.72,
    panoramaRepeat: 1.6,
    panoramaY: 115,
    rotation: 0.72,
    wind: 0.78,
    hardware: [0xff39dd, 0x78ff3e, 0x31104f],
  },
};

const _frame = {
  s: 0,
  pos: new THREE.Vector3(),
  tangent: new THREE.Vector3(),
  right: new THREE.Vector3(),
  up: new THREE.Vector3(),
  halfWidth: 10,
  curvature: 0,
  verticalCurvature: 0,
  bank: 0,
};
const _matrix = new THREE.Matrix4();
const _basis = new THREE.Matrix4();
const _quat = new THREE.Quaternion();
const _scale = new THREE.Vector3();
const _pos = new THREE.Vector3();

function loadPanorama(renderer, url) {
  return new Promise((resolve, reject) => {
    new THREE.TextureLoader().load(
      url,
      (texture) => {
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.wrapS = THREE.RepeatWrapping;
        texture.wrapT = THREE.ClampToEdgeWrapping;
        texture.minFilter = THREE.LinearMipmapLinearFilter;
        texture.magFilter = THREE.LinearFilter;
        texture.generateMipmaps = true;
        texture.anisotropy = renderer && renderer.capabilities
          ? Math.min(8, renderer.capabilities.getMaxAnisotropy())
          : 4;
        texture.needsUpdate = true;
        resolve(texture);
      },
      undefined,
      reject,
    );
  });
}

function createPanorama(texture, profile) {
  // The background plate sits beyond every authored object. Its bottom half is
  // deliberately below the circuit, letting geometry and fog own the horizon.
  texture.repeat.set(profile.panoramaRepeat || 1, 1);
  const geometry = new THREE.SphereGeometry(3950, 96, 48);
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    color: profile.panoramaTint,
    transparent: true,
    opacity: profile.panoramaOpacity,
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
    toneMapped: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = 'panorama-background';
  mesh.position.y = profile.panoramaY;
  mesh.rotation.y = profile.rotation;
  mesh.renderOrder = -20;
  mesh.frustumCulled = false;
  return { mesh, geometry, material };
}

function makeHardwareTexture(theme) {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  const coast = theme === 'coast';
  const prism = theme === 'psychedelic';
  ctx.fillStyle = coast ? '#d5d7ce' : prism ? '#190b28' : '#101521';
  ctx.fillRect(0, 0, 512, 512);

  // Panel seams, fasteners, brushing and accumulated grime. Kept deterministic
  // so level switching never changes the authored visual identity.
  ctx.strokeStyle = coast ? 'rgba(45,72,78,.32)' : 'rgba(150,190,220,.2)';
  ctx.lineWidth = 4;
  for (let y = 0; y <= 512; y += 128) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(512, y); ctx.stroke();
  }
  for (let x = 0; x <= 512; x += 128) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 512); ctx.stroke();
  }
  for (let y = 64; y < 512; y += 128) {
    for (let x = 64; x < 512; x += 128) {
      ctx.fillStyle = coast ? '#61747a' : '#667c95';
      ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'rgba(0,0,0,.45)';
      ctx.beginPath(); ctx.arc(x + 2, y + 2, 2, 0, Math.PI * 2); ctx.fill();
    }
  }
  for (let i = 0; i < 1300; i++) {
    const v = (i * 73) % 512;
    const y = (i * 191) % 512;
    ctx.fillStyle = `rgba(${coast ? '93,75,52' : '4,8,15'},${0.018 + (i % 7) * 0.004})`;
    ctx.fillRect(v, y, 1 + (i % 3), 2 + (i % 11));
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(2, 4);
  texture.anisotropy = 8;
  texture.needsUpdate = true;
  return texture;
}

function placeMatrix(track, s, lateral, height, scale, out) {
  track.at(s, _frame);
  _basis.makeBasis(_frame.right, _frame.up, _frame.tangent.clone().multiplyScalar(-1));
  _quat.setFromRotationMatrix(_basis);
  _pos.copy(_frame.pos)
    .addScaledVector(_frame.right, lateral)
    .addScaledVector(_frame.up, height);
  out.compose(_pos, _quat, scale);
  return _frame;
}

function createTracksideHardware(track, level, profile) {
  const group = new THREE.Group();
  group.name = 'environment-detail-' + level.id;
  const materials = [];
  const geometries = [];
  const texture = makeHardwareTexture(level.theme);

  const pylonGeo = new THREE.BoxGeometry(1.1, 5.2, 1.1);
  pylonGeo.translate(0, 2.6, 0);
  const capGeo = new THREE.CylinderGeometry(0.9, 1.25, 0.38, 8);
  const moduleGeo = new THREE.BoxGeometry(2.8, 1.35, 1.2);
  const pylonMat = new THREE.MeshStandardMaterial({
    color: profile.hardware[2],
    map: texture,
    roughness: level.theme === 'coast' ? 0.65 : 0.38,
    metalness: level.theme === 'coast' ? 0.3 : 0.72,
    envMapIntensity: 0.8,
  });
  const capMat = new THREE.MeshStandardMaterial({
    color: profile.hardware[0], roughness: 0.26, metalness: 0.72,
    emissive: profile.hardware[0], emissiveIntensity: 0.16,
  });
  const lightMat = new THREE.MeshBasicMaterial({
    color: profile.hardware[1], toneMapped: false, transparent: true, opacity: 0.9,
    depthWrite: false,
  });
  geometries.push(pylonGeo, capGeo, moduleGeo);
  materials.push(pylonMat, capMat, lightMat);

  const count = Math.max(20, Math.round(track.length / 118));
  const instances = count * 2;
  const pylons = new THREE.InstancedMesh(pylonGeo, pylonMat, instances);
  const caps = new THREE.InstancedMesh(capGeo, capMat, instances);
  const modules = new THREE.InstancedMesh(moduleGeo, lightMat, instances);
  const unit = new THREE.Vector3(1, 1, 1);
  let at = 0;
  for (let i = 0; i < count; i++) {
    const s = ((i + 0.37) / count) * track.length;
    for (let side = -1; side <= 1; side += 2) {
      track.at(s, _frame);
      const lateral = side * (_frame.halfWidth + 3.2);
      placeMatrix(track, s, lateral, 0, unit, _matrix);
      pylons.setMatrixAt(at, _matrix);
      placeMatrix(track, s, lateral, 5.35, new THREE.Vector3(1, 1, 1), _matrix);
      caps.setMatrixAt(at, _matrix);
      placeMatrix(track, s, lateral - side * 0.25, 3.75, new THREE.Vector3(1, 1, 1), _matrix);
      modules.setMatrixAt(at, _matrix);
      at++;
    }
  }
  pylons.castShadow = true;
  pylons.receiveShadow = true;
  group.add(pylons, caps, modules);

  // Fine reflector studs provide reliable near-field speed scale at night and
  // become warm solar markers on the coast.
  const studGeo = new THREE.BoxGeometry(0.28, 0.11, 0.62);
  const studMat = new THREE.MeshBasicMaterial({ color: profile.hardware[0], toneMapped: false });
  geometries.push(studGeo);
  materials.push(studMat);
  const studCount = Math.max(80, Math.round(track.length / 17)) * 2;
  const studs = new THREE.InstancedMesh(studGeo, studMat, studCount);
  for (let i = 0; i < studCount / 2; i++) {
    const s = (i / (studCount / 2)) * track.length;
    track.at(s, _frame);
    for (let side = -1; side <= 1; side += 2) {
      const index = i * 2 + (side > 0 ? 1 : 0);
      placeMatrix(track, s, side * (_frame.halfWidth - 1.25), 0.11, unit, _matrix);
      studs.setMatrixAt(index, _matrix);
    }
  }
  studs.frustumCulled = false;
  group.add(studs);

  const animated = {
    modules,
    studs,
    profile,
    studColor: new THREE.Color(profile.hardware[0]),
    windables: [],
  };
  return {
    group,
    animated,
    dispose() {
      for (let i = 0; i < geometries.length; i++) geometries[i].dispose();
      for (let i = 0; i < materials.length; i++) materials[i].dispose();
      texture.dispose();
      group.clear();
    },
  };
}

function updateEnvironmentDetail(detail, t, speed01) {
  if (!detail) return;
  // Lower background pulse at racing speed: the road remains the brightest and
  // most stable visual system when the player needs it most.
  const quiet = 1 - speed01 * 0.22;
  if (detail.modules && detail.modules.material) {
    detail.modules.material.opacity = quiet * (0.82 + Math.sin(t * 3.4) * 0.08);
  }
  if (detail.studs && detail.studs.material) {
    detail.studs.material.color.copy(detail.studColor).offsetHSL(Math.sin(t * 0.17) * 0.006, 0, 0);
  }
}

export async function createEnvironment(scene, track, textures, renderer, level) {
  const profile = PROFILES[level.theme] || PROFILES.city;
  const panoramaTexture = await loadPanorama(renderer, BACKDROPS[level.id] || BACKDROPS.akari);
  const base = level.theme === 'city'
    ? createWorld(scene, track, textures, renderer)
    : createThemedWorld(scene, track, level);

  const panorama = createPanorama(panoramaTexture, profile);
  const detail = createTracksideHardware(track, level, profile);
  const group = new THREE.Group();
  group.name = 'environment-controller-' + level.id;
  group.add(panorama.mesh, detail.group);
  scene.add(group);

  let time = 0;
  return {
    group,
    base,
    update(dt, cameraPos, speed01, playerShip) {
      const step = Math.max(0, Math.min(0.1, dt || 0));
      time += step;
      if (base && typeof base.update === 'function') base.update(step, cameraPos, speed01);
      if (cameraPos) {
        panorama.mesh.position.x = cameraPos.x;
        panorama.mesh.position.z = cameraPos.z;
      }
      // Very slow celestial drift prevents the panorama from reading as a flat
      // wallpaper; it never follows craft yaw, so landmarks remain stable.
      panorama.mesh.rotation.y = profile.rotation + Math.sin(time * 0.018) * 0.025;
      panorama.material.opacity = profile.panoramaOpacity * (1 - speed01 * 0.08);
      updateEnvironmentDetail(detail.animated, time, speed01 || 0);

      if (base && typeof base.setEnvironmentState === 'function') {
        base.setEnvironmentState({
          time,
          wind: profile.wind,
          speed01: speed01 || 0,
          raceProgress: playerShip && track.length ? playerShip.s / track.length : 0,
        });
      }
    },
    dispose() {
      scene.remove(group);
      if (base && typeof base.dispose === 'function') base.dispose();
      detail.dispose();
      panorama.geometry.dispose();
      panorama.material.dispose();
      panoramaTexture.dispose();
      group.clear();
    },
  };
}
