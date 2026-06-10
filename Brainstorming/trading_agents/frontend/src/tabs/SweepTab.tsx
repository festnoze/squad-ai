import { useState } from "react";
import Plot from "react-plotly.js";
import { api } from "../api";
import type { TabProps, SweepResult } from "../types";
import GlobalParams from "../components/GlobalParams";

export default function SweepTab({
  globalParams,
  onGlobalParamsChange,
  symbols,
  onAddSymbol,
  onStatus,
  setLoading,
}: TabProps) {
  const [fastMin, setFastMin] = useState(5);
  const [fastMax, setFastMax] = useState(50);
  const [fastStep, setFastStep] = useState(5);
  const [slowMin, setSlowMin] = useState(20);
  const [slowMax, setSlowMax] = useState(200);
  const [slowStep, setSlowStep] = useState(10);
  const [result, setResult] = useState<SweepResult | null>(null);
  const [error, setError] = useState("");

  const { symbol, interval, start, end } = globalParams;
  const totalCombos = Math.floor((fastMax - fastMin) / fastStep + 1) * Math.floor((slowMax - slowMin) / slowStep + 1);

  const handleRun = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.runSweep({
        symbol, interval, start, end,
        fast_min: fastMin, fast_max: fastMax, fast_step: fastStep,
        slow_min: slowMin, slow_max: slowMax, slow_step: slowStep,
      });
      setResult(res.data);
      onStatus(`Sweep complete: best Sharpe ${res.data.best.sharpe.toFixed(3)} at fast=${res.data.best.fast}, slow=${res.data.best.slow}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sweep failed";
      setError(msg);
      onStatus(`Error: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const RangeInput = ({ label, min, max, step, onMinChange, onMaxChange, onStepChange }: {
    label: string; min: number; max: number; step: number;
    onMinChange: (v: number) => void; onMaxChange: (v: number) => void; onStepChange: (v: number) => void;
  }) => (
    <div className="mb-3">
      <label className="block text-xs text-slate-400 mb-1">{label}</label>
      <div className="grid grid-cols-3 gap-2">
        {[["Min", min, onMinChange], ["Max", max, onMaxChange], ["Step", step, onStepChange]].map(([lbl, val, fn]) => (
          <div key={lbl as string}>
            <span className="text-[10px] text-slate-500">{lbl as string}</span>
            <input type="number" value={val as number} onChange={(e) => (fn as (v: number) => void)(Number(e.target.value))}
              className="w-full px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-xs text-slate-200 focus:outline-none focus:border-purple-500" />
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="w-[280px] shrink-0 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto">
        <GlobalParams params={globalParams} onChange={onGlobalParamsChange} symbols={symbols} onAddSymbol={onAddSymbol} />

        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Sweep Ranges</h3>
        <RangeInput label="Fast MA Range" min={fastMin} max={fastMax} step={fastStep}
          onMinChange={setFastMin} onMaxChange={setFastMax} onStepChange={setFastStep} />
        <RangeInput label="Slow MA Range" min={slowMin} max={slowMax} step={slowStep}
          onMinChange={setSlowMin} onMaxChange={setSlowMax} onStepChange={setSlowStep} />
        <div className="text-xs text-slate-400 mb-3">
          Total: <span className="text-purple-400 font-semibold">{totalCombos}</span> combos
        </div>
        <button onClick={handleRun}
          className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white rounded text-sm font-medium transition-colors cursor-pointer">
          Run Sweep
        </button>
      </div>

      <div className="flex-1 p-6 overflow-y-auto">
        {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}
        {result ? (
          <div className="space-y-4">
            <div className="bg-slate-800 rounded-lg p-4">
              <Plot
                data={[{ z: result.sharpe_matrix, x: result.slow_values.map(String), y: result.fast_values.map(String),
                  type: "heatmap", colorscale: "RdYlGn",
                  colorbar: { title: { text: "Sharpe", side: "right" as const }, tickfont: { color: "#94a3b8" } },
                }]}
                layout={{
                  title: { text: `${symbol} - Sharpe Ratio Heatmap`, font: { color: "#e2e8f0", size: 14 } },
                  paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8" },
                  xaxis: { title: { text: "Slow MA" }, gridcolor: "#334155" },
                  yaxis: { title: { text: "Fast MA" }, gridcolor: "#334155" },
                  margin: { t: 40, r: 80, b: 60, l: 60 }, autosize: true,
                }}
                useResizeHandler style={{ width: "100%", height: "450px" }}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-2">Best Combination</h3>
                <div className="space-y-1 text-sm">
                  <div><span className="text-slate-400">Fast MA: </span><span className="text-green-400 font-semibold">{result.best.fast}</span></div>
                  <div><span className="text-slate-400">Slow MA: </span><span className="text-green-400 font-semibold">{result.best.slow}</span></div>
                  <div><span className="text-slate-400">Sharpe: </span><span className="text-purple-400 font-semibold">{result.best.sharpe.toFixed(3)}</span></div>
                </div>
              </div>
              <div className="bg-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-2">Statistics</h3>
                <div className="space-y-1 text-sm">
                  <div><span className="text-slate-400">Mean: </span><span>{result.stats.mean.toFixed(3)}</span></div>
                  <div><span className="text-slate-400">Median: </span><span>{result.stats.median.toFixed(3)}</span></div>
                  <div><span className="text-slate-400">Max: </span><span>{result.stats.max.toFixed(3)}</span></div>
                  <div><span className="text-slate-400">Valid: </span><span>{result.stats.valid_count}</span></div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-64 text-slate-500 text-sm">Configure parameter ranges and run a sweep</div>
        )}
      </div>
    </div>
  );
}
