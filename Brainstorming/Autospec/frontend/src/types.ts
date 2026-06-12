export type PipelinePhase =
  | "idle"
  | "spec"
  | "analyze"
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

export type ChatRole = "user" | "pm" | "po" | "dev" | "analyst" | "qa" | "system";

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
}

export interface Epic {
  id: string;
  title: string;
  description: string;
  iteration: number;
}

export interface ProjectState {
  id: string;
  name: string;
  goal: string;
  auto_spec: boolean;
  phase: PipelinePhase;
  brief: string;
  backlog: FeatureHypothesis[];
  epics: Epic[];
  stories: UserStory[];
  chat: ChatMessage[];
  feedback: string[];
  iteration: number;
  running: boolean;
  error: string;
  created_at: number;
}

export interface LogLine {
  source: string;
  line: string;
}

export type WsEvent =
  | { type: "state"; project_id: string; state: ProjectState }
  | { type: "log"; project_id: string; source: string; line: string }
  | { type: "deleted"; project_id: string };

/** Derived state of a criterion: green only when all its tests are green. */
export function criterionState(
  story: UserStory,
  criterion: AcceptanceCriterion,
): TestState {
  if (story.status === "done") return "green";
  const tests = story.test_plan.filter((t) => t.criteria.includes(criterion.id));
  if (tests.some((t) => t.status === "red")) return "red";
  if (tests.length > 0 && tests.every((t) => t.status === "green")) return "green";
  return "nonexistent";
}
