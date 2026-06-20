import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Board } from "./Board";
import { Epic, Stream, Task, UserStory } from "../types";

function makeStory(overrides: Partial<UserStory> = {}): UserStory {
  return {
    id: "S1",
    epic_id: "E1",
    title: "Ma user story",
    description: "",
    acceptance_criteria: [],
    gherkin: "",
    test_plan: [],
    depends_on: [],
    priority: 3,
    status: "todo",
    iteration: 0,
    attempts: 0,
    last_error: "",
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
    status: "todo",
    attempts: 0,
    last_error: "",
    files_hint: [],
    ...overrides,
  };
}

const STREAMS: Stream[] = [
  { id: "backend", kind: "backend", language: "python", toolchain: "", file_root: "", primary: true },
  { id: "frontend", kind: "frontend", language: "react", toolchain: "", file_root: "frontend", primary: false },
];

describe("Board", () => {
  it("affiche un état vide actionnable quand il n'y a pas d'epic", () => {
    const { container } = render(<Board epics={[]} stories={[]} projectId="p1" />);
    // Hors phase de planification : consigne claire (UI6), pas de spinner.
    expect(screen.getByText(/Pas encore de plan/i)).toBeInTheDocument();
    expect(container.querySelector(".spinner")).toBeNull();
  });

  it("UI6 : pendant la planification, l'état vide montre un spinner", () => {
    const { container } = render(
      <Board epics={[]} stories={[]} projectId="p1" phase="plan" />,
    );
    expect(container.querySelector(".spinner")).not.toBeNull();
    expect(screen.getByText(/génère le plan/i)).toBeInTheDocument();
  });

  it("navigation hiérarchique : épics → epic → story (drill-down)", () => {
    const epic: Epic = {
      id: "E1",
      title: "Mon epic",
      description: "",
      iteration: 1,
    };
    const story = makeStory({ epic_id: "E1", title: "Connexion utilisateur" });
    render(<Board epics={[epic]} stories={[story]} projectId="p1" />);

    // Niveau racine : l'epic est visible, la story ne l'est pas encore.
    expect(screen.getByText("Mon epic")).toBeInTheDocument();
    expect(screen.queryByText("Connexion utilisateur")).not.toBeInTheDocument();

    // Clic sur la carte epic → niveau epic : la story apparaît.
    fireEvent.click(screen.getByText("Mon epic"));
    expect(screen.getByText("Connexion utilisateur")).toBeInTheDocument();

    // Clic sur la story → niveau us : le fil d'Ariane montre l'id de la story.
    fireEvent.click(screen.getByText("Connexion utilisateur"));
    const crumbs = screen.getAllByText("S1");
    expect(crumbs.length).toBeGreaterThan(0);
  });

  it("carte epic : avancement (barre + compteur) au niveau racine", () => {
    const epic: Epic = { id: "E1", title: "Cœur", description: "", iteration: 1 };
    render(
      <Board
        epics={[epic]}
        stories={[
          makeStory({ id: "S1", status: "done" }),
          makeStory({ id: "S2", status: "done" }),
          makeStory({ id: "S3", status: "todo" }),
        ]}
        projectId="p1"
      />,
    );
    const card = screen.getByTestId("epic-E1");
    expect(card).toHaveTextContent("2/3 terminée(s)");
    expect(card.querySelector('[role="progressbar"]')).toHaveAttribute(
      "aria-valuenow",
      "67",
    );
    // Aucune US en cours → pas de spinner ni d'état « working ».
    expect(screen.queryByTestId("epic-spinner")).not.toBeInTheDocument();
    expect(card.className).not.toMatch(/epic-working/);
  });

  it("US en cours : epic mis en valeur (spinner + classe working) + compteur", () => {
    const epic: Epic = { id: "E1", title: "Cœur", description: "", iteration: 1 };
    render(
      <Board
        epics={[epic]}
        stories={[
          makeStory({ id: "S1", status: "in_progress" }),
          makeStory({ id: "S2", status: "todo" }),
        ]}
        projectId="p1"
      />,
    );
    const card = screen.getByTestId("epic-E1");
    expect(card.className).toMatch(/epic-working/);
    expect(screen.getByTestId("epic-spinner")).toBeInTheDocument();
    expect(card).toHaveTextContent("1 en cours");
  });

  it("US en cours : la story porte la classe status-in_progress (halo)", () => {
    const epic: Epic = { id: "E1", title: "Cœur", description: "", iteration: 1 };
    const story = makeStory({ id: "S1", status: "in_progress", title: "Dev story" });
    render(<Board epics={[epic]} stories={[story]} projectId="p1" />);
    fireEvent.click(screen.getByText("Cœur")); // drill dans l'epic
    const row = screen.getByTestId("story-S1");
    expect(row.className).toMatch(/status-in_progress/);
  });
});

describe("Board — vision produit à plat + pastille itération", () => {
  const ep = (id: string, iteration: number): Epic => ({
    id,
    title: `Epic ${id}`,
    description: "",
    iteration,
  });

  it("plusieurs itérations → grille à plat (pas de regroupement par itération)", () => {
    render(
      <Board
        epics={[ep("E1", 1), ep("E2", 2)]}
        stories={[
          makeStory({ id: "S1", epic_id: "E1", status: "done" }),
          makeStory({ id: "S2", epic_id: "E2", status: "todo" }),
        ]}
        projectId="grp1"
      />,
    );
    // Tous les epics visibles d'emblée, quelle que soit leur itération.
    expect(screen.getByTestId("epic-E1")).toBeInTheDocument();
    expect(screen.getByTestId("epic-E2")).toBeInTheDocument();
    // Plus d'en-têtes d'itération repliables.
    expect(screen.queryByTestId("iter-header-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("iter-header-2")).not.toBeInTheDocument();
  });

  it("la pastille « it. N » est un lien quand onOpenIteration est fourni", () => {
    const onOpenIteration = vi.fn();
    render(
      <Board
        epics={[ep("E1", 1), ep("E2", 2)]}
        stories={[makeStory({ id: "S2", epic_id: "E2" })]}
        projectId="grp2"
        onOpenIteration={onOpenIteration}
      />,
    );
    fireEvent.click(screen.getByTitle("Voir l'itération 2 dans la chronologie"));
    expect(onOpenIteration).toHaveBeenCalledWith(2);
  });

  it("focus externe : navigue directement vers la US ciblée", () => {
    render(
      <Board
        epics={[ep("E1", 1)]}
        stories={[makeStory({ id: "S1", epic_id: "E1", title: "Story ciblée" })]}
        projectId="grp3"
        focus={{ epicId: "E1", storyId: "S1" }}
      />,
    );
    // Le fil d'Ariane montre l'id de la US → on est bien au niveau détail.
    expect(screen.getAllByText("S1").length).toBeGreaterThan(0);
    expect(screen.getByText("Story ciblée")).toBeInTheDocument();
  });
});

describe("Board — relance d'une story bloquée (US todo en erreur)", () => {
  const epic: Epic = { id: "E1", title: "Cœur", description: "", iteration: 1 };
  const stuck = makeStory({
    id: "US-13",
    epic_id: "E1",
    status: "todo",
    attempts: 1,
    last_error: "boom",
    title: "US bloquée",
  });

  function openDetail(phase: string) {
    render(<Board epics={[epic]} stories={[stuck]} projectId="p1" phase={phase} />);
    fireEvent.click(screen.getByText("Cœur")); // épics -> epic
    fireEvent.click(screen.getByText("US bloquée")); // epic -> détail
  }

  it("pipeline dormante : une US todo tentée/en erreur est relançable", () => {
    openDetail("done");
    expect(screen.getByRole("button", { name: /Relancer/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Forcer terminé/ })).toBeInTheDocument();
  });

  it("pipeline active : pas de relance par story (le build tourne)", () => {
    openDetail("build");
    expect(screen.queryByRole("button", { name: /Relancer/ })).not.toBeInTheDocument();
  });
});

describe("Board — multi-stream (ST-12/13/14)", () => {
  const epic: Epic = { id: "E1", title: "Cœur", description: "", iteration: 1 };

  function drillToEpic(story: UserStory, extra: Partial<Parameters<typeof Board>[0]> = {}) {
    render(
      <Board
        epics={[epic]}
        stories={[story]}
        streams={STREAMS}
        projectId="p1"
        {...extra}
      />,
    );
    fireEvent.click(screen.getByText("Cœur"));
  }

  it("ST-12 : badge stream sur une US non-défaut + filtre par stream visible", () => {
    drillToEpic(makeStory({ id: "S1", stream: "frontend", title: "Front US" }));
    // Badge stream sur la carte US.
    expect(screen.getByTestId("stream-badge-frontend")).toBeInTheDocument();
    // La barre de filtre apparaît (projet multi-stream).
    expect(screen.getByTestId("stream-filter-backend")).toBeInTheDocument();
    expect(screen.getByTestId("stream-filter-frontend")).toBeInTheDocument();
  });

  it("ST-12 : les tâches d'une US sont dépliables avec leur badge stream", () => {
    const story = makeStory({
      id: "S1",
      tasks: [
        makeTask({ id: "T-back", stream: "backend", title: "API" }),
        makeTask({ id: "T-front", stream: "frontend", title: "UI" }),
      ],
    });
    drillToEpic(story);
    // Sous-liste de tâches rendue + badge stream frontend visible sur la tâche.
    expect(screen.getByTestId("tasks-S1")).toBeInTheDocument();
    expect(screen.getByTestId("task-T-back")).toBeInTheDocument();
    expect(screen.getByTestId("task-T-front")).toBeInTheDocument();
    // Repli/dépli.
    fireEvent.click(screen.getByTestId("task-toggle-S1"));
    expect(screen.queryByTestId("tasks-S1")).not.toBeInTheDocument();
  });

  it("ST-12 : le statut d'une US conteneur est dérivé de ses tâches (in_progress)", () => {
    const story = makeStory({
      id: "S1",
      status: "todo",
      tasks: [
        makeTask({ id: "T1", status: "done" }),
        makeTask({ id: "T2", status: "in_progress" }),
      ],
    });
    drillToEpic(story);
    const row = screen.getByTestId("story-S1");
    // Halo « en cours » dérivé bien que le statut stocké soit todo.
    expect(row.className).toMatch(/status-in_progress/);
  });

  it("ST-14 : une tâche todo dont la dépendance n'est pas done affiche « bloquée par »", () => {
    const story = makeStory({
      id: "S1",
      tasks: [
        makeTask({ id: "T-back", status: "in_progress" }),
        makeTask({ id: "T-front", status: "todo", depends_on: ["T-back"] }),
      ],
    });
    drillToEpic(story);
    const frontRow = screen.getByTestId("task-T-front");
    expect(frontRow).toHaveTextContent(/bloquée par T-back/);
  });

  it("ST-14 : une tâche failed sur conflit de merge affiche l'indice de conflit", () => {
    const story = makeStory({
      id: "S1",
      tasks: [
        makeTask({
          id: "T-back",
          status: "failed",
          last_error: "conflit de merge inter-stream non résolu",
        }),
      ],
    });
    drillToEpic(story);
    const row = screen.getByTestId("task-T-back");
    expect(row).toHaveTextContent(/conflit de merge/);
  });

  it("ST-13 : ouvrir une tâche montre son détail + actions par tâche (relance)", () => {
    const story = makeStory({
      id: "S1",
      tasks: [
        makeTask({
          id: "T-back",
          stream: "backend",
          status: "failed",
          attempts: 1,
          last_error: "boom",
          title: "API en échec",
        }),
      ],
    });
    drillToEpic(story, { phase: "done" });
    fireEvent.click(screen.getByText("API en échec"));
    expect(screen.getByTestId("task-detail-T-back")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Relancer/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Forcer terminé/ })).toBeInTheDocument();
  });

  it("legacy (aucun stream/tâche) : rendu inchangé, pas de filtre ni badge stream", () => {
    render(
      <Board
        epics={[epic]}
        stories={[makeStory({ id: "S1", title: "US legacy" })]}
        projectId="p1"
      />,
    );
    fireEvent.click(screen.getByText("Cœur"));
    // Aucune barre de filtre, aucune sous-liste de tâches, aucun badge stream.
    expect(screen.queryByTestId("stream-filter-backend")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tasks-S1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("stream-badge-frontend")).not.toBeInTheDocument();
    // La US s'affiche normalement.
    expect(screen.getByTestId("story-S1")).toBeInTheDocument();
  });
});
