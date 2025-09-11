import { useState } from 'react'
import { useQuery } from 'react-query'
import { PortfolioSummary } from './PortfolioSummary'
import { QuickActions } from './QuickActions'
import { RecentActivity } from './RecentActivity'
import { PerformanceOverview } from './PerformanceOverview'
import { MarketOverview } from './MarketOverview'
import { Card } from '@/components/ui/Card'
import { PortfolioService } from '@/services/portfolioService'
import { TradingService } from '@/services/tradingService'
import { ChartService } from '@/services/chartService'
import { useAppStore } from '@/stores/appStore'
import type { PortfolioSummary as PortfolioSummaryType, Trade, TradingSignal } from '@/types'

export function Dashboard() {
  const { selectedPortfolio } = useAppStore()
  const [timeRange, setTimeRange] = useState<'1d' | '7d' | '30d' | '90d'>('30d')

  // Get default portfolio ID if none selected
  const { data: portfolios = [] } = useQuery('portfolios', PortfolioService.listPortfolios)
  const portfolioId = selectedPortfolio || portfolios[0]?.id

  // Portfolio summary
  const { data: portfolioSummary, isLoading: portfolioLoading } = useQuery<PortfolioSummaryType>(
    ['portfolioSummary', portfolioId],
    () => portfolioId ? PortfolioService.getPortfolioSummary(portfolioId) : null,
    { enabled: !!portfolioId }
  )

  // Recent trades
  const { data: recentTrades = [] } = useQuery<Trade[]>(
    'recentTrades',
    () => TradingService.getTrades(undefined, undefined, 10),
    { refetchInterval: 30000 } // Refresh every 30 seconds
  )

  // Recent signals
  const { data: recentSignals = [] } = useQuery<TradingSignal[]>(
    'recentSignals',
    () => TradingService.getSignals(undefined, undefined, 10),
    { refetchInterval: 30000 }
  )

  // Available chart files
  const { data: chartFiles = [] } = useQuery('chartFiles', ChartService.listChartFiles)

  // Portfolio performance
  const { data: performance } = useQuery(
    ['portfolioPerformance', portfolioId, timeRange],
    () => portfolioId ? PortfolioService.getPortfolioPerformance(portfolioId, getTimeRangeDays(timeRange)) : null,
    { enabled: !!portfolioId }
  )

  function getTimeRangeDays(range: string): number {
    switch (range) {
      case '1d': return 1
      case '7d': return 7
      case '30d': return 30
      case '90d': return 90
      default: return 30
    }
  }

  if (portfolioLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner"></div>
        <span className="ml-2 text-gray-600 dark:text-gray-400">Loading dashboard...</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Trading Dashboard
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Overview of your trading performance and market activity
          </p>
        </div>
        
        {/* Time Range Selector */}
        <div className="mt-4 sm:mt-0">
          <div className="flex space-x-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
            {['1d', '7d', '30d', '90d'].map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range as any)}
                className={`px-3 py-1 text-sm font-medium rounded transition-colors ${
                  timeRange === range
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                {range.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Portfolio Summary */}
      {portfolioSummary && (
        <PortfolioSummary summary={portfolioSummary} />
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column */}
        <div className="lg:col-span-2 space-y-6">
          {/* Performance Overview */}
          {performance && (
            <PerformanceOverview 
              performance={performance} 
              timeRange={timeRange}
            />
          )}

          {/* Recent Activity */}
          <RecentActivity 
            trades={recentTrades} 
            signals={recentSignals} 
          />
        </div>

        {/* Right Column */}
        <div className="space-y-6">
          {/* Quick Actions */}
          <QuickActions 
            availableCharts={chartFiles}
            portfolioId={portfolioId}
          />

          {/* Market Overview */}
          <MarketOverview />

          {/* System Status */}
          <Card className="p-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
              System Status
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600 dark:text-gray-400">API Connection</span>
                <div className="flex items-center space-x-2">
                  <div className="h-2 w-2 bg-green-500 rounded-full"></div>
                  <span className="text-sm text-green-600 dark:text-green-400">Connected</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600 dark:text-gray-400">Data Feed</span>
                <div className="flex items-center space-x-2">
                  <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse"></div>
                  <span className="text-sm text-green-600 dark:text-green-400">Live</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600 dark:text-gray-400">Trading Engine</span>
                <div className="flex items-center space-x-2">
                  <div className="h-2 w-2 bg-yellow-500 rounded-full"></div>
                  <span className="text-sm text-yellow-600 dark:text-yellow-400">Standby</span>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}