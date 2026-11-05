import { describe, expect, it } from "vitest";
import { formatCost, formatCountdown } from "./format";

describe("format", () => {
  it("formats a cost in dollars with two decimals", () => {
    expect(formatCost(0.375)).toMatch(/^0,38\s\$$/u);
    expect(formatCost(Number.NaN)).toMatch(/^0,00/);
  });

  it("formats the countdown to an automatic resume", () => {
    const now = 1_000_000_000_000;
    expect(formatCountdown(now / 1000 + 12 * 60, now)).toBe("dans 12 min");
    expect(formatCountdown(now / 1000 + 90 * 60, now)).toBe("dans 1 h 30 min");
    expect(formatCountdown(now / 1000 + 120 * 60, now)).toBe("dans 2 h");
    expect(formatCountdown(now / 1000 - 5, now)).toBe("imminente");
  });
});
