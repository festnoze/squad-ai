export interface BacktestMetrics {
  total_return: number;
  sharpe: number;
  max_dd: number;
  trades: number;
  win_rate: number;
  profit_factor: number;
}

export interface TimeSeriesPoint {
  date: string;
  value: number;
}

export interface BacktestResult {
  metrics: BacktestMetrics;
  portfolio_values: TimeSeriesPoint[];
  buy_hold_values: TimeSeriesPoint[];
  entries: string[]; // dates
  exits: string[];
  price_data: TimeSeriesPoint[];
}

export interface SweepResult {
  sharpe_matrix: number[][];
  fast_values: number[];
  slow_values: number[];
  best: { fast: number; slow: number; sharpe: number };
  stats: { mean: number; median: number; max: number; valid_count: number };
}

export interface GenerationUpdate {
  type: "generation";
  gen: number;
  nevals: number;
  avg: number;
  best: number;
  viable: number;
}

export interface EvolutionComplete {
  type: "complete";
  top_strategies: StrategyResult[];
}

export interface StrategyResult {
  rank: number;
  entry_expression: string;
  exit_expression: string;
  entry_size: number;
  exit_size: number;
  train_return: number;
  train_sharpe: number;
  train_drawdown: number;
  train_trades: number;
  test_return: number;
  test_sharpe: number;
  test_drawdown: number;
  test_trades: number;
  is_overfit: boolean;
}

export interface TickerInfo {
  name: string;
  currency: string;
  symbol: string;
}

export type TabId = "data" | "backtest" | "sweep" | "evolution" | "optimize" | "results";

export interface TabProps {
  globalParams: { symbol: string; interval: string; start: string; end: string };
  onGlobalParamsChange: (p: { symbol: string; interval: string; start: string; end: string }) => void;
  symbols: string[];
  onAddSymbol: (s: string) => void;
  onStatus: (msg: string) => void;
  setLoading: (v: boolean) => void;
}
