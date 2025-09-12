import { ApiClient } from './api'
import type { ChartData } from '@/types'

export interface TechnicalIndicators {
  sma?: number[]
  ema?: number[]
  rsi?: number[]
  macd?: {
    macd: number[]
    signal: number[]
    histogram: number[]
  }
  bollinger_bands?: {
    upper: number[]
    middle: number[]
    lower: number[]
  }
}

export interface ChartPattern {
  type: string
  start_index: number
  end_index: number
  confidence: number
  description: string
}

export interface SupportResistanceLevel {
  level: number
  type: 'support' | 'resistance'
  strength: number
  touches: number[]
}

export interface VolatilityData {
  historical_volatility: number
  implied_volatility?: number
  volatility_percentile: number
  rolling_volatility: number[]
}

export interface MarketSummary {
  symbol: string
  price: number
  change: number
  change_percent: number
  volume: number
  high_24h: number
  low_24h: number
  market_cap?: number
  timestamp: string
}

export class ChartService {
  /**
   * List available chart files
   */
  static async listChartFiles(): Promise<string[]> {
    return ApiClient.get<string[]>('/api/charts/files')
  }

  /**
   * Get chart data with technical indicators
   */
  static async getChartData(
    symbol: string,
    interval: string = '1d',
    limit: number = 100,
    indicators?: string[]
  ): Promise<ChartData & { indicators?: TechnicalIndicators }> {
    const params: any = { symbol, interval, limit }
    if (indicators && indicators.length > 0) {
      params.indicators = indicators.join(',')
    }
    
    return ApiClient.get<ChartData & { indicators?: TechnicalIndicators }>('/api/charts/data', params)
  }

  /**
   * Get chart statistics
   */
  static async getChartStats(filename: string): Promise<any> {
    return ApiClient.get(`/api/charts/stats/${filename}`)
  }

  /**
   * Resample chart data to different interval
   */
  static async resampleChartData(filename: string, interval: string): Promise<ChartData> {
    return ApiClient.post<ChartData>('/api/charts/resample', { filename, interval })
  }

  /**
   * Calculate technical indicators
   */
  static async getIndicators(
    symbol: string,
    indicators: string[],
    period?: number,
    interval: string = '1d'
  ): Promise<TechnicalIndicators> {
    const data = {
      symbol,
      indicators,
      period,
      interval
    }
    
    return ApiClient.post<TechnicalIndicators>('/api/charts/indicators', data)
  }

  /**
   * Detect chart patterns
   */
  static async getPatterns(
    symbol: string,
    pattern_types?: string[],
    interval: string = '1d'
  ): Promise<ChartPattern[]> {
    const params: any = { symbol, interval }
    if (pattern_types && pattern_types.length > 0) {
      params.pattern_types = pattern_types.join(',')
    }
    
    return ApiClient.get<ChartPattern[]>('/api/charts/patterns', params)
  }

  /**
   * Get support and resistance levels
   */
  static async getSupportResistance(
    symbol: string,
    interval: string = '1d',
    lookback_periods: number = 50
  ): Promise<SupportResistanceLevel[]> {
    const params = {
      symbol,
      interval,
      lookback_periods
    }
    
    return ApiClient.get<SupportResistanceLevel[]>('/api/charts/support-resistance', params)
  }

  /**
   * Calculate price volatility
   */
  static async getVolatility(
    symbol: string,
    period: number = 20,
    interval: string = '1d'
  ): Promise<VolatilityData> {
    const params = {
      symbol,
      period,
      interval
    }
    
    return ApiClient.get<VolatilityData>('/api/charts/volatility', params)
  }

  /**
   * Get market summary for symbol
   */
  static async getMarketSummary(symbol: string): Promise<MarketSummary> {
    const params = { symbol }
    
    return ApiClient.get<MarketSummary>('/api/charts/market-summary', params)
  }
}