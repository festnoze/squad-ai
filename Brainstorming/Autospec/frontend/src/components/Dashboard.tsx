import { useEffect, useState } from "react";
import { errorMessage, getMetrics } from "../api";
import { Metrics } from "../types";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}

export function Dashboard({ onClose }: { onClose: () => void }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMetrics()
      .then(setMetrics)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  const pct = (v: number | null) => (v != null ? `${v}/100` : "—");

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal dashboard" onClick={(e) => e.stopPropagation()}>
        <div className="dashboard-head">
          <h2>📊 Dashboard de l'usine</h2>
          <button className="ghost small-btn" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        </div>
        {error && <div className="edit-error">{error}</div>}
        {!metrics ? (
          <p className="placeholder">Chargement…</p>
        ) : (
          <div className="metrics-grid">
            <Stat label="Projets" value={metrics.projects} />
            <Stat label="Coût total" value={`$${metrics.total_cost_usd.toFixed(4)}`} />
            <Stat label="Appels agent" value={metrics.total_agent_calls} />
            <Stat label="Stories" value={metrics.total_stories} />
            <Stat label="Terminées" value={metrics.stories_done} />
            <Stat label="Échouées" value={metrics.stories_failed} />
            <Stat label="Taux de succès" value={`${metrics.success_rate}%`} />
            <Stat label="Tentatives moy." value={metrics.avg_attempts} />
            <Stat label="Coût / story" value={`$${metrics.cost_per_story.toFixed(4)}`} />
            <Stat label="Qualité moy." value={pct(metrics.avg_quality)} />
            <Stat label="Mutation moy." value={pct(metrics.avg_mutation)} />
            <Stat
              label="Couverture moy."
              value={metrics.avg_coverage != null ? `${metrics.avg_coverage}%` : "—"}
            />
            <Stat label="Findings" value={metrics.findings} />
            <Stat label="Régressions" value={metrics.regressions} />
          </div>
        )}
      </div>
    </div>
  );
}
