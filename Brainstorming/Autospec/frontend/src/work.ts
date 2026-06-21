// Frontend mirror of the backend work-item graph (orchestrator/streams.py) and
// UserStory.effective_status (models.py). Kept dependency-light and pure so the
// multi-stream Board (ST-12/13/14) can derive effective status, readiness
// ("bloquée par X") and merge state without extra round-trips.

import {
  BuildStage,
  GuidanceEntry,
  RecoveryState,
  Stream,
  StoryStatus,
  Task,
  TickItem,
  UserStory,
} from "./types";

const DONE: StoryStatus = "done";

// ---------------------------------------------------------------------------
// B-UX stage tracker helpers (pure, dependency-light, unit-tested in work.test).
// ---------------------------------------------------------------------------

/** The canonical left→right order of BUILD stages shown in the Stepper. The two
 *  terminal stages "done"/"failed" share the last slot (a stepper renders the
 *  reached terminal one). */
export const STAGE_ORDER: BuildStage[] = [
  "queued",
  "analyzing",
  "contracts",
  "implementing",
  "verifying",
  "merge_wait",
  "merging",
  "done",
];

/** Index of a stage in STAGE_ORDER. "failed" maps to the terminal slot (same as
 *  "done"); an unknown/empty stage → 0 (queued). */
export function stageIndex(stage: string): number {
  if (stage === "failed") return STAGE_ORDER.length - 1;
  const i = STAGE_ORDER.indexOf(stage as BuildStage);
  return i < 0 ? 0 : i;
}

/** A stepper cell is "done" when the item's current stage is strictly past it
 *  (or the item itself is done). The terminal "done" cell is done only when the
 *  item actually reached "done". */
export function isStageDone(cell: BuildStage, current: string): boolean {
  if (current === "done") return true;
  if (current === "failed") return false;
  return stageIndex(current) > stageIndex(cell);
}

/** A stepper cell is "active" when it is exactly the item's current stage and the
 *  item is neither done nor failed. */
export function isStageActive(cell: BuildStage, current: string): boolean {
  if (current === "done" || current === "failed") return false;
  return stageIndex(current) === stageIndex(cell) && current === cell;
}

/** Human elapsed label since `startedAt` (epoch seconds) measured at `now`
 *  (epoch ms). "" when never started (0/undefined) or clock skew. */
export function elapsedLabel(startedAt: number | undefined, now: number): string {
  if (!startedAt || startedAt <= 0) return "";
  const secs = Math.floor(now / 1000 - startedAt);
  if (secs < 0) return "";
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m}m ${secs % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** A view of one work item combining persisted fields (story/task in `state`)
 *  with the latest heartbeat `tick`. The tick wins for live BUILD telemetry
 *  (stage/persona/recovery/status); persisted fields are the fallback. */
export interface ItemView {
  id: string;
  kind: "story" | "task";
  status: StoryStatus;
  stage: BuildStage;
  stageStartedAt: number;
  persona: string;
  recovery: RecoveryState;
  guidance: GuidanceEntry[];
  /** true when this view's live data came from a tick (vs. persisted only). */
  fromTick: boolean;
}

const EMPTY_RECOVERY: RecoveryState = { attempt: 0, max_attempts: 0, kind: "" };

/** Combine a persisted story/task with its optional latest tick into one view.
 *  Stage/persona/recovery/status prefer the tick; guidance always from persisted
 *  state (the tick never carries it). */
export function deriveItemView(
  item: UserStory | Task,
  tick?: TickItem,
): ItemView {
  const kind: "story" | "task" = "epic_id" in item ? "story" : "task";
  const persistedStage = (item.current_stage ?? "queued") as BuildStage;
  const persistedRecovery = item.recovery ?? EMPTY_RECOVERY;
  return {
    id: item.id,
    kind,
    status: (tick?.status as StoryStatus) ?? item.status,
    stage: (tick?.current_stage as BuildStage) ?? persistedStage,
    stageStartedAt: tick?.stage_started_at ?? item.stage_started_at ?? 0,
    persona: tick?.current_persona ?? item.current_persona ?? "",
    recovery: tick?.recovery ?? persistedRecovery,
    guidance: item.guidance ?? [],
    fromTick: !!tick,
  };
}

/** Effective status of a US: stored status for a taskless US, else DERIVED from
 *  its tasks (all done → done ; any active → in_progress ; any failed → failed ;
 *  else todo). Mirrors `UserStory.effective_status` on the backend. */
export function effectiveStatus(story: UserStory): StoryStatus {
  const tasks = story.tasks ?? [];
  if (tasks.length === 0) return story.status;
  const states = tasks.map((t) => t.status);
  if (states.every((s) => s === "done")) return "done";
  if (states.some((s) => s === "in_progress" || s === "red" || s === "green"))
    return "in_progress";
  if (states.some((s) => s === "failed")) return "failed";
  return "todo";
}

export interface WorkItem {
  id: string;
  kind: "task" | "story";
  storyId: string;
  stream: string;
  title: string;
  status: StoryStatus;
  dependsOn: string[]; // resolved to other work-item ids
}

/** The id every empty (`""`) stream reference resolves to. */
export function primaryStreamId(streams: Stream[]): string {
  const prim = streams.find((s) => s.primary);
  if (prim) return prim.id;
  const back = streams.find((s) => s.kind === "backend");
  if (back) return back.id;
  return streams[0]?.id ?? "backend";
}

/** Build the work-item graph (mirror of backend `build_work_graph`): a taskless
 *  US is one item; a decomposed US contributes one item per task. US→US deps
 *  expand to all tasks of the depended US; a task inherits its US's deps. */
export function buildWorkGraph(
  stories: UserStory[],
  streams: Stream[],
): Map<string, WorkItem> {
  const primary = primaryStreamId(streams);
  const storyById = new Map(stories.map((s) => [s.id, s]));
  const taskIds = new Set(
    stories.flatMap((s) => (s.tasks ?? []).map((t) => t.id)),
  );
  const items = new Map<string, WorkItem>();

  const resolve = (depIds: string[], owner: string): string[] => {
    const out: string[] = [];
    const seen = new Set<string>();
    for (const dep of depIds) {
      if (dep === owner) continue;
      let targets: string[];
      if (taskIds.has(dep)) targets = [dep];
      else if (storyById.has(dep)) {
        const ds = storyById.get(dep)!;
        const dts = ds.tasks ?? [];
        targets = dts.length ? dts.map((t) => t.id) : [dep];
      } else continue; // unknown dep: dropped (as the backend does)
      for (const t of targets) {
        if (t !== owner && !seen.has(t)) {
          seen.add(t);
          out.push(t);
        }
      }
    }
    return out;
  };

  for (const story of stories) {
    const tasks = story.tasks ?? [];
    if (tasks.length) {
      for (const task of tasks) {
        items.set(task.id, {
          id: task.id,
          kind: "task",
          storyId: story.id,
          stream: task.stream || primary,
          title: task.title || task.id,
          status: task.status,
          dependsOn: resolve(
            [...(task.depends_on ?? []), ...(story.depends_on ?? [])],
            task.id,
          ),
        });
      }
    } else {
      items.set(story.id, {
        id: story.id,
        kind: "story",
        storyId: story.id,
        stream: story.stream || primary,
        title: story.title || story.id,
        status: story.status,
        dependsOn: resolve(story.depends_on ?? [], story.id),
      });
    }
  }
  return items;
}

/** Unmet dependency ids holding a work item back (ST-14). Empty = ready/unblocked. */
export function blockedBy(
  itemId: string,
  items: Map<string, WorkItem>,
): string[] {
  const it = items.get(itemId);
  if (!it) return [];
  return it.dependsOn.filter(
    (d) => items.has(d) && items.get(d)!.status !== DONE,
  );
}

export type MergeState = "merged" | "conflict" | null;

/** Merge state of a work item (ST-14), derived from its status + last error:
 *  a done item is merged; a failed item whose error mentions a merge conflict is
 *  in conflict; otherwise no merge state to show yet. */
export function mergeState(
  status: StoryStatus,
  lastError?: string,
): MergeState {
  if (status === "done") return "merged";
  if (status === "failed" && (lastError ?? "").toLowerCase().includes("merge"))
    return "conflict";
  return null;
}

/** Declared streams, or one implicit backend stream (legacy / flag-off). */
export function effectiveStreams(
  streams: Stream[] | undefined,
  backendLanguage = "python",
): Stream[] {
  if (streams && streams.length) return streams;
  return [
    {
      id: "backend",
      kind: "backend",
      language: backendLanguage,
      toolchain: "",
      file_root: "",
      primary: true,
    },
  ];
}

/** Whether the project has a real multi-stream shape (so the Board shows the
 *  stream UI). Single implicit backend stream + no tasks ⇒ legacy look. */
export function hasMultiStream(
  streams: Stream[] | undefined,
  stories: UserStory[],
): boolean {
  return (
    (streams?.length ?? 0) > 1 ||
    stories.some((s) => (s.tasks ?? []).length > 0)
  );
}

const STREAM_ICON: Record<string, string> = {
  backend: "⚙️",
  frontend: "🎨",
  cache: "⚡",
  database: "🗄️",
  other: "🔧",
};

/** Small emoji for a stream kind (badge prefix). */
export function streamIcon(kind: string): string {
  return STREAM_ICON[kind] ?? STREAM_ICON.other;
}
