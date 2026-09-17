import { useEffect, useState } from "react";
import { api } from "../api";
import type { DatasetSummary, MarketDetail, MarketSummary } from "../types";
import { count, date, decimal, errorMessage, foldName, providerName } from "../util";
import { PriceChart } from "./PriceChart";

export function Explorer({ dataset, onExperiment }: { dataset: DatasetSummary; onExperiment: () => void }) {
  const [provider, setProvider] = useState("");
  const [fold, setFold] = useState("");
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [markets, setMarkets] = useState<MarketSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<MarketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => { const timer = setTimeout(() => { setSearch(query.trim()); setPage(1); }, 250); return () => clearTimeout(timer); }, [query]);
  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    api.markets(dataset.name, { provider, fold, category, q: search, page: String(page), page_size: "15" }).then(result => {
      if (!current) return;
      setMarkets(result.items); setTotal(result.total);
      setSelected(previous => result.items.some(m => m.id === previous) ? previous : result.items[0]?.id ?? "");
    }).catch(error => { if (current) setError(errorMessage(error)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [dataset.name, provider, fold, category, search, page, reload]);
  useEffect(() => {
    setDetail(null); setDetailError("");
    if (!selected) { setDetailLoading(false); return; }
    let current = true; setDetailLoading(true);
    api.market(dataset.name, selected).then(result => { if (current) setDetail(result); })
      .catch(error => { if (current) setDetailError(errorMessage(error)); })
      .finally(() => { if (current) setDetailLoading(false); });
    return () => { current = false; };
  }, [dataset.name, selected, reload]);
  const resetPage = (setter: (value: string) => void, value: string) => { setter(value); setPage(1); };

  return <section aria-label="Explorateur de marchés">
    <div className="section-heading"><div><span className="eyebrow">01 / COMPRENDRE LES DONNÉES</span><h2>Explorer les marchés</h2><p>Les observations réelles, avant toute stratégie.</p></div><button className="button secondary" onClick={onExperiment}>Créer une expérience <span aria-hidden="true">↗</span></button></div>
    <div className="filters">
      <label className="search-field"><span>Rechercher un marché</span><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Question ou mot-clé…" /></label>
      <label><span>Plateforme</span><select value={provider} onChange={e => resetPage(setProvider, e.target.value)}><option value="">Toutes les plateformes</option>{dataset.providers.map(p => <option key={p} value={p}>{providerName(p)}</option>)}</select></label>
      <label><span>Échantillon</span><select value={fold} onChange={e => resetPage(setFold, e.target.value)}><option value="">Entraînement + validation</option><option value="train">Entraînement</option><option value="validation">Validation</option></select></label>
      <label><span>Catégorie</span><select value={category} onChange={e => resetPage(setCategory, e.target.value)}><option value="">Toutes les catégories</option>{dataset.categories.map(c => <option key={c}>{c}</option>)}</select></label>
    </div>
    {error && <div role="alert" className="error-box">{error}<button onClick={() => setReload(r => r + 1)}>Réessayer</button></div>}
    <div className="explorer-layout">
      <aside className="market-list panel" aria-label="Liste des marchés" aria-busy={loading}>
        <div className="list-heading"><strong>{loading ? "Chargement…" : `${count(total)} marchés`}</strong><span>Hors échantillon scellé</span></div>
        <div className="market-items">{!loading && !markets.length && <div className="empty compact">Aucun marché ne correspond à ces filtres.</div>}{markets.map(m => <button key={m.id} className={`market-item ${selected === m.id ? "selected" : ""}`} onClick={() => setSelected(m.id)} aria-pressed={selected === m.id}>
          <span className="market-meta"><span>{providerName(m.provider)}</span><span>{m.category}</span></span>
          <strong>{m.question}</strong>
          <span className="market-item-foot"><span>{foldName(m.fold)}</span><span>{date(m.resolved_at_ms)}</span></span>
        </button>)}</div>
        <div className="pagination"><button disabled={page === 1 || loading} onClick={() => setPage(p => p - 1)} aria-label="Page précédente">←</button><span>{page} / {Math.max(1, Math.ceil(total / 15))}</span><button disabled={page * 15 >= total || loading} onClick={() => setPage(p => p + 1)} aria-label="Page suivante">→</button></div>
      </aside>
      <div className="market-detail panel" aria-busy={detailLoading}>
        {detailError && <div role="alert" className="error-box">{detailError}<button onClick={() => setReload(r => r + 1)}>Réessayer</button></div>}
        {detailLoading && <div className="empty"><span className="loader" />Lecture de l'historique du marché…</div>}
        {!detailLoading && !detail && !detailError && <div className="empty">Sélectionnez un marché pour inspecter ses données.</div>}
        {detail && <MarketView detail={detail} interval={dataset.interval_min} />}
      </div>
    </div>
  </section>;
}

function MarketView({ detail, interval }: { detail: MarketDetail; interval: number }) {
  const { market, bars, news } = detail;
  const [cursor, setCursor] = useState(bars.length - 1);
  useEffect(() => { setCursor(bars.length - 1); }, [market.id, bars.length]);
  const bar = bars[Math.max(0, Math.min(cursor, bars.length - 1))];
  const visibleNews = news.filter(item => item.visible_from_ms <= (bar ? bar.t_ms + interval * 60000 : market.resolved_at_ms));
  const safeLink = (url: string) => /^https?:\/\//i.test(url);
  return <>
    <div className="detail-heading"><div className="inline-tags"><span className="tag">{providerName(market.provider)}</span><span className="tag subtle">{foldName(market.fold)}</span><span className="tag subtle">{market.currency}</span></div><span className={`outcome ${market.resolution ? "yes" : "no"}`}>Résolu : {market.resolution ? "OUI" : "NON"}</span></div>
    <h3 className="market-question">{market.question}</h3>
    <div className="detail-metadata"><span>{market.category}</span><span>{count(market.n_bars)} barres</span><span>Volume : {decimal(market.volume_milli / 1000, 0)}</span><span>Résolu le {date(market.resolved_at_ms)}</span></div>
    <div className="chart-heading"><div><span className="eyebrow">PROBABILITÉ IMPLICITE DU MARCHÉ</span><strong>{bar ? `${decimal(bar.close_bp / 100, 1)} %` : "Indisponible"}</strong></div><span>{bar ? date(bar.t_ms) : ""} · UTC</span></div>
    <PriceChart times={bars.map(b => b.t_ms)} series={[{ id: "market", label: "Prix de clôture OUI", color: "#176376", values: bars.map(b => b.close_bp / 100) }]} volumes={bars.map(b => b.volume_milli)} cursor={cursor} onCursor={setCursor} title="Historique du prix OUI et du volume" />
    {bars.length > 1 && <input className="time-slider" type="range" min="0" max={bars.length - 1} value={cursor} onChange={e => setCursor(Number(e.target.value))} aria-label="Date de l'observation du marché" />}
    <div className="chart-note">{interval === 1440 ? "Barres journalières" : `Barres de ${interval} minutes`} · Volumes observés, sans garantie de liquidité disponible pour un ordre.</div>
    <p className="chart-note">Informations disponibles à la date sélectionnée. Rattachement automatique non audité : certaines associations peuvent être hors sujet.</p>
    <div className="news-heading"><h4>Informations datées</h4><span>{count(visibleNews.length)} élément{visibleNews.length > 1 ? "s" : ""}</span></div>
    {!visibleNews.length ? <p className="muted small">Aucune information associée disponible à la date sélectionnée.</p> : <div className="news-list">{visibleNews.map(n => <article key={n.id} className="news-item"><div><span>{n.source}</span><time>{date(n.published_at_ms, true)} UTC</time></div><p>{n.text}</p><footer>Visible à partir du {date(n.visible_from_ms, true)} UTC{safeLink(n.url) && <a href={n.url} target="_blank" rel="noreferrer">Voir la source ↗</a>}</footer></article>)}</div>}
    <details className="provenance"><summary>Provenance et identifiants</summary><dl><dt>Marché</dt><dd className="mono">{market.id}</dd><dt>Source</dt><dd>{market.source}</dd><dt>Cohorte</dt><dd className="mono">{market.cohort_id ?? "Non renseignée"}</dd><dt>Création</dt><dd>{date(market.created_at_ms, true)} UTC</dd><dt>{market.close_time_verified === false ? "Fin observée" : "Clôture"}</dt><dd>{date(market.close_at_ms, true)} UTC{market.close_time_verified === false ? " · heure contractuelle non vérifiée" : ""}</dd><dt>Sujets</dt><dd>{market.subjects.join(", ") || "Non renseignés"}</dd></dl></details>
  </>;
}

