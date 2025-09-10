// Core trading types
export interface Candle {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface ChartMetadata {
  asset_name: string
  currency: string
  period_duration: string
  symbol?: string
  exchange?: string
}

export interface ChartData {
  metadata: ChartMetadata
  candles: Candle[]
}

export interface ChartDataRequest {
  symbol: string
  interval?: string
  limit?: number
  start_date?: string
  end_date?: string
}

export interface ChartDataResponse {
  success: boolean
  message?: string
  data?: ChartData
  filename?: string
}

// Trading types
export enum TradeType {
  LONG = 'long',
  SHORT = 'short'
}

export enum TradeStatus {
  OPEN = 'open',
  CLOSED = 'closed',
  PENDING = 'pending',
  CANCELLED = 'cancelled'
}

export interface Trade {
  id: string
  symbol: string
  trade_type: TradeType
  status: TradeStatus
  entry_price: number
  entry_time: string
  quantity: number
  exit_price?: number
  exit_time?: string
  stop_loss?: number
  take_profit?: number
  realized_pnl: number
  unrealized_pnl: number
  strategy_name?: string
  notes?: string
}

export interface TradeRequest {
  symbol: string
  trade_type: TradeType
  quantity: number
  price?: number
  stop_loss?: number
  take_profit?: number
  strategy_name?: string
}

export interface TradeResponse {
  success: boolean
  message?: string
  trade?: Trade
}

// Portfolio types
export interface Portfolio {
  id: string
  name: string
  initial_balance: number
  current_balance: number
  currency: string
  total_value: number
  unrealized_pnl: number
  realized_pnl: number
  total_pnl: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  max_drawdown: number
  risk_per_trade: number
}

export interface PortfolioSummary {
  current_balance: number
  equity: number
  total_pnl: number
  unrealized_pnl: number
  realized_pnl: number
  open_trades: number
  total_trades: number
  win_rate: number
  return_percentage: number
  max_drawdown: number
}

export interface PositionSummary {
  symbol: string
  open_positions: number
  total_units: number
  average_price: number
  unrealized_pnl: number
  side: string
}

export interface PortfolioPerformance {
  daily_returns: number[]
  cumulative_returns: number[]
  equity_curve: number[]
  dates: string[]
  sharpe_ratio: number
  max_drawdown: number
  volatility: number
}

// Strategy types
export enum SignalType {
  ENTRY = 'entry',
  EXIT = 'exit',
  PYRAMID = 'pyramid',
  STOP_LOSS = 'stop_loss',
  TAKE_PROFIT = 'take_profit'
}

export interface TradingSignal {
  id: string
  symbol: string
  signal_type: SignalType
  trade_type: TradeType
  price: number
  confidence: number
  quantity: number
  reason: string
  timestamp: string
  strategy_name: string
  stop_loss?: number
  take_profit?: number
  metadata?: Record<string, any>
}

export interface StrategyConfig {
  name: string
  description?: string
  version?: string
  parameters?: Record<string, any>
  entry_rules?: string[]
  exit_rules?: string[]
  max_position_size?: number
  stop_loss_pct?: number
  take_profit_pct?: number
  timeframes?: string[]
  is_active?: boolean
  created_at?: string
}

export interface BacktestRequest {
  strategy_name: string
  symbol: string
  start_date: string
  end_date: string
  initial_balance?: number
  parameters?: Record<string, any>
}

export interface BacktestResult {
  strategy_name: string
  symbol: string
  start_date: string
  end_date: string
  initial_balance: number
  final_balance: number
  total_return: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  max_drawdown: number
  sharpe_ratio: number
  trades: any[]
  signals: TradingSignal[]
  equity_curve: number[]
  returns: number[]
  dates: string[]
}

// Market data types
export interface TradingPair {
  symbol: string
  asset_name: string
  currency: string
  base?: string
  quote?: string
}

export interface DataSource {
  name: string
  description: string
  type: string
  supported_intervals: string[]
}

export interface PriceData {
  symbol: string
  price: number
  change: number
  change_percent: number
  timestamp: string
}

// API response types
export interface ApiResponse<T = any> {
  success: boolean
  message?: string
  data?: T
}

export interface PaginatedResponse<T = any> extends ApiResponse<T[]> {
  total: number
  page: number
  size: number
  pages: number
}

// UI State types
export interface AppState {
  sidebarOpen: boolean
  darkMode: boolean
  selectedPortfolio: string | null
  activeStrategy: string | null
}

export interface ChartState {
  selectedSymbol: string | null
  selectedInterval: string
  selectedChartFile: string | null
}

export interface TradingState {
  autoTradingEnabled: boolean
  selectedStrategy: string | null
  riskPerTrade: number
}

// Utility types
export type SortDirection = 'asc' | 'desc'

export interface SortConfig {
  key: string
  direction: SortDirection
}

export interface FilterConfig {
  [key: string]: any
}

export interface TableColumn<T = any> {
  key: keyof T
  label: string
  sortable?: boolean
  render?: (value: any, item: T) => React.ReactNode
}

// WebSocket types
export interface WebSocketMessage {
  type: string
  data: any
  timestamp: string
}

export interface RealtimeUpdate {
  type: 'trade' | 'signal' | 'portfolio' | 'price'
  data: any
}