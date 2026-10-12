import { fireEvent, render, screen, within } from "@testing-library/react";
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
  onRestartFromScratch: () => void = vi.fn(),
  onUndeploy: () => void = vi.fn(),
  onVerifyDelivery: () => void = vi.fn(),
  onResumeBuild: () => void = vi.fn(),
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
      onResumeBuild={onResumeBuild}
      onRetryFailed={onRetryFailed}
      onRestartFromScratch={onRestartFromScratch}
      onDocument={vi.fn()}
      onExportZip={vi.fn()}
      onGitExport={vi.fn()}
      onCancelResume={vi.fn()}
      onApprove={vi.fn()}
      onReject={vi.fn()}
      onDeploy={vi.fn()}
      onUndeploy={onUndeploy}
      onVerifyDelivery={onVerifyDelivery}
    />,
  );
  return {
    ...utils,
    onRetryFailed,
    onRun,
    onRestartFromScratch,
    onUndeploy,
    onVerifyDelivery,
    onResumeBuild,
  };
}

describe("RunPanel", () => {
  it("phase 'done' : bouton « Lancer » activé, pas de bouton « Stopper »", () => {
    renderPanel(makeProject({ phase: "done" }));
    const run = screen.getByRole("button", { name: "▶ Run project" });
    expect(run).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "⏹ Stop" }),
    ).not.toBeInTheDocument();
  });

  it("phase 'build' : bouton « Stopper » présent", () => {
    renderPanel(makeProject({ phase: "build" }));
    expect(
      screen.getByRole("button", { name: "⏹ Stop" }),
    ).toBeInTheDocument();
  });

  it("phase 'spec' : bouton « Lancer » désactivé (canRun faux)", () => {
    // canRun exclut spec/plan/analyze/architect/idle. La phase « build » N'EST
    // PAS exclue, donc le bouton y reste actif : on teste donc « spec ».
    renderPanel(makeProject({ phase: "spec" }));
    expect(
      screen.getByRole("button", { name: "▶ Run project" }),
    ).toBeDisabled();
  });

  it("paused=true (phase build) : bouton « Reprendre » présent, pas « Pause »", () => {
    renderPanel(makeProject({ phase: "build", paused: true }));
    expect(
      screen.getByRole("button", { name: "▶ Resume" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "⏸ Pause" }),
    ).not.toBeInTheDocument();
  });

  it("running=true : bouton « Arrêter l'app » présent, libellé primaire « En cours… »", () => {
    renderPanel(makeProject({ phase: "build", running: true }));
    expect(
      screen.getByRole("button", { name: "■ Stop app" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "▶ Running…" }),
    ).toBeInTheDocument();
  });

  it("phase 'stopped' avec story 'todo' : bouton « Continuer le build » présent", () => {
    renderPanel(
      makeProject({ phase: "stopped", stories: [makeStory({ status: "todo" })] }),
    );
    expect(
      screen.getByRole("button", { name: "▶ Continue build" }),
    ).toBeInTheDocument();
  });

  it("REGRESSION (snake) : phase 'done' avec stories 'todo' restantes : bouton « Continuer le build » présent", () => {
    // Une itération auto-spec terminée laisse la phase à 'done' tout en gardant
    // des US non construites. Le bouton doit s'afficher (gating dormant inclut
    // 'done', cf. backend aresume_build). C'était le bug d'origine : 'done' était
    // absent de la liste des phases côté RunPanel.
    renderPanel(
      makeProject({
        phase: "done",
        stories: [
          makeStory({ id: "S1", status: "done" }),
          makeStory({ id: "S2", status: "todo" }),
        ],
      }),
    );
    expect(
      screen.getByRole("button", { name: "▶ Continue build" }),
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
      screen.getByRole("button", { name: "▶ Continue build" }),
    ).toBeInTheDocument();
  });

  it("phase 'stopped' sans story todo/red : pas de bouton « Continuer le build »", () => {
    renderPanel(
      makeProject({ phase: "stopped", stories: [makeStory({ status: "done" })] }),
    );
    expect(
      screen.queryByRole("button", { name: "▶ Continue build" }),
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

  it("labels recorded cost and budget as estimates, not a bill or guaranteed spending cap", () => {
    const { container } = renderPanel(makeProject({
      budget_usd: 2,
      usage: { ...NEUTRAL_USAGE, cost_usd: 2.25, agent_calls: 3 },
    }));
    const meter = container.querySelector(".usage-meter")!;
    expect(meter).toHaveTextContent("Estimated: $2.2500 / guardrail: $2.00");
    expect(meter).toHaveClass("over-budget");
    expect(meter).toHaveAttribute("title", expect.stringContaining("not invoices"));
    expect(screen.getByText("About cost estimates")).toBeVisible();
    expect(screen.queryByText(/Incomplete estimate/)).not.toBeInTheDocument();
  });

  it("warns about unreported usage even when the recorded estimate is zero", () => {
    renderPanel(makeProject({
      usage: { ...NEUTRAL_USAGE, agent_calls: 2, failed_calls: 2, unreported_calls: 2 },
    }));
    expect(screen.getByText(/Estimated: \$0\.0000/)).toBeVisible();
    expect(screen.getByText("⚠ Incomplete estimate: 2 call(s) without usage data")).toBeVisible();
    expect(screen.getByText(/not invoices/)).toBeVisible();
  });

  it("delivery_issues : affiche une bannière de livraison bloquée", () => {
    renderPanel(makeProject({ delivery_issues: ["US-2 n'est pas livrée"] }));
    expect(screen.getByText(/Livraison · 1/)).toBeInTheDocument();
  });

  it("delivery_partial : bannière 📦 (avertissement) au lieu de ⛔", () => {
    renderPanel(
      makeProject({
        delivery_partial: true,
        delivery_issues: ["Livraison partielle : 2/3", "US-2 livrée SANS cette story"],
      }),
    );
    expect(screen.getByTestId("partial-delivery").textContent).toContain("2");
    expect(screen.queryByText(/⛔ Livraison/)).not.toBeInTheDocument();
  });

  it("deploy_status 'deployed' : chip 🐳 avec lien vers le port + action Undeploy", () => {
    const onUndeploy = vi.fn();
    renderPanel(
      makeProject({ deploy_status: "deployed", deploy_host_port: 18001 }),
      [],
      vi.fn(),
      vi.fn(),
      vi.fn(),
      onUndeploy,
    );
    const link = screen.getByRole("link", { name: /Deployed/ });
    // Exact IPv4 loopback matches the owned ingress and APP_ORIGIN; a
    // localhost alias would change browser Origin and fail legitimate CSRF.
    expect(link).toHaveAttribute("href", "http://127.0.0.1:18001");
    const undeploy = screen.getByRole("button", { name: "Undeploy" });
    fireEvent.click(undeploy);
    expect(onUndeploy).toHaveBeenCalledTimes(1);
  });

  it("deploy_status 'failed' : chip rouge avec le détail en title", () => {
    renderPanel(
      makeProject({ deploy_status: "failed", deploy_detail: "docker build a échoué" }),
    );
    expect(screen.getByTestId("deploy-chip")).toHaveAttribute(
      "title",
      "docker build a échoué",
    );
  });

  it("deploy_status 'building' : chip en cours (pulsant)", () => {
    const { container } = renderPanel(makeProject({ deploy_status: "building" }));
    const chip = screen.getByTestId("deploy-chip");
    expect(chip.className).toMatch(/deploy-chip-progress/);
    expect(container.querySelector(".deploy-chip-ok")).toBeNull();
  });

  it("resume_at > 0 : bannière de reprise auto + bouton annuler (M2)", () => {
    const { container } = renderPanel(
      makeProject({ phase: "stopped", resume_at: Date.now() / 1000 + 3600 }),
    );
    expect(container.querySelector(".resume-banner")).not.toBeNull();
    expect(screen.getByText(/Auto-resume at/)).toBeInTheDocument();
    expect(
      screen.getByTitle("Cancel automatic resume"),
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
    expect(screen.getByText(/none yet/i)).toBeInTheDocument();
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
    const trigger = screen.getByRole("button", { name: /⋯ Delivery/ });
    fireEvent.click(trigger);
    expect(screen.getByRole("menuitem", { name: /Doc \(README\)/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Export as zip/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Deployment/ })).toBeInTheDocument();
  });

  it("UI7 : pas de menu Livraison tant qu'aucun build n'existe (phase build)", () => {
    renderPanel(makeProject({ phase: "build" }));
    expect(screen.queryByRole("button", { name: /⋯ Delivery/ })).not.toBeInTheDocument();
  });

  it("retry-failed : bouton « Relancer les échecs (N) » + clic, quand dormant", () => {
    const { onRetryFailed } = renderPanel(
      makeProject({
        phase: "stopped",
        stories: [makeStory({ status: "failed" }), makeStory({ id: "S2", status: "done" })],
      }),
    );
    const btn = screen.getByRole("button", { name: /Retry failures \(1\)/ });
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
      screen.getByRole("button", { name: /Retry failures \(1\)/ }),
    ).toBeInTheDocument();
  });

  it("retry-failed : pas de bouton sans story en échec", () => {
    renderPanel(makeProject({ phase: "done", stories: [makeStory({ status: "done" })] }));
    expect(
      screen.queryByRole("button", { name: /Retry failures/ }),
    ).not.toBeInTheDocument();
  });

  it("restart : bouton « Relancer from scratch » quand dormant + brief, et clic", () => {
    const { onRestartFromScratch } = renderPanel(
      makeProject({ phase: "done", brief: "un brief", stories: [makeStory({ status: "done" })] }),
      [],
      vi.fn(),
      vi.fn(),
    );
    const btn = screen.getByRole("button", { name: /Restart from scratch/ });
    fireEvent.click(btn);
    expect(onRestartFromScratch).toHaveBeenCalledTimes(1);
  });

  it("restart : pas de bouton sans brief", () => {
    renderPanel(makeProject({ phase: "done", brief: "", stories: [makeStory({ status: "done" })] }));
    expect(
      screen.queryByRole("button", { name: /Restart from scratch/ }),
    ).not.toBeInTheDocument();
  });

  it("restart : pas de bouton si la pipeline est active (build)", () => {
    renderPanel(makeProject({ phase: "build", brief: "un brief" }));
    expect(
      screen.queryByRole("button", { name: /Restart from scratch/ }),
    ).not.toBeInTheDocument();
  });

  it("retry-failed : pas de bouton si la pipeline est active (build)", () => {
    renderPanel(makeProject({ phase: "build", stories: [makeStory({ status: "failed" })] }));
    expect(
      screen.queryByRole("button", { name: /Retry failures/ }),
    ).not.toBeInTheDocument();
  });

  it("P5 : « Re-vérifier la livraison » visible quand dormant + au moins une story done, et clic", () => {
    const { onVerifyDelivery } = renderPanel(
      makeProject({
        phase: "done",
        stories: [makeStory({ status: "done" }), makeStory({ id: "S2", status: "todo" })],
      }),
    );
    const btn = screen.getByTestId("verify-delivery");
    expect(btn).toHaveTextContent("Re-verify delivery");
    fireEvent.click(btn);
    expect(onVerifyDelivery).toHaveBeenCalledTimes(1);
  });

  it("P5 : statut EFFECTIF - US multi-stream dont toutes les tâches sont done (status brut 'todo') : bouton présent", () => {
    renderPanel(
      makeProject({
        phase: "needs_attention",
        stories: [
          makeStory({
            status: "todo",
            tasks: [
              makeTask({ id: "T1", status: "done" }),
              makeTask({ id: "T2", status: "done" }),
            ],
          }),
        ],
      }),
    );
    expect(screen.getByTestId("verify-delivery")).toBeInTheDocument();
  });

  it("P5 : pas de bouton pendant le build (pipeline active)", () => {
    renderPanel(
      makeProject({ phase: "build", stories: [makeStory({ status: "done" })] }),
    );
    expect(screen.queryByTestId("verify-delivery")).not.toBeInTheDocument();
  });

  it("P5 : pas de bouton quand aucune story n'est done (rien à vérifier)", () => {
    renderPanel(
      makeProject({ phase: "stopped", stories: [makeStory({ status: "todo" })] }),
    );
    expect(screen.queryByTestId("verify-delivery")).not.toBeInTheDocument();
  });

  it("run : les arguments saisis sont transmis à onRun", () => {
    const onRun = vi.fn();
    renderPanel(makeProject({ phase: "done" }), [], vi.fn(), onRun);
    const input = screen.getByPlaceholderText(/arguments/i);
    fireEvent.change(input, { target: { value: "auth-screen" } });
    fireEvent.click(screen.getByRole("button", { name: "▶ Run project" }));
    expect(onRun).toHaveBeenCalledWith("auth-screen");
  });

  it("run : pas de champ d'arguments quand on ne peut pas lancer (phase build)", () => {
    renderPanel(makeProject({ phase: "build" }));
    expect(screen.queryByPlaceholderText(/arguments/i)).not.toBeInTheDocument();
  });
});

describe("RunPanel — filtres de logs (Q3)", () => {
  const LOGS = [
    { projectId: "p1", source: "dev:US-1", line: "building the thing" },
    { projectId: "p1", source: "qa:US-1", line: "❌ test failed on step 2" },
    { projectId: "p1", source: "dev:US-2", line: "another build line" },
  ];

  it("filtre par texte libre + compteur affiché/total", () => {
    renderPanel(makeProject({ phase: "done" }), LOGS);
    fireEvent.change(screen.getByPlaceholderText("Filter logs…"), {
      target: { value: "another" },
    });
    expect(screen.getByText(/another build line/)).toBeInTheDocument();
    expect(screen.queryByText(/building the thing/)).not.toBeInTheDocument();
    expect(screen.getByText("1/3 lines")).toBeInTheDocument();
  });

  it("filtre par source (tag dev:US-n / qa:US-n)", () => {
    renderPanel(makeProject({ phase: "done" }), LOGS);
    fireEvent.change(screen.getByLabelText("Filter logs by source"), {
      target: { value: "qa:US-1" },
    });
    expect(screen.getByText(/test failed on step 2/)).toBeInTheDocument();
    expect(screen.queryByText(/another build line/)).not.toBeInTheDocument();
  });

  it("« erreurs seulement » (heuristique ❌/⚠️)", () => {
    renderPanel(makeProject({ phase: "done" }), LOGS);
    fireEvent.click(screen.getByRole("checkbox", { name: "Errors only" }));
    expect(screen.getByText(/test failed on step 2/)).toBeInTheDocument();
    expect(screen.queryByText(/building the thing/)).not.toBeInTheDocument();
    expect(screen.getByText("1/3 lines")).toBeInTheDocument();
  });

  it("sans filtre actif : toutes les lignes, pas de compteur", () => {
    renderPanel(makeProject({ phase: "done" }), LOGS);
    expect(screen.getByText(/building the thing/)).toBeInTheDocument();
    expect(screen.getByText(/another build line/)).toBeInTheDocument();
    expect(screen.queryByText(/\/3 lines/)).not.toBeInTheDocument();
  });
});

describe("RunPanel — socle technique et images sans service HTTP", () => {
  it.each([
    ["preparing", "Preparing project foundation"],
    ["verifying", "Checking project foundation"],
  ] as const)("%s : le statut est visible et les contrôles concurrents sont bloqués", (status, label) => {
    // A retry can publish its bootstrap status while phase is still dormant.
    renderPanel(makeProject({
      phase: "needs_attention",
      brief: "a useful application",
      bootstrap_status: status,
      stories: [makeStory({ status: "todo" }), makeStory({ id: "done", status: "done" })],
    }));
    const statusPanel = screen.getByTestId("bootstrap-status");
    expect(within(statusPanel).getByText(label)).toBeVisible();
    expect(statusPanel).toHaveAttribute("aria-busy", "true");
    expect(statusPanel).toHaveClass("deploy-chip-progress");
    expect(screen.getByRole("button", { name: "▶ Run project" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Continue build|Retry initialization|Restart from scratch/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId("verify-delivery")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "⏹ Stop" })).toBeEnabled();
  });

  it("échec sans story : ouvre le diagnostic et propose de reprendre l'initialisation", () => {
    const { onResumeBuild, onRun } = renderPanel(makeProject({
      phase: "needs_attention",
      bootstrap_status: "failed",
      bootstrap_detail: "Node.js executable not found",
      technical_stack: { backend: "python", frontend: "react", database: "sqlite", source: "architect", template_version: "1" },
      stories: [],
    }));
    const statusPanel = screen.getByTestId("bootstrap-status");
    expect(statusPanel).toHaveAttribute("open");
    expect(statusPanel).toHaveAttribute("aria-busy", "false");
    expect(within(statusPanel).getByText("Node.js executable not found")).toBeVisible();
    expect(statusPanel).toHaveTextContent("backend: python · frontend: react · database: sqlite");
    expect(statusPanel).not.toHaveTextContent("template_version");
    expect(statusPanel).not.toHaveTextContent("source:");
    const retry = screen.getByRole("button", { name: "▶ Retry initialization" });
    expect(retry).toHaveAttribute("title", "Check the project foundation again, then continue planning and building");
    fireEvent.click(retry);
    expect(onResumeBuild).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "▶ Run project" }));
    expect(onRun).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /⋯ Delivery/ })).not.toBeInTheDocument();
  });

  it("socle vérifié : pas de reprise initiale fictive et lancement disponible", () => {
    renderPanel(makeProject({ phase: "done", bootstrap_status: "ready", bootstrap_detail: "HTTP and SQLite verified" }));
    expect(screen.getByText("Project foundation verified")).toBeVisible();
    expect(screen.getByTestId("bootstrap-status")).toHaveClass("deploy-chip-ok");
    expect(screen.getByRole("button", { name: "▶ Run project" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Retry initialization/ })).not.toBeInTheDocument();
  });

  it.each([undefined, "", "skipped"] as const)("statut socle %s : aucun indicateur trompeur", (status) => {
    renderPanel(makeProject({ bootstrap_status: status }));
    expect(screen.queryByTestId("bootstrap-status")).not.toBeInTheDocument();
  });

  it("image CLI/bibliothèque : nom et retrait disponibles, sans lien localhost", () => {
    const { onUndeploy } = renderPanel(makeProject({
      deploy_status: "packaged",
      deployed_image: "autospec/cli-project:latest",
      deployed_container: "",
      deploy_host_port: 0,
      deploy_detail: "Image built and CLI help checked offline",
    }));
    const chip = screen.getByTestId("deploy-chip");
    expect(chip).toHaveTextContent("Docker image verified");
    expect(chip).toHaveTextContent("autospec/cli-project:latest");
    expect(chip).toHaveAttribute("title", "Image built and CLI help checked offline");
    expect(within(chip).queryByRole("link")).not.toBeInTheDocument();
    const remove = within(chip).getByRole("button", { name: "Undeploy" });
    expect(remove).toHaveAttribute("title", "Remove the packaged Docker image");
    fireEvent.click(remove);
    expect(onUndeploy).toHaveBeenCalledTimes(1);
  });

  it.each(["", "autospec-project"])("retrait échoué : conserve une action de nettoyage (%s)", (container) => {
    const { onUndeploy } = renderPanel(makeProject({
      deploy_status: "failed",
      deployed_image: "autospec/project:latest",
      deployed_container: container,
      deploy_host_port: container ? 18042 : 0,
      deploy_detail: "Docker daemon unavailable; removal unconfirmed",
    }));
    const chip = screen.getByTestId("deploy-chip");
    expect(within(chip).queryByRole("link")).not.toBeInTheDocument();
    const retry = within(chip).getByRole("button", { name: "Undeploy" });
    if (!container) expect(retry).toHaveAttribute("title", "Remove the packaged Docker image");
    fireEvent.click(retry);
    expect(onUndeploy).toHaveBeenCalledTimes(1);
  });

  it("build Docker échoué sans ressource : aucun retrait fictif", () => {
    renderPanel(makeProject({ deploy_status: "failed", deployed_image: "", deployed_container: "" }));
    expect(within(screen.getByTestId("deploy-chip")).queryByRole("button", { name: "Undeploy" })).not.toBeInTheDocument();
  });
});
