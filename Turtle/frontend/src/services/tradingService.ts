import { ApiClient } from './api'
import type {
  Trade,
  TradeRequest,
  TradeResponse,
  TradingSignal,
  StrategyConfig,
  BacktestRequest,
  BacktestResult
} from '@/types'
import { TradeStatus, TradeType } from '@/types'

export interface Position {
  symbol: string
  quantity: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
  side: 'long' | 'short'
  entry_time: string
}

export interface PerformanceMetrics {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_pnl: number
  avg_win: number
  avg_loss: number
  profit_factor: number
  max_drawdown: number
  sharpe_ratio: number
  return_percentage: number
}

export interface PositionCalculation {
  symbol: string
  position_size: number
  risk_amount: number
  entry_price: number
  stop_loss: number
  take_profit?: number
  risk_reward_ratio: number
}

export interface StopTarget {
  trade_id: string
  symbol: string
  current_price: number
  stop_loss: number
  take_profit?: number
  should_close: boolean
  reason: string
}

export class TradingService {
  /**
   * Get trading strategies
   */
  static async getStrategies(): Promise<StrategyConfig[]> {
    return ApiClient.get<StrategyConfig[]>('/api/trading/strategies')
  }

  /**
   * Get trading signals
   */
  static async getSignals(
    symbol?: string,
    limit: number = 100
  ): Promise<TradingSignal[]> {
    const params: any = { limit }
    if (symbol) params.symbol = symbol
    
    return ApiClient.get<TradingSignal[]>('/api/trading/signals', params)
  }

  /**
   * Get backtest results
   */
  static async getBacktestResults(
    strategyName: string,
    symbol?: string
  ): Promise<BacktestResult[]> {
    const params: any = { strategy_name: strategyName }
    if (symbol) params.symbol = symbol
    
    return ApiClient.get<BacktestResult[]>('/api/trading/backtest/results', params)
  }

  /**
   * Run backtest
   */
  static async runBacktest(request: BacktestRequest): Promise<BacktestResult> {
    return ApiClient.post<BacktestResult>('/api/trading/backtest', request)
  }

  /**
   * Activate strategy
   */
  static async activateStrategy(strategyName: string): Promise<{ success: boolean }> {
    return ApiClient.post<{ success: boolean }>('/api/trading/strategy/activate', { 
      strategy_name: strategyName 
    })
  }

  /**
   * Deactivate strategy
   */
  static async deactivateStrategy(strategyName: string): Promise<{ success: boolean }> {
    return ApiClient.post<{ success: boolean }>('/api/trading/strategy/deactivate', { 
      strategy_name: strategyName 
    })
  }

  /**
   * Start auto trading
   */
  static async startAutoTrading(): Promise<{ success: boolean }> {
    return ApiClient.post<{ success: boolean }>('/api/trading/auto/start', {})
  }

  /**
   * Stop auto trading
   */
  static async stopAutoTrading(): Promise<{ success: boolean }> {
    return ApiClient.post<{ success: boolean }>('/api/trading/auto/stop', {})
  }

  /**
   * Get all trades (open/closed)
   */
  static async getTrades(
    status?: 'open' | 'closed' | 'all',
    symbol?: string,
    limit: number = 100
  ): Promise<Trade[]> {
    const params: any = { limit }
    if (status && status !== 'all') params.status = status
    if (symbol) params.symbol = symbol
    
    return ApiClient.get<Trade[]>('/api/trading/trades', params)
  }

  /**
   * Create new trade
   */
  static async createTrade(request: TradeRequest): Promise<TradeResponse> {
    return ApiClient.post<TradeResponse>('/api/trading/trade', request)
  }

  /**
   * Close existing trade
   */
  static async closeTrade(tradeId: string, exitPrice?: number): Promise<TradeResponse> {
    const data: any = { trade_id: tradeId }
    if (exitPrice) data.exit_price = exitPrice
    
    return ApiClient.post<TradeResponse>('/api/trading/close', data)
  }

  /**
   * Get open positions
   */
  static async getPositions(symbol?: string): Promise<Position[]> {
    const params = symbol ? { symbol } : {}
    return ApiClient.get<Position[]>('/api/trading/positions', params)
  }

  /**
   * Get trading performance statistics
   */
  static async getPerformance(
    symbol?: string,
    startDate?: string,
    endDate?: string
  ): Promise<PerformanceMetrics> {
    const params: any = {}
    if (symbol) params.symbol = symbol
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    
    return ApiClient.get<PerformanceMetrics>('/api/trading/performance', params)
  }

  /**
   * Check stop losses and take profits
   */
  static async checkStopsTargets(symbol?: string): Promise<StopTarget[]> {
    const params = symbol ? { symbol } : {}
    return ApiClient.get<StopTarget[]>('/api/trading/stops-targets', params)
  }

  /**
   * Calculate position size based on risk
   */
  static async calculatePosition(
    symbol: string,
    entryPrice: number,
    stopLoss: number,
    riskAmount: number,
    takeProfit?: number
  ): Promise<PositionCalculation> {
    const data = {
      symbol,
      entry_price: entryPrice,
      stop_loss: stopLoss,
      risk_amount: riskAmount,
      take_profit: takeProfit
    }
    
    return ApiClient.post<PositionCalculation>('/api/trading/calculate-position', data)
  }

  /**
   * WebSocket connection for real-time trade updates
   */
  static connectWebSocket(onMessage: (data: any) => void): WebSocket | null {
    try {
      const wsUrl = (import.meta as any).env?.VITE_WS_URL || 'ws://localhost:8000/api/trading/ws'
      const ws = new WebSocket(wsUrl)
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          onMessage(data)
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }
      
      ws.onclose = () => {
        console.log('WebSocket connection closed')
      }
      
      return ws
    } catch (error) {
      console.error('Error creating WebSocket connection:', error)
      return null
    }
  }

  /**
   * Calculate position size based on risk management
   */
  static calculatePositionSize(
    accountBalance: number,
    riskPerTrade: number,
    entryPrice: number,
    stopLoss: number
  ): number {
    const riskAmount = accountBalance * riskPerTrade
    const riskPerShare = Math.abs(entryPrice - stopLoss)
    
    if (riskPerShare === 0) return 0
    
    return Math.floor(riskAmount / riskPerShare)
  }

  /**
   * Calculate trade P&L
   */
  static calculatePnL(
    trade: Trade,
    currentPrice?: number
  ): { realizedPnL: number; unrealizedPnL: number } {
    let realizedPnL = 0
    let unrealizedPnL = 0

    if (trade.status === TradeStatus.CLOSED && trade.exit_price) {
      if (trade.trade_type === TradeType.LONG) {
        realizedPnL = (trade.exit_price - trade.entry_price) * trade.quantity
      } else {
        realizedPnL = (trade.entry_price - trade.exit_price) * trade.quantity
      }
    } else if (trade.status === TradeStatus.OPEN && currentPrice) {
      if (trade.trade_type === TradeType.LONG) {
        unrealizedPnL = (currentPrice - trade.entry_price) * trade.quantity
      } else {
        unrealizedPnL = (trade.entry_price - currentPrice) * trade.quantity
      }
    }

    return { realizedPnL, unrealizedPnL }
  }
}