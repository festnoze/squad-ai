import { useEffect, useMemo, useState } from "react";
import {
  addStory,
  deleteStory,
  editStory,
  errorMessage,
  forceDoneStory,
  forceDoneTask,
  rebuildStory,
  rebuildTask,
  reorderStories,
  storyDiff,
  taskDiff,
} from "../api";
import {
  AcceptanceCriterion,
  blockedBy,
  criterionState,
  Epic,
  mergeState,
  Stream,
  StreamKind,
  StoryStatus,
  Task,
  TestState,
  UserStory,
  usEffectiveStatus,
} from "../types";
import { LlmActivity } from "./LlmActivity";
import { useI18n } from "../i18n/i18n";

/** Translate a work-item status to its display label. Resolved at render time so
 * the active language applies. */
function statusLabel(t: (key: string) => string, status: string): string {
  const map: Record<string, string> = {
    todo: t("board.status_todo"),
    in_progress: t("board.status_in_progress"),
    red: t("board.status_red"),
    green: t("board.status_green"),
    done: t("board.status_done"),
    failed: t("board.status_failed"),
  };
  return map[status] ?? status;
}

/** A work item is actively being worked on (so its LLM calls should poll live). */
function isLiveStatus(status: string): boolean {
  return status === "in_progress" || status === "red" || status === "green";
}

/** Translate a test state to its short label (resolved at render time). */
function testStateLabel(t: (key: string) => string, state: TestState): string {
  const map: Record<TestState, string> = {
    nonexistent: t("board.testState_nonexistent"),
    red: t("board.testState_red"),
    green: t("board.testState_green"),
  };
  return map[state];
}

const TEST_STATE_ICON: Record<TestState, string> = {
  nonexistent: "○",
  red: "●",
  green: "●",
};

/** ST-12: per-stream-kind icon. The colour is driven by CSS via the
 * `stream-badge-<kind>` class. */
const STREAM_ICON: Record<StreamKind, string> = {
  backend: "⚙",
  frontend: "🎨",
  cache: "⚡",
  database: "🗄",
  other: "📦",
};

/** ST-12: per-stream-kind short label, resolved at render time. */
function streamLabel(t: (key: string) => string, kind: StreamKind): string {
  const map: Record<StreamKind, string> = {
    backend: t("board.stream_backend"),
    frontend: t("board.stream_frontend"),
    cache: t("board.stream_cache"),
    database: t("board.stream_database"),
    other: t("board.stream_other"),
  };
  return map[kind] ?? map.other;
}

/** Stops a click from bubbling up to a parent click handler. */
const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();

/**
 * ST-12: stream badge (icon + label, colour per kind). Resolves a stream id to
 * the project's declared stream; falls back to the kind's generic label for an
 * unknown id. Rendered only by callers that have decided the item carries a
 * non-default stream — a legacy project (no streams) never shows one.
 */
function StreamBadge({ streamId, streams }: { streamId: string; streams: Stream[] }) {
  const { t } = useI18n();
  const stream = streams.find((s) => s.id === streamId);
  const kind: StreamKind = stream?.kind ?? "other";
  const icon = STREAM_ICON[kind] ?? STREAM_ICON.other;
  const kindLabel = streamLabel(t, kind);
  const label = stream ? `${icon} ${stream.id}` : `${icon} ${kindLabel}`;
  return (
    <span
      className={`stream-badge stream-badge-${kind}`}
      data-testid={`stream-badge-${streamId}`}
      title={t("board.streamBadge_title", { id: stream?.id ?? streamId, kind: kindLabel })}
    >
      {label}
    </span>
  );
}

/** ST-14: « bloquée par X » badge for a todo item with unmet dependencies. */
function BlockedBadge({ blockers }: { blockers: string[] }) {
  const { t } = useI18n();
  if (blockers.length === 0) return null;
  return (
    <span
      className="blocked-badge"
      data-testid="blocked-badge"
      title={t("board.blocked_title")}
    >
      ⛔ {t("board.blocked_label", { blockers: blockers.join(", ") })}
    </span>
  );
}

/** ST-14: merge-state hint — done = merged ✓, failed-on-conflict = ✗. */
function MergeBadge({ status, lastError }: { status: StoryStatus; lastError?: string }) {
  const { t } = useI18n();
  const state = mergeState(status, lastError);
  if (state === "merged") {
    return (
      <span
        className="merge-badge merge-ok"
        data-testid="merge-badge"
        title={t("board.merge_ok_title")}
      >
        ✓ {t("board.merge_ok_label")}
      </span>
    );
  }
  if (state === "conflict") {
    return (
      <span
        className="merge-badge merge-conflict"
        data-testid="merge-badge"
        title={t("board.merge_conflict_title")}
      >
        ✗ {t("board.merge_conflict_label")}
      </span>
    );
  }
  return null;
}

/**
 * Pastille « itération N ». Cliquable (hyperlien vers la vue Itérations) quand
 * `onOpen` est fourni — sinon simple libellé. Le clic ne propage pas pour ne pas
 * déclencher l'ouverture de la carte parente.
 */
function IterationBadge({
  iteration,
  onOpen,
  compact,
}: {
  iteration: number;
  onOpen?: (iter: number) => void;
  compact?: boolean;
}) {
  const { t } = useI18n();
  const label = compact
    ? t("board.iteration_compact", { n: iteration })
    : t("board.iteration_full", { n: iteration });
  if (!onOpen) return <span className="epic-iter">{label}</span>;
  return (
    <button
      type="button"
      className="epic-iter epic-iter-link"
      title={t("board.iteration_title", { n: iteration })}
      onClick={(e) => {
        stop(e);
        onOpen(iteration);
      }}
    >
      🕒 {label}
    </button>
  );
}

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
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const state = criterionState(story, criterion);
  // `?? []` : robustesse face aux anciens états persistés sans ces champs.
  const tests = (story.test_plan ?? []).filter((tst) =>
    (tst.criteria ?? []).includes(criterion.id),
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
          {testStateLabel(t, state)}
        </span>
        <span className="criterion-expander">{open ? "▾" : "▸"}</span>
      </div>
      {open && (
        <div className="criterion-body">
          <h5>{t("board.acceptanceTests_heading", { count: tests.length })}</h5>
          {tests.length === 0 ? (
            <p className="placeholder small">{t("board.noUnitTest")}</p>
          ) : (
            <ul className="criterion-tests">
              {tests.map((tst) => (
                <li key={tst.id}>
                  <span className={`state-dot state-${tst.status}`}>
                    {TEST_STATE_ICON[tst.status]}
                  </span>
                  <span className="test-layer">{tst.layer || "?"}</span>
                  <span className="test-desc">{tst.description}</span>
                  {(tst.mocks ?? []).length > 0 && (
                    <span className="test-mocks">
                      {" · "}
                      {t("board.testMocks", { mocks: tst.mocks.join(", ") })}
                    </span>
                  )}
                  <span className={`state-tag state-${tst.status}`}>
                    {testStateLabel(t, tst.status)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {story.gherkin && (
            <>
              <h5>{t("board.gherkinAssociated")}</h5>
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
  const { t } = useI18n();
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
        <span>{t("board.field_title")}</span>
        <input
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
      </label>
      <label className="edit-field">
        <span>{t("board.field_description")}</span>
        <textarea
          rows={2}
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        />
      </label>
      <label className="edit-field">
        <span>{t("board.field_priority")}</span>
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
        <span>{t("board.field_criteria")}</span>
        <div className="edit-criteria">
          {draft.criteria.map((c, i) => (
            <div className="edit-criterion-row" key={c.id ?? `new-${i}`}>
              <input
                value={c.text}
                onChange={(e) => setCriterion(i, e.target.value)}
                placeholder={t("board.criterion_placeholder")}
              />
              <button
                type="button"
                className="danger small-btn"
                onClick={() => removeCriterion(i)}
                title={t("board.removeCriterion_title")}
              >
                ✕
              </button>
            </div>
          ))}
          <button type="button" className="ghost small-btn" onClick={addCriterion}>
            {t("board.addCriterion")}
          </button>
        </div>
      </div>
      <label className="edit-field">
        <span>{t("board.field_gherkin")}</span>
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
          {t("common.save")}
        </button>
        <button className="ghost" disabled={saving} onClick={onClose}>
          {t("common.cancel")}
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

/**
 * Diff overlay reusable for a story OR a task: the caller supplies the label id
 * and the fetcher (``storyDiff`` / ``taskDiff``), so the per-task Diff action
 * (ST-13) reuses the exact same UI as the story one.
 */
function DiffViewer({
  label,
  fetcher,
  onClose,
}: {
  label: string;
  fetcher: () => Promise<{ available: boolean; diff: string }>;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [diff, setDiff] = useState("");
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    fetcher()
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [label]);

  return (
    <div className="diff-overlay" onClick={onClose}>
      <div className="diff-panel" onClick={(e) => e.stopPropagation()}>
        <div className="diff-header">
          <span className="diff-title">📊 {t("board.diff_title", { label })}</span>
          <button
            type="button"
            className="ghost diff-close"
            onClick={onClose}
            aria-label={t("common.close")}
          >
            ✕
          </button>
        </div>
        <div className="diff-content">
          {loading && <div className="diff-muted">{t("common.loading")}</div>}
          {!loading && error && <div className="diff-error">{error}</div>}
          {!loading && !error && (!available || diff.trim() === "") && (
            <div className="diff-muted">{t("board.diff_none")}</div>
          )}
          {!loading && !error && available && diff.trim() !== "" && (
            <DiffBody diff={diff} />
          )}
        </div>
      </div>
    </div>
  );
}

/** Badges communs (priorité, statut, score qualité) d'une user story. Le statut
 * affiché est l'« effective status » : pour une US conteneur (avec tâches) il est
 * dérivé de ses tâches, sinon c'est le statut stocké. */
function StoryBadges({
  story,
  onStatusClick,
}: {
  story: UserStory;
  /** When set, the status badge becomes a button (opens the LLM activity view). */
  onStatusClick?: () => void;
}) {
  const { t } = useI18n();
  const status = usEffectiveStatus(story);
  const statusInner = (
    <>
      {status === "in_progress" && (
        <span className="spinner spinner-sm" aria-hidden="true" />
      )}
      {statusLabel(t, status)}
    </>
  );
  return (
    <span className="story-right">
      <span className={`prio prio-${story.priority}`} title={t("board.prio_title")}>
        P{story.priority}
      </span>
      {onStatusClick ? (
        <button
          type="button"
          className={`badge badge-${status} badge-btn`}
          title={t("board.statusBadge_title")}
          data-testid={`status-badge-${story.id}`}
          onClick={(e) => {
            stop(e);
            onStatusClick();
          }}
        >
          {statusInner} 🧠
        </button>
      ) : (
        <span className={`badge badge-${status}`}>{statusInner}</span>
      )}
      {story.quality_score >= 0 && (
        <span className="quality-badge" title={t("board.quality_title")}>
          ⚙ {story.quality_score}/100
        </span>
      )}
      {(story.mutation_score ?? -1) >= 0 && (
        <span className="mutation-badge" title={t("board.mutation_title")}>
          🧬 {story.mutation_score}/100
        </span>
      )}
      {(story.coverage_score ?? -1) >= 0 && (
        <span className="coverage-badge" title={t("board.coverage_title")}>
          📊 {story.coverage_score}%
        </span>
      )}
    </span>
  );
}

/**
 * ST-12: a task row inside a US's expandable sub-list. Carries its stream badge,
 * status (with the shared in-progress spinner for parallelism), blocked-by and
 * merge hints, and opens the task detail on click.
 */
function TaskRow({
  task,
  stories,
  streams,
  primaryStreamId,
  onOpen,
}: {
  task: Task;
  stories: UserStory[];
  streams: Stream[];
  primaryStreamId: string;
  onOpen: () => void;
}) {
  const { t } = useI18n();
  const blockers = blockedBy(task.depends_on, task.status, stories);
  const showStream = !!task.stream && task.stream !== primaryStreamId;
  return (
    <div
      className={`task-row status-${task.status}`}
      data-testid={`task-${task.id}`}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <span className="task-id">{task.id}</span>
      {showStream && <StreamBadge streamId={task.stream} streams={streams} />}
      <span className="task-title">{task.title || task.id}</span>
      <span className={`badge badge-${task.status}`}>
        {task.status === "in_progress" && (
          <span className="spinner spinner-sm" aria-hidden="true" />
        )}
        {statusLabel(t, task.status)}
      </span>
      <BlockedBadge blockers={blockers} />
      <MergeBadge status={task.status} lastError={task.last_error} />
    </div>
  );
}

/**
 * Carte compacte cliquable d'une user story (niveau « epic »). Le clic ouvre le
 * détail (niveau « us ») ; la poignée ⠿ reste dédiée au drag-&-drop de tri.
 * ST-12 : badge stream (si non-défaut), badges bloquée/merge, et sous-liste de
 * tâches dépliable quand la US est un conteneur.
 */
function StoryRow({
  story,
  stories,
  streams,
  primaryStreamId,
  onOpen,
  onOpenTask,
  dragOver,
  onHandleDragStart,
  onCardDragOver,
  onCardDragLeave,
  onCardDrop,
}: {
  story: UserStory;
  stories: UserStory[];
  streams: Stream[];
  primaryStreamId: string;
  onOpen: () => void;
  onOpenTask: (taskId: string) => void;
  dragOver: boolean;
  onHandleDragStart: (e: React.DragEvent) => void;
  onCardDragOver: (e: React.DragEvent) => void;
  onCardDragLeave: (e: React.DragEvent) => void;
  onCardDrop: (e: React.DragEvent) => void;
}) {
  const { t } = useI18n();
  const tasks = story.tasks ?? [];
  const [expanded, setExpanded] = useState(true);
  const effStatus = usEffectiveStatus(story);
  const blockers = blockedBy(story.depends_on, effStatus, stories);
  const showStream = !!story.stream && story.stream !== primaryStreamId;
  return (
    <div
      className={`story status-${effStatus}${dragOver ? " drag-over" : ""}`}
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
          title={t("board.dragHandle_title")}
          aria-label={t("board.dragHandle_aria")}
        >
          ⠿
        </span>
        <span className="story-id">{story.id}</span>
        {showStream && <StreamBadge streamId={story.stream!} streams={streams} />}
        <StoryBadges story={story} />
      </div>
      <div className="story-title">{story.title}</div>
      {(story.depends_on ?? []).length > 0 && (
        <div className="story-deps">
          ⛓ {t("board.dependsOn", { deps: story.depends_on.join(", ") })}
        </div>
      )}
      <div className="story-row-hints">
        <BlockedBadge blockers={blockers} />
        <MergeBadge status={effStatus} lastError={story.last_error} />
      </div>
      {tasks.length > 0 && (
        <div className="task-list" onClick={stop}>
          <button
            type="button"
            className="task-list-toggle"
            data-testid={`task-toggle-${story.id}`}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "▾" : "▸"}{" "}
            {tasks.length > 1
              ? t("board.tasks_count_plural", { count: tasks.length })
              : t("board.tasks_count", { count: tasks.length })}
          </button>
          {expanded && (
            <div className="tasks" data-testid={`tasks-${story.id}`}>
              {tasks.map((t) => (
                <TaskRow
                  key={t.id}
                  task={t}
                  stories={stories}
                  streams={streams}
                  primaryStreamId={primaryStreamId}
                  onOpen={() => onOpenTask(t.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
      <div className="story-open-hint">▸ {t("board.storyOpenHint")}</div>
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
  phase,
  onDeleted,
  onOpenIteration,
}: {
  projectId: string;
  story: UserStory;
  phase?: string;
  onDeleted: () => void;
  onOpenIteration?: (iter: number) => void;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [showLlm, setShowLlm] = useState(false);

  const handleDelete = async () => {
    if (!window.confirm(t("board.confirmDeleteStory", { title: story.title }))) return;
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

  // Une story « bloquée » (échec, tests rouges, ou todo déjà tentée/en erreur —
  // p. ex. orpheline d'une itération passée) est relançable dès que la pipeline
  // est dormante. Sans ça, une US `todo` avec une erreur n'avait aucun bouton.
  const dormant = ["done", "stopped", "error"].includes(phase ?? "");
  const stuck =
    story.status === "failed" ||
    story.status === "red" ||
    (story.status === "todo" && (story.attempts > 0 || !!story.last_error));
  const canRelaunch = dormant && stuck;

  return (
    <div className="story-detail">
      <div className="story-detail-head">
        <span className="story-id">{story.id}</span>
        <IterationBadge iteration={story.iteration} onOpen={onOpenIteration} compact />
        <StoryBadges story={story} onStatusClick={() => setShowLlm((v) => !v)} />
      </div>
      <h3 className="story-detail-title">{story.title}</h3>
      {(story.depends_on ?? []).length > 0 && (
        <div className="story-deps">
          ⛓ {t("board.dependsOn", { deps: story.depends_on.join(", ") })}
        </div>
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
              ✏️ {t("board.action_edit")}
            </button>
            <button className="danger small-btn" onClick={handleDelete}>
              🗑 {t("board.action_delete")}
            </button>
            {canRelaunch && (
              <>
                <button
                  className="action-btn small-btn"
                  disabled={busy}
                  onClick={handleRebuild}
                  title={t("board.relaunchStory_title")}
                >
                  🔄 {t("board.action_relaunch")}
                </button>
                <button
                  className="action-btn action-done small-btn"
                  disabled={busy}
                  onClick={handleForceDone}
                  title={t("board.forceDoneStory_title")}
                >
                  ✓ {t("board.action_forceDone")}
                </button>
              </>
            )}
            {story.status === "done" && (
              <button
                className="action-btn small-btn"
                disabled={busy}
                onClick={handleRebuild}
              >
                🔁 {t("board.action_replay")}
              </button>
            )}
            {story.status === "done" && (
              <button className="ghost small-btn" onClick={() => setShowDiff(true)}>
                📊 {t("board.action_diff")}
              </button>
            )}
          </div>
          {error && <div className="edit-error">{error}</div>}
          <p>{story.description}</p>
          {(story.acceptance_criteria ?? []).length > 0 && (
            <>
              <h4>{t("board.acceptanceCriteria_heading")}</h4>
              <div className="criteria">
                {story.acceptance_criteria.map((c) => (
                  <CriterionRow key={c.id} story={story} criterion={c} />
                ))}
              </div>
            </>
          )}
          {story.last_error && (
            <>
              <h4>{t("board.lastError_heading")}</h4>
              <pre className="error-output">{story.last_error}</pre>
            </>
          )}
        </>
      )}
      {showLlm && !editing && (
        <LlmActivity
          projectId={projectId}
          itemId={story.id}
          live={isLiveStatus(usEffectiveStatus(story))}
        />
      )}
      {showDiff && (
        <DiffViewer
          label={story.id}
          fetcher={() => storyDiff(projectId, story.id)}
          onClose={() => setShowDiff(false)}
        />
      )}
    </div>
  );
}

/**
 * ST-13: detailed view of a single task, mirroring ``StoryDetail`` : stream,
 * criteria, dependencies (with the blocked-by hint), merge state, last error and
 * the per-task actions Relancer / Forcer terminé / Diff. The relaunch guard
 * mirrors the story one (dormant pipeline + a stuck task).
 */
function TaskDetail({
  projectId,
  task,
  stories,
  streams,
  primaryStreamId,
  phase,
}: {
  projectId: string;
  task: Task;
  stories: UserStory[];
  streams: Stream[];
  primaryStreamId: string;
  phase?: string;
}) {
  const { t } = useI18n();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [showLlm, setShowLlm] = useState(false);

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

  const handleRebuild = run(() => rebuildTask(projectId, task.id));
  const handleForceDone = run(() => forceDoneTask(projectId, task.id));

  const dormant = ["done", "stopped", "error"].includes(phase ?? "");
  const stuck =
    task.status === "failed" ||
    task.status === "red" ||
    (task.status === "todo" && (task.attempts > 0 || !!task.last_error));
  const canRelaunch = dormant && stuck;
  const blockers = blockedBy(task.depends_on, task.status, stories);
  const showStream = !!task.stream && task.stream !== primaryStreamId;

  return (
    <div className="story-detail" data-testid={`task-detail-${task.id}`}>
      <div className="story-detail-head">
        <span className="story-id">{task.id}</span>
        {showStream && <StreamBadge streamId={task.stream} streams={streams} />}
        <button
          type="button"
          className={`badge badge-${task.status} badge-btn`}
          title={t("board.taskStatusBadge_title")}
          data-testid={`status-badge-${task.id}`}
          onClick={() => setShowLlm((v) => !v)}
        >
          {task.status === "in_progress" && (
            <span className="spinner spinner-sm" aria-hidden="true" />
          )}
          {statusLabel(t, task.status)} 🧠
        </button>
        <MergeBadge status={task.status} lastError={task.last_error} />
      </div>
      <h3 className="story-detail-title">{task.title || task.id}</h3>
      {(task.depends_on ?? []).length > 0 && (
        <div className="story-deps">
          ⛓ {t("board.dependsOn", { deps: task.depends_on.join(", ") })}
        </div>
      )}
      <div className="story-row-hints">
        <BlockedBadge blockers={blockers} />
      </div>
      <div className="story-toolbar">
        {canRelaunch && (
          <>
            <button
              className="action-btn small-btn"
              disabled={busy}
              onClick={handleRebuild}
              title={t("board.relaunchTask_title")}
            >
              🔄 {t("board.action_relaunch")}
            </button>
            <button
              className="action-btn action-done small-btn"
              disabled={busy}
              onClick={handleForceDone}
              title={t("board.forceDoneTask_title")}
            >
              ✓ {t("board.action_forceDone")}
            </button>
          </>
        )}
        {task.status === "done" && (
          <button
            className="action-btn small-btn"
            disabled={busy}
            onClick={handleRebuild}
          >
            🔁 {t("board.action_replay")}
          </button>
        )}
        {task.status === "done" && (
          <button className="ghost small-btn" onClick={() => setShowDiff(true)}>
            📊 {t("board.action_diff")}
          </button>
        )}
      </div>
      {error && <div className="edit-error">{error}</div>}
      {task.description && <p>{task.description}</p>}
      {(task.acceptance_criteria ?? []).length > 0 && (
        <>
          <h4>{t("board.acceptanceCriteria_heading")}</h4>
          <ul className="task-criteria">
            {task.acceptance_criteria.map((c) => (
              <li key={c.id}>{c.text}</li>
            ))}
          </ul>
        </>
      )}
      {task.gherkin && (
        <>
          <h4>{t("board.field_gherkin")}</h4>
          <pre className="gherkin">{task.gherkin}</pre>
        </>
      )}
      {task.last_error && (
        <>
          <h4>{t("board.lastError_heading")}</h4>
          <pre className="error-output">{task.last_error}</pre>
        </>
      )}
      {showLlm && (
        <LlmActivity
          projectId={projectId}
          itemId={task.id}
          live={isLiveStatus(task.status)}
        />
      )}
      {showDiff && (
        <DiffViewer
          label={task.id}
          fetcher={() => taskDiff(projectId, task.id)}
          onClose={() => setShowDiff(false)}
        />
      )}
    </div>
  );
}

function AddStoryForm({ projectId, epicId }: { projectId: string; epicId: string }) {
  const { t } = useI18n();
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
      setError(t("board.titleRequired"));
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
        {t("board.addStory")}
      </button>
    );
  }

  return (
    <div className="add-story-form">
      <label className="edit-field">
        <span>{t("board.field_titleRequired")}</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="edit-field">
        <span>{t("board.field_description")}</span>
        <textarea
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <label className="edit-field">
        <span>{t("board.field_priority")}</span>
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
          {t("board.create")}
        </button>
        <button className="ghost" disabled={saving} onClick={reset}>
          {t("common.cancel")}
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
  allStories,
  streams,
  primaryStreamId,
  onOpen,
  onOpenTask,
}: {
  projectId: string;
  stories: UserStory[];
  /** Every story (all epics) — needed to resolve cross-stream blocked-by. */
  allStories: UserStory[];
  streams: Stream[];
  primaryStreamId: string;
  onOpen: (storyId: string) => void;
  onOpenTask: (taskId: string) => void;
}) {
  const { t } = useI18n();
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
      setError(t("board.reorderFailed", { error: errorMessage(err) }));
    }
  };

  return (
    <div className="stories">
      {error && <div className="edit-error">{error}</div>}
      {ordered.map((s) => (
        <StoryRow
          key={s.id}
          story={s}
          stories={allStories}
          streams={streams}
          primaryStreamId={primaryStreamId}
          onOpen={() => onOpen(s.id)}
          onOpenTask={onOpenTask}
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
  taskId,
  onNavEpics,
  onNavEpic,
  onNavStory,
}: {
  epic: Epic | null;
  story: UserStory | null;
  taskId?: string | null;
  onNavEpics: () => void;
  onNavEpic: () => void;
  onNavStory: () => void;
}) {
  const { t } = useI18n();
  return (
    <nav className="breadcrumb" aria-label={t("board.breadcrumb_aria")}>
      <button className="crumb" onClick={onNavEpics} disabled={!epic && !story}>
        {t("board.breadcrumb_epics")}
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
          {taskId ? (
            <button className="crumb" onClick={onNavStory}>
              {story.id}
            </button>
          ) : (
            <span className="crumb current">{story.id}</span>
          )}
        </>
      )}
      {taskId && (
        <>
          <span className="crumb-sep">/</span>
          <span className="crumb current">{taskId}</span>
        </>
      )}
    </nav>
  );
}

export type EpicState = "working" | "failed" | "done" | "pending";

export interface EpicProgress {
  total: number;
  done: number;
  inProgress: number;
  failed: number;
  pct: number;
  state: EpicState;
}

/** Avancement d'un ensemble de stories : compteurs + état dérivé (priorité au
 * « en cours »). Réutilisé par la vue Itérations. */
export function epicProgress(stories: UserStory[]): EpicProgress {
  // ST-12: count by EFFECTIVE status so a container US (with tasks) contributes
  // its derived state. Legacy taskless US keep their stored status, unchanged.
  const total = stories.length;
  const eff = stories.map((s) => usEffectiveStatus(s));
  const done = eff.filter((s) => s === "done").length;
  const inProgress = eff.filter((s) => s === "in_progress").length;
  const failed = eff.filter((s) => s === "failed").length;
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  const state: EpicState =
    inProgress > 0
      ? "working"
      : failed > 0
        ? "failed"
        : total > 0 && done === total
          ? "done"
          : "pending";
  return { total, done, inProgress, failed, pct, state };
}

/** Barre d'avancement d'un epic + ligne de compteurs (done / en cours / échec). */
export function EpicProgressBar({ prog }: { prog: EpicProgress }) {
  const { t } = useI18n();
  return (
    <>
      <div
        className="epic-progress"
        role="progressbar"
        aria-valuenow={prog.pct}
        aria-valuemin={0}
        aria-valuemax={100}
        title={t("board.progress_title", {
          done: prog.done,
          total: prog.total,
          pct: prog.pct,
        })}
      >
        <div
          className={`epic-progress-fill state-${prog.state}`}
          style={{ width: `${prog.pct}%` }}
        />
      </div>
      <div className="epic-card-meta">
        {t("board.progress_done", { done: prog.done, total: prog.total })}
        {prog.inProgress > 0 && (
          <span className="epic-meta-working">
            {" · "}
            {t("board.progress_inProgress", { count: prog.inProgress })}
          </span>
        )}
        {prog.failed > 0 && (
          <span className="epic-meta-failed">
            {" · "}
            {t("board.progress_failed", { count: prog.failed })}
          </span>
        )}
      </div>
    </>
  );
}

/** Carte epic cliquable (niveau racine) : avancement + halo « working ». */
function EpicCard({
  epic,
  stories,
  epicDeps,
  onOpenEpic,
  onOpenIteration,
}: {
  epic: Epic;
  stories: UserStory[];
  epicDeps: Map<string, string[]>;
  onOpenEpic: (epicId: string) => void;
  onOpenIteration?: (iter: number) => void;
}) {
  const { t } = useI18n();
  const es = stories.filter((s) => s.epic_id === epic.id);
  const prog = epicProgress(es);
  const deps = epicDeps.get(epic.id) ?? [];
  return (
    <div
      className={`epic epic-card epic-${prog.state}`}
      data-testid={`epic-${epic.id}`}
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
        <span className="epic-head-right">
          {prog.state === "working" && (
            <span
              className="spinner"
              data-testid="epic-spinner"
              title={t("board.developmentInProgress")}
              aria-label={t("board.developmentInProgress")}
            />
          )}
          <IterationBadge
            iteration={epic.iteration}
            onOpen={onOpenIteration}
            compact
          />
        </span>
      </div>
      <div className="epic-title">{epic.title}</div>
      {epic.description && <p className="epic-desc">{epic.description}</p>}
      <EpicProgressBar prog={prog} />
      {deps.length > 0 && (
        <div className="story-deps">
          ⛓ {t("board.dependsOn", { deps: deps.join(", ") })}
        </div>
      )}
    </div>
  );
}

/**
 * Niveau racine : vision produit à plat. Tous les epics sont affichés dans une
 * grille unique, indépendamment de leur itération de build — la dimension
 * temporelle vit dans la vue « Itérations » dédiée. Chaque carte porte une
 * pastille « it. N » cliquable qui bascule vers cette chronologie.
 */
function EpicsView({
  epics,
  stories,
  epicDeps,
  onOpenEpic,
  onOpenIteration,
}: {
  epics: Epic[];
  stories: UserStory[];
  epicDeps: Map<string, string[]>;
  onOpenEpic: (epicId: string) => void;
  onOpenIteration?: (iter: number) => void;
}) {
  return (
    <div className="epic-grid">
      {epics.map((epic) => (
        <EpicCard
          key={epic.id}
          epic={epic}
          stories={stories}
          epicDeps={epicDeps}
          onOpenEpic={onOpenEpic}
          onOpenIteration={onOpenIteration}
        />
      ))}
    </div>
  );
}

/**
 * ST-12: does an item (US or any of its tasks) belong to the given stream id?
 * Used by the stream filter — a US is kept if itself OR any task matches.
 */
function storyTouchesStream(
  story: UserStory,
  streamId: string,
  primaryStreamId: string,
): boolean {
  const usStream = story.stream || primaryStreamId;
  if (usStream === streamId) return true;
  return (story.tasks ?? []).some((t) => (t.stream || primaryStreamId) === streamId);
}

/** Niveau epic : description + liste des US (drag-&-drop, ajout). ST-12 : la
 * liste peut être filtrée par stream. */
function EpicView({
  projectId,
  epic,
  stories,
  streams,
  primaryStreamId,
  streamFilter,
  epicDeps,
  onOpenStory,
  onOpenTask,
  onOpenIteration,
}: {
  projectId: string;
  epic: Epic;
  stories: UserStory[];
  streams: Stream[];
  primaryStreamId: string;
  streamFilter: string; // "" = no filter (all streams)
  epicDeps: Map<string, string[]>;
  onOpenStory: (storyId: string) => void;
  onOpenTask: (taskId: string) => void;
  onOpenIteration?: (iter: number) => void;
}) {
  const { t } = useI18n();
  const all = stories.filter((s) => s.epic_id === epic.id);
  const es = streamFilter
    ? all.filter((s) => storyTouchesStream(s, streamFilter, primaryStreamId))
    : all;
  const prog = epicProgress(all);
  const deps = epicDeps.get(epic.id) ?? [];
  return (
    <div className={`epic-view epic-${prog.state}`}>
      <div className="epic-head">
        <span className="epic-id">{epic.id}</span>
        <IterationBadge iteration={epic.iteration} onOpen={onOpenIteration} />
      </div>
      <h3 className="epic-view-title">
        {prog.state === "working" && (
          <span
            className="spinner"
            title={t("board.developmentInProgress")}
            aria-label={t("board.developmentInProgress")}
          />
        )}
        {epic.title}
      </h3>
      {epic.description && <p className="epic-view-desc">{epic.description}</p>}
      <EpicProgressBar prog={prog} />
      {deps.length > 0 && (
        <div className="story-deps">
          ⛓ {t("board.dependsOn", { deps: deps.join(", ") })}
        </div>
      )}
      <EpicStories
        projectId={projectId}
        stories={es}
        allStories={stories}
        streams={streams}
        primaryStreamId={primaryStreamId}
        onOpen={onOpenStory}
        onOpenTask={onOpenTask}
      />
      <AddStoryForm projectId={projectId} epicId={epic.id} />
    </div>
  );
}

type Nav = {
  level: "epics" | "epic" | "us" | "task";
  epicId?: string;
  storyId?: string;
  taskId?: string;
};

interface Props {
  epics: Epic[];
  stories: UserStory[];
  /** ST-12: declared streams (empty/absent = legacy single-stream project). */
  streams?: Stream[];
  projectId: string;
  phase?: string;
  /** Cible de navigation pilotée de l'extérieur (depuis la vue Itérations) :
   * ouvre l'epic, et la US si fournie. */
  focus?: { epicId: string; storyId?: string } | null;
  /** Appelé une fois `focus` appliqué, pour que le parent le remette à null. */
  onFocusConsumed?: () => void;
  /** Bascule vers la vue Itérations sur l'itération donnée (pastille « it. N »). */
  onOpenIteration?: (iter: number) => void;
}

const PLANNING_PHASES = ["spec", "analyze", "plan", "architect"];

export function Board({
  epics,
  stories,
  streams,
  projectId,
  phase,
  focus,
  onFocusConsumed,
  onOpenIteration,
}: Props) {
  const { t } = useI18n();
  const [nav, setNav] = useState<Nav>({ level: "epics" });
  // ST-12: active stream filter ("" = all streams). Only offered when the
  // project declares more than one stream (legacy projects never see it).
  const [streamFilter, setStreamFilter] = useState<string>("");

  const declaredStreams = streams ?? [];
  const multiStream = declaredStreams.length > 1;
  const primaryStreamId = useMemo(
    () => declaredStreams.find((s) => s.primary)?.id
      ?? declaredStreams.find((s) => s.kind === "backend")?.id
      ?? declaredStreams[0]?.id
      ?? "backend",
    [declaredStreams],
  );

  // Navigation pilotée depuis l'extérieur (clic sur une US dans la chronologie).
  useEffect(() => {
    if (!focus) return;
    setNav(
      focus.storyId
        ? { level: "us", epicId: focus.epicId, storyId: focus.storyId }
        : { level: "epic", epicId: focus.epicId },
    );
    onFocusConsumed?.();
  }, [focus, onFocusConsumed]);

  if (epics.length === 0) {
    // UI6 : état vide contextuel — un spinner « plan en cours » quand le PM/PO
    // travaille, sinon une consigne claire (plutôt qu'une phrase morte).
    const planning = PLANNING_PHASES.includes(phase ?? "");
    return (
      <div className="panel board empty">
        <h2>{t("board.boardTitle")}</h2>
        <div className="board-empty">
          {planning ? (
            <>
              <span className="spinner" aria-hidden="true" />
              <p className="placeholder">{t("board.empty_planning")}</p>
            </>
          ) : phase === "build" ? (
            <p className="placeholder">{t("board.empty_building")}</p>
          ) : (
            <p className="placeholder">
              {t("board.empty_noPlan_before")}
              <strong>{t("board.empty_noPlan_execution")}</strong>
              {t("board.empty_noPlan_after")}
            </p>
          )}
        </div>
      </div>
    );
  }

  // Résolution de la navigation contre les props courantes (rafraîchies en live
  // par WebSocket) : un élément sélectionné qui disparaît fait remonter d'un
  // niveau plutôt que d'afficher du vide.
  const epicDeps = deriveEpicDeps(stories);
  const epic = nav.epicId ? epics.find((e) => e.id === nav.epicId) ?? null : null;
  const story =
    (nav.level === "us" || nav.level === "task") && epic && nav.storyId
      ? stories.find((s) => s.id === nav.storyId) ?? null
      : null;
  const task =
    nav.level === "task" && story && nav.taskId
      ? (story.tasks ?? []).find((t) => t.id === nav.taskId) ?? null
      : null;
  const level: Nav["level"] = !epic
    ? "epics"
    : (nav.level === "us" || nav.level === "task") && !story
      ? "epic"
      : nav.level === "task" && !task
        ? "us"
        : nav.level;

  // Resolve a task id to its (epic, story) so we can open its detail from any
  // level — the task carries its story_id, the story its epic_id.
  const openTaskById = (taskId: string) => {
    const owner = stories.find((s) => (s.tasks ?? []).some((t) => t.id === taskId));
    if (!owner) return;
    setNav({ level: "task", epicId: owner.epic_id, storyId: owner.id, taskId });
  };
  const openTask = (storyId: string, taskId: string) => {
    const owner = stories.find((s) => s.id === storyId);
    setNav({ level: "task", epicId: owner?.epic_id, storyId, taskId });
  };

  return (
    <div className="panel board">
      <div className="board-top">
        <h2>{t("board.boardTitle")}</h2>
        <Breadcrumb
          epic={epic}
          story={story}
          taskId={level === "task" ? task?.id : null}
          onNavEpics={() => setNav({ level: "epics" })}
          onNavEpic={() => epic && setNav({ level: "epic", epicId: epic.id })}
          onNavStory={() =>
            epic && story && setNav({ level: "us", epicId: epic.id, storyId: story.id })
          }
        />
      </div>
      {multiStream && (
        <div className="stream-filter" role="group" aria-label={t("board.streamFilter_aria")}>
          <button
            type="button"
            className={streamFilter === "" ? "active" : ""}
            aria-pressed={streamFilter === ""}
            onClick={() => setStreamFilter("")}
          >
            {t("board.streamFilter_all")}
          </button>
          {declaredStreams.map((s) => (
            <button
              key={s.id}
              type="button"
              data-testid={`stream-filter-${s.id}`}
              className={streamFilter === s.id ? "active" : ""}
              aria-pressed={streamFilter === s.id}
              onClick={() => setStreamFilter((cur) => (cur === s.id ? "" : s.id))}
            >
              {STREAM_ICON[s.kind] ?? STREAM_ICON.other} {s.id}
            </button>
          ))}
        </div>
      )}
      {level === "epics" && (
        <EpicsView
          epics={epics}
          stories={stories}
          epicDeps={epicDeps}
          onOpenEpic={(epicId) => setNav({ level: "epic", epicId })}
          onOpenIteration={onOpenIteration}
        />
      )}
      {level === "epic" && epic && (
        <EpicView
          projectId={projectId}
          epic={epic}
          stories={stories}
          streams={declaredStreams}
          primaryStreamId={primaryStreamId}
          streamFilter={streamFilter}
          epicDeps={epicDeps}
          onOpenStory={(storyId) => setNav({ level: "us", epicId: epic.id, storyId })}
          onOpenTask={openTaskById}
          onOpenIteration={onOpenIteration}
        />
      )}
      {level === "us" && epic && story && (
        <div className="us-view">
          {(story.tasks ?? []).length > 0 && (
            <div className="us-tasks" data-testid={`us-tasks-${story.id}`}>
              <h4>{t("board.tasksHeading", { count: story.tasks!.length })}</h4>
              <div className="tasks">
                {story.tasks!.map((t) => (
                  <TaskRow
                    key={t.id}
                    task={t}
                    stories={stories}
                    streams={declaredStreams}
                    primaryStreamId={primaryStreamId}
                    onOpen={() => openTask(story.id, t.id)}
                  />
                ))}
              </div>
            </div>
          )}
          <StoryDetail
            projectId={projectId}
            story={story}
            phase={phase}
            onDeleted={() => setNav({ level: "epic", epicId: epic.id })}
            onOpenIteration={onOpenIteration}
          />
        </div>
      )}
      {level === "task" && epic && story && task && (
        <div className="us-view">
          <TaskDetail
            projectId={projectId}
            task={task}
            stories={stories}
            streams={declaredStreams}
            primaryStreamId={primaryStreamId}
            phase={phase}
          />
        </div>
      )}
    </div>
  );
}
