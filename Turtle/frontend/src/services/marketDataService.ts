import { ApiClient } from './api'
import type { ChartData, PriceData } from '@/types'

export interface DataSourceConfig {
  name: string
  description: string
  type: string
  supported_intervals: string[]
  api_key_required?: boolean
  rate_limit?: number
}

export interface MarketDataParams {
  symbol: string
  interval?: string
  limit?: number
  start_date?: string
  end_date?: string
}

export interface MultiSymbolData {
  [symbol: string]: ChartData
}

export class MarketDataService {
  /**
   * List available data sources
   */
  static async getDataSources(): Promise<DataSourceConfig[]> {
    return ApiClient.get<DataSourceConfig[]>('/api/market-data/sources')
  }

  /**
   * Get Binance cryptocurrency data
   */
  static async getBinanceData(params: MarketDataParams): Promise<ChartData> {
    return ApiClient.get<ChartData>('/api/market-data/binance', params)
  }

  /**
   * Get Yahoo Finance stock data
   */
  static async getYahooData(params: MarketDataParams): Promise<ChartData> {
    return ApiClient.get<ChartData>('/api/market-data/yahoo', params)
  }

  /**
   * Get Alpha Vantage API data
   */
  static async getAlphaVantageData(params: MarketDataParams): Promise<ChartData> {
    return ApiClient.get<ChartData>('/api/market-data/alpha-vantage', params)
  }

  /**
   * Generate synthetic data for testing
   */
  static async getSyntheticData(params: MarketDataParams): Promise<ChartData> {
    return ApiClient.get<ChartData>('/api/market-data/synthetic', params)
  }

  /**
   * Get chart data from any source
   */
  static async getChartData(
    source: string,
    params: MarketDataParams
  ): Promise<ChartData> {
    const requestParams = { source, ...params }
    return ApiClient.get<ChartData>('/api/market-data/chart-data', requestParams)
  }

  /**
   * Get current price for symbol
   */
  static async getLatestPrice(symbol: string, source?: string): Promise<PriceData> {
    const params: any = { symbol }
    if (source) params.source = source
    
    return ApiClient.get<PriceData>('/api/market-data/latest-price', params)
  }

  /**
   * Get data for multiple symbols
   */
  static async getMultipleSymbols(
    symbols: string[],
    source?: string,
    interval?: string
  ): Promise<MultiSymbolData> {
    const data: any = { symbols }
    if (source) data.source = source
    if (interval) data.interval = interval
    
    return ApiClient.post<MultiSymbolData>('/api/market-data/multiple-symbols', data)
  }

  /**
   * Get available symbols for a data source
   */
  static async getAvailableSymbols(source: string): Promise<string[]> {
    const params = { source }
    return ApiClient.get<string[]>('/api/market-data/symbols', params)
  }

  /**
   * Test connection to a data source
   */
  static async testDataSource(source: string): Promise<{ success: boolean; message: string }> {
    const params = { source }
    return ApiClient.get<{ success: boolean; message: string }>('/api/market-data/test', params)
  }
}