import { render, screen } from "@testing-library/react";
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

  it("affiche le titre de la story quand un epic et une story sont fournis", () => {
    const epic: Epic = {
      id: "E1",
      title: "Mon epic",
      description: "",
      iteration: 1,
    };
    const story = makeStory({ epic_id: "E1", title: "Connexion utilisateur" });
    render(<Board epics={[epic]} stories={[story]} projectId="p1" />);
    expect(screen.getByText("Connexion utilisateur")).toBeInTheDocument();
  });
});
