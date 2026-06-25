import { FeatureHypothesis } from "../types";
import { CollapsibleSection } from "./CollapsibleSection";
import { useI18n } from "../i18n/i18n";

interface Props {
  backlog: FeatureHypothesis[];
}

export function BacklogPanel({ backlog }: Props) {
  const { t } = useI18n();
  const STATUS_LABEL: Record<string, string> = {
    proposed: t("backlogPanel.statusProposed"),
    selected: t("backlogPanel.statusSelected"),
    done: t("backlogPanel.statusDone"),
    rejected: t("backlogPanel.statusRejected"),
  };

  if (backlog.length === 0) return null;
  const active = backlog
    .filter((h) => h.status !== "done")
    .sort((a, b) => a.rank - b.rank);
  const shipped = backlog.filter((h) => h.status === "done");

  return (
    <CollapsibleSection title={t("backlogPanel.title")} className="backlog">
      <div className="hypotheses">
        {active.map((h) => (
          <div key={h.id} className={`hypothesis hyp-${h.status}`} title={h.rationale}>
            <span className="hyp-rank">#{h.rank}</span>
            <span className="hyp-title">{h.title}</span>
            <span className="hyp-scores">
              V{h.value} / C{h.complexity}
            </span>
            <span className={`badge badge-hyp-${h.status}`}>
              {STATUS_LABEL[h.status] ?? h.status}
            </span>
          </div>
        ))}
        {shipped.length > 0 && (
          <div className="hyp-shipped">
            ✅ {t("backlogPanel.shipped")} {shipped.map((h) => h.title).join(", ")}
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
