import { ReactNode } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface MetricCardProps {
  title: string
  value: string | number
  subtitle?: string
  change?: number
  changeType?: 'currency' | 'percentage'
  icon?: ReactNode
  className?: string
  valueColor?: 'positive' | 'negative' | 'neutral'
}

export function MetricCard({
  title,
  value,
  subtitle,
  change,
  changeType = 'percentage',
  icon,
  className = '',
  valueColor = 'neutral'
}: MetricCardProps) {
  const getValueColorClass = () => {
    switch (valueColor) {
      case 'positive':
        return 'text-success-600 dark:text-success-400'
      case 'negative':
        return 'text-danger-600 dark:text-danger-400'
      default:
        return 'text-gray-900 dark:text-white'
    }
  }

  const getChangeColorClass = () => {
    if (change === undefined) return ''
    return change >= 0
      ? 'text-success-600 dark:text-success-400'
      : 'text-danger-600 dark:text-danger-400'
  }

  const formatChange = () => {
    if (change === undefined) return null
    
    const prefix = change >= 0 ? '+' : ''
    const suffix = changeType === 'percentage' ? '%' : ''
    
    return (
      <div className={`flex items-center space-x-1 ${getChangeColorClass()}`}>
        {change >= 0 ? (
          <TrendingUp className="h-3 w-3" />
        ) : (
          <TrendingDown className="h-3 w-3" />
        )}
        <span className="text-xs font-medium">
          {prefix}{Math.abs(change).toFixed(2)}{suffix}
        </span>
      </div>
    )
  }

  return (
    <div className={`metric-card ${className}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2">
            {icon && <div className="text-gray-500 dark:text-gray-400">{icon}</div>}
            <p className="metric-label">{title}</p>
          </div>
          
          <div className="mt-1">
            <p className={`metric-value ${getValueColorClass()}`}>
              {typeof value === 'number' ? value.toLocaleString() : value}
            </p>
            {subtitle && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        
        {change !== undefined && (
          <div className="ml-2">
            {formatChange()}
          </div>
        )}
      </div>
    </div>
  )
}