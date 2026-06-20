// Frontend mirror of the backend work-item graph (orchestrator/streams.py) and
// UserStory.effective_status (models.py). Kept dependency-light and pure so the
// multi-stream Board (ST-12/13/14) can derive effective status, readiness
// ("bloquée par X") and merge state without extra round-trips.

import { Stream, StoryStatus, UserStory } from "./types";

const DONE: StoryStatus = "done";

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
