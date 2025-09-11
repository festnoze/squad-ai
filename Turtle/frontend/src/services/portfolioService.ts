import { ApiClient } from './api'
import type {
  Portfolio,
  PortfolioSummary,
  PortfolioRequest,
  PortfolioResponse,
  PositionSummary,
  PortfolioPerformance
} from '@/types'

export class PortfolioService {
  /**
   * List all portfolios
   */
  static async listPortfolios(): Promise<Portfolio[]> {
    return ApiClient.get<Portfolio[]>('/api/portfolio')
  }

  /**
   * Get portfolio by ID
   */
  static async getPortfolio(portfolioId: string): Promise<Portfolio> {
    return ApiClient.get<Portfolio>(`/api/portfolio/${portfolioId}`)
  }

  /**
   * Create a new portfolio
   */
  static async createPortfolio(request: PortfolioRequest): Promise<PortfolioResponse> {
    return ApiClient.post<PortfolioResponse>('/api/portfolio', request)
  }

  /**
   * Update portfolio settings
   */
  static async updatePortfolio(portfolioId: string, request: PortfolioRequest): Promise<PortfolioResponse> {
    return ApiClient.put<PortfolioResponse>(`/api/portfolio/${portfolioId}`, request)
  }

  /**
   * Delete a portfolio
   */
  static async deletePortfolio(portfolioId: string): Promise<{ message: string }> {
    return ApiClient.delete<{ message: string }>(`/api/portfolio/${portfolioId}`)
  }

  /**
   * Get portfolio summary with key metrics
   */
  static async getPortfolioSummary(portfolioId: string): Promise<PortfolioSummary> {
    return ApiClient.get<PortfolioSummary>(`/api/portfolio/${portfolioId}/summary`)
  }

  /**
   * Get portfolio positions
   */
  static async getPortfolioPositions(portfolioId: string): Promise<PositionSummary[]> {
    return ApiClient.get<PositionSummary[]>(`/api/portfolio/${portfolioId}/positions`)
  }

  /**
   * Get position summary for a specific symbol
   */
  static async getPositionSummary(portfolioId: string, symbol: string): Promise<PositionSummary> {
    return ApiClient.get<PositionSummary>(`/api/portfolio/${portfolioId}/positions/${symbol}`)
  }

  /**
   * Get portfolio performance metrics over time
   */
  static async getPortfolioPerformance(portfolioId: string, days: number = 30): Promise<PortfolioPerformance> {
    return ApiClient.get<PortfolioPerformance>(`/api/portfolio/${portfolioId}/performance`, { days })
  }

  /**
   * Reset portfolio to initial state
   */
  static async resetPortfolio(portfolioId: string): Promise<{ message: string }> {
    return ApiClient.post<{ message: string }>(`/api/portfolio/${portfolioId}/reset`)
  }

  /**
   * Update portfolio balance and currency
   */
  static async updatePortfolioBalance(
    portfolioId: string,
    newBalance: number,
    currency?: string
  ): Promise<{ message: string }> {
    return ApiClient.post<{ message: string }>(`/api/portfolio/${portfolioId}/update-balance`, {
      new_balance: newBalance,
      currency
    })
  }

  /**
   * Get portfolio risk metrics
   */
  static async getRiskMetrics(portfolioId: string): Promise<any> {
    return ApiClient.get<any>(`/api/portfolio/${portfolioId}/risk-metrics`)
  }

  /**
   * Calculate portfolio allocation
   */
  static calculateAllocation(positions: PositionSummary[], totalValue: number) {
    return positions.map(position => {
      const allocation = totalValue > 0 ? (Math.abs(position.unrealized_pnl) / totalValue) * 100 : 0
      return {
        ...position,
        allocation
      }
    })
  }

  /**
   * Get portfolio statistics
   */
  static getPortfolioStats(portfolio: Portfolio) {
    const winRate = portfolio.total_trades > 0 ? (portfolio.winning_trades / portfolio.total_trades) * 100 : 0
    const lossRate = 100 - winRate
    const avgWin = portfolio.winning_trades > 0 ? portfolio.realized_pnl / portfolio.winning_trades : 0
    const avgLoss = portfolio.losing_trades > 0 ? Math.abs(portfolio.realized_pnl) / portfolio.losing_trades : 0
    const profitFactor = avgLoss > 0 ? avgWin / avgLoss : 0

    return {
      winRate,
      lossRate,
      avgWin,
      avgLoss,
      profitFactor,
      totalReturn: ((portfolio.current_balance - portfolio.initial_balance) / portfolio.initial_balance) * 100,
      sharpeRatio: 0, // Would need daily returns to calculate
      maxDrawdown: portfolio.max_drawdown
    }
  }
}