import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { RunPanel } from "./RunPanel";
import { PipelinePhase, ProjectState, StoryStatus, Usage, UserStory } from "../types";

// jsdom n'implémente pas Element.scrollIntoView ; RunPanel l'appelle dans un
// useEffect. On le stub pour éviter une erreur d'environnement (pas un bug prod).
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const NEUTRAL_USAGE: Usage = {
  cost_usd: 0,
  input_tokens: 0,
  output_tokens: 0,
  agent_calls: 0,
};

function makeStory(overrides: Partial<UserStory> = {}): UserStory {
  return {
    id: "S1",
    epic_id: "E1",
    title: "Ma story",
    description: "",
    acceptance_criteria: [],
    gherkin: "",
    test_plan: [],
    depends_on: [],
    priority: 3,
    status: "todo" as StoryStatus,
    iteration: 0,
    attempts: 0,
    last_error: "",
    quality_score: 0,
    ...overrides,
  };
}

function makeProject(overrides: Partial<ProjectState> = {}): ProjectState {
  return {
    id: "p1",
    name: "Projet test",
    goal: "",
    auto_spec: false,
    spec_mode: "interview",
    phase: "done" as PipelinePhase,
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

function renderPanel(project: ProjectState) {
  return render(
    <RunPanel
      project={project}
      logs={[]}
      onRun={vi.fn()}
      onStop={vi.fn()}
      onPause={vi.fn()}
      onResume={vi.fn()}
      onStopApp={vi.fn()}
      onResumeBuild={vi.fn()}
    />,
  );
}

describe("RunPanel", () => {
  it("phase 'done' : bouton « Lancer » activé, pas de bouton « Stopper »", () => {
    renderPanel(makeProject({ phase: "done" }));
    const run = screen.getByRole("button", { name: "▶ Lancer le projet" });
    expect(run).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "⏹ Stopper" }),
    ).not.toBeInTheDocument();
  });

  it("phase 'build' : bouton « Stopper » présent", () => {
    renderPanel(makeProject({ phase: "build" }));
    expect(
      screen.getByRole("button", { name: "⏹ Stopper" }),
    ).toBeInTheDocument();
  });

  it("phase 'spec' : bouton « Lancer » désactivé (canRun faux)", () => {
    // canRun exclut spec/plan/analyze/architect/idle. La phase « build » N'EST
    // PAS exclue, donc le bouton y reste actif : on teste donc « spec ».
    renderPanel(makeProject({ phase: "spec" }));
    expect(
      screen.getByRole("button", { name: "▶ Lancer le projet" }),
    ).toBeDisabled();
  });

  it("paused=true (phase build) : bouton « Reprendre » présent, pas « Pause »", () => {
    renderPanel(makeProject({ phase: "build", paused: true }));
    expect(
      screen.getByRole("button", { name: "▶ Reprendre" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "⏸ Pause" }),
    ).not.toBeInTheDocument();
  });

  it("running=true : bouton « Arrêter l'app » présent, libellé primaire « En cours… »", () => {
    renderPanel(makeProject({ phase: "build", running: true }));
    expect(
      screen.getByRole("button", { name: "■ Arrêter l'app" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "▶ En cours…" }),
    ).toBeInTheDocument();
  });

  it("phase 'stopped' avec story 'todo' : bouton « Continuer le build » présent", () => {
    renderPanel(
      makeProject({ phase: "stopped", stories: [makeStory({ status: "todo" })] }),
    );
    expect(
      screen.getByRole("button", { name: "▶ Continuer le build" }),
    ).toBeInTheDocument();
  });

  it("phase 'stopped' sans story todo/red : pas de bouton « Continuer le build »", () => {
    renderPanel(
      makeProject({ phase: "stopped", stories: [makeStory({ status: "done" })] }),
    );
    expect(
      screen.queryByRole("button", { name: "▶ Continuer le build" }),
    ).not.toBeInTheDocument();
  });

  it("usage-meter visible quand agent_calls > 0", () => {
    const { container } = renderPanel(
      makeProject({ usage: { ...NEUTRAL_USAGE, agent_calls: 3 } }),
    );
    expect(container.querySelector(".usage-meter")).not.toBeNull();
  });

  it("usage-meter absent quand agent_calls = 0", () => {
    const { container } = renderPanel(
      makeProject({ usage: { ...NEUTRAL_USAGE, agent_calls: 0 } }),
    );
    expect(container.querySelector(".usage-meter")).toBeNull();
  });
});
