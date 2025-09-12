import { ApiClient } from './api'
import type { StrategyConfig, BacktestRequest, BacktestResult, TradingSignal } from '@/types'

export interface StrategyPerformance {
  strategy_name: string
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  total_return: number
  sharpe_ratio: number
  max_drawdown: number
  profit_factor: number
  avg_trade_duration: number
  best_trade: number
  worst_trade: number
}

export interface StrategySignal extends TradingSignal {
  execution_price?: number
  execution_time?: string
  status: 'pending' | 'executed' | 'expired' | 'cancelled'
}

export interface StrategyExecution {
  strategy_name: string
  symbol: string
  status: 'running' | 'stopped' | 'paused'
  start_time: string
  signals_generated: number
  trades_executed: number
  current_pnl: number
  parameters: Record<string, any>
}

export class StrategyService {
  /**
   * List available strategies
   */
  static async getStrategies(): Promise<StrategyConfig[]> {
    return ApiClient.get<StrategyConfig[]>('/api/strategies/list')
  }

  /**
   * Run strategy backtest
   */
  static async runBacktest(request: BacktestRequest): Promise<BacktestResult> {
    return ApiClient.post<BacktestResult>('/api/strategies/backtest', request)
  }

  /**
   * Get trading signals from strategies
   */
  static async getSignals(
    strategyName?: string,
    symbol?: string,
    limit?: number
  ): Promise<StrategySignal[]> {
    const params: any = {}
    if (strategyName) params.strategy_name = strategyName
    if (symbol) params.symbol = symbol
    if (limit) params.limit = limit
    
    return ApiClient.get<StrategySignal[]>('/api/strategies/signals', params)
  }

  /**
   * Execute strategy on live data
   */
  static async executeStrategy(
    strategyName: string,
    symbol: string,
    parameters?: Record<string, any>
  ): Promise<StrategyExecution> {
    const data = {
      strategy_name: strategyName,
      symbol,
      parameters
    }
    
    return ApiClient.post<StrategyExecution>('/api/strategies/execute', data)
  }

  /**
   * Get strategy performance metrics
   */
  static async getPerformance(
    strategyName: string,
    symbol?: string,
    startDate?: string,
    endDate?: string
  ): Promise<StrategyPerformance> {
    const params: any = { strategy_name: strategyName }
    if (symbol) params.symbol = symbol
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    
    return ApiClient.get<StrategyPerformance>('/api/strategies/performance', params)
  }

  /**
   * Stop strategy execution
   */
  static async stopStrategy(strategyName: string, symbol?: string): Promise<{ message: string }> {
    const data: any = { strategy_name: strategyName }
    if (symbol) data.symbol = symbol
    
    return ApiClient.post<{ message: string }>('/api/strategies/stop', data)
  }

  /**
   * Pause strategy execution
   */
  static async pauseStrategy(strategyName: string, symbol?: string): Promise<{ message: string }> {
    const data: any = { strategy_name: strategyName }
    if (symbol) data.symbol = symbol
    
    return ApiClient.post<{ message: string }>('/api/strategies/pause', data)
  }

  /**
   * Resume strategy execution
   */
  static async resumeStrategy(strategyName: string, symbol?: string): Promise<{ message: string }> {
    const data: any = { strategy_name: strategyName }
    if (symbol) data.symbol = symbol
    
    return ApiClient.post<{ message: string }>('/api/strategies/resume', data)
  }

  /**
   * Get strategy configuration
   */
  static async getStrategyConfig(strategyName: string): Promise<StrategyConfig> {
    return ApiClient.get<StrategyConfig>(`/api/strategies/${strategyName}/config`)
  }

  /**
   * Update strategy configuration
   */
  static async updateStrategyConfig(
    strategyName: string,
    config: Partial<StrategyConfig>
  ): Promise<StrategyConfig> {
    return ApiClient.put<StrategyConfig>(`/api/strategies/${strategyName}/config`, config)
  }

  /**
   * Get active strategy executions
   */
  static async getActiveExecutions(): Promise<StrategyExecution[]> {
    return ApiClient.get<StrategyExecution[]>('/api/strategies/active')
  }

  /**
   * Get strategy execution history
   */
  static async getExecutionHistory(
    strategyName?: string,
    limit?: number
  ): Promise<StrategyExecution[]> {
    const params: any = {}
    if (strategyName) params.strategy_name = strategyName
    if (limit) params.limit = limit
    
    return ApiClient.get<StrategyExecution[]>('/api/strategies/history', params)
  }

  /**
   * Validate strategy parameters
   */
  static validateParameters(strategy: StrategyConfig, parameters: Record<string, any>): boolean {
    if (!strategy.parameters) return true
    
    for (const [key, value] of Object.entries(parameters)) {
      const paramConfig = strategy.parameters[key]
      if (!paramConfig) continue
      
      if (paramConfig.required && (value === undefined || value === null)) {
        return false
      }
      
      if (paramConfig.type === 'number' && typeof value !== 'number') {
        return false
      }
      
      if (paramConfig.min !== undefined && value < paramConfig.min) {
        return false
      }
      
      if (paramConfig.max !== undefined && value > paramConfig.max) {
        return false
      }
    }
    
    return true
  }

  /**
   * Calculate strategy statistics
   */
  static calculateStrategyStats(backtest: BacktestResult): StrategyPerformance {
    const winningTrades = backtest.winning_trades
    const losingTrades = backtest.losing_trades
    const totalTrades = backtest.total_trades
    
    const winRate = totalTrades > 0 ? (winningTrades / totalTrades) * 100 : 0
    const avgWin = winningTrades > 0 ? backtest.returns.filter(r => r > 0).reduce((sum, r) => sum + r, 0) / winningTrades : 0
    const avgLoss = losingTrades > 0 ? Math.abs(backtest.returns.filter(r => r < 0).reduce((sum, r) => sum + r, 0)) / losingTrades : 0
    const profitFactor = avgLoss > 0 ? avgWin / avgLoss : 0
    
    const bestTrade = Math.max(...backtest.returns)
    const worstTrade = Math.min(...backtest.returns)
    
    const avgTradeDuration = backtest.trades.length > 0 
      ? backtest.trades.reduce((sum, trade) => {
          const entry = new Date(trade.entry_time).getTime()
          const exit = new Date(trade.exit_time || Date.now()).getTime()
          return sum + (exit - entry)
        }, 0) / backtest.trades.length / (1000 * 60 * 60 * 24) // days
      : 0

    return {
      strategy_name: backtest.strategy_name,
      total_trades: totalTrades,
      winning_trades: winningTrades,
      losing_trades: losingTrades,
      win_rate: winRate,
      total_return: backtest.total_return,
      sharpe_ratio: backtest.sharpe_ratio,
      max_drawdown: backtest.max_drawdown,
      profit_factor: profitFactor,
      avg_trade_duration: avgTradeDuration,
      best_trade: bestTrade,
      worst_trade: worstTrade
    }
  }
}