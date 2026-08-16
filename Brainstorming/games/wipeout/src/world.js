/**
 * VELOCITRON - world.js
 *
 * Everything around the circuit: night sky, PMREM environment, fog, lights,
 * an instanced neon megacity, a textured city ground, low mesa relief, a low
 * cloud deck, a horizon light dome, a moon, flying traffic, holographic
 * billboards and a star field.
 *
 * Placement rule: the centreline is sampled once into a flat array and baked
 * into a coarse 2D occupancy grid. No prop is ever placed closer than
 * CLEARANCE metres (XZ) from the centreline, so nothing can intersect the
 * circuit whatever its height.
 *
 * Brightness rule: the background exists to be READ, never to compete. The
 * track neon emits above 1.0 in linear space and owns the bloom (threshold
 * 1.0); every background element here peaks below ~0.09 linear, which lands
 * around 80/255 after the ACES + sRGB pass in post.js. Detail and contrast
 * inside the dark range, never more overall brightness.
 *
 * Budget: roughly 25 draw calls (4 instanced building meshes, 1 rooftop deck
 * mesh, 1 facade sign mesh, 2 instanced traffic meshes, 1 beacon mesh, 1 mesa
 * mesh, ground, 2 cloud layers, horizon dome, moon, 3 billboard meshes, stars)
 * and never allocates in update().
 */

import * as THREE from 'three';
import { PALETTE } from './config.js';

// ---------------------------------------------------------------------------
// Tuning
// ---------------------------------------------------------------------------
const SAMPLE_STEP = 6; // metres between cached centreline samples
const CLEARANCE = 45; // minimum XZ distance from the centreline for any prop
const CELL = 42; // occupancy / building cell size, metres

const CITY_RADIUS = 1300; // buildings live inside this radius around the track
const BUILDING_TARGET = 520; // instanced skyscrapers, 3 profiles
const SIGNATURE_TOWERS = 8; // taller landmarks with blinking antennas
const BEACONS_PER_TOWER = 2;
const MESA_COUNT = 110;
const TRAFFIC_COUNT = 18;
const BILLBOARD_TARGET = 14;
const BILLBOARD_OFFSET = 34; // metres beyond the wall, keeps ~45 m from the axis
const STAR_COUNT = 1500;
const STAR_RADIUS = 3500;

const GROUND_DROP = 60; // ground plane sits this far below the lowest track point
const CITY_GROUND_SIZE = 14000; // static, centred on the circuit, edge always in the fog
const CITY_GROUND_TILE = 440; // metres per city block plan tile

// Rooftop decks. The building profiles are merged geometries without a
// separate top face group, so each building gets one instanced quad instead.
// Per profile: height fraction of the deck, then its footprint fraction.
const ROOF_DECK = [
  [0.944, 0.98, 0.98], // slab: full width roof, the penthouse pokes through it
  [0.983, 0.50, 0.50], // stepped: small deck on the top step
  [0.924, 0.72, 0.72], // prism: square deck inscribed in the octagonal cap
];

const SIGN_EVERY = 6; // one tall tower in six carries a vertical neon sign
const SIGN_MIN_HEIGHT = 95;

// Low cloud deck. Heights are metres above the highest point of the circuit
// (about 46 m), so the layers always sit above the road and below the
// signature towers. Per layer: size, height, opacity, drift x, drift z.
// Two layers, not three, and no wider than the fog actually lets you see: these
// planes are full screen alpha, and at 9 km across the deck alone cost more per
// frame than the entire rest of the scene.
const CLOUD_LAYERS = [
  [3400, 112, 0.60, 5.5, 2.0],
  [4600, 190, 0.38, -3.6, 4.2],
];
const CLOUD_REPEAT = 2; // same texture for both layers, the plane size sets the scale

// Moon, fixed in direction relative to the camera so it never slides around.
const MOON_DIR = new THREE.Vector3(-0.52, 0.44, -0.73).normalize();
const MOON_DISTANCE = 3000;
const MOON_SIZE = 300;
const MOON_HALO_SCALE = 3.6;
const MOON_OFFSET = MOON_DIR.clone().multiplyScalar(MOON_DISTANCE);

// Horizon light dome: sits beyond the mesas and inside the star radius, so
// every silhouette in the scene has something to stand against.
const DOME_RADIUS = 3050;
const DOME_HEIGHT = 1900;
const DOME_DROP = 120; // dome base below the ground plane

const FOG_DENSITY = 0.0009; // 0.0016 erased the whole mid distance

const SHADOW_SPAN = 140; // ortho shadow camera width, metres
const SHADOW_MAP_SIZE = 2048;

const POINT_LIGHT_COUNT = 6; // never changes: swapping light counts recompiles shaders
const POINT_LIGHT_SPOTS = 16;
const POINT_LIGHT_RANGE = 320;
const POINT_LIGHT_INTENSITY = 5200; // candela, decay 2
const LIGHT_PICK_INTERVAL = 0.2; // seconds between point light reassignments

const WORLD_UP = new THREE.Vector3(0, 1, 0);
const LIGHT_OFFSET = new THREE.Vector3(-190, 250, 140);
const LIGHT_AXIS_Z = LIGHT_OFFSET.clone().normalize();
const LIGHT_AXIS_X = new THREE.Vector3().crossVectors(WORLD_UP, LIGHT_AXIS_Z).normalize();
const LIGHT_AXIS_Y = new THREE.Vector3().crossVectors(LIGHT_AXIS_Z, LIGHT_AXIS_X).normalize();

const NEON_TINTS = [
  PALETTE.cyan, PALETTE.magenta, PALETTE.violet,
  PALETTE.amber, PALETTE.lime, PALETTE.white,
];

// The per instance colour multiplies the WHOLE emissive facade, so a saturated
// hue turns every tower into one flat block of colour and the skyline reads as
// a bar chart. Pull each tint most of the way to white: the building keeps a
// recognisable cast, the individual window tints painted in the texture survive,
// and nothing back there competes with the track neon.
const TINT_DESATURATION = 0.66;
const _tintWhite = new THREE.Color(1, 1, 1);

// ---------------------------------------------------------------------------
// Deterministic PRNG so the city is identical on every run
// ---------------------------------------------------------------------------
function mulberry32(seed) {
  let a = seed >>> 0;
  return function random() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Texture lookup that always yields null (never undefined) for three. */
function tex(textures, name) {
  return (textures && textures[name]) || null;
}

/**
 * Safe lookup: the wanted texture, else the closest existing equivalent, else
 * null. textures.js grows independently of this file, so every new map is read
 * through here and the world still builds when one of them is not there yet.
 */
function texOr(textures, name, fallback) {
  return tex(textures, name) || (fallback ? tex(textures, fallback) : null);
}

/** Shared bookkeeping for the texture instances this module configures. */
function makeTexState() {
  return { owned: [], claimed: new Set(), cache: new Map() };
}

/**
 * Same as texOr, but returns an instance whose wrapping and repeat are set to
 * (rx, ry). The first caller of a given source claims it; a later caller that
 * needs another repeat gets a clone. Clones share the GPU upload (three keys
 * the upload on texture.source), only the repeat uniform differs, so this is
 * cheap and it keeps two users from fighting over one repeat.
 */
function repeatMap(textures, state, name, fallback, rx, ry) {
  const src = texOr(textures, name, fallback);
  if (!src) return null;
  const key = `${src.uuid}|${rx}|${ry}`;
  const cached = state.cache.get(key);
  if (cached) return cached;
  let out = src;
  if (state.claimed.has(src.uuid)) {
    out = src.clone();
    state.owned.push(out);
  } else {
    state.claimed.add(src.uuid);
  }
  out.wrapS = THREE.RepeatWrapping;
  out.wrapT = THREE.RepeatWrapping;
  out.repeat.set(rx, ry);
  out.needsUpdate = true;
  state.cache.set(key, out);
  return out;
}

function smoothstep(edge0, edge1, x) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

// ---------------------------------------------------------------------------
// Scratch state. Each block belongs to exactly one function so that two
// functions can never stomp on each other, even if one calls the other.
// ---------------------------------------------------------------------------
const _camFallback = new THREE.Vector3();

const _shadowVec = new THREE.Vector3();

const _pickIdx = new Int32Array(POINT_LIGHT_COUNT);
const _pickDist = new Float64Array(POINT_LIGHT_COUNT);

const _trafficMat = new THREE.Matrix4();
const _trafficPos = new THREE.Vector3();
const _trafficScale = new THREE.Vector3(1, 1, 1); // traffic never scales
const _trafficQuat = new THREE.Quaternion();
const _trafficRoll = new THREE.Quaternion();
const _trafficAxisY = new THREE.Vector3(0, 1, 0);
const _trafficAxisX = new THREE.Vector3(1, 0, 0);

const _beaconMat = new THREE.Matrix4();

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

/**
 * Concatenate a list of small generated geometries into one non indexed
 * BufferGeometry. The inputs are consumed (disposed): they only exist to be
 * merged. three/examples BufferGeometryUtils is not available here.
 */
function mergeGeoms(list) {
  const flat = [];
  let total = 0;
  for (let i = 0; i < list.length; i++) {
    const src = list[i];
    const g = src.index ? src.toNonIndexed() : src;
    if (g !== src) src.dispose();
    flat.push(g);
    total += g.attributes.position.count;
  }
  const position = new Float32Array(total * 3);
  const normal = new Float32Array(total * 3);
  const uv = new Float32Array(total * 2);
  let vo = 0;
  for (let i = 0; i < flat.length; i++) {
    const g = flat[i];
    const p = g.attributes.position;
    position.set(p.array.subarray(0, p.count * 3), vo * 3);
    const n = g.attributes.normal;
    if (n) normal.set(n.array.subarray(0, p.count * 3), vo * 3);
    const u = g.attributes.uv;
    if (u) uv.set(u.array.subarray(0, p.count * 2), vo * 2);
    vo += p.count;
    g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(position, 3));
  out.setAttribute('normal', new THREE.BufferAttribute(normal, 3));
  out.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  out.computeBoundingSphere();
  return out;
}

function box(w, h, d, y) {
  const g = new THREE.BoxGeometry(w, h, d);
  g.translate(0, y, 0);
  return g;
}

function tube(rTop, rBottom, h, sides, y) {
  const g = new THREE.CylinderGeometry(rTop, rBottom, h, sides, 1, false);
  g.translate(0, y, 0);
  return g;
}

/** Unit building profiles: footprint 1 x 1 in XZ, height 1 in Y, base at y = 0. */
function makeBuildingProfiles() {
  const slab = mergeGeoms([
    box(1, 0.94, 1, 0.47),
    box(0.74, 0.05, 0.74, 0.965),
    box(0.1, 0.06, 0.1, 1.01),
  ]);
  const stepped = mergeGeoms([
    box(1, 0.52, 1, 0.26),
    box(0.78, 0.28, 0.78, 0.66),
    box(0.52, 0.18, 0.52, 0.89),
    box(0.05, 0.16, 0.05, 1.06),
  ]);
  const prism = mergeGeoms([
    tube(0.44, 0.5, 0.88, 8, 0.44),
    tube(0.56, 0.56, 0.04, 8, 0.9),
    tube(0.02, 0.09, 0.26, 5, 1.05),
  ]);
  return [slab, stepped, prism];
}

/** Landmark tower, same unit convention, total height 1.08. */
function makeSignatureGeometry() {
  return mergeGeoms([
    tube(0.4, 0.62, 0.72, 6, 0.36),
    box(0.52, 0.05, 0.52, 0.745),
    tube(0.3, 0.34, 0.1, 6, 0.82),
    tube(0.03, 0.06, 0.3, 4, 0.98),
  ]);
}

/**
 * Patch a standard material so the per instance color also tints the emissive
 * channel. Without this every instance of a mesh glows the exact same colour.
 * three declares vColor in the fragment shader under USE_COLOR as soon as an
 * instanceColor attribute exists, hence the guard.
 */
function tintEmissiveByInstanceColor(material) {
  material.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <emissivemap_fragment>',
      '#include <emissivemap_fragment>\n\t#ifdef USE_COLOR\n\ttotalEmissiveRadiance *= vColor;\n\t#endif',
    );
  };
  material.customProgramCacheKey = () => 'velocitron-instance-emissive';
}

// ---------------------------------------------------------------------------
// Track sampling and occupancy
// ---------------------------------------------------------------------------

function buildTrackSamples(track) {
  const frame = track.makeFrame();
  const count = Math.max(16, Math.round(track.length / SAMPLE_STEP));
  const step = track.length / count;
  const pts = new Float32Array(count * 3);
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  let minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < count; i++) {
    track.at(i * step, frame);
    const p = frame.pos;
    pts[i * 3] = p.x;
    pts[i * 3 + 1] = p.y;
    pts[i * 3 + 2] = p.z;
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.z < minZ) minZ = p.z;
    if (p.z > maxZ) maxZ = p.z;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  const centreX = (minX + maxX) * 0.5;
  const centreZ = (minZ + maxZ) * 0.5;
  let radius = 0;
  for (let i = 0; i < count; i++) {
    const d = Math.hypot(pts[i * 3] - centreX, pts[i * 3 + 2] - centreZ);
    if (d > radius) radius = d;
  }
  return { pts, count, step, minY, maxY, centreX, centreZ, radius };
}

/** Coarse grid flagging every cell that could contain a point too close to the axis. */
function buildOccupancy(samples, halfExtent) {
  const minX = samples.centreX - halfExtent;
  const minZ = samples.centreZ - halfExtent;
  const nx = Math.ceil((halfExtent * 2) / CELL) + 1;
  const nz = nx;
  const blocked = new Uint8Array(nx * nz);
  const reach = CLEARANCE + CELL * Math.SQRT1_2; // cell centre test, conservative
  const span = Math.ceil(reach / CELL);
  const reach2 = reach * reach;
  for (let i = 0; i < samples.count; i++) {
    const px = samples.pts[i * 3];
    const pz = samples.pts[i * 3 + 2];
    const gx = Math.floor((px - minX) / CELL);
    const gz = Math.floor((pz - minZ) / CELL);
    for (let dz = -span; dz <= span; dz++) {
      const cz = gz + dz;
      if (cz < 0 || cz >= nz) continue;
      const wz = minZ + (cz + 0.5) * CELL - pz;
      for (let dx = -span; dx <= span; dx++) {
        const cx = gx + dx;
        if (cx < 0 || cx >= nx) continue;
        const wx = minX + (cx + 0.5) * CELL - px;
        if (wx * wx + wz * wz <= reach2) blocked[cz * nx + cx] = 1;
      }
    }
  }
  return { blocked, used: new Uint8Array(nx * nz), nx, nz, minX, minZ };
}

function cellIndex(occ, x, z) {
  const gx = Math.floor((x - occ.minX) / CELL);
  const gz = Math.floor((z - occ.minZ) / CELL);
  if (gx < 0 || gz < 0 || gx >= occ.nx || gz >= occ.nz) return -1;
  return gz * occ.nx + gx;
}

/**
 * Exact distance from (x, z) to the centreline, ignoring the samples inside a
 * window centred on skipIndex (used to place props alongside their own section
 * of track while still checking every other section).
 */
function distanceToTrack(samples, x, z, skipIndex, skipSpan) {
  let best = Infinity;
  const n = samples.count;
  for (let i = 0; i < n; i++) {
    if (skipSpan > 0) {
      let d = i - skipIndex;
      if (d > n * 0.5) d -= n;
      if (d < -n * 0.5) d += n;
      if (Math.abs(d) <= skipSpan) continue;
    }
    const dx = samples.pts[i * 3] - x;
    const dz = samples.pts[i * 3 + 2] - z;
    const d2 = dx * dx + dz * dz;
    if (d2 < best) best = d2;
  }
  return Math.sqrt(best);
}

/** Cheap bounding radius reject in front of the exact per sample test. */
function isFarFromTrack(samples, x, z, minDist, skipIndex, skipSpan) {
  const r = Math.hypot(x - samples.centreX, z - samples.centreZ);
  if (r > samples.radius + minDist) return true;
  return distanceToTrack(samples, x, z, skipIndex, skipSpan) >= minDist;
}

// ---------------------------------------------------------------------------
// Builders
// ---------------------------------------------------------------------------

function buildSky(scene, textures, renderer) {
  const sky = tex(textures, 'sky');
  if (!sky) return null;
  sky.mapping = THREE.EquirectangularReflectionMapping;
  sky.colorSpace = THREE.SRGBColorSpace;
  sky.wrapS = THREE.RepeatWrapping;
  sky.wrapT = THREE.ClampToEdgeWrapping;
  sky.needsUpdate = true;
  scene.background = sky;

  const gl = renderer || (textures && textures.renderer) || null;
  if (gl && gl.isWebGLRenderer) {
    // Explicit PMREM so the craft hulls get a proper blurred night reflection.
    const pmrem = new THREE.PMREMGenerator(gl);
    pmrem.compileEquirectangularShader();
    const target = pmrem.fromEquirectangular(sky);
    pmrem.dispose();
    scene.environment = target.texture;
    return target;
  }
  // No renderer handed over: three builds the same PMREM internally the first
  // time the environment is used (WebGLCubeUVMaps), which is equivalent here.
  scene.environment = sky;
  return null;
}

function buildLights(group) {
  // The only non emissive surfaces are the asphalt and the craft hulls, so
  // these two lights carry the whole readability of the race. Too low and the
  // craft disappears against black tarmac.
  const hemi = new THREE.HemisphereLight(0x4a36a0, 0x06070f, 0.6);
  group.add(hemi);

  const sun = new THREE.DirectionalLight(0x9fc4ff, 1.55);
  sun.position.copy(LIGHT_OFFSET);
  sun.castShadow = true;
  sun.shadow.mapSize.set(SHADOW_MAP_SIZE, SHADOW_MAP_SIZE);
  const cam = sun.shadow.camera;
  cam.left = -SHADOW_SPAN * 0.5;
  cam.right = SHADOW_SPAN * 0.5;
  cam.top = SHADOW_SPAN * 0.5;
  cam.bottom = -SHADOW_SPAN * 0.5;
  cam.near = 10;
  cam.far = 700;
  cam.updateProjectionMatrix();
  sun.shadow.bias = -0.0006;
  sun.shadow.normalBias = 0.4;
  group.add(sun);
  group.add(sun.target);

  const points = [];
  for (let i = 0; i < POINT_LIGHT_COUNT; i++) {
    const light = new THREE.PointLight(0xffffff, 0, POINT_LIGHT_RANGE, 2);
    light.castShadow = false;
    group.add(light);
    points.push(light);
  }
  return { hemi, sun, points };
}

function buildPointLightSpots(track, samples, rand) {
  const frame = track.makeFrame();
  const spots = new Float32Array(POINT_LIGHT_SPOTS * 3);
  const colors = [];
  let n = 0;
  for (let k = 0; k < POINT_LIGHT_SPOTS * 3 && n < POINT_LIGHT_SPOTS; k++) {
    const s = (k / (POINT_LIGHT_SPOTS * 3)) * track.length;
    track.at(s, frame);
    const side = rand() < 0.5 ? -1 : 1;
    const off = frame.halfWidth + 52 + rand() * 22;
    // Horizontal part of the frame right vector, so banking does not eat the offset.
    const rl = Math.hypot(frame.right.x, frame.right.z) || 1;
    const x = frame.pos.x + (frame.right.x / rl) * side * off;
    const z = frame.pos.z + (frame.right.z / rl) * side * off;
    const idx = Math.round(s / samples.step) % samples.count;
    if (!isFarFromTrack(samples, x, z, CLEARANCE, idx, 14)) continue;
    spots[n * 3] = x;
    spots[n * 3 + 1] = frame.pos.y - 3;
    spots[n * 3 + 2] = z;
    colors.push(new THREE.Color(NEON_TINTS[n % NEON_TINTS.length]));
    n++;
  }
  return { spots, colors, count: n };
}

/**
 * One instanced quad per building, laid flat at the top of its main mass. The
 * merged profile geometries have no separate top face group, so this is how a
 * roof gets its own vents / tanks / helipad material.
 */
function buildRooftops(group, textures, texState, buckets, groundY) {
  let total = 0;
  for (let p = 0; p < buckets.length; p++) total += buckets[p].length / 7;
  if (total === 0) return null;

  const geometry = new THREE.PlaneGeometry(1, 1, 1, 1);
  geometry.rotateX(-Math.PI * 0.5);
  const material = new THREE.MeshStandardMaterial({
    color: 0x151824,
    map: repeatMap(textures, texState, 'rooftop', null, 1, 1),
    emissive: 0xffffff,
    emissiveMap: repeatMap(textures, texState, 'rooftopEmissive', null, 1, 1),
    emissiveIntensity: 0.85,
    roughness: 0.95,
    metalness: 0.05,
  });
  // A deck faces straight up into the directional light, so the albedo has to
  // stay low or the roofs turn into the brightest thing on screen. These are
  // linear values: peak texel lands near 0.05 linear, about 65 out of 255.
  if (material.map) material.color.setRGB(0.085, 0.090, 0.115);
  const mesh = new THREE.InstancedMesh(geometry, material, total);
  mesh.receiveShadow = false;

  const mat4 = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const pos = new THREE.Vector3();
  const scale = new THREE.Vector3();
  const axis = new THREE.Vector3(0, 1, 0);

  let k = 0;
  for (let p = 0; p < buckets.length; p++) {
    const data = buckets[p];
    const deck = ROOF_DECK[p] || ROOF_DECK[0];
    for (let i = 0; i < data.length; i += 7) {
      const h = data[i + 4];
      pos.set(data[i], groundY + h * deck[0], data[i + 1]);
      scale.set(data[i + 2] * deck[1], 1, data[i + 3] * deck[2]);
      quat.setFromAxisAngle(axis, data[i + 5]);
      mat4.compose(pos, quat, scale);
      mesh.setMatrixAt(k, mat4);
      k++;
    }
  }
  mesh.count = k;
  mesh.instanceMatrix.needsUpdate = true;
  mesh.computeBoundingSphere();
  group.add(mesh);
  return { mesh, geometry, material };
}

/** Horizontal direction from (x, z) to the closest point of the centreline. */
function directionToTrack(samples, x, z, out) {
  let best = Infinity;
  let bi = 0;
  for (let i = 0; i < samples.count; i++) {
    const dx = samples.pts[i * 3] - x;
    const dz = samples.pts[i * 3 + 2] - z;
    const d2 = dx * dx + dz * dz;
    if (d2 < best) { best = d2; bi = i; }
  }
  out.set(samples.pts[bi * 3] - x, 0, samples.pts[bi * 3 + 2] - z);
  if (out.lengthSq() > 1e-6) out.normalize();
  else out.set(1, 0, 0);
  return Math.sqrt(best);
}

/**
 * Tall vertical neon strips hung on one facade of a subset of the taller
 * towers, snapped to the nearest facade plane and turned toward the circuit.
 * Alpha blended (not additive) so the fog can still swallow the far ones, and
 * tinted well under 1.0 so they never read brighter than the track.
 */
function buildFacadeSigns(group, textures, samples, buckets, groundY) {
  const map = texOr(textures, 'facadeSign', null);
  if (!map) return null;

  const positions = [];
  const normals = [];
  const uvs = [];
  const colors = [];
  const dir = new THREE.Vector3();
  const tint = new THREE.Color();
  let candidate = 0;
  let placed = 0;

  for (let p = 0; p < buckets.length; p++) {
    const data = buckets[p];
    for (let i = 0; i < data.length; i += 7) {
      const h = data[i + 4];
      if (h < SIGN_MIN_HEIGHT) continue;
      candidate++;
      if (candidate % SIGN_EVERY !== 0) continue;

      const px = data[i];
      const pz = data[i + 1];
      const w = data[i + 2];
      const d = data[i + 3];
      const rot = data[i + 5];
      directionToTrack(samples, px, pz, dir);

      // Snap the facing to the dominant local axis of the footprint so the
      // panel lies flat on a real facade instead of floating off a corner.
      // A yaw of rot about Y sends local X to (cos, -sin) and local Z to
      // (sin, cos) in world (x, z).
      const cs = Math.cos(rot);
      const sn = Math.sin(rot);
      const ax = dir.x * cs - dir.z * sn; // component along local X
      const az = dir.x * sn + dir.z * cs; // component along local Z
      let nx;
      let nz;
      let half;
      let sw;
      if (Math.abs(ax) >= Math.abs(az)) {
        const s = ax >= 0 ? 1 : -1;
        nx = cs * s;
        nz = -sn * s;
        half = w * 0.5;
        sw = Math.min(6.5, d * 0.34);
      } else {
        const s = az >= 0 ? 1 : -1;
        nx = sn * s;
        nz = cs * s;
        half = d * 0.5;
        sw = Math.min(6.5, w * 0.34);
      }
      const cx = px + nx * (half + 0.45);
      const cz = pz + nz * (half + 0.45);
      if (!isFarFromTrack(samples, cx, cz, CLEARANCE, 0, 0)) continue;

      // Panel plane: normal (nx, nz), width axis is the horizontal tangent.
      const tx = -nz;
      const tz = nx;
      const y0 = data[i + 6]; // reused as a stable per building random
      const bottom = groundY + h * (0.3 + y0 * 0.08);
      const top = groundY + h * (0.82 + y0 * 0.06);
      const hw = sw * 0.5;

      const corners = [
        [-hw, bottom], [hw, bottom], [hw, top],
        [-hw, bottom], [hw, top], [-hw, top],
      ];
      const cuv = [[0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1]];
      tint.setHex(NEON_TINTS[placed % NEON_TINTS.length]).multiplyScalar(0.5);
      for (let c = 0; c < 6; c++) {
        positions.push(cx + tx * corners[c][0], corners[c][1], cz + tz * corners[c][0]);
        normals.push(nx, 0, nz);
        uvs.push(cuv[c][0], cuv[c][1]);
        colors.push(tint.r, tint.g, tint.b);
      }
      placed++;
    }
  }
  if (placed === 0) return null;

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(normals), 3));
  geometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvs), 2));
  geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(colors), 3));
  geometry.computeBoundingSphere();

  const material = new THREE.MeshBasicMaterial({
    map,
    vertexColors: true, // plain Mesh, the color attribute above really exists
    transparent: true,
    opacity: 0.85,
    side: THREE.DoubleSide,
    depthWrite: false,
    fog: true,
  });
  const mesh = new THREE.Mesh(geometry, material);
  group.add(mesh);
  return { mesh, geometry, material, count: placed };
}

function buildCity(group, textures, texState, occ, samples, rand, groundY) {
  const profiles = makeBuildingProfiles();
  const meshes = [];
  const materials = [];
  // One facade per profile, with its own window pitch. Three identical towers
  // repeated 500 times is what made the old skyline read as a single cut-out.
  const facades = [
    { map: 'windows', emissive: 'windowsEmissive', repeat: [2, 4], intensity: 0.95 },
    { map: 'windowsWarm', emissive: 'windowsWarmEmissive', repeat: [3, 6], intensity: 0.82 },
    { map: 'windowsSlim', emissive: 'windowsSlimEmissive', repeat: [4, 9], intensity: 0.88 },
  ];

  // Pick the cells first so the three instanced meshes get exact counts.
  const buckets = [[], [], []];
  const downtown = [
    { x: samples.centreX + 520, z: samples.centreZ - 430, r: 520 },
    { x: samples.centreX - 610, z: samples.centreZ + 250, r: 460 },
    { x: samples.centreX + 90, z: samples.centreZ + 690, r: 420 },
  ];
  let placed = 0;
  for (let attempt = 0; attempt < 26000 && placed < BUILDING_TARGET; attempt++) {
    const x = samples.centreX + (rand() * 2 - 1) * CITY_RADIUS;
    const z = samples.centreZ + (rand() * 2 - 1) * CITY_RADIUS;
    const ci = cellIndex(occ, x, z);
    if (ci < 0 || occ.blocked[ci] || occ.used[ci]) continue;
    const r = Math.hypot(x - samples.centreX, z - samples.centreZ);
    if (r > CITY_RADIUS) continue;
    if (rand() > 1 - 0.55 * smoothstep(300, CITY_RADIUS, r)) continue;
    occ.used[ci] = 1;

    // Cell centre plus a small jitter, footprint kept inside its own cell.
    const gx = ci % occ.nx;
    const gz = (ci - gx) / occ.nx;
    const px = occ.minX + (gx + 0.5) * CELL + (rand() * 2 - 1) * 8;
    const pz = occ.minZ + (gz + 0.5) * CELL + (rand() * 2 - 1) * 8;

    let boost = 0;
    for (let d = 0; d < downtown.length; d++) {
      const dd = Math.hypot(px - downtown[d].x, pz - downtown[d].z);
      boost = Math.max(boost, 1 - smoothstep(0, downtown[d].r, dd));
    }
    const profile = rand() < 0.44 ? 0 : (rand() < 0.62 ? 1 : 2);
    const w = 12 + rand() * 14;
    const d2 = w * (0.72 + rand() * 0.5);
    const h = (34 + rand() * 96) * (1 + boost * 1.35);
    buckets[profile].push(px, pz, w, d2, h, Math.floor(rand() * 24) * (Math.PI / 12), rand());
    placed++;
  }

  const tint = new THREE.Color();
  const mat4 = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const pos = new THREE.Vector3();
  const scale = new THREE.Vector3();
  const axis = new THREE.Vector3(0, 1, 0);

  for (let p = 0; p < profiles.length; p++) {
    const data = buckets[p];
    const count = data.length / 7;
    const facade = facades[p];
    const rx = facade.repeat[0];
    const ry = facade.repeat[1];
    // Each variant falls back to the original facade pair, so a profile keeps
    // a sane look even before textures.js grows its new maps.
    const map = repeatMap(textures, texState, facade.map, 'windows', rx, ry);
    const emissiveMap = repeatMap(
      textures, texState, facade.emissive, 'windowsEmissive', rx, ry,
    );

    const material = new THREE.MeshStandardMaterial({
      color: 0x0a0c14,
      map,
      emissive: 0xffffff,
      emissiveMap,
      emissiveIntensity: facade.intensity,
      roughness: 0.82,
      metalness: 0.12,
      // Do NOT set vertexColors here. The r169 fragment prefix already defines
      // USE_COLOR from instancingColor, so setColorAt works as is; turning
      // vertexColors on would also declare a `color` attribute in the vertex
      // shader that these merged geometries do not have, and the unbound
      // attribute reads (0,0,0) and blacks the whole city out.
    });
    tintEmissiveByInstanceColor(material);
    materials.push(material);

    const mesh = new THREE.InstancedMesh(profiles[p], material, Math.max(1, count));
    mesh.count = count;
    for (let i = 0; i < count; i++) {
      const o = i * 7;
      pos.set(data[o], groundY, data[o + 1]);
      scale.set(data[o + 2], data[o + 4], data[o + 3]);
      quat.setFromAxisAngle(axis, data[o + 5]);
      mat4.compose(pos, quat, scale);
      mesh.setMatrixAt(i, mat4);
      const t = data[o + 6];
      const hex = NEON_TINTS[Math.floor(t * NEON_TINTS.length) % NEON_TINTS.length];
      tint.setHex(hex).lerp(_tintWhite, TINT_DESATURATION).multiplyScalar(0.34 + t * 0.30);
      mesh.setColorAt(i, tint);
    }
    if (count === 0) mesh.setColorAt(0, tint.setRGB(1, 1, 1));
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
    group.add(mesh);
    meshes.push(mesh);
  }

  const rooftops = buildRooftops(group, textures, texState, buckets, groundY);
  const signs = buildFacadeSigns(group, textures, samples, buckets, groundY);

  return { meshes, materials, geometries: profiles, rooftops, signs };
}

function buildSignatures(group, textures, texState, occ, samples, rand, groundY) {
  const geometry = makeSignatureGeometry();
  // Landmarks are 320 m plus, so they need a much finer window pitch than the
  // ordinary blocks or the facade reads as a grid of hangar doors.
  const material = new THREE.MeshStandardMaterial({
    color: 0x0b0e18,
    map: repeatMap(textures, texState, 'windowsSlim', 'windows', 5, 14),
    emissive: 0xffffff,
    emissiveMap: repeatMap(textures, texState, 'windowsSlimEmissive', 'windowsEmissive', 5, 14),
    emissiveIntensity: 1.15,
    roughness: 0.7,
    metalness: 0.25,
  });
  tintEmissiveByInstanceColor(material);

  const mesh = new THREE.InstancedMesh(geometry, material, SIGNATURE_TOWERS);
  const beaconGeom = new THREE.OctahedronGeometry(3.2, 0);
  const beaconMaterial = new THREE.MeshBasicMaterial({ color: 0xff5a4a, fog: false });
  beaconMaterial.color.multiplyScalar(4.5); // above 1 so the bloom catches it
  const beacons = new THREE.InstancedMesh(
    beaconGeom, beaconMaterial, SIGNATURE_TOWERS * BEACONS_PER_TOWER,
  );
  beacons.frustumCulled = false;

  const beaconHome = new Float32Array(SIGNATURE_TOWERS * BEACONS_PER_TOWER * 3);
  const beaconPhase = new Float32Array(SIGNATURE_TOWERS * BEACONS_PER_TOWER * 2);

  const mat4 = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const pos = new THREE.Vector3();
  const scale = new THREE.Vector3();
  const axis = new THREE.Vector3(0, 1, 0);
  const tint = new THREE.Color();

  let placed = 0;
  for (let attempt = 0; attempt < 4000 && placed < SIGNATURE_TOWERS; attempt++) {
    const ang = rand() * Math.PI * 2;
    const rad = 300 + rand() * (CITY_RADIUS - 260);
    const x = samples.centreX + Math.cos(ang) * rad;
    const z = samples.centreZ + Math.sin(ang) * rad;

    // Reserve a 3 x 3 block of cells so no small building grows inside a tower.
    let clear = true;
    for (let dz = -1; dz <= 1 && clear; dz++) {
      for (let dx = -1; dx <= 1; dx++) {
        const ci = cellIndex(occ, x + dx * CELL, z + dz * CELL);
        if (ci < 0 || occ.blocked[ci] || occ.used[ci]) { clear = false; break; }
      }
    }
    if (!clear) continue;
    if (!isFarFromTrack(samples, x, z, CLEARANCE + 55, 0, 0)) continue;
    for (let dz = -1; dz <= 1; dz++) {
      for (let dx = -1; dx <= 1; dx++) {
        const ci = cellIndex(occ, x + dx * CELL, z + dz * CELL);
        if (ci >= 0) occ.used[ci] = 1;
      }
    }

    const w = 46 + rand() * 26;
    const h = 320 + rand() * 170;
    pos.set(x, groundY, z);
    scale.set(w, h, w);
    quat.setFromAxisAngle(axis, rand() * Math.PI);
    mat4.compose(pos, quat, scale);
    mesh.setMatrixAt(placed, mat4);
    tint.setHex(NEON_TINTS[placed % NEON_TINTS.length]);
    tint.lerp(_tintWhite, TINT_DESATURATION).multiplyScalar(0.42 + rand() * 0.3);
    mesh.setColorAt(placed, tint);

    for (let b = 0; b < BEACONS_PER_TOWER; b++) {
      const k = placed * BEACONS_PER_TOWER + b;
      beaconHome[k * 3] = x;
      beaconHome[k * 3 + 1] = groundY + h * (b === 0 ? 1.1 : 0.79);
      beaconHome[k * 3 + 2] = z;
      beaconPhase[k * 2] = rand() * Math.PI * 2;
      beaconPhase[k * 2 + 1] = 0.75 + rand() * 0.9; // blink rate
    }
    placed++;
  }

  mesh.count = placed;
  beacons.count = placed * BEACONS_PER_TOWER;
  if (placed === 0) mesh.setColorAt(0, tint.setRGB(1, 1, 1));
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  mesh.computeBoundingSphere();
  group.add(mesh);
  group.add(beacons);

  return {
    mesh, material, geometry,
    beacons, beaconGeom, beaconMaterial, beaconHome, beaconPhase,
  };
}

/**
 * City ground. One static textured plane centred on the circuit: a top down
 * block plan whose avenues carry their own lit streets, which replaces both
 * the flat black plate and the old additive neon grid. It is static rather
 * than camera locked so the street pattern never swims under the buildings,
 * and it is wide enough that its edge is always deep inside the fog.
 */
function buildGround(group, textures, texState, samples, groundY) {
  const repeat = CITY_GROUND_SIZE / CITY_GROUND_TILE;
  const geometry = new THREE.PlaneGeometry(CITY_GROUND_SIZE, CITY_GROUND_SIZE, 1, 1);
  geometry.rotateX(-Math.PI * 0.5);
  const material = new THREE.MeshStandardMaterial({
    color: PALETTE.ground,
    map: repeatMap(textures, texState, 'cityGround', null, repeat, repeat),
    emissive: 0xffffff,
    emissiveMap: repeatMap(textures, texState, 'cityGroundEmissive', null, repeat, repeat),
    // Street lighting seen at a grazing angle: the mip chain already averages
    // most of it away, so this is the knob to turn if the plain reads too hot.
    emissiveIntensity: 0.6,
    roughness: 0.95,
    metalness: 0,
  });
  // Linear albedo, tuned against the hemisphere plus directional pair: the
  // brightest texel of the plan lands near 0.056 linear, about 70 out of 255,
  // and the average block sits far below that. Without a map, fall back to the
  // old flat plate colour rather than to this grey.
  if (material.map) material.color.setRGB(0.095, 0.100, 0.130);
  else material.color.setHex(PALETTE.ground);
  const plate = new THREE.Mesh(geometry, material);
  plate.position.set(samples.centreX, groundY - 0.6, samples.centreZ);
  plate.frustumCulled = false;
  group.add(plate);

  return { plate, geometry, material };
}

/**
 * Two or three very large horizontal planes drifting above the circuit. They
 * all share one texture: the plane size sets the apparent cloud scale, so no
 * clone is needed and each layer still reads at its own size.
 */
function buildClouds(group, textures, texState, samples) {
  const map = repeatMap(textures, texState, 'clouds', null, CLOUD_REPEAT, CLOUD_REPEAT);
  if (!map) return null;

  const layers = [];
  const geometries = [];
  const materials = [];
  const color = new THREE.Color();
  // Linear values on purpose: the deck must stay a dark veil lit from below by
  // the city, never a grey haze sitting on top of the track.
  color.setRGB(0.030, 0.024, 0.045);

  for (let i = 0; i < CLOUD_LAYERS.length; i++) {
    const spec = CLOUD_LAYERS[i];
    const geometry = new THREE.PlaneGeometry(spec[0], spec[0], 1, 1);
    geometry.rotateX(-Math.PI * 0.5);
    const material = new THREE.MeshBasicMaterial({
      map,
      color,
      transparent: true,
      opacity: spec[2],
      side: THREE.DoubleSide,
      depthWrite: false,
      fog: true,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.y = samples.maxY + spec[1];
    mesh.frustumCulled = false;
    mesh.renderOrder = -2;
    group.add(mesh);
    layers.push({ mesh, tile: spec[0] / CLOUD_REPEAT, driftX: spec[3], driftZ: spec[4] });
    geometries.push(geometry);
    materials.push(material);
  }
  return { layers, geometries, materials };
}

/**
 * Moon plus a soft halo, held at a constant direction from the camera so it
 * behaves like a body at infinity while the craft moves. Depth tested, so the
 * skyline can cut across it.
 */
function buildMoon(group, textures) {
  const map = texOr(textures, 'moon', null);
  if (!map) return null;

  const root = new THREE.Group();
  root.position.copy(MOON_DIR).multiplyScalar(MOON_DISTANCE);
  root.lookAt(0, 0, 0); // fixed direction, so this orientation never changes
  root.renderOrder = -3;

  const geometries = [];
  const materials = [];

  const haloMap = texOr(textures, 'flare', 'spark');
  if (haloMap) {
    const haloGeom = new THREE.PlaneGeometry(MOON_SIZE * MOON_HALO_SCALE, MOON_SIZE * MOON_HALO_SCALE);
    const haloMat = new THREE.MeshBasicMaterial({
      map: haloMap,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      fog: false,
    });
    haloMat.color.setRGB(0.018, 0.021, 0.030);
    const halo = new THREE.Mesh(haloGeom, haloMat);
    halo.renderOrder = -3;
    root.add(halo);
    geometries.push(haloGeom);
    materials.push(haloMat);
  }

  const discGeom = new THREE.PlaneGeometry(MOON_SIZE, MOON_SIZE);
  const discMat = new THREE.MeshBasicMaterial({
    map,
    transparent: true,
    depthWrite: false,
    fog: false,
  });
  // The single brightest background element, and still under 90 out of 255
  // once post.js has run its ACES pass.
  discMat.color.setRGB(0.085, 0.088, 0.100);
  const disc = new THREE.Mesh(discGeom, discMat);
  disc.position.z = 1; // in front of the halo, both face the camera
  disc.renderOrder = -2;
  root.add(disc);
  geometries.push(discGeom);
  materials.push(discMat);

  group.add(root);
  return { root, geometries, materials };
}

/**
 * Horizon light dome: the city glow the skyline stands against. Sits beyond
 * the mesas and inside the star radius, alpha blended over the sky, back side
 * only, no fog of its own since it IS the far distance.
 */
function buildHorizonDome(group, textures, groundY) {
  const map = texOr(textures, 'skyGlow', null);
  if (!map) return null;

  map.wrapS = THREE.RepeatWrapping;
  map.wrapT = THREE.ClampToEdgeWrapping;
  map.repeat.set(2, 1);
  map.needsUpdate = true;

  const geometry = new THREE.CylinderGeometry(
    DOME_RADIUS, DOME_RADIUS, DOME_HEIGHT, 48, 1, true,
  );
  const material = new THREE.MeshBasicMaterial({
    map,
    transparent: true,
    opacity: 0.9,
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
  });
  // Warm violet at the base, tuned to peak around 80 out of 255 in the final
  // image. Raising this is the fastest way to wash the whole race out.
  material.color.setRGB(0.075, 0.055, 0.095);

  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.y = groundY - DOME_DROP + DOME_HEIGHT * 0.5;
  mesh.frustumCulled = false;
  mesh.renderOrder = -4;
  group.add(mesh);
  return { mesh, geometry, material };
}

function buildMesas(group, textures, texState, samples, rand, groundY) {
  const geometry = new THREE.ConeGeometry(1, 1, 6, 1, false);
  geometry.translate(0, 0.5, 0);
  const rockMap = repeatMap(textures, texState, 'rock', null, 3, 2);
  const rockNormal = repeatMap(textures, texState, 'rockNormal', null, 3, 2);
  const material = new THREE.MeshStandardMaterial({
    color: PALETTE.rock,
    map: rockMap,
    normalMap: rockNormal,
    emissive: 0x0a1030,
    emissiveIntensity: 0.55,
    roughness: 1,
    metalness: 0,
    // Flat shading keeps the hard mesa silhouette; the normal map only adds
    // the strata inside each facet (three derives the TBN from the uv).
    flatShading: true,
  });
  // PALETTE.rock is a base colour meant to be used alone; multiplied by a map
  // it would sink to black, so the hue is kept and the level lifted.
  if (rockMap) material.color.setRGB(0.075, 0.068, 0.155);
  if (rockNormal) material.normalScale.set(1.1, 1.1);
  const mesh = new THREE.InstancedMesh(geometry, material, MESA_COUNT);
  mesh.frustumCulled = false;

  const mat4 = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const pos = new THREE.Vector3();
  const scale = new THREE.Vector3();
  const axis = new THREE.Vector3(0, 1, 0);

  let placed = 0;
  for (let attempt = 0; attempt < 3000 && placed < MESA_COUNT; attempt++) {
    const ang = rand() * Math.PI * 2;
    // Everything sits beyond the city so a mesa never swallows a skyscraper.
    const near = rand() < 0.3;
    const rad = near ? CITY_RADIUS + 150 + rand() * 450 : 1950 + rand() * 950;
    const x = samples.centreX + Math.cos(ang) * rad;
    const z = samples.centreZ + Math.sin(ang) * rad;
    if (!isFarFromTrack(samples, x, z, CLEARANCE + 90, 0, 0)) continue;
    const w = near ? 90 + rand() * 150 : 200 + rand() * 320;
    const h = (near ? 45 + rand() * 70 : 90 + rand() * 150);
    pos.set(x, groundY - 6, z);
    scale.set(w, h, w * (0.6 + rand() * 0.7));
    quat.setFromAxisAngle(axis, rand() * Math.PI * 2);
    mat4.compose(pos, quat, scale);
    mesh.setMatrixAt(placed, mat4);
    placed++;
  }
  mesh.count = placed;
  mesh.instanceMatrix.needsUpdate = true;
  group.add(mesh);
  return { mesh, geometry, material };
}

function buildTraffic(group, samples, rand, trafficY) {
  const bodyGeom = new THREE.BoxGeometry(7, 1.4, 2.4);
  const bodyMat = new THREE.MeshStandardMaterial({
    color: 0x0c101c,
    emissive: 0x22344a,
    emissiveIntensity: 0.8,
    roughness: 0.55,
    metalness: 0.4,
  });
  const glowGeom = new THREE.BoxGeometry(9.2, 0.45, 0.9);
  const glowMat = new THREE.MeshBasicMaterial({
    fog: false,
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false,
  });
  // Above 1 so the bloom catches it, the hue itself comes from instanceColor.
  glowMat.color.setRGB(3.4, 3.4, 3.4);

  const body = new THREE.InstancedMesh(bodyGeom, bodyMat, TRAFFIC_COUNT);
  const glow = new THREE.InstancedMesh(glowGeom, glowMat, TRAFFIC_COUNT);
  body.frustumCulled = false;
  glow.frustumCulled = false;

  // path = centre x, centre z, radius, altitude, angular speed, phase, bob
  const paths = new Float32Array(TRAFFIC_COUNT * 7);
  for (let i = 0; i < TRAFFIC_COUNT; i++) {
    const o = i * 7;
    paths[o] = samples.centreX + (rand() * 2 - 1) * 420;
    paths[o + 1] = samples.centreZ + (rand() * 2 - 1) * 420;
    paths[o + 2] = 320 + rand() * 900;
    paths[o + 3] = trafficY + rand() * 190;
    paths[o + 4] = (0.035 + rand() * 0.06) * (rand() < 0.5 ? -1 : 1);
    paths[o + 5] = rand() * Math.PI * 2;
    paths[o + 6] = 4 + rand() * 9;
  }

  const tint = new THREE.Color();
  for (let i = 0; i < TRAFFIC_COUNT; i++) {
    tint.setHex(i % 3 === 0 ? PALETTE.amber : (i % 3 === 1 ? PALETTE.cyan : PALETTE.magenta));
    glow.setColorAt(i, tint);
  }
  if (glow.instanceColor) glow.instanceColor.needsUpdate = true;

  group.add(body);
  group.add(glow);
  return { body, glow, bodyGeom, bodyMat, glowGeom, glowMat, paths };
}

function buildBillboards(group, track, textures, samples, rand) {
  // Three advert panels instead of one, so the roadside is not a corridor of
  // the same hologram repeated fourteen times. One mesh per map.
  const names = ['billboard', 'hologramB', 'hologramC'];
  const banks = [];
  for (let i = 0; i < names.length; i++) {
    const map = texOr(textures, names[i], 'billboard');
    banks.push({ map, positions: [], normals: [], uvs: [], colors: [] });
  }
  const frame = track.makeFrame();
  const tint = new THREE.Color();

  const step = track.length / (BILLBOARD_TARGET * 2);
  let placed = 0;
  for (let k = 0; k < BILLBOARD_TARGET * 2 && placed < BILLBOARD_TARGET; k++) {
    const s = k * step + step * 0.5;
    track.at(s, frame);
    const side = (k % 2 === 0) ? 1 : -1;
    const off = frame.halfWidth + BILLBOARD_OFFSET;
    const rl = Math.hypot(frame.right.x, frame.right.z) || 1;
    const cx = frame.pos.x + (frame.right.x / rl) * side * off;
    const cy = frame.pos.y + 13 + rand() * 8;
    const cz = frame.pos.z + (frame.right.z / rl) * side * off;
    const idx = Math.round(s / samples.step) % samples.count;
    if (!isFarFromTrack(samples, cx, cz, CLEARANCE - 6, idx, 12)) continue;

    // Vertical panel containing the horizontal tangent.
    let tx = frame.tangent.x;
    let tz = frame.tangent.z;
    const tl = Math.hypot(tx, tz) || 1;
    tx /= tl;
    tz /= tl;
    const hw = (17 + rand() * 10);
    const hh = hw * (0.42 + rand() * 0.22);
    const flip = rand() < 0.5;
    const nx = -tz * side;
    const nz = tx * side;

    const corners = [
      [-hw, -hh], [hw, -hh], [hw, hh],
      [-hw, -hh], [hw, hh], [-hw, hh],
    ];
    const cuv = [
      [flip ? 1 : 0, 0], [flip ? 0 : 1, 0], [flip ? 0 : 1, 1],
      [flip ? 1 : 0, 0], [flip ? 0 : 1, 1], [flip ? 1 : 0, 1],
    ];
    tint.setHex(NEON_TINTS[placed % NEON_TINTS.length]).multiplyScalar(1.6);
    const bank = banks[placed % banks.length];
    for (let c = 0; c < 6; c++) {
      bank.positions.push(cx + tx * corners[c][0], cy + corners[c][1], cz + tz * corners[c][0]);
      bank.normals.push(nx, 0, nz);
      bank.uvs.push(cuv[c][0], cuv[c][1]);
      bank.colors.push(tint.r, tint.g, tint.b);
    }
    placed++;
  }

  const meshes = [];
  const geometries = [];
  const materials = [];
  for (let i = 0; i < banks.length; i++) {
    const bank = banks[i];
    if (bank.positions.length === 0) continue;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(bank.positions), 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(bank.normals), 3));
    geometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(bank.uvs), 2));
    geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(bank.colors), 3));
    geometry.computeBoundingSphere();

    const material = new THREE.MeshBasicMaterial({
      map: bank.map,
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      fog: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.renderOrder = -1;
    group.add(mesh);
    meshes.push(mesh);
    geometries.push(geometry);
    materials.push(material);
  }
  return { meshes, geometries, materials, count: placed };
}

function buildStars(group, textures, rand) {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(STAR_COUNT * 3);
  const colors = new Float32Array(STAR_COUNT * 3);
  const tint = new THREE.Color();
  for (let i = 0; i < STAR_COUNT; i++) {
    // Cosine weighted toward the upper hemisphere, nothing below the horizon.
    const u = rand() * 2 - 1;
    const phi = rand() * Math.PI * 2;
    const y = Math.abs(u) * 0.92 + 0.06;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    positions[i * 3] = Math.cos(phi) * r * STAR_RADIUS;
    positions[i * 3 + 1] = y * STAR_RADIUS;
    positions[i * 3 + 2] = Math.sin(phi) * r * STAR_RADIUS;
    const warm = rand();
    tint.setRGB(0.72 + warm * 0.28, 0.78 + warm * 0.16, 1.0);
    const b = 0.35 + Math.pow(rand(), 2.2) * 1.5;
    colors[i * 3] = tint.r * b;
    colors[i * 3 + 1] = tint.g * b;
    colors[i * 3 + 2] = tint.b * b;
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.computeBoundingSphere();

  const material = new THREE.PointsMaterial({
    map: tex(textures, 'spark'),
    size: 3.0,
    sizeAttenuation: false,
    vertexColors: true,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    fog: false,
  });
  const points = new THREE.Points(geometry, material);
  points.frustumCulled = false;
  points.renderOrder = -3;
  group.add(points);
  return { points, geometry, material };
}

// ---------------------------------------------------------------------------
// Per frame work (allocation free)
// ---------------------------------------------------------------------------

function updateShadow(world, cx, cy, cz) {
  const texel = SHADOW_SPAN / SHADOW_MAP_SIZE;
  const a = Math.round(
    (cx * LIGHT_AXIS_X.x + cy * LIGHT_AXIS_X.y + cz * LIGHT_AXIS_X.z) / texel,
  ) * texel;
  const b = Math.round(
    (cx * LIGHT_AXIS_Y.x + cy * LIGHT_AXIS_Y.y + cz * LIGHT_AXIS_Y.z) / texel,
  ) * texel;
  const c = cx * LIGHT_AXIS_Z.x + cy * LIGHT_AXIS_Z.y + cz * LIGHT_AXIS_Z.z;
  _shadowVec.set(
    LIGHT_AXIS_X.x * a + LIGHT_AXIS_Y.x * b + LIGHT_AXIS_Z.x * c,
    LIGHT_AXIS_X.y * a + LIGHT_AXIS_Y.y * b + LIGHT_AXIS_Z.y * c,
    LIGHT_AXIS_X.z * a + LIGHT_AXIS_Y.z * b + LIGHT_AXIS_Z.z * c,
  );
  world.sun.target.position.copy(_shadowVec);
  world.sun.position.copy(_shadowVec).add(LIGHT_OFFSET);
}

function updatePointLights(world, cx, cy, cz) {
  const spots = world._spots;
  const n = world._spotCount;
  for (let k = 0; k < POINT_LIGHT_COUNT; k++) {
    _pickIdx[k] = -1;
    _pickDist[k] = Infinity;
  }
  for (let i = 0; i < n; i++) {
    const dx = spots[i * 3] - cx;
    const dy = spots[i * 3 + 1] - cy;
    const dz = spots[i * 3 + 2] - cz;
    const d2 = dx * dx + dy * dy + dz * dz;
    for (let k = 0; k < POINT_LIGHT_COUNT; k++) {
      if (d2 < _pickDist[k]) {
        for (let j = POINT_LIGHT_COUNT - 1; j > k; j--) {
          _pickDist[j] = _pickDist[j - 1];
          _pickIdx[j] = _pickIdx[j - 1];
        }
        _pickDist[k] = d2;
        _pickIdx[k] = i;
        break;
      }
    }
  }
  for (let k = 0; k < POINT_LIGHT_COUNT; k++) {
    const light = world.pointLights[k];
    const i = _pickIdx[k];
    if (i < 0) {
      light.intensity = 0;
      continue;
    }
    light.position.set(spots[i * 3], spots[i * 3 + 1], spots[i * 3 + 2]);
    light.color.copy(world._spotColors[i]);
    const fade = 1 - Math.min(1, Math.sqrt(_pickDist[k]) / POINT_LIGHT_RANGE);
    light.intensity = POINT_LIGHT_INTENSITY * fade * fade;
  }
}

function updateTraffic(world, t) {
  const traffic = world._traffic;
  const paths = traffic.paths;
  for (let i = 0; i < TRAFFIC_COUNT; i++) {
    const o = i * 7;
    const w = paths[o + 4];
    const ang = paths[o + 5] + t * w;
    const rad = paths[o + 2];
    const x = paths[o] + Math.cos(ang) * rad;
    const z = paths[o + 1] + Math.sin(ang) * rad;
    const y = paths[o + 3] + Math.sin(t * 0.31 + paths[o + 5]) * paths[o + 6];
    const dir = w >= 0 ? -1 : 1;
    const heading = dir * (ang + Math.PI * 0.5);
    _trafficPos.set(x, y, z);
    _trafficQuat.setFromAxisAngle(_trafficAxisY, heading);
    _trafficRoll.setFromAxisAngle(_trafficAxisX, dir * 0.24 + Math.sin(t * 0.7 + i) * 0.05);
    _trafficQuat.multiply(_trafficRoll);
    _trafficMat.compose(_trafficPos, _trafficQuat, _trafficScale);
    traffic.body.setMatrixAt(i, _trafficMat);
    traffic.glow.setMatrixAt(i, _trafficMat);
  }
  traffic.body.instanceMatrix.needsUpdate = true;
  traffic.glow.instanceMatrix.needsUpdate = true;
}

function updateBeacons(world, t) {
  const sig = world._signatures;
  const n = sig.beacons.count;
  for (let i = 0; i < n; i++) {
    const phase = sig.beaconPhase[i * 2];
    const rate = sig.beaconPhase[i * 2 + 1];
    // Sharp on / soft off, like a real aircraft warning light.
    const cycle = Math.sin(t * rate + phase);
    const s = 0.22 + Math.pow(Math.max(0, cycle), 6) * 1.35;
    _beaconMat.makeScale(s, s, s);
    _beaconMat.setPosition(
      sig.beaconHome[i * 3], sig.beaconHome[i * 3 + 1], sig.beaconHome[i * 3 + 2],
    );
    sig.beacons.setMatrixAt(i, _beaconMat);
  }
  if (n > 0) sig.beacons.instanceMatrix.needsUpdate = true;
}

// ---------------------------------------------------------------------------
// Public factory
// ---------------------------------------------------------------------------

/**
 * Build the whole environment and attach it to the scene.
 *
 * @param {THREE.Scene} scene
 * @param {object} track   the Track produced by track.js
 * @param {object} textures the Textures produced by textures.js
 * @param {THREE.WebGLRenderer} [renderer] optional, only used to bake the PMREM
 *        environment explicitly. Without it three bakes the very same PMREM
 *        internally the first time the environment map is sampled.
 */
export function createWorld(scene, track, textures, renderer) {
  const group = new THREE.Group();
  group.name = 'world';

  const rand = mulberry32(0x5eed1234);
  const texState = makeTexState();
  const samples = buildTrackSamples(track);
  const occ = buildOccupancy(samples, CITY_RADIUS + 220);
  const groundY = samples.minY - GROUND_DROP;
  const trafficY = samples.maxY + 130;

  // Thinner fog than the original 0.0016, which erased the whole mid distance,
  // plus a hue pushed toward the horizon glow so the far towers separate from
  // the sky instead of dissolving into it. This is a hue shift at roughly
  // constant luminance: pushing it any brighter is what greys the race out.
  const fogColor = new THREE.Color(PALETTE.fog)
    .lerp(new THREE.Color(PALETTE.haze), 0.3)
    .lerp(new THREE.Color(PALETTE.streetLight), 0.02);
  scene.fog = new THREE.FogExp2(PALETTE.fog, FOG_DENSITY);
  scene.fog.color.copy(fogColor); // copied, not re-hexed, to stay in linear space
  const envTarget = buildSky(scene, textures, renderer);

  const lights = buildLights(group);
  const spots = buildPointLightSpots(track, samples, rand);
  const city = buildCity(group, textures, texState, occ, samples, rand, groundY);
  const signatures = buildSignatures(group, textures, texState, occ, samples, rand, groundY);
  const ground = buildGround(group, textures, texState, samples, groundY);
  const mesas = buildMesas(group, textures, texState, samples, rand, groundY);
  const traffic = buildTraffic(group, samples, rand, trafficY);
  const billboards = buildBillboards(group, track, textures, samples, rand);
  const clouds = buildClouds(group, textures, texState, samples);
  const moon = buildMoon(group, textures);
  const dome = buildHorizonDome(group, textures, groundY);
  const stars = buildStars(group, textures, rand);

  if (renderer && renderer.isWebGLRenderer) {
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  }

  scene.add(group);

  const world = {
    group,
    scene,
    sun: lights.sun,
    hemi: lights.hemi,
    pointLights: lights.points,
    groundY,
    buildingCount: city.meshes.reduce((n, m) => n + m.count, 0),
    // internals used by update()
    _spots: spots.spots,
    _spotColors: spots.colors,
    _spotCount: spots.count,
    _city: city,
    _signatures: signatures,
    _ground: ground,
    _mesas: mesas,
    _traffic: traffic,
    _billboards: billboards,
    _clouds: clouds,
    _moon: moon,
    _dome: dome,
    _stars: stars,
    _envTarget: envTarget,
    _ownedTextures: texState.owned,
    _time: 0,
    _lightTimer: 0,
    update: null,
    dispose: null,
  };

  // Seed the frame dependent parts so the very first rendered frame is correct.
  _camFallback.set(samples.centreX, samples.maxY + 20, samples.centreZ);
  updateShadow(world, _camFallback.x, _camFallback.y, _camFallback.z);
  updatePointLights(world, _camFallback.x, _camFallback.y, _camFallback.z);
  updateTraffic(world, 0);
  updateBeacons(world, 0);

  /**
   * @param {number} dt seconds
   * @param {THREE.Vector3} cameraPos world position of the active camera
   * @param {number} playerSpeed01 player speed, normalised to [0, 1]
   */
  world.update = function update(dt, cameraPos, playerSpeed01) {
    const step = dt > 0 ? (dt > 0.1 ? 0.1 : dt) : 0;
    world._time += step;
    const t = world._time;
    if (cameraPos) _camFallback.copy(cameraPos);
    const cx = _camFallback.x;
    const cy = _camFallback.y;
    const cz = _camFallback.z;
    const speed01 = playerSpeed01 > 0 ? (playerSpeed01 < 1 ? playerSpeed01 : 1) : 0;

    updateTraffic(world, t);
    updateBeacons(world, t);
    updateShadow(world, cx, cy, cz);

    world._lightTimer -= step;
    if (world._lightTimer <= 0) {
      world._lightTimer = LIGHT_PICK_INTERVAL;
      updatePointLights(world, cx, cy, cz);
    }

    // Infinite elements follow the camera. The star dome and the horizon dome
    // simply translate; each cloud layer translates too, plus a drift wrapped
    // on its own tile size so the pattern lands identically and never swims.
    stars.points.position.set(cx, cy, cz);
    if (dome) {
      dome.mesh.position.x = cx;
      dome.mesh.position.z = cz;
    }
    if (moon) {
      moon.root.position.set(
        cx + MOON_OFFSET.x, cy + MOON_OFFSET.y, cz + MOON_OFFSET.z,
      );
    }
    if (clouds) {
      for (let i = 0; i < clouds.layers.length; i++) {
        const layer = clouds.layers[i];
        const tile = layer.tile;
        layer.mesh.position.x = cx + ((t * layer.driftX) % tile);
        layer.mesh.position.z = cz + ((t * layer.driftZ) % tile);
      }
    }

    // The holograms flicker, and the panels dim slightly at speed so the
    // roadside furniture never fights the track for attention.
    const flicker = 0.86 + Math.sin(t * 6.1) * 0.05 + Math.sin(t * 13.7) * 0.03;
    const glitch = (t * 0.41) % 1 < 0.025 ? 0.35 : 1;
    const panel = flicker * glitch * (1 - speed01 * 0.12);
    for (let i = 0; i < billboards.materials.length; i++) {
      billboards.materials[i].opacity = panel;
    }
  };

  world.dispose = function dispose() {
    scene.remove(group);
    if (scene.background === tex(textures, 'sky')) scene.background = null;
    if (envTarget) {
      scene.environment = null;
      envTarget.dispose();
    } else if (scene.environment === tex(textures, 'sky')) {
      scene.environment = null;
    }
    scene.fog = null;

    const geometries = [];
    const materials = [];
    group.traverse((obj) => {
      if (obj.geometry) geometries.push(obj.geometry);
      if (obj.material) materials.push(obj.material);
      if (obj.isInstancedMesh) obj.dispose();
    });
    for (let i = 0; i < geometries.length; i++) geometries[i].dispose();
    for (let i = 0; i < materials.length; i++) materials[i].dispose();
    // Every mesh added above lives under group, so the traversal covers the
    // rooftops, the signs, the clouds, the moon and the dome as well. Only the
    // texture clones this module made are left, and they are owned here.
    for (let i = 0; i < texState.owned.length; i++) texState.owned[i].dispose();
    texState.owned.length = 0;
    texState.cache.clear();
    texState.claimed.clear();
    group.clear();
  };

  // One dry run so the camera locked elements (dome, moon, clouds) are already
  // in place on the very first rendered frame. dt = 0 advances nothing.
  world.update(0, _camFallback, 0);

  return world;
}
