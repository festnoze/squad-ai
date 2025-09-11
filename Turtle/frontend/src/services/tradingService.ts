import { ApiClient } from './api'
import type {
  Trade,
  TradeRequest,
  TradeResponse,
  TradingSignal,
  TradeStatus
} from '@/types'

export class TradingService {
  /**
   * Get trades with optional filtering
   */
  static async getTrades(
    symbol?: string,
    status?: TradeStatus,
    limit: number = 100
  ): Promise<Trade[]> {
    const params: any = { limit }
    if (symbol) params.symbol = symbol
    if (status) params.status = status
    
    return ApiClient.get<Trade[]>('/api/trading/trades', params)
  }

  /**
   * Get trade by ID
   */
  static async getTrade(tradeId: string): Promise<Trade> {
    return ApiClient.get<Trade>(`/api/trading/trades/${tradeId}`)
  }

  /**
   * Create a new trade
   */
  static async createTrade(request: TradeRequest): Promise<TradeResponse> {
    return ApiClient.post<TradeResponse>('/api/trading/trades', request)
  }

  /**
   * Close an open trade
   */
  static async closeTrade(tradeId: string, exitPrice?: number): Promise<TradeResponse> {
    const data = exitPrice ? { exit_price: exitPrice } : {}
    return ApiClient.put<TradeResponse>(`/api/trading/trades/${tradeId}/close`, data)
  }

  /**
   * Cancel a pending trade
   */
  static async cancelTrade(tradeId: string): Promise<{ message: string }> {
    return ApiClient.delete<{ message: string }>(`/api/trading/trades/${tradeId}`)
  }

  /**
   * Get trading signals with optional filtering
   */
  static async getSignals(
    symbol?: string,
    strategy?: string,
    limit: number = 50
  ): Promise<TradingSignal[]> {
    const params: any = { limit }
    if (symbol) params.symbol = symbol
    if (strategy) params.strategy = strategy
    
    return ApiClient.get<TradingSignal[]>('/api/trading/signals', params)
  }

  /**
   * Process market data and generate trading signals
   */
  static async processMarketData(
    symbol: string,
    strategyName?: string
  ): Promise<{ signals: TradingSignal[]; count: number }> {
    const data: any = { symbol }
    if (strategyName) data.strategy_name = strategyName
    
    return ApiClient.post<{ signals: TradingSignal[]; count: number }>(
      '/api/trading/signals/process',
      data
    )
  }

  /**
   * Get current positions
   */
  static async getPositions(symbol?: string): Promise<any[]> {
    const params = symbol ? { symbol } : {}
    return ApiClient.get<any[]>('/api/trading/positions', params)
  }

  /**
   * Enable automatic trading for a strategy
   */
  static async enableAutoTrading(strategyName: string, symbol: string): Promise<{ message: string }> {
    return ApiClient.post<{ message: string }>(`/api/trading/auto-trade/${strategyName}`, { symbol })
  }

  /**
   * Disable automatic trading for a strategy
   */
  static async disableAutoTrading(strategyName: string, symbol?: string): Promise<{ message: string }> {
    const data = symbol ? { symbol } : {}
    return ApiClient.delete<{ message: string }>(`/api/trading/auto-trade/${strategyName}`, data)
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

    if (trade.status === 'closed' && trade.exit_price) {
      // Calculate realized P&L
      if (trade.trade_type === 'long') {
        realizedPnL = (trade.exit_price - trade.entry_price) * trade.quantity
      } else {
        realizedPnL = (trade.entry_price - trade.exit_price) * trade.quantity
      }
    } else if (trade.status === 'open' && currentPrice) {
      // Calculate unrealized P&L
      if (trade.trade_type === 'long') {
        unrealizedPnL = (currentPrice - trade.entry_price) * trade.quantity
      } else {
        unrealizedPnL = (trade.entry_price - currentPrice) * trade.quantity
      }
    }

    return { realizedPnL, unrealizedPnL }
  }

  /**
   * Get trade statistics
   */
  static getTradeStats(trades: Trade[]) {
    const totalTrades = trades.length
    const openTrades = trades.filter(t => t.status === 'open').length
    const closedTrades = trades.filter(t => t.status === 'closed')
    
    const winningTrades = closedTrades.filter(t => t.realized_pnl > 0).length
    const losingTrades = closedTrades.filter(t => t.realized_pnl < 0).length
    
    const totalPnL = closedTrades.reduce((sum, trade) => sum + trade.realized_pnl, 0)
    const winRate = closedTrades.length > 0 ? (winningTrades / closedTrades.length) * 100 : 0
    
    const avgWin = winningTrades > 0 
      ? closedTrades.filter(t => t.realized_pnl > 0).reduce((sum, t) => sum + t.realized_pnl, 0) / winningTrades 
      : 0
    
    const avgLoss = losingTrades > 0 
      ? Math.abs(closedTrades.filter(t => t.realized_pnl < 0).reduce((sum, t) => sum + t.realized_pnl, 0)) / losingTrades 
      : 0

    return {
      totalTrades,
      openTrades,
      closedTrades: closedTrades.length,
      winningTrades,
      losingTrades,
      winRate,
      totalPnL,
      avgWin,
      avgLoss,
      profitFactor: avgLoss > 0 ? avgWin / avgLoss : 0
    }
  }
}