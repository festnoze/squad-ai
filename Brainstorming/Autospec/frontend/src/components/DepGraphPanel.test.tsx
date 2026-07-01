import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DepGraphPanel } from "./DepGraphPanel";
import { Stream, UserStory } from "../types";

const STREAMS: Stream[] = [
  { id: "backend", kind: "backend", language: "python", toolchain: "", file_root: "", primary: true },
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

describe("DepGraphPanel (vue graphe DAG)", () => {
  it("ne rend rien sans éléments", () => {
    const { container } = render(<DepGraphPanel stories={[]} streams={STREAMS} />);
    expect(container.firstChild).toBeNull();
  });

  it("rend les nœuds + le résumé et ouvre la story au clic", () => {
    const onOpenItem = vi.fn();
    render(
      <DepGraphPanel
        stories={[story({ id: "US-1" }), story({ id: "US-2", depends_on: ["US-1"] })]}
        streams={STREAMS}
        onOpenItem={onOpenItem}
      />,
    );
    expect(screen.getByTestId("dag-summary")).toBeTruthy();
    expect(screen.getByTestId("dag-node-US-1")).toBeTruthy();
    fireEvent.click(screen.getByTestId("dag-node-US-2"));
    expect(onOpenItem).toHaveBeenCalledWith("US-2");
  });

  it("met en évidence le chemin critique", () => {
    const { container } = render(
      <DepGraphPanel
        stories={[story({ id: "US-1" }), story({ id: "US-2", depends_on: ["US-1"] })]}
        streams={STREAMS}
      />,
    );
    expect(container.querySelector(".dag-node-crit")).toBeTruthy();
  });
});
