import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { RunPanel } from "./RunPanel";
import { PipelinePhase, ProjectState, StoryStatus, Task, Usage, UserStory } from "../types";

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

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: "T1",
    story_id: "S1",
    stream: "",
    title: "Ma tâche",
    description: "",
    acceptance_criteria: [],
    gherkin: "",
    depends_on: [],
    status: "todo" as StoryStatus,
    attempts: 0,
    last_error: "",
    files_hint: [],
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
    budget_usd: 0,
    archived: false,
    ...overrides,
  };
}

function renderPanel(
  project: ProjectState,
  logs: { projectId: string; source: string; line: string }[] = [],
  onRetryFailed: () => void = vi.fn(),
  onRun: (args: string) => void = vi.fn(),
) {
  const utils = render(
    <RunPanel
      project={project}
      logs={logs}
      onRun={onRun}
      onStop={vi.fn()}
      onPause={vi.fn()}
      onResume={vi.fn()}
      onStopApp={vi.fn()}
      onResumeBuild={vi.fn()}
      onRetryFailed={onRetryFailed}
      onDocument={vi.fn()}
      onExportZip={vi.fn()}
      onGitExport={vi.fn()}
      onCancelResume={vi.fn()}
      onApprove={vi.fn()}
      onReject={vi.fn()}
      onDeploy={vi.fn()}
    />,
  );
  return { ...utils, onRetryFailed, onRun };
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

  it("BUG3 : phase 'stopped' avec US multi-stream à moitié faite (tasks [done, todo], status brut 'done') : bouton « Continuer le build » présent", () => {
    // Statut stocké = 'done' (pas todo/red), mais effective_status = todo car une
    // tâche reste à faire : le bouton doit s'afficher (gating sur statut effectif).
    renderPanel(
      makeProject({
        phase: "stopped",
        stories: [
          makeStory({
            status: "done",
            tasks: [
              makeTask({ id: "T1", status: "done" }),
              makeTask({ id: "T2", status: "todo" }),
            ],
          }),
        ],
      }),
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

  it("resume_at > 0 : bannière de reprise auto + bouton annuler (M2)", () => {
    const { container } = renderPanel(
      makeProject({ phase: "stopped", resume_at: Date.now() / 1000 + 3600 }),
    );
    expect(container.querySelector(".resume-banner")).not.toBeNull();
    expect(screen.getByText(/Reprise auto à/)).toBeInTheDocument();
    expect(
      screen.getByTitle("Annuler la reprise automatique"),
    ).toBeInTheDocument();
  });

  it("resume_at absent : pas de bannière de reprise", () => {
    const { container } = renderPanel(makeProject({ phase: "stopped" }));
    expect(container.querySelector(".resume-banner")).toBeNull();
  });

  it("UI4 : sans logs, le panneau est replié et n'affiche pas la boîte de logs", () => {
    const { container } = renderPanel(makeProject());
    expect(container.querySelector(".run")?.className).toMatch(/run-collapsed/);
    expect(container.querySelector(".logs")).toBeNull();
    expect(screen.getByText(/aucun pour l'instant/i)).toBeInTheDocument();
  });

  it("UI4 : avec des logs, la boîte s'affiche + compteur, panneau non replié", () => {
    const { container } = renderPanel(makeProject(), [
      { projectId: "p1", source: "dev:US-1", line: "build ok" },
    ]);
    expect(container.querySelector(".run")?.className).not.toMatch(/run-collapsed/);
    expect(container.querySelector(".logs")).not.toBeNull();
    expect(screen.getByText("build ok")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Logs \(1\)/ })).toBeInTheDocument();
  });

  it("UI7 : actions de livraison repliées dans un menu ⋯, déployées au clic", () => {
    renderPanel(makeProject({ phase: "done" }));
    // Les actions post-build ne sont pas des boutons inline.
    expect(screen.queryByRole("button", { name: /Doc \(README\)/ })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: /⋯ Livraison/ });
    fireEvent.click(trigger);
    expect(screen.getByRole("menuitem", { name: /Doc \(README\)/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Exporter en zip/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Déploiement/ })).toBeInTheDocument();
  });

  it("UI7 : pas de menu Livraison tant qu'aucun build n'existe (phase build)", () => {
    renderPanel(makeProject({ phase: "build" }));
    expect(screen.queryByRole("button", { name: /⋯ Livraison/ })).not.toBeInTheDocument();
  });

  it("retry-failed : bouton « Relancer les échecs (N) » + clic, quand dormant", () => {
    const { onRetryFailed } = renderPanel(
      makeProject({
        phase: "stopped",
        stories: [makeStory({ status: "failed" }), makeStory({ id: "S2", status: "done" })],
      }),
    );
    const btn = screen.getByRole("button", { name: /Relancer les échecs \(1\)/ });
    fireEvent.click(btn);
    expect(onRetryFailed).toHaveBeenCalledTimes(1);
  });

  it("BUG5 : retry-failed compte le statut EFFECTIF (US multi-stream tasks [failed, done], status brut 'todo') : « Relancer les échecs (1) »", () => {
    // Statut stocké = 'todo' mais effective_status = failed (une tâche failed, aucune
    // active) : le compteur doit s'aligner sur le backend (aretry_failed agit sur
    // effective_status), comme canResumeBuild.
    renderPanel(
      makeProject({
        phase: "stopped",
        stories: [
          makeStory({
            status: "todo",
            tasks: [
              makeTask({ id: "T1", status: "failed" }),
              makeTask({ id: "T2", status: "done" }),
            ],
          }),
        ],
      }),
    );
    expect(
      screen.getByRole("button", { name: /Relancer les échecs \(1\)/ }),
    ).toBeInTheDocument();
  });

  it("retry-failed : pas de bouton sans story en échec", () => {
    renderPanel(makeProject({ phase: "done", stories: [makeStory({ status: "done" })] }));
    expect(
      screen.queryByRole("button", { name: /Relancer les échecs/ }),
    ).not.toBeInTheDocument();
  });

  it("retry-failed : pas de bouton si la pipeline est active (build)", () => {
    renderPanel(makeProject({ phase: "build", stories: [makeStory({ status: "failed" })] }));
    expect(
      screen.queryByRole("button", { name: /Relancer les échecs/ }),
    ).not.toBeInTheDocument();
  });

  it("run : les arguments saisis sont transmis à onRun", () => {
    const onRun = vi.fn();
    renderPanel(makeProject({ phase: "done" }), [], vi.fn(), onRun);
    const input = screen.getByPlaceholderText(/arguments/i);
    fireEvent.change(input, { target: { value: "auth-screen" } });
    fireEvent.click(screen.getByRole("button", { name: "▶ Lancer le projet" }));
    expect(onRun).toHaveBeenCalledWith("auth-screen");
  });

  it("run : pas de champ d'arguments quand on ne peut pas lancer (phase build)", () => {
    renderPanel(makeProject({ phase: "build" }));
    expect(screen.queryByPlaceholderText(/arguments/i)).not.toBeInTheDocument();
  });
});
