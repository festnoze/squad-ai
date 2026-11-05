import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { mockFetch } from "../test/fetchMock";
import { makeSummary } from "../test/fixtures";
import { ProjectsPage } from "./ProjectsPage";

describe("ProjectsPage", () => {
  it("renders every project with its phase, progress and cost", async () => {
    mockFetch({
      "GET /api/v2/projects": {
        body: [
          makeSummary(),
          makeSummary({
            id: "slugify",
            name: "Slugify",
            profile: "lib",
            phase: "done",
            running: false,
            stories_done: 1,
            stories_total: 1,
            cost_usd: 0.18,
          }),
          makeSummary({ id: "notes", name: "Notes", profile: null, phase: "error", running: false, error: "boom" }),
        ],
      },
    });
    render(<ProjectsPage onCreated={vi.fn()} />);

    const link = await screen.findByRole("link", { name: "Todo CLI" });
    expect(link.getAttribute("href")).toBe("#/projects/todo-cli");

    const rows = screen.getAllByRole("row").slice(1); // skip the header row
    expect(rows).toHaveLength(3);
    const first = within(rows[0]);
    expect(first.getByText("Construction")).toBeTruthy();
    expect(first.getByText("en cours")).toBeTruthy();
    expect(first.getByText("2/5")).toBeTruthy();
    expect(first.getByText(/0,38/)).toBeTruthy();
    expect(first.getByLabelText("2 stories terminées sur 5")).toBeTruthy();

    const second = within(rows[1]);
    expect(second.getByText("Terminé")).toBeTruthy();
    expect(second.queryByText("en cours")).toBeNull();
    expect(second.getByText("1/1")).toBeTruthy();

    const third = within(rows[2]);
    expect(third.getByText("Erreur")).toBeTruthy();
    expect(third.getByText("(erreur)").getAttribute("title")).toBe("boom");

    // The creation form sits on the same screen.
    expect(screen.getByRole("form", { name: "Nouveau projet" })).toBeTruthy();
  });

  it("shows an empty state", async () => {
    mockFetch({ "GET /api/v2/projects": { body: [] } });
    render(<ProjectsPage onCreated={vi.fn()} />);
    expect(await screen.findByText(/Aucun projet pour l'instant/)).toBeTruthy();
  });

  it("reports a server that cannot be reached", async () => {
    mockFetch({ "GET /api/v2/projects": { status: 502 } });
    render(<ProjectsPage onCreated={vi.fn()} />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Erreur HTTP 502");
  });

  it("refreshes the list on demand", async () => {
    const mock = mockFetch({ "GET /api/v2/projects": { body: [] } });
    render(<ProjectsPage onCreated={vi.fn()} refreshMs={60_000} />);
    await screen.findByText(/Aucun projet/);
    mock.routes["GET /api/v2/projects"] = { body: [makeSummary({ name: "Nouveau" })] };
    fireEvent.click(screen.getByRole("button", { name: "Actualiser" }));
    expect(await screen.findByRole("link", { name: "Nouveau" })).toBeTruthy();
  });
});
