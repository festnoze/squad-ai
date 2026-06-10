import { useState } from "react";
import Plot from "react-plotly.js";
import type Plotly from "plotly.js";
import { api } from "../api";
import type { TabProps, TimeSeriesPoint } from "../types";
import GlobalParams from "../components/GlobalParams";

interface CompareResult {
  rank: number;
  name: string;
  composite_score: number;
  metrics: Record<string, number | null>;
  drawdown: { max_depth: number; time_in_drawdown_pct: number };
  portfolio_values: TimeSeriesPoint[];
}

interface AllocResult {
  combined_portfolio: TimeSeriesPoint[];
  buy_hold: TimeSeriesPoint[];
  strategy_values: Record<string, TimeSeriesPoint[]>;
  weights: Record<string, TimeSeriesPoint[]>;
  regime: { date: string; regime: string }[];
  metrics: Record<string, unknown>;
}

const COLORS = ["#a855f7", "#22c55e", "#f97316", "#06b6d4", "#ec4899", "#eab308"];

const STRATEGIES = [
  { name: "MA(20/50)", type: "ma_crossover", params: { fast_ma: 20, slow_ma: 50 } },
  { name: "MA(10/30)", type: "ma_crossover", params: { fast_ma: 10, slow_ma: 30 } },
  { name: "RSI+BB", type: "rsi_bb", params: { rsi_window: 14, rsi_lo: 30, rsi_hi: 70, bb_window: 20, bb_alpha: 2 } },
  { name: "Adaptive", type: "adaptive", params: {} },
];

export default function ResultsTab(props: TabProps) {
  const { globalParams, onGlobalParamsChange, symbols, onAddSymbol, onStatus, setLoading } = props;
  const [compareResult, setCompareResult] = useState<CompareResult[] | null>(null);
  const [allocResult, setAllocResult] = useState<AllocResult | null>(null);
  const [buyHold, setBuyHold] = useState<TimeSeriesPoint[]>([]);
  const [mcResult, setMcResult] = useState<Record<string, unknown> | null>(null);
  const [maResult, setMaResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"compare" | "allocate" | "montecarlo" | "multiasset">("compare");

  const { symbol, interval, start, end } = globalParams;

  const handleMonteCarlo = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.runMonteCarlo({
        symbol, interval, start, end,
        strategy: "ma_crossover", params: { fast_ma: 20, slow_ma: 50 },
        n_simulations: 500,
      });
      setMcResult(res.data);
      setMode("montecarlo");
      onStatus("Monte Carlo test complete");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Monte Carlo failed");
    } finally {
      setLoading(false);
    }
  };

  const handleMultiAsset = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.runMultiAsset({
        symbol, interval, start, end,
        strategy: "ma_crossover", params: { fast_ma: 20, slow_ma: 50 },
        validation_symbols: ["BTC-USD", "ETH-USD", "AAPL", "GOOGL", "MSFT"],
      });
      setMaResult(res.data);
      setMode("multiasset");
      onStatus("Multi-asset validation complete");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Multi-asset failed");
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.compareStrategies({
        symbol, interval, start, end, strategies: STRATEGIES,
      });
      setCompareResult(res.data.strategies);
      setBuyHold(res.data.buy_hold);
      setMode("compare");
      onStatus(`Compared ${res.data.strategies.length} strategies on ${symbol}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Compare failed");
    } finally {
      setLoading(false);
    }
  };

  const handleAllocate = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.allocateStrategies({
        symbol, interval, start, end, strategies: STRATEGIES,
      });
      setAllocResult(res.data);
      setMode("allocate");
      onStatus(`Allocation computed for ${STRATEGIES.length} strategies`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Allocation failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="w-[280px] shrink-0 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto">
        <GlobalParams params={globalParams} onChange={onGlobalParamsChange} symbols={symbols} onAddSymbol={onAddSymbol} />

        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Strategies</h3>
        {STRATEGIES.map((s, i) => (
          <div key={i} className="flex items-center gap-2 mb-2 text-sm">
            <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
            <span className="text-slate-200 flex-1">{s.name}</span>
            <span className="text-xs text-slate-500">{s.type}</span>
          </div>
        ))}

        <hr className="border-slate-700 my-3" />

        <button onClick={handleCompare}
          className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white rounded text-sm font-medium mb-2 transition-colors cursor-pointer">
          Compare Strategies
        </button>
        <button onClick={handleAllocate}
          className="w-full py-2 bg-green-700 hover:bg-green-600 text-white rounded text-sm font-medium mb-2 transition-colors cursor-pointer">
          Compute Allocation
        </button>

        <hr className="border-slate-700 my-3" />
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Validation</h3>

        <button onClick={handleMonteCarlo}
          className="w-full py-2 bg-blue-700 hover:bg-blue-600 text-white rounded text-sm font-medium mb-2 transition-colors cursor-pointer">
          Monte Carlo Test
        </button>
        <button onClick={handleMultiAsset}
          className="w-full py-2 bg-orange-700 hover:bg-orange-600 text-white rounded text-sm font-medium transition-colors cursor-pointer">
          Multi-Asset Test
        </button>
      </div>

      <div className="flex-1 p-6 overflow-y-auto">
        {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}

        {mode === "compare" && compareResult && (
          <div className="space-y-4">
            <div className="bg-slate-800 rounded-lg p-4">
              <Plot
                data={[
                  ...compareResult.map((s, i) => ({
                    x: s.portfolio_values.map((p) => p.date),
                    y: s.portfolio_values.map((p) => p.value),
                    type: "scatter" as const, mode: "lines" as const,
                    name: s.name, line: { color: COLORS[i % COLORS.length], width: 2 },
                  })),
                  {
                    x: buyHold.map((p) => p.date), y: buyHold.map((p) => p.value),
                    type: "scatter" as const, mode: "lines" as const,
                    name: "Buy & Hold", line: { color: "gray", width: 1.5, dash: "dot" as const },
                  },
                ]}
                layout={{
                  title: { text: `${symbol} - Strategy Comparison`, font: { color: "#e2e8f0", size: 14 } },
                  paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8" },
                  xaxis: { gridcolor: "#334155" }, yaxis: { gridcolor: "#334155", tickprefix: "$" },
                  legend: { orientation: "h", y: -0.15 },
                  margin: { t: 40, r: 20, b: 60, l: 60 }, autosize: true,
                }}
                useResizeHandler style={{ width: "100%", height: "400px" }}
              />
            </div>

            <div className="grid gap-3">
              {compareResult.map((s, i) => (
                <div key={s.name} className="bg-slate-800 rounded-lg p-4 border-l-4"
                  style={{ borderLeftColor: COLORS[i % COLORS.length] }}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <span className="text-lg font-bold text-slate-300">#{s.rank}</span>
                      <span className="text-sm font-semibold text-slate-200">{s.name}</span>
                    </div>
                    <div className="bg-purple-900/50 px-3 py-1 rounded">
                      <span className="text-xs text-slate-400">Score: </span>
                      <span className="text-sm font-bold text-purple-400">{s.composite_score?.toFixed(2) ?? "N/A"}</span>
                    </div>
                  </div>
                  <div className="grid grid-cols-6 gap-2 text-xs">
                    {([
                      ["Return", s.metrics.total_return, true],
                      ["Sharpe", s.metrics.sharpe_ratio, false],
                      ["Sortino", s.metrics.sortino_ratio, false],
                      ["Max DD", s.metrics.max_drawdown, true],
                      ["Exposure", s.metrics.exposure_pct, true],
                      ["Win Rate", s.metrics.win_rate, true],
                    ] as [string, number | null, boolean][]).map(([label, val, isPct]) => (
                      <div key={label} className="text-center">
                        <div className="text-slate-500">{label}</div>
                        <div className={`font-semibold ${
                          label === "Max DD" ? "text-red-400" :
                          typeof val === "number" && val > 0 ? "text-green-400" : "text-slate-300"
                        }`}>
                          {val != null ? (isPct ? `${(val * 100).toFixed(1)}%` : val.toFixed(2)) : "N/A"}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {mode === "allocate" && allocResult && (
          <div className="space-y-4">
            <div className="bg-slate-800 rounded-lg p-4">
              <Plot
                data={[
                  {
                    x: allocResult.combined_portfolio.map((p) => p.date),
                    y: allocResult.combined_portfolio.map((p) => p.value),
                    type: "scatter", mode: "lines",
                    name: "Combined (allocated)", line: { color: "#a855f7", width: 3 },
                  },
                  ...Object.entries(allocResult.strategy_values).map(([name, vals], i) => ({
                    x: vals.map((p) => p.date), y: vals.map((p) => p.value),
                    type: "scatter" as const, mode: "lines" as const,
                    name, line: { color: COLORS[(i + 1) % COLORS.length], width: 1, dash: "dot" as const },
                  })),
                  {
                    x: allocResult.buy_hold.map((p) => p.date),
                    y: allocResult.buy_hold.map((p) => p.value),
                    type: "scatter", mode: "lines",
                    name: "Buy & Hold", line: { color: "gray", width: 1.5, dash: "dash" },
                  },
                ]}
                layout={{
                  title: { text: `${symbol} - Allocated Portfolio`, font: { color: "#e2e8f0", size: 14 } },
                  paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8" },
                  xaxis: { gridcolor: "#334155" }, yaxis: { gridcolor: "#334155", tickprefix: "$" },
                  legend: { orientation: "h", y: -0.15 },
                  margin: { t: 40, r: 20, b: 60, l: 60 }, autosize: true,
                }}
                useResizeHandler style={{ width: "100%", height: "400px" }}
              />
            </div>

            <div className="bg-slate-800 rounded-lg p-4">
              <Plot
                data={Object.entries(allocResult.weights).map(([name, vals], i) => ({
                  x: vals.map((p) => p.date), y: vals.map((p) => p.value * 100),
                  type: "scatter" as const, mode: "lines" as const,
                  name, stackgroup: "weights",
                  line: { color: COLORS[i % COLORS.length] },
                }))}
                layout={{
                  title: { text: "Strategy Weights Over Time (%)", font: { color: "#e2e8f0", size: 14 } },
                  paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8" },
                  xaxis: { gridcolor: "#334155" },
                  yaxis: { gridcolor: "#334155", title: { text: "Weight %" }, range: [0, 100] },
                  legend: { orientation: "h", y: -0.15 },
                  margin: { t: 40, r: 20, b: 60, l: 60 }, autosize: true,
                }}
                useResizeHandler style={{ width: "100%", height: "300px" }}
              />
            </div>

            {allocResult.metrics && (
              <div className="bg-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-3">Allocation Metrics</h3>
                <div className="grid grid-cols-3 gap-3">
                  {([
                    ["Total Return", allocResult.metrics.total_return as number],
                    ["Max Drawdown", allocResult.metrics.max_drawdown as number],
                    ["Exposure", allocResult.metrics.exposure_pct as number],
                  ] as [string, number][]).map(([label, val]) => (
                    <div key={label} className="bg-slate-700/50 rounded p-3 text-center">
                      <div className="text-xs text-slate-400 mb-1">{label}</div>
                      <div className={`text-lg font-semibold ${
                        label === "Max Drawdown" ? "text-red-400" : val > 0 ? "text-green-400" : "text-slate-300"
                      }`}>
                        {`${(val * 100).toFixed(1)}%`}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Monte Carlo */}
        {mode === "montecarlo" && mcResult && (() => {
          const perm = mcResult.permutation as Record<string, unknown>;
          const boot = mcResult.bootstrap as Record<string, Record<string, number>>;
          const rand = mcResult.random_entry as Record<string, unknown>;
          const simSharpes = (perm.simulated_sharpes as number[]) || [];
          const realSharpe = perm.real_sharpe as number;

          return (
            <div className="space-y-4">
              {/* Verdict */}
              <div className={`rounded-lg p-4 border ${
                perm.is_significant_95 ? "bg-green-950/30 border-green-700" :
                (perm.p_value as number) < 0.1 ? "bg-yellow-950/30 border-yellow-700" :
                "bg-red-950/30 border-red-700"
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-lg font-bold">
                    {perm.is_significant_99 ? "HIGHLY SIGNIFICANT" :
                     perm.is_significant_95 ? "SIGNIFICANT" :
                     (perm.p_value as number) < 0.1 ? "MARGINAL" : "NOT SIGNIFICANT"}
                  </span>
                  <span className="text-sm text-slate-400">p-value: {(perm.p_value as number)?.toFixed(4)}</span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Strategy Sharpe ({realSharpe?.toFixed(3)}) is at the {(perm.percentile as number)?.toFixed(1)}th percentile of {simSharpes.length * 5} random permutations
                </p>
              </div>

              {/* Distribution histogram */}
              <div className="bg-slate-800 rounded-lg p-4">
                <Plot
                  data={[
                    { x: simSharpes, type: "histogram", name: "Simulated Sharpes", marker: { color: "#475569" } } as Partial<Plotly.PlotData>,
                    { x: [realSharpe, realSharpe], y: [0, simSharpes.length / 5], type: "scatter", mode: "lines",
                      name: `Real Sharpe (${realSharpe?.toFixed(3)})`, line: { color: "#a855f7", width: 3, dash: "dash" } },
                  ]}
                  layout={{
                    title: { text: "Sharpe Distribution: Real vs Random Permutations", font: { color: "#e2e8f0", size: 14 } },
                    paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8" },
                    xaxis: { title: { text: "Sharpe Ratio" }, gridcolor: "#334155" },
                    yaxis: { title: { text: "Count" }, gridcolor: "#334155" },
                    margin: { t: 40, r: 20, b: 60, l: 60 }, autosize: true, showlegend: true,
                    legend: { orientation: "h", y: -0.2 },
                  }}
                  useResizeHandler style={{ width: "100%", height: "350px" }}
                />
              </div>

              {/* Bootstrap CI + Random entry */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-800 rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-slate-200 mb-3">Bootstrap {(((boot.confidence_level as unknown as number) ?? 0.95) * 100).toFixed(0)}% CI</h3>
                  <div className="space-y-2 text-sm">
                    {(["total_return", "sharpe_ratio", "max_drawdown"] as const).map((key) => {
                      const ci = boot[key];
                      return ci ? (
                        <div key={key} className="flex justify-between">
                          <span className="text-slate-400">{key.replace("_", " ")}</span>
                          <span className="text-slate-200 font-mono text-xs">
                            [{(ci.lower * (key === "max_drawdown" || key === "total_return" ? 100 : 1)).toFixed(2)}
                            , {(ci.upper * (key === "max_drawdown" || key === "total_return" ? 100 : 1)).toFixed(2)}]
                          </span>
                        </div>
                      ) : null;
                    })}
                  </div>
                </div>
                <div className="bg-slate-800 rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-slate-200 mb-3">vs Random Trading</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Sharpe p-value</span>
                      <span className={`font-semibold ${(rand.p_value_sharpe as number) < 0.05 ? "text-green-400" : "text-red-400"}`}>
                        {(rand.p_value_sharpe as number)?.toFixed(4)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Return p-value</span>
                      <span className={`font-semibold ${(rand.p_value_return as number) < 0.05 ? "text-green-400" : "text-red-400"}`}>
                        {(rand.p_value_return as number)?.toFixed(4)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Avg random return</span>
                      <span className="text-slate-300">{((rand.mean_random_return as number) * 100)?.toFixed(1)}%</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })()}

        {/* Multi-Asset */}
        {mode === "multiasset" && maResult && (() => {
          const rob = maResult.robustness as Record<string, unknown>;
          const assets = (maResult.per_asset as Record<string, unknown>[]) || [];
          const gradeColor: Record<string, string> = { A: "text-green-400", B: "text-green-300", C: "text-yellow-400", D: "text-orange-400", F: "text-red-400" };

          return (
            <div className="space-y-4">
              {/* Grade */}
              <div className="bg-slate-800 rounded-lg p-4 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-200">Robustness Grade</h3>
                  <p className="text-xs text-slate-400 mt-1">
                    {rob.n_profitable as number}/{rob.n_assets as number} assets profitable ({((rob.profitable_pct as number) * 100).toFixed(0)}%)
                  </p>
                </div>
                <span className={`text-5xl font-black ${gradeColor[rob.grade as string] ?? "text-slate-400"}`}>
                  {rob.grade as string}
                </span>
              </div>

              {/* Portfolio overlay */}
              <div className="bg-slate-800 rounded-lg p-4">
                <Plot
                  data={assets.filter(a => a.portfolio_values).map((a, i) => ({
                    x: (a.portfolio_values as TimeSeriesPoint[]).map(p => p.date),
                    y: (a.portfolio_values as TimeSeriesPoint[]).map(p => p.value),
                    type: "scatter" as const, mode: "lines" as const,
                    name: a.symbol as string, line: { color: COLORS[i % COLORS.length], width: 2 },
                  }))}
                  layout={{
                    title: { text: "Cross-Asset Performance", font: { color: "#e2e8f0", size: 14 } },
                    paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8" },
                    xaxis: { gridcolor: "#334155" }, yaxis: { gridcolor: "#334155", tickprefix: "$" },
                    legend: { orientation: "h", y: -0.15 },
                    margin: { t: 40, r: 20, b: 60, l: 60 }, autosize: true,
                  }}
                  useResizeHandler style={{ width: "100%", height: "400px" }}
                />
              </div>

              {/* Per-asset table */}
              <div className="bg-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-3">Per-Asset Results</h3>
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-400">
                      <th className="py-2 px-3">Symbol</th>
                      <th className="py-2 px-3">Return</th>
                      <th className="py-2 px-3">Sharpe</th>
                      <th className="py-2 px-3">Max DD</th>
                      <th className="py-2 px-3">Trades</th>
                      <th className="py-2 px-3">Win Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assets.map((a, i) => (
                      <tr key={i} className="border-b border-slate-700/50">
                        <td className="py-2 px-3 font-semibold" style={{ color: COLORS[i % COLORS.length] }}>{a.symbol as string}</td>
                        <td className={`py-2 px-3 ${(a.total_return as number) > 0 ? "text-green-400" : "text-red-400"}`}>
                          {((a.total_return as number) * 100).toFixed(1)}%
                        </td>
                        <td className="py-2 px-3 text-slate-300">{(a.sharpe_ratio as number)?.toFixed(2)}</td>
                        <td className="py-2 px-3 text-red-400">{((a.max_drawdown as number) * 100).toFixed(1)}%</td>
                        <td className="py-2 px-3 text-slate-300">{a.n_trades as number}</td>
                        <td className="py-2 px-3 text-slate-300">{((a.win_rate as number) * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Summary stats */}
              <div className="grid grid-cols-4 gap-3">
                {([
                  ["Mean Sharpe", rob.mean_sharpe],
                  ["Sharpe Std", rob.sharpe_std],
                  ["Mean Return", rob.mean_return],
                  ["Mean Max DD", rob.mean_max_dd],
                ] as [string, unknown][]).map(([label, val]) => (
                  <div key={label} className="bg-slate-700/50 rounded p-3 text-center">
                    <div className="text-xs text-slate-400 mb-1">{label}</div>
                    <div className="text-sm font-semibold text-slate-200">
                      {label.includes("Return") || label.includes("DD") ? `${((val as number) * 100).toFixed(1)}%` : (val as number)?.toFixed(3)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}

        {!compareResult && !allocResult && !mcResult && !maResult && (
          <div className="flex items-center justify-center h-64 text-slate-500 text-sm">
            Click "Compare Strategies" to rank them, or "Compute Allocation" for temporal weighting
          </div>
        )}
      </div>
    </div>
  );
}
