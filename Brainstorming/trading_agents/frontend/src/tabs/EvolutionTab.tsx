import { useState, useRef, useCallback } from "react";
import Plot from "react-plotly.js";
import { connectEvolution } from "../api";
import type { TabProps, GenerationUpdate, EvolutionComplete, StrategyResult } from "../types";
import GlobalParams from "../components/GlobalParams";

export default function EvolutionTab({
  globalParams,
  onGlobalParamsChange,
  symbols,
  onAddSymbol,
  onStatus,
  setLoading,
}: TabProps) {
  // Compute default train_end = midpoint between start and end
  const midDate = (() => {
    const s = new Date(globalParams.start);
    const e = new Date(globalParams.end);
    return new Date((s.getTime() + e.getTime()) / 2).toISOString().slice(0, 10);
  })();

  const [trainEnd, setTrainEnd] = useState(midDate);
  const [popSize, setPopSize] = useState(100);
  const [nGen, setNGen] = useState(30);
  const [maxDepth, setMaxDepth] = useState(6);
  const [complexityPenalty, setComplexityPenalty] = useState(0.03);
  const [seed, setSeed] = useState(42);
  const [running, setRunning] = useState(false);
  const [generations, setGenerations] = useState<GenerationUpdate[]>([]);
  const [topStrategies, setTopStrategies] = useState<StrategyResult[]>([]);
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const { symbol, interval, start, end } = globalParams;

  const handleStart = useCallback(() => {
    setRunning(true);
    setGenerations([]);
    setTopStrategies([]);
    setError("");
    setLoading(true);
    onStatus("Evolution started...");

    const config = {
      symbol, interval, start, end, train_end: trainEnd,
      pop_size: popSize, n_gen: nGen, max_depth: maxDepth,
      complexity_penalty: complexityPenalty, seed,
    };

    wsRef.current = connectEvolution(
      config,
      (msg) => {
        const data = msg as unknown;
        if (typeof data === "object" && data !== null && "type" in data) {
          const typed = data as { type: string };
          if (typed.type === "generation") {
            const gen = data as GenerationUpdate;
            setGenerations((prev) => [...prev, gen]);
            onStatus(`Generation ${gen.gen}: best=${gen.best.toFixed(3)}, avg=${gen.avg.toFixed(3)}`);
          } else if (typed.type === "complete") {
            const complete = data as EvolutionComplete;
            setTopStrategies(complete.top_strategies);
            onStatus("Evolution complete!");
          } else if (typed.type === "error") {
            const errData = data as { message?: string };
            setError(errData.message ?? "Evolution error");
            onStatus("Evolution error");
          }
        }
      },
      () => { setRunning(false); setLoading(false); },
    );
  }, [symbol, interval, start, end, trainEnd, popSize, nGen, maxDepth, complexityPenalty, seed, onStatus, setLoading]);

  const handleStop = () => {
    wsRef.current?.close();
    setRunning(false);
    setLoading(false);
    onStatus("Evolution stopped");
  };

  const progressPct = generations.length > 0 ? (generations.length / nGen) * 100 : 0;

  const Slider = ({ label, value, onChange, min, max, step = 1 }: {
    label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number;
  }) => (
    <div className="mb-3">
      <label className="flex justify-between text-xs text-slate-400 mb-1">
        <span>{label}</span><span className="text-purple-400">{value}</span>
      </label>
      <input type="range" min={min} max={max} step={step} value={value} disabled={running}
        onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-purple-500" />
    </div>
  );

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="w-[280px] shrink-0 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto">
        <GlobalParams params={globalParams} onChange={onGlobalParamsChange} symbols={symbols} onAddSymbol={onAddSymbol} disabled={running} />

        <label className="block text-xs text-slate-400 mb-1">Train End Date</label>
        <input type="date" value={trainEnd} onChange={(e) => setTrainEnd(e.target.value)} disabled={running}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-3 focus:outline-none focus:border-purple-500 disabled:opacity-50" />

        <hr className="border-slate-700 my-3" />
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">GP Parameters</h3>

        <Slider label="Population Size" value={popSize} onChange={setPopSize} min={50} max={500} step={10} />
        <Slider label="Generations" value={nGen} onChange={setNGen} min={10} max={100} step={5} />
        <Slider label="Max Depth" value={maxDepth} onChange={setMaxDepth} min={4} max={10} />
        <Slider label="Complexity Penalty" value={complexityPenalty} onChange={setComplexityPenalty} min={0.01} max={0.1} step={0.01} />

        <label className="block text-xs text-slate-400 mb-1">Seed</label>
        <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} disabled={running}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-3 focus:outline-none focus:border-purple-500 disabled:opacity-50" />

        {running ? (
          <button onClick={handleStop} className="w-full py-2 bg-red-600 hover:bg-red-700 text-white rounded text-sm font-medium transition-colors cursor-pointer">Stop</button>
        ) : (
          <button onClick={handleStart} className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white rounded text-sm font-medium transition-colors cursor-pointer">Start Evolution</button>
        )}
      </div>

      <div className="flex-1 p-6 overflow-y-auto">
        {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}

        {(running || generations.length > 0) && (
          <div className="bg-slate-800 rounded-lg p-4 mb-4">
            <div className="flex justify-between text-sm text-slate-300 mb-2">
              <span>Generation {generations.length} / {nGen}</span>
              <span>{progressPct.toFixed(0)}%</span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-2">
              <div className="bg-purple-500 h-2 rounded-full transition-all duration-300" style={{ width: `${progressPct}%` }} />
            </div>
          </div>
        )}

        {generations.length > 0 && (
          <div className="bg-slate-800 rounded-lg p-4 mb-4">
            <Plot
              data={[
                { x: generations.map((g) => g.gen), y: generations.map((g) => g.best), type: "scatter", mode: "lines+markers",
                  name: "Best Fitness", line: { color: "#a855f7", width: 2 }, marker: { size: 4 } },
                { x: generations.map((g) => g.gen), y: generations.map((g) => g.avg), type: "scatter", mode: "lines+markers",
                  name: "Avg Fitness", line: { color: "#64748b", width: 1.5, dash: "dot" }, marker: { size: 3 } },
              ]}
              layout={{
                title: { text: "Fitness Over Generations", font: { color: "#e2e8f0", size: 14 } },
                paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8" },
                xaxis: { title: { text: "Generation" }, gridcolor: "#334155", linecolor: "#334155" },
                yaxis: { title: { text: "Fitness" }, gridcolor: "#334155", linecolor: "#334155" },
                legend: { orientation: "h", y: -0.2 }, margin: { t: 40, r: 20, b: 60, l: 60 }, autosize: true,
              }}
              useResizeHandler style={{ width: "100%", height: "350px" }}
            />
          </div>
        )}

        {topStrategies.length > 0 && (
          <div className="bg-slate-800 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-slate-200 mb-3">Top Strategies (Entry + Exit trees)</h3>
            <div className="space-y-3">
              {topStrategies.map((s) => (
                <div key={s.rank} className={`border rounded-lg p-3 ${s.is_overfit ? "border-red-800/50 bg-red-950/20" : "border-green-800/50 bg-green-950/20"}`}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold text-slate-200">#{s.rank}</span>
                    <div className="flex gap-2 items-center">
                      <span className="text-xs text-slate-400">Entry: {s.entry_size} nodes | Exit: {s.exit_size} nodes</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${s.is_overfit ? "bg-red-900/50 text-red-400" : "bg-green-900/50 text-green-400"}`}>
                        {s.is_overfit ? "Overfit" : "OK"}
                      </span>
                    </div>
                  </div>
                  <div className="space-y-1 mb-2">
                    <div className="flex gap-2 items-start">
                      <span className="text-xs text-green-500 font-semibold w-10 shrink-0">BUY</span>
                      <code className="text-xs text-slate-300 font-mono break-all">{s.entry_expression}</code>
                    </div>
                    <div className="flex gap-2 items-start">
                      <span className="text-xs text-red-500 font-semibold w-10 shrink-0">SELL</span>
                      <code className="text-xs text-slate-300 font-mono break-all">{s.exit_expression}</code>
                    </div>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-xs">
                    <div className="text-center">
                      <div className="text-slate-500">Train Ret</div>
                      <div className={s.train_return > 0 ? "text-green-400" : "text-red-400"}>{(s.train_return * 100).toFixed(1)}%</div>
                    </div>
                    <div className="text-center">
                      <div className="text-slate-500">Train Sharpe</div>
                      <div className="text-slate-300">{s.train_sharpe.toFixed(2)}</div>
                    </div>
                    <div className="text-center">
                      <div className="text-slate-500">Test Ret</div>
                      <div className={s.test_return > 0 ? "text-green-400" : "text-red-400"}>{(s.test_return * 100).toFixed(1)}%</div>
                    </div>
                    <div className="text-center">
                      <div className="text-slate-500">Test Sharpe</div>
                      <div className="text-slate-300">{s.test_sharpe.toFixed(2)}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {generations.length === 0 && topStrategies.length === 0 && (
          <div className="flex items-center justify-center h-64 text-slate-500 text-sm">Configure parameters and start evolution</div>
        )}
      </div>
    </div>
  );
}
