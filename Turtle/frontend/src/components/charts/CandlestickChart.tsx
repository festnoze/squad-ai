import { useEffect, useRef, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  TimeScale,
  Title,
  Tooltip,
  Legend,
  ChartOptions
} from 'chart.js'
import { Chart } from 'react-chartjs-2'
import { CandlestickController, CandlestickElement } from 'chartjs-chart-financial'
import 'chartjs-adapter-date-fns'
import type { ChartData as ChartDataType, Candle } from '@/types'

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  TimeScale,
  Title,
  Tooltip,
  Legend,
  CandlestickController,
  CandlestickElement
)

interface CandlestickChartProps {
  data: ChartDataType
  height?: number
  showVolume?: boolean
  overlays?: {
    high_20?: number
    low_20?: number
    high_55?: number
    low_55?: number
  }
  signals?: Array<{
    timestamp: string
    price: number
    type: 'buy' | 'sell'
    label?: string
  }>
}

export function CandlestickChart({ 
  data, 
  height = 400, 
  showVolume = false,
  overlays = {},
  signals = []
}: CandlestickChartProps) {
  const chartRef = useRef<ChartJS>(null)
  const [chartData, setChartData] = useState<any>(null)

  useEffect(() => {
    if (!data.candles || data.candles.length === 0) return

    // Transform candle data for Chart.js
    const candleData = data.candles.map((candle: Candle) => ({
      x: new Date(candle.timestamp).getTime(),
      o: candle.open,
      h: candle.high,
      l: candle.low,
      c: candle.close,
      v: candle.volume || 0
    }))

    // Create datasets
    const datasets: any[] = [
      {
        label: data.metadata.asset_name,
        data: candleData,
        type: 'candlestick',
        borderColor: 'rgba(75, 192, 192, 1)',
        borderWidth: 1,
        color: {
          up: '#22c55e',
          down: '#ef4444',
          unchanged: '#6b7280'
        }
      }
    ]

    // Add overlay lines
    if (overlays.high_20) {
      datasets.push({
        label: '20-Day High',
        data: candleData.map(d => ({ x: d.x, y: overlays.high_20 })),
        type: 'line',
        borderColor: '#3b82f6',
        borderDash: [5, 5],
        borderWidth: 1,
        pointRadius: 0,
        fill: false
      })
    }

    if (overlays.low_20) {
      datasets.push({
        label: '20-Day Low',
        data: candleData.map(d => ({ x: d.x, y: overlays.low_20 })),
        type: 'line',
        borderColor: '#3b82f6',
        borderDash: [5, 5],
        borderWidth: 1,
        pointRadius: 0,
        fill: false
      })
    }

    if (overlays.high_55) {
      datasets.push({
        label: '55-Day High',
        data: candleData.map(d => ({ x: d.x, y: overlays.high_55 })),
        type: 'line',
        borderColor: '#ef4444',
        borderDash: [2, 2],
        borderWidth: 1,
        pointRadius: 0,
        fill: false
      })
    }

    if (overlays.low_55) {
      datasets.push({
        label: '55-Day Low',
        data: candleData.map(d => ({ x: d.x, y: overlays.low_55 })),
        type: 'line',
        borderColor: '#ef4444',
        borderDash: [2, 2],
        borderWidth: 1,
        pointRadius: 0,
        fill: false
      })
    }

    // Add trading signals
    if (signals.length > 0) {
      const buySignals = signals.filter(s => s.type === 'buy').map(s => ({
        x: new Date(s.timestamp).getTime(),
        y: s.price
      }))

      const sellSignals = signals.filter(s => s.type === 'sell').map(s => ({
        x: new Date(s.timestamp).getTime(),
        y: s.price
      }))

      if (buySignals.length > 0) {
        datasets.push({
          label: 'Buy Signals',
          data: buySignals,
          type: 'scatter',
          backgroundColor: '#22c55e',
          borderColor: '#16a34a',
          pointRadius: 6,
          pointHoverRadius: 8,
          showLine: false
        })
      }

      if (sellSignals.length > 0) {
        datasets.push({
          label: 'Sell Signals',
          data: sellSignals,
          type: 'scatter',
          backgroundColor: '#ef4444',
          borderColor: '#dc2626',
          pointRadius: 6,
          pointHoverRadius: 8,
          showLine: false
        })
      }
    }

    // Add volume chart if requested
    if (showVolume) {
      datasets.push({
        label: 'Volume',
        data: candleData.map(d => ({ x: d.x, y: d.v })),
        type: 'bar',
        backgroundColor: 'rgba(156, 163, 175, 0.3)',
        borderColor: 'rgba(156, 163, 175, 0.8)',
        borderWidth: 1,
        yAxisID: 'volume',
        order: 1
      })
    }

    setChartData({ datasets })
  }, [data, overlays, signals, showVolume])

  const options: ChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    plugins: {
      title: {
        display: true,
        text: `${data.metadata.asset_name} (${data.metadata.currency}) - ${data.metadata.period_duration}`,
        font: {
          size: 16,
          weight: 'bold'
        }
      },
      legend: {
        display: true,
        position: 'top'
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          title: (context) => {
            const date = new Date(context[0].parsed.x)
            return date.toLocaleString()
          },
          label: (context) => {
            const dataset = context.dataset
            if (dataset.type === 'candlestick') {
              const data = context.raw as any
              return [
                `Open: ${data.o.toFixed(2)}`,
                `High: ${data.h.toFixed(2)}`,
                `Low: ${data.l.toFixed(2)}`,
                `Close: ${data.c.toFixed(2)}`,
                `Volume: ${data.v.toLocaleString()}`
              ]
            }
            return `${dataset.label}: ${context.parsed.y.toFixed(2)}`
          }
        }
      }
    },
    scales: {
      x: {
        type: 'time',
        time: {
          displayFormats: {
            minute: 'HH:mm',
            hour: 'MMM dd HH:mm',
            day: 'MMM dd',
            week: 'MMM dd',
            month: 'MMM yyyy',
          }
        },
        title: {
          display: true,
          text: 'Time'
        }
      },
      y: {
        type: 'linear',
        position: 'right',
        title: {
          display: true,
          text: `Price (${data.metadata.currency})`
        }
      },
      ...(showVolume && {
        volume: {
          type: 'linear',
          position: 'left',
          title: {
            display: true,
            text: 'Volume'
          },
          grid: {
            display: false
          }
        }
      })
    }
  }

  if (!chartData) {
    return (
      <div className="chart-container flex items-center justify-center">
        <div className="spinner"></div>
        <span className="ml-2 text-gray-600">Loading chart...</span>
      </div>
    )
  }

  return (
    <div className="chart-container" style={{ height: `${height}px` }}>
      <Chart
        ref={chartRef}
        type="candlestick"
        data={chartData}
        options={options}
      />
    </div>
  )
}