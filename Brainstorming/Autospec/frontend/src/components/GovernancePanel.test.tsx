import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { decisionDiffLine, GovernancePanel } from "./GovernancePanel";
import { EngineeringObservation, GovernanceDecision } from "../types";

function makeDecision(overrides: Partial<GovernanceDecision> = {}): GovernanceDecision {
  return {
    id: "GOV-1",
    observation_id: "OBS-1",
    action: "create_story",
    target_id: "",
    payload: { title: "Brancher Redis", epic_id: "EPIC-3" },
    rationale: "Dette bloquante",
    status: "proposed",
    iteration: 1,
    ...overrides,
  };
}

function makeObservation(
  overrides: Partial<EngineeringObservation> = {},
): EngineeringObservation {
  return {
    id: "OBS-1",
    type: "tech_debt",
    summary: "Cache maison au lieu de Redis",
    description: "",
    evidence: [],
    impact: "",
    confidence: 0.5,
    urgency: "normal",
    workaround: "",
    recommendations: [],
    reevaluate_when: "",
    source_role: "dev",
    work_item_id: "",
    stream: "",
    iteration: 1,
    status: "routed",
    routed_to: "po",
    resolution: "",
    merged_count: 0,
    ...overrides,
  };
}

function renderPanel(
  decisions: GovernanceDecision[],
  handlers: { onApprove?: ReturnType<typeof vi.fn>; onReject?: ReturnType<typeof vi.fn> } = {},
) {
  const onApprove = handlers.onApprove ?? vi.fn();
  const onReject = handlers.onReject ?? vi.fn();
  const view = render(
    <GovernancePanel
      decisions={decisions}
      observations={[makeObservation()]}
      onApprove={onApprove}
      onReject={onReject}
    />,
  );
  return { onApprove, onReject, ...view };
}

describe("decisionDiffLine — diff lisible du backlog (US-F7.3)", () => {
  it("create_story → « + US “titre” dans EPIC »", () => {
    expect(decisionDiffLine(makeDecision())).toBe("+ US “Brancher Redis” in EPIC-3");
  });

  it("create_story technique → TS", () => {
    const d = makeDecision({
      payload: { title: "Refacto cache", epic_id: "EPIC-3", technical: true },
    });
    expect(decisionDiffLine(d)).toBe("+ TS “Refacto cache” in EPIC-3");
  });

  it("create_task → tâche rattachée à la story cible", () => {
    const d = makeDecision({
      action: "create_task",
      target_id: "US-7",
      payload: { title: "Ajouter un TTL" },
    });
    expect(decisionDiffLine(d)).toBe("+ task “Ajouter un TTL” in US-7");
  });

  it("create_epic", () => {
    const d = makeDecision({ action: "create_epic", payload: { title: "Observabilité" } });
    expect(decisionDiffLine(d)).toBe("+ epic “Observabilité”");
  });

  it("enrich_criteria → nombre d'AC ajoutés à la cible", () => {
    const d = makeDecision({
      action: "enrich_criteria",
      target_id: "US-7",
      payload: { acceptance_criteria: ["AC un", "AC deux"] },
    });
    expect(decisionDiffLine(d)).toBe("2 AC added to US-7");
  });

  it("update_story → champs modifiés", () => {
    const d = makeDecision({
      action: "update_story",
      target_id: "US-4",
      payload: { description: "Nouvelle description", priority: 1 },
    });
    expect(decisionDiffLine(d)).toBe("US-4 updated (description, priority)");
  });

  it("defer / persist / dismiss", () => {
    expect(
      decisionDiffLine(makeDecision({ action: "defer", payload: { title: "Idée cache" } })),
    ).toBe("deferred as pending idea (“Idée cache”)");
    expect(decisionDiffLine(makeDecision({ action: "persist", payload: {} }))).toBe(
      "persisted to memory only",
    );
    expect(decisionDiffLine(makeDecision({ action: "dismiss", payload: {} }))).toBe(
      "dismissed",
    );
  });
});

describe("GovernancePanel (US-F7.3)", () => {
  it("ne rend rien sans décision (flag OFF → panneau invisible)", () => {
    const { container } = renderPanel([]);
    expect(container.firstChild).toBeNull();
  });

  it("décision proposée : diff, rationale, observation source et actions", () => {
    renderPanel([makeDecision()]);
    expect(screen.getByText("+ US “Brancher Redis” in EPIC-3")).toBeInTheDocument();
    expect(screen.getByText(/Dette bloquante/)).toBeInTheDocument();
    expect(screen.getByText(/OBS-1 — Cache maison au lieu de Redis/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/ })).toBeInTheDocument();
  });

  it("Approuver appelle onApprove avec l'id de la décision", () => {
    const { onApprove, onReject } = renderPanel([makeDecision()]);
    fireEvent.click(screen.getByRole("button", { name: /Approve/ }));
    expect(onApprove).toHaveBeenCalledWith("GOV-1");
    expect(onReject).not.toHaveBeenCalled();
  });

  it("Rejeter demande un motif puis appelle onReject(id, motif)", () => {
    const { onReject } = renderPanel([makeDecision()]);
    fireEvent.click(screen.getByRole("button", { name: /Reject/ }));
    const input = screen.getByPlaceholderText(/Rejection reason/);
    fireEvent.change(input, { target: { value: "Trop tôt" } });
    fireEvent.click(screen.getByRole("button", { name: /Confirm rejection/ }));
    expect(onReject).toHaveBeenCalledWith("GOV-1", "Trop tôt");
  });

  it("annuler le rejet referme la saisie sans appeler onReject", () => {
    const { onReject } = renderPanel([makeDecision()]);
    fireEvent.click(screen.getByRole("button", { name: /Reject/ }));
    fireEvent.click(screen.getByRole("button", { name: /Cancel/ }));
    expect(screen.queryByPlaceholderText(/Rejection reason/)).not.toBeInTheDocument();
    expect(onReject).not.toHaveBeenCalled();
  });

  it("journal : les décisions traitées affichent statut final et rationale", () => {
    renderPanel([
      makeDecision({ id: "GOV-2", status: "applied", rationale: "Approuvée en itér. 1" }),
      makeDecision({
        id: "GOV-3",
        status: "rejected_by_human",
        action: "dismiss",
        payload: {},
        rationale: "Pas pertinent",
      }),
    ]);
    // Pas de file d'attente : aucune décision « proposed ».
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
    expect(screen.getByText("applied")).toBeInTheDocument();
    expect(screen.getByText("rejected (human)")).toBeInTheDocument();
    expect(screen.getByText(/Approuvée en itér\. 1/)).toBeInTheDocument();
    expect(screen.getByText(/Pas pertinent/)).toBeInTheDocument();
  });
});
