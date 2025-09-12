import { useState } from 'react'
import { useQuery } from 'react-query'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { RefreshCw, TrendingUp, TrendingDown } from 'lucide-react'

// Mock market data - in real app this would come from an API
const mockMarketData = [
  { symbol: 'BTCUSD', price: 43250.50, change: 1250.30, changePercent: 2.98 },
  { symbol: 'ETHUSD', price: 2680.75, change: -85.25, changePercent: -3.08 },
  { symbol: 'EURUSD', price: 1.0895, change: 0.0012, changePercent: 0.11 },
  { symbol: 'GBPUSD', price: 1.2734, change: -0.0043, changePercent: -0.34 },
  { symbol: 'USDJPY', price: 149.82, change: 0.76, changePercent: 0.51 }
]

export function MarketOverview() {
  const [refreshing, setRefreshing] = useState(false)

  // In a real app, this would fetch from market data API
  const { data: marketData = mockMarketData, refetch } = useQuery(
    'marketOverview',
    () => Promise.resolve(mockMarketData),
    {
      refetchInterval: 30000, // Refresh every 30 seconds
      staleTime: 15000 // Consider data stale after 15 seconds
    }
  )

  const handleRefresh = async () => {
    setRefreshing(true)
    await refetch()
    setTimeout(() => setRefreshing(false), 1000)
  }

  const formatPrice = (symbol: string, price: number) => {
    // Format based on asset type
    if (symbol.includes('USD') && !symbol.startsWith('USD')) {
      return `$${price.toLocaleString()}`
    } else if (symbol.startsWith('USD')) {
      return price.toFixed(2)
    } else {
      return price.toFixed(4)
    }
  }

  const formatChange = (change: number, symbol: string) => {
    const prefix = change >= 0 ? '+' : ''
    if (symbol.includes('USD') && !symbol.startsWith('USD')) {
      return `${prefix}$${change.toFixed(2)}`
    } else {
      return `${prefix}${change.toFixed(4)}`
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Market Overview
        </h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <div className="space-y-3">
        {marketData.map((item) => (
          <div
            key={item.symbol}
            className="flex items-center justify-between p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <div>
              <div className="font-medium text-gray-900 dark:text-white text-sm">
                {item.symbol}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {formatPrice(item.symbol, item.price)}
              </div>
            </div>
            
            <div className="text-right">
              <div className={`flex items-center space-x-1 text-sm ${
                item.change >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
              }`}>
                {item.change >= 0 ? (
                  <TrendingUp className="h-3 w-3" />
                ) : (
                  <TrendingDown className="h-3 w-3" />
                )}
                <span>{formatChange(item.change, item.symbol)}</span>
              </div>
              <div className={`text-xs ${
                item.changePercent >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
              }`}>
                {item.changePercent >= 0 ? '+' : ''}{item.changePercent.toFixed(2)}%
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-3 border-t border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-center text-xs text-gray-500 dark:text-gray-400">
          <div className="h-2 w-2 bg-green-500 rounded-full mr-2 animate-pulse"></div>
          Live market data • Updates every 30s
        </div>
      </div>
    </Card>
  )
}