import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";
import { CampaignReview } from "./CampaignReview";
import { CampaignPerformance } from "./CampaignPerformance";
import type { CampaignDetail, CampaignJob, CampaignSummary, DatasetSummary, DiscoveryCandidate, DiscoveryPeriodResult } from "../types";
import { count, date, decimal, errorMessage, money, providerCurrency, providerName, remember, stored } from "../util";

const budgetOptions = [
  { value: 12, label: "Rapide", note: "12 essais" },
  { value: 30, label: "Équilibré", note: "30 essais" },
  { value: 60, label: "Étendu", note: "60 essais" },
];

const campaignStatus = (status: CampaignSummary["status"]) => ({
  queued: "En attente", running: "Recherche", validating: "Validation",
  completed: "Terminée", failed: "Échec", cancelled: "Arrêtée",
}[status]);

const candidateStatus = (candidate: DiscoveryCandidate) => candidate.selected ? "Finaliste" : ({
  running: "En cours", completed: "Évalué", rejected: "Rejeté", failed: "Échec",
}[candidate.status]);

const familyName = (family: string) => ({
  level: "Retour vers un niveau", trend: "Tendance", revert: "Retour à la moyenne", rule: "Règle découverte",
}[family] ?? family);

function numberParameter(parameters: Record<string, unknown>, name: string): number | null {
  const value = parameters[name];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

const probability = (basisPoints: number) => `${decimal(basisPoints / 100, basisPoints % 100 ? 2 : 0)} %`;
const basisPoints = (value: number) => `${count(value)} pb`;

function predicateText(predicate: unknown): string | null {
  if (!predicate || typeof predicate !== "object") return null;
  const row = predicate as Record<string, unknown>;
  if (typeof row.feature !== "string" || typeof row.op !== "string" || typeof row.value !== "number") return null;
  const feature = ({
    last_price_bp: "dernier prix", ret_1b_bp: "variation sur 1 barre", ret_7b_bp: "variation sur 7 barres",
    realised_vol_bp_30b: "volatilité réalisée sur 30 barres",
    dist_from_high_bp_30b: "distance au plus haut sur 30 barres",
    dist_from_low_bp_30b: "distance au plus bas sur 30 barres",
  } as Record<string, string>)[row.feature] ?? row.feature.replaceAll("_", " ");
  const operator = ({ le: "≤", lt: "<", ge: "≥", gt: ">", eq: "=" } as Record<string, string>)[row.op] ?? row.op;
  const value = row.feature === "last_price_bp" ? probability(row.value) : row.feature.includes("_bp") ? basisPoints(row.value) : count(row.value);
  return `${feature} ${operator} ${value}`;
}

function candidateExplanation(candidate: DiscoveryCandidate): string {
  const parameters = candidate.parameters;
  const lookback = numberParameter(parameters, "lookback_bars");
  const anchor = numberParameter(parameters, "anchor_bp");
  const strength = numberParameter(parameters, "strength_permille");
  const edge = numberParameter(parameters, "edge_min_bp");
  const position = numberParameter(parameters, "max_position");
  const pieces: string[] = [];
  if (candidate.family === "level" && anchor !== null) pieces.push(`Ramène la probabilité vers le niveau cible ${probability(anchor)}`);
  else if (candidate.family === "trend" && lookback !== null) pieces.push(`Prolonge le mouvement des ${count(lookback)} dernières barres terminées`);
  else if (candidate.family === "revert" && lookback !== null) pieces.push(`Anticipe un retour vers la moyenne des ${count(lookback)} dernières barres terminées`);
  else if (candidate.family === "rule" && candidate.rule) {
    const condition = candidate.rule.condition;
    const predicates = Array.isArray(condition) ? condition.map(predicateText).filter((value): value is string => value !== null) : [];
    const claim = candidate.rule.claim && typeof candidate.rule.claim === "object" ? candidate.rule.claim as Record<string, unknown> : null;
    const side = claim?.direction === 1 ? "OUI" : claim?.direction === -1 ? "NON" : null;
    if (predicates.length && side) pieces.push(`Quand ${predicates.join(" et ")}, déplace l’estimation vers ${side}`);
  }
  if (strength !== null) pieces.push(`force ${decimal(strength / 10, 0)} %`);
  if (edge !== null) pieces.push(`écart minimal ${basisPoints(edge)}`);
  if (position !== null) pieces.push(`exposition maximale ${count(position)} contrats`);
  return pieces.length ? `${pieces.join(" ; ")}.` : "Définition structurée disponible dans l’audit technique.";
}

const aggregate = (results: DiscoveryPeriodResult[]) => results.length ? {
  pnl: results.reduce((sum, result) => sum + result.pnl_cents, 0),
  fees: results.reduce((sum, result) => sum + result.fees_cents, 0),
  fills: results.reduce((sum, result) => sum + result.n_fills, 0),
  markets: results.reduce((sum, result) => sum + result.n_markets, 0),
  drawdown: Math.max(...results.map(result => result.max_drawdown_bp)),
} : null;

const parameterName = (name: string) => ({
  lookback_bars: "Fenêtre", threshold_bp: "Seuil", edge_bp: "Marge exigée",
  max_edge_bp: "Correction maximale", edge_min_bp: "Écart minimal", strength_permille: "Force",
  anchor_bp: "Niveau cible", max_position: "Exposition maximale", trade_size: "Taille d’ordre",
  horizon_bars: "Horizon",
}[name] ?? name.replaceAll("_", " "));

function parameterValue(name: string, value: unknown): string {
  if (typeof value !== "number") return typeof value === "object" ? JSON.stringify(value) : String(value);
  if (name === "anchor_bp") return probability(value);
  if (name.endsWith("_bp")) return basisPoints(value);
  if (name === "strength_permille") return `${decimal(value / 10, 0)} %`;
  if (name.endsWith("_bars")) return `${count(value)} barres`;
  if (name === "max_position") return `${count(value)} contrats`;
  return count(value);
}

function MetricBlock({ title, results, currency }: { title: string; results: DiscoveryPeriodResult[]; currency: string }) {
  const metrics = aggregate(results);
  return <div className="candidate-metrics"><strong>{title}</strong>{metrics ? <dl>
    <div><dt>Résultat net</dt><dd className={metrics.pnl > 0 ? "positive" : metrics.pnl < 0 ? "negative" : ""}>{money(metrics.pnl, currency)}</dd></div>
    <div><dt>Frais</dt><dd>{money(metrics.fees, currency)}</dd></div>
    <div><dt>Repli max.</dt><dd>{decimal(metrics.drawdown / 100)} %</dd></div>
    <div><dt>Exécutions</dt><dd>{count(metrics.fills)}</dd></div>
    <div><dt>Marchés-périodes</dt><dd>{count(metrics.markets)}</dd></div>
  </dl> : <p>Pas encore mesuré.</p>}{results.length > 0 && <div className="period-table-scroll"><table className="period-table"><thead><tr><th>Période</th><th>Net</th><th>Frais</th><th>Repli</th><th>Exéc.</th><th>Marchés traités</th></tr></thead><tbody>{results.map(result => <tr key={`${result.period}-${result.run_id}`}><td><strong>{result.period}</strong><small>{date(result.t0_ms)} → {date(result.t1_ms)}</small></td><td className={result.pnl_cents > 0 ? "positive" : result.pnl_cents < 0 ? "negative" : ""}>{money(result.pnl_cents, currency)}</td><td>{money(result.fees_cents, currency)}</td><td>{decimal(result.max_drawdown_bp / 100)} %</td><td>{count(result.n_fills)}</td><td>{count(result.traded_market_ids?.length ?? 0)}</td></tr>)}</tbody></table></div>}</div>;
}

function CandidateDetail({ candidate, currency, inspectRun }: { candidate: DiscoveryCandidate; currency: string; inspectRun: (id: string) => void }) {
  const validationRun = candidate.validation_results.find(result => result.run_id)?.run_id;
  return <article className="panel candidate-detail">
    <div className="candidate-title"><div><span className="eyebrow">ESSAI {candidate.trial_number + 1}</span><h3>{familyName(candidate.family)}</h3></div><span className={`tag candidate-${candidate.status}`}>{candidateStatus(candidate)}</span></div>
    <div className="rule-box"><span>Logique exécutée</span><strong>{candidateExplanation(candidate)}</strong></div>
    <div className="parameter-grid">{Object.entries(candidate.parameters).map(([name, value]) => <div key={name}><span>{parameterName(name)}</span><strong>{parameterValue(name, value)}</strong></div>)}</div>
    {!Object.keys(candidate.parameters).length && !candidate.rule_text && <p className="muted small">Cette proposition ne déclare aucun paramètre supplémentaire.</p>}
    <div className="period-comparison"><MetricBlock title="Recherche · entraînement" results={candidate.train_results} currency={currency} /><MetricBlock title="Contrôle · validation ultérieure" results={candidate.validation_results} currency={currency} /></div>
    {!!candidate.rejection_reasons.length && <div className="rejection-box"><strong>Pourquoi cette proposition n’est pas retenue</strong><ul>{candidate.rejection_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div>}
    {candidate.error && <p className="error-text" role="alert">Calcul interrompu : {candidate.error}</p>}
    {validationRun && <button className="button secondary" onClick={() => inspectRun(validationRun)}>Ouvrir le journal et le replay <span aria-hidden="true">→</span></button>}
    {(candidate.rule_text || candidate.rule) && <details className="provenance"><summary>Définition technique exacte</summary>{candidate.rule_text && <p className="technical-rule">{candidate.rule_text}</p>}{candidate.rule && <pre>{JSON.stringify(candidate.rule, null, 2)}</pre>}</details>}
  </article>;
}

export function Discovery({ dataset, onInspectRun }: { dataset: DatasetSummary; onInspectRun: (id: string) => void }) {
  const [provider, setProvider] = useState(dataset.providers.includes("polymarket") ? "polymarket" : dataset.providers[0] ?? "");
  const [trials, setTrials] = useState(30);
  const [seed, setSeed] = useState("7");
  const [bankroll, setBankroll] = useState("1000");
  const [maxMarkets, setMaxMarkets] = useState("60");
  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<CampaignJob | null>(() => {
    const jobId = stored("pmx.discoveryJob"); const campaignId = stored("pmx.discoveryCampaign");
    return jobId ? { job_id: jobId, campaign_id: campaignId, status: "queued", run_id: null, error: null } : null;
  });
  const [history, setHistory] = useState<CampaignSummary[]>([]);
  const [selectedId, setSelectedId] = useState(stored("pmx.selectedCampaign") ?? "");
  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    let current = true; setLoading(true);
    api.campaigns().then(result => { if (!current) return; setHistory(result.campaigns); setSelectedId(previous => result.campaigns.some(item => item.campaign_id === previous) ? previous : result.campaigns[0]?.campaign_id ?? ""); })
      .catch(reason => { if (current) setError(errorMessage(reason)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [revision]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    let current = true; remember("pmx.selectedCampaign", selectedId);
    const load = () => api.campaign(selectedId).then(result => { if (!current) return; setDetail(result); setError(""); setSelectedCandidateId(previous => result.candidates.some(candidate => candidate.candidate_id === previous) ? previous : result.selected_candidate_ids[0] ?? result.candidates[0]?.candidate_id ?? ""); }).catch(reason => { if (current) setError(errorMessage(reason)); });
    void load();
    const timer = setInterval(() => { if (detail?.status === "running" || detail?.status === "validating" || running) void load(); }, 1800);
    return () => { current = false; clearInterval(timer); };
  }, [selectedId, revision, running, detail?.status]);

  useEffect(() => {
    if (!job || !running) return;
    let current = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api.job(job.job_id);
        if (!current) return;
        const next = { ...result, campaign_id: job.campaign_id };
        setJob(next);
        if (result.status === "completed" || result.status === "failed" || result.status === "cancelled") {
          remember("pmx.discoveryJob", null); setRevision(value => value + 1); return;
        }
      } catch (reason) { if (current) setError(errorMessage(reason)); }
      if (current) timer = setTimeout(poll, 1500);
    };
    void poll(); return () => { current = false; clearTimeout(timer); };
  }, [job?.job_id, running]);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(""); setSubmitting(true);
    try {
      const result = await api.startCampaign({ dataset: dataset.name, provider, seed: Number(seed), n_trials: trials, max_markets: Number(maxMarkets), bankroll_cents: Math.round(Number(bankroll) * 100), n_splits: 3, finalists: 3 });
      setJob(result); remember("pmx.discoveryJob", result.job_id); remember("pmx.discoveryCampaign", result.campaign_id);
      if (result.campaign_id) { setSelectedId(result.campaign_id); setRevision(value => value + 1); }
    } catch (reason) { setError(errorMessage(reason)); } finally { setSubmitting(false); }
  };

  const stop = async () => {
    if (!job) return;
    try { const result = await api.cancelJob(job.job_id); setJob({ ...result, campaign_id: job.campaign_id }); }
    catch (reason) { setError(errorMessage(reason)); }
  };
  const selectedCandidate = useMemo(() => detail?.candidates.find(candidate => candidate.candidate_id === selectedCandidateId) ?? null, [detail, selectedCandidateId]);
  const progress = detail?.progress;

  return <section aria-label="Découverte automatique">
    <div className="section-heading"><div><span className="eyebrow">RECHERCHE AUTOMATIQUE BORNÉE</span><h2>Découvrir des stratégies</h2><p>Explorer des paramètres et des règles sur l’entraînement, puis contrôler les finalistes sur une période ultérieure.</p></div><span className="tag exploratory">Résultats exploratoires</span></div>
    <div className="discovery-layout">
      <aside className="discovery-sidebar">
        <form className="panel run-form" onSubmit={submit}>
          <div className="form-heading"><span className="step-number">01</span><h3>Définir la campagne</h3></div>
          <label><span>Jeu de données</span><input value={dataset.name} readOnly /></label>
          <label><span>Plateforme et unité de compte</span><select value={provider} onChange={event => setProvider(event.target.value)}>{dataset.providers.map(item => <option key={item} value={item}>{providerName(item)}</option>)}</select></label>
          <fieldset><legend>Budget de recherche</legend><div className="budget-options">{budgetOptions.map(option => <button type="button" key={option.value} className={trials === option.value ? "selected" : ""} onClick={() => setTrials(option.value)} aria-pressed={trials === option.value}><strong>{option.label}</strong><span>{option.note}</span></button>)}</div></fieldset>
          <p className="form-note">Chaque essai compte dans le budget, y compris un rejet ou un échec. Plus d’essais augmentent le coût et le risque de sélection opportuniste.</p>
          <details className="advanced-settings"><summary>Réglages reproductibles</summary><div className="form-two"><label><span>Marchés maximum</span><input type="number" min="6" max="200" value={maxMarkets} onChange={event => setMaxMarkets(event.target.value)} required /></label><label><span>Graine</span><input type="number" min="0" max="2147483647" value={seed} onChange={event => setSeed(event.target.value)} required /></label></div><label><span>Capital simulé par candidat ({providerCurrency(provider)})</span><input type="number" min="100" max="10000000" step="0.01" value={bankroll} onChange={event => setBankroll(event.target.value)} required /></label><p>Trois découpages chronologiques d’entraînement, puis au plus trois finalistes en validation.</p></details>
          {error && <div className="error-box" role="alert">{error}</div>}
          <button className="button primary launch-button" disabled={submitting || running || !provider}>{submitting || running ? <><span className="loader light" />{submitting ? "Création…" : "Recherche en cours…"}</> : <>Lancer {trials} essais <span aria-hidden="true">→</span></>}</button>
          {running && <button type="button" className="text-button" onClick={stop}>Arrêter après l’essai en cours</button>}
          <p className="form-note">La période scellée reste inaccessible. Aucun ordre réel n’est produit.</p>
        </form>
        <section className="panel history-panel"><div className="history-heading"><h3>Campagnes enregistrées</h3><button className="text-button" onClick={() => setRevision(value => value + 1)} aria-label="Actualiser">↻</button></div>{loading && !history.length && <p className="muted small">Chargement…</p>}{!loading && !history.length && <p className="muted small">La première campagne apparaîtra ici et restera disponible après fermeture.</p>}<div className="history-list">{history.map(item => <button key={item.campaign_id} className={`history-item ${selectedId === item.campaign_id ? "selected" : ""}`} onClick={() => setSelectedId(item.campaign_id)}><strong>{providerName(item.config.provider)} <span>{campaignStatus(item.status)}</span></strong><span>{item.progress.completed_trials}/{item.progress.total_trials} essais · {item.currency}</span><small>{item.created_at ? `${date(item.created_at, true)} UTC` : item.campaign_id}</small></button>)}</div></section>
      </aside>
      <div className="discovery-results">
        {!detail && !loading && <div className="panel result-placeholder"><span className="eyebrow">UNE CAMPAGNE, DES ESSAIS TRAÇABLES</span><h3>Chercher sans masquer les échecs</h3><p>Choisissez une plateforme et un budget. Chaque proposition conservera sa règle, ses paramètres, ses résultats d’entraînement et son motif de rejet.</p></div>}
        {detail && <>
          <section className="panel campaign-overview"><div className="candidate-title"><div><span className="eyebrow">CAMPAGNE {detail.campaign_id}</span><h3>{campaignStatus(detail.status)}</h3><p className="muted small">{detail.dataset} · {providerName(detail.config.provider)} · {detail.currency.toUpperCase()}</p></div><a className="button secondary" href={`/api/campaigns/${encodeURIComponent(detail.campaign_id)}/export`} download>Exporter JSON ↓</a></div>
            <div className="progress-track" aria-label={`${progress?.completed_trials ?? 0} essais terminés sur ${progress?.total_trials ?? detail.config.n_trials}`}><i style={{ width: `${Math.min(100, 100 * (progress?.completed_trials ?? 0) / Math.max(1, progress?.total_trials ?? detail.config.n_trials))}%` }} /></div>
            <div className="campaign-facts"><span><strong>{progress?.completed_trials ?? 0} / {progress?.total_trials ?? detail.config.n_trials}</strong> essais évalués</span><span><strong>{detail.selected_candidate_ids.length}</strong> finalistes</span><span><strong>{money(detail.baseline?.pnl_cents ?? 0, detail.currency)}</strong> référence sans ordre</span><span><strong>{detail.currency}</strong> unité séparée</span></div>
            <p className="chart-note">L’objectif sert à classer les essais sur l’entraînement. Les totaux d’entraînement additionnent des simulations indépendantes, chacune repartant du même capital. La validation ultérieure n’ajuste plus les paramètres. Être finaliste signifie seulement avoir été sélectionné par cet objectif interne ; cela ne signifie pas être rentable.</p>
            {detail.error && <p className="error-text" role="alert">{detail.error}</p>}
            {detail.status === "completed" && !detail.candidates.some(candidate => candidate.status === "completed" && candidate.objective !== null && candidate.objective > (detail.baseline?.objective ?? 0)) && <p className="analysis-verdict">Aucune stratégie ne dépasse la référence sans ordre sur l’objectif d’entraînement. Les finalistes restent des candidats exploratoires.</p>}
          </section>
          {detail.status === "completed" && <CampaignPerformance key={detail.campaign_id} campaign={detail} />}
          <CampaignReview campaignId={detail.campaign_id} completed={detail.status === "completed"} />
          <div className="candidate-workspace">
            <section className="panel candidate-list"><div className="list-heading"><strong>Tous les candidats</strong><span>{detail.candidates.length} conservés</span></div>{!detail.candidates.length && <div className="empty compact">Les candidats apparaîtront après le premier essai.</div>}<div>{detail.candidates.map(candidate => <button key={candidate.candidate_id} className={`candidate-row ${selectedCandidateId === candidate.candidate_id ? "selected" : ""}`} onClick={() => setSelectedCandidateId(candidate.candidate_id)}><span>#{candidate.trial_number + 1}</span><div><strong>{familyName(candidate.family)}</strong><small>{candidateStatus(candidate)}{candidate.objective === null ? "" : ` · objectif ${decimal(candidate.objective, 4)}`}</small></div><i className={`candidate-state ${candidate.status}`} /></button>)}</div></section>
            {selectedCandidate ? <CandidateDetail candidate={selectedCandidate} currency={detail.currency} inspectRun={onInspectRun} /> : <div className="panel empty">Sélectionnez un candidat pour examiner ses paramètres.</div>}
          </div>
          {detail.mining && <details className="panel mining-panel"><summary>Recherche de règles et audit</summary><div className="mining-summary">{Object.entries(detail.mining).map(([name, value]) => <div key={name}><span>{parameterName(name)}</span><strong>{Array.isArray(value) ? value.join(", ") || "Aucun" : typeof value === "object" ? JSON.stringify(value) : String(value)}</strong></div>)}</div></details>}
          {!!detail.limitations.length && <details className="dataset-limitations"><summary><span className="notice-icon">i</span> Limites de cette campagne <span className="summary-hint">Lire avant d’interpréter</span></summary><div><ul>{detail.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></div></details>}
        </>}
      </div>
    </div>
  </section>;
}
