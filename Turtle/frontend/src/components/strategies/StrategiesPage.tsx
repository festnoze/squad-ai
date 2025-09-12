import { useState } from 'react'
import { useQuery } from 'react-query'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { TradingService } from '@/services/tradingService'
import { StrategyConfig, BacktestResult } from '@/types'

export function StrategiesPage() {
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null)
  const [backtestConfig, setBacktestConfig] = useState({
    symbol: 'BTCUSDT',
    startDate: '',
    endDate: '',
    initialBalance: 10000
  })

  const { data: strategies = [], isLoading: strategiesLoading, refetch } = useQuery<StrategyConfig[]>(
    'strategies',
    TradingService.getStrategies
  )

  const { data: backtestResults = [] } = useQuery<BacktestResult[]>(
    ['backtest-results', selectedStrategy],
    () => selectedStrategy ? TradingService.getBacktestResults(selectedStrategy) : Promise.resolve([]),
    {
      enabled: !!selectedStrategy
    }
  )

  const handleRunBacktest = async () => {
    if (!selectedStrategy) return
    
    try {
      await TradingService.runBacktest({
        strategy_name: selectedStrategy,
        symbol: backtestConfig.symbol,
        start_date: backtestConfig.startDate,
        end_date: backtestConfig.endDate,
        initial_balance: backtestConfig.initialBalance
      })
      // Refetch results after running backtest
      refetch()
    } catch (error) {
      console.error('Error running backtest:', error)
    }
  }

  const handleActivateStrategy = async (strategyName: string, isActive: boolean) => {
    try {
      if (isActive) {
        await TradingService.activateStrategy(strategyName)
      } else {
        await TradingService.deactivateStrategy(strategyName)
      }
      refetch()
    } catch (error) {
      console.error('Error updating strategy status:', error)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Strategies</h1>
        <Button>Create Strategy</Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Available Strategies</h3>
          {strategiesLoading ? (
            <div>Loading strategies...</div>
          ) : (
            <div className="space-y-3">
              {strategies.map((strategy) => (
                <div
                  key={strategy.name}
                  className={`p-4 border rounded-lg ${
                    selectedStrategy === strategy.name
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-300'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <div
                      className="cursor-pointer flex-1"
                      onClick={() => setSelectedStrategy(strategy.name)}
                    >
                      <div className="font-medium">{strategy.name}</div>
                      {strategy.description && (
                        <div className="text-sm text-gray-600 mt-1">
                          {strategy.description}
                        </div>
                      )}
                      {strategy.version && (
                        <div className="text-xs text-gray-500 mt-1">
                          v{strategy.version}
                        </div>
                      )}
                    </div>
                    <Button
                      size="sm"
                      variant={strategy.is_active ? 'destructive' : 'default'}
                      onClick={() => handleActivateStrategy(strategy.name, !strategy.is_active)}
                    >
                      {strategy.is_active ? 'Deactivate' : 'Activate'}
                    </Button>
                  </div>
                  
                  {strategy.parameters && (
                    <div className="mt-3 p-2 bg-gray-50 rounded text-xs">
                      <div className="font-medium mb-1">Parameters:</div>
                      <div className="space-y-1">
                        {Object.entries(strategy.parameters).map(([key, value]) => (
                          <div key={key} className="flex justify-between">
                            <span>{key}:</span>
                            <span>{String(value)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Backtest Configuration</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Symbol</label>
              <Input
                value={backtestConfig.symbol}
                onChange={(e) => setBacktestConfig(prev => ({ ...prev, symbol: e.target.value }))}
                placeholder="BTCUSDT"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Start Date</label>
              <Input
                type="date"
                value={backtestConfig.startDate}
                onChange={(e) => setBacktestConfig(prev => ({ ...prev, startDate: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">End Date</label>
              <Input
                type="date"
                value={backtestConfig.endDate}
                onChange={(e) => setBacktestConfig(prev => ({ ...prev, endDate: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Initial Balance</label>
              <Input
                type="number"
                value={backtestConfig.initialBalance}
                onChange={(e) => setBacktestConfig(prev => ({ ...prev, initialBalance: Number(e.target.value) }))}
              />
            </div>
            <Button
              onClick={handleRunBacktest}
              disabled={!selectedStrategy}
              className="w-full"
            >
              Run Backtest
            </Button>
          </div>
        </Card>

        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Backtest Results</h3>
          {!selectedStrategy ? (
            <div className="text-gray-500">Select a strategy to view backtest results</div>
          ) : backtestResults.length === 0 ? (
            <div className="text-gray-500">No backtest results available</div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm text-gray-600">Total Return</div>
                  <div className={`text-lg font-semibold ${
                    (backtestResults[0]?.total_return ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {(backtestResults[0]?.total_return ?? 0) >= 0 ? '+' : ''}{(backtestResults[0]?.total_return ?? 0).toFixed(2)}%
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Win Rate</div>
                  <div className="text-lg font-semibold">{(backtestResults[0]?.win_rate ?? 0).toFixed(1)}%</div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Total Trades</div>
                  <div className="text-lg font-semibold">{backtestResults[0]?.total_trades ?? 0}</div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Max Drawdown</div>
                  <div className="text-lg font-semibold text-red-600">
                    {(backtestResults[0]?.max_drawdown ?? 0).toFixed(2)}%
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Sharpe Ratio</div>
                  <div className="text-lg font-semibold">{(backtestResults[0]?.sharpe_ratio ?? 0).toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-sm text-gray-600">Final Balance</div>
                  <div className="text-lg font-semibold">${(backtestResults[0]?.final_balance ?? 0).toLocaleString()}</div>
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>

      {selectedStrategy && backtestResults && (
        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Trade Details</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2">Symbol</th>
                  <th className="text-left py-2">Type</th>
                  <th className="text-left py-2">Entry</th>
                  <th className="text-left py-2">Exit</th>
                  <th className="text-left py-2">Quantity</th>
                  <th className="text-left py-2">P&L</th>
                  <th className="text-left py-2">Return %</th>
                </tr>
              </thead>
              <tbody>
                {(backtestResults[0]?.trades ?? []).slice(0, 10).map((trade: any, index: number) => (
                  <tr key={index} className="border-b">
                    <td className="py-2">{trade.symbol || backtestResults[0]?.symbol || 'N/A'}</td>
                    <td className="py-2">{trade.type || 'long'}</td>
                    <td className="py-2">${trade.entry_price?.toFixed(2) || 'N/A'}</td>
                    <td className="py-2">${trade.exit_price?.toFixed(2) || 'N/A'}</td>
                    <td className="py-2">{trade.quantity || 'N/A'}</td>
                    <td className={`py-2 ${
                      (trade.pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      ${(trade.pnl || 0).toFixed(2)}
                    </td>
                    <td className={`py-2 ${
                      (trade.return_pct || 0) >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {(trade.return_pct || 0).toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}