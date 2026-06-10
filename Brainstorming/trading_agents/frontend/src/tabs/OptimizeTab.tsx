import { useState, useRef, useCallback } from "react";
import Plot from "react-plotly.js";
import { connectOptimizer } from "../api";
import type { TabProps } from "../types";
import GlobalParams from "../components/GlobalParams";

interface TrialResult {
  trial: number;
  params: Record<string, number>;
  score: number | null;
}

interface OptimizeComplete {
  best_params: Record<string, number>;
  best_score: number;
  best_strategy: {
    entry_expression: string;
    exit_expression: string;
    train_return: number;
    train_sharpe: number;
    test_return: number;
    test_sharpe: number;
  };
  study_stats: {
    n_trials: number;
    n_complete: number;
    optimization_time_seconds: number;
  };
  all_trials: TrialResult[];
}

export default function OptimizeTab({
  globalParams, onGlobalParamsChange, symbols, onAddSymbol, onStatus, setLoading,
}: TabProps) {
  const midDate = (() => {
    const s = new Date(globalParams.start);
    const e = new Date(globalParams.end);
    return new Date((s.getTime() + e.getTime()) / 2).toISOString().slice(0, 10);
  })();

  const [trainEnd, setTrainEnd] = useState(midDate);
  const [nTrials, setNTrials] = useState(15);
  const [seed, setSeed] = useState(42);
  const [running, setRunning] = useState(false);
  const [trials, setTrials] = useState<TrialResult[]>([]);
  const [result, setResult] = useState<OptimizeComplete | null>(null);
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const { symbol, interval, start, end } = globalParams;

  const handleStart = useCallback(() => {
    setRunning(true);
    setTrials([]);
    setResult(null);
    setError("");
    setLoading(true);
    onStatus("Optuna optimization started...");

    wsRef.current = connectOptimizer(
      { symbol, interval, start, end, train_end: trainEnd, n_trials: nTrials, seed },
      (msg) => {
        const data = msg as { type: string } & Record<string, unknown>;
        if (data.type === "trial") {
          const tr = data as unknown as TrialResult;
          setTrials((prev) => [...prev, tr]);
          onStatus(`Trial ${tr.trial}: score=${tr.score?.toFixed(3) ?? "N/A"}`);
        } else if (data.type === "complete") {
          setResult(data as unknown as OptimizeComplete);
          onStatus("Optimization complete!");
        } else if (data.type === "error") {
          setError((data as { message?: string }).message ?? "Optimization error");
        }
      },
      () => { setRunning(false); setLoading(false); },
    );
  }, [symbol, interval, start, end, trainEnd, nTrials, seed, onStatus, setLoading]);

  const handleStop = () => {
    wsRef.current?.close();
    setRunning(false);
    setLoading(false);
  };

  const progressPct = trials.length > 0 ? (trials.length / nTrials) * 100 : 0;

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="w-[280px] shrink-0 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto">
        <GlobalParams params={globalParams} onChange={onGlobalParamsChange}
          symbols={symbols} onAddSymbol={onAddSymbol} disabled={running} />

        <label className="block text-xs text-slate-400 mb-1">Train End Date</label>
        <input type="date" value={trainEnd} onChange={(e) => setTrainEnd(e.target.value)}
          disabled={running}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-3 focus:outline-none focus:border-purple-500 disabled:opacity-50" />

        <hr className="border-slate-700 my-3" />
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Optuna</h3>

        <div className="mb-3">
          <label className="flex justify-between text-xs text-slate-400 mb-1">
            <span>Trials</span><span className="text-purple-400">{nTrials}</span>
          </label>
          <input type="range" min={5} max={50} step={5} value={nTrials}
            onChange={(e) => setNTrials(Number(e.target.value))} disabled={running}
            className="w-full accent-purple-500" />
        </div>

        <label className="block text-xs text-slate-400 mb-1">Seed</label>
        <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))}
          disabled={running}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-3 focus:outline-none focus:border-purple-500 disabled:opacity-50" />

        <p className="text-xs text-slate-500 mb-3">
          Optuna will search: pop_size, n_gen, max_depth, complexity_penalty, cx/mut rates, walk-forward splits
        </p>

        {running ? (
          <button onClick={handleStop}
            className="w-full py-2 bg-red-600 hover:bg-red-700 text-white rounded text-sm font-medium transition-colors cursor-pointer">Stop</button>
        ) : (
          <button onClick={handleStart}
            className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white rounded text-sm font-medium transition-colors cursor-pointer">Start Optimization</button>
        )}
      </div>

      <div className="flex-1 p-6 overflow-y-auto">
        {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}

        {/* Progress */}
        {(running || trials.length > 0) && (
          <div className="bg-slate-800 rounded-lg p-4 mb-4">
            <div className="flex justify-between text-sm text-slate-300 mb-2">
              <span>Trial {trials.length} / {nTrials}</span>
              <span>{progressPct.toFixed(0)}%</span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-2">
              <div className="bg-purple-500 h-2 rounded-full transition-all duration-300" style={{ width: `${progressPct}%` }} />
            </div>
          </div>
        )}

        {/* Score per trial chart */}
        {trials.length > 0 && (
          <div className="bg-slate-800 rounded-lg p-4 mb-4">
            <Plot
              data={[
                {
                  x: trials.map((t) => t.trial),
                  y: trials.map((t) => t.score ?? -1),
                  type: "scatter", mode: "lines+markers",
                  name: "Trial Score (test Sharpe)",
                  marker: {
                    size: 8,
                    color: trials.map((t) => (t.score ?? -1) > 0 ? "#22c55e" : "#ef4444"),
                  },
                  line: { color: "#64748b", width: 1, dash: "dot" },
                },
                // Best so far line
                {
                  x: trials.map((t) => t.trial),
                  y: trials.reduce((acc: number[], t) => {
                    const prev = acc.length > 0 ? acc[acc.length - 1] : -999;
                    acc.push(Math.max(prev, t.score ?? -999));
                    return acc;
                  }, []),
                  type: "scatter", mode: "lines",
                  name: "Best so far",
                  line: { color: "#a855f7", width: 2 },
                },
              ]}
              layout={{
                title: { text: "Optuna Trial Scores", font: { color: "#e2e8f0", size: 14 } },
                paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8" },
                xaxis: { title: { text: "Trial" }, gridcolor: "#334155" },
                yaxis: { title: { text: "Test Sharpe" }, gridcolor: "#334155" },
                legend: { orientation: "h", y: -0.2 },
                margin: { t: 40, r: 20, b: 60, l: 60 }, autosize: true,
              }}
              useResizeHandler style={{ width: "100%", height: "350px" }}
            />
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-4">
            {/* Best params */}
            <div className="bg-slate-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-slate-200 mb-3">Optimal Hyperparameters</h3>
              <div className="grid grid-cols-4 gap-3">
                {Object.entries(result.best_params).map(([key, val]) => (
                  <div key={key} className="bg-slate-700/50 rounded p-2 text-center">
                    <div className="text-xs text-slate-400">{key}</div>
                    <div className="text-sm font-semibold text-purple-400">
                      {typeof val === "number" ? (Number.isInteger(val) ? val : val.toFixed(3)) : String(val)}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Best strategy */}
            <div className="bg-green-950/20 border border-green-800/50 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-slate-200 mb-2">Best Strategy Found</h3>
              <div className="space-y-1 mb-3">
                <div className="flex gap-2">
                  <span className="text-xs text-green-500 font-semibold w-10">BUY</span>
                  <code className="text-xs text-slate-300 font-mono break-all">{result.best_strategy.entry_expression}</code>
                </div>
                <div className="flex gap-2">
                  <span className="text-xs text-red-500 font-semibold w-10">SELL</span>
                  <code className="text-xs text-slate-300 font-mono break-all">{result.best_strategy.exit_expression}</code>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-2 text-xs text-center">
                <div><div className="text-slate-500">Train Ret</div>
                  <div className={result.best_strategy.train_return > 0 ? "text-green-400" : "text-red-400"}>
                    {(result.best_strategy.train_return * 100).toFixed(1)}%</div></div>
                <div><div className="text-slate-500">Train Sharpe</div>
                  <div className="text-slate-300">{result.best_strategy.train_sharpe.toFixed(2)}</div></div>
                <div><div className="text-slate-500">Test Ret</div>
                  <div className={result.best_strategy.test_return > 0 ? "text-green-400" : "text-red-400"}>
                    {(result.best_strategy.test_return * 100).toFixed(1)}%</div></div>
                <div><div className="text-slate-500">Test Sharpe</div>
                  <div className="text-slate-300">{result.best_strategy.test_sharpe.toFixed(2)}</div></div>
              </div>
            </div>

            {/* Study stats */}
            <div className="bg-slate-800 rounded-lg p-4">
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div className="text-center">
                  <div className="text-xs text-slate-400">Trials</div>
                  <div className="text-lg font-semibold text-slate-200">{result.study_stats.n_complete}/{result.study_stats.n_trials}</div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-400">Best Score</div>
                  <div className={`text-lg font-semibold ${result.best_score > 0 ? "text-green-400" : "text-red-400"}`}>
                    {result.best_score.toFixed(3)}</div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-400">Time</div>
                  <div className="text-lg font-semibold text-slate-200">
                    {result.study_stats.optimization_time_seconds > 60
                      ? `${(result.study_stats.optimization_time_seconds / 60).toFixed(1)}m`
                      : `${result.study_stats.optimization_time_seconds.toFixed(0)}s`}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {trials.length === 0 && !result && (
          <div className="flex items-center justify-center h-64 text-slate-500 text-sm">
            Configure parameters and start Optuna hyperparameter optimization
          </div>
        )}
      </div>
    </div>
  );
}
