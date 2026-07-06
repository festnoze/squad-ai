import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Mock the api so the per-item actions/chat/extend don't hit the network.
const storyChat = vi.fn().mockResolvedValue({ ok: true, entry_id: "g-1" });
const taskChat = vi.fn().mockResolvedValue({ ok: true, entry_id: "g-1" });
const extendStory = vi.fn().mockResolvedValue({});
const rebuildStory = vi.fn().mockResolvedValue(undefined);

vi.mock("../api", async (importActual) => ({
  ...(await importActual<typeof import("../api")>()),
  storyChat: (...a: unknown[]) => storyChat(...a),
  taskChat: (...a: unknown[]) => taskChat(...a),
  extendStory: (...a: unknown[]) => extendStory(...a),
  rebuildStory: (...a: unknown[]) => rebuildStory(...a),
}));

import { Activity } from "./Activity";
import { Epic, ProjectTicks, UserStory } from "../types";

const epic = (id: string): Epic => ({ id, title: `Epic ${id}`, description: "", iteration: 1 });

function story(overrides: Partial<UserStory> = {}): UserStory {
  return {
    id: "US-1",
    epic_id: "E1",
    title: "Story one",
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

function renderActivity(props: Partial<React.ComponentProps<typeof Activity>> = {}) {
  return render(
    <Activity
      epics={[epic("E1")]}
      stories={[story()]}
      projectId="p1"
      phase="build"
      {...props}
    />,
  );
}

describe("Activity", () => {
  it("rend la région Activité avec un stepper par item", () => {
    renderActivity();
    expect(screen.getByRole("region", { name: "Activity" })).toBeInTheDocument();
    expect(screen.getByTestId("stepper-US-1")).toBeInTheDocument();
    expect(screen.getByTestId("activity-row-US-1")).toBeInTheDocument();
  });

  it("en-tête : compteurs + chip à-traiter persistant + stall reason", () => {
    const ticks: ProjectTicks = {
      ts: Math.floor(Date.now() / 1000),
      items: {},
      counts: { running: 1, queued: 2, done: 3, failed: 1, blocked: 1 },
      stallReason: "merge_lock_held:US-9",
    };
    renderActivity({ ticks });
    expect(screen.getByTestId("activity-counts")).toHaveTextContent("1 running");
    expect(screen.getByTestId("activity-counts")).toHaveTextContent("3 done");
    // failed (1) + blocked (1) = 2 à traiter
    expect(screen.getByTestId("attention-chip")).toHaveTextContent("2");
    expect(screen.getByTestId("stall-reason")).toHaveTextContent(/Merge in progress/);
  });

  it("région « à traiter » épinglée pour un item failed", () => {
    renderActivity({ stories: [story({ status: "failed" })] });
    const region = screen.getByTestId("attention-region");
    expect(within(region).getByTestId("activity-row-US-1")).toBeInTheDocument();
  });

  it("BUG11 : un item épinglé n'est PAS dupliqué dans la liste principale", () => {
    renderActivity({ stories: [story({ status: "failed" })] });
    // L'item failed est dans « À traiter » ; il ne doit apparaître qu'une fois au
    // total (sinon un second ActivityRow monte chat/menu/poller en double).
    expect(screen.getAllByTestId("activity-row-US-1")).toHaveLength(1);
    const main = screen.getByTestId("activity-rows");
    expect(within(main).queryByTestId("activity-row-US-1")).not.toBeInTheDocument();
  });

  it("le tick live est fusionné dans le stepper (étape active depuis le tick)", () => {
    const ticks: ProjectTicks = {
      ts: Math.floor(Date.now() / 1000),
      items: {
        "US-1": {
          id: "US-1",
          kind: "story",
          status: "in_progress",
          current_stage: "implementing",
          stage_started_at: 0,
          current_persona: "dev",
          recovery: { attempt: 0, max_attempts: 0, kind: "" },
        },
      },
      counts: { running: 1, queued: 0, done: 0, failed: 0, blocked: 0 },
      stallReason: "",
    };
    renderActivity({ ticks });
    expect(screen.getByTestId("stage-US-1-implementing")).toHaveAttribute(
      "data-state",
      "active",
    );
    expect(screen.getByTestId("activity-persona-US-1")).toBeInTheDocument();
  });

  it("les chips de compteurs filtrent les items par statut (toggle + tous)", () => {
    renderActivity({
      stories: [
        story({ id: "US-1", status: "in_progress" }),
        story({ id: "US-2", status: "done" }),
        story({ id: "US-3", status: "todo" }),
      ],
    });
    // « faits » ne montre que l'item done.
    fireEvent.click(screen.getByTestId("filter-done"));
    expect(screen.queryByTestId("activity-row-US-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("activity-row-US-2")).toBeInTheDocument();
    expect(screen.queryByTestId("activity-row-US-3")).not.toBeInTheDocument();
    // Re-clic sur le même chip = retour à « tous ».
    fireEvent.click(screen.getByTestId("filter-done"));
    expect(screen.getByTestId("activity-row-US-1")).toBeInTheDocument();
    // « en cours » ne montre que l'item in_progress.
    fireEvent.click(screen.getByTestId("filter-running"));
    expect(screen.getByTestId("activity-row-US-1")).toBeInTheDocument();
    expect(screen.queryByTestId("activity-row-US-2")).not.toBeInTheDocument();
    // « en file » ne montre que le todo non bloqué.
    fireEvent.click(screen.getByTestId("filter-queued"));
    expect(screen.getByTestId("activity-row-US-3")).toBeInTheDocument();
    expect(screen.queryByTestId("activity-row-US-1")).not.toBeInTheDocument();
    // « tous » réinitialise.
    fireEvent.click(screen.getByTestId("filter-all"));
    expect(screen.getByTestId("activity-row-US-1")).toBeInTheDocument();
    expect(screen.getByTestId("activity-row-US-2")).toBeInTheDocument();
    expect(screen.getByTestId("activity-row-US-3")).toBeInTheDocument();
  });

  it("le chip « à traiter » filtre sur les items failed/bloqués", () => {
    renderActivity({
      stories: [
        story({ id: "US-1", status: "failed" }),
        story({ id: "US-2", status: "todo" }),
      ],
    });
    fireEvent.click(screen.getByTestId("attention-chip"));
    expect(screen.getByTestId("activity-row-US-1")).toBeInTheDocument();
    expect(screen.queryByTestId("activity-row-US-2")).not.toBeInTheDocument();
  });

  it("chat ciblé par item : envoie une consigne via storyChat", async () => {
    renderActivity();
    fireEvent.click(screen.getByTestId("activity-toggle-US-1"));
    const input = screen.getByTestId("item-chat-input-US-1");
    fireEvent.change(input, { target: { value: "Utilise une regex" } });
    fireEvent.click(screen.getByTestId("item-chat-send-US-1"));
    await waitFor(() =>
      expect(storyChat).toHaveBeenCalledWith("p1", "US-1", "Utilise une regex"),
    );
  });

  it("liste les consignes avec leur statut de livraison", () => {
    renderActivity({
      stories: [
        story({
          guidance: [
            { id: "g1", text: "Consigne A", ts: 1, status: "applied" },
            { id: "g2", text: "Consigne B", ts: 2, status: "too_late" },
          ],
        }),
      ],
    });
    fireEvent.click(screen.getByTestId("activity-toggle-US-1"));
    expect(screen.getByTestId("guidance-entry-g1")).toHaveAttribute(
      "data-status",
      "applied",
    );
    expect(screen.getByTestId("guidance-entry-g2")).toHaveTextContent(/too late/);
  });

  it("affordance « étendre les critères » sur un item TODO appelle extendStory", async () => {
    renderActivity({
      stories: [
        story({
          status: "todo",
          acceptance_criteria: [{ id: "c1", text: "existant" }],
        }),
      ],
    });
    fireEvent.click(screen.getByTestId("activity-toggle-US-1"));
    fireEvent.click(screen.getByTestId("extend-US-1"));
    fireEvent.change(screen.getByTestId("extend-input-US-1"), {
      target: { value: "nouveau critère" },
    });
    fireEvent.click(screen.getByTestId("extend-submit-US-1"));
    await waitFor(() =>
      expect(extendStory).toHaveBeenCalledWith("p1", "US-1", [
        "existant",
        "nouveau critère",
      ]),
    );
  });

  it("bannière d'approbation visible avec la gate string + bouton approuver", () => {
    const onApprove = vi.fn();
    renderActivity({ awaitingApproval: "spec-review", onApprove });
    const banner = screen.getByTestId("approval-banner-activity");
    expect(banner).toHaveTextContent("spec-review");
    fireEvent.click(within(banner).getByText(/Approve/));
    expect(onApprove).toHaveBeenCalled();
  });

  it("menu d'action par item : Relancer appelle rebuildStory", async () => {
    renderActivity({ stories: [story({ status: "failed" })] });
    // L'item failed apparaît dans la région à-traiter ET la liste : on cible la
    // première instance du menu.
    fireEvent.click(screen.getAllByTestId("activity-menu-US-1")[0]);
    fireEvent.click(screen.getAllByRole("menuitem", { name: /Restart/ })[0]);
    await waitFor(() => expect(rebuildStory).toHaveBeenCalledWith("p1", "US-1"));
  });

  it("Q5 : item failed avec last_error → CTA « Voir l'erreur » ouvre le tiroir avec l'erreur", () => {
    renderActivity({
      stories: [story({ status: "failed", last_error: "pytest: 2 tests failed\nAssertionError" })],
    });
    const cta = screen.getByTestId("view-error-US-1");
    expect(cta).toBeInTheDocument();
    fireEvent.click(cta);
    const block = screen.getByTestId("last-error-US-1");
    expect(block).toHaveTextContent("pytest: 2 tests failed");
  });

  it("Q5 : pas de CTA d'erreur sans last_error ou hors échec", () => {
    renderActivity({ stories: [story({ status: "done", last_error: "vieille erreur" })] });
    expect(screen.queryByTestId("view-error-US-1")).not.toBeInTheDocument();
  });

  it("Q1 : Escape ferme le menu d'actions d'un item", () => {
    renderActivity();
    fireEvent.click(screen.getByTestId("activity-menu-US-1"));
    expect(screen.getAllByRole("menuitem").length).toBeGreaterThan(0);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menuitem")).not.toBeInTheDocument();
  });
});
