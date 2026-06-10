import { useState, useEffect } from "react";

const STORAGE_KEY = "trading-agents-symbols";

const DEFAULT_SYMBOLS = ["BTC-USD", "AAPL", "GOOGL", "MSFT", "ETH-USD"];

export function usePersistedSymbols() {
  const [symbols, setSymbols] = useState<string[]>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        return JSON.parse(stored);
      } catch {
        return DEFAULT_SYMBOLS;
      }
    }
    return DEFAULT_SYMBOLS;
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols));
  }, [symbols]);

  const addSymbol = (symbol: string) => {
    const s = symbol.toUpperCase().trim();
    if (s && !symbols.includes(s)) {
      setSymbols((prev) => [...prev, s]);
    }
  };

  return { symbols, addSymbol };
}
