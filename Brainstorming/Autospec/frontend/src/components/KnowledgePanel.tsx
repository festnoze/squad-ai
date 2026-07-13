import { useEffect, useState } from "react";
import {
  deleteKnowledgeEntry,
  errorMessage,
  getKnowledge,
  patchKnowledgeEntry,
} from "../api";
import {
  Adr,
  DebtEntry,
  EngineeringObservation,
  KnowledgeBase,
  KnowledgeEntryPatch,
  KnowledgeSection,
  MemoryEntry,
  PendingIdea,
  RiskEntry,
} from "../types";
import { CollapsibleSection } from "./CollapsibleSection";
import { useI18n } from "../i18n/i18n";
import { confirmAction } from "./ConfirmDialog";

/**
 * V3-F7 (US-F7.4) : mémoire logicielle du projet — onglets ADRs / Dette /
 * Risques / Idées en suspens / Notes & mémoire composant, avec édition et
 * suppression humaines (PATCH/DELETE US-F4.4) et lien vers l'observation
 * source. Rechargé quand `refreshKey` change (événements SSE de la boucle
 * d'observation). Panneau invisible tant que la base est vide (flag OFF).
 */

type Tab = "adrs" | "debt" | "risks" | "ideas" | "notes";

interface Props {
  projectId: string;
  /** Incrémenté par App à chaque événement observation/gouvernance → refetch. */
  refreshKey?: number;
  /** Observations du projet : affichage inline de l'observation source. */
  observations?: EngineeringObservation[];
}

function kbEmpty(kb: KnowledgeBase): boolean {
  return (
    kb.adrs.length === 0 &&
    kb.debt_register.length === 0 &&
    kb.risk_register.length === 0 &&
    kb.pending_ideas.length === 0 &&
    kb.architecture_notes.length === 0 &&
    Object.keys(kb.component_memory).length === 0
  );
}

/** Le champ « corps » éditable d'une entrée, selon sa section. */
function bodyField(section: KnowledgeSection): keyof KnowledgeEntryPatch {
  if (section === "adrs") return "decision";
  if (section === "architecture_notes" || section === "component_memory") return "text";
  return "detail";
}

export function KnowledgePanel({ projectId, refreshKey = 0, observations = [] }: Props) {
  const { t } = useI18n();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [tab, setTab] = useState<Tab>("adrs");
  const [error, setError] = useState("");
  // Édition en cours : section + id + brouillons (titre et corps).
  const [editing, setEditing] = useState<{ section: KnowledgeSection; id: string } | null>(
    null,
  );
  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getKnowledge(projectId)
      .then((data) => {
        if (!cancelled) {
          setKb(data);
          setError("");
        }
      })
      .catch(() => {
        // Base indisponible (backend ancien / projet inconnu) : panneau muet.
        if (!cancelled) setKb(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, refreshKey]);

  if (!kb || kbEmpty(kb)) return null;

  const reload = () =>
    getKnowledge(projectId)
      .then(setKb)
      .catch(() => undefined);

  const startEdit = (
    section: KnowledgeSection,
    id: string,
    title: string,
    body: string,
  ) => {
    setEditing({ section, id });
    setDraftTitle(title);
    setDraftBody(body);
  };

  const saveEdit = async (hasTitle: boolean) => {
    if (!editing) return;
    setBusy(true);
    try {
      const patch: KnowledgeEntryPatch = { [bodyField(editing.section)]: draftBody };
      if (hasTitle) patch.title = draftTitle;
      await patchKnowledgeEntry(projectId, editing.section, editing.id, patch);
      setEditing(null);
      await reload();
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (section: KnowledgeSection, id: string) => {
    const ok = await confirmAction({
      title: t("knowledgePanel.deleteEntry"),
      body: t("knowledgePanel.confirmDelete"),
      confirmLabel: t("common.delete"),
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      await deleteKnowledgeEntry(projectId, section, id);
      await reload();
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const sourceObs = (id: string): string => {
    if (!id) return "";
    const obs = observations.find((o) => o.id === id);
    return obs ? `${id} — ${obs.summary}` : id;
  };

  /** Pied commun d'une entrée : observation source + itération. */
  const EntryMeta = ({ src, iteration }: { src: string; iteration: number }) => (
    <div className="kn-meta">
      {src && (
        <span className="kn-source">
          {t("knowledgePanel.sourceObservation")} {sourceObs(src)}
        </span>
      )}
      <span className="kn-iter">{t("knowledgePanel.iterationShort", { n: iteration })}</span>
    </div>
  );

  /** Boutons ✎/🗑 ou le formulaire d'édition (titre + corps). */
  const EntryActions = ({
    section,
    id,
    title,
    body,
    hasTitle,
  }: {
    section: KnowledgeSection;
    id: string;
    title: string;
    body: string;
    hasTitle: boolean;
  }) => {
    const isEditing = editing?.section === section && editing.id === id;
    if (!isEditing) {
      return (
        <span className="kn-actions">
          <button
            type="button"
            className="ghost small-btn"
            title={t("knowledgePanel.editEntry")}
            aria-label={`${t("knowledgePanel.editEntry")} ${id}`}
            disabled={busy}
            onClick={() => startEdit(section, id, title, body)}
          >
            ✎
          </button>
          <button
            type="button"
            className="ghost small-btn"
            title={t("knowledgePanel.deleteEntry")}
            aria-label={`${t("knowledgePanel.deleteEntry")} ${id}`}
            disabled={busy}
            onClick={() => void remove(section, id)}
          >
            🗑
          </button>
        </span>
      );
    }
    return (
      <div className="kn-edit-form">
        {hasTitle && (
          <input
            type="text"
            aria-label={t("governancePanel.fieldTitle")}
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
          />
        )}
        <textarea
          aria-label={t("common.edit")}
          value={draftBody}
          onChange={(e) => setDraftBody(e.target.value)}
          rows={3}
        />
        <div className="kn-edit-actions">
          <button
            type="button"
            className="primary small-btn"
            disabled={busy}
            onClick={() => void saveEdit(hasTitle)}
          >
            {t("common.save")}
          </button>
          <button
            type="button"
            className="ghost small-btn"
            onClick={() => setEditing(null)}
          >
            {t("common.cancel")}
          </button>
        </div>
      </div>
    );
  };

  const TABS: { id: Tab; label: string; count: number }[] = [
    { id: "adrs", label: t("knowledgePanel.tabAdrs"), count: kb.adrs.length },
    { id: "debt", label: t("knowledgePanel.tabDebt"), count: kb.debt_register.length },
    { id: "risks", label: t("knowledgePanel.tabRisks"), count: kb.risk_register.length },
    { id: "ideas", label: t("knowledgePanel.tabIdeas"), count: kb.pending_ideas.length },
    {
      id: "notes",
      label: t("knowledgePanel.tabNotes"),
      count:
        kb.architecture_notes.length +
        Object.values(kb.component_memory).reduce((n, l) => n + l.length, 0),
    },
  ];

  const renderAdr = (e: Adr) => (
    <div key={e.id} className="kn-entry">
      <div className="kn-head">
        <strong className="kn-title">{e.title}</strong>
        <span className={`badge badge-adr-${e.status}`}>{e.status}</span>
        <EntryActions
          section="adrs"
          id={e.id}
          title={e.title}
          body={e.decision}
          hasTitle
        />
      </div>
      {e.decision && (
        <div className="kn-body">
          <strong>{t("knowledgePanel.decision")}</strong> {e.decision}
        </div>
      )}
      {e.context && (
        <div className="kn-body">
          <strong>{t("knowledgePanel.context")}</strong> {e.context}
        </div>
      )}
      <EntryMeta src={e.source_observation_id} iteration={e.iteration} />
    </div>
  );

  const renderDebt = (e: DebtEntry) => (
    <div key={e.id} className="kn-entry">
      <div className="kn-head">
        <strong className="kn-title">{e.title}</strong>
        <span className={`badge badge-urgency badge-urgency-${e.urgency || "normal"}`}>
          {e.urgency || "normal"}
        </span>
        <EntryActions
          section="debt_register"
          id={e.id}
          title={e.title}
          body={e.detail}
          hasTitle
        />
      </div>
      {e.detail && <div className="kn-body">{e.detail}</div>}
      {e.effort_estimate && (
        <div className="kn-body">
          <strong>{t("knowledgePanel.effort")}</strong> {e.effort_estimate}
        </div>
      )}
      {e.interest && (
        <div className="kn-body">
          <strong>{t("knowledgePanel.interest")}</strong> {e.interest}
        </div>
      )}
      <EntryMeta src={e.source_observation_id} iteration={e.iteration} />
    </div>
  );

  const renderRisk = (e: RiskEntry) => (
    <div key={e.id} className="kn-entry">
      <div className="kn-head">
        <strong className="kn-title">{e.title}</strong>
        <span className={`badge badge-urgency badge-urgency-${e.urgency || "normal"}`}>
          {e.urgency || "normal"}
        </span>
        <EntryActions
          section="risk_register"
          id={e.id}
          title={e.title}
          body={e.detail}
          hasTitle
        />
      </div>
      {e.detail && <div className="kn-body">{e.detail}</div>}
      {e.likelihood && (
        <div className="kn-body">
          <strong>{t("knowledgePanel.likelihood")}</strong> {e.likelihood}
        </div>
      )}
      {e.mitigation && (
        <div className="kn-body">
          <strong>{t("knowledgePanel.mitigation")}</strong> {e.mitigation}
        </div>
      )}
      <EntryMeta src={e.source_observation_id} iteration={e.iteration} />
    </div>
  );

  const renderIdea = (e: PendingIdea) => (
    <div key={e.id} className="kn-entry">
      <div className="kn-head">
        <strong className="kn-title">{e.title}</strong>
        <EntryActions
          section="pending_ideas"
          id={e.id}
          title={e.title}
          body={e.detail}
          hasTitle
        />
      </div>
      {e.detail && <div className="kn-body">{e.detail}</div>}
      {e.value_hint && (
        <div className="kn-body">
          <strong>{t("knowledgePanel.valueHint")}</strong> {e.value_hint}
        </div>
      )}
      {e.reevaluate_when && (
        <div className="kn-body">
          <strong>{t("knowledgePanel.reevaluateWhen")}</strong> {e.reevaluate_when}
        </div>
      )}
      <EntryMeta src={e.source_observation_id} iteration={e.iteration} />
    </div>
  );

  const renderNote = (e: MemoryEntry, section: KnowledgeSection) => (
    <div key={e.id} className="kn-entry">
      <div className="kn-head">
        <span className="kn-title">{e.text}</span>
        {e.kind && <span className="badge">{e.kind}</span>}
        <EntryActions section={section} id={e.id} title="" body={e.text} hasTitle={false} />
      </div>
      <EntryMeta src={e.source_observation_id} iteration={e.iteration} />
    </div>
  );

  return (
    <CollapsibleSection title={t("knowledgePanel.title")} className="knowledge">
      {error && <div className="edit-error">{error}</div>}
      <div className="kn-tabs" role="tablist">
        {TABS.map(({ id, label, count }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={`kn-tab ${tab === id ? "active" : ""}`}
            onClick={() => setTab(id)}
          >
            {label}
            {count > 0 && <span className="kn-count">{count}</span>}
          </button>
        ))}
      </div>
      <div className="kn-entries">
        {tab === "adrs" &&
          (kb.adrs.length === 0 ? (
            <p className="placeholder">{t("knowledgePanel.emptyTab")}</p>
          ) : (
            kb.adrs.map(renderAdr)
          ))}
        {tab === "debt" &&
          (kb.debt_register.length === 0 ? (
            <p className="placeholder">{t("knowledgePanel.emptyTab")}</p>
          ) : (
            kb.debt_register.map(renderDebt)
          ))}
        {tab === "risks" &&
          (kb.risk_register.length === 0 ? (
            <p className="placeholder">{t("knowledgePanel.emptyTab")}</p>
          ) : (
            kb.risk_register.map(renderRisk)
          ))}
        {tab === "ideas" &&
          (kb.pending_ideas.length === 0 ? (
            <p className="placeholder">{t("knowledgePanel.emptyTab")}</p>
          ) : (
            kb.pending_ideas.map(renderIdea)
          ))}
        {tab === "notes" && (
          <>
            {kb.architecture_notes.length === 0 &&
              Object.keys(kb.component_memory).length === 0 && (
                <p className="placeholder">{t("knowledgePanel.emptyTab")}</p>
              )}
            {kb.architecture_notes.length > 0 && (
              <div className="kn-group">
                <h4>{t("knowledgePanel.architectureNotes")}</h4>
                {kb.architecture_notes.map((e) => renderNote(e, "architecture_notes"))}
              </div>
            )}
            {Object.entries(kb.component_memory).map(([stream, entries]) => (
              <div key={stream} className="kn-group">
                <h4>{t("knowledgePanel.componentMemory", { stream })}</h4>
                {entries.map((e) => renderNote(e, "component_memory"))}
              </div>
            ))}
          </>
        )}
      </div>
    </CollapsibleSection>
  );
}
