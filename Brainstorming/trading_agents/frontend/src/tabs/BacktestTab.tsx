import { useState } from "react";
import { api } from "../api";
import type { TabProps, BacktestResult } from "../types";
import GlobalParams from "../components/GlobalParams";
import MetricsTable from "../components/MetricsTable";
import PriceChart from "../components/PriceChart";
import PortfolioChart from "../components/PortfolioChart";

type StrategyType = "ma_crossover" | "rsi_bb" | "adaptive";

export default function BacktestTab({
  globalParams,
  onGlobalParamsChange,
  symbols,
  onAddSymbol,
  onStatus,
  setLoading,
}: TabProps) {
  const [strategy, setStrategy] = useState<StrategyType>("ma_crossover");
  const [fastMa, setFastMa] = useState(10);
  const [slowMa, setSlowMa] = useState(50);
  const [rsiWindow, setRsiWindow] = useState(14);
  const [rsiLo, setRsiLo] = useState(30);
  const [rsiHi, setRsiHi] = useState(70);
  const [bbWindow, setBbWindow] = useState(20);
  const [bbAlpha, setBbAlpha] = useState(2.0);
  const [trendFast, setTrendFast] = useState(10);
  const [trendSlow, setTrendSlow] = useState(50);
  const [revRsiWindow, setRevRsiWindow] = useState(14);
  const [revRsiLo, setRevRsiLo] = useState(30);
  const [revRsiHi, setRevRsiHi] = useState(70);
  const [initCash, setInitCash] = useState(100000);
  const [fees, setFees] = useState(0.001);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState("");

  const { symbol, interval, start, end } = globalParams;

  const buildParams = () => {
    const base = { symbol, interval, start, end, strategy, init_cash: initCash, fees };
    switch (strategy) {
      case "ma_crossover":
        return { ...base, params: { fast_ma: fastMa, slow_ma: slowMa } };
      case "rsi_bb":
        return { ...base, params: { rsi_window: rsiWindow, rsi_lo: rsiLo, rsi_hi: rsiHi, bb_window: bbWindow, bb_alpha: bbAlpha } };
      case "adaptive":
        return { ...base, params: { fast_ma: trendFast, slow_ma: trendSlow, rsi_window: revRsiWindow, rsi_lo: revRsiLo, rsi_hi: revRsiHi } };
    }
  };

  const handleRun = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.runBacktest(buildParams());
      setResult(res.data);
      onStatus(`Backtest complete: ${res.data.metrics.total_return > 0 ? "+" : ""}${(res.data.metrics.total_return * 100).toFixed(2)}% return`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Backtest failed";
      setError(msg);
      onStatus(`Error: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const Slider = ({ label, value, onChange, min, max, step = 1 }: {
    label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number;
  }) => (
    <div className="mb-3">
      <label className="flex justify-between text-xs text-slate-400 mb-1">
        <span>{label}</span><span className="text-purple-400">{value}</span>
      </label>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-purple-500" />
    </div>
  );

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="w-[280px] shrink-0 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto">
        <GlobalParams params={globalParams} onChange={onGlobalParamsChange} symbols={symbols} onAddSymbol={onAddSymbol} />

        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Strategy</h3>

        <select value={strategy} onChange={(e) => setStrategy(e.target.value as StrategyType)}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-3 focus:outline-none focus:border-purple-500">
          <option value="ma_crossover">MA Crossover</option>
          <option value="rsi_bb">RSI + Bollinger Bands</option>
          <option value="adaptive">Adaptive</option>
        </select>

        {strategy === "ma_crossover" && (<>
          <Slider label="Fast MA" value={fastMa} onChange={setFastMa} min={5} max={100} />
          <Slider label="Slow MA" value={slowMa} onChange={setSlowMa} min={10} max={200} />
        </>)}

        {strategy === "rsi_bb" && (<>
          <Slider label="RSI Window" value={rsiWindow} onChange={setRsiWindow} min={5} max={30} />
          <Slider label="RSI Low" value={rsiLo} onChange={setRsiLo} min={10} max={40} />
          <Slider label="RSI High" value={rsiHi} onChange={setRsiHi} min={60} max={90} />
          <Slider label="BB Window" value={bbWindow} onChange={setBbWindow} min={10} max={50} />
          <Slider label="BB Alpha" value={bbAlpha} onChange={setBbAlpha} min={1} max={4} step={0.1} />
        </>)}

        {strategy === "adaptive" && (<>
          <Slider label="Trend Fast" value={trendFast} onChange={setTrendFast} min={5} max={50} />
          <Slider label="Trend Slow" value={trendSlow} onChange={setTrendSlow} min={20} max={200} />
          <Slider label="Rev RSI Window" value={revRsiWindow} onChange={setRevRsiWindow} min={5} max={30} />
          <Slider label="Rev RSI Low" value={revRsiLo} onChange={setRevRsiLo} min={10} max={40} />
          <Slider label="Rev RSI High" value={revRsiHi} onChange={setRevRsiHi} min={60} max={90} />
        </>)}

        <hr className="border-slate-700 my-3" />
        <label className="block text-xs text-slate-400 mb-1">Initial Cash</label>
        <input type="number" value={initCash} onChange={(e) => setInitCash(Number(e.target.value))}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-3 focus:outline-none focus:border-purple-500" />
        <label className="block text-xs text-slate-400 mb-1">Fees</label>
        <input type="number" step={0.0001} value={fees} onChange={(e) => setFees(Number(e.target.value))}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-3 focus:outline-none focus:border-purple-500" />

        <button onClick={handleRun}
          className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white rounded text-sm font-medium transition-colors cursor-pointer">
          Run Backtest
        </button>
      </div>

      <div className="flex-1 p-6 overflow-y-auto">
        {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-sm text-red-300">{error}</div>}
        {result ? (
          <div className="space-y-4">
            <div className="bg-slate-800 rounded-lg p-4">
              <PriceChart prices={result.price_data} entries={result.entries} exits={result.exits} title={`${symbol} - Buy/Sell Signals`} />
            </div>
            <div className="bg-slate-800 rounded-lg p-4">
              <PortfolioChart portfolioValues={result.portfolio_values} buyHoldValues={result.buy_hold_values} title="Portfolio Value vs Buy & Hold" />
            </div>
            <div className="bg-slate-800 rounded-lg p-4">
              <h3 className="text-sm font-semibold text-slate-200 mb-3">Performance Metrics</h3>
              <MetricsTable metrics={result.metrics} />
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-64 text-slate-500 text-sm">Configure parameters and run a backtest</div>
        )}
      </div>
    </div>
  );
}
