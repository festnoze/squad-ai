import { ApiClient } from './api'
import type { Portfolio, PortfolioRequest, PortfolioResponse, PortfolioPerformance, Trade } from '@/types'

export interface PortfolioValue {
  total_value: number
  cash_balance: number
  positions_value: number
  unrealized_pnl: number
  realized_pnl: number
}

export interface PortfolioMetrics {
  total_return: number
  annualized_return: number
  volatility: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  calmar_ratio: number
}

export interface DrawdownData {
  current_drawdown: number
  max_drawdown: number
  drawdown_duration: number
  recovery_time?: number
  drawdown_periods: Array<{
    start_date: string
    end_date: string
    max_drawdown: number
    recovery_date?: string
  }>
}

export interface RiskMetrics {
  var_95: number
  var_99: number
  cvar_95: number
  cvar_99: number
  beta?: number
  alpha?: number
  information_ratio?: number
  tracking_error?: number
}

export interface RebalanceRecommendation {
  symbol: string
  current_weight: number
  target_weight: number
  recommended_action: 'buy' | 'sell' | 'hold'
  quantity: number
  value: number
}

export class PortfolioService {
  /**
   * List all portfolios
   */
  static async getPortfolios(): Promise<Portfolio[]> {
    return ApiClient.get<Portfolio[]>('/api/portfolio/list')
  }

  /**
   * Get portfolio positions
   */
  static async getPortfolioPositions(portfolioId: string): Promise<any[]> {
    return ApiClient.get<any[]>(`/api/portfolio/${portfolioId}/positions`)
  }

  /**
   * Get portfolio performance data
   */
  static async getPortfolioPerformance(portfolioId: string): Promise<PortfolioPerformance> {
    return ApiClient.get<PortfolioPerformance>(`/api/portfolio/${portfolioId}/performance`)
  }

  /**
   * Create new portfolio
   */
  static async createPortfolio(request: PortfolioRequest): Promise<PortfolioResponse> {
    return ApiClient.post<PortfolioResponse>('/api/portfolio/create', request)
  }

  /**
   * Get portfolio by ID
   */
  static async getPortfolio(portfolioId: string): Promise<Portfolio> {
    return ApiClient.get<Portfolio>(`/api/portfolio/${portfolioId}`)
  }

  /**
   * Update portfolio balance
   */
  static async updateBalance(
    portfolioId: string, 
    newBalance: number, 
    reason?: string
  ): Promise<Portfolio> {
    const data = { balance: newBalance, reason }
    return ApiClient.put<Portfolio>(`/api/portfolio/${portfolioId}/balance`, data)
  }

  /**
   * Add trade to portfolio
   */
  static async addTrade(portfolioId: string, trade: Trade): Promise<Portfolio> {
    return ApiClient.post<Portfolio>(`/api/portfolio/${portfolioId}/trade`, trade)
  }

  /**
   * Get portfolio trades
   */
  static async getPortfolioTrades(
    portfolioId: string,
    limit?: number,
    offset?: number
  ): Promise<Trade[]> {
    const params: any = {}
    if (limit) params.limit = limit
    if (offset) params.offset = offset
    
    return ApiClient.get<Trade[]>(`/api/portfolio/${portfolioId}/trades`, params)
  }

  /**
   * Calculate total portfolio value
   */
  static async getPortfolioValue(portfolioId: string): Promise<PortfolioValue> {
    return ApiClient.get<PortfolioValue>(`/api/portfolio/${portfolioId}/value`)
  }

  /**
   * Get performance metrics
   */
  static async getPerformance(
    portfolioId: string,
    startDate?: string,
    endDate?: string
  ): Promise<PortfolioPerformance> {
    const params: any = {}
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    
    return ApiClient.get<PortfolioPerformance>(`/api/portfolio/${portfolioId}/performance`, params)
  }

  /**
   * Calculate portfolio drawdown
   */
  static async getDrawdown(portfolioId: string): Promise<DrawdownData> {
    return ApiClient.get<DrawdownData>(`/api/portfolio/${portfolioId}/drawdown`)
  }

  /**
   * Get risk metrics
   */
  static async getRiskMetrics(
    portfolioId: string,
    benchmark?: string
  ): Promise<RiskMetrics> {
    const params = benchmark ? { benchmark } : {}
    return ApiClient.get<RiskMetrics>(`/api/portfolio/${portfolioId}/risk-metrics`, params)
  }

  /**
   * Generate rebalancing trades
   */
  static async getRebalanceRecommendations(
    portfolioId: string,
    targetWeights: Record<string, number>
  ): Promise<RebalanceRecommendation[]> {
    const data = { target_weights: targetWeights }
    return ApiClient.post<RebalanceRecommendation[]>(`/api/portfolio/${portfolioId}/rebalance`, data)
  }

  /**
   * Delete portfolio
   */
  static async deletePortfolio(portfolioId: string): Promise<{ message: string }> {
    return ApiClient.delete<{ message: string }>(`/api/portfolio/${portfolioId}`)
  }

  /**
   * Get portfolio summary statistics
   */
  static async getPortfolioSummary(portfolioId: string) {
    const [portfolio, value, performance] = await Promise.all([
      this.getPortfolio(portfolioId),
      this.getPortfolioValue(portfolioId),
      this.getPerformance(portfolioId)
    ])

    return {
      portfolio,
      value,
      performance,
      totalReturn: ((value.total_value - portfolio.initial_balance) / portfolio.initial_balance) * 100
    }
  }

  /**
   * Calculate position size based on portfolio risk
   */
  static calculatePositionSize(
    portfolioValue: number,
    riskPerTrade: number,
    entryPrice: number,
    stopLoss: number
  ): number {
    const riskAmount = portfolioValue * (riskPerTrade / 100)
    const riskPerShare = Math.abs(entryPrice - stopLoss)
    
    if (riskPerShare === 0) return 0
    
    return Math.floor(riskAmount / riskPerShare)
  }
}