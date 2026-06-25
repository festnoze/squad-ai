import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// getIterations est appelé au montage (si onRollbackTo fourni) : on le mocke
// pour éviter un fetch réseau, en gardant le reste du module ./api réel.
vi.mock("../api", async (importActual) => ({
  ...(await importActual<typeof import("../api")>()),
  getIterations: vi.fn().mockResolvedValue([1, 2]),
}));

import { WorkspaceViews } from "./WorkspaceViews";
import { Epic, UserStory } from "../types";

const epic = (id: string, iteration: number, title = `Epic ${id}`): Epic => ({
  id,
  title,
  description: "",
  iteration,
});

function story(overrides: Partial<UserStory> = {}): UserStory {
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
    status: "todo",
    iteration: 1,
    attempts: 0,
    last_error: "",
    ...overrides,
  };
}

describe("WorkspaceViews", () => {
  it("une seule itération → pas de bascule (vision produit seule)", () => {
    render(
      <WorkspaceViews
        epics={[epic("E1", 1)]}
        stories={[story({ id: "S1", epic_id: "E1" })]}
        projectId="p1"
      />,
    );
    expect(screen.queryByRole("tab", { name: /Iterations/ })).not.toBeInTheDocument();
    expect(screen.getByTestId("epic-E1")).toBeInTheDocument();
  });

  it("≥2 itérations → bascule visible ; on passe à la chronologie", () => {
    render(
      <WorkspaceViews
        epics={[epic("E1", 1), epic("E2", 2)]}
        stories={[
          story({ id: "S1", epic_id: "E1", iteration: 1 }),
          story({ id: "S2", epic_id: "E2", iteration: 2 }),
        ]}
        projectId="p2"
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Iterations/ }));
    expect(screen.getByTestId("iter-card-2")).toBeInTheDocument();
    expect(screen.getByTestId("iter-card-1")).toBeInTheDocument();
  });

  it("lien croisé : pastille « it. N » du Board → chronologie focalisée", () => {
    render(
      <WorkspaceViews
        epics={[epic("E1", 1), epic("E2", 2)]}
        stories={[story({ id: "S2", epic_id: "E2", iteration: 2 })]}
        projectId="p3"
      />,
    );
    fireEvent.click(screen.getByTitle("View iteration 2 in the timeline"));
    const card = screen.getByTestId("iter-card-2");
    expect(card.className).toMatch(/focused/);
  });

  it("lien croisé retour : clic sur une US de la chronologie → Board sur la US", () => {
    render(
      <WorkspaceViews
        epics={[epic("E1", 1), epic("E2", 2)]}
        stories={[
          story({ id: "S2", epic_id: "E2", iteration: 2, title: "Story ciblée" }),
        ]}
        projectId="p4"
      />,
    );
    // Aller à la chronologie puis cliquer la US.
    fireEvent.click(screen.getByRole("tab", { name: /Iterations/ }));
    fireEvent.click(screen.getByTitle("Open S2 in the product vision"));
    // Retour au Board, navigué sur la US S2.
    expect(screen.getByText("Story ciblée")).toBeInTheDocument();
    expect(screen.getAllByText("S2").length).toBeGreaterThan(0);
  });

  it("affiche le coût/tokens par itération dans la chronologie", () => {
    render(
      <WorkspaceViews
        epics={[epic("E1", 1), epic("E2", 2)]}
        stories={[story({ id: "S2", epic_id: "E2", iteration: 2 })]}
        projectId="p5"
        iterationUsage={{
          "2": { cost_usd: 0.05, input_tokens: 1000, output_tokens: 500, agent_calls: 3 },
        }}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Iterations/ }));
    const card = screen.getByTestId("iter-card-2");
    expect(card).toHaveTextContent("$0.0500");
    expect(card).toHaveTextContent("1.5k tok");
    expect(card).toHaveTextContent("3 agent calls");
  });

  it("bouton rollback par itération (snapshot dispo) → appelle onRollbackTo", async () => {
    const onRollbackTo = vi.fn();
    render(
      <WorkspaceViews
        epics={[epic("E1", 1), epic("E2", 2)]}
        stories={[story({ id: "S2", epic_id: "E2", iteration: 2 })]}
        projectId="p6"
        onRollbackTo={onRollbackTo}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Iterations/ }));
    // getIterations (mocké → [1,2]) résout de façon asynchrone.
    const btn = await screen.findByTitle(
      "Restore the workspace to the iteration 2 snapshot",
    );
    fireEvent.click(btn);
    await waitFor(() => expect(onRollbackTo).toHaveBeenCalledWith(2));
  });
});
