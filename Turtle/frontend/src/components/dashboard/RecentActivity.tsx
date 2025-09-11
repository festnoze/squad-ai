import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { TrendingUp, TrendingDown, Clock, Activity } from 'lucide-react'
import type { Trade, TradingSignal } from '@/types'

interface RecentActivityProps {
  trades: Trade[]
  signals: TradingSignal[]
}

export function RecentActivity({ trades, signals }: RecentActivityProps) {
  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value)
  }

  const getTradeIcon = (tradeType: string) => {
    return tradeType === 'long' 
      ? <TrendingUp className="h-4 w-4 text-green-500" />
      : <TrendingDown className="h-4 w-4 text-red-500" />
  }

  const getSignalIcon = (signalType: string) => {
    switch (signalType) {
      case 'entry':
        return <TrendingUp className="h-4 w-4 text-blue-500" />
      case 'exit':
        return <TrendingDown className="h-4 w-4 text-orange-500" />
      default:
        return <Activity className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'success' | 'warning' | 'danger' | 'secondary'> = {
      open: 'success',
      closed: 'secondary',
      pending: 'warning',
      cancelled: 'danger'
    }
    return variants[status] || 'secondary'
  }

  // Combine and sort recent activity
  const recentActivity = [
    ...trades.slice(0, 5).map(trade => ({
      id: trade.id,
      type: 'trade' as const,
      timestamp: trade.entry_time,
      data: trade
    })),
    ...signals.slice(0, 5).map(signal => ({
      id: signal.id,
      type: 'signal' as const,
      timestamp: signal.timestamp,
      data: signal
    }))
  ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, 8)

  return (
    <Card className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Recent Activity
        </h3>
        <div className="flex items-center space-x-2 text-sm text-gray-500 dark:text-gray-400">
          <Clock className="h-4 w-4" />
          <span>Last 24 hours</span>
        </div>
      </div>

      {recentActivity.length === 0 ? (
        <div className="text-center py-8">
          <Activity className="h-8 w-8 text-gray-400 mx-auto mb-2" />
          <p className="text-gray-500 dark:text-gray-400">No recent activity</p>
        </div>
      ) : (
        <div className="space-y-3">
          {recentActivity.map((item) => (
            <div key={`${item.type}-${item.id}`} className="flex items-center space-x-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
              <div className="flex-shrink-0">
                {item.type === 'trade' 
                  ? getTradeIcon(item.data.trade_type)
                  : getSignalIcon(item.data.signal_type)
                }
              </div>
              
              <div className="flex-1 min-w-0">
                {item.type === 'trade' ? (
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-medium text-gray-900 dark:text-white">
                        {item.data.trade_type.toUpperCase()} {item.data.symbol}
                      </span>
                      <Badge variant={getStatusBadge(item.data.status)}>
                        {item.data.status}
                      </Badge>
                    </div>
                    <div className="flex items-center space-x-2 text-xs text-gray-500 dark:text-gray-400">
                      <span>{formatCurrency(item.data.entry_price)}</span>
                      <span>•</span>
                      <span>{item.data.quantity} units</span>
                      {item.data.realized_pnl !== 0 && (
                        <>
                          <span>•</span>
                          <span className={item.data.realized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                            {formatCurrency(item.data.realized_pnl)}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-medium text-gray-900 dark:text-white">
                        {item.data.signal_type.toUpperCase()} signal for {item.data.symbol}
                      </span>
                      <Badge variant="secondary">
                        {(item.data.confidence * 100).toFixed(0)}%
                      </Badge>
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {item.data.reason} • {formatCurrency(item.data.price)}
                    </div>
                  </div>
                )}
              </div>
              
              <div className="flex-shrink-0 text-xs text-gray-400 dark:text-gray-500">
                {formatTime(item.timestamp)}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}