import { useState } from 'react'
import { useQuery } from 'react-query'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { PortfolioService } from '@/services/portfolioService'
import { Portfolio, PositionSummary } from '@/types'
import { PortfolioSummary } from '@/components/dashboard/PortfolioSummary'

export function PortfolioPage() {
  const [selectedPortfolio, setSelectedPortfolio] = useState<string | null>(null)

  const { data: portfolios = [], isLoading: portfoliosLoading } = useQuery<Portfolio[]>(
    'portfolios',
    PortfolioService.getPortfolios
  )

  const { data: portfolioSummary } = useQuery(
    ['portfolio-summary', selectedPortfolio],
    () => selectedPortfolio ? PortfolioService.getPortfolioSummary(selectedPortfolio) : undefined,
    {
      enabled: !!selectedPortfolio
    }
  )

  const { data: positions = [] } = useQuery<PositionSummary[]>(
    ['portfolio-positions', selectedPortfolio],
    () => selectedPortfolio ? PortfolioService.getPortfolioPositions(selectedPortfolio) : Promise.resolve([]),
    {
      enabled: !!selectedPortfolio
    }
  )

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Portfolio</h1>
        <Button>Create Portfolio</Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <Card className="p-6">
          <h3 className="text-lg font-semibold mb-4">Portfolio Selection</h3>
          {portfoliosLoading ? (
            <div>Loading portfolios...</div>
          ) : (
            <div className="space-y-2">
              {portfolios.map((portfolio) => (
                <div
                  key={portfolio.id}
                  className={`p-3 border rounded-lg cursor-pointer ${
                    selectedPortfolio === portfolio.id
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-300 hover:bg-gray-50'
                  }`}
                  onClick={() => setSelectedPortfolio(portfolio.id)}
                >
                  <div className="font-medium">{portfolio.name}</div>
                  <div className="text-sm text-gray-600">
                    ${portfolio.current_balance.toFixed(2)}
                  </div>
                  <div className={`text-sm ${
                    portfolio.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {portfolio.total_pnl >= 0 ? '+' : ''}${portfolio.total_pnl.toFixed(2)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="lg:col-span-3 space-y-6">
          {selectedPortfolio && portfolioSummary && portfolioSummary.portfolio && portfolioSummary.value && (
            <>
              <PortfolioSummary summary={{
                current_balance: portfolioSummary.value.cash_balance,
                equity: portfolioSummary.value.total_value,
                total_pnl: portfolioSummary.value.realized_pnl + portfolioSummary.value.unrealized_pnl,
                unrealized_pnl: portfolioSummary.value.unrealized_pnl,
                realized_pnl: portfolioSummary.value.realized_pnl,
                open_trades: 0, // This would need to be fetched separately
                total_trades: portfolioSummary.portfolio.total_trades,
                win_rate: portfolioSummary.portfolio.winning_trades / portfolioSummary.portfolio.total_trades * 100,
                return_percentage: portfolioSummary.totalReturn,
                max_drawdown: portfolioSummary.portfolio.max_drawdown
              }} />

              <Card className="p-6">
                <h3 className="text-lg font-semibold mb-4">Open Positions</h3>
                {positions.length === 0 ? (
                  <div className="text-gray-500 text-center py-8">
                    No open positions
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2">Symbol</th>
                          <th className="text-left py-2">Side</th>
                          <th className="text-left py-2">Positions</th>
                          <th className="text-left py-2">Units</th>
                          <th className="text-left py-2">Avg Price</th>
                          <th className="text-left py-2">Unrealized P&L</th>
                        </tr>
                      </thead>
                      <tbody>
                        {positions.map((position) => (
                          <tr key={position.symbol} className="border-b">
                            <td className="py-2 font-medium">{position.symbol}</td>
                            <td className="py-2">
                              <span className={`px-2 py-1 text-xs rounded-full ${
                                position.side === 'long' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                              }`}>
                                {position.side}
                              </span>
                            </td>
                            <td className="py-2">{position.open_positions}</td>
                            <td className="py-2">{position.total_units}</td>
                            <td className="py-2">${position.average_price.toFixed(2)}</td>
                            <td className={`py-2 ${
                              position.unrealized_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {position.unrealized_pnl >= 0 ? '+' : ''}${position.unrealized_pnl.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <Card className="p-6">
                <h3 className="text-lg font-semibold mb-4">Portfolio Details</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <div className="text-sm text-gray-600">Total Trades</div>
                    <div className="text-lg font-semibold">{portfolioSummary.portfolio.total_trades}</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">Win Rate</div>
                    <div className="text-lg font-semibold">{(portfolioSummary.portfolio.winning_trades / portfolioSummary.portfolio.total_trades * 100).toFixed(1)}%</div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">Return</div>
                    <div className={`text-lg font-semibold ${
                      portfolioSummary.totalReturn >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {portfolioSummary.totalReturn >= 0 ? '+' : ''}{portfolioSummary.totalReturn.toFixed(2)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-600">Max Drawdown</div>
                    <div className="text-lg font-semibold text-red-600">
                      {portfolioSummary.portfolio.max_drawdown.toFixed(2)}%
                    </div>
                  </div>
                </div>
              </Card>
            </>
          )}

          {!selectedPortfolio && (
            <Card className="p-6">
              <div className="text-center py-12">
                <div className="text-gray-500 mb-4">Select a portfolio to view details</div>
                <Button>Create New Portfolio</Button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}