// Typed client of the Autospec v2 HTTP API (docs/v2/CONTRACTS.md section 9.1).
// Field names mirror backend/autospec/core/models.py exactly.

export const API_BASE = "/api/v2";

export type Profile = "lib" | "cli" | "api" | "fullstack";

export type Phase =
  | "created"
  | "brief"
  | "plan"
  | "build"
  | "deliver"
  | "done"
  | "needs_attention"
  | "stopped"
  | "error";

export type StoryStatus = "todo" | "in_progress" | "done" | "failed";

export interface ProjectSummary {
  id: string;
  name: string;
  profile: Profile | null;
  phase: Phase;
  running: boolean;
  stories_done: number;
  stories_total: number;
  cost_usd: number;
  updated_at: string;
  error: string;
  /** Epoch seconds of the automatic resume, null when none is planned. */
  resume_at: number | null;
}

export interface AcceptanceCriterion {
  id: string; // qualified, e.g. "US-1.AC-2"
  text: string;
}

export interface AcceptanceTest {
  ac_id: string;
  nodeids: string[];
}

export interface Epic {
  id: string;
  title: string;
  description: string;
}

export interface Story {
  id: string;
  epic_id: string;
  title: string;
  description: string;
  criteria: AcceptanceCriterion[];
  gherkin: string;
  depends_on: string[];
  priority: number;
  status: StoryStatus;
  attempts: number;
  acceptance_tests: AcceptanceTest[];
  test_fingerprint: Record<string, string>;
  dev_session_id: string | null;
  last_error: string;
}

export interface Usage {
  calls: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  duration_ms: number;
}

export interface ProjectState {
  version: number;
  id: string;
  name: string;
  package: string;
  profile: Profile | null;
  goal: string;
  brief: string;
  phase: Phase;
  epics: Epic[];
  stories: Story[];
  usage: Usage;
  error: string;
  created_at: string;
  updated_at: string;
  /** Agent model chosen at creation ("" = the factory default). */
  model?: string;
  /** Epoch seconds of the automatic resume of a run parked by the provider, null when none. */
  resume_at?: number | null;
}

/** GET /projects/{id}: the full state plus whether a run is in progress. */
export interface ProjectDetail extends ProjectState {
  running: boolean;
}

export interface CreateProjectBody {
  name: string;
  package?: string;
  profile?: Profile;
  brief?: string;
  goal?: string;
  model?: string;
}

/** One line of events.jsonl: {"ts", "type", ...data}. */
export interface ProjectEvent {
  ts?: string;
  type: string;
  [field: string]: unknown;
}

export interface EventsPage {
  events: ProjectEvent[];
  next: number;
}

export interface FileContent {
  path: string;
  content: string;
  truncated: boolean;
}

export interface StoryDiff {
  available: boolean;
  diff: string;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{"loc": [...], "msg": "..."}]
    const messages = detail.map((item) => (item as { msg?: unknown })?.msg).filter(Boolean);
    if (messages.length) return messages.join(" ; ");
  }
  return `Erreur HTTP ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, body));
  return body as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method: "POST" };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  return request<T>(path, init);
}

const project = (id: string) => `/projects/${encodeURIComponent(id)}`;

export const health = () => request<{ status: string }>("/health");

export const listProjects = () => request<ProjectSummary[]>("/projects");

export const createProject = (body: CreateProjectBody) => post<ProjectSummary>("/projects", body);

export const getProject = (id: string) => request<ProjectDetail>(project(id));

export const resumeProject = (id: string) => post<{ ok: boolean }>(`${project(id)}/resume`);

export const stopProject = (id: string) => post<{ ok: boolean }>(`${project(id)}/stop`);

export const deleteProject = (id: string) => request<void>(project(id), { method: "DELETE" });

/** Events from index `after` on (after=0 returns the whole journal); pass `next` back. */
export const getEvents = (id: string, after: number) =>
  request<EventsPage>(`${project(id)}/events?after=${after}`);

export const listFiles = (id: string) => request<{ files: string[] }>(`${project(id)}/files`);

export const readFile = (id: string, path: string) =>
  request<FileContent>(`${project(id)}/files/raw?path=${encodeURIComponent(path)}`);

export const getStoryDiff = (id: string, storyId: string) =>
  request<StoryDiff>(`${project(id)}/stories/${encodeURIComponent(storyId)}/diff`);

/**
 * URL of the server-sent events stream (one `data: <event json>` per event, `id:` = index).
 * `after` skips the events already received when a stream is reopened; a server that
 * ignores it replays from 0 and the client drops the indexes it already has.
 */
export const streamUrl = (id: string, after = 0) =>
  `${API_BASE}${project(id)}/stream${after > 0 ? `?after=${after}` : ""}`;
