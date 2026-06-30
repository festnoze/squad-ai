import { CollapsibleSection } from "./CollapsibleSection";
import { useI18n } from "../i18n/i18n";

interface Props {
  planQuality: number;
  issues: string[];
  suggestions: string[];
}

/** « Revue du plan » (AUTOSPEC_REVIEW_PLAN) : le score qualité du plan PO + les
 *  problèmes signalés et améliorations proposées par l'agent critic. Masqué tant
 *  que la revue n'a pas tourné (score < 0 et aucune issue). */
export function PlanReviewPanel({ planQuality, issues, suggestions }: Props) {
  const { t } = useI18n();
  const ran = planQuality >= 0;
  if (!ran && issues.length === 0 && suggestions.length === 0) return null;
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
      {ran && issues.length === 0 && suggestions.length === 0 && (
        <div className="plan-review-clean">{t("planReviewPanel.clean")}</div>
      )}
    </CollapsibleSection>
  );
}
