import { useState, useEffect } from 'react'
import { useQuery } from 'react-query'
import { toast } from 'react-hot-toast'
import { ChartControls } from './ChartControls'
import { CandlestickChart } from './CandlestickChart'
import { MetricCard } from '@/components/common/MetricCard'
import { Card } from '@/components/ui/Card'
import { ChartService } from '@/services/chartService'
import { useChartStore } from '@/stores/appStore'
import type { ChartData } from '@/types'
import { BarChart3, Clock, TrendingUp, Volume2 } from 'lucide-react'

export function ChartsPage() {
  const {
    selectedChartFile,
    selectedInterval,
    setSelectedChartFile,
    setSelectedInterval
  } = useChartStore()

  const [chartData, setChartData] = useState<ChartData | null>(null)
  const [chartStats, setChartStats] = useState<any>(null)

  // Query for available chart files
  const { data: chartFiles = [], isLoading: filesLoading, refetch: refetchFiles } = useQuery(
    'chartFiles',
    ChartService.listChartFiles,
    {
      onError: (error) => {
        toast.error('Failed to load chart files')
        console.error('Chart files error:', error)
      }
    }
  )

  // Query for chart data when file is selected
  const { data: loadedChartData, isLoading: chartLoading, refetch: refetchChart } = useQuery(
    ['chartData', selectedChartFile],
    () => selectedChartFile ? ChartService.getChartData(selectedChartFile) : null,
    {
      enabled: !!selectedChartFile,
      onSuccess: (data) => {
        if (data) {
          setChartData(data)
          // Load chart statistics
          ChartService.getChartStats(selectedChartFile!).then(setChartStats)
        }
      },
      onError: (error) => {
        toast.error('Failed to load chart data')
        console.error('Chart data error:', error)
      }
    }
  )

  // Get available intervals based on chart data
  const getAvailableIntervals = () => {
    if (!chartData) return ['1d']
    
    const nativePeriod = chartData.metadata.period_duration
    const hierarchy = ['1min', '5min', '15min', '1h', '4h', '12h', '1d', '1w']
    const nativeIndex = hierarchy.indexOf(nativePeriod)
    
    return nativeIndex >= 0 ? hierarchy.slice(nativeIndex) : hierarchy
  }

  // Handle file selection
  const handleFileChange = (filename: string) => {
    if (filename) {
      setSelectedChartFile(filename)
    }
  }

  // Handle interval change
  const handleIntervalChange = (interval: string) => {
    setSelectedInterval(interval)
    
    // If interval is different from native, resample the data
    if (chartData && interval !== chartData.metadata.period_duration) {
      ChartService.resampleChartData(selectedChartFile!, interval)
        .then((resampledData) => {
          setChartData({
            ...resampledData,
            metadata: {
              ...resampledData.metadata,
              period_duration: interval
            }
          })
        })
        .catch((error) => {
          toast.error('Failed to resample chart data')
          console.error('Resample error:', error)
        })
    }
  }

  // Handle refresh
  const handleRefresh = () => {
    refetchFiles()
    if (selectedChartFile) {
      refetchChart()
    }
  }

  // Handle download (placeholder)
  const handleDownload = () => {
    toast.info('Download functionality will be implemented')
  }

  // Auto-select first file if none selected
  useEffect(() => {
    if (chartFiles.length > 0 && !selectedChartFile) {
      setSelectedChartFile(chartFiles[0])
    }
  }, [chartFiles, selectedChartFile, setSelectedChartFile])

  const isLoading = filesLoading || chartLoading

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Charts
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Interactive candlestick charts with trading analysis
        </p>
      </div>

      {/* Chart Controls */}
      <ChartControls
        selectedInterval={selectedInterval}
        onIntervalChange={handleIntervalChange}
        availableIntervals={getAvailableIntervals()}
        selectedFile={selectedChartFile}
        onFileChange={handleFileChange}
        availableFiles={chartFiles}
        onRefresh={handleRefresh}
        onDownload={handleDownload}
        loading={isLoading}
      />

      {/* Chart Statistics */}
      {chartStats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Price Range"
            value={`${chartStats.priceStats.min.toFixed(2)} - ${chartStats.priceStats.max.toFixed(2)}`}
            subtitle={chartData?.metadata.currency}
            icon={<BarChart3 className="h-4 w-4" />}
          />
          <MetricCard
            title="Price Change"
            value={`${chartStats.priceStats.change.toFixed(2)}`}
            change={chartStats.priceStats.changePercent}
            changeType="percentage"
            valueColor={chartStats.priceStats.change >= 0 ? 'positive' : 'negative'}
            icon={<TrendingUp className="h-4 w-4" />}
          />
          <MetricCard
            title="Total Candles"
            value={chartStats.totalCandles.toLocaleString()}
            subtitle={`${selectedInterval} intervals`}
            icon={<Clock className="h-4 w-4" />}
          />
          <MetricCard
            title="Avg Volume"
            value={chartStats.volumeStats.average.toLocaleString()}
            subtitle="Per period"
            icon={<Volume2 className="h-4 w-4" />}
          />
        </div>
      )}

      {/* Main Chart */}
      <Card className="p-6">
        {isLoading ? (
          <div className="flex items-center justify-center h-96">
            <div className="spinner"></div>
            <span className="ml-2 text-gray-600 dark:text-gray-400">
              Loading chart data...
            </span>
          </div>
        ) : chartData ? (
          <CandlestickChart
            data={chartData}
            height={500}
            showVolume={true}
          />
        ) : (
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <BarChart3 className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600 dark:text-gray-400">
                {chartFiles.length === 0 
                  ? 'No chart files available. Download some data to get started.'
                  : 'Select a chart file to view the data.'
                }
              </p>
            </div>
          </div>
        )}
      </Card>

      {/* Chart Information */}
      {chartData && (
        <Card className="p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Chart Information
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="font-medium text-gray-700 dark:text-gray-300">Asset:</span>
              <span className="ml-2 text-gray-600 dark:text-gray-400">
                {chartData.metadata.asset_name}
              </span>
            </div>
            <div>
              <span className="font-medium text-gray-700 dark:text-gray-300">Currency:</span>
              <span className="ml-2 text-gray-600 dark:text-gray-400">
                {chartData.metadata.currency}
              </span>
            </div>
            <div>
              <span className="font-medium text-gray-700 dark:text-gray-300">Period:</span>
              <span className="ml-2 text-gray-600 dark:text-gray-400">
                {chartData.metadata.period_duration}
              </span>
            </div>
            {chartStats && (
              <>
                <div>
                  <span className="font-medium text-gray-700 dark:text-gray-300">Date Range:</span>
                  <span className="ml-2 text-gray-600 dark:text-gray-400">
                    {new Date(chartStats.dateRange.start).toLocaleDateString()} - {new Date(chartStats.dateRange.end).toLocaleDateString()}
                  </span>
                </div>
                <div>
                  <span className="font-medium text-gray-700 dark:text-gray-300">Avg Price:</span>
                  <span className="ml-2 text-gray-600 dark:text-gray-400">
                    {chartStats.priceStats.average.toFixed(2)} {chartData.metadata.currency}
                  </span>
                </div>
                <div>
                  <span className="font-medium text-gray-700 dark:text-gray-300">Total Volume:</span>
                  <span className="ml-2 text-gray-600 dark:text-gray-400">
                    {chartStats.volumeStats.total.toLocaleString()}
                  </span>
                </div>
              </>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}