import type { Backtest, MarketMeta, Tournament, WalkForward } from "./types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const fetchAgents = () => getJSON<{ agents: string[] }>("/agents").then((r) => r.agents);
export const fetchMarkets = () => getJSON<MarketMeta[]>("/markets");
export const fetchBacktest = (id: string, agents?: string[]) =>
  getJSON<Backtest>(`/markets/${encodeURIComponent(id)}/backtest${agents?.length ? `?agents=${agents.join(",")}` : ""}`);
export const fetchTournament = (agents?: string[]) =>
  getJSON<Tournament>(`/tournament${agents?.length ? `?agents=${agents.join(",")}` : ""}`);
export const fetchWalkForward = (agents?: string[]) =>
  getJSON<WalkForward>(`/walkforward${agents?.length ? `?agents=${agents.join(",")}` : ""}`);
