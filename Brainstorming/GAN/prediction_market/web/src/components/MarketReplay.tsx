import { useEffect, useMemo, useRef, useState } from "react";
import { fetchBacktest } from "../api";
import type { Backtest, MarketMeta } from "../types";
import { agentColor, brierStr, dollars, pct, shortT, skillStr } from "../util";
import { PriceChart } from "./PriceChart";

const DEFAULT_ON = ["market_follower", "momentum", "calibrated", "contrarian"];

export function MarketReplay({ market }: { market: MarketMeta }) {
  const [bt, setBt] = useState<Backtest | null>(null);
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set(DEFAULT_ON));
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setBt(null);
    setErr(null);
    fetchBacktest(market.id)
      .then((b) => {
        setBt(b);
        setTick(0);
        setPlaying(false);
      })
      .catch((e) => setErr(String(e)));
  }, [market.id]);

  const saved = useRef(tick);
  saved.current = tick;
  useEffect(() => {
    if (!playing || !bt) return;
    const last = bt.ticks.length - 1;
    const id = window.setInterval(() => {
      const cur = saved.current;
      if (cur >= last) {
        setPlaying(false);
        return;
      }
      setTick(cur + 1);
    }, 650);
    return () => window.clearInterval(id);
  }, [playing, bt]);

  const resultsById = useMemo(() => {
    const m: Record<string, Backtest["results"][number]> = {};
    bt?.results.forEach((r) => (m[r.agent_id] = r));
    return m;
  }, [bt]);

  if (err) return <div className="err">Failed to load: {err}</div>;
  if (!bt) return <div className="loading">Loading backtest…</div>;

  const last = bt.ticks.length - 1;
  const revealed = tick >= last;
  const row = bt.ticks[tick];
  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  // agents ranked for the side table: by final mean Brier (best first)
  const ranked = [...bt.agent_ids].sort(
    (a, b) => resultsById[a].mean_brier_micro - resultsById[b].mean_brier_micro,
  );

  return (
    <div className="replay">
      <div className="mkt-head">
        <div className="mkt-q">
          <span className={`src ${market.source}`}>{market.source === "imported" ? "real data" : "reconstructed path"}</span>
          <h2>{market.question}</h2>
          <div className="mkt-meta">
            <span className="cat">{market.category}</span>
            <span>resolved {market.resolved_date}</span>
            <span className={revealed ? (market.resolution ? "reso yes" : "reso no") : "reso hidden"}>
              {revealed ? (market.resolution ? "outcome: YES" : "outcome: NO") : "outcome hidden until the end"}
            </span>
          </div>
        </div>
      </div>

      <PriceChart bt={bt} tick={tick} selected={selected} revealed={revealed} />

      <div className="legend-row">
        {bt.agent_ids.map((id) => (
          <button
            key={id}
            className={`legend-chip ${selected.has(id) ? "on" : ""}`}
            onClick={() => toggle(id)}
            style={selected.has(id) ? { borderColor: agentColor(id), color: agentColor(id) } : undefined}
          >
            <span className="swatch" style={{ background: agentColor(id) }} />
            {id}
          </button>
        ))}
      </div>

      <div className="transport">
        <button className="tbtn" onClick={() => setTick(0)} disabled={tick === 0}>
          ⏮
        </button>
        <button className="tbtn" onClick={() => setTick(Math.max(0, tick - 1))} disabled={tick === 0}>
          ◀
        </button>
        <button
          className="tbtn play"
          onClick={() => {
            if (revealed) setTick(0);
            setPlaying(!playing);
          }}
        >
          {playing ? "⏸ Pause" : revealed ? "↻ Replay" : "▶ Play"}
        </button>
        <button className="tbtn" onClick={() => setTick(Math.min(last, tick + 1))} disabled={revealed}>
          ▶
        </button>
        <button className="tbtn" onClick={() => setTick(last)} disabled={revealed}>
          ⏭
        </button>
        <input
          className="scrub"
          type="range"
          min={0}
          max={last}
          value={tick}
          onChange={(e) => setTick(Number(e.target.value))}
        />
        <span className="tread">
          {shortT(row.t)} · {row.price}c
        </span>
      </div>

      <table className="agent-table">
        <thead>
          <tr>
            <th>agent</th>
            <th>says now</th>
            <th>equity</th>
            <th>mean Brier</th>
            <th>vs market</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((id) => {
            const st = row.agents[id];
            const r = resultsById[id];
            const beats = r.mean_brier_micro < r.market_brier_micro;
            return (
              <tr key={id} className={selected.has(id) ? "sel" : ""} onClick={() => toggle(id)}>
                <td>
                  <span className="swatch" style={{ background: agentColor(id) }} /> {id}
                  {id === "market_follower" && <span className="base">baseline</span>}
                </td>
                <td className="num">{pct(st.prob_ppm)}%</td>
                <td className={`num ${st.equity >= 0 ? "pos" : "neg"}`}>{dollars(st.equity)}</td>
                <td className="num">{brierStr(r.mean_brier_micro)}</td>
                <td className={`num ${beats ? "pos" : "neg"}`}>{revealed ? skillStr(r.market_brier_micro - r.mean_brier_micro) : "-"}</td>
              </tr>
            );
          })}
          <tr className="market-row">
            <td>the market (its own price)</td>
            <td className="num">{row.price}%</td>
            <td className="num">-</td>
            <td className="num">{brierStr(bt.results[0].market_brier_micro)}</td>
            <td className="num">baseline</td>
          </tr>
        </tbody>
      </table>
      {market.notes && <p className="notes">{market.notes}</p>}
    </div>
  );
}
