import { useEffect, useState } from "react";
import {
  addStory,
  deleteStory,
  editStory,
  errorMessage,
  forceDoneStory,
  rebuildStory,
  reorderStories,
  storyDiff,
} from "../api";
import {
  AcceptanceCriterion,
  criterionState,
  Epic,
  TestState,
  UserStory,
} from "../types";

const STATUS_LABEL: Record<string, string> = {
  todo: "À faire",
  in_progress: "Dev en cours",
  red: "Tests rouges",
  green: "Tests verts",
  done: "Terminé",
  failed: "Échec",
};

const TEST_STATE_LABEL: Record<TestState, string> = {
  nonexistent: "inexistant",
  red: "rouge",
  green: "vert",
};

const TEST_STATE_ICON: Record<TestState, string> = {
  nonexistent: "○",
  red: "●",
  green: "●",
};

/** Stops a click from bubbling up to the card's expand/collapse handler. */
const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();

function CriterionRow({
  story,
  criterion,
}: {
  story: UserStory;
  criterion: AcceptanceCriterion;
}) {
  const [open, setOpen] = useState(false);
  const state = criterionState(story, criterion);
  // `?? []` : robustesse face aux anciens états persistés sans ces champs.
  const tests = (story.test_plan ?? []).filter((t) =>
    (t.criteria ?? []).includes(criterion.id),
  );

  return (
    <div className={`criterion state-${state}`} data-testid={`criterion-${criterion.id}`}>
      <div
        className="criterion-head"
        data-testid={`criterion-head-${criterion.id}`}
        onClick={() => setOpen(!open)}
      >
        <span className={`state-dot state-${state}`}>{TEST_STATE_ICON[state]}</span>
        <span className="criterion-text">{criterion.text}</span>
        <span className={`state-tag state-${state}`} data-testid="criterion-state">
          {TEST_STATE_LABEL[state]}
        </span>
        <span className="criterion-expander">{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <div className="criterion-body">
          <h5>Tests d'acceptance ({tests.length})</h5>
          {tests.length === 0 ? (
            <p className="placeholder small">
              Aucun test unitaire rattaché — couvert par le test fonctionnel Gherkin ci-dessous.
            </p>
          ) : (
            <ul className="criterion-tests">
              {tests.map((t) => (
                <li key={t.id}>
                  <span className={`state-dot state-${t.status}`}>
                    {TEST_STATE_ICON[t.status]}
                  </span>
                  <span className="test-layer">{t.layer || "?"}</span>
                  <span className="test-desc">{t.description}</span>
                  {(t.mocks ?? []).length > 0 && (
                    <span className="test-mocks"> · mocks : {t.mocks.join(", ")}</span>
                  )}
                  <span className={`state-tag state-${t.status}`}>
                    {TEST_STATE_LABEL[t.status]}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {story.gherkin && (
            <>
              <h5>Gherkin associé</h5>
              <pre className="gherkin">{story.gherkin}</pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface EditDraft {
  title: string;
  description: string;
  priority: number;
  gherkin: string;
  criteria: { id?: string; text: string }[];
}

function StoryEditor({
  projectId,
  story,
  onClose,
}: {
  projectId: string;
  story: UserStory;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<EditDraft>({
    title: story.title,
    description: story.description,
    priority: story.priority,
    gherkin: story.gherkin,
    criteria: (story.acceptance_criteria ?? []).map((c) => ({ id: c.id, text: c.text })),
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const setCriterion = (i: number, text: string) =>
    setDraft((d) => {
      const criteria = [...d.criteria];
      criteria[i] = { ...criteria[i], text };
      return { ...d, criteria };
    });

  const removeCriterion = (i: number) =>
    setDraft((d) => ({ ...d, criteria: d.criteria.filter((_, j) => j !== i) }));

  const addCriterion = () =>
    setDraft((d) => ({ ...d, criteria: [...d.criteria, { text: "" }] }));

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await editStory(projectId, story.id, {
        title: draft.title,
        description: draft.description,
        gherkin: draft.gherkin,
        priority: draft.priority,
        acceptance_criteria: draft.criteria
          .filter((c) => c.text.trim() !== "")
          .map((c) => ({ id: c.id, text: c.text })),
      });
      onClose();
    } catch (e) {
      setError(errorMessage(e));
      setSaving(false);
    }
  };

  return (
    <div className="story-editor" onClick={stop}>
      <label className="edit-field">
        <span>Titre</span>
        <input
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
      </label>
      <label className="edit-field">
        <span>Description</span>
        <textarea
          rows={2}
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        />
      </label>
      <label className="edit-field">
        <span>Priorité (1=haute)</span>
        <input
          type="number"
          min={1}
          max={5}
          value={draft.priority}
          onChange={(e) =>
            setDraft({ ...draft, priority: Number(e.target.value) })
          }
        />
      </label>
      <div className="edit-field">
        <span>Critères d'acceptance</span>
        <div className="edit-criteria">
          {draft.criteria.map((c, i) => (
            <div className="edit-criterion-row" key={c.id ?? `new-${i}`}>
              <input
                value={c.text}
                onChange={(e) => setCriterion(i, e.target.value)}
                placeholder="Critère…"
              />
              <button
                type="button"
                className="danger small-btn"
                onClick={() => removeCriterion(i)}
                title="Supprimer ce critère"
              >
                ✕
              </button>
            </div>
          ))}
          <button type="button" className="ghost small-btn" onClick={addCriterion}>
            + critère
          </button>
        </div>
      </div>
      <label className="edit-field">
        <span>Gherkin</span>
        <textarea
          rows={4}
          className="mono"
          value={draft.gherkin}
          onChange={(e) => setDraft({ ...draft, gherkin: e.target.value })}
        />
      </label>
      {error && <div className="edit-error">{error}</div>}
      <div className="edit-actions">
        <button className="primary" disabled={saving} onClick={save}>
          Enregistrer
        </button>
        <button className="ghost" disabled={saving} onClick={onClose}>
          Annuler
        </button>
      </div>
    </div>
  );
}

/** Rendu ligne-par-ligne du diff avec coloration +/- (hors entêtes +++/---). */
function DiffBody({ diff }: { diff: string }) {
  const lines = diff.split("\n");
  return (
    <pre className="diff-pre">
      {lines.map((line, i) => {
        let cls = "";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "diff-add";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "diff-del";
        return (
          <span key={i} className={cls}>
            {line + (i < lines.length - 1 ? "\n" : "")}
          </span>
        );
      })}
    </pre>
  );
}

function DiffViewer({
  projectId,
  story,
  onClose,
}: {
  projectId: string;
  story: UserStory;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [diff, setDiff] = useState("");
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    storyDiff(projectId, story.id)
      .then((res) => {
        if (cancelled) return;
        setAvailable(res.available);
        setDiff(res.diff);
      })
      .catch((e) => {
        if (!cancelled) setError(errorMessage(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, story.id]);

  return (
    <div className="diff-overlay" onClick={onClose}>
      <div className="diff-panel" onClick={(e) => e.stopPropagation()}>
        <div className="diff-header">
          <span className="diff-title">📊 Diff — {story.id}</span>
          <button
            type="button"
            className="ghost diff-close"
            onClick={onClose}
            aria-label="Fermer"
          >
            ✕
          </button>
        </div>
        <div className="diff-content">
          {loading && <div className="diff-muted">Chargement…</div>}
          {!loading && error && <div className="diff-error">{error}</div>}
          {!loading && !error && (!available || diff.trim() === "") && (
            <div className="diff-muted">Aucun diff disponible pour cette story.</div>
          )}
          {!loading && !error && available && diff.trim() !== "" && (
            <DiffBody diff={diff} />
          )}
        </div>
      </div>
    </div>
  );
}

function StoryCard({
  projectId,
  story,
  dragOver,
  onHandleDragStart,
  onCardDragOver,
  onCardDragLeave,
  onCardDrop,
}: {
  projectId: string;
  story: UserStory;
  dragOver: boolean;
  onHandleDragStart: (e: React.DragEvent) => void;
  onCardDragOver: (e: React.DragEvent) => void;
  onCardDragLeave: (e: React.DragEvent) => void;
  onCardDrop: (e: React.DragEvent) => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showDiff, setShowDiff] = useState(false);

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Supprimer la user story « ${story.title} » ?`)) return;
    setError("");
    try {
      await deleteStory(projectId, story.id);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  // Enveloppe une action API de la carte : erreur affichée + anti double-clic.
  const action = (fn: () => Promise<void>) => async (e: React.MouseEvent) => {
    e.stopPropagation();
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleRebuild = action(() => rebuildStory(projectId, story.id));
  const handleForceDone = action(() => forceDoneStory(projectId, story.id));

  return (
    <div
      className={`story status-${story.status}${dragOver ? " drag-over" : ""}`}
      data-testid={`story-${story.id}`}
      onDragOver={onCardDragOver}
      onDragLeave={onCardDragLeave}
      onDrop={onCardDrop}
    >
      <div className="story-head" onClick={() => setOpen(!open)}>
        <span
          className="drag-handle"
          draggable
          onDragStart={onHandleDragStart}
          onClick={stop}
          title="Glisser pour réordonner"
          aria-label="Poignée de déplacement"
        >
          ⠿
        </span>
        <span className="story-id">{story.id}</span>
        <span className="story-right">
          <span className={`prio prio-${story.priority}`} title="Priorité kanban (1=haute)">
            P{story.priority}
          </span>
          <span className={`badge badge-${story.status}`}>
            {STATUS_LABEL[story.status] ?? story.status}
          </span>
          {story.quality_score >= 0 && (
            <span className="quality-badge" title="Qualité du code (raffinement)">
              ⚙ {story.quality_score}/100
            </span>
          )}
        </span>
      </div>
      <div className="story-title" onClick={() => setOpen(!open)}>
        {story.title}
      </div>
      {(story.depends_on ?? []).length > 0 && (
        <div className="story-deps">⛓ dépend de {story.depends_on.join(", ")}</div>
      )}
      {open && (
        <div className="story-details">
          {editing ? (
            <StoryEditor
              projectId={projectId}
              story={story}
              onClose={() => setEditing(false)}
            />
          ) : (
            <>
              <div className="story-toolbar" onClick={stop}>
                <button
                  className="ghost small-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditing(true);
                  }}
                >
                  ✏️ Éditer
                </button>
                <button className="danger small-btn" onClick={handleDelete}>
                  🗑 Supprimer
                </button>
                {story.status === "failed" && (
                  <>
                    <button
                      className="action-btn small-btn"
                      disabled={busy}
                      onClick={handleRebuild}
                    >
                      🔄 Relancer
                    </button>
                    <button
                      className="action-btn action-done small-btn"
                      disabled={busy}
                      onClick={handleForceDone}
                    >
                      ✓ Forcer terminé
                    </button>
                  </>
                )}
                {story.status === "done" && (
                  <button
                    className="action-btn small-btn"
                    disabled={busy}
                    onClick={handleRebuild}
                  >
                    🔁 Rejouer
                  </button>
                )}
                {story.status === "done" && (
                  <button
                    className="ghost small-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowDiff(true);
                    }}
                  >
                    📊 Diff
                  </button>
                )}
              </div>
              {error && <div className="edit-error">{error}</div>}
              <p>{story.description}</p>
              {(story.acceptance_criteria ?? []).length > 0 && (
                <>
                  <h4>Critères d'acceptance</h4>
                  <div className="criteria">
                    {story.acceptance_criteria.map((c) => (
                      <CriterionRow key={c.id} story={story} criterion={c} />
                    ))}
                  </div>
                </>
              )}
              {story.last_error && (
                <>
                  <h4>Dernière erreur</h4>
                  <pre className="error-output">{story.last_error}</pre>
                </>
              )}
            </>
          )}
        </div>
      )}
      {showDiff && (
        <DiffViewer
          projectId={projectId}
          story={story}
          onClose={() => setShowDiff(false)}
        />
      )}
    </div>
  );
}

function AddStoryForm({ projectId, epicId }: { projectId: string; epicId: string }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState(3);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setTitle("");
    setDescription("");
    setPriority(3);
    setError("");
    setOpen(false);
  };

  const submit = async () => {
    if (title.trim() === "") {
      setError("Le titre est requis.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await addStory(projectId, {
        epic_id: epicId,
        title: title.trim(),
        description: description.trim() || undefined,
        priority,
      });
      reset();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button className="ghost add-story-btn" onClick={() => setOpen(true)}>
        + Ajouter une US
      </button>
    );
  }

  return (
    <div className="add-story-form">
      <label className="edit-field">
        <span>Titre *</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="edit-field">
        <span>Description</span>
        <textarea
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <label className="edit-field">
        <span>Priorité (1=haute)</span>
        <input
          type="number"
          min={1}
          max={5}
          value={priority}
          onChange={(e) => setPriority(Number(e.target.value))}
        />
      </label>
      {error && <div className="edit-error">{error}</div>}
      <div className="edit-actions">
        <button className="primary" disabled={saving} onClick={submit}>
          Créer
        </button>
        <button className="ghost" disabled={saving} onClick={reset}>
          Annuler
        </button>
      </div>
    </div>
  );
}

/**
 * Liste des user stories d'un même epic, triée par priorité (croissante, tri
 * stable) et réordonnançable par glisser-déposer via la poignée des cartes.
 */
function EpicStories({
  projectId,
  stories,
}: {
  projectId: string;
  stories: UserStory[];
}) {
  // id de la story en cours de drag, et id de la story survolée (cible de drop).
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [error, setError] = useState("");

  // Tri stable par priorité croissante (1=haute). Array.sort est stable en JS,
  // donc à priorité égale l'ordre de déclaration est conservé.
  const ordered = [...stories].sort((a, b) => a.priority - b.priority);

  const handleDrop = async (targetId: string) => {
    const sourceId = draggingId;
    setDraggingId(null);
    setOverId(null);
    if (!sourceId || sourceId === targetId) return;
    // source et cible sont forcément dans le même epic (ce composant ne rend
    // que les stories d'un epic), mais on vérifie la présence par sécurité.
    const ids = ordered.map((s) => s.id);
    if (!ids.includes(sourceId) || !ids.includes(targetId)) return;

    const without = ids.filter((id) => id !== sourceId);
    const targetIdx = without.indexOf(targetId);
    without.splice(targetIdx, 0, sourceId);

    const priorities = without.map((id, i) => ({
      id,
      priority: Math.min(i + 1, 5),
    }));
    setError("");
    try {
      await reorderStories(projectId, priorities);
      // Pas de re-fetch : le backend diffuse le nouvel état par WebSocket.
    } catch (err) {
      // Erreur affichée à l'utilisateur plutôt que perdue en console.
      setError(`Échec du réordonnancement : ${errorMessage(err)}`);
    }
  };

  return (
    <div className="stories">
      {error && <div className="edit-error">{error}</div>}
      {ordered.map((s) => (
        <StoryCard
          key={s.id}
          projectId={projectId}
          story={s}
          dragOver={overId === s.id && draggingId !== null && draggingId !== s.id}
          onHandleDragStart={(e) => {
            e.stopPropagation();
            setDraggingId(s.id);
            e.dataTransfer.effectAllowed = "move";
          }}
          onCardDragOver={(e) => {
            e.preventDefault();
            if (draggingId !== null && draggingId !== s.id) setOverId(s.id);
          }}
          onCardDragLeave={() => {
            setOverId((cur) => (cur === s.id ? null : cur));
          }}
          onCardDrop={(e) => {
            e.preventDefault();
            void handleDrop(s.id);
          }}
        />
      ))}
    </div>
  );
}

interface Props {
  epics: Epic[];
  stories: UserStory[];
  projectId: string;
}

export function Board({ epics, stories, projectId }: Props) {
  if (epics.length === 0) {
    return (
      <div className="panel board empty">
        <h2>Board Epics / User stories</h2>
        <p className="placeholder">Le PO n'a pas encore produit de plan.</p>
      </div>
    );
  }
  return (
    <div className="panel board">
      <h2>Board Epics / User stories</h2>
      <div className="epics">
        {epics.map((epic) => (
          <div key={epic.id} className="epic">
            <div className="epic-head">
              <span className="epic-id">{epic.id}</span>
              <span className="epic-iter">itération {epic.iteration}</span>
            </div>
            <div className="epic-title">{epic.title}</div>
            <EpicStories
              projectId={projectId}
              stories={stories.filter((s) => s.epic_id === epic.id)}
            />
            <AddStoryForm projectId={projectId} epicId={epic.id} />
          </div>
        ))}
      </div>
    </div>
  );
}
