import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { AgentInteraction } from "../types";

const getItemInteractions = vi.fn();

vi.mock("../api", async (importActual) => ({
  ...(await importActual<typeof import("../api")>()),
  getItemInteractions: (...a: unknown[]) => getItemInteractions(...a),
}));

import { LlmActivity } from "./LlmActivity";

function call(overrides: Partial<AgentInteraction> = {}): AgentInteraction {
  return {
    id: "call-1",
    item_id: "US-1",
    phase: "build",
    persona: "dev",
    prompt: "Implémente la story",
    response: '{"status":"green"}',
    ok: true,
    error: "",
    input_tokens: 1200,
    output_tokens: 340,
    cost_usd: 0.0123,
    duration_ms: 4200,
    prompt_truncated: false,
    response_truncated: false,
    ts: 1781226000,
    ...overrides,
  };
}

describe("LlmActivity", () => {
  beforeEach(() => {
    getItemInteractions.mockReset();
  });

  it("liste les appels (récents en premier) et affiche le rôle d'agent", async () => {
    getItemInteractions.mockResolvedValue([
      call({ id: "call-1", persona: "qa", prompt: "Plan de test" }),
      call({ id: "call-2", persona: "dev", prompt: "Implémente" }),
    ]);
    render(<LlmActivity projectId="p1" itemId="US-1" />);

    await waitFor(() => expect(screen.getByTestId("llm-call-call-2")).toBeInTheDocument());
    expect(getItemInteractions).toHaveBeenCalledWith("p1", "US-1", 20);
    // Most recent (call-2 / dev) is rendered first and auto-expanded.
    const cards = screen.getAllByTestId(/^llm-call-call-/);
    expect(cards[0]).toHaveAttribute("data-testid", "llm-call-call-2");
    expect(screen.getByText("Implémente")).toBeInTheDocument(); // dev prompt shown (open)
  });

  it("révèle prompt et réponse au clic sur un appel replié", async () => {
    getItemInteractions.mockResolvedValue([
      call({ id: "call-1", prompt: "PROMPT-A", response: "REPONSE-A" }),
      call({ id: "call-2", prompt: "PROMPT-B", response: "REPONSE-B" }),
    ]);
    render(<LlmActivity projectId="p1" itemId="US-1" />);

    // call-1 is the older one -> collapsed by default.
    const head = await screen.findByTestId("llm-call-head-call-1");
    expect(screen.queryByText("PROMPT-A")).not.toBeInTheDocument();
    fireEvent.click(head);
    const card = screen.getByTestId("llm-call-call-1");
    expect(within(card).getByText("PROMPT-A")).toBeInTheDocument();
    expect(within(card).getByText("REPONSE-A")).toBeInTheDocument();
  });

  it("montre un état vide explicite", async () => {
    getItemInteractions.mockResolvedValue([]);
    render(<LlmActivity projectId="p1" itemId="US-9" />);
    await waitFor(() =>
      expect(screen.getByText(/No LLM call recorded/)).toBeInTheDocument(),
    );
  });

  it("marque un appel en échec", async () => {
    getItemInteractions.mockResolvedValue([
      call({ id: "call-x", ok: false, error: "timeout", response: "" }),
    ]);
    render(<LlmActivity projectId="p1" itemId="US-1" />);
    await waitFor(() => expect(screen.getByText("failed")).toBeInTheDocument());
    expect(screen.getByText("timeout")).toBeInTheDocument();
  });
});
