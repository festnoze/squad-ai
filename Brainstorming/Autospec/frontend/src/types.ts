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
  ui?: boolean;
  ui_tests?: string[];
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
  backlog: FeatureHypothesis[];
  components?: ProductComponent[];
  epics: Epic[];
  stories: UserStory[];
  chat: ChatMessage[];
  feedback: string[];
  iteration: number;
  running: boolean;
  paused: boolean;
  error: string;
  created_at: number;
  architecture: string;
  plan_quality: number;
  usage: Usage;
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
  | { type: "deleted"; project_id: string };

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
