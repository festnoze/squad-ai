import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { makeProject, makeStory } from "../test/fixtures";
import { StoriesTable } from "./StoriesTable";

const stories = makeProject().stories;

describe("StoriesTable", () => {
  it("lists every story with its status and attempts", () => {
    render(<StoriesTable stories={stories} onShowDiff={vi.fn()} />);
    const rows = screen.getAllByRole("row").slice(1); // skip the header row
    expect(rows).toHaveLength(2);
    const first = within(rows[0]);
    expect(first.getByRole("rowheader").textContent).toBe("US-1");
    expect(first.getByText("Ajouter une tâche")).toBeTruthy();
    expect(first.getByText("Terminée")).toBeTruthy();
    const second = within(rows[1]);
    expect(second.getByText("En cours")).toBeTruthy();
    expect(second.getByRole("cell", { name: "2" })).toBeTruthy(); // attempts
  });

  it("expands the criteria of a story with their acceptance nodeids", () => {
    render(<StoriesTable stories={stories} onShowDiff={vi.fn()} />);
    const toggle = screen.getByRole("button", { name: "2 critères de US-1" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("list", { name: "Critères de US-1" })).toBeNull();

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const criteria = screen.getByRole("list", { name: "Critères de US-1" });
    expect(within(criteria).getByText("add enregistre la tâche")).toBeTruthy();
    const nodeids = within(screen.getByRole("list", { name: "Tests d'acceptance de US-1.AC-1" }));
    expect(nodeids.getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "tests/acceptance/test_us_1.py::test_ac1_add",
      "tests/acceptance/test_us_1.py::test_ac1_add_twice",
    ]);
    // US-1.AC-2 has no test yet.
    expect(within(criteria).getByText("Pas encore de test d'acceptance.")).toBeTruthy();

    fireEvent.click(toggle);
    expect(screen.queryByRole("list", { name: "Critères de US-1" })).toBeNull();
  });

  it("shows the dependencies and the last error of an expanded story", () => {
    render(<StoriesTable stories={stories} onShowDiff={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "1 critère de US-2" }));
    expect(screen.getByText("Dépend de : US-1")).toBeTruthy();
    expect(screen.getByText("AssertionError: expected 0, got 1")).toBeTruthy();
  });

  it("merges the nodeids of a criterion mapped twice", () => {
    const story = makeStory({
      acceptance_tests: [
        { ac_id: "US-1.AC-1", nodeids: ["tests/acceptance/test_us_1.py::a"] },
        { ac_id: "US-1.AC-1", nodeids: ["frontend/src/acceptance/us_1.test.tsx::counter > b"] },
      ],
    });
    render(<StoriesTable stories={[story]} onShowDiff={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "2 critères de US-1" }));
    const nodeids = within(screen.getByRole("list", { name: "Tests d'acceptance de US-1.AC-1" }));
    expect(nodeids.getAllByRole("listitem")).toHaveLength(2);
  });

  it("asks for the diff of a story", () => {
    const onShowDiff = vi.fn();
    render(<StoriesTable stories={stories} selectedDiff="US-2" onShowDiff={onShowDiff} />);
    expect(screen.getByRole("button", { name: "Voir le diff de US-2" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Voir le diff de US-1" }));
    expect(onShowDiff).toHaveBeenCalledWith("US-1");
  });

  it("says when there is no plan yet", () => {
    render(<StoriesTable stories={[]} onShowDiff={vi.fn()} />);
    expect(screen.getByText(/Aucune story pour l'instant/)).toBeTruthy();
  });
});
