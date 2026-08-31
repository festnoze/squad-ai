// Shapes returned by the pmx API.

export interface MarketMeta {
  id: string;
  question: string;
  category: string;
  source: "reconstructed" | "imported";
  resolution: number; // 1 = YES, 0 = NO
  resolved_date: string;
  n_ticks: number;
  notes: string;
}

export interface AgentTickState {
  prob_ppm: number;
  position: number;
  equity: number; // cents, mark-to-market
}

export interface TickRow {
  t: string;
  price: number; // cents
  agents: Record<string, AgentTickState>;
}

export interface AgentResult {
  agent_id: string;
  market_id: string;
  resolution: number;
  final_prob_ppm: number;
  final_brier_micro: number;
  mean_brier_micro: number;
  pnl_cents: number;
  trades: number;
  market_brier_micro: number;
}

export interface Backtest {
  run_id: string;
  market: MarketMeta & { prices: { t: string; price: number }[] };
  agent_ids: string[];
  ticks: TickRow[];
  results: AgentResult[];
}

export interface LeaderRow {
  agent_id: string;
  markets: number;
  mean_final_brier_micro: number;
  mean_brier_micro: number;
  total_pnl_cents: number;
  mean_pnl_cents: number;
  beat_market_count: number;
  beat_market_pct: number;
  skill_vs_market_micro: number;
}

export interface Tournament {
  agent_ids: string[];
  board: LeaderRow[];
  per_market: { market: MarketMeta; results: AgentResult[] }[];
}

export interface WalkForward {
  train_ids: string[];
  test_ids: string[];
  train_board: LeaderRow[];
  test_board: LeaderRow[];
  train_winner: string;
  test_winner: string;
  generalised: boolean;
}
