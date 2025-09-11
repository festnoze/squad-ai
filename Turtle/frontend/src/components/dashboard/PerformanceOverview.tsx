import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'
import { Card } from '@/components/ui/Card'
import type { PortfolioPerformance } from '@/types'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

interface PerformanceOverviewProps {
  performance: PortfolioPerformance
  timeRange: string
}

export function PerformanceOverview({ performance, timeRange }: PerformanceOverviewProps) {
  const chartData = {
    labels: performance.dates,
    datasets: [
      {
        label: 'Equity Curve',
        data: performance.equity_curve,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        borderWidth: 2,
        fill: true,
        tension: 0.1,
        pointRadius: 0,
        pointHoverRadius: 4
      },
      {
        label: 'Cumulative Returns',
        data: performance.cumulative_returns.map(r => r * 100),
        borderColor: '#10b981',
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        pointRadius: 0,
        pointHoverRadius: 4,
        yAxisID: 'percentage'
      }
    ]
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      title: {
        display: true,
        text: `Portfolio Performance - ${timeRange.toUpperCase()}`,
        font: {
          size: 16,
          weight: 'bold' as const
        }
      },
      legend: {
        position: 'top' as const,
      },
      tooltip: {
        mode: 'index' as const,
        intersect: false,
        callbacks: {
          title: (context: any) => {
            return new Date(context[0].label).toLocaleDateString()
          },
          label: (context: any) => {
            const label = context.dataset.label || ''
            if (label === 'Equity Curve') {
              return `${label}: $${context.parsed.y.toLocaleString()}`
            } else {
              return `${label}: ${context.parsed.y.toFixed(2)}%`
            }
          }
        }
      }
    },
    scales: {
      x: {
        display: true,
        title: {
          display: true,
          text: 'Date'
        }
      },
      y: {
        type: 'linear' as const,
        display: true,
        position: 'left' as const,
        title: {
          display: true,
          text: 'Portfolio Value ($)'
        },
        ticks: {
          callback: function(value: any) {
            return '$' + value.toLocaleString()
          }
        }
      },
      percentage: {
        type: 'linear' as const,
        display: true,
        position: 'right' as const,
        title: {
          display: true,
          text: 'Cumulative Return (%)'
        },
        grid: {
          drawOnChartArea: false,
        },
        ticks: {
          callback: function(value: any) {
            return value.toFixed(1) + '%'
          }
        }
      }
    }
  }

  const formatMetric = (value: number, isPercentage = false) => {
    if (isPercentage) {
      return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
    }
    return value.toFixed(2)
  }

  return (
    <Card className="p-6">
      <div className="h-80 mb-6">
        <Line data={chartData} options={options} />
      </div>
      
      {/* Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {formatMetric(performance.sharpe_ratio)}
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400">Sharpe Ratio</div>
        </div>
        
        <div className="text-center">
          <div className={`text-2xl font-bold ${performance.max_drawdown < 0 ? 'text-red-600' : 'text-gray-900 dark:text-white'}`}>
            {formatMetric(performance.max_drawdown, true)}
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400">Max Drawdown</div>
        </div>
        
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {formatMetric(performance.volatility, true)}
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400">Volatility</div>
        </div>
      </div>
    </Card>
  )
}