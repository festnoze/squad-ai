import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const rebuildStory = vi.fn().mockResolvedValue(undefined);
const forceDoneStory = vi.fn().mockResolvedValue(undefined);

vi.mock("../api", async (importActual) => ({
  ...(await importActual<typeof import("../api")>()),
  rebuildStory: (...a: unknown[]) => rebuildStory(...a),
  forceDoneStory: (...a: unknown[]) => forceDoneStory(...a),
}));

import { CommandPalette, fuzzyScore, paletteItems } from "./CommandPalette";
import { ConfirmHost } from "./ConfirmDialog";
import { subscribeNav, type NavIntent } from "../navigation";
import { UserStory } from "../types";

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

function renderPalette(props: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
  const items = paletteItems([
    story({ id: "US-1", title: "Login screen", status: "failed" }),
    story({ id: "US-2", title: "Billing page", status: "todo" }),
  ]);
  return render(
    <>
      <ConfirmHost />
      <CommandPalette
        open
        onClose={vi.fn()}
        items={items}
        projectId="p1"
        hasProject
        hasGraph={false}
        multiIter={false}
        onNewProject={vi.fn()}
        onOpenDashboard={vi.fn()}
        onOpenSettings={vi.fn()}
        {...props}
      />
    </>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("fuzzyScore", () => {
  it("renvoie -1 sans match, l'index sinon (diacritiques ignorés)", () => {
    expect(fuzzyScore("Aller à Activité", "xyz")).toBe(-1);
    expect(fuzzyScore("Aller à Activité", "activite")).toBeGreaterThanOrEqual(0);
    expect(fuzzyScore("US-1", "us-1")).toBe(0);
  });
});

describe("CommandPalette (R2)", () => {
  it("filtre les commandes et lance une commande immédiate", () => {
    const onOpenSettings = vi.fn();
    renderPalette({ onOpenSettings });
    fireEvent.change(screen.getByLabelText(/Command palette input/), {
      target: { value: "settings" },
    });
    fireEvent.click(screen.getByTestId("palette-cmd-open-settings"));
    expect(onOpenSettings).toHaveBeenCalled();
  });

  it("verbe ciblé : « Retry » affiche un chip cible puis relance l'item choisi", async () => {
    const onClose = vi.fn();
    renderPalette({ onClose });
    fireEvent.click(screen.getByTestId("palette-cmd-retry"));
    expect(screen.getByTestId("palette-verb-chip")).toBeInTheDocument();
    // Les cibles (stories) sont listées ; on choisit US-2.
    fireEvent.click(screen.getByTestId("palette-target-US-2"));
    await waitFor(() => expect(rebuildStory).toHaveBeenCalledWith("p1", "US-2"));
    expect(onClose).toHaveBeenCalled();
  });

  it("verbe destructif « Force done » passe par la confirmation", async () => {
    renderPalette();
    fireEvent.click(screen.getByTestId("palette-cmd-force"));
    fireEvent.click(screen.getByTestId("palette-target-US-1"));
    // Dialogue de confirmation rendu ; on confirme.
    const accept = await screen.findByTestId("confirm-accept");
    fireEvent.click(accept);
    await waitFor(() => expect(forceDoneStory).toHaveBeenCalledWith("p1", "US-1"));
  });

  it("« Aller au prochain échec » dispatche une navigation vers l'item failed", () => {
    const intents: NavIntent[] = [];
    const off = subscribeNav((i) => intents.push(i));
    renderPalette();
    fireEvent.click(screen.getByTestId("palette-cmd-goto-next-failure"));
    expect(intents).toContainEqual({ type: "goto-item", storyId: "US-1" });
    off();
  });

  it("navigation clavier : ↓ puis Entrée lance la 2e commande sélectionnée", () => {
    const onOpenDashboard = vi.fn();
    const onOpenSettings = vi.fn();
    renderPalette({ onOpenDashboard, onOpenSettings });
    const input = screen.getByLabelText(/Command palette input/);
    // « Open » ne matche que « Open dashboard » (0) et « Open settings » (1).
    fireEvent.change(input, { target: { value: "Open" } });
    fireEvent.keyDown(input, { key: "ArrowDown" }); // sel 0 → 1 (settings)
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onOpenSettings).toHaveBeenCalled();
    expect(onOpenDashboard).not.toHaveBeenCalled();
  });

  it("sans projet : seules les commandes app sont proposées", () => {
    renderPalette({ hasProject: false, items: [] });
    expect(screen.queryByTestId("palette-cmd-retry")).not.toBeInTheDocument();
    expect(screen.getByTestId("palette-cmd-new-project")).toBeInTheDocument();
  });
});
