import { useEffect, useState } from "react";
import { fetchMarkets } from "./api";
import { Leaderboard } from "./components/Leaderboard";
import { MarketReplay } from "./components/MarketReplay";
import { WalkForwardView } from "./components/WalkForwardView";
import type { MarketMeta } from "./types";

type Tab = "replay" | "leaderboard" | "walkforward";

export function App() {
  const [markets, setMarkets] = useState<MarketMeta[]>([]);
  const [marketId, setMarketId] = useState<string>("");
  const [tab, setTab] = useState<Tab>("replay");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchMarkets()
      .then((ms) => {
        setMarkets(ms);
        if (ms.length) setMarketId(ms[0].id);
        else setErr("No markets. Run: pmx data seed");
      })
      .catch((e) => setErr(String(e)));
  }, []);

  const market = markets.find((m) => m.id === marketId);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">pmx</span>
          <span className="tagline">prediction-market backtest arena · reality is the referee</span>
        </div>
        <nav className="tabs">
          <button className={tab === "replay" ? "on" : ""} onClick={() => setTab("replay")}>
            Market replay
          </button>
          <button className={tab === "leaderboard" ? "on" : ""} onClick={() => setTab("leaderboard")}>
            Leaderboard
          </button>
          <button className={tab === "walkforward" ? "on" : ""} onClick={() => setTab("walkforward")}>
            Walk-forward
          </button>
        </nav>
      </header>

      {err && <div className="err">{err} <span className="hint">(is the API up on :8175?)</span></div>}

      {tab === "replay" && (
        <div className="replay-layout">
          <aside className="mkt-list">
            <div className="mkt-list-head">{markets.length} resolved markets</div>
            {markets.map((m) => (
              <button
                key={m.id}
                className={`mkt-item ${m.id === marketId ? "on" : ""}`}
                onClick={() => setMarketId(m.id)}
              >
                <span className="mi-q">{m.question}</span>
                <span className="mi-meta">
                  <span className="cat">{m.category}</span>
                  <span className="mi-date">{m.resolved_date}</span>
                </span>
              </button>
            ))}
          </aside>
          <main className="replay-main">{market && <MarketReplay market={market} />}</main>
        </div>
      )}

      {tab === "leaderboard" && (
        <main className="single">
          <Leaderboard />
        </main>
      )}
      {tab === "walkforward" && (
        <main className="single">
          <WalkForwardView />
        </main>
      )}
    </div>
  );
}
