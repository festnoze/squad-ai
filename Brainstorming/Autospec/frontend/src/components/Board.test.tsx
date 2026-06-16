import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Board } from "./Board";
import { Epic, UserStory } from "../types";

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
