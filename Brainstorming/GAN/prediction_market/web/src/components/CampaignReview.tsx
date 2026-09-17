import { useEffect, useState } from "react";
import { api } from "../api";
import type { CampaignAnalysis } from "../types";
import { errorMessage } from "../util";

export function CampaignReview({ campaignId, completed }: { campaignId: string; completed: boolean }) {
  const [analysis, setAnalysis] = useState<CampaignAnalysis | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setAnalysis(null); setError("");
    const load = async () => {
      try { const next = await api.analysis(campaignId); if (active) { setAnalysis(next); setError(""); } }
      catch (reason) { if (active) setError(errorMessage(reason)); }
    };
    void load(); const timer = setInterval(() => void load(), 5000);
    return () => { active = false; clearInterval(timer); };
  }, [campaignId]);
  const request = async () => {
    setBusy(true); setError("");
    try { setAnalysis(await api.requestAnalysis(campaignId)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };
  const configure = async (enabled: boolean) => {
    setBusy(true); setError("");
    try { await api.analysisSettings(enabled); setAnalysis(await api.analysis(campaignId)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };
  const running = analysis?.status === "queued" || analysis?.status === "running";
  const report = analysis?.report;
  return <section className="panel campaign-review" aria-label="Analyse de la campagne par Codex">
    <div className="candidate-title"><div><span className="eyebrow">APRÈS LA CAMPAGNE</span><h3>Ce que les résultats nous apprennent</h3></div><span className="tag">Codex · abonnement ChatGPT</span></div>
    <label className="analysis-toggle"><input type="checkbox" checked={analysis?.automatic_enabled ?? false} disabled={busy || !analysis} onChange={event => void configure(event.target.checked)} />Analyser automatiquement les nouvelles campagnes terminées</label>
    <p className="muted small">Un appel par résultat nouveau, avec le quota de l’abonnement connecté à Codex. Le rapport propose des tests ; il ne modifie ni les stratégies ni les résultats et ne lance aucune campagne.</p>
    {(error || analysis?.error) && <p role="alert" className="error-text">{error || analysis?.error}</p>}
    {running && <p role="status">{analysis?.status === "queued" ? "Analyse en attente…" : "Codex examine les résultats et leurs limites…"}</p>}
    {!completed && <p className="muted small">L’analyse démarrera après la validation des finalistes.</p>}
    {completed && !report && !running && <button className="button secondary" disabled={busy} onClick={() => void request()}>{analysis?.status === "failed" ? "Réessayer l’analyse" : "Analyser cette campagne"}</button>}
    {report && <>
      <p className="analysis-summary">{report.summary}</p><p className="analysis-verdict">{report.verdict}</p>
      <details><summary>Points saillants et preuves</summary>{report.findings.map((finding, index) => <article className="analysis-finding" key={index}><h4>{finding.title}</h4><p>{finding.evidence}</p><p className="muted">{finding.interpretation}</p></article>)}</details>
      <h4>Prochains tests proposés</h4><ol className="analysis-tests">{report.next_tests.map((test, index) => <li key={index}><strong>{test.priority} · {test.hypothesis}</strong><p>{test.protocol}</p><p className="muted">Critère de succès : {test.success_criterion}</p></li>)}</ol>
      <details><summary>Limites de cette interprétation</summary><ul>{report.limitations.map((limit, index) => <li key={index}>{limit}</li>)}</ul></details>
      <div className="analysis-exports"><a href={`/api/campaigns/${encodeURIComponent(campaignId)}/analysis/export`} download>Exporter le rapport ↓</a><a href={`/api/campaigns/${encodeURIComponent(campaignId)}/analysis/evidence`} download>Voir les preuves chiffrées ↓</a></div>
    </>}
  </section>;
}
