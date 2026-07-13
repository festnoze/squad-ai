import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { KnowledgeBase } from "../types";

// Mock du client API : le panneau charge la base via getKnowledge et
// édite/supprime via patchKnowledgeEntry / deleteKnowledgeEntry.
vi.mock("../api", () => ({
  errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  getKnowledge: vi.fn(),
  patchKnowledgeEntry: vi.fn().mockResolvedValue({}),
  deleteKnowledgeEntry: vi.fn().mockResolvedValue(undefined),
}));

import { deleteKnowledgeEntry, getKnowledge, patchKnowledgeEntry } from "../api";
import { KnowledgePanel } from "./KnowledgePanel";

const getKnowledgeMock = vi.mocked(getKnowledge);

function makeKb(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    component_memory: {
      backend: [
        {
          id: "mem-1",
          text: "Le cache est un dict Python avec TTL",
          kind: "constraint",
          source_observation_id: "OBS-1",
          iteration: 1,
          created_at: 1,
        },
      ],
    },
    architecture_notes: [
      {
        id: "mem-2",
        text: "API REST versionnée /api/v1",
        kind: "",
        source_observation_id: "",
        iteration: 1,
        created_at: 1,
      },
    ],
    adrs: [
      {
        id: "adr-1",
        title: "Utiliser FastAPI",
        decision: "FastAPI retenu pour l'async natif",
        context: "Le backend est fortement I/O bound",
        status: "accepted",
        source_observation_id: "OBS-2",
        iteration: 1,
        created_at: 1,
      },
    ],
    debt_register: [
      {
        id: "debt-1",
        title: "Cache non persistant",
        detail: "Perdu au redémarrage",
        effort_estimate: "1 j",
        interest: "s'aggrave si le trafic augmente",
        urgency: "high",
        source_observation_id: "OBS-1",
        iteration: 1,
        created_at: 1,
      },
    ],
    risk_register: [
      {
        id: "risk-1",
        title: "Fuite mémoire",
        detail: "Le cache croît sans borne",
        likelihood: "medium",
        mitigation: "Ajouter une éviction LRU",
        urgency: "normal",
        source_observation_id: "",
        iteration: 1,
        created_at: 1,
      },
    ],
    pending_ideas: [
      {
        id: "idea-1",
        title: "Mode hors-ligne",
        detail: "Un service worker",
        value_hint: "retention",
        reevaluate_when: "après la v1",
        source_observation_id: "OBS-3",
        iteration: 2,
        created_at: 1,
      },
    ],
    ...overrides,
  };
}

const EMPTY_KB: KnowledgeBase = {
  component_memory: {},
  architecture_notes: [],
  adrs: [],
  debt_register: [],
  risk_register: [],
  pending_ideas: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("KnowledgePanel (US-F7.4)", () => {
  it("base vide → panneau invisible (flag OFF, pas de crash)", async () => {
    getKnowledgeMock.mockResolvedValue(EMPTY_KB);
    const { container } = render(<KnowledgePanel projectId="p1" />);
    await waitFor(() => expect(getKnowledgeMock).toHaveBeenCalledWith("p1"));
    expect(container.firstChild).toBeNull();
  });

  it("erreur de chargement → panneau muet (backend sans l'endpoint)", async () => {
    getKnowledgeMock.mockRejectedValue(new Error("Erreur 404 : Projet inconnu"));
    const { container } = render(<KnowledgePanel projectId="p1" />);
    await waitFor(() => expect(getKnowledgeMock).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it("affiche les onglets avec compteurs et l'onglet ADRs par défaut", async () => {
    getKnowledgeMock.mockResolvedValue(makeKb());
    render(<KnowledgePanel projectId="p1" />);
    expect(await screen.findByText("Utiliser FastAPI")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /ADRs/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Debt/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Risks/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Pending ideas/ })).toBeInTheDocument();
    // Notes & memory : 1 note archi + 1 mémoire composant = compteur 2.
    expect(screen.getByRole("tab", { name: /Notes & memory/ })).toHaveTextContent("2");
    expect(screen.getByText(/FastAPI retenu pour l'async natif/)).toBeInTheDocument();
  });

  it("change d'onglet : Dette puis Notes & mémoire composant", async () => {
    getKnowledgeMock.mockResolvedValue(makeKb());
    render(<KnowledgePanel projectId="p1" />);
    await screen.findByText("Utiliser FastAPI");
    fireEvent.click(screen.getByRole("tab", { name: /Debt/ }));
    expect(screen.getByText("Cache non persistant")).toBeInTheDocument();
    expect(screen.getByText(/s'aggrave si le trafic augmente/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Notes & memory/ }));
    expect(screen.getByText(/Component memory — backend/)).toBeInTheDocument();
    expect(screen.getByText(/dict Python avec TTL/)).toBeInTheDocument();
    expect(screen.getByText(/API REST versionnée/)).toBeInTheDocument();
  });

  it("lien vers l'observation source (résumé inline quand connue)", async () => {
    getKnowledgeMock.mockResolvedValue(makeKb());
    render(
      <KnowledgePanel
        projectId="p1"
        observations={[
          {
            id: "OBS-2",
            type: "constraint",
            summary: "Backend I/O bound",
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
            status: "persisted",
            routed_to: "architecture",
            resolution: "",
            merged_count: 0,
          },
        ]}
      />,
    );
    await screen.findByText("Utiliser FastAPI");
    expect(screen.getByText(/OBS-2 — Backend I\/O bound/)).toBeInTheDocument();
  });

  it("édition d'une entrée → PATCH avec les champs modifiés puis rechargement", async () => {
    getKnowledgeMock.mockResolvedValue(makeKb());
    render(<KnowledgePanel projectId="p1" />);
    await screen.findByText("Utiliser FastAPI");
    fireEvent.click(screen.getByRole("button", { name: /Edit this entry adr-1/ }));
    fireEvent.change(screen.getByLabelText("title"), {
      target: { value: "Utiliser FastAPI partout" },
    });
    fireEvent.change(screen.getByLabelText("Edit"), {
      target: { value: "FastAPI + uvicorn" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save/ }));
    await waitFor(() =>
      expect(patchKnowledgeEntry).toHaveBeenCalledWith("p1", "adrs", "adr-1", {
        decision: "FastAPI + uvicorn",
        title: "Utiliser FastAPI partout",
      }),
    );
    // Rechargement après édition (2 appels : montage + reload).
    await waitFor(() => expect(getKnowledgeMock).toHaveBeenCalledTimes(2));
  });

  it("suppression d'une entrée → DELETE puis rechargement", async () => {
    getKnowledgeMock.mockResolvedValue(makeKb());
    // Sans <ConfirmHost/>, confirmAction retombe sur window.confirm.
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<KnowledgePanel projectId="p1" />);
    await screen.findByText("Utiliser FastAPI");
    fireEvent.click(screen.getByRole("tab", { name: /Pending ideas/ }));
    fireEvent.click(screen.getByRole("button", { name: /Delete this entry idea-1/ }));
    await waitFor(() =>
      expect(deleteKnowledgeEntry).toHaveBeenCalledWith("p1", "pending_ideas", "idea-1"),
    );
    await waitFor(() => expect(getKnowledgeMock).toHaveBeenCalledTimes(2));
    confirmSpy.mockRestore();
  });

  it("refreshKey déclenche un refetch (mise à jour live US-F7.5)", async () => {
    getKnowledgeMock.mockResolvedValue(makeKb());
    const { rerender } = render(<KnowledgePanel projectId="p1" refreshKey={0} />);
    await screen.findByText("Utiliser FastAPI");
    rerender(<KnowledgePanel projectId="p1" refreshKey={1} />);
    await waitFor(() => expect(getKnowledgeMock).toHaveBeenCalledTimes(2));
  });
});
