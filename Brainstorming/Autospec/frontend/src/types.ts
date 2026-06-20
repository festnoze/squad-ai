export type PipelinePhase =
  | "idle"
  | "spec"
  | "analyze"
  | "architect"
  | "plan"
  | "build"
  | "done"
  | "stopped"
  | "error";

export type StoryStatus =
  | "todo"
  | "in_progress"
  | "red"
  | "green"
  | "done"
  | "failed";

export type ChatRole = "user" | "pm" | "po" | "dev" | "analyst" | "architect" | "qa" | "critic" | "judge" | "system";

export type TestState = "nonexistent" | "red" | "green";

export interface PlannedTest {
  id: string;
  layer: string;
  description: string;
  mocks: string[];
  file_hint: string;
  criteria: string[];
  status: TestState;
}

export interface AcceptanceCriterion {
  id: string;
  text: string;
}

export type HypothesisStatus = "proposed" | "selected" | "done" | "rejected";

export type ComponentStatus = "proposed" | "approved" | "created" | "rejected";

/** Composant technique du produit généré (backend, frontend, BDD…). */
export interface ProductComponent {
  id: string;
  kind: string; // backend | frontend | database | cache | other
  name: string;
  technology: string;
  rationale: string;
  optional: boolean;
  status: ComponentStatus;
}

/** Provider d'agents (M1) : Claude (harness CLI), OpenAI ou Ollama (LangChain). */
export interface ProviderInfo {
  provider: string;
  model: string;
  available: string[];
  /** Suggested model choices per provider, driving the adaptive 2nd dropdown. */
  models: Record<string, string[]>;
}

/** Observation de l'évaluateur de produit (E6). */
export interface Finding {
  id: string;
  severity: string; // low | medium | high
  kind: string; // bug | integration | ux | gap
  title: string;
  detail: string;
  iteration: number;
}

export interface FeatureHypothesis {
  id: string;
  title: string;
  rationale: string;
  value: number;
  complexity: number;
  status: HypothesisStatus;
  rank: number;
}

export interface ChatMessage {
  role: ChatRole;
  content: string;
  ts: number;
}

/** ST-1: a work area's nature — drives the stream badge colour + icon. */
export type StreamKind = "backend" | "frontend" | "cache" | "database" | "other";

/** ST-1: a parallelizable work area with its own toolchain/language/file zone. */
export interface Stream {
  id: string;
  kind: StreamKind;
  language: string;
  toolchain: string;
  file_root: string;
  primary: boolean;
}

/** ST-2: a unit of work within a single stream, below a UserStory. */
export interface Task {
  id: string;
  story_id: string;
  stream: string; // "" = the project's primary/backend stream
  title: string;
  description: string;
  acceptance_criteria: AcceptanceCriterion[];
  gherkin: string;
  depends_on: string[]; // other Task ids (possibly cross-stream)
  status: StoryStatus;
  attempts: number;
  last_error: string;
  files_hint: string[];
}

export interface UserStory {
  id: string;
  epic_id: string;
  title: string;
  description: string;
  acceptance_criteria: AcceptanceCriterion[];
  gherkin: string;
  test_plan: PlannedTest[];
  depends_on: string[];
  priority: number;
  status: StoryStatus;
  iteration: number;
  attempts: number;
  last_error: string;
  quality_score: number;
  mutation_score?: number;
  coverage_score?: number;
  ui?: boolean;
  ui_tests?: string[];
  // ST-2: stream tagging + optional multi-stream decomposition. "" stream means
  // the project's primary/backend stream; non-empty `tasks` make the US a
  // container whose status is derived from its tasks (see `usEffectiveStatus`).
  stream?: string;
  tasks?: Task[];
}

export interface Epic {
  id: string;
  title: string;
  description: string;
  iteration: number;
}

export interface Usage {
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  agent_calls: number;
}

export interface ProjectState {
  id: string;
  name: string;
  goal: string;
  auto_spec: boolean;
  spec_mode: "interview" | "brainstorm";
  phase: PipelinePhase;
  brief: string;
  // B-IDEA: idea-maturity assessment + brainstorming-assist state.
  idea_maturity?: "" | "structured" | "vague";
  idea_rationale?: string;
  brainstorm_techniques?: string[];
  awaiting_brainstorm_decision?: boolean;
  // ST-1: parallelizable work areas chosen by the architect. Empty/absent = one
  // implicit backend stream (legacy / flag-off behaviour, unchanged).
  streams?: Stream[];
  backlog: FeatureHypothesis[];
  components?: ProductComponent[];
  epics: Epic[];
  stories: UserStory[];
  chat: ChatMessage[];
  feedback: string[];
  findings?: Finding[]; // E6 evaluator observations
  lessons?: string[]; // E7 durable retro lessons
  retro_recommendations?: string[]; // E7 tuning advice
  iteration: number;
  running: boolean;
  paused: boolean;
  awaiting_approval?: string;
  regressions?: string[];
  resume_at?: number; // epoch de la reprise auto programmée (0 = aucune) — M2
  error: string;
  created_at: number;
  architecture: string;
  plan_quality: number;
  backend_language?: "python" | "go" | "rust";
  language_complexity?: number;
  language_criticality?: number;
  language_rationale?: string;
  usage: Usage;
  // Per-iteration usage breakdown, keyed by iteration number (as a string in
  // JSON). The global `usage` above stays the project-wide total.
  iteration_usage?: Record<string, Usage>;
  budget_usd: number;
  archived: boolean;
}

export interface LogLine {
  source: string;
  line: string;
}

export type WsEvent =
  | { type: "state"; project_id: string; state: ProjectState }
  | { type: "log"; project_id: string; source: string; line: string }
  | { type: "deleted"; project_id: string }
  | { type: "notify"; project_id: string; level: string; title: string; body: string };

/** Body for editing an existing user story (all fields optional). */
export interface StoryPatch {
  title?: string;
  description?: string;
  gherkin?: string;
  priority?: number;
  acceptance_criteria?: { id?: string; text: string }[];
}

/** Body for creating a new user story under an epic. */
export interface NewStoryBody {
  epic_id: string;
  title: string;
  description?: string;
  gherkin?: string;
  priority?: number;
  acceptance_criteria?: string[];
  depends_on?: string[];
}

/** Listing of generated workspace files (relative POSIX paths, sorted). */
export interface FileListing {
  files: string[];
}

/** Raw content of a generated workspace file. */
export interface FileContent {
  path: string;
  content: string;
  truncated: boolean;
}

/** Diff (git show) du commit « story <id> done ». */
export interface StoryDiff {
  ok: boolean;
  available: boolean;
  diff: string;
}

/** Derived state of a criterion: green only when all its tests are green. */
export function criterionState(
  story: UserStory,
  criterion: AcceptanceCriterion,
): TestState {
  if (story.status === "done") return "green";
  // `?? []` : robustesse face aux anciens états persistés sans ces champs.
  const tests = (story.test_plan ?? []).filter((t) =>
    (t.criteria ?? []).includes(criterion.id),
  );
  if (tests.some((t) => t.status === "red")) return "red";
  if (tests.length > 0 && tests.every((t) => t.status === "green")) return "green";
  return "nonexistent";
}

/**
 * ST-12: derived status of a user story. A taskless US uses its stored `status`;
 * a US decomposed into tasks derives it from its tasks — mirrors the backend
 * `UserStory.effective_status`: all done → done; any active → in_progress; any
 * failed → failed; else todo.
 */
export function usEffectiveStatus(story: UserStory): StoryStatus {
  const tasks = story.tasks ?? [];
  if (tasks.length === 0) return story.status;
  const states = tasks.map((t) => t.status);
  if (states.every((s) => s === "done")) return "done";
  if (states.some((s) => s === "in_progress" || s === "red" || s === "green"))
    return "in_progress";
  if (states.some((s) => s === "failed")) return "failed";
  return "todo";
}

/** Merge-state hint inferred (no new backend field) from status + last_error. */
export type MergeState = "merged" | "conflict" | "none";

/** ST-14: a `done` item is merged ✓; a `failed` whose error mentions a merge
 * conflict is a merge-conflict ✗; otherwise no merge hint. */
export function mergeState(status: StoryStatus, lastError = ""): MergeState {
  if (status === "done") return "merged";
  if (status === "failed" && /conflit de merge|merge conflict/i.test(lastError))
    return "conflict";
  return "none";
}

/**
 * ST-14: the unmet dependency ids holding a `todo` item back — a `depends_on`
 * target that isn't `done`. Computed in the frontend from the statuses of the
 * referenced US/tasks. Depending on a US decomposed into tasks means depending
 * on the whole US (done only when all its tasks are done).
 */
export function blockedBy(
  dependsOn: string[],
  status: StoryStatus,
  stories: UserStory[],
): string[] {
  if (status !== "todo") return [];
  const storyById = new Map(stories.map((s) => [s.id, s]));
  const taskById = new Map<string, Task>();
  for (const s of stories) for (const t of s.tasks ?? []) taskById.set(t.id, t);
  const isDone = (id: string): boolean => {
    const t = taskById.get(id);
    if (t) return t.status === "done";
    const s = storyById.get(id);
    if (s) return usEffectiveStatus(s) === "done";
    return true; // unknown target: don't treat as a blocker
  };
  return (dependsOn ?? []).filter((id) => !isDone(id));
}

export interface Metrics {
  projects: number;
  total_cost_usd: number;
  total_tokens: number;
  total_agent_calls: number;
  total_stories: number;
  stories_done: number;
  stories_failed: number;
  success_rate: number;
  avg_attempts: number;
  cost_per_story: number;
  avg_quality: number | null;
  avg_mutation: number | null;
  avg_coverage: number | null;
  findings: number;
  regressions: number;
}
