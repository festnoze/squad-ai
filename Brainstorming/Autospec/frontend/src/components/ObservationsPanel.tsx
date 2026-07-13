import { useMemo, useState } from "react";
import {
  EngineeringObservation,
  GovernanceDecision,
  ObservationStatus,
  ObservationType,
} from "../types";
import { CollapsibleSection } from "./CollapsibleSection";
import { useI18n } from "../i18n/i18n";

/**
 * V3-F7 (US-F7.2) : liste filtrable des observations d'ingénierie (type,
 * statut, stream, itération) avec badge d'urgence et détail extensible
 * (preuves, impact, recommandations, décision PO liée). Suit le pattern de
 * `BacklogPanel` : rien n'est rendu tant qu'aucune observation n'existe
 * (feature flag OFF → panneau invisible, pas de crash).
 */

interface Props {
  observations: EngineeringObservation[];
  /** Journal de gouvernance : permet d'afficher la décision PO liée. */
  decisions?: GovernanceDecision[];
}

export function ObservationsPanel({ observations, decisions = [] }: Props) {
  const { t } = useI18n();
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [streamFilter, setStreamFilter] = useState("");
  const [iterationFilter, setIterationFilter] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const TYPE_LABEL: Record<ObservationType, string> = {
    workaround: t("observationsPanel.typeWorkaround"),
    tech_debt: t("observationsPanel.typeTechDebt"),
    risk: t("observationsPanel.typeRisk"),
    limitation: t("observationsPanel.typeLimitation"),
    refactoring: t("observationsPanel.typeRefactoring"),
    improvement: t("observationsPanel.typeImprovement"),
    ambiguity: t("observationsPanel.typeAmbiguity"),
    constraint: t("observationsPanel.typeConstraint"),
    pattern: t("observationsPanel.typePattern"),
  };
  const STATUS_LABEL: Record<ObservationStatus, string> = {
    new: t("observationsPanel.statusNew"),
    validated: t("observationsPanel.statusValidated"),
    rejected: t("observationsPanel.statusRejected"),
    routed: t("observationsPanel.statusRouted"),
    actioned: t("observationsPanel.statusActioned"),
    persisted: t("observationsPanel.statusPersisted"),
    deferred: t("observationsPanel.statusDeferred"),
    dismissed: t("observationsPanel.statusDismissed"),
  };
  const URGENCY_LABEL: Record<string, string> = {
    low: t("observationsPanel.urgencyLow"),
    normal: t("observationsPanel.urgencyNormal"),
    high: t("observationsPanel.urgencyHigh"),
    critical: t("observationsPanel.urgencyCritical"),
  };

  // Options de filtres dérivées des données réellement présentes.
  const options = useMemo(() => {
    const types = new Set<string>();
    const statuses = new Set<string>();
    const streams = new Set<string>();
    const iterations = new Set<number>();
    for (const o of observations) {
      types.add(o.type);
      statuses.add(o.status);
      if (o.stream) streams.add(o.stream);
      iterations.add(o.iteration ?? 0);
    }
    return {
      types: [...types].sort(),
      statuses: [...statuses].sort(),
      streams: [...streams].sort(),
      iterations: [...iterations].sort((a, b) => a - b),
    };
  }, [observations]);

  const filtered = useMemo(
    () =>
      observations.filter(
        (o) =>
          (!typeFilter || o.type === typeFilter) &&
          (!statusFilter || o.status === statusFilter) &&
          (!streamFilter || o.stream === streamFilter) &&
          (!iterationFilter || String(o.iteration ?? 0) === iterationFilter),
      ),
    [observations, typeFilter, statusFilter, streamFilter, iterationFilter],
  );

  if (observations.length === 0) return null;

  const decisionFor = (obs: EngineeringObservation): GovernanceDecision | undefined =>
    decisions.find((d) => d.observation_id === obs.id);

  return (
    <CollapsibleSection
      title={t("observationsPanel.title")}
      className="observations"
      headerExtra={<span className="panel-count">{observations.length}</span>}
    >
      <div className="obs-filters">
        <select
          aria-label={t("observationsPanel.filterType")}
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">
            {t("observationsPanel.filterType")} · {t("observationsPanel.filterAll")}
          </option>
          {options.types.map((v) => (
            <option key={v} value={v}>
              {TYPE_LABEL[v as ObservationType] ?? v}
            </option>
          ))}
        </select>
        <select
          aria-label={t("observationsPanel.filterStatus")}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">
            {t("observationsPanel.filterStatus")} · {t("observationsPanel.filterAll")}
          </option>
          {options.statuses.map((v) => (
            <option key={v} value={v}>
              {STATUS_LABEL[v as ObservationStatus] ?? v}
            </option>
          ))}
        </select>
        {options.streams.length > 0 && (
          <select
            aria-label={t("observationsPanel.filterStream")}
            value={streamFilter}
            onChange={(e) => setStreamFilter(e.target.value)}
          >
            <option value="">
              {t("observationsPanel.filterStream")} · {t("observationsPanel.filterAll")}
            </option>
            {options.streams.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        )}
        {options.iterations.length > 1 && (
          <select
            aria-label={t("observationsPanel.filterIteration")}
            value={iterationFilter}
            onChange={(e) => setIterationFilter(e.target.value)}
          >
            <option value="">
              {t("observationsPanel.filterIteration")} · {t("observationsPanel.filterAll")}
            </option>
            {options.iterations.map((n) => (
              <option key={n} value={String(n)}>
                {t("observationsPanel.iterationShort", { n })}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="obs-list">
        {filtered.length === 0 && (
          <p className="placeholder">{t("observationsPanel.empty")}</p>
        )}
        {filtered.map((o) => {
          const expanded = expandedId === o.id;
          const linked = decisionFor(o);
          const urgency = o.urgency || "normal";
          return (
            <div key={o.id} className={`obs-item obs-${o.status}`}>
              <button
                type="button"
                className="obs-row"
                aria-expanded={expanded}
                title={expanded ? t("observationsPanel.collapse") : t("observationsPanel.expand")}
                onClick={() => setExpandedId(expanded ? null : o.id)}
              >
                <span className="obs-id">{o.id}</span>
                <span className={`badge badge-obs-type`}>
                  {TYPE_LABEL[o.type] ?? o.type}
                </span>
                <span className={`badge badge-urgency badge-urgency-${urgency}`}>
                  {URGENCY_LABEL[urgency] ?? urgency}
                </span>
                <span className="obs-summary">{o.summary}</span>
                <span className="obs-meta">
                  {o.stream && <span className="obs-stream">{o.stream}</span>}
                  <span className="obs-iter">
                    {t("observationsPanel.iterationShort", { n: o.iteration ?? 0 })}
                  </span>
                  <span className={`badge badge-obs-status badge-obs-${o.status}`}>
                    {STATUS_LABEL[o.status] ?? o.status}
                  </span>
                </span>
              </button>
              {expanded && (
                <div className="obs-detail">
                  {o.description && (
                    <p className="obs-description">{o.description}</p>
                  )}
                  {(o.evidence ?? []).length > 0 && (
                    <div className="obs-block">
                      <strong>{t("observationsPanel.evidence")}</strong>
                      <ul>
                        {o.evidence.map((ev, i) => (
                          <li key={i}>{ev}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {o.impact && (
                    <div className="obs-block">
                      <strong>{t("observationsPanel.impact")}</strong> {o.impact}
                    </div>
                  )}
                  {o.workaround && (
                    <div className="obs-block">
                      <strong>{t("observationsPanel.workaround")}</strong> {o.workaround}
                    </div>
                  )}
                  {(o.recommendations ?? []).length > 0 && (
                    <div className="obs-block">
                      <strong>{t("observationsPanel.recommendations")}</strong>
                      <ul>
                        {o.recommendations.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div className="obs-block obs-facts">
                    <span>
                      {t("observationsPanel.confidence")} :{" "}
                      {Math.round((o.confidence ?? 0) * 100)}%
                    </span>
                    {o.source_role && (
                      <span>
                        {t("observationsPanel.source")} : {o.source_role}
                        {o.work_item_id ? ` · ${o.work_item_id}` : ""}
                      </span>
                    )}
                    {o.routed_to && (
                      <span>
                        {t("observationsPanel.routedTo")} : {o.routed_to}
                      </span>
                    )}
                    {(o.merged_count ?? 0) > 0 && (
                      <span>
                        {t("observationsPanel.mergedCount", { count: o.merged_count })}
                      </span>
                    )}
                  </div>
                  {o.reevaluate_when && (
                    <div className="obs-block">
                      <strong>{t("observationsPanel.reevaluateWhen")}</strong>{" "}
                      {o.reevaluate_when}
                    </div>
                  )}
                  {o.resolution && (
                    <div className="obs-block">
                      <strong>{t("observationsPanel.resolution")}</strong> {o.resolution}
                    </div>
                  )}
                  {linked && (
                    <div className="obs-block obs-linked-decision">
                      <strong>{t("observationsPanel.linkedDecision")}</strong>{" "}
                      {linked.id} · {linked.action} · {linked.status}
                      {linked.rationale ? ` — ${linked.rationale}` : ""}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </CollapsibleSection>
  );
}
