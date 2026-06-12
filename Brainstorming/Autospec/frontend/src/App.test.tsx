import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PipelinePhase, ProjectState, Usage, WsEvent } from "./types";

// --- Mock du module ./api ---------------------------------------------------
// On capture le callback `onEvent` passé à connectEvents pour pouvoir émettre
// des évènements WebSocket depuis les tests.
let capturedOnEvent: ((e: WsEvent) => void) | null = null;
const cleanup = vi.fn();

vi.mock("./api", () => ({
  listProjects: vi.fn().mockResolvedValue([]),
  connectEvents: vi.fn((onEvent: (e: WsEvent) => void) => {
    capturedOnEvent = onEvent;
    return cleanup;
  }),
  createProject: vi.fn().mockResolvedValue({ id: "x", state: {} }),
  deleteProject: vi.fn().mockResolvedValue(undefined),
  archiveProject: vi.fn().mockResolvedValue(undefined),
  unarchiveProject: vi.fn().mockResolvedValue(undefined),
  pauseProject: vi.fn().mockResolvedValue(undefined),
  resumeProject: vi.fn().mockResolvedValue(undefined),
  runProject: vi.fn().mockResolvedValue(undefined),
  stopProject: vi.fn().mockResolvedValue(undefined),
  stopApp: vi.fn().mockResolvedValue(undefined),
  resumeBuild: vi.fn().mockResolvedValue(undefined),
  sendChat: vi.fn().mockResolvedValue(undefined),
}));

// Import APRÈS le vi.mock pour que App consomme la version mockée.
import App from "./App";

const NEUTRAL_USAGE: Usage = {
  cost_usd: 0,
  input_tokens: 0,
  output_tokens: 0,
  agent_calls: 0,
};

function makeProject(overrides: Partial<ProjectState> = {}): ProjectState {
  return {
    id: "p1",
    name: "Projet Alpha",
    goal: "",
    auto_spec: false,
    phase: "idle" as PipelinePhase,
    brief: "",
    backlog: [],
    epics: [],
    stories: [],
    chat: [],
    feedback: [],
    iteration: 0,
    running: false,
    paused: false,
    error: "",
    created_at: 0,
    architecture: "",
    plan_quality: 0,
    usage: { ...NEUTRAL_USAGE },
    archived: false,
    ...overrides,
  };
}

function emit(event: WsEvent) {
  act(() => {
    capturedOnEvent?.(event);
  });
}

beforeEach(() => {
  capturedOnEvent = null;
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("App — gestion des évènements WebSocket", () => {
  it("un event 'state' fait apparaître le projet (nom dans la ProjectBar)", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject() });

    expect(await screen.findByText("Projet Alpha")).toBeInTheDocument();
  });

  it("un second 'state' pour le même id met à jour sans dupliquer (upsert)", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject() });
    await screen.findByText("Projet Alpha");

    emit({
      type: "state",
      project_id: "p1",
      state: makeProject({ name: "Projet Renommé" }),
    });

    expect(await screen.findByText("Projet Renommé")).toBeInTheDocument();
    expect(screen.queryByText("Projet Alpha")).not.toBeInTheDocument();
    expect(screen.queryAllByText("Projet Renommé")).toHaveLength(1);
  });

  it("un event 'deleted' fait disparaître le projet", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject() });
    await screen.findByText("Projet Alpha");

    emit({ type: "deleted", project_id: "p1" });

    await waitFor(() =>
      expect(screen.queryByText("Projet Alpha")).not.toBeInTheDocument(),
    );
  });

  it("anti-résurrection : un 'state' retardé après 'deleted' ne ressuscite pas le projet", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject() });
    await screen.findByText("Projet Alpha");

    emit({ type: "deleted", project_id: "p1" });
    await waitFor(() =>
      expect(screen.queryByText("Projet Alpha")).not.toBeInTheDocument(),
    );

    // Event « state » retardé pour le même id : doit être ignoré.
    emit({ type: "state", project_id: "p1", state: makeProject() });

    // On laisse le temps à un éventuel re-render fautif de se produire.
    await Promise.resolve();
    expect(screen.queryByText("Projet Alpha")).not.toBeInTheDocument();
  });
});
