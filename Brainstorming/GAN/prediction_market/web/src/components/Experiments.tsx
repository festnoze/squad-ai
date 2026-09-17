import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";
import type { AgentSummary, DatasetSummary, Fold, Job, RunDetail, RunSummary } from "../types";
import { agentColor, agentName, date, errorMessage, foldName, providerName, providerCurrency, remember, stored } from "../util";
import { Leaderboard } from "./Leaderboard";

const descriptions: Record<string, string> = {
  follower: "Suit la probabilité du marché, sans passer d'ordre. La référence pour mesurer la qualité des prévisions.",
  trend: "Prolonge de façon bornée le mouvement récent des prix. Une hypothèse simple de poursuite de tendance.",
  revert: "Anticipe un retour vers la moyenne récente. Une hypothèse simple de correction des écarts.",
};

export function Experiments({ dataset, agents, requestedRun = "" }: { dataset: DatasetSummary; agents: AgentSummary[]; requestedRun?: string }) {
  const [provider, setProvider] = useState(dataset.providers.includes("kalshi") ? "kalshi" : dataset.providers[0] ?? "");
  const [fold, setFold] = useState<Fold>("validation");
  const [agentIds, setAgentIds] = useState(agents.map(a => a.id));
  const [seed, setSeed] = useState("7");
  const [bankroll, setBankroll] = useState("1000");
  const [maxMarkets, setMaxMarkets] = useState("12");
  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<Job | null>(() => {
    const id = stored("pmx.pendingJob");
    return id ? { job_id: id, status: "queued", run_id: null, error: null } : null;
  });
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [selectedRun, setSelectedRun] = useState(stored("pmx.selectedRun") ?? "");
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => { if (requestedRun) setSelectedRun(requestedRun); }, [requestedRun]);

  useEffect(() => {
    let current = true; setHistoryError(""); setHistoryLoading(true);
    api.runs().then(result => {
      if (!current) return;
      setHistory(result.runs);
      setSelectedRun(previous => result.runs.some(run => run.run_id === previous) ? previous : result.runs[0]?.run_id ?? "");
    }).catch(error => { if (current) setHistoryError(errorMessage(error)); }).finally(() => { if (current) setHistoryLoading(false); });
    return () => { current = false; };
  }, [revision]);
  useEffect(() => {
    setDetail(null); setDetailError("");
    if (!selectedRun) { setDetailLoading(false); return; }
    remember("pmx.selectedRun", selectedRun);
    let current = true; setDetailLoading(true);
    api.run(selectedRun).then(result => { if (current) setDetail(result); })
      .catch(error => { if (current) setDetailError(errorMessage(error)); })
      .finally(() => { if (current) setDetailLoading(false); });
    return () => { current = false; };
  }, [selectedRun, revision]);
  useEffect(() => {
    if (!job || !running) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api.job(job.job_id);
        if (cancelled) return;
        setPollError(""); setJob(result);
        if (result.status === "completed" || result.status === "failed") {
          remember("pmx.pendingJob", null);
          if (result.run_id) { setSelectedRun(result.run_id); setRevision(value => value + 1); }
          return;
        }
      } catch (error) {
        if (cancelled) return;
        setPollError(errorMessage(error));
      }
      if (!cancelled) timer = setTimeout(poll, 1500);
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [job?.job_id, running]);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setPollError("");
    if (!agentIds.length) { setError("Sélectionnez au moins une stratégie."); return; }
    setSubmitting(true);
    try {
      const result = await api.startRun({ dataset: dataset.name, provider, fold, agent_ids: agentIds, seed: Number(seed), bankroll_cents: Math.round(Number(bankroll) * 100), max_markets: Number(maxMarkets) });
      setJob(result); remember("pmx.pendingJob", result.job_id);
    } catch (error) { setError(errorMessage(error)); }
    finally { setSubmitting(false); }
  };
  return <section aria-label="Expériences">
    <div className="section-heading"><div><span className="eyebrow">DE L'HYPOTHÈSE À L'OBSERVATION</span><h2>Votre première comparaison</h2><p>Un échantillon borné, des stratégies explicites et un journal rejouable.</p></div><span className="tag exploratory">Moteur v2 · exécution locale</span></div>
    <div className="experiments-layout">
      <aside className="experiment-sidebar">
        <form className="panel run-form" onSubmit={submit}>
          <div className="form-heading"><span className="step-number">01</span><h3>Configurer l'expérience</h3></div>
          <label><span>Jeu de données</span><input value={dataset.name} readOnly /></label>
          <div className="form-two"><label><span>Plateforme</span><select value={provider} onChange={e => setProvider(e.target.value)}>{dataset.providers.map(p => <option key={p} value={p}>{providerName(p)}</option>)}</select></label><label><span>Échantillon</span><select value={fold} onChange={e => setFold(e.target.value as Fold)}><option value="validation">Validation</option><option value="train">Entraînement</option></select></label></div>
          <fieldset><legend>Stratégies à comparer</legend><div className="agent-options">{agents.map(agent => <label className={`agent-option ${agentIds.includes(agent.id) ? "checked" : ""}`} key={agent.id}><input type="checkbox" checked={agentIds.includes(agent.id)} onChange={() => setAgentIds(ids => ids.includes(agent.id) ? ids.filter(id => id !== agent.id) : [...ids, agent.id])} /><span><strong><i style={{ background: agentColor(agent.id) }} />{agentName(agent.id)}</strong><small>{descriptions[agent.id] ?? agent.description}</small></span></label>)}</div></fieldset>
          <details className="provenance"><summary>Paramètres fixes des stratégies</summary>{agents.map(agent => <div key={agent.id}><strong>{agentName(agent.id)}</strong><dl>{Object.entries(agent.parameters).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>{!Object.keys(agent.parameters).length && <p className="small">Probabilité du marché, aucun ordre.</p>}</div>)}</details>
          <div className="form-two"><label><span>Marchés maximum</span><input type="number" min="1" max="30" step="1" required value={maxMarkets} onChange={e => setMaxMarkets(e.target.value)} /></label><label><span>Graine aléatoire</span><input type="number" min="0" max="2147483647" step="1" required value={seed} onChange={e => setSeed(e.target.value)} /></label></div>
          <label><span>Capital initial par stratégie ({providerCurrency(provider)})</span><input type="number" min="1" max="10000000" step="0.01" required value={bankroll} onChange={e => setBankroll(e.target.value)} /></label>
          <p className="form-note">Même graine et mêmes paramètres : même expérience. Jusqu'à 30 marchés du même fournisseur, hors échantillon scellé.</p>
          {error && <div className="error-box" role="alert">{error}</div>}
          <button className="button primary launch-button" type="submit" disabled={submitting || running || !agentIds.length || !provider}>{submitting || running ? <><span className="loader light" />{submitting ? "Envoi…" : "Exécution en cours…"}</> : <>Lancer la comparaison <span aria-hidden="true">→</span></>}</button>
          {!agents.length && <p className="error-text">Aucune stratégie disponible. Vérifiez le registre du serveur.</p>}
        </form>
        {job && <div className={`job-box ${job.status}`} role="status" aria-live="polite"><strong>{job.status === "queued" ? "Expérience en attente" : job.status === "running" ? "Calcul en cours" : job.status === "completed" ? "Expérience terminée" : "Échec de l'expérience"}</strong><p>{job.status === "failed" ? job.error ?? "Le serveur a interrompu le calcul." : running ? "Le moteur calcule les décisions, les exécutions et les résultats. Vous pouvez continuer à explorer les données." : "Les résultats sont enregistrés et disponibles ci-contre."}</p><span className="mono">{job.job_id}</span>{pollError && <><p className="error-text">Suivi interrompu : {pollError} Nouvelle tentative automatique.</p><button className="text-button" onClick={() => { setJob(null); setPollError(""); remember("pmx.pendingJob", null); setRevision(r => r + 1); }}>Fermer ce suivi</button><p className="small">Fermer le suivi n'annule pas un calcul sur le serveur.</p></>}</div>}
        <section className="panel history-panel" aria-label="Historique"><div className="history-heading"><h3>Expériences enregistrées</h3><button className="text-button" onClick={() => setRevision(r => r + 1)} disabled={historyLoading} aria-label="Actualiser l'historique">↻</button></div>
          {historyError && <p role="alert" className="error-text">{historyError}</p>}
          {historyLoading && !history.length ? <p className="muted small">Chargement de l'historique…</p> : !history.length && <p className="muted small">Votre première expérience apparaîtra ici. Les résultats restent disponibles après fermeture du navigateur.</p>}
          <div className="history-list">{history.map(run => <button key={run.run_id} className={`history-item ${selectedRun === run.run_id ? "selected" : ""}`} onClick={() => setSelectedRun(run.run_id)} aria-pressed={selectedRun === run.run_id}><strong>{providerName(run.provider)} <span>{run.n_markets} marchés</span></strong><span>{foldName(run.fold)} · {run.agent_ids.length} stratégies · {run.currency}</span><small>{date(run.created_at, true)} UTC · graine {run.seed}</small></button>)}</div>
        </section>
      </aside>
      <div className="experiment-results" aria-busy={detailLoading}>
        {detailError && <div role="alert" className="error-box">{detailError}<button onClick={() => setRevision(r => r + 1)}>Réessayer</button></div>}
        {detailLoading && <div className="panel empty"><span className="loader" />Ouverture des résultats…</div>}
        {detail && <Leaderboard detail={detail} />}
        {!detailLoading && !detail && !detailError && <div className="panel result-placeholder"><div className="placeholder-chart" aria-hidden="true"><svg viewBox="0 0 320 130"><path d="M10 105H310M10 70H310M10 35H310" stroke="#e3e9e8" fill="none" /><path d="M10 100L70 78L130 88L190 44L250 50L310 17" stroke="#a2c4c7" strokeWidth="3" fill="none" strokeDasharray="5 6" /></svg></div><span className="eyebrow">UNE QUESTION. UNE EXPÉRIENCE.</span><h3>Le marché est-il difficile à battre ?</h3><p>Comparez la référence marché à deux stratégies simples. Inspectez ensuite les prévisions, les positions et chaque exécution pour comprendre le résultat.</p><ol><li><span>1</span>Choisissez une plateforme et vos stratégies.</li><li><span>2</span>Lancez le calcul sur un échantillon limité.</li><li><span>3</span>Comparez la qualité et le résultat économique.</li></ol><p className="small muted">Le graphique ci-dessus est un repère visuel, sans données de résultat.</p></div>}
      </div>
    </div>
  </section>;
}

