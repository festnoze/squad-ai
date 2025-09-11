import { MetricCard } from '@/components/common/MetricCard'
import { Wallet, TrendingUp, Target, Activity, Award } from 'lucide-react'
import type { PortfolioSummary as PortfolioSummaryType } from '@/types'

interface PortfolioSummaryProps {
  summary: PortfolioSummaryType
}

export function PortfolioSummary({ summary }: PortfolioSummaryProps) {
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value)
  }

  const formatPercentage = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
      <MetricCard
        title="Portfolio Balance"
        value={formatCurrency(summary.current_balance)}
        subtitle="Available cash"
        icon={<Wallet className="h-4 w-4" />}
        valueColor="neutral"
      />
      
      <MetricCard
        title="Total Equity"
        value={formatCurrency(summary.equity)}
        subtitle="Cash + unrealized P&L"
        change={summary.return_percentage}
        changeType="percentage"
        valueColor={summary.equity >= summary.current_balance ? 'positive' : 'negative'}
        icon={<TrendingUp className="h-4 w-4" />}
      />
      
      <MetricCard
        title="Total P&L"
        value={formatCurrency(summary.total_pnl)}
        subtitle={`Realized: ${formatCurrency(summary.realized_pnl)}`}
        valueColor={summary.total_pnl >= 0 ? 'positive' : 'negative'}
        icon={<Target className="h-4 w-4" />}
      />
      
      <MetricCard
        title="Open Trades"
        value={summary.open_trades}
        subtitle={`Total: ${summary.total_trades}`}
        icon={<Activity className="h-4 w-4" />}
      />
      
      <MetricCard
        title="Win Rate"
        value={formatPercentage(summary.win_rate)}
        subtitle={`Max DD: ${formatPercentage(summary.max_drawdown)}`}
        valueColor={summary.win_rate >= 50 ? 'positive' : 'negative'}
        icon={<Award className="h-4 w-4" />}
      />
    </div>
  )
}