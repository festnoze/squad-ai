/** Lightweight, strongly themed worlds used by the additional circuits. */
import * as THREE from 'three';

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

function ownMaterial(list, material) {
  list.push(material);
  return material;
}

function makeDetailTexture(kind, owned) {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 512;
  const ctx = canvas.getContext('2d');
  const rock = kind === 'rock';
  const stucco = kind === 'stucco';
  ctx.fillStyle = rock ? '#b7a880' : stucco ? '#e8e1cd' : '#251039';
  ctx.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 5200; i++) {
    const x = (i * 83) % 512;
    const y = (i * 197) % 512;
    const a = 0.018 + (i % 11) * 0.004;
    ctx.fillStyle = rock
      ? `rgba(${40 + (i % 70)},${31 + (i % 55)},${20 + (i % 38)},${a})`
      : stucco
        ? `rgba(80,72,55,${a * 0.65})`
        : `rgba(${80 + (i % 170)},${15 + (i % 90)},${110 + (i % 145)},${a})`;
    ctx.fillRect(x, y, 1 + (i % 4), 1 + ((i * 3) % 5));
  }
  if (rock) {
    ctx.lineWidth = 3;
    for (let i = 0; i < 18; i++) {
      const y = 20 + i * 28 + (i % 3) * 5;
      ctx.strokeStyle = `rgba(65,54,36,${0.08 + (i % 4) * 0.025})`;
      ctx.beginPath();
      ctx.moveTo(0, y);
      for (let x = 0; x <= 512; x += 32) ctx.lineTo(x, y + Math.sin(x * 0.021 + i) * 8);
      ctx.stroke();
    }
  } else if (stucco) {
    ctx.strokeStyle = 'rgba(80,96,102,.18)';
    ctx.lineWidth = 5;
    for (let y = 0; y < 512; y += 128) {
      ctx.strokeRect(0, y, 512, 128);
      for (let x = 18; x < 512; x += 58) {
        ctx.fillStyle = 'rgba(16,54,68,.72)';
        ctx.fillRect(x, y + 28, 31, 48);
        ctx.fillStyle = 'rgba(120,213,235,.22)';
        ctx.fillRect(x + 3, y + 31, 25, 4);
      }
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  texture.needsUpdate = true;
  owned.push(texture);
  return texture;
}

function makeOceanMaterial(materials) {
  return ownMaterial(materials, new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uWind: { value: 1 },
      uDeep: { value: new THREE.Color(0x032f56) },
      uShallow: { value: new THREE.Color(0x20bcd0) },
      uSun: { value: new THREE.Color(0xffe5a7) },
    },
    vertexShader: `
      uniform float uTime;
      uniform float uWind;
      varying vec3 vWorld;
      varying float vWave;
      void main() {
        vec3 p = position;
        float w1 = sin(p.x * 0.009 + uTime * 0.62) * 1.7;
        float w2 = sin(p.y * 0.015 - uTime * 0.81) * 0.85;
        float w3 = sin((p.x + p.y) * 0.028 + uTime * 1.35) * 0.28;
        p.z += (w1 + w2 + w3) * uWind;
        vWave = w1 * 0.32 + w2 * 0.5 + w3;
        vec4 world = modelMatrix * vec4(p, 1.0);
        vWorld = world.xyz;
        gl_Position = projectionMatrix * viewMatrix * world;
      }
    `,
    fragmentShader: `
      uniform float uTime;
      uniform vec3 uDeep;
      uniform vec3 uShallow;
      uniform vec3 uSun;
      varying vec3 vWorld;
      varying float vWave;
      void main() {
        float ripple = sin(vWorld.x * 0.072 + uTime * 2.1) * sin(vWorld.z * 0.055 - uTime * 1.6);
        float glint = pow(max(0.0, ripple * 0.5 + vWave * 0.24), 7.0);
        float bands = 0.5 + 0.5 * sin((vWorld.x + vWorld.z) * 0.004 + vWave);
        vec3 water = mix(uDeep, uShallow, 0.22 + bands * 0.14);
        water += uSun * glint * 1.7;
        gl_FragColor = vec4(water, 1.0);
      }
    `,
    fog: false,
  }));
}

function addSun(group, color, position, size, materials, geometries) {
  const geometry = new THREE.SphereGeometry(size, 32, 16);
  const material = new THREE.MeshBasicMaterial({ color, toneMapped: false });
  geometries.push(geometry);
  materials.push(material);
  const sun = new THREE.Mesh(geometry, material);
  sun.position.copy(position);
  group.add(sun);
  return sun;
}

function createCoast(group, track, materials, geometries, textures, animated) {
  const hemi = new THREE.HemisphereLight(0x9cecff, 0x183a48, 2.25);
  const key = new THREE.DirectionalLight(0xfff1c7, 3.6);
  key.position.set(-650, 900, 420);
  group.add(hemi, key);
  animated.hemi = hemi;
  animated.key = key;

  const oceanGeo = new THREE.PlaneGeometry(9000, 9000, 128, 128);
  const oceanMat = makeOceanMaterial(materials);
  geometries.push(oceanGeo);
  const ocean = new THREE.Mesh(oceanGeo, oceanMat);
  ocean.rotation.x = -Math.PI * 0.5;
  ocean.position.y = -14;
  ocean.receiveShadow = true;
  group.add(ocean);
  animated.ocean = ocean;
  animated.oceanMaterial = oceanMat;

  const rockTexture = makeDetailTexture('rock', textures);
  rockTexture.repeat.set(2.4, 3.1);
  const cliffGeo = new THREE.CylinderGeometry(34, 70, 95, 11, 3);
  const cliffMat = ownMaterial(materials, new THREE.MeshStandardMaterial({
    color: 0xe0d3ad, map: rockTexture, roughness: 0.93, metalness: 0.02,
  }));
  geometries.push(cliffGeo);
  const cliffCount = Math.max(18, Math.round(track.length / 145));
  const cliffs = new THREE.InstancedMesh(cliffGeo, cliffMat, cliffCount);
  const matrix = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  const pos = new THREE.Vector3();
  for (let i = 0; i < cliffCount; i++) {
    track.at((i / cliffCount) * track.length, _frame);
    const side = i % 3 === 0 ? -1 : 1;
    pos.copy(_frame.pos).addScaledVector(_frame.right, side * (_frame.halfWidth + 34));
    pos.y -= 45 + (i % 4) * 5;
    scale.set(0.7 + (i % 5) * 0.09, 0.85 + (i % 3) * 0.14, 0.75 + ((i + 2) % 4) * 0.08);
    matrix.compose(pos, quat, scale);
    cliffs.setMatrixAt(i, matrix);
  }
  cliffs.castShadow = true;
  cliffs.receiveShadow = true;
  group.add(cliffs);

  // White resort towers and palms establish a sunlit Mediterranean shoreline.
  const stuccoTexture = makeDetailTexture('stucco', textures);
  stuccoTexture.repeat.set(1.5, 4);
  const towerGeo = new THREE.BoxGeometry(30, 95, 30, 2, 8, 2);
  const towerMat = ownMaterial(materials, new THREE.MeshStandardMaterial({
    color: 0xf5f0df, map: stuccoTexture, emissive: 0x31536a, emissiveIntensity: 0.08, roughness: 0.75,
  }));
  geometries.push(towerGeo);
  for (let i = 0; i < 11; i++) {
    const tower = new THREE.Mesh(towerGeo, towerMat);
    const angle = (i / 11) * Math.PI * 2;
    tower.position.set(Math.cos(angle) * 900, 24 + (i % 3) * 22, Math.sin(angle) * 900);
    tower.scale.y = 0.65 + (i % 4) * 0.22;
    tower.rotation.y = angle;
    group.add(tower);
  }

  const trunkGeo = new THREE.CylinderGeometry(1.2, 2, 24, 7);
  const crownGeo = new THREE.ConeGeometry(5, 4, 7);
  const frondGeo = new THREE.BoxGeometry(14, 0.18, 1.5, 6, 1, 1);
  const trunkMat = ownMaterial(materials, new THREE.MeshStandardMaterial({ color: 0x7b4b2a, roughness: 1 }));
  const crownMat = ownMaterial(materials, new THREE.MeshStandardMaterial({ color: 0x1f8b5a, roughness: 0.9 }));
  geometries.push(trunkGeo, crownGeo, frondGeo);
  for (let i = 0; i < 24; i++) {
    track.at(((i + 0.35) / 24) * track.length, _frame);
    const side = i % 2 ? 1 : -1;
    const palm = new THREE.Group();
    palm.position.copy(_frame.pos).addScaledVector(_frame.right, side * (_frame.halfWidth + 22));
    const trunk = new THREE.Mesh(trunkGeo, trunkMat);
    trunk.position.y = 12;
    const crown = new THREE.Mesh(crownGeo, crownMat);
    crown.position.y = 27;
    crown.rotation.x = Math.PI;
    palm.add(trunk, crown);
    for (let f = 0; f < 7; f++) {
      const frond = new THREE.Mesh(frondGeo, crownMat);
      const a = (f / 7) * Math.PI * 2;
      frond.position.set(Math.cos(a) * 6, 27.5, Math.sin(a) * 6);
      frond.rotation.y = -a;
      frond.rotation.z = -0.28;
      palm.add(frond);
    }
    group.add(palm);
  }

  // Small craft and navigation buoys provide believable scale on the water.
  const hullGeo = new THREE.CapsuleGeometry(3.2, 12, 4, 10);
  const cabinGeo = new THREE.BoxGeometry(4.8, 2.6, 5.8);
  const hullMat = ownMaterial(materials, new THREE.MeshStandardMaterial({ color: 0xf1efe6, roughness: 0.46, metalness: 0.18 }));
  const glassMat = ownMaterial(materials, new THREE.MeshStandardMaterial({ color: 0x143e52, roughness: 0.1, metalness: 0.6 }));
  geometries.push(hullGeo, cabinGeo);
  const boats = [];
  for (let i = 0; i < 9; i++) {
    const boat = new THREE.Group();
    const hull = new THREE.Mesh(hullGeo, hullMat);
    hull.rotation.x = Math.PI * 0.5;
    hull.scale.set(1, 0.48, 1);
    const cabin = new THREE.Mesh(cabinGeo, glassMat);
    cabin.position.y = 2.1;
    boat.add(hull, cabin);
    const a = i * 2.31;
    boat.position.set(Math.cos(a) * (1050 + (i % 3) * 180), -10, Math.sin(a) * (1050 + (i % 3) * 180));
    boat.rotation.y = a + 0.4;
    boat.userData.phase = i * 0.74;
    group.add(boat);
    boats.push(boat);
  }
  animated.boats = boats;

  addSun(group, 0xffe7a3, new THREE.Vector3(-1200, 720, -1800), 125, materials, geometries);
}

function createPsychedelic(group, track, materials, geometries, textures, animated) {
  const hemi = new THREE.HemisphereLight(0xff45ec, 0x10265f, 1.9);
  const key = new THREE.DirectionalLight(0x83ff54, 2.8);
  key.position.set(500, 800, 300);
  group.add(hemi, key);
  animated.hemi = hemi;
  animated.key = key;

  const floorGeo = new THREE.CircleGeometry(3100, 96);
  const floorTexture = makeDetailTexture('crystal', textures);
  floorTexture.repeat.set(12, 12);
  const floorMat = ownMaterial(materials, new THREE.MeshStandardMaterial({
    color: 0x170326, map: floorTexture, emissive: 0x3b0758, emissiveMap: floorTexture,
    emissiveIntensity: 0.75, roughness: 0.65, metalness: 0.3, side: THREE.DoubleSide,
  }));
  geometries.push(floorGeo);
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI * 0.5;
  floor.position.y = -55;
  group.add(floor);

  const ringGeo = new THREE.TorusGeometry(21, 1.4, 8, 48);
  geometries.push(ringGeo);
  const ringColors = [0xff32dc, 0x73ff3e, 0x35d9ff, 0xffa229];
  const rings = [];
  for (let i = 0; i < 18; i++) {
    track.at(((i + 0.55) / 18) * track.length, _frame);
    const material = ownMaterial(materials, new THREE.MeshBasicMaterial({
      color: ringColors[i % ringColors.length],
      transparent: true,
      opacity: 0.68,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    }));
    const ring = new THREE.Mesh(ringGeo, material);
    ring.position.copy(_frame.pos).addScaledVector(_frame.up, 8);
    const basis = new THREE.Matrix4().makeBasis(_frame.right, _frame.up, _frame.tangent);
    ring.quaternion.setFromRotationMatrix(basis);
    ring.scale.setScalar(0.7 + (i % 5) * 0.12);
    ring.userData.phase = i * 0.73;
    group.add(ring);
    rings.push(ring);
  }
  animated.rings = rings;

  const crystalGeo = new THREE.IcosahedronGeometry(26, 0);
  geometries.push(crystalGeo);
  const crystals = [];
  for (let i = 0; i < 42; i++) {
    const mat = ownMaterial(materials, new THREE.MeshStandardMaterial({
      color: ringColors[(i + 2) % ringColors.length],
      emissive: ringColors[i % ringColors.length],
      emissiveIntensity: 1.7,
      roughness: 0.18,
      metalness: 0.55,
      flatShading: true,
    }));
    const crystal = new THREE.Mesh(crystalGeo, mat);
    const angle = (i / 42) * Math.PI * 2 * 3.7;
    const radius = 420 + (i % 7) * 115;
    crystal.position.set(Math.cos(angle) * radius, 80 + (i % 9) * 38, Math.sin(angle) * radius);
    crystal.scale.setScalar(0.55 + (i % 4) * 0.24);
    crystal.userData.phase = i * 0.47;
    group.add(crystal);
    crystals.push(crystal);
  }
  animated.crystals = crystals;

  // Deep field dust adds scale and parallax without adding opaque geometry.
  const dustGeo = new THREE.BufferGeometry();
  const dustCount = 1800;
  const dustPos = new Float32Array(dustCount * 3);
  const dustCol = new Float32Array(dustCount * 3);
  const c = new THREE.Color();
  for (let i = 0; i < dustCount; i++) {
    const a = i * 2.399963;
    const radius = 300 + ((i * 137) % 2600);
    dustPos[i * 3] = Math.cos(a) * radius;
    dustPos[i * 3 + 1] = 20 + ((i * 97) % 1250);
    dustPos[i * 3 + 2] = Math.sin(a) * radius;
    c.setHSL((i * 0.037) % 1, 0.9, 0.62);
    dustCol[i * 3] = c.r;
    dustCol[i * 3 + 1] = c.g;
    dustCol[i * 3 + 2] = c.b;
  }
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
  dustGeo.setAttribute('color', new THREE.BufferAttribute(dustCol, 3));
  const dustMat = ownMaterial(materials, new THREE.PointsMaterial({
    size: 3.2, vertexColors: true, transparent: true, opacity: 0.66,
    depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true,
  }));
  geometries.push(dustGeo);
  const dust = new THREE.Points(dustGeo, dustMat);
  group.add(dust);
  animated.dust = dust;

  const knotGeo = new THREE.TorusKnotGeometry(185, 19, 180, 16, 2, 5);
  const knotMat = ownMaterial(materials, new THREE.MeshBasicMaterial({
    color: 0xff3fe5, wireframe: true, transparent: true, opacity: 0.32,
    blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false,
  }));
  geometries.push(knotGeo);
  const knot = new THREE.Mesh(knotGeo, knotMat);
  knot.position.set(0, 280, 0);
  group.add(knot);
  animated.knot = knot;
}

export function createThemedWorld(scene, track, level) {
  const group = new THREE.Group();
  group.name = 'world-' + level.theme;
  const materials = [];
  const geometries = [];
  const ownedTextures = [];
  const animated = {};

  if (level.theme === 'coast') {
    scene.background = new THREE.Color(0x66cbed);
    scene.fog = new THREE.Fog(0x8edbf0, 900, 4300);
    createCoast(group, track, materials, geometries, ownedTextures, animated);
  } else {
    scene.background = new THREE.Color(0x070014);
    scene.fog = new THREE.FogExp2(0x160329, 0.00042);
    createPsychedelic(group, track, materials, geometries, ownedTextures, animated);
  }
  scene.environment = null;
  scene.add(group);

  return {
    group,
    update(dt) {
      const t = performance.now() * 0.001;
      if (animated.ocean) {
        animated.ocean.position.y = -14 + Math.sin(t * 0.7) * 0.35;
      }
      if (animated.oceanMaterial) {
        animated.oceanMaterial.uniforms.uTime.value = t;
      }
      if (animated.boats) {
        for (let i = 0; i < animated.boats.length; i++) {
          const boat = animated.boats[i];
          boat.position.y = -9.2 + Math.sin(t * 0.8 + boat.userData.phase) * 0.7;
          boat.rotation.z = Math.sin(t * 0.65 + boat.userData.phase) * 0.025;
        }
      }
      if (animated.rings) {
        for (let i = 0; i < animated.rings.length; i++) {
          const ring = animated.rings[i];
          ring.rotation.z += dt * (0.18 + (i % 3) * 0.08);
          ring.material.opacity = 0.48 + Math.sin(t * 2.1 + ring.userData.phase) * 0.2;
          ring.material.color.setHSL((t * 0.045 + i / animated.rings.length) % 1, 1, 0.62);
        }
      }
      if (animated.crystals) {
        for (let i = 0; i < animated.crystals.length; i++) {
          const crystal = animated.crystals[i];
          crystal.rotation.x += dt * 0.13;
          crystal.rotation.y += dt * 0.21;
          crystal.position.y += Math.sin(t * 1.2 + crystal.userData.phase) * dt * 2.2;
          crystal.material.emissive.setHSL((t * 0.06 + i * 0.071) % 1, 1, 0.42);
        }
      }
      if (animated.knot) {
        animated.knot.rotation.x = t * 0.08;
        animated.knot.rotation.y = t * 0.13;
        animated.knot.material.color.setHSL((t * 0.08) % 1, 1, 0.62);
      }
      if (animated.dust) animated.dust.rotation.y = t * 0.006;
    },
    setEnvironmentState(state) {
      if (animated.oceanMaterial && state) {
        animated.oceanMaterial.uniforms.uWind.value = Math.max(0.45, state.wind || 1);
      }
      if (animated.dust && state) {
        animated.dust.material.opacity = 0.66 - (state.speed01 || 0) * 0.12;
      }
      if (animated.key && state) {
        const pulse = level.theme === 'psychedelic'
          ? 1 + Math.sin(state.time * 0.7) * 0.12
          : 1 + Math.sin(state.time * 0.08) * 0.025;
        animated.key.intensity = (level.theme === 'coast' ? 3.6 : 2.8) * pulse;
      }
      if (animated.hemi && state) {
        animated.hemi.intensity = (level.theme === 'coast' ? 2.25 : 1.9)
          * (1 - (state.speed01 || 0) * 0.06);
      }
      if (scene.fog && scene.fog.isFogExp2 && state) {
        scene.fog.density = 0.00042 * (1 + Math.sin(state.raceProgress * Math.PI * 2) * 0.14);
      }
    },
    dispose() {
      scene.remove(group);
      scene.fog = null;
      scene.background = null;
      for (let i = 0; i < geometries.length; i++) geometries[i].dispose();
      for (let i = 0; i < materials.length; i++) materials[i].dispose();
      for (let i = 0; i < ownedTextures.length; i++) ownedTextures[i].dispose();
      group.clear();
    },
  };
}
