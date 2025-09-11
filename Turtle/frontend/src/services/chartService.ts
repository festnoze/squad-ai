import { ApiClient } from './api'
import type { ChartData, ChartDataRequest, ChartDataResponse, ChartMetadata } from '@/types'

export class ChartService {
  /**
   * List all available chart files
   */
  static async listChartFiles(): Promise<string[]> {
    return ApiClient.get<string[]>('/api/charts')
  }

  /**
   * Get chart data from file
   */
  static async getChartData(filename: string): Promise<ChartData> {
    return ApiClient.get<ChartData>(`/api/charts/${filename}`)
  }

  /**
   * Download new chart data
   */
  static async downloadChartData(request: ChartDataRequest): Promise<ChartDataResponse> {
    return ApiClient.post<ChartDataResponse>('/api/charts/download', request)
  }

  /**
   * Resample chart data to different timeframe
   */
  static async resampleChartData(filename: string, targetPeriod: string): Promise<ChartData> {
    return ApiClient.post<ChartData>('/api/charts/resample', null, {
      params: { filename, target_period: targetPeriod }
    })
  }

  /**
   * Delete a chart file
   */
  static async deleteChartFile(filename: string): Promise<{ message: string }> {
    return ApiClient.delete<{ message: string }>(`/api/charts/${filename}`)
  }

  /**
   * Get chart metadata without loading full data
   */
  static async getChartMetadata(filename: string): Promise<ChartMetadata> {
    return ApiClient.get<ChartMetadata>(`/api/charts/metadata/${filename}`)
  }

  /**
   * Upload chart data file
   */
  static async uploadChartData(file: File): Promise<ChartDataResponse> {
    const formData = new FormData()
    formData.append('file', file)
    
    return ApiClient.post<ChartDataResponse>('/api/charts/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  }

  /**
   * Get chart statistics
   */
  static async getChartStats(filename: string) {
    const chartData = await this.getChartData(filename)
    const candles = chartData.candles
    
    if (candles.length === 0) {
      return null
    }

    const prices = candles.map(c => c.close)
    const volumes = candles.map(c => c.volume || 0)
    
    const minPrice = Math.min(...prices)
    const maxPrice = Math.max(...prices)
    const avgPrice = prices.reduce((sum, price) => sum + price, 0) / prices.length
    const totalVolume = volumes.reduce((sum, vol) => sum + vol, 0)
    
    const firstCandle = candles[0]
    const lastCandle = candles[candles.length - 1]
    const priceChange = lastCandle.close - firstCandle.close
    const priceChangePercent = (priceChange / firstCandle.close) * 100

    return {
      symbol: chartData.metadata.symbol || chartData.metadata.asset_name,
      totalCandles: candles.length,
      dateRange: {
        start: firstCandle.timestamp,
        end: lastCandle.timestamp
      },
      priceStats: {
        min: minPrice,
        max: maxPrice,
        average: avgPrice,
        change: priceChange,
        changePercent: priceChangePercent
      },
      volumeStats: {
        total: totalVolume,
        average: totalVolume / candles.length
      }
    }
  }
}