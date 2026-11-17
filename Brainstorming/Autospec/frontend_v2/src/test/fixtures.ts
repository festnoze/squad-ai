// Realistic API payloads (same shapes as docs/v2/CONTRACTS.md section 9.1).
import type { ProjectDetail, ProjectSummary, Story } from "../api";

export function makeSummary(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    id: "todo-cli",
    name: "Todo CLI",
    profile: "cli",
    phase: "build",
    running: true,
    stories_done: 2,
    stories_total: 5,
    cost_usd: 0.38,
    updated_at: "2026-11-02T18:30:00+00:00",
    error: "",
    resume_at: null,
    ...overrides,
  };
}

export function makeStory(overrides: Partial<Story> = {}): Story {
  return {
    id: "US-1",
    epic_id: "EPIC-1",
    title: "Ajouter une tâche",
    description: "En tant qu'utilisateur, je veux ajouter une tâche.",
    criteria: [
      { id: "US-1.AC-1", text: "add enregistre la tâche" },
      { id: "US-1.AC-2", text: "list affiche la tâche ajoutée" },
    ],
    gherkin: "",
    depends_on: [],
    priority: 1,
    status: "done",
    attempts: 1,
    acceptance_tests: [
      {
        ac_id: "US-1.AC-1",
        nodeids: ["tests/acceptance/test_us_1.py::test_ac1_add", "tests/acceptance/test_us_1.py::test_ac1_add_twice"],
      },
    ],
    test_fingerprint: {},
    dev_session_id: null,
    last_error: "",
    ...overrides,
  };
}

export function makeProject(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  return {
    version: 2,
    id: "todo-cli",
    name: "Todo CLI",
    package: "todo_cli",
    profile: "cli",
    goal: "",
    brief: "# Todo CLI\nUne liste de tâches en ligne de commande.",
    phase: "build",
    epics: [{ id: "EPIC-1", title: "Tâches", description: "" }],
    stories: [
      makeStory(),
      makeStory({
        id: "US-2",
        title: "Terminer une tâche",
        status: "in_progress",
        attempts: 2,
        criteria: [{ id: "US-2.AC-1", text: "done marque la tâche" }],
        acceptance_tests: [],
        depends_on: ["US-1"],
        last_error: "AssertionError: expected 0, got 1",
      }),
    ],
    usage: { calls: 6, cost_usd: 0.62, input_tokens: 1200, output_tokens: 800, duration_ms: 42000 },
    error: "",
    created_at: "2026-11-02T18:00:00+00:00",
    updated_at: "2026-11-02T18:30:00+00:00",
    resume_at: null,
    running: true,
    ...overrides,
  };
}
