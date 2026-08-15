/**
 * Procedural vehicle bodies.
 *
 * Each class is described as a set of cross-sections ("stations") along the length of the
 * car, which are lofted into a hull. That gives tapered noses, kicked-up rear haunches and
 * a proper greenhouse - shapes a stack of boxes cannot produce - while staying fully
 * procedural and cheap.
 *
 * Geometry is built once per class and cached; only the paint material differs per car,
 * so a hundred cars cost a handful of pipelines.
 */

import {
  Group, Mesh, CylinderGeometry, TorusGeometry, BoxGeometry, MeshStandardMaterial,
  MeshPhysicalMaterial, Color, Vector3,
} from 'three/webgpu';
import { GeometryBuilder } from '../world/GeometryBuilder.js';
import { makeCarPaint, getCarGlass } from '../render/Materials.js';

/**
 * Station: `z` along the car (negative = rear), `hw` half-width, `y0` sill, `y1` shoulder.
 * Cabin: `z0`/`z1` extent, `hw` half-width, `y` roof height, `taper` roof inset.
 */
export const VEHICLE_CLASSES = {
  sedan: {
    label: 'Sedan',
    mass: 1350,
    wheelRadius: 0.33,
    wheelWidth: 0.24,
    track: 0.9,
    wheelbase: 1.32,
    chassis: { hx: 0.88, hy: 0.42, hz: 2.2 },
    topSpeed: 54,
    power: 4200,
    body: [
      { z: -2.20, hw: 0.72, y0: 0.34, y1: 0.86 },
      { z: -1.80, hw: 0.88, y0: 0.26, y1: 0.94 },
      { z: -0.70, hw: 0.92, y0: 0.22, y1: 0.96 },
      { z: 0.60, hw: 0.92, y0: 0.22, y1: 0.94 },
      { z: 1.70, hw: 0.86, y0: 0.26, y1: 0.84 },
      { z: 2.18, hw: 0.70, y0: 0.34, y1: 0.74 },
    ],
    cabin: { z0: -1.45, z1: 0.85, hw: 0.80, y: 1.46, taperFront: 0.42, taperRear: 0.30 },
  },
  coupe: {
    label: 'Coupe',
    mass: 1180,
    wheelRadius: 0.34,
    wheelWidth: 0.28,
    track: 0.92,
    wheelbase: 1.28,
    chassis: { hx: 0.92, hy: 0.36, hz: 2.1 },
    topSpeed: 68,
    power: 6200,
    body: [
      { z: -2.05, hw: 0.78, y0: 0.28, y1: 0.78 },
      { z: -1.60, hw: 0.94, y0: 0.20, y1: 0.84 },
      { z: -0.40, hw: 0.96, y0: 0.17, y1: 0.84 },
      { z: 0.80, hw: 0.94, y0: 0.17, y1: 0.80 },
      { z: 1.75, hw: 0.86, y0: 0.20, y1: 0.68 },
      { z: 2.10, hw: 0.66, y0: 0.26, y1: 0.60 },
    ],
    cabin: { z0: -1.25, z1: 0.55, hw: 0.80, y: 1.24, taperFront: 0.62, taperRear: 0.34 },
  },
  suv: {
    label: 'SUV',
    mass: 1950,
    wheelRadius: 0.40,
    wheelWidth: 0.30,
    track: 0.93,
    wheelbase: 1.42,
    chassis: { hx: 0.95, hy: 0.52, hz: 2.35 },
    topSpeed: 48,
    power: 4800,
    body: [
      { z: -2.35, hw: 0.80, y0: 0.42, y1: 1.12 },
      { z: -1.90, hw: 0.95, y0: 0.34, y1: 1.18 },
      { z: -0.60, hw: 0.98, y0: 0.30, y1: 1.20 },
      { z: 0.90, hw: 0.98, y0: 0.30, y1: 1.18 },
      { z: 1.95, hw: 0.92, y0: 0.34, y1: 1.10 },
      { z: 2.35, hw: 0.78, y0: 0.42, y1: 1.00 },
    ],
    cabin: { z0: -1.85, z1: 1.05, hw: 0.88, y: 1.86, taperFront: 0.30, taperRear: 0.14 },
  },
  van: {
    label: 'Van',
    mass: 2300,
    wheelRadius: 0.38,
    wheelWidth: 0.26,
    track: 0.99,
    wheelbase: 1.55,
    chassis: { hx: 1.0, hy: 0.62, hz: 2.6 },
    topSpeed: 42,
    power: 4200,
    body: [
      { z: -2.60, hw: 0.92, y0: 0.40, y1: 1.90 },
      { z: -2.10, hw: 1.00, y0: 0.34, y1: 2.00 },
      { z: 0.90, hw: 1.02, y0: 0.30, y1: 2.00 },
      { z: 1.90, hw: 0.98, y0: 0.32, y1: 1.60 },
      { z: 2.45, hw: 0.84, y0: 0.40, y1: 1.15 },
      { z: 2.60, hw: 0.72, y0: 0.46, y1: 1.05 },
    ],
    cabin: null,
    vanGlass: { z0: 1.55, z1: 2.5, y0: 1.15, y1: 1.72 },
  },
  pickup: {
    label: 'Pickup',
    mass: 2050,
    wheelRadius: 0.42,
    wheelWidth: 0.30,
    track: 0.95,
    wheelbase: 1.60,
    chassis: { hx: 0.98, hy: 0.50, hz: 2.7 },
    topSpeed: 46,
    power: 5000,
    body: [
      { z: -2.70, hw: 0.92, y0: 0.44, y1: 1.16 },
      { z: -2.20, hw: 1.00, y0: 0.38, y1: 1.20 },
      { z: -0.20, hw: 1.00, y0: 0.34, y1: 1.20 },
      { z: 0.30, hw: 0.98, y0: 0.34, y1: 1.14 },
      { z: 2.05, hw: 0.94, y0: 0.36, y1: 1.10 },
      { z: 2.60, hw: 0.80, y0: 0.44, y1: 1.02 },
    ],
    cabin: { z0: 0.30, z1: 1.85, hw: 0.88, y: 1.90, taperFront: 0.34, taperRear: 0.10 },
    bed: { z0: -2.55, z1: 0.10, hw: 0.98, y: 1.22 },
  },
  sports: {
    label: 'Sports',
    mass: 1080,
    wheelRadius: 0.35,
    wheelWidth: 0.32,
    track: 0.94,
    wheelbase: 1.30,
    chassis: { hx: 0.94, hy: 0.32, hz: 2.15 },
    topSpeed: 82,
    power: 8600,
    body: [
      { z: -2.15, hw: 0.82, y0: 0.24, y1: 0.72 },
      { z: -1.55, hw: 0.98, y0: 0.16, y1: 0.78 },
      { z: -0.30, hw: 1.00, y0: 0.13, y1: 0.76 },
      { z: 0.85, hw: 0.98, y0: 0.13, y1: 0.68 },
      { z: 1.80, hw: 0.88, y0: 0.16, y1: 0.56 },
      { z: 2.15, hw: 0.62, y0: 0.22, y1: 0.48 },
    ],
    cabin: { z0: -1.15, z1: 0.35, hw: 0.76, y: 1.10, taperFront: 0.70, taperRear: 0.40 },
    spoiler: true,
  },
};

/** Paint colours that read as "traffic", not "toy box". */
export const TRAFFIC_COLOURS = [
  0xb8bcc0, 0x8d9298, 0x2b3038, 0xd8d6d0, 0x5a6672, 0x1f2933,
  0x7a2f2f, 0x2f4f7a, 0x2f5f45, 0x8a7a3f, 0x6b4f7a, 0xa85f2f,
  0xc9c4b8, 0x3f4a52, 0x9a3f3f, 0x35566b,
];

const geometryCache = new Map();

/* --------------------------------------------------------------------- geometry */

/**
 * Loft the body stations into a closed hull.
 *
 * Winding matters: every quad is wound counter-clockwise as seen from *outside* the hull,
 * so back-face culling keeps the shell solid. Getting a flank backwards makes the car look
 * hollow, because you end up looking straight through it at its unlit interior.
 */
function loftBody(b, stations, tile = 1.4) {
  for (let i = 0; i < stations.length - 1; i++) {
    const a = stations[i], c = stations[i + 1];
    const v = (p) => new Vector3(p[0], p[1], p[2]);

    // Right and left flanks. Stations run rear -> front, so +Z is forward.
    for (const side of [1, -1]) {
      const n = new Vector3(side, 0.15, 0).normalize();
      const p0 = v([a.hw * side, a.y0, a.z]);   // rear sill
      const p1 = v([a.hw * side, a.y1, a.z]);   // rear shoulder
      const p2 = v([c.hw * side, c.y1, c.z]);   // front shoulder
      const p3 = v([c.hw * side, c.y0, c.z]);   // front sill
      if (side > 0) b.quad(p0, p1, p2, p3, [0, 0], [0, 1], [1, 1], [1, 0], n);
      else b.quad(p0, p3, p2, p1, [0, 0], [1, 0], [1, 1], [0, 1], n);
    }

    // Deck (bonnet / boot / lower roofline) and floor.
    const up = new Vector3(0, 1, 0);
    b.quad(
      v([-a.hw, a.y1, a.z]), v([-c.hw, c.y1, c.z]), v([c.hw, c.y1, c.z]), v([a.hw, a.y1, a.z]),
      [0, 0], [0, 1], [1, 1], [1, 0], up,
    );
    const down = new Vector3(0, -1, 0);
    b.quad(
      v([a.hw, a.y0, a.z]), v([c.hw, c.y0, c.z]), v([-c.hw, c.y0, c.z]), v([-a.hw, a.y0, a.z]),
      [0, 0], [0, 1], [1, 1], [1, 0], down,
    );
  }
  // Caps.
  const first = stations[0], last = stations[stations.length - 1];
  const V = (x, y, z) => new Vector3(x, y, z);
  b.quad(
    V(-first.hw, first.y0, first.z), V(-first.hw, first.y1, first.z),
    V(first.hw, first.y1, first.z), V(first.hw, first.y0, first.z),
    [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(0, 0, -1),
  );
  b.quad(
    V(last.hw, last.y0, last.z), V(last.hw, last.y1, last.z),
    V(-last.hw, last.y1, last.z), V(-last.hw, last.y0, last.z),
    [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(0, 0, 1),
  );
  void tile;
}

/** Greenhouse: a tapered box sitting on the body's shoulder line. */
function buildCabin(b, cabin, shoulderY) {
  const { z0, z1, hw, y, taperFront, taperRear } = cabin;
  const V = (x, yy, z) => new Vector3(x, yy, z);
  const rtHw = hw - 0.06;
  // Roof is shorter than the base: front pillar rakes back, rear pillar rakes forward.
  const rz0 = z0 + taperRear, rz1 = z1 - taperFront;

  for (const side of [1, -1]) {
    const n = new Vector3(side, 0.1, 0).normalize();
    const p0 = V(hw * side, shoulderY, z0);   // rear base of the pillar
    const p1 = V(rtHw * side, y, rz0);        // rear roof corner
    const p2 = V(rtHw * side, y, rz1);        // front roof corner
    const p3 = V(hw * side, shoulderY, z1);   // front base
    if (side > 0) b.quad(p0, p1, p2, p3, [0, 0], [0, 1], [1, 1], [1, 0], n);
    else b.quad(p0, p3, p2, p1, [0, 0], [1, 0], [1, 1], [0, 1], n);
  }
  // Roof.
  b.quad(
    V(-rtHw, y, rz0), V(-rtHw, y, rz1), V(rtHw, y, rz1), V(rtHw, y, rz0),
    [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(0, 1, 0),
  );
  // Rear screen and windscreen slabs.
  b.quad(
    V(-hw, shoulderY, z0), V(-rtHw, y, rz0), V(rtHw, y, rz0), V(hw, shoulderY, z0),
    [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(0, 0.4, -1).normalize(),
  );
  b.quad(
    V(hw, shoulderY, z1), V(rtHw, y, rz1), V(-rtHw, y, rz1), V(-hw, shoulderY, z1),
    [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(0, 0.4, 1).normalize(),
  );
}

/** Build (and cache) the geometry set for a vehicle class. */
function buildClassGeometry(className) {
  if (geometryCache.has(className)) return geometryCache.get(className);
  const spec = VEHICLE_CLASSES[className];

  const bodyB = new GeometryBuilder();
  loftBody(bodyB, spec.body);

  const glassB = new GeometryBuilder();
  const trimB = new GeometryBuilder();

  if (spec.cabin) {
    // Pillars and roof in paint; the window apertures are a slightly inset glass shell.
    buildCabin(bodyB, spec.cabin, shoulderAt(spec, spec.cabin.z0));
    const inset = { ...spec.cabin, hw: spec.cabin.hw - 0.035, y: spec.cabin.y - 0.05 };
    buildCabin(glassB, inset, shoulderAt(spec, spec.cabin.z0) + 0.08);
  }
  if (spec.vanGlass) {
    const g = spec.vanGlass;
    for (const side of [1, -1]) {
      glassB.quad(
        new Vector3(1.01 * side, g.y0, g.z0), new Vector3(1.01 * side, g.y1, g.z0),
        new Vector3(0.86 * side, g.y1, g.z1), new Vector3(0.86 * side, g.y0, g.z1),
        [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(side, 0, 0),
      );
    }
    glassB.quad(
      new Vector3(0.86, g.y0, g.z1), new Vector3(0.86, g.y1, g.z1),
      new Vector3(-0.86, g.y1, g.z1), new Vector3(-0.86, g.y0, g.z1),
      [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(0, 0.3, 1).normalize(),
    );
  }
  if (spec.bed) {
    // Pickup bed walls.
    const bd = spec.bed;
    const wall = 0.07;
    trimB.box(new Vector3(-bd.hw, bd.y - 0.5, bd.z0), new Vector3(-bd.hw + wall, bd.y, bd.z1), 1);
    trimB.box(new Vector3(bd.hw - wall, bd.y - 0.5, bd.z0), new Vector3(bd.hw, bd.y, bd.z1), 1);
    trimB.box(new Vector3(-bd.hw, bd.y - 0.5, bd.z0), new Vector3(bd.hw, bd.y, bd.z0 + wall), 1);
  }
  if (spec.spoiler) {
    const last = spec.body[0];
    trimB.box(
      new Vector3(-0.78, last.y1 + 0.18, last.z + 0.05),
      new Vector3(0.78, last.y1 + 0.26, last.z + 0.45), 1,
    );
    for (const side of [-0.6, 0.6]) {
      trimB.box(
        new Vector3(side - 0.05, last.y1, last.z + 0.12),
        new Vector3(side + 0.05, last.y1 + 0.2, last.z + 0.3), 1,
      );
    }
  }

  // Bumpers and sills in dark trim.
  const front = spec.body[spec.body.length - 1];
  const rear = spec.body[0];
  trimB.box(
    new Vector3(-front.hw * 0.98, front.y0 - 0.02, front.z - 0.08),
    new Vector3(front.hw * 0.98, front.y0 + 0.26, front.z + 0.1), 1,
  );
  trimB.box(
    new Vector3(-rear.hw * 0.98, rear.y0 - 0.02, rear.z - 0.1),
    new Vector3(rear.hw * 0.98, rear.y0 + 0.26, rear.z + 0.08), 1,
  );

  const set = {
    body: bodyB.build(),
    glass: glassB.isEmpty ? null : glassB.build(),
    trim: trimB.isEmpty ? null : trimB.build(),
    spec,
  };
  geometryCache.set(className, set);
  return set;
}

/** Interpolate the body's shoulder height at a given z. */
function shoulderAt(spec, z) {
  const s = spec.body;
  for (let i = 0; i < s.length - 1; i++) {
    if (z >= s[i].z && z <= s[i + 1].z) {
      const t = (z - s[i].z) / (s[i + 1].z - s[i].z);
      return s[i].y1 + (s[i + 1].y1 - s[i].y1) * t;
    }
  }
  return s[0].y1;
}

/* ------------------------------------------------------------ shared small parts */

const wheelCache = new Map();
const lampGeo = new BoxGeometry(0.28, 0.13, 0.06);

/**
 * Wheel geometry keyed by size. An earlier version kept a single module-level geometry
 * and rebuilt it whenever a different size was requested, which silently gave every
 * vehicle on screen the last-built wheel.
 */
function sharedWheel(radius, width) {
  const key = `${radius.toFixed(3)}_${width.toFixed(3)}`;
  if (!wheelCache.has(key)) {
    // Tyre is a cylinder of exactly the physics wheel radius, so the visual contact
    // patch matches where the raycast suspension thinks the ground is.
    const tyre = new CylinderGeometry(radius, radius, width, 18);
    tyre.rotateZ(Math.PI / 2);
    // Hubcap: narrower than the tyre but proud of it, so the face reads from the side
    // without the rim sticking out like a drum.
    const rim = new CylinderGeometry(radius * 0.64, radius * 0.64, width * 1.06, 12);
    rim.rotateZ(Math.PI / 2);
    wheelCache.set(key, { rim, tyre });
  }
  return wheelCache.get(key);
}

const trimMaterial = new MeshStandardMaterial({ color: 0x14161a, roughness: 0.62, metalness: 0.35 });
const rubberMaterial = new MeshStandardMaterial({ color: 0x0e1013, roughness: 0.92, metalness: 0.0 });
const rimMaterial = new MeshStandardMaterial({ color: 0x8d949c, roughness: 0.42, metalness: 0.8 });
const headlightMaterial = new MeshStandardMaterial({
  color: 0xfff6dd, emissive: new Color(0xfff0cc), emissiveIntensity: 0.15, roughness: 0.2,
});
const taillightMaterial = new MeshStandardMaterial({
  color: 0x8c1712, emissive: new Color(0xff2a18), emissiveIntensity: 0.25, roughness: 0.3,
});

/**
 * Build a complete vehicle Object3D.
 * @returns {{group:Group, wheels:Group[], spec:object, headlights:Mesh[], taillights:Mesh[]}}
 */
export function createVehicleMesh(className, paintColour) {
  const set = buildClassGeometry(className);
  const spec = set.spec;
  const group = new Group();
  group.name = `vehicle_${className}`;

  /*
   * Body stations are authored in *ground space*: y = 0 is the road, y = 1.46 is the
   * roof. The chassis rigid body's origin, however, sits roughly half a metre up. This
   * sub-group carries the body down so the authored shape lines up with the wheels
   * instead of hovering above them.
   */
  const restSuspension = 0.32 * 0.7;   // approximate loaded ride height
  const connectionY = spec.chassis.hy * 0.1;
  const shell = new Group();
  shell.position.y = connectionY - restSuspension - spec.wheelRadius;
  group.add(shell);
  group.userData.shell = shell;

  const body = new Mesh(set.body, makeCarPaint(paintColour));
  body.castShadow = true;
  body.receiveShadow = true;
  shell.add(body);

  if (set.trim) {
    const trim = new Mesh(set.trim, trimMaterial);
    trim.castShadow = true;
    shell.add(trim);
  }
  if (set.glass) {
    const glass = new Mesh(set.glass, getCarGlass());
    glass.castShadow = false;
    shell.add(glass);
  }

  const { rim: rimGeo, tyre: tyreGeo } = sharedWheel(spec.wheelRadius, spec.wheelWidth);

  // Wheels hang off the car group (not the shell) because they are positioned each frame
  // from live suspension travel, which is already in chassis space.
  const wheels = [];
  for (let i = 0; i < 4; i++) {
    const w = new Group();
    const rim = new Mesh(rimGeo, rimMaterial);
    rim.castShadow = true;
    const tyre = new Mesh(tyreGeo, rubberMaterial);
    tyre.castShadow = true;
    w.add(rim, tyre);
    group.add(w);
    wheels.push(w);
  }

  const front = spec.body[spec.body.length - 1];
  const rear = spec.body[0];
  const headlights = [];
  const taillights = [];
  for (const side of [-1, 1]) {
    const h = new Mesh(lampGeo, headlightMaterial.clone());
    h.position.set(side * front.hw * 0.62, front.y1 - 0.14, front.z + 0.02);
    shell.add(h);
    headlights.push(h);

    const t = new Mesh(lampGeo, taillightMaterial.clone());
    t.position.set(side * rear.hw * 0.66, rear.y1 - 0.12, rear.z - 0.01);
    shell.add(t);
    taillights.push(t);
  }

  // Details that can be dropped at distance without changing the silhouette.
  const details = [...headlights, ...taillights];
  return { group, shell, wheels, spec, headlights, taillights, body, details };
}

/** Roof accessories for emergency vehicles. */
export function addLightbar(group, spec) {
  const bar = new Group();
  const base = new Mesh(new BoxGeometry(1.05, 0.09, 0.24), trimMaterial);
  bar.add(base);
  const red = new Mesh(new BoxGeometry(0.44, 0.12, 0.2),
    new MeshPhysicalMaterial({ color: 0x5a0a0a, emissive: new Color(0xff1a1a), emissiveIntensity: 2, roughness: 0.3 }));
  red.position.x = -0.28;
  const blue = new Mesh(new BoxGeometry(0.44, 0.12, 0.2),
    new MeshPhysicalMaterial({ color: 0x0a1a5a, emissive: new Color(0x2a5aff), emissiveIntensity: 2, roughness: 0.3 }));
  blue.position.x = 0.28;
  bar.add(red, blue);
  const cabin = spec.cabin;
  bar.position.set(0, (cabin?.y ?? 1.5) + 0.06, cabin ? (cabin.z0 + cabin.z1) / 2 : 0);
  group.add(bar);
  return { bar, red, blue };
}

export function disposeVehicleGeometry() {
  for (const set of geometryCache.values()) {
    set.body.dispose();
    set.glass?.dispose();
    set.trim?.dispose();
  }
  geometryCache.clear();
}
