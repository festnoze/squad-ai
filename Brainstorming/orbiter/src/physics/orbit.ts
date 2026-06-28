/**
 * Two-body Keplerian orbital mechanics — the trajectory engine.
 *
 * Everything works in a parent-centred inertial frame aligned with the J2000
 * ecliptic (x toward the vernal equinox, z toward the ecliptic north pole).
 * Angles in radians, distances in metres, time in seconds.
 */

import { add, cross, norm, scale, sub, dot, type Vec3 } from "./vec";

export interface OrbitalElements {
  /** Semi-major axis [m]. */
  a: number;
  /** Eccentricity (0 = circle, <1 = ellipse). */
  e: number;
  /** Inclination [rad]. */
  i: number;
  /** Right ascension of the ascending node Ω [rad]. */
  raan: number;
  /** Argument of periapsis ω [rad]. */
  argp: number;
  /** Mean anomaly at epoch M₀ [rad]. */
  m0: number;
  /** Epoch [s since J2000] at which M₀ is given. */
  epoch: number;
}

export interface State {
  r: Vec3; // position [m]
  v: Vec3; // velocity [m/s]
}

/** Mean motion n = √(μ/a³) [rad/s]. */
export function meanMotion(a: number, mu: number): number {
  return Math.sqrt(mu / (a * a * a));
}

/** Orbital period T = 2π/n [s] (finite only for bound, e<1 orbits). */
export function period(a: number, mu: number): number {
  return (2 * Math.PI) / meanMotion(a, mu);
}

/**
 * Solve Kepler's equation M = E − e·sin E for the eccentric anomaly E [rad]
 * via Newton–Raphson. Converges quadratically; the starting guess keeps it
 * robust up to high eccentricity.
 */
export function solveKepler(M: number, e: number, tol = 1e-12, maxIter = 100): number {
  // Normalise M to [-π, π] for a well-conditioned start.
  const Mn = Math.atan2(Math.sin(M), Math.cos(M));
  let E = e < 0.8 ? Mn : Math.PI * Math.sign(Mn || 1);
  for (let k = 0; k < maxIter; k++) {
    const f = E - e * Math.sin(E) - Mn;
    const fp = 1 - e * Math.cos(E);
    const dE = f / fp;
    E -= dE;
    if (Math.abs(dE) < tol) break;
  }
  return E;
}

/** True anomaly ν [rad] from the eccentric anomaly E. */
export function trueAnomaly(E: number, e: number): number {
  return 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(E / 2), Math.sqrt(1 - e) * Math.cos(E / 2));
}

/** Rotate a perifocal vector into the inertial frame by (Ω, i, ω). */
function perifocalToInertial(p: Vec3, raan: number, i: number, argp: number): Vec3 {
  const cO = Math.cos(raan), sO = Math.sin(raan);
  const ci = Math.cos(i), si = Math.sin(i);
  const cw = Math.cos(argp), sw = Math.sin(argp);
  // R = Rz(Ω)·Rx(i)·Rz(ω)
  const r11 = cO * cw - sO * sw * ci;
  const r12 = -cO * sw - sO * cw * ci;
  const r13 = sO * si;
  const r21 = sO * cw + cO * sw * ci;
  const r22 = -sO * sw + cO * cw * ci;
  const r23 = -cO * si;
  const r31 = sw * si;
  const r32 = cw * si;
  const r33 = ci;
  return [
    r11 * p[0] + r12 * p[1] + r13 * p[2],
    r21 * p[0] + r22 * p[1] + r23 * p[2],
    r31 * p[0] + r32 * p[1] + r33 * p[2],
  ];
}

/** Position + velocity at time t [s since J2000] for the given elements. */
export function elementsToState(el: OrbitalElements, mu: number, t: number): State {
  const n = meanMotion(el.a, mu);
  const M = el.m0 + n * (t - el.epoch);
  const E = solveKepler(M, el.e);
  const cE = Math.cos(E), sE = Math.sin(E);
  const b = el.a * Math.sqrt(1 - el.e * el.e);

  // Perifocal position & velocity.
  const pPos: Vec3 = [el.a * (cE - el.e), b * sE, 0];
  const Edot = n / (1 - el.e * cE);
  const pVel: Vec3 = [-el.a * sE * Edot, b * cE * Edot, 0];

  return {
    r: perifocalToInertial(pPos, el.raan, el.i, el.argp),
    v: perifocalToInertial(pVel, el.raan, el.i, el.argp),
  };
}

/** Position only (cheap path for drawing). */
export function positionAt(el: OrbitalElements, mu: number, t: number): Vec3 {
  return elementsToState(el, mu, t).r;
}

/** Sample N points along the full orbit path (geometric ellipse), for drawing.
 *  Independent of μ — it walks the eccentric anomaly around one revolution. */
export function sampleOrbit(el: OrbitalElements, samples = 256): Vec3[] {
  const pts: Vec3[] = [];
  for (let k = 0; k < samples; k++) {
    const E = (2 * Math.PI * k) / samples;
    const cE = Math.cos(E), sE = Math.sin(E);
    const b = el.a * Math.sqrt(1 - el.e * el.e);
    pts.push(perifocalToInertial([el.a * (cE - el.e), b * sE, 0], el.raan, el.i, el.argp));
  }
  return pts;
}

/** A circular orbit of radius `a` about a body, in the body's equatorial/ecliptic
 *  plane unless an inclination is given. Handy for GEO and quick satellites. */
export function circularElements(a: number, opts: Partial<OrbitalElements> = {}): OrbitalElements {
  return { a, e: 0, i: 0, raan: 0, argp: 0, m0: 0, epoch: 0, ...opts };
}

/**
 * Recover classical orbital elements from a state vector (r, v) about a body of
 * gravitational parameter μ. Used when a satellite is defined by position/velocity.
 */
export function stateToElements(state: State, mu: number, epoch = 0): OrbitalElements {
  const { r, v } = state;
  const rMag = norm(r);
  const vMag = norm(v);
  const h = cross(r, v);
  const hMag = norm(h);
  const nodeVec = cross([0, 0, 1], h); // points to ascending node
  const nMag = norm(nodeVec);

  // Eccentricity vector.
  const eVec = scale(
    sub(scale(r, vMag * vMag - mu / rMag), scale(v, dot(r, v))),
    1 / mu,
  );
  const e = norm(eVec);

  const energy = (vMag * vMag) / 2 - mu / rMag;
  const a = Math.abs(energy) < 1e-12 ? Infinity : -mu / (2 * energy);

  const i = Math.acos(clamp(h[2] / hMag, -1, 1));

  let raan = nMag > 1e-9 ? Math.acos(clamp(nodeVec[0] / nMag, -1, 1)) : 0;
  if (nodeVec[1] < 0) raan = 2 * Math.PI - raan;

  let argp = 0;
  if (nMag > 1e-9 && e > 1e-9) {
    argp = Math.acos(clamp(dot(nodeVec, eVec) / (nMag * e), -1, 1));
    if (eVec[2] < 0) argp = 2 * Math.PI - argp;
  }

  let nu = 0;
  if (e > 1e-9) {
    nu = Math.acos(clamp(dot(eVec, r) / (e * rMag), -1, 1));
    if (dot(r, v) < 0) nu = 2 * Math.PI - nu;
  }
  // True → eccentric → mean anomaly.
  const E = 2 * Math.atan2(Math.sqrt(1 - e) * Math.sin(nu / 2), Math.sqrt(1 + e) * Math.cos(nu / 2));
  const m0 = E - e * Math.sin(E);

  return { a, e, i, raan, argp, m0, epoch };
}

function clamp(x: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, x));
}

export { add, sub, scale, norm, type Vec3 };
