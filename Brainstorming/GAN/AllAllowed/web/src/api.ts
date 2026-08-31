import type { AlaEvent, MatchSummary } from "./types";

// All calls hit the same origin; Vite proxies /matches to the ala API on 8165.

export async function fetchMatches(): Promise<string[]> {
  const res = await fetch("/matches");
  if (!res.ok) throw new Error(`GET /matches failed: ${res.status}`);
  return res.json();
}

export async function fetchJournal(matchId: string): Promise<AlaEvent[]> {
  const res = await fetch(`/matches/${encodeURIComponent(matchId)}/journal`);
  if (!res.ok) throw new Error(`journal for ${matchId} failed: ${res.status}`);
  return res.json();
}

export async function fetchSummary(matchId: string): Promise<MatchSummary> {
  const res = await fetch(`/matches/${encodeURIComponent(matchId)}`);
  if (!res.ok) throw new Error(`summary for ${matchId} failed: ${res.status}`);
  return res.json();
}

export interface RunRequest {
  seed: number;
  agents: string[];
  ticks: number;
  cull_every: number;
  permission: string;
}

export interface RunResult {
  match_id: string;
  ticks: number;
  final_ranking: string[];
  journal_hash: string;
}

// Launch a fresh scripted match. This is the one mutating call the API exposes (POST /runs).
export async function createRun(req: RunRequest): Promise<RunResult> {
  const res = await fetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario: "concours", ...req }),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the status code */
    }
    throw new Error(detail);
  }
  return res.json();
}
