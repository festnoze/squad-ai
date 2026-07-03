import { CollapsibleSection } from "./CollapsibleSection";
import { useI18n } from "../i18n/i18n";
import type { PlanCalibration } from "../types";

interface Props {
  planQuality: number;
  issues: string[];
  suggestions: string[];
  /** §8 : compteurs de calibration aval de l'itération courante. */
  calibration?: PlanCalibration;
}

const CALIB_KEYS = [
  "reactive_splits",
  "over_budget_tasks",
  "degradations",
  "merge_requeues",
  "p2b_resumes",
  "orphan_resets",
  "infra_retries",
] as const;

/** « Revue du plan » (REVIEW_PLAN) : le score qualité du plan PO + les
 *  problèmes signalés et améliorations proposées par l'agent critic, plus la
 *  calibration aval (§8) — les signaux du build qui jugent le dimensionnement.
 *  Masqué tant que rien n'a tourné (score < 0, aucune issue, aucun signal). */
export function PlanReviewPanel({ planQuality, issues, suggestions, calibration }: Props) {
  const { t } = useI18n();
  const ran = planQuality >= 0;
  const calibEntries = CALIB_KEYS.map(
    (k) => [k, calibration?.[k] ?? 0] as const,
  ).filter(([, v]) => v > 0);
  if (!ran && issues.length === 0 && suggestions.length === 0 && calibEntries.length === 0)
    return null;
  const calibLabels: Record<(typeof CALIB_KEYS)[number], string> = {
    reactive_splits: t("planReviewPanel.calib_reactive_splits"),
    over_budget_tasks: t("planReviewPanel.calib_over_budget_tasks"),
    degradations: t("planReviewPanel.calib_degradations"),
    merge_requeues: t("planReviewPanel.calib_merge_requeues"),
    p2b_resumes: t("planReviewPanel.calib_p2b_resumes"),
    orphan_resets: t("planReviewPanel.calib_orphan_resets"),
    infra_retries: t("planReviewPanel.calib_infra_retries"),
  };
  const scoreClass = planQuality >= 80 ? "good" : planQuality >= 50 ? "mid" : "low";

  return (
    <CollapsibleSection title={t("planReviewPanel.title")} className="plan-review">
      {ran && (
        <div
          className={`plan-review-score plan-review-score-${scoreClass}`}
          data-testid="plan-review-score"
        >
          {t("planReviewPanel.score")} <strong>{planQuality}/100</strong>
        </div>
      )}
      {issues.length > 0 && (
        <div className="plan-review-block">
          <div className="plan-review-heading">{t("planReviewPanel.issues")}</div>
          <ul className="plan-review-list plan-review-issues">
            {issues.map((it, i) => (
              <li key={`i-${i}`}>⚠ {it}</li>
            ))}
          </ul>
        </div>
      )}
      {suggestions.length > 0 && (
        <div className="plan-review-block">
          <div className="plan-review-heading">{t("planReviewPanel.suggestions")}</div>
          <ul className="plan-review-list plan-review-suggestions">
            {suggestions.map((s, i) => (
              <li key={`s-${i}`}>→ {s}</li>
            ))}
          </ul>
        </div>
      )}
      {calibEntries.length > 0 && (
        <div className="plan-review-block" data-testid="plan-calibration">
          <div className="plan-review-heading">{t("planReviewPanel.calibration")}</div>
          <ul className="plan-review-list plan-calibration-list">
            {calibEntries.map(([k, v]) => (
              <li key={k}>
                <strong>{v}</strong> × {calibLabels[k]}
              </li>
            ))}
          </ul>
        </div>
      )}
      {ran && issues.length === 0 && suggestions.length === 0 && calibEntries.length === 0 && (
        <div className="plan-review-clean">{t("planReviewPanel.clean")}</div>
      )}
    </CollapsibleSection>
  );
}
