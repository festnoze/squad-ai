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
  const onSelect = handlers.onSelect ?? vi.fn();
  render(
    <ProjectBar
      projects={projects}
      selectedId={handlers.selectedId ?? null}
      onSelect={onSelect}
      onNew={vi.fn()}
      onDelete={vi.fn()}
      showArchived={handlers.showArchived ?? false}
      onToggleArchived={vi.fn()}
      onArchive={vi.fn()}
      onUnarchive={vi.fn()}
      onPlay={onPlay}
      onStop={onStop}
    />,
  );
  return { onPlay, onStop, onSelect };
}

describe("ProjectBar — surveillance multi-projets (U1)", () => {
  it("projet en build : indicateur pulsant + bouton ⏹ qui stoppe", () => {
    const { onStop, onPlay } = renderBar([makeProject({ phase: "build" })]);
    const { container } = { container: document.body };
    expect(container.querySelector(".dot.pulse")).not.toBeNull();
    const stop = screen.getByTitle("Stop this project's pipeline");
    fireEvent.click(stop);
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(onPlay).not.toHaveBeenCalled();
  });

  it("projet stoppé avec stories restantes : bouton ▶ qui relance le build", () => {
    // UI3 : un projet dormant n'est une chip que s'il est sélectionné.
    const { onPlay } = renderBar(
      [makeProject({ id: "p1", phase: "stopped", stories: [makeStory("todo")] })],
      { selectedId: "p1" },
    );
    fireEvent.click(screen.getByTitle("Resume building the remaining stories"));
    expect(onPlay).toHaveBeenCalledTimes(1);
  });

  it("projet en pause : ▶ reprend, pas de pulse", () => {
    const { onPlay } = renderBar([makeProject({ phase: "build", paused: true })]);
    expect(document.body.querySelector(".dot.pulse")).toBeNull();
    fireEvent.click(screen.getByTitle("Resume the pipeline"));
    expect(onPlay).toHaveBeenCalledTimes(1);
  });

  it("projet terminé sans story restante : ni ▶ ni ⏹, progression visible", () => {
    renderBar([makeProject({ id: "p1", phase: "done", stories: [makeStory("done")] })], {
      selectedId: "p1",
    });
    expect(screen.queryByTitle(/Stop this project's pipeline/)).toBeNull();
    expect(screen.queryByTitle(/Resume/)).toBeNull();
    expect(screen.getByText("1/1")).toBeInTheDocument();
  });

  it("UI3 : projets inactifs masqués des chips, indiqués « +N dans 🗂 »", () => {
    renderBar([
      makeProject({ id: "p1", name: "Actif", phase: "build" }),
      makeProject({ id: "p2", name: "Fini1", phase: "done" }),
      makeProject({ id: "p3", name: "Fini2", phase: "stopped" }),
    ]);
    // Seule la chip active est rendue ; les 2 inactives sont dans le sélecteur.
    expect(document.body.querySelectorAll(".project-chip")).toHaveLength(1);
    expect(screen.getByText("+2 in 🗂")).toBeInTheDocument();
    // …mais toutes figurent dans le sélecteur.
    expect(screen.getByRole("option", { name: /Fini1/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Fini2/ })).toBeInTheDocument();
  });

  it("plusieurs projets actifs en parallèle : chaque chip a son état", () => {
    renderBar([
      makeProject({ id: "p1", name: "Alpha", phase: "build" }),
      makeProject({ id: "p2", name: "Beta", phase: "spec" }),
      makeProject({ id: "p3", name: "Gamma", phase: "done" }),
    ]);
    expect(document.body.querySelectorAll(".dot.pulse")).toHaveLength(2);
    expect(screen.getAllByTitle("Stop this project's pipeline")).toHaveLength(2);
  });
});

describe("ProjectBar — sélecteur de projet", () => {
  it("liste tous les projets et reflète le projet courant", () => {
    renderBar(
      [
        makeProject({ id: "p1", name: "Alpha", phase: "build", stories: [makeStory("todo")] }),
        makeProject({ id: "p2", name: "Beta", phase: "done" }),
      ],
      { selectedId: "p2" },
    );
    const select = screen.getByLabelText("Select the active project") as HTMLSelectElement;
    expect(select.value).toBe("p2");
    expect(screen.getByRole("option", { name: /Alpha/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Beta/ })).toBeInTheDocument();
  });

  it("changer la sélection appelle onSelect avec l'id choisi", () => {
    const { onSelect } = renderBar(
      [
        makeProject({ id: "p1", name: "Alpha" }),
        makeProject({ id: "p2", name: "Beta" }),
      ],
      { selectedId: "p1" },
    );
    fireEvent.change(screen.getByLabelText("Select the active project"), {
      target: { value: "p2" },
    });
    expect(onSelect).toHaveBeenCalledWith("p2");
  });

  it("inclut le projet courant même s'il est archivé et les archivés masqués", () => {
    renderBar(
      [
        makeProject({ id: "p1", name: "Alpha" }),
        makeProject({ id: "p2", name: "ArchivedOne", archived: true }),
      ],
      { selectedId: "p2", showArchived: false },
    );
    const select = screen.getByLabelText("Select the active project") as HTMLSelectElement;
    expect(select.value).toBe("p2");
    expect(screen.getByRole("option", { name: /ArchivedOne/ })).toBeInTheDocument();
  });
});
