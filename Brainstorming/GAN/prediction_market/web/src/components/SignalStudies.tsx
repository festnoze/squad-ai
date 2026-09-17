import { useEffect, useState } from "react";
import { api } from "../api";
import type { DatasetSummary, SignalRow, SignalStudy } from "../types";
import { count, date, decimal, errorMessage } from "../util";
import { PriceChart } from "./PriceChart";

const statusName = (status: SignalRow["status"]) => ({ candidate_for_replication: "À répliquer", not_retained: "Non retenu", inconclusive: "Indéterminé" })[status];
const effect = (value: number | null) => value === null ? "n/d" : `${decimal(value / 100, 2)} pp`;

function CalibrationChart({ rows }: { rows: SignalRow[] }) {
  const points = rows.filter(row => row.family === "calibration" && row.mean_price_bp !== null && row.win_rate !== null);
  if (!points.length) return <p className="muted">Aucune cible de calibration disponible.</p>;
  return <div className="calibration-figure"><svg viewBox="0 0 540 310" role="img" aria-label="Calibration : prix moyen contre fréquence gagnante"><title>Un point au-dessus de la diagonale indique une fréquence gagnante supérieure au prix moyen, avant coûts.</title>
    {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1="55" x2="490" y1={255 - value * 2.1} y2={255 - value * 2.1} className="grid-line" /><text x="42" y={259 - value * 2.1} textAnchor="end" className="axis-label">{value}%</text><text x={55 + value * 4.35} y="276" textAnchor="middle" className="axis-label">{value}%</text></g>)}
    <path d="M55 255L490 45" fill="none" stroke="#87989e" strokeDasharray="5 5" />
    {points.map(row => <circle key={row.variant_id} cx={55 + row.mean_price_bp! / 100 * 4.35} cy={255 - row.win_rate! * 210} r={Math.min(11, 4 + Math.sqrt(row.n_markets) / 2)} fill={row.n_markets >= 30 ? "#187888" : "#fff"} stroke="#187888" strokeWidth="2"><title>{row.label} : {decimal(row.win_rate! * 100, 1)} % gagnants, {row.n_markets} marchés</title></circle>)}
    <text x="55" y="22" className="axis-label">Fréquence gagnante observée</text><text x="270" y="301" textAnchor="middle" className="axis-label">Prix OUI moyen à l’observation</text>
  </svg><p className="small muted">Diagonale : fréquence égale au prix. Cercles vides : moins de 30 marchés. La taille reflète le nombre de marchés. Un écart visuel ne prouve ni significativité ni rentabilité.</p></div>;
}

export function SignalStudies({ dataset }: { dataset: DatasetSummary }) {
  const [studies, setStudies] = useState<SignalStudy[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<SignalStudy | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState("all");
  const [rowId, setRowId] = useState("");
  useEffect(() => {
    let current = true;
    api.signalStudies().then(data => { if (current) { const rows = data.studies.filter(row => row.dataset === dataset.name); setStudies(rows); setSelected(rows[0]?.study_id ?? ""); } }).catch(reason => { if (current) setError(errorMessage(reason)); });
    return () => { current = false; };
  }, [dataset.name]);
  useEffect(() => {
    if (!selected) return;
    let current = true; let timer: ReturnType<typeof setTimeout>;
    setDetail(null); setError("");
    const poll = async () => {
      try { const next = await api.signalStudy(selected); if (!current) return; setDetail(next); setError(""); if (next.status === "queued" || next.status === "running") timer = setTimeout(() => void poll(), 2000); }
      catch (reason) { if (current) { setError(errorMessage(reason)); timer = setTimeout(() => void poll(), 5000); } }
    };
    void poll(); return () => { current = false; clearTimeout(timer); };
  }, [selected]);
  const launch = async () => {
    setBusy(true); setError("");
    try { const next = await api.startSignalStudy(dataset.name); setStudies(previous => [next, ...previous.filter(row => row.study_id !== next.study_id)]); setDetail(next); setSelected(""); setTimeout(() => setSelected(next.study_id), 0); }
    catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  };
  const result = detail?.result;
  const rows = result?.rows.filter(row => row.activity === activity) ?? [];
  const focused = rows.find(row => row.variant_id === rowId) ?? rows[0];
  const compatible = dataset.coverage?.start_ms === 1704067200000 && dataset.coverage?.end_ms === 1719792000000 && dataset.interval_min === 60;
  const running = detail?.status === "queued" || detail?.status === "running";
  return <section aria-label="Étude des signaux">
    <div className="section-heading"><div><span className="eyebrow">R1 · MESURER AVANT D’OPTIMISER</span><h2>Existe-t-il un signal ?</h2><p>Des hypothèses fixées à l’avance, des effets bruts et leurs limites.</p></div><span className="tag exploratory">Entraînement uniquement</span></div>
    <div className="panel results-panel"><h3>Le protocole en clair</h3><p>28 variantes : dix tranches de prix et quatre retournements à 24/48 heures, chacun avec et sans condition d’activité récente. Une ancre par marché et variante. Les dates et seuils sont fixés ; aucun réglage automatique.</p>
      <p className="muted">Une présélection exige au moins 30 marchés, 3 semaines, 80 % de cibles disponibles, un effet brut supérieur à 1 point de probabilité et un effet positif en janvier, février et mars. Elle demande ensuite une réplication indépendante.</p>
      {!compatible && <p className="guide-example">Pour exécuter R1, choisissez <strong>polyarchive2024h1</strong> dans « Jeu de données actif ». Le protocole ne s’applique pas à une autre période.</p>}
      <button className="button primary" disabled={!compatible || busy || running} onClick={() => void launch()}>{running ? "Étude en cours…" : busy ? "Enregistrement…" : detail?.status === "completed" ? "Rouvrir le résultat enregistré" : "Exécuter le protocole R1"}</button>
      <p className="muted small">Une exécution identique réutilise son résultat. Cette étude mesure des signaux ; elle ne passe pas d’ordres et ne lance pas de campagne d’optimisation.</p>
      {!!studies.length && <label className="study-select">Étude enregistrée<select value={selected} onChange={event => setSelected(event.target.value)}>{studies.map(row => <option key={row.study_id} value={row.study_id}>{date(row.created_at, true)} · {row.study_id}</option>)}</select></label>}
      {(error || detail?.error) && <p role="alert" className="error-text">{error || detail?.error}</p>}
      {running && <p role="status">Vérification du corpus et calcul des 28 variantes. Le résultat sera conservé après fermeture de cet écran.</p>}
    </div>
    {result && <div className="results-stack signal-results">
      <section className="panel results-panel"><h3>Combien de données utiles ?</h3><div className="campaign-facts"><div><strong>{count(result.coverage.markets_with_bars)}</strong>marchés train avec observations</div><div><strong>{count(result.coverage.observed_hours)}</strong>heures avec transactions</div><div><strong>{decimal((result.coverage.observed_fraction ?? 0) * 100, 1)} %</strong>densité dans l’étude</div><div><strong>{result.rows.filter(row => row.status === "candidate_for_replication").length} / 28</strong>variantes à répliquer</div></div>
        <p>Corpus complet : {decimal(result.corpus_coverage.adapter_observed_hours / result.corpus_coverage.adapter_bars * 100, 1)} % d’heures observées, contre {decimal(result.reference_coverage.adapter_observed_hours / result.reference_coverage.adapter_bars * 100, 1)} % en 2023. Fin effective de l’étude : {date(result.effective_cutoff_ms, true)} UTC.</p>
        <p className="muted small">{count(result.protected_ids_count)} identifiants historiques protégés ; {count(result.excluded_overlap)} recoupements exclus. Les semaines et les marchés ne sont pas nécessairement des événements indépendants.</p>
      </section>
      <section className="panel results-panel"><div className="chart-toolbar"><h3>Calibration et activité</h3><label>Condition<select aria-label="Condition d’activité" value={activity} onChange={event => setActivity(event.target.value)}><option value="all">Tous les points d’observation</option><option value="active_fresh">Actif et prix récent</option></select></label></div><p className="muted small">Actif et récent : au moins 6 heures avec transactions sur les 24 dernières heures et prix observé depuis au plus 6 heures. Le filtre est appliqué au point d’observation déjà choisi.</p><CalibrationChart rows={rows} />
        <div className="table-scroll"><table className="data-table"><thead><tr><th>Hypothèse</th><th>Cibles / ancres</th><th>Couverture</th><th>Effet brut</th><th>Lecture</th></tr></thead><tbody>{rows.map(row => <tr key={row.variant_id}><td><button className="text-button" aria-pressed={focused?.variant_id === row.variant_id} onClick={() => setRowId(row.variant_id)}>{row.label}</button></td><td>{row.n_markets} / {row.n_anchors}</td><td>{row.target_coverage === null ? "n/d" : `${decimal(row.target_coverage * 100, 0)} %`}</td><td>{effect(row.mean_effect_bp)}</td><td>{statusName(row.status)}</td></tr>)}</tbody></table></div>
        <p className="muted small">pp = points de probabilité ; +1 pp = +100 points de base. Effets avant coûts. « Indéterminé » indique un support ou une couverture insuffisants. Les 14 lignes du filtre complémentaire restent accessibles ci-dessus.</p>
      </section>
      {focused && <section className="panel results-panel"><h3>{focused.label} · lecture par mois</h3><PriceChart times={focused.months.map(row => Date.parse(`${row.month}-01T00:00:00Z`))} series={[{ id: "signal", label: "Effet brut moyen (pp)", color: "#187888", values: focused.months.map(row => row.mean_effect_bp === null ? null : row.mean_effect_bp / 100) }, { id: "zero", label: "Aucun écart", color: "#86939a", values: focused.months.map(() => 0) }]} fixedDomain={false} title="Effet brut par mois, en points de probabilité" />
        <div className="chart-readout">{focused.months.map(row => <span key={row.month}>{row.month} : <b>{effect(row.mean_effect_bp)}</b> · {row.n} marchés</span>)}</div>
        {focused.family === "calibration" && focused.win_rate !== null && <p>Prix moyen : {decimal((focused.mean_price_bp ?? 0) / 100, 2)} %. Fréquence gagnante observée : {decimal(focused.win_rate * 100, 2)} % sur {focused.n_markets} marchés. Une série de réussites sur un petit échantillon de prix très élevés ne suffit pas à établir un avantage ; les résolutions manquantes peuvent inverser l’écart.</p>}
        <p>Moyenne des {focused.n_weeks} semaines : {effect(focused.weekly_mean_effect_bp)}. Intervalle approximatif à 95 % : {focused.weekly_interval_95_bp ? `${effect(focused.weekly_interval_95_bp[0])} à ${effect(focused.weekly_interval_95_bp[1])}` : "indisponible (moins de trois semaines)"}.</p><p className="muted small">Cet intervalle descriptif n’est pas corrigé pour les 28 variantes et ne constitue pas un test de rentabilité. Les semaines ont ici le même poids ; la moyenne du tableau donne le même poids à chaque marché.</p>
        <p className="small">Cibles manquantes : {Object.entries(focused.missing_reasons).map(([key, value]) => `${({label_after_cutoff:"résolution au-delà de la borne",target_after_cutoff:"horizon au-delà de la borne",target_after_resolution:"horizon après résolution",target_without_observed_trade:"aucune transaction à l’heure cible"} as Record<string,string>)[key] ?? key} (${value})`).join(" ; ") || "aucune pour les ancres retenues"}.</p>
      </section>}
      <section className="panel results-panel"><h3>Preuves et limites</h3><ul>{result.limitations.map(value => <li key={value}>{value}</li>)}</ul><div className="analysis-exports"><a href={`/api/signal-studies/${selected}/export`} download>Exporter les résultats ↓</a><a href={`/api/signal-studies/${selected}/observations`} download>Exporter les observations ↓</a></div><details><summary>Protocole exact et empreintes</summary><pre className="signal-protocol">{JSON.stringify(result.protocol, null, 2)}</pre><p className="mono">Données : {result.dataset_hash}</p><p className="mono">Protocole : {result.protocol_hash}</p></details></section>
    </div>}
  </section>;
}
