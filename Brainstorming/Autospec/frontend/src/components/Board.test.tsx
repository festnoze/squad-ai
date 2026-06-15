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
  it("affiche l'état vide quand il n'y a pas d'epic", () => {
    render(<Board epics={[]} stories={[]} projectId="p1" />);
    expect(
      screen.getByText("Le PO n'a pas encore produit de plan."),
    ).toBeInTheDocument();
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
