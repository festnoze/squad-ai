import { describe, expect, it } from "vitest";
import { MU } from "./constants";
import {
  circularElements,
  elementsToState,
  meanMotion,
  period,
  solveKepler,
  stateToElements,
} from "./orbit";
import { norm, sub } from "./vec";

describe("Kepler solver", () => {
  it("satisfies M = E - e·sin E", () => {
    for (const e of [0, 0.1, 0.5, 0.9, 0.97]) {
      for (const M of [0.1, 1, 3, 5, 6.2]) {
        const E = solveKepler(M, e);
        const Mback = E - e * Math.sin(E);
        // compare modulo 2π
        const diff = Math.atan2(Math.sin(Mback - M), Math.cos(Mback - M));
        expect(Math.abs(diff)).toBeLessThan(1e-9);
      }
    }
  });
  it("returns M for a circular orbit (e=0)", () => {
    expect(solveKepler(1.234, 0)).toBeCloseTo(1.234, 10);
  });
});

describe("circular orbit", () => {
  it("keeps constant radius and matches the analytic period", () => {
    const a = 7_000e3; // LEO-ish radius
    const el = circularElements(a);
    const T = period(a, MU.earth);
    const r0 = norm(elementsToState(el, MU.earth, 0).r);
    const rHalf = norm(elementsToState(el, MU.earth, T / 2).r);
    expect(r0).toBeCloseTo(a, 3);
    expect(rHalf).toBeCloseTo(a, 3);
    // After one full period it returns to the start.
    const back = elementsToState(el, MU.earth, T).r;
    const start = elementsToState(el, MU.earth, 0).r;
    expect(norm(sub(back, start))).toBeLessThan(1); // < 1 metre
  });

  it("circular speed equals √(μ/r)", () => {
    const a = 1e7;
    const v = norm(elementsToState(circularElements(a), MU.earth, 0).v);
    expect(v).toBeCloseTo(Math.sqrt(MU.earth / a), 2);
  });

  it("mean motion is 2π/period", () => {
    const a = 4.2164e7;
    expect(meanMotion(a, MU.earth)).toBeCloseTo((2 * Math.PI) / period(a, MU.earth), 12);
  });
});

describe("state ↔ elements round-trip", () => {
  it("recovers eccentric, inclined elements", () => {
    const el = {
      a: 2.0e7,
      e: 0.3,
      i: 0.4,
      raan: 1.0,
      argp: 0.7,
      m0: 0.9,
      epoch: 0,
    };
    const state = elementsToState(el, MU.earth, 0);
    const rec = stateToElements(state, MU.earth, 0);
    expect(rec.a).toBeCloseTo(el.a, 1);
    expect(rec.e).toBeCloseTo(el.e, 6);
    expect(rec.i).toBeCloseTo(el.i, 6);
    expect(rec.raan).toBeCloseTo(el.raan, 6);
    expect(rec.argp).toBeCloseTo(el.argp, 6);
  });
});
