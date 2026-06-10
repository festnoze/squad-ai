import type { BacktestMetrics } from "../types";

interface MetricsTableProps {
  metrics: BacktestMetrics;
}

function formatMetric(key: string, value: number): string {
  switch (key) {
    case "total_return":
    case "max_dd":
    case "win_rate":
      return `${(value * 100).toFixed(2)}%`;
    case "sharpe":
    case "profit_factor":
      return value.toFixed(3);
    case "trades":
      return value.toString();
    default:
      return value.toFixed(4);
  }
}

function labelFor(key: string): string {
  const labels: Record<string, string> = {
    total_return: "Total Return",
    sharpe: "Sharpe Ratio",
    max_dd: "Max Drawdown",
    trades: "Trades",
    win_rate: "Win Rate",
    profit_factor: "Profit Factor",
  };
  return labels[key] ?? key;
}

function colorFor(key: string, value: number): string {
  if (key === "max_dd") return "text-red-400";
  if (key === "trades") return "text-slate-200";
  if (key === "total_return" || key === "sharpe" || key === "profit_factor") {
    return value > 0 ? "text-green-400" : "text-red-400";
  }
  if (key === "win_rate") {
    return value > 0.5 ? "text-green-400" : "text-yellow-400";
  }
  return "text-slate-200";
}

export default function MetricsTable({ metrics }: MetricsTableProps) {
  const entries = Object.entries(metrics) as [string, number][];

  return (
    <div className="grid grid-cols-3 gap-3">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="bg-slate-700/50 rounded-lg p-3 text-center"
        >
          <div className="text-xs text-slate-400 mb-1">{labelFor(key)}</div>
          <div className={`text-lg font-semibold ${colorFor(key, value)}`}>
            {formatMetric(key, value)}
          </div>
        </div>
      ))}
    </div>
  );
}
