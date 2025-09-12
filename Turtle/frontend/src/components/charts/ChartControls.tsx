import { Select, Button } from '@/components/ui'
import { Download, RefreshCw, Settings, TrendingUp } from 'lucide-react'

interface ChartControlsProps {
  selectedInterval: string
  onIntervalChange: (interval: string) => void
  availableIntervals: string[]
  selectedFile: string | null
  onFileChange: (filename: string) => void
  availableFiles: string[]
  onRefresh: () => void
  onDownload: () => void
  loading?: boolean
}

const INTERVAL_LABELS: Record<string, string> = {
  '1min': '1 Minute',
  '5min': '5 Minutes',
  '15min': '15 Minutes',
  '1h': '1 Hour',
  '4h': '4 Hours',
  '12h': '12 Hours',
  '1d': '1 Day',
  '1w': '1 Week'
}

export function ChartControls({
  selectedInterval,
  onIntervalChange,
  availableIntervals,
  selectedFile,
  onFileChange,
  availableFiles,
  onRefresh,
  onDownload,
  loading = false
}: ChartControlsProps) {
  const formatFilename = (filename: string) => {
    // Remove .json extension and format for display
    return filename
      .replace('.json', '')
      .replace(/_/g, ' ')
      .replace(/-/g, ' ')
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4 mb-6">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between space-y-4 lg:space-y-0 lg:space-x-4">
        {/* Chart Selection */}
        <div className="flex flex-col sm:flex-row sm:items-center space-y-2 sm:space-y-0 sm:space-x-4">
          <div className="min-w-0 flex-1">
            <Select
              value={selectedFile || ''}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onFileChange(e.target.value)}
            >
              <option value="">Select a chart file...</option>
              {availableFiles.map((file) => (
                <option key={file} value={file}>
                  {formatFilename(file)}
                </option>
              ))}
            </Select>
          </div>

          <div className="min-w-0 flex-1">
            <Select
              value={selectedInterval}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onIntervalChange(e.target.value)}
              disabled={!selectedFile}
            >
              {availableIntervals.map((interval) => (
                <option key={interval} value={interval}>
                  {INTERVAL_LABELS[interval] || interval}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center space-x-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={loading}
            icon={<RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={onDownload}
            icon={<Download className="h-4 w-4" />}
          >
            Download Data
          </Button>

          <Button
            variant="outline"
            size="sm"
            icon={<Settings className="h-4 w-4" />}
          >
            Chart Settings
          </Button>
        </div>
      </div>

      {/* Chart Info */}
      {selectedFile && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-4 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex items-center space-x-1">
              <TrendingUp className="h-4 w-4" />
              <span>File: {formatFilename(selectedFile)}</span>
            </div>
            <div className="flex items-center space-x-1">
              <span>Interval: {INTERVAL_LABELS[selectedInterval] || selectedInterval}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}