import { useState } from "react";
import { EngineeringObservation, GovernanceDecision } from "../types";
import { CollapsibleSection } from "./CollapsibleSection";
import { t as translate, useI18n } from "../i18n/i18n";

/**
 * V3-F7 (US-F7.3) : gouvernance du backlog — décisions PO en attente
 * (« proposed ») avec Approuver/Rejeter, diff lisible du backlog dérivé de
 * action+payload+target_id, et journal des décisions passées (rationale +
 * statut final). Panneau invisible tant qu'aucune décision n'existe.
 */

interface Props {
  decisions: GovernanceDecision[];
  /** Observations : résumé de l'observation source de chaque décision. */
  observations?: EngineeringObservation[];
  onApprove: (decisionId: string) => void;
  onReject: (decisionId: string, reason: string) => void;
  /** Approve/reject en cours : désactive les boutons (anti double-clic). */
  busyId?: string | null;
}

/**
 * Diff lisible du backlog pour UNE décision (ex. « + US “titre” dans EPIC-3 »,
 * « 2 AC ajouté(s) à US-7 », « différé en idée en suspens »). Dérivé de
 * action + payload + target_id, sans appel réseau. Exporté pour les tests.
 */
export function decisionDiffLine(
  d: GovernanceDecision,
  t: typeof translate = translate,
): string {
  const p = d.payload ?? {};
  const title = String(p.title ?? "").trim();
  switch (d.action) {
    case "create_task":
      return t("governancePanel.diffCreateTask", {
        title: title || d.id,
        target: d.target_id || "?",
      });
    case "create_story": {
      const epic = String(p.epic_id ?? "").trim() || d.target_id || "?";
      const key = p.technical
        ? "governancePanel.diffCreateTechStory"
        : "governancePanel.diffCreateStory";
      return t(key, { title: title || d.id, epic });
    }
    case "create_epic":
      return t("governancePanel.diffCreateEpic", { title: title || d.id });
    case "update_story": {
      const fields = [
        title ? t("governancePanel.fieldTitle") : "",
        p.description !== undefined ? t("governancePanel.fieldDescription") : "",
        p.priority !== undefined ? t("governancePanel.fieldPriority") : "",
      ]
        .filter(Boolean)
        .join(", ");
      return t("governancePanel.diffUpdateStory", {
        target: d.target_id || "?",
        fields: fields || "…",
      });
    }
    case "enrich_criteria": {
      const criteria = Array.isArray(p.acceptance_criteria)
        ? (p.acceptance_criteria as unknown[]).length
        : 1;
      return t("governancePanel.diffEnrichCriteria", {
        count: criteria,
        target: d.target_id || "?",
      });
    }
    case "defer":
      return t("governancePanel.diffDefer", { title: title || d.observation_id });
    case "persist":
      return t("governancePanel.diffPersist");
    case "dismiss":
      return t("governancePanel.diffDismiss");
    default:
      return `${d.action} ${d.target_id}`.trim();
  }
}

export function GovernancePanel({
  decisions,
  observations = [],
  onApprove,
  onReject,
  busyId = null,
}: Props) {
  const { t } = useI18n();
  // Décision dont le rejet est en cours de confirmation (saisie du motif).
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const STATUS_LABEL: Record<string, string> = {
    proposed: t("governancePanel.statusProposed"),
    approved: t("governancePanel.statusApproved"),
    applied: t("governancePanel.statusApplied"),
    rejected_by_policy: t("governancePanel.statusRejectedByPolicy"),
    rejected_by_human: t("governancePanel.statusRejectedByHuman"),
    invalid: t("governancePanel.statusInvalid"),
  };

  if (decisions.length === 0) return null;

  const pending = decisions.filter((d) => d.status === "proposed");
  const history = decisions.filter((d) => d.status !== "proposed");
  const obsSummary = (id: string): string =>
    observations.find((o) => o.id === id)?.summary ?? "";

  return (
    <CollapsibleSection
      title={t("governancePanel.title")}
      className="governance"
      headerExtra={
        pending.length > 0 ? (
          <span className="gov-pending-count">{pending.length}</span>
        ) : undefined
      }
    >
      {pending.length > 0 && (
        <div className="gov-pending">
          <h3>{t("governancePanel.pending")}</h3>
          {pending.map((d) => (
            <div key={d.id} className="gov-decision gov-proposed">
              <div className="gov-diff-line">{decisionDiffLine(d, t)}</div>
              {d.rationale && (
                <div className="gov-rationale">
                  <strong>{t("governancePanel.rationale")}</strong> {d.rationale}
                </div>
              )}
              {obsSummary(d.observation_id) && (
                <div className="gov-source" title={d.observation_id}>
                  <strong>{t("governancePanel.sourceObservation")}</strong>{" "}
                  {d.observation_id} — {obsSummary(d.observation_id)}
                </div>
              )}
              <div className="gov-actions">
                <button
                  type="button"
                  className="primary small-btn"
                  disabled={busyId === d.id}
                  onClick={() => onApprove(d.id)}
                >
                  ✓ {t("governancePanel.approve")}
                </button>
                {rejectingId === d.id ? (
                  <>
                    <input
                      type="text"
                      className="gov-reject-reason"
                      placeholder={t("governancePanel.rejectReason")}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                    <button
                      type="button"
                      className="ghost small-btn"
                      disabled={busyId === d.id}
                      onClick={() => {
                        onReject(d.id, reason.trim());
                        setRejectingId(null);
                        setReason("");
                      }}
                    >
                      {t("governancePanel.confirmReject")}
                    </button>
                    <button
                      type="button"
                      className="ghost small-btn"
                      onClick={() => {
                        setRejectingId(null);
                        setReason("");
                      }}
                    >
                      {t("common.cancel")}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="ghost small-btn"
                    disabled={busyId === d.id}
                    onClick={() => setRejectingId(d.id)}
                  >
                    ✕ {t("governancePanel.reject")}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {history.length > 0 && (
        <div className="gov-history">
          <h3>{t("governancePanel.history")}</h3>
          {history.map((d) => (
            <div key={d.id} className={`gov-decision gov-${d.status}`}>
              <div className="gov-history-row">
                <span className="gov-id">{d.id}</span>
                <span className="gov-diff-line">{decisionDiffLine(d, t)}</span>
                <span className={`badge badge-gov-${d.status}`}>
                  {STATUS_LABEL[d.status] ?? d.status}
                </span>
              </div>
              {d.rationale && (
                <div className="gov-rationale">
                  <strong>{t("governancePanel.rationale")}</strong> {d.rationale}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </CollapsibleSection>
  );
}
