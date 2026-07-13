import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ObservationsPanel } from "./ObservationsPanel";
import { EngineeringObservation, GovernanceDecision } from "../types";

function makeObservation(
  overrides: Partial<EngineeringObservation> = {},
): EngineeringObservation {
  return {
    id: "OBS-1",
    type: "tech_debt",
    summary: "Cache maison au lieu de Redis",
    description: "Un cache en mémoire a été codé faute de Redis dispo.",
    evidence: ["backend/app/cache.py", "sortie de test : 3 passed"],
    impact: "Le composant cache ne survit pas au redémarrage",
    confidence: 0.8,
    urgency: "high",
    workaround: "dict Python avec TTL",
    recommendations: ["Brancher un vrai Redis", "Extraire une interface"],
    reevaluate_when: "quand Redis sera disponible",
    source_role: "dev",
    work_item_id: "US-3",
    stream: "backend",
    iteration: 1,
    status: "routed",
    routed_to: "debt",
    resolution: "",
    merged_count: 0,
    ...overrides,
  };
}

function makeDecision(overrides: Partial<GovernanceDecision> = {}): GovernanceDecision {
  return {
    id: "GOV-1",
    observation_id: "OBS-1",
    action: "create_story",
    target_id: "",
    payload: { title: "Brancher Redis", epic_id: "EPIC-2" },
    rationale: "Dette bloquante pour la prod",
    status: "proposed",
    iteration: 1,
    ...overrides,
  };
}

describe("ObservationsPanel (US-F7.2)", () => {
  it("ne rend rien sans observation (flag OFF → panneau invisible)", () => {
    const { container } = render(<ObservationsPanel observations={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("liste les observations avec badge d'urgence et statut", () => {
    render(
      <ObservationsPanel
        observations={[
          makeObservation(),
          makeObservation({ id: "OBS-2", type: "risk", urgency: "critical", status: "new", summary: "Fuite mémoire possible" }),
        ]}
      />,
    );
    expect(screen.getByText("Cache maison au lieu de Redis")).toBeInTheDocument();
    expect(screen.getByText("Fuite mémoire possible")).toBeInTheDocument();
    // Urgences (langue par défaut des tests : en).
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
    // Statuts (badges — les mêmes libellés existent aussi en <option> du filtre).
    const statusBadges = [...document.body.querySelectorAll(".badge-obs-status")].map(
      (e) => e.textContent,
    );
    expect(statusBadges).toEqual(expect.arrayContaining(["routed", "new"]));
  });

  it("filtre par type", () => {
    render(
      <ObservationsPanel
        observations={[
          makeObservation(),
          makeObservation({ id: "OBS-2", type: "risk", summary: "Un risque" }),
        ]}
      />,
    );
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "risk" } });
    expect(screen.getByText("Un risque")).toBeInTheDocument();
    expect(screen.queryByText("Cache maison au lieu de Redis")).not.toBeInTheDocument();
  });

  it("filtre par statut, stream et itération", () => {
    render(
      <ObservationsPanel
        observations={[
          makeObservation(),
          makeObservation({
            id: "OBS-2",
            summary: "Observation frontend",
            stream: "frontend",
            iteration: 2,
            status: "actioned",
          }),
        ]}
      />,
    );
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "actioned" } });
    expect(screen.getByText("Observation frontend")).toBeInTheDocument();
    expect(screen.queryByText("Cache maison au lieu de Redis")).not.toBeInTheDocument();
    // Retour à « tous » puis filtre stream.
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Stream"), { target: { value: "backend" } });
    expect(screen.getByText("Cache maison au lieu de Redis")).toBeInTheDocument();
    expect(screen.queryByText("Observation frontend")).not.toBeInTheDocument();
    // Filtre itération (le select n'apparaît que si > 1 itération présente).
    fireEvent.change(screen.getByLabelText("Stream"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Iteration"), { target: { value: "2" } });
    expect(screen.getByText("Observation frontend")).toBeInTheDocument();
    expect(screen.queryByText("Cache maison au lieu de Redis")).not.toBeInTheDocument();
  });

  it("aucun résultat → état vide silencieux (pas de crash)", () => {
    render(<ObservationsPanel observations={[makeObservation()]} />);
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "tech_debt" } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "routed" } });
    fireEvent.change(screen.getByLabelText("Stream"), { target: { value: "backend" } });
    // Filtre incompatible : type présent mais statut absent des données.
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "" } });
    expect(screen.getByText("Cache maison au lieu de Redis")).toBeInTheDocument();
  });

  it("le détail extensible expose preuves, impact, recommandations et décision liée", () => {
    render(
      <ObservationsPanel
        observations={[makeObservation()]}
        decisions={[makeDecision()]}
      />,
    );
    // Replié : le détail n'est pas rendu.
    expect(screen.queryByText(/backend\/app\/cache\.py/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle("Show details"));
    expect(screen.getByText("backend/app/cache.py")).toBeInTheDocument();
    expect(screen.getByText(/ne survit pas au redémarrage/)).toBeInTheDocument();
    expect(screen.getByText("Brancher un vrai Redis")).toBeInTheDocument();
    expect(screen.getByText(/dict Python avec TTL/)).toBeInTheDocument();
    expect(screen.getByText(/80%/)).toBeInTheDocument();
    // Décision PO liée via observation_id.
    expect(screen.getByText(/GOV-1/)).toBeInTheDocument();
    expect(screen.getByText(/Dette bloquante pour la prod/)).toBeInTheDocument();
    // Re-clic : repli.
    fireEvent.click(screen.getByTitle("Hide details"));
    expect(screen.queryByText("backend/app/cache.py")).not.toBeInTheDocument();
  });
});
