import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DepGraphPanel } from "./DepGraphPanel";
import { Epic, Stream, UserStory } from "../types";

const STREAMS: Stream[] = [
  { id: "backend", kind: "backend", language: "python", toolchain: "", file_root: "", primary: true },
];

const EPICS: Epic[] = [
  { id: "E1", title: "Epic un", description: "", iteration: 1 },
];

function story(o: Partial<UserStory> = {}): UserStory {
  return {
    id: "US-1",
    epic_id: "E1",
    title: "US",
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
    quality_score: -1,
    ...o,
  };
}

const STORIES = [story({ id: "US-1" }), story({ id: "US-2", depends_on: ["US-1"] })];

describe("DepGraphPanel (vue graphe hiérarchique React Flow)", () => {
  it("ne rend rien sans éléments", () => {
    const { container } = render(
      <DepGraphPanel epics={[]} stories={[]} streams={STREAMS} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("tout est replié par défaut : l'epic est visible, pas ses US", () => {
    render(<DepGraphPanel epics={EPICS} stories={STORIES} streams={STREAMS} />);
    expect(screen.getByTestId("dag-summary")).toBeTruthy();
    expect(screen.getByTestId("dag-node-E1")).toBeTruthy();
    expect(screen.queryByTestId("dag-node-US-1")).toBeNull();
  });

  it("« tout déplier » montre les US, « tout replier » les cache", () => {
    render(<DepGraphPanel epics={EPICS} stories={STORIES} streams={STREAMS} />);
    fireEvent.click(screen.getByTestId("dag-expand-all"));
    expect(screen.getByTestId("dag-group-E1")).toBeTruthy();
    expect(screen.getByTestId("dag-node-US-1")).toBeTruthy();
    fireEvent.click(screen.getByTestId("dag-collapse-all"));
    expect(screen.queryByTestId("dag-node-US-1")).toBeNull();
    expect(screen.getByTestId("dag-node-E1")).toBeTruthy();
  });

  it("le chevron déplie/replie un seul conteneur", () => {
    render(<DepGraphPanel epics={EPICS} stories={STORIES} streams={STREAMS} />);
    fireEvent.click(screen.getByTestId("dag-toggle-E1"));
    expect(screen.getByTestId("dag-node-US-2")).toBeTruthy();
    fireEvent.click(screen.getByTestId("dag-toggle-E1"));
    expect(screen.queryByTestId("dag-node-US-2")).toBeNull();
  });

  it("double-clic sur une US ouvre la vision produit ; sur une epic, l'epic", () => {
    const onOpenItem = vi.fn();
    const onOpenEpic = vi.fn();
    render(
      <DepGraphPanel
        epics={EPICS}
        stories={STORIES}
        streams={STREAMS}
        onOpenItem={onOpenItem}
        onOpenEpic={onOpenEpic}
      />,
    );
    fireEvent.doubleClick(screen.getByTestId("dag-node-E1"));
    expect(onOpenEpic).toHaveBeenCalledWith("E1");
    fireEvent.click(screen.getByTestId("dag-expand-all"));
    fireEvent.doubleClick(screen.getByTestId("dag-node-US-2"));
    expect(onOpenItem).toHaveBeenCalledWith("US-2");
  });

  it("focus sur une epic puis retour à la vue projet", () => {
    render(<DepGraphPanel epics={EPICS} stories={STORIES} streams={STREAMS} />);
    fireEvent.click(screen.getByTestId("dag-focus-E1"));
    // Le focus ouvre l'élément : ses US deviennent visibles.
    expect(screen.getByTestId("dag-group-E1")).toBeTruthy();
    expect(screen.getByTestId("dag-node-US-1")).toBeTruthy();
    fireEvent.click(screen.getByTestId("dag-back"));
    expect(screen.queryByTestId("dag-back")).toBeNull();
    expect(screen.getByTestId("dag-node-E1")).toBeTruthy();
  });
});
