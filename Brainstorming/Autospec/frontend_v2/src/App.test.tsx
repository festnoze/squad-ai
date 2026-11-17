import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { mockFetch } from "./test/fetchMock";
import { makeProject, makeSummary } from "./test/fixtures";

const API = "/api/v2/projects";

function mockServer() {
  return mockFetch({
    [`GET ${API}`]: { body: [makeSummary()] },
    [`POST ${API}`]: { status: 201, body: makeSummary({ id: "notes-1", name: "Notes" }) },
    [`GET ${API}/todo-cli`]: { body: makeProject() },
    [`GET ${API}/todo-cli/files`]: { body: { files: [] } },
    [`GET ${API}/notes-1`]: { body: makeProject({ id: "notes-1", name: "Notes" }) },
    [`GET ${API}/notes-1/files`]: { body: { files: [] } },
  });
}

describe("App", () => {
  it("shows the project list by default and a project from its hash", async () => {
    mockServer();
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Projets" })).toBeTruthy();

    // jsdom applies the fragment navigation of a link click asynchronously.
    fireEvent.click(screen.getByRole("link", { name: "Todo CLI" }));
    await waitFor(() => expect(window.location.hash).toBe("#/projects/todo-cli"));
    expect(await screen.findByRole("heading", { level: 1, name: "Todo CLI" })).toBeTruthy();

    fireEvent.click(screen.getByRole("link", { name: "← Projets" }));
    await waitFor(() => expect(window.location.hash).toBe("#/"));
    expect(await screen.findByRole("heading", { level: 1, name: "Projets" })).toBeTruthy();
  });

  it("shows the project list for a hash that names no possible project", async () => {
    const mock = mockServer();
    window.location.hash = "#/projects/..";
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Projets" })).toBeTruthy();
    expect(new Set(mock.calls.map((call) => call.path))).toEqual(new Set([API])); // nothing but the list
  });

  it("shows an error instead of a blank page when a response has an unexpected shape", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {}); // React reports the caught error
    const mock = mockServer();
    mock.routes[`GET ${API}/todo-cli`] = { body: [makeSummary()] }; // a list where a project is expected
    window.location.hash = "#/projects/todo-cli";
    render(<App />);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("heading", { name: "Cette page a rencontré une erreur" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Autospec/ })).toBeTruthy(); // the shell is still there

    fireEvent.click(within(alert).getByRole("link", { name: "Retour aux projets" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Projets" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("opens a project once it is created", async () => {
    const mock = mockServer();
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: "Projets" });

    fireEvent.change(screen.getByLabelText("Nom"), { target: { value: "Notes" } });
    fireEvent.change(screen.getByLabelText("Brief"), { target: { value: "une API de notes" } });
    fireEvent.click(screen.getByRole("button", { name: "Créer et lancer" }));

    await waitFor(() => expect(window.location.hash).toBe("#/projects/notes-1"));
    expect(await screen.findByRole("heading", { level: 1, name: "Notes" })).toBeTruthy();
    expect(mock.callsTo("POST", API)[0].body).toEqual({ name: "Notes", brief: "une API de notes" });
  });
});
