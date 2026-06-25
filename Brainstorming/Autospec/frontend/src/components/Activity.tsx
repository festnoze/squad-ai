import { useEffect, useMemo, useState } from "react";
import {
  errorMessage,
  extendStory,
  forceDoneStory,
  forceDoneTask,
  rebuildStory,
  rebuildTask,
  storyChat,
  storyDiff,
  taskChat,
  taskDiff,
} from "../api";
import {
  Epic,
  GuidanceEntry,
  ProjectTicks,
  Stream,
  Task,
  TickItem,
  UserStory,
} from "../types";
import {
  blockedBy,
  buildWorkGraph,
  deriveItemView,
  ItemView,
  WorkItem,
} from "../work";
import { useI18n } from "../i18n/i18n";
import { LlmActivity } from "./LlmActivity";
import { Stepper } from "./Stepper";

type TFn = (key: string, vars?: Record<string, string | number>) => string;

/** Is the item actively being worked on (so its LLM calls should poll live)? */
function isLive(status: string): boolean {
  return status === "in_progress" || status === "red" || status === "green";
}

/** P15: persona → icon (forme/icône = persona, canal orthogonal de la couleur). */
const PERSONA_META: Record<string, { icon: string; labelKey: string }> = {
  dev: { icon: "👨‍💻", labelKey: "activity.personaDev" },
  qa: { icon: "🧪", labelKey: "activity.personaQa" },
  critic: { icon: "🔍", labelKey: "activity.personaCritic" },
  judge: { icon: "⚖️", labelKey: "activity.personaJudge" },
  architect: { icon: "🏛️", labelKey: "activity.personaArchitect" },
  analyst: { icon: "📊", labelKey: "activity.personaAnalyst" },
  pm: { icon: "📋", labelKey: "activity.personaPm" },
  po: { icon: "🗂", labelKey: "activity.personaPo" },
};

/** Translation key for a guidance delivery status. */
const GUIDANCE_STATUS_KEY: Record<string, string> = {
  queued: "activity.guidanceQueued",
  applied: "activity.guidanceApplied",
  too_late: "activity.guidanceTooLate",
};

/** Human label for a stall reason (why the build can't advance right now). */
function stallLabel(reason: string, t: TFn): string {
  if (!reason) return "";
  if (reason.startsWith("merge_lock_held:")) {
    return t("activity.stallMergeLock", {
      holder: reason.slice("merge_lock_held:".length),
    });
  }
  if (reason === "awaiting_approval") return t("activity.stallAwaitingApproval");
  if (reason === "budget_paused") return t("activity.stallBudgetPaused");
  return reason;
}

/** Resolve the persisted story or task behind a work item id. */
function itemSource(
  item: WorkItem,
  storyById: Map<string, UserStory>,
  taskById: Map<string, Task>,
): UserStory | Task | undefined {
  return item.kind === "task" ? taskById.get(item.id) : storyById.get(item.id);
}

/** Is the item one the operator should look at first? */
function needsAttention(view: ItemView, blockers: string[]): boolean {
  return (
    view.status === "failed" ||
    view.status === "red" ||
    view.stage === "failed" ||
    blockers.length > 0
  );
}

/** Per-item targeted chat box: send a directive, list guidance with its delivery
 *  status. Used inside an item row's drawer. */
function ItemChat({
  view,
  guidance,
  onSend,
}: {
  view: ItemView;
  guidance: GuidanceEntry[];
  onSend: (message: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    const message = text.trim();
    if (!message) return;
    setBusy(true);
    setError("");
    try {
      await onSend(message);
      setText("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="item-chat" data-testid={`item-chat-${view.id}`}>
      <div className="item-chat-guidance" data-testid={`guidance-list-${view.id}`}>
        {guidance.length === 0 ? (
          <p className="placeholder small">{t("activity.noGuidance")}</p>
        ) : (
          <ul className="guidance-entries">
            {guidance.map((g) => (
              <li
                key={g.id}
                className={`guidance-entry guidance-${g.status}`}
                data-testid={`guidance-entry-${g.id}`}
                data-status={g.status}
              >
                <span className="guidance-text">{g.text}</span>
                <span className={`guidance-status guidance-status-${g.status}`}>
                  {GUIDANCE_STATUS_KEY[g.status] ? t(GUIDANCE_STATUS_KEY[g.status]) : g.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="item-chat-input">
        <textarea
          rows={2}
          value={text}
          placeholder={t("activity.guidancePlaceholder", { id: view.id })}
          aria-label={t("activity.guidanceAriaLabel", { id: view.id })}
          data-testid={`item-chat-input-${view.id}`}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <button
          type="button"
          className="primary small-btn"
          disabled={busy || text.trim() === ""}
          data-testid={`item-chat-send-${view.id}`}
          onClick={() => void submit()}
        >
          {t("activity.send")}
        </button>
      </div>
      {error && <div className="edit-error">{error}</div>}
    </div>
  );
}

/** "Extend criteria" affordance for a TODO item: add acceptance criteria before
 *  the item is built. Only offered for a not-yet-built story. */
function ExtendCriteria({
  story,
  onExtend,
}: {
  story: UserStory;
  onExtend: (criteria: string[]) => Promise<void>;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const existing = (story.acceptance_criteria ?? []).map((c) => c.text);

  const submit = async () => {
    const added = text
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l !== "");
    if (added.length === 0) return;
    setBusy(true);
    setError("");
    try {
      await onExtend([...existing, ...added]);
      setText("");
      setOpen(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        className="ghost small-btn"
        data-testid={`extend-${story.id}`}
        onClick={() => setOpen(true)}
        title={t("activity.extendTitle")}
      >
        {t("activity.extendButton")}
      </button>
    );
  }

  return (
    <div className="extend-criteria" data-testid={`extend-form-${story.id}`}>
      <textarea
        rows={3}
        value={text}
        placeholder={t("activity.extendPlaceholder")}
        aria-label={t("activity.extendAriaLabel", { id: story.id })}
        data-testid={`extend-input-${story.id}`}
        onChange={(e) => setText(e.target.value)}
      />
      {error && <div className="edit-error">{error}</div>}
      <div className="edit-actions">
        <button
          type="button"
          className="primary small-btn"
          disabled={busy || text.trim() === ""}
          data-testid={`extend-submit-${story.id}`}
          onClick={() => void submit()}
        >
          {t("common.add")}
        </button>
        <button
          type="button"
          className="ghost small-btn"
          disabled={busy}
          onClick={() => {
            setOpen(false);
            setText("");
          }}
        >
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}

/** One Activity row: a Stepper + per-item action menu + collapsible drawer with
 *  the targeted chat (and the extend affordance for a TODO story). */
function ActivityRow({
  item,
  view,
  source,
  blockers,
  now,
  tickTs,
  projectId,
  onSendGuidance,
}: {
  item: WorkItem;
  view: ItemView;
  source: UserStory | Task | undefined;
  blockers: string[];
  now: number;
  tickTs?: number;
  projectId: string;
  onSendGuidance: (message: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);

  const isTask = item.kind === "task";
  const persona = view.persona ? PERSONA_META[view.persona] : undefined;
  const attention = needsAttention(view, blockers);
  const isStory = !isTask;
  const story = isStory ? (source as UserStory | undefined) : undefined;
  const canExtend = isStory && !!story && view.status === "todo";

  const run = (fn: () => Promise<void>) => async () => {
    setActionError("");
    setBusy(true);
    setMenuOpen(false);
    try {
      await fn();
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const handleRetry = run(() =>
    isTask ? rebuildTask(projectId, item.id) : rebuildStory(projectId, item.id),
  );
  const handleForce = run(() =>
    isTask ? forceDoneTask(projectId, item.id) : forceDoneStory(projectId, item.id),
  );

  return (
    <div
      className={`activity-row${attention ? " activity-row-attention" : ""}`}
      data-testid={`activity-row-${item.id}`}
      data-attention={attention ? "true" : "false"}
    >
      <div className="activity-row-main">
        <button
          type="button"
          className="activity-row-toggle"
          aria-expanded={drawerOpen}
          aria-label={t("activity.detailsAriaLabel", { id: item.id })}
          data-testid={`activity-toggle-${item.id}`}
          onClick={() => setDrawerOpen((o) => !o)}
        >
          {drawerOpen ? "▾" : "▸"}
        </button>
        <span className="activity-row-id">{item.id}</span>
        {persona && (
          <span
            className="activity-persona"
            data-testid={`activity-persona-${item.id}`}
            title={t("activity.personaTitle", { label: t(persona.labelKey) })}
          >
            {persona.icon} {t(persona.labelKey)}
          </span>
        )}
        <span className="activity-row-title">{item.title}</span>
        <Stepper view={view} now={now} tickTs={tickTs} />
        <div className="activity-row-menu-wrap">
          <button
            type="button"
            className="ghost small-btn"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-label={t("activity.actionsAriaLabel", { id: item.id })}
            data-testid={`activity-menu-${item.id}`}
            disabled={busy}
            onClick={() => setMenuOpen((o) => !o)}
          >
            ⋯
          </button>
          {menuOpen && (
            <div className="activity-menu" role="menu">
              <button role="menuitem" onClick={handleRetry}>
                {t("activity.menuRetry")}
              </button>
              <button role="menuitem" onClick={handleForce}>
                {t("activity.menuForceDone")}
              </button>
              <button
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  setShowDiff(true);
                }}
              >
                {t("activity.menuDiff")}
              </button>
              <button
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  setDrawerOpen(true);
                }}
              >
                {t("activity.menuChat")}
              </button>
            </div>
          )}
        </div>
      </div>
      {blockers.length > 0 && (
        <div className="activity-blockers" data-testid={`activity-blockers-${item.id}`}>
          {t("activity.blockedBy", { blockers: blockers.join(", ") })}
        </div>
      )}
      {actionError && <div className="edit-error">{actionError}</div>}
      {drawerOpen && (
        <div className="activity-drawer" data-testid={`activity-drawer-${item.id}`}>
          <ItemChat view={view} guidance={view.guidance} onSend={onSendGuidance} />
          {canExtend && story && (
            <ExtendCriteria
              story={story}
              onExtend={(criteria) => extendStory(projectId, story.id, criteria).then(() => undefined)}
            />
          )}
          <LlmActivity
            projectId={projectId}
            itemId={item.id}
            live={isLive(view.status)}
          />
        </div>
      )}
      {showDiff && (
        <div
          className="diff-overlay"
          data-testid={`activity-diff-${item.id}`}
          onClick={() => setShowDiff(false)}
        >
          <div className="diff-panel" onClick={(e) => e.stopPropagation()}>
            <div className="diff-header">
              <span className="diff-title">{t("activity.diffTitle", { id: item.id })}</span>
              <button
                type="button"
                className="ghost diff-close"
                aria-label={t("common.close")}
                onClick={() => setShowDiff(false)}
              >
                ✕
              </button>
            </div>
            <DiffContent
              fetcher={() =>
                isTask ? taskDiff(projectId, item.id) : storyDiff(projectId, item.id)
              }
            />
          </div>
        </div>
      )}
    </div>
  );
}

/** Minimal diff loader (the Board has a richer one; here we keep Activity
 *  self-contained while reusing the same api fns). */
function DiffContent({
  fetcher,
}: {
  fetcher: () => Promise<{ available: boolean; diff: string }>;
}) {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [diff, setDiff] = useState("");
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
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
  }, []);

  return (
    <div className="diff-content">
      {loading && <div className="diff-muted">{t("common.loading")}</div>}
      {!loading && error && <div className="diff-error">{error}</div>}
      {!loading && !error && (!available || diff.trim() === "") && (
        <div className="diff-muted">{t("activity.noDiff")}</div>
      )}
      {!loading && !error && available && diff.trim() !== "" && (
        <pre className="diff-pre">{diff}</pre>
      )}
    </div>
  );
}

interface Props {
  epics: Epic[];
  stories: UserStory[];
  streams?: Stream[];
  projectId: string;
  phase?: string;
  /** Whole project (for the approval banner / awaiting_approval gate string). */
  awaitingApproval?: string;
  onApprove?: () => void;
  onReject?: () => void;
  /** B-UX: live heartbeat for THIS project. */
  ticks?: ProjectTicks;
}

/**
 * P6: the canonical build surface. Fed by `buildWorkGraph` + the `ProjectTicks`
 * heartbeat. Header carries running/queued/done/failed counts + a persistent
 * failed/blocked count chip + the stall reason. A pinned "needs attention" region
 * lists failed/blocked items first. Each row is a Stepper for one work item,
 * merging the persisted stage with the live tick. A collapsible crew rail filters
 * rows by `current_persona`.
 *
 * Accessible names / test ids the e2e stage can target:
 *  - tab (in WorkspaceViews): role="tab" name "⚡ Activité"
 *  - region: role="region", aria-label="Activité"
 *  - approval banner: data-testid="approval-banner-activity"
 *  - failed/blocked chip: data-testid="attention-chip"
 *  - crew rail: data-testid="crew-rail", buttons data-testid={`crew-${persona}`}
 *  - per row: data-testid={`activity-row-${id}`}, the Stepper {`stepper-${id}`}
 *  - per-item chat: input {`item-chat-input-${id}`}, send {`item-chat-send-${id}`}
 *  - guidance entry: {`guidance-entry-${entryId}`}
 *  - extend control: {`extend-${storyId}`}
 */
export function Activity({
  epics,
  stories,
  streams,
  projectId,
  awaitingApproval,
  onApprove,
  onReject,
  ticks,
}: Props) {
  void epics;
  const { t } = useI18n();
  const [crewFilter, setCrewFilter] = useState<string>("");
  const [crewOpen, setCrewOpen] = useState(true);
  const now = Date.now();
  const tickTs = ticks?.ts ? ticks.ts * 1000 : undefined;

  const tickById = useMemo(() => {
    const m = new Map<string, TickItem>();
    for (const id in ticks?.items ?? {}) m.set(id, ticks!.items[id]);
    return m;
  }, [ticks]);

  const storyById = useMemo(() => new Map(stories.map((s) => [s.id, s])), [stories]);
  const taskById = useMemo(() => {
    const m = new Map<string, Task>();
    for (const s of stories) for (const t of s.tasks ?? []) m.set(t.id, t);
    return m;
  }, [stories]);

  const graph = useMemo(
    () => buildWorkGraph(stories, streams ?? []),
    [stories, streams],
  );

  // Build one row model per work item (persisted ⊕ tick).
  const rows = useMemo(() => {
    const out: {
      item: WorkItem;
      view: ItemView;
      source: UserStory | Task | undefined;
      blockers: string[];
    }[] = [];
    for (const item of graph.values()) {
      const source = itemSource(item, storyById, taskById);
      if (!source) continue;
      const view = deriveItemView(source, tickById.get(item.id));
      const blockers = blockedBy(item.id, graph);
      out.push({ item, view, source, blockers });
    }
    return out;
  }, [graph, storyById, taskById, tickById]);

  // Header counts: prefer the live tick counts; fall back to deriving from rows.
  const counts = useMemo(() => {
    if (ticks?.counts) return ticks.counts;
    let running = 0;
    let queued = 0;
    let done = 0;
    let failed = 0;
    let blocked = 0;
    for (const r of rows) {
      const st = r.view.status;
      if (st === "in_progress" || st === "red" || st === "green") running++;
      else if (st === "done") done++;
      else if (st === "failed") failed++;
      else if (r.blockers.length > 0) blocked++;
      else queued++;
    }
    return { running, queued, done, failed, blocked };
  }, [ticks, rows]);

  const stallReason = ticks?.stallReason ?? "";
  const attentionCount = counts.failed + counts.blocked;

  // Crew rail: personas currently active across the rows, with their counts.
  const crew = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) {
      const p = r.view.persona;
      if (p) m.set(p, (m.get(p) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [rows]);

  const visibleRows = crewFilter
    ? rows.filter((r) => r.view.persona === crewFilter)
    : rows;

  const attentionRows = visibleRows.filter((r) =>
    needsAttention(r.view, r.blockers),
  );
  // BUG11 : un item épinglé dans « À traiter » ne doit pas aussi apparaître dans
  // la liste principale — un ActivityRow dupliqué monte un second tiroir de chat /
  // menu d'actions / poller LlmActivity live pour le même item.
  const normalRows = attentionRows.length
    ? visibleRows.filter((r) => !needsAttention(r.view, r.blockers))
    : visibleRows;

  const sendGuidance = (item: WorkItem) => (message: string) =>
    (item.kind === "task"
      ? taskChat(projectId, item.id, message)
      : storyChat(projectId, item.id, message)
    ).then(() => undefined);

  const renderRow = (r: (typeof rows)[number]) => (
    <ActivityRow
      key={r.item.id}
      item={r.item}
      view={r.view}
      source={r.source}
      blockers={r.blockers}
      now={now}
      tickTs={tickTs}
      projectId={projectId}
      onSendGuidance={sendGuidance(r.item)}
    />
  );

  return (
    <section className="panel activity" role="region" aria-label={t("activity.regionAriaLabel")}>
      <div className="activity-header">
        <h2>{t("activity.heading")}</h2>
        <div className="activity-counts" data-testid="activity-counts">
          <span className="count-chip count-running" title={t("activity.countRunningTitle")}>
            {t("activity.countRunning", { n: counts.running })}
          </span>
          <span className="count-chip count-queued" title={t("activity.countQueuedTitle")}>
            {t("activity.countQueued", { n: counts.queued })}
          </span>
          <span className="count-chip count-done" title={t("activity.countDoneTitle")}>
            {t("activity.countDone", { n: counts.done })}
          </span>
          <span className="count-chip count-failed" title={t("activity.countFailedTitle")}>
            {t("activity.countFailed", { n: counts.failed })}
          </span>
        </div>
        {attentionCount > 0 && (
          <span
            className="attention-chip"
            data-testid="attention-chip"
            title={t("activity.attentionTitle")}
          >
            {t("activity.attentionChip", { n: attentionCount })}
          </span>
        )}
        {stallReason && (
          <span
            className="stall-reason"
            data-testid="stall-reason"
            title={t("activity.stallTitle")}
          >
            {t("activity.stall", { reason: stallLabel(stallReason, t) })}
          </span>
        )}
      </div>

      {awaitingApproval && (
        <div
          className="approval-banner approval-banner-scene"
          data-testid="approval-banner-activity"
          role="alert"
        >
          <span className="approval-banner-text">
            {t("activity.approvalRequired")} <strong>{awaitingApproval}</strong>
          </span>
          {onApprove && (
            <button className="small-btn approve-btn" onClick={onApprove}>
              {t("activity.approve")}
            </button>
          )}
          {onReject && (
            <button className="small-btn danger" onClick={onReject}>
              {t("activity.reject")}
            </button>
          )}
        </div>
      )}

      <div className="activity-body">
        {crew.length > 0 && (
          <div className="crew-rail" data-testid="crew-rail">
            <button
              type="button"
              className="crew-rail-toggle"
              aria-expanded={crewOpen}
              data-testid="crew-rail-toggle"
              onClick={() => setCrewOpen((o) => !o)}
            >
              {crewOpen ? "▾" : "▸"} {t("activity.crewToggle")}
            </button>
            {crewOpen && (
              <div className="crew-rail-list" role="group" aria-label={t("activity.crewFilterAriaLabel")}>
                <button
                  type="button"
                  className={crewFilter === "" ? "active" : ""}
                  aria-pressed={crewFilter === ""}
                  data-testid="crew-all"
                  onClick={() => setCrewFilter("")}
                >
                  {t("activity.crewAll")}
                </button>
                {crew.map(([persona, n]) => (
                  <button
                    key={persona}
                    type="button"
                    className={crewFilter === persona ? "active" : ""}
                    aria-pressed={crewFilter === persona}
                    data-testid={`crew-${persona}`}
                    onClick={() =>
                      setCrewFilter((cur) => (cur === persona ? "" : persona))
                    }
                  >
                    {(PERSONA_META[persona]?.icon ?? "•")}{" "}
                    {PERSONA_META[persona] ? t(PERSONA_META[persona].labelKey) : persona} ({n})
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="activity-rows-wrap">
          {attentionRows.length > 0 && (
            <div
              className="activity-attention-region"
              data-testid="attention-region"
              aria-label={t("activity.attentionRegionAriaLabel")}
            >
              <h3 className="activity-region-title">{t("activity.attentionRegionTitle")}</h3>
              {attentionRows.map(renderRow)}
            </div>
          )}
          <div className="activity-rows" data-testid="activity-rows">
            {visibleRows.length === 0 ? (
              <p className="placeholder">{t("activity.empty")}</p>
            ) : (
              normalRows.map(renderRow)
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
