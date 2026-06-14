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

/** Stops a click from bubbling up to a parent click handler. */
const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();

/**
 * Dérive les dépendances entre epics depuis les `depends_on` des US : l'epic A
 * « dépend de » l'epic B si une US de A dépend d'une US de B (B ≠ A). Renvoie
 * une Map epicId -> liste d'epicIds dont il dépend (triée, dédupliquée).
 */
function deriveEpicDeps(stories: UserStory[]): Map<string, string[]> {
  const epicOf = new Map(stories.map((s) => [s.id, s.epic_id]));
  const acc = new Map<string, Set<string>>();
  for (const s of stories) {
    for (const dep of s.depends_on ?? []) {
      const depEpic = epicOf.get(dep);
      if (depEpic && depEpic !== s.epic_id) {
        if (!acc.has(s.epic_id)) acc.set(s.epic_id, new Set());
        acc.get(s.epic_id)!.add(depEpic);
      }
    }
  }
  const out = new Map<string, string[]>();
  for (const [k, v] of acc) out.set(k, [...v].sort());
  return out;
}

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

/** Badges communs (priorité, statut, score qualité) d'une user story. */
function StoryBadges({ story }: { story: UserStory }) {
  return (
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
      {(story.mutation_score ?? -1) >= 0 && (
        <span className="mutation-badge" title="Robustesse des tests (mutation testing)">
          🧬 {story.mutation_score}/100
        </span>
      )}
      {(story.coverage_score ?? -1) >= 0 && (
        <span className="coverage-badge" title="Couverture de tests">
          📊 {story.coverage_score}%
        </span>
      )}
    </span>
  );
}

/**
 * Carte compacte cliquable d'une user story (niveau « epic »). Le clic ouvre le
 * détail (niveau « us ») ; la poignée ⠿ reste dédiée au drag-&-drop de tri.
 */
function StoryRow({
  story,
  onOpen,
  dragOver,
  onHandleDragStart,
  onCardDragOver,
  onCardDragLeave,
  onCardDrop,
}: {
  story: UserStory;
  onOpen: () => void;
  dragOver: boolean;
  onHandleDragStart: (e: React.DragEvent) => void;
  onCardDragOver: (e: React.DragEvent) => void;
  onCardDragLeave: (e: React.DragEvent) => void;
  onCardDrop: (e: React.DragEvent) => void;
}) {
  return (
    <div
      className={`story status-${story.status}${dragOver ? " drag-over" : ""}`}
      data-testid={`story-${story.id}`}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      onDragOver={onCardDragOver}
      onDragLeave={onCardDragLeave}
      onDrop={onCardDrop}
    >
      <div className="story-head">
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
        <StoryBadges story={story} />
      </div>
      <div className="story-title">{story.title}</div>
      {(story.depends_on ?? []).length > 0 && (
        <div className="story-deps">⛓ dépend de {story.depends_on.join(", ")}</div>
      )}
      <div className="story-open-hint">▸ détails</div>
    </div>
  );
}

/**
 * Vue détaillée d'une user story (niveau « us ») : description, toolbar
 * d'actions, critères d'acceptance (tests + Gherkin) et dernière erreur.
 */
function StoryDetail({
  projectId,
  story,
  onDeleted,
}: {
  projectId: string;
  story: UserStory;
  onDeleted: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showDiff, setShowDiff] = useState(false);

  const handleDelete = async () => {
    if (!window.confirm(`Supprimer la user story « ${story.title} » ?`)) return;
    setError("");
    try {
      await deleteStory(projectId, story.id);
      onDeleted();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  // Enveloppe une action API : erreur affichée + anti double-clic.
  const run = (fn: () => Promise<void>) => async () => {
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

  const handleRebuild = run(() => rebuildStory(projectId, story.id));
  const handleForceDone = run(() => forceDoneStory(projectId, story.id));

  return (
    <div className="story-detail">
      <div className="story-detail-head">
        <span className="story-id">{story.id}</span>
        <StoryBadges story={story} />
      </div>
      <h3 className="story-detail-title">{story.title}</h3>
      {(story.depends_on ?? []).length > 0 && (
        <div className="story-deps">⛓ dépend de {story.depends_on.join(", ")}</div>
      )}
      {editing ? (
        <StoryEditor
          projectId={projectId}
          story={story}
          onClose={() => setEditing(false)}
        />
      ) : (
        <>
          <div className="story-toolbar">
            <button className="ghost small-btn" onClick={() => setEditing(true)}>
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
              <button className="ghost small-btn" onClick={() => setShowDiff(true)}>
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
 * Liste des user stories d'un epic, triée par priorité (croissante, stable) et
 * réordonnançable par glisser-déposer via la poignée. Un clic ouvre le détail.
 */
function EpicStories({
  projectId,
  stories,
  onOpen,
}: {
  projectId: string;
  stories: UserStory[];
  onOpen: (storyId: string) => void;
}) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [error, setError] = useState("");

  // Tri stable par priorité croissante (1=haute) : Array.sort est stable en JS.
  const ordered = [...stories].sort((a, b) => a.priority - b.priority);

  const handleDrop = async (targetId: string) => {
    const sourceId = draggingId;
    setDraggingId(null);
    setOverId(null);
    if (!sourceId || sourceId === targetId) return;
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
      setError(`Échec du réordonnancement : ${errorMessage(err)}`);
    }
  };

  return (
    <div className="stories">
      {error && <div className="edit-error">{error}</div>}
      {ordered.map((s) => (
        <StoryRow
          key={s.id}
          story={s}
          onOpen={() => onOpen(s.id)}
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

/** Fil d'Ariane : Épics / EPIC-x / US-y, chaque ancêtre cliquable. */
function Breadcrumb({
  epic,
  story,
  onNavEpics,
  onNavEpic,
}: {
  epic: Epic | null;
  story: UserStory | null;
  onNavEpics: () => void;
  onNavEpic: () => void;
}) {
  return (
    <nav className="breadcrumb" aria-label="Fil d'Ariane">
      <button className="crumb" onClick={onNavEpics} disabled={!epic && !story}>
        Épics
      </button>
      {epic && (
        <>
          <span className="crumb-sep">/</span>
          {story ? (
            <button className="crumb" onClick={onNavEpic}>
              {epic.id}
            </button>
          ) : (
            <span className="crumb current">{epic.id}</span>
          )}
        </>
      )}
      {story && (
        <>
          <span className="crumb-sep">/</span>
          <span className="crumb current">{story.id}</span>
        </>
      )}
    </nav>
  );
}

/** Niveau racine : grille de cartes epic avec compteur d'US et deps dérivées. */
function EpicsView({
  epics,
  stories,
  epicDeps,
  onOpenEpic,
}: {
  epics: Epic[];
  stories: UserStory[];
  epicDeps: Map<string, string[]>;
  onOpenEpic: (epicId: string) => void;
}) {
  return (
    <div className="epic-grid">
      {epics.map((epic) => {
        const es = stories.filter((s) => s.epic_id === epic.id);
        const done = es.filter((s) => s.status === "done").length;
        const deps = epicDeps.get(epic.id) ?? [];
        return (
          <div
            key={epic.id}
            className="epic epic-card"
            role="button"
            tabIndex={0}
            onClick={() => onOpenEpic(epic.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpenEpic(epic.id);
              }
            }}
          >
            <div className="epic-head">
              <span className="epic-id">{epic.id}</span>
              <span className="epic-iter">itération {epic.iteration}</span>
            </div>
            <div className="epic-title">{epic.title}</div>
            {epic.description && <p className="epic-desc">{epic.description}</p>}
            <div className="epic-card-meta">
              {es.length} US · {done}/{es.length} terminée(s)
            </div>
            {deps.length > 0 && (
              <div className="story-deps">⛓ dépend de {deps.join(", ")}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Niveau epic : description + liste des US (drag-&-drop, ajout). */
function EpicView({
  projectId,
  epic,
  stories,
  epicDeps,
  onOpenStory,
}: {
  projectId: string;
  epic: Epic;
  stories: UserStory[];
  epicDeps: Map<string, string[]>;
  onOpenStory: (storyId: string) => void;
}) {
  const es = stories.filter((s) => s.epic_id === epic.id);
  const deps = epicDeps.get(epic.id) ?? [];
  return (
    <div className="epic-view">
      <div className="epic-head">
        <span className="epic-id">{epic.id}</span>
        <span className="epic-iter">itération {epic.iteration}</span>
      </div>
      <h3 className="epic-view-title">{epic.title}</h3>
      {epic.description && <p className="epic-view-desc">{epic.description}</p>}
      {deps.length > 0 && (
        <div className="story-deps">⛓ dépend de {deps.join(", ")}</div>
      )}
      <EpicStories projectId={projectId} stories={es} onOpen={onOpenStory} />
      <AddStoryForm projectId={projectId} epicId={epic.id} />
    </div>
  );
}

type Nav = { level: "epics" | "epic" | "us"; epicId?: string; storyId?: string };

interface Props {
  epics: Epic[];
  stories: UserStory[];
  projectId: string;
}

export function Board({ epics, stories, projectId }: Props) {
  const [nav, setNav] = useState<Nav>({ level: "epics" });

  if (epics.length === 0) {
    return (
      <div className="panel board empty">
        <h2>Board Epics / User stories</h2>
        <p className="placeholder">Le PO n'a pas encore produit de plan.</p>
      </div>
    );
  }

  // Résolution de la navigation contre les props courantes (rafraîchies en live
  // par WebSocket) : un élément sélectionné qui disparaît fait remonter d'un
  // niveau plutôt que d'afficher du vide.
  const epicDeps = deriveEpicDeps(stories);
  const epic = nav.epicId ? epics.find((e) => e.id === nav.epicId) ?? null : null;
  const story =
    nav.level === "us" && epic && nav.storyId
      ? stories.find((s) => s.id === nav.storyId) ?? null
      : null;
  const level: Nav["level"] = !epic
    ? "epics"
    : nav.level === "us" && !story
      ? "epic"
      : nav.level;

  return (
    <div className="panel board">
      <div className="board-top">
        <h2>Board Epics / User stories</h2>
        <Breadcrumb
          epic={epic}
          story={story}
          onNavEpics={() => setNav({ level: "epics" })}
          onNavEpic={() => epic && setNav({ level: "epic", epicId: epic.id })}
        />
      </div>
      {level === "epics" && (
        <EpicsView
          epics={epics}
          stories={stories}
          epicDeps={epicDeps}
          onOpenEpic={(epicId) => setNav({ level: "epic", epicId })}
        />
      )}
      {level === "epic" && epic && (
        <EpicView
          projectId={projectId}
          epic={epic}
          stories={stories}
          epicDeps={epicDeps}
          onOpenStory={(storyId) => setNav({ level: "us", epicId: epic.id, storyId })}
        />
      )}
      {level === "us" && epic && story && (
        <div className="us-view">
          <StoryDetail
            projectId={projectId}
            story={story}
            onDeleted={() => setNav({ level: "epic", epicId: epic.id })}
          />
        </div>
      )}
    </div>
  );
}
