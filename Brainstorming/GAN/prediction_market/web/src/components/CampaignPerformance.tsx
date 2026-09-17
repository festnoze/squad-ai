import { useEffect, useState } from "react";
import { api } from "../api";
import type { CampaignDetail } from "../types";
import { errorMessage } from "../util";
import { PerformanceChart } from "./PerformanceChart";
import type { PerformanceCurve } from "./PerformanceChart";

export function CampaignPerformance({ campaign }: { campaign: CampaignDetail }) {
  const [curves, setCurves] = useState<PerformanceCurve[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true; setLoading(true); setError(""); setCurves([]);
    const finalists = campaign.candidates.filter(row => row.selected && row.validation_results.length);
    const reference = finalists[0]?.validation_results[0];
    const compatible = finalists.every(row => { const period = row.validation_results[0]; return period.t0_ms === reference?.t0_ms && period.t1_ms === reference?.t1_ms && [...period.market_ids].sort().join() === [...reference.market_ids].sort().join(); });
    if (!compatible) { setError("Les finalistes n’ont pas été évalués sur les mêmes dates et marchés. Leurs courbes ne sont pas superposées."); setLoading(false); return; }
    Promise.all(finalists.map(async candidate => {
      const detail = await api.run(candidate.validation_results[0].run_id);
      if (detail.run.dataset_hash !== campaign.dataset_hash || detail.run.currency !== campaign.currency || detail.run.bankroll_cents !== campaign.config.bankroll_cents) throw new Error("Une courbe ne correspond pas aux données et au capital de la campagne.");
      return { id: candidate.candidate_id, label: `Essai ${candidate.trial_number + 1} · ${candidate.family === "revert" ? "Retour à la moyenne" : candidate.family === "trend" ? "Tendance" : candidate.family === "rule" ? "Règle" : "Niveau"}`, initial: detail.run.bankroll_cents, points: detail.equity.filter(row => row.agents[candidate.candidate_id] !== undefined).map(row => ({ t: row.t_ms, value: row.agents[candidate.candidate_id] })) };
    })).then(next => { if (active) setCurves(next); }).catch(reason => { if (active) setError(errorMessage(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [campaign.campaign_id]);
  return <div className="panel results-panel">{loading ? <p role="status">Chargement des courbes enregistrées…</p> : error ? <p role="alert" className="error-text">{error}</p> : <PerformanceChart curves={curves} currency={campaign.currency} independent />}</div>;
}
