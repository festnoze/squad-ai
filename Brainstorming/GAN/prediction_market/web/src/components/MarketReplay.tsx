import { useEffect, useState } from "react";
import { api } from "../api";
import type { RunDetail, RunMarketReplay } from "../types";
import { agentColor, agentName, count, date, decimal, errorMessage, money } from "../util";
import { PriceChart } from "./PriceChart";

export function MarketReplay({ detail }: { detail: RunDetail }) {
  const [marketId, setMarketId] = useState(detail.markets[0]?.id ?? "");
  const [replay, setReplay] = useState<RunMarketReplay | null>(null);
  const [cursor, setCursor] = useState(0);
  const [selected, setSelected] = useState<string[]>(detail.run.agent_ids);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!marketId) return;
    let current = true; setReplay(null); setError(""); setPlaying(false);
    api.replay(detail.run.run_id, marketId).then(result => { if (current) { setReplay(result); setCursor(Math.max(0, result.ticks.length - 1)); } })
      .catch(error => { if (current) setError(errorMessage(error)); });
    return () => { current = false; };
  }, [detail.run.run_id, marketId, reload]);
  useEffect(() => {
    if (!playing || !replay) return;
    const timer = setInterval(() => setCursor(index => {
      if (index >= replay.ticks.length - 1) { setPlaying(false); return index; }
      return index + 1;
    }), 250);
    return () => clearInterval(timer);
  }, [playing, replay]);
  const tick = replay?.ticks[cursor];
  const fills = replay?.fills.filter(fill => tick && fill.t_ms <= tick.t_ms && selected.includes(fill.agent_id)) ?? [];
  const market = detail.markets.find(m => m.id === marketId);
  return <section className="panel replay-panel" aria-label="Replay de l'expérience">
    <div className="section-heading small-heading"><div><span className="eyebrow">03 / COMPRENDRE LES DÉCISIONS</span><h3>Rejouer un marché</h3></div>{replay && <a className="text-button" href={`/api/runs/${encodeURIComponent(detail.run.run_id)}/markets/${encodeURIComponent(marketId)}/export`} download>Exporter le replay ↓</a>}</div>
    <label className="market-select"><span>Marché de l'expérience</span><select value={marketId} onChange={e => setMarketId(e.target.value)}>{detail.markets.map(m => <option key={m.id} value={m.id}>{m.question}</option>)}</select></label>
    {error && <div role="alert" className="error-box">{error}<button onClick={() => setReload(r => r + 1)}>Réessayer</button></div>}
    {!replay && !error && <div className="empty"><span className="loader" />Lecture du journal d'exécution…</div>}
    {replay && !replay.ticks.length && <div className="empty">Aucun événement à rejouer sur ce marché.</div>}
    {replay && tick && <>
      <div className="replay-agents">{replay.agent_ids.map(id => <label key={id} style={{ borderColor: selected.includes(id) ? agentColor(id) : undefined }}><input type="checkbox" checked={selected.includes(id)} onChange={() => setSelected(ids => ids.includes(id) ? ids.filter(a => a !== id) : [...ids, id])} /><i style={{ background: agentColor(id) }} />{agentName(id)}</label>)}</div>
      <PriceChart times={replay.ticks.map(t => t.t_ms)} series={[
        { id: "market", label: "Prix connu lors de la décision", color: "#173e4a", values: replay.ticks.map(t => t.price_bp / 100) },
        ...selected.map(id => ({ id, label: agentName(id), color: agentColor(id), values: replay.ticks.map(t => t.agents[id] ? t.agents[id].prob_ppm / 10000 : null) })),
      ]} cursor={cursor} onCursor={value => { setCursor(value); setPlaying(false); }} markers={replay.fills.filter(f => selected.includes(f.agent_id)).map(f => replay.ticks.findIndex(t => t.t_ms === f.t_ms)).filter(index => index >= 0)} title="Prix connu, probabilités des stratégies et exécutions" />
      <div className="replay-controls"><button className="button secondary icon-button" disabled={replay.ticks.length < 2} onClick={() => { if (cursor === replay.ticks.length - 1) setCursor(0); setPlaying(p => !p); }} aria-label={playing ? "Mettre le replay en pause" : "Lire le replay"}>{playing ? "Ⅱ" : "▶"}</button><input type="range" min="0" max={replay.ticks.length - 1} value={cursor} onChange={e => { setCursor(Number(e.target.value)); setPlaying(false); }} aria-label="Date du replay" /><div><strong>{date(tick.t_ms, true)} UTC</strong><span>Étape {cursor + 1} / {replay.ticks.length}</span></div></div>
      <p className="chart-note">La ligne de prix montre l'information connue lors de la prévision. Positions et capital sont mesurés en fin de barre. Les points ocre repèrent les exécutions.</p>
      <div className="table-scroll"><table className="data-table replay-table"><thead><tr><th>Stratégie à cet instant</th><th>Probabilité OUI</th><th>Position</th><th>Capital simulé</th></tr></thead><tbody>{selected.map(id => {
        const state = tick.agents[id];
        return <tr key={id}><td><span className="agent-dot" style={{ background: agentColor(id) }} />{agentName(id)}</td><td>{state ? `${decimal(state.prob_ppm / 10000, 1)} %` : "Indisponible"}</td><td>{state ? count(state.position) : "Indisponible"}</td><td>{state ? money(state.equity_cents, detail.run.currency) : "Indisponible"}</td></tr>;
      })}</tbody></table></div>
      <div className="news-heading"><h4>Exécutions jusqu'au curseur</h4><span>{count(fills.length)} exécution{fills.length > 1 ? "s" : ""}</span></div>
      {!fills.length ? <p className="muted small">Aucune exécution pour les stratégies affichées à cet instant.</p> : <div className="table-scroll fills-scroll"><table className="data-table"><thead><tr><th>Date UTC</th><th>Stratégie</th><th>Sens</th><th>Quantité</th><th>Prix OUI</th><th>Frais</th></tr></thead><tbody>{fills.slice().reverse().map((fill, index) => <tr key={index}><td>{date(fill.t_ms, true)}</td><td>{agentName(fill.agent_id)}</td><td><span className="tag subtle">{fill.side.toLowerCase() === "buy" ? "Achat" : fill.side.toLowerCase() === "sell" ? "Vente" : fill.side}</span></td><td>{count(fill.size)}</td><td>{decimal(fill.price_bp / 100, 1)} %</td><td>{money(fill.fee_cents, detail.run.currency)}</td></tr>)}</tbody></table></div>}
      {market && <p className="chart-note">Issue historique : {market.resolution ? "OUI" : "NON"}, résolue le {date(market.resolved_at_ms, true)} UTC. L'interface de recherche affiche cette issue ; les stratégies reçoivent seulement les informations disponibles à chaque instant.</p>}
    </>}
  </section>;
}
