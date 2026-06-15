import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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

describe("Board — groupement par itération (UI1)", () => {
  const ep = (id: string, iteration: number): Epic => ({
    id,
    title: `Epic ${id}`,
    description: "",
    iteration,
  });

  it("plusieurs itérations → groupées ; historique replié, récente dépliée", () => {
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
    expect(screen.getByTestId("iter-header-2")).toBeInTheDocument();
    expect(screen.getByTestId("iter-header-1")).toBeInTheDocument();
    // itération 2 (récente) dépliée ; itération 1 repliée
    expect(screen.getByTestId("epic-E2")).toBeInTheDocument();
    expect(screen.queryByTestId("epic-E1")).not.toBeInTheDocument();
    // déplier l'historique
    fireEvent.click(screen.getByTestId("iter-header-1"));
    expect(screen.getByTestId("epic-E1")).toBeInTheDocument();
  });

  it("une seule itération → pas de regroupement (grille à plat)", () => {
    render(
      <Board
        epics={[ep("E1", 1)]}
        stories={[makeStory({ epic_id: "E1" })]}
        projectId="grp2"
      />,
    );
    expect(screen.queryByTestId("iter-header-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("epic-E1")).toBeInTheDocument();
  });

  it("une itération en cours est dépliée automatiquement", () => {
    render(
      <Board
        epics={[ep("E1", 1), ep("E2", 2)]}
        stories={[
          makeStory({ id: "S1", epic_id: "E1", status: "in_progress" }),
          makeStory({ id: "S2", epic_id: "E2", status: "done" }),
        ]}
        projectId="grp3"
      />,
    );
    // itération 1 (en cours) dépliée même si ce n'est pas la plus récente
    expect(screen.getByTestId("epic-E1")).toBeInTheDocument();
    expect(screen.getByTestId("epic-E2")).toBeInTheDocument();
  });
});
