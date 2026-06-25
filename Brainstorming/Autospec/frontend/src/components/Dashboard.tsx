import { useEffect, useState } from "react";
import { errorMessage, getMetrics } from "../api";
import { Metrics } from "../types";
import { useI18n } from "../i18n/i18n";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}

export function Dashboard({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
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
          <h2>{t("dashboard.title")}</h2>
          <button className="ghost small-btn" onClick={onClose} aria-label={t("common.close")}>
            ✕
          </button>
        </div>
        {error && <div className="edit-error">{error}</div>}
        {!metrics ? (
          <p className="placeholder">{t("common.loading")}</p>
        ) : (
          <div className="metrics-grid">
            <Stat label={t("dashboard.projects")} value={metrics.projects} />
            <Stat label={t("dashboard.totalCost")} value={`$${metrics.total_cost_usd.toFixed(4)}`} />
            <Stat label={t("dashboard.agentCalls")} value={metrics.total_agent_calls} />
            <Stat label={t("dashboard.stories")} value={metrics.total_stories} />
            <Stat label={t("dashboard.done")} value={metrics.stories_done} />
            <Stat label={t("dashboard.failed")} value={metrics.stories_failed} />
            <Stat label={t("dashboard.successRate")} value={`${metrics.success_rate}%`} />
            <Stat label={t("dashboard.avgAttempts")} value={metrics.avg_attempts} />
            <Stat label={t("dashboard.costPerStory")} value={`$${metrics.cost_per_story.toFixed(4)}`} />
            <Stat label={t("dashboard.avgQuality")} value={pct(metrics.avg_quality)} />
            <Stat label={t("dashboard.avgMutation")} value={pct(metrics.avg_mutation)} />
            <Stat
              label={t("dashboard.avgCoverage")}
              value={metrics.avg_coverage != null ? `${metrics.avg_coverage}%` : "—"}
            />
            <Stat label={t("dashboard.findings")} value={metrics.findings} />
            <Stat label={t("dashboard.regressions")} value={metrics.regressions} />
          </div>
        )}
      </div>
    </div>
  );
}
