import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { useQuery } from 'react-query'
import { TradingService } from '@/services/tradingService'
import { StrategyConfig, TradingSignal, Trade } from '@/types'

export function TradingPage() {
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null)
  const [autoTradingEnabled, setAutoTradingEnabled] = useState(false)

  const { data: strategies = [], isLoading: strategiesLoading } = useQuery<StrategyConfig[]>(
    'strategies',
    TradingService.getStrategies
  )

  const { data: signals = [] } = useQuery<TradingSignal[]>(
    'trading-signals',
    () => TradingService.getSignals()
  )

  const { data: trades = [] } = useQuery<Trade[]>(
    'trades',
    () => TradingService.getTrades()
  )

  const handleToggleAutoTrading = async () => {
    if (!selectedStrategy) return
    
    try {
      if (autoTradingEnabled) {
        await TradingService.stopAutoTrading()
      } else {
        await TradingService.startAutoTrading()
      }
      setAutoTradingEnabled(!autoTradingEnabled)
    } catch (error) {
      console.error('Error toggling auto trading:', error)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Trading</h1>
        <Button 
          onClick={handleToggleAutoTrading}
          disabled={!selectedStrategy}
          variant={autoTradingEnabled ? 'destructive' : 'default'}
        >
          {autoTradingEnabled ? 'Stop Auto Trading' : 'Start Auto Trading'}
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Strategy Selection</h3>
          {strategiesLoading ? (
            <div>Loading strategies...</div>
          ) : (
            <div className="space-y-2">
              {strategies.map((strategy) => (
                <div
                  key={strategy.name}
                  className={`p-3 border rounded-lg cursor-pointer ${
                    selectedStrategy === strategy.name
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-300 hover:bg-gray-50'
                  }`}
                  onClick={() => setSelectedStrategy(strategy.name)}
                >
                  <div className="font-medium">{strategy.name}</div>
                  {strategy.description && (
                    <div className="text-sm text-gray-600">{strategy.description}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Recent Signals</h3>
          <div className="space-y-3">
            {signals.slice(0, 5).map((signal: TradingSignal) => (
              <div key={signal.id} className="border-l-4 border-blue-500 pl-3">
                <div className="font-medium">{signal.symbol}</div>
                <div className="text-sm text-gray-600">
                  {signal.signal_type} - {signal.trade_type}
                </div>
                <div className="text-sm text-gray-500">
                  ${signal.price.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Active Trades</h3>
          <div className="space-y-3">
            {trades.filter((trade: Trade) => trade.status === 'open').slice(0, 5).map((trade: Trade) => (
              <div key={trade.id} className="border-l-4 border-green-500 pl-3">
                <div className="font-medium">{trade.symbol}</div>
                <div className="text-sm text-gray-600">
                  {trade.trade_type} - {trade.quantity} units
                </div>
                <div className={`text-sm ${
                  trade.unrealized_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  P&L: ${trade.unrealized_pnl.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">Trade History</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2">Symbol</th>
                <th className="text-left py-2">Type</th>
                <th className="text-left py-2">Quantity</th>
                <th className="text-left py-2">Entry Price</th>
                <th className="text-left py-2">Exit Price</th>
                <th className="text-left py-2">P&L</th>
                <th className="text-left py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade: Trade) => (
                <tr key={trade.id} className="border-b">
                  <td className="py-2">{trade.symbol}</td>
                  <td className="py-2">{trade.trade_type}</td>
                  <td className="py-2">{trade.quantity}</td>
                  <td className="py-2">${trade.entry_price.toFixed(2)}</td>
                  <td className="py-2">
                    {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '-'}
                  </td>
                  <td className={`py-2 ${
                    trade.realized_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    ${trade.realized_pnl.toFixed(2)}
                  </td>
                  <td className="py-2">
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      trade.status === 'open' ? 'bg-green-100 text-green-800' :
                      trade.status === 'closed' ? 'bg-gray-100 text-gray-800' :
                      'bg-yellow-100 text-yellow-800'
                    }`}>
                      {trade.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}