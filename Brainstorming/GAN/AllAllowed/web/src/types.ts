// The shapes the ala API serves. An Event is exactly one journal record.

export interface AlaEvent {
  kind: string;
  tick: number;
  seq: number;
  payload: Record<string, unknown>;
}

// One agent's reconstructed state at a given tick.
export interface AgentState {
  id: string;
  credits: number;
  startCredits: number;
  role: "user" | "root";
  alive: boolean;
  isClone: boolean;
  lastAction: string; // plain-English description of what it did most recently
  lastActionFamily: Family | null;
  // cumulative behaviour flags, used to infer what kind of agent this is
  didEscalate: boolean;
  didForge: boolean;
  didKill: boolean;
  didPost: boolean;
  didRead: boolean;
  didCompute: boolean;
  acted: boolean;
}

export type Family = "work" | "coop" | "attack" | "cheat" | "system";

export interface BoardEntry {
  agent: string;
  channel: string;
  key: string;
  tick: number;
}

export interface StoryLine {
  tick: number;
  family: Family;
  icon: string;
  text: string;
  important: boolean;
}

// A full snapshot of the world after all events up to and including one tick.
export interface Frame {
  tick: number;
  agents: AgentState[];
  board: BoardEntry[];
  scorerAlive: boolean;
  scoredThisTick: boolean;
  rubricHash: string | null;
  rubricTampered: boolean;
  floor: number;
  story: StoryLine[]; // cumulative story up to this frame
  flash: Record<string, Family>; // agent id -> family that acted this tick (for pulse animation)
  payoutsThisTick: { id: string; paid: number; score: number }[];
  counts: {
    submits: number;
    posts: number;
    kills: number;
    escalations: number;
    forges: number;
    deaths: number;
  };
}

export interface Replay {
  matchId: string;
  scenario: string;
  seed: number;
  startBudget: number;
  permission: string;
  events: AlaEvent[]; // the raw journal, kept for per-agent dossiers
  frames: Frame[]; // one per distinct tick, in order
  finalRanking: string[];
}

export interface MatchSummary {
  scenario: string;
  seed: number;
  ticks: number;
  final_ranking: string[];
  incidents_by_kind: Record<string, number>;
  metrics: Record<string, Record<string, number | string>>;
}
