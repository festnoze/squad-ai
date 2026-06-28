/**
 * The mutable world: the four natural bodies (from the physics layer) plus any
 * artificial satellites the user adds. Every satellite is a Keplerian orbit
 * about a chosen central body, computed from real formulas.
 */

import {
  AU,
  BODIES,
  type BodyId,
  GEO_RADIUS,
  LUNAR_STATIONARY_RADIUS,
  MU,
  RADIUS,
  approximateNrho,
  circularElements,
  elementsToState,
  heliocentricPosition,
  type OrbitalElements,
  stationaryRadius,
  type Vec3,
  add,
} from "../physics";

export interface Satellite {
  id: string;
  name: string;
  central: BodyId;
  elements: OrbitalElements;
  color: number;
  note?: string;
}

const MARS_SIDEREAL_DAY = 88642.66; // s

export type PresetId =
  | "geo"
  | "iss"
  | "lunar-stationary"
  | "nrho"
  | "areostationary"
  | "hohmann-mars";

export interface PresetDef {
  id: PresetId;
  label: string;
}

export const PRESETS: PresetDef[] = [
  { id: "geo", label: "Géostationnaire (Terre, GEO)" },
  { id: "iss", label: "Orbite basse type ISS (Terre)" },
  { id: "lunar-stationary", label: "Sélénostationnaire (Lune, théorique)" },
  { id: "nrho", label: "NRHO ~ Gateway (Lune, approx.)" },
  { id: "areostationary", label: "Aréostationnaire (Mars)" },
  { id: "hohmann-mars", label: "Transfert Hohmann Terre→Mars (Soleil)" },
];

let counter = 0;
const COLORS = [0x4ade80, 0xf472b6, 0x38bdf8, 0xfbbf24, 0xa78bfa, 0xfb7185];

/** Build a satellite from a preset, computing its orbit from the formulas. */
export function makePreset(id: PresetId, t: number): Satellite {
  const color = COLORS[counter % COLORS.length];
  const sid = `sat-${++counter}`;
  switch (id) {
    case "geo":
      return {
        id: sid, name: `GEO #${counter}`, central: "earth", color,
        elements: circularElements(GEO_RADIUS),
        note: `r = (μ⊕/ω²)^⅓ = ${(GEO_RADIUS / 1000).toFixed(0)} km`,
      };
    case "iss":
      return {
        id: sid, name: `LEO/ISS #${counter}`, central: "earth", color,
        elements: circularElements(RADIUS.earth + 420e3, { i: (51.64 * Math.PI) / 180 }),
        note: "altitude 420 km, i = 51.6°",
      };
    case "lunar-stationary":
      return {
        id: sid, name: `Sélénostat. #${counter}`, central: "moon", color,
        elements: circularElements(LUNAR_STATIONARY_RADIUS),
        note: `r = ${(LUNAR_STATIONARY_RADIUS / 1000).toFixed(0)} km — au-delà de la sphère de Hill (théorique)`,
      };
    case "nrho": {
      // Apolune toward Earth–Moon L2 (anti-Earth direction).
      const earth = heliocentricPosition("earth", t);
      const moon = heliocentricPosition("moon", t);
      const antiEarth: Vec3 = [moon[0] - earth[0], moon[1] - earth[1], moon[2] - earth[2]];
      const nrho = approximateNrho(antiEarth);
      return {
        id: sid, name: `NRHO #${counter}`, central: "moon", color,
        elements: nrho.elements,
        note: `périlune ${((nrho.perilune - RADIUS.moon) / 1000).toFixed(0)} km / apolune ${((nrho.apolune - RADIUS.moon) / 1000).toFixed(0)} km (approx. halo)`,
      };
    }
    case "areostationary": {
      const r = stationaryRadius(MU.mars, MARS_SIDEREAL_DAY);
      return {
        id: sid, name: `Aréostat. #${counter}`, central: "mars", color,
        elements: circularElements(r),
        note: `r = ${(r / 1000).toFixed(0)} km (jour sidéral martien)`,
      };
    }
    case "hohmann-mars": {
      const rE = BODIES.earth.elementsAt!(t).a;
      const rM = BODIES.mars.elementsAt!(t).a;
      const a = (rE + rM) / 2;
      const e = (rM - rE) / (rM + rE);
      return {
        id: sid, name: `Hohmann →Mars #${counter}`, central: "sun", color,
        elements: { a, e, i: 0, raan: 0, argp: 0, m0: 0, epoch: t },
        note: `demi-ellipse, a = ${(a / AU).toFixed(3)} UA, e = ${e.toFixed(3)}`,
      };
    }
  }
}

export class World {
  satellites: Satellite[] = [];

  add(sat: Satellite): void {
    this.satellites.push(sat);
  }

  remove(id: string): void {
    this.satellites = this.satellites.filter((s) => s.id !== id);
  }

  /** Heliocentric (Sun-frame) position of a satellite at time t. */
  satellitePosition(sat: Satellite, t: number): Vec3 {
    const local = elementsToState(sat.elements, MU[sat.central], t).r;
    return add(heliocentricPosition(sat.central, t), local);
  }
}
