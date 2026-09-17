export type Fold = "train" | "validation";

export interface SignalRow {
  variant_id: string; family: "calibration" | "reversal"; label: string; activity: string;
  n_anchors: number; n_markets: number; n_weeks: number; target_coverage: number | null;
  mean_effect_bp: number | null; weekly_mean_effect_bp: number | null; weekly_interval_95_bp: number[] | null;
  mean_price_bp: number | null; win_rate: number | null; missing_reasons: Record<string, number>;
  status: "candidate_for_replication" | "not_retained" | "inconclusive";
  months: { month: string; n: number; mean_effect_bp: number | null }[];
}
export interface SignalStudy {
  study_id: string; dataset: string; status: "queued" | "running" | "completed" | "failed";
  error: string | null; created_at: string; protocol_hash: string;
  result?: {
    dataset_hash: string; protocol_hash: string; effective_cutoff_ms: number;
    protocol: Record<string, unknown>; rows: SignalRow[]; limitations: string[];
    coverage: { eligible_train_markets: number; markets_with_bars: number; bars: number; observed_hours: number; observed_fraction: number | null; calibration_anchors: number };
    corpus_coverage: { adapter_bars: number; adapter_observed_hours: number; population_conditions: number; selected_conditions: number; exclusions: Record<string, number> };
    reference_coverage: { adapter_bars: number; adapter_observed_hours: number };
    protected_ids_count: number; excluded_overlap: number;
  } | null;
}

export interface DatasetSummary {
  name: string; dataset_hash: string; freeze_date: string; interval_min: number;
  n_markets: number; n_visible_markets: number; providers: string[]; categories: string[];
  counts_by_provider: Record<string, number>; counts_by_fold: Record<string, number>;
  limitations: string[];
  coverage: DatasetCoverage | null;
}
export interface DatasetCoverage {
  schema: string; start_ms: number; end_ms: number; interval_min: number;
  population_conditions: number; selected_conditions: number; selected_observed_hours: number;
  settled_adapter_markets: number; label_status_counts: Record<string, number>;
  exclusions: Record<string, number>; known_historical_close: boolean;
  verified_event_groups: number; event_group_policy: string;
  historical_fee_schedule_known: boolean; fee_schedule_id: string; fee_policy: string;
  population_scope: string; adapter_scope: string; order_book_available: boolean;
}
export interface MarketSummary {
  id: string; question: string; category: string; provider: string; currency: string;
  fold: Fold; source: string; created_at_ms: number; close_at_ms: number; resolved_at_ms: number;
  resolution: 0 | 1; n_bars: number; n_trades: number; volume_milli: number;
  subjects: string[]; structure: string; horizon: string; cohort_id: string | null;
  close_time_verified?: boolean;
}
export interface Bar {
  t_ms: number; open_bp: number; high_bp: number; low_bp: number; close_bp: number; volume_milli: number;
}
export interface MarketDetail {
  market: MarketSummary;
  bars: Bar[];
  news: { id: string; published_at_ms: number; visible_from_ms: number; source: string; text: string; url: string }[];
}
export interface AgentSummary {
  id: string; name: string; description: string; baseline: boolean; parameters: Record<string, number>;
}
export interface RunRequest {
  dataset: string; provider: string; fold: Fold; agent_ids: string[];
  seed: number; bankroll_cents: number; max_markets: number;
}
export interface Job {
  job_id: string; status: "queued" | "running" | "completed" | "failed" | "cancelled";
  run_id: string | null; error: string | null;
}
export interface RunSummary {
  run_id: string; dataset: string; dataset_hash: string; provider: string; currency: string; fold: Fold;
  seed: number; bankroll_cents: number; market_ids: string[]; agent_ids: string[]; n_markets: number;
  journal_hash: string; created_at: string; status: "completed"; limitations: string[];
}
export interface AgentResult {
  agent_id: string; name: string; baseline: boolean; n_markets: number; mean_brier_micro: number;
  market_brier_micro: number; skill_micro: number; pnl_cents: number; fees_cents: number;
  n_fills: number; max_drawdown_bp: number; final_equity_cents: number;
}
export interface RunDetail {
  run: RunSummary; leaderboard: AgentResult[];
  equity: { t_ms: number; agents: Record<string, number> }[];
  markets: MarketSummary[];
}
export interface ReplayTick {
  t_ms: number; price_bp: number;
  agents: Record<string, { prob_ppm: number; position: number; equity_cents: number }>;
}
export interface RunMarketReplay {
  market_id: string; agent_ids: string[]; ticks: ReplayTick[];
  fills: { t_ms: number; agent_id: string; side: string; size: number; price_bp: number; fee_cents: number }[];
}

export type CampaignStatus = "queued" | "running" | "validating" | "completed" | "failed" | "cancelled";
export type CandidateStatus = "running" | "completed" | "rejected" | "failed";

export interface DiscoveryConfig {
  provider: string; seed: number; n_trials: number; max_markets: number;
  bankroll_cents: number; n_splits: number; finalists: number;
  mining_budget?: number;
}
export interface DiscoveryPeriodResult {
  period: string; fold: Fold; t0_ms: number; t1_ms: number; market_ids: string[];
  run_id: string; journal_hash: string; pnl_cents: number; fees_cents: number;
  max_drawdown_bp: number; n_fills: number; n_markets: number; final_equity_cents: number;
  n_settled_markets?: number; traded_market_ids?: string[];
}
export interface DiscoveryCandidate {
  candidate_id: string; trial_number: number; family: string;
  parameters: Record<string, unknown>; status: CandidateStatus; error: string | null;
  objective: number | null; train_results: DiscoveryPeriodResult[];
  validation_results: DiscoveryPeriodResult[]; selected: boolean;
  rejection_reasons: string[]; rule_text?: string | null;
  rule?: Record<string, unknown> | null;
  search_parameters?: Record<string, unknown>; validation_status?: "completed" | "failed";
  validation_error?: string | null;
}
export interface DiscoverySplit {
  name: string; fold: Fold; t0_ms: number; t1_ms: number; market_ids: string[];
}
export interface CampaignSummary {
  campaign_id: string; status: CampaignStatus; dataset: string; dataset_hash: string;
  config: DiscoveryConfig; currency: string; created_at?: string;
  progress: { completed_trials: number; total_trials: number };
  error?: string | null;
}
export interface CampaignDetail extends CampaignSummary {
  splits: DiscoverySplit[]; candidates: DiscoveryCandidate[];
  selected_candidate_ids: string[]; limitations: string[];
  mining: Record<string, unknown> | null;
  baseline?: { name: string; pnl_cents: number; objective: number };
  objective_name?: string;
}
export interface CampaignRequest extends DiscoveryConfig { dataset: string; }
export interface CampaignJob extends Job { campaign_id: string | null; }

export interface CampaignAnalysis {
  campaign_id: string; status: "not_requested" | "queued" | "running" | "completed" | "failed";
  automatic_enabled: boolean; error: string | null; evidence_hash?: string; finished_at?: string;
  report: null | {
    summary: string; verdict: string;
    findings: { title: string; evidence: string; interpretation: string }[];
    next_tests: { priority: string; hypothesis: string; protocol: string; success_criterion: string }[];
    limitations: string[];
  };
}
