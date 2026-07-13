import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PipelinePhase, ProjectState, Usage, WsEvent } from "./types";

// --- Mock du module ./api ---------------------------------------------------
// On capture le callback `onEvent` passé à connectEvents pour pouvoir émettre
// des évènements WebSocket depuis les tests.
let capturedOnEvent: ((e: WsEvent) => void) | null = null;
const cleanup = vi.fn();

vi.mock("./api", () => ({
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
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
  getProvider: vi
    .fn()
    .mockResolvedValue({
      provider: "claude",
      model: "(défaut CLI)",
      available: ["claude", "openai", "ollama"],
      models: {
        claude: ["opus", "sonnet", "haiku"],
        openai: ["gpt-4.1", "gpt-5.4"],
        ollama: ["llama3.1"],
      },
    }),
  setProvider: vi.fn().mockResolvedValue({ ok: true, provider: "claude", model: "" }),
  updateComponents: vi.fn().mockResolvedValue(undefined),
  setupComponents: vi.fn().mockResolvedValue(undefined),
  documentProject: vi.fn().mockResolvedValue(undefined),
  cancelResume: vi.fn().mockResolvedValue(undefined),
  gitExportProject: vi.fn().mockResolvedValue({ commit: "abc" }),
  exportZipUrl: (id: string) => `/api/projects/${id}/export`,
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
    spec_mode: "interview",
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
    budget_usd: 0,
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
  // UI3 : un projet idle/dormant figure dans le sélecteur 🗂 (option), pas
  // forcément en chip — on l'y cherche donc par son option.
  const findProjectOption = (re: RegExp) => screen.findByRole("option", { name: re });
  const queryProjectOption = (re: RegExp) => screen.queryByRole("option", { name: re });

  it("un event 'state' fait apparaître le projet (dans le sélecteur)", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject() });

    expect(await findProjectOption(/Projet Alpha/)).toBeInTheDocument();
  });

  it("un second 'state' pour le même id met à jour sans dupliquer (upsert)", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject() });
    await findProjectOption(/Projet Alpha/);

    emit({
      type: "state",
      project_id: "p1",
      state: makeProject({ name: "Projet Renommé" }),
    });

    expect(await findProjectOption(/Projet Renommé/)).toBeInTheDocument();
    expect(queryProjectOption(/Projet Alpha/)).not.toBeInTheDocument();
    expect(screen.queryAllByRole("option", { name: /Projet Renommé/ })).toHaveLength(1);
  });

  it("un event 'deleted' fait disparaître le projet", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject() });
    await findProjectOption(/Projet Alpha/);

    emit({ type: "deleted", project_id: "p1" });

    await waitFor(() => expect(queryProjectOption(/Projet Alpha/)).not.toBeInTheDocument());
  });

  it("anti-résurrection : un 'state' retardé après 'deleted' ne ressuscite pas le projet", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject() });
    await findProjectOption(/Projet Alpha/);

    emit({ type: "deleted", project_id: "p1" });
    await waitFor(() => expect(queryProjectOption(/Projet Alpha/)).not.toBeInTheDocument());

    // Event « state » retardé pour le même id : doit être ignoré.
    emit({ type: "state", project_id: "p1", state: makeProject() });

    // On laisse le temps à un éventuel re-render fautif de se produire.
    await Promise.resolve();
    expect(queryProjectOption(/Projet Alpha/)).not.toBeInTheDocument();
  });

  it("un event 'tick' n'écrase pas l'état projet (titre conservé)", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({ type: "state", project_id: "p1", state: makeProject({ name: "Projet Tick" }) });
    await findProjectOption(/Projet Tick/);

    // Un tick item-level arrive : il ne doit pas remplacer l'état complet.
    emit({
      type: "tick",
      project_id: "p1",
      ts: 123,
      items: [
        {
          id: "US-1",
          kind: "story",
          status: "in_progress",
          current_stage: "implementing",
          stage_started_at: 100,
          current_persona: "dev",
          recovery: { attempt: 0, max_attempts: 0, kind: "" },
        },
      ],
      counts: { running: 1, queued: 0, done: 0, failed: 0, blocked: 0 },
      stall_reason: "",
    });

    await Promise.resolve();
    expect(await findProjectOption(/Projet Tick/)).toBeInTheDocument();
  });

  it("un 'tick' pour un projet inconnu ne crée pas de projet fantôme", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({
      type: "tick",
      project_id: "ghost",
      ts: 1,
      items: [],
      counts: { running: 0, queued: 0, done: 0, failed: 0, blocked: 0 },
      stall_reason: "",
    });

    await Promise.resolve();
    expect(queryProjectOption(/Projet/)).not.toBeInTheDocument();
  });

  it("un event 'governance_decision' alimente le badge ⚖ en live (US-F7.5)", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    // Projet actif (chip rendue) sans décision : pas de badge.
    emit({ type: "state", project_id: "p1", state: makeProject({ phase: "build" }) });
    await findProjectOption(/Projet Alpha/);
    expect(document.body.querySelector(".chip-approvals")).toBeNull();

    emit({
      type: "governance_decision",
      project_id: "p1",
      decision: {
        id: "GOV-1",
        observation_id: "OBS-1",
        action: "create_story",
        target_id: "",
        payload: {},
        rationale: "",
        status: "proposed",
        iteration: 1,
      },
    });
    expect(await screen.findByText("⚖ 1")).toBeInTheDocument();

    // La même décision passe « applied » (upsert par id) : badge retiré.
    emit({
      type: "governance_decision",
      project_id: "p1",
      decision: {
        id: "GOV-1",
        observation_id: "OBS-1",
        action: "create_story",
        target_id: "",
        payload: {},
        rationale: "",
        status: "applied",
        iteration: 1,
      },
    });
    await waitFor(() =>
      expect(document.body.querySelector(".chip-approvals")).toBeNull(),
    );
  });

  it("un 'governance_decision' pour un projet inconnu est ignoré (pas de fantôme)", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());
    emit({
      type: "governance_decision",
      project_id: "ghost",
      decision: {
        id: "GOV-1",
        observation_id: "OBS-1",
        action: "dismiss",
        target_id: "",
        payload: {},
        rationale: "",
        status: "proposed",
        iteration: 1,
      },
    });
    await Promise.resolve();
    expect(queryProjectOption(/Projet/)).not.toBeInTheDocument();
  });

  it("un event 'notify' affiche un toast (U3)", async () => {
    render(<App />);
    await waitFor(() => expect(capturedOnEvent).not.toBeNull());

    emit({
      type: "notify",
      project_id: "p1",
      level: "success",
      title: "Itération terminée",
      body: "Projet Alpha",
    });

    expect(await screen.findByText("Itération terminée")).toBeInTheDocument();
  });
});

describe("App — popup de création au démarrage", () => {
  it("la popup s'ouvre sans projet mais reste FERMABLE (pas de création forcée)", async () => {
    // listProjects (mock) renvoie [] → accueil sans projet : la popup s'ouvre.
    render(<App />);
    const close = await screen.findByRole("button", {
      name: /Close project creation/,
    });

    fireEvent.click(close);

    // Popup fermée : le formulaire disparaît, l'accueil explique comment la
    // rouvrir, et le bouton « ＋ New » de la barre reste disponible.
    expect(
      screen.queryByRole("button", { name: /Close project creation/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/create one with/)).toBeInTheDocument();

    // Ré-ouverture à la demande depuis la barre de projets.
    fireEvent.click(screen.getByRole("button", { name: /New/ }));
    expect(
      await screen.findByRole("button", { name: /Close project creation/ }),
    ).toBeInTheDocument();
  });
});
