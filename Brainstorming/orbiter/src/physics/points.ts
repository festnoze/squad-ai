/**
 * Special points & reference orbits:
 *  - stationary orbits (Earth geostationary, lunar "selenostationary"),
 *  - the five Lagrange points of a two-body system (exact collinear solve),
 *  - a representative Near-Rectilinear Halo Orbit (NRHO) about the Moon.
 */

import { MU, RADIUS, SIDEREAL_ROTATION } from "./constants";
import { circularElements, type OrbitalElements } from "./orbit";
import { add, cross, normalize, scale, sub, type Vec3 } from "./vec";

/** Radius of a circular orbit synchronous with a body's rotation:
 *  r = (μ / ω²)^(1/3), with ω = 2π / T_sidereal. */
export function stationaryRadius(mu: number, siderealPeriod: number): number {
  const omega = (2 * Math.PI) / siderealPeriod;
  return Math.cbrt(mu / (omega * omega));
}

/** Geostationary orbit radius ≈ 42 164 km (from Earth's centre). */
export const GEO_RADIUS = stationaryRadius(MU.earth, SIDEREAL_ROTATION.earth);

/** "Selenostationary" radius — synchronous with the Moon's sidereal rotation.
 *  NB: it lies BEYOND the Moon's Hill sphere, so it is only theoretical. */
export const LUNAR_STATIONARY_RADIUS = stationaryRadius(MU.moon, SIDEREAL_ROTATION.moon);

/** Hill sphere radius of the secondary: r_H ≈ a·(m2/3m1)^(1/3). */
export function hillRadius(a: number, massSecondary: number, massPrimary: number): number {
  return a * Math.cbrt(massSecondary / (3 * massPrimary));
}

/** Net along-axis acceleration in the normalised rotating frame (units: R=1,
 *  total mass=1, n=1). Primary1 at −μ, primary2 at 1−μ. Zero at collinear points. */
function collinearResidual(x: number, mu: number): number {
  const r1 = Math.abs(x + mu);
  const r2 = Math.abs(x - (1 - mu));
  return x - ((1 - mu) * (x + mu)) / r1 ** 3 - (mu * (x - (1 - mu))) / r2 ** 3;
}

function newtonCollinear(x0: number, mu: number): number {
  let x = x0;
  const h = 1e-7;
  for (let k = 0; k < 100; k++) {
    const f = collinearResidual(x, mu);
    const fp = (collinearResidual(x + h, mu) - collinearResidual(x - h, mu)) / (2 * h);
    const dx = f / fp;
    x -= dx;
    if (Math.abs(dx) < 1e-12) break;
  }
  return x;
}

export interface LagrangeSet {
  L1: Vec3; L2: Vec3; L3: Vec3; L4: Vec3; L5: Vec3;
}

/**
 * The five Lagrange points (x,y) in the normalised rotating frame, in units of
 * the separation R. μ = m2/(m1+m2) is the secondary's mass fraction.
 * Origin = barycentre, primary1 at x=−μ, primary2 at x=1−μ.
 */
export function lagrangeNormalized(mu: number): Record<keyof LagrangeSet, [number, number]> {
  const rh = Math.cbrt(mu / 3); // L1/L2 offset seed (Hill radius in units of R)
  const L1 = newtonCollinear(1 - mu - rh, mu);
  const L2 = newtonCollinear(1 - mu + rh, mu);
  const L3 = newtonCollinear(-(1 + (5 / 12) * mu), mu);
  return {
    L1: [L1, 0],
    L2: [L2, 0],
    L3: [L3, 0],
    L4: [0.5 - mu, Math.sqrt(3) / 2], // leading equilateral vertex
    L5: [0.5 - mu, -Math.sqrt(3) / 2], // trailing
  };
}

/**
 * Inertial positions of the five Lagrange points of (primary1, primary2) given
 * their current positions and the orbit-plane normal. The x-axis points from
 * primary1 to primary2; y completes the right-handed plane.
 */
export function lagrangePositions(
  p1: Vec3,
  p2: Vec3,
  normal: Vec3,
  massPrimary: number,
  massSecondary: number,
): LagrangeSet {
  const mu = massSecondary / (massPrimary + massSecondary);
  const dx = sub(p2, p1);
  const R = Math.hypot(dx[0], dx[1], dx[2]);
  const ux = normalize(dx);
  const uy = normalize(cross(normalize(normal), ux));
  const bary = add(p1, scale(ux, mu * R)); // barycentre (primary1 at −μR)
  const norm2d = lagrangeNormalized(mu);
  const place = ([nx, ny]: [number, number]): Vec3 =>
    add(bary, add(scale(ux, nx * R), scale(uy, ny * R)));
  return {
    L1: place(norm2d.L1),
    L2: place(norm2d.L2),
    L3: place(norm2d.L3),
    L4: place(norm2d.L4),
    L5: place(norm2d.L5),
  };
}

/**
 * A representative southern NRHO about the Moon (Gateway-class). NB: a true NRHO
 * is a CR3BP halo found by differential correction — this is an APPROXIMATION as
 * a near-polar, high-eccentricity Keplerian ellipse with apolune on the L2
 * (anti-Earth) side, which reads correctly for visualisation.
 *
 * @param l2Direction unit vector Moon→L2 (anti-Earth) in the inertial frame.
 */
export function approximateNrho(l2Direction: Vec3): {
  elements: OrbitalElements;
  perilune: number;
  apolune: number;
  approximate: true;
} {
  const perilune = RADIUS.moon + 3_500e3; // ~3 500 km altitude
  const apolune = RADIUS.moon + 70_000e3; // ~70 000 km altitude
  const a = (perilune + apolune) / 2;
  const e = (apolune - perilune) / (apolune + perilune);
  // Orient: line of apsides along ±l2Direction (apolune toward L2), near-polar.
  const raan = Math.atan2(l2Direction[1], l2Direction[0]) + Math.PI / 2;
  const elements = circularElements(a, {
    e,
    i: (Math.PI / 180) * 87, // near-polar
    raan,
    argp: Math.PI, // apolune toward the node line / L2 side
    m0: Math.PI, // start near apolune
  });
  return { elements, perilune, apolune, approximate: true };
}
