import axios from "axios";

const API = axios.create({ baseURL: "http://localhost:8005/api" });

export const api = {
  // Data
  loadData: (params: {
    symbol: string;
    interval: string;
    start: string;
    end: string;
  }) => API.get("/data/load", { params }),
  getTickerInfo: (symbol: string) =>
    API.get("/data/ticker-info", { params: { symbol } }),
  getCache: () => API.get("/data/cache"),

  // Backtest
  runBacktest: (body: Record<string, unknown>) =>
    API.post("/backtest/run", body),
  getRegime: (params: Record<string, unknown>) =>
    API.get("/backtest/regime", { params }),

  // Sweep
  runSweep: (body: Record<string, unknown>) => API.post("/sweep/run", body),

  // Multi-strategy
  compareStrategies: (body: Record<string, unknown>) => API.post("/multi/compare", body),
  allocateStrategies: (body: Record<string, unknown>) => API.post("/multi/allocate", body),

  // Validation
  runMonteCarlo: (body: Record<string, unknown>) => API.post("/validate/montecarlo", body),
  runMultiAsset: (body: Record<string, unknown>) => API.post("/validate/multiasset", body),
};

// WebSocket for Optuna optimization
export function connectOptimizer(
  config: Record<string, unknown>,
  onMessage: (msg: Record<string, unknown>) => void,
  onClose: () => void,
) {
  const ws = new WebSocket("ws://localhost:8005/api/optimize/ws");
  ws.onopen = () => ws.send(JSON.stringify(config));
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onclose = onClose;
  return ws;
}

// WebSocket for evolution
export function connectEvolution(
  config: Record<string, unknown>,
  onMessage: (msg: Record<string, unknown>) => void,
  onClose: () => void,
) {
  const ws = new WebSocket("ws://localhost:8005/api/evolution/ws");
  ws.onopen = () => ws.send(JSON.stringify(config));
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onclose = onClose;
  return ws;
}
