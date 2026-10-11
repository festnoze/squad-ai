import { useEffect, useState } from "react";
import { errorMessage, getMetrics } from "../api";
import { FusionMetrics, Metrics } from "../types";
import { useEscapeToClose } from "../hooks";
import { useI18n } from "../i18n/i18n";
import { CostEstimateNote } from "./CostEstimateNote";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}

/**
 * P3 (GENERATION_FUSION_REVIEW): the cost of the merge/canary loop, read from
 * the `fusion` block of GET /api/metrics. Rendered only when the backend serves
 * that block (an older backend simply has no section). `suites_per_item` is the
 * headline number: how many full test suites the factory burns to deliver one
 * work item.
 */
function FusionSection({ fusion }: { fusion: FusionMetrics }) {
  const { t } = useI18n();
  const verdicts = Object.entries(fusion.canary_verdicts ?? {}).sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
  );
  return (
    <section className="fusion-block" data-testid="dashboard-fusion">
      <h3 className="fusion-title">{t("dashboard.fusionTitle")}</h3>
      <div className="metrics-grid">
        <Stat label={t("dashboard.fusionSuitesPerItem")} value={fusion.suites_per_item} />
        <Stat label={t("dashboard.fusionItemsDelivered")} value={fusion.items_delivered} />
        <Stat label={t("dashboard.fusionSuiteRuns")} value={fusion.suite_runs} />
        <Stat
          label={t("dashboard.fusionRequeues")}
          value={`${fusion.merge_requeues} / ${fusion.requeue_refunds}`}
        />
        <Stat label={t("dashboard.fusionCanaryReverts")} value={fusion.canary_reverts} />
        <Stat
          label={t("dashboard.fusionBatches")}
          value={`${fusion.canary_batches} / ${fusion.canary_bisect_reverts}`}
        />
        <Stat label={t("dashboard.fusionInfraRetries")} value={fusion.infra_retries} />
      </div>
      {verdicts.length > 0 && (
        <>
          <h4 className="fusion-subtitle">{t("dashboard.fusionVerdicts")}</h4>
          <ul className="fusion-verdicts" data-testid="fusion-verdicts">
            {verdicts.map(([verdict, count]) => (
              <li key={verdict}>
                <span className="fusion-verdict-key">{verdict}</span>
                <span className="fusion-verdict-count">{count}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export function Dashboard({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState("");
  useEscapeToClose(true, onClose);

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
        {metrics && <CostEstimateNote />}
        {metrics?.fusion && <FusionSection fusion={metrics.fusion} />}
      </div>
    </div>
  );
}
