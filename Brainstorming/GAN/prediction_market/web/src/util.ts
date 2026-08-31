// Formatting and a stable colour per agent.

export const AGENT_COLORS: Record<string, string> = {
  market_follower: "#8b95a7", // grey: the baseline
  calibrated: "#38bdf8",
  sharp: "#22d3ee",
  momentum: "#34d399",
  mean_revert: "#a78bfa",
  contrarian: "#fb7185",
  anchor: "#f59e0b",
  stubborn: "#64748b",
};

export function agentColor(id: string): string {
  return AGENT_COLORS[id] ?? "#38bdf8";
}

export function brierStr(micro: number): string {
  return (micro / 1_000_000).toFixed(3);
}

export function skillStr(micro: number): string {
  const v = micro / 1_000_000;
  return (v >= 0 ? "+" : "") + v.toFixed(3);
}

export function dollars(cents: number): string {
  const v = cents / 100;
  return (v >= 0 ? "+$" : "-$") + Math.abs(v).toFixed(2);
}

export function pct(ppm: number): number {
  return Math.round(ppm / 10_000);
}

// A short human label for the tick time, trimming ISO noise.
export function shortT(t: string): string {
  return t.replace("T", " ").replace(/:00$/, "h");
}
