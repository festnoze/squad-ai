/**
 * The reduced solar system: Sun, Earth, Moon, Mars.
 *
 * Earth & Mars use the JPL "approximate positions of the planets" Keplerian
 * elements (J2000 ecliptic) with their per-century secular rates. The Moon uses
 * low-precision geocentric mean elements (node regression ~18.6 yr, apsidal
 * precession ~8.85 yr). Good to a fraction of a degree — ample for navigation
 * and visualisation.
 */

import { AU, DAY, DEG, MU, RADIUS } from "./constants";
import { add, elementsToState, type OrbitalElements, type Vec3 } from "./orbit";

export type BodyId = "sun" | "earth" | "moon" | "mars";

export interface Body {
  id: BodyId;
  name: string;
  parent: BodyId | null; // null = frame origin (Sun)
  mu: number; // [m^3/s^2]
  radius: number; // [m]
  color: number; // hex
  /** Instantaneous elements about the parent at time t [s since J2000]. */
  elementsAt?: (t: number) => OrbitalElements;
}

const T_CENTURY = DAY * 36525;

interface JplRow {
  a0: number; aR: number; // AU
  e0: number; eR: number;
  I0: number; IR: number; // deg
  L0: number; LR: number; // deg, mean longitude
  w0: number; wR: number; // deg, longitude of perihelion ϖ
  O0: number; OR: number; // deg, longitude of ascending node Ω
}

function jplElements(row: JplRow): (t: number) => OrbitalElements {
  return (t: number): OrbitalElements => {
    const T = t / T_CENTURY;
    const wbar = (row.w0 + row.wR * T) * DEG;
    const raan = (row.O0 + row.OR * T) * DEG;
    const L = (row.L0 + row.LR * T) * DEG;
    return {
      a: (row.a0 + row.aR * T) * AU,
      e: row.e0 + row.eR * T,
      i: (row.I0 + row.IR * T) * DEG,
      raan,
      argp: wbar - raan,
      m0: L - wbar,
      epoch: t,
    };
  };
}

// JPL (Standish) elements valid 1800–2050.
const EARTH_ROW: JplRow = {
  a0: 1.00000261, aR: 0.00000562,
  e0: 0.01671123, eR: -0.00004392,
  I0: -0.00001531, IR: -0.01294668,
  L0: 100.46457166, LR: 35999.37244981,
  w0: 102.93768193, wR: 0.32327364,
  O0: 0.0, OR: 0.0,
};

const MARS_ROW: JplRow = {
  a0: 1.52371034, aR: 0.00001847,
  e0: 0.0933941, eR: 0.00007882,
  I0: 1.84969142, IR: -0.00813131,
  L0: -4.55343205, LR: 19140.30268499,
  w0: -23.94362959, wR: 0.44441088,
  O0: 49.55953891, OR: -0.29257343,
};

function moonElements(t: number): OrbitalElements {
  const d = t / DAY; // days since J2000
  const raan = (125.0445 - 0.0529538083 * d) * DEG; // ascending node Ω
  const wbar = (83.3532 + 0.1114040803 * d) * DEG; // longitude of perigee ϖ
  const L = (218.3162 + 13.1763966 * d) * DEG; // mean longitude
  return {
    a: 384399e3,
    e: 0.0549,
    i: 5.145 * DEG,
    raan,
    argp: wbar - raan,
    m0: L - wbar,
    epoch: t,
  };
}

export const BODIES: Record<BodyId, Body> = {
  sun: { id: "sun", name: "Soleil", parent: null, mu: MU.sun, radius: RADIUS.sun, color: 0xffd14a },
  earth: {
    id: "earth", name: "Terre", parent: "sun", mu: MU.earth, radius: RADIUS.earth,
    color: 0x3a7bd5, elementsAt: jplElements(EARTH_ROW),
  },
  moon: {
    id: "moon", name: "Lune", parent: "earth", mu: MU.moon, radius: RADIUS.moon,
    color: 0xc9c9c9, elementsAt: moonElements,
  },
  mars: {
    id: "mars", name: "Mars", parent: "sun", mu: MU.mars, radius: RADIUS.mars,
    color: 0xc1440e, elementsAt: jplElements(MARS_ROW),
  },
};

export const BODY_LIST: Body[] = [BODIES.sun, BODIES.earth, BODIES.moon, BODIES.mars];

/** μ of a body's parent (the central mass it orbits). */
export function parentMu(body: Body): number {
  return body.parent ? BODIES[body.parent].mu : 0;
}

/** Heliocentric (Sun-frame) position of a body at time t, summing the chain
 *  Sun → parent → body so the Moon rides the Earth. */
export function heliocentricPosition(id: BodyId, t: number): Vec3 {
  const body = BODIES[id];
  if (!body.parent || !body.elementsAt) return [0, 0, 0];
  const local = elementsToState(body.elementsAt(t), BODIES[body.parent].mu, t).r;
  return add(heliocentricPosition(body.parent, t), local);
}
