import { useState } from "react";

export interface GlobalParamsData {
  symbol: string;
  interval: string;
  start: string;
  end: string;
}

interface GlobalParamsProps {
  params: GlobalParamsData;
  onChange: (params: GlobalParamsData) => void;
  symbols: string[];
  onAddSymbol: (symbol: string) => void;
  disabled?: boolean;
}

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"];

export default function GlobalParams({
  params,
  onChange,
  symbols,
  onAddSymbol,
  disabled = false,
}: GlobalParamsProps) {
  const [customSymbol, setCustomSymbol] = useState("");

  const update = (patch: Partial<GlobalParamsData>) => {
    onChange({ ...params, ...patch });
  };

  const handleAddSymbol = () => {
    const s = customSymbol.toUpperCase().trim();
    if (s) {
      onAddSymbol(s);
      update({ symbol: s });
      setCustomSymbol("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleAddSymbol();
  };

  return (
    <div className="bg-slate-750 border-b border-slate-700 pb-3 mb-3">
      <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
        Market Data
      </h3>

      <label className="block text-xs text-slate-400 mb-1">Symbol</label>
      <select
        value={params.symbol}
        onChange={(e) => update({ symbol: e.target.value })}
        disabled={disabled}
        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-2 focus:outline-none focus:border-purple-500 disabled:opacity-50"
      >
        {symbols.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      <div className="flex gap-1 mb-3">
        <input
          type="text"
          value={customSymbol}
          onChange={(e) => setCustomSymbol(e.target.value.toUpperCase())}
          onKeyDown={handleKeyDown}
          placeholder="Add symbol..."
          disabled={disabled}
          className="flex-1 px-2 py-1.5 bg-slate-700 border border-slate-600 rounded text-xs text-slate-200 focus:outline-none focus:border-purple-500 disabled:opacity-50"
        />
        <button
          onClick={handleAddSymbol}
          disabled={disabled || !customSymbol.trim()}
          className="px-2 py-1.5 bg-slate-600 hover:bg-slate-500 text-slate-200 rounded text-xs disabled:opacity-30 cursor-pointer"
        >
          +
        </button>
      </div>

      <label className="block text-xs text-slate-400 mb-1">Interval</label>
      <select
        value={params.interval}
        onChange={(e) => update({ interval: e.target.value })}
        disabled={disabled}
        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-sm text-slate-200 mb-3 focus:outline-none focus:border-purple-500 disabled:opacity-50"
      >
        {INTERVALS.map((iv) => (
          <option key={iv} value={iv}>
            {iv}
          </option>
        ))}
      </select>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Start</label>
          <input
            type="date"
            value={params.start}
            onChange={(e) => update({ start: e.target.value })}
            disabled={disabled}
            className="w-full px-2 py-2 bg-slate-700 border border-slate-600 rounded text-xs text-slate-200 focus:outline-none focus:border-purple-500 disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">End</label>
          <input
            type="date"
            value={params.end}
            onChange={(e) => update({ end: e.target.value })}
            disabled={disabled}
            className="w-full px-2 py-2 bg-slate-700 border border-slate-600 rounded text-xs text-slate-200 focus:outline-none focus:border-purple-500 disabled:opacity-50"
          />
        </div>
      </div>
    </div>
  );
}
