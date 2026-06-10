import { useState } from "react";
import Plot from "react-plotly.js";
import { api } from "../api";
import type { TabProps, TickerInfo, TimeSeriesPoint } from "../types";
import GlobalParams from "../components/GlobalParams";

export default function DataTab({
  globalParams,
  onGlobalParamsChange,
  symbols,
  onAddSymbol,
  onStatus,
  setLoading,
}: TabProps) {
  const [tickerInfo, setTickerInfo] = useState<TickerInfo | null>(null);
  const [priceData, setPriceData] = useState<TimeSeriesPoint[]>([]);
  const [barCount, setBarCount] = useState(0);
  const [error, setError] = useState("");

  const { symbol, interval, start, end } = globalParams;

  const handleLoad = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.loadData({ symbol, interval, start, end });
      const data = res.data;
      setPriceData(data.prices ?? []);
      setBarCount(data.bars ?? data.bar_count ?? data.prices?.length ?? 0);
      onStatus(`Loaded ${data.bars ?? "?"} bars for ${symbol}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load data";
      setError(msg);
      onStatus(`Error: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const handleGetInfo = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.getTickerInfo(symbol);
      setTickerInfo(res.data);
      onStatus(`Fetched info for ${symbol}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to get ticker info";
      setError(msg);
      onStatus(`Error: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="w-[280px] shrink-0 bg-slate-800 border-r border-slate-700 p-4 overflow-y-auto">
        <GlobalParams
          params={globalParams}
          onChange={onGlobalParamsChange}
          symbols={symbols}
          onAddSymbol={onAddSymbol}
        />

        <button
          onClick={handleLoad}
          className="w-full py-2 bg-purple-600 hover:bg-purple-700 text-white rounded text-sm font-medium mb-2 transition-colors cursor-pointer"
        >
          Load Data
        </button>
        <button
          onClick={handleGetInfo}
          className="w-full py-2 bg-slate-600 hover:bg-slate-500 text-white rounded text-sm font-medium transition-colors cursor-pointer"
        >
          Get Info
        </button>
      </div>

      <div className="flex-1 p-6 overflow-y-auto">
        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 mb-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {tickerInfo && (
          <div className="bg-slate-800 rounded-lg p-4 mb-4">
            <h3 className="text-sm font-semibold text-slate-200 mb-2">Ticker Info</h3>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div><span className="text-slate-400">Name: </span><span>{tickerInfo.name}</span></div>
              <div><span className="text-slate-400">Symbol: </span><span>{tickerInfo.symbol}</span></div>
              <div><span className="text-slate-400">Currency: </span><span>{tickerInfo.currency}</span></div>
            </div>
          </div>
        )}

        {barCount > 0 && (
          <div className="bg-slate-800 rounded-lg p-4 mb-4">
            <span className="text-sm text-slate-400">
              Loaded <span className="text-purple-400 font-semibold">{barCount}</span> bars | {start} to {end}
            </span>
          </div>
        )}

        {priceData.length > 0 ? (
          <div className="bg-slate-800 rounded-lg p-4">
            <Plot
              data={[{
                x: priceData.map((p) => p.date),
                y: priceData.map((p) => p.value),
                type: "scatter", mode: "lines",
                name: symbol, line: { color: "#a855f7", width: 1.5 },
              }]}
              layout={{
                title: { text: `${symbol} Price`, font: { color: "#e2e8f0", size: 14 } },
                paper_bgcolor: "transparent", plot_bgcolor: "transparent",
                font: { color: "#94a3b8" },
                xaxis: { gridcolor: "#334155", linecolor: "#334155" },
                yaxis: { gridcolor: "#334155", linecolor: "#334155", tickprefix: "$" },
                margin: { t: 40, r: 20, b: 40, l: 60 }, autosize: true,
              }}
              useResizeHandler
              style={{ width: "100%", height: "400px" }}
            />
          </div>
        ) : (
          <div className="flex items-center justify-center h-64 text-slate-500 text-sm">
            Load data to see the price chart
          </div>
        )}
      </div>
    </div>
  );
}
