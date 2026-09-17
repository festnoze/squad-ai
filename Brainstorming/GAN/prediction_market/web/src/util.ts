const integer = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
export const count = (value: number) => integer.format(value);
export const decimal = (value: number, digits = 2) => new Intl.NumberFormat("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
export const date = (value: number | string, withTime = false) => new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", ...(withTime ? { timeStyle: "short" as const } : {}), timeZone: "UTC" }).format(new Date(value));
export const money = (cents: number, currency: string) => `${decimal(cents / 100)} ${currency.toUpperCase()}`;
export const signed = (value: number, digits = 3) => `${value > 0 ? "+" : ""}${decimal(value, digits)}`;
export const foldName = (fold: string) => fold === "train" ? "Entraînement" : fold === "validation" ? "Validation" : "Scellé";
export const providerName = (provider: string) => provider === "kalshi" ? "Kalshi" : provider === "manifold" ? "Manifold" : provider === "polymarket" ? "Polymarket" : provider;
export const providerCurrency = (provider: string) => provider === "polymarket" ? "USDC" : provider === "manifold" ? "MANA" : "USD";
export const agentName = (id: string) => ({ follower: "Référence marché", trend: "Tendance", revert: "Retour à la moyenne" }[id] ?? id);
export const agentColor = (id: string) => ({ follower: "#7a8898", trend: "#168da0", revert: "#b16b2d" }[id] ?? "#7357af");
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);
export function stored(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
export function remember(key: string, value: string | null) {
  try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch { /* Storage may be unavailable in a private session. */ }
}
