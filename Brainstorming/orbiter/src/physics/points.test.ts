import { describe, expect, it } from "vitest";
import { MASS, MU } from "./constants";
import {
  GEO_RADIUS,
  LUNAR_STATIONARY_RADIUS,
  lagrangeNormalized,
  lagrangePositions,
  stationaryRadius,
} from "./points";
import { norm, sub, type Vec3 } from "./vec";

describe("stationary orbits", () => {
  it("geostationary radius ≈ 42 164 km", () => {
    expect(GEO_RADIUS / 1000).toBeGreaterThan(42_100);
    expect(GEO_RADIUS / 1000).toBeLessThan(42_200);
  });
  it("selenostationary radius ≈ 88 000 km (theoretical, beyond Hill sphere)", () => {
    expect(LUNAR_STATIONARY_RADIUS / 1000).toBeGreaterThan(86_000);
    expect(LUNAR_STATIONARY_RADIUS / 1000).toBeLessThan(90_000);
  });
  it("matches r=(μ/ω²)^(1/3)", () => {
    const T = 12345;
    const r = stationaryRadius(MU.earth, T);
    const omega = (2 * Math.PI) / T;
    expect(r).toBeCloseTo(Math.cbrt(MU.earth / (omega * omega)), 3);
  });
});

describe("Lagrange points (normalised)", () => {
  const mu = MASS.moon / (MASS.earth + MASS.moon); // Earth–Moon ≈ 0.0121
  const L = lagrangeNormalized(mu);

  it("L1 is between the primaries, L2 beyond the secondary, L3 opposite", () => {
    const secondary = 1 - mu;
    expect(L.L1[0]).toBeLessThan(secondary);
    expect(L.L1[0]).toBeGreaterThan(-mu);
    expect(L.L2[0]).toBeGreaterThan(secondary);
    expect(L.L3[0]).toBeLessThan(-mu);
  });

  it("L1 and L2 straddle the secondary by ~the Hill radius", () => {
    const rh = Math.cbrt(mu / 3);
    expect(1 - mu - L.L1[0]).toBeCloseTo(rh, 1);
    expect(L.L2[0] - (1 - mu)).toBeCloseTo(rh, 1);
  });

  it("L4/L5 form equilateral triangles (60°), y = ±√3/2", () => {
    expect(L.L4[1]).toBeCloseTo(Math.sqrt(3) / 2, 10);
    expect(L.L5[1]).toBeCloseTo(-Math.sqrt(3) / 2, 10);
    expect(L.L4[0]).toBeCloseTo(0.5 - mu, 10);
  });
});

describe("Lagrange points (inertial placement)", () => {
  it("places L4/L5 equidistant from both primaries", () => {
    const p1: Vec3 = [0, 0, 0];
    const R = 3.844e8;
    const p2: Vec3 = [R, 0, 0];
    const normal: Vec3 = [0, 0, 1];
    const set = lagrangePositions(p1, p2, normal, MASS.earth, MASS.moon);
    // L4 is equidistant from Earth and Moon, at distance ≈ R.
    expect(norm(sub(set.L4, p1))).toBeCloseTo(R, 0);
    expect(norm(sub(set.L4, p2))).toBeCloseTo(R, 0);
  });
});
