import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Input'
import { 
  TrendingUp, 
  BarChart3, 
  Brain, 
  Download, 
  Play, 
  Pause 
} from 'lucide-react'
import { useTradingStore } from '@/stores/appStore'
import toast from 'react-hot-toast'

interface QuickActionsProps {
  availableCharts: string[]
  portfolioId?: string
}

export function QuickActions({ availableCharts }: Omit<QuickActionsProps, 'portfolioId'>) {
  const navigate = useNavigate()
  const { autoTradingEnabled, setAutoTradingEnabled } = useTradingStore()
  const [selectedChart, setSelectedChart] = useState('')

  const formatFilename = (filename: string) => {
    return filename
      .replace('.json', '')
      .replace(/_/g, ' ')
      .replace(/-/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }

  const handleQuickTrade = () => {
    if (!selectedChart) {
      toast.error('Please select a chart first')
      return
    }
    navigate('/trading')
  }

  const handleViewChart = () => {
    if (!selectedChart) {
      toast.error('Please select a chart first')
      return
    }
    navigate('/charts')
  }

  const handleToggleAutoTrading = () => {
    setAutoTradingEnabled(!autoTradingEnabled)
    toast.success(autoTradingEnabled ? 'Auto-trading disabled' : 'Auto-trading enabled')
  }

  return (
    <Card className="p-4">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        Quick Actions
      </h3>
      
      <div className="space-y-4">
        {/* Chart Selection */}
        <Select
          label="Select Chart"
          value={selectedChart}
          onChange={(e) => setSelectedChart(e.target.value)}
        >
          <option value="">Choose a chart...</option>
          {availableCharts.map((file) => (
            <option key={file} value={file}>
              {formatFilename(file)}
            </option>
          ))}
        </Select>

        {/* Action Buttons */}
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={handleQuickTrade}
            icon={<TrendingUp className="h-4 w-4" />}
            disabled={!selectedChart}
          >
            Quick Trade
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleViewChart}
            icon={<BarChart3 className="h-4 w-4" />}
            disabled={!selectedChart}
          >
            View Chart
          </Button>
        </div>

        {/* Navigation Buttons */}
        <div className="space-y-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/strategies')}
            icon={<Brain className="h-4 w-4" />}
            className="w-full justify-start"
          >
            Manage Strategies
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/settings')}
            icon={<Download className="h-4 w-4" />}
            className="w-full justify-start"
          >
            Download Data
          </Button>
        </div>

        {/* Auto Trading Toggle */}
        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Auto Trading
            </span>
            <div className={`h-2 w-2 rounded-full ${autoTradingEnabled ? 'bg-green-500' : 'bg-gray-400'}`}></div>
          </div>
          
          <Button
            variant={autoTradingEnabled ? 'danger' : 'success'}
            size="sm"
            onClick={handleToggleAutoTrading}
            icon={autoTradingEnabled ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            className="w-full"
          >
            {autoTradingEnabled ? 'Disable Auto Trading' : 'Enable Auto Trading'}
          </Button>
          
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            {autoTradingEnabled 
              ? 'Automated trading is active based on strategy signals'
              : 'Manual trading mode - trades require confirmation'
            }
          </p>
        </div>
      </div>
    </Card>
  )
}