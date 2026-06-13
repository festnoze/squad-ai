import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProjectBar } from "./ProjectBar";
import { PipelinePhase, ProjectState, StoryStatus, Usage, UserStory } from "../types";

const NEUTRAL_USAGE: Usage = {
  cost_usd: 0,
  input_tokens: 0,
  output_tokens: 0,
  agent_calls: 0,
};

function makeStory(status: StoryStatus): UserStory {
  return {
    id: "S1",
    epic_id: "E1",
    title: "Story",
    description: "",
    acceptance_criteria: [],
    gherkin: "",
    test_plan: [],
    depends_on: [],
    priority: 3,
    status,
    iteration: 0,
    attempts: 0,
    last_error: "",
    quality_score: 0,
  };
}

function makeProject(overrides: Partial<ProjectState> = {}): ProjectState {
  return {
    id: "p1",
    name: "Alpha",
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
    budget_usd: 0,
    archived: false,
    ...overrides,
  };
}

function renderBar(projects: ProjectState[], handlers: Partial<Record<string, any>> = {}) {
  const onPlay = handlers.onPlay ?? vi.fn();
  const onStop = handlers.onStop ?? vi.fn();
  render(
    <ProjectBar
      projects={projects}
      selectedId={null}
      onSelect={vi.fn()}
      onNew={vi.fn()}
      onDelete={vi.fn()}
      showArchived={false}
      onToggleArchived={vi.fn()}
      onArchive={vi.fn()}
      onUnarchive={vi.fn()}
      onPlay={onPlay}
      onStop={onStop}
    />,
  );
  return { onPlay, onStop };
}

describe("ProjectBar — surveillance multi-projets (U1)", () => {
  it("projet en build : indicateur pulsant + bouton ⏹ qui stoppe", () => {
    const { onStop, onPlay } = renderBar([makeProject({ phase: "build" })]);
    const { container } = { container: document.body };
    expect(container.querySelector(".dot.pulse")).not.toBeNull();
    const stop = screen.getByTitle("Stopper la pipeline de ce projet");
    fireEvent.click(stop);
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(onPlay).not.toHaveBeenCalled();
  });

  it("projet stoppé avec stories restantes : bouton ▶ qui relance le build", () => {
    const { onPlay } = renderBar([
      makeProject({ phase: "stopped", stories: [makeStory("todo")] }),
    ]);
    fireEvent.click(screen.getByTitle("Reprendre le build des stories restantes"));
    expect(onPlay).toHaveBeenCalledTimes(1);
  });

  it("projet en pause : ▶ reprend, pas de pulse", () => {
    const { onPlay } = renderBar([makeProject({ phase: "build", paused: true })]);
    expect(document.body.querySelector(".dot.pulse")).toBeNull();
    fireEvent.click(screen.getByTitle("Reprendre la pipeline"));
    expect(onPlay).toHaveBeenCalledTimes(1);
  });

  it("projet terminé sans story restante : ni ▶ ni ⏹, progression visible", () => {
    renderBar([makeProject({ phase: "done", stories: [makeStory("done")] })]);
    expect(screen.queryByTitle(/Stopper la pipeline/)).toBeNull();
    expect(screen.queryByTitle(/Reprendre/)).toBeNull();
    expect(screen.getByText("1/1")).toBeInTheDocument();
  });

  it("plusieurs projets actifs en parallèle : chaque chip a son état", () => {
    renderBar([
      makeProject({ id: "p1", name: "Alpha", phase: "build" }),
      makeProject({ id: "p2", name: "Beta", phase: "spec" }),
      makeProject({ id: "p3", name: "Gamma", phase: "done" }),
    ]);
    expect(document.body.querySelectorAll(".dot.pulse")).toHaveLength(2);
    expect(screen.getAllByTitle("Stopper la pipeline de ce projet")).toHaveLength(2);
  });
});
